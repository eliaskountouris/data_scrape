"""Tests for the provider-dispatch interface.

Uses fake providers so nothing touches the network -- the point under test is
the routing, not any particular upstream.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.flights import (  # noqa: E402
    FlightData,
    FlightProvider,
    FlightSchema,
    ProviderRegistry,
    SchemaError,
)


def canonical_frame(pairs):
    """Minimal schema-complete frame for the given (origin, dest) pairs."""
    rows = []
    for i, (origin, dest) in enumerate(pairs):
        rows.append({
            "flight_date": pd.Timestamp("2025-01-01"),
            "carrier": "XX",
            "tail": f"N{i}",
            "flight_number": i,
            "origin": origin,
            "dest": dest,
            "crs_dep_min": 480,
            "crs_arr_min": 600,
            "crs_dep_dt": pd.Timestamp("2025-01-01 08:00"),
            "dep_delay": 0.0,
            "arr_delay": 0.0,
            "cancelled": False,
            "diverted": False,
        })
    return pd.DataFrame(rows)


class FakeUS(FlightProvider):
    name = "fake_us"
    coverage = "US airports"

    def load_records(self, periods):
        return canonical_frame([("ATL", "LAX"), ("LAX", "ORD")])


class FakeCanada(FlightProvider):
    name = "fake_ca"
    coverage = "Canadian airports"

    def load_records(self, periods):
        return canonical_frame([("YYZ", "YVR")])


class Broken(FlightProvider):
    name = "broken"
    coverage = "nothing useful"

    def load_records(self, periods):
        return pd.DataFrame({"origin": ["ATL"], "dest": ["LAX"]})


def test_single_provider_serves_its_airports():
    fd = FlightData([FakeUS()])
    flights = fd.load(["2025-01"], airports=["ATL", "LAX"])
    cov = fd.coverage(["ATL", "LAX"], flights)
    assert cov.served == {"ATL": "fake_us", "LAX": "fake_us"}
    assert cov.unserved == ()
    assert cov.complete is True
    assert bool(cov) is True
    assert cov.provider_for("ATL") == "fake_us"


def test_airports_route_to_different_providers():
    fd = FlightData([FakeUS(), FakeCanada()])
    flights = fd.load(["2025-01"], airports=["ATL", "YYZ"])
    cov = fd.coverage(["ATL", "YYZ"], flights)
    assert cov.served == {"ATL": "fake_us", "YYZ": "fake_ca"}
    assert set(cov.providers_used) == {"fake_us", "fake_ca"}


def test_uncovered_airport_is_reported_not_hidden(caplog):
    fd = FlightData([FakeUS()])
    with caplog.at_level("WARNING"):
        flights = fd.load(["2025-01"], airports=["ATL", "YYZ"])
    assert "YYZ" in caplog.text
    assert "US airports" in caplog.text  # the coverage string is actionable
    cov = fd.coverage(["ATL", "YYZ"], flights)
    assert cov.unserved == ("YYZ",)
    assert cov.complete is False
    assert cov.provider_for("YYZ") is None


def test_load_returns_whole_frames_not_rows_filtered_to_airports():
    """Turnaround chaining needs an aircraft's other legs, so filtering here
    would silently break the analysis downstream."""
    fd = FlightData([FakeUS()])
    flights = fd.load(["2025-01"], airports=["ATL"])
    assert set(flights["origin"]) == {"ATL", "LAX"}


def test_might_cover_skips_providers_that_cannot_help():
    class Picky(FakeCanada):
        def might_cover(self, airport):
            return airport.startswith("Y")

    fd = FlightData([FakeUS(), Picky()])
    flights = fd.load(["2025-01"], airports=["ATL"])
    assert set(flights["provider"]) == {"fake_us"}


def test_provider_missing_required_columns_is_a_hard_error():
    fd = FlightData([Broken()])
    with pytest.raises(SchemaError, match="missing required columns"):
        fd.load(["2025-01"], airports=["ATL"])


def test_optional_columns_are_backfilled():
    fd = FlightData([FakeUS()])
    flights = fd.load(["2025-01"], airports=["ATL"])
    assert "late_aircraft_delay" in flights.columns


def test_coverage_renders_a_routing_report():
    fd = FlightData([FakeUS()])
    flights = fd.load(["2025-01"], airports=["ATL", "YYZ"], warn=False)
    report = str(fd.coverage(["ATL", "YYZ"], flights))
    assert "ATL: fake_us" in report
    assert "YYZ: NO PROVIDER" in report


def test_no_candidate_provider_raises_with_guidance():
    class Nope(FakeUS):
        def might_cover(self, airport):
            return False

    with pytest.raises(LookupError, match="no registered provider"):
        FlightData([Nope()]).load(["2025-01"], airports=["YYZ"])


def test_bts_satisfies_the_provider_interface():
    """Guards the Source.load(key) / FlightProvider.load_flights(months) split."""
    from common.flights import BTSOnTime

    bts = BTSOnTime()
    assert isinstance(bts, FlightProvider)
    assert callable(bts.load_records)
    assert "US domestic" in bts.coverage


def test_required_columns_cover_what_turnaround_analysis_uses():
    for col in ("tail", "origin", "dest", "crs_dep_dt", "arr_delay", "dep_delay"):
        assert col in FlightSchema.required()


def test_required_and_optional_do_not_overlap():
    assert not set(FlightSchema.required()) & set(FlightSchema.optional())


# -- the ABC contract ------------------------------------------------------

def test_provider_must_declare_name_and_coverage():
    """Caught at class definition, not when someone reads a useless report."""
    with pytest.raises(TypeError, match="must override 'name'"):
        class Nameless(FlightProvider):
            coverage = "somewhere"

            def load_records(self, periods):
                return canonical_frame([("ATL", "LAX")])

    with pytest.raises(TypeError, match="must override 'coverage'"):
        class Uncovered(FlightProvider):
            name = "uncovered"

            def load_records(self, periods):
                return canonical_frame([("ATL", "LAX")])


def test_provider_without_load_flights_cannot_be_instantiated():
    class Incomplete(FlightProvider):
        name = "incomplete"
        coverage = "nothing"

    with pytest.raises(TypeError, match="abstract"):
        Incomplete()


# -- the registry ----------------------------------------------------------

def test_registry_is_a_mapping_of_name_to_class():
    reg = ProviderRegistry(base=FlightProvider)
    reg.register(FakeUS)
    assert reg["fake_us"] is FakeUS
    assert list(reg) == ["fake_us"]
    assert len(reg) == 1


def test_registry_rejects_duplicate_names():
    reg = ProviderRegistry(base=FlightProvider)
    reg.register(FakeUS)

    class Clashing(FlightProvider):
        name = "fake_us"
        coverage = "different thing"

        def load_records(self, periods):
            return canonical_frame([("ATL", "LAX")])

    with pytest.raises(ValueError, match="already registered"):
        reg.register(Clashing)


def test_registry_creates_instances_and_reports_unknown_names():
    reg = ProviderRegistry(base=FlightProvider)
    reg.register(FakeUS)
    reg.register(FakeCanada)
    assert [p.name for p in reg.create()] == ["fake_us", "fake_ca"]
    assert [p.name for p in reg.create(["fake_ca"])] == ["fake_ca"]
    with pytest.raises(KeyError, match="unknown provider"):
        reg.create(["nope"])


def test_flight_data_selects_providers_by_name_from_the_registry():
    reg = ProviderRegistry(base=FlightProvider)
    reg.register(FakeUS)
    reg.register(FakeCanada)
    fd = FlightData(provider_names=["fake_ca"], registry=reg)
    assert [p.name for p in fd.providers] == ["fake_ca"]


def test_flight_data_rejects_both_providers_and_names():
    with pytest.raises(TypeError, match="not both"):
        FlightData(providers=[FakeUS()], provider_names=["fake_us"])


def test_builtin_bts_is_registered_by_default():
    """FlightData() with no arguments must find the real provider."""
    from common.flights import flight_registry

    assert "bts_ontime" in flight_registry
    assert [p.name for p in FlightData().providers] == ["bts_ontime"]
