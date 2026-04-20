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
        item = data["actionable"][0]
        assert item["product_id"] == "ACARS_V8_1"
        # last_run must be present on both tracks so the UI can render indicators
        assert item["binaries"]["last_run"]["state"] == "idle"
        assert item["release_notes"]["last_run"]["state"] == "idle"

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


class TestRefetchReleaseNotes:
    @patch("app.api.patches.finalize_scan_record")
    @patch("app.api.patches.save_scan_record")
    @patch("app.api.patches.refetch_release_notes")
    def test_refetch_success(self, mock_refetch, mock_save, mock_fin, client):
        mock_refetch.return_value = {
            "outcome": "converted",
            "product_id": "ACARS_V8_1",
            "patch_id": "8.1.0.0",
            "release_notes_status": "converted",
            "last_run": {"state": "success"},
        }
        resp = client.post(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/refetch"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["outcome"] == "converted"
        assert data["release_notes_status"] == "converted"
        assert "scan_id" in data

        saved_record = mock_save.call_args.args[0]
        assert saved_record.trigger == "targeted"
        assert mock_fin.call_count == 1

    @patch("app.api.patches.finalize_scan_record")
    @patch("app.api.patches.save_scan_record")
    @patch("app.api.patches.refetch_release_notes")
    def test_refetch_not_eligible_returns_409(
        self, mock_refetch, mock_save, mock_fin, client
    ):
        mock_refetch.return_value = {
            "outcome": "not_eligible",
            "product_id": "ACARS_V8_1",
            "patch_id": "8.1.0.0",
            "release_notes_status": "pending_approval",
            "last_run": {"state": "success"},
        }
        resp = client.post(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/refetch"
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["current_status"] == "pending_approval"

    @patch("app.api.patches.finalize_scan_record")
    @patch("app.api.patches.save_scan_record")
    @patch("app.api.patches.refetch_release_notes")
    def test_refetch_already_running_returns_200(
        self, mock_refetch, mock_save, mock_fin, client
    ):
        # Per-cell lock — return 200 with outcome=already_running (could be
        # the main scan legitimately processing this cell).
        mock_refetch.return_value = {
            "outcome": "already_running",
            "product_id": "ACARS_V8_1",
            "patch_id": "8.1.0.0",
            "release_notes_status": "not_started",
            "last_run": {"state": "running"},
        }
        resp = client.post(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/refetch"
        )
        assert resp.status_code == 200
        assert resp.json()["outcome"] == "already_running"

    @patch("app.api.patches.finalize_scan_record")
    @patch("app.api.patches.save_scan_record")
    @patch("app.api.patches.refetch_release_notes")
    def test_refetch_patch_not_found_returns_404(
        self, mock_refetch, mock_save, mock_fin, client
    ):
        mock_refetch.side_effect = PatchNotFoundError("nope")
        resp = client.post(
            "/api/patches/ACARS_V8_1/NOPE/release-notes/refetch"
        )
        assert resp.status_code == 404
        # Record was still finalized.
        assert mock_fin.call_count == 1

    @patch("app.api.patches.finalize_scan_record")
    @patch("app.api.patches.save_scan_record")
    @patch("app.api.patches.refetch_release_notes")
    def test_refetch_not_found_outcome(
        self, mock_refetch, mock_save, mock_fin, client
    ):
        # Zendesk looked and there's no article — clean-negative, 200.
        mock_refetch.return_value = {
            "outcome": "not_found",
            "product_id": "ACARS_V8_1",
            "patch_id": "8.1.0.0",
            "release_notes_status": "not_found",
            "last_run": {"state": "success"},
        }
        resp = client.post(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/refetch"
        )
        assert resp.status_code == 200
        assert resp.json()["outcome"] == "not_found"


def _tracker_with_release_notes(
    *,
    source_pdf_path: str | None = None,
    generated_docx_path: str | None = None,
):
    tracker = _make_tracker()
    rn = tracker.versions["8.1.0"].patches["8.1.0.0"].release_notes
    rn.source_pdf_path = source_pdf_path
    rn.generated_docx_path = generated_docx_path
    patch_entry = tracker.versions["8.1.0"].patches["8.1.0.0"]
    return tracker, patch_entry


class TestGetSourcePdf:
    @patch("app.api.patches.find_patch")
    def test_returns_pdf_file(self, mock_find, client, tmp_path):
        pdf_path = tmp_path / "8.1.0.0.pdf"
        pdf_bytes = b"%PDF-1.4 fake pdf bytes"
        pdf_path.write_bytes(pdf_bytes)

        tracker, patch_entry = _tracker_with_release_notes(
            source_pdf_path=str(pdf_path)
        )
        mock_find.return_value = (tracker, "8.1.0", patch_entry)

        resp = client.get(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/source.pdf"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content == pdf_bytes

    @patch("app.api.patches.find_patch")
    def test_404_when_path_is_none(self, mock_find, client):
        tracker, patch_entry = _tracker_with_release_notes(source_pdf_path=None)
        mock_find.return_value = (tracker, "8.1.0", patch_entry)

        resp = client.get(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/source.pdf"
        )
        assert resp.status_code == 404

    @patch("app.api.patches.find_patch")
    def test_404_when_file_missing_on_disk(self, mock_find, client, tmp_path):
        missing = tmp_path / "does-not-exist.pdf"
        tracker, patch_entry = _tracker_with_release_notes(
            source_pdf_path=str(missing)
        )
        mock_find.return_value = (tracker, "8.1.0", patch_entry)

        resp = client.get(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/source.pdf"
        )
        assert resp.status_code == 404

    @patch("app.api.patches.find_patch")
    def test_404_when_patch_not_found(self, mock_find, client):
        mock_find.side_effect = PatchNotFoundError("not found")
        resp = client.get(
            "/api/patches/ACARS_V8_1/NOPE/release-notes/source.pdf"
        )
        assert resp.status_code == 404


class TestGetDraftDocx:
    DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    @patch("app.api.patches.find_patch")
    def test_returns_docx_file(self, mock_find, client, tmp_path):
        docx_path = tmp_path / "8.1.0.0.docx"
        docx_bytes = b"PK\x03\x04 fake docx bytes"
        docx_path.write_bytes(docx_bytes)

        tracker, patch_entry = _tracker_with_release_notes(
            generated_docx_path=str(docx_path)
        )
        mock_find.return_value = (tracker, "8.1.0", patch_entry)

        resp = client.get(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/draft.docx"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == self.DOCX_MIME
        assert resp.content == docx_bytes

    @patch("app.api.patches.find_patch")
    def test_404_when_path_is_none(self, mock_find, client):
        tracker, patch_entry = _tracker_with_release_notes(
            generated_docx_path=None
        )
        mock_find.return_value = (tracker, "8.1.0", patch_entry)

        resp = client.get(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/draft.docx"
        )
        assert resp.status_code == 404

    @patch("app.api.patches.find_patch")
    def test_404_when_file_missing_on_disk(self, mock_find, client, tmp_path):
        missing = tmp_path / "does-not-exist.docx"
        tracker, patch_entry = _tracker_with_release_notes(
            generated_docx_path=str(missing)
        )
        mock_find.return_value = (tracker, "8.1.0", patch_entry)

        resp = client.get(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/draft.docx"
        )
        assert resp.status_code == 404

    @patch("app.api.patches.find_patch")
    def test_404_when_patch_not_found(self, mock_find, client):
        mock_find.side_effect = PatchNotFoundError("not found")
        resp = client.get(
            "/api/patches/ACARS_V8_1/NOPE/release-notes/draft.docx"
        )
        assert resp.status_code == 404


class TestGetPreviewPdf:
    @patch("app.api.patches.export_docx_to_pdf")
    @patch("app.api.patches.find_patch")
    def test_returns_pdf_file(self, mock_find, mock_export, client, tmp_path):
        docx_path = tmp_path / "8.1.0.0.docx"
        docx_path.write_bytes(b"PK\x03\x04 fake docx")
        pdf_path = tmp_path / "8.1.0.0.pdf"
        pdf_bytes = b"%PDF-1.4 fake converted pdf"
        pdf_path.write_bytes(pdf_bytes)
        mock_export.return_value = pdf_path

        tracker, patch_entry = _tracker_with_release_notes(
            generated_docx_path=str(docx_path)
        )
        mock_find.return_value = (tracker, "8.1.0", patch_entry)

        resp = client.get(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/preview.pdf"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content == pdf_bytes

    @patch("app.api.patches.find_patch")
    def test_404_when_docx_path_is_none(self, mock_find, client):
        tracker, patch_entry = _tracker_with_release_notes(
            generated_docx_path=None
        )
        mock_find.return_value = (tracker, "8.1.0", patch_entry)

        resp = client.get(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/preview.pdf"
        )
        assert resp.status_code == 404

    @patch("app.api.patches.find_patch")
    def test_404_when_docx_missing_on_disk(self, mock_find, client, tmp_path):
        missing = tmp_path / "does-not-exist.docx"
        tracker, patch_entry = _tracker_with_release_notes(
            generated_docx_path=str(missing)
        )
        mock_find.return_value = (tracker, "8.1.0", patch_entry)

        resp = client.get(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/preview.pdf"
        )
        assert resp.status_code == 404

    @patch("app.api.patches.export_docx_to_pdf")
    @patch("app.api.patches.find_patch")
    def test_503_when_soffice_missing(self, mock_find, mock_export, client, tmp_path):
        docx_path = tmp_path / "8.1.0.0.docx"
        docx_path.write_bytes(b"PK\x03\x04")
        mock_export.side_effect = FileNotFoundError("soffice missing")

        tracker, patch_entry = _tracker_with_release_notes(
            generated_docx_path=str(docx_path)
        )
        mock_find.return_value = (tracker, "8.1.0", patch_entry)

        resp = client.get(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/preview.pdf"
        )
        assert resp.status_code == 503

    @patch("app.api.patches.export_docx_to_pdf")
    @patch("app.api.patches.find_patch")
    def test_500_when_conversion_fails(self, mock_find, mock_export, client, tmp_path):
        docx_path = tmp_path / "8.1.0.0.docx"
        docx_path.write_bytes(b"PK\x03\x04")
        mock_export.side_effect = RuntimeError("soffice exited 1: boom")

        tracker, patch_entry = _tracker_with_release_notes(
            generated_docx_path=str(docx_path)
        )
        mock_find.return_value = (tracker, "8.1.0", patch_entry)

        resp = client.get(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/preview.pdf"
        )
        assert resp.status_code == 500

    @patch("app.api.patches.find_patch")
    def test_404_when_patch_not_found(self, mock_find, client):
        mock_find.side_effect = PatchNotFoundError("not found")
        resp = client.get(
            "/api/patches/ACARS_V8_1/NOPE/release-notes/preview.pdf"
        )
        assert resp.status_code == 404


class TestOpenDocxInWord:
    @patch("app.api.patches.subprocess.run")
    @patch("app.api.patches.find_patch")
    def test_opens_docx(self, mock_find, mock_run, client, tmp_path):
        docx_path = tmp_path / "8.1.0.0.docx"
        docx_path.write_bytes(b"PK\x03\x04")

        tracker, patch_entry = _tracker_with_release_notes(
            generated_docx_path=str(docx_path)
        )
        mock_find.return_value = (tracker, "8.1.0", patch_entry)

        resp = client.post(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/open-in-word"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["opened"] is True
        assert body["path"] == str(docx_path)
        mock_run.assert_called_once_with(["open", str(docx_path)], check=False)

    @patch("app.api.patches.find_patch")
    def test_404_when_path_is_none(self, mock_find, client):
        tracker, patch_entry = _tracker_with_release_notes(generated_docx_path=None)
        mock_find.return_value = (tracker, "8.1.0", patch_entry)

        resp = client.post(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/open-in-word"
        )
        assert resp.status_code == 404

    @patch("app.api.patches.find_patch")
    def test_404_when_file_missing(self, mock_find, client, tmp_path):
        missing = tmp_path / "nope.docx"
        tracker, patch_entry = _tracker_with_release_notes(generated_docx_path=str(missing))
        mock_find.return_value = (tracker, "8.1.0", patch_entry)

        resp = client.post(
            "/api/patches/ACARS_V8_1/8.1.0.0/release-notes/open-in-word"
        )
        assert resp.status_code == 404

    @patch("app.api.patches.find_patch")
    def test_404_when_patch_not_found(self, mock_find, client):
        mock_find.side_effect = PatchNotFoundError("not found")
        resp = client.post(
            "/api/patches/ACARS_V8_1/NOPE/release-notes/open-in-word"
        )
        assert resp.status_code == 404
