import pytest
from pydantic import ValidationError

from app.state.models import (
    BinariesState,
    PatchEntry,
    ProductTracker,
    ReleaseNotesState,
    VersionData,
)


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
