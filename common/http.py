"""Polite, retrying HTTP client shared by every source.

The rules baked in here are the ones you want on *every* scrape: identify
yourself, back off on 429/5xx, rate-limit yourself, and never download the same
bytes twice.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .cache import Cache

log = logging.getLogger(__name__)

USER_AGENT = (
    "data-scrape/0.1 (research/personal use; +https://github.com/) python-requests"
)


class Fetcher:
    """A ``requests.Session`` with retries, a rate limit, and a disk cache.

    Parameters
    ----------
    min_interval:
        Minimum seconds between requests to be polite to the host.
    cache:
        Where downloads land. Pass a namespaced cache per source.
    """

    def __init__(
        self,
        cache: Cache | None = None,
        min_interval: float = 1.0,
        timeout: float = 60.0,
        user_agent: str = USER_AGENT,
    ) -> None:
        self.cache = cache or Cache()
        self.min_interval = min_interval
        self.timeout = timeout
        self._last_request = 0.0

        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        retry = Retry(
            total=5,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request = time.monotonic()

    def get(self, url: str, **kwargs) -> requests.Response:
        """Rate-limited GET that raises on HTTP error."""
        self._wait()
        log.debug("GET %s", url)
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp

    def get_json(self, url: str, **kwargs):
        return self.get(url, **kwargs).json()

    def download(self, url: str, name: str | None = None, force: bool = False) -> Path:
        """Stream a URL to the cache and return its path.

        Skips the network entirely if the file is already cached.
        """
        name = name or self.cache.key_for_url(url)
        dest = self.cache.path(name)
        if dest.exists() and dest.stat().st_size > 0 and not force:
            log.info("cached: %s", dest.name)
            return dest

        self._wait()
        log.info("downloading %s -> %s", url, dest.name)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with self.session.get(url, stream=True, timeout=self.timeout) as resp:
            resp.raise_for_status()
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
        tmp.replace(dest)
        return dest
