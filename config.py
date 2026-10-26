"""
config.py – Central configuration loaded from environment variables / .env file.

All other modules import settings from here; nothing is hardcoded.
"""
from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings resolved from .env or environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── PostgreSQL ─────────────────────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "kerala_climate"
    postgres_user: str = "kerala_user"
    postgres_password: str = "changeme"

    @property
    def database_url(self) -> str:
        """SQLAlchemy-compatible connection string."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── Ingestion ──────────────────────────────────────────────────────────────
    bronze_dir: Path = Path("data/bronze")
    districts_csv: Path = Path("districts.csv")
    backfill_days: int = 7
    http_max_retries: int = 3
    http_backoff_factor: int = 2

    # ── API ────────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False

    # ── Timezone ───────────────────────────────────────────────────────────────
    timezone: str = "Asia/Kolkata"

    # ── Optional LLM ──────────────────────────────────────────────────────────
    openai_api_key: str = ""
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""


# Singleton – import `settings` everywhere
settings = Settings()
