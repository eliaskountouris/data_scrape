"""Week 1 -- how expensive is each airport to fly out of?

Uses the DB1B ticket survey to compute, per airport, the passenger-weighted
dollars per mile, and then the distance-controlled price index that says how
much of that is the airport's pricing rather than its route mix.

    python projects/flights/week1_prices/run.py --quarters 2025Q1

Outputs CSV tables and charts to ``build/flights/week1_prices/``.

Note the source is US **domestic** only, so non-US airports (YYZ, LHR, ...) have
no rows -- the run warns about any requested airport it cannot see.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from common import project_out  # noqa: E402
from common.flights import (  # noqa: E402
    FareData,
    airport_fare_rates,
    national_baseline,
    prepare_fares,
)
from viz import charts, render  # noqa: E402

SOURCE_NOTE = "Source: US DOT / BTS DB1B Origin & Destination Survey (10% ticket sample)"


def make_charts(rates: pd.DataFrame, baseline: pd.DataFrame, out_dir: Path, period: str):
    """Who is expensive, why the raw shorthand misleads, and by how much."""
    extremes = pd.concat([rates.head(10), rates.tail(10)])
    corr = rates["dollars_per_mile"].corr(rates["price_index"])
    median_shift = (
        rates["dollars_per_mile"].rank(ascending=False)
        - rates["price_index"].rank(ascending=False)
    ).abs().median()

    def draw_index(fig, theme):
        ax = fig.subplots()
        charts.diverging_hbar(
            ax,
            extremes["airport"].tolist(),
            extremes["price_index"].tolist(),
            theme,
            baseline=1.0,
            high_label="more expensive than average",
            low_label="cheaper than average",
        )
        ax.set_xlabel("price index (1.00 = national rate for the same trip length)")
        charts.titles(
            fig, ax, theme,
            "The most and least expensive US airports to fly from",
            f"Fares compared with what comparable-distance trips cost nationally · {period}",
            SOURCE_NOTE,
            subtitle_y=1.075,
            title_pad=46,
        )

    def draw_distance_curve(fig, theme):
        ax = fig.subplots()
        # Plot at each band's median trip, not its midpoint: the top band is
        # open-ended and its midpoint would sit far beyond any real route.
        x = baseline["median_distance_mi"].tolist()
        charts.line_curve(ax, x, baseline["dollars_per_mile"].tolist(), theme)
        ax.set_xlabel("trip distance (miles)")
        ax.set_ylabel("dollars per mile")
        ax.set_ylim(0, max(baseline["dollars_per_mile"]) * 1.18)
        charts.titles(
            fig, ax, theme,
            "Dollars per mile is mostly a measure of distance",
            "A short hop costs several times more per mile than a transcon "
            f"at the same price level · {period}",
            SOURCE_NOTE,
        )

    def draw_raw_vs_adjusted(fig, theme):
        ax = fig.subplots()
        # The two measures correlate, so the story is not "they disagree" -- it
        # is how far the ranking moves. Name the biggest movers only.
        d = rates.assign(
            shift=(
                rates["dollars_per_mile"].rank(ascending=False)
                - rates["price_index"].rank(ascending=False)
            ).abs()
        )
        movers = d.nlargest(6, "shift")["airport"].tolist()
        charts.scatter(
            ax,
            rates["dollars_per_mile"].tolist(),
            rates["price_index"].tolist(),
            theme,
            labels=rates["airport"].tolist(),
            annotate=movers,
        )
        ax.axhline(1.0, color=theme.text_muted, linewidth=1.2, linestyle=(0, (4, 3)))
        ax.set_xlabel("raw dollars per mile")
        ax.set_ylabel("distance-controlled price index")
        charts.titles(
            fig, ax, theme,
            f"Controlling for distance moves the typical airport {median_shift:.0f} places",
            f"The two measures correlate ({corr:.2f}), but not for everyone · "
            f"labelled points are the biggest movers · {period}",
            SOURCE_NOTE,
        )

    written = []
    written += render(draw_index, out_dir / "price-index-ranking", figsize=(9, 7.5))
    written += render(draw_distance_curve, out_dir / "distance-curve", figsize=(9, 5.5))
    written += render(draw_raw_vs_adjusted, out_dir / "raw-vs-adjusted", figsize=(9, 6))
    return written


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--quarters", nargs="+", default=["2025Q1"], help="YYYYQN keys")
    p.add_argument(
        "--airports", nargs="+", default=None,
        help="IATA codes to analyse; default is every airport above the size floor",
    )
    p.add_argument(
        "--direction", default="origin", choices=("origin", "dest", "either"),
        help="'origin' = expensive to fly OUT of (default)",
    )
    p.add_argument("--min-passengers", type=float, default=20000.0)
    p.add_argument("--include-bulk", action="store_true")
    p.add_argument("--out", type=Path, default=project_out("flights/week1_prices"))
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    fare_data = FareData()
    raw = fare_data.load(args.quarters, airports=args.airports)
    logging.info("loaded %d priced markets over %s", len(raw), ", ".join(args.quarters))
    if args.airports is not None:
        logging.info("provider routing:\n%s", fare_data.coverage(args.airports, raw))

    fares = prepare_fares(raw, include_bulk=args.include_bulk)
    baseline = national_baseline(fares)
    rates = airport_fare_rates(
        fares,
        airports=args.airports,
        direction=args.direction,
        min_passengers=args.min_passengers,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    rates.to_csv(args.out / "airport_fare_rates.csv", index=False)
    baseline.to_csv(args.out / "national_baseline.csv", index=False)

    period = " to ".join(dict.fromkeys([args.quarters[0], args.quarters[-1]]))
    written = make_charts(rates, baseline, args.out, period)

    print(f"\n=== Fares at {len(rates)} airports, {period} ===")
    print(f"sampled passengers: {fares['passengers'].sum():,.0f} (DB1B is a 10% sample)")
    print("\nnational dollars per mile by trip distance:")
    print(baseline.to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    cols = ["airport", "passengers", "mean_fare_usd", "dollars_per_mile",
            "median_distance_mi", "price_index"]
    print("\nmost expensive:")
    print(rates.head(10)[cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\ncheapest:")
    print(rates.tail(10)[cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\nwrote:", ", ".join(str(w) for w in [
        args.out / "airport_fare_rates.csv", args.out / "national_baseline.csv", *written
    ]))


if __name__ == "__main__":
    main()
