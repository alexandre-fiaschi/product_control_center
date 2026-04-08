"""Zip patch folders and upload them to Jira tickets."""

import io
import logging
import zipfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("jira.attachment")


def zip_patch_folder(local_path: str | Path, patch_id: str) -> bytes:
    """Zip all files in *local_path* into an in-memory archive and return the bytes."""
    local_path = Path(local_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(local_path.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(local_path))
    buf.seek(0)
    logger.info("Zipped %s → %d bytes", patch_id, buf.getbuffer().nbytes)
    return buf.read()


def upload_attachment(jira_client: Any, ticket_key: str, patch_id: str, zip_bytes: bytes) -> dict:
    """Upload a zip archive to a Jira ticket as an attachment."""
    filename = f"{patch_id}.zip"
    logger.info("Uploading %s (%d bytes) to %s", filename, len(zip_bytes), ticket_key)
    return jira_client.add_attachment(ticket_key, filename, zip_bytes)
