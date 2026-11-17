"""Calendar-month period keys, shared by every monthly-chunked source.

Sources that fetch by date range still cache by month (``"2025-01"``): a month
is small enough to download in one go and large enough that a year is twelve
files rather than 365. A month is only *closed* -- safe to cache forever --
once its last day is far enough in the past that the upstream won't revise it.
"""

from __future__ import annotations

import datetime as dt


def parse_month(key: str) -> tuple[dt.date, dt.date]:
    """``"2025-01"`` -> (first day, first day of the *next* month)."""
    year, month = (int(p) for p in key.split("-"))
    start = dt.date(year, month, 1)
    end = dt.date(year + (month == 12), month % 12 + 1, 1)
    return start, end


def month_of(day: dt.date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def months_between(start: dt.date | str, end: dt.date | str) -> list[str]:
    """Every month key touched by the inclusive range ``start``..``end``."""
    start, end = _as_date(start), _as_date(end)
    if end < start:
        raise ValueError(f"end {end} is before start {start}")
    keys, cur = [], dt.date(start.year, start.month, 1)
    while cur <= end:
        keys.append(month_of(cur))
        cur = parse_month(keys[-1])[1]
    return keys


def month_is_closed(key: str, lag_days: int = 0, today: dt.date | None = None) -> bool:
    """True once the month ended at least ``lag_days`` before ``today``."""
    today = today or dt.date.today()
    _, end = parse_month(key)
    return end + dt.timedelta(days=lag_days) <= today


def _as_date(d: dt.date | str) -> dt.date:
    return d if isinstance(d, dt.date) else dt.date.fromisoformat(d)
