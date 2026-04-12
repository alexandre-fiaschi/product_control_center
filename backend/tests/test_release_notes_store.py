import json
import os

from app.state.release_notes_models import ReleaseNoteRecord, ReleaseNotesIndex
from app.state.release_notes_store import (
    get_record,
    load_release_notes,
    save_release_notes,
    upsert_record,
)


def test_load_missing_returns_empty(tmp_release_notes_dir):
    index = load_release_notes("NONEXISTENT", state_dir=tmp_release_notes_dir)
    assert isinstance(index, ReleaseNotesIndex)
    assert index.product_id == "NONEXISTENT"
    assert index.release_notes == {}


def test_save_and_reload_roundtrip(tmp_release_notes_dir, sample_release_note_record):
    index = ReleaseNotesIndex(
        product_id="ACARS_V8_0",
        updated_at="2026-04-11T12:00:00+00:00",
        release_notes={"8.0.18.1": sample_release_note_record},
    )
    save_release_notes(index, state_dir=tmp_release_notes_dir)

    reloaded = load_release_notes("ACARS_V8_0", state_dir=tmp_release_notes_dir)
    assert reloaded.product_id == "ACARS_V8_0"
    assert "8.0.18.1" in reloaded.release_notes
    rec = reloaded.release_notes["8.0.18.1"]
    assert rec.version == "8.0.18.1"
    assert len(rec.items) == 1
    assert rec.items[0].am_card == "AM1393"


def test_atomic_write_uses_replace(tmp_release_notes_dir, sample_release_note_record, monkeypatch):
    replace_calls = []
    original_os_replace = os.replace

    def tracking_replace(src, dst):
        replace_calls.append((str(src), str(dst)))
        return original_os_replace(src, dst)

    monkeypatch.setattr(os, "replace", tracking_replace)

    index = ReleaseNotesIndex(
        product_id="ACARS_V8_0",
        updated_at="2026-04-11T12:00:00+00:00",
        release_notes={"8.0.18.1": sample_release_note_record},
    )
    save_release_notes(index, state_dir=tmp_release_notes_dir)

    assert len(replace_calls) == 1
    src, dst = replace_calls[0]
    assert src.endswith(".json.tmp")
    assert dst.endswith(".json")


def test_save_creates_state_dir(tmp_path, sample_release_note_record):
    new_dir = tmp_path / "new" / "release_notes_items"
    index = ReleaseNotesIndex(
        product_id="ACARS_V8_0",
        updated_at="2026-04-11T12:00:00+00:00",
        release_notes={"8.0.18.1": sample_release_note_record},
    )
    save_release_notes(index, state_dir=new_dir)
    assert (new_dir / "ACARS_V8_0.json").exists()


def test_saved_json_is_valid(tmp_release_notes_dir, sample_release_note_record):
    index = ReleaseNotesIndex(
        product_id="ACARS_V8_0",
        updated_at="2026-04-11T12:00:00+00:00",
        release_notes={"8.0.18.1": sample_release_note_record},
    )
    save_release_notes(index, state_dir=tmp_release_notes_dir)

    path = tmp_release_notes_dir / "ACARS_V8_0.json"
    with open(path) as f:
        data = json.load(f)
    assert data["product_id"] == "ACARS_V8_0"
    assert "release_notes" in data
    assert "8.0.18.1" in data["release_notes"]


def test_get_record_found(tmp_release_notes_dir, sample_release_note_record):
    upsert_record("ACARS_V8_0", sample_release_note_record, state_dir=tmp_release_notes_dir)
    rec = get_record("ACARS_V8_0", "8.0.18.1", state_dir=tmp_release_notes_dir)
    assert rec is not None
    assert rec.version == "8.0.18.1"
    assert rec.items[0].am_card == "AM1393"


def test_get_record_not_found(tmp_release_notes_dir):
    rec = get_record("ACARS_V8_0", "9.9.9.9", state_dir=tmp_release_notes_dir)
    assert rec is None


def test_upsert_record_new(tmp_release_notes_dir, sample_release_note_record):
    upsert_record("ACARS_V8_0", sample_release_note_record, state_dir=tmp_release_notes_dir)

    index = load_release_notes("ACARS_V8_0", state_dir=tmp_release_notes_dir)
    assert "8.0.18.1" in index.release_notes


def test_upsert_record_update(tmp_release_notes_dir, sample_release_note_record):
    upsert_record("ACARS_V8_0", sample_release_note_record, state_dir=tmp_release_notes_dir)

    updated = sample_release_note_record.model_copy(update={"source_pdf_pages": 99})
    upsert_record("ACARS_V8_0", updated, state_dir=tmp_release_notes_dir)

    rec = get_record("ACARS_V8_0", "8.0.18.1", state_dir=tmp_release_notes_dir)
    assert rec is not None
    assert rec.source_pdf_pages == 99
