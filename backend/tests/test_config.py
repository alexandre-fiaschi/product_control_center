from app.config import Settings, PROJECT_ROOT


def test_config_loads_env():
    s = Settings()
    assert s.JIRA_BASE_URL == "https://caeglobal.atlassian.net"
    assert s.JIRA_PROJECT_KEY == "CFSSOCP"


def test_config_loads_pipeline_json():
    s = Settings()
    assert "pipeline" in s.pipeline_config
    products = s.pipeline_config["pipeline"]["products"]
    assert "ACARS_V8_1" in products
    assert "ACARS_V8_0" in products
    assert "ACARS_V7_3" in products


def test_config_paths():
    s = Settings()
    assert s.state_dir == PROJECT_ROOT / "state" / "patches"
    assert s.patches_dir == PROJECT_ROOT / "patches"
    assert s.state_dir.exists()


def test_config_sftp_defaults():
    s = Settings()
    assert s.SFTP_PORT == 22
