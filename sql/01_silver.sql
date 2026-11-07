-- 01_silver.sql : cleaned, typed hourly table + pipeline run log.
-- Written to run unchanged on PostgreSQL (production) and SQLite (unit tests).

CREATE TABLE IF NOT EXISTS silver_weather_hourly (
    district_id     SMALLINT         NOT NULL,
    observed_at     TIMESTAMP        NOT NULL,   -- IST, tz-naive
    observed_date   DATE             NOT NULL,
    observed_hour   SMALLINT         NOT NULL,
    temperature_c   DOUBLE PRECISION,
    humidity_pct    DOUBLE PRECISION,
    rainfall_mm     DOUBLE PRECISION,
    wind_speed_kmh  DOUBLE PRECISION,
    pm10            DOUBLE PRECISION,
    pm2_5           DOUBLE PRECISION,
    aqi             DOUBLE PRECISION,            -- US AQI
    is_forecast     BOOLEAN          NOT NULL,
    loaded_at       TIMESTAMP        NOT NULL,
    PRIMARY KEY (district_id, observed_at)
);

CREATE INDEX IF NOT EXISTS idx_silver_date ON silver_weather_hourly (observed_date);

CREATE TABLE IF NOT EXISTS pipeline_run_log (
    run_id          VARCHAR(36)  PRIMARY KEY,
    started_at      TIMESTAMP    NOT NULL,
    finished_at     TIMESTAMP,
    status          VARCHAR(10)  NOT NULL,       -- RUNNING / SUCCESS / FAILED
    rows_loaded     INTEGER,
    quality_status  VARCHAR(4),                  -- PASS / WARN / FAIL
    message         VARCHAR(500)
)
