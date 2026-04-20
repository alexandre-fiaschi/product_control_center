"""DOCX → PDF export via LibreOffice headless.

Used by the docs review preview endpoint (Unit 9) and the approval publish
flow (Unit 10). Idempotent: re-running on an unchanged DOCX reuses the cached
PDF.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("pipelines.docs.exporter")

_MACOS_DEFAULT = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")


def _resolve_soffice() -> str | None:
    override = os.environ.get("LIBREOFFICE_BIN")
    if override:
        return override
    which = shutil.which("soffice")
    if which:
        return which
    if _MACOS_DEFAULT.exists():
        return str(_MACOS_DEFAULT)
    return None


def export_docx_to_pdf(docx_path: Path, out_dir: Path | None = None) -> Path:
    """Convert ``docx_path`` to PDF, returning the output path.

    The PDF is written to ``out_dir`` (defaults to the DOCX's parent) as
    ``<stem>.pdf`` — LibreOffice derives the output filename from the input.
    If the output PDF already exists and its mtime is >= the DOCX mtime, the
    conversion is skipped and the cached path is returned.

    Raises:
        FileNotFoundError: the DOCX does not exist, or LibreOffice is not
            installed / resolvable.
        RuntimeError: LibreOffice ran but exited non-zero.
    """
    docx_path = Path(docx_path)
    if not docx_path.is_file():
        raise FileNotFoundError(f"DOCX not found: {docx_path}")

    target_dir = Path(out_dir) if out_dir is not None else docx_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = target_dir / f"{docx_path.stem}.pdf"

    if pdf_path.is_file() and pdf_path.stat().st_mtime >= docx_path.stat().st_mtime:
        logger.debug("export_docx_to_pdf cache hit: %s", pdf_path)
        return pdf_path

    soffice = _resolve_soffice()
    if soffice is None:
        raise FileNotFoundError(
            "LibreOffice 'soffice' binary not found. Install via "
            "'brew install --cask libreoffice' or set LIBREOFFICE_BIN."
        )

    cmd = [
        soffice,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(target_dir),
        str(docx_path),
    ]
    logger.info("export_docx_to_pdf: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-500:]
        raise RuntimeError(
            f"soffice exited {result.returncode} converting {docx_path.name}: {tail}"
        )

    if not pdf_path.is_file():
        raise RuntimeError(
            f"soffice reported success but {pdf_path} was not written"
        )

    return pdf_path
