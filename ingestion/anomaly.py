"""anomaly.py – Optional ML step: flag unusual hourly readings per district.

An Isolation Forest is trained per district on observed hours; the most
isolated ~2% of readings are flagged in gold_anomalies.
"""
from __future__ import annotations

import pandas as pd
from sklearn.ensemble import IsolationForest
from sqlalchemy.engine import Engine

from ingestion.db import upsert
from ingestion.logger import get_logger

log = get_logger(__name__)

FEATURES = ["temperature_c", "humidity_pct", "rainfall_mm", "wind_speed_kmh", "pm2_5"]
MIN_ROWS = 48  # need at least two days of hours to say anything useful


def score_frame(df: pd.DataFrame, contamination: float = 0.02) -> pd.DataFrame:
    """Return district_id, observed_at, anomaly_score, is_anomaly for each row."""
    out = []
    for district_id, g in df.groupby("district_id"):
        g = g.dropna(subset=FEATURES)
        if len(g) < MIN_ROWS:
            log.warning("District %s: only %d usable rows, skipping", district_id, len(g))
            continue
        model = IsolationForest(contamination=contamination, random_state=42)
        model.fit(g[FEATURES])
        out.append(
            pd.DataFrame(
                {
                    "district_id": district_id,
                    "observed_at": g["observed_at"].values,
                    # sklearn: lower decision_function = more abnormal; flip so higher = more anomalous
                    "anomaly_score": -model.decision_function(g[FEATURES]),
                    "is_anomaly": model.predict(g[FEATURES]) == -1,
                }
            )
        )
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(
        columns=["district_id", "observed_at", "anomaly_score", "is_anomaly"]
    )


def run_anomaly_detection(engine: Engine) -> int:
    df = pd.read_sql(
        "SELECT district_id, observed_at, temperature_c, humidity_pct, rainfall_mm, "
        "wind_speed_kmh, pm2_5 FROM fact_weather WHERE is_forecast = FALSE",
        engine,
        parse_dates=["observed_at"],
    )
    scored = score_frame(df)
    rows = [
        {
            "district_id": int(r.district_id),
            "observed_at": pd.Timestamp(r.observed_at).to_pydatetime(),
            "anomaly_score": float(r.anomaly_score),
            "is_anomaly": bool(r.is_anomaly),
        }
        for r in scored.itertuples(index=False)
    ]
    n = upsert(engine, "gold_anomalies", rows, ["district_id", "observed_at"])
    log.info("Scored %d rows, %d flagged anomalous", n, int(scored["is_anomaly"].sum()) if n else 0)
    return n
