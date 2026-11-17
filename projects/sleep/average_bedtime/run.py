"""Sleep stages against my recent wake-up time.

The same stage timelines as ``sleep/sunrise`` (days across, time of day up,
grey for each sleep session, the stage's stretches on top), with a red line
for my average wake-up time and a dark blue line for my average bedtime,
each over the previous two weeks. One chart per stage
in ``--stages`` (deep and REM by default).

    python projects/sleep/average_bedtime/run.py
    python projects/sleep/average_bedtime/run.py --window 14 --min-nights 7
    python projects/sleep/average_bedtime/run.py --stages deep rem light

Needs a one-time ``python -m common.health auth``. Outputs a per-night CSV and
charts to ``build/sleep/average_bedtime/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # projects/sleep
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))   # repo root

import shared  # noqa: E402

from common.health import nightly, stage_segments  # noqa: E402
from common.stats import trailing_mean  # noqa: E402
from viz import SEQUENTIAL_BLUE, charts, ramp, render  # noqa: E402
from viz import sleep as vsleep  # noqa: E402

SOURCE_NOTE = shared.HEALTH_SOURCE


def sleep_times(sleep: pd.DataFrame, windows: list[int],
                min_nights: dict[int, int]) -> pd.DataFrame:
    """Per day: that night's bedtime and wake-up, and trailing averages of each.

    Bedtime is the start of the night's main sleep and wake-up its end, both
    in local wall-clock hours after the wake-up day's midnight (so 23:30 the
    evening before is -0.5). ``avg_bed_hour_<w>`` / ``avg_wake_hour_<w>`` for
    day D average the nights in the ``w`` days before D (D itself excluded),
    once at least ``min_nights[w]`` of them have data.
    """
    nights = nightly(sleep)
    out = None
    for col, name in (("bed_local", "bed"), ("wake_local", "wake")):
        hours = pd.Series(charts.hours_since(nights[col], nights["night"]).to_numpy(),
                          index=nights["night"])
        part = pd.DataFrame({"day": hours.index, f"{name}_hour": hours.to_numpy()})
        for w in windows:
            avg = trailing_mean(hours, days=w, min_periods=min_nights[w])
            part = pd.DataFrame({"day": avg.index, f"avg_{name}_hour_{w}": avg.to_numpy()}
                                ).merge(part, on="day", how="left")
        out = part if out is None else out.merge(part, on="day", how="outer")
    return out.sort_values("day").reset_index(drop=True)


def window_minimums(windows: list[int], main: int, main_min: int) -> dict[int, int]:
    """Nights required before each window's average is drawn: ``main_min`` for
    the main window, half the window (rounded up) for the rest."""
    return {w: main_min if w == main else max(1, -(-w // 2)) for w in windows}


def clock(hours: float) -> str:
    if pd.isna(hours):
        return "–"
    h, m = divmod(round(hours * 60), 60)
    return f"{h % 24:02d}:{m:02d}"


def draw(fig, theme, stage: str, segments: pd.DataFrame, sleep: pd.DataFrame,
         times: pd.DataFrame, window: int) -> None:
    ax = fig.subplots()
    dark_blue = SEQUENTIAL_BLUE[10] if theme.name == "light" else theme.slot(0)
    vsleep.stage_timeline(
        ax, theme, stage, segments, sleep,
        lines=[(f"average bedtime, previous {window} days", times["day"],
                times[f"avg_bed_hour_{window}"], dark_blue),
               (f"average wake-up, previous {window} days", times["day"],
                times[f"avg_wake_hour_{window}"], theme.slot(7))],    # red
    )
    charts.titles(fig, ax, theme,
                  f"When I was in {vsleep.STAGE_NAMES[stage]}, against my recent "
                  f"bedtime and wake-up",
                  source=f"{SOURCE_NOTE} · lines: mean bedtime and wake-up over the "
                         f"{window} days before each day")


def window_colors(theme, kind: str, n: int) -> list[str]:
    """Shortest window first. In light mode the longest window is the darkest,
    as asked; in dark mode the ramp runs the other way so the longest window
    is still the strongest line against the background."""
    if theme.name == "light":
        light, dark = ((SEQUENTIAL_BLUE[2], SEQUENTIAL_BLUE[12]) if kind == "bed"
                       else ("#f5b5b4", "#9e1b1a"))
        return ramp(light, dark, n)
    # Dark mode: dim-but-visible for the shortest window, brightest for the longest.
    dim, bright = ((SEQUENTIAL_BLUE[8], SEQUENTIAL_BLUE[0]) if kind == "bed"
                   else ("#b04140", "#ffc4c3"))
    return ramp(dim, bright, n)


def draw_windows(fig, theme, stage: str, segments: pd.DataFrame, sleep: pd.DataFrame,
                 times: pd.DataFrame, windows: list[int]) -> None:
    """The stage timeline with bedtime and wake-up averaged over every window:
    the shortest and longest windows solid, the ones between dotted, and a
    gradient from light (shortest) to dark (longest)."""
    ax = fig.subplots()
    ws = sorted(windows)
    middle = ws[1:-1]
    lines = []
    for kind, name in (("bed", "bedtime"), ("wake", "wake-up")):
        colors = window_colors(theme, kind, len(ws))
        for w, color in zip(ws, colors):
            solid = w in (ws[0], ws[-1])
            if solid:
                label = f"{name} {w}d"
            elif middle and w == middle[len(middle) // 2]:
                label = f"{name} {middle[0]}–{middle[-1]}d"   # one key for the dotted group
            else:
                label = None
            style = ({"linewidth": 2.4} if solid else
                     {"linewidth": 1.6, "linestyle": (0, (1, 2.2))})
            lines.append((label, times["day"], times[f"avg_{kind}_hour_{w}"], color, style))
    # No clock-change labels: a one-day "average" jumps by more than the
    # threshold most nights, which would label every other day.
    vsleep.stage_timeline(ax, theme, stage, segments, sleep, lines=lines, legend_ncol=4,
                          mark_jumps=None)
    charts.titles(
        fig, ax, theme,
        f"When I was in {vsleep.STAGE_NAMES[stage]}, against bedtime and wake-up "
        f"averaged over {ws[0]}–{ws[-1]} days",
        source=(f"{SOURCE_NOTE} · lines: mean bedtime (blue) and wake-up (red) over the "
                f"{', '.join(map(str, ws))} days before each day · "
                f"{'darker' if theme.name == 'light' else 'brighter'} = longer window"),
    )


def main() -> None:
    p = shared.parser(__doc__, "average_bedtime", stages=True)
    p.add_argument("--window", type=int, default=14, help="days in the trailing average")
    p.add_argument("--min-nights", type=int, default=7,
                   help="nights needed in the main window before its average is drawn")
    p.add_argument("--windows", type=int, nargs="+", default=[1, 3, 7, 11, 14, 17, 21],
                   help="windows for the multi-window variant (other windows need "
                        "half their length in nights)")
    args = shared.parse(p)
    sleep = shared.load_sleep(args)
    windows = sorted(set(args.windows) | {args.window})
    times = sleep_times(sleep, windows,
                        window_minimums(windows, args.window, args.min_nights))

    (args.out / "wake_times.csv").unlink(missing_ok=True)        # superseded
    times.to_csv(args.out / "sleep_times.csv", index=False)

    written = []
    for stage in args.stages:
        segments = stage_segments(sleep, stage)
        written += render(
            lambda f, t: draw(f, t, stage, segments, sleep, times, args.window),
            args.out / f"{stage}-timeline", figsize=(12, 6.5),
        )
        written += render(
            lambda f, t: draw_windows(f, t, stage, segments, sleep, times, args.windows),
            args.out / f"{stage}-timeline-windows", figsize=(12, 7),
        )

    print(f"\n=== Stages vs recent bedtime and wake-up, {times['day'].min().date()} – "
          f"{times['day'].max().date()} ===")
    print(f"nights with times                {times['wake_hour'].notna().sum()}")
    for name in ("bed", "wake"):
        col = f"avg_{name}_hour_{args.window}"
        have = times.dropna(subset=[col])
        label = "bedtime" if name == "bed" else "wake-up"
        print(f"{label:<8} average, all nights   {clock(times[f'{name}_hour'].mean())}"
              f" · {args.window}-day average ranges {clock(have[col].min())} – "
              f"{clock(have[col].max())} · latest {clock(have[col].iloc[-1])}")
    print("\nwrote:", ", ".join(str(w) for w in [args.out / "sleep_times.csv", *written]))


if __name__ == "__main__":
    main()
