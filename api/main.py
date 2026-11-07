"""main.py – FastAPI serving layer on top of the gold views.

    uvicorn api.main:app --reload
    open http://localhost:8000/docs
"""

from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from api.schemas import (
    Alert,
    Anomaly,
    District,
    Health,
    History,
    LatestReading,
    Ranking,
)
from ingestion.db import get_engine, init_schema

# Common alternate names people actually use.
ALIASES = {"trivandrum": "thiruvananthapuram", "cochin": "ernakulam", "calicut": "kozhikode"}


def create_app(engine: Engine | None = None, *, init_db: bool = True) -> FastAPI:
    """App factory so tests can inject their own engine."""
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if init_db:  # views must exist before the first request
            init_schema(app.state.engine)
        yield

    app = FastAPI(
        title="Kerala Climate Pulse API",
        version="1.0.0",
        description="Hourly weather and air quality for Kerala's 14 districts (Open-Meteo data).",
        lifespan=lifespan,
    )
    app.state.engine = engine or get_engine()

    def get_conn(request: Request):
        with request.app.state.engine.connect() as conn:
            yield conn

    Conn = Annotated[Connection, Depends(get_conn)]

    def resolve_district(conn: Connection, name: str) -> dict:
        key = ALIASES.get(name.strip().lower(), name.strip().lower())
        row = conn.execute(
            text("SELECT district_id, district_name FROM dim_district WHERE LOWER(district_name) = :n"),
            {"n": key},
        ).mappings().first()
        if not row:
            raise HTTPException(404, f"Unknown district '{name}'. See /districts for valid names.")
        return dict(row)

    @app.get("/health", response_model=Health, tags=["meta"])
    def health(conn: Conn):
        try:
            latest = conn.execute(
                text("SELECT MAX(observed_at) FROM fact_weather WHERE is_forecast = FALSE")
            ).scalar()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, f"database unavailable: {type(exc).__name__}") from exc
        return Health(status="ok", database="up", latest_observation=latest)

    @app.get("/districts", response_model=list[District], tags=["districts"])
    def districts(conn: Conn):
        rows = conn.execute(
            text("SELECT district_id, district_name, region, latitude, longitude "
                 "FROM dim_district ORDER BY district_id")
        ).mappings().all()
        return [dict(r) for r in rows]

    @app.get("/district/{name}/latest", response_model=LatestReading, tags=["districts"])
    def district_latest(name: str, conn: Conn):
        d = resolve_district(conn, name)
        row = conn.execute(
            text("SELECT * FROM vw_latest_reading WHERE district_id = :id"), {"id": d["district_id"]}
        ).mappings().first()
        if not row:
            raise HTTPException(404, f"No observations loaded yet for {d['district_name']}.")
        return dict(row)

    @app.get("/district/{name}/history", response_model=History, tags=["districts"])
    def district_history(
        name: str,
        conn: Conn,
        days: Annotated[int, Query(ge=1, le=30, description="How many recent days")] = 7,
    ):
        d = resolve_district(conn, name)
        rows = conn.execute(
            text(
                "SELECT * FROM (SELECT * FROM vw_rolling_rainfall WHERE district_id = :id "
                "ORDER BY full_date DESC LIMIT :days) t ORDER BY full_date"
            ),
            {"id": d["district_id"], "days": days},
        ).mappings().all()
        return {"district_name": d["district_name"], "days": days, "records": [dict(r) for r in rows]}

    def _alerts(conn: Connection, alert_type: str, days: int) -> list[dict]:
        latest = conn.execute(text("SELECT MAX(full_date) FROM vw_daily_district_summary")).scalar()
        if latest is None:
            return []
        if isinstance(latest, str):  # SQLite returns dates as text
            latest = date.fromisoformat(latest)
        cutoff = latest - timedelta(days=days - 1)
        rows = conn.execute(
            text(
                "SELECT * FROM vw_alerts WHERE alert_type = :t AND full_date >= :cutoff "
                "ORDER BY full_date DESC, observed_value DESC"
            ),
            {"t": alert_type, "cutoff": cutoff},
        ).mappings().all()
        return [dict(r) for r in rows]

    @app.get("/alerts/heavy-rain", response_model=list[Alert], tags=["alerts"])
    def heavy_rain_alerts(conn: Conn, days: Annotated[int, Query(ge=1, le=7)] = 1):
        """Districts whose daily rainfall reached IMD's 'heavy' class (>= 64.5 mm)."""
        return _alerts(conn, "HEAVY_RAIN", days)

    @app.get("/alerts/air-quality", response_model=list[Alert], tags=["alerts"])
    def air_quality_alerts(conn: Conn, days: Annotated[int, Query(ge=1, le=7)] = 1):
        """Districts where the daily peak US AQI reached 101 or more."""
        return _alerts(conn, "POOR_AIR_QUALITY", days)

    @app.get("/rankings/aqi", response_model=list[Ranking], tags=["rankings"])
    def aqi_rankings(conn: Conn):
        """Latest day, worst air quality first."""
        rows = conn.execute(
            text("SELECT * FROM vw_district_rankings ORDER BY aqi_rank_worst_first, district_id")
        ).mappings().all()
        return [dict(r) for r in rows]

    @app.get("/rankings/rainfall", response_model=list[Ranking], tags=["rankings"])
    def rainfall_rankings(conn: Conn):
        """Latest day, wettest district first."""
        rows = conn.execute(
            text("SELECT * FROM vw_district_rankings ORDER BY rain_rank_today, district_id")
        ).mappings().all()
        return [dict(r) for r in rows]

    @app.get("/anomalies", response_model=list[Anomaly], tags=["ml"])
    def anomalies(conn: Conn, limit: Annotated[int, Query(ge=1, le=200)] = 50):
        """Most unusual hourly readings (needs `--with-anomaly` pipeline run)."""
        rows = conn.execute(
            text(
                "SELECT a.district_id, d.district_name, a.observed_at, a.anomaly_score "
                "FROM gold_anomalies a JOIN dim_district d ON d.district_id = a.district_id "
                "WHERE a.is_anomaly = TRUE ORDER BY a.anomaly_score DESC LIMIT :limit"
            ),
            {"limit": limit},
        ).mappings().all()
        return [dict(r) for r in rows]

    return app


app = create_app()
