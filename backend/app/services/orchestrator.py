"""Coordinates SFTP scan → discover → download → update state."""

import logging
from typing import Any

from app.config import settings
from app.integrations.sftp.connector import SFTPConnector
from app.integrations.sftp.scanner import discover_patches, update_tracker
from app.pipelines.binaries.fetcher import download_patch
from app.state.manager import load_tracker, save_tracker

logger = logging.getLogger("services.orchestrator")


def run_scan(product_ids: list[str] | None = None) -> dict[str, Any]:
    """Scan SFTP for all (or specified) products. Returns summary of results."""
    products_cfg = settings.pipeline_config["pipeline"]["products"]

    if product_ids is None:
        product_ids = list(products_cfg.keys())

    logger.info("Starting scan for products: %s", product_ids)
    results: dict[str, Any] = {}

    with SFTPConnector(settings) as conn:
        for pid in product_ids:
            if pid not in products_cfg:
                logger.warning("Unknown product %s, skipping", pid)
                results[pid] = {"error": f"Unknown product {pid}"}
                continue
            try:
                results[pid] = run_scan_product(conn, pid, products_cfg[pid])
            except Exception:
                logger.error("Scan failed for %s", pid, exc_info=True)
                results[pid] = {"error": f"Scan failed for {pid}"}

    logger.info("Scan complete: %s", {k: v.get("new_patches", v.get("error", "?")) for k, v in results.items()})
    return results


def run_scan_product(conn: SFTPConnector, product_id: str, product_cfg: dict) -> dict[str, Any]:
    """Scan a single product: discover → download → update tracker."""
    logger.info("Scanning product %s", product_id)

    tracker = load_tracker(product_id)

    # Discover patches on SFTP
    raw_patches = discover_patches(conn, product_id, product_cfg)

    # Update tracker with new patches (status=discovered)
    new_patch_ids = update_tracker(tracker, product_id, raw_patches)

    # Download each new patch
    downloaded = 0
    for patch_id in new_patch_ids:
        for version_data in tracker.versions.values():
            if patch_id not in version_data.patches:
                continue
            patch = version_data.patches[patch_id]
            try:
                file_count = download_patch(conn, patch.sftp_path, str(settings.patches_dir / product_id / patch_id))
                patch.binaries.status = "downloaded"
                from datetime import datetime, timezone
                patch.binaries.downloaded_at = datetime.now(timezone.utc)
                patch.binaries.status = "pending_approval"
                downloaded += 1
                logger.info("Downloaded patch %s (%d files)", patch_id, file_count)
            except Exception:
                logger.error("Failed to download patch %s", patch_id, exc_info=True)
            break

    # Save tracker
    save_tracker(tracker)
    logger.info("Product %s scan done: %d discovered, %d downloaded", product_id, len(new_patch_ids), downloaded)

    return {
        "product_id": product_id,
        "new_patches": len(new_patch_ids),
        "downloaded": downloaded,
        "patch_ids": new_patch_ids,
    }
