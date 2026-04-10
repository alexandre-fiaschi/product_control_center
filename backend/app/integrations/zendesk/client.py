"""Zendesk help-center client for release-notes scraping.

Thin wrapper around a curl_cffi session — no business logic, no lifecycle
awareness. The pipeline fetcher in app/pipelines/docs/fetcher.py owns the
state-machine transitions; this module only knows how to log in, find an
article matching a version, and stream a PDF.

Auth strategy is lifted from scripts/test_zendesk_scraper.py and validated
against cyberjetsupport.zendesk.com on 2026-04-10. See HANDOFF.md for the
gotchas (curl_cffi impersonation, legacy /access/login endpoint, etc.).
"""

from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from app.integrations.zendesk.parsers import (
    SECTION_PATTERNS,
    family_for_version,
)

logger = logging.getLogger("integrations.zendesk.client")

# curl_cffi impersonation profile — defeats Cloudflare's "Just a moment..." JS
# challenge by presenting a real Chrome TLS fingerprint. Do NOT override the
# session User-Agent: impersonate= sets UA + TLS fingerprint together.
IMPERSONATE = "chrome"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ZendeskAuthError(RuntimeError):
    """Login failed: bad creds, missing CSRF token, SSO redirect, etc."""


class ZendeskNotFound(LookupError):
    """No article matching the requested version was found."""


class ZendeskAmbiguous(LookupError):
    """Multiple articles matched the requested version — refusing to guess."""

    def __init__(self, version: str, candidates: list["ArticleMatch"]):
        self.version = version
        self.candidates = candidates
        super().__init__(
            f"Multiple Zendesk articles matched {version}: "
            f"{[c.title for c in candidates]}"
        )


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ArticleMatch:
    title: str
    article_url: str
    pdf_filename: str
    pdf_url: str


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class ZendeskClient:
    """Authenticated, polite-throttled help-center scraper.

    One instance per scan. Login is lazy: it happens on the first call that
    needs an authenticated session.
    """

    def __init__(
        self,
        subdomain: str,
        email: str,
        password: str,
        *,
        category_url: str | None = None,
    ):
        if not subdomain or not email or not password:
            raise ZendeskAuthError(
                "Zendesk credentials missing — set ZENDESK_SUBDOMAIN, "
                "ZENDESK_EMAIL, ZENDESK_PASSWORD in .env"
            )
        self.subdomain = subdomain
        self.email = email
        self.password = password
        self.base_url = f"https://{subdomain}.zendesk.com"
        self.signin_url = f"{self.base_url}/hc/en-gb/signin"
        self.spa_signin_url = f"{self.base_url}/auth/v3/signin"
        self.login_post_url = f"{self.base_url}/access/login"
        # Category URL can be overridden via config; default matches the
        # validated CyberJet release-note category.
        self.category_url = (
            category_url
            or f"{self.base_url}/hc/en-gb/categories/360000515774-Release-Note"
        )
        self._session: curl_requests.Session | None = None
        self._authenticated = False

    # -- session management ------------------------------------------------

    def _ensure_session(self) -> curl_requests.Session:
        if self._session is None:
            s = curl_requests.Session(impersonate=IMPERSONATE)
            s.headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9",
            })
            self._session = s
        return self._session

    def _polite_sleep(self) -> None:
        time.sleep(random.uniform(0.5, 1.5))

    def _ensure_auth(self) -> None:
        if not self._authenticated:
            self.login()

    def close(self) -> None:
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None
            self._authenticated = False

    def __enter__(self) -> "ZendeskClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- auth --------------------------------------------------------------

    def login(self) -> None:
        """Log into the Zendesk help center.

        Validated 2026-04-10 against cyberjetsupport.zendesk.com:
          1. GET /hc/en-gb/signin (redirects to /auth/v3/signin SPA HTML).
          2. Scrape `authenticity_token` from the SPA HTML.
          3. POST classic form payload to /access/login (Referer must be the
             SPA URL or Zendesk silently rejects).
          4. Verify by GETing the gated category page — success means no
             redirect back to /access/login and `_zendesk_authenticated`
             cookie is set.
        """
        session = self._ensure_session()

        logger.info("zendesk.auth.start subdomain=%s", self.subdomain)
        r = session.get(self.signin_url, allow_redirects=True)
        if r.status_code != 200:
            raise ZendeskAuthError(
                f"Signin GET returned HTTP {r.status_code}"
            )

        final_host = urlparse(r.url).netloc
        if final_host and final_host != urlparse(self.base_url).netloc:
            raise ZendeskAuthError(
                f"Signin redirected off-domain to {final_host} — looks like SSO"
            )

        soup = BeautifulSoup(r.text, "html.parser")
        token_input = soup.find("input", attrs={"name": "authenticity_token"})
        token = token_input["value"] if token_input and token_input.get("value") else None
        if not token:
            meta = soup.find("meta", attrs={"name": "csrf-token"})
            token = meta.get("content") if meta else None
        if not token:
            raise ZendeskAuthError(
                "Could not find authenticity_token / csrf-token on signin page"
            )

        payload = {
            "utf8": "✓",
            "authenticity_token": token,
            "user[email]": self.email,
            "user[password]": self.password,
            "user[remember_me]": "0",
            "return_to": self.category_url,
            "commit": "Sign in",
        }
        headers = {
            "Referer": self.spa_signin_url,
            "Origin": self.base_url,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        self._polite_sleep()
        r = session.post(
            self.login_post_url, data=payload, headers=headers, allow_redirects=True,
        )
        if r.status_code >= 400:
            raise ZendeskAuthError(
                f"Login POST returned HTTP {r.status_code} (final URL {r.url})"
            )

        self._polite_sleep()
        r = session.get(self.category_url, allow_redirects=True)
        if r.status_code != 200:
            raise ZendeskAuthError(
                f"Category GET returned HTTP {r.status_code} after login"
            )
        if "/access/login" in r.url or "/auth/v3/signin" in r.url:
            raise ZendeskAuthError(
                f"After login redirected to {r.url} — credentials rejected"
            )
        if "user[password]" in r.text and "user[email]" in r.text:
            raise ZendeskAuthError(
                "Category page still shows the login form — auth did not stick"
            )

        # _zendesk_authenticated is the success cookie marker per HANDOFF.md.
        # We log it but do not require it — some sessions return success
        # without it depending on cookie store quirks.
        try:
            auth_cookie = any(
                c.name == "_zendesk_authenticated" for c in session.cookies.jar
            )
        except Exception:
            auth_cookie = False
        logger.info(
            "zendesk.auth.success subdomain=%s auth_cookie=%s",
            self.subdomain, auth_cookie,
        )
        self._authenticated = True

    # -- discovery ---------------------------------------------------------

    def find_article_for_version(self, version: str) -> ArticleMatch:
        """Find the release-notes article + PDF for a full version string.

        Walks the product-family section, lists every article, opens each one
        to enumerate PDF attachments, and filters to candidates whose article
        title or PDF filename starts with the full ``version`` string.

        Raises ZendeskNotFound on zero matches, ZendeskAmbiguous on multiple.
        """
        self._ensure_auth()

        family = family_for_version(version)
        if family is None or family not in SECTION_PATTERNS:
            raise ZendeskNotFound(
                f"Cannot resolve product family for version {version!r}"
            )

        logger.info(
            "zendesk.fetch.start version=%s family=%s",
            version, family,
        )

        section_url = self._resolve_family_section(family)
        if section_url is None:
            logger.warning(
                "zendesk.fetch.no_section version=%s family=%s",
                version, family,
            )
            raise ZendeskNotFound(
                f"No section matched product family {family} on {self.category_url}"
            )

        articles = list(self._discover_articles(section_url))
        logger.debug(
            "zendesk.fetch.section_walk version=%s family=%s articles=%d",
            version, family, len(articles),
        )

        # Two-phase match: first by article title prefix (cheap, no extra
        # request), then fall back to opening any article whose title contains
        # the version's first three components (e.g. "8.1.16") to look for a
        # PDF filename match. This keeps the request count down on the common
        # case where article titles are well-named.
        candidates: list[ArticleMatch] = []
        seen_pdf_urls: set[str] = set()

        # First, scan article titles for an exact prefix match.
        title_hits = [
            (title, url) for (title, url) in articles
            if title.lstrip().startswith(version)
        ]
        for title, article_url in title_hits:
            for filename, pdf_url in self._discover_pdfs(article_url):
                if pdf_url in seen_pdf_urls:
                    continue
                seen_pdf_urls.add(pdf_url)
                candidates.append(
                    ArticleMatch(
                        title=title,
                        article_url=article_url,
                        pdf_filename=filename,
                        pdf_url=pdf_url,
                    )
                )

        # If nothing matched by title alone, scan any article whose title
        # mentions the maintenance band (first three components) and look for
        # PDFs whose filename starts with the full version.
        if not candidates:
            parts = version.split(".")
            band = ".".join(parts[:3]) if len(parts) >= 3 else version
            for title, article_url in articles:
                if band not in title:
                    continue
                for filename, pdf_url in self._discover_pdfs(article_url):
                    if not filename.lstrip().startswith(version):
                        continue
                    if pdf_url in seen_pdf_urls:
                        continue
                    seen_pdf_urls.add(pdf_url)
                    candidates.append(
                        ArticleMatch(
                            title=title,
                            article_url=article_url,
                            pdf_filename=filename,
                            pdf_url=pdf_url,
                        )
                    )

        if not candidates:
            logger.info(
                "zendesk.fetch.no_match version=%s family=%s articles_scanned=%d",
                version, family, len(articles),
            )
            raise ZendeskNotFound(
                f"No release-notes article found for version {version}"
            )

        if len(candidates) > 1:
            logger.warning(
                "zendesk.fetch.ambiguous_match version=%s family=%s candidates=%d titles=%s",
                version, family, len(candidates), [c.title for c in candidates],
            )
            raise ZendeskAmbiguous(version, candidates)

        match = candidates[0]
        logger.info(
            "zendesk.fetch.matched version=%s title=%r pdf=%r",
            version, match.title, match.pdf_filename,
        )
        return match

    def _resolve_family_section(self, family: str) -> str | None:
        import re
        session = self._ensure_session()
        self._polite_sleep()
        r = session.get(self.category_url)
        if r.status_code != 200:
            raise ZendeskNotFound(
                f"Category page returned HTTP {r.status_code}"
            )
        soup = BeautifulSoup(r.text, "html.parser")
        pattern = SECTION_PATTERNS[family]
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/sections/" not in href:
                continue
            name = " ".join(a.get_text().split())
            if not name:
                continue
            if re.search(pattern, name, re.IGNORECASE):
                full = urljoin(self.base_url, href.split("?")[0])
                logger.debug(
                    "zendesk.fetch.section_resolved family=%s name=%r url=%s",
                    family, name, full,
                )
                return full
        return None

    def _discover_articles(self, section_url: str) -> Iterable[tuple[str, str]]:
        """Yield (article_title, article_url) for every article in a section."""
        import re
        session = self._ensure_session()
        seen: set[str] = set()
        page = 1
        while True:
            url = f"{section_url}?page={page}" if page > 1 else section_url
            self._polite_sleep()
            r = session.get(url)
            if r.status_code != 200:
                logger.warning(
                    "zendesk.fetch.section_page_failed url=%s status=%d",
                    url, r.status_code,
                )
                break
            soup = BeautifulSoup(r.text, "html.parser")

            page_count = 0
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/articles/" not in href:
                    continue
                title = " ".join(a.get_text().split())
                if not title:
                    continue
                full = urljoin(self.base_url, href.split("?")[0].split("#")[0])
                if full in seen:
                    continue
                seen.add(full)
                page_count += 1
                yield (title, full)

            if page_count == 0:
                break

            next_link = soup.find("a", attrs={"rel": "next"}) or soup.find(
                "a", string=re.compile(r"next", re.I),
            )
            if not next_link:
                break
            page += 1
            if page > 20:  # safety cap
                logger.warning("zendesk.fetch.pagination_capped url=%s", section_url)
                break

    def _discover_pdfs(self, article_url: str) -> list[tuple[str, str]]:
        """Return [(filename, attachment_url), ...] for PDFs on an article page."""
        session = self._ensure_session()
        self._polite_sleep()
        r = session.get(article_url)
        if r.status_code != 200:
            logger.warning(
                "zendesk.fetch.article_failed url=%s status=%d",
                article_url, r.status_code,
            )
            return []
        soup = BeautifulSoup(r.text, "html.parser")

        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            is_attachment = (
                "/article_attachments/" in href
                or "/hc/article_attachments/" in href
            )
            looks_like_pdf = href.lower().endswith(".pdf") or ".pdf" in a.get_text().lower()
            if not (is_attachment or looks_like_pdf):
                continue
            full = urljoin(self.base_url, href)
            if full in seen:
                continue
            seen.add(full)
            text = " ".join(a.get_text().split())
            filename = (
                text if text.lower().endswith(".pdf")
                else os.path.basename(urlparse(full).path)
            )
            if not filename.lower().endswith(".pdf"):
                filename += ".pdf"
            out.append((filename, full))
        return out

    # -- download ----------------------------------------------------------

    def download_pdf(self, pdf_url: str, dest_path: Path) -> int:
        """Stream a PDF to disk. Returns the number of bytes written.

        Overwrites any existing file at ``dest_path``. Raises IOError on any
        non-200 response or if the response is HTML (auth bounce).
        """
        self._ensure_auth()
        session = self._ensure_session()

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        self._polite_sleep()
        logger.info(
            "zendesk.download.start url=%s dest=%s",
            pdf_url, dest_path,
        )

        # NB: curl_cffi Response is NOT a context manager — call .close() in
        # finally per HANDOFF.md.
        r = session.get(pdf_url, stream=True, allow_redirects=True)
        try:
            if r.status_code != 200:
                raise IOError(
                    f"Download HTTP {r.status_code} for {pdf_url}"
                )
            ctype = r.headers.get("Content-Type", "")
            if "html" in ctype.lower():
                raise IOError(
                    f"Got HTML instead of PDF for {pdf_url} — auth bounce"
                )

            tmp = dest_path.with_suffix(dest_path.suffix + ".part")
            size = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
                        size += len(chunk)
            tmp.replace(dest_path)
        finally:
            r.close()

        logger.info(
            "zendesk.download.success dest=%s bytes=%d",
            dest_path, size,
        )
        return size
