"""Integration test — downloads a single patch from real SFTP. Run with:

    cd backend && pytest tests/test_sftp_download.py -v -k integration -s

Requires VPN + SFTP credentials in .env. Skips automatically if SFTP_HOST is not set.
"""

import stat

import pytest

from app.config import settings
from app.integrations.sftp.connector import SFTPConnector
from app.pipelines.binaries.fetcher import download_patch

needs_sftp = pytest.mark.skipif(
    not settings.SFTP_HOST,
    reason="SFTP_HOST not configured — skipping live SFTP test",
)


def _enable_keepalive(conn: SFTPConnector, interval: int = 15) -> None:
    """Set keepalive on the underlying transport to prevent server timeouts."""
    transport = conn.client.get_channel().get_transport()
    if transport:
        transport.set_keepalive(interval)


def _list_recursive(conn: SFTPConnector, path: str, indent: int = 0) -> None:
    """Print remote directory tree with file sizes."""
    entries = conn.client.listdir_attr(path)
    for e in sorted(entries, key=lambda x: x.filename):
        prefix = "  " * indent
        if stat.S_ISDIR(e.st_mode):
            print(f"{prefix}📁 {e.filename}/")
            _list_recursive(conn, f"{path}/{e.filename}", indent + 1)
        else:
            mb = e.st_size / (1024 * 1024)
            print(f"{prefix}📄 {e.filename}  ({mb:.1f} MB)")


@pytest.mark.integration
@needs_sftp
def test_list_patch_contents():
    """Just list what's in the patch folder — no download."""
    sftp_path = "/ACARS_V8_1/ACARS_V8_1_12/8.1.12.0"
    with SFTPConnector(settings) as conn:
        _enable_keepalive(conn)
        print(f"\nContents of {sftp_path}:")
        _list_recursive(conn, sftp_path)


@pytest.mark.integration
@needs_sftp
def test_download_single_patch(tmp_path):
    """Download a known patch folder from SFTP and verify files land on disk."""
    sftp_path = "/ACARS_V8_1/ACARS_V8_1_12/8.1.12.0"
    local_path = str(tmp_path / "8.1.12.0")

    with SFTPConnector(settings) as conn:
        _enable_keepalive(conn)
        count = download_patch(conn, sftp_path, local_path)

    assert count > 0, f"Expected files but got {count}"
    actual_files = [f for f in (tmp_path / "8.1.12.0").rglob("*") if f.is_file()]
    print(f"\nDownloaded {len(actual_files)} files:")
    for f in sorted(actual_files):
        print(f"  {f.relative_to(tmp_path)}")
    assert len(actual_files) == count
