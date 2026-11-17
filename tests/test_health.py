"""Google Health flattening, filters and paging. No network, no OAuth."""

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.cache import Cache  # noqa: E402
from common.health import (  # noqa: E402
    AuthError,
    GoogleHealth,
    GoogleHealthAuth,
    flatten_datapoints,
    kind_of,
    month_filter,
)

SRC = {"recordingMethod": "PASSIVELY_MEASURED", "device": {"displayName": "Charge 6"},
       "platform": "FITBIT"}

STEPS = [{
    "dataSource": SRC,
    "steps": {
        "interval": {"startTime": "2026-03-04T07:05:00Z", "startUtcOffset": "-18000s",
                     "endTime": "2026-03-04T07:06:00Z", "endUtcOffset": "-18000s"},
        "count": "40",
    },
}]

SLEEP = [{
    "name": "users/1/dataTypes/sleep/dataPoints/2",
    "dataSource": SRC,
    "sleep": {
        "interval": {"startTime": "2026-03-03T20:57:30Z", "endTime": "2026-03-04T04:41:30Z"},
        "type": "STAGES",
        "stages": [{"type": "DEEP"}, {"type": "REM"}],
        "summary": {"minutesAsleep": "407", "minutesAwake": "57"},
    },
}]

HEART_RATE = [{
    "dataSource": SRC,
    "heartRate": {
        "sampleTime": {"physicalTime": "2026-03-04T12:00:05Z", "utcOffset": "3600s"},
        "beatsPerMinute": "61",
    },
}]

RESTING = [{"dailyRestingHeartRate": {"date": {"year": 2026, "month": 3, "day": 4},
                                      "beatsPerMinute": "55"}}]


def test_interval_points_get_utc_and_local_times():
    df = flatten_datapoints(STEPS, "steps")
    row = df.iloc[0]
    assert row["start_time"] == pd.Timestamp("2026-03-04 07:05", tz="UTC")
    assert row["start_local"] == pd.Timestamp("2026-03-04 02:05")
    assert row["count"] == 40 and pd.api.types.is_numeric_dtype(df["count"])
    assert row["source_device"] == "Charge 6"
    assert "interval_start_time" not in df.columns


def test_sleep_summary_flattens_and_stages_stay_json():
    row = flatten_datapoints(SLEEP, "sleep").iloc[0]
    assert row["summary_minutes_asleep"] == 407
    assert row["stages"].startswith("[")
    assert row["type"] == "STAGES"


def test_sample_and_daily_shapes():
    hr = flatten_datapoints(HEART_RATE, "heart-rate").iloc[0]
    assert hr["time_local"] == pd.Timestamp("2026-03-04 13:00:05")
    assert hr["beats_per_minute"] == 61
    rest = flatten_datapoints(RESTING, "daily-resting-heart-rate").iloc[0]
    assert rest["date"] == pd.Timestamp("2026-03-04")


def test_durations_become_seconds():
    pts = [{"exercise": {"interval": {"startTime": "2026-03-04T07:00:00Z",
                                      "endTime": "2026-03-04T08:00:00Z"},
                         "activeDuration": "3540s"}}]
    df = flatten_datapoints(pts, "exercise")
    assert df.loc[0, "active_duration_s"] == 3540.0


def test_empty_month_is_an_empty_frame():
    assert flatten_datapoints([], "steps").empty


@pytest.mark.parametrize("data_type,expected", [
    ("steps", 'steps.interval.civil_start_time >= "2026-03-01T00:00:00" AND '
              'steps.interval.civil_start_time < "2026-04-01T00:00:00"'),
    ("heart-rate", 'heart_rate.sample_time.civil_time >= "2026-03-01T00:00:00" AND '
                   'heart_rate.sample_time.civil_time < "2026-04-01T00:00:00"'),
    ("daily-resting-heart-rate", 'daily_resting_heart_rate.date >= "2026-03-01" AND '
                                 'daily_resting_heart_rate.date < "2026-04-01"'),
    ("sleep", 'sleep.interval.civil_end_time >= "2026-03-01T00:00:00" AND '
              'sleep.interval.civil_end_time < "2026-04-01T00:00:00"'),
])
def test_month_filter_matches_the_type_kind(data_type, expected):
    assert month_filter(data_type, "2026-03") == expected


def test_kinds():
    assert kind_of("sleep") == "interval"
    assert kind_of("weight") == "sample"
    assert kind_of("daily-heart-rate-variability") == "daily"


class FakeAuth:
    def token(self):
        return "tok"


def test_pages_follow_next_page_token(tmp_path, monkeypatch):
    gh = GoogleHealth(auth=FakeAuth(), cache=Cache(tmp_path), today=dt.date(2026, 11, 17))
    pages = [{"dataPoints": STEPS, "nextPageToken": "p2"}, {"dataPoints": STEPS}]
    seen = []

    def fake_get_json(url, params, headers):
        seen.append((url, dict(params), headers))
        return pages[len(seen) - 1]

    monkeypatch.setattr(gh.fetcher, "get_json", fake_get_json)
    df = gh.load("steps/2026-03")
    assert len(df) == 2
    assert seen[0][0].endswith("/users/me/dataTypes/steps/dataPoints")
    assert seen[1][1]["pageToken"] == "p2"
    assert seen[0][2] == {"Authorization": "Bearer tok"}
    # closed month -> cached; a second load makes no requests
    gh.load("steps/2026-03")
    assert len(seen) == 2


def test_small_page_types_use_page_size_25(tmp_path, monkeypatch):
    gh = GoogleHealth(auth=FakeAuth(), cache=Cache(tmp_path))
    sizes = []
    monkeypatch.setattr(gh.fetcher, "get_json",
                        lambda url, params, headers: sizes.append(params["pageSize"]) or {})
    list(gh._pages("sleep", "x"))
    list(gh._pages("steps", "x"))
    assert sizes == [25, 10_000]


def test_missing_token_says_how_to_sign_in(tmp_path):
    pytest.importorskip("google.oauth2.credentials")
    auth = GoogleHealthAuth(token_path=tmp_path / "none.json")
    with pytest.raises(AuthError, match="python -m common.health auth"):
        auth.token()


def test_sleep_belongs_to_the_wake_up_date(tmp_path, monkeypatch):
    """A night starting Mar 3 and ending Mar 4 is a Mar 4 night -- the same
    rule the API's end-time filter applies, so it can't fall between months."""
    gh = GoogleHealth(auth=FakeAuth(), cache=Cache(tmp_path))
    monkeypatch.setattr(gh, "load", lambda key: flatten_datapoints(SLEEP, "sleep"))
    assert len(gh.load_range("sleep", "2026-03-04", "2026-03-04")) == 1
    assert gh.load_range("sleep", "2026-03-03", "2026-03-03").empty
