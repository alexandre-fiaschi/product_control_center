"""Tests for app.pipelines.docs.field_regen.regenerate_fields (Unit 11).

Fast tests mock the osascript subprocess. One integration test drives real
Microsoft Word against a pre-rendered DOCX and asserts the TOC cached runs
reflect actual document headings.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.pipelines.docs import field_regen


def _write_fake_docx(path: Path) -> None:
    path.write_bytes(b"PK\x03\x04 fake docx")


# ---------------------------------------------------------------------------
# Fast tests (mocked)
# ---------------------------------------------------------------------------


class TestRegenerateFieldsFastPath:
    def test_shells_out_with_expected_args(self, tmp_path):
        docx = tmp_path / "8.1.0.0.docx"
        _write_fake_docx(docx)

        with patch.object(field_regen, "_WORD_APP") as mock_word, \
             patch.object(
                 field_regen.subprocess,
                 "run",
                 return_value=MagicMock(returncode=0, stdout="", stderr=""),
             ) as mock_run:
            mock_word.exists.return_value = True
            field_regen.regenerate_fields(docx)

        mock_run.assert_called_once()
        cmd = mock_run.call_args.args[0]
        assert cmd[0] == "/usr/bin/osascript"
        assert cmd[1].endswith("_regen_fields.applescript")
        assert cmd[2] == str(docx)

    def test_raises_on_non_zero_exit(self, tmp_path):
        docx = tmp_path / "8.1.0.0.docx"
        _write_fake_docx(docx)

        with patch.object(field_regen, "_WORD_APP") as mock_word, \
             patch.object(
                 field_regen.subprocess,
                 "run",
                 return_value=MagicMock(returncode=2, stdout="", stderr="AppleEvent timed out"),
             ):
            mock_word.exists.return_value = True
            with pytest.raises(RuntimeError, match="exited 2"):
                field_regen.regenerate_fields(docx)

    def test_raises_on_timeout(self, tmp_path):
        docx = tmp_path / "8.1.0.0.docx"
        _write_fake_docx(docx)

        def boom(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 360))

        with patch.object(field_regen, "_WORD_APP") as mock_word, \
             patch.object(field_regen.subprocess, "run", side_effect=boom):
            mock_word.exists.return_value = True
            with pytest.raises(RuntimeError, match="timed out"):
                field_regen.regenerate_fields(docx, timeout_s=1)

    def test_raises_when_docx_missing(self, tmp_path):
        docx = tmp_path / "nope.docx"
        with pytest.raises(FileNotFoundError, match="DOCX not found"):
            field_regen.regenerate_fields(docx)

    def test_raises_when_word_missing(self, tmp_path):
        docx = tmp_path / "8.1.0.0.docx"
        _write_fake_docx(docx)

        with patch.object(field_regen, "_WORD_APP") as mock_word:
            mock_word.exists.return_value = False
            mock_word.__str__ = lambda s: "/Applications/Microsoft Word.app"
            with pytest.raises(FileNotFoundError, match="Microsoft Word"):
                field_regen.regenerate_fields(docx)


# ---------------------------------------------------------------------------
# Integration test (real Microsoft Word, macOS only)
# ---------------------------------------------------------------------------


def _word_available() -> bool:
    return field_regen._WORD_APP.exists()


@pytest.mark.integration
@pytest.mark.skipif(not _word_available(), reason="Microsoft Word not installed")
class TestRegenerateFieldsIntegration:
    """Drives real Word. After regen, the DOCX's first TOC field's cached
    runs must contain the body headings we injected and NOT the CAE template
    placeholder strings.
    """

    def test_toc_cache_matches_body_headings(self, tmp_path):
        from datetime import datetime, timezone

        from docx import Document

        from app.config import settings
        from app.pipelines.docs.converter import render_release_notes
        from app.state.models import BinariesState, PatchEntry, ReleaseNotesState
        from app.state.release_notes_models import (
            ParagraphBlock,
            ReleaseNoteItem,
            ReleaseNoteRecord,
        )

        template = settings.docs_template_path
        if not template.exists():
            pytest.skip(f"template not found at {template}")

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
            source_pdf_pages=1,
            items=[
                ReleaseNoteItem(
                    section="New Features",
                    am_card="AM9901",
                    customers=["HAL"],
                    title="Regen Canary Feature",
                    summary="Short.",
                    body=[ParagraphBlock(type="paragraph", text="Body.")],
                ),
                ReleaseNoteItem(
                    section="Defect Fixes",
                    am_card="AM9902",
                    customers=[],
                    title="Regen Canary Fix",
                    summary="Short.",
                    body=[ParagraphBlock(type="paragraph", text="Body.")],
                ),
            ],
        )
        record_path.write_text(record.model_dump_json(indent=2))

        patch = PatchEntry(
            sftp_folder="v8.0.18.1",
            sftp_path="/ACARS_V8_0/ACARS_V8_0_18/v8.0.18.1",
            local_path="patches/ACARS_V8_0/8.0.18.1",
            binaries=BinariesState(status="pending_approval"),
            release_notes=ReleaseNotesState(
                status="extracted",
                record_json_path=str(record_path),
            ),
        )

        render_release_notes(
            patch,
            product_id="ACARS_V8_0",
            version="8.0.18.1",
            template_path=template,
        )

        assert patch.release_notes.status == "converted"
        docx_path = Path(patch.release_notes.generated_docx_path)
        assert docx_path.exists()

        doc = Document(str(docx_path))
        toc_text = _extract_first_toc_cache_text(doc)

        assert "Regen Canary" in toc_text or "New Features" in toc_text, (
            f"TOC cache missing rendered headings. Cache was: {toc_text!r}"
        )
        for placeholder in ("Insert your Heading", "Delete This Chapter"):
            assert placeholder not in toc_text, (
                f"Template placeholder {placeholder!r} still in TOC cache: {toc_text!r}"
            )


def _extract_first_toc_cache_text(doc) -> str:
    """Concatenate the text runs between the first TOC field's separate and end fldChars."""
    from docx.oxml.ns import qn

    body = doc.element.body
    fldChar_tag = qn("w:fldChar")
    fldCharType_attr = qn("w:fldCharType")
    instrText_tag = qn("w:instrText")
    t_tag = qn("w:t")

    elements = list(body.iter())
    toc_begin = None
    for i, elem in enumerate(elements):
        if elem.tag != fldChar_tag or elem.get(fldCharType_attr) != "begin":
            continue
        for j in range(i + 1, min(i + 8, len(elements))):
            nxt = elements[j]
            if nxt.tag == instrText_tag and (nxt.text or "").lstrip().startswith("TOC"):
                toc_begin = i
                break
            if nxt.tag == fldChar_tag:
                break
        if toc_begin is not None:
            break
    if toc_begin is None:
        return ""

    separate_idx = None
    end_idx = None
    for j in range(toc_begin + 1, len(elements)):
        if elements[j].tag == fldChar_tag:
            t = elements[j].get(fldCharType_attr)
            if t == "separate" and separate_idx is None:
                separate_idx = j
            elif t == "end":
                end_idx = j
                break
    if separate_idx is None or end_idx is None:
        return ""

    chunks = []
    for k in range(separate_idx + 1, end_idx):
        if elements[k].tag == t_tag and elements[k].text:
            chunks.append(elements[k].text)
    return "".join(chunks)
