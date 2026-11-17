"""Tests for the fare analysis.

The distance control is the part that matters: raw dollars-per-mile is mostly a
measure of route length, so the tests below pin the behaviour that separates
"this airport is expensive" from "this airport flies short routes".
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.flights import FareSchema  # noqa: E402
from common.flights.fares import (  # noqa: E402
    airport_fare_rates,
    national_baseline,
    prepare,
)


def market(origin, dest, fare, distance, passengers=100.0, bulk=False, coupons=1):
    return {
        "period": "2025Q1",
        "origin": origin,
        "dest": dest,
        "fare_usd": fare,
        "distance_mi": distance,
        "passengers": passengers,
        "carrier": "XX",
        "coupons": coupons,
        "bulk_fare": bulk,
        "nonstop_mi": distance,
    }


def frame(rows):
    return pd.DataFrame(rows)


def test_dollars_per_mile_is_fare_over_distance():
    df = prepare(frame([market("ATL", "LAX", 400.0, 2000.0)]), trim_quantile=0)
    assert df.loc[0, "dollars_per_mile"] == pytest.approx(0.2)


def test_bulk_fares_are_excluded_by_default():
    rows = frame([
        market("ATL", "LAX", 400.0, 2000.0),
        market("ATL", "LAX", 5.0, 2000.0, bulk=True),
    ])
    assert len(prepare(rows, trim_quantile=0)) == 1
    assert len(prepare(rows, include_bulk=True, trim_quantile=0)) == 2


def test_very_short_markets_are_dropped():
    """Tiny denominators make dollars-per-mile explode into noise."""
    rows = frame([
        market("ATL", "LAX", 400.0, 2000.0),
        market("ATL", "MCO", 150.0, 50.0),
    ])
    out = prepare(rows, trim_quantile=0)
    assert set(out["dest"]) == {"LAX"}


def test_nonpositive_fares_are_dropped():
    rows = frame([
        market("ATL", "LAX", 400.0, 2000.0),
        market("ATL", "ORD", 0.0, 600.0),
    ])
    assert set(prepare(rows, trim_quantile=0)["dest"]) == {"LAX"}


def test_averages_are_passenger_weighted():
    """A row is a group of tickets; ignoring the weight skews every average."""
    rows = frame([
        market("ATL", "LAX", 100.0, 1000.0, passengers=1),
        market("ATL", "LAX", 200.0, 1000.0, passengers=99),
    ])
    out = airport_fare_rates(prepare(rows, trim_quantile=0), min_passengers=0)
    assert out.loc[0, "mean_fare_usd"] == pytest.approx(199.0)


def test_price_index_is_one_when_an_airport_matches_the_national_rate():
    rows = frame([
        market("ATL", "LAX", 400.0, 2000.0),
        market("DEN", "LAX", 400.0, 2000.0),
    ])
    out = airport_fare_rates(prepare(rows, trim_quantile=0), min_passengers=0)
    assert out["price_index"].tolist() == pytest.approx([1.0, 1.0])


def test_price_index_separates_expensive_from_merely_short_haul():
    """The whole reason the index exists.

    SHORT flies only short routes at the going rate; PRICEY flies the same long
    route as everyone else but charges double. Raw dollars-per-mile ranks SHORT
    as more expensive; the index correctly ranks PRICEY.

    BASE carries most of the traffic so that it sets the national rate. The
    baseline includes the airport being measured -- as any index does -- so a
    thin band would let PRICEY drag its own yardstick upward and understate it.
    """
    rows = frame([
        # National long-haul rate: $0.20/mi. National short-haul rate: $0.50/mi.
        market("BASE", "LAX", 400.0, 2000.0, passengers=100_000),
        market("BASE", "ORD", 150.0, 300.0, passengers=100_000),
        # Short-haul-only airport, charging exactly the going short-haul rate.
        market("SHORT", "ORD", 150.0, 300.0, passengers=1000),
        # Long-haul airport charging double the going long-haul rate.
        market("PRICEY", "LAX", 800.0, 2000.0, passengers=1000),
    ])
    out = airport_fare_rates(prepare(rows, trim_quantile=0), min_passengers=0)
    rates = out.set_index("airport")

    # Raw dollars-per-mile gets it wrong ...
    assert rates.loc["SHORT", "dollars_per_mile"] > rates.loc["PRICEY", "dollars_per_mile"]
    # ... the distance-controlled index gets it right.
    assert rates.loc["SHORT", "price_index"] == pytest.approx(1.0)
    assert rates.loc["PRICEY", "price_index"] == pytest.approx(2.0, rel=0.02)
    assert out.iloc[0]["airport"] == "PRICEY"  # sorted most expensive first


def test_direction_selects_which_endpoint_counts():
    rows = frame([market("ATL", "LAX", 400.0, 2000.0)])
    prepared = prepare(rows, trim_quantile=0)
    assert set(airport_fare_rates(prepared, min_passengers=0)["airport"]) == {"ATL"}
    assert set(
        airport_fare_rates(prepared, direction="dest", min_passengers=0)["airport"]
    ) == {"LAX"}
    assert set(
        airport_fare_rates(prepared, direction="either", min_passengers=0)["airport"]
    ) == {"ATL", "LAX"}


def test_bad_direction_is_rejected():
    prepared = prepare(frame([market("ATL", "LAX", 400.0, 2000.0)]), trim_quantile=0)
    with pytest.raises(ValueError, match="direction must be"):
        airport_fare_rates(prepared, direction="sideways")


def test_thin_airports_are_dropped():
    rows = frame([
        market("BIG", "LAX", 400.0, 2000.0, passengers=5000),
        market("TINY", "LAX", 400.0, 2000.0, passengers=10),
    ])
    out = airport_fare_rates(prepare(rows, trim_quantile=0), min_passengers=1000)
    assert set(out["airport"]) == {"BIG"}


def test_national_baseline_is_per_distance_band():
    rows = frame([
        market("A", "B", 150.0, 300.0),
        market("C", "D", 400.0, 2000.0),
    ])
    base = national_baseline(prepare(rows, trim_quantile=0))
    assert len(base) == 2
    assert base["dollars_per_mile"].max() == pytest.approx(0.5)
    assert base["dollars_per_mile"].min() == pytest.approx(0.2)


def test_fare_schema_declares_the_weight_column():
    """Forgetting `passengers` would silently unweight every average."""
    assert "passengers" in FareSchema.required()
    assert "fare_usd" in FareSchema.required()
    assert "distance_mi" in FareSchema.required()
