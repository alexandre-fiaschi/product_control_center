"""Tests for app.pipelines.docs.converter.extract_release_notes.

Fixture-based, no live API. The converter's cache helpers read/write under
settings.docs_cache_dir, so we monkeypatch that to a tmp dir per test.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.config import settings
from app.integrations.claude.client import ClaudeExtractionError
from app.integrations.claude.extractor import EXTRACTOR_VERSION as CURRENT_EXTRACTOR_VERSION
from app.pipelines.docs.converter import extract_release_notes
from app.services.lifecycle import run_cell
from app.state.models import (
    BinariesState,
    PatchEntry,
    ReleaseNotesState,
)
from app.state.release_notes_models import (
    ParagraphBlock,
    ReleaseNoteItem,
    ReleaseNoteRecord,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_cache_dir(tmp_path, monkeypatch):
    """Redirect the converter's cache directory to a tmp path."""
    cache_dir = tmp_path / "cache" / "claude"
    cache_dir.mkdir(parents=True)
    monkeypatch.setattr(
        type(settings), "docs_cache_dir",
        property(lambda self: cache_dir),
    )
    return cache_dir


@pytest.fixture
def fake_pdf(tmp_path):
    """Create a fake PDF file the converter can hash."""
    pdf_dir = tmp_path / "patches" / "ACARS_V8_0" / "8.0.18.1" / "release_notes"
    pdf_dir.mkdir(parents=True)
    pdf_path = pdf_dir / "8.0.18.1 - Release Notes.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake content for test " * 100)
    return pdf_path


def _make_patch(pdf_path: Path) -> PatchEntry:
    return PatchEntry(
        sftp_folder="v8.0.18.1",
        sftp_path="/ACARS_V8_0/ACARS_V8_0_18/v8.0.18.1",
        local_path="patches/ACARS_V8_0/8.0.18.1",
        binaries=BinariesState(status="pending_approval"),
        release_notes=ReleaseNotesState(
            status="downloaded",
            source_pdf_path=str(pdf_path),
        ),
    )


def _make_record(version: str, extractor_version: int = CURRENT_EXTRACTOR_VERSION) -> ReleaseNoteRecord:
    return ReleaseNoteRecord(
        version=version,
        extracted_at=datetime.now(timezone.utc),
        extractor="claude",
        extractor_version=extractor_version,
        source_pdf_path="ignored",
        source_pdf_hash="0" * 64,
        source_pdf_pages=1,
        items=[
            ReleaseNoteItem(
                section="New Features",
                am_card="AM1393",
                customers=["HAL"],
                title="Test feature",
                summary="A test summary.",
                body=[ParagraphBlock(type="paragraph", text="Body text.")],
            ),
        ],
    )


def _seed_cache(cache_dir: Path, pdf_path: Path, record: ReleaseNoteRecord) -> Path:
    """Write a cached record at the SHA256-keyed path the converter expects."""
    import hashlib
    pdf_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    cache_file = cache_dir / f"{pdf_hash}.json"
    cache_file.write_text(record.model_dump_json(indent=2))
    return cache_file


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExtractCacheHit:
    def test_cache_hit_advances_to_extracted(self, tmp_cache_dir, fake_pdf):
        record = _make_record("8.0.18.1")
        _seed_cache(tmp_cache_dir, fake_pdf, record)
        patch = _make_patch(fake_pdf)

        result = extract_release_notes(
            patch,
            product_id="ACARS_V8_0",
            version="8.0.18.1",
            claude_client=None,  # cache hit means we never need it
        )

        assert result == "extracted"
        assert patch.release_notes.status == "extracted"
        assert patch.release_notes.extracted_at is not None
        assert patch.release_notes.record_json_path is not None
        # The persisted record JSON sits next to the source PDF.
        record_path = Path(patch.release_notes.record_json_path)
        assert record_path.exists()
        # Round-trip: the persisted record matches what we cached.
        persisted = json.loads(record_path.read_text())
        assert persisted["version"] == "8.0.18.1"
        assert len(persisted["items"]) == 1


class TestExtractCacheMissNoApi:
    def test_skipped_no_api_when_client_none(self, tmp_cache_dir, fake_pdf, caplog):
        patch = _make_patch(fake_pdf)

        import logging
        with caplog.at_level(logging.INFO, logger="pipelines.docs.converter"):
            result = extract_release_notes(
                patch,
                product_id="ACARS_V8_0",
                version="8.0.18.1",
                claude_client=None,
            )

        assert result == "skipped_no_api"
        # Workflow status untouched
        assert patch.release_notes.status == "downloaded"
        assert patch.release_notes.extracted_at is None
        assert patch.release_notes.record_json_path is None
        assert any("convert.extract.skipped" in r.message and "claude_disabled" in r.message
                   for r in caplog.records)


class TestExtractFailure:
    def test_extractor_exception_propagates_via_run_cell(
        self, tmp_cache_dir, fake_pdf, monkeypatch,
    ):
        patch = _make_patch(fake_pdf)

        def _boom(*args, **kwargs):
            raise ClaudeExtractionError("API rate limit")

        monkeypatch.setattr(
            "app.pipelines.docs.converter.extract_release_note", _boom,
        )
        # Image extraction must succeed before the boom — stub it.
        monkeypatch.setattr(
            "app.pipelines.docs.converter.extract_images",
            lambda pdf_path: _stub_manifest(),
        )

        # Wrap in run_cell so we exercise the lifecycle bookkeeping path.
        ok = run_cell(
            patch.release_notes,
            lambda: extract_release_notes(
                patch,
                product_id="ACARS_V8_0",
                version="8.0.18.1",
                claude_client=_FakeClient(),
            ),
            step_name="extract",
            product="ACARS_V8_0",
            version="8.0.18.1",
        )

        assert ok is False
        assert patch.release_notes.status == "downloaded"  # untouched
        assert patch.release_notes.last_run.state == "failed"
        assert patch.release_notes.last_run.step == "extract"
        assert "rate limit" in patch.release_notes.last_run.error


class TestExtractCacheVersionGuard:
    def test_stale_cache_version_treated_as_miss(
        self, tmp_cache_dir, fake_pdf, monkeypatch,
    ):
        # Seed cache with an old extractor_version
        old_record = _make_record("8.0.18.1", extractor_version=0)
        _seed_cache(tmp_cache_dir, fake_pdf, old_record)
        patch = _make_patch(fake_pdf)

        # Stub the real extractor — it should still be called because the
        # cached record has a stale version.
        new_record = _make_record("8.0.18.1", extractor_version=CURRENT_EXTRACTOR_VERSION)
        called = {"count": 0}

        def _stub_extract(pdf_path, manifest, *, version, claude_client):
            called["count"] += 1
            return new_record

        monkeypatch.setattr(
            "app.pipelines.docs.converter.extract_release_note", _stub_extract,
        )
        monkeypatch.setattr(
            "app.pipelines.docs.converter.extract_images",
            lambda pdf_path: _stub_manifest(),
        )

        result = extract_release_notes(
            patch,
            product_id="ACARS_V8_0",
            version="8.0.18.1",
            claude_client=_FakeClient(),
        )

        assert result == "extracted"
        assert called["count"] == 1, "stale-version cache should be ignored"
        # The persisted record reflects the new version.
        persisted = json.loads(Path(patch.release_notes.record_json_path).read_text())
        assert persisted["extractor_version"] == CURRENT_EXTRACTOR_VERSION


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _stub_manifest():
    """Minimal ImageManifest for tests that mock the extractor itself."""
    from app.integrations.pdf.image_extractor import ImageManifest
    return ImageManifest(
        extracted_at=datetime.now(timezone.utc),
        source_pdf_pages=1,
        images=[],
    )


class _FakeClient:
    """Sentinel for 'API is allowed' — the actual extractor is mocked out."""
    pass
