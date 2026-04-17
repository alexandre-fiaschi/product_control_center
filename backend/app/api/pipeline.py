"""Scan and dashboard endpoints."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.services.orchestrator import refetch_release_notes, run_scan
from app.state.manager import load_tracker
from app.state.models import ScanRecord
from app.state.scan_history import (
    finalize_scan_record,
    is_main_scan_running,
    save_scan_record,
)

logger = logging.getLogger("api.pipeline")
router = APIRouter(prefix="/api")


# Counter keys emitted per-product by run_scan_product(); summed across products
# into the ScanRecord.counts dict. Keep in sync with orchestrator.py.
_SCAN_COUNTER_KEYS = (
    "new_patches",
    "downloaded",
    "failed",
    "notes_downloaded",
    "notes_not_found",
    "notes_failed",
    "notes_extracted",
    "notes_extract_skipped",
    "notes_extract_failed",
    "notes_rendered",
    "notes_render_failed",
)


def _aggregate_counts(results: dict[str, Any]) -> dict[str, int]:
    counts = {k: 0 for k in _SCAN_COUNTER_KEYS}
    product_errors = 0
    for result in results.values():
        if "error" in result:
            product_errors += 1
            continue
        for key in _SCAN_COUNTER_KEYS:
            counts[key] += int(result.get(key, 0))
    counts["product_errors"] = product_errors
    return counts


def _run_main_scan(product_ids: list[str] | None, trigger: str) -> dict[str, Any]:
    if is_main_scan_running():
        logger.warning("scan.main.blocked reason=already_running")
        raise HTTPException(status_code=409, detail="scan already running")

    scan_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc)
    products_for_record = product_ids or list(
        settings.pipeline_config.get("pipeline", {}).get("products", {}).keys()
    )
    record = ScanRecord(
        scan_id=scan_id,
        trigger=trigger,  # type: ignore[arg-type]
        started_at=started_at,
        products=products_for_record,
    )
    save_scan_record(record)
    logger.info(
        "scan.main.start scan_id=%s trigger=%s products=%s",
        scan_id, trigger, ",".join(products_for_record),
    )

    counts: dict[str, int] = {}
    try:
        results = run_scan(product_ids=product_ids)
        counts = _aggregate_counts(results)
        return results
    finally:
        duration_ms = int(
            (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
        )
        finalize_scan_record(scan_id, counts=counts, duration_ms=duration_ms)
        logger.info(
            "scan.main.finished scan_id=%s duration_ms=%d counts=%s",
            scan_id, duration_ms, counts,
        )


@router.post("/pipeline/scan")
def scan_all() -> dict[str, Any]:
    results = _run_main_scan(product_ids=None, trigger="manual")
    return _format_scan_response(results)


# NOTE: registered BEFORE /pipeline/scan/{product_id} so FastAPI matches
# "release-notes" to this endpoint rather than treating it as a product id.
@router.post("/pipeline/scan/release-notes")
def scan_release_notes_bulk(version: str | None = None) -> dict[str, Any]:
    """Bulk targeted-refetch endpoint. `version` is a prefix match on patch_id.

    Not blocked by `is_main_scan_running` — per-cell locks (last_run.state ==
    "running") are the only concurrency barrier. See PLAN_DOCS_PIPELINE.md §4.1.
    """
    scan_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc)
    products_cfg = settings.pipeline_config.get("pipeline", {}).get("products", {})
    version_filter = version or ""

    # Collect all (product_id, patch_id) pairs matching the prefix filter.
    candidates: list[tuple[str, str]] = []
    for product_id in products_cfg.keys():
        tracker = load_tracker(product_id)
        for version_data in tracker.versions.values():
            for patch_id in version_data.patches.keys():
                if patch_id.startswith(version_filter):
                    candidates.append((product_id, patch_id))

    record = ScanRecord(
        scan_id=scan_id,
        trigger="bulk_docs",
        started_at=started_at,
        products=sorted({p for p, _ in candidates}),
    )
    save_scan_record(record)
    logger.info(
        "scan.bulk.start scan_id=%s version_filter=%s candidates=%d",
        scan_id, version_filter, len(candidates),
    )

    results: list[dict[str, Any]] = []
    counts = {
        "attempted": 0,
        "downloaded": 0,
        "not_found": 0,
        "converted": 0,
        "extract_skipped": 0,
        "not_eligible": 0,
        "already_running": 0,
        "failed": 0,
    }
    try:
        for product_id, patch_id in candidates:
            result = refetch_release_notes(product_id, patch_id)
            outcome = result.get("outcome", "failed")
            counts["attempted"] += 1
            if outcome in counts:
                counts[outcome] += 1
            results.append({
                "product_id": product_id,
                "patch_id": patch_id,
                "outcome": outcome,
                "release_notes_status": result.get("release_notes_status"),
            })
    finally:
        duration_ms = int(
            (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
        )
        finalize_scan_record(scan_id, counts=counts, duration_ms=duration_ms)
        logger.info(
            "scan.bulk.finished scan_id=%s attempted=%d duration_ms=%d counts=%s",
            scan_id, counts["attempted"], duration_ms, counts,
        )

    return {
        "scan_id": scan_id,
        "version_filter": version_filter,
        "attempted": counts["attempted"],
        "results": results,
        "counts": counts,
    }


@router.post("/pipeline/scan/{product_id}")
def scan_product(product_id: str) -> dict[str, Any]:
    products_cfg = settings.pipeline_config.get("pipeline", {}).get("products", {})
    if product_id not in products_cfg:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    results = _run_main_scan(product_ids=[product_id], trigger="manual")
    return _format_scan_response(results)


def _format_scan_response(results: dict[str, Any]) -> dict[str, Any]:
    new_patches = []
    for product_id, result in results.items():
        if "error" in result:
            continue
        for pid in result.get("patch_ids", []):
            tracker = load_tracker(product_id)
            for vd in tracker.versions.values():
                if pid in vd.patches:
                    patch = vd.patches[pid]
                    new_patches.append({
                        "product_id": product_id,
                        "patch_id": pid,
                        "binaries_status": patch.binaries.status,
                        "release_notes_status": patch.release_notes.status,
                    })
                    break

    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "products_scanned": list(results.keys()),
        "new_patches": new_patches,
        "total_new": len(new_patches),
    }


@router.get("/dashboard/summary")
def dashboard_summary() -> dict[str, Any]:
    products_cfg = settings.pipeline_config.get("pipeline", {}).get("products", {})

    bin_counts: dict[str, int] = {}
    rn_counts: dict[str, int] = {}
    by_product = []
    total_patches = 0
    last_scan = None

    for product_id, cfg in products_cfg.items():
        tracker = load_tracker(product_id)

        if tracker.last_scanned_at:
            if last_scan is None or tracker.last_scanned_at > last_scan:
                last_scan = tracker.last_scanned_at

        product_total = 0
        product_actionable = 0
        product_published = 0

        for version_data in tracker.versions.values():
            for patch in version_data.patches.values():
                product_total += 1
                bin_counts[patch.binaries.status] = bin_counts.get(patch.binaries.status, 0) + 1
                rn_counts[patch.release_notes.status] = rn_counts.get(patch.release_notes.status, 0) + 1

                both_published = (
                    patch.binaries.status == "published"
                    and patch.release_notes.status == "published"
                )
                if both_published:
                    product_published += 1
                else:
                    product_actionable += 1

        total_patches += product_total
        by_product.append({
            "product_id": product_id,
            "display_name": cfg.get("display_name", product_id),
            "actionable": product_actionable,
            "published": product_published,
            "total": product_total,
        })

    return {
        "total_patches": total_patches,
        "binaries": bin_counts,
        "release_notes": rn_counts,
        "by_product": by_product,
        "last_scan": last_scan,
    }
