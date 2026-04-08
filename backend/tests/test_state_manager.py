import json

from app.state.manager import load_tracker, save_tracker
from app.state.models import ProductTracker


def test_load_existing_tracker(tmp_state_dir, tracker_json_file):
    tracker = load_tracker("ACARS_V8_1", state_dir=tmp_state_dir)
    assert isinstance(tracker, ProductTracker)
    assert tracker.product_id == "ACARS_V8_1"
    assert "8.1.0" in tracker.versions
    patch = tracker.versions["8.1.0"].patches["8.1.0.0"]
    assert patch.binaries.status == "pending_approval"


def test_load_missing_returns_empty(tmp_state_dir):
    tracker = load_tracker("NONEXISTENT", state_dir=tmp_state_dir)
    assert isinstance(tracker, ProductTracker)
    assert tracker.product_id == "NONEXISTENT"
    assert tracker.versions == {}


def test_save_and_reload_roundtrip(tmp_state_dir, sample_tracker):
    save_tracker(sample_tracker, state_dir=tmp_state_dir)

    path = tmp_state_dir / "ACARS_V8_1.json"
    assert path.exists()

    reloaded = load_tracker("ACARS_V8_1", state_dir=tmp_state_dir)
    assert reloaded.product_id == sample_tracker.product_id
    patch = reloaded.versions["8.1.0"].patches["8.1.0.0"]
    assert patch.binaries.status == "pending_approval"
    assert patch.release_notes.status == "published"


def test_atomic_write_uses_replace(tmp_state_dir, sample_tracker, monkeypatch):
    replace_calls = []

    import os
    original_os_replace = os.replace

    def tracking_replace(src, dst):
        replace_calls.append((str(src), str(dst)))
        return original_os_replace(src, dst)

    monkeypatch.setattr(os, "replace", tracking_replace)
    save_tracker(sample_tracker, state_dir=tmp_state_dir)

    assert len(replace_calls) == 1
    src, dst = replace_calls[0]
    assert src.endswith(".json.tmp")
    assert dst.endswith(".json")


def test_save_creates_state_dir(tmp_path, sample_tracker):
    new_dir = tmp_path / "new" / "state"
    save_tracker(sample_tracker, state_dir=new_dir)
    assert (new_dir / "ACARS_V8_1.json").exists()


def test_saved_json_is_valid(tmp_state_dir, sample_tracker):
    save_tracker(sample_tracker, state_dir=tmp_state_dir)
    path = tmp_state_dir / "ACARS_V8_1.json"
    with open(path) as f:
        data = json.load(f)
    assert data["product_id"] == "ACARS_V8_1"
    assert "versions" in data
