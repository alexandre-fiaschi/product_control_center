"""Per-cell lifecycle helper.

Implements the 5-step contract from PLAN_DOCS_PIPELINE.md §3.4: pre-flight
lock check, start, execute, success, or failure bookkeeping on a cell's
`last_run` (run status). Workflow status (`cell.status`) is never touched
by this helper — that is always the caller's decision.
"""

import logging
from datetime import datetime, timezone
from typing import Callable

from app.state.models import BinariesState, LastRun, ReleaseNotesState

logger = logging.getLogger("services.lifecycle")

Cell = BinariesState | ReleaseNotesState


def _format_fields(log_fields: dict[str, object]) -> str:
    return " ".join(f"{k}={v}" for k, v in log_fields.items())


def run_cell(
    cell: Cell,
    work_fn: Callable[[], object],
    *,
    step_name: str,
    **log_fields: object,
) -> bool:
    """Run ``work_fn`` against ``cell`` with full lifecycle bookkeeping.

    See PLAN_DOCS_PIPELINE.md §3.4 for the 5-step contract.

    Returns True on success, False on exception or lock-skip. The caller
    inspects ``cell.last_run.state`` if it needs to distinguish failure
    from skip. The caller is responsible for advancing ``cell.status``
    (workflow) on success — this helper only touches ``cell.last_run``
    (run status).
    """
    # 1. Pre-flight lock check
    if cell.last_run.state == "running":
        logger.warning(
            "lifecycle.%s.skipped reason=locked %s",
            step_name,
            _format_fields(log_fields),
        )
        return False

    # 2. Start
    cell.last_run = LastRun(
        state="running",
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        step=None,
        error=None,
    )

    # 3. Execute
    try:
        work_fn()
    except Exception as exc:
        # 5. On exception
        err_msg = (str(exc).splitlines() or [""])[0][:200]
        cell.last_run.state = "failed"
        cell.last_run.finished_at = datetime.now(timezone.utc)
        cell.last_run.step = step_name
        cell.last_run.error = err_msg
        logger.error(
            "lifecycle.%s.failed %s error=%s",
            step_name,
            _format_fields(log_fields),
            err_msg,
            exc_info=True,
        )
        return False

    # 4. On success
    cell.last_run.state = "success"
    cell.last_run.finished_at = datetime.now(timezone.utc)
    return True
