"""Common shape for every data source in the toolkit.

A source owns three things: where the raw bytes come from, how to turn them into
a tidy DataFrame, and where both live on disk. Subclasses implement ``_download``
and ``_parse``; the caching/parquet plumbing is inherited.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from ..cache import Cache
from ..http import Fetcher

log = logging.getLogger(__name__)


class Source(ABC):
    """Base class for a cached, parquet-backed data source.

    The contract is ``load(key) -> DataFrame``. Behind it:

    1. ``_download(key)`` fetches raw bytes into the cache (skipped if present).
    2. ``_parse(path)`` turns them into a tidy DataFrame.
    3. The result is written to parquet so step 2 only ever runs once.
    """

    #: cache sub-directory, e.g. ``"bts"``
    name: str = "source"

    def __init__(self, cache: Cache | None = None, min_interval: float = 1.0) -> None:
        self.cache = (cache or Cache()).namespace(self.name)
        self.fetcher = Fetcher(cache=self.cache, min_interval=min_interval)

    @abstractmethod
    def _download(self, key: str) -> Path:
        """Fetch raw data for ``key`` into the cache, return its path."""

    @abstractmethod
    def _parse(self, raw: Path) -> pd.DataFrame:
        """Turn a raw cached file into a tidy DataFrame."""

    def _parquet_path(self, key: str) -> Path:
        return self.cache.path(f"parsed/{key}.parquet")

    def _is_final(self, key: str) -> bool:
        """Whether ``key``'s data can no longer change upstream.

        Historical feeds (the default) are always final. Sources that can be
        asked about a period still in progress -- this month's weather, today's
        steps -- override this so an open period is never frozen into the
        cache. They should also pass ``force=not self._is_final(key)`` when
        downloading so the raw file is refreshed too.
        """
        return True

    def load(self, key: str, force: bool = False) -> pd.DataFrame:
        """Return the tidy DataFrame for ``key``, doing as little work as possible."""
        pq = self._parquet_path(key)
        final = self._is_final(key)
        if pq.exists() and not force and final:
            log.info("[%s] reading cached parquet %s", self.name, pq.name)
            return pd.read_parquet(pq)

        raw = self._download(key)
        df = self._parse(raw)
        if final:
            df.to_parquet(pq, index=False)
        else:
            pq.unlink(missing_ok=True)
            log.info("[%s] %s is still open upstream; not caching parquet", self.name, key)
        log.info("[%s] parsed %s -> %d rows", self.name, key, len(df))
        return df

    def load_many(self, keys: list[str], force: bool = False) -> pd.DataFrame:
        """Concatenate several keys (e.g. a run of months) into one frame."""
        frames = [self.load(k, force=force) for k in keys]
        return pd.concat(frames, ignore_index=True)
