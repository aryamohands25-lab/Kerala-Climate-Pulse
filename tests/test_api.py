from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from ingestion.run_pipeline import run
from tests.factories import HEAVY_RAIN_DISTRICT, NOW, RUN_DATE


@pytest.fixture()
def client(sqlite_engine, bronze_dir, districts, tmp_path):
    run(sqlite_engine, run_date=RUN_DATE, skip_ingest=True, districts=districts, bronze_dir=bronze_dir,
        reports_dir=tmp_path / "r", now=NOW, with_anomaly=True)
    with TestClient(create_app(sqlite_engine)) as c:
        yield c


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["latest_observation"].startswith("2026-10-24")


def test_districts_lists_all_fourteen(client):
    rows = client.get("/districts").json()
    assert len(rows) == 14 and rows[0]["district_name"] == "Thiruvananthapuram"


def test_latest_reading_and_aliases(client):
    r = client.get("/district/Idukki/latest").json()
    assert r["district_name"] == "Idukki" and r["observed_at"].startswith("2026-10-24T14:00")
    assert r["aqi_category"] in {"GOOD", "MODERATE", "UNHEALTHY_FOR_SENSITIVE"}
    assert client.get("/district/trivandrum/latest").json()["district_name"] == "Thiruvananthapuram"
    assert client.get("/district/KOCHI/latest").status_code == 404


def test_unknown_district_gives_helpful_404(client):
    r = client.get("/district/atlantis/latest")
    assert r.status_code == 404 and "/districts" in r.json()["detail"]


def test_history_days_and_validation(client):
    body = client.get("/district/idukki/history?days=3").json()
    assert body["days"] == 3 and len(body["records"]) == 3
    assert [r["full_date"] for r in body["records"]] == ["2026-10-22", "2026-10-23", "2026-10-24"]
    assert client.get("/district/idukki/history?days=0").status_code == 422
    assert client.get("/district/idukki/history?days=99").status_code == 422


def test_heavy_rain_alerts_window(client):
    # latest data day is 24th; the heavy-rain day is the 23rd
    assert client.get("/alerts/heavy-rain?days=1").json() == []
    two_days = client.get("/alerts/heavy-rain?days=2").json()
    assert len(two_days) == 1
    assert two_days[0]["district_id"] == HEAVY_RAIN_DISTRICT and two_days[0]["severity"] == "HEAVY"
    assert client.get("/alerts/heavy-rain?days=9").status_code == 422


def test_air_quality_alert(client):
    rows = client.get("/alerts/air-quality?days=2").json()
    assert [r["district_name"] for r in rows] == ["Ernakulam"]


def test_rankings(client):
    aqi = client.get("/rankings/aqi").json()
    rain = client.get("/rankings/rainfall").json()
    assert len(aqi) == 14 and aqi[0]["aqi_rank_worst_first"] == 1
    assert len(rain) == 14 and rain[0]["rain_rank_today"] == 1


def test_anomalies_endpoint(client):
    rows = client.get("/anomalies?limit=5").json()
    assert 0 < len(rows) <= 5
    assert rows == sorted(rows, key=lambda r: -r["anomaly_score"])


def test_openapi_docs_available(client):
    assert client.get("/docs").status_code == 200
    assert "/alerts/heavy-rain" in client.get("/openapi.json").json()["paths"]
