"""ingest.py – Bronze layer: pull raw Open-Meteo JSON and store it by date.

Raw responses are never modified. Re-running on the same day overwrites the
same files, so ingestion is idempotent.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from config import settings
from ingestion.constants import (
    AIR_HOURLY,
    AIR_QUALITY_URL,
    UNIT_PARAMS,
    WEATHER_HOURLY,
    WEATHER_URL,
)
from ingestion.logger import get_logger
from ingestion.timeutil import now_local

log = get_logger(__name__)


class TransientHTTPError(Exception):
    """Raised for 429 / 5xx responses so they are retried."""


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(
        exc, (TransientHTTPError, requests.ConnectionError, requests.Timeout)
    )


def fetch_json(
    url: str,
    params: dict,
    *,
    session: requests.Session | None = None,
    max_retries: int | None = None,
    backoff_factor: float | None = None,
    timeout: int = 30,
) -> dict:
    """GET a JSON document with exponential-backoff retries on transient errors."""
    session = session or requests.Session()
    attempts = max_retries if max_retries is not None else settings.http_max_retries
    backoff = backoff_factor if backoff_factor is not None else settings.http_backoff_factor

    def _log_retry(state) -> None:
        log.warning(
            "Retry %d/%d for %s after %s", state.attempt_number, attempts, url, state.outcome.exception()
        )

    for attempt in Retrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=backoff, min=0, max=30),
        retry=retry_if_exception(_is_retryable),
        before_sleep=_log_retry,
        reraise=True,
    ):
        with attempt:
            resp = session.get(url, params=params, timeout=timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise TransientHTTPError(f"HTTP {resp.status_code} from {url}")
            resp.raise_for_status()
            return resp.json()
    raise RuntimeError("unreachable")  # pragma: no cover


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def bronze_path(bronze_dir: Path, run_date: date, district_name: str, kind: str) -> Path:
    return Path(bronze_dir) / run_date.isoformat() / f"{slugify(district_name)}_{kind}.json"


def save_bronze(path: Path, payload: dict, meta: dict) -> Path:
    """Atomically write {_meta, payload} so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"_meta": meta, "payload": payload}), encoding="utf-8")
    os.replace(tmp, path)
    return path


@dataclass
class IngestResult:
    saved: list[Path] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def _params(row: pd.Series, hourly: list[str], past_days: int) -> dict:
    return {
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "hourly": ",".join(hourly),
        "past_days": past_days,
        "forecast_days": 1,
        "timezone": settings.timezone,
        **(UNIT_PARAMS if hourly is WEATHER_HOURLY else {}),
    }


def ingest_all(
    run_date: date | None = None,
    districts: pd.DataFrame | None = None,
    *,
    session: requests.Session | None = None,
    bronze_dir: Path | None = None,
    past_days: int | None = None,
    max_retries: int | None = None,
    backoff_factor: float | None = None,
) -> IngestResult:
    """Fetch weather and air quality for every district into the bronze layer.

    One failing district never stops the others; failures are returned so the
    quality checks (district coverage) can decide whether to abort.
    """
    districts = districts if districts is not None else pd.read_csv(settings.districts_csv)
    run_date = run_date or now_local().date()
    bronze_dir = Path(bronze_dir or settings.bronze_dir)
    past_days = past_days if past_days is not None else settings.backfill_days
    session = session or requests.Session()
    result = IngestResult()

    sources = [
        ("weather", WEATHER_URL, WEATHER_HOURLY),
        ("air_quality", AIR_QUALITY_URL, AIR_HOURLY),
    ]
    for _, row in districts.iterrows():
        for kind, url, hourly in sources:
            label = f"{row['district_name']}/{kind}"
            try:
                payload = fetch_json(
                    url,
                    _params(row, hourly, past_days),
                    session=session,
                    max_retries=max_retries,
                    backoff_factor=backoff_factor,
                )
                meta = {
                    "district_id": int(row["district_id"]),
                    "district_name": row["district_name"],
                    "kind": kind,
                    "source_url": url,
                    "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                }
                path = bronze_path(bronze_dir, run_date, row["district_name"], kind)
                result.saved.append(save_bronze(path, payload, meta))
                log.info("Saved %s", path)
            except Exception as exc:  # noqa: BLE001 - keep going, report at the end
                log.error("Failed %s: %s", label, exc)
                result.failures.append(label)
    log.info("Ingestion done: %d files saved, %d failures", len(result.saved), len(result.failures))
    return result
