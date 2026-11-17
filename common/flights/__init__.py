"""common.flights -- getting and analysing flight data.

Two datasets behind two identical interfaces:

* :class:`FlightData` -- scheduled-flight records, monthly (``"2025-01"``).
  Analysed by :mod:`~common.flights.turnaround`.
* :class:`FareData` -- ticket prices, quarterly (``"2025Q1"``).
  Analysed by :mod:`~common.flights.fares`.

Ask a facade for periods and airports and it routes to whichever providers can
serve them. The analysis modules never learn where a row came from.
"""

from ..providers import Coverage, ProviderRegistry
from ..schema import Column, SchemaError, TableSchema
from .absorption import add_absorption, airport_absorption
from .bts import BTSOnTime
from .db1b import DB1BMarket
from .fares import (
    DISTANCE_BANDS,
    airport_fare_rates,
    distance_curve,
    national_baseline,
)
from .fares import prepare as prepare_fares
from .provider import (
    FareData,
    FareProvider,
    FlightData,
    FlightProvider,
    fare_registry,
    flight_registry,
)
from .schema import FareSchema, FlightSchema
from .turnaround import (
    DOT_LATE_MIN,
    MAX_GROUND_MIN,
    airport_delay_rates,
    build_turnarounds,
    ground_time_curve,
    label_turnarounds,
)

__all__ = [
    # interfaces
    "FlightData",
    "FareData",
    "FlightProvider",
    "FareProvider",
    "ProviderRegistry",
    "flight_registry",
    "fare_registry",
    "Coverage",
    # schemas
    "FlightSchema",
    "FareSchema",
    "TableSchema",
    "SchemaError",
    "Column",
    # providers
    "BTSOnTime",
    "DB1BMarket",
    # delay analysis
    "add_absorption",
    "airport_absorption",
    "DOT_LATE_MIN",
    "MAX_GROUND_MIN",
    "build_turnarounds",
    "label_turnarounds",
    "airport_delay_rates",
    "ground_time_curve",
    # fare analysis
    "DISTANCE_BANDS",
    "prepare_fares",
    "national_baseline",
    "distance_curve",
    "airport_fare_rates",
]
