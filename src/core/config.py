from __future__ import annotations

from functools import lru_cache

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """配置缺失或非法。字段名以大写环境变量形式抛出，便于直接照着修。"""

    def __init__(self, fields: list[str]) -> None:
        self.fields = fields
        super().__init__("配置缺失或非法，请检查：" + ", ".join(fields))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "dev"
    log_level: str = "info"

    # 必填：没有数据库路径就不允许启动
    database_path: str
    data_dir: str = "./data"

    max_upload_mb: int = Field(default=50, gt=0)
    max_pages: int = Field(default=400, gt=0)
    max_filings_per_session: int = Field(default=5, ge=1, le=20)

    align_confidence_threshold: float = Field(default=0.85, ge=0, le=1)
    request_timeout_seconds: int = Field(default=600, gt=0)


def _missing_fields(exc: ValidationError) -> list[str]:
    names: set[str] = set()
    for error in exc.errors():
        loc = error.get("loc") or ()
        if loc:
            names.add(str(loc[0]).upper())
    return sorted(names)


def load_settings(**overrides: object) -> Settings:
    """加载配置。overrides 可传 `_env_file=None` 以便测试完全脱离 .env。"""
    try:
        return Settings(**overrides)  # type: ignore[arg-type]
    except ValidationError as exc:
        raise ConfigError(_missing_fields(exc)) from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
