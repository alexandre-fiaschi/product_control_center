"""Docs pipeline stub — placeholder for Phase 1."""

import logging

logger = logging.getLogger("pipelines.docs.stub")


def process_docs(patch_id: str) -> dict:
    """Placeholder — docs pipeline not implemented in MVP."""
    logger.info("Docs pipeline skipped for %s (not implemented)", patch_id)
    return {"status": "skipped"}
