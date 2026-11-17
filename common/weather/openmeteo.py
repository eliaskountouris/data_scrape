"""Open-Meteo weather and sunrise/sunset, daily or hourly, for any coordinate.

One request returns weather *and* astronomical daylight for a place and date
range, so a single source covers both. Free, no API key, CC BY 4.0 (credit
"Weather data by Open-Meteo.com" on anything published).

Two upstream endpoints, picked per month:

* **archive** (ERA5 reanalysis, 1940 onwards) for months that have closed and
  settled -- cached forever.
* **forecast** for the current month and the one just ended, which the archive
  doesn't fully cover yet. These are re-fetched on every load and never cached,
  because the numbers firm up over the following days. Dates up to 16 days
  ahead are forecasts, not observations.

Source: https://open-meteo.com/en/docs
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlencode

import pandas as pd

from ..periods import month_is_closed, months_between, parse_month
from ..schema import TableSchema
from ..sources.base import Source
from .schema import DailyWeatherSchema, HourlyWeatherSchema

log = logging.getLogger(__name__)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

#: The archive lags real time by a few days; give it a week before trusting a
#: closed month to be complete there.
ARCHIVE_LAG_DAYS = 7
#: How far ahead the forecast endpoint will answer.
FORECAST_HORIZON_DAYS = 15

#: WMO 4677 codes as Open-Meteo reports them.
WMO_CODES = {
    0: "clear", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "rime fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "light freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "light freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "violent showers",
    85: "light snow showers", 86: "snow showers",
    95: "thunderstorm", 96: "thunderstorm, hail", 99: "thunderstorm, heavy hail",
}


@dataclass(frozen=True, slots=True)
class Location:
    """A point to fetch weather for. ``name`` is just a label for the output."""

    latitude: float
    longitude: float
    name: str | None = None

    def __post_init__(self) -> None:
        if not (-90 <= self.latitude <= 90 and -180 <= self.longitude <= 180):
            raise ValueError(f"not a coordinate: {self.latitude}, {self.longitude}")

    @property
    def slug(self) -> str:
        """Filesystem-safe cache key. 4 dp is ~11 m -- finer than the model grid."""
        return f"{self.latitude:.4f}_{self.longitude:.4f}"

    @property
    def label(self) -> str:
        return self.name or f"{self.latitude:.4f},{self.longitude:.4f}"

    @classmethod
    def coerce(cls, loc: "Location | tuple[float, float]") -> "Location":
        return loc if isinstance(loc, Location) else cls(*loc)


class _OpenMeteo(Source):
    """Shared plumbing; subclasses pick daily vs hourly via the attributes below.

    Cache keys are ``"<lat>_<lon>/<YYYY-MM>"``. Use :meth:`load_range` rather
    than building keys by hand.
    """

    granularity: ClassVar[str]                 # "daily" | "hourly"
    variables: ClassVar[dict[str, str]]        # open-meteo name -> our column
    schema: ClassVar[type[TableSchema]]

    def __init__(self, *args, today: dt.date | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._today = today                    # injectable for tests

    @property
    def today(self) -> dt.date:
        return self._today or dt.date.today()

    # -- public API --------------------------------------------------------
    def load_range(
        self,
        locations: Location | tuple[float, float] | Sequence[Location | tuple[float, float]],
        start: dt.date | str,
        end: dt.date | str,
    ) -> pd.DataFrame:
        """Rows for every location, inclusive ``start``..``end`` local dates."""
        single_pair = isinstance(locations, tuple) and all(
            isinstance(x, (int, float)) for x in locations
        )
        if isinstance(locations, Location) or single_pair:
            locations = [locations]
        locs = [Location.coerce(loc) for loc in locations]
        start_d, end_d = pd.Timestamp(start).date(), pd.Timestamp(end).date()
        horizon = self.today + dt.timedelta(days=FORECAST_HORIZON_DAYS)
        if end_d > horizon:
            raise ValueError(f"Open-Meteo forecasts reach {horizon}; asked for {end_d}")

        frames = []
        for loc in locs:
            for month in months_between(start_d, end_d):
                df = self.load(f"{loc.slug}/{month}")
                df["location"] = loc.label
                frames.append(df)
        out = pd.concat(frames, ignore_index=True)
        day = out["date"] if "date" in out else out["time"].dt.normalize()
        keep = (day >= pd.Timestamp(start_d)) & (day <= pd.Timestamp(end_d))
        return out.loc[keep].reset_index(drop=True)

    # -- Source hooks ------------------------------------------------------
    def _is_final(self, key: str) -> bool:
        return month_is_closed(key.split("/")[1], ARCHIVE_LAG_DAYS, self.today)

    def _request(self, key: str) -> str:
        slug, month = key.split("/")
        lat, lon = (float(x) for x in slug.split("_"))
        first, nxt = parse_month(month)
        last = nxt - dt.timedelta(days=1)
        final = self._is_final(key)
        if not final:
            last = min(last, self.today + dt.timedelta(days=FORECAST_HORIZON_DAYS))
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": first.isoformat(),
            "end_date": last.isoformat(),
            self.granularity: ",".join(self.variables),
            "timezone": "auto",
            "timeformat": "unixtime",
        }
        return f"{ARCHIVE_URL if final else FORECAST_URL}?{urlencode(params)}"

    def _download(self, key: str) -> Path:
        return self.fetcher.download(
            self._request(key), name=f"raw/{key}.json", force=not self._is_final(key)
        )

    def _parse(self, raw: Path) -> pd.DataFrame:
        return self.parse_payload(json.loads(raw.read_text()), raw)

    def parse_payload(self, payload: dict, raw: Path | None = None) -> pd.DataFrame:
        """Turn one Open-Meteo JSON response into schema-conforming rows."""
        if payload.get("error"):
            raise RuntimeError(f"Open-Meteo error: {payload.get('reason')}")
        tz = payload["timezone"]
        block = payload[self.granularity]
        df = pd.DataFrame(block).rename(columns=self.variables)

        def local(col: str) -> pd.Series:
            utc = pd.to_datetime(df[col], unit="s", utc=True)
            return utc.dt.tz_convert(tz).dt.tz_localize(None)

        # Requested coordinates come back in the cache key; the response holds
        # the snapped grid cell instead, which isn't what the caller asked for.
        if raw is not None:
            lat, lon = (float(x) for x in raw.parent.name.split("_"))
        else:
            lat, lon = payload["latitude"], payload["longitude"]
        df.insert(0, "latitude", lat)
        df.insert(1, "longitude", lon)
        df.insert(2, "timezone", tz)
        df.insert(0, "location", f"{lat:.4f},{lon:.4f}")

        self._finish(df, local)
        df["weather_code"] = df["weather_code"].astype("Int64")
        df["weather"] = df["weather_code"].map(WMO_CODES).astype("string")
        df = self.schema.validate(df, self.name)
        order = [c.name for c in self.schema.COLUMNS]
        return df[order + [c for c in df.columns if c not in order]]

    def _finish(self, df: pd.DataFrame, local) -> None:
        raise NotImplementedError


class OpenMeteoDaily(_OpenMeteo):
    """Daily weather plus sunrise, sunset and day length.

    >>> OpenMeteoDaily().load_range(Location(40.71, -74.01, "NYC"), "2025-01-01", "2025-03-31")
    """

    name = "openmeteo_daily"
    granularity = "daily"
    schema = DailyWeatherSchema
    variables = {
        "weather_code": "weather_code",
        "temperature_2m_max": "temp_max_c",
        "temperature_2m_min": "temp_min_c",
        "temperature_2m_mean": "temp_mean_c",
        "apparent_temperature_max": "feels_max_c",
        "apparent_temperature_min": "feels_min_c",
        "sunrise": "sunrise_utc",
        "sunset": "sunset_utc",
        "daylight_duration": "daylight_h",
        "sunshine_duration": "sunshine_h",
        "precipitation_sum": "precip_mm",
        "rain_sum": "rain_mm",
        "snowfall_sum": "snowfall_cm",
        "precipitation_hours": "precip_hours",
        "wind_speed_10m_max": "wind_max_kmh",
        "wind_gusts_10m_max": "gust_max_kmh",
        "wind_direction_10m_dominant": "wind_dir_deg",
        "shortwave_radiation_sum": "radiation_mj_m2",
    }

    def _finish(self, df: pd.DataFrame, local) -> None:
        df["date"] = local("time").dt.normalize()
        df.drop(columns="time", inplace=True)
        for col in ("daylight_h", "sunshine_h"):
            df[col] = df[col] / 3600
        # Polar night/day: open-meteo reports sunrise = sunset = local midnight,
        # which would read as a real event. There is no sunrise; say so.
        no_event = (df["daylight_h"] <= 0) | (df["daylight_h"] >= 24)
        for event in ("sunrise", "sunset"):
            secs = pd.to_numeric(df[f"{event}_utc"], errors="coerce")
            df[f"{event}_utc"] = secs.where(~no_event & (secs > 0))
            df[event] = local(f"{event}_utc")
            df[f"{event}_utc"] = pd.to_datetime(df[f"{event}_utc"], unit="s", utc=True)


class OpenMeteoHourly(_OpenMeteo):
    """Hourly weather. ``is_day`` marks hours with the sun up."""

    name = "openmeteo_hourly"
    granularity = "hourly"
    schema = HourlyWeatherSchema
    variables = {
        "temperature_2m": "temp_c",
        "apparent_temperature": "feels_c",
        "relative_humidity_2m": "humidity_pct",
        "precipitation": "precip_mm",
        "rain": "rain_mm",
        "snowfall": "snowfall_cm",
        "cloud_cover": "cloud_pct",
        "wind_speed_10m": "wind_kmh",
        "wind_gusts_10m": "gust_kmh",
        "wind_direction_10m": "wind_dir_deg",
        "weather_code": "weather_code",
        "is_day": "is_day",
        "shortwave_radiation": "radiation_w_m2",
    }

    def _finish(self, df: pd.DataFrame, local) -> None:
        df["time_utc"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df["time"] = local("time")
        df["is_day"] = df["is_day"].fillna(0).astype(bool)
