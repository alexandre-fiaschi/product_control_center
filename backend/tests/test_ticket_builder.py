"""Tests for Jira ticket payload builder — pure functions, no I/O."""

import json
from pathlib import Path

from app.integrations.jira.ticket_builder import (
    build_binaries_payload,
    build_docs_payload,
    text_to_adf,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
with open(PROJECT_ROOT / "config" / "pipeline.json") as f:
    JIRA_CONFIG = json.load(f)["pipeline"]["jira"]


# ------------------------------------------------------------------
# text_to_adf
# ------------------------------------------------------------------


class TestTextToAdf:
    def test_multiline(self):
        adf = text_to_adf("hello\nworld")
        content = adf["content"][0]["content"]
        types = [n["type"] for n in content]
        assert types == ["text", "hardBreak", "text"]
        assert content[0]["text"] == "hello"
        assert content[2]["text"] == "world"

    def test_single_line_no_hardbreak(self):
        adf = text_to_adf("single line")
        content = adf["content"][0]["content"]
        assert len(content) == 1
        assert content[0] == {"type": "text", "text": "single line"}

    def test_adf_structure(self):
        adf = text_to_adf("test")
        assert adf["version"] == 1
        assert adf["type"] == "doc"
        assert len(adf["content"]) == 1
        assert adf["content"][0]["type"] == "paragraph"


# ------------------------------------------------------------------
# build_binaries_payload
# ------------------------------------------------------------------

EXPECTED_FIELD_IDS = {
    "project",
    "issuetype",
    "summary",
    "description",
    "customfield_10328",
    "customfield_10538",
    "customfield_10562",
    "customfield_10563",
    "customfield_10616",
    "customfield_10617",
    "customfield_10618",
}


class TestBuildBinariesPayload:
    def test_has_all_10_fields(self):
        payload = build_binaries_payload("8.1.11.0", "8.1.11", True, JIRA_CONFIG)
        fields = payload["fields"]
        # 11 keys: project, issuetype, summary, description + 7 custom fields = 11
        assert set(fields.keys()) == EXPECTED_FIELD_IDS

    def test_new_folder(self):
        payload = build_binaries_payload("8.1.11.0", "8.1.11", True, JIRA_CONFIG)
        assert payload["fields"]["customfield_10618"] == {"value": "New CAE Portal Release"}

    def test_existing_folder(self):
        payload = build_binaries_payload("8.1.11.0", "8.1.11", False, JIRA_CONFIG)
        assert payload["fields"]["customfield_10618"] == {"value": "Existing CAE Portal Release"}

    def test_summary_template(self):
        payload = build_binaries_payload("8.1.11.0", "8.1.11", True, JIRA_CONFIG)
        assert payload["fields"]["summary"] == "Add Release Version 8.1.11.0"

    def test_release_name(self):
        payload = build_binaries_payload("8.1.11.0", "8.1.11", True, JIRA_CONFIG)
        assert payload["fields"]["customfield_10563"] == "Version 8.1.11"

    def test_project_key(self):
        payload = build_binaries_payload("8.1.11.0", "8.1.11", True, JIRA_CONFIG)
        assert payload["fields"]["project"] == {"key": "CFSSOCP"}

    def test_issue_type(self):
        payload = build_binaries_payload("8.1.11.0", "8.1.11", True, JIRA_CONFIG)
        assert payload["fields"]["issuetype"] == {"id": "10163"}


# ------------------------------------------------------------------
# build_docs_payload
# ------------------------------------------------------------------


class TestBuildDocsPayload:
    def test_docs_summary_template(self):
        payload = build_docs_payload("8.1.11.0", "8.1.11", True, JIRA_CONFIG)
        assert payload["fields"]["summary"] == "Add Release notes 8.1.11.0"

    def test_docs_has_all_fields(self):
        payload = build_docs_payload("8.1.11.0", "8.1.11", True, JIRA_CONFIG)
        assert set(payload["fields"].keys()) == EXPECTED_FIELD_IDS
