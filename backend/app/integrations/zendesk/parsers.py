"""Pure helpers for the Zendesk integration.

Kept separate from client.py so they can be unit-tested without touching HTTP.
Lifted from scripts/test_zendesk_scraper.py — see header comments there for
the original validated logic.
"""

import re

VERSION_RE = re.compile(r"(\d+(?:\.\d+){1,3})")

# Section name → product branch identifier. The release-note category page
# lists one section per product family; we resolve a patch's family from the
# first two version components and look up the matching pattern here.
SECTION_PATTERNS: dict[str, str] = {
    "8.1": r"v?8\.?1.*ACARS",
    "8.0": r"v?8\.?0.*ACARS",
    "7.3": r"v?7\.?3.*ACARS",
}

SAFE_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def parse_version_tuple(text: str) -> tuple[int, ...] | None:
    """Extract a dotted version like '8.1.16.1' from arbitrary text."""
    m = VERSION_RE.search(text or "")
    if not m:
        return None
    try:
        return tuple(int(p) for p in m.group(1).split("."))
    except ValueError:
        return None


def safe_name(name: str) -> str:
    """Strip filesystem-unsafe characters from a filename."""
    return SAFE_NAME_RE.sub("_", name).strip().rstrip(".")


def family_for_version(version: str) -> str | None:
    """Return the product-family key (e.g. '8.1') for a version like '8.1.16.1'.

    Returns None if the version cannot be parsed or has fewer than two parts.
    """
    parts = parse_version_tuple(version)
    if not parts or len(parts) < 2:
        return None
    return f"{parts[0]}.{parts[1]}"
