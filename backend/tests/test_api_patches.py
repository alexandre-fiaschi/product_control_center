"""Tests for patch API endpoints."""

from unittest.mock import patch, MagicMock

from app.state.models import (
    BinariesState,
    PatchEntry,
    ProductTracker,
    ReleaseNotesState,
    VersionData,
)
from app.services.patch_service import PatchNotFoundError, InvalidTransitionError


def _make_tracker(product_id="ACARS_V8_1", binaries_status="pending_approval"):
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
                        binaries=BinariesState(status=binaries_status),
                        release_notes=ReleaseNotesState(status="published"),
                    ),
                }
            )
        },
    )


PRODUCTS_CFG = {
    "ACARS_V8_1": {"display_name": "ACARS V8.1", "sftp_root": "/ACARS_V8_1"},
}


class TestListAllPatches:
    @patch("app.api.patches.load_tracker")
    @patch("app.api.patches.settings")
    def test_splits_actionable_history(self, mock_settings, mock_load, client):
        mock_settings.pipeline_config = {"pipeline": {"products": PRODUCTS_CFG}}
        mock_load.return_value = _make_tracker()

        resp = client.get("/api/patches")
        assert resp.status_code == 200
        data = resp.json()
        # binaries=pending_approval, release_notes=published → actionable
        assert len(data["actionable"]) == 1
        assert len(data["history"]) == 0
        assert data["actionable"][0]["product_id"] == "ACARS_V8_1"

    @patch("app.api.patches.load_tracker")
    @patch("app.api.patches.settings")
    def test_published_goes_to_history(self, mock_settings, mock_load, client):
        mock_settings.pipeline_config = {"pipeline": {"products": PRODUCTS_CFG}}
        mock_load.return_value = _make_tracker(binaries_status="published")

        resp = client.get("/api/patches")
        data = resp.json()
        assert len(data["actionable"]) == 0
        assert len(data["history"]) == 1

    @patch("app.api.patches.load_tracker")
    @patch("app.api.patches.settings")
    def test_status_filter(self, mock_settings, mock_load, client):
        mock_settings.pipeline_config = {"pipeline": {"products": PRODUCTS_CFG}}
        mock_load.return_value = _make_tracker()

        resp = client.get("/api/patches?status=published")
        data = resp.json()
        # release_notes is published so it matches
        assert len(data["actionable"]) == 1

        resp = client.get("/api/patches?status=approved")
        data = resp.json()
        assert len(data["actionable"]) == 0


class TestListProductPatches:
    @patch("app.api.patches.load_tracker")
    @patch("app.api.patches.settings")
    def test_returns_patches(self, mock_settings, mock_load, client):
        mock_settings.pipeline_config = {"pipeline": {"products": PRODUCTS_CFG}}
        mock_load.return_value = _make_tracker()

        resp = client.get("/api/patches/ACARS_V8_1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["product_id"] == "ACARS_V8_1"
        assert len(data["actionable"]) == 1

    @patch("app.api.patches.settings")
    def test_product_not_found(self, mock_settings, client):
        mock_settings.pipeline_config = {"pipeline": {"products": {}}}
        resp = client.get("/api/patches/UNKNOWN")
        assert resp.status_code == 404


class TestGetPatchDetail:
    @patch("app.api.patches.settings")
    @patch("app.api.patches.find_patch")
    def test_returns_detail(self, mock_find, mock_settings, client, tmp_path):
        tracker = _make_tracker()
        patch_entry = tracker.versions["8.1.0"].patches["8.1.0.0"]
        mock_find.return_value = (tracker, "8.1.0", patch_entry)
        mock_settings.patches_dir = tmp_path

        # Create fake local files
        patch_dir = tmp_path / "ACARS_V8_1" / "8.1.0.0"
        patch_dir.mkdir(parents=True)
        (patch_dir / "installer.exe").touch()
        (patch_dir / "readme.txt").touch()

        resp = client.get("/api/patches/ACARS_V8_1/8.1.0.0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["patch_id"] == "8.1.0.0"
        assert data["version"] == "8.1.0"
        assert set(data["binaries"]["files"]) == {"installer.exe", "readme.txt"}

    @patch("app.api.patches.find_patch")
    def test_not_found(self, mock_find, client):
        mock_find.side_effect = PatchNotFoundError("not found")
        resp = client.get("/api/patches/ACARS_V8_1/NOPE")
        assert resp.status_code == 404


class TestApproveBinaries:
    @patch("app.api.patches.approve_binaries")
    def test_approve_no_jira(self, mock_approve, client):
        mock_approve.return_value = {"status": "published", "jira": None}

        resp = client.post("/api/patches/ACARS_V8_1/8.1.0.0/binaries/approve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "published"
        assert data["jira_ticket_key"] is None
        mock_approve.assert_called_once_with("ACARS_V8_1", "8.1.0.0", jira_fields=None)

    @patch("app.api.patches.approve_binaries")
    def test_approve_with_jira(self, mock_approve, client):
        mock_approve.return_value = {
            "status": "published",
            "jira": {"key": "CFSSOCP-1234", "url": "https://jira/browse/CFSSOCP-1234"},
        }

        resp = client.post(
            "/api/patches/ACARS_V8_1/8.1.0.0/binaries/approve",
            json={"summary": "test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["jira_ticket_key"] == "CFSSOCP-1234"
        mock_approve.assert_called_once_with("ACARS_V8_1", "8.1.0.0", jira_fields={"summary": "test"})

    @patch("app.api.patches.approve_binaries")
    def test_approve_jira_failure(self, mock_approve, client):
        mock_approve.side_effect = Exception("Jira 401")

        resp = client.post(
            "/api/patches/ACARS_V8_1/8.1.0.0/binaries/approve",
            json={"summary": "test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert "Jira 401" in data["error"]

    @patch("app.api.patches.approve_binaries")
    def test_invalid_transition(self, mock_approve, client):
        mock_approve.side_effect = InvalidTransitionError("bad transition")

        resp = client.post("/api/patches/ACARS_V8_1/8.1.0.0/binaries/approve")
        # The exception is caught by the endpoint's try/except, not the handler
        # because InvalidTransitionError is a subclass of Exception
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"


class TestApproveDocs:
    @patch("app.api.patches.approve_docs")
    def test_approve_docs_stubbed(self, mock_approve, client):
        mock_approve.return_value = {"status": "skipped"}

        resp = client.post("/api/patches/ACARS_V8_1/8.1.0.0/docs/approve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "skipped"
