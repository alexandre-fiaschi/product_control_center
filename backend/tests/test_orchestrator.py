"""Tests for services.orchestrator."""

from unittest.mock import MagicMock, patch, call

from app.services.orchestrator import run_scan, run_scan_product
from app.state.models import (
    BinariesState,
    PatchEntry,
    ProductTracker,
    ReleaseNotesState,
    VersionData,
)


def _empty_tracker(product_id="ACARS_V8_1"):
    return ProductTracker(product_id=product_id)


def _tracker_with_patch(product_id="ACARS_V8_1"):
    return ProductTracker(
        product_id=product_id,
        versions={
            "8.1.0": VersionData(
                patches={
                    "8.1.0.0": PatchEntry(
                        sftp_folder="v8.1.0.0",
                        sftp_path="/ACARS_V8_1/ACARS_V8_1_0/v8.1.0.0",
                        local_path="patches/ACARS_V8_1/8.1.0.0",
                        binaries=BinariesState(status="pending_approval"),
                        release_notes=ReleaseNotesState(status="not_started"),
                    )
                }
            )
        },
    )


class TestRunScanProduct:
    @patch("app.services.orchestrator.save_tracker")
    @patch("app.services.orchestrator.download_patch", return_value=3)
    @patch("app.services.orchestrator.settings")
    @patch("app.services.orchestrator.update_tracker", return_value=["8.1.0.0"])
    @patch("app.services.orchestrator.discover_patches")
    @patch("app.services.orchestrator.load_tracker")
    def test_discovers_and_downloads(self, mock_load, mock_discover, mock_update, mock_settings, mock_download, mock_save):
        # update_tracker returns new IDs but we need the tracker to have the patch
        tracker = _empty_tracker()
        mock_load.return_value = tracker

        # After update_tracker is called, the tracker should have the patch
        def fake_update(t, pid, raw):
            t.versions["8.1.0"] = VersionData(
                patches={
                    "8.1.0.0": PatchEntry(
                        sftp_folder="v8.1.0.0",
                        sftp_path="/ACARS_V8_1/ACARS_V8_1_0/v8.1.0.0",
                        local_path="patches/ACARS_V8_1/8.1.0.0",
                        binaries=BinariesState(status="discovered"),
                        release_notes=ReleaseNotesState(status="not_started"),
                    )
                }
            )
            return ["8.1.0.0"]

        mock_update.side_effect = fake_update
        mock_discover.return_value = [{"sftp_folder": "v8.1.0.0", "sftp_path": "/ACARS_V8_1/ACARS_V8_1_0/v8.1.0.0"}]
        mock_settings.patches_dir = MagicMock()

        conn = MagicMock()
        result = run_scan_product(conn, "ACARS_V8_1", {"sftp_path": "/ACARS_V8_1", "track_from": None})

        assert result["new_patches"] == 1
        assert result["downloaded"] == 1
        assert result["failed"] == 0
        mock_save.assert_called_once()

        # Unit 2: binaries.last_run must be populated with a success record.
        patch_entry = tracker.versions["8.1.0"].patches["8.1.0.0"]
        assert patch_entry.binaries.last_run.state == "success"
        assert patch_entry.binaries.last_run.started_at is not None
        assert patch_entry.binaries.last_run.finished_at is not None
        assert patch_entry.binaries.last_run.step is None
        assert patch_entry.binaries.last_run.error is None

    @patch("app.services.orchestrator.save_tracker")
    @patch("app.services.orchestrator.download_patch", side_effect=IOError("permission denied"))
    @patch("app.services.orchestrator.settings")
    @patch("app.services.orchestrator.update_tracker", return_value=["8.1.0.0"])
    @patch("app.services.orchestrator.discover_patches")
    @patch("app.services.orchestrator.load_tracker")
    def test_download_failure_is_recorded_and_does_not_advance_status(
        self, mock_load, mock_discover, mock_update, mock_settings, mock_download, mock_save
    ):
        """Regression: when download_patch raises, the orchestrator must see the
        failure. Previously the fetcher swallowed IOError and returned 0, so the
        orchestrator advanced status to pending_approval for a zero-file download.
        """
        tracker = _empty_tracker()
        mock_load.return_value = tracker

        def fake_update(t, pid, raw):
            t.versions["8.1.0"] = VersionData(
                patches={
                    "8.1.0.0": PatchEntry(
                        sftp_folder="v8.1.0.0",
                        sftp_path="/ACARS_V8_1/ACARS_V8_1_0/v8.1.0.0",
                        local_path="patches/ACARS_V8_1/8.1.0.0",
                        binaries=BinariesState(status="discovered"),
                        release_notes=ReleaseNotesState(status="not_started"),
                    )
                }
            )
            return ["8.1.0.0"]

        mock_update.side_effect = fake_update
        mock_discover.return_value = [{"sftp_folder": "v8.1.0.0", "sftp_path": "/ACARS_V8_1/ACARS_V8_1_0/v8.1.0.0"}]
        mock_settings.patches_dir = MagicMock()

        conn = MagicMock()
        result = run_scan_product(conn, "ACARS_V8_1", {"sftp_path": "/ACARS_V8_1", "track_from": None})

        assert result["new_patches"] == 1
        assert result["downloaded"] == 0
        assert result["failed"] == 1
        # Critical: the patch must NOT have been advanced to pending_approval
        patch_entry = tracker.versions["8.1.0"].patches["8.1.0.0"]
        assert patch_entry.binaries.status == "discovered"
        mock_save.assert_called_once()

        # Unit 2: the failure must be recorded on binaries.last_run.
        assert patch_entry.binaries.last_run.state == "failed"
        assert patch_entry.binaries.last_run.step == "download"
        assert patch_entry.binaries.last_run.error is not None
        assert "permission denied" in patch_entry.binaries.last_run.error
        assert patch_entry.binaries.last_run.finished_at is not None

    @patch("app.services.orchestrator.save_tracker")
    @patch("app.services.orchestrator.update_tracker", return_value=[])
    @patch("app.services.orchestrator.discover_patches")
    @patch("app.services.orchestrator.load_tracker")
    def test_idempotent_no_new_patches(self, mock_load, mock_discover, mock_update, mock_save):
        mock_load.return_value = _tracker_with_patch()
        mock_discover.return_value = [{"sftp_folder": "v8.1.0.0", "sftp_path": "/path"}]

        conn = MagicMock()
        result = run_scan_product(conn, "ACARS_V8_1", {"sftp_path": "/ACARS_V8_1"})

        assert result["new_patches"] == 0
        assert result["downloaded"] == 0
        assert result["failed"] == 0


class TestRunScan:
    @patch("app.services.orchestrator.run_scan_product")
    @patch("app.services.orchestrator.SFTPConnector")
    @patch("app.services.orchestrator.settings")
    def test_scans_all_products(self, mock_settings, mock_sftp_cls, mock_scan_product):
        mock_settings.pipeline_config = {
            "pipeline": {
                "products": {
                    "ACARS_V8_1": {"sftp_path": "/V81"},
                    "ACARS_V8_0": {"sftp_path": "/V80"},
                }
            }
        }
        mock_sftp_cls.return_value.__enter__ = MagicMock()
        mock_sftp_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_scan_product.return_value = {"new_patches": 1, "downloaded": 1}

        results = run_scan()

        assert len(results) == 2
        assert mock_scan_product.call_count == 2

    @patch("app.services.orchestrator.run_scan_product")
    @patch("app.services.orchestrator.SFTPConnector")
    @patch("app.services.orchestrator.settings")
    def test_partial_failure_continues(self, mock_settings, mock_sftp_cls, mock_scan_product):
        mock_settings.pipeline_config = {
            "pipeline": {
                "products": {
                    "ACARS_V8_1": {"sftp_path": "/V81"},
                    "ACARS_V8_0": {"sftp_path": "/V80"},
                }
            }
        }
        mock_sftp_cls.return_value.__enter__ = MagicMock()
        mock_sftp_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_scan_product.side_effect = [
            Exception("SFTP error"),
            {"new_patches": 2, "downloaded": 2},
        ]

        results = run_scan()

        assert "error" in results["ACARS_V8_1"]
        assert results["ACARS_V8_0"]["new_patches"] == 2
