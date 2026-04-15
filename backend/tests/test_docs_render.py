"""Tests for app.pipelines.docs.converter.render_release_notes.

Uses the real Flightscape template that ships with the repo, since the
render path is mostly python-docx + template manipulation and the only
fixture-able piece is the persisted ReleaseNoteRecord JSON.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.config import settings
from app.pipelines.docs.converter import render_release_notes
from app.services.lifecycle import run_cell
from app.state.models import (
    BinariesState,
    PatchEntry,
    ReleaseNotesState,
)
from app.state.release_notes_models import (
    HeadingBlock,
    ListBlock,
    ParagraphBlock,
    ReleaseNoteItem,
    ReleaseNoteRecord,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def real_template():
    """The actual Flightscape template that ships with the repo."""
    p = settings.docs_template_path
    if not p.exists():
        pytest.skip(f"template not found at {p}")
    return p


@pytest.fixture
def patch_with_record(tmp_path):
    """A patch at status=extracted with a small ReleaseNoteRecord on disk."""
    pdf_dir = tmp_path / "patches" / "ACARS_V8_0" / "8.0.18.1" / "release_notes"
    pdf_dir.mkdir(parents=True)
    record_path = pdf_dir / "8.0.18.1.json"

    record = ReleaseNoteRecord(
        version="8.0.18.1",
        extracted_at=datetime.now(timezone.utc),
        extractor="claude",
        extractor_version=1,
        source_pdf_path=str(pdf_dir / "8.0.18.1 - Release Notes.pdf"),
        source_pdf_hash="0" * 64,
        source_pdf_pages=10,
        items=[
            ReleaseNoteItem(
                section="New Features",
                am_card="AM1393",
                customers=["HAL"],
                title="Test feature for rendering",
                summary="A short summary of the feature.",
                body=[
                    ParagraphBlock(type="paragraph", text="First paragraph of body."),
                    HeadingBlock(type="heading", level=3, text="Bug Description:"),
                    ParagraphBlock(type="paragraph", text="More body text after the heading."),
                    ListBlock(type="list", ordered=False, items=["First bullet", "Second bullet"]),
                ],
            ),
            ReleaseNoteItem(
                section="Defect Fixes",
                am_card="AM2001",
                customers=[],
                title="Fixed a thing",
                summary="The thing is fixed.",
                body=[ParagraphBlock(type="paragraph", text="Fix description.")],
            ),
        ],
    )
    record_path.write_text(record.model_dump_json(indent=2))

    return PatchEntry(
        sftp_folder="v8.0.18.1",
        sftp_path="/ACARS_V8_0/ACARS_V8_0_18/v8.0.18.1",
        local_path="patches/ACARS_V8_0/8.0.18.1",
        binaries=BinariesState(status="pending_approval"),
        release_notes=ReleaseNotesState(
            status="extracted",
            record_json_path=str(record_path),
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRenderHappyPath:
    def test_render_advances_to_converted(self, real_template, patch_with_record):
        render_release_notes(
            patch_with_record,
            product_id="ACARS_V8_0",
            version="8.0.18.1",
            template_path=real_template,
        )

        assert patch_with_record.release_notes.status == "converted"
        assert patch_with_record.release_notes.converted_at is not None
        assert patch_with_record.release_notes.generated_docx_path is not None
        docx_path = Path(patch_with_record.release_notes.generated_docx_path)
        assert docx_path.exists()
        assert docx_path.stat().st_size > 0
        # File extension should be .docx
        assert docx_path.suffix == ".docx"


class TestRenderTemplateMissing:
    def test_missing_template_propagates_via_run_cell(self, patch_with_record, tmp_path):
        bogus_template = tmp_path / "does_not_exist.docx"

        ok = run_cell(
            patch_with_record.release_notes,
            lambda: render_release_notes(
                patch_with_record,
                product_id="ACARS_V8_0",
                version="8.0.18.1",
                template_path=bogus_template,
            ),
            step_name="render",
            product="ACARS_V8_0",
            version="8.0.18.1",
        )

        assert ok is False
        assert patch_with_record.release_notes.status == "extracted"  # untouched
        assert patch_with_record.release_notes.last_run.state == "failed"
        assert patch_with_record.release_notes.last_run.step == "render"
        assert "Template not found" in patch_with_record.release_notes.last_run.error


class TestRenderRecordMissing:
    def test_missing_record_json_propagates(self, real_template, tmp_path):
        # Patch has record_json_path pointing at a file that doesn't exist
        patch = PatchEntry(
            sftp_folder="v8.0.18.1",
            sftp_path="/ACARS_V8_0/ACARS_V8_0_18/v8.0.18.1",
            local_path="patches/ACARS_V8_0/8.0.18.1",
            binaries=BinariesState(status="pending_approval"),
            release_notes=ReleaseNotesState(
                status="extracted",
                record_json_path=str(tmp_path / "missing.json"),
            ),
        )

        ok = run_cell(
            patch.release_notes,
            lambda: render_release_notes(
                patch,
                product_id="ACARS_V8_0",
                version="8.0.18.1",
                template_path=real_template,
            ),
            step_name="render",
            product="ACARS_V8_0",
            version="8.0.18.1",
        )

        assert ok is False
        assert patch.release_notes.status == "extracted"
        assert patch.release_notes.last_run.state == "failed"
        assert patch.release_notes.last_run.step == "render"


class TestRenderIdempotent:
    def test_re_render_overwrites_docx(self, real_template, patch_with_record):
        # First render
        render_release_notes(
            patch_with_record,
            product_id="ACARS_V8_0",
            version="8.0.18.1",
            template_path=real_template,
        )
        first_path = Path(patch_with_record.release_notes.generated_docx_path)
        first_mtime = first_path.stat().st_mtime

        # Reset status so the precondition check passes again
        patch_with_record.release_notes.status = "extracted"
        time.sleep(0.05)  # ensure mtime changes

        # Second render
        render_release_notes(
            patch_with_record,
            product_id="ACARS_V8_0",
            version="8.0.18.1",
            template_path=real_template,
        )
        second_mtime = first_path.stat().st_mtime

        assert patch_with_record.release_notes.status == "converted"
        assert first_path.exists()
        assert second_mtime > first_mtime  # file was overwritten
