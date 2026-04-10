"""Docs pipeline — Block A: discover + download release notes from Zendesk.

This module owns the workflow-status transitions for the release_notes track.
HTTP, auth, and HTML parsing live in app/integrations/zendesk/. Run-status
bookkeeping (last_run) is owned by app/services/lifecycle.run_cell — this
function is meant to be called from inside it.

See PLAN_DOCS_PIPELINE.md §2 Block A and §3 for the contract.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from app.integrations.zendesk import (
    ZendeskAmbiguous,
    ZendeskClient,
    ZendeskNotFound,
)
from app.integrations.zendesk.parsers import safe_name
from app.state.models import PatchEntry

logger = logging.getLogger("pipelines.docs.fetcher")


def fetch_release_notes(
    client: ZendeskClient,
    patch: PatchEntry,
    *,
    product_id: str,
    version: str,
    dest_dir: Path,
) -> None:
    """Discover and download the Zendesk release-notes PDF for one patch.

    Workflow status transitions (only this function may touch them):
      - Happy path: not_started → discovered → downloaded
      - Clean negative (no article / multiple matches): not_started → not_found
      - Exception (login, network, HTTP, IO): WORKFLOW STATUS UNTOUCHED.
        Run status is recorded by run_cell when the exception propagates.

    The asymmetry is the whole point of PLAN §4.2: not_found is reachable
    only by an explicit, clean Zendesk response. Anything murky leaves the
    cell in not_started so that auto-scan retries it next tick.
    """
    cell = patch.release_notes

    try:
        match = client.find_article_for_version(version)
    except ZendeskNotFound:
        logger.info(
            "zendesk.fetch.no_match product=%s version=%s",
            product_id, version,
        )
        cell.status = "not_found"
        return
    except ZendeskAmbiguous as exc:
        logger.warning(
            "zendesk.fetch.ambiguous_match product=%s version=%s candidates=%d",
            product_id, version, len(exc.candidates),
        )
        cell.status = "not_found"
        return

    # Match found — advance to discovered, download the PDF, advance to downloaded.
    now = datetime.now(timezone.utc)
    cell.status = "discovered"
    cell.discovered_at = now
    cell.source_url = match.article_url

    dest_path = dest_dir / safe_name(match.pdf_filename)
    client.download_pdf(match.pdf_url, dest_path)

    cell.status = "downloaded"
    cell.downloaded_at = datetime.now(timezone.utc)
    cell.source_pdf_path = str(dest_path)
    logger.info(
        "zendesk.fetch.success product=%s version=%s pdf=%s",
        product_id, version, dest_path,
    )
