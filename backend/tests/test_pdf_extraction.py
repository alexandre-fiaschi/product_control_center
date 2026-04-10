"""Reference test — benchmark PDF extraction across multiple libraries.

This is a REFERENCE only. It does not run in the normal test suite. It exists
to compare PDF extraction libraries against the same CAE release-note PDFs so
we can pick the right one for the production pipeline. Tables and images are
the most important categories — they're how vendors document changes.

Modes exercised:

  1. fast          — opendataloader-pdf fast mode (Java, deterministic)
  2. pdfplumber    — pure Python, MIT, text + bordered tables
  3. pymupdf       — fitz, AGPL-3.0 (test-only — see PYMUPDF_LICENSE_NOTE below)
  4. pypdfium2     — Google PDFium wrapper, BSD-3, text + image rendering
  5. hybrid-claude — opendataloader-pdf via Claude API (kept for tomorrow)

Run the benchmark with:

    cd backend && pytest tests/test_pdf_extraction.py -v -m reference -s \\
        --pdf=/path/to/release_note.pdf \\
        --pdf-output=/path/to/output_dir

Each mode that can't run is skipped with a clear reason. The summary test
prints a side-by-side comparison at the end.

PYMUPDF_LICENSE_NOTE
--------------------
PyMuPDF (fitz) is AGPL-3.0. It's installed as a test/benchmark dependency only
— DO NOT add it to production requirements.txt without legal review of CAE's
policy on AGPL software in internal services.
"""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from typing import Any

import pytest

# Skip the whole module if the library isn't installed — we don't want to force
# everyone to install Java + opendataloader just to run the normal test suite.
opendataloader_pdf = pytest.importorskip(
    "opendataloader_pdf",
    reason="opendataloader-pdf not installed — reference test only",
)

# Mark every test in this file as `reference`. The `_resolve_pdf` helper skips
# the test when --pdf is not passed, which keeps it out of the normal suite
# (since nobody passes --pdf in CI) while still letting `pytest --pdf=...` run
# the benchmark explicitly.
pytestmark = [pytest.mark.reference]


HYBRID_HOST = "127.0.0.1"
HYBRID_PORT = 5002

# Module-level cache so the summary test can read what each mode produced
# without re-running the conversions. Keyed by mode name.
RESULTS: dict[str, dict[str, Any]] = {}


# ─────────────────────────── helpers ───────────────────────────


def _resolve_pdf(pytestconfig) -> Path:
    """Resolve the --pdf path. Skips the test if --pdf wasn't passed."""
    pdf_arg = pytestconfig.getoption("--pdf", default=None)
    if not pdf_arg:
        pytest.skip("--pdf=<path> not provided — reference test only")
    path = Path(pdf_arg)
    if not path.exists():
        pytest.skip(f"PDF not found: {path}")
    return path


def _resolve_output_root(pytestconfig, tmp_path_factory) -> Path:
    """Persistent output dir if --pdf-output is given, else a tmp dir."""
    out_arg = pytestconfig.getoption("--pdf-output", default=None)
    if out_arg:
        root = Path(out_arg)
        root.mkdir(parents=True, exist_ok=True)
    else:
        root = tmp_path_factory.mktemp("pdf-bench")
    return root


def _hybrid_server_up() -> bool:
    """Quick TCP probe — is the opendataloader-pdf-hybrid server listening?"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect((HYBRID_HOST, HYBRID_PORT))
            return True
        except OSError:
            return False


def _walk_elements(node: Any, type_counts: dict[str, int]) -> None:
    """Recursively tally element `type` fields in a JSON payload."""
    if isinstance(node, dict):
        t = node.get("type") or node.get("element_type")
        if isinstance(t, str):
            type_counts[t] = type_counts.get(t, 0) + 1
        for v in node.values():
            _walk_elements(v, type_counts)
    elif isinstance(node, list):
        for item in node:
            _walk_elements(item, type_counts)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _render_md_table(rows: list[list[Any]]) -> str:
    """Render a list-of-rows as a Markdown pipe-table, robust to ragged rows."""
    if not rows:
        return ""
    cleaned: list[list[str]] = []
    max_cols = 0
    for row in rows:
        if not row:
            continue
        cells = [
            ("" if c is None else str(c))
            .replace("\n", " ")
            .replace("|", "\\|")
            .strip()
            for c in row
        ]
        max_cols = max(max_cols, len(cells))
        cleaned.append(cells)
    if not cleaned:
        return ""
    cleaned = [r + [""] * (max_cols - len(r)) for r in cleaned]
    header = cleaned[0]
    body = cleaned[1:] if len(cleaned) > 1 else []
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def _build_result(
    mode: str,
    output_dir: Path,
    md_path: Path,
    elapsed: float,
    element_types: dict[str, int],
) -> dict[str, Any]:
    markdown = _read_text(md_path)
    return {
        "mode": mode,
        "output_dir": str(output_dir),
        "md_path": str(md_path),
        "elapsed_s": round(elapsed, 2),
        "markdown_chars": len(markdown),
        "markdown_lines": markdown.count("\n") + 1 if markdown else 0,
        "element_total": sum(element_types.values()),
        "element_types": element_types,
        "markdown_preview": markdown[:1500],
    }


# ─────────────── extractors: opendataloader-pdf modes ───────────────


def _run_opendataloader(
    pdf_path: Path,
    output_dir: Path,
    mode: str,
) -> dict[str, Any]:
    """Run opendataloader-pdf in the given mode, return metrics for one PDF."""
    output_dir.mkdir(parents=True, exist_ok=True)

    kwargs: dict[str, Any] = {
        "input_path": [str(pdf_path)],
        "output_dir": str(output_dir),
        "format": "markdown,json",
    }
    if mode == "hybrid-claude":
        kwargs["hybrid"] = "claude"
        kwargs["hybrid_mode"] = "full"

    started = time.perf_counter()
    opendataloader_pdf.convert(**kwargs)
    elapsed = time.perf_counter() - started

    # Read only the files this PDF produced (not the whole output_dir).
    pdf_stem = pdf_path.stem
    md_path = output_dir / f"{pdf_stem}.md"
    json_path = output_dir / f"{pdf_stem}.json"

    type_counts: dict[str, int] = {}
    payload = _read_json(json_path)
    if payload is not None:
        _walk_elements(payload, type_counts)

    return _build_result(mode, output_dir, md_path, elapsed, type_counts)


# ─────────────── extractors: alternative libraries ───────────────


def _extract_with_pdfplumber(pdf_path: Path, output_dir: Path) -> dict[str, Any]:
    """pdfplumber — pure Python, MIT. Text + bordered tables.

    Image extraction here crops the page region as a 150-DPI PNG. That's not
    the original embedded image bytes, but it's the cleanest thing pdfplumber
    exposes and the result is visually equivalent for screenshots.
    """
    import pdfplumber  # noqa: PLC0415

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_stem = pdf_path.stem
    md_path = output_dir / f"{pdf_stem}.md"
    json_path = output_dir / f"{pdf_stem}.json"
    images_dir = output_dir / f"{pdf_stem}_images"

    md_parts: list[str] = []
    counts = {"page": 0, "table": 0, "image": 0}
    pages_meta: list[dict[str, Any]] = []

    started = time.perf_counter()
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            counts["page"] += 1
            md_parts.append(f"\n## Page {i}\n")
            text = page.extract_text() or ""
            md_parts.append(text)

            tables = page.extract_tables() or []
            for j, table in enumerate(tables, start=1):
                md_parts.append(f"\n**Table p{i}.{j}:**\n")
                md_parts.append(_render_md_table(table))
                counts["table"] += 1

            page_images = page.images or []
            for k, img in enumerate(page_images, start=1):
                try:
                    images_dir.mkdir(exist_ok=True)
                    bbox = (
                        max(float(img["x0"]), 0.0),
                        max(float(img["top"]), 0.0),
                        min(float(img["x1"]), float(page.width)),
                        min(float(img["bottom"]), float(page.height)),
                    )
                    cropped = page.crop(bbox).to_image(resolution=150)
                    cropped.save(str(images_dir / f"page{i:03d}_image{k:02d}.png"))
                    counts["image"] += 1
                except Exception as e:
                    md_parts.append(
                        f"\n_(image extraction failed for p{i} img{k}: {e})_\n"
                    )

            pages_meta.append({
                "page": i,
                "text_chars": len(text),
                "tables": len(tables),
                "images": len(page_images),
            })

    elapsed = time.perf_counter() - started

    md_path.write_text("\n".join(md_parts), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {"library": "pdfplumber", "counts": counts, "pages": pages_meta},
            indent=2,
        ),
        encoding="utf-8",
    )

    return _build_result("pdfplumber", output_dir, md_path, elapsed, counts)


def _extract_with_pymupdf(pdf_path: Path, output_dir: Path) -> dict[str, Any]:
    """PyMuPDF (fitz) — AGPL-3.0. Best image extraction (raw bytes) + tables."""
    import fitz  # PyMuPDF  # noqa: PLC0415

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_stem = pdf_path.stem
    md_path = output_dir / f"{pdf_stem}.md"
    json_path = output_dir / f"{pdf_stem}.json"
    images_dir = output_dir / f"{pdf_stem}_images"

    md_parts: list[str] = []
    counts = {"page": 0, "table": 0, "image": 0}
    pages_meta: list[dict[str, Any]] = []

    started = time.perf_counter()
    doc = fitz.open(str(pdf_path))
    try:
        for i, page in enumerate(doc, start=1):
            counts["page"] += 1
            md_parts.append(f"\n## Page {i}\n")
            text = page.get_text() or ""
            md_parts.append(text)

            page_tables = 0
            try:
                table_finder = page.find_tables()
                for j, tbl in enumerate(table_finder.tables, start=1):
                    md_parts.append(f"\n**Table p{i}.{j}:**\n")
                    md_parts.append(_render_md_table(tbl.extract()))
                    counts["table"] += 1
                    page_tables += 1
            except Exception as e:
                md_parts.append(f"\n_(table extraction failed for p{i}: {e})_\n")

            page_images = page.get_images(full=True) or []
            for k, img_info in enumerate(page_images, start=1):
                try:
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    images_dir.mkdir(exist_ok=True)
                    ext = base_image.get("ext", "png")
                    (
                        images_dir / f"page{i:03d}_image{k:02d}.{ext}"
                    ).write_bytes(base_image["image"])
                    counts["image"] += 1
                except Exception as e:
                    md_parts.append(
                        f"\n_(image extraction failed for p{i} img{k}: {e})_\n"
                    )

            pages_meta.append({
                "page": i,
                "text_chars": len(text),
                "tables": page_tables,
                "images": len(page_images),
            })
    finally:
        doc.close()

    elapsed = time.perf_counter() - started

    md_path.write_text("\n".join(md_parts), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {"library": "pymupdf", "counts": counts, "pages": pages_meta},
            indent=2,
        ),
        encoding="utf-8",
    )

    return _build_result("pymupdf", output_dir, md_path, elapsed, counts)


def _extract_with_pypdfium2(pdf_path: Path, output_dir: Path) -> dict[str, Any]:
    """pypdfium2 — BSD wrapper around Google PDFium. No table extraction."""
    import pypdfium2 as pdfium  # noqa: PLC0415

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_stem = pdf_path.stem
    md_path = output_dir / f"{pdf_stem}.md"
    json_path = output_dir / f"{pdf_stem}.json"
    images_dir = output_dir / f"{pdf_stem}_images"

    md_parts: list[str] = []
    counts = {"page": 0, "table": 0, "image": 0}
    pages_meta: list[dict[str, Any]] = []

    started = time.perf_counter()
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        for i, page in enumerate(pdf, start=1):
            counts["page"] += 1
            md_parts.append(f"\n## Page {i}\n")
            text_page = page.get_textpage()
            text = text_page.get_text_range() or ""
            md_parts.append(text)
            text_page.close()

            page_images = 0
            try:
                for k, obj in enumerate(page.get_objects(), start=1):
                    # PDFium image object type constant is int 3.
                    if getattr(obj, "type", None) == 3:
                        try:
                            images_dir.mkdir(exist_ok=True)
                            pil_image = obj.get_bitmap().to_pil()
                            pil_image.save(
                                str(images_dir / f"page{i:03d}_image{k:02d}.png")
                            )
                            counts["image"] += 1
                            page_images += 1
                        except Exception as e:
                            md_parts.append(
                                f"\n_(image extraction failed for p{i} img{k}: {e})_\n"
                            )
            except Exception as e:
                md_parts.append(f"\n_(image enumeration failed for p{i}: {e})_\n")

            pages_meta.append({
                "page": i,
                "text_chars": len(text),
                "tables": 0,
                "images": page_images,
            })
            page.close()
    finally:
        pdf.close()

    elapsed = time.perf_counter() - started

    md_path.write_text("\n".join(md_parts), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {"library": "pypdfium2", "counts": counts, "pages": pages_meta},
            indent=2,
        ),
        encoding="utf-8",
    )

    return _build_result("pypdfium2", output_dir, md_path, elapsed, counts)


# ─────────────────────────── printing ───────────────────────────


def _print_result(result: dict[str, Any]) -> None:
    print(f"\n=== {result['mode']} ===")
    print(f"  output dir   : {result['output_dir']}")
    print(f"  elapsed      : {result['elapsed_s']}s")
    print(
        f"  markdown     : {result['markdown_chars']} chars / "
        f"{result['markdown_lines']} lines"
    )
    print(f"  total elems  : {result['element_total']}")
    print("  element types:")
    for t, n in sorted(result["element_types"].items(), key=lambda kv: -kv[1]):
        print(f"    {t:20s} {n}")
    print("  markdown preview:")
    preview_lines = result["markdown_preview"].splitlines()[:20]
    print("  " + "\n  ".join(preview_lines))


# ─────────────────────────── fixtures ───────────────────────────


@pytest.fixture(scope="module")
def pdf_path(pytestconfig):
    return _resolve_pdf(pytestconfig)


@pytest.fixture(scope="module")
def output_root(pytestconfig, tmp_path_factory):
    root = _resolve_output_root(pytestconfig, tmp_path_factory)
    print(f"\n[pdf-bench] Output root: {root}")
    return root


# ─────────────────────────── tests ───────────────────────────


def test_fast_mode(pdf_path, output_root):
    """opendataloader-pdf fast mode — local Java, no AI, no network."""
    result = _run_opendataloader(pdf_path, output_root / "fast", mode="fast")
    RESULTS["fast"] = result
    _print_result(result)
    assert result["element_total"] > 0, "fast mode produced no elements"


def test_pdfplumber(pdf_path, output_root):
    """pdfplumber — pure Python, MIT. Text + bordered tables."""
    pytest.importorskip("pdfplumber")
    result = _extract_with_pdfplumber(pdf_path, output_root / "pdfplumber")
    RESULTS["pdfplumber"] = result
    _print_result(result)
    assert result["markdown_chars"] > 0, "pdfplumber produced no text"


def test_pymupdf(pdf_path, output_root):
    """PyMuPDF (fitz) — AGPL. Test/benchmark only, NOT for production."""
    pytest.importorskip("fitz")
    result = _extract_with_pymupdf(pdf_path, output_root / "pymupdf")
    RESULTS["pymupdf"] = result
    _print_result(result)
    assert result["markdown_chars"] > 0, "pymupdf produced no text"


def test_pypdfium2(pdf_path, output_root):
    """pypdfium2 — BSD wrapper around Google PDFium. Text + image rendering."""
    pytest.importorskip("pypdfium2")
    result = _extract_with_pypdfium2(pdf_path, output_root / "pypdfium2")
    RESULTS["pypdfium2"] = result
    _print_result(result)
    assert result["markdown_chars"] > 0, "pypdfium2 produced no text"


def test_hybrid_claude(pdf_path, output_root):
    """opendataloader-pdf via Claude API — kept available for tomorrow."""
    if not _hybrid_server_up():
        pytest.skip(
            f"hybrid server not reachable at {HYBRID_HOST}:{HYBRID_PORT} — "
            "start it with: opendataloader-pdf-hybrid --port 5002"
        )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set — required for the claude backend")
    result = _run_opendataloader(
        pdf_path, output_root / "hybrid-claude", mode="hybrid-claude"
    )
    RESULTS["hybrid-claude"] = result
    _print_result(result)
    assert result["element_total"] > 0, "hybrid-claude produced no elements"


def test_summary_compare():
    """Print a side-by-side comparison of every mode that ran. Always passes."""
    if not RESULTS:
        pytest.skip("No mode produced results — nothing to compare")

    print("\n\n" + "=" * 82)
    print("PDF extraction benchmark — side-by-side")
    print("=" * 82)

    header = (
        f"{'mode':14s} {'elapsed':>10s} {'md chars':>10s} "
        f"{'pages':>8s} {'tables':>8s} {'images':>8s}"
    )
    print(header)
    print("-" * len(header))
    for mode, r in RESULTS.items():
        et = r["element_types"]
        # Normalize across libraries: opendataloader uses different keys.
        pages = et.get("page", 0)
        tables = et.get("table", 0)
        images = et.get("image", 0)
        print(
            f"{mode:14s} "
            f"{r['elapsed_s']:>9.2f}s "
            f"{r['markdown_chars']:>10d} "
            f"{pages:>8d} "
            f"{tables:>8d} "
            f"{images:>8d}"
        )

    # Full element-type breakdown (opendataloader has a much richer taxonomy).
    all_types: set[str] = set()
    for r in RESULTS.values():
        all_types.update(r["element_types"].keys())

    if all_types:
        print("\nFull element type counts per mode:")
        col_header = f"  {'type':20s}" + "".join(
            f"{m:>14s}" for m in RESULTS.keys()
        )
        print(col_header)
        print("  " + "-" * (len(col_header) - 2))
        for t in sorted(all_types):
            row = f"  {t:20s}"
            for mode in RESULTS.keys():
                row += f"{RESULTS[mode]['element_types'].get(t, 0):>14d}"
            print(row)

    print("\nOutput files (open the markdown / images folders to compare):")
    for mode, r in RESULTS.items():
        print(f"  {mode:14s} {r['md_path']}")
