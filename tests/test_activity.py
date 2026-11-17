"""Exercise de-duplication and the dual-axis chart. No network."""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.health import daily_exercise, exercise_bouts  # noqa: E402
from viz import charts, render  # noqa: E402


def session(start, end, active_min, kind="STRENGTH_TRAINING"):
    return {"start_local": pd.Timestamp(start), "end_local": pd.Timestamp(end),
            "active_duration_s": active_min * 60 if active_min is not None else None,
            "exercise_type": kind}


EX = pd.DataFrame([
    # the same workout recorded by watch and phone
    session("2026-11-09 20:35", "2026-11-09 22:12", 95),
    session("2026-11-09 20:36", "2026-11-09 21:24", 47),
    # a separate walk later that day
    session("2026-11-09 23:00", "2026-11-09 23:20", None, "WALKING"),
    session("2026-11-11 07:00", "2026-11-11 07:30", 30, "WALKING"),
])


def test_overlapping_recordings_merge_into_one_bout():
    b = exercise_bouts(EX)
    assert len(b) == 3
    first = b.iloc[0]
    assert first["recordings"] == 2 and first["minutes"] == 95   # longest, not summed
    assert b.iloc[1]["minutes"] == 20                             # elapsed when no active time


def test_daily_exercise_fills_rest_days_with_zero():
    d = daily_exercise(EX, "2026-11-09", "2026-11-11").set_index("day")
    assert d.loc["2026-11-09", "exercise_min"] == 115
    assert d.loc["2026-11-09", "workouts"] == 2
    assert d.loc["2026-11-10", "exercise_min"] == 0               # a real zero
    assert d.loc["2026-11-11", "exercise_min"] == 30


def test_no_exercise_at_all():
    assert exercise_bouts(EX.iloc[0:0]).empty


def test_dual_axis_lines_share_one_legend(tmp_path):
    days = pd.date_range("2026-11-01", periods=4)

    def draw(fig, theme):
        ax = fig.subplots()
        ax2 = charts.dual_axis_lines(
            ax, theme,
            left=[("deep sleep", days, [80, None, 70, 90], None),
                  ("REM sleep", days, [100, 90, None, 95], None)],
            right=[("exercise", days, [0, 1.5, 0, 0.5], None)],
            left_label="minutes", right_label="hours")
        assert ax2 is not None and ax2.get_ylim()[0] == 0
        assert len(ax.get_lines()) == 2 and len(ax2.get_lines()) == 1
        assert fig.legends == [] and ax2.get_legend() is None

    render(draw, tmp_path / "dual", modes=("light",))
