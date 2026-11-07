-- 03_views.sql : analytics views (CTEs + window functions) on the star schema.
-- Only observed hours (is_forecast = FALSE) feed the daily aggregates.
-- Alert thresholds mirror ingestion/constants.py (IMD rain classes, US AQI).

DROP VIEW IF EXISTS vw_alerts;
DROP VIEW IF EXISTS vw_district_rankings;
DROP VIEW IF EXISTS vw_rolling_rainfall;
DROP VIEW IF EXISTS vw_latest_reading;
DROP VIEW IF EXISTS vw_daily_district_summary;

CREATE VIEW vw_daily_district_summary AS
SELECT
    d.district_id,
    d.district_name,
    d.region,
    dt.full_date,
    dt.season,
    ROUND(CAST(SUM(f.rainfall_mm)   AS NUMERIC), 1) AS rain_mm_total,
    ROUND(CAST(AVG(f.temperature_c) AS NUMERIC), 1) AS temp_avg_c,
    ROUND(CAST(MIN(f.temperature_c) AS NUMERIC), 1) AS temp_min_c,
    ROUND(CAST(MAX(f.temperature_c) AS NUMERIC), 1) AS temp_max_c,
    ROUND(CAST(AVG(f.humidity_pct)  AS NUMERIC), 1) AS humidity_avg_pct,
    ROUND(CAST(MAX(f.wind_speed_kmh) AS NUMERIC), 1) AS wind_max_kmh,
    ROUND(CAST(AVG(f.pm2_5)         AS NUMERIC), 1) AS pm2_5_avg,
    ROUND(CAST(AVG(f.aqi)           AS NUMERIC), 0) AS aqi_avg,
    ROUND(CAST(MAX(f.aqi)           AS NUMERIC), 0) AS aqi_max,
    COUNT(*) AS hours_observed
FROM fact_weather f
JOIN dim_district d ON d.district_id = f.district_id
JOIN dim_date dt    ON dt.date_key   = f.date_key
WHERE f.is_forecast = FALSE
GROUP BY d.district_id, d.district_name, d.region, dt.full_date, dt.season;

CREATE VIEW vw_latest_reading AS
SELECT
    t.district_id, t.district_name, t.region, t.observed_at,
    t.temperature_c, t.humidity_pct, t.rainfall_mm, t.wind_speed_kmh,
    t.pm10, t.pm2_5, t.aqi,
    CASE
        WHEN t.aqi IS NULL  THEN 'UNKNOWN'
        WHEN t.aqi <= 50    THEN 'GOOD'
        WHEN t.aqi <= 100   THEN 'MODERATE'
        WHEN t.aqi <= 150   THEN 'UNHEALTHY_FOR_SENSITIVE'
        WHEN t.aqi <= 200   THEN 'UNHEALTHY'
        ELSE 'VERY_UNHEALTHY'
    END AS aqi_category
FROM (
    SELECT
        d.district_id, d.district_name, d.region, f.observed_at,
        f.temperature_c, f.humidity_pct, f.rainfall_mm, f.wind_speed_kmh,
        f.pm10, f.pm2_5, f.aqi,
        ROW_NUMBER() OVER (PARTITION BY f.district_id ORDER BY f.observed_at DESC) AS rn
    FROM fact_weather f
    JOIN dim_district d ON d.district_id = f.district_id
    WHERE f.is_forecast = FALSE
) t
WHERE t.rn = 1;

CREATE VIEW vw_rolling_rainfall AS
SELECT
    s.district_id, s.district_name, s.region, s.full_date, s.season,
    s.rain_mm_total, s.temp_avg_c, s.temp_max_c, s.humidity_avg_pct,
    s.wind_max_kmh, s.pm2_5_avg, s.aqi_avg, s.aqi_max, s.hours_observed,
    ROUND(CAST(SUM(s.rain_mm_total) OVER (
        PARTITION BY s.district_id ORDER BY s.full_date
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS NUMERIC), 1) AS rain_3d_mm,
    ROUND(CAST(SUM(s.rain_mm_total) OVER (
        PARTITION BY s.district_id ORDER BY s.full_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS NUMERIC), 1) AS rain_7d_mm,
    ROUND(CAST(s.rain_mm_total - LAG(s.rain_mm_total) OVER (
        PARTITION BY s.district_id ORDER BY s.full_date) AS NUMERIC), 1) AS rain_change_vs_prev_day_mm
FROM vw_daily_district_summary s;

CREATE VIEW vw_district_rankings AS
WITH latest AS (
    SELECT MAX(full_date) AS max_date FROM vw_rolling_rainfall
)
SELECT
    r.district_id, r.district_name, r.region, r.full_date,
    r.rain_mm_total, r.rain_7d_mm, r.aqi_avg, r.aqi_max,
    RANK() OVER (ORDER BY r.rain_mm_total DESC NULLS LAST) AS rain_rank_today,
    RANK() OVER (ORDER BY r.rain_7d_mm    DESC NULLS LAST) AS rain_rank_7d,
    RANK() OVER (ORDER BY r.aqi_avg       DESC NULLS LAST) AS aqi_rank_worst_first
FROM vw_rolling_rainfall r
JOIN latest l ON r.full_date = l.max_date;

CREATE VIEW vw_alerts AS
SELECT
    district_id, district_name, region, full_date,
    'HEAVY_RAIN' AS alert_type,
    CASE
        WHEN rain_mm_total >= 204.5 THEN 'EXTREMELY_HEAVY'
        WHEN rain_mm_total >= 115.6 THEN 'VERY_HEAVY'
        ELSE 'HEAVY'
    END AS severity,
    rain_mm_total AS observed_value,
    64.5 AS threshold
FROM vw_rolling_rainfall
WHERE rain_mm_total >= 64.5
UNION ALL
SELECT
    district_id, district_name, region, full_date,
    'POOR_AIR_QUALITY' AS alert_type,
    CASE WHEN aqi_max >= 151 THEN 'UNHEALTHY' ELSE 'UNHEALTHY_FOR_SENSITIVE' END AS severity,
    aqi_max AS observed_value,
    101.0 AS threshold
FROM vw_daily_district_summary
WHERE aqi_max >= 101
