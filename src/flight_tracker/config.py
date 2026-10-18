"""Static configuration loaded from environment variables / the ``.env`` file.

Secrets (API keys, tokens, SMTP passwords) live here. User-editable runtime
settings (scan interval, thresholds...) are stored in the database instead -
see :class:`flight_tracker.models.AppSettings`.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR: Path = Path(__file__).resolve().parent
PROJECT_ROOT: Path = PACKAGE_DIR.parent.parent
STATIC_DIR: Path = PACKAGE_DIR / "static"


class ProviderName(StrEnum):
    MOCK = "mock"
    SERPAPI = "serpapi"
    DUFFEL = "duffel"
    TRAVELPAYOUTS = "travelpayouts"


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- general
    flight_provider: ProviderName = ProviderName.MOCK
    origin_airport: str = Field(default="TLV", min_length=3, max_length=3)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    http_timeout_seconds: float = Field(default=40.0, gt=0)
    data_dir: Path = PROJECT_ROOT / "data"

    # --- data providers
    serpapi_api_key: SecretStr = SecretStr("")
    duffel_access_token: SecretStr = SecretStr("")
    travelpayouts_token: SecretStr = SecretStr("")

    # --- telegram
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""

    # --- email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    email_from: str = ""
    email_to: str = ""

    @field_validator("origin_airport", "currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "flights.db"

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token.get_secret_value() and self.telegram_chat_id)

    @property
    def email_configured(self) -> bool:
        return bool(
            self.smtp_host and self.smtp_user and self.smtp_password.get_secret_value() and self.email_to
        )


@lru_cache(maxsize=1)
def get_config() -> Config:
    config = Config()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    return config
