"""How expensive is an airport?

The obvious shorthand -- average dollars per mile out of an airport -- is
mostly a measure of *route length*, not price level. Fares have a large fixed
component, so cents per mile falls steeply with distance: a 300-mile hop is
several times more expensive per mile than a transcon on the same carrier at
the same price level. An airport whose network is short-haul heavy therefore
looks expensive even when every one of its fares is unremarkable.

So this module reports two numbers:

``dollars_per_mile``
    The raw shorthand, passenger-weighted. Easy to explain, but reflects the
    airport's distance mix as much as its pricing.

``price_index``
    The same fares compared against what the *national* market charges for
    trips of the same length. 1.00 is exactly average; 1.15 means passengers
    pay 15% more than comparable-distance trips cost elsewhere. This is the
    number to use when ranking airports by expensiveness.

Every average here is weighted by ``passengers``, because a DB1B row is a group
of tickets rather than one ticket.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: Distance bands for the national baseline. Narrow where the curve is steep.
DISTANCE_BANDS: tuple[float, ...] = (0, 250, 500, 750, 1000, 1500, 2000, 3000, 12000)

#: Below this, the mile denominator is small enough that dollars-per-mile is
#: dominated by fixed costs and becomes noise.
MIN_DISTANCE_MI = 100.0

#: Trim this share off each tail of the dollars-per-mile distribution. DB1B is
#: a raw sample and contains keying errors in both directions.
TRIM_QUANTILE = 0.001


def prepare(
    fares: pd.DataFrame,
    include_bulk: bool = False,
    min_distance_mi: float = MIN_DISTANCE_MI,
    trim_quantile: float = TRIM_QUANTILE,
) -> pd.DataFrame:
    """Clean the raw fare table and add ``dollars_per_mile``.

    Bulk fares are excluded by default, following DOT's own guidance for fare
    averages: they are negotiated or opaque tickets whose recorded price does
    not correspond to what a passenger would pay.
    """
    df = fares.copy()
    if not include_bulk and "bulk_fare" in df.columns:
        df = df[~df["bulk_fare"].fillna(False).astype(bool)]

    df = df[
        (df["distance_mi"] >= min_distance_mi)
        & (df["fare_usd"] > 0)
        & (df["passengers"] > 0)
    ].copy()

    df["dollars_per_mile"] = df["fare_usd"] / df["distance_mi"]

    if trim_quantile:
        lo, hi = df["dollars_per_mile"].quantile([trim_quantile, 1 - trim_quantile])
        df = df[df["dollars_per_mile"].between(lo, hi)].copy()

    df["distance_band"] = pd.cut(
        df["distance_mi"], bins=list(DISTANCE_BANDS), right=False
    )
    return df


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    total = weights.sum()
    return float((values * weights).sum() / total) if total else float("nan")


def national_baseline(fares: pd.DataFrame) -> pd.DataFrame:
    """Passenger-weighted dollars per mile by distance band, across all markets.

    This is the yardstick :func:`airport_fare_rates` measures each airport
    against.
    """
    return (
        fares.groupby("distance_band", observed=True)
        .apply(
            lambda g: pd.Series(
                {
                    "passengers": g["passengers"].sum(),
                    "dollars_per_mile": _weighted_mean(
                        g["dollars_per_mile"], g["passengers"]
                    ),
                    "mean_fare_usd": _weighted_mean(g["fare_usd"], g["passengers"]),
                    "median_distance_mi": g["distance_mi"].median(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )


def add_expected_fare(fares: pd.DataFrame, baseline: pd.DataFrame | None = None):
    """Attach what each market would cost at national rates for its distance."""
    baseline = national_baseline(fares) if baseline is None else baseline
    rate = baseline.set_index("distance_band")["dollars_per_mile"]
    df = fares.copy()
    df["expected_dpm"] = df["distance_band"].map(rate).astype(float)
    df["expected_fare_usd"] = df["expected_dpm"] * df["distance_mi"]
    return df


def airport_fare_rates(
    fares: pd.DataFrame,
    airports: list[str] | None = None,
    direction: str = "origin",
    min_passengers: float = 1000.0,
) -> pd.DataFrame:
    """Per-airport fare summary, most expensive first.

    Parameters
    ----------
    fares:
        Output of :func:`prepare`.
    airports:
        Restrict to these IATA codes. ``None`` = all.
    direction:
        ``"origin"`` for fares on trips departing the airport (the default, and
        what "expensive to fly out of" means), ``"dest"`` for arrivals, or
        ``"either"`` to count both endpoints.
    min_passengers:
        Drop airports thinner than this; DB1B is a 10% sample, so small
        airports carry wide error bars.

    Returns
    -------
    One row per airport with the raw ``dollars_per_mile``, the
    distance-controlled ``price_index``, and the mix statistics that explain
    the difference between them.
    """
    if direction not in {"origin", "dest", "either"}:
        raise ValueError(f"direction must be origin, dest or either; got {direction!r}")

    df = add_expected_fare(fares)

    if direction == "either":
        # One row per (market, endpoint), so a market counts toward both.
        df = pd.concat(
            [df.assign(airport=df["origin"]), df.assign(airport=df["dest"])],
            ignore_index=True,
        )
    else:
        df = df.assign(airport=df[direction])

    df["airport"] = df["airport"].astype(str)
    if airports is not None:
        df = df[df["airport"].isin(airports)]

    out = (
        df.groupby("airport", observed=True)
        .apply(_airport_summary, include_groups=False)
        .reset_index()
    )
    out = out[out["passengers"] >= min_passengers]
    return out.sort_values("price_index", ascending=False).reset_index(drop=True)


def _airport_summary(g: pd.DataFrame) -> pd.Series:
    pax = g["passengers"]
    actual = (g["fare_usd"] * pax).sum()
    expected = (g["expected_fare_usd"] * pax).sum()
    return pd.Series(
        {
            "passengers": pax.sum(),
            "markets": len(g),
            "mean_fare_usd": _weighted_mean(g["fare_usd"], pax),
            "dollars_per_mile": _weighted_mean(g["dollars_per_mile"], pax),
            "median_distance_mi": g["distance_mi"].median(),
            # Distance-controlled: what passengers actually paid, over what
            # comparable-length trips cost nationally.
            "price_index": float(actual / expected) if expected else np.nan,
            "nonstop_share": _weighted_mean((g["coupons"] == 1).astype(float), pax)
            if "coupons" in g
            else np.nan,
        }
    )


def distance_curve(fares: pd.DataFrame) -> pd.DataFrame:
    """The national dollars-per-mile curve -- the reason ``price_index`` exists."""
    return national_baseline(fares)
