"""Patch list, detail, and approval endpoints."""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.services.patch_service import approve_binaries, approve_docs, find_patch
from app.state.manager import load_tracker

logger = logging.getLogger("api.patches")
router = APIRouter(prefix="/api")


def _patch_summary(patch_id: str, version: str, patch, *, include_product: str | None = None) -> dict[str, Any]:
    """Build a patch summary dict for list views."""
    binaries: dict[str, Any] = {
        "status": patch.binaries.status,
        "jira_ticket_key": patch.binaries.jira_ticket_key,
        "jira_ticket_url": patch.binaries.jira_ticket_url,
    }
    if patch.binaries.status == "published" and patch.binaries.published_at:
        binaries["published_at"] = patch.binaries.published_at

    release_notes: dict[str, Any] = {
        "status": patch.release_notes.status,
        "jira_ticket_key": patch.release_notes.jira_ticket_key,
        "jira_ticket_url": patch.release_notes.jira_ticket_url,
    }
    if patch.release_notes.status == "published" and patch.release_notes.published_at:
        release_notes["published_at"] = patch.release_notes.published_at

    item: dict[str, Any] = {
        "patch_id": patch_id,
        "version": version,
        "binaries": binaries,
        "release_notes": release_notes,
    }
    if include_product is not None:
        item["product_id"] = include_product
    return item


def _is_actionable(patch) -> bool:
    return patch.binaries.status != "published" or patch.release_notes.status != "published"


@router.get("/patches")
def list_all_patches(
    status: str | None = Query(None),
    pipeline: str | None = Query(None),
) -> dict[str, Any]:
    products_cfg = settings.pipeline_config.get("pipeline", {}).get("products", {})
    actionable = []
    history = []

    for product_id in products_cfg:
        tracker = load_tracker(product_id)
        for version_key, version_data in tracker.versions.items():
            for patch_id, patch in version_data.patches.items():
                # Apply filters
                if status and pipeline:
                    pipe_obj = patch.binaries if pipeline == "binaries" else patch.release_notes
                    if pipe_obj.status != status:
                        continue
                elif status:
                    if patch.binaries.status != status and patch.release_notes.status != status:
                        continue

                item = _patch_summary(patch_id, version_key, patch, include_product=product_id)
                if _is_actionable(patch):
                    actionable.append(item)
                else:
                    history.append(item)

    return {"actionable": actionable, "history": history}


@router.get("/patches/{product_id}")
def list_product_patches(product_id: str) -> dict[str, Any]:
    products_cfg = settings.pipeline_config.get("pipeline", {}).get("products", {})
    if product_id not in products_cfg:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    tracker = load_tracker(product_id)
    actionable = []
    history = []

    for version_key, version_data in tracker.versions.items():
        for patch_id, patch in version_data.patches.items():
            item = _patch_summary(patch_id, version_key, patch)
            if _is_actionable(patch):
                actionable.append(item)
            else:
                history.append(item)

    return {"product_id": product_id, "actionable": actionable, "history": history}


@router.get("/patches/{product_id}/{patch_id}")
def get_patch_detail(product_id: str, patch_id: str) -> dict[str, Any]:
    tracker, version_key, patch = find_patch(product_id, patch_id)

    # List local files for binaries
    local_dir = settings.patches_dir / product_id / patch_id
    files = []
    if local_dir.exists():
        files = sorted(f.name for f in local_dir.iterdir() if f.is_file())

    binaries = patch.binaries.model_dump(mode="json")
    binaries["files"] = files

    release_notes = patch.release_notes.model_dump(mode="json")

    return {
        "product_id": product_id,
        "patch_id": patch_id,
        "version": version_key,
        "sftp_folder": patch.sftp_folder,
        "sftp_path": patch.sftp_path,
        "local_path": patch.local_path,
        "binaries": binaries,
        "release_notes": release_notes,
    }


@router.post("/patches/{product_id}/{patch_id}/binaries/approve")
def approve_binaries_endpoint(
    product_id: str, patch_id: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    jira_fields = body if body else None
    logger.info("Approving binaries for %s/%s (jira=%s)", product_id, patch_id, bool(jira_fields))

    try:
        result = approve_binaries(product_id, patch_id, jira_fields=jira_fields)
    except Exception as exc:
        # If approval succeeded but Jira failed, patch is stuck at "approved"
        logger.error("Binaries approve failed for %s/%s: %s", product_id, patch_id, exc)
        return {
            "patch_id": patch_id,
            "pipeline": "binaries",
            "status": "approved",
            "error": str(exc),
            "note": "Binaries approved but not published. Retry will attempt Jira again.",
        }

    return {
        "patch_id": patch_id,
        "pipeline": "binaries",
        "status": result["status"],
        "jira_ticket_key": result["jira"]["key"] if result.get("jira") else None,
        "jira_ticket_url": result["jira"]["url"] if result.get("jira") else None,
    }


@router.post("/patches/{product_id}/{patch_id}/docs/approve")
def approve_docs_endpoint(
    product_id: str, patch_id: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    jira_fields = body if body else None
    logger.info("Approving docs for %s/%s", product_id, patch_id)

    try:
        result = approve_docs(product_id, patch_id, jira_fields=jira_fields)
    except Exception as exc:
        logger.error("Docs approve failed for %s/%s: %s", product_id, patch_id, exc)
        return {
            "patch_id": patch_id,
            "pipeline": "docs",
            "status": "approved",
            "error": str(exc),
            "note": "Docs approved but not published. Fix template and retry.",
        }

    return {
        "patch_id": patch_id,
        "pipeline": "docs",
        "status": result["status"],
        "jira_ticket_key": result["jira"]["key"] if result.get("jira") else None,
        "jira_ticket_url": result["jira"]["url"] if result.get("jira") else None,
    }
