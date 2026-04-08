"""Normalize SFTP folder names to dotted patch IDs and parse version/patch components."""

import re


def _match_ints(pattern: str, text: str) -> tuple[int, ...] | None:
    """Apply regex, return captured groups as ints, or None on no match."""
    m = re.match(pattern, text)
    return tuple(int(g) for g in m.groups()) if m else None


# --- Regex patterns per product ---
_V73_PATCH = r"7_3_(\d+)_(\d+)$"
_V80_VERSION = r"8_0_(\d+)$"
_V80_PATCH = r"8_0_(\d+)_(\d+)$"
_V81_VERSION = r"ACARS_V8_1_(\d+)$"
_V81_PATCH = r"v?8\.1\.(\d+)\.(\d+)$"


def normalize_patch_id(product_id: str, folder_name: str) -> str | None:
    """Convert any folder naming to normalized dotted format.

    7_3_27_7   -> 7.3.27.7
    8_0_28_1   -> 8.0.28.1
    v8.1.9.1   -> 8.1.9.1
    8.1.11.0   -> 8.1.11.0
    """
    pattern, prefix = {
        "ACARS_V7_3": (_V73_PATCH, "7.3"),
        "ACARS_V8_0": (_V80_PATCH, "8.0"),
        "ACARS_V8_1": (_V81_PATCH, "8.1"),
    }.get(product_id, (None, None))

    if pattern is None:
        return None
    parts = _match_ints(pattern, folder_name)
    return f"{prefix}.{parts[0]}.{parts[1]}" if parts else None


def version_from_patch_id(patch_id: str) -> str:
    """8.1.9.1 -> 8.1.9, 7.3.27.7 -> 7.3.27"""
    return patch_id.rsplit(".", 1)[0]


def parse_v81_version(folder_name: str) -> int | None:
    """ACARS_V8_1_0 -> 0, ACARS_V8_1_12 -> 12"""
    r = _match_ints(_V81_VERSION, folder_name)
    return r[0] if r else None


def parse_v81_patch(folder_name: str) -> tuple[int, int] | None:
    """v8.1.0.0 -> (0, 0), 8.1.11.0 -> (11, 0)"""
    return _match_ints(_V81_PATCH, folder_name)


def parse_v80_version(folder_name: str) -> int | None:
    """8_0_4 -> 4, 8_0_28 -> 28"""
    r = _match_ints(_V80_VERSION, folder_name)
    return r[0] if r else None


def parse_v80_patch(folder_name: str) -> tuple[int, int] | None:
    """8_0_28_1 -> (28, 1)"""
    return _match_ints(_V80_PATCH, folder_name)


def parse_v73_patch(folder_name: str) -> tuple[int, int] | None:
    """7_3_27_7 -> (27, 7)"""
    return _match_ints(_V73_PATCH, folder_name)


def parse_track_from(track_from: str | None, product_id: str) -> int | tuple[int, int] | None:
    """Parse the track_from config value into a comparable cutoff."""
    if track_from is None:
        return None
    if product_id == "ACARS_V8_0":
        r = _match_ints(r"8_0_(\d+)", track_from)
        return r[0] if r else 0
    if product_id == "ACARS_V7_3":
        r = _match_ints(r"7_3_(\d+)_(\d+)", track_from)
        return r if r else (0, 0)
    return None
