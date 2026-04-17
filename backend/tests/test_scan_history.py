from datetime import datetime, timezone

import pytest

from app.state.models import ScanRecord
from app.state.scan_history import (
    finalize_scan_record,
    is_main_scan_running,
    list_recent_scans,
    load_scan_record,
    save_scan_record,
)


def _record(scan_id: str, *, trigger: str = "manual", finished: bool = False, started: str | None = None) -> ScanRecord:
    rec = ScanRecord(
        scan_id=scan_id,
        trigger=trigger,  # type: ignore[arg-type]
        started_at=datetime.fromisoformat(started or "2026-04-17T12:00:00+00:00"),
        products=["ACARS_V8_1"],
    )
    if finished:
        rec.finished_at = datetime.now(timezone.utc)
        rec.counts = {"new_patches": 2}
        rec.duration_ms = 1234
    return rec


class TestSaveAndLoad:
    def test_save_then_load_roundtrip(self, tmp_scans_dir):
        rec = _record("abc123")
        save_scan_record(rec, scans_dir=tmp_scans_dir)

        loaded = load_scan_record("abc123", scans_dir=tmp_scans_dir)
        assert loaded is not None
        assert loaded.scan_id == "abc123"
        assert loaded.trigger == "manual"
        assert loaded.finished_at is None
        assert loaded.products == ["ACARS_V8_1"]

    def test_load_missing_returns_none(self, tmp_scans_dir):
        assert load_scan_record("does-not-exist", scans_dir=tmp_scans_dir) is None

    def test_save_creates_scans_dir(self, tmp_path):
        new_dir = tmp_path / "state" / "scans"
        assert not new_dir.exists()
        save_scan_record(_record("xyz"), scans_dir=new_dir)
        assert new_dir.exists()
        assert (new_dir / "xyz.json").exists()


class TestFinalize:
    def test_finalize_sets_finished_fields(self, tmp_scans_dir):
        save_scan_record(_record("abc123"), scans_dir=tmp_scans_dir)
        finalize_scan_record(
            "abc123",
            counts={"new_patches": 5, "downloaded": 3},
            duration_ms=2500,
            scans_dir=tmp_scans_dir,
        )

        loaded = load_scan_record("abc123", scans_dir=tmp_scans_dir)
        assert loaded is not None
        assert loaded.finished_at is not None
        assert loaded.counts == {"new_patches": 5, "downloaded": 3}
        assert loaded.duration_ms == 2500

    def test_finalize_missing_is_noop(self, tmp_scans_dir):
        finalize_scan_record(
            "nope", counts={}, duration_ms=0, scans_dir=tmp_scans_dir
        )


class TestIsMainScanRunning:
    def test_empty_dir_returns_false(self, tmp_scans_dir):
        assert is_main_scan_running(scans_dir=tmp_scans_dir) is False

    def test_unfinalized_manual_blocks(self, tmp_scans_dir):
        save_scan_record(_record("a", trigger="manual"), scans_dir=tmp_scans_dir)
        assert is_main_scan_running(scans_dir=tmp_scans_dir) is True

    def test_unfinalized_cron_blocks(self, tmp_scans_dir):
        save_scan_record(_record("a", trigger="cron"), scans_dir=tmp_scans_dir)
        assert is_main_scan_running(scans_dir=tmp_scans_dir) is True

    def test_finalized_does_not_block(self, tmp_scans_dir):
        save_scan_record(
            _record("a", trigger="manual", finished=True), scans_dir=tmp_scans_dir
        )
        assert is_main_scan_running(scans_dir=tmp_scans_dir) is False

    def test_targeted_refetch_does_not_block(self, tmp_scans_dir):
        save_scan_record(_record("a", trigger="targeted"), scans_dir=tmp_scans_dir)
        assert is_main_scan_running(scans_dir=tmp_scans_dir) is False

    def test_bulk_refetch_does_not_block(self, tmp_scans_dir):
        save_scan_record(_record("a", trigger="bulk_docs"), scans_dir=tmp_scans_dir)
        assert is_main_scan_running(scans_dir=tmp_scans_dir) is False

    def test_missing_dir_returns_false(self, tmp_path):
        assert is_main_scan_running(scans_dir=tmp_path / "nope") is False


class TestListRecentScans:
    def test_sorts_newest_first(self, tmp_scans_dir):
        save_scan_record(_record("a", started="2026-04-15T10:00:00+00:00"), scans_dir=tmp_scans_dir)
        save_scan_record(_record("b", started="2026-04-17T10:00:00+00:00"), scans_dir=tmp_scans_dir)
        save_scan_record(_record("c", started="2026-04-16T10:00:00+00:00"), scans_dir=tmp_scans_dir)

        records = list_recent_scans(scans_dir=tmp_scans_dir)
        assert [r.scan_id for r in records] == ["b", "c", "a"]

    def test_limit_applies(self, tmp_scans_dir):
        for i in range(5):
            save_scan_record(
                _record(f"s{i}", started=f"2026-04-{10+i:02d}T10:00:00+00:00"),
                scans_dir=tmp_scans_dir,
            )
        records = list_recent_scans(limit=3, scans_dir=tmp_scans_dir)
        assert len(records) == 3

    def test_missing_dir_returns_empty(self, tmp_path):
        assert list_recent_scans(scans_dir=tmp_path / "nope") == []
