"""Claude-based release-notes extractor.

Sends a release-notes PDF (plus pre-extracted images) to Claude via tool-use.
Claude calls ``save_release_note_item`` once per AM item in document order.
We validate each tool call and assemble a :class:`ReleaseNoteRecord`.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.integrations.claude.client import ClaudeClient, ClaudeExtractionError
from app.integrations.pdf.image_extractor import ImageManifest
from app.state.release_notes_models import (
    CodeBlock,
    ExtractionUsage,
    HeadingBlock,
    ImageBlock,
    ListBlock,
    ParagraphBlock,
    ReleaseNoteItem,
    ReleaseNoteRecord,
    TableBlock,
)

logger = logging.getLogger("claude.extractor")

EXTRACTOR_NAME = "claude"
EXTRACTOR_VERSION = 1

AM_CARD_RE = re.compile(r"^AM\d{2,5}$")
IMAGE_ID_RE = re.compile(r"^p\d+_img\d+$")


# ───── Public API ────────────────────────────────────────────────────────


def extract_release_note(
    pdf_path: Path | str,
    manifest: ImageManifest,
    *,
    version: str,
    claude_client: ClaudeClient | None = None,
) -> ReleaseNoteRecord:
    """Extract structured release-note items from a PDF via Claude.

    Parameters
    ----------
    pdf_path:
        Path to the release-notes PDF on disk.
    manifest:
        Image manifest produced by :func:`extract_images` (Block 1).
    version:
        The release version string (e.g. ``"8.0.18.1"``).
    claude_client:
        Optional pre-built client.  When ``None``, one is created from
        application settings.

    Returns
    -------
    ReleaseNoteRecord
        Fully validated record ready for persistence via the store.

    Raises
    ------
    ClaudeExtractionError
        On API failure or if zero valid items are extracted.
    """
    pdf_path = Path(pdf_path)
    pdf_bytes = pdf_path.read_bytes()
    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()

    if claude_client is None:
        claude_client = ClaudeClient.from_settings(settings)

    content_blocks = _build_user_message(pdf_path, pdf_bytes, manifest)
    tool_def = _build_tool_schema()
    system_prompt = _build_system_prompt()

    logger.info("Extracting release note for %s from %s", version, pdf_path.name)

    tool_calls, stop_reason, usage_info = claude_client.send_extraction(
        content_blocks, [tool_def], system_prompt,
    )

    if stop_reason == "max_tokens":
        logger.warning(
            "Claude hit max_tokens — extraction may be incomplete (%d items received so far)",
            len(tool_calls),
        )

    # Validate each tool call
    valid_image_ids = {img.id for img in manifest.images if not img.chrome}
    items: list[ReleaseNoteItem] = []

    for i, tc in enumerate(tool_calls):
        if tc["name"] != "save_release_note_item":
            logger.warning("Unexpected tool call %r (index %d), skipping", tc["name"], i)
            continue
        try:
            item = _validate_item(tc["input"], valid_image_ids)
            items.append(item)
        except (ValueError, KeyError) as exc:
            logger.warning("Skipping invalid item at index %d: %s", i, exc)

    if not items:
        raise ClaudeExtractionError(
            f"Extraction produced no valid items from {len(tool_calls)} tool call(s)",
        )

    logger.info("Extracted %d valid item(s) from %s", len(items), pdf_path.name)

    return ReleaseNoteRecord(
        version=version,
        extracted_at=datetime.now(timezone.utc),
        extractor=EXTRACTOR_NAME,
        extractor_version=EXTRACTOR_VERSION,
        source_pdf_path=str(pdf_path),
        source_pdf_hash=pdf_hash,
        source_pdf_pages=manifest.source_pdf_pages,
        usage=ExtractionUsage(**usage_info),
        items=items,
    )


# ───── User message builder ─────────────────────────────────────────────


def _build_user_message(
    pdf_path: Path,
    pdf_bytes: bytes,
    manifest: ImageManifest,
) -> list[dict]:
    """Build the content blocks for the user message.

    Contains: PDF document block, non-chrome image blocks, manifest text.
    """
    blocks: list[dict] = []

    # 1. PDF document block
    blocks.append({
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": base64.standard_b64encode(pdf_bytes).decode("ascii"),
        },
    })

    # 2. Non-chrome image blocks
    images_dir = pdf_path.parent / "images"
    content_images = [img for img in manifest.images if not img.chrome]

    for img in content_images:
        img_file = images_dir / f"{img.id}.png"
        if not img_file.exists():
            logger.warning("Image file missing for %s, skipping from message", img.id)
            continue
        img_bytes = img_file.read_bytes()
        blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.standard_b64encode(img_bytes).decode("ascii"),
            },
        })

    # 3. Manifest text — lists valid image IDs for Claude to reference
    manifest_lines = ["Image manifest (use these exact IDs in image blocks):"]
    for img in content_images:
        img_file = images_dir / f"{img.id}.png"
        if not img_file.exists():
            continue
        manifest_lines.append(
            f"  {img.id} — page {img.page}, {img.width_px}×{img.height_px} px"
        )
    manifest_lines.append("")
    manifest_lines.append(
        "When you reference an image from the PDF, match it visually against "
        "the image blocks above and use the exact ID. Never invent IDs. "
        "Never reference an image that isn't in this list."
    )
    blocks.append({
        "type": "text",
        "text": "\n".join(manifest_lines),
        "cache_control": {"type": "ephemeral"},
    })

    logger.debug(
        "Built user message: 1 PDF + %d image blocks + manifest text",
        len(content_images),
    )
    return blocks


# ───── Tool schema ───────────────────────────────────────────────────────


def _build_tool_schema() -> dict:
    """Return the ``save_release_note_item`` tool definition.

    Uses a flat body-block schema with ``additionalProperties: true`` —
    Claude handles flat schemas with good descriptions better than nested
    ``oneOf``.  Per-type field validation happens in :func:`_validate_item`.
    """
    return {
        "name": "save_release_note_item",
        "description": (
            "Save one release-note item (one AM card). "
            "Call this tool once per item, in document order."
        ),
        "input_schema": {
            "type": "object",
            "required": ["section", "am_card", "customers", "title", "summary", "body"],
            "properties": {
                "section": {
                    "type": "string",
                    "description": (
                        "Verbatim section heading from the PDF "
                        "(e.g. 'New Features', 'Defect Fixes', 'Not Tested')."
                    ),
                },
                "am_card": {
                    "type": "string",
                    "pattern": r"^AM\d{2,5}$",
                    "description": (
                        "The AM card number (e.g. 'AM1393'). "
                        "Never invent one — skip items without an AM code."
                    ),
                },
                "customers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Customer codes associated with the item "
                        "(e.g. ['FFT', 'HAL']). Empty array if none."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": (
                        "Item title with AM card and customer codes stripped. "
                        "Single line, no trailing punctuation."
                    ),
                },
                "summary": {
                    "type": "string",
                    "description": (
                        "One short sentence (max ~20 words) paraphrasing what "
                        "this item changes. Do not copy the title."
                    ),
                },
                "body": {
                    "type": "array",
                    "description": (
                        "Body content blocks in reading order. Each block has a "
                        "'type' field. Types and their fields:\n"
                        "- paragraph: {type, text} — body text, verbatim from PDF\n"
                        "- heading: {type, level, text} — inline sub-label like "
                        "'Bug Description', 'After correction'. level is 1-4.\n"
                        "- image: {type, image_id, describes} — screenshot. "
                        "image_id must be from the manifest. describes is a "
                        "short phrase explaining what the screenshot shows.\n"
                        "- list: {type, ordered, items} — bulleted or numbered "
                        "list. ordered is bool, items is array of strings.\n"
                        "- table: {type, headers, rows} — data table. headers "
                        "is array of strings, rows is array of string arrays.\n"
                        "- code: {type, text} — raw machine-formatted text: "
                        "log lines, SQL, ACARS/AFTN messages, JSON, XML, "
                        "command output. Preserve line breaks."
                    ),
                    "items": {
                        "type": "object",
                        "required": ["type"],
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "paragraph", "heading", "image",
                                    "list", "table", "code",
                                ],
                            },
                        },
                        "additionalProperties": True,
                    },
                },
            },
            "additionalProperties": False,
        },
    }


# ───── System prompt ─────────────────────────────────────────────────────


def _build_system_prompt() -> str:
    """Return the system prompt with extraction rules."""
    return (
        "You are extracting structured data from a Cyberjet / CAE OpsComm "
        "release-notes PDF.\n\n"
        "Call the save_release_note_item tool once per AM item, in the order "
        "they appear in the document. Each item typically starts with a heading "
        "containing an AM code like 'AM1393'.\n\n"
        "Rules:\n"
        "- Walk the document top to bottom in real reading order.\n"
        "- The 'section' field is the top-level section heading (e.g. "
        "'New Features', 'Defect Fixes', 'Improvements', 'Not Tested'). "
        "Copy it verbatim from the PDF.\n"
        "- Extract the AM card number (e.g. 'AM1393') and customer codes "
        "(e.g. 'HAL', 'FFT') from the item heading. Strip both from the "
        "'title' field. An item can have multiple customer codes.\n"
        "- Never invent an AM card number. If an item has no AM code, skip "
        "it entirely.\n"
        "- The 'summary' field is a short (~20 word) paraphrase — do not "
        "copy the title.\n"
        "- For body blocks:\n"
        "  - Use 'paragraph' for regular body text. Copy verbatim.\n"
        "  - Use 'heading' for inline sub-labels like 'Bug Description', "
        "'After correction', 'Setting', 'Result'. Set level=3.\n"
        "  - Use 'image' for screenshots. Match each screenshot against the "
        "image manifest provided and use its exact ID. The 'describes' "
        "field should explain what the screenshot shows in context.\n"
        "  - Use 'list' when you see a real bulleted or numbered list — "
        "group all items into a single list block.\n"
        "  - Use 'table' for real data tables with headers and rows.\n"
        "  - Use 'code' for raw machine-formatted text: log lines, SQL "
        "queries, ACARS/AFTN messages, flight plan payloads, JSON, XML, "
        "command output. Preserve line breaks and spacing.\n"
        "- Skip page headers, footers, page numbers, the Cyberjet logo, "
        "and the cover page table of contents.\n"
        "- Do NOT transcribe text inside screenshots (UI labels, dialog "
        "buttons, form fields). Screenshots are image blocks only.\n"
    )


# ───── Validation ────────────────────────────────────────────────────────


def _validate_item(raw: dict, valid_image_ids: set[str]) -> ReleaseNoteItem:
    """Validate raw tool-call arguments and build a :class:`ReleaseNoteItem`.

    Raises :class:`ValueError` for fatal issues (bad ``am_card``).
    Non-fatal issues (unknown block type, invalid image ID) log a warning
    and skip the individual block.
    """
    am_card = raw["am_card"]
    if not AM_CARD_RE.match(am_card):
        raise ValueError(f"Invalid am_card: {am_card!r}")

    body_blocks = []
    for j, block in enumerate(raw.get("body", [])):
        btype = block.get("type")

        if btype == "paragraph":
            body_blocks.append(ParagraphBlock(text=block["text"]))

        elif btype == "heading":
            body_blocks.append(HeadingBlock(
                level=block.get("level", 3),
                text=block["text"],
            ))

        elif btype == "image":
            image_id = block.get("image_id", "")
            if not IMAGE_ID_RE.match(image_id):
                logger.warning("Invalid image_id format %r in body block %d, skipping", image_id, j)
                continue
            if image_id not in valid_image_ids:
                logger.warning("Unknown image_id %r in body block %d, skipping", image_id, j)
                continue
            body_blocks.append(ImageBlock(
                image_id=image_id,
                describes=block.get("describes", ""),
            ))

        elif btype == "list":
            body_blocks.append(ListBlock(
                ordered=block.get("ordered", False),
                items=block.get("items", []),
            ))

        elif btype == "table":
            body_blocks.append(TableBlock(
                headers=block.get("headers", []),
                rows=block.get("rows", []),
            ))

        elif btype == "code":
            body_blocks.append(CodeBlock(text=block["text"]))

        else:
            logger.warning("Unknown body block type %r at index %d, skipping", btype, j)

    return ReleaseNoteItem(
        section=raw["section"],
        am_card=am_card,
        customers=raw.get("customers", []),
        title=raw["title"],
        summary=raw["summary"],
        body=body_blocks,
    )
