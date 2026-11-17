"""viz -- the visualization library.

One validated palette in :mod:`viz.theme`, consumed by role rather than by hex,
so light and dark stay in sync. :mod:`viz.charts` holds the matplotlib forms;
:mod:`viz.animate` holds manim scenes drawing from the same palette (imported
only on demand, since manim is an optional dependency).
"""

from .theme import DARK, LIGHT, SEQUENTIAL_BLUE, THEMES, Theme, ramp, stage_color, styled
from . import sleep
from .charts import (
    axes_aspect,
    centered_bbox,
    clock_axis,
    clock_label,
    day_timeline,
    diverging_hbar,
    dual_axis_lines,
    dumbbell,
    hbar_ranking,
    hours_since,
    legend_above,
    line_curve,
    percent_axis,
    render,
    rounded_bar,
    scatter,
    capitalize_legends,
    legend_case,
    sign,
    titles,
)

__all__ = [
    "Theme",
    "LIGHT",
    "DARK",
    "THEMES",
    "SEQUENTIAL_BLUE",
    "styled",
    "sleep",
    "stage_color",
    "ramp",
    "render",
    "hbar_ranking",
    "dumbbell",
    "diverging_hbar",
    "scatter",
    "line_curve",
    "percent_axis",
    "titles",
    "sign",
    "legend_case",
    "capitalize_legends",
    "day_timeline",
    "dual_axis_lines",
    "rounded_bar",
    "axes_aspect",
    "centered_bbox",
    "hours_since",
    "legend_above",
    "clock_axis",
    "clock_label",
]
