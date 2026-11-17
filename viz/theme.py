"""Chart theme: one palette, two modes, applied through matplotlib rcParams.

Every chart in the toolkit draws its colors from here by *role* (surface, ink,
series slot) rather than by hex, so light and dark stay in sync and a future
brand swap is a one-file change.

The categorical slot order is a colorblind-safety mechanism, not decoration:
assign slots in order, never cycle past slot 8. Both modes are validated
(adjacent-pair CVD separation, chroma, lightness band, contrast vs surface).
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field

import matplotlib as mpl
import matplotlib.pyplot as plt


@dataclass(frozen=True)
class Theme:
    """A resolved set of chart colors for one mode."""

    name: str
    surface: str
    text_primary: str
    text_secondary: str
    text_muted: str
    grid: str
    series: tuple[str, ...] = field(default=())
    #: Diverging poles (low, high) with a neutral midpoint -- for values read
    #: against a reference, like an index around 1.0. Two hues that read as
    #: opposite; never a rainbow, never a hue at the midpoint.
    diverging: tuple[str, str] = ("#2a78d6", "#e34948")
    neutral: str = "#f0efec"

    def slot(self, i: int) -> str:
        """Categorical color ``i`` (0-based). Raises past slot 8 on purpose --
        a 9th series should fold into "Other", facet, or use small multiples."""
        if i >= len(self.series):
            raise IndexError(
                f"categorical slot {i} exceeds the {len(self.series)}-hue palette; "
                "fold into 'Other', facet, or use small multiples instead of cycling"
            )
        return self.series[i]


LIGHT = Theme(
    name="light",
    surface="#fcfcfb",
    text_primary="#0b0b0b",
    text_secondary="#52514e",
    text_muted="#7a7972",
    grid="#e4e3df",
    series=(
        "#2a78d6",  # blue
        "#eb6834",  # orange
        "#1baf7a",  # aqua
        "#eda100",  # yellow
        "#e87ba4",  # magenta
        "#008300",  # green
        "#4a3aa7",  # violet
        "#e34948",  # red
    ),
    diverging=("#2a78d6", "#e34948"),
    neutral="#f0efec",
)

DARK = Theme(
    name="dark",
    surface="#1a1a19",
    text_primary="#ffffff",
    text_secondary="#c3c2b7",
    text_muted="#96958c",
    grid="#383835",
    series=(
        "#3987e5",
        "#d95926",
        "#199e70",
        "#c98500",
        "#d55181",
        "#008300",
        "#9085e9",
        "#e66767",
    ),
    diverging=("#3987e5", "#e66767"),
    neutral="#383835",
)

THEMES = {"light": LIGHT, "dark": DARK}

#: Sequential ramp (blue, light -> dark) for continuous magnitude.
SEQUENTIAL_BLUE = (
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec",
    "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab",
    "#184f95", "#104281", "#0d366b",
)


def rc_params(theme: Theme) -> dict:
    """rcParams implementing the house style for one theme."""
    return {
        "figure.facecolor": theme.surface,
        "axes.facecolor": theme.surface,
        "savefig.facecolor": theme.surface,
        "savefig.bbox": "tight",
        "savefig.dpi": 200,
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans"],
        "font.size": 10,
        "text.color": theme.text_primary,
        "axes.labelcolor": theme.text_secondary,
        "axes.edgecolor": theme.grid,
        # Charts carry no titles (see charts.titles); this only covers a stray
        # set_title so it at least stays recessive.
        "axes.titlecolor": theme.text_secondary,
        "axes.titlesize": 13,
        "axes.titleweight": "semibold",
        "axes.titlelocation": "left",
        "axes.titlepad": 14,
        "axes.labelsize": 10,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        # Recessive grid: present enough to read values off, never competing
        # with the data marks.
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": theme.grid,
        "grid.linewidth": 0.8,
        "grid.alpha": 1.0,
        "xtick.color": theme.text_muted,
        "ytick.color": theme.text_muted,
        "xtick.labelcolor": theme.text_secondary,
        "ytick.labelcolor": theme.text_secondary,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "legend.labelcolor": theme.text_secondary,
        "lines.linewidth": 2.0,
        "lines.markersize": 8,
        "lines.solid_capstyle": "round",
        "axes.prop_cycle": mpl.cycler(color=list(theme.series)),
    }


@contextmanager
def styled(mode: str = "light"):
    """Draw inside the house style, then restore whatever was set before.

    >>> with styled("dark") as theme:
    ...     fig, ax = plt.subplots()
    ...     ax.plot(x, y, color=theme.slot(0))
    """
    theme = THEMES[mode]
    with plt.rc_context(rc_params(theme)):
        yield theme


def stage_color(theme: Theme, stage: str) -> str:
    """The colour of a sleep stage, the same in every chart.

    Deep is violet and REM light blue (and light a pale grey-blue, awake
    orange), so a reader who learns the colours on one chart can read the next
    one without the legend.
    """
    light_mode = theme.name == "light"
    colors = {
        "deep": theme.slot(6),
        "rem": SEQUENTIAL_BLUE[4] if light_mode else SEQUENTIAL_BLUE[2],
        "light": SEQUENTIAL_BLUE[1] if light_mode else "#5b6f8a",
        "awake": theme.slot(1),
    }
    try:
        return colors[stage.lower()]
    except KeyError:
        raise KeyError(f"no colour for stage {stage!r}; known: {list(colors)}") from None


def ramp(start: str, end: str, n: int) -> list[str]:
    """``n`` colours evenly blended from ``start`` to ``end`` (inclusive).

    For a family of related series that differ by one ordered quantity --
    rolling windows of increasing length, say -- so the order reads from the
    colour alone.
    """
    import numpy as np
    from matplotlib.colors import to_hex, to_rgb

    a, b = np.array(to_rgb(start)), np.array(to_rgb(end))
    if n == 1:
        return [to_hex(b)]
    return [to_hex(a + (b - a) * i / (n - 1)) for i in range(n)]
