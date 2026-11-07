"""schemas.py – Pydantic response models for the API."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: str
    database: str
    latest_observation: Optional[datetime] = None


class District(BaseModel):
    district_id: int
    district_name: str
    region: str
    latitude: float
    longitude: float


class LatestReading(BaseModel):
    district_id: int
    district_name: str
    region: str
    observed_at: datetime
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    rainfall_mm: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    pm10: Optional[float] = None
    pm2_5: Optional[float] = None
    aqi: Optional[float] = None
    aqi_category: str


class DailyRecord(BaseModel):
    full_date: date
    season: str
    rain_mm_total: Optional[float] = None
    rain_3d_mm: Optional[float] = None
    rain_7d_mm: Optional[float] = None
    rain_change_vs_prev_day_mm: Optional[float] = None
    temp_avg_c: Optional[float] = None
    temp_max_c: Optional[float] = None
    humidity_avg_pct: Optional[float] = None
    wind_max_kmh: Optional[float] = None
    aqi_avg: Optional[float] = None
    aqi_max: Optional[float] = None
    hours_observed: int = Field(description="Hours of data behind this day (<24 for today)")


class History(BaseModel):
    district_name: str
    days: int
    records: list[DailyRecord]


class Alert(BaseModel):
    district_id: int
    district_name: str
    region: str
    full_date: date
    alert_type: str
    severity: str
    observed_value: float
    threshold: float


class Ranking(BaseModel):
    district_id: int
    district_name: str
    region: str
    full_date: date
    rain_mm_total: Optional[float] = None
    rain_7d_mm: Optional[float] = None
    aqi_avg: Optional[float] = None
    aqi_max: Optional[float] = None
    rain_rank_today: int
    rain_rank_7d: int
    aqi_rank_worst_first: int


class Anomaly(BaseModel):
    district_id: int
    district_name: str
    observed_at: datetime
    anomaly_score: float
