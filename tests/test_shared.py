"""Shared helpers promoted out of projects: stats and Google Health time."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.health.timeutil import offset_seconds, utc, wall_clock  # noqa: E402
from common.stats import correlate, correlation_table  # noqa: E402


def test_correlate_reports_both_coefficients_p_and_n():
    df = pd.DataFrame({"x": range(40), "y": [v * 2 + (v % 3) for v in range(40)],
                       "z": [None] * 5 + list(range(35))})
    c = correlate(df, "x", "y")
    assert c.pearson > 0.99 and c.spearman > 0.99 and c.p < 0.001 and c.n == 40
    assert correlate(df, "x", "z").n == 35           # NaN rows dropped
    r, rho, p, n = c                                 # unpacks like a tuple
    assert "n=40" in str(c)


def test_correlate_too_few_rows_is_nan_not_an_error():
    c = correlate(pd.DataFrame({"x": [1, 2], "y": [2, 1]}), "x", "y")
    assert c.n == 2 and pd.isna(c.pearson)


def test_correlation_table_one_row_per_driver():
    df = pd.DataFrame({"a": range(10), "b": range(10, 0, -1), "y": range(10)})
    t = correlation_table(df, ["a", "b"], "y")
    assert list(t["driver"]) == ["a", "b"]
    assert t.set_index("driver").loc["b", "spearman"] == pytest.approx(-1)


def test_wall_clock_applies_the_recorded_offset():
    assert utc("2026-11-16T10:02:00Z") == pd.Timestamp("2026-11-16 10:02", tz="UTC")
    assert offset_seconds("-28800s") == -28800 and offset_seconds(None) == 0
    assert wall_clock("2026-11-16T10:02:00Z", "-28800s") == pd.Timestamp("2026-11-16 02:02")
    assert wall_clock(utc("2026-11-16T10:02:00Z"), "3600s") == pd.Timestamp("2026-11-16 11:02")


def test_trailing_mean_uses_only_the_days_before():
    from common.stats import trailing_mean

    s = pd.Series(range(20), index=pd.date_range("2026-01-01", periods=20))
    s = s.drop(pd.Timestamp("2026-01-16"))
    t = trailing_mean(s, days=14, min_periods=7)
    assert t.loc["2026-01-15"] == sum(range(14)) / 14         # Jan 1-14, not the 15th
    assert t.loc["2026-01-16"] == sum(range(1, 15)) / 14      # a value even on a missing day
    assert pd.isna(t.loc["2026-01-07"])                        # only 6 prior days
    assert t.loc["2026-01-08"] == 3.0
    inc = trailing_mean(s, days=14, min_periods=7, include_current=True)
    assert inc.loc["2026-01-15"] == sum(range(1, 15)) / 14    # 14 days ending on the 15th


def test_stage_timeline_draws_stage_sessions_and_lines(tmp_path):
    import matplotlib

    matplotlib.use("Agg")
    from viz import render
    from viz import sleep as vsleep

    night = pd.Timestamp("2026-11-16")
    seg = pd.DataFrame({"night": [night], "start_local": [night + pd.Timedelta(hours=1)],
                        "end_local": [night + pd.Timedelta(hours=1.5)]})
    sessions = pd.DataFrame({"start_local": [night - pd.Timedelta(hours=0.5)],
                             "end_local": [night + pd.Timedelta(hours=8)]})

    def draw(fig, theme):
        ax = fig.subplots()
        vsleep.stage_timeline(ax, theme, "rem", seg, sessions,
                              lines=[("average wake-up", [night], [8.5], theme.slot(7))])
        labels = [t.get_text() for t in ax.get_legend().get_texts()]
        assert labels == ["asleep (any stage)", "REM sleep", "average wake-up"]
        assert len(ax.patches) == 2

    render(draw, tmp_path / "t", modes=("light",))
