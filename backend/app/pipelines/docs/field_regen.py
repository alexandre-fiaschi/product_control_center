"""Regenerate DOCX field caches (TOC, indexes) via Microsoft Word.

python-docx has no layout engine so it can't compute page numbers, and
LibreOffice's ``--headless --convert-to pdf`` path skips field regeneration
entirely — PDFs exported from a freshly-rendered DOCX ship the template's
stale TOC cache. We drive Word via AppleScript once at render time to
rebuild the TOC cache in the on-disk DOCX, so every downstream consumer
(preview PDF, published PDF, Open-in-Word) sees fresh entries without
relying on Word's on-open regen.

Per-call cost: ~10-15s (cold Word launch + open + update + save + close).
No long-lived process — Word is activated on demand and closes the file
after saving.

macOS-only. On a Linux deployment, swap the implementation behind the
same ``regenerate_fields`` signature.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger("pipelines.docs.field_regen")

_WORD_APP = Path("/Applications/Microsoft Word.app")
_OSASCRIPT = "/usr/bin/osascript"
_APPLESCRIPT = Path(__file__).parent / "_regen_fields.applescript"

_DEFAULT_TIMEOUT_S = 360


def regenerate_fields(docx_path: Path, timeout_s: int = _DEFAULT_TIMEOUT_S) -> None:
    """Rebuild TOC / index caches inside ``docx_path`` by driving Word.

    Overwrites the file in place. The resulting DOCX's cached TOC runs
    reflect the actual document headings and layout-computed page numbers.

    Raises:
        FileNotFoundError: DOCX missing or Microsoft Word not installed.
        RuntimeError: AppleScript exited non-zero or timed out.
    """
    docx_path = Path(docx_path)
    if not docx_path.is_file():
        raise FileNotFoundError(f"DOCX not found: {docx_path}")

    if not _WORD_APP.exists():
        raise FileNotFoundError(
            f"Microsoft Word not installed at {_WORD_APP}. "
            "Install Word or swap the regenerate_fields backend."
        )

    cmd = [_OSASCRIPT, str(_APPLESCRIPT), str(docx_path)]
    logger.info("field_regen.start path=%s", docx_path)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s, check=False
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("field_regen.timeout path=%s seconds=%d", docx_path, timeout_s)
        raise RuntimeError(
            f"Word field regen timed out after {timeout_s}s on {docx_path.name}"
        ) from exc

    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-500:]
        logger.error(
            "field_regen.failed path=%s rc=%d stderr=%s",
            docx_path, result.returncode, tail,
        )
        raise RuntimeError(
            f"Word field regen exited {result.returncode} on {docx_path.name}: {tail}"
        )

    logger.info(
        "field_regen.success path=%s size=%d",
        docx_path, docx_path.stat().st_size,
    )
