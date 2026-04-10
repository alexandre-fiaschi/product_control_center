"""Tests for services.lifecycle.run_cell — the per-cell 5-step contract."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.services.lifecycle import run_cell
from app.state.models import BinariesState, LastRun, ReleaseNotesState


def test_run_cell_success():
    cell = BinariesState(status="discovered")
    called = []

    def work_fn():
        called.append(True)

    result = run_cell(cell, work_fn, step_name="download", product="X", version="1.0")

    assert result is True
    assert called == [True]
    assert cell.last_run.state == "success"
    assert cell.last_run.started_at is not None
    assert cell.last_run.finished_at is not None
    assert cell.last_run.finished_at >= cell.last_run.started_at
    assert cell.last_run.step is None
    assert cell.last_run.error is None
    # Workflow status must NOT be touched by the helper.
    assert cell.status == "discovered"


def test_run_cell_failure_records_error():
    cell = BinariesState(status="discovered")

    def work_fn():
        raise IOError("permission denied")

    result = run_cell(cell, work_fn, step_name="download", product="X", version="1.0")

    assert result is False
    assert cell.last_run.state == "failed"
    assert cell.last_run.step == "download"
    assert cell.last_run.error is not None
    assert "permission denied" in cell.last_run.error
    assert cell.last_run.started_at is not None
    assert cell.last_run.finished_at is not None
    # Workflow status still unchanged.
    assert cell.status == "discovered"


def test_run_cell_failure_truncates_long_errors():
    cell = BinariesState(status="discovered")
    long_msg = "line one of the error\n" + "x" * 500

    def work_fn():
        raise RuntimeError(long_msg)

    result = run_cell(cell, work_fn, step_name="download")

    assert result is False
    assert cell.last_run.error is not None
    # Single line, ≤200 chars.
    assert "\n" not in cell.last_run.error
    assert len(cell.last_run.error) <= 200
    assert cell.last_run.error.startswith("line one of the error")


def test_run_cell_lock_skip_does_not_call_work_fn():
    locked_at = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    cell = BinariesState(
        status="discovered",
        last_run=LastRun(state="running", started_at=locked_at),
    )
    work_fn = MagicMock()

    result = run_cell(cell, work_fn, step_name="download", product="X", version="1.0")

    assert result is False
    work_fn.assert_not_called()
    # Helper left last_run exactly as it found it.
    assert cell.last_run.state == "running"
    assert cell.last_run.started_at == locked_at
    assert cell.last_run.finished_at is None
    assert cell.last_run.step is None
    assert cell.last_run.error is None


def test_run_cell_works_on_release_notes_state():
    cell = ReleaseNotesState(status="not_started")

    def work_fn():
        pass

    result = run_cell(cell, work_fn, step_name="zendesk_fetch")

    assert result is True
    assert cell.last_run.state == "success"
    assert cell.status == "not_started"  # workflow untouched
