"""Open-Meteo parsing and the open-month caching rule. No network."""

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.cache import Cache  # noqa: E402
from common.periods import month_is_closed, months_between, parse_month  # noqa: E402
from common.weather import (  # noqa: E402
    DailyWeatherSchema,
    HourlyWeatherSchema,
    Location,
    OpenMeteoDaily,
    OpenMeteoHourly,
)

TODAY = dt.date(2026, 11, 17)

# Two real NYC days (2025-01-01/02) as returned with timeformat=unixtime,
# plus a third synthetic polar-night day (sunrise == sunset == local midnight).
DAILY = {
    "latitude": 40.738136, "longitude": -74.04254,
    "utc_offset_seconds": -18000, "timezone": "America/New_York",
    "daily": {
        "time": [1735707600, 1735794000, 1735880400],
        "weather_code": [53, 3, 71],
        "temperature_2m_max": [11.0, 5.4, 1.0],
        "temperature_2m_min": [3.0, -0.3, -2.0],
        "sunrise": [1735734018, 1735820423, 1735880400],
        "sunset": [1735767588, 1735854040, 1735880400],
        "daylight_duration": [33559.46, 33605.90, 0.0],
        "sunshine_duration": [18443.58, 28032.63, 0.0],
        "precipitation_sum": [1.10, 0.00, 0.0],
    },
}

HOURLY = {
    "latitude": 51.5, "longitude": -0.13, "timezone": "Europe/London",
    "hourly": {
        # 2025-03-30 00:00 and 02:00 local -- straddling the BST switch.
        "time": [1743292800, 1743296400],
        "temperature_2m": [7.6, 7.4],
        "precipitation": [0.8, 0.0],
        "is_day": [0, 0],
        "weather_code": [53, 3],
    },
}


def raw_path(tmp_path, slug):
    p = tmp_path / slug / "2025-01.json"
    p.parent.mkdir(parents=True)
    return p


def test_daily_sunrise_sunset_are_local_and_utc(tmp_path):
    src = OpenMeteoDaily(cache=Cache(tmp_path))
    df = src.parse_payload(DAILY, raw_path(tmp_path, "40.7128_-74.0060"))
    first = df.iloc[0]
    assert first["date"] == pd.Timestamp("2025-01-01")
    assert first["sunrise"] == pd.Timestamp("2025-01-01 07:20:18")
    assert first["sunrise_utc"] == pd.Timestamp("2025-01-01 12:20:18", tz="UTC")
    assert first["sunset"].hour == 16
    assert first["daylight_h"] == pytest.approx(9.32, abs=0.01)
    assert first["weather"] == "drizzle"
    # requested coordinates, not the snapped grid cell
    assert first["latitude"] == 40.7128


def test_polar_night_has_no_sunrise(tmp_path):
    src = OpenMeteoDaily(cache=Cache(tmp_path))
    df = src.parse_payload(DAILY, raw_path(tmp_path, "40.7128_-74.0060"))
    polar = df.iloc[2]
    assert pd.isna(polar["sunrise"]) and pd.isna(polar["sunset_utc"])
    assert polar["daylight_h"] == 0


def test_daily_conforms_to_schema_and_backfills_optional(tmp_path):
    df = OpenMeteoDaily(cache=Cache(tmp_path)).parse_payload(DAILY)
    assert set(DailyWeatherSchema.required()) <= set(df.columns)
    assert "snowfall_cm" in df.columns  # not in the payload, backfilled


def test_hourly_local_time_follows_dst(tmp_path):
    df = OpenMeteoHourly(cache=Cache(tmp_path)).parse_payload(HOURLY)
    assert list(df["time"].dt.hour) == [0, 2]  # 01:00 local never happened
    assert df["is_day"].dtype == bool
    assert set(HourlyWeatherSchema.required()) <= set(df.columns)


def test_closed_months_use_archive_open_months_use_forecast(tmp_path):
    src = OpenMeteoDaily(cache=Cache(tmp_path), today=TODAY)
    assert "archive-api" in src._request("40.7128_-74.0060/2026-09")
    recent = src._request("40.7128_-74.0060/2026-11")
    assert "api.open-meteo.com/v1/forecast" in recent
    assert "end_date=2026-11-30" in recent
    assert not src._is_final("40.7128_-74.0060/2026-11")
    # October ended 17 days ago -> settled in the archive
    assert src._is_final("40.7128_-74.0060/2026-10")


def test_forecast_requests_are_clipped_to_the_horizon(tmp_path):
    src = OpenMeteoDaily(cache=Cache(tmp_path), today=dt.date(2026, 11, 1))
    assert "end_date=2026-11-16" in src._request("1.0000_2.0000/2026-11")


def test_open_month_is_never_cached(tmp_path, monkeypatch):
    src = OpenMeteoDaily(cache=Cache(tmp_path), today=TODAY)
    calls = []

    def fake_download(key):
        calls.append(key)
        p = src.cache.path(f"raw/{key}.json")
        p.write_text(json.dumps(DAILY))
        return p

    monkeypatch.setattr(src, "_download", fake_download)
    key = "40.7128_-74.0060/2026-11"
    src.load(key)
    src.load(key)
    assert len(calls) == 2
    assert not src._parquet_path(key).exists()


def test_load_range_trims_to_requested_days(tmp_path, monkeypatch):
    src = OpenMeteoDaily(cache=Cache(tmp_path), today=TODAY)
    monkeypatch.setattr(src, "load", lambda key: src.parse_payload(DAILY))
    df = src.load_range(Location(40.7128, -74.006, "NYC"), "2025-01-02", "2025-01-02")
    assert list(df["date"]) == [pd.Timestamp("2025-01-02")]
    assert list(df["location"]) == ["NYC"]


def test_location_validates_and_slugs():
    assert Location(40.71281, -74.00601).slug == "40.7128_-74.0060"
    with pytest.raises(ValueError):
        Location(91, 0)


def test_months_between_and_closure():
    assert months_between("2025-11-15", "2026-02-01") == [
        "2025-11", "2025-12", "2026-01", "2026-02",
    ]
    assert parse_month("2025-12") == (dt.date(2025, 12, 1), dt.date(2026, 1, 1))
    assert month_is_closed("2026-10", today=TODAY)
    assert not month_is_closed("2026-10", lag_days=30, today=TODAY)
    assert not month_is_closed("2026-11", today=TODAY)
