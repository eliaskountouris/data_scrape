"""US DOT / BTS DB1B Market -- the Airline Origin and Destination Survey.

A 10% random sample of all US itinerary tickets, published quarterly. Each row
is one group of tickets for an origin-destination market, with the fare paid,
the distance covered, and how many passengers the row represents.

Source: https://www.transtats.bts.gov/ (public domain, no API key)

Two properties shape how this module works:

* **The raw file is ~1.8 GB of CSV per quarter.** It is read in chunks and
  aggregated on the way in, to the grain the fare analysis actually needs --
  market x carrier x coupons x bulk flag -- which collapses ~7.3M rows to a few
  hundred thousand without losing any passenger-weighted average.
* **``Passengers`` is a sampling weight, not a count of rows.** Every average
  computed downstream must be weighted by it, so it is a required column of
  :class:`~common.flights.schema.FareSchema`.

Publication lag is longer than the on-time feed: roughly two quarters.
"""

from __future__ import annotations

import logging
import zipfile
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from ..sources.base import Source
from .provider import FareProvider, fare_registry

log = logging.getLogger(__name__)

URL_TEMPLATE = (
    "https://transtats.bts.gov/PREZIP/"
    "Origin_and_Destination_Survey_DB1BMarket_{year}_{quarter}.zip"
)

#: Only what the fare analysis needs. The raw file has 42 columns.
COLUMNS = [
    "Origin",
    "Dest",
    "TkCarrier",
    "Passengers",
    "MktFare",
    "MktDistance",
    "NonStopMiles",
    "MktCoupons",
    "BulkFare",
]

#: Grain the chunks are aggregated to.
GROUP_KEYS = ["origin", "dest", "carrier", "coupons", "bulk_fare"]

CHUNK_ROWS = 1_000_000


@fare_registry.register
class DB1BMarket(Source, FareProvider):
    """Quarterly DB1B market fares. Keys are ``"YYYYQN"``, e.g. ``"2025Q1"``."""

    name = "db1b_market"
    coverage = (
        "US domestic itinerary markets, a 10% ticket sample "
        "(no international markets, so no non-US airports)"
    )

    def load_records(self, periods: Sequence[str]) -> pd.DataFrame:
        """FareProvider entry point: one frame for several quarters."""
        return self.load_many(list(periods))

    @staticmethod
    def _split_key(key: str) -> tuple[int, int]:
        """``"2025Q1"`` -> ``(2025, 1)``."""
        year, _, quarter = key.upper().partition("Q")
        if not quarter:
            raise ValueError(f"expected a quarter key like '2025Q1', got {key!r}")
        return int(year), int(quarter)

    def _download(self, key: str) -> Path:
        year, quarter = self._split_key(key)
        url = URL_TEMPLATE.format(year=year, quarter=quarter)
        return self.fetcher.download(url, name=f"raw/{key}.zip")

    def _parse(self, raw: Path) -> pd.DataFrame:
        period = raw.stem
        with zipfile.ZipFile(raw) as zf:
            csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            log.info("parsing %s in chunks of %d rows", csv_name, CHUNK_ROWS)
            with zf.open(csv_name) as fh:
                parts = [
                    self._aggregate_chunk(chunk)
                    for chunk in pd.read_csv(
                        fh,
                        usecols=COLUMNS,
                        chunksize=CHUNK_ROWS,
                        low_memory=False,
                    )
                ]

        # Chunk boundaries split groups, so combine once more across parts.
        df = self._combine(pd.concat(parts, ignore_index=True))
        df["period"] = period
        df["fare_usd"] = df["fare_weighted_sum"] / df["passengers"]
        df = df.drop(columns=["fare_weighted_sum"])

        for col in ("origin", "dest", "carrier"):
            df[col] = df[col].astype("category")
        return df

    @staticmethod
    def _aggregate_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
        chunk = chunk.rename(
            columns={
                "Origin": "origin",
                "Dest": "dest",
                "TkCarrier": "carrier",
                "Passengers": "passengers",
                "MktFare": "fare_usd",
                "MktDistance": "distance_mi",
                "NonStopMiles": "nonstop_mi",
                "MktCoupons": "coupons",
                "BulkFare": "bulk_fare",
            }
        )
        # A non-positive fare is a data error, not a cheap ticket; it would drag
        # every average it touches. Bulk fares are kept but flagged, so callers
        # decide -- DOT's own guidance is to exclude them from fare averages.
        chunk = chunk[(chunk["fare_usd"] > 0) & (chunk["passengers"] > 0)]
        chunk["bulk_fare"] = chunk["bulk_fare"].fillna(0).astype(bool)
        # Carry the weighted sum, not the mean: means cannot be re-averaged
        # across chunks without it.
        chunk["fare_weighted_sum"] = chunk["fare_usd"] * chunk["passengers"]
        return DB1BMarket._combine(chunk)

    @staticmethod
    def _combine(df: pd.DataFrame) -> pd.DataFrame:
        return (
            df.groupby(GROUP_KEYS, observed=True, dropna=False)
            .agg(
                passengers=("passengers", "sum"),
                fare_weighted_sum=("fare_weighted_sum", "sum"),
                distance_mi=("distance_mi", "max"),
                nonstop_mi=("nonstop_mi", "max"),
            )
            .reset_index()
        )
