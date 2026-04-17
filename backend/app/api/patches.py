"""Patch list, detail, and approval endpoints."""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import settings
from app.services.orchestrator import refetch_release_notes
from app.services.patch_service import (
    PatchNotFoundError,
    approve_binaries,
    approve_docs,
    find_patch,
)
from app.state.manager import load_tracker
from app.state.models import ScanRecord
from app.state.scan_history import finalize_scan_record, save_scan_record

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


@router.post("/patches/{product_id}/{patch_id}/release-notes/refetch")
def refetch_release_notes_endpoint(
    product_id: str, patch_id: str
) -> dict[str, Any]:
    """Targeted refetch of release notes for a single patch.

    Eligible when release_notes.status ∈ {not_started, not_found} and the
    per-cell lock is free. Runs Pass 3/4/5 (fetch + extract + render) as a
    single operation. Allowed during a main scan — the per-cell lock is the
    only concurrency barrier.
    """
    scan_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc)
    record = ScanRecord(
        scan_id=scan_id,
        trigger="targeted",
        started_at=started_at,
        products=[product_id],
    )
    save_scan_record(record)

    outcome_for_counts = "error"
    try:
        try:
            result = refetch_release_notes(product_id, patch_id)
        except PatchNotFoundError as exc:
            outcome_for_counts = "patch_not_found"
            raise HTTPException(status_code=404, detail=str(exc))
        outcome_for_counts = result.get("outcome", "error")
    finally:
        duration_ms = int(
            (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
        )
        finalize_scan_record(
            scan_id,
            counts={f"outcome_{outcome_for_counts}": 1},
            duration_ms=duration_ms,
        )

    if result["outcome"] == "not_eligible":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "not eligible",
                "current_status": result.get("release_notes_status"),
            },
        )

    result["scan_id"] = scan_id
    return result


@router.get("/patches/{product_id}/{patch_id}/release-notes/source.pdf")
def get_release_notes_source_pdf(product_id: str, patch_id: str) -> FileResponse:
    try:
        _tracker, _version_key, patch = find_patch(product_id, patch_id)
    except PatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    path_str = patch.release_notes.source_pdf_path
    if not path_str:
        raise HTTPException(status_code=404, detail="Source PDF not available for this patch")

    path = Path(path_str)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{patch_id}-release-notes.pdf",
    )


@router.get("/patches/{product_id}/{patch_id}/release-notes/draft.docx")
def get_release_notes_draft_docx(product_id: str, patch_id: str) -> FileResponse:
    try:
        _tracker, _version_key, patch = find_patch(product_id, patch_id)
    except PatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    path_str = patch.release_notes.generated_docx_path
    if not path_str:
        raise HTTPException(status_code=404, detail="Generated DOCX not available for this patch")

    path = Path(path_str)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{patch_id}-release-notes.docx",
    )


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
