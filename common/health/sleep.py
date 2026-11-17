"""Working with Google Health ``sleep`` rows.

The raw rows are sleep *sessions*, naps included, with every stage stretch
packed into a JSON column. These helpers unpack them:

* :func:`stage_table`    -- every stage stretch of every session, one row each
* :func:`stage_segments` -- just the stretches of one stage (``"deep"``...)
* :func:`nightly`        -- one row per night with minutes in each stage

Every row is dated by ``night``, the local date the session *ended* on (the
morning you woke up). That matches the only way the API lets you filter sleep,
so a night can't fall between two months.
"""

from __future__ import annotations

import json

import pandas as pd

from .timeutil import wall_clock

STAGES = ("deep", "light", "rem", "awake")
#: Stages that count as asleep, each of which gets a ``<stage>_share`` column.
SLEEPING = ("deep", "light", "rem")


def main_sleeps(sleep: pd.DataFrame) -> pd.DataFrame:
    """Drop naps and anything not flagged as a main sleep."""
    df = sleep
    if "metadata_main_sleep" in df:
        df = df[df["metadata_main_sleep"].eq(True)]
    if "metadata_nap" in df:
        df = df[~df["metadata_nap"].eq(True)]
    return df


def stage_table(sleep: pd.DataFrame) -> pd.DataFrame:
    """Every stage stretch of every session, one row each.

    Columns: ``session`` (row index in ``sleep``), ``night``, ``stage``
    (lower case: deep/light/rem/awake), ``start_local``, ``end_local``,
    ``minutes``. Sessions recorded without stages contribute nothing.
    """
    rows = []
    if "stages" in sleep:
        for idx, night, packed in zip(sleep.index, sleep["end_local"].dt.normalize(),
                                      sleep["stages"]):
            if not isinstance(packed, str):
                continue
            for seg in json.loads(packed):
                rows.append({
                    "session": idx,
                    "night": night,
                    "stage": seg.get("type", "").lower(),
                    "start_local": wall_clock(seg["startTime"], seg.get("startUtcOffset")),
                    "end_local": wall_clock(seg["endTime"], seg.get("endUtcOffset")),
                })
    out = pd.DataFrame(rows, columns=["session", "night", "stage", "start_local", "end_local"])
    out["minutes"] = (out["end_local"] - out["start_local"]) / pd.Timedelta(minutes=1)
    return out.sort_values("start_local").reset_index(drop=True)


def stage_segments(sleep: pd.DataFrame, stage: str = "deep") -> pd.DataFrame:
    """Every stretch of ``stage``: ``night``, ``start_local``, ``end_local``,
    ``minutes``. Naps are kept, since this answers "when was I in deep sleep",
    not "how was last night"."""
    t = stage_table(sleep)
    t = t[t["stage"] == stage.lower()]
    return t[["night", "start_local", "end_local", "minutes"]].reset_index(drop=True)


def nightly(sleep: pd.DataFrame) -> pd.DataFrame:
    """One row per night, keyed by the local date you woke up (``night``).

    Only main sleeps count: naps are dropped, and if a night still has more than
    one main sleep the longest one wins. Stage columns are ``<stage>_min``, and
    ``<stage>_share`` is that stage's fraction of time asleep;
    nights recorded without stages (``type == "CLASSIC"``, e.g. the band was
    loose) have NaN for them rather than zero, so they can't drag averages down.

    ``bed_local``/``wake_local`` are wall-clock times wherever you slept (the
    watch follows your phone's time zone, so they jump when you travel).
    ``bed_time``/``wake_time`` are the same instants in UTC: use those to line
    sleep up with another source's timestamps. ``utc_offset_h`` is the offset
    the watch was on when you woke (-8 in PST, -5 in New York), so a night away
    from home's time zone shows up as a different value.
    """
    cols = ["night", "bed_local", "wake_local", "bed_time", "wake_time", "utc_offset_h",
            "asleep_min",
            *(f"{s}_min" for s in STAGES), *(f"{s}_share" for s in SLEEPING)]
    if sleep.empty:
        return pd.DataFrame(columns=cols)
    df = main_sleeps(sleep)

    stage_min = df["summary_stages_summary"].map(_stage_minutes).apply(pd.Series)
    staged = df["type"].eq("STAGES")
    out = pd.DataFrame({
        "night": df["end_local"].dt.normalize(),
        "bed_local": df["start_local"],
        "wake_local": df["end_local"],
        "bed_time": df["start_time"],
        "wake_time": df["end_time"],
        "utc_offset_h": (df["end_local"] - df["end_time"].dt.tz_localize(None))
        / pd.Timedelta(hours=1),
        "asleep_min": df["summary_minutes_asleep"].astype(float),
    })
    for stage in STAGES:
        col = stage_min.get(stage, pd.Series(index=df.index, dtype=float))
        out[f"{stage}_min"] = col.where(staged)
    for stage in SLEEPING:
        out[f"{stage}_share"] = out[f"{stage}_min"] / out["asleep_min"]

    out = out.sort_values("asleep_min").drop_duplicates("night", keep="last")
    return out.sort_values("night").reset_index(drop=True)[cols]


def _stage_minutes(packed) -> dict[str, float]:
    if not isinstance(packed, str):
        return {}
    return {s["type"].lower(): float(s.get("minutes", 0)) for s in json.loads(packed)}
