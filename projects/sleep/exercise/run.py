"""Sleep and exercise -- does a workout change that night's deep and REM sleep?

One chart: days across, deep sleep and REM minutes on the left axis, hours of
exercise on the right. Each night is plotted on the day it *started*, so a
day's exercise lines up with the sleep that followed it.

    python projects/sleep/exercise/run.py
    python projects/sleep/exercise/run.py --start 2026-08-01 --end 2026-11-16

Needs a one-time ``python -m common.health auth``. Outputs a per-day CSV and
the chart to ``build/sleep/exercise/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # projects/sleep
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))   # repo root

import shared  # noqa: E402

from common.health import daily_exercise, nightly  # noqa: E402
from common.stats import correlate  # noqa: E402
from viz import SEQUENTIAL_BLUE, charts, render, stage_color  # noqa: E402

SOURCE_NOTE = (f"{shared.HEALTH_SOURCE} · sleep plotted on the day it started · "
               "exercise is recorded workouts, duplicate recordings merged")


def build_days(sleep: pd.DataFrame, exercise: pd.DataFrame, start, end) -> pd.DataFrame:
    """One row per day: that day's exercise and the night that followed it."""
    days = daily_exercise(exercise, start, end)
    nights = nightly(sleep)
    # nightly() dates a night by the morning you woke up; the night after day D
    # is the one that ended on D + 1.
    nights["day"] = nights["night"] - pd.Timedelta(days=1)
    out = days.merge(nights[["day", "deep_min", "rem_min", "asleep_min"]],
                     on="day", how="left")
    out["exercise_h"] = out["exercise_min"] / 60
    return out


def draw(fig, theme, days: pd.DataFrame) -> None:
    ax = fig.subplots()
    dark_blue = SEQUENTIAL_BLUE[9] if theme.name == "light" else theme.slot(0)
    charts.dual_axis_lines(
        ax, theme,
        left=[("deep sleep", days["day"], days["deep_min"], stage_color(theme, "deep")),
              ("REM sleep", days["day"], days["rem_min"], stage_color(theme, "rem"))],
        right=[("exercise", days["day"], days["exercise_h"], dark_blue)],
        left_label="sleep that night (minutes)",
        right_label="exercise that day (hours)",
    )
    charts.titles(fig, ax, theme, "Deep and REM sleep against exercise",
                  source=SOURCE_NOTE)


def main() -> None:
    args = shared.parse(shared.parser(__doc__, "exercise"))
    exercise = shared.load("exercise", args.start, args.end)
    # one extra day of sleep: the night after the last day ends the next morning
    sleep = shared.load_sleep(args, extra_days=1)
    days = build_days(sleep, exercise, args.start, args.end)
    # trim to the stretch where sleep was actually recorded
    have = days["deep_min"].notna()
    days = days.loc[have.idxmax(): have[::-1].idxmax()].reset_index(drop=True)

    days.to_csv(args.out / "days.csv", index=False)
    written = render(lambda fig, theme: draw(fig, theme, days),
                     args.out / "sleep-vs-exercise", figsize=(12, 6))

    first, last = days["day"].min().date(), days["day"].max().date()
    active = days["exercise_min"] > 0
    print(f"\n=== Sleep vs exercise, {first} – {last} ===")
    print(f"days                  {len(days)} ({active.sum()} with a workout)")
    print(f"exercise              {days['exercise_min'].mean():5.1f} min/day on average")
    for stage in ("deep_min", "rem_min"):
        on, off = days.loc[active, stage].mean(), days.loc[~active, stage].mean()
        print(f"{stage[:-4]:<5} sleep after a workout day {on:5.1f} min · "
              f"after a rest day {off:5.1f} min")
        print(f"      exercise minutes vs {stage}: {correlate(days, 'exercise_min', stage)}")
    print("\nwrote:", ", ".join(str(w) for w in [args.out / "days.csv", *written]))


if __name__ == "__main__":
    main()
