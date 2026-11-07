from __future__ import annotations

import pytest
import requests

from ingestion.constants import AIR_QUALITY_URL, WEATHER_URL
from ingestion.ingest import TransientHTTPError, fetch_json, ingest_all, slugify
from tests.factories import RUN_DATE, air_payload, weather_payload


def test_retries_transient_errors_then_succeeds(requests_mock):
    requests_mock.get(WEATHER_URL, [{"status_code": 500}, {"status_code": 503}, {"json": {"ok": 1}}])
    assert fetch_json(WEATHER_URL, {}, max_retries=3, backoff_factor=0) == {"ok": 1}
    assert requests_mock.call_count == 3


def test_gives_up_after_max_retries(requests_mock):
    requests_mock.get(WEATHER_URL, status_code=500)
    with pytest.raises(TransientHTTPError):
        fetch_json(WEATHER_URL, {}, max_retries=3, backoff_factor=0)
    assert requests_mock.call_count == 3


def test_client_errors_are_not_retried(requests_mock):
    requests_mock.get(WEATHER_URL, status_code=400, json={"reason": "bad"})
    with pytest.raises(requests.HTTPError):
        fetch_json(WEATHER_URL, {}, max_retries=3, backoff_factor=0)
    assert requests_mock.call_count == 1


def test_ingest_saves_files_and_is_idempotent(requests_mock, districts, tmp_path):
    requests_mock.get(WEATHER_URL, json=weather_payload(1))
    requests_mock.get(AIR_QUALITY_URL, json=air_payload(1))
    for _ in range(2):  # run twice: same files, no duplicates
        res = ingest_all(RUN_DATE, districts, bronze_dir=tmp_path, past_days=7, max_retries=1, backoff_factor=0)
    files = sorted((tmp_path / "2026-10-24").glob("*.json"))
    assert len(files) == 28 and not res.failures
    assert (tmp_path / "2026-10-24" / "thiruvananthapuram_weather.json").exists()


def test_one_failing_district_does_not_stop_the_rest(requests_mock, districts, tmp_path):
    requests_mock.get(WEATHER_URL, json=weather_payload(1))
    requests_mock.get(AIR_QUALITY_URL, json=air_payload(1))
    # Kasaragod's latitude (12.4996) -> always fails
    requests_mock.get(AIR_QUALITY_URL, status_code=500, additional_matcher=lambda r: "latitude=12.4996" in r.url)
    res = ingest_all(RUN_DATE, districts, bronze_dir=tmp_path, max_retries=1, backoff_factor=0)
    assert res.failures == ["Kasaragod/air_quality"]
    assert len(res.saved) == 27


def test_request_params_use_explicit_units_and_timezone(requests_mock, districts, tmp_path):
    requests_mock.get(WEATHER_URL, json=weather_payload(1))
    requests_mock.get(AIR_QUALITY_URL, json=air_payload(1))
    ingest_all(RUN_DATE, districts.head(1), bronze_dir=tmp_path, past_days=7, max_retries=1, backoff_factor=0)
    q = requests_mock.request_history[0].qs
    assert q["timezone"] == ["asia/kolkata"] and q["past_days"] == ["7"] and q["forecast_days"] == ["1"]
    assert q["wind_speed_unit"] == ["kmh"] and q["precipitation_unit"] == ["mm"]


def test_slugify():
    assert slugify("Thiruvananthapuram") == "thiruvananthapuram"
    assert slugify("Some District") == "some_district"
