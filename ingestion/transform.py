"""transform.py – Silver layer: bronze JSON -> one clean, typed hourly table.

Steps: parse -> merge weather + air quality -> type coercion -> IST
standardisation -> de-duplication -> derived columns (date, hour, forecast flag).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from ingestion.constants import COLUMN_MAP, IST_OFFSET_SECONDS, MEASURE_COLUMNS
from ingestion.ingest import bronze_path
from ingestion.logger import get_logger
from ingestion.timeutil import now_local

log = get_logger(__name__)

SILVER_COLUMNS = [
    "district_id",
    "observed_at",
    "observed_date",
    "observed_hour",
    *MEASURE_COLUMNS,
    "is_forecast",
]


def payload_to_frame(doc: dict, district_id: int) -> pd.DataFrame:
    """Turn one bronze document into a tidy frame in IST."""
    payload = doc["payload"]
    hourly = payload.get("hourly")
    if not hourly or "time" not in hourly:
        raise ValueError(f"district {district_id}: payload has no hourly block")

    df = pd.DataFrame(hourly).rename(columns={"time": "observed_at", **COLUMN_MAP})
    df["observed_at"] = pd.to_datetime(df["observed_at"], errors="coerce")
    # Normalise to IST if the API ever answers in another offset.
    offset = int(payload.get("utc_offset_seconds", IST_OFFSET_SECONDS))
    if offset != IST_OFFSET_SECONDS:
        df["observed_at"] += pd.Timedelta(seconds=IST_OFFSET_SECONDS - offset)
    df.insert(0, "district_id", district_id)
    return df


def load_district_frames(
    bronze_dir: Path, run_date: date, districts: pd.DataFrame
) -> list[pd.DataFrame]:
    """Read weather + air-quality files per district and merge them on time."""
    frames: list[pd.DataFrame] = []
    for _, row in districts.iterrows():
        parts = []
        for kind in ("weather", "air_quality"):
            path = bronze_path(bronze_dir, run_date, row["district_name"], kind)
            if not path.exists():
                log.warning("Missing bronze file %s", path)
                continue
            try:
                parts.append(
                    payload_to_frame(json.loads(path.read_text("utf-8")), int(row["district_id"]))
                )
            except (ValueError, json.JSONDecodeError) as exc:
                log.error("Skipping unreadable %s: %s", path, exc)
        if not parts:
            continue
        merged = parts[0]
        for extra in parts[1:]:
            merged = merged.merge(extra, on=["district_id", "observed_at"], how="outer")
        frames.append(merged)
    return frames


def clean(df: pd.DataFrame, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Type, de-duplicate and enrich the merged frame (no value clipping here)."""
    now = now if now is not None else now_local()
    if df.empty:
        return pd.DataFrame(columns=SILVER_COLUMNS)

    df = df.copy()
    for col in MEASURE_COLUMNS:
        if col not in df:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce").round(2)

    df = df.dropna(subset=["observed_at"]).copy()
    df["district_id"] = df["district_id"].astype(int)

    before = len(df)
    df = df.drop_duplicates(subset=["district_id", "observed_at"], keep="last")
    if before - len(df):
        log.info("Removed %d duplicate (district, hour) rows", before - len(df))

    df["observed_date"] = df["observed_at"].dt.date
    df["observed_hour"] = df["observed_at"].dt.hour.astype(int)
    df["is_forecast"] = df["observed_at"] > now.floor("h")
    return (
        df[SILVER_COLUMNS]
        .sort_values(["district_id", "observed_at"])
        .reset_index(drop=True)
    )


def build_silver_frame(
    bronze_dir: Path,
    run_date: date,
    districts: pd.DataFrame,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    frames = load_district_frames(Path(bronze_dir), run_date, districts)
    if not frames:
        return clean(pd.DataFrame(), now)
    return clean(pd.concat(frames, ignore_index=True), now)
