import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.state.models import (
    BinariesState,
    PatchEntry,
    ProductTracker,
    ReleaseNotesState,
    VersionData,
)


def pytest_addoption(parser):
    parser.addoption(
        "--pdf",
        action="store",
        default=None,
        help="Path to a PDF file for the reference PDF-extraction tests",
    )
    parser.addoption(
        "--pdf-output",
        action="store",
        default=None,
        help="Persistent output dir for the PDF benchmark (default: tmp dir)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "reference: reference-only tests, skipped by default (run with -m reference)",
    )


@pytest.fixture
def tmp_state_dir(tmp_path):
    state_dir = tmp_path / "state" / "patches"
    state_dir.mkdir(parents=True)
    return state_dir


@pytest.fixture
def sample_tracker():
    return ProductTracker(
        product_id="ACARS_V8_1",
        last_scanned_at="2026-04-03T17:04:35.873201+00:00",
        versions={
            "8.1.0": VersionData(
                patches={
                    "8.1.0.0": PatchEntry(
                        sftp_folder="v8.1.0.0",
                        sftp_path="/ACARS_V8_1/ACARS_V8_1_0/v8.1.0.0",
                        local_path="patches/ACARS_V8_1/8.1.0.0",
                        binaries=BinariesState(
                            status="pending_approval",
                            discovered_at="2026-04-03T17:01:11.127980+00:00",
                            downloaded_at="2026-04-03T17:01:12.668255+00:00",
                        ),
                        release_notes=ReleaseNotesState(
                            status="published",
                            published_at="2026-01-28T00:00:00+00:00",
                        ),
                    )
                }
            )
        },
    )


@pytest.fixture
def sample_tracker_json():
    return {
        "product_id": "ACARS_V8_1",
        "last_scanned_at": "2026-04-03T17:04:35.873201+00:00",
        "versions": {
            "8.1.0": {
                "patches": {
                    "8.1.0.0": {
                        "sftp_folder": "v8.1.0.0",
                        "sftp_path": "/ACARS_V8_1/ACARS_V8_1_0/v8.1.0.0",
                        "local_path": "patches/ACARS_V8_1/8.1.0.0",
                        "binaries": {
                            "status": "pending_approval",
                            "discovered_at": "2026-04-03T17:01:11.127980+00:00",
                            "downloaded_at": "2026-04-03T17:01:12.668255+00:00",
                            "approved_at": None,
                            "published_at": None,
                            "jira_ticket_key": None,
                            "jira_ticket_url": None,
                        },
                        "release_notes": {
                            "status": "published",
                            "discovered_at": None,
                            "downloaded_at": None,
                            "converted_at": None,
                            "approved_at": None,
                            "published_at": "2026-01-28T00:00:00+00:00",
                            "pdf_exported_at": None,
                            "jira_ticket_key": None,
                            "jira_ticket_url": None,
                        },
                    }
                }
            }
        },
    }


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def tracker_json_file(tmp_state_dir, sample_tracker_json):
    path = tmp_state_dir / "ACARS_V8_1.json"
    with open(path, "w") as f:
        json.dump(sample_tracker_json, f, indent=2)
    return path
