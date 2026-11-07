
"""
Central configuration loaded from environment variables / .env file.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database configuration
    database_url_env: str = Field(
        default="",
        validation_alias="DATABASE_URL",
    )

    # Local PostgreSQL fallback
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "kerala_climate"
    postgres_user: str = "kerala_user"
    postgres_password: str = Field(
        default="",
        repr=False,
    )

    @property
    def database_url(self) -> str:
        """Use Neon when configured; otherwise use local PostgreSQL."""

        url = os.getenv("DATABASE_URL") or self.database_url_env

        if url:
            url = url.strip()

            if url.startswith("postgres://"):
                url = url.replace(
                    "postgres://",
                    "postgresql+psycopg2://",
                    1,
                )
            elif url.startswith("postgresql://"):
                url = url.replace(
                    "postgresql://",
                    "postgresql+psycopg2://",
                    1,
                )

            return url

        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)

        return (
            f"postgresql+psycopg2://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Ingestion
    bronze_dir: Path = Path("data/bronze")
    districts_csv: Path = Path("districts.csv")
    backfill_days: int = 7
    http_max_retries: int = 3
    http_backoff_factor: int = 2

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False

    # Timezone
    timezone: str = "Asia/Kolkata"

    # Optional LLM
    openai_api_key: str = ""
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""


settings = Settings()
