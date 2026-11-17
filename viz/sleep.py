"""Sleep charts, built on :func:`viz.charts.day_timeline`.

These take the tidy tables from :mod:`common.health` (``night``,
``start_local``, ``end_local`` columns) so a script goes straight from data to
chart without re-deriving hours-after-midnight or stage colours.
"""

from __future__ import annotations

from typing import Sequence

import matplotlib.pyplot as plt
import pandas as pd

from . import charts
from .theme import Theme, stage_color

#: How stages are named in labels.
STAGE_NAMES = {"deep": "deep sleep", "rem": "REM sleep", "light": "light sleep",
               "awake": "awake"}


def spans(df: pd.DataFrame, day_col: str = "night"):
    """``(days, starts, ends)`` for :func:`charts.day_timeline`, with times as
    hours after each row's ``day_col`` midnight."""
    return (df[day_col], charts.hours_since(df["start_local"], df[day_col]),
            charts.hours_since(df["end_local"], df[day_col]))


def stage_timeline(
    ax: plt.Axes,
    theme: Theme,
    stage: str,
    segments: pd.DataFrame,
    sessions: pd.DataFrame | None = None,
    *,
    lines: Sequence[tuple[str, Sequence, Sequence[float], str | None]] = (),
    missed: pd.DataFrame | None = None,
    min_range: tuple[float, float] | None = (0, 12),
    legend_ncol: int | None = None,
    mark_jumps: float | None = 0.5,
) -> None:
    """Days across, time of day up: one rounded bar per stretch of ``stage``.

    ``segments`` is :func:`common.health.stage_segments` output.
    ``sessions`` (raw ``sleep`` rows) adds a grey bar per whole session
    behind. ``missed`` (:meth:`common.health.StageModel.missed` output) adds
    pink bars where the stage was predicted but didn't happen. ``lines`` are
    reference curves in hours after midnight, e.g. sunrise or an average
    wake-up time. Everything sits in the column of the morning the night ended.
    ``mark_jumps`` labels clock changes on the lines (see
    :func:`charts.day_timeline`); pass ``None`` for lines that are jumpy by
    nature, such as a one-day average.
    """
    name = STAGE_NAMES.get(stage, stage)
    behind = None
    if sessions is not None:
        behind = spans(sessions.assign(night=sessions["end_local"].dt.normalize()))
    overlays = []
    if missed is not None:
        overlays.append((f"predicted {name} that didn't happen", *spans(missed),
                         theme.slot(4)))                              # pink
    charts.day_timeline(
        ax, theme, *spans(segments),
        bar_label=name, bar_color=stage_color(theme, stage),
        behind=behind, behind_label="asleep (any stage)" if behind else None,
        overlays=overlays, lines=lines, min_range=min_range, legend_ncol=legend_ncol,
        mark_jumps=mark_jumps,
    )
