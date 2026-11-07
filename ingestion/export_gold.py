"""export_gold.py – Dump gold views to CSV for Power BI (no DB driver needed)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy.engine import Engine

from ingestion.logger import get_logger

log = get_logger(__name__)

EXPORTS = {
    "districts": "SELECT * FROM dim_district ORDER BY district_id",
    "daily_summary": "SELECT * FROM vw_rolling_rainfall ORDER BY district_id, full_date",
    "hourly": (
        "SELECT f.*, d.district_name FROM fact_weather f "
        "JOIN dim_district d ON d.district_id = f.district_id ORDER BY f.district_id, f.observed_at"
    ),
    "latest_reading": "SELECT * FROM vw_latest_reading ORDER BY district_id",
    "rankings": "SELECT * FROM vw_district_rankings ORDER BY rain_rank_today",
    "alerts": "SELECT * FROM vw_alerts ORDER BY full_date DESC, district_id",
}


def export_gold(engine: Engine, out_dir: Path = Path("data/gold")) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, sql in EXPORTS.items():
        df = pd.read_sql(sql, engine)
        path = out_dir / f"{name}.csv"
        df.to_csv(path, index=False)
        log.info("Exported %s (%d rows)", path, len(df))
        paths.append(path)
    return paths
