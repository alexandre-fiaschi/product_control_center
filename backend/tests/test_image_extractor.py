"""Tests for the PDF image extractor (Unit 4.5 Block 1)."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from PIL import Image

from app.integrations.pdf.image_extractor import (
    EXTRACTOR_VERSION,
    ImageManifest,
    _is_chrome_image,
    extract_images,
)

# ───── Pure-function unit tests (run on every pytest invocation) ──────────


class TestChromeDetection:
    def test_tiny_top_left_image_is_chrome(self):
        # Small image sitting at the top of the page — like the Cyberjet logo.
        assert _is_chrome_image((67.0, 20.0, 139.0, 92.0)) is True

    def test_large_centered_image_is_not_chrome(self):
        # A real body screenshot — wide and far from the top edge.
        assert _is_chrome_image((72.0, 300.0, 540.0, 600.0)) is False

    def test_small_image_below_top_band_is_not_chrome(self):
        # A small icon in the middle of a page — not page chrome.
        assert _is_chrome_image((100.0, 400.0, 160.0, 460.0)) is False

    def test_wide_image_in_top_band_is_not_chrome(self):
        # A wide banner in the top band — still not chrome (too wide).
        assert _is_chrome_image((50.0, 20.0, 500.0, 80.0)) is False

    def test_tall_image_in_top_band_is_not_chrome(self):
        # A tall image whose top edge is in the band but body isn't.
        assert _is_chrome_image((67.0, 20.0, 139.0, 600.0)) is False


class TestReadingOrderSort:
    """The sort key inside `_extract_page_images` is `(top, x0)`.

    We don't invoke `_extract_page_images` directly because it requires a real
    pdfplumber page object. Instead we replicate the exact sort on synthetic
    inputs to lock in the contract.
    """

    @staticmethod
    def _sort(items):
        return sorted(items, key=lambda im: (round(im["top"], 1), round(im["x0"], 1)))

    def test_top_to_bottom(self):
        items = [
            {"top": 500.0, "x0": 100.0, "name": "bottom"},
            {"top": 100.0, "x0": 100.0, "name": "top"},
            {"top": 300.0, "x0": 100.0, "name": "middle"},
        ]
        assert [i["name"] for i in self._sort(items)] == ["top", "middle", "bottom"]

    def test_left_to_right_within_same_row(self):
        items = [
            {"top": 100.0, "x0": 400.0, "name": "right"},
            {"top": 100.0, "x0": 100.0, "name": "left"},
            {"top": 100.0, "x0": 250.0, "name": "center"},
        ]
        assert [i["name"] for i in self._sort(items)] == ["left", "center", "right"]

    def test_mixed_rows(self):
        items = [
            {"top": 200.0, "x0": 50.0, "name": "row2_left"},
            {"top": 100.0, "x0": 300.0, "name": "row1_right"},
            {"top": 200.0, "x0": 300.0, "name": "row2_right"},
            {"top": 100.0, "x0": 50.0, "name": "row1_left"},
        ]
        names = [i["name"] for i in self._sort(items)]
        assert names == ["row1_left", "row1_right", "row2_left", "row2_right"]


# ───── Integration tests against a real fixture PDF ──────────────────────

FIXTURE_PDF = (
    Path(__file__).parent.parent.parent
    / "docs_example"
    / "pdf_examples"
    / "8.0"
    / "8.0.18.1 - Release Notes.pdf"
)

ID_PATTERN = re.compile(r"^p\d+_img\d+$")


@pytest.fixture
def copied_pdf(tmp_path):
    """Copy the fixture PDF to tmp so `images/` sidecar goes in tmp."""
    if not FIXTURE_PDF.exists():
        pytest.skip(f"fixture PDF not available: {FIXTURE_PDF}")
    dest = tmp_path / FIXTURE_PDF.name
    shutil.copy2(FIXTURE_PDF, dest)
    return dest


@pytest.mark.integration
class TestRealPdfExtraction:
    def test_extracts_and_writes_manifest(self, copied_pdf):
        manifest = extract_images(copied_pdf)

        manifest_path = copied_pdf.parent / "images" / "manifest.json"
        assert manifest_path.exists()

        # Structural assertions on the in-memory manifest.
        assert manifest.source_pdf_pages > 0
        assert manifest.extractor_version == EXTRACTOR_VERSION
        assert len(manifest.images) >= 10  # 32-page PDF; expect many images

        # Every image ID matches the convention.
        for img in manifest.images:
            assert ID_PATTERN.match(img.id), f"bad id: {img.id}"

        # Persisted manifest round-trips through Pydantic.
        persisted = ImageManifest.model_validate_json(manifest_path.read_text())
        assert len(persisted.images) == len(manifest.images)

    def test_index_on_page_is_monotonic(self, copied_pdf):
        manifest = extract_images(copied_pdf)
        by_page: dict[int, list[int]] = {}
        for img in manifest.images:
            by_page.setdefault(img.page, []).append(img.index_on_page)
        for page, indices in by_page.items():
            assert indices == sorted(indices), f"page {page} indices not sorted"
            assert indices == list(range(1, len(indices) + 1)), (
                f"page {page} indices not 1..N contiguous: {indices}"
            )

    def test_png_files_on_disk_are_valid(self, copied_pdf):
        manifest = extract_images(copied_pdf)
        images_dir = copied_pdf.parent / "images"
        for img in manifest.images:
            png_path = images_dir / f"{img.id}.png"
            assert png_path.exists(), f"missing {png_path}"
            with Image.open(png_path) as loaded:
                loaded.verify()

    def test_cyberjet_logo_flagged_as_chrome(self, copied_pdf):
        manifest = extract_images(copied_pdf)
        chrome_images = [img for img in manifest.images if img.chrome]
        # Cyberjet logo appears once per page in the top band.
        assert len(chrome_images) >= 1

    def test_idempotency_cache_hit(self, copied_pdf):
        manifest_path = copied_pdf.parent / "images" / "manifest.json"

        extract_images(copied_pdf)
        first_mtime = manifest_path.stat().st_mtime_ns
        first_bytes = manifest_path.read_bytes()

        m2 = extract_images(copied_pdf)
        second_mtime = manifest_path.stat().st_mtime_ns

        assert second_mtime == first_mtime, "manifest was rewritten on cache hit"
        assert manifest_path.read_bytes() == first_bytes
        assert len(m2.images) > 0

    def test_force_bypasses_cache(self, copied_pdf):
        manifest_path = copied_pdf.parent / "images" / "manifest.json"

        extract_images(copied_pdf)
        first_mtime = manifest_path.stat().st_mtime_ns

        # Nudge the clock by touching the file back in time, then force re-extract.
        import os
        import time

        past = time.time() - 10
        os.utime(manifest_path, (past, past))

        extract_images(copied_pdf, force=True)
        second_mtime = manifest_path.stat().st_mtime_ns

        assert second_mtime != first_mtime, "force=True did not rewrite manifest"

    def test_stale_extractor_version_invalidates_cache(self, copied_pdf):
        manifest_path = copied_pdf.parent / "images" / "manifest.json"

        extract_images(copied_pdf)

        # Simulate a previous-version manifest on disk.
        data = json.loads(manifest_path.read_text())
        data["extractor_version"] = 0
        manifest_path.write_text(json.dumps(data))

        fresh = extract_images(copied_pdf)
        assert fresh.extractor_version == EXTRACTOR_VERSION
        reloaded = json.loads(manifest_path.read_text())
        assert reloaded["extractor_version"] == EXTRACTOR_VERSION
