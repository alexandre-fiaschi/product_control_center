"""Scan history persistence — one JSON file per scan under state/scans/.

Backs the 409 guard on POST /pipeline/scan (any record with finished_at=None
whose trigger is a main-scan trigger blocks new main scans) and will back the
future scan-history UI. See PLAN_DOCS_PIPELINE.md §4.3 and Unit 6.
"""

import fcntl
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.state.models import ScanRecord

logger = logging.getLogger("state.scan_history")

# Only main-scan triggers count toward "a scan is running" — targeted/bulk
# refetches run concurrently with a main scan because the per-cell lock
# (last_run.state == "running") already prevents double work on the same cell.
# See PLAN_DOCS_PIPELINE.md §4.1, "Locking" row.
MAIN_SCAN_TRIGGERS = {"cron", "manual"}


def save_scan_record(record: ScanRecord, scans_dir: Path | None = None) -> None:
    """Atomic write of a scan record to <scans_dir>/<scan_id>.json."""
    scans_dir = scans_dir or settings.scans_dir
    scans_dir.mkdir(parents=True, exist_ok=True)

    path = scans_dir / f"{record.scan_id}.json"
    tmp_path = path.with_suffix(".json.tmp")

    try:
        with open(tmp_path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(record.model_dump(mode="json"), f, indent=2)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        os.replace(tmp_path, path)
    except Exception:
        logger.error("scan_history.save.failed scan_id=%s", record.scan_id, exc_info=True)
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def load_scan_record(scan_id: str, scans_dir: Path | None = None) -> ScanRecord | None:
    scans_dir = scans_dir or settings.scans_dir
    path = scans_dir / f"{scan_id}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return ScanRecord.model_validate(json.load(f))


def finalize_scan_record(
    scan_id: str,
    *,
    counts: dict[str, int],
    duration_ms: int,
    scans_dir: Path | None = None,
) -> None:
    """Set finished_at=now, merge counts, set duration_ms, save back."""
    record = load_scan_record(scan_id, scans_dir=scans_dir)
    if record is None:
        logger.warning("scan_history.finalize.missing scan_id=%s", scan_id)
        return
    record.finished_at = datetime.now(timezone.utc)
    record.counts = counts
    record.duration_ms = duration_ms
    save_scan_record(record, scans_dir=scans_dir)


def is_main_scan_running(scans_dir: Path | None = None) -> bool:
    """True if any main-scan record has finished_at=None."""
    scans_dir = scans_dir or settings.scans_dir
    if not scans_dir.exists():
        return False
    for entry in os.scandir(scans_dir):
        if not entry.name.endswith(".json"):
            continue
        try:
            with open(entry.path) as f:
                data = json.load(f)
        except Exception:
            logger.warning("scan_history.is_running.parse_failed file=%s", entry.name)
            continue
        if data.get("finished_at") is not None:
            continue
        if data.get("trigger") in MAIN_SCAN_TRIGGERS:
            return True
    return False


def list_recent_scans(
    limit: int = 50, scans_dir: Path | None = None
) -> list[ScanRecord]:
    """Most-recent scans first, up to limit."""
    scans_dir = scans_dir or settings.scans_dir
    if not scans_dir.exists():
        return []
    records: list[ScanRecord] = []
    for entry in os.scandir(scans_dir):
        if not entry.name.endswith(".json"):
            continue
        try:
            with open(entry.path) as f:
                records.append(ScanRecord.model_validate(json.load(f)))
        except Exception:
            logger.warning("scan_history.list.parse_failed file=%s", entry.name)
            continue
    records.sort(key=lambda r: r.started_at, reverse=True)
    return records[:limit]
