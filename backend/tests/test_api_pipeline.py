"""Tests for scan and dashboard API endpoints."""

from unittest.mock import patch

import pytest

from app.state.models import (
    BinariesState,
    PatchEntry,
    ProductTracker,
    ReleaseNotesState,
    VersionData,
)


def _make_tracker(product_id="ACARS_V8_1"):
    return ProductTracker(
        product_id=product_id,
        last_scanned_at="2026-04-07T10:00:00+00:00",
        versions={
            "8.1.0": VersionData(
                patches={
                    "8.1.0.0": PatchEntry(
                        sftp_folder="v8.1.0.0",
                        sftp_path="/ACARS_V8_1/ACARS_V8_1_0/v8.1.0.0",
                        local_path="patches/ACARS_V8_1/8.1.0.0",
                        binaries=BinariesState(status="pending_approval"),
                        release_notes=ReleaseNotesState(status="published"),
                    ),
                }
            )
        },
    )


PRODUCTS_CFG = {
    "ACARS_V8_1": {"display_name": "ACARS V8.1", "sftp_root": "/ACARS_V8_1"},
}


class TestScanAll:
    @patch("app.api.pipeline.finalize_scan_record")
    @patch("app.api.pipeline.save_scan_record")
    @patch("app.api.pipeline.is_main_scan_running", return_value=False)
    @patch("app.api.pipeline.load_tracker")
    @patch("app.api.pipeline.run_scan")
    def test_scan_success(self, mock_scan, mock_load, mock_running, mock_save, mock_fin, client):
        mock_scan.return_value = {
            "ACARS_V8_1": {
                "product_id": "ACARS_V8_1",
                "new_patches": 1,
                "downloaded": 1,
                "patch_ids": ["8.1.0.0"],
            }
        }
        mock_load.return_value = _make_tracker()

        resp = client.post("/api/pipeline/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_new"] == 1
        assert data["products_scanned"] == ["ACARS_V8_1"]
        assert data["new_patches"][0]["patch_id"] == "8.1.0.0"

        # A scan record was saved at start, finalized on exit.
        assert mock_save.call_count == 1
        assert mock_fin.call_count == 1
        saved_record = mock_save.call_args.args[0]
        assert saved_record.trigger == "manual"
        assert saved_record.finished_at is None

        # Finalize got aggregated counts.
        fin_kwargs = mock_fin.call_args.kwargs
        assert fin_kwargs["counts"]["new_patches"] == 1
        assert fin_kwargs["counts"]["downloaded"] == 1
        assert "duration_ms" in fin_kwargs

    @patch("app.api.pipeline.finalize_scan_record")
    @patch("app.api.pipeline.save_scan_record")
    @patch("app.api.pipeline.is_main_scan_running", return_value=False)
    @patch("app.api.pipeline.run_scan")
    def test_scan_no_new(self, mock_scan, mock_running, mock_save, mock_fin, client):
        mock_scan.return_value = {
            "ACARS_V8_1": {"product_id": "ACARS_V8_1", "new_patches": 0, "downloaded": 0, "patch_ids": []}
        }

        resp = client.post("/api/pipeline/scan")
        data = resp.json()
        assert data["total_new"] == 0
        assert data["new_patches"] == []

    @patch("app.api.pipeline.is_main_scan_running", return_value=True)
    def test_scan_blocked_when_running(self, mock_running, client):
        resp = client.post("/api/pipeline/scan")
        assert resp.status_code == 409
        assert "scan already running" in resp.json()["detail"]

    @patch("app.api.pipeline.finalize_scan_record")
    @patch("app.api.pipeline.save_scan_record")
    @patch("app.api.pipeline.is_main_scan_running", return_value=False)
    @patch("app.api.pipeline.run_scan")
    def test_scan_finalizes_even_on_exception(
        self, mock_scan, mock_running, mock_save, mock_fin, client
    ):
        # TestClient re-raises uncaught server exceptions by default; we only
        # care that the finally block in _run_main_scan ran before propagation.
        mock_scan.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError, match="boom"):
            client.post("/api/pipeline/scan")
        assert mock_fin.call_count == 1


class TestScanProduct:
    @patch("app.api.pipeline.finalize_scan_record")
    @patch("app.api.pipeline.save_scan_record")
    @patch("app.api.pipeline.is_main_scan_running", return_value=False)
    @patch("app.api.pipeline.load_tracker")
    @patch("app.api.pipeline.run_scan")
    @patch("app.api.pipeline.settings")
    def test_scan_single(
        self, mock_settings, mock_scan, mock_load, mock_running, mock_save, mock_fin, client
    ):
        mock_settings.pipeline_config = {"pipeline": {"products": PRODUCTS_CFG}}
        mock_scan.return_value = {
            "ACARS_V8_1": {"product_id": "ACARS_V8_1", "new_patches": 0, "downloaded": 0, "patch_ids": []}
        }

        resp = client.post("/api/pipeline/scan/ACARS_V8_1")
        assert resp.status_code == 200

    @patch("app.api.pipeline.settings")
    def test_scan_unknown_product(self, mock_settings, client):
        mock_settings.pipeline_config = {"pipeline": {"products": {}}}
        resp = client.post("/api/pipeline/scan/UNKNOWN")
        assert resp.status_code == 404


class TestBulkRefetch:
    @patch("app.api.pipeline.finalize_scan_record")
    @patch("app.api.pipeline.save_scan_record")
    @patch("app.api.pipeline.refetch_release_notes")
    @patch("app.api.pipeline.load_tracker")
    @patch("app.api.pipeline.settings")
    def test_bulk_refetch_filters_by_version_prefix(
        self, mock_settings, mock_load, mock_refetch, mock_save, mock_fin, client
    ):
        mock_settings.pipeline_config = {"pipeline": {"products": PRODUCTS_CFG}}
        tracker = _make_tracker()
        tracker.versions["8.0.10"] = VersionData(
            patches={
                "8.0.10.0": PatchEntry(
                    sftp_folder="v8.0.10.0", sftp_path="/x", local_path="p",
                    binaries=BinariesState(status="published"),
                    release_notes=ReleaseNotesState(status="not_found"),
                )
            }
        )
        mock_load.return_value = tracker
        mock_refetch.return_value = {
            "outcome": "downloaded",
            "release_notes_status": "converted",
        }

        resp = client.post("/api/pipeline/scan/release-notes?version=8.1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version_filter"] == "8.1"
        # Only the 8.1.0.0 patch matches the prefix; 8.0.10.0 is filtered out.
        assert data["attempted"] == 1
        assert mock_refetch.call_count == 1
        assert mock_refetch.call_args.args == ("ACARS_V8_1", "8.1.0.0")

    @patch("app.api.pipeline.finalize_scan_record")
    @patch("app.api.pipeline.save_scan_record")
    @patch("app.api.pipeline.refetch_release_notes")
    @patch("app.api.pipeline.load_tracker")
    @patch("app.api.pipeline.settings")
    def test_bulk_refetch_aggregates_outcomes(
        self, mock_settings, mock_load, mock_refetch, mock_save, mock_fin, client
    ):
        mock_settings.pipeline_config = {"pipeline": {"products": PRODUCTS_CFG}}
        mock_load.return_value = _make_tracker()
        mock_refetch.return_value = {
            "outcome": "not_found",
            "release_notes_status": "not_found",
        }

        resp = client.post("/api/pipeline/scan/release-notes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["counts"]["attempted"] == 1
        assert data["counts"]["not_found"] == 1
        assert data["results"][0]["outcome"] == "not_found"

    @patch("app.api.pipeline.is_main_scan_running", return_value=True)
    @patch("app.api.pipeline.finalize_scan_record")
    @patch("app.api.pipeline.save_scan_record")
    @patch("app.api.pipeline.refetch_release_notes")
    @patch("app.api.pipeline.load_tracker")
    @patch("app.api.pipeline.settings")
    def test_bulk_refetch_not_blocked_by_main_scan(
        self, mock_settings, mock_load, mock_refetch, mock_save, mock_fin, mock_running, client
    ):
        # Main scan is "running" but bulk refetch should still run.
        mock_settings.pipeline_config = {"pipeline": {"products": PRODUCTS_CFG}}
        mock_load.return_value = _make_tracker()
        mock_refetch.return_value = {
            "outcome": "downloaded",
            "release_notes_status": "converted",
        }

        resp = client.post("/api/pipeline/scan/release-notes")
        assert resp.status_code == 200


class TestDashboardSummary:
    @patch("app.api.pipeline.load_tracker")
    @patch("app.api.pipeline.settings")
    def test_summary(self, mock_settings, mock_load, client):
        mock_settings.pipeline_config = {"pipeline": {"products": PRODUCTS_CFG}}
        mock_load.return_value = _make_tracker()

        resp = client.get("/api/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_patches"] == 1
        assert data["binaries"]["pending_approval"] == 1
        assert data["release_notes"]["published"] == 1
        assert len(data["by_product"]) == 1
        assert data["by_product"][0]["actionable"] == 1
        assert data["by_product"][0]["published"] == 0

    @patch("app.api.pipeline.load_tracker")
    @patch("app.api.pipeline.settings")
    def test_empty_dashboard(self, mock_settings, mock_load, client):
        mock_settings.pipeline_config = {"pipeline": {"products": PRODUCTS_CFG}}
        mock_load.return_value = ProductTracker(product_id="ACARS_V8_1")

        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        assert data["total_patches"] == 0
        assert data["by_product"][0]["total"] == 0
