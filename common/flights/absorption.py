"""Which departure delays actually reach the passenger?

A flight that pushes back 30 minutes late and still lands on time cost nobody
anything: the schedule had enough padding in it to swallow the delay. A flight
that pushes back 30 minutes late and lands 30 minutes late passed the whole
delay through. The difference is what this module measures.

For a flight leaving ``D`` minutes late and arriving ``A`` minutes late:

======================  ====================================================
``A <= 0``              fully absorbed -- unabsorbed is 0
``0 < A < D``           partly absorbed -- unabsorbed is ``A``
``A >= D``              fully unabsorbed -- unabsorbed is ``D``
======================  ====================================================

So ``unabsorbed = clip(A, 0, D)``, and ``absorbed = D - unabsorbed``.

The cap at ``D`` matters: a flight that leaves 10 late and lands 40 late picked
up 30 minutes *en route*, which is airspace or weather, not something the origin
airport did. Only the part of the arrival delay the departure could account for
is attributed to the origin.

Flights that leave on or ahead of schedule have no departure delay to absorb, so
they contribute 0 -- whatever happens to them later is not the origin's doing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_absorption(flights: pd.DataFrame) -> pd.DataFrame:
    """Add per-flight absorption columns.

    Cancelled and diverted flights are dropped: they have no arrival to compare
    against, and a cancellation is a different kind of harm than a late arrival.
    """
    df = flights[
        ~flights["cancelled"]
        & ~flights["diverted"]
        & flights["dep_delay"].notna()
        & flights["arr_delay"].notna()
    ].copy()

    dep_late = df["dep_delay"].clip(lower=0)
    df["dep_delay_pos"] = dep_late
    # Only the portion of arrival lateness the departure delay could explain.
    df["unabsorbed_min"] = df["arr_delay"].clip(lower=0).clip(upper=dep_late)
    df["absorbed_min"] = dep_late - df["unabsorbed_min"]
    return df


def _summary(g: pd.DataFrame, late_min: float) -> pd.Series:
    dep_total = g["dep_delay_pos"].sum()
    unabsorbed_total = g["unabsorbed_min"].sum()
    late = g[g["dep_delay_pos"] >= late_min]
    return pd.Series(
        {
            "flights": len(g),
            # Averaged over every departure, so this is the airport's overall
            # contribution to passenger lateness per flight it sends out.
            "mean_dep_delay_min": g["dep_delay_pos"].mean(),
            "mean_unabsorbed_min": g["unabsorbed_min"].mean(),
            "mean_absorbed_min": g["absorbed_min"].mean(),
            # Of all the departure delay generated here, how much the network
            # managed to swallow before anyone landed.
            "absorbed_share": (
                float((dep_total - unabsorbed_total) / dep_total)
                if dep_total
                else np.nan
            ),
            "late_dep_rate": float((g["dep_delay_pos"] >= late_min).mean()),
            # Conditional view: given a flight did leave late, how much of that
            # lateness survived to the destination.
            "mean_unabsorbed_given_late_min": (
                late["unabsorbed_min"].mean() if len(late) else np.nan
            ),
        }
    )


def airport_absorption(
    flights: pd.DataFrame,
    airports: list[str] | None = None,
    min_flights: int = 500,
    late_min: float = 15.0,
) -> pd.DataFrame:
    """Per-airport unabsorbed delay, worst first.

    Attributed to the **origin**: the delay starts at the airport the flight
    leaves from, and the question is how much of it is still there when the
    aircraft reaches somewhere else.

    Parameters
    ----------
    flights:
        Output of :func:`add_absorption`.
    airports:
        Restrict to these IATA codes. ``None`` = all.
    min_flights:
        Drop airports thinner than this.
    late_min:
        Threshold for the conditional "given it left late" columns.
    """
    df = flights.assign(airport=flights["origin"].astype(str))
    if airports is not None:
        df = df[df["airport"].isin(airports)]

    out = (
        df.groupby("airport", observed=True)
        .apply(_summary, late_min=late_min, include_groups=False)
        .reset_index()
    )
    out = out[out["flights"] >= min_flights]
    return out.sort_values("mean_unabsorbed_min", ascending=False).reset_index(drop=True)
