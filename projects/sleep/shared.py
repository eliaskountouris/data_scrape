"""Glue shared by the sleep projects.

Everything here is specific to *these* investigations (my home location, the
default date window, how the scripts take arguments), which is why it lives
beside them rather than in ``common/``. Each ``run.py`` imports it with::

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import shared
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common import project_out  # noqa: E402
from common.health import GoogleHealth  # noqa: E402
from common.weather import Location  # noqa: E402

#: Where I sleep: the default for anything that needs sunrise or weather.
HOME = Location(37.7749, -122.4194, "San Francisco")

#: Default look-back for every sleep script.
DEFAULT_DAYS = 180

STAGE_CHOICES = ("deep", "light", "rem")

HEALTH_SOURCE = "Source: Google Health API (sleep stages)"
WEATHER_SOURCE = "Weather data by Open-Meteo.com"


def parser(doc: str, project: str, *, stages: bool = False,
           location: bool = False) -> argparse.ArgumentParser:
    """An argument parser with the options every sleep script shares.

    Always: ``--start``/``--end`` (default: the last 180 days ending
    yesterday) and ``--out`` (default ``build/sleep/<project>/``). With
    ``stages``: ``--stages`` (default deep and REM). With ``location``:
    ``--lat``/``--lon``/``--place`` (default :data:`HOME`). Scripts add their
    own options on top.
    """
    p = argparse.ArgumentParser(description=doc,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    yesterday = dt.date.today() - dt.timedelta(days=1)
    p.add_argument("--start", default=str(yesterday - dt.timedelta(days=DEFAULT_DAYS)),
                   help=f"first day (default: {DEFAULT_DAYS} days before --end)")
    p.add_argument("--end", default=str(yesterday), help="last day (default: yesterday)")
    p.add_argument("--out", type=Path, default=project_out(f"sleep/{project}"))
    if stages:
        p.add_argument("--stages", nargs="+", default=["deep", "rem"],
                       choices=STAGE_CHOICES, help="stages to chart")
    if location:
        p.add_argument("--lat", type=float, default=HOME.latitude, help="where you sleep")
        p.add_argument("--lon", type=float, default=HOME.longitude)
        p.add_argument("--place", default=None,
                       help=f"label for charts (default: {HOME.name} at the default coordinates)")
    return p


def parse(p: argparse.ArgumentParser) -> argparse.Namespace:
    """Parse arguments, set up logging and make the output folder."""
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args.out.mkdir(parents=True, exist_ok=True)
    return args


def where(args: argparse.Namespace) -> Location:
    """The location from ``--lat/--lon/--place``, named after :data:`HOME`
    when the coordinates are the defaults."""
    is_home = (args.lat, args.lon) == (HOME.latitude, HOME.longitude)
    return Location(args.lat, args.lon, args.place or (HOME.name if is_home else None))


_health: GoogleHealth | None = None


def load(data_type: str, start, end):
    """A Google Health data type for the inclusive range, from one shared
    client, so scripts that need several types reuse one session."""
    global _health
    if _health is None:
        _health = GoogleHealth()
    return _health.load_range(data_type, start, end)


def load_sleep(args: argparse.Namespace, extra_days: int = 0):
    """``sleep`` for ``--start``..``--end`` (plus ``extra_days`` after the end,
    never past today), exiting with a clear message when there is none."""
    end = min(dt.date.fromisoformat(str(args.end)) + dt.timedelta(days=extra_days),
              dt.date.today())
    sleep = load("sleep", args.start, end)
    if sleep.empty:
        sys.exit(f"no sleep data between {args.start} and {end}")
    return sleep
