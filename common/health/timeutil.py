"""Timestamps as the Google Health API sends them.

Instants come as RFC 3339 strings, with the wearer's UTC offset alongside as a
duration string (``"-28800s"``). Every module here needs both forms, the
instant (tz-aware UTC) and the wall-clock time where it happened (naive
local), so both conversions live in one place.
"""

from __future__ import annotations

import pandas as pd


def utc(stamp: str) -> pd.Timestamp:
    """An RFC 3339 string as a tz-aware UTC timestamp."""
    t = pd.Timestamp(stamp)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def offset_seconds(offset: str | None) -> float:
    """``"-28800s"`` -> -28800.0; missing -> 0."""
    return float(offset.rstrip("s")) if offset else 0.0


def wall_clock(stamp: str | pd.Timestamp, offset: str | None) -> pd.Timestamp:
    """Naive local time where the event happened: the instant shifted by the
    recorded UTC offset."""
    t = stamp if isinstance(stamp, pd.Timestamp) else utc(stamp)
    t = utc(str(t)) if t.tzinfo is None else t.tz_convert("UTC")
    return (t + pd.Timedelta(seconds=offset_seconds(offset))).tz_localize(None)
