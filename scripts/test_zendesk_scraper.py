#!/usr/bin/env python3
"""
Zendesk Release Notes Scraper — standalone prototype.

Logs into the CyberJet Zendesk help center with user/password, walks the
"Release Note" category, finds release-notes articles for ACARS 7.3 / 8.0 / 8.1,
and downloads every PDF attachment to docs_example/<branch>/zendesk_pdf_download/.

Two-phase usage (recommended):

  # Phase A — prove auth works (no downloads):
  python scripts/test_zendesk_scraper.py --check-auth --verbose

  # Phase B — once auth is green, run the real crawl:
  python scripts/test_zendesk_scraper.py --product 8.1 --min-version 8.1.10 --verbose
  python scripts/test_zendesk_scraper.py --product 8.1 --min-version 8.1.10 --limit 1 --dry-run --verbose

Required env vars (.env in project root):
  ZENDESK_SUBDOMAIN=cyberjetsupport
  ZENDESK_EMAIL=...
  ZENDESK_PASSWORD=...
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

ZENDESK_SUBDOMAIN = os.getenv("ZENDESK_SUBDOMAIN", "cyberjetsupport")
ZENDESK_EMAIL = os.getenv("ZENDESK_EMAIL", "")
ZENDESK_PASSWORD = os.getenv("ZENDESK_PASSWORD", "")

BASE_URL = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com"
SIGNIN_URL = f"{BASE_URL}/hc/en-gb/signin"
# Zendesk's new Next.js auth flow lives here — used as Referer for the legacy POST.
SPA_SIGNIN_URL = f"{BASE_URL}/auth/v3/signin"
LOGIN_POST_URL = f"{BASE_URL}/access/login"
CATEGORY_URL = f"{BASE_URL}/hc/en-gb/categories/360000515774-Release-Note"

# curl_cffi impersonation profile — defeats Cloudflare's "Just a moment..." JS challenge
# by presenting a real Chrome TLS fingerprint. See README for why requests fails here.
IMPERSONATE = "chrome"

# Section name → product branch identifier (used for output paths and filtering)
SECTION_PATTERNS: dict[str, str] = {
    "8.1": r"v?8\.?1.*ACARS",
    "8.0": r"v?8\.?0.*ACARS",
    "7.3": r"v?7\.?3.*ACARS",
}

logger = logging.getLogger("scripts.zendesk_scraper")


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet noisy libs
    logging.getLogger("urllib3").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# HTTP session + polite throttling
# ---------------------------------------------------------------------------

def make_session() -> requests.Session:
    # curl_cffi sets the Chrome User-Agent + matching TLS fingerprint automatically
    # via impersonate=. Don't override User-Agent or it desyncs from the fingerprint
    # and Cloudflare blocks us again.
    s = requests.Session(impersonate=IMPERSONATE)
    s.headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    })
    return s


def polite_sleep() -> None:
    time.sleep(random.uniform(0.5, 1.5))


def snippet(text: str, n: int = 400) -> str:
    text = " ".join(text.split())
    return text[:n] + ("..." if len(text) > n else "")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class AuthError(RuntimeError):
    pass


def login(session: requests.Session) -> None:
    """Log into Zendesk help center.

    Flow (validated 2026-04-10 against cyberjetsupport.zendesk.com):
      1. GET /hc/en-gb/signin — redirects to the new Next.js SPA at /auth/v3/signin.
         The HTML still contains a hidden `authenticity_token` input we can scrape,
         and the response sets the session cookies we need (_zendesk_session, etc.).
      2. POST credentials directly to the legacy /access/login endpoint. The new
         SPA frontend submits via JS to a different path, but the legacy backend
         endpoint still accepts the classic form payload — much simpler than
         reverse-engineering the SPA's bundled JS.
      3. Verify by GETing the gated category page; success = no login form in body.
    """
    if not ZENDESK_EMAIL or not ZENDESK_PASSWORD:
        raise AuthError(
            "Missing ZENDESK_EMAIL / ZENDESK_PASSWORD in .env. "
            "Add them to the project root .env file and retry."
        )

    logger.info("Fetching signin page: %s", SIGNIN_URL)
    r = session.get(SIGNIN_URL, allow_redirects=True)
    logger.debug("GET signin → %s (final URL %s)", r.status_code, r.url)
    if r.status_code != 200:
        raise AuthError(f"Signin GET returned HTTP {r.status_code}: {snippet(r.text)}")

    # Detect SSO redirects upfront — these mean username/password login won't work.
    final_host = urlparse(r.url).netloc
    if final_host and final_host != urlparse(BASE_URL).netloc:
        raise AuthError(
            f"Signin page redirected off-domain to {final_host} — looks like SSO. "
            "Bring this output back and re-plan auth strategy."
        )

    soup = BeautifulSoup(r.text, "html.parser")
    token_input = soup.find("input", attrs={"name": "authenticity_token"})
    token = token_input["value"] if token_input and token_input.get("value") else None
    if not token:
        meta = soup.find("meta", attrs={"name": "csrf-token"})
        token = meta.get("content") if meta else None
    if not token:
        raise AuthError(
            "Could not find authenticity_token / csrf-token on signin page. "
            f"Body snippet: {snippet(r.text)}"
        )
    logger.debug("CSRF token acquired (len=%d)", len(token))

    payload = {
        "utf8": "✓",
        "authenticity_token": token,
        "user[email]": ZENDESK_EMAIL,
        "user[password]": ZENDESK_PASSWORD,
        "user[remember_me]": "0",
        "return_to": CATEGORY_URL,
        "commit": "Sign in",
    }
    headers = {
        "Referer": SPA_SIGNIN_URL,
        "Origin": BASE_URL,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    polite_sleep()
    logger.info("POST credentials to %s", LOGIN_POST_URL)
    r = session.post(LOGIN_POST_URL, data=payload, headers=headers, allow_redirects=True)
    logger.debug("POST login → %s (final URL %s)", r.status_code, r.url)

    if r.status_code >= 400:
        raise AuthError(
            f"Login POST returned HTTP {r.status_code}. "
            f"Final URL: {r.url}. Body snippet: {snippet(r.text)}"
        )

    # Verify: the POST already follows redirects, so r.url should already be the
    # category page on success. Re-GET it to be sure cookies stick across requests.
    polite_sleep()
    logger.info("Verifying auth by GET %s", CATEGORY_URL)
    r = session.get(CATEGORY_URL, allow_redirects=True)
    logger.debug("GET category → %s (final URL %s)", r.status_code, r.url)

    if r.status_code != 200:
        raise AuthError(f"Category GET returned HTTP {r.status_code}: {snippet(r.text)}")
    if "/access/login" in r.url or "/auth/v3/signin" in r.url:
        raise AuthError(
            f"After login we got redirected to {r.url} — credentials rejected or "
            f"extra step required. Body snippet: {snippet(r.text)}"
        )
    if "user[password]" in r.text and "user[email]" in r.text:
        raise AuthError(
            "Category page still shows the login form — auth did not stick. "
            f"Body snippet: {snippet(r.text)}"
        )

    # Success marker: Zendesk sets _zendesk_authenticated cookie after login.
    auth_cookie = any(c.name == "_zendesk_authenticated" for c in session.cookies.jar)
    logger.debug("_zendesk_authenticated cookie set: %s", auth_cookie)
    logger.info("AUTH OK ✓")


# ---------------------------------------------------------------------------
# Crawl
# ---------------------------------------------------------------------------

VERSION_RE = re.compile(r"(\d+(?:\.\d+){1,3})")


def parse_version_tuple(text: str) -> tuple[int, ...] | None:
    m = VERSION_RE.search(text or "")
    if not m:
        return None
    try:
        return tuple(int(p) for p in m.group(1).split("."))
    except ValueError:
        return None


def version_ge(a: tuple[int, ...], b: tuple[int, ...]) -> bool:
    """Return True if a >= b, padding the shorter with zeros."""
    n = max(len(a), len(b))
    return tuple(a + (0,) * (n - len(a))) >= tuple(b + (0,) * (n - len(b)))


def discover_sections(session: requests.Session, products: list[str]) -> list[tuple[str, str]]:
    """Return [(branch, section_url), ...] for the requested product branches."""
    polite_sleep()
    r = session.get(CATEGORY_URL)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/sections/" not in href:
            continue
        name = " ".join(a.get_text().split())
        if not name:
            continue
        for branch in products:
            pat = SECTION_PATTERNS[branch]
            if re.search(pat, name, re.IGNORECASE):
                full = urljoin(BASE_URL, href.split("?")[0])
                key = (branch, full)
                if full in seen:
                    continue
                seen.add(full)
                found.append((branch, full))
                logger.info("Section discovered: [%s] %s → %s", branch, name, full)
                break
    if not found:
        logger.warning("No sections matched for products=%s on category page", products)
    return found


def discover_articles(session: requests.Session, section_url: str) -> list[tuple[str, str]]:
    """Return [(article_title, article_url), ...] across all pages of a section."""
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    page = 1
    while True:
        url = f"{section_url}?page={page}" if page > 1 else section_url
        polite_sleep()
        logger.debug("Fetching section page: %s", url)
        r = session.get(url)
        if r.status_code != 200:
            logger.warning("Section page %s returned HTTP %s — stopping pagination", url, r.status_code)
            break
        soup = BeautifulSoup(r.text, "html.parser")

        page_articles: list[tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/articles/" not in href:
                continue
            title = " ".join(a.get_text().split())
            if not title:
                continue
            full = urljoin(BASE_URL, href.split("?")[0].split("#")[0])
            if full in seen:
                continue
            seen.add(full)
            page_articles.append((title, full))

        if not page_articles:
            logger.debug("No new articles on page %d — stopping", page)
            break
        results.extend(page_articles)
        logger.debug("Page %d: %d new articles", page, len(page_articles))

        # Look for an explicit "next page" link; otherwise stop after the first
        # empty page above.
        next_link = soup.find("a", attrs={"rel": "next"}) or soup.find("a", string=re.compile(r"next", re.I))
        if not next_link:
            break
        page += 1
        if page > 20:  # safety
            logger.warning("Stopping pagination at page 20 (safety cap)")
            break

    return results


def discover_pdfs(session: requests.Session, article_url: str) -> list[tuple[str, str]]:
    """Return [(filename, attachment_url), ...] for all PDF attachments on an article."""
    polite_sleep()
    r = session.get(article_url)
    if r.status_code != 200:
        logger.warning("Article %s → HTTP %s", article_url, r.status_code)
        return []
    soup = BeautifulSoup(r.text, "html.parser")

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        is_attachment = "/article_attachments/" in href or "/hc/article_attachments/" in href
        looks_like_pdf = href.lower().endswith(".pdf") or ".pdf" in a.get_text().lower()
        if not (is_attachment or looks_like_pdf):
            continue
        full = urljoin(BASE_URL, href)
        if full in seen:
            continue
        seen.add(full)
        # Filename: prefer the visible link text, fall back to URL basename.
        text = " ".join(a.get_text().split())
        filename = text if text.lower().endswith(".pdf") else os.path.basename(urlparse(full).path)
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        out.append((filename, full))
    return out


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

SAFE_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name: str) -> str:
    return SAFE_NAME_RE.sub("_", name).strip().rstrip(".")


def download_pdf(session: requests.Session, url: str, dest: Path, dry_run: bool) -> bool:
    """Stream a PDF to disk. Returns True if downloaded, False if skipped."""
    if dest.exists() and dest.stat().st_size > 0:
        logger.info("SKIP (exists): %s", dest.relative_to(PROJECT_ROOT))
        return False
    if dry_run:
        logger.info("DRY-RUN would download: %s → %s", url, dest.relative_to(PROJECT_ROOT))
        return False

    polite_sleep()
    logger.info("Downloading %s", url)
    # NB: curl_cffi Response is not a context manager — call .close() in finally.
    r = session.get(url, stream=True, allow_redirects=True)
    try:
        if r.status_code != 200:
            logger.error("Download failed HTTP %s for %s", r.status_code, url)
            return False
        ctype = r.headers.get("Content-Type", "")
        if "application/pdf" not in ctype.lower():
            # Accept octet-stream (some Zendesk attachments come back that way) but
            # reject anything that smells like HTML — that means auth bounce.
            if "html" in ctype.lower():
                logger.error("Got HTML instead of PDF for %s — likely auth bounce", url)
                return False
            logger.warning("Unexpected Content-Type %r for %s — saving anyway", ctype, url)

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        size = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if chunk:
                    f.write(chunk)
                    size += len(chunk)
        tmp.rename(dest)
    finally:
        r.close()
    logger.info("Saved %s (%d bytes)", dest.relative_to(PROJECT_ROOT), size)
    return True


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_crawl(
    session: requests.Session,
    products: list[str],
    min_versions: dict[str, tuple[int, ...] | None],
    limit: int | None,
    dry_run: bool,
) -> None:
    sections = discover_sections(session, products)
    if not sections:
        logger.error("No matching sections found — aborting crawl")
        return

    total_downloaded = 0
    total_skipped = 0
    for branch, section_url in sections:
        logger.info("=== Branch %s — %s ===", branch, section_url)
        articles = discover_articles(session, section_url)
        logger.info("Branch %s: %d articles found", branch, len(articles))

        # Filter by min version
        floor = min_versions.get(branch)
        kept: list[tuple[str, str, tuple[int, ...]]] = []
        for title, url in articles:
            v = parse_version_tuple(title)
            if v is None:
                logger.debug("Skip (no version): %s", title)
                continue
            if floor and not version_ge(v, floor):
                logger.debug("Skip (below floor %s): %s", floor, title)
                continue
            kept.append((title, url, v))

        # Newest first by version tuple
        kept.sort(key=lambda x: x[2], reverse=True)
        if limit:
            kept = kept[:limit]

        logger.info("Branch %s: %d articles kept after filtering", branch, len(kept))

        for title, url, _ in kept:
            logger.info("--- Article: %s", title)
            pdfs = discover_pdfs(session, url)
            if not pdfs:
                logger.warning("No PDFs found on %s", url)
                continue
            article_dir = PROJECT_ROOT / "docs_example" / branch / "zendesk_pdf_download" / safe_name(title)
            for filename, pdf_url in pdfs:
                dest = article_dir / safe_name(filename)
                if download_pdf(session, pdf_url, dest, dry_run):
                    total_downloaded += 1
                else:
                    total_skipped += 1

    logger.info("Done. Downloaded: %d, skipped: %d", total_downloaded, total_skipped)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Zendesk release-notes scraper (standalone test)")
    p.add_argument("--check-auth", action="store_true",
                   help="Only verify login works, then exit. Run this first.")
    p.add_argument("--product", choices=["7.3", "8.0", "8.1", "all"], default="8.1",
                   help="Which product branch to crawl (default: 8.1)")
    p.add_argument("--min-version", default=None,
                   help="Floor version, e.g. 8.1.10 (defaults to 8.1.10 when --product=8.1)")
    p.add_argument("--limit", type=int, default=None,
                   help="Max number of newest articles per branch")
    p.add_argument("--dry-run", action="store_true",
                   help="Crawl + log what would be downloaded, but don't write files")
    p.add_argument("--verbose", action="store_true", help="DEBUG logging")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)

    logger.info("Zendesk subdomain: %s", ZENDESK_SUBDOMAIN)
    logger.info("Email: %s", ZENDESK_EMAIL or "<missing>")

    session = make_session()
    try:
        login(session)
    except AuthError as e:
        logger.error("AUTH FAILED: %s", e)
        return 2

    if args.check_auth:
        logger.info("Phase A complete — auth works. Re-run without --check-auth to crawl.")
        return 0

    # Resolve product list and min-version floors
    if args.product == "all":
        products = ["7.3", "8.0", "8.1"]
    else:
        products = [args.product]

    min_versions: dict[str, tuple[int, ...] | None] = {b: None for b in products}
    if args.min_version:
        v = parse_version_tuple(args.min_version)
        if not v:
            logger.error("Could not parse --min-version %r", args.min_version)
            return 2
        for b in products:
            min_versions[b] = v
    else:
        # Default floor only for 8.1 in this iteration
        if "8.1" in products:
            min_versions["8.1"] = (8, 1, 10)

    logger.info("Products: %s | min-versions: %s | limit: %s | dry-run: %s",
                products, min_versions, args.limit, args.dry_run)

    try:
        run_crawl(session, products, min_versions, args.limit, args.dry_run)
    except RequestException as e:
        logger.error("HTTP error during crawl: %s", e)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
