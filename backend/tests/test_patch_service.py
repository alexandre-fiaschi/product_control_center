"""Tests for services.patch_service."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.patch_service import (
    InvalidTransitionError,
    PatchNotFoundError,
    approve_binaries,
    find_patch,
    validate_transition,
)
from app.state.models import (
    BinariesState,
    PatchEntry,
    ProductTracker,
    ReleaseNotesState,
    VersionData,
)


def _make_tracker(binaries_status="pending_approval"):
    return ProductTracker(
        product_id="ACARS_V8_1",
        versions={
            "8.1.0": VersionData(
                patches={
                    "8.1.0.0": PatchEntry(
                        sftp_folder="v8.1.0.0",
                        sftp_path="/ACARS_V8_1/ACARS_V8_1_0/v8.1.0.0",
                        local_path="patches/ACARS_V8_1/8.1.0.0",
                        binaries=BinariesState(
                            status=binaries_status,
                            discovered_at=datetime(2026, 4, 3, tzinfo=timezone.utc),
                            downloaded_at=datetime(2026, 4, 3, tzinfo=timezone.utc),
                        ),
                        release_notes=ReleaseNotesState(status="not_started"),
                    )
                }
            )
        },
    )


class TestValidateTransition:
    def test_valid_binaries_transition(self):
        validate_transition("pending_approval", "approved", "binaries")

    def test_invalid_binaries_transition(self):
        with pytest.raises(InvalidTransitionError):
            validate_transition("published", "approved", "binaries")

    def test_invalid_skip_transition(self):
        with pytest.raises(InvalidTransitionError):
            validate_transition("discovered", "approved", "binaries")


class TestFindPatch:
    @patch("app.services.patch_service.load_tracker")
    def test_finds_existing_patch(self, mock_load):
        mock_load.return_value = _make_tracker()
        tracker, version, patch = find_patch("ACARS_V8_1", "8.1.0.0")
        assert version == "8.1.0"
        assert patch.binaries.status == "pending_approval"

    @patch("app.services.patch_service.load_tracker")
    def test_raises_for_missing_patch(self, mock_load):
        mock_load.return_value = _make_tracker()
        with pytest.raises(PatchNotFoundError):
            find_patch("ACARS_V8_1", "9.9.9.9")


class TestApproveBinaries:
    @patch("app.services.patch_service.save_tracker")
    @patch("app.services.patch_service.load_tracker")
    def test_empty_jira_fields_marks_published(self, mock_load, mock_save):
        mock_load.return_value = _make_tracker()
        result = approve_binaries("ACARS_V8_1", "8.1.0.0", jira_fields=None)

        assert result["status"] == "published"
        assert result["jira"] is None
        # Two saves: one for approved, one for published
        assert mock_save.call_count == 2

    @patch("app.services.patch_service.save_tracker")
    @patch("app.services.patch_service.load_tracker")
    def test_already_published_rejects(self, mock_load, mock_save):
        mock_load.return_value = _make_tracker(binaries_status="published")
        with pytest.raises(InvalidTransitionError):
            approve_binaries("ACARS_V8_1", "8.1.0.0")

    @patch("app.services.patch_service.upload_attachment")
    @patch("app.services.patch_service.zip_patch_folder", return_value=b"zipdata")
    @patch("app.services.patch_service.JiraClient")
    @patch("app.services.patch_service.settings")
    @patch("app.services.patch_service.save_tracker")
    @patch("app.services.patch_service.load_tracker")
    def test_full_jira_flow(self, mock_load, mock_save, mock_settings, mock_jira_cls, mock_zip, mock_upload):
        mock_load.return_value = _make_tracker()

        # Configure settings
        mock_settings.patches_dir = MagicMock()
        mock_settings.patches_dir.__truediv__ = MagicMock(return_value=MagicMock(__truediv__=MagicMock(return_value="/fake/path")))
        mock_settings.JIRA_BASE_URL = "https://jira.example.com"
        mock_settings.JIRA_EMAIL = "test@test.com"
        mock_settings.JIRA_API_TOKEN_NO_SCOPES = "token"
        mock_settings.pipeline_config = {
            "pipeline": {
                "jira": {
                    "project_key": "TEST",
                    "issue_type_id": "10163",
                    "existing_detection_jql": 'project = TEST AND cf[10563] = "Version {version}"',
                    "fields": {
                        "client": {"id": "cf_1", "value": [{"value": "Test"}]},
                        "environment": {"id": "cf_2", "value": {"value": "All"}},
                        "product_name": {"id": "cf_3", "value": "Product"},
                        "release_name": {"id": "cf_4", "template": "Version {version}"},
                        "release_type": {"id": "cf_5", "value": {"value": "Version"}},
                        "release_approval": {"id": "cf_6", "value": {"value": "No approval"}},
                        "create_update_remove": {"id": "cf_7", "values": {"new": {"value": "New"}, "existing": {"value": "Existing"}}},
                    },
                    "summary_templates": {"binaries": "Add Release Version {patch_id}"},
                    "description_template": "Release {version} {new_or_existing} {release_name}",
                },
            },
        }

        # Mock Jira client
        jira_instance = MagicMock()
        mock_jira_cls.return_value = jira_instance
        jira_instance.search_jql.return_value = {"total": 0}
        jira_instance.create_issue.return_value = {"key": "TEST-123"}

        result = approve_binaries("ACARS_V8_1", "8.1.0.0", jira_fields={"some": "fields"})

        assert result["status"] == "published"
        assert result["jira"]["key"] == "TEST-123"
        assert mock_save.call_count == 2  # Two-step save
        jira_instance.create_issue.assert_called_once()
        mock_upload.assert_called_once()

    @patch("app.services.patch_service.JiraClient")
    @patch("app.services.patch_service.zip_patch_folder", return_value=b"zipdata")
    @patch("app.services.patch_service.settings")
    @patch("app.services.patch_service.save_tracker")
    @patch("app.services.patch_service.load_tracker")
    def test_jira_failure_stays_approved(self, mock_load, mock_save, mock_settings, mock_zip, mock_jira_cls):
        mock_load.return_value = _make_tracker()

        mock_settings.patches_dir = MagicMock()
        mock_settings.patches_dir.__truediv__ = MagicMock(return_value=MagicMock(__truediv__=MagicMock(return_value="/fake/path")))
        mock_settings.JIRA_BASE_URL = "https://jira.example.com"
        mock_settings.JIRA_EMAIL = "test@test.com"
        mock_settings.JIRA_API_TOKEN_NO_SCOPES = "token"
        mock_settings.pipeline_config = {"pipeline": {"jira": {
            "existing_detection_jql": 'project = TEST AND cf[10563] = "Version {version}"',
        }}}

        jira_instance = MagicMock()
        mock_jira_cls.return_value = jira_instance
        jira_instance.search_jql.side_effect = Exception("Jira down")

        with pytest.raises(Exception, match="Jira down"):
            approve_binaries("ACARS_V8_1", "8.1.0.0", jira_fields={"some": "fields"})

        # First save happened (approved), but not second (published)
        assert mock_save.call_count == 1
        tracker = mock_load.return_value
        patch = tracker.versions["8.1.0"].patches["8.1.0.0"]
        assert patch.binaries.status == "approved"
