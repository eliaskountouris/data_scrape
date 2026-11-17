"""Turnaround analysis: does an on-time arrival still leave late?

The unit of analysis is a *turnaround*: two consecutive flights by the same
aircraft where the first one's destination is the second one's origin. Chaining
them lets us ask the question this toolkit was built for --

    of the flights that land on time at airport X, how many of those aircraft
    then depart late, and how many are still late when they reach the next
    destination?

Ordering is done on *scheduled* departure time. Actual times in the BTS feed are
local ``HHMM`` values that wrap around midnight, so they can't be sorted.
"""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

#: DOT's definition of "late": 15 minutes or more behind schedule.
DOT_LATE_MIN = 15.0

#: Turns longer than this are aircraft parked overnight/for maintenance, not a
#: real turnaround -- delay can't meaningfully propagate across them.
MAX_GROUND_MIN = 8 * 60

IN_COLS = [
    "carrier",
    "flight_number",
    "tail",
    "origin",
    "dest",
    "flight_date",
    "crs_dep_dt",
    "crs_dep_min",
    "crs_arr_min",
    "arr_delay",
    "dep_delay",
]
OUT_COLS = [
    "carrier",
    "flight_number",
    "origin",
    "dest",
    "flight_date",
    "crs_dep_dt",
    "dep_delay",
    "arr_delay",
    "late_aircraft_delay",
    "carrier_delay",
    "weather_delay",
    "nas_delay",
]


def _warn_about_missing(
    flights: pd.DataFrame, turns: pd.DataFrame, requested: list[str]
) -> None:
    """Say so when a requested airport contributes nothing.

    An airport that isn't in the loaded frame drops out silently and looks like
    a real result. Why it's absent is the provider layer's business -- see
    :meth:`common.flights.FlightData.coverage` -- so this only reports the fact.
    """
    served = set(flights["dest"].astype(str)) | set(flights["origin"].astype(str))
    absent = [a for a in requested if a not in served]
    if absent:
        log.warning(
            "no flights in the loaded data at: %s", ", ".join(sorted(absent))
        )

    have_turns = set(turns["airport"])
    empty = [a for a in requested if a in served and a not in have_turns]
    if empty:
        log.warning(
            "present in the data but produced no turnarounds: %s",
            ", ".join(sorted(empty)),
        )


def build_turnarounds(
    flights: pd.DataFrame,
    airports: list[str] | None = None,
    max_ground_min: float | None = MAX_GROUND_MIN,
) -> pd.DataFrame:
    """Pair each flight with the same aircraft's next flight.

    Parameters
    ----------
    flights:
        Tidy frame from :class:`common.flights.BTSOnTime`.
    airports:
        Restrict to turnarounds happening at these IATA codes. ``None`` = all.
    max_ground_min:
        Drop turns with more scheduled ground time than this (overnight parking).
        ``None`` keeps everything.

    Returns
    -------
    One row per turnaround, with ``in_*`` columns for the arriving flight and
    ``out_*`` for the departing one, plus ``airport`` and ``sched_ground_min``.
    """
    d = flights[
        ~flights["cancelled"]
        & ~flights["diverted"]
        & flights["tail"].notna()
        & (flights["tail"].str.strip() != "")
        & flights["arr_delay"].notna()
    ].copy()

    d = d.sort_values(["tail", "crs_dep_dt"], kind="stable").reset_index(drop=True)

    inbound = d[IN_COLS].add_prefix("in_")
    # shift(-1) inside each tail group gives that aircraft's next flight; the
    # last flight of each group becomes NaN and drops out below.
    outbound = (
        d.groupby("tail", observed=True, sort=False)[OUT_COLS]
        .shift(-1)
        .add_prefix("out_")
    )
    turns = pd.concat([inbound, outbound], axis=1)

    # A real turnaround continues from where the aircraft landed.
    turns = turns[
        turns["out_origin"].notna()
        & (turns["in_dest"].astype(str) == turns["out_origin"].astype(str))
    ].copy()

    turns["airport"] = turns["in_dest"].astype(str)
    if airports is not None:
        _warn_about_missing(flights, turns, airports)
        turns = turns[turns["airport"].isin(airports)].copy()

    # Scheduled arrival, in the turn airport's own local time. The calendar date
    # on a BTS row is the *departure* date, so a flight whose scheduled arrival
    # clock reads earlier than its departure clock landed the next day.
    crosses_midnight = turns["in_crs_arr_min"] < turns["in_crs_dep_min"]
    turns["in_crs_arr_dt"] = (
        turns["in_flight_date"]
        + pd.to_timedelta(turns["in_crs_arr_min"], unit="m")
        + pd.to_timedelta(crosses_midnight.astype(int), unit="D")
    )

    turns["sched_ground_min"] = (
        turns["out_crs_dep_dt"] - turns["in_crs_arr_dt"]
    ).dt.total_seconds() / 60.0

    # Negative ground time means the pairing is wrong (schedule quirk or a tail
    # number reused across aircraft); those rows are noise.
    turns = turns[turns["sched_ground_min"] >= 0]
    if max_ground_min is not None:
        turns = turns[turns["sched_ground_min"] <= max_ground_min]

    return turns.reset_index(drop=True)


def label_turnarounds(
    turns: pd.DataFrame,
    late_min: float = DOT_LATE_MIN,
    inbound_on_time_min: float | None = None,
) -> pd.DataFrame:
    """Add the boolean outcome columns the rate tables are built from.

    ``inbound_on_time_min`` defaults to ``late_min``, i.e. an inbound flight is
    "on time" exactly when it is not "late". Set it to ``0`` to require the
    stricter reading of on-time (at or before schedule).
    """
    threshold_in = late_min if inbound_on_time_min is None else inbound_on_time_min
    t = turns.copy()
    t["in_on_time"] = t["in_arr_delay"] < threshold_in
    t["in_late"] = t["in_arr_delay"] >= late_min
    t["out_dep_late"] = t["out_dep_delay"] >= late_min
    t["out_arr_late"] = t["out_arr_delay"] >= late_min
    # Did the outbound leg claw back the delay it left with?
    t["out_recovered"] = t["out_dep_late"] & ~t["out_arr_late"]
    return t


def _rates(g: pd.DataFrame) -> pd.Series:
    on_time = g[g["in_on_time"]]
    late = g[g["in_late"]]
    return pd.Series(
        {
            "turnarounds": len(g),
            "median_ground_min": g["sched_ground_min"].median(),
            "inbound_on_time_n": len(on_time),
            # The headline numbers: aircraft landed on time, then what?
            "ot_dep_late_rate": on_time["out_dep_late"].mean(),
            "ot_arr_late_rate": on_time["out_arr_late"].mean(),
            "ot_recovery_rate": (
                on_time.loc[on_time["out_dep_late"], "out_recovered"].mean()
                if on_time["out_dep_late"].any()
                else float("nan")
            ),
            "inbound_late_n": len(late),
            # Contrast group, so the headline numbers have a baseline.
            "late_dep_late_rate": late["out_dep_late"].mean(),
            "late_arr_late_rate": late["out_arr_late"].mean(),
        }
    )


def airport_delay_rates(
    turns: pd.DataFrame, min_turnarounds: int = 200
) -> pd.DataFrame:
    """Per-airport turnaround outcome rates, sorted worst-first.

    ``lift`` is how many times more likely a late departure is when the inbound
    aircraft arrived late rather than on time -- i.e. how much of the airport's
    departure delay is inherited rather than generated on the ground.
    """
    out = (
        turns.groupby("airport", observed=True)
        .apply(_rates, include_groups=False)
        .reset_index()
    )
    out = out[out["turnarounds"] >= min_turnarounds]
    out["lift"] = out["late_dep_late_rate"] / out["ot_dep_late_rate"]
    return out.sort_values("ot_dep_late_rate", ascending=False).reset_index(drop=True)


def ground_time_curve(
    turns: pd.DataFrame,
    edges: tuple[float, ...] = (0, 30, 45, 60, 90, 120, 180, 480),
) -> pd.DataFrame:
    """Late-departure rate as a function of scheduled ground time.

    Restricted to on-time arrivals, so what's left is the schedule's own
    tightness rather than inherited delay.
    """
    t = turns[turns["in_on_time"]].copy()
    t["ground_bucket"] = pd.cut(t["sched_ground_min"], bins=list(edges), right=False)
    return (
        t.groupby("ground_bucket", observed=True)
        .agg(
            turnarounds=("out_dep_late", "size"),
            dep_late_rate=("out_dep_late", "mean"),
            arr_late_rate=("out_arr_late", "mean"),
            median_dep_delay=("out_dep_delay", "median"),
        )
        .reset_index()
    )
