"""Zendesk integration — release-notes scraper.

Lifted into production from scripts/test_zendesk_scraper.py. See
PLAN_DOCS_PIPELINE.md unit 3 for the design.
"""

from app.integrations.zendesk.client import (
    ArticleMatch,
    ZendeskAmbiguous,
    ZendeskAuthError,
    ZendeskClient,
    ZendeskNotFound,
)

__all__ = [
    "ArticleMatch",
    "ZendeskAmbiguous",
    "ZendeskAuthError",
    "ZendeskClient",
    "ZendeskNotFound",
]
