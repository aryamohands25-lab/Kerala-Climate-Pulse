# Power BI dashboard guide

Power BI Desktop is free (Windows only). Two ways to load the data:

## Option A: CSV files (easiest, no driver needed)
Run `python -m ingestion.run_pipeline --export`, then in Power BI: **Get data > Text/CSV** and load from `data/gold/`:
`districts.csv`, `daily_summary.csv`, `hourly.csv`, `latest_reading.csv`, `rankings.csv`, `alerts.csv`.
Refresh by re-running the pipeline and clicking **Refresh**. (Scheduled runs on GitHub upload these as artifacts.)

## Option B: PostgreSQL directly
**Get data > PostgreSQL database**, server `localhost:5432`, database `kerala_climate`, user `kerala_user`
(password from `.env`). Pick `dim_district`, `dim_date`, `fact_weather` and the `vw_*` views.
Power BI may ask you to install the Npgsql provider the first time.

## Model
Relate `fact_weather[district_id]` to `dim_district[district_id]` and `fact_weather[date_key]` to `dim_date[date_key]`
(many-to-one, single direction). Use `daily_summary`/`vw_rolling_rainfall` for the daily visuals.

## Pages and visuals
1. **Overview:** filled map or bubble map of `dim_district` (latitude, longitude; size = rainfall, colour = AQI), KPI cards, a season slicer from `dim_date[season]`.
2. **Rainfall:** line chart of `rain_mm_total` by `full_date` per district, `rain_7d_mm` as a second line, column chart of the 7-day ranking.
3. **Air quality:** matrix heatmap (rows = district, columns = `full_date`, values = `aqi_max`, conditional formatting at 50 / 100 / 150).
4. **Alerts:** table from `alerts.csv` (district, date, type, severity, value) plus a count card.

## DAX measures
```DAX
Total Rainfall (mm) = SUM ( daily_summary[rain_mm_total] )

Rain 7d Rolling (mm) =
CALCULATE ( MAX ( daily_summary[rain_7d_mm] ), LASTDATE ( daily_summary[full_date] ) )

Heavy Rain Days =
CALCULATE ( DISTINCTCOUNT ( daily_summary[full_date] ), daily_summary[rain_mm_total] >= 64.5 )

% Days With AQI Alert =
DIVIDE (
    CALCULATE ( COUNTROWS ( daily_summary ), daily_summary[aqi_max] >= 101 ),
    COUNTROWS ( daily_summary )
)

Wettest District =
VAR t = TOPN ( 1, SUMMARIZE ( daily_summary, daily_summary[district_name], "r", SUM ( daily_summary[rain_mm_total] ) ), [r], DESC )
RETURN MAXX ( t, daily_summary[district_name] )
```
Commit the `.pbix` file and add 3-4 screenshots to `docs/` for the README.
