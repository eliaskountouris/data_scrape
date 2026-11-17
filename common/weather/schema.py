"""Canonical schemas for weather and daylight data.

Units are fixed and appear in the column names, so a frame can never be
silently mixed with one in other units. Local times are naive wall-clock times
in the row's ``timezone``; ``*_utc`` columns are the same instants, tz-aware.
"""

from __future__ import annotations

from typing import ClassVar

from ..schema import Column, TableSchema


class DailyWeatherSchema(TableSchema):
    """One row per location per local calendar day."""

    COLUMNS: ClassVar[tuple[Column, ...]] = (
        Column("location", "caller's label for the place (or 'lat,lon')"),
        Column("latitude", "requested latitude"),
        Column("longitude", "requested longitude"),
        Column("timezone", "IANA zone the local columns are in"),
        Column("date", "local calendar date"),
        Column("sunrise", "local wall-clock sunrise (NaT during polar night/day)"),
        Column("sunset", "local wall-clock sunset (NaT during polar night/day)"),
        Column("sunrise_utc", "sunrise instant, UTC"),
        Column("sunset_utc", "sunset instant, UTC"),
        Column("daylight_h", "hours between sunrise and sunset"),
        Column("temp_max_c", "2 m air temperature, daily max"),
        Column("temp_min_c", "2 m air temperature, daily min"),
        Column("precip_mm", "total precipitation (rain + snow water equivalent)"),
        Column("weather_code", "WMO weather code for the day's most severe weather"),
        Column("weather", "readable label for weather_code"),
        Column("temp_mean_c", "2 m air temperature, daily mean", required=False),
        Column("feels_max_c", "apparent temperature, daily max", required=False),
        Column("feels_min_c", "apparent temperature, daily min", required=False),
        Column("sunshine_h", "hours of direct sunshine", required=False),
        Column("rain_mm", "liquid precipitation", required=False),
        Column("snowfall_cm", "snowfall depth", required=False),
        Column("precip_hours", "hours with measurable precipitation", required=False),
        Column("wind_max_kmh", "10 m wind speed, daily max", required=False),
        Column("gust_max_kmh", "10 m wind gusts, daily max", required=False),
        Column("wind_dir_deg", "dominant 10 m wind direction", required=False),
        Column("radiation_mj_m2", "shortwave radiation, daily sum", required=False),
    )


class HourlyWeatherSchema(TableSchema):
    """One row per location per hour."""

    COLUMNS: ClassVar[tuple[Column, ...]] = (
        Column("location", "caller's label for the place (or 'lat,lon')"),
        Column("latitude", "requested latitude"),
        Column("longitude", "requested longitude"),
        Column("timezone", "IANA zone the local columns are in"),
        Column("time", "local wall-clock start of the hour"),
        Column("time_utc", "start of the hour, UTC"),
        Column("temp_c", "2 m air temperature"),
        Column("precip_mm", "precipitation over the preceding hour"),
        Column("is_day", "bool: sun above the horizon"),
        Column("weather_code", "WMO weather code"),
        Column("weather", "readable label for weather_code"),
        Column("feels_c", "apparent temperature", required=False),
        Column("humidity_pct", "2 m relative humidity", required=False),
        Column("rain_mm", "liquid precipitation", required=False),
        Column("snowfall_cm", "snowfall depth", required=False),
        Column("cloud_pct", "total cloud cover", required=False),
        Column("wind_kmh", "10 m wind speed", required=False),
        Column("gust_kmh", "10 m wind gusts", required=False),
        Column("wind_dir_deg", "10 m wind direction", required=False),
        Column("radiation_w_m2", "shortwave radiation", required=False),
    )
