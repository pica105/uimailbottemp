"""Central configuration for MailHub backend.

All values are loaded from environment variables / .env file and validated
at import time. Missing critical values (BOT_TOKEN, ENCRYPTION_KEY) abort
startup with a clear message.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
# The .env file lives next to the package (mailhub/.env), matching the
# README setup: `cd mailhub && cp .env.example .env`.
PACKAGE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Application settings, validated from environment variables."""

    model_config = SettingsConfigDict(
        env_file=PACKAGE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Telegram -------------------------------------------------------
    BOT_TOKEN: str
    MINI_APP_URL: str = "https://mailhub.vercel.app"

    # --- Network --------------------------------------------------------
    # Public base URL of the backend (used to build OAuth redirect URIs).
    BASE_URL: str = "http://localhost:8080"
    HOST: str = "0.0.0.0"
    PORT: int = 8080

    # --- Encryption -----------------------------------------------------
    ENCRYPTION_KEY: str

    # --- OAuth credentials ---------------------------------------------
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    YANDEX_CLIENT_ID: str = ""
    YANDEX_CLIENT_SECRET: str = ""

    # --- Storage --------------------------------------------------------
    DB_PATH: Path = BASE_DIR / "mailhub.db"

    # --- Sync engine ----------------------------------------------------
    # Engine loop tick: how often the sync loop wakes up and checks accounts.
    SYNC_BASE_INTERVAL_SECONDS: int = 5
    SYNC_ERROR_MAX_BACKOFF_SECONDS: int = 3600
    OAUTH_STATE_TTL_SECONDS: int = 600
    GMAIL_HISTORY_PAGE_SIZE: int = 100

    # --- Heuristic classification --------------------------------------
    # Small blacklists used by classifier.py for Yandex/IMAP messages.
    SPAM_DOMAINS: tuple[str, ...] = (
        "marketing@",
        "newsletter@",
        "mailer@",
        "noreply@",
        "no-reply@",
        "donotreply@",
        "info@",
        "promo@",
    )
    SPAM_KEYWORDS: tuple[str, ...] = (
        "unsubscribe",
        "специальное предложение",
        "скидка",
        "discount",
        "promotion",
        "выиграйте",
        "win a",
        "congratulations you",
        "free gift",
        "act now",
    )

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def _validate_encryption_key(cls, value: str) -> str:
        """Ensure the key is a valid Fernet key (urlsafe base64, 32 bytes)."""
        try:
            decoded = base64.urlsafe_b64decode(value.encode("ascii"))
        except Exception as exc:  # noqa: BLE001 - any malformed input is invalid
            raise ValueError(
                "ENCRYPTION_KEY is not a valid base64 string. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            ) from exc
        if len(decoded) != 32:
            raise ValueError(
                "ENCRYPTION_KEY must decode to exactly 32 bytes (a Fernet key)."
            )
        return value

    @field_validator("BOT_TOKEN")
    @classmethod
    def _validate_bot_token(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("BOT_TOKEN must not be empty.")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (read once at startup)."""
    return Settings()


settings = get_settings()
