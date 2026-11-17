"""Reusable chart forms.

Each helper draws one *form* onto an axes and takes the theme explicitly, so the
same call renders correctly in light and dark. Use :func:`render` to get both
modes from a single draw function.

Form guide: bars for magnitude compared across categories, dumbbells for the
gap between two conditions on the same category, lines for a trend along a
continuous axis, a day timeline for *when* things happen across many days.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path
from typing import Callable, Sequence

import math

import matplotlib.colors as mcolors
import matplotlib.dates as mdates
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.legend_handler import HandlerPatch
from matplotlib.patches import FancyBboxPatch, Patch
from matplotlib.transforms import Bbox
from matplotlib.ticker import FuncFormatter, MultipleLocator
from matplotlib.ticker import PercentFormatter

from .theme import Theme, styled

#: Who signs every chart. ``$SCRAPE_AUTHOR`` overrides it.
AUTHOR = os.environ.get("SCRAPE_AUTHOR", "Elias Kountouris")


def render(
    draw: Callable[[plt.Figure, Theme], None],
    out_stem: Path | str,
    figsize: tuple[float, float] = (9, 6),
    modes: Sequence[str] = ("light", "dark"),
    center: bool = True,
) -> list[Path]:
    """Run ``draw`` once per mode and save ``<stem>.png`` / ``<stem>-dark.png``.

    ``draw`` receives the figure and the active theme; it is responsible for
    creating its own axes so multi-panel figures work too. With ``center`` (the
    default) the plot area sits in the horizontal middle of the image; see
    :func:`centered_bbox`.
    """
    out_stem = Path(out_stem)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for mode in modes:
        with styled(mode) as theme:
            fig = plt.figure(figsize=figsize)
            draw(fig, theme)
            capitalize_legends(fig)
            sign(fig, theme)
            suffix = "" if mode == "light" else f"-{mode}"
            path = out_stem.with_name(out_stem.name + suffix).with_suffix(".png")
            fig.savefig(path, bbox_inches=centered_bbox(fig) if center else "tight")
            plt.close(fig)
            written.append(path)
    return written


def centered_bbox(fig: plt.Figure, pad: float = 0.15) -> Bbox:
    """The region to save, in inches, so the plot area is horizontally centred.

    A tight crop puts the edge of the image right against whatever sticks out
    furthest, and axis labels stick out on the left, so the plot itself always
    lands right of centre. This takes the tight crop and widens whichever side
    is narrower until the margins either side of the plot area (the union of
    all axes) are equal. Vertically it stays tight.
    """
    renderer = fig.canvas.get_renderer()
    tight = fig.get_tightbbox(renderer)                     # inches
    axes = [ax.get_window_extent(renderer) for ax in fig.axes]
    if not axes:
        return tight.padded(pad)
    plot = Bbox.union(axes).transformed(fig.dpi_scale_trans.inverted())
    margin = max(plot.x0 - tight.x0, tight.x1 - plot.x1)
    return Bbox.from_extents(plot.x0 - margin, tight.y0,
                             plot.x1 + margin, tight.y1).padded(pad)


_WORD_START = re.compile(r"(^|\s)([(\[\"'“‘]*)([a-z])")


def legend_case(label: str) -> str:
    """Capitalise the first letter of every word, leaving the rest alone.

    Unlike ``str.title`` it keeps acronyms and mixed case intact (``SFO``
    stays ``SFO``, not ``Sfo``) and doesn't touch words that start with a digit
    (``7-night`` stays put). Words opening with a bracket or quote are
    capitalised after it: ``(any stage)`` becomes ``(Any Stage)``.
    """
    return _WORD_START.sub(lambda m: m.group(1) + m.group(2) + m.group(3).upper(), label)


def capitalize_legends(fig: plt.Figure) -> None:
    """Apply :func:`legend_case` to every legend entry on the figure.

    :func:`render` calls this after drawing, so it's the default for every
    chart however its legend was made.
    """
    legends = list(fig.legends) + [ax.get_legend() for ax in fig.axes]
    for legend in legends:
        if legend is None:
            continue
        for text in legend.get_texts():
            text.set_text(legend_case(text.get_text()))


def sign(fig: plt.Figure, theme: Theme, author: str = AUTHOR,
         when: dt.date | None = None) -> None:
    """Author and generation date, bottom left, under anything already there
    (the source line, say). :func:`render` calls this for every chart."""
    when = when or dt.date.today()
    # Measure where existing text actually ends, so a source note that wraps
    # onto several lines pushes the signature down rather than overlapping it.
    renderer = fig.canvas.get_renderer()
    to_fig = fig.transFigure.inverted()
    bottoms = [t.get_window_extent(renderer).transformed(to_fig).y0 for t in fig.texts]
    gap = 10 / 72 / fig.get_figheight()           # ~10 pt, in figure fractions
    top = min(min(bottoms, default=0.0), 0.0) - gap if bottoms else -0.02
    fig.text(
        0.005, top, f"{author} {when:%Y/%m/%d}",
        fontsize=8, color=theme.text_muted, va="top", ha="left",
    )


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def percent_axis(ax: plt.Axes, which: str = "x", decimals: int = 0) -> None:
    """Show a 0-1 fraction axis as percentages.

    Mixing ``0.14`` on the axis with ``13.4%`` on the labels makes a reader do
    arithmetic; always match the units.
    """
    axis = ax.xaxis if which == "x" else ax.yaxis
    axis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=decimals))


def hbar_ranking(
    ax: plt.Axes,
    labels: Sequence[str],
    values: Sequence[float],
    theme: Theme,
    color: str | None = None,
    value_fmt: Callable[[float], str] = _pct,
    reference: float | None = None,
    reference_label: str = "average",
    percent: bool = True,
) -> None:
    """Sorted horizontal bars with a direct value label on each.

    Highest value at the top. A single series carries no legend -- the title
    names it.
    """
    color = color or theme.slot(0)
    y = range(len(labels))
    # Thin bars: the gap between them is what makes a ranking scannable.
    ax.barh(y, values, height=0.62, color=color, zorder=3)
    ax.set_yticks(list(y), list(labels))
    ax.invert_yaxis()

    ax.grid(axis="x", zorder=0)
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)

    if percent:
        percent_axis(ax, "x")

    span = max(values) if len(values) else 1.0
    for yi, v in zip(y, values):
        ax.text(
            v + span * 0.015,
            yi,
            value_fmt(v),
            va="center",
            ha="left",
            fontsize=9,
            color=theme.text_secondary,
            zorder=5,
            # Halo so a label stays readable where it crosses the reference line.
            path_effects=[pe.withStroke(linewidth=3, foreground=theme.surface)],
        )
    ax.set_xlim(0, span * 1.16)

    if reference is not None:
        ax.axvline(
            reference, color=theme.text_muted, linewidth=1.2, linestyle=(0, (4, 3)),
            zorder=4,
        )
        ax.text(
            reference,
            -0.85,
            f"  {reference_label} {value_fmt(reference)}",
            fontsize=9,
            color=theme.text_muted,
            va="center",
            ha="left",
        )


def dumbbell(
    ax: plt.Axes,
    labels: Sequence[str],
    left: Sequence[float],
    right: Sequence[float],
    theme: Theme,
    left_label: str,
    right_label: str,
    value_fmt: Callable[[float], str] = _pct,
    percent: bool = True,
) -> None:
    """Two conditions per category, joined by a connector.

    Reads as "how big is the gap", which a grouped bar chart buries.
    """
    c_left, c_right = theme.slot(0), theme.slot(1)
    y = list(range(len(labels)))

    for yi, a, b in zip(y, left, right):
        ax.plot([a, b], [yi, yi], color=theme.grid, linewidth=2.5, zorder=2)

    # A 2px surface ring keeps the dots legible where they nearly overlap.
    common = dict(zorder=3, markersize=9, linestyle="none",
                  markeredgecolor=theme.surface, markeredgewidth=2)
    ax.plot(list(left), y, marker="o", color=c_left, label=left_label, **common)
    ax.plot(list(right), y, marker="o", color=c_right, label=right_label, **common)

    ax.set_yticks(y, list(labels))
    ax.invert_yaxis()
    ax.grid(axis="x", zorder=0)
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    if percent:
        percent_axis(ax, "x")
    # Above the plot area, not inside it -- with a full-height dumbbell stack
    # there is no empty corner for a legend to sit in.
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.005), ncols=2)

    lo = min(min(left), min(right))
    hi = max(max(left), max(right))
    pad = (hi - lo) * 0.12
    ax.set_xlim(max(0.0, lo - pad), hi + pad)


def diverging_hbar(
    ax: plt.Axes,
    labels: Sequence[str],
    values: Sequence[float],
    theme: Theme,
    baseline: float = 0.0,
    low_label: str = "below average",
    high_label: str = "above average",
    value_fmt: Callable[[float], str] = lambda v: f"{v:.2f}",
) -> None:
    """Horizontal bars measured from a reference value.

    For quantities read as "above or below par" -- an index around 1.0, a
    change against a benchmark. Bars grow away from ``baseline`` in one of two
    hues, with the reference itself drawn as the spine.
    """
    c_low, c_high = theme.diverging
    y = list(range(len(labels)))
    colors = [c_high if v >= baseline else c_low for v in values]

    ax.barh(
        y,
        [v - baseline for v in values],
        left=baseline,
        height=0.62,
        color=colors,
        zorder=3,
    )
    ax.set_yticks(y, list(labels))
    ax.invert_yaxis()
    ax.grid(axis="x", zorder=0)
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)

    ax.axvline(baseline, color=theme.text_secondary, linewidth=1.2, zorder=4)

    span = max(abs(v - baseline) for v in values) if len(values) else 1.0
    for yi, v in zip(y, values):
        beyond = v >= baseline
        ax.text(
            v + (span * 0.03 if beyond else -span * 0.03),
            yi,
            value_fmt(v),
            va="center",
            ha="left" if beyond else "right",
            fontsize=9,
            color=theme.text_secondary,
            zorder=5,
            path_effects=[pe.withStroke(linewidth=3, foreground=theme.surface)],
        )
    ax.set_xlim(baseline - span * 1.25, baseline + span * 1.25)

    # Identity is never colour alone: name both poles.
    handles = [
        Patch(facecolor=c_high, label=high_label),
        Patch(facecolor=c_low, label=low_label),
    ]
    ax.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.0, 1.005), ncols=2)


def scatter(
    ax: plt.Axes,
    x: Sequence[float],
    y: Sequence[float],
    theme: Theme,
    labels: Sequence[str] | None = None,
    annotate: Sequence[str] = (),
    color: str | None = None,
    sizes: Sequence[float] | None = None,
    max_size: float = 320.0,
    trend: bool = False,
    weights: Sequence[float] | None = None,
) -> None:
    """One series of points, with selective direct labels.

    ``annotate`` names the few points worth calling out -- never every point.
    ``sizes`` encodes a third value as *area* (matplotlib's ``s`` is area in
    points squared, so a linear scale here is area-proportional and reads
    honestly). ``trend`` draws a least-squares line -- only use it when the
    caller also states the correlation, so a weak relationship isn't dressed up
    as a strong one. ``weights`` weights the trend line's fit, e.g. by how
    many observations each point averages, so a point built on one game
    doesn't count as much as one built on ten.
    """
    color = color or theme.slot(0)

    if sizes is None:
        s = 44.0
    else:
        peak = max(sizes) or 1.0
        s = [max_size * (v / peak) + 12 for v in sizes]

    ax.scatter(
        x, y,
        s=s,
        color=color,
        alpha=0.85 if sizes is not None else 1.0,
        edgecolors=theme.surface,
        linewidths=1.5,
        zorder=3,
    )

    if trend and len(x) > 1:
        # polyfit's w multiplies residuals, so sqrt(weight) weights squared error.
        w = None if weights is None else np.sqrt(np.asarray(weights, float))
        slope, intercept = np.polyfit(np.asarray(x, float), np.asarray(y, float), 1, w=w)
        xs = np.array([min(x), max(x)])
        ax.plot(
            xs, slope * xs + intercept,
            color=theme.text_muted,
            linewidth=1.5,
            linestyle=(0, (5, 3)),
            zorder=2,
        )
    ax.grid(zorder=0)
    # Direct labels sit outside their point, so leave room or they clip.
    ax.margins(x=0.10, y=0.10)

    if labels is not None and len(annotate):
        wanted = set(annotate)
        for xi, yi, name in zip(x, y, labels):
            if name in wanted:
                ax.annotate(
                    name,
                    (xi, yi),
                    textcoords="offset points",
                    xytext=(7, 4),
                    fontsize=9,
                    color=theme.text_secondary,
                    zorder=5,
                    path_effects=[pe.withStroke(linewidth=3, foreground=theme.surface)],
                )


def line_curve(
    ax: plt.Axes,
    x: Sequence[float],
    y: Sequence[float],
    theme: Theme,
    color: str | None = None,
    label: str | None = None,
    marker: str = "o",
) -> None:
    """A single trend along a continuous axis."""
    color = color or theme.slot(0)
    ax.plot(
        x, y,
        color=color,
        marker=marker,
        markersize=8,
        markeredgecolor=theme.surface,
        markeredgewidth=2,
        label=label,
        zorder=3,
    )
    ax.grid(axis="y", zorder=0)
    ax.grid(axis="x", visible=False)


def titles(
    fig: plt.Figure,
    ax: plt.Axes,
    theme: Theme,
    title: str,
    subtitle: str | None = None,
    source: str | None = None,
    subtitle_y: float = 1.035,
    title_pad: float | None = None,
) -> None:
    """The chart's source line, bottom left.

    Charts in this toolkit carry **no title or subtitle**: the axes, legend and
    source line have to explain the chart on their own. ``title`` and
    ``subtitle`` are still required at the call site as a description of what
    each chart shows, kept in the code where the next reader needs it, but
    they are never drawn. ``subtitle_y`` and ``title_pad`` are accepted and
    ignored so existing calls keep working.
    """
    if source:
        fig.text(
            0.005, -0.02, source,
            fontsize=8,
            color=theme.text_muted,
            va="top",
            ha="left",
        )


# -- day timeline ------------------------------------------------------------

def hours_since(ts: pd.Series, day: pd.Series) -> pd.Series:
    """Clock time as hours after ``day``'s midnight.

    Times before that midnight come out negative (23:30 the evening before ->
    -0.5), so an overnight event stays in one day's column.
    """
    return (pd.to_datetime(ts) - pd.to_datetime(day)) / pd.Timedelta(hours=1)


def clock_label(hours: float, _pos=None) -> str:
    """Hours after midnight -> wall-clock label (-1 -> ``23:00``, 26 -> ``02:00``)."""
    return f"{int(round(hours)) % 24:02d}:00"


def clock_axis(ax: plt.Axes, which: str = "y", step: float = 2) -> None:
    """Label an hours-after-midnight axis as clock times every ``step`` hours."""
    axis = ax.yaxis if which == "y" else ax.xaxis
    axis.set_major_locator(MultipleLocator(step))
    axis.set_major_formatter(FuncFormatter(clock_label))


def axes_aspect(ax: plt.Axes) -> float:
    """Data-y units per data-x unit *on screen*, at the current limits.

    Needed whenever something must look round on axes whose units differ
    (days across, hours up). Set the limits first.
    """
    fig = ax.figure
    bbox = ax.get_position()
    fw, fh = fig.get_size_inches()
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    return (abs(y1 - y0) / (bbox.height * fh)) / (abs(x1 - x0) / (bbox.width * fw))


def rounded_bar(
    ax: plt.Axes,
    x: float,
    bottom: float,
    width: float,
    height: float,
    color: str,
    aspect: float,
    roundness: float = 0.45,
    zorder: float = 2,
) -> FancyBboxPatch:
    """A bar with circular corners, centred on ``x``, spanning ``bottom`` +
    ``height``. Get ``aspect`` from :func:`axes_aspect`.

    Corners never take more than half the bar, so a very short bar becomes a
    pill rather than a blob that overstates its length.
    """
    radius = min(width * roundness, (abs(height) / 2) / aspect)
    patch = FancyBboxPatch(
        (x - width / 2, bottom), width, height,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        mutation_aspect=aspect,
        facecolor=color, edgecolor="none", zorder=zorder,
    )
    ax.add_patch(patch)
    return patch


class _RoundedHandler(HandlerPatch):
    """Legend key drawn as a rounded bar to match :func:`rounded_bar`."""

    def create_artists(self, legend, orig, xd, yd, width, height, fontsize, trans):
        r = min(width, height) * 0.45
        p = FancyBboxPatch((xd, yd), width, height,
                           boxstyle=f"round,pad=0,rounding_size={r}",
                           facecolor=orig.get_facecolor(), edgecolor="none",
                           transform=trans)
        return [p]


def day_timeline(
    ax: plt.Axes,
    theme: Theme,
    days: Sequence,
    starts: Sequence[float],
    ends: Sequence[float],
    *,
    bar_label: str | None = None,
    bar_color: str | None = None,
    lines: Sequence[tuple[str, Sequence, Sequence[float], str | None]] = (),
    behind: tuple[Sequence, Sequence[float], Sequence[float]] | None = None,
    behind_label: str | None = None,
    behind_color: str | None = None,
    overlays: Sequence[tuple[str, Sequence, Sequence[float], Sequence[float], str]] = (),
    width: float = 0.72,
    hour_step: float = 2,
    min_range: tuple[float, float] | None = None,
    invert: bool = False,
    mark_jumps: float | None = 0.5,
    jump_label: str = "clocks change",
    legend_ncol: int | None = None,
) -> None:
    """Days across, time of day up or down: *when* something happened, day by day.

    Each span (``days[i]``, ``starts[i]``..``ends[i]``) becomes one rounded bar
    in that day's column; times are hours after that day's midnight (see
    :func:`hours_since`), so they may be negative or exceed 24. ``lines`` adds
    one reference curve per ``(label, days, hours, color)`` -- sunrise, say --
    with an optional fifth element, a dict of plot styling such as
    ``{"linestyle": ":"}``. A line with an empty label stays out of the legend.
    ``legend_ncol`` wraps a long legend onto several rows.

    ``behind`` is a second set of ``(days, starts, ends)`` spans drawn as muted
    bars underneath -- the whole night behind its deep-sleep stretches, say.
    ``overlays`` adds more foreground series, each ``(label, days, starts,
    ends, color)``, drawn at the same level as the main bars -- predicted
    stretches that didn't happen, for instance.

    Time runs upward, the way time flows on every other axis in the toolkit
    (``invert=True`` flips it, but don't without a reason). ``min_range``
    guarantees the axis covers at least those hours -- ``(0, 12)`` keeps
    midnight-to-noon in view -- and still extends if the data goes further, so
    nothing is clipped. ``mark_jumps`` labels any line step bigger than that
    many hours with ``jump_label`` (a clock change, by default) so it doesn't
    read as a data error; ``None`` turns it off.
    """
    bar_color = bar_color or theme.slot(6)
    xs = mdates.date2num(pd.to_datetime(pd.Series(days)))
    starts, ends = np.asarray(starts, float), np.asarray(ends, float)
    # A line is (label, days, hours, color) plus an optional dict of plot
    # styling (linestyle, linewidth...). A falsy label keeps it out of the legend.
    line_data = [(ln[0], mdates.date2num(pd.to_datetime(pd.Series(ln[1]))),
                  np.asarray(ln[2], float), ln[3], ln[4] if len(ln) > 4 else {})
                 for ln in lines]

    if behind is not None:
        bx = mdates.date2num(pd.to_datetime(pd.Series(behind[0])))
        bs, be = np.asarray(behind[1], float), np.asarray(behind[2], float)
    else:
        bx = bs = be = np.array([])

    over_data = [(label, mdates.date2num(pd.to_datetime(pd.Series(d))),
                  np.asarray(a, float), np.asarray(b, float), color)
                 for label, d, a, b, color in overlays]

    all_x = np.concatenate([xs, bx, *(ox for _, ox, _, _, _ in over_data),
                            *(ld[1] for ld in line_data)])
    all_y = np.concatenate([starts, ends, bs, be,
                            *(v for _, _, oa, ob, _ in over_data for v in (oa, ob)),
                            *(ld[2] for ld in line_data)])
    all_y = all_y[~np.isnan(all_y)]
    lo, hi = math.floor(all_y.min() - 0.25), math.ceil(all_y.max() + 0.25)
    if min_range is not None:
        lo, hi = min(lo, min_range[0]), max(hi, min_range[1])
    ax.set_ylim((hi, lo) if invert else (lo, hi))
    ax.set_xlim(all_x.min() - 1, all_x.max() + 1)

    aspect = axes_aspect(ax)
    # Muted, so the foreground bars stay the subject. The surface colour
    # blended toward muted ink reads as grey in both modes.
    behind_color = behind_color or mcolors.to_hex(
        0.72 * np.array(mcolors.to_rgb(theme.surface))
        + 0.28 * np.array(mcolors.to_rgb(theme.text_muted))
    )
    for x, a, b in zip(bx, bs, be):
        rounded_bar(ax, x, a, width, b - a, behind_color, aspect, zorder=1.5)
    for x, a, b in zip(xs, starts, ends):
        rounded_bar(ax, x, a, width, b - a, bar_color, aspect)
    for _, ox, oa, ob, color in over_data:
        for x, a, b in zip(ox, oa, ob):
            rounded_bar(ax, x, a, width, b - a, color, aspect)

    handles: list = []
    if behind is not None and behind_label:
        handles.append(Patch(facecolor=behind_color, label=behind_label))
    if bar_label:
        handles.append(Patch(facecolor=bar_color, label=bar_label))
    for label, _, _, _, color in over_data:
        if label:
            handles.append(Patch(facecolor=color, label=label))
    for i, (label, lx, ly, color, style) in enumerate(line_data):
        color = color or theme.slot(3 + i)
        (line,) = ax.plot(lx, ly, **{"color": color, "linewidth": 2.6, "zorder": 3,
                                     "solid_joinstyle": "round", "label": label, **style})
        if label:
            handles.append(line)
        if mark_jumps is not None:
            for j in np.flatnonzero(np.abs(np.diff(ly)) > mark_jumps):
                ax.annotate(jump_label, (lx[j + 1], ly[j + 1]),
                            textcoords="offset points", xytext=(6, -12 if invert else 10),
                            fontsize=8, color=theme.text_muted, zorder=5,
                            path_effects=[pe.withStroke(linewidth=3, foreground=theme.surface)])

    clock_axis(ax, "y", hour_step)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    ax.grid(axis="y", zorder=0)
    ax.set_ylabel("time of day")
    if handles:
        legend_above(ax, handles, ncol=legend_ncol)


def legend_above(ax: plt.Axes, handles: Sequence, ncol: int | None = None) -> None:
    """The house legend: one row (or ``ncol`` columns) above the plot, so it
    never sits on data, with patch keys drawn as rounded bars."""
    ax.legend(handles=list(handles), loc="lower left", bbox_to_anchor=(0, 1.0),
              ncol=ncol or len(handles), frameon=False, borderaxespad=0.2,
              handler_map={Patch: _RoundedHandler()})


# -- dual-axis time series ------------------------------------------------------

def dual_axis_lines(
    ax: plt.Axes,
    theme: Theme,
    left: Sequence[tuple[str, Sequence, Sequence[float], str | None]],
    right: Sequence[tuple[str, Sequence, Sequence[float], str | None]] = (),
    *,
    left_label: str = "",
    right_label: str = "",
    linewidth: float = 2.2,
    markers: bool = True,
    zero_based: tuple[bool, bool] = (True, True),
) -> plt.Axes | None:
    """Lines over dates on two y axes, for series in different units.

    Each series is ``(label, dates, values, color)``; ``left`` series share the
    left axis, ``right`` series the right one. Gaps (NaN) break the line rather
    than being bridged, so a missing night doesn't look like an average one.
    One legend above the plot covers both axes. Returns the right axes (or
    ``None`` when there are no right series) for further styling.

    ``zero_based`` starts the (left, right) axis at 0 -- right for amounts
    like minutes, wrong for clock times or temperatures, where 0 means nothing
    and only squashes the line.

    Two axes invite reading crossings as meaningful; they aren't, since each
    scale is arbitrary relative to the other. Use this to show *timing*
    (did the lines move together?), and quote a correlation for strength.
    """
    def draw(target, series, offset):
        handles = []
        for i, (label, x, y, color) in enumerate(series):
            color = color or theme.slot(offset + i)
            (line,) = target.plot(
                pd.to_datetime(pd.Series(x)), np.asarray(y, float),
                color=color, linewidth=linewidth, label=label, zorder=3,
                marker="o" if markers else None, markersize=3.5,
                markeredgewidth=0,
            )
            handles.append(line)
        return handles

    handles = draw(ax, left, 0)
    ax.set_ylabel(left_label)
    ax.grid(axis="y", zorder=0)
    ax2 = None
    if right:
        ax2 = ax.twinx()
        handles += draw(ax2, right, len(left))
        ax2.set_ylabel(right_label)
        ax2.grid(False)
        ax2.spines["right"].set_visible(True)
        if zero_based[1]:
            ax2.set_ylim(bottom=0)
    if zero_based[0]:
        ax.set_ylim(bottom=0)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.0),
              ncol=len(handles), frameon=False, borderaxespad=0.2)
    return ax2
