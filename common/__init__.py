"""common -- shared scraping helpers.

The generic layer: a polite HTTP client, an on-disk cache, and the ``Source``
base class every dataset plugs into. Dataset-specific helpers live in
subpackages (:mod:`common.flights`, ...).
"""

from .cache import Cache
from .http import Fetcher
from .paths import BUILD_ROOT, CACHE_ROOT, CONFIG_ROOT, MEDIA_ROOT, REPO_ROOT, project_out
from .sources import Source

__version__ = "0.1.0"
__all__ = [
    "Cache",
    "Fetcher",
    "Source",
    "BUILD_ROOT",
    "CACHE_ROOT",
    "CONFIG_ROOT",
    "MEDIA_ROOT",
    "REPO_ROOT",
    "project_out",
]
