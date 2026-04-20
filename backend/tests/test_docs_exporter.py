"""Tests for the DOCX → PDF exporter (Unit 9)."""

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from app.pipelines.docs import exporter


def _write_docx(path, content=b"PK\x03\x04 fake docx"):
    path.write_bytes(content)


def test_calls_soffice_with_expected_args(tmp_path):
    docx = tmp_path / "8.1.0.0.docx"
    _write_docx(docx)

    def fake_run(cmd, capture_output, text, check):
        # Simulate soffice writing the output file.
        (tmp_path / "8.1.0.0.pdf").write_bytes(b"%PDF-1.4")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(exporter, "_resolve_soffice", return_value="/fake/soffice"), \
         patch.object(exporter.subprocess, "run", side_effect=fake_run) as mock_run:
        result = exporter.export_docx_to_pdf(docx)

    assert result == tmp_path / "8.1.0.0.pdf"
    mock_run.assert_called_once()
    cmd = mock_run.call_args.args[0]
    assert cmd[0] == "/fake/soffice"
    assert "--headless" in cmd
    assert "--convert-to" in cmd
    assert "pdf" in cmd
    assert str(docx) in cmd


def test_reuses_cached_pdf_when_mtime_newer(tmp_path):
    docx = tmp_path / "8.1.0.0.docx"
    _write_docx(docx)
    pdf = tmp_path / "8.1.0.0.pdf"
    pdf.write_bytes(b"%PDF-1.4 cached")

    # Force the PDF mtime to be strictly newer than the DOCX.
    import os
    st = docx.stat()
    os.utime(pdf, (st.st_atime, st.st_mtime + 5))

    with patch.object(exporter, "_resolve_soffice", return_value="/fake/soffice"), \
         patch.object(exporter.subprocess, "run") as mock_run:
        result = exporter.export_docx_to_pdf(docx)

    assert result == pdf
    mock_run.assert_not_called()


def test_reconverts_when_docx_newer_than_cached_pdf(tmp_path):
    docx = tmp_path / "8.1.0.0.docx"
    _write_docx(docx)
    pdf = tmp_path / "8.1.0.0.pdf"
    pdf.write_bytes(b"%PDF-1.4 stale")

    # Force the DOCX mtime newer than the PDF (simulate an edit in Word).
    import os
    st = pdf.stat()
    os.utime(docx, (st.st_atime, st.st_mtime + 5))

    def fake_run(cmd, capture_output, text, check):
        pdf.write_bytes(b"%PDF-1.4 fresh")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(exporter, "_resolve_soffice", return_value="/fake/soffice"), \
         patch.object(exporter.subprocess, "run", side_effect=fake_run) as mock_run:
        result = exporter.export_docx_to_pdf(docx)

    assert result == pdf
    assert pdf.read_bytes() == b"%PDF-1.4 fresh"
    mock_run.assert_called_once()


def test_raises_when_docx_missing(tmp_path):
    docx = tmp_path / "nope.docx"
    with pytest.raises(FileNotFoundError, match="DOCX not found"):
        exporter.export_docx_to_pdf(docx)


def test_raises_when_soffice_missing(tmp_path):
    docx = tmp_path / "8.1.0.0.docx"
    _write_docx(docx)

    with patch.object(exporter, "_resolve_soffice", return_value=None):
        with pytest.raises(FileNotFoundError, match="LibreOffice"):
            exporter.export_docx_to_pdf(docx)


def test_raises_when_soffice_exits_nonzero(tmp_path):
    docx = tmp_path / "8.1.0.0.docx"
    _write_docx(docx)

    with patch.object(exporter, "_resolve_soffice", return_value="/fake/soffice"), \
         patch.object(
            exporter.subprocess,
            "run",
            return_value=MagicMock(returncode=1, stdout="", stderr="boom"),
         ):
        with pytest.raises(RuntimeError, match="soffice exited 1"):
            exporter.export_docx_to_pdf(docx)


def test_raises_when_output_pdf_not_written(tmp_path):
    docx = tmp_path / "8.1.0.0.docx"
    _write_docx(docx)

    # Returncode 0 but no output file — simulate a soffice bug.
    with patch.object(exporter, "_resolve_soffice", return_value="/fake/soffice"), \
         patch.object(
            exporter.subprocess,
            "run",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
         ):
        with pytest.raises(RuntimeError, match="was not written"):
            exporter.export_docx_to_pdf(docx)


def test_writes_to_custom_out_dir(tmp_path):
    docx = tmp_path / "src" / "8.1.0.0.docx"
    docx.parent.mkdir()
    _write_docx(docx)
    out_dir = tmp_path / "cache"

    def fake_run(cmd, capture_output, text, check):
        (out_dir / "8.1.0.0.pdf").write_bytes(b"%PDF-1.4")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(exporter, "_resolve_soffice", return_value="/fake/soffice"), \
         patch.object(exporter.subprocess, "run", side_effect=fake_run) as mock_run:
        result = exporter.export_docx_to_pdf(docx, out_dir=out_dir)

    assert result == out_dir / "8.1.0.0.pdf"
    cmd = mock_run.call_args.args[0]
    assert "--outdir" in cmd
    assert str(out_dir) in cmd


class TestResolveSoffice:
    def test_prefers_env_override(self, monkeypatch):
        monkeypatch.setenv("LIBREOFFICE_BIN", "/custom/soffice")
        assert exporter._resolve_soffice() == "/custom/soffice"

    def test_falls_back_to_which(self, monkeypatch):
        monkeypatch.delenv("LIBREOFFICE_BIN", raising=False)
        with patch.object(exporter.shutil, "which", return_value="/usr/local/bin/soffice"):
            assert exporter._resolve_soffice() == "/usr/local/bin/soffice"

    def test_falls_back_to_macos_default(self, monkeypatch):
        monkeypatch.delenv("LIBREOFFICE_BIN", raising=False)
        with patch.object(exporter.shutil, "which", return_value=None), \
             patch.object(exporter, "_MACOS_DEFAULT") as mock_default:
            mock_default.exists.return_value = True
            mock_default.__str__ = lambda s: "/Applications/LibreOffice.app/Contents/MacOS/soffice"
            result = exporter._resolve_soffice()
            assert result == str(mock_default)

    def test_returns_none_when_nothing_found(self, monkeypatch):
        monkeypatch.delenv("LIBREOFFICE_BIN", raising=False)
        with patch.object(exporter.shutil, "which", return_value=None), \
             patch.object(exporter, "_MACOS_DEFAULT") as mock_default:
            mock_default.exists.return_value = False
            assert exporter._resolve_soffice() is None
