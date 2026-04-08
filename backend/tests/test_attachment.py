"""Tests for zip_patch_folder and upload_attachment."""

import zipfile
from io import BytesIO
from unittest.mock import MagicMock

from app.integrations.jira.attachment import upload_attachment, zip_patch_folder


class TestZipPatchFolder:
    def test_creates_valid_zip(self, tmp_path):
        (tmp_path / "file1.txt").write_text("hello")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "file2.bin").write_bytes(b"\x00\x01\x02")

        data = zip_patch_folder(tmp_path, "8.1.11.0")

        with zipfile.ZipFile(BytesIO(data)) as zf:
            names = sorted(zf.namelist())
            assert names == ["file1.txt", "sub/file2.bin"]
            assert zf.read("file1.txt") == b"hello"

    def test_empty_folder(self, tmp_path):
        data = zip_patch_folder(tmp_path, "empty")
        with zipfile.ZipFile(BytesIO(data)) as zf:
            assert zf.namelist() == []


class TestUploadAttachment:
    def test_calls_add_attachment(self):
        mock_client = MagicMock()
        mock_client.add_attachment.return_value = [{"filename": "8.1.11.0.zip"}]

        result = upload_attachment(mock_client, "PROJ-1", "8.1.11.0", b"zipdata")

        mock_client.add_attachment.assert_called_once_with(
            "PROJ-1", "8.1.11.0.zip", b"zipdata"
        )
        assert result == [{"filename": "8.1.11.0.zip"}]
