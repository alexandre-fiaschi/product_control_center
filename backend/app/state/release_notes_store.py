import fcntl
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.state.release_notes_models import ReleaseNoteRecord, ReleaseNotesIndex

logger = logging.getLogger("state.release_notes_store")


def load_release_notes(product_id: str, state_dir: Path | None = None) -> ReleaseNotesIndex:
    state_dir = state_dir or settings.release_notes_state_dir
    path = state_dir / f"{product_id}.json"

    if not path.exists():
        logger.warning("No release-notes index for %s, returning empty index", product_id)
        return ReleaseNotesIndex(
            product_id=product_id,
            updated_at=datetime.now(timezone.utc),
        )

    logger.info("Loading release-notes index for %s from %s", product_id, path)
    with open(path) as f:
        data = json.load(f)
    return ReleaseNotesIndex.model_validate(data)


def save_release_notes(index: ReleaseNotesIndex, state_dir: Path | None = None) -> None:
    state_dir = state_dir or settings.release_notes_state_dir
    state_dir.mkdir(parents=True, exist_ok=True)

    path = state_dir / f"{index.product_id}.json"
    tmp_path = path.with_suffix(".json.tmp")

    logger.info("Saving release-notes index for %s to %s", index.product_id, path)
    try:
        with open(tmp_path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(index.model_dump(mode="json"), f, indent=2)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        os.replace(tmp_path, path)
    except Exception:
        logger.error("Failed to save release-notes index for %s", index.product_id, exc_info=True)
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def get_record(product_id: str, version: str, state_dir: Path | None = None) -> ReleaseNoteRecord | None:
    index = load_release_notes(product_id, state_dir=state_dir)
    return index.release_notes.get(version)


def upsert_record(product_id: str, record: ReleaseNoteRecord, state_dir: Path | None = None) -> None:
    index = load_release_notes(product_id, state_dir=state_dir)
    index.release_notes[record.version] = record
    index.updated_at = datetime.now(timezone.utc)
    save_release_notes(index, state_dir=state_dir)
