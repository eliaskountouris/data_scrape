"""Tests for the turnaround chaining.

The pairing logic fails silently when it's wrong -- a bad midnight wrap just
produces plausible-looking ground times -- so the edge cases are pinned here.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.flights import build_turnarounds, label_turnarounds  # noqa: E402


def flight(
    tail, date, origin, dest, crs_dep, crs_arr, dep_delay=0.0, arr_delay=0.0,
    cancelled=False, diverted=False,
):
    """One BTS-shaped row. Times are ``HH:MM`` strings, local to their airport."""
    def mins(hhmm):
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)

    d = pd.Timestamp(date)
    return {
        "tail": tail,
        "flight_date": d,
        "origin": origin,
        "dest": dest,
        "crs_dep_min": mins(crs_dep),
        "crs_arr_min": mins(crs_arr),
        "crs_dep_dt": d + pd.Timedelta(minutes=mins(crs_dep)),
        "dep_delay": dep_delay,
        "arr_delay": arr_delay,
        "cancelled": cancelled,
        "diverted": diverted,
        "carrier": "XX",
        "flight_number": 1,
        "late_aircraft_delay": 0.0,
        "carrier_delay": 0.0,
        "weather_delay": 0.0,
        "nas_delay": 0.0,
    }


def frame(rows):
    df = pd.DataFrame(rows)
    df["tail"] = df["tail"].astype("string")
    return df


def test_pairs_consecutive_flights_of_one_aircraft():
    df = frame([
        flight("N1", "2025-01-01", "AAA", "BBB", "08:00", "10:00"),
        flight("N1", "2025-01-01", "BBB", "CCC", "11:00", "13:00"),
    ])
    t = build_turnarounds(df)
    assert len(t) == 1
    assert t.loc[0, "airport"] == "BBB"
    assert t.loc[0, "sched_ground_min"] == 60


def test_does_not_pair_across_different_aircraft():
    df = frame([
        flight("N1", "2025-01-01", "AAA", "BBB", "08:00", "10:00"),
        flight("N2", "2025-01-01", "BBB", "CCC", "11:00", "13:00"),
    ])
    assert len(build_turnarounds(df)) == 0


def test_does_not_pair_when_aircraft_did_not_continue_from_where_it_landed():
    """A gap in the data (e.g. a ferry flight) must not become a turnaround."""
    df = frame([
        flight("N1", "2025-01-01", "AAA", "BBB", "08:00", "10:00"),
        flight("N1", "2025-01-01", "ZZZ", "CCC", "11:00", "13:00"),
    ])
    assert len(build_turnarounds(df)) == 0


def test_overnight_inbound_gets_next_day_arrival():
    """A red-eye's BTS date is its *departure* date; the turn is the day after."""
    df = frame([
        flight("N1", "2025-01-01", "AAA", "BBB", "23:00", "01:30"),
        flight("N1", "2025-01-02", "BBB", "CCC", "02:30", "05:00"),
    ])
    t = build_turnarounds(df)
    assert len(t) == 1
    assert t.loc[0, "in_crs_arr_dt"] == pd.Timestamp("2025-01-02 01:30")
    assert t.loc[0, "sched_ground_min"] == 60


def test_orders_by_schedule_not_row_order():
    df = frame([
        flight("N1", "2025-01-01", "BBB", "CCC", "11:00", "13:00"),
        flight("N1", "2025-01-01", "AAA", "BBB", "08:00", "10:00"),
    ])
    t = build_turnarounds(df)
    assert len(t) == 1
    assert t.loc[0, "airport"] == "BBB"


def test_cancelled_and_diverted_flights_are_excluded():
    df = frame([
        flight("N1", "2025-01-01", "AAA", "BBB", "08:00", "10:00", cancelled=True),
        flight("N1", "2025-01-01", "BBB", "CCC", "11:00", "13:00"),
        flight("N1", "2025-01-01", "CCC", "DDD", "14:00", "16:00", diverted=True),
    ])
    assert len(build_turnarounds(df)) == 0


def test_long_ground_time_is_dropped_as_overnight_parking():
    df = frame([
        flight("N1", "2025-01-01", "AAA", "BBB", "08:00", "10:00"),
        flight("N1", "2025-01-01", "BBB", "CCC", "21:00", "23:00"),
    ])
    assert len(build_turnarounds(df, max_ground_min=8 * 60)) == 0
    assert len(build_turnarounds(df, max_ground_min=None)) == 1


def test_warns_when_a_requested_airport_is_not_in_the_dataset(caplog):
    """BTS is US domestic only; asking for YYZ must not fail silently."""
    df = frame([
        flight("N1", "2025-01-01", "AAA", "BBB", "08:00", "10:00"),
        flight("N1", "2025-01-01", "BBB", "CCC", "11:00", "13:00"),
    ])
    with caplog.at_level("WARNING"):
        t = build_turnarounds(df, airports=["BBB", "YYZ"])
    assert len(t) == 1
    assert "YYZ" in caplog.text
    assert "BBB" not in caplog.text


def test_airport_filter_applies_to_the_turn_airport():
    df = frame([
        flight("N1", "2025-01-01", "AAA", "BBB", "08:00", "10:00"),
        flight("N1", "2025-01-01", "BBB", "CCC", "11:00", "13:00"),
    ])
    assert len(build_turnarounds(df, airports=["BBB"])) == 1
    assert len(build_turnarounds(df, airports=["AAA"])) == 0


@pytest.mark.parametrize(
    "arr_delay,dep_delay,out_arr_delay,on_time,dep_late,arr_late,recovered",
    [
        (0.0, 0.0, 0.0, True, False, False, False),
        (5.0, 20.0, 3.0, True, True, False, True),      # left late, caught up
        (5.0, 20.0, 40.0, True, True, True, False),     # left late, stayed late
        (30.0, 45.0, 50.0, False, True, True, False),   # inherited
    ],
)
def test_outcome_labels(
    arr_delay, dep_delay, out_arr_delay, on_time, dep_late, arr_late, recovered
):
    df = frame([
        flight("N1", "2025-01-01", "AAA", "BBB", "08:00", "10:00", arr_delay=arr_delay),
        flight("N1", "2025-01-01", "BBB", "CCC", "11:00", "13:00",
               dep_delay=dep_delay, arr_delay=out_arr_delay),
    ])
    t = label_turnarounds(build_turnarounds(df))
    assert bool(t.loc[0, "in_on_time"]) is on_time
    assert bool(t.loc[0, "out_dep_late"]) is dep_late
    assert bool(t.loc[0, "out_arr_late"]) is arr_late
    assert bool(t.loc[0, "out_recovered"]) is recovered
