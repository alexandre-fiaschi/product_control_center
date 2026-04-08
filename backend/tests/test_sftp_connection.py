"""Integration test — connects to real SFTP. Skipped by default."""

import pytest

from app.config import settings
from app.integrations.sftp.connector import SFTPConnector


@pytest.mark.integration
def test_sftp_connection():
    """Verify we can connect and list the root directory."""
    with SFTPConnector(settings) as conn:
        dirs = conn.list_dirs("/")
        assert isinstance(dirs, list)
