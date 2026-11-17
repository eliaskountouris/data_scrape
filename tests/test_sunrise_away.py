"""Sunrise project: nights in another time zone are detected. No network."""

import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("sunrise_run", ROOT / "projects/sleep/sunrise/run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def test_away_from_uses_the_locations_offset_on_that_date():
    nights = pd.DataFrame({
        "wake_time": pd.to_datetime(["2026-10-30 15:00", "2026-11-03 16:00",
                                     "2026-11-07 13:00"], utc=True),
        # PDT at home, PST at home after the clock change, then New York
        "utc_offset_h": [-7.0, -8.0, -5.0],
    })
    assert run.away_from(nights, "America/Los_Angeles").tolist() == [False, False, True]
