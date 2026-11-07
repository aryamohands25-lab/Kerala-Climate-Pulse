-- 02_gold.sql : star schema (dim_district, dim_date, fact_weather) + anomalies.

CREATE TABLE IF NOT EXISTS dim_district (
    district_id    SMALLINT      PRIMARY KEY,
    district_name  VARCHAR(40)   NOT NULL UNIQUE,
    latitude       DOUBLE PRECISION NOT NULL,
    longitude      DOUBLE PRECISION NOT NULL,
    region         VARCHAR(20)   NOT NULL,
    area_sq_km     INTEGER,
    hq_city        VARCHAR(40)
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key       INTEGER       PRIMARY KEY,    -- YYYYMMDD
    full_date      DATE          NOT NULL UNIQUE,
    year           SMALLINT      NOT NULL,
    month          SMALLINT      NOT NULL,
    month_name     VARCHAR(10)   NOT NULL,
    day_of_month   SMALLINT      NOT NULL,
    day_name       VARCHAR(10)   NOT NULL,
    is_weekend     BOOLEAN       NOT NULL,
    season         VARCHAR(20)   NOT NULL        -- Kerala climate season
);

CREATE TABLE IF NOT EXISTS fact_weather (
    district_id    SMALLINT      NOT NULL REFERENCES dim_district (district_id),
    observed_at    TIMESTAMP     NOT NULL,
    date_key       INTEGER       NOT NULL REFERENCES dim_date (date_key),
    hour_of_day    SMALLINT      NOT NULL,
    temperature_c  DOUBLE PRECISION,
    humidity_pct   DOUBLE PRECISION,
    rainfall_mm    DOUBLE PRECISION,
    wind_speed_kmh DOUBLE PRECISION,
    pm10           DOUBLE PRECISION,
    pm2_5          DOUBLE PRECISION,
    aqi            DOUBLE PRECISION,
    is_forecast    BOOLEAN       NOT NULL,
    PRIMARY KEY (district_id, observed_at)
);

-- Serves "all districts for a day" scans (rankings, daily summaries).
CREATE INDEX IF NOT EXISTS idx_fact_date_district ON fact_weather (date_key, district_id);

CREATE TABLE IF NOT EXISTS gold_anomalies (
    district_id    SMALLINT      NOT NULL REFERENCES dim_district (district_id),
    observed_at    TIMESTAMP     NOT NULL,
    anomaly_score  DOUBLE PRECISION NOT NULL,
    is_anomaly     BOOLEAN       NOT NULL,
    PRIMARY KEY (district_id, observed_at)
)
