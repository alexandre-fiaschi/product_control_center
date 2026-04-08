"""Integration test — requires real Jira credentials in .env."""

import pytest

from app.config import settings
from app.integrations.jira.client import JiraClient


@pytest.mark.integration
def test_jira_auth():
    """Verify that get_myself() succeeds with the configured credentials."""
    client = JiraClient(
        settings.JIRA_BASE_URL,
        settings.JIRA_EMAIL,
        settings.JIRA_API_TOKEN_NO_SCOPES,
    )
    me = client.get_myself()
    assert "accountId" in me
    assert "displayName" in me
