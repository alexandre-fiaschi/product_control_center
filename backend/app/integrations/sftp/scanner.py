"""Discover patches on SFTP and update product trackers."""

import logging
from datetime import datetime, timezone

from app.integrations.sftp.connector import SFTPConnector
from app.integrations.sftp.product_parsers import (
    normalize_patch_id,
    parse_track_from,
    parse_v73_patch,
    parse_v80_patch,
    parse_v80_version,
    parse_v81_patch,
    parse_v81_version,
    version_from_patch_id,
)
from app.state.models import (
    BinariesState,
    PatchEntry,
    ProductTracker,
    ReleaseNotesState,
    VersionData,
)

logger = logging.getLogger("sftp.scanner")


def discover_v81(conn: SFTPConnector, sftp_path: str) -> list[dict]:
    """Discover V8.1 patches (hierarchical: version folders -> patch folders)."""
    patches = []
    for vfolder in conn.list_dirs(sftp_path):
        if parse_v81_version(vfolder) is None:
            continue
        for pfolder in conn.list_dirs(f"{sftp_path}/{vfolder}"):
            if parse_v81_patch(pfolder) is None:
                continue
            patches.append({
                "sftp_folder": pfolder,
                "sftp_path": f"{sftp_path}/{vfolder}/{pfolder}",
            })
    return patches


def discover_v80(conn: SFTPConnector, sftp_path: str, track_from_minor: int) -> list[dict]:
    """Discover V8.0 patches (hierarchical, filtered by track_from)."""
    patches = []
    for vfolder in conn.list_dirs(sftp_path):
        minor = parse_v80_version(vfolder)
        if minor is None or minor < track_from_minor:
            continue
        for pfolder in conn.list_dirs(f"{sftp_path}/{vfolder}"):
            if parse_v80_patch(pfolder) is None:
                continue
            patches.append({
                "sftp_folder": pfolder,
                "sftp_path": f"{sftp_path}/{vfolder}/{pfolder}",
            })
    return patches


def discover_v73(conn: SFTPConnector, sftp_path: str, track_from_tuple: tuple[int, int]) -> list[dict]:
    """Discover V7.3 patches (flat directory, filtered by track_from)."""
    patches = []
    for pfolder in conn.list_dirs(sftp_path):
        parsed = parse_v73_patch(pfolder)
        if parsed is None or parsed < track_from_tuple:
            continue
        patches.append({
            "sftp_folder": pfolder,
            "sftp_path": f"{sftp_path}/{pfolder}",
        })
    return patches


def discover_patches(conn: SFTPConnector, product_id: str, product_cfg: dict) -> list[dict]:
    """Dispatch discovery to the correct product-specific scanner."""
    sftp_path = product_cfg["sftp_path"]
    track_from = product_cfg.get("track_from")

    logger.info("Scanning %s at %s (track_from=%s)", product_id, sftp_path, track_from)

    if product_id == "ACARS_V8_1":
        results = discover_v81(conn, sftp_path)
    elif product_id == "ACARS_V8_0":
        cutoff = parse_track_from(track_from, product_id)
        results = discover_v80(conn, sftp_path, cutoff)
    elif product_id == "ACARS_V7_3":
        cutoff = parse_track_from(track_from, product_id)
        results = discover_v73(conn, sftp_path, cutoff)
    else:
        logger.warning("Unknown product %s, skipping", product_id)
        results = []

    logger.info("Found %d patches on SFTP for %s", len(results), product_id)
    return results


def update_tracker(tracker: ProductTracker, product_id: str, raw_patches: list[dict]) -> list[str]:
    """Add newly discovered patches to tracker. Returns list of new patch IDs."""
    now = datetime.now(timezone.utc)
    tracker.last_scanned_at = now
    new_patches: list[str] = []

    for raw in raw_patches:
        patch_id = normalize_patch_id(product_id, raw["sftp_folder"])
        if patch_id is None:
            logger.debug("Skipping un-parseable folder: %s", raw["sftp_folder"])
            continue

        version = version_from_patch_id(patch_id)

        if version not in tracker.versions:
            tracker.versions[version] = VersionData()

        if patch_id in tracker.versions[version].patches:
            logger.warning("Patch %s already tracked, skipping", patch_id)
            continue

        tracker.versions[version].patches[patch_id] = PatchEntry(
            sftp_folder=raw["sftp_folder"],
            sftp_path=raw["sftp_path"],
            local_path=f"patches/{product_id}/{patch_id}",
            binaries=BinariesState(
                status="discovered",
                discovered_at=now,
            ),
            release_notes=ReleaseNotesState(status="not_started"),
        )
        new_patches.append(patch_id)
        logger.debug("Discovered new patch: %s (version %s)", patch_id, version)

    logger.info("Tracker update: %d new patches for %s", len(new_patches), product_id)
    return new_patches
