"""Tests for scan and dashboard API endpoints."""

from unittest.mock import patch

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
    @patch("app.api.pipeline.load_tracker")
    @patch("app.api.pipeline.run_scan")
    def test_scan_success(self, mock_scan, mock_load, client):
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

    @patch("app.api.pipeline.run_scan")
    def test_scan_no_new(self, mock_scan, client):
        mock_scan.return_value = {
            "ACARS_V8_1": {"product_id": "ACARS_V8_1", "new_patches": 0, "downloaded": 0, "patch_ids": []}
        }

        resp = client.post("/api/pipeline/scan")
        data = resp.json()
        assert data["total_new"] == 0
        assert data["new_patches"] == []


class TestScanProduct:
    @patch("app.api.pipeline.load_tracker")
    @patch("app.api.pipeline.run_scan")
    @patch("app.api.pipeline.settings")
    def test_scan_single(self, mock_settings, mock_scan, mock_load, client):
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
