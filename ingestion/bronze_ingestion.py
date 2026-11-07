
"""Fetch raw hourly weather and air-quality data for Kerala districts."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import settings
from ingestion.logger import get_logger

logger = get_logger(__name__)

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

WEATHER_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "wind_direction_10m",
    "cloud_cover",
]

AIR_QUALITY_VARIABLES = [
    "pm10",
    "pm2_5",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
    "us_aqi",
    "european_aqi",
]


def create_session() -> requests.Session:
    """Create an HTTP session that retries temporary API failures."""
    retry = Retry(
        total=settings.http_max_retries,
        connect=settings.http_max_retries,
        read=settings.http_max_retries,
        backoff_factor=settings.http_backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "KeralaClimatePulse/1.0"})
    return session


def fetch_json(
    session: requests.Session,
    url: str,
    params: dict[str, object],
) -> dict:
    """Fetch and validate a JSON API response."""
    response = session.get(url, params=params, timeout=(10, 60))
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, dict) or "hourly" not in payload:
        raise ValueError("API response is missing the expected hourly data")

    return payload


def safe_name(value: str) -> str:
    """Convert a district name into a safe folder name."""
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def save_raw_json(
    payload: dict,
    output_path: Path,
    metadata: dict[str, object],
) -> None:
    """Save raw API data and metadata without partial-file writes."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(".json.tmp")

    document = {
        "metadata": metadata,
        "data": payload,
    }

    try:
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(document, file, ensure_ascii=False, indent=2)
        temporary_path.replace(output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def ingest_district(
    session: requests.Session,
    district: dict[str, object],
    run_dir: Path,
    run_id: str,
    extracted_at: str,
) -> int:
    """Fetch and store weather and air-quality data for one district."""
    district_name = str(district["district_name"])
    district_dir = run_dir / safe_name(district_name)

    common_params: dict[str, object] = {
        "latitude": float(district["latitude"]),
        "longitude": float(district["longitude"]),
        "timezone": settings.timezone,
        "forecast_days": 7,
    }

    sources = [
        (
            "weather",
            WEATHER_URL,
            {**common_params, "hourly": ",".join(WEATHER_VARIABLES)},
        ),
        (
            "air_quality",
            AIR_QUALITY_URL,
            {**common_params, "hourly": ",".join(AIR_QUALITY_VARIABLES)},
        ),
    ]

    failures = 0

    for source_name, url, params in sources:
        try:
            payload = fetch_json(session, url, params)
            save_raw_json(
                payload,
                district_dir / f"{source_name}.json",
                metadata={
                    "district_id": int(district["district_id"]),
                    "district_name": district_name,
                    "source": source_name,
                    "run_id": run_id,
                    "extracted_at": extracted_at,
                    "timezone": settings.timezone,
                },
            )
            logger.info(
                "Saved %s data for %s", source_name, district_name
            )
        except (requests.RequestException, ValueError, OSError) as exc:
            failures += 1
            logger.error(
                "Failed %s data for %s: %s",
                source_name,
                district_name,
                exc,
            )

    return failures


def main() -> int:
    """Run Bronze ingestion for all districts in the CSV."""
    csv_path = Path(settings.districts_csv)
    if not csv_path.exists():
        logger.error("District CSV not found: %s", csv_path.resolve())
        return 1

    districts_df = pd.read_csv(csv_path)
    required_columns = {
        "district_id",
        "district_name",
        "latitude",
        "longitude",
    }
    missing = required_columns.difference(districts_df.columns)

    if missing:
        logger.error("District CSV is missing columns: %s", sorted(missing))
        return 1

    if districts_df.empty:
        logger.error("District CSV contains no districts")
        return 1

    if districts_df[list(required_columns)].isnull().any().any():
        logger.error("District CSV contains missing required values")
        return 1

    local_now = datetime.now(ZoneInfo(settings.timezone))
    date_partition = local_now.strftime("%Y-%m-%d")
    extracted_at = local_now.isoformat()
    run_id = local_now.strftime("%Y%m%dT%H%M%S%f")

    run_dir = Path(settings.bronze_dir) / f"date={date_partition}" / f"run_id={run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)

    logger.info(
        "Starting Bronze ingestion for %d districts; run_id=%s",
        len(districts_df),
        run_id,
    )

    failures = 0
    session = create_session()

    try:
        for district in districts_df.to_dict(orient="records"):
            failures += ingest_district(
                session=session,
                district=district,
                run_dir=run_dir,
                run_id=run_id,
                extracted_at=extracted_at,
            )
    finally:
        session.close()

    successful_sources = len(districts_df) * 2 - failures
    logger.info(
        "Bronze run finished: %d districts, %d/%d successful sources, "
        "%d failures. Output: %s",
        len(districts_df),
        successful_sources,
        len(districts_df) * 2,
        failures,
        run_dir.resolve(),
    )

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
