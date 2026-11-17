"""The base contract between providers and analysis.

A schema names the columns a dataset guarantees. Required columns are enforced
when a provider's output is loaded; optional ones are backfilled with NA so
downstream code can rely on their existence without every provider having to
supply them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pandas as pd


@dataclass(frozen=True, slots=True)
class Column:
    """One column of a canonical schema."""

    name: str
    description: str
    required: bool = True


class SchemaError(ValueError):
    """A provider returned data the analysis layer cannot use."""


class TableSchema:
    """Base class for a dataset's column contract.

    Subclasses declare :attr:`COLUMNS`; everything else is inherited.
    """

    COLUMNS: ClassVar[tuple[Column, ...]] = ()

    @classmethod
    def required(cls) -> tuple[str, ...]:
        return tuple(c.name for c in cls.COLUMNS if c.required)

    @classmethod
    def optional(cls) -> tuple[str, ...]:
        return tuple(c.name for c in cls.COLUMNS if not c.required)

    @classmethod
    def validate(cls, df: pd.DataFrame, provider: str) -> pd.DataFrame:
        """Enforce the contract, backfilling optional columns.

        Raises
        ------
        SchemaError
            If a required column is missing -- a provider that cannot supply
            one is broken, not merely limited, so this fails rather than warns.
        """
        missing = [c for c in cls.required() if c not in df.columns]
        if missing:
            raise SchemaError(
                f"provider {provider!r} is missing required columns {missing}. "
                f"Required: {list(cls.required())}"
            )
        for name in cls.optional():
            if name not in df.columns:
                df[name] = pd.NA
        return df

    @classmethod
    def describe(cls) -> str:
        """Readable column reference, for docs and error messages."""
        return "\n".join(
            f"{c.name:<22}{'required' if c.required else 'optional':<10}{c.description}"
            for c in cls.COLUMNS
        )
