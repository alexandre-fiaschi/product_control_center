"""Tests for app.pipelines.docs.fetcher.fetch_release_notes.

Uses a fake ZendeskClient that returns canned results, so we exercise the
state-machine transitions in isolation from HTTP. The fetcher's contract is
in PLAN_DOCS_PIPELINE.md §2 Block A and §3.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.integrations.zendesk import (
    ArticleMatch,
    ZendeskAmbiguous,
    ZendeskAuthError,
    ZendeskNotFound,
)
from app.pipelines.docs.fetcher import fetch_release_notes
from app.services.lifecycle import run_cell
from app.state.models import (
    BinariesState,
    PatchEntry,
    ReleaseNotesState,
)


class FakeClient:
    def __init__(
        self,
        *,
        find_result: ArticleMatch | None = None,
        find_exc: Exception | None = None,
        download_exc: Exception | None = None,
    ):
        self.find_result = find_result
        self.find_exc = find_exc
        self.download_exc = download_exc
        self.download_calls: list[tuple[str, Path]] = []

    def find_article_for_version(self, version: str) -> ArticleMatch:
        if self.find_exc is not None:
            raise self.find_exc
        assert self.find_result is not None
        return self.find_result

    def download_pdf(self, pdf_url: str, dest_path: Path) -> int:
        self.download_calls.append((pdf_url, dest_path))
        if self.download_exc is not None:
            raise self.download_exc
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(b"%PDF-fake")
        return len(b"%PDF-fake")


def _new_patch() -> PatchEntry:
    return PatchEntry(
        sftp_folder="v8.1.16.1",
        sftp_path="/ACARS_V8_1/ACARS_V8_1_16/v8.1.16.1",
        local_path="patches/ACARS_V8_1/8.1.16.1",
        binaries=BinariesState(status="pending_approval"),
        release_notes=ReleaseNotesState(status="not_started"),
    )


class TestFetchReleaseNotes:
    def test_happy_path_transitions_to_downloaded(self, tmp_path: Path):
        match = ArticleMatch(
            title="8.1.16.1 - Release Notes",
            article_url="https://example.zendesk.com/hc/en-gb/articles/8001",
            pdf_filename="8.1.16.1 - Release Notes.pdf",
            pdf_url="https://example.zendesk.com/hc/article_attachments/9001",
        )
        client = FakeClient(find_result=match)
        patch = _new_patch()

        fetch_release_notes(
            client, patch,
            product_id="ACARS_V8_1",
            version="8.1.16.1",
            dest_dir=tmp_path / "release_notes",
        )

        # Single transition: not_started → downloaded. source_url and
        # source_pdf_path are both set together at the end of the happy path.
        assert patch.release_notes.status == "downloaded"
        assert patch.release_notes.downloaded_at is not None
        assert patch.release_notes.source_url == match.article_url
        assert patch.release_notes.source_pdf_path is not None
        assert Path(patch.release_notes.source_pdf_path).exists()

    def test_not_found_no_match_sets_reason(self, tmp_path: Path, caplog):
        client = FakeClient(find_exc=ZendeskNotFound("nope"))
        patch = _new_patch()

        with caplog.at_level(logging.INFO, logger="pipelines.docs.fetcher"):
            fetch_release_notes(
                client, patch,
                product_id="ACARS_V8_1",
                version="8.1.99.99",
                dest_dir=tmp_path / "release_notes",
            )

        assert patch.release_notes.status == "not_found"
        assert patch.release_notes.not_found_reason == "no_match"
        assert patch.release_notes.downloaded_at is None
        assert patch.release_notes.source_pdf_path is None
        assert any("zendesk.fetch.no_match" in r.message for r in caplog.records)
        assert client.download_calls == []

    def test_ambiguous_sets_not_found_reason_and_log(
        self, tmp_path: Path, caplog,
    ):
        candidates = [
            ArticleMatch("a", "u1", "a.pdf", "p1"),
            ArticleMatch("b", "u2", "b.pdf", "p2"),
        ]
        client = FakeClient(find_exc=ZendeskAmbiguous("8.1.16.1", candidates))
        patch = _new_patch()

        with caplog.at_level(logging.WARNING, logger="pipelines.docs.fetcher"):
            fetch_release_notes(
                client, patch,
                product_id="ACARS_V8_1",
                version="8.1.16.1",
                dest_dir=tmp_path / "release_notes",
            )

        assert patch.release_notes.status == "not_found"
        assert patch.release_notes.not_found_reason == "ambiguous_match"
        assert any(
            "zendesk.fetch.ambiguous_match" in r.message for r in caplog.records
        )

    def test_auth_error_propagates(self, tmp_path: Path):
        client = FakeClient(find_exc=ZendeskAuthError("login broke"))
        patch = _new_patch()

        with pytest.raises(ZendeskAuthError):
            fetch_release_notes(
                client, patch,
                product_id="ACARS_V8_1",
                version="8.1.16.1",
                dest_dir=tmp_path / "release_notes",
            )
        # Workflow status MUST stay not_started — exceptions never advance it.
        assert patch.release_notes.status == "not_started"

    def test_download_failure_propagates_workflow_unchanged(self, tmp_path: Path):
        match = ArticleMatch(
            title="8.1.16.1 - Release Notes",
            article_url="https://example.zendesk.com/hc/en-gb/articles/8001",
            pdf_filename="8.1.16.1 - Release Notes.pdf",
            pdf_url="https://example.zendesk.com/hc/article_attachments/9001",
        )
        client = FakeClient(find_result=match, download_exc=IOError("HTTP 500"))
        patch = _new_patch()

        with pytest.raises(IOError):
            fetch_release_notes(
                client, patch,
                product_id="ACARS_V8_1",
                version="8.1.16.1",
                dest_dir=tmp_path / "release_notes",
            )
        # The download crashed before the success path could set status =
        # "downloaded" or any of source_url / source_pdf_path. Workflow status
        # stays at not_started so the next scan retries the whole fetch — the
        # PDF download was the failure mode and is exactly what we want to
        # retry (likely transient). No partial state to clean up.
        assert patch.release_notes.status == "not_started"
        assert patch.release_notes.source_url is None
        assert patch.release_notes.source_pdf_path is None


class TestFetchInsideRunCell:
    def test_run_cell_records_failure_on_exception(self, tmp_path: Path):
        client = FakeClient(find_exc=ZendeskAuthError("cloudflare blocked"))
        patch = _new_patch()

        ok = run_cell(
            patch.release_notes,
            lambda: fetch_release_notes(
                client, patch,
                product_id="ACARS_V8_1",
                version="8.1.16.1",
                dest_dir=tmp_path / "release_notes",
            ),
            step_name="fetch_release_notes",
            product="ACARS_V8_1",
            version="8.1.16.1",
        )

        assert ok is False
        assert patch.release_notes.last_run.state == "failed"
        assert patch.release_notes.last_run.step == "fetch_release_notes"
        assert "cloudflare" in patch.release_notes.last_run.error
        # Workflow status untouched
        assert patch.release_notes.status == "not_started"

    def test_run_cell_records_success_on_clean_negative(self, tmp_path: Path):
        client = FakeClient(find_exc=ZendeskNotFound("not yet published"))
        patch = _new_patch()

        ok = run_cell(
            patch.release_notes,
            lambda: fetch_release_notes(
                client, patch,
                product_id="ACARS_V8_1",
                version="8.1.99.99",
                dest_dir=tmp_path / "release_notes",
            ),
            step_name="fetch_release_notes",
            product="ACARS_V8_1",
            version="8.1.99.99",
        )

        assert ok is True
        assert patch.release_notes.last_run.state == "success"
        assert patch.release_notes.status == "not_found"
