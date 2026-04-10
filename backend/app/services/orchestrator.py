"""Coordinates SFTP scan → discover → download → docs fetch → update state."""

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.integrations.sftp.connector import SFTPConnector
from app.integrations.sftp.scanner import discover_patches, update_tracker
from app.integrations.zendesk import ZendeskAuthError, ZendeskClient
from app.pipelines.binaries.fetcher import download_patch
from app.pipelines.docs.fetcher import fetch_release_notes
from app.services.lifecycle import run_cell
from app.state.manager import load_tracker, save_tracker

logger = logging.getLogger("services.orchestrator")


def _build_zendesk_client() -> ZendeskClient | None:
    """Build a ZendeskClient if config + credentials are present.

    Returns None (and logs scan.docs.disabled once) if the docs pass should
    be skipped — either because the feature flag is off or the env vars are
    missing. Returning None is intentionally indistinguishable to callers
    from "feature disabled": both mean "do not run the docs pass".
    """
    docs_cfg = settings.pipeline_config.get("pipeline", {}).get("docs", {})
    if not docs_cfg.get("enabled"):
        logger.info("scan.docs.disabled reason=feature_flag_off")
        return None

    zendesk_cfg = docs_cfg.get("zendesk", {})
    subdomain = zendesk_cfg.get("subdomain") or settings.ZENDESK_SUBDOMAIN
    if not (subdomain and settings.ZENDESK_EMAIL and settings.ZENDESK_PASSWORD):
        logger.warning("scan.docs.disabled reason=missing_credentials")
        return None

    try:
        return ZendeskClient(
            subdomain=subdomain,
            email=settings.ZENDESK_EMAIL,
            password=settings.ZENDESK_PASSWORD,
            category_url=zendesk_cfg.get("category_url"),
        )
    except ZendeskAuthError as exc:
        logger.warning("scan.docs.disabled reason=client_init_failed error=%s", exc)
        return None


def run_scan(product_ids: list[str] | None = None) -> dict[str, Any]:
    """Scan SFTP for all (or specified) products. Returns summary of results."""
    products_cfg = settings.pipeline_config["pipeline"]["products"]

    if product_ids is None:
        product_ids = list(products_cfg.keys())

    logger.info("scan.start products=%s", ",".join(product_ids))
    results: dict[str, Any] = {}

    # Build the Zendesk client once for the whole scan. One login session is
    # reused across every product and every patch (1 login → N PDF downloads).
    zendesk_client = _build_zendesk_client()

    try:
        with SFTPConnector(settings) as conn:
            for pid in product_ids:
                if pid not in products_cfg:
                    logger.warning("scan.product.unknown product=%s", pid)
                    results[pid] = {"error": f"Unknown product {pid}"}
                    continue
                try:
                    results[pid] = run_scan_product(
                        conn, pid, products_cfg[pid],
                        zendesk_client=zendesk_client,
                    )
                except Exception:
                    logger.error("scan.product.failed product=%s", pid, exc_info=True)
                    results[pid] = {"error": f"Scan failed for {pid}"}
    finally:
        if zendesk_client is not None:
            zendesk_client.close()

    total_discovered = sum(r.get("new_patches", 0) for r in results.values())
    total_downloaded = sum(r.get("downloaded", 0) for r in results.values())
    total_failed = sum(r.get("failed", 0) for r in results.values())
    total_notes_downloaded = sum(r.get("notes_downloaded", 0) for r in results.values())
    total_notes_not_found = sum(r.get("notes_not_found", 0) for r in results.values())
    total_notes_failed = sum(r.get("notes_failed", 0) for r in results.values())
    total_errors = sum(1 for r in results.values() if "error" in r)
    logger.info(
        "scan.summary products=%d discovered=%d downloaded=%d failed=%d "
        "notes_downloaded=%d notes_not_found=%d notes_failed=%d product_errors=%d",
        len(results), total_discovered, total_downloaded, total_failed,
        total_notes_downloaded, total_notes_not_found, total_notes_failed,
        total_errors,
    )
    return results


def run_scan_product(
    conn: SFTPConnector,
    product_id: str,
    product_cfg: dict,
    *,
    zendesk_client: ZendeskClient | None = None,
) -> dict[str, Any]:
    """Scan a single product: discover → download binaries → fetch docs → save."""
    logger.info("scan.product.start product=%s", product_id)

    tracker = load_tracker(product_id)

    # Pass 1: SFTP discovery
    raw_patches = discover_patches(conn, product_id, product_cfg)
    new_patch_ids = update_tracker(tracker, product_id, raw_patches)

    # Pass 2: binaries download (only for newly discovered patches)
    downloaded = 0
    failed = 0
    for patch_id in new_patch_ids:
        for version_data in tracker.versions.values():
            if patch_id not in version_data.patches:
                continue
            patch = version_data.patches[patch_id]
            ok = run_cell(
                patch.binaries,
                lambda p=patch: download_patch(
                    conn,
                    p.sftp_path,
                    str(settings.patches_dir / product_id / patch_id),
                    product_id=product_id,
                    version=patch_id,
                ),
                step_name="download",
                product=product_id,
                version=patch_id,
            )
            if ok:
                patch.binaries.status = "downloaded"
                patch.binaries.downloaded_at = datetime.now(timezone.utc)
                patch.binaries.status = "pending_approval"
                downloaded += 1
            elif patch.binaries.last_run.state == "failed":
                failed += 1
            # else: lock-skip (cell already running) — not counted as a failure
            break

    # Pass 3: docs fetch from Zendesk (PLAN_DOCS_PIPELINE.md §4.0).
    # Auto-acts on release_notes.status == "not_started" only — never on
    # "not_found" (see §4.2 for the asymmetry). Walks ALL patches in the
    # tracker, not just the newly discovered ones, because an older patch
    # whose binaries landed in a previous scan may still be eligible.
    notes_downloaded = 0
    notes_not_found = 0
    notes_failed = 0
    if zendesk_client is not None:
        for version_data in tracker.versions.values():
            for pid, patch in version_data.patches.items():
                if patch.release_notes.status != "not_started":
                    continue
                ok = run_cell(
                    patch.release_notes,
                    lambda p=patch, vid=pid: fetch_release_notes(
                        zendesk_client,
                        p,
                        product_id=product_id,
                        version=vid,
                        dest_dir=settings.patches_dir / product_id / vid / "release_notes",
                    ),
                    step_name="fetch_release_notes",
                    product=product_id,
                    version=pid,
                )
                if ok:
                    if patch.release_notes.status == "downloaded":
                        notes_downloaded += 1
                    elif patch.release_notes.status == "not_found":
                        notes_not_found += 1
                elif patch.release_notes.last_run.state == "failed":
                    notes_failed += 1

    # Save tracker
    save_tracker(tracker)
    logger.info(
        "scan.product.summary product=%s discovered=%d downloaded=%d failed=%d "
        "notes_downloaded=%d notes_not_found=%d notes_failed=%d",
        product_id, len(new_patch_ids), downloaded, failed,
        notes_downloaded, notes_not_found, notes_failed,
    )

    return {
        "product_id": product_id,
        "new_patches": len(new_patch_ids),
        "downloaded": downloaded,
        "failed": failed,
        "patch_ids": new_patch_ids,
        "notes_downloaded": notes_downloaded,
        "notes_not_found": notes_not_found,
        "notes_failed": notes_failed,
    }
