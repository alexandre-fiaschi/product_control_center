"""Tests for product API endpoints."""

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
                    "8.1.0.1": PatchEntry(
                        sftp_folder="v8.1.0.1",
                        sftp_path="/ACARS_V8_1/ACARS_V8_1_0/v8.1.0.1",
                        local_path="patches/ACARS_V8_1/8.1.0.1",
                        binaries=BinariesState(status="published"),
                        release_notes=ReleaseNotesState(status="published"),
                    ),
                }
            )
        },
    )


PRODUCTS_CFG = {
    "ACARS_V8_1": {"display_name": "ACARS V8.1", "sftp_root": "/ACARS_V8_1"},
}


class TestListProducts:
    @patch("app.api.products.load_tracker")
    @patch("app.api.products.settings")
    def test_returns_products(self, mock_settings, mock_load, client):
        mock_settings.pipeline_config = {"pipeline": {"products": PRODUCTS_CFG}}
        mock_load.return_value = _make_tracker()

        resp = client.get("/api/products")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["product_id"] == "ACARS_V8_1"
        assert data[0]["display_name"] == "ACARS V8.1"
        assert data[0]["total_patches"] == 2
        assert data[0]["counts"]["binaries"]["pending_approval"] == 1
        assert data[0]["counts"]["binaries"]["published"] == 1

    @patch("app.api.products.load_tracker")
    @patch("app.api.products.settings")
    def test_empty_products(self, mock_settings, mock_load, client):
        mock_settings.pipeline_config = {"pipeline": {"products": {}}}
        resp = client.get("/api/products")
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetProduct:
    @patch("app.api.products.load_tracker")
    @patch("app.api.products.settings")
    def test_returns_detail(self, mock_settings, mock_load, client):
        mock_settings.pipeline_config = {"pipeline": {"products": PRODUCTS_CFG}}
        mock_load.return_value = _make_tracker()

        resp = client.get("/api/products/ACARS_V8_1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["product_id"] == "ACARS_V8_1"
        assert "8.1.0" in data["versions"]
        assert data["versions"]["8.1.0"]["patch_count"] == 2

    @patch("app.api.products.settings")
    def test_not_found(self, mock_settings, client):
        mock_settings.pipeline_config = {"pipeline": {"products": {}}}
        resp = client.get("/api/products/UNKNOWN")
        assert resp.status_code == 404
