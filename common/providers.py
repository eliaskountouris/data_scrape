"""Provider dispatch: one standard interface per dataset, many sources behind it.

Callers ask a :class:`DataFacade` for periods and airports; it works out which
providers can serve them, validates each against the dataset's schema, and
returns one frame. Swapping or adding an upstream source is a change behind the
facade, not a change to any caller.

Concretely, :mod:`common.flights` builds two facades on this -- ``FlightData``
for on-time records and ``FareData`` for ticket prices -- with identical
surfaces.

Coverage is resolved from the data itself rather than a hardcoded airport list,
which keeps it honest when a provider's network changes period to period.
"""

from __future__ import annotations

import importlib
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import ClassVar

import pandas as pd

from .schema import TableSchema

log = logging.getLogger(__name__)


class Provider(ABC):
    """One upstream source of records for a dataset.

    A subclass supplies three things: a ``name``, a ``coverage`` description,
    and :meth:`load_records`. Routing, schema validation, coverage reporting
    and concatenation all belong to :class:`DataFacade`.

    Concrete subclasses must override ``name`` and ``coverage``; forgetting is
    caught at class-definition time rather than surfacing as an unhelpful
    coverage report much later.
    """

    #: Short identifier, unique within its registry. Used as the registry key.
    name: str = "provider"

    #: What this provider can see. It is quoted verbatim when a user asks for
    #: an airport nobody covers, so make it specific enough to act on.
    coverage: str = "unspecified"

    def __init_subclass__(cls, abstract: bool = False, **kwargs) -> None:
        """Check that a concrete provider declares its identity.

        Intermediate bases that only narrow the contract (``FlightProvider``,
        ``FareProvider``) opt out with ``class X(Provider, abstract=True)``.
        ``__abstractmethods__`` cannot be used to detect them here -- ABCMeta
        populates it only after ``__init_subclass__`` has run.
        """
        super().__init_subclass__(**kwargs)
        if abstract:
            return
        for attr in ("name", "coverage"):
            if getattr(cls, attr) == getattr(Provider, attr):
                raise TypeError(
                    f"{cls.__name__} must override {attr!r} "
                    f"(it is what users see when routing or coverage is explained). "
                    f"If this is an intermediate base, declare it "
                    f"`class {cls.__name__}(..., abstract=True)`."
                )

    def might_cover(self, airport: str) -> bool:
        """Cheap prefilter, to skip loading a provider that cannot help.

        The default says "maybe" -- actual coverage is then determined from the
        loaded data. Override when a provider can answer without a download.
        """
        return True

    @abstractmethod
    def load_records(self, periods: Sequence[str]) -> pd.DataFrame:
        """Return schema-conforming records for these periods.

        Period strings are dataset-specific -- ``"2025-01"`` for monthly feeds,
        ``"2025Q1"`` for quarterly ones. Named distinctly from
        ``Source.load(key)`` so one class can be both: a per-key scraper
        underneath and a multi-period provider on top.
        """

    def __repr__(self) -> str:  # pragma: no cover
        return f"{type(self).__name__}(name={self.name!r})"


class ProviderRegistry(Mapping[str, type[Provider]]):
    """The set of known provider classes for one dataset, keyed by name.

    Providers register themselves at import time::

        @fare_registry.register
        class MyFares(FareProvider):
            name = "mine"
            coverage = "..."
    """

    def __init__(
        self,
        base: type[Provider] = Provider,
        builtin_modules: Sequence[str] = (),
    ) -> None:
        #: Providers must be subclasses of this, so a fare provider cannot be
        #: registered into the flights registry.
        self.base = base
        #: Modules holding built-in providers, imported on first use so that
        #: registration happens even when a facade is imported directly.
        self.builtin_modules = tuple(builtin_modules)
        self._classes: dict[str, type[Provider]] = {}
        self._builtins_loaded = False

    def register(self, cls: type[Provider]) -> type[Provider]:
        """Class decorator adding ``cls`` to this registry."""
        if not issubclass(cls, self.base):
            raise TypeError(f"{cls.__name__} is not a {self.base.__name__}")
        existing = self._classes.get(cls.name)
        if existing is not None and existing is not cls:
            raise ValueError(
                f"provider name {cls.name!r} already registered by {existing.__name__}"
            )
        self._classes[cls.name] = cls
        return cls

    def _load_builtins(self) -> None:
        if self._builtins_loaded:
            return
        self._builtins_loaded = True
        for module in self.builtin_modules:
            importlib.import_module(module)

    # -- Mapping interface -------------------------------------------------
    def __getitem__(self, name: str) -> type[Provider]:
        self._load_builtins()
        return self._classes[name]

    def __iter__(self) -> Iterator[str]:
        self._load_builtins()
        return iter(self._classes)

    def __len__(self) -> int:
        self._load_builtins()
        return len(self._classes)

    # -- Construction ------------------------------------------------------
    def create(self, names: Sequence[str] | None = None) -> list[Provider]:
        """Instantiate the named providers, or all of them."""
        self._load_builtins()
        chosen = list(self._classes) if names is None else list(names)
        unknown = [n for n in chosen if n not in self._classes]
        if unknown:
            raise KeyError(f"unknown provider(s) {unknown}; known: {list(self._classes)}")
        return [self._classes[n]() for n in chosen]

    def describe(self) -> str:
        return "; ".join(f"{n} covers {c.coverage}" for n, c in sorted(self.items()))

    def __repr__(self) -> str:  # pragma: no cover
        return f"ProviderRegistry({self.base.__name__}, {list(self._classes)})"


@dataclass(frozen=True, slots=True)
class Coverage:
    """Which requested airports each provider actually served."""

    requested: tuple[str, ...]
    served: Mapping[str, str] = field(default_factory=dict)
    unserved: tuple[str, ...] = ()
    providers_used: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        """True when every requested airport was served."""
        return not self.unserved

    def __bool__(self) -> bool:
        return self.complete

    def provider_for(self, airport: str) -> str | None:
        return self.served.get(airport)

    def __str__(self) -> str:
        return "\n".join(
            f"{a}: {self.served[a]}" if a in self.served else f"{a}: NO PROVIDER"
            for a in self.requested
        )


class DataFacade:
    """The standard entry point for one dataset.

    Subclasses bind three class attributes -- the provider base class, the
    registry to draw from, and the schema to validate against -- and inherit
    the whole interface.

    Parameters
    ----------
    providers:
        Provider instances, ordered by preference. Defaults to every registered
        provider.
    provider_names:
        Alternative to ``providers``: names to instantiate from the registry.
    """

    provider_base: ClassVar[type[Provider]] = Provider
    registry: ClassVar[ProviderRegistry]
    schema: ClassVar[type[TableSchema]]

    #: Columns holding airport codes, used to resolve coverage.
    airport_columns: ClassVar[tuple[str, ...]] = ("origin", "dest")

    def __init__(
        self,
        providers: Sequence[Provider] | None = None,
        provider_names: Sequence[str] | None = None,
        registry: ProviderRegistry | None = None,
    ) -> None:
        if providers is not None and provider_names is not None:
            raise TypeError("pass providers or provider_names, not both")
        self.provider_registry = registry or type(self).registry
        if providers is not None:
            self.providers: list[Provider] = list(providers)
        else:
            self.providers = self.provider_registry.create(provider_names)

    def load(
        self,
        periods: Sequence[str],
        airports: Sequence[str] | None = None,
        warn: bool = True,
    ) -> pd.DataFrame:
        """Load every record needed to analyse ``airports`` over ``periods``.

        Returns each provider's **complete** frame, not rows filtered down to
        ``airports``: ``airports`` selects *providers*, not rows. Filter at the
        analysis step, which knows what context it needs (chaining an
        aircraft's flights, for instance, needs its whole day).
        """
        candidates = self._candidates(airports)
        if not candidates:
            raise LookupError(
                f"no registered provider can serve {list(airports or [])}; "
                f"registered: {self.describe()}"
            )

        frames = []
        for provider in candidates:
            df = self.schema.validate(provider.load_records(periods), provider.name)
            df["provider"] = provider.name
            frames.append(df)

        records = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

        if airports is not None and warn:
            cov = self.coverage(airports, records)
            if not cov.complete:
                log.warning(
                    "no %s data for %s -- %s",
                    type(self).__name__,
                    ", ".join(cov.unserved),
                    self.describe(),
                )
        return records

    def _candidates(self, airports: Sequence[str] | None) -> list[Provider]:
        if airports is None:
            return list(self.providers)
        return [p for p in self.providers if any(p.might_cover(a) for a in airports)]

    def coverage(self, airports: Sequence[str], records: pd.DataFrame) -> Coverage:
        """Work out, from loaded data, who ended up serving each airport."""
        served: dict[str, str] = {}
        for name, group in records.groupby("provider", observed=True):
            seen: set[str] = set()
            for col in self.airport_columns:
                seen |= set(group[col].astype(str))
            for airport in airports:
                if airport in seen and airport not in served:
                    served[airport] = str(name)
        return Coverage(
            requested=tuple(airports),
            served=served,
            unserved=tuple(a for a in airports if a not in served),
            providers_used=tuple(sorted(set(served.values()))),
        )

    def describe(self) -> str:
        """One-line summary of what these providers can see."""
        return "; ".join(f"{p.name} covers {p.coverage}" for p in self.providers)

    def __repr__(self) -> str:  # pragma: no cover
        return f"{type(self).__name__}(providers={[p.name for p in self.providers]})"
