"""Patch status transitions and approval workflows."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.integrations.jira.attachment import upload_attachment, zip_patch_folder
from app.integrations.jira.client import JiraClient
from app.integrations.jira.ticket_builder import build_binaries_payload
from app.state.manager import load_tracker, save_tracker
from app.state.models import PatchEntry, ProductTracker

logger = logging.getLogger("services.patch_service")

BINARIES_TRANSITIONS = {
    "discovered": ["downloaded"],
    "downloaded": ["pending_approval"],
    "pending_approval": ["approved"],
    "approved": ["published"],
    "published": [],
}

RELEASE_NOTES_TRANSITIONS = {
    "not_started": ["downloaded"],
    "downloaded": ["extracted"],
    "extracted": ["converted"],
    "converted": ["pending_approval"],
    "pending_approval": ["approved"],
    "approved": ["pdf_exported"],
    "pdf_exported": ["published"],
    "published": [],
}


class PatchNotFoundError(Exception):
    pass


class InvalidTransitionError(Exception):
    pass


def find_patch(product_id: str, patch_id: str) -> tuple[ProductTracker, str, PatchEntry]:
    """Load tracker and find a specific patch. Returns (tracker, version_key, patch_entry)."""
    tracker = load_tracker(product_id)
    for version_key, version_data in tracker.versions.items():
        if patch_id in version_data.patches:
            return tracker, version_key, version_data.patches[patch_id]
    raise PatchNotFoundError(f"Patch {patch_id} not found in {product_id}")


def validate_transition(current: str, target: str, pipeline: str) -> None:
    """Raise InvalidTransitionError if the transition is not allowed."""
    transitions = BINARIES_TRANSITIONS if pipeline == "binaries" else RELEASE_NOTES_TRANSITIONS
    allowed = transitions.get(current, [])
    if target not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition {pipeline} from '{current}' to '{target}'"
        )


def approve_binaries(
    product_id: str,
    patch_id: str,
    jira_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Approve a patch's binaries pipeline.

    If jira_fields is None/empty: mark as published directly (skip Jira).
    If jira_fields provided: full flow with two-step save.
    """
    tracker, version_key, patch = find_patch(product_id, patch_id)
    now = datetime.now(timezone.utc)

    validate_transition(patch.binaries.status, "approved", "binaries")

    # Step 1: Mark approved + first save
    patch.binaries.status = "approved"
    patch.binaries.approved_at = now
    save_tracker(tracker)
    logger.info("Patch %s binaries approved (product=%s)", patch_id, product_id)

    if not jira_fields:
        # Skip Jira — mark published directly
        patch.binaries.status = "published"
        patch.binaries.published_at = datetime.now(timezone.utc)
        save_tracker(tracker)
        logger.info("Patch %s binaries marked published (no Jira)", patch_id)
        return {"status": "published", "jira": None}

    # Full Jira flow
    jira_config = settings.pipeline_config["pipeline"]["jira"]
    jira_client = JiraClient(
        base_url=settings.JIRA_BASE_URL,
        email=settings.JIRA_EMAIL,
        api_token=settings.JIRA_API_TOKEN_NO_SCOPES,
    )

    # Zip patch folder
    local_path = settings.patches_dir / product_id / patch_id
    zip_bytes = zip_patch_folder(local_path, patch_id)

    # Determine new/existing folder via JQL
    jql_template = jira_config["existing_detection_jql"]
    jql = jql_template.format(version=version_key)
    search_result = jira_client.search_jql(jql)
    is_new = search_result.get("total", 0) == 0

    # Create Jira ticket
    payload = build_binaries_payload(patch_id, version_key, is_new, jira_config)
    ticket = jira_client.create_issue(payload)
    ticket_key = ticket["key"]
    ticket_url = f"{settings.JIRA_BASE_URL}/browse/{ticket_key}"

    # Upload attachment
    upload_attachment(jira_client, ticket_key, patch_id, zip_bytes)

    # Step 2: Mark published + second save
    patch.binaries.status = "published"
    patch.binaries.published_at = datetime.now(timezone.utc)
    patch.binaries.jira_ticket_key = ticket_key
    patch.binaries.jira_ticket_url = ticket_url
    save_tracker(tracker)
    logger.info("Patch %s binaries published (ticket=%s)", patch_id, ticket_key)

    return {"status": "published", "jira": {"key": ticket_key, "url": ticket_url}}


def approve_docs(
    product_id: str,
    patch_id: str,
    jira_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Approve a patch's docs pipeline. Stubbed for MVP — returns skipped."""
    logger.info("Docs approval skipped for %s (not implemented)", patch_id)
    return {"status": "skipped"}
