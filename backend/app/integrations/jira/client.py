import logging
from typing import Any

import requests

logger = logging.getLogger("jira.client")


class JiraError(Exception):
    """Raised when a Jira API call returns an unexpected HTTP status."""

    def __init__(self, status_code: int, body: str, message: str = ""):
        self.status_code = status_code
        self.body = body
        super().__init__(message or f"Jira HTTP {status_code}: {body[:200]}")


class JiraClient:
    """Low-level wrapper around Jira Cloud REST API v3 using Basic Auth."""

    def __init__(self, base_url: str, email: str, api_token: str):
        self._base_url = base_url.rstrip("/")
        self._auth = (email, api_token)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_jql(self, jql: str, max_results: int = 1) -> dict[str, Any]:
        """Search issues via POST /rest/api/3/search/jql.

        Uses the new POST endpoint (the old GET /search was removed — returns 410).
        """
        url = f"{self._base_url}/rest/api/3/search/jql"
        payload = {
            "jql": jql,
            "maxResults": max_results,
            "fields": ["summary", "customfield_10563"],
        }
        logger.debug("POST %s  payload=%s", url, payload)
        resp = requests.post(
            url,
            auth=self._auth,
            json=payload,
            headers={"Accept": "application/json"},
        )
        logger.debug("Response %s: %s", resp.status_code, resp.text[:300])

        if resp.status_code != 200:
            logger.warning("JQL search failed — HTTP %s: %s", resp.status_code, resp.text[:200])
            raise JiraError(resp.status_code, resp.text)

        data = resp.json()
        logger.info("JQL search returned %s result(s)", data.get("total", 0))
        return data

    # ------------------------------------------------------------------
    # Create issue
    # ------------------------------------------------------------------

    def create_issue(self, payload: dict) -> dict[str, Any]:
        """Create a Jira issue via POST /rest/api/3/issue."""
        url = f"{self._base_url}/rest/api/3/issue"
        logger.debug("POST %s  payload keys=%s", url, list(payload.get("fields", {}).keys()))
        resp = requests.post(
            url,
            auth=self._auth,
            json=payload,
            headers={"Accept": "application/json"},
        )
        logger.debug("Response %s: %s", resp.status_code, resp.text[:300])

        if resp.status_code != 201:
            logger.warning("Create issue failed — HTTP %s: %s", resp.status_code, resp.text[:200])
            raise JiraError(resp.status_code, resp.text)

        data = resp.json()
        logger.info("Created Jira issue %s", data.get("key", "?"))
        return data

    # ------------------------------------------------------------------
    # Attachment
    # ------------------------------------------------------------------

    def add_attachment(self, ticket_key: str, filename: str, file_content: bytes) -> dict[str, Any]:
        """Upload a file attachment to an existing issue.

        Uses multipart/form-data with the required ``X-Atlassian-Token: no-check`` header.
        """
        url = f"{self._base_url}/rest/api/3/issue/{ticket_key}/attachments"
        logger.debug("POST %s  filename=%s  size=%d bytes", url, filename, len(file_content))
        resp = requests.post(
            url,
            auth=self._auth,
            headers={"X-Atlassian-Token": "no-check"},
            files={"file": (filename, file_content, "application/zip")},
        )
        logger.debug("Response %s: %s", resp.status_code, resp.text[:300])

        if resp.status_code not in (200, 201):
            logger.warning("Attachment upload failed — HTTP %s: %s", resp.status_code, resp.text[:200])
            raise JiraError(resp.status_code, resp.text)

        data = resp.json()
        logger.info("Attached %s to %s", filename, ticket_key)
        return data

    # ------------------------------------------------------------------
    # Auth check
    # ------------------------------------------------------------------

    def get_myself(self) -> dict[str, Any]:
        """GET /rest/api/3/myself — quick auth validation."""
        url = f"{self._base_url}/rest/api/3/myself"
        logger.debug("GET %s", url)
        resp = requests.get(
            url,
            auth=self._auth,
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            logger.warning("Auth check failed — HTTP %s", resp.status_code)
            raise JiraError(resp.status_code, resp.text)

        data = resp.json()
        logger.info("Authenticated as %s", data.get("displayName", "?"))
        return data
