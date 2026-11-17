"""On-disk cache for scraped artifacts.

Everything a source downloads lands here, keyed by a stable name, so re-running a
scrape is free and reproducible. Nothing here knows about HTTP -- it just hands
out paths and answers "do I already have this?".
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .paths import CACHE_ROOT as DEFAULT_ROOT


class Cache:
    """A namespaced directory of downloaded files.

    >>> cache = Cache().namespace("bts")
    >>> path = cache.path("2025_01.zip")
    """

    def __init__(self, root: Path | str = DEFAULT_ROOT) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def namespace(self, name: str) -> "Cache":
        """Return a sub-cache, e.g. ``data/bts/``."""
        return Cache(self.root / name)

    def path(self, name: str) -> Path:
        """Absolute path a given cache entry would live at (may not exist)."""
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def has(self, name: str) -> bool:
        p = self.root / name
        return p.exists() and p.stat().st_size > 0

    def key_for_url(self, url: str, suffix: str = "") -> str:
        """Stable filename for a URL, for when there's no natural name."""
        return hashlib.sha256(url.encode()).hexdigest()[:16] + suffix

    def __repr__(self) -> str:  # pragma: no cover
        return f"Cache({self.root})"
