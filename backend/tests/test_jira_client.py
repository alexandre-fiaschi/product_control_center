"""Tests for JiraClient — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

import pytest

from app.integrations.jira.client import JiraClient, JiraError


@pytest.fixture
def client():
    return JiraClient("https://example.atlassian.net", "user@test.com", "tok123")


# ------------------------------------------------------------------
# search_jql
# ------------------------------------------------------------------


class TestSearchJql:
    def test_success_returns_dict(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total": 1, "issues": [{"key": "X-1"}]}
        mock_resp.text = "{}"

        with patch("app.integrations.jira.client.requests.post", return_value=mock_resp) as m:
            result = client.search_jql("project = X")
            assert result["total"] == 1
            assert len(result["issues"]) == 1
            # Verify correct endpoint
            call_url = m.call_args[0][0]
            assert call_url.endswith("/rest/api/3/search/jql")

    def test_zero_results(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total": 0, "issues": []}
        mock_resp.text = "{}"

        with patch("app.integrations.jira.client.requests.post", return_value=mock_resp):
            result = client.search_jql("project = X AND summary ~ nothing")
            assert result["total"] == 0

    def test_401_raises_jira_error(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        with patch("app.integrations.jira.client.requests.post", return_value=mock_resp):
            with pytest.raises(JiraError) as exc_info:
                client.search_jql("project = X")
            assert exc_info.value.status_code == 401

    def test_basic_auth_header(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total": 0, "issues": []}
        mock_resp.text = "{}"

        with patch("app.integrations.jira.client.requests.post", return_value=mock_resp) as m:
            client.search_jql("project = X")
            assert m.call_args[1]["auth"] == ("user@test.com", "tok123")


# ------------------------------------------------------------------
# create_issue
# ------------------------------------------------------------------


class TestCreateIssue:
    def test_201_returns_key(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": "1", "key": "PROJ-42", "self": "..."}
        mock_resp.text = "{}"

        with patch("app.integrations.jira.client.requests.post", return_value=mock_resp):
            result = client.create_issue({"fields": {}})
            assert result["key"] == "PROJ-42"

    def test_400_raises_jira_error(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = '{"errors":{"summary":"required"}}'

        with patch("app.integrations.jira.client.requests.post", return_value=mock_resp):
            with pytest.raises(JiraError) as exc_info:
                client.create_issue({"fields": {}})
            assert exc_info.value.status_code == 400


# ------------------------------------------------------------------
# add_attachment
# ------------------------------------------------------------------


class TestAddAttachment:
    def test_includes_no_check_header(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"filename": "test.zip"}]
        mock_resp.text = "[]"

        with patch("app.integrations.jira.client.requests.post", return_value=mock_resp) as m:
            client.add_attachment("PROJ-1", "test.zip", b"data")
            headers = m.call_args[1]["headers"]
            assert headers["X-Atlassian-Token"] == "no-check"

    def test_sends_multipart_file(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"filename": "p.zip"}]
        mock_resp.text = "[]"

        with patch("app.integrations.jira.client.requests.post", return_value=mock_resp) as m:
            client.add_attachment("PROJ-1", "p.zip", b"\x00\x01")
            files = m.call_args[1]["files"]
            assert "file" in files
            fname, content, mime = files["file"]
            assert fname == "p.zip"
            assert content == b"\x00\x01"
            assert mime == "application/zip"


# ------------------------------------------------------------------
# get_myself
# ------------------------------------------------------------------


class TestGetMyself:
    def test_success(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"displayName": "Test User", "accountId": "abc"}
        mock_resp.text = "{}"

        with patch("app.integrations.jira.client.requests.get", return_value=mock_resp):
            result = client.get_myself()
            assert result["displayName"] == "Test User"

    def test_401_raises(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        with patch("app.integrations.jira.client.requests.get", return_value=mock_resp):
            with pytest.raises(JiraError):
                client.get_myself()
