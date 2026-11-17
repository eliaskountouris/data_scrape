"""Daily exercise from Google Health ``exercise`` sessions.

The same workout is often recorded twice -- once by the watch, once by the
phone or Health Connect -- as two overlapping sessions with different
durations. Summing them would double-count, so overlapping sessions are
merged into one bout and the bout counts once, at the longest active
duration any of its recordings reports.
"""

from __future__ import annotations

import pandas as pd


def exercise_bouts(exercise: pd.DataFrame) -> pd.DataFrame:
    """One row per distinct workout, duplicates merged.

    Columns: ``day`` (local date it started), ``start_local``, ``end_local``,
    ``minutes`` (active time, falling back to elapsed time when a recording
    has no active duration), ``types`` (the exercise types merged into it),
    ``recordings`` (how many sessions were merged).
    """
    cols = ["day", "start_local", "end_local", "minutes", "types", "recordings"]
    if exercise.empty:
        return pd.DataFrame(columns=cols)
    df = exercise.sort_values("start_local").reset_index(drop=True)
    elapsed = (df["end_local"] - df["start_local"]) / pd.Timedelta(minutes=1)
    active = df["active_duration_s"] / 60 if "active_duration_s" in df else elapsed
    df = df.assign(_minutes=active.fillna(elapsed))

    # A session starting before the running bout ends belongs to that bout.
    bout = (df["start_local"] >= df["end_local"].cummax().shift()).cumsum()
    kind = df["exercise_type"] if "exercise_type" in df else pd.Series("", index=df.index)
    out = df.assign(_bout=bout, _type=kind).groupby("_bout").agg(
        start_local=("start_local", "min"),
        end_local=("end_local", "max"),
        minutes=("_minutes", "max"),
        types=("_type", lambda s: ", ".join(sorted(set(s.dropna().astype(str))))),
        recordings=("_minutes", "size"),
    ).reset_index(drop=True)
    out.insert(0, "day", out["start_local"].dt.normalize())
    return out[cols]


def daily_exercise(exercise: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    """Minutes of exercise per local day, duplicates merged.

    With ``start``/``end`` every day in that inclusive range gets a row, with
    0 for rest days, because a day without a workout is a real zero, not
    missing data.
    """
    bouts = exercise_bouts(exercise)
    per_day = bouts.groupby("day").agg(exercise_min=("minutes", "sum"),
                                       workouts=("minutes", "size"))
    if start is not None and end is not None:
        days = pd.date_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize())
        per_day = per_day.reindex(days, fill_value=0)
    per_day.index.name = "day"
    return per_day.reset_index()
