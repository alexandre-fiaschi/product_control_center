"""PDF image extractor for the Claude-based release-notes pipeline.

Walks a release-notes PDF, extracts every embedded image as PNG, and writes a
sibling ``images/`` folder + ``manifest.json``. The manifest is consumed by the
Claude extractor (Unit 4.5 Block 3) and by the DOCX renderer (Block 4).
"""

from __future__ import annotations

import fcntl
import io
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import pdfplumber
from PIL import Image
from pydantic import BaseModel, Field

logger = logging.getLogger("pdf.image_extractor")

EXTRACTOR_NAME = "pdfplumber"
EXTRACTOR_VERSION = 1

# Chrome-detection thresholds — ported from is_page_header_logo() in
# scripts/test_docx_conversion.py lines 766–785. The old heuristic used PDF
# native coords (y=0 at bottom of page, A4 height ~842pt). pdfplumber
# normalizes the y-axis so top=0, so we flip the direction of the check:
# "top < CHROME_TOP_BAND_PT" = "the image sits in the top inch of the page".
CHROME_MAX_WIDTH_PT = 200
CHROME_MAX_HEIGHT_PT = 200
CHROME_TOP_BAND_PT = 160  # top inch + slack


class ManifestImage(BaseModel):
    id: str
    page: int
    index_on_page: int
    bbox: tuple[float, float, float, float]  # (x0, top, x1, bottom)
    width_px: int
    height_px: int
    format: Literal["png"] = "png"
    chrome: bool = False
    describes: str | None = None


class ImageManifest(BaseModel):
    extracted_at: datetime
    extractor: str = EXTRACTOR_NAME
    extractor_version: int = EXTRACTOR_VERSION
    source_pdf_pages: int
    images: list[ManifestImage] = Field(default_factory=list)


# ───── Public API ─────────────────────────────────────────────────────────


def extract_images(pdf_path: Path | str, *, force: bool = False) -> ImageManifest:
    """Extract images from ``pdf_path`` into a sibling ``images/`` folder.

    Idempotent: if ``images/manifest.json`` exists and its ``extractor_version``
    matches the current one, the cached manifest is returned without
    re-extracting. Pass ``force=True`` (or delete the ``images/`` folder) to
    override — e.g. after Cyberjet re-issues a corrected PDF for the same
    version.
    """
    pdf_path = Path(pdf_path).resolve()
    images_dir = pdf_path.parent / "images"
    manifest_path = images_dir / "manifest.json"

    if not force and manifest_path.exists():
        try:
            cached = ImageManifest.model_validate_json(manifest_path.read_text())
            if cached.extractor_version == EXTRACTOR_VERSION:
                logger.info(
                    "image_extractor.cache_hit pdf=%s images=%d",
                    pdf_path.name,
                    len(cached.images),
                )
                return cached
            logger.info(
                "image_extractor.cache_stale pdf=%s (extractor_version changed)",
                pdf_path.name,
            )
        except Exception:
            logger.warning(
                "image_extractor.cache_unreadable path=%s",
                manifest_path,
                exc_info=True,
            )

    images_dir.mkdir(parents=True, exist_ok=True)
    logger.info("image_extractor.start pdf=%s", pdf_path.name)

    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        manifest = ImageManifest(
            extracted_at=datetime.now(timezone.utc),
            source_pdf_pages=page_count,
        )

        for page_num, page in enumerate(pdf.pages, start=1):
            entries = _extract_page_images(page, page_num, images_dir)
            manifest.images.extend(entries)

    chrome_count = sum(1 for img in manifest.images if img.chrome)
    logger.info(
        "image_extractor.done pdf=%s pages=%d images=%d chrome=%d",
        pdf_path.name,
        page_count,
        len(manifest.images),
        chrome_count,
    )

    _write_manifest_atomic(manifest_path, manifest)
    return manifest


# ───── Per-page extraction ────────────────────────────────────────────────


def _extract_page_images(
    page: Any, page_num: int, images_dir: Path
) -> list[ManifestImage]:
    raw_images = page.images or []

    # Sort by reading order: top-to-bottom, then left-to-right.
    # pdfplumber uses top=0, so smaller `top` = higher on page.
    sorted_imgs = sorted(
        raw_images, key=lambda im: (round(im["top"], 1), round(im["x0"], 1))
    )

    results: list[ManifestImage] = []
    for idx, img_info in enumerate(sorted_imgs, start=1):
        img_id = f"p{page_num}_img{idx}"
        out_path = images_dir / f"{img_id}.png"

        try:
            png_bytes = _render_image(img_info)
        except Exception as exc:
            logger.warning(
                "image_extractor.decode_failed id=%s error=%s — falling back to raster",
                img_id,
                exc,
            )
            try:
                png_bytes = _raster_fallback(page, img_info)
            except Exception:
                logger.error(
                    "image_extractor.raster_fallback_failed id=%s",
                    img_id,
                    exc_info=True,
                )
                continue

        out_path.write_bytes(png_bytes)

        width_px, height_px = _png_dimensions(png_bytes)
        bbox = (
            float(img_info["x0"]),
            float(img_info["top"]),
            float(img_info["x1"]),
            float(img_info["bottom"]),
        )
        is_chrome = _is_chrome_image(bbox)

        results.append(
            ManifestImage(
                id=img_id,
                page=page_num,
                index_on_page=idx,
                bbox=bbox,
                width_px=width_px,
                height_px=height_px,
                chrome=is_chrome,
            )
        )
        logger.debug(
            "image_extractor.extracted id=%s bbox=%s chrome=%s",
            img_id,
            bbox,
            is_chrome,
        )

    return results


_PIXEL_MODES: dict[tuple[str, int], str] = {
    # (colorspace, bits_per_component) → Pillow mode
    ("DeviceRGB", 8): "RGB",
    ("DeviceGray", 8): "L",
    ("DeviceGray", 1): "1",
    ("DeviceCMYK", 8): "CMYK",
}


def _render_image(img_info: dict) -> bytes:
    """Decode a pdfplumber image stream and re-encode as PNG.

    PDF images come in two flavors:

    1. **Encoded image formats** (JPEG via ``/DCTDecode``, JPEG2000 via
       ``/JPXDecode``): the stream's raw bytes already ARE a JPEG / JP2 file,
       so we hand them straight to ``Image.open``.
    2. **Raw pixel arrays** (``/FlateDecode`` over raw RGB/Gray/CMYK pixels):
       the decompressed stream is just pixel bytes. Pillow cannot auto-detect
       these — we have to call ``Image.frombytes`` with explicit mode + size.

    Width, height, colorspace, and bits-per-component all live on the PDF
    image dict (``img_info``), not on the stream attrs, because pdfplumber
    unpacks them for us.
    """
    stream = img_info["stream"]
    filters = _stream_filters(stream)

    # Path 1: encoded image formats — JPEG, JPEG2000, CCITT fax.
    if any(f in ("DCTDecode", "JPXDecode") for f in filters):
        raw = stream.get_rawdata()
        im = Image.open(io.BytesIO(raw))
    else:
        # Path 2: raw pixel array. get_data() applies FlateDecode / LZWDecode.
        raw = stream.get_data()
        width = int(img_info["srcsize"][0])
        height = int(img_info["srcsize"][1])
        colorspace = _simple_colorspace(img_info.get("colorspace"))
        bits = int(img_info.get("bits") or 8)
        mode = _PIXEL_MODES.get((colorspace, bits))
        if mode is None:
            raise ValueError(
                f"unsupported raw-pixel combo colorspace={colorspace} bits={bits}"
            )
        im = Image.frombytes(mode, (width, height), raw)

    # Normalize mode — CMYK / LA / P → RGB for portability.
    if im.mode not in ("RGB", "RGBA", "L", "1"):
        im = im.convert("RGB")
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


def _stream_filters(stream: Any) -> list[str]:
    """Return the filter names on a PDFStream as plain strings."""
    try:
        raw_filters = stream.get_filters() or []
    except Exception:
        return []
    names: list[str] = []
    for entry in raw_filters:
        # get_filters() returns a list of (filter_name, params) tuples.
        name = entry[0] if isinstance(entry, tuple) else entry
        # pdfplumber wraps names as pdfminer PSLiteral — str() gives "/'Name'"
        s = str(name).strip("/").strip("'")
        names.append(s)
    return names


def _simple_colorspace(cs: Any) -> str:
    """Extract the colorspace name from the messy pdfminer representation."""
    if cs is None:
        return ""
    if isinstance(cs, list) and cs:
        cs = cs[0]
    return str(cs).strip("/").strip("'")


def _raster_fallback(page: Any, img_info: dict) -> bytes:
    """Fallback: rasterize the cropped page region at 200 DPI.

    Always works — even for unsupported filters — because we are rendering the
    final visual output rather than decoding the source stream.
    """
    bbox = (
        img_info["x0"],
        img_info["top"],
        img_info["x1"],
        img_info["bottom"],
    )
    cropped = page.crop(bbox).to_image(resolution=200)
    out = io.BytesIO()
    cropped.save(out, format="PNG")
    return out.getvalue()


def _png_dimensions(png_bytes: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(png_bytes)) as im:
        return im.size  # (width, height)


def _is_chrome_image(bbox: tuple[float, float, float, float]) -> bool:
    """Port of ``is_page_header_logo`` (test_docx_conversion.py:766-785).

    Adapted for pdfplumber coords (top=0). An image is chrome if it is small
    AND sits in the top band of the page — that's the Cyberjet logo stamped
    into every page header.
    """
    x0, top, x1, bottom = bbox
    width = x1 - x0
    height = bottom - top
    return (
        top < CHROME_TOP_BAND_PT
        and width < CHROME_MAX_WIDTH_PT
        and height < CHROME_MAX_HEIGHT_PT
    )


# ───── Utilities ──────────────────────────────────────────────────────────


def _write_manifest_atomic(path: Path, manifest: ImageManifest) -> None:
    """Atomic JSON write — mirrors the pattern from state/manager.py:27-47."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    try:
        with open(tmp_path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(manifest.model_dump_json(indent=2))
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        os.replace(tmp_path, path)
    except Exception:
        logger.error(
            "image_extractor.manifest_write_failed path=%s", path, exc_info=True
        )
        if tmp_path.exists():
            tmp_path.unlink()
        raise
