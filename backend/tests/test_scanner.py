"""Tests for SFTP scanner with mocked SFTP connections."""

import pytest

from app.integrations.sftp.scanner import (
    discover_patches,
    discover_v73,
    discover_v80,
    discover_v81,
    update_tracker,
)
from app.state.models import ProductTracker, VersionData, PatchEntry, BinariesState, ReleaseNotesState


class FakeConn:
    """Fake SFTPConnector that returns pre-configured directory listings."""

    def __init__(self, tree: dict[str, list[str]]):
        self._tree = tree

    def list_dirs(self, path: str) -> list[str]:
        return sorted(self._tree.get(path, []))


# --- discover_v81 ---

class TestDiscoverV81:
    def test_finds_patches(self):
        conn = FakeConn({
            "/ACARS_V8_1": ["ACARS_V8_1_0", "ACARS_V8_1_11", "README.txt"],
            "/ACARS_V8_1/ACARS_V8_1_0": ["v8.1.0.0", "v8.1.0.1"],
            "/ACARS_V8_1/ACARS_V8_1_11": ["8.1.11.0"],
        })
        result = discover_v81(conn, "/ACARS_V8_1")
        assert len(result) == 3
        assert result[0]["sftp_folder"] == "v8.1.0.0"
        assert result[0]["sftp_path"] == "/ACARS_V8_1/ACARS_V8_1_0/v8.1.0.0"

    def test_skips_non_version_folders(self):
        conn = FakeConn({
            "/ACARS_V8_1": ["README", "ACARS_V8_1_0"],
            "/ACARS_V8_1/ACARS_V8_1_0": ["v8.1.0.0"],
        })
        result = discover_v81(conn, "/ACARS_V8_1")
        assert len(result) == 1

    def test_empty_sftp(self):
        conn = FakeConn({})
        assert discover_v81(conn, "/ACARS_V8_1") == []


# --- discover_v80 ---

class TestDiscoverV80:
    def test_filters_by_track_from(self):
        conn = FakeConn({
            "/ACARS_V8_0": ["8_0_4", "8_0_28", "8_0_29"],
            "/ACARS_V8_0/8_0_4": ["8_0_4_1"],
            "/ACARS_V8_0/8_0_28": ["8_0_28_1"],
            "/ACARS_V8_0/8_0_29": ["8_0_29_0"],
        })
        result = discover_v80(conn, "/ACARS_V8_0", track_from_minor=28)
        assert len(result) == 2
        folders = [r["sftp_folder"] for r in result]
        assert "8_0_4_1" not in folders
        assert "8_0_28_1" in folders
        assert "8_0_29_0" in folders


# --- discover_v73 ---

class TestDiscoverV73:
    def test_filters_by_track_from(self):
        conn = FakeConn({
            "/ACARS_V7_3": ["7_3_26_5", "7_3_27_0", "7_3_27_7"],
        })
        result = discover_v73(conn, "/ACARS_V7_3", track_from_tuple=(27, 0))
        assert len(result) == 2
        folders = [r["sftp_folder"] for r in result]
        assert "7_3_26_5" not in folders
        assert "7_3_27_0" in folders


# --- discover_patches (dispatcher) ---

class TestDiscoverPatches:
    def test_dispatches_v81(self):
        conn = FakeConn({
            "/ACARS_V8_1": ["ACARS_V8_1_0"],
            "/ACARS_V8_1/ACARS_V8_1_0": ["v8.1.0.0"],
        })
        cfg = {"sftp_path": "/ACARS_V8_1", "track_from": None}
        result = discover_patches(conn, "ACARS_V8_1", cfg)
        assert len(result) == 1

    def test_unknown_product_returns_empty(self):
        conn = FakeConn({})
        result = discover_patches(conn, "UNKNOWN", {"sftp_path": "/X"})
        assert result == []


# --- update_tracker ---

class TestUpdateTracker:
    def test_creates_nested_structure(self):
        tracker = ProductTracker(product_id="ACARS_V7_3")
        raw = [{"sftp_folder": "7_3_27_7", "sftp_path": "/ACARS_V7_3/7_3_27_7"}]

        new_ids = update_tracker(tracker, "ACARS_V7_3", raw)

        assert new_ids == ["7.3.27.7"]
        assert "7.3.27" in tracker.versions
        patch = tracker.versions["7.3.27"].patches["7.3.27.7"]
        assert patch.sftp_folder == "7_3_27_7"
        assert patch.local_path == "patches/ACARS_V7_3/7.3.27.7"
        assert patch.binaries.status == "discovered"
        assert patch.binaries.discovered_at is not None
        assert patch.release_notes.status == "not_started"

    def test_idempotent(self):
        tracker = ProductTracker(product_id="ACARS_V7_3")
        raw = [{"sftp_folder": "7_3_27_7", "sftp_path": "/ACARS_V7_3/7_3_27_7"}]

        first = update_tracker(tracker, "ACARS_V7_3", raw)
        second = update_tracker(tracker, "ACARS_V7_3", raw)

        assert len(first) == 1
        assert len(second) == 0
        assert len(tracker.versions["7.3.27"].patches) == 1

    def test_skips_unparseable_folders(self):
        tracker = ProductTracker(product_id="ACARS_V8_1")
        raw = [{"sftp_folder": "garbage", "sftp_path": "/ACARS_V8_1/garbage"}]

        new_ids = update_tracker(tracker, "ACARS_V8_1", raw)
        assert new_ids == []

    def test_sets_last_scanned_at(self):
        tracker = ProductTracker(product_id="ACARS_V8_1")
        assert tracker.last_scanned_at is None

        update_tracker(tracker, "ACARS_V8_1", [])
        assert tracker.last_scanned_at is not None

    def test_multiple_patches_multiple_versions(self):
        tracker = ProductTracker(product_id="ACARS_V8_1")
        raw = [
            {"sftp_folder": "v8.1.0.0", "sftp_path": "/ACARS_V8_1/ACARS_V8_1_0/v8.1.0.0"},
            {"sftp_folder": "v8.1.0.1", "sftp_path": "/ACARS_V8_1/ACARS_V8_1_0/v8.1.0.1"},
            {"sftp_folder": "8.1.11.0", "sftp_path": "/ACARS_V8_1/ACARS_V8_1_11/8.1.11.0"},
        ]

        new_ids = update_tracker(tracker, "ACARS_V8_1", raw)
        assert len(new_ids) == 3
        assert "8.1.0" in tracker.versions
        assert "8.1.11" in tracker.versions
        assert len(tracker.versions["8.1.0"].patches) == 2
