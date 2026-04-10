"""Download patch folder contents from SFTP."""

import logging
import stat
from pathlib import Path

from app.integrations.sftp.connector import SFTPConnector

logger = logging.getLogger("pipelines.binaries.fetcher")


def download_patch(
    conn: SFTPConnector,
    sftp_path: str,
    local_path: str,
    *,
    product_id: str,
    version: str,
) -> int:
    """Recursively download all files from sftp_path to local_path.

    Returns the number of files downloaded. Raises IOError if the remote
    directory cannot be listed (the caller is expected to handle the failure).
    """
    local = Path(local_path)
    local.mkdir(parents=True, exist_ok=True)
    logger.info(
        "binaries.download.start product=%s version=%s sftp=%s local=%s",
        product_id, version, sftp_path, local_path,
    )

    count = _download_recursive(conn, sftp_path, local)
    logger.info(
        "binaries.download.success product=%s version=%s files=%d",
        product_id, version, count,
    )
    return count


def _download_recursive(conn: SFTPConnector, remote_dir: str, local_dir: Path) -> int:
    """Walk remote directory tree and download all files."""
    count = 0
    entries = conn.client.listdir_attr(remote_dir)

    for entry in sorted(entries, key=lambda e: e.filename):
        remote_path = f"{remote_dir}/{entry.filename}"
        local_path = local_dir / entry.filename

        if stat.S_ISDIR(entry.st_mode):
            local_path.mkdir(parents=True, exist_ok=True)
            count += _download_recursive(conn, remote_path, local_path)
        else:
            conn.client.get(remote_path, str(local_path))
            count += 1
            logger.debug("binaries.download.file remote=%s", remote_path)

    return count
