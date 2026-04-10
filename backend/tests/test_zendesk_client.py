"""Tests for app.integrations.zendesk.client.ZendeskClient.

Fixture-based — no live HTTP. We monkey-patch ZendeskClient._ensure_session
to return a fake session that serves canned HTML/PDF responses keyed by URL.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.integrations.zendesk.client import (
    ArticleMatch,
    ZendeskAmbiguous,
    ZendeskAuthError,
    ZendeskClient,
    ZendeskNotFound,
)
from app.integrations.zendesk.parsers import (
    family_for_version,
    parse_version_tuple,
    safe_name,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CATEGORY_URL = "https://example.zendesk.com/hc/en-gb/categories/360000515774-Release-Note"
SECTION_81_URL = "https://example.zendesk.com/hc/en-gb/sections/111-OpsComm-8-1-ACARS"
ARTICLE_8_1_16_1_URL = "https://example.zendesk.com/hc/en-gb/articles/8001"
ARTICLE_8_1_16_2_URL = "https://example.zendesk.com/hc/en-gb/articles/8002"
ARTICLE_8_1_15_0_URL = "https://example.zendesk.com/hc/en-gb/articles/8000"
PDF_8_1_16_1_URL = "https://example.zendesk.com/hc/article_attachments/9001"
PDF_8_1_16_2_URL = "https://example.zendesk.com/hc/article_attachments/9002"
PDF_DUP_8_1_16_1_URL = "https://example.zendesk.com/hc/article_attachments/9003"


def _signin_html(token: str | None = "csrf-abc123") -> str:
    if token is None:
        return "<html><body>no token here</body></html>"
    return f"""
    <html><body>
        <form>
            <input type="hidden" name="authenticity_token" value="{token}" />
        </form>
    </body></html>
    """


def _category_html() -> str:
    return f"""
    <html><body>
        <a href="/hc/en-gb/sections/111-OpsComm-8-1-ACARS">OpsComm v8.1 ACARS</a>
        <a href="/hc/en-gb/sections/222-OpsComm-8-0-ACARS">OpsComm v8.0 ACARS</a>
        <a href="/hc/en-gb/sections/333-OpsComm-7-3-ACARS">OpsComm v7.3 ACARS</a>
    </body></html>
    """


def _section_81_html() -> str:
    return f"""
    <html><body>
        <a href="/hc/en-gb/articles/8000">8.1.15.0 - Release Notes</a>
        <a href="/hc/en-gb/articles/8001">8.1.16.1 - Release Notes</a>
        <a href="/hc/en-gb/articles/8002">8.1.16.2 - Release Notes</a>
    </body></html>
    """


def _article_html(pdf_filename: str, pdf_url: str) -> str:
    return f"""
    <html><body>
        <a href="{pdf_url}">{pdf_filename}</a>
    </body></html>
    """


def _article_html_two_pdfs() -> str:
    """Article that lists the same version PDF twice — drives ambiguous match."""
    return f"""
    <html><body>
        <a href="{PDF_8_1_16_1_URL}">8.1.16.1 - Release Notes.pdf</a>
        <a href="{PDF_DUP_8_1_16_1_URL}">8.1.16.1 - Release Notes (v2).pdf</a>
    </body></html>
    """


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        text: str = "",
        url: str = "",
        content_type: str = "text/html",
        body: bytes = b"",
        cookies_set: list[str] | None = None,
    ):
        self.status_code = status_code
        self.text = text
        self.url = url or ""
        self.headers = {"Content-Type": content_type}
        self._body = body

    def iter_content(self, chunk_size: int = 64 * 1024):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def close(self) -> None:
        pass


class FakeCookies:
    def __init__(self) -> None:
        self.jar: list[SimpleNamespace] = []

    def add(self, name: str) -> None:
        self.jar.append(SimpleNamespace(name=name))


class FakeSession:
    """Map URLs → FakeResponse, record calls. Works for GET and POST."""

    def __init__(self, routes: dict[str, FakeResponse]):
        self.routes = routes
        self.headers: dict[str, str] = {}
        self.cookies = FakeCookies()
        self.calls: list[tuple[str, str]] = []  # (method, url)
        self.post_payloads: list[dict] = []

    def _match(self, url: str) -> FakeResponse:
        # Exact match first, then prefix match (handles ?page=N pagination).
        if url in self.routes:
            resp = self.routes[url]
        else:
            for prefix, resp in self.routes.items():
                if url.startswith(prefix):
                    break
            else:
                return FakeResponse(status_code=404, text="not found", url=url)
        # Stamp the response URL so that auth verification sees the gated URL.
        if not resp.url:
            resp.url = url
        return resp

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append(("GET", url))
        return self._match(url)

    def post(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append(("POST", url))
        self.post_payloads.append(kwargs.get("data") or {})
        # Login POST sets the auth cookie on success path.
        if url.endswith("/access/login") and "success-creds" in str(kwargs.get("data", {})):
            self.cookies.add("_zendesk_authenticated")
        return self._match(url)

    def close(self) -> None:
        pass


def _make_client_with_session(session: FakeSession) -> ZendeskClient:
    client = ZendeskClient(
        subdomain="example",
        email="user@example.com",
        password="success-creds",
        category_url=CATEGORY_URL,
    )
    client._session = session
    # Disable polite_sleep so the suite stays fast.
    client._polite_sleep = lambda: None  # type: ignore[method-assign]
    return client


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------

class TestParsers:
    def test_parse_version_tuple_full(self):
        assert parse_version_tuple("8.1.16.1 - Release Notes") == (8, 1, 16, 1)

    def test_parse_version_tuple_none(self):
        assert parse_version_tuple("nothing here") is None

    def test_safe_name_strips_unsafe(self):
        assert safe_name("8.1.16.1 / Release Notes.pdf") == "8.1.16.1 _ Release Notes.pdf"

    def test_family_for_version(self):
        assert family_for_version("8.1.16.1") == "8.1"
        assert family_for_version("7.3.27.0") == "7.3"
        assert family_for_version("nothing") is None


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success(self):
        routes = {
            "https://example.zendesk.com/hc/en-gb/signin": FakeResponse(
                text=_signin_html(), url="https://example.zendesk.com/auth/v3/signin",
            ),
            "https://example.zendesk.com/access/login": FakeResponse(
                text="ok", url=CATEGORY_URL,
            ),
            CATEGORY_URL: FakeResponse(text=_category_html(), url=CATEGORY_URL),
        }
        session = FakeSession(routes)
        client = _make_client_with_session(session)

        client.login()

        assert client._authenticated is True
        # POST hit /access/login with the CSRF token
        assert any(call[0] == "POST" for call in session.calls)
        payload = session.post_payloads[0]
        assert payload["authenticity_token"] == "csrf-abc123"
        assert payload["user[email]"] == "user@example.com"

    def test_login_missing_csrf_token_raises(self):
        routes = {
            "https://example.zendesk.com/hc/en-gb/signin": FakeResponse(
                text=_signin_html(token=None),
                url="https://example.zendesk.com/auth/v3/signin",
            ),
        }
        session = FakeSession(routes)
        client = _make_client_with_session(session)

        with pytest.raises(ZendeskAuthError, match="authenticity_token"):
            client.login()

    def test_login_redirect_back_to_login_raises(self):
        routes = {
            "https://example.zendesk.com/hc/en-gb/signin": FakeResponse(
                text=_signin_html(), url="https://example.zendesk.com/auth/v3/signin",
            ),
            "https://example.zendesk.com/access/login": FakeResponse(
                text="bad creds", url="https://example.zendesk.com/access/login",
            ),
            CATEGORY_URL: FakeResponse(
                text="login form here",
                url="https://example.zendesk.com/access/login",
            ),
        }
        session = FakeSession(routes)
        client = _make_client_with_session(session)

        with pytest.raises(ZendeskAuthError, match="redirected"):
            client.login()

    def test_missing_credentials_init_raises(self):
        with pytest.raises(ZendeskAuthError, match="missing"):
            ZendeskClient(subdomain="", email="", password="")


# ---------------------------------------------------------------------------
# find_article_for_version
# ---------------------------------------------------------------------------

def _login_routes() -> dict[str, FakeResponse]:
    """Routes that always succeed authentication, for find/download tests."""
    return {
        "https://example.zendesk.com/hc/en-gb/signin": FakeResponse(
            text=_signin_html(), url="https://example.zendesk.com/auth/v3/signin",
        ),
        "https://example.zendesk.com/access/login": FakeResponse(
            text="ok", url=CATEGORY_URL,
        ),
    }


class TestFindArticleForVersion:
    def test_happy_path_single_match(self):
        routes = _login_routes()
        routes[CATEGORY_URL] = FakeResponse(text=_category_html(), url=CATEGORY_URL)
        routes[SECTION_81_URL] = FakeResponse(text=_section_81_html(), url=SECTION_81_URL)
        routes[ARTICLE_8_1_15_0_URL] = FakeResponse(
            text=_article_html("8.1.15.0 - Release Notes.pdf",
                               "https://example.zendesk.com/hc/article_attachments/8500"),
            url=ARTICLE_8_1_15_0_URL,
        )
        routes[ARTICLE_8_1_16_1_URL] = FakeResponse(
            text=_article_html("8.1.16.1 - Release Notes.pdf", PDF_8_1_16_1_URL),
            url=ARTICLE_8_1_16_1_URL,
        )
        routes[ARTICLE_8_1_16_2_URL] = FakeResponse(
            text=_article_html("8.1.16.2 - Release Notes.pdf", PDF_8_1_16_2_URL),
            url=ARTICLE_8_1_16_2_URL,
        )
        client = _make_client_with_session(FakeSession(routes))

        match = client.find_article_for_version("8.1.16.1")

        assert isinstance(match, ArticleMatch)
        assert match.title.startswith("8.1.16.1")
        assert match.pdf_filename.startswith("8.1.16.1")
        assert match.pdf_url == PDF_8_1_16_1_URL
        assert match.article_url == ARTICLE_8_1_16_1_URL

    def test_not_found_raises_zendesk_not_found(self):
        routes = _login_routes()
        routes[CATEGORY_URL] = FakeResponse(text=_category_html(), url=CATEGORY_URL)
        routes[SECTION_81_URL] = FakeResponse(text=_section_81_html(), url=SECTION_81_URL)
        # Articles exist but none match version 8.1.99.99
        routes[ARTICLE_8_1_15_0_URL] = FakeResponse(
            text=_article_html("8.1.15.0 - Release Notes.pdf",
                               "https://example.zendesk.com/hc/article_attachments/8500"),
            url=ARTICLE_8_1_15_0_URL,
        )
        routes[ARTICLE_8_1_16_1_URL] = FakeResponse(
            text=_article_html("8.1.16.1 - Release Notes.pdf", PDF_8_1_16_1_URL),
            url=ARTICLE_8_1_16_1_URL,
        )
        routes[ARTICLE_8_1_16_2_URL] = FakeResponse(
            text=_article_html("8.1.16.2 - Release Notes.pdf", PDF_8_1_16_2_URL),
            url=ARTICLE_8_1_16_2_URL,
        )
        client = _make_client_with_session(FakeSession(routes))

        with pytest.raises(ZendeskNotFound):
            client.find_article_for_version("8.1.99.99")

    def test_ambiguous_raises_zendesk_ambiguous(self):
        routes = _login_routes()
        routes[CATEGORY_URL] = FakeResponse(text=_category_html(), url=CATEGORY_URL)
        # Two articles whose titles both start with 8.1.16.1
        routes[SECTION_81_URL] = FakeResponse(
            text="""
            <html><body>
                <a href="/hc/en-gb/articles/8001">8.1.16.1 - Release Notes</a>
                <a href="/hc/en-gb/articles/8011">8.1.16.1 - Release Notes (revised)</a>
            </body></html>
            """,
            url=SECTION_81_URL,
        )
        routes[ARTICLE_8_1_16_1_URL] = FakeResponse(
            text=_article_html("8.1.16.1 - Release Notes.pdf", PDF_8_1_16_1_URL),
            url=ARTICLE_8_1_16_1_URL,
        )
        routes["https://example.zendesk.com/hc/en-gb/articles/8011"] = FakeResponse(
            text=_article_html("8.1.16.1 - Release Notes (v2).pdf", PDF_DUP_8_1_16_1_URL),
            url="https://example.zendesk.com/hc/en-gb/articles/8011",
        )
        client = _make_client_with_session(FakeSession(routes))

        with pytest.raises(ZendeskAmbiguous) as excinfo:
            client.find_article_for_version("8.1.16.1")
        assert excinfo.value.version == "8.1.16.1"
        assert len(excinfo.value.candidates) == 2

    def test_no_section_for_unknown_family_raises_not_found(self):
        routes = _login_routes()
        routes[CATEGORY_URL] = FakeResponse(text=_category_html(), url=CATEGORY_URL)
        client = _make_client_with_session(FakeSession(routes))

        # Family 9.9 has no section pattern at all
        with pytest.raises(ZendeskNotFound):
            client.find_article_for_version("9.9.0.0")


# ---------------------------------------------------------------------------
# download_pdf
# ---------------------------------------------------------------------------

class TestDownloadPdf:
    def test_streams_pdf_to_disk(self, tmp_path: Path):
        routes = {}
        body = b"%PDF-fake-content" * 50
        routes[PDF_8_1_16_1_URL] = FakeResponse(
            content_type="application/pdf",
            body=body,
            url=PDF_8_1_16_1_URL,
        )
        client = _make_client_with_session(FakeSession(routes))
        client._authenticated = True  # skip login — covered by TestLogin

        dest = tmp_path / "out.pdf"
        size = client.download_pdf(PDF_8_1_16_1_URL, dest)

        assert size == len(body)
        assert dest.exists()
        assert dest.read_bytes() == body

    def test_html_content_type_raises_ioerror(self, tmp_path: Path):
        routes = {
            PDF_8_1_16_1_URL: FakeResponse(
                content_type="text/html",
                body=b"<html>auth bounce</html>",
                url=PDF_8_1_16_1_URL,
            )
        }
        client = _make_client_with_session(FakeSession(routes))
        client._authenticated = True

        with pytest.raises(IOError, match="auth bounce"):
            client.download_pdf(PDF_8_1_16_1_URL, tmp_path / "out.pdf")

    def test_http_error_raises_ioerror(self, tmp_path: Path):
        routes = {
            PDF_8_1_16_1_URL: FakeResponse(
                status_code=403,
                content_type="text/html",
                body=b"forbidden",
                url=PDF_8_1_16_1_URL,
            )
        }
        client = _make_client_with_session(FakeSession(routes))
        client._authenticated = True

        with pytest.raises(IOError, match="HTTP 403"):
            client.download_pdf(PDF_8_1_16_1_URL, tmp_path / "out.pdf")
