"""Google Health API -- your own Fitbit / Pixel Watch / Health Connect data.

The successor to the Fitbit Web API (switched off November 2026). Every data
type is read from the same endpoint::

    GET https://health.googleapis.com/v4/users/me/dataTypes/{type}/dataPoints

and comes back as a list of ``dataPoints``, each holding one union field named
after the type (``steps``, ``heartRate``, ``sleep``...). Each type is timed
one of three ways, and that decides both the filter syntax and the columns:

* **interval** -- ``start_time`` / ``end_time`` (steps, distance, sleep...)
* **sample**   -- one instant, ``time`` (heart rate, weight, SpO2...)
* **daily**    -- one ``date`` (resting heart rate, daily HRV...)

Cached by ``"<type>/<YYYY-MM>"``. The current month and the few days after it
are re-fetched on every load because devices sync late.

Reference: https://developers.google.com/health/reference/rest
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
from collections.abc import Iterable, Sequence
from pathlib import Path

import pandas as pd

from ..periods import month_is_closed, months_between, parse_month
from ..sources.base import Source
from .auth import GoogleHealthAuth
from .timeutil import utc, wall_clock

log = logging.getLogger(__name__)

API_ROOT = "https://health.googleapis.com"
#: The docs currently show both ``v4`` and ``v4beta`` paths; override with
#: ``$GOOGLE_HEALTH_API_VERSION`` if one of them starts returning 404.
API_VERSION = os.environ.get("GOOGLE_HEALTH_API_VERSION", "v4")

#: Days after a month ends before it's trusted not to gain late-synced data.
SYNC_LAG_DAYS = 3

SAMPLE_TYPES = frozenset({
    "heart-rate", "heart-rate-variability", "weight", "body-fat", "height",
    "oxygen-saturation", "vo2-max", "run-vo2-max", "blood-glucose",
    "core-body-temperature", "respiratory-rate-sleep-summary",
    "skin-temperature-sensors", "symptoms", "moods", "ovulation-test",
})

#: Session types the API only lets you filter by *end* time. A night of sleep
#: therefore belongs to the date you woke up -- which is also how Fitbit dates it.
END_FILTER_TYPES = frozenset({"sleep"})

#: Types whose list endpoint caps pages at 25 instead of 10 000.
SMALL_PAGE_TYPES = frozenset({"sleep", "exercise"})

#: Handy defaults. Any type the API knows works -- these are just documented.
COMMON_TYPES = (
    "steps", "distance", "floors", "active-zone-minutes", "exercise", "sleep",
    "heart-rate", "daily-resting-heart-rate", "daily-heart-rate-variability",
    "weight", "body-fat", "oxygen-saturation",
)


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).replace("-", "_").lower()


def _camel(kebab: str) -> str:
    head, *rest = kebab.split("-")
    return head + "".join(p.title() for p in rest)


def kind_of(data_type: str) -> str:
    """``"interval"``, ``"sample"`` or ``"daily"`` for a kebab-case type name."""
    if data_type.startswith("daily-") or data_type == "activity-level":
        return "daily"
    return "sample" if data_type in SAMPLE_TYPES else "interval"


def month_filter(data_type: str, month: str) -> str:
    """AIP-160 filter selecting one local calendar month of ``data_type``."""
    first, nxt = parse_month(month)
    field = _snake(data_type)
    kind = kind_of(data_type)
    if kind == "daily":
        f, lo, hi = f"{field}.date", first.isoformat(), nxt.isoformat()
    else:
        if kind == "sample":
            sub = "sample_time.civil_time"
        elif data_type in END_FILTER_TYPES:
            sub = "interval.civil_end_time"
        else:
            sub = "interval.civil_start_time"
        f, lo, hi = f"{field}.{sub}", f"{first}T00:00:00", f"{nxt}T00:00:00"
    return f'{f} >= "{lo}" AND {f} < "{hi}"'


class GoogleHealth(Source):
    """Your Google Health data, one data type at a time.

    >>> gh = GoogleHealth()
    >>> steps = gh.load_range("steps", "2026-01-01", "2026-03-31")
    >>> hr = gh.load_range("heart-rate", "2026-03-01", "2026-03-07")
    """

    name = "google_health"

    def __init__(
        self,
        auth: GoogleHealthAuth | None = None,
        *args,
        today: dt.date | None = None,
        **kwargs,
    ) -> None:
        # A light rate limit: heart-rate months can run to hundreds of pages.
        kwargs.setdefault("min_interval", 0.2)
        super().__init__(*args, **kwargs)
        self.auth = auth or GoogleHealthAuth()
        self._today = today

    @property
    def today(self) -> dt.date:
        return self._today or dt.date.today()

    # -- public API --------------------------------------------------------
    def load_range(
        self, data_type: str, start: dt.date | str, end: dt.date | str
    ) -> pd.DataFrame:
        """Every point of ``data_type`` in the inclusive local-date range."""
        data_type = _kebab(data_type)
        start_d, end_d = pd.Timestamp(start).date(), pd.Timestamp(end).date()
        frames = [self.load(f"{data_type}/{m}") for m in months_between(start_d, end_d)]
        frames = [f for f in frames if len(f)]
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True)
        col = _day_column(out, data_type)
        day = out[col].dt.normalize()
        keep = (day >= pd.Timestamp(start_d)) & (day <= pd.Timestamp(end_d))
        return out.loc[keep].sort_values(col).reset_index(drop=True)

    # -- Source hooks ------------------------------------------------------
    def _is_final(self, key: str) -> bool:
        return month_is_closed(key.split("/")[1], SYNC_LAG_DAYS, self.today)

    def _download(self, key: str) -> Path:
        dest = self.cache.path(f"raw/{key}.json")
        if dest.exists() and self._is_final(key):
            return dest
        data_type, month = key.split("/")
        points = list(self._pages(data_type, month_filter(data_type, month)))
        tmp = dest.with_suffix(".json.part")
        tmp.write_text(json.dumps({"dataType": data_type, "dataPoints": points}))
        tmp.replace(dest)
        log.info("[%s] %s: %d points", self.name, key, len(points))
        return dest

    def _pages(self, data_type: str, filter_: str) -> Iterable[dict]:
        url = f"{API_ROOT}/{API_VERSION}/users/me/dataTypes/{data_type}/dataPoints"
        params = {
            "filter": filter_,
            "pageSize": 25 if data_type in SMALL_PAGE_TYPES else 10_000,
        }
        while True:
            # Ask for the token every page: a long heart-rate pull can outlive it.
            headers = {"Authorization": f"Bearer {self.auth.token()}"}
            body = self.fetcher.get_json(url, params=params, headers=headers)
            yield from body.get("dataPoints", [])
            token = body.get("nextPageToken")
            if not token:
                return
            params["pageToken"] = token

    def _parse(self, raw: Path) -> pd.DataFrame:
        payload = json.loads(raw.read_text())
        return flatten_datapoints(payload["dataPoints"], payload["dataType"])


# -- flattening ------------------------------------------------------------

def flatten_datapoints(points: Sequence[dict], data_type: str) -> pd.DataFrame:
    """One tidy row per data point, whatever the type.

    Time columns are derived from the point's timing shape:

    * interval: ``start_time``/``end_time`` (UTC) and ``start_local``/``end_local``
    * sample:   ``time`` (UTC) and ``time_local``
    * daily:    ``date``

    Value fields are flattened to snake_case columns (``count``,
    ``beats_per_minute``, ``summary_minutes_asleep``...). Int64-as-string values
    become numbers, ``"123s"`` durations become float seconds with an ``_s``
    suffix, and nested lists (sleep stages, exercise splits) are kept as JSON
    strings.
    """
    key = _camel(_kebab(data_type))
    if not points:
        return pd.DataFrame()

    rows = []
    for p in points:
        body = p.get(key)
        if body is None:  # tolerate a type name the API spells differently
            body = next((v for k, v in p.items() if k not in ("name", "dataSource")), {})
        row = {"data_type": data_type, **_timing(body)}
        row.update(_flatten(_strip_timing(body)))
        src = p.get("dataSource") or {}
        row["source_platform"] = src.get("platform")
        row["source_device"] = (src.get("device") or {}).get("displayName")
        row["recording_method"] = src.get("recordingMethod")
        rows.append(row)

    df = pd.DataFrame(rows)
    for col in df.columns:
        df[col] = _coerce(df[col])
    durations = [c for c in df.columns if _is_text(df[c]) and _is_duration(df[c])]
    for col in durations:
        df[f"{col}_s"] = df.pop(col).str.rstrip("s").astype(float)
    return df


def _timing(body: dict) -> dict:
    if "interval" in body:
        iv = body["interval"]
        start = utc(iv["startTime"])
        end = utc(iv["endTime"])
        return {
            "start_time": start,
            "end_time": end,
            "start_local": wall_clock(start, iv.get("startUtcOffset")),
            "end_local": wall_clock(end, iv.get("endUtcOffset")),
        }
    if "sampleTime" in body:
        st = body["sampleTime"]
        t = utc(st["physicalTime"])
        return {"time": t, "time_local": wall_clock(t, st.get("utcOffset"))}
    if "date" in body:
        d = body["date"]
        if isinstance(d, dict):
            return {"date": pd.Timestamp(d["year"], d["month"], d["day"])}
        return {"date": pd.Timestamp(d)}
    return {}


def _strip_timing(body: dict) -> dict:
    return {k: v for k, v in body.items() if k not in ("interval", "sampleTime", "date")}


def _flatten(obj: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in obj.items():
        name = f"{prefix}{_snake(k)}"
        if isinstance(v, dict):
            out.update(_flatten(v, name + "_"))
        elif isinstance(v, list):
            out[name] = json.dumps(v)
        else:
            out[name] = v
    return out


_DURATION = re.compile(r"^-?\d+(\.\d+)?s$")


def _is_duration(s: pd.Series) -> bool:
    vals = s.dropna()
    return len(vals) > 0 and vals.map(lambda v: isinstance(v, str) and bool(_DURATION.match(v))).all()


def _is_text(s: pd.Series) -> bool:
    """Object or string dtype. pandas 3 stores text as its own ``str`` dtype
    rather than ``object``, so checking for ``object`` alone misses it."""
    return pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)


def _coerce(s: pd.Series) -> pd.Series:
    """The API sends int64s as strings; make all-numeric columns numeric."""
    if not _is_text(s):
        return s
    vals = s.dropna()
    if len(vals) and vals.map(lambda v: isinstance(v, str)).all():
        num = pd.to_numeric(vals, errors="coerce")
        if num.notna().all():
            return pd.to_numeric(s)
    return s


def _kebab(data_type: str) -> str:
    return _snake(data_type).replace("_", "-")


def _day_column(df: pd.DataFrame, data_type: str) -> str:
    """The column that decides which date a row belongs to -- matching the
    month filter, so a row is never dropped between two months."""
    first = "end_local" if data_type in END_FILTER_TYPES else "start_local"
    for col in (first, "time_local", "date"):
        if col in df:
            return col
    raise KeyError(f"no time column in {list(df.columns)}")
