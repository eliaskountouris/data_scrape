"""US DOT / BTS "Marketing Carrier On-Time Performance" monthly data.

Every US carrier above a revenue threshold must report one row per scheduled
domestic flight: scheduled and actual departure/arrival times, delay minutes,
cancellation and diversion flags, and -- crucially for turnaround analysis --
the aircraft's tail number.

Source: https://www.transtats.bts.gov/ (public domain, no API key)

Note the ~2 month publication lag: data for a given month appears roughly 8-10
weeks later.
"""

from __future__ import annotations

import logging
import zipfile
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from ..sources.base import Source
from .provider import FlightProvider, flight_registry

log = logging.getLogger(__name__)

URL_TEMPLATE = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)

#: Only the columns the toolkit actually uses. The raw file has 110.
COLUMNS = [
    "FlightDate",
    "Reporting_Airline",
    "Tail_Number",
    "Flight_Number_Reporting_Airline",
    "Origin",
    "Dest",
    "CRSDepTime",
    "DepTime",
    "DepDelay",
    "CRSArrTime",
    "ArrTime",
    "ArrDelay",
    "CRSElapsedTime",
    "Cancelled",
    "Diverted",
    "Distance",
    "CarrierDelay",
    "WeatherDelay",
    "NASDelay",
    "SecurityDelay",
    "LateAircraftDelay",
]

RENAME = {
    "FlightDate": "flight_date",
    "Reporting_Airline": "carrier",
    "Tail_Number": "tail",
    "Flight_Number_Reporting_Airline": "flight_number",
    "Origin": "origin",
    "Dest": "dest",
    "CRSDepTime": "crs_dep_hhmm",
    "DepTime": "dep_hhmm",
    "DepDelay": "dep_delay",
    "CRSArrTime": "crs_arr_hhmm",
    "ArrTime": "arr_hhmm",
    "ArrDelay": "arr_delay",
    "CRSElapsedTime": "crs_elapsed_min",
    "Cancelled": "cancelled",
    "Diverted": "diverted",
    "Distance": "distance_mi",
    "CarrierDelay": "carrier_delay",
    "WeatherDelay": "weather_delay",
    "NASDelay": "nas_delay",
    "SecurityDelay": "security_delay",
    "LateAircraftDelay": "late_aircraft_delay",
}


def _hhmm_to_minutes(s: pd.Series) -> pd.Series:
    """Convert BTS ``HHMM`` integers to minutes after local midnight.

    BTS writes midnight as ``2400``; normalise it to 0 so arithmetic behaves.
    """
    v = pd.to_numeric(s, errors="coerce")
    v = v.where(v != 2400, 0)
    return (v // 100) * 60 + (v % 100)


@flight_registry.register
class BTSOnTime(Source, FlightProvider):
    """Monthly BTS on-time performance. Keys are ``"YYYY-MM"``.

    Doubles as a :class:`~common.flights.provider.FlightProvider`, so it can be
    used directly (``BTSOnTime().load("2025-01")``) or reached through the
    provider-agnostic :class:`~common.flights.provider.FlightData` facade.
    """

    name = "bts_ontime"
    coverage = (
        "US domestic segments on carriers above the DOT reporting threshold "
        "(no international legs, so no non-US airports)"
    )

    def load_records(self, months: Sequence[str]) -> pd.DataFrame:
        """FlightProvider entry point: one frame for several months."""
        return self.load_many(list(months))

    @staticmethod
    def _split_key(key: str) -> tuple[int, int]:
        year, month = key.split("-")
        return int(year), int(month)

    def _download(self, key: str) -> Path:
        year, month = self._split_key(key)
        url = URL_TEMPLATE.format(year=year, month=month)
        return self.fetcher.download(url, name=f"raw/{key}.zip")

    def _parse(self, raw: Path) -> pd.DataFrame:
        with zipfile.ZipFile(raw) as zf:
            csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            log.info("parsing %s", csv_name)
            with zf.open(csv_name) as fh:
                df = pd.read_csv(
                    fh,
                    usecols=COLUMNS,
                    dtype={"Tail_Number": "string", "Reporting_Airline": "string"},
                    low_memory=False,
                )

        df = df.rename(columns=RENAME)
        df["flight_date"] = pd.to_datetime(df["flight_date"])

        for col in ("crs_dep", "dep", "crs_arr", "arr"):
            df[f"{col}_min"] = _hhmm_to_minutes(df[f"{col}_hhmm"])
        df = df.drop(columns=[c for c in df.columns if c.endswith("_hhmm")])

        for col in ("cancelled", "diverted"):
            df[col] = df[col].fillna(0).astype(bool)

        # Scheduled departure as a real timestamp -- the only reliable way to put
        # one aircraft's flights in order (actual times wrap around midnight).
        df["crs_dep_dt"] = df["flight_date"] + pd.to_timedelta(
            df["crs_dep_min"], unit="m"
        )

        for col in ("origin", "dest", "carrier"):
            df[col] = df[col].astype("category")

        return df
