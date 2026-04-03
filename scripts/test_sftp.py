#!/usr/bin/env python3
"""
SFTP Pipeline Dry Run
Scans tracked product folders on SFTP, discovers new patches,
saves per-product tracker JSONs, simulates download + approval gate.
"""

import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import paramiko

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = PROJECT_ROOT / "state" / "patches"
load_dotenv(PROJECT_ROOT / ".env")

SFTP_HOST = os.getenv("SFTP_HOST")
SFTP_PORT = int(os.getenv("SFTP_PORT", "22"))
SFTP_USERNAME = os.getenv("SFTP_USERNAME")
SFTP_PASSWORD = os.getenv("SFTP_PASSWORD")
SFTP_KEY_PATH = os.getenv("SFTP_KEY_PATH")

with open(PROJECT_ROOT / "config" / "pipeline.json") as f:
    CONFIG = json.load(f)["pipeline"]


def connect_sftp():
    transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
    if SFTP_KEY_PATH:
        key_path = os.path.expanduser(SFTP_KEY_PATH)
        pkey = paramiko.RSAKey.from_private_key_file(key_path)
        transport.connect(username=SFTP_USERNAME, pkey=pkey)
    else:
        transport.connect(username=SFTP_USERNAME, password=SFTP_PASSWORD)
    return transport, paramiko.SFTPClient.from_transport(transport)


def list_dirs(sftp, path):
    dirs = []
    try:
        for entry in sorted(sftp.listdir_attr(path), key=lambda e: e.filename):
            if stat.S_ISDIR(entry.st_mode):
                dirs.append(entry.filename)
    except IOError:
        pass
    return dirs


# --- Normalize folder names to dotted patch IDs ---

def normalize_patch_id(product_id, folder_name):
    """Convert any folder naming to normalized dotted format.
    7_3_27_7   -> 7.3.27.7
    8_0_28_1   -> 8.0.28.1
    v8.1.9.1   -> 8.1.9.1
    8.1.11.0   -> 8.1.11.0
    """
    if product_id == "ACARS_V7_3":
        m = re.match(r"7_3_(\d+)_(\d+)$", folder_name)
        if m:
            return f"7.3.{m.group(1)}.{m.group(2)}"
    elif product_id == "ACARS_V8_0":
        m = re.match(r"8_0_(\d+)_(\d+)$", folder_name)
        if m:
            return f"8.0.{m.group(1)}.{m.group(2)}"
    elif product_id == "ACARS_V8_1":
        m = re.match(r"v?8\.1\.(\d+)\.(\d+)$", folder_name)
        if m:
            return f"8.1.{m.group(1)}.{m.group(2)}"
    return None


def version_from_patch_id(patch_id):
    """8.1.9.1 -> 8.1.9, 7.3.27.7 -> 7.3.27"""
    parts = patch_id.rsplit(".", 1)
    return parts[0]


# --- Parsers for filtering ---

def parse_v81_version(folder_name):
    m = re.match(r"ACARS_V8_1_(\d+)$", folder_name)
    return int(m.group(1)) if m else None


def parse_v81_patch(folder_name):
    m = re.match(r"v?8\.1\.(\d+)\.(\d+)$", folder_name)
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_v80_version(folder_name):
    m = re.match(r"8_0_(\d+)$", folder_name)
    return int(m.group(1)) if m else None


def parse_v80_patch(folder_name):
    m = re.match(r"8_0_(\d+)_(\d+)$", folder_name)
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_v73_patch(folder_name):
    m = re.match(r"7_3_(\d+)_(\d+)$", folder_name)
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_track_from(track_from, product_id):
    if track_from is None:
        return None
    if product_id == "ACARS_V8_0":
        m = re.match(r"8_0_(\d+)", track_from)
        return int(m.group(1)) if m else 0
    if product_id == "ACARS_V7_3":
        m = re.match(r"7_3_(\d+)_(\d+)", track_from)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    return None


# --- Discovery ---

def discover_v81(sftp, sftp_path):
    patches = []
    for vfolder in list_dirs(sftp, sftp_path):
        if parse_v81_version(vfolder) is None:
            continue
        for pfolder in list_dirs(sftp, f"{sftp_path}/{vfolder}"):
            if parse_v81_patch(pfolder) is None:
                continue
            patches.append({
                "sftp_folder": pfolder,
                "sftp_path": f"{sftp_path}/{vfolder}/{pfolder}",
            })
    return patches


def discover_v80(sftp, sftp_path, track_from_minor):
    patches = []
    for vfolder in list_dirs(sftp, sftp_path):
        minor = parse_v80_version(vfolder)
        if minor is None or minor < track_from_minor:
            continue
        for pfolder in list_dirs(sftp, f"{sftp_path}/{vfolder}"):
            if parse_v80_patch(pfolder) is None:
                continue
            patches.append({
                "sftp_folder": pfolder,
                "sftp_path": f"{sftp_path}/{vfolder}/{pfolder}",
            })
    return patches


def discover_v73(sftp, sftp_path, track_from_tuple):
    patches = []
    for pfolder in list_dirs(sftp, sftp_path):
        parsed = parse_v73_patch(pfolder)
        if parsed is None or parsed < track_from_tuple:
            continue
        patches.append({
            "sftp_folder": pfolder,
            "sftp_path": f"{sftp_path}/{pfolder}",
        })
    return patches


def discover_patches(sftp, product_id, product_cfg):
    sftp_path = product_cfg["sftp_path"]
    track_from = product_cfg.get("track_from")

    if product_id == "ACARS_V8_1":
        return discover_v81(sftp, sftp_path)
    elif product_id == "ACARS_V8_0":
        cutoff = parse_track_from(track_from, product_id)
        return discover_v80(sftp, sftp_path, cutoff)
    elif product_id == "ACARS_V7_3":
        cutoff = parse_track_from(track_from, product_id)
        return discover_v73(sftp, sftp_path, cutoff)
    return []


# --- Tracker ---

def load_tracker(product_id):
    """Load existing tracker JSON or return empty structure."""
    path = STATE_DIR / f"{product_id}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {
        "product_id": product_id,
        "last_scanned_at": None,
        "versions": {},
    }


def save_tracker(tracker):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{tracker['product_id']}.json"
    with open(path, "w") as f:
        json.dump(tracker, f, indent=2)


def update_tracker(tracker, product_id, raw_patches):
    """Add newly discovered patches to tracker. Returns list of new patch IDs."""
    now = datetime.now(timezone.utc).isoformat()
    tracker["last_scanned_at"] = now
    new_patches = []

    for raw in raw_patches:
        patch_id = normalize_patch_id(product_id, raw["sftp_folder"])
        if patch_id is None:
            continue

        version = version_from_patch_id(patch_id)

        # Init version bucket if needed
        if version not in tracker["versions"]:
            tracker["versions"][version] = {"patches": {}}

        # Skip if already tracked
        if patch_id in tracker["versions"][version]["patches"]:
            continue

        tracker["versions"][version]["patches"][patch_id] = {
            "sftp_folder": raw["sftp_folder"],
            "sftp_path": raw["sftp_path"],
            "status": "discovered",
            "discovered_at": now,
            "downloaded_at": None,
            "approved_at": None,
            "published_at": None,
        }
        new_patches.append(patch_id)

    return new_patches


def simulate_download(tracker):
    """Simulate downloading all 'discovered' patches."""
    now = datetime.now(timezone.utc).isoformat()
    downloaded = []
    for version_id, version_data in tracker["versions"].items():
        for patch_id, patch in version_data["patches"].items():
            if patch["status"] == "discovered":
                patch["status"] = "pending_approval"
                patch["downloaded_at"] = now
                downloaded.append(patch_id)
    return downloaded


def main():
    print("=" * 60)
    print("  SFTP PIPELINE DRY RUN")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not SFTP_HOST or SFTP_HOST == "your-sftp-host-here":
        print("ERROR: Fill in .env first.")
        sys.exit(1)

    print(f"\n  Connecting...")
    try:
        transport, sftp = connect_sftp()
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)
    print("  Connected.\n")

    all_new = {}

    # --- PHASE 1: SCAN + UPDATE TRACKERS ---
    print("=" * 60)
    print("  PHASE 1: SCAN SFTP & UPDATE TRACKERS")
    print("=" * 60)

    for product_id, product_cfg in CONFIG["products"].items():
        track_label = product_cfg.get("track_from") or "ALL"
        print(f"\n--- {product_cfg['display_name']} (track from: {track_label}) ---")

        raw_patches = discover_patches(sftp, product_id, product_cfg)
        tracker = load_tracker(product_id)
        new_patches = update_tracker(tracker, product_id, raw_patches)
        save_tracker(tracker)

        all_new[product_id] = new_patches

        if new_patches:
            for pid in new_patches:
                version = version_from_patch_id(pid)
                print(f"  NEW: {version}/{pid}")
            print(f"  ({len(new_patches)} new, {len(raw_patches)} total on SFTP)")
        else:
            print(f"  No new patches. ({len(raw_patches)} already tracked)")

    sftp.close()
    transport.close()

    # --- PHASE 2: SIMULATE DOWNLOAD ---
    print("\n" + "=" * 60)
    print("  PHASE 2: DOWNLOAD SIMULATION")
    print("=" * 60)

    for product_id in CONFIG["products"]:
        tracker = load_tracker(product_id)
        downloaded = simulate_download(tracker)
        save_tracker(tracker)

        display = CONFIG["products"][product_id]["display_name"]
        if downloaded:
            for pid in downloaded:
                print(f"  [DOWNLOAD] {display} / {pid}")
                print(f"    -> downloaded -> pending_approval")

    # --- PHASE 3: APPROVAL GATE ---
    print("\n" + "=" * 60)
    print("  PHASE 3: APPROVAL GATE")
    print("=" * 60)

    total_pending = 0
    for product_id in CONFIG["products"]:
        tracker = load_tracker(product_id)
        display = CONFIG["products"][product_id]["display_name"]

        print(f"\n--- {display} ---")

        for vid in sorted(tracker["versions"]):
            patches = tracker["versions"][vid]["patches"]
            pending = {pid: p for pid, p in patches.items() if p["status"] == "pending_approval"}
            if not pending:
                continue
            for pid in sorted(pending):
                total_pending += 1
                print(f"  [{total_pending}] {vid}/{pid}")
                print(f"      >> APPROVE binaries for {pid}? (simulated: YES)")
                print(f"      -> pending_approval -> approved -> published")

    # --- SUMMARY ---
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)

    for product_id in CONFIG["products"]:
        tracker = load_tracker(product_id)
        display = CONFIG["products"][product_id]["display_name"]
        version_count = len(tracker["versions"])
        patch_count = sum(
            len(v["patches"]) for v in tracker["versions"].values()
        )
        print(f"\n  {display}: {version_count} versions, {patch_count} patches")
        for version_id in sorted(tracker["versions"]):
            patches = tracker["versions"][version_id]["patches"]
            print(f"    {version_id}/")
            for pid in sorted(patches):
                status = patches[pid]["status"]
                print(f"      {pid}  [{status}]")

    print(f"\n  TOTAL PENDING APPROVAL: {total_pending}")
    print(f"  Tracker files saved to: {STATE_DIR}/\n")


if __name__ == "__main__":
    main()
