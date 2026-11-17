"""Canonical schemas for flight data.

Every provider, whatever its upstream format, emits these columns. That is what
makes the analysis layer provider-agnostic: :mod:`common.flights.turnaround`
and :mod:`common.flights.fares` never learn where a row came from.
"""

from __future__ import annotations

from typing import ClassVar

from ..schema import Column, TableSchema


class FlightSchema(TableSchema):
    """One row per scheduled flight.

    Times are minutes after local midnight *at the airport the event happens
    at* -- ``crs_dep_min``/``dep_min`` local to the origin,
    ``crs_arr_min``/``arr_min`` local to the destination. Delays are signed
    minutes (negative = early). ``flight_date`` is the local departure date.
    """

    COLUMNS: ClassVar[tuple[Column, ...]] = (
        Column("flight_date", "local departure date"),
        Column("carrier", "operating carrier code"),
        Column("tail", "aircraft registration -- the key that chains flights"),
        Column("flight_number", "flight number"),
        Column("origin", "origin airport code"),
        Column("dest", "destination airport code"),
        Column("crs_dep_min", "scheduled departure, minutes after local midnight"),
        Column("crs_arr_min", "scheduled arrival, minutes after local midnight"),
        Column("crs_dep_dt", "scheduled departure as a sortable timestamp"),
        Column("dep_delay", "departure delay, signed minutes"),
        Column("arr_delay", "arrival delay, signed minutes"),
        Column("cancelled", "bool"),
        Column("diverted", "bool"),
        Column("dep_min", "actual departure, local minutes", required=False),
        Column("arr_min", "actual arrival, local minutes", required=False),
        Column("crs_elapsed_min", "scheduled block time", required=False),
        Column("distance_mi", "great-circle distance", required=False),
        Column("carrier_delay", "DOT delay cause split", required=False),
        Column("weather_delay", "DOT delay cause split", required=False),
        Column("nas_delay", "DOT delay cause split", required=False),
        Column("security_delay", "DOT delay cause split", required=False),
        Column("late_aircraft_delay", "DOT delay cause split", required=False),
    )


class FareSchema(TableSchema):
    """One row per priced origin-destination market.

    A *market* is a directional origin-destination pair on one ticket,
    regardless of connections. ``fare_usd`` is the per-passenger price for the
    whole market and ``distance_mi`` the miles it covers, so dollars per mile
    is ``fare_usd / distance_mi``.

    ``passengers`` is the sampling weight: rows are groups of tickets, not
    individual ones, so every average must be weighted by it.
    """

    COLUMNS: ClassVar[tuple[Column, ...]] = (
        Column("period", "period the fare was surveyed in, e.g. '2025Q1'"),
        Column("origin", "origin airport code"),
        Column("dest", "destination airport code"),
        Column("fare_usd", "per-passenger market fare in US dollars"),
        Column("distance_mi", "market distance in miles"),
        Column("passengers", "sampling weight -- tickets this row represents"),
        Column("carrier", "ticketing carrier", required=False),
        Column("nonstop_mi", "nonstop great-circle distance", required=False),
        Column("coupons", "flight segments in the market", required=False),
        Column("bulk_fare", "bool: part of a bulk/opaque fare", required=False),
    )
