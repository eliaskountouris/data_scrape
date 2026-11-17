"""Standard interfaces for flight data.

Two datasets, one shape. Both facades take periods and airports, route to
whichever providers can serve them, validate against a schema, and hand back a
single frame:

    from common.flights import FlightData, FareData

    flights = FlightData().load(["2025-01"], airports=["ATL", "DEN"])
    fares = FareData().load(["2025Q1"], airports=["ATL", "DEN"])

Note the period strings differ because the upstream feeds do -- on-time data is
monthly, the fare survey quarterly. Everything else about the two interfaces is
identical, and both are defined by binding three class attributes to the
machinery in :mod:`common.providers`.
"""

from __future__ import annotations

from typing import ClassVar

from ..providers import Coverage, DataFacade, Provider, ProviderRegistry
from .schema import FareSchema, FlightSchema

__all__ = [
    "Coverage",
    "FareData",
    "FareProvider",
    "FlightData",
    "FlightProvider",
    "ProviderRegistry",
    "fare_registry",
    "flight_registry",
]


class FlightProvider(Provider, abstract=True):
    """A source of scheduled-flight records conforming to :class:`FlightSchema`.

    Implement :meth:`~common.providers.Provider.load_records`, taking monthly
    ``"YYYY-MM"`` period keys.
    """


class FareProvider(Provider, abstract=True):
    """A source of ticket-price records conforming to :class:`FareSchema`.

    Implement :meth:`~common.providers.Provider.load_records`, taking quarterly
    ``"YYYYQN"`` period keys.
    """


flight_registry = ProviderRegistry(
    base=FlightProvider, builtin_modules=("common.flights.bts",)
)

fare_registry = ProviderRegistry(
    base=FareProvider, builtin_modules=("common.flights.db1b",)
)


class FlightData(DataFacade):
    """The standard entry point for scheduled-flight records."""

    provider_base: ClassVar[type[Provider]] = FlightProvider
    registry: ClassVar[ProviderRegistry] = flight_registry
    schema: ClassVar[type[FlightSchema]] = FlightSchema


class FareData(DataFacade):
    """The standard entry point for ticket prices."""

    provider_base: ClassVar[type[Provider]] = FareProvider
    registry: ClassVar[ProviderRegistry] = fare_registry
    schema: ClassVar[type[FareSchema]] = FareSchema
