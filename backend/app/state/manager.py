import fcntl
import json
import logging
import os
from pathlib import Path

from app.config import settings
from app.state.models import ProductTracker

logger = logging.getLogger("state.manager")


def load_tracker(product_id: str, state_dir: Path | None = None) -> ProductTracker:
    state_dir = state_dir or settings.state_dir
    path = state_dir / f"{product_id}.json"

    if not path.exists():
        logger.warning("No tracker file for %s, returning empty tracker", product_id)
        return ProductTracker(product_id=product_id)

    logger.info("Loading tracker for %s from %s", product_id, path)
    with open(path) as f:
        data = json.load(f)
    return ProductTracker.model_validate(data)


def save_tracker(tracker: ProductTracker, state_dir: Path | None = None) -> None:
    state_dir = state_dir or settings.state_dir
    state_dir.mkdir(parents=True, exist_ok=True)

    path = state_dir / f"{tracker.product_id}.json"
    tmp_path = path.with_suffix(".json.tmp")

    logger.info("Saving tracker for %s to %s", tracker.product_id, path)
    try:
        with open(tmp_path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(tracker.model_dump(mode="json"), f, indent=2)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        os.replace(tmp_path, path)
    except Exception:
        logger.error("Failed to save tracker for %s", tracker.product_id, exc_info=True)
        if tmp_path.exists():
            tmp_path.unlink()
        raise
