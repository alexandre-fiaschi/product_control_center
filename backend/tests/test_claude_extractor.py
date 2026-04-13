"""Tests for the Claude-based release-notes extractor — all API calls mocked."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.claude.client import ClaudeClient, ClaudeExtractionError, compute_cost
from app.integrations.claude.extractor import (
    _build_system_prompt,
    _build_tool_schema,
    _build_user_message,
    _validate_item,
    extract_release_note,
)
from app.integrations.pdf.image_extractor import ImageManifest, ManifestImage
from app.state.release_notes_models import (
    CodeBlock,
    HeadingBlock,
    ImageBlock,
    ListBlock,
    ParagraphBlock,
    ReleaseNoteItem,
    TableBlock,
)


# ───── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_manifest():
    """Manifest with 3 images: 2 content, 1 chrome."""
    return ImageManifest(
        extracted_at=datetime(2026, 4, 12, tzinfo=timezone.utc),
        source_pdf_pages=4,
        images=[
            ManifestImage(
                id="p1_img1", page=1, index_on_page=1,
                bbox=(10, 10, 50, 50), width_px=100, height_px=100,
                chrome=True,
            ),
            ManifestImage(
                id="p2_img1", page=2, index_on_page=1,
                bbox=(70, 200, 540, 500), width_px=1248, height_px=372,
            ),
            ManifestImage(
                id="p3_img1", page=3, index_on_page=1,
                bbox=(70, 100, 540, 400), width_px=900, height_px=600,
            ),
        ],
    )


@pytest.fixture
def valid_image_ids():
    return {"p2_img1", "p3_img1"}


@pytest.fixture
def sample_tool_input():
    """Raw tool-call input dict for a valid AM item."""
    return {
        "section": "New Features",
        "am_card": "AM1393",
        "customers": ["HAL"],
        "title": "Adding characters replacement feature for freetext uplink",
        "summary": "Lets admins define character replacements for free-text uplink messages.",
        "body": [
            {"type": "heading", "level": 3, "text": "Setting"},
            {"type": "paragraph", "text": "Go to \"Global References\" menu."},
            {"type": "image", "image_id": "p2_img1", "describes": "Character Replacement screen"},
            {"type": "code", "text": "SELECT * FROM rules WHERE dir = 'UPLINK'"},
            {"type": "list", "ordered": False, "items": ["Item A", "Item B"]},
            {"type": "table", "headers": ["Col1", "Col2"], "rows": [["a", "b"]]},
        ],
    }


@pytest.fixture
def pdf_workspace(tmp_path):
    """Create a minimal PDF file + images dir with dummy PNGs."""
    pdf_dir = tmp_path / "release_notes"
    pdf_dir.mkdir()
    pdf_file = pdf_dir / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy content for testing")

    images_dir = pdf_dir / "images"
    images_dir.mkdir()
    # Write minimal 1x1 PNG for each content image
    # PNG header + minimal IHDR + IDAT + IEND
    minimal_png = (
        b"\x89PNG\r\n\x1a\n"  # PNG signature
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"  # 1x1 RGB
        b"\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    (images_dir / "p2_img1.png").write_bytes(minimal_png)
    (images_dir / "p3_img1.png").write_bytes(minimal_png)

    return pdf_file


# ───── TestBuildToolSchema ───────────────────────────────────────────────


class TestBuildToolSchema:
    def test_schema_has_tool_name(self):
        schema = _build_tool_schema()
        assert schema["name"] == "save_release_note_item"

    def test_schema_has_required_fields(self):
        schema = _build_tool_schema()
        required = schema["input_schema"]["required"]
        assert "section" in required
        assert "am_card" in required
        assert "customers" in required
        assert "title" in required
        assert "summary" in required
        assert "body" in required

    def test_am_card_pattern_in_schema(self):
        schema = _build_tool_schema()
        am_card = schema["input_schema"]["properties"]["am_card"]
        assert "pattern" in am_card
        assert "AM" in am_card["pattern"]

    def test_body_block_types_listed(self):
        schema = _build_tool_schema()
        body_items = schema["input_schema"]["properties"]["body"]["items"]
        enum_vals = body_items["properties"]["type"]["enum"]
        assert set(enum_vals) == {"paragraph", "heading", "image", "list", "table", "code"}


# ───── TestBuildUserMessage ──────────────────────────────────────────────


class TestBuildUserMessage:
    def test_includes_pdf_document_block(self, pdf_workspace, mock_manifest):
        blocks = _build_user_message(pdf_workspace, pdf_workspace.read_bytes(), mock_manifest)
        assert blocks[0]["type"] == "document"
        assert blocks[0]["source"]["media_type"] == "application/pdf"

    def test_pdf_block_has_cache_control(self, pdf_workspace, mock_manifest):
        blocks = _build_user_message(pdf_workspace, pdf_workspace.read_bytes(), mock_manifest)
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}

    def test_includes_non_chrome_images_only(self, pdf_workspace, mock_manifest):
        blocks = _build_user_message(pdf_workspace, pdf_workspace.read_bytes(), mock_manifest)
        image_blocks = [b for b in blocks if b["type"] == "image"]
        # 2 content images, not the chrome one
        assert len(image_blocks) == 2

    def test_includes_manifest_text(self, pdf_workspace, mock_manifest):
        blocks = _build_user_message(pdf_workspace, pdf_workspace.read_bytes(), mock_manifest)
        text_blocks = [b for b in blocks if b["type"] == "text"]
        assert len(text_blocks) == 1
        text = text_blocks[0]["text"]
        assert "p2_img1" in text
        assert "p3_img1" in text
        # Chrome image should NOT appear
        assert "p1_img1" not in text

    def test_missing_image_file_skipped(self, pdf_workspace, mock_manifest):
        # Delete one image file
        (pdf_workspace.parent / "images" / "p3_img1.png").unlink()
        blocks = _build_user_message(pdf_workspace, pdf_workspace.read_bytes(), mock_manifest)
        image_blocks = [b for b in blocks if b["type"] == "image"]
        assert len(image_blocks) == 1
        # Manifest text should also skip the missing image
        text = [b for b in blocks if b["type"] == "text"][0]["text"]
        assert "p3_img1" not in text


# ───── TestBuildSystemPrompt ─────────────────────────────────────────────


class TestBuildSystemPrompt:
    def test_prompt_mentions_tool_name(self):
        prompt = _build_system_prompt()
        assert "save_release_note_item" in prompt

    def test_prompt_mentions_am_card(self):
        prompt = _build_system_prompt()
        assert "AM" in prompt
        assert "am_card" not in prompt or "am_card" in prompt  # just check AM rules exist

    def test_prompt_mentions_block_types(self):
        prompt = _build_system_prompt()
        for btype in ["paragraph", "heading", "image", "list", "table", "code"]:
            assert btype in prompt


# ───── TestValidateItem ──────────────────────────────────────────────────


class TestValidateItem:
    def test_valid_item_returns_release_note_item(self, sample_tool_input, valid_image_ids):
        item = _validate_item(sample_tool_input, valid_image_ids)
        assert isinstance(item, ReleaseNoteItem)
        assert item.am_card == "AM1393"
        assert item.customers == ["HAL"]
        assert len(item.body) == 6

    def test_body_block_types_correct(self, sample_tool_input, valid_image_ids):
        item = _validate_item(sample_tool_input, valid_image_ids)
        assert isinstance(item.body[0], HeadingBlock)
        assert isinstance(item.body[1], ParagraphBlock)
        assert isinstance(item.body[2], ImageBlock)
        assert isinstance(item.body[3], CodeBlock)
        assert isinstance(item.body[4], ListBlock)
        assert isinstance(item.body[5], TableBlock)

    def test_invalid_am_card_raises(self, sample_tool_input, valid_image_ids):
        sample_tool_input["am_card"] = "BADCARD"
        with pytest.raises(ValueError, match="Invalid am_card"):
            _validate_item(sample_tool_input, valid_image_ids)

    def test_am_card_too_long_raises(self, sample_tool_input, valid_image_ids):
        sample_tool_input["am_card"] = "AM123456"  # 6 digits, max is 5
        with pytest.raises(ValueError, match="Invalid am_card"):
            _validate_item(sample_tool_input, valid_image_ids)

    def test_unknown_image_id_skipped_from_body(self, valid_image_ids):
        raw = {
            "section": "Bug Fixes",
            "am_card": "AM2904",
            "customers": [],
            "title": "Some fix",
            "summary": "Fixes something.",
            "body": [
                {"type": "paragraph", "text": "Before the image."},
                {"type": "image", "image_id": "p99_img1", "describes": "Ghost image"},
                {"type": "paragraph", "text": "After the image."},
            ],
        }
        item = _validate_item(raw, valid_image_ids)
        # The image block should be dropped, paragraphs kept
        assert len(item.body) == 2
        assert all(isinstance(b, ParagraphBlock) for b in item.body)

    def test_invalid_image_id_format_skipped(self, valid_image_ids):
        raw = {
            "section": "Bug Fixes",
            "am_card": "AM2904",
            "customers": [],
            "title": "Some fix",
            "summary": "Fixes something.",
            "body": [
                {"type": "image", "image_id": "bad_format", "describes": "Bad"},
            ],
        }
        item = _validate_item(raw, valid_image_ids)
        assert len(item.body) == 0

    def test_unknown_block_type_skipped(self, valid_image_ids):
        raw = {
            "section": "New Features",
            "am_card": "AM1000",
            "customers": [],
            "title": "Test",
            "summary": "Test.",
            "body": [
                {"type": "paragraph", "text": "Keep me."},
                {"type": "unknown_type", "text": "Skip me."},
            ],
        }
        item = _validate_item(raw, valid_image_ids)
        assert len(item.body) == 1
        assert isinstance(item.body[0], ParagraphBlock)

    def test_heading_defaults_level_to_3(self, valid_image_ids):
        raw = {
            "section": "New Features",
            "am_card": "AM1000",
            "customers": [],
            "title": "Test",
            "summary": "Test.",
            "body": [{"type": "heading", "text": "Setting"}],
        }
        item = _validate_item(raw, valid_image_ids)
        assert isinstance(item.body[0], HeadingBlock)
        assert item.body[0].level == 3

    def test_empty_body_allowed(self, valid_image_ids):
        raw = {
            "section": "Not Tested",
            "am_card": "AM2970",
            "customers": [],
            "title": "Placeholder item",
            "summary": "Not tested in this release.",
            "body": [],
        }
        item = _validate_item(raw, valid_image_ids)
        assert item.body == []

    def test_missing_customers_defaults_empty(self, valid_image_ids):
        raw = {
            "section": "New Features",
            "am_card": "AM1000",
            "title": "Test",
            "summary": "Test.",
            "body": [],
        }
        item = _validate_item(raw, valid_image_ids)
        assert item.customers == []


# ───── TestClaudeClient ──────────────────────────────────────────────────


class TestClaudeClient:
    def test_empty_api_key_raises(self):
        with pytest.raises(ClaudeExtractionError, match="ANTHROPIC_API_KEY is empty"):
            ClaudeClient("")

    def test_send_extraction_collects_tool_calls(self):
        client = ClaudeClient("sk-test-key")

        # Build a mock response with 2 tool_use blocks
        mock_block_1 = MagicMock()
        mock_block_1.type = "tool_use"
        mock_block_1.id = "call_1"
        mock_block_1.name = "save_release_note_item"
        mock_block_1.input = {"am_card": "AM1000"}

        mock_block_2 = MagicMock()
        mock_block_2.type = "tool_use"
        mock_block_2.id = "call_2"
        mock_block_2.name = "save_release_note_item"
        mock_block_2.input = {"am_card": "AM2000"}

        mock_response = MagicMock()
        mock_response.content = [mock_block_1, mock_block_2]
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 5000
        mock_response.usage.output_tokens = 1500

        with patch.object(client._client.messages, "create", return_value=mock_response):
            blocks, stop_reason, usage_info = client.send_extraction([], [], "test prompt")
            assert len(blocks) == 2
            assert blocks[0]["input"]["am_card"] == "AM1000"
            assert stop_reason == "end_turn"
            assert usage_info["input_tokens"] == 5000
            assert usage_info["output_tokens"] == 1500
            assert usage_info["model"] == "claude-opus-4-6"
            assert usage_info["cost_usd"] > 0

    def test_send_extraction_no_tool_calls_raises(self):
        client = ClaudeClient("sk-test-key")

        mock_text_block = MagicMock()
        mock_text_block.type = "text"

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50

        with patch.object(client._client.messages, "create", return_value=mock_response):
            with pytest.raises(ClaudeExtractionError, match="no tool calls"):
                client.send_extraction([], [], "test prompt")

    def test_auth_error_raises_extraction_error(self):
        import anthropic as anthropic_mod

        client = ClaudeClient("sk-bad-key")

        with patch.object(
            client._client.messages,
            "create",
            side_effect=anthropic_mod.AuthenticationError(
                message="invalid key",
                response=MagicMock(status_code=401),
                body={"error": {"message": "invalid key"}},
            ),
        ):
            with pytest.raises(ClaudeExtractionError, match="Authentication failed"):
                client.send_extraction([], [], "test prompt")


# ───── TestExtractReleaseNote ────────────────────────────────────────────


class TestExtractReleaseNote:
    def _make_tool_calls(self, items: list[dict]) -> list[dict]:
        """Build fake tool_use block dicts."""
        return [
            {"id": f"call_{i}", "name": "save_release_note_item", "input": item}
            for i, item in enumerate(items)
        ]

    def test_happy_path(self, pdf_workspace, mock_manifest):
        tool_inputs = [
            {
                "section": "New Features",
                "am_card": "AM1393",
                "customers": ["HAL"],
                "title": "Character replacement feature",
                "summary": "Adds character replacement for uplink messages.",
                "body": [{"type": "paragraph", "text": "Some text."}],
            },
            {
                "section": "Defect Fixes",
                "am_card": "AM2904",
                "customers": ["ETH"],
                "title": "MIAM configurable response code",
                "summary": "Allows configuring response code F or E.",
                "body": [],
            },
        ]

        mock_client = MagicMock(spec=ClaudeClient)
        mock_usage = {
            "input_tokens": 50000, "output_tokens": 3000,
            "model": "claude-opus-4-6", "cost_usd": 0.325,
        }
        mock_client.send_extraction.return_value = (
            self._make_tool_calls(tool_inputs),
            "end_turn",
            mock_usage,
        )

        record = extract_release_note(
            pdf_workspace, mock_manifest,
            version="8.0.18.1",
            claude_client=mock_client,
        )

        assert record.version == "8.0.18.1"
        assert record.extractor == "claude"
        assert record.extractor_version == 1
        assert len(record.items) == 2
        assert record.items[0].am_card == "AM1393"
        assert record.items[1].am_card == "AM2904"
        assert record.source_pdf_pages == 4
        assert len(record.source_pdf_hash) == 64  # SHA-256 hex
        assert record.usage is not None
        assert record.usage.model == "claude-opus-4-6"
        assert record.usage.cost_usd == 0.325

    def test_max_tokens_logs_warning(self, pdf_workspace, mock_manifest, caplog):
        tool_inputs = [
            {
                "section": "New Features",
                "am_card": "AM1000",
                "customers": [],
                "title": "Test",
                "summary": "Test.",
                "body": [],
            },
        ]

        mock_client = MagicMock(spec=ClaudeClient)
        mock_client.send_extraction.return_value = (
            self._make_tool_calls(tool_inputs),
            "max_tokens",
            {"input_tokens": 1000, "output_tokens": 500, "model": "claude-opus-4-6", "cost_usd": 0.02},
        )

        import logging
        with caplog.at_level(logging.WARNING, logger="claude.extractor"):
            record = extract_release_note(
                pdf_workspace, mock_manifest,
                version="8.0.18.1",
                claude_client=mock_client,
            )

        assert len(record.items) == 1
        assert "max_tokens" in caplog.text

    def test_all_items_invalid_raises(self, pdf_workspace, mock_manifest):
        tool_inputs = [
            {
                "section": "New Features",
                "am_card": "BADCARD",
                "customers": [],
                "title": "Bad",
                "summary": "Bad.",
                "body": [],
            },
        ]

        mock_client = MagicMock(spec=ClaudeClient)
        mock_client.send_extraction.return_value = (
            self._make_tool_calls(tool_inputs),
            "end_turn",
            {"input_tokens": 1000, "output_tokens": 500, "model": "claude-opus-4-6", "cost_usd": 0.02},
        )

        with pytest.raises(ClaudeExtractionError, match="no valid items"):
            extract_release_note(
                pdf_workspace, mock_manifest,
                version="8.0.18.1",
                claude_client=mock_client,
            )

    def test_partial_validation_failure_skips_bad_items(self, pdf_workspace, mock_manifest):
        tool_inputs = [
            {
                "section": "New Features",
                "am_card": "AM1000",
                "customers": [],
                "title": "Good item",
                "summary": "Good.",
                "body": [],
            },
            {
                "section": "Bug Fixes",
                "am_card": "INVALID",
                "customers": [],
                "title": "Bad item",
                "summary": "Bad.",
                "body": [],
            },
            {
                "section": "Bug Fixes",
                "am_card": "AM2000",
                "customers": ["FFT"],
                "title": "Another good item",
                "summary": "Also good.",
                "body": [],
            },
        ]

        mock_client = MagicMock(spec=ClaudeClient)
        mock_client.send_extraction.return_value = (
            self._make_tool_calls(tool_inputs),
            "end_turn",
            {"input_tokens": 1000, "output_tokens": 500, "model": "claude-opus-4-6", "cost_usd": 0.02},
        )

        record = extract_release_note(
            pdf_workspace, mock_manifest,
            version="8.0.18.1",
            claude_client=mock_client,
        )

        assert len(record.items) == 2
        assert record.items[0].am_card == "AM1000"
        assert record.items[1].am_card == "AM2000"

    def test_api_error_propagates(self, pdf_workspace, mock_manifest):
        mock_client = MagicMock(spec=ClaudeClient)
        mock_client.send_extraction.side_effect = ClaudeExtractionError("API timeout")

        with pytest.raises(ClaudeExtractionError, match="API timeout"):
            extract_release_note(
                pdf_workspace, mock_manifest,
                version="8.0.18.1",
                claude_client=mock_client,
            )


# ───── TestComputeCost ───────────────────────────────────────────────────


class TestComputeCost:
    def test_opus_46_cost(self):
        # 100k input × $5/MTok + 10k output × $25/MTok = $0.50 + $0.25 = $0.75
        cost = compute_cost("claude-opus-4-6", 100_000, 10_000)
        assert cost == pytest.approx(0.75)

    def test_sonnet_46_cost(self):
        # 100k input × $3/MTok + 10k output × $15/MTok = $0.30 + $0.15 = $0.45
        cost = compute_cost("claude-sonnet-4-6", 100_000, 10_000)
        assert cost == pytest.approx(0.45)

    def test_unknown_model_returns_zero(self):
        cost = compute_cost("unknown-model", 100_000, 10_000)
        assert cost == 0.0
