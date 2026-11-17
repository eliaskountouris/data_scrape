"""Where generated files go.

Everything the toolkit produces -- downloads, parsed parquet, charts, tables,
rendered animations -- lands under a single ``build/`` root so the repo can
ignore one directory and a clean rebuild is one ``rm -rf``. Nothing outside
this module should hardcode an output path.

Override the root with ``$SCRAPE_BUILD`` (useful for scratch runs or CI).
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

BUILD_ROOT = Path(os.environ.get("SCRAPE_BUILD", REPO_ROOT / "build"))

#: Scraped artifacts: raw downloads and the parsed parquet beside them.
CACHE_ROOT = BUILD_ROOT / "cache"

#: Rendered manim output.
MEDIA_ROOT = BUILD_ROOT / "media"

#: Credentials and OAuth tokens. Deliberately *outside* ``build/`` so that a
#: clean rebuild doesn't log you out, and outside the repo so they can't be
#: committed. Override with ``$SCRAPE_CONFIG``.
CONFIG_ROOT = Path(
    os.environ.get(
        "SCRAPE_CONFIG",
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "data_scrape",
    )
)


def project_out(name: str) -> Path:
    """Output directory for one project, e.g. ``build/flights/week0_delays/``."""
    return BUILD_ROOT / name
