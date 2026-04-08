"""SFTP connection management via paramiko."""

import logging
import os
import stat
from types import TracebackType

import paramiko

from app.config import Settings

logger = logging.getLogger("sftp.connector")


class SFTPConnector:
    """Context manager for SFTP connections."""

    def __init__(self, sftp_settings: Settings) -> None:
        self._host = sftp_settings.SFTP_HOST
        self._port = sftp_settings.SFTP_PORT
        self._username = sftp_settings.SFTP_USERNAME
        self._password = sftp_settings.SFTP_PASSWORD
        self._key_path = sftp_settings.SFTP_KEY_PATH
        self._transport: paramiko.Transport | None = None
        self._sftp: paramiko.SFTPClient | None = None

    def __enter__(self) -> "SFTPConnector":
        logger.info("Connecting to SFTP %s:%d as %s", self._host, self._port, self._username)
        try:
            self._transport = paramiko.Transport((self._host, self._port))
            if self._key_path:
                key_path = os.path.expanduser(self._key_path)
                pkey = paramiko.RSAKey.from_private_key_file(key_path)
                self._transport.connect(username=self._username, pkey=pkey)
            else:
                self._transport.connect(username=self._username, password=self._password)
            self._sftp = paramiko.SFTPClient.from_transport(self._transport)
            logger.info("SFTP connection established")
        except Exception:
            logger.error("Failed to connect to SFTP %s:%d", self._host, self._port, exc_info=True)
            self.close()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._sftp:
            self._sftp.close()
            self._sftp = None
        if self._transport:
            self._transport.close()
            self._transport = None
        logger.info("SFTP connection closed")

    @property
    def client(self) -> paramiko.SFTPClient:
        if self._sftp is None:
            raise RuntimeError("SFTP not connected")
        return self._sftp

    def list_dirs(self, path: str) -> list[str]:
        """Return sorted directory names under path. Empty list if path doesn't exist."""
        dirs: list[str] = []
        try:
            for entry in sorted(self.client.listdir_attr(path), key=lambda e: e.filename):
                if stat.S_ISDIR(entry.st_mode):
                    dirs.append(entry.filename)
        except IOError:
            logger.debug("Cannot list %s (path may not exist)", path)
        logger.debug("list_dirs(%s) -> %d entries", path, len(dirs))
        return dirs
