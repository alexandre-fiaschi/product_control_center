"""Coordinates SFTP scan → discover → download → docs fetch → extract → render → save."""

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.integrations.claude.client import ClaudeClient
from app.integrations.sftp.connector import SFTPConnector
from app.integrations.sftp.scanner import discover_patches, update_tracker
from app.integrations.zendesk import ZendeskAuthError, ZendeskClient
from app.pipelines.binaries.fetcher import download_patch
from app.pipelines.docs.converter import extract_release_notes, render_release_notes
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


def _build_claude_client() -> ClaudeClient | None:
    """Build a ClaudeClient if the feature flag is on and the API key is set.

    Returns None if either is missing — meaning "no API calls during this
    scan". The convert pass still runs and uses cached extractions for any
    patch whose record is already on disk; cache misses are logged as a
    clean skip rather than a failure.
    """
    claude_cfg = settings.pipeline_config.get("pipeline", {}).get("claude", {})
    if not claude_cfg.get("enabled"):
        logger.info("scan.claude.disabled reason=feature_flag_off")
        return None
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("scan.claude.disabled reason=missing_api_key")
        return None
    return ClaudeClient.from_settings(settings)


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
    # Same one-build-many-uses pattern for Claude.
    claude_client = _build_claude_client()

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
                        claude_client=claude_client,
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
    total_notes_extracted = sum(r.get("notes_extracted", 0) for r in results.values())
    total_notes_extract_skipped = sum(r.get("notes_extract_skipped", 0) for r in results.values())
    total_notes_extract_failed = sum(r.get("notes_extract_failed", 0) for r in results.values())
    total_notes_rendered = sum(r.get("notes_rendered", 0) for r in results.values())
    total_notes_render_failed = sum(r.get("notes_render_failed", 0) for r in results.values())
    total_errors = sum(1 for r in results.values() if "error" in r)
    logger.info(
        "scan.summary products=%d discovered=%d downloaded=%d failed=%d "
        "notes_downloaded=%d notes_not_found=%d notes_failed=%d "
        "notes_extracted=%d notes_extract_skipped=%d notes_extract_failed=%d "
        "notes_rendered=%d notes_render_failed=%d product_errors=%d",
        len(results), total_discovered, total_downloaded, total_failed,
        total_notes_downloaded, total_notes_not_found, total_notes_failed,
        total_notes_extracted, total_notes_extract_skipped, total_notes_extract_failed,
        total_notes_rendered, total_notes_render_failed,
        total_errors,
    )
    return results


def run_scan_product(
    conn: SFTPConnector,
    product_id: str,
    product_cfg: dict,
    *,
    zendesk_client: ZendeskClient | None = None,
    claude_client: ClaudeClient | None = None,
) -> dict[str, Any]:
    """Scan a single product: discover → download binaries → fetch docs → extract → render → save."""
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

    # Pass 4: Claude extraction (PLAN_DOCS_PIPELINE.md §2 Block B / Unit 5).
    # Walks ALL patches whose release_notes.status == "downloaded". The cache
    # key is the SHA256 of the PDF bytes, so re-runs on the same PDF skip the
    # API call entirely. claude.enabled gates API calls only — when it's off,
    # the pass still runs and extracts any patch whose record is already
    # cached, then logs a clean skip for the rest.
    notes_extracted = 0
    notes_extract_skipped = 0
    notes_extract_failed = 0
    for version_data in tracker.versions.values():
        for pid, patch in version_data.patches.items():
            if patch.release_notes.status != "downloaded":
                continue
            result_holder: dict[str, Any] = {"value": None}

            def work(p=patch, vid=pid):
                result_holder["value"] = extract_release_notes(
                    p,
                    product_id=product_id,
                    version=vid,
                    claude_client=claude_client,
                )

            ok = run_cell(
                patch.release_notes,
                work,
                step_name="extract",
                product=product_id,
                version=pid,
            )
            if ok:
                if result_holder["value"] == "extracted":
                    notes_extracted += 1
                else:
                    notes_extract_skipped += 1
            elif patch.release_notes.last_run.state == "failed":
                notes_extract_failed += 1

    # Pass 5: render DOCX from extracted records. Walks ALL patches whose
    # release_notes.status == "extracted". Always runs — no flag, no API,
    # pure local Python. Idempotent on the orchestrator side because we
    # filter by status == "extracted".
    notes_rendered = 0
    notes_render_failed = 0
    for version_data in tracker.versions.values():
        for pid, patch in version_data.patches.items():
            if patch.release_notes.status != "extracted":
                continue
            ok = run_cell(
                patch.release_notes,
                lambda p=patch, vid=pid: render_release_notes(
                    p,
                    product_id=product_id,
                    version=vid,
                    template_path=settings.docs_template_path,
                ),
                step_name="render",
                product=product_id,
                version=pid,
            )
            if ok:
                notes_rendered += 1
            elif patch.release_notes.last_run.state == "failed":
                notes_render_failed += 1

    # Save tracker
    save_tracker(tracker)
    logger.info(
        "scan.product.summary product=%s discovered=%d downloaded=%d failed=%d "
        "notes_downloaded=%d notes_not_found=%d notes_failed=%d "
        "notes_extracted=%d notes_extract_skipped=%d notes_extract_failed=%d "
        "notes_rendered=%d notes_render_failed=%d",
        product_id, len(new_patch_ids), downloaded, failed,
        notes_downloaded, notes_not_found, notes_failed,
        notes_extracted, notes_extract_skipped, notes_extract_failed,
        notes_rendered, notes_render_failed,
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
        "notes_extracted": notes_extracted,
        "notes_extract_skipped": notes_extract_skipped,
        "notes_extract_failed": notes_extract_failed,
        "notes_rendered": notes_rendered,
        "notes_render_failed": notes_render_failed,
    }
