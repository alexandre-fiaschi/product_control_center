"""Tests for the docs pass added to services.orchestrator in unit 3.

These cover the third sequential pass: Zendesk client construction, the
auto-eligibility rule (only `not_started`), the kill-switch behaviour when
the feature flag is off or credentials are missing, and the new scan
summary counters.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.zendesk import (
    ArticleMatch,
    ZendeskAuthError,
    ZendeskNotFound,
)
from app.services.orchestrator import (
    _build_zendesk_client,
    run_scan_product,
)
from app.state.models import (
    BinariesState,
    PatchEntry,
    ProductTracker,
    ReleaseNotesState,
    VersionData,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tracker_with_mixed_release_states() -> ProductTracker:
    """Tracker with three patches in different release_notes states.

    Only the `not_started` patch should be auto-acted on by the docs pass.
    """
    return ProductTracker(
        product_id="ACARS_V8_1",
        versions={
            "8.1.16": VersionData(
                patches={
                    "8.1.16.0": PatchEntry(
                        sftp_folder="v8.1.16.0",
                        sftp_path="/ACARS_V8_1/ACARS_V8_1_16/v8.1.16.0",
                        local_path="patches/ACARS_V8_1/8.1.16.0",
                        binaries=BinariesState(status="pending_approval"),
                        release_notes=ReleaseNotesState(status="not_started"),
                    ),
                    "8.1.16.1": PatchEntry(
                        sftp_folder="v8.1.16.1",
                        sftp_path="/ACARS_V8_1/ACARS_V8_1_16/v8.1.16.1",
                        local_path="patches/ACARS_V8_1/8.1.16.1",
                        binaries=BinariesState(status="pending_approval"),
                        # not_found must NOT be retried by auto-scan (PLAN §4.2)
                        release_notes=ReleaseNotesState(status="not_found"),
                    ),
                    "8.1.16.2": PatchEntry(
                        sftp_folder="v8.1.16.2",
                        sftp_path="/ACARS_V8_1/ACARS_V8_1_16/v8.1.16.2",
                        local_path="patches/ACARS_V8_1/8.1.16.2",
                        binaries=BinariesState(status="pending_approval"),
                        release_notes=ReleaseNotesState(status="downloaded"),
                    ),
                }
            )
        },
    )


class FakeZendeskClient:
    """Records calls and returns canned ArticleMatch / exceptions per version."""

    def __init__(self, responses: dict[str, ArticleMatch | Exception]):
        self.responses = responses
        self.find_calls: list[str] = []
        self.download_calls: list[tuple[str, Path]] = []
        self.closed = False

    def find_article_for_version(self, version: str) -> ArticleMatch:
        self.find_calls.append(version)
        resp = self.responses.get(version)
        if isinstance(resp, Exception):
            raise resp
        if resp is None:
            raise ZendeskNotFound(f"no canned response for {version}")
        return resp

    def download_pdf(self, pdf_url: str, dest_path: Path) -> int:
        self.download_calls.append((pdf_url, dest_path))
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(b"%PDF-fake")
        return 9

    def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# _build_zendesk_client
# ---------------------------------------------------------------------------

class TestBuildZendeskClient:
    @patch("app.services.orchestrator.settings")
    def test_disabled_feature_flag_returns_none(self, mock_settings, caplog):
        mock_settings.pipeline_config = {"pipeline": {"docs": {"enabled": False}}}
        with caplog.at_level(logging.INFO, logger="services.orchestrator"):
            assert _build_zendesk_client() is None
        assert any("scan.docs.disabled" in r.message and "feature_flag_off" in r.message
                   for r in caplog.records)

    @patch("app.services.orchestrator.settings")
    def test_missing_credentials_returns_none(self, mock_settings, caplog):
        mock_settings.pipeline_config = {
            "pipeline": {
                "docs": {
                    "enabled": True,
                    "zendesk": {"subdomain": "example"},
                }
            }
        }
        mock_settings.ZENDESK_SUBDOMAIN = ""
        mock_settings.ZENDESK_EMAIL = ""
        mock_settings.ZENDESK_PASSWORD = ""
        with caplog.at_level(logging.WARNING, logger="services.orchestrator"):
            assert _build_zendesk_client() is None
        assert any("missing_credentials" in r.message for r in caplog.records)

    @patch("app.services.orchestrator.settings")
    def test_returns_client_when_configured(self, mock_settings):
        mock_settings.pipeline_config = {
            "pipeline": {
                "docs": {
                    "enabled": True,
                    "zendesk": {
                        "subdomain": "example",
                        "category_url": "https://example.zendesk.com/cat",
                    },
                }
            }
        }
        mock_settings.ZENDESK_SUBDOMAIN = "example"
        mock_settings.ZENDESK_EMAIL = "user@example.com"
        mock_settings.ZENDESK_PASSWORD = "secret"
        client = _build_zendesk_client()
        assert client is not None
        assert client.subdomain == "example"
        assert client.category_url == "https://example.zendesk.com/cat"


# ---------------------------------------------------------------------------
# Docs pass eligibility + counters
# ---------------------------------------------------------------------------

class TestDocsPass:
    @patch("app.services.orchestrator.save_tracker")
    @patch("app.services.orchestrator.settings")
    @patch("app.services.orchestrator.update_tracker", return_value=[])
    @patch("app.services.orchestrator.discover_patches", return_value=[])
    @patch("app.services.orchestrator.load_tracker")
    def test_docs_pass_acts_only_on_not_started(
        self, mock_load, mock_discover, mock_update, mock_settings, mock_save,
        tmp_path: Path,
    ):
        mock_load.return_value = _tracker_with_mixed_release_states()
        mock_settings.patches_dir = tmp_path

        match = ArticleMatch(
            title="8.1.16.0 - Release Notes",
            article_url="https://example.zendesk.com/hc/en-gb/articles/8000",
            pdf_filename="8.1.16.0 - Release Notes.pdf",
            pdf_url="https://example.zendesk.com/hc/article_attachments/9000",
        )
        client = FakeZendeskClient({"8.1.16.0": match})

        result = run_scan_product(
            MagicMock(), "ACARS_V8_1", {"sftp_path": "/V81"},
            zendesk_client=client,
        )

        # Only 8.1.16.0 (not_started) should have been touched.
        assert client.find_calls == ["8.1.16.0"]
        assert len(client.download_calls) == 1
        assert result["notes_downloaded"] == 1
        assert result["notes_not_found"] == 0
        assert result["notes_failed"] == 0

        # Inspect tracker state — passed by reference.
        tracker = mock_load.return_value
        patches = tracker.versions["8.1.16"].patches
        assert patches["8.1.16.0"].release_notes.status == "downloaded"
        assert patches["8.1.16.0"].release_notes.last_run.state == "success"
        # not_found is preserved, NOT retried
        assert patches["8.1.16.1"].release_notes.status == "not_found"
        assert patches["8.1.16.1"].release_notes.last_run.state == "idle"
        # downloaded is preserved
        assert patches["8.1.16.2"].release_notes.status == "downloaded"
        assert patches["8.1.16.2"].release_notes.last_run.state == "idle"

    @patch("app.services.orchestrator.save_tracker")
    @patch("app.services.orchestrator.settings")
    @patch("app.services.orchestrator.update_tracker", return_value=[])
    @patch("app.services.orchestrator.discover_patches", return_value=[])
    @patch("app.services.orchestrator.load_tracker")
    def test_clean_negative_counts_as_not_found(
        self, mock_load, mock_discover, mock_update, mock_settings, mock_save,
        tmp_path: Path,
    ):
        mock_load.return_value = _tracker_with_mixed_release_states()
        mock_settings.patches_dir = tmp_path
        client = FakeZendeskClient({"8.1.16.0": ZendeskNotFound("not yet")})

        result = run_scan_product(
            MagicMock(), "ACARS_V8_1", {"sftp_path": "/V81"},
            zendesk_client=client,
        )

        assert result["notes_downloaded"] == 0
        assert result["notes_not_found"] == 1
        assert result["notes_failed"] == 0
        patch_entry = mock_load.return_value.versions["8.1.16"].patches["8.1.16.0"]
        assert patch_entry.release_notes.status == "not_found"
        assert patch_entry.release_notes.last_run.state == "success"

    @patch("app.services.orchestrator.save_tracker")
    @patch("app.services.orchestrator.settings")
    @patch("app.services.orchestrator.update_tracker", return_value=[])
    @patch("app.services.orchestrator.discover_patches", return_value=[])
    @patch("app.services.orchestrator.load_tracker")
    def test_exception_counts_as_failed_and_workflow_untouched(
        self, mock_load, mock_discover, mock_update, mock_settings, mock_save,
        tmp_path: Path,
    ):
        mock_load.return_value = _tracker_with_mixed_release_states()
        mock_settings.patches_dir = tmp_path
        client = FakeZendeskClient({"8.1.16.0": ZendeskAuthError("cloudflare")})

        result = run_scan_product(
            MagicMock(), "ACARS_V8_1", {"sftp_path": "/V81"},
            zendesk_client=client,
        )

        assert result["notes_downloaded"] == 0
        assert result["notes_not_found"] == 0
        assert result["notes_failed"] == 1
        patch_entry = mock_load.return_value.versions["8.1.16"].patches["8.1.16.0"]
        assert patch_entry.release_notes.status == "not_started"
        assert patch_entry.release_notes.last_run.state == "failed"
        assert patch_entry.release_notes.last_run.step == "fetch_release_notes"
        assert "cloudflare" in patch_entry.release_notes.last_run.error

    @patch("app.services.orchestrator.save_tracker")
    @patch("app.services.orchestrator.settings")
    @patch("app.services.orchestrator.update_tracker", return_value=[])
    @patch("app.services.orchestrator.discover_patches", return_value=[])
    @patch("app.services.orchestrator.load_tracker")
    def test_zendesk_client_none_skips_docs_pass(
        self, mock_load, mock_discover, mock_update, mock_settings, mock_save,
        tmp_path: Path,
    ):
        mock_load.return_value = _tracker_with_mixed_release_states()
        mock_settings.patches_dir = tmp_path

        result = run_scan_product(
            MagicMock(), "ACARS_V8_1", {"sftp_path": "/V81"},
            zendesk_client=None,
        )

        assert result["notes_downloaded"] == 0
        assert result["notes_not_found"] == 0
        assert result["notes_failed"] == 0
        # No patch was touched.
        for pid in ("8.1.16.0", "8.1.16.1", "8.1.16.2"):
            patch_entry = mock_load.return_value.versions["8.1.16"].patches[pid]
            assert patch_entry.release_notes.last_run.state == "idle"
