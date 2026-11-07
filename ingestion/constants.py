"""constants.py – API endpoints, column mappings, and validation ranges."""
from __future__ import annotations

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

WEATHER_HOURLY = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
]
AIR_HOURLY = ["pm10", "pm2_5", "us_aqi"]

# Explicit units so the silver layer never depends on API defaults.
UNIT_PARAMS = {
    "temperature_unit": "celsius",
    "wind_speed_unit": "kmh",
    "precipitation_unit": "mm",
}

# Open-Meteo field name -> silver column name
COLUMN_MAP = {
    "temperature_2m": "temperature_c",
    "relative_humidity_2m": "humidity_pct",
    "precipitation": "rainfall_mm",
    "wind_speed_10m": "wind_speed_kmh",
    "pm10": "pm10",
    "pm2_5": "pm2_5",
    "us_aqi": "aqi",
}
MEASURE_COLUMNS = list(COLUMN_MAP.values())

# Plausible physical ranges (inclusive) for Kerala hourly data.
VALUE_RANGES: dict[str, tuple[float, float]] = {
    "temperature_c": (5.0, 50.0),
    "humidity_pct": (0.0, 100.0),
    "rainfall_mm": (0.0, 200.0),
    "wind_speed_kmh": (0.0, 200.0),
    "pm10": (0.0, 1000.0),
    "pm2_5": (0.0, 1000.0),
    "aqi": (0.0, 500.0),
}

IST_OFFSET_SECONDS = 19800  # UTC+05:30

# Alert thresholds (daily totals). Rain classes follow IMD's daily categories.
HEAVY_RAIN_MM = 64.5
VERY_HEAVY_RAIN_MM = 115.6
EXTREME_RAIN_MM = 204.5
AQI_UNHEALTHY_SENSITIVE = 101
AQI_UNHEALTHY = 151
