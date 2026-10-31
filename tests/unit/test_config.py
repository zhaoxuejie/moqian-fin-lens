import pytest

from core.config import ConfigError, Settings, load_settings


def test_requires_database_path(monkeypatch):
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    with pytest.raises(ConfigError) as exc_info:
        load_settings(_env_file=None)
    assert "DATABASE_PATH" in exc_info.value.fields


def test_reads_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "x.db"))
    settings = load_settings(_env_file=None)
    assert settings.database_path.endswith("x.db")


def test_defaults_are_applied():
    settings = Settings(database_path="./data/app.db", _env_file=None)
    assert settings.app_env == "dev"
    assert settings.log_level == "info"
    assert settings.max_upload_mb == 50
    assert settings.max_pages == 400
    assert settings.max_filings_per_session == 5
    assert settings.align_confidence_threshold == 0.85


def test_invalid_value_is_reported_as_field(monkeypatch):
    monkeypatch.setenv("ALIGN_CONFIDENCE_THRESHOLD", "2")
    with pytest.raises(ConfigError) as exc_info:
        load_settings(_env_file=None, database_path="./data/app.db")
    assert "ALIGN_CONFIDENCE_THRESHOLD" in exc_info.value.fields


def test_config_error_message_lists_fields():
    error = ConfigError(["DATABASE_PATH"])
    assert "DATABASE_PATH" in str(error)
