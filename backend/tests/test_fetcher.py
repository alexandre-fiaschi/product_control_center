"""Tests for pipelines.binaries.fetcher."""

import stat as stat_module
from pathlib import Path
from unittest.mock import MagicMock

from app.pipelines.binaries.fetcher import download_patch


def _make_attr(filename: str, is_dir: bool = False) -> MagicMock:
    attr = MagicMock()
    attr.filename = filename
    attr.st_mode = stat_module.S_IFDIR | 0o755 if is_dir else stat_module.S_IFREG | 0o644
    return attr


class TestDownloadPatch:
    def test_downloads_files_to_correct_path(self, tmp_path):
        conn = MagicMock()
        conn.client.listdir_attr.return_value = [
            _make_attr("file1.bin"),
            _make_attr("file2.txt"),
        ]
        conn.client.get.side_effect = lambda remote, local: Path(local).write_text("data")

        local_path = str(tmp_path / "patch")
        count = download_patch(conn, "/remote/patch", local_path)

        assert count == 2
        assert (tmp_path / "patch" / "file1.bin").exists()
        assert (tmp_path / "patch" / "file2.txt").exists()

    def test_creates_subdirectories(self, tmp_path):
        def listdir_side_effect(path):
            if path == "/remote/patch":
                return [_make_attr("subdir", is_dir=True), _make_attr("root.bin")]
            elif path == "/remote/patch/subdir":
                return [_make_attr("nested.bin")]
            return []

        conn = MagicMock()
        conn.client.listdir_attr.side_effect = listdir_side_effect
        conn.client.get.side_effect = lambda remote, local: Path(local).write_text("data")

        count = download_patch(conn, "/remote/patch", str(tmp_path / "patch"))

        assert count == 2
        assert (tmp_path / "patch" / "subdir" / "nested.bin").exists()
        assert (tmp_path / "patch" / "root.bin").exists()

    def test_handles_empty_folder(self, tmp_path):
        conn = MagicMock()
        conn.client.listdir_attr.return_value = []

        count = download_patch(conn, "/remote/empty", str(tmp_path / "empty"))

        assert count == 0
        assert (tmp_path / "empty").is_dir()
