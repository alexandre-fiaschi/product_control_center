"""Scan and dashboard endpoints."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.services.orchestrator import run_scan
from app.state.manager import load_tracker

logger = logging.getLogger("api.pipeline")
router = APIRouter(prefix="/api")


@router.post("/pipeline/scan")
def scan_all() -> dict[str, Any]:
    logger.info("Triggering scan for all products")
    results = run_scan()
    return _format_scan_response(results)


@router.post("/pipeline/scan/{product_id}")
def scan_product(product_id: str) -> dict[str, Any]:
    products_cfg = settings.pipeline_config.get("pipeline", {}).get("products", {})
    if product_id not in products_cfg:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    logger.info("Triggering scan for %s", product_id)
    results = run_scan(product_ids=[product_id])
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
