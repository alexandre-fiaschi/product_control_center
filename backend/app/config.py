import json
from pathlib import Path
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # SFTP
    SFTP_HOST: str = ""
    SFTP_PORT: int = 22
    SFTP_USERNAME: str = ""
    SFTP_PASSWORD: str = ""
    SFTP_KEY_PATH: str = ""

    # Jira
    JIRA_BASE_URL: str = ""
    JIRA_EMAIL: str = ""
    JIRA_API_TOKEN_NO_SCOPES: str = ""
    JIRA_PROJECT_KEY: str = ""

    # Loaded from pipeline.json
    pipeline_config: dict[str, Any] = {}

    @model_validator(mode="after")
    def load_pipeline_config(self) -> "Settings":
        config_path = PROJECT_ROOT / "config" / "pipeline.json"
        if config_path.exists():
            with open(config_path) as f:
                self.pipeline_config = json.load(f)
        return self

    @property
    def state_dir(self) -> Path:
        return PROJECT_ROOT / "state" / "patches"

    @property
    def patches_dir(self) -> Path:
        return PROJECT_ROOT / "patches"


settings = Settings()
