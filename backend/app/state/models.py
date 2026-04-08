from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BinariesState(BaseModel):
    status: Literal["discovered", "downloaded", "pending_approval", "approved", "published"] = "discovered"
    discovered_at: datetime | None = None
    downloaded_at: datetime | None = None
    approved_at: datetime | None = None
    published_at: datetime | None = None
    jira_ticket_key: str | None = None
    jira_ticket_url: str | None = None


class ReleaseNotesState(BaseModel):
    status: Literal["not_started", "discovered", "downloaded", "converted", "pending_approval", "approved", "pdf_exported", "published"] = "not_started"
    discovered_at: datetime | None = None
    downloaded_at: datetime | None = None
    converted_at: datetime | None = None
    approved_at: datetime | None = None
    published_at: datetime | None = None
    pdf_exported_at: datetime | None = None
    jira_ticket_key: str | None = None
    jira_ticket_url: str | None = None


class PatchEntry(BaseModel):
    sftp_folder: str
    sftp_path: str
    local_path: str
    binaries: BinariesState
    release_notes: ReleaseNotesState


class VersionData(BaseModel):
    patches: dict[str, PatchEntry] = {}


class ProductTracker(BaseModel):
    product_id: str
    last_scanned_at: datetime | None = None
    versions: dict[str, VersionData] = {}
