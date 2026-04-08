"""Product list and detail endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.state.manager import load_tracker

logger = logging.getLogger("api.products")
router = APIRouter(prefix="/api")


def _count_statuses(tracker) -> dict[str, dict[str, int]]:
    """Count patches by binaries/release_notes status."""
    bin_counts: dict[str, int] = {}
    rn_counts: dict[str, int] = {}
    for version_data in tracker.versions.values():
        for patch in version_data.patches.values():
            bin_counts[patch.binaries.status] = bin_counts.get(patch.binaries.status, 0) + 1
            rn_counts[patch.release_notes.status] = rn_counts.get(patch.release_notes.status, 0) + 1
    return {"binaries": bin_counts, "release_notes": rn_counts}


def _total_patches(tracker) -> int:
    return sum(len(vd.patches) for vd in tracker.versions.values())


@router.get("/products")
def list_products() -> list[dict[str, Any]]:
    products_cfg = settings.pipeline_config.get("pipeline", {}).get("products", {})
    result = []
    for product_id, cfg in products_cfg.items():
        tracker = load_tracker(product_id)
        counts = _count_statuses(tracker)
        result.append({
            "product_id": product_id,
            "display_name": cfg.get("display_name", product_id),
            "last_scanned_at": tracker.last_scanned_at,
            "counts": counts,
            "total_patches": _total_patches(tracker),
        })
    return result


@router.get("/products/{product_id}")
def get_product(product_id: str) -> dict[str, Any]:
    products_cfg = settings.pipeline_config.get("pipeline", {}).get("products", {})
    if product_id not in products_cfg:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    cfg = products_cfg[product_id]
    tracker = load_tracker(product_id)
    counts = _count_statuses(tracker)

    versions = {}
    for version_key, version_data in tracker.versions.items():
        versions[version_key] = {"patch_count": len(version_data.patches)}

    return {
        "product_id": product_id,
        "display_name": cfg.get("display_name", product_id),
        "last_scanned_at": tracker.last_scanned_at,
        "versions": versions,
        "counts": counts,
    }
