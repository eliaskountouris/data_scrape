"""Tests for unabsorbed-delay accounting.

The definition is the whole analysis: unabsorbed = clip(arrival delay, 0,
departure delay). Each branch of that clip is pinned below, because getting it
wrong produces numbers that still look plausible.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.flights import add_absorption, airport_absorption  # noqa: E402


def flight(origin="AAA", dest="BBB", dep_delay=0.0, arr_delay=0.0,
           cancelled=False, diverted=False):
    return {
        "origin": origin,
        "dest": dest,
        "dep_delay": dep_delay,
        "arr_delay": arr_delay,
        "cancelled": cancelled,
        "diverted": diverted,
    }


def frame(rows):
    return pd.DataFrame(rows)


@pytest.mark.parametrize(
    "dep_delay,arr_delay,unabsorbed,absorbed",
    [
        # Left 30 late, arrived on time: the schedule swallowed all of it.
        (30.0, 0.0, 0.0, 30.0),
        (30.0, -12.0, 0.0, 30.0),
        # Left 30 late, arrived 30 late: none of it absorbed.
        (30.0, 30.0, 30.0, 0.0),
        # Left 30 late, arrived 10 late: two thirds absorbed.
        (30.0, 10.0, 10.0, 20.0),
        # Left 10 late, arrived 40 late: 30 minutes picked up en route, which is
        # not the origin airport's doing -- attribution caps at the 10 it caused.
        (10.0, 40.0, 10.0, 0.0),
        # Left early and arrived late: no departure delay to absorb.
        (-5.0, 20.0, 0.0, 0.0),
        # Left early, arrived early.
        (-5.0, -20.0, 0.0, 0.0),
        # Exactly on time.
        (0.0, 0.0, 0.0, 0.0),
    ],
)
def test_absorption_arithmetic(dep_delay, arr_delay, unabsorbed, absorbed):
    df = add_absorption(frame([flight(dep_delay=dep_delay, arr_delay=arr_delay)]))
    assert df.loc[0, "unabsorbed_min"] == pytest.approx(unabsorbed)
    assert df.loc[0, "absorbed_min"] == pytest.approx(absorbed)


def test_unabsorbed_never_exceeds_departure_delay():
    df = add_absorption(frame([
        flight(dep_delay=d, arr_delay=a)
        for d in (-10, 0, 5, 60)
        for a in (-30, 0, 15, 120)
    ]))
    assert (df["unabsorbed_min"] <= df["dep_delay_pos"] + 1e-9).all()
    assert (df["unabsorbed_min"] >= 0).all()
    assert (df["absorbed_min"] >= 0).all()


def test_cancelled_and_diverted_flights_are_excluded():
    df = add_absorption(frame([
        flight(dep_delay=30.0, arr_delay=30.0, cancelled=True),
        flight(dep_delay=30.0, arr_delay=30.0, diverted=True),
        flight(dep_delay=30.0, arr_delay=30.0),
    ]))
    assert len(df) == 1


def test_missing_delays_are_excluded():
    df = add_absorption(frame([
        flight(dep_delay=None, arr_delay=10.0),
        flight(dep_delay=10.0, arr_delay=None),
        flight(dep_delay=10.0, arr_delay=10.0),
    ]))
    assert len(df) == 1


def test_absorption_is_attributed_to_the_origin():
    """The delay starts where the flight leaves from."""
    df = add_absorption(frame([flight(origin="AAA", dest="BBB", dep_delay=30, arr_delay=30)]))
    out = airport_absorption(df, min_flights=1)
    assert out["airport"].tolist() == ["AAA"]


def test_airport_summary_averages_over_every_departure():
    """On-time flights are part of the denominator: the metric is the airport's
    contribution per flight it sends out, not per late flight."""
    df = add_absorption(frame([
        flight(dep_delay=40.0, arr_delay=40.0),
        flight(dep_delay=0.0, arr_delay=0.0),
        flight(dep_delay=0.0, arr_delay=0.0),
        flight(dep_delay=0.0, arr_delay=0.0),
    ]))
    out = airport_absorption(df, min_flights=1)
    assert out.loc[0, "mean_unabsorbed_min"] == pytest.approx(10.0)
    assert out.loc[0, "mean_unabsorbed_given_late_min"] == pytest.approx(40.0)


def test_absorbed_share_is_over_total_delay_generated():
    df = add_absorption(frame([
        flight(dep_delay=100.0, arr_delay=25.0),   # 75 absorbed
        flight(dep_delay=100.0, arr_delay=100.0),  # 0 absorbed
    ]))
    out = airport_absorption(df, min_flights=1)
    assert out.loc[0, "absorbed_share"] == pytest.approx(0.375)


def test_thin_airports_are_dropped():
    df = add_absorption(frame(
        [flight(origin="BIG", dep_delay=10, arr_delay=5)] * 10
        + [flight(origin="TINY", dep_delay=10, arr_delay=5)]
    ))
    out = airport_absorption(df, min_flights=5)
    assert out["airport"].tolist() == ["BIG"]
