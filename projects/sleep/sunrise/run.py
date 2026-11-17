"""Sleep vs sunrise -- does the light outside change my deep and REM sleep?

Joins Google Health sleep stages (one row per night, dated by the morning I
woke up) to that morning's sunrise, day length and weather, then draws the same
set of charts for each stage in ``--stages`` (deep and REM by default).

    python projects/sleep/sunrise/run.py                    # San Francisco, last 180 nights
    python projects/sleep/sunrise/run.py --start 2026-08-01
    python projects/sleep/sunrise/run.py --stages deep rem light
    python projects/sleep/sunrise/run.py --lat 47.61 --lon -122.33 --place Seattle

Needs a one-time ``python -m common.health auth``. Outputs a per-night CSV and
charts to ``build/sleep/sunrise/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # projects/sleep
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))   # repo root

import shared  # noqa: E402

from common.health import StageModel, nightly, stage_segments  # noqa: E402
from common.stats import correlate, correlation_table  # noqa: E402
from common.weather import OpenMeteoDaily  # noqa: E402
from viz import charts, render, stage_color  # noqa: E402
from viz import sleep as vsleep  # noqa: E402

SOURCE_NOTE = f"{shared.HEALTH_SOURCE} · {shared.WEATHER_SOURCE}"

STAGE_NAMES = vsleep.STAGE_NAMES

#: What each stage is compared against. Column -> axis label.
DRIVERS = {
    "sunrise_hour": "sunrise (local hour)",
    "daylight_h": "day length (hours)",
    "wake_after_sunrise_min": "woke up this long after sunrise (min)",
    "bed_hour": "fell asleep (hours after midnight)",
    "temp_min_c": "overnight low (°C)",
}


def away_from(nights: pd.DataFrame, tz: str) -> pd.Series:
    """True for nights the watch spent on a different UTC offset from ``tz``
    (the sunrise location's zone) -- i.e. you were travelling, so that
    location's sunrise isn't the one you slept under. Trips within the same
    time zone can't be detected this way."""
    home = nights["wake_time"].dt.tz_convert(tz)
    home_h = home.map(lambda t: t.utcoffset().total_seconds() / 3600)
    return nights["utc_offset_h"].ne(home_h)


def build_nights(sleep: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """One row per night at the sunrise location, with that morning's weather.
    Nights spent in another time zone are dropped (see :func:`away_from`);
    how many is in ``attrs["away"]``."""
    nights = nightly(sleep)
    away = away_from(nights, weather["timezone"].iloc[0]) if len(weather) else None
    if away is not None:
        nights = nights.loc[~away]
    joined = nights.merge(weather, left_on="night", right_on="date", how="inner")
    joined.attrs["away"] = int(away.sum()) if away is not None else 0
    joined["sunrise_hour"] = charts.hours_since(joined["sunrise"], joined["night"])
    joined["bed_hour"] = charts.hours_since(joined["bed_local"], joined["night"])
    joined["wake_after_sunrise_min"] = (
        (joined["wake_local"] - joined["sunrise"]) / pd.Timedelta(minutes=1)
    )
    return joined


# -- charts, each drawn once per stage ------------------------------------------

def draw_timeline(fig, theme, stage: str, segments: pd.DataFrame, sessions: pd.DataFrame,
                  sun: pd.DataFrame, place: str, missed: pd.DataFrame | None = None) -> None:
    """The stage timeline with sunrise in yellow (and, with ``missed``, pink
    where the average-night model expected the stage but it didn't happen)."""
    ax = fig.subplots()
    vsleep.stage_timeline(
        ax, theme, stage, segments, sessions, missed=missed,
        lines=[(f"sunrise, {place}", sun["date"],
                charts.hours_since(sun["sunrise"], sun["date"]), theme.slot(3))],  # yellow
    )
    charts.titles(fig, ax, theme, f"When I was in {STAGE_NAMES[stage]}, against sunrise",
                  source=SOURCE_NOTE)


def draw_model_curve(fig, theme, stage: str, model: StageModel, scores: dict) -> None:
    """The average night: chance of being in the stage by hours since falling
    asleep, with the stretches the model predicts (chance >= threshold) shaded."""
    ax = fig.subplots()
    name = STAGE_NAMES.get(stage, stage)
    color = stage_color(theme, stage)
    nights = model.nights_at
    last = int(nights[nights >= model.min_nights].index.max())
    hours = model.curve.index[:last] / 60
    p = model.curve.to_numpy()[:last]
    for i, (_, w) in enumerate(model.windows().iterrows()):
        ax.axvspan(w["start_min"] / 60, w["end_min"] / 60, color=color, alpha=0.18,
                   linewidth=0, zorder=1, label=f"predicted {name}" if i == 0 else None)
    ax.plot(hours, p, color=color, linewidth=2.4, zorder=3,
            label=f"share of nights in {name}")
    ax.axhline(model.threshold, color=theme.text_muted, linewidth=1.2,
               linestyle=(0, (4, 3)), zorder=2)
    ax.annotate(f"predict {name} above {model.threshold:.0%}",
                (hours[-1], model.threshold), textcoords="offset points", xytext=(0, 5),
                ha="right", fontsize=8, color=theme.text_muted)
    charts.percent_axis(ax, "y")
    ax.set_ylim(0, 1)
    ax.set_xlim(0, hours[-1])
    ax.set_xlabel("hours since falling asleep")
    ax.set_ylabel(f"chance of being in {name}")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False,
              borderaxespad=0.2)
    charts.titles(
        fig, ax, theme, f"My average night of {name}",
        source=(f"Source: Google Health API · {scores['nights']} nights · cross-validated: "
                f"{scores['precision']:.0%} of predicted {stage.upper() if stage == 'rem' else stage} "
                f"minutes were right, {scores['recall']:.0%} of actual ones were predicted"),
    )


def draw_vs_sunrise(fig, theme, stage: str, nights: pd.DataFrame) -> None:
    """One point per night: minutes in the stage against that morning's sunrise."""
    ax = fig.subplots()
    name = STAGE_NAMES.get(stage, stage)
    d = nights.dropna(subset=[f"{stage}_min", "sunrise_hour"])
    c = correlate(d, "sunrise_hour", f"{stage}_min")
    charts.scatter(ax, d["sunrise_hour"].tolist(), d[f"{stage}_min"].tolist(), theme,
                   trend=True, color=stage_color(theme, stage))
    ax.set_xlabel("sunrise on the morning I woke (hours after midnight)")
    ax.set_ylabel(f"{name} (minutes)")
    charts.titles(fig, ax, theme, f"{name} against sunrise time",
                  source=f"{SOURCE_NOTE} · Pearson {c.pearson:+.2f}, "
                         f"Spearman {c.spearman:+.2f}, n={c.n}")


def draw_over_time(fig, theme, stage: str, nights: pd.DataFrame) -> None:
    """The stage's 7-night mean (with each night as a faint point) and sunrise
    through the season. Both drift with the calendar, so a shared trend here
    isn't evidence of a link on its own."""
    ax = fig.subplots()
    name = STAGE_NAMES.get(stage, stage)
    color = stage_color(theme, stage)
    d = nights.dropna(subset=[f"{stage}_min"])
    rolling = d.set_index("night")[f"{stage}_min"].rolling("7D").mean()
    ax.scatter(d["night"], d[f"{stage}_min"], s=14, color=color, alpha=0.35, zorder=2)
    charts.dual_axis_lines(
        ax, theme,
        left=[(f"{name}, 7-night mean", rolling.index, rolling.values, color)],
        right=[("sunrise", nights["night"], nights["sunrise_hour"], theme.slot(3))],
        left_label=f"{name} (minutes)",
        right_label="sunrise (hours after midnight)",
        markers=False,
        zero_based=(True, False),        # a clock time has no meaningful zero
    )
    charts.titles(fig, ax, theme, f"{name} and sunrise through the season",
                  source=SOURCE_NOTE)


def main() -> None:
    args = shared.parse(shared.parser(__doc__, "sunrise", stages=True, location=True))
    where = shared.where(args)
    sleep = shared.load_sleep(args)
    weather = OpenMeteoDaily().load_range(where, args.start, args.end)
    nights = build_nights(sleep, weather)
    if nights.empty:
        sys.exit(f"no nights with sleep data between {args.start} and {args.end}")

    nights.to_csv(args.out / "nights.csv", index=False)
    # The timelines show every day in range, including nights with no sleep data.
    sun = weather[(weather["date"] >= nights["night"].min())
                  & (weather["date"] <= nights["night"].max())]

    first, last = nights["night"].min().date(), nights["night"].max().date()
    print(f"\n=== Sleep vs sunrise, {where.label}, {first} – {last} ===")
    print(f"nights           {len(nights)} ({nights['deep_min'].notna().sum()} with sleep stages)")
    if nights.attrs.get("away"):
        print(f"                 {nights.attrs['away']} more left out: spent in another time zone, "
              f"so {where.label}'s sunrise doesn't apply")
    print(f"sunrise range    {nights['sunrise'].dt.strftime('%H:%M').min()} – "
          f"{nights['sunrise'].dt.strftime('%H:%M').max()}")

    written = []
    for stage in args.stages:
        name = STAGE_NAMES[stage]
        out = args.out / stage
        segments = stage_segments(sleep, stage)
        # Average-night model: fitted on every night for the charts, scored with
        # cross-validation so the reported accuracy isn't flattered.
        model = StageModel(stage).fit(sleep)
        scores = model.evaluate(sleep)
        missed = model.missed(sleep)
        missed = missed[missed["minutes"] >= 2]          # drop 1-minute edge slivers

        def timeline(missed_layer):
            return lambda fig, theme: draw_timeline(fig, theme, stage, segments, sleep,
                                                    sun, where.label, missed_layer)

        written += render(timeline(None), out / f"{stage}-timeline", figsize=(12, 6.5))
        written += render(timeline(missed), out / f"{stage}-predicted", figsize=(12, 6.5))
        written += render(lambda f, t: draw_model_curve(f, t, stage, model, scores),
                          out / f"{stage}-model", figsize=(9, 5.5))
        written += render(lambda f, t: draw_vs_sunrise(f, t, stage, nights),
                          out / f"{stage}-vs-sunrise", figsize=(9, 6.5))
        written += render(lambda f, t: draw_over_time(f, t, stage, nights),
                          out / f"{stage}-over-time", figsize=(10, 6))

        print(f"\n--- {name} ---")
        print(f"{nights[f'{stage}_min'].mean():5.1f} min/night "
              f"({nights[f'{stage}_share'].mean():.1%} of sleep)")
        for y in (f"{stage}_min", f"{stage}_share"):
            print(f"\n{y} against:")
            print(correlation_table(nights, DRIVERS, y).to_string(
                index=False, float_format=lambda v: f"{v:+.3f}"))
        print(f"\naverage-night model ({name} on >= {model.threshold:.0%} of nights):")
        for _, w in model.windows().iterrows():
            print(f"  {w['start_min'] / 60:4.2f}h – {w['end_min'] / 60:4.2f}h after falling "
                  f"asleep (peak {w['peak_p']:.0%} of nights)")
        print(f"  cross-validated: accuracy {scores['accuracy']:.1%} "
              f"(never-{stage} baseline {scores['baseline_accuracy']:.1%}), "
              f"precision {scores['precision']:.1%}, recall {scores['recall']:.1%}")
        per_night = missed.groupby("night")["minutes"].sum()
        print(f"  predicted-but-missed {name}: {per_night.sum() / len(nights):.0f} "
              f"min/night on average")

    print(f"\nwrote {len(written) + 1} files under {args.out}")


if __name__ == "__main__":
    main()
