"""common.health -- personal health data from the Google Health API.

    from common.health import GoogleHealth

    gh = GoogleHealth()                                   # needs a one-time login,
    steps = gh.load_range("steps", "2026-01-01", "2026-03-31")   # see auth.py
    sleep = gh.load_range("sleep", "2026-03-01", "2026-03-31")

Sign in once with ``python -m common.health auth``.
"""

from .activity import daily_exercise, exercise_bouts
from .auth import DEFAULT_SCOPES, AuthError, GoogleHealthAuth
from .google import COMMON_TYPES, GoogleHealth, flatten_datapoints, kind_of, month_filter
from .sleep import STAGES, main_sleeps, nightly, stage_segments, stage_table
from .sleep_model import Night, StageModel, nights_on_grid
from .timeutil import utc, wall_clock

__all__ = [
    "GoogleHealth",
    "GoogleHealthAuth",
    "AuthError",
    "DEFAULT_SCOPES",
    "COMMON_TYPES",
    "flatten_datapoints",
    "kind_of",
    "month_filter",
    "nightly",
    "stage_segments",
    "stage_table",
    "main_sleeps",
    "STAGES",
    "StageModel",
    "Night",
    "nights_on_grid",
    "utc",
    "wall_clock",
    "exercise_bouts",
    "daily_exercise",
]
