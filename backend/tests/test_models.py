from pathlib import Path

import pytest
from pydantic import ValidationError

from app.state.models import (
    BinariesState,
    LastRun,
    PatchEntry,
    ProductTracker,
    ReleaseNotesState,
    VersionData,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_PATCHES_DIR = REPO_ROOT / "state" / "patches"


def test_patch_entry_from_json(sample_tracker_json):
    patch_data = sample_tracker_json["versions"]["8.1.0"]["patches"]["8.1.0.0"]
    entry = PatchEntry.model_validate(patch_data)
    assert entry.binaries.status == "pending_approval"
    assert entry.release_notes.status == "published"
    assert entry.sftp_folder == "v8.1.0.0"


def test_full_tracker_from_json(sample_tracker_json):
    tracker = ProductTracker.model_validate(sample_tracker_json)
    assert tracker.product_id == "ACARS_V8_1"
    assert "8.1.0" in tracker.versions
    patches = tracker.versions["8.1.0"].patches
    assert "8.1.0.0" in patches


def test_invalid_binaries_status():
    with pytest.raises(ValidationError):
        BinariesState(status="invalid_status")


def test_invalid_release_notes_status():
    with pytest.raises(ValidationError):
        ReleaseNotesState(status="invalid_status")


def test_optional_fields_default_none():
    b = BinariesState(status="discovered")
    assert b.discovered_at is None
    assert b.approved_at is None
    assert b.jira_ticket_key is None


def test_roundtrip(sample_tracker):
    dumped = sample_tracker.model_dump(mode="json")
    reloaded = ProductTracker.model_validate(dumped)
    assert reloaded.product_id == sample_tracker.product_id
    assert reloaded.versions["8.1.0"].patches["8.1.0.0"].binaries.status == "pending_approval"


def test_empty_tracker():
    tracker = ProductTracker(product_id="TEST")
    assert tracker.versions == {}
    assert tracker.last_scanned_at is None


def test_last_run_default():
    lr = LastRun()
    assert lr.state == "idle"
    assert lr.started_at is None
    assert lr.finished_at is None
    assert lr.step is None
    assert lr.error is None


def test_binaries_state_default_last_run():
    b = BinariesState(status="discovered")
    assert b.last_run.state == "idle"
    assert b.last_run.started_at is None
    assert b.last_run.error is None


def test_release_notes_state_default_last_run():
    rn = ReleaseNotesState()
    assert rn.status == "not_started"
    assert rn.last_run.state == "idle"
    assert rn.last_run.finished_at is None


def test_release_notes_not_found_status():
    rn = ReleaseNotesState(status="not_found")
    assert rn.status == "not_found"
    with pytest.raises(ValidationError):
        ReleaseNotesState(status="not_a_real_value")


def test_legacy_json_lazy_migration(sample_tracker_json):
    # sample_tracker_json intentionally has no `last_run` keys — simulates on-disk
    # state files written before unit 1. Must parse with `last_run` defaulting to idle.
    tracker = ProductTracker.model_validate(sample_tracker_json)
    patch = tracker.versions["8.1.0"].patches["8.1.0.0"]
    assert patch.binaries.last_run.state == "idle"
    assert patch.binaries.last_run.started_at is None
    assert patch.release_notes.last_run.state == "idle"
    assert patch.release_notes.last_run.error is None


@pytest.mark.skipif(
    not STATE_PATCHES_DIR.exists() or not any(STATE_PATCHES_DIR.glob("*.json")),
    reason="no real state files in state/patches/",
)
def test_real_state_files_load():
    # Every real state/patches/*.json file must load cleanly with default last_run
    # on every patch, and survive a semantic round-trip (parse → dump → parse).
    for json_file in sorted(STATE_PATCHES_DIR.glob("*.json")):
        raw = json_file.read_text()
        tracker = ProductTracker.model_validate_json(raw)
        for version in tracker.versions.values():
            for patch in version.patches.values():
                assert patch.binaries.last_run.state == "idle"
                assert patch.release_notes.last_run.state == "idle"
        dumped = tracker.model_dump(mode="json")
        reloaded = ProductTracker.model_validate(dumped)
        assert reloaded.product_id == tracker.product_id
        assert reloaded.versions.keys() == tracker.versions.keys()


def test_last_run_invalid_state_rejected():
    with pytest.raises(ValidationError):
        LastRun(state="bogus")
