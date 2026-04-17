from datetime import datetime
from typing import Literal

from pydantic import BaseModel


# Workflow status (the Literal on BinariesState/ReleaseNotesState) describes where a
# track is in the business process. Execution outcomes — including failures — live on
# LastRun, never on workflow status. Do not add "failed" or "error" values to either
# status Literal. See PLAN_DOCS_PIPELINE.md §3.
class LastRun(BaseModel):
    state: Literal["idle", "running", "success", "failed"] = "idle"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    step: str | None = None
    error: str | None = None


class BinariesState(BaseModel):
    status: Literal["discovered", "downloaded", "pending_approval", "approved", "published"] = "discovered"
    discovered_at: datetime | None = None
    downloaded_at: datetime | None = None
    approved_at: datetime | None = None
    published_at: datetime | None = None
    jira_ticket_key: str | None = None
    jira_ticket_url: str | None = None
    last_run: LastRun = LastRun()


class ReleaseNotesState(BaseModel):
    status: Literal["not_started", "downloaded", "extracted", "converted", "pending_approval", "approved", "pdf_exported", "published", "not_found"] = "not_started"
    downloaded_at: datetime | None = None
    extracted_at: datetime | None = None
    converted_at: datetime | None = None
    approved_at: datetime | None = None
    published_at: datetime | None = None
    pdf_exported_at: datetime | None = None
    jira_ticket_key: str | None = None
    jira_ticket_url: str | None = None
    source_pdf_path: str | None = None
    source_url: str | None = None
    record_json_path: str | None = None
    generated_docx_path: str | None = None
    not_found_reason: Literal["no_match", "ambiguous_match"] | None = None
    last_run: LastRun = LastRun()


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


class ScanRecord(BaseModel):
    scan_id: str
    trigger: Literal["cron", "manual", "targeted", "bulk_docs"]
    started_at: datetime
    finished_at: datetime | None = None
    products: list[str] = []
    counts: dict[str, int] = {}
    duration_ms: int | None = None
