"""Week 2 -- does unabsorbed delay cost you, or cost the airline?

Joins the two datasets already in the toolkit: per airport, how much departure
delay actually survives to the destination (:mod:`common.flights.absorption`),
against how expensive that airport is to fly out of
(:mod:`common.flights.fares`).

    python projects/flights/week2_delay_vs_price/run.py --months 2025-01 2025-02 2025-03 \
        --quarters 2025Q1

Periods should line up: the fare survey is quarterly, the on-time feed monthly,
so a quarter of fares wants that quarter's three months of flights.

Outputs CSV tables and charts to ``build/flights/week2_delay_vs_price/``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from common import project_out  # noqa: E402
from common.stats import correlate  # noqa: E402
from common.flights import (  # noqa: E402
    FareData,
    FlightData,
    add_absorption,
    airport_absorption,
    airport_fare_rates,
    prepare_fares,
)
from viz import charts, render  # noqa: E402

SOURCE_NOTE = (
    "Sources: US DOT / BTS on-time performance and DB1B ticket survey (10% sample)"
)


def make_charts(joined: pd.DataFrame, out_dir: Path, period: str):
    """The scatter that was asked for, plus the one that shows why it misleads."""

    def _annotated(d: pd.DataFrame, y: str) -> list[str]:
        picks = set(d.nlargest(4, "mean_unabsorbed_min")["airport"])
        picks |= set(d.nsmallest(4, "mean_unabsorbed_min")["airport"])
        picks |= set(d.nlargest(2, y)["airport"]) | set(d.nsmallest(2, y)["airport"])
        return sorted(picks)

    def draw_vs_index(fig, theme):
        ax = fig.subplots()
        r, rho, p, _ = correlate(joined, "mean_unabsorbed_min", "price_index")
        charts.scatter(
            ax,
            joined["mean_unabsorbed_min"].tolist(),
            joined["price_index"].tolist(),
            theme,
            labels=joined["airport"].tolist(),
            annotate=_annotated(joined, "price_index"),
            sizes=joined["passengers"].tolist(),
            trend=True,
        )
        ax.axhline(1.0, color=theme.text_muted, linewidth=1.2, linestyle=(0, (4, 3)))
        ax.set_xlabel("mean unabsorbed delay per departure (minutes)")
        ax.set_ylabel("price index (1.00 = national rate for the trip length)")
        charts.titles(
            fig, ax, theme,
            "Expensive airports pass through slightly more delay",
            f"Point size is passengers · Pearson {r:+.2f}, Spearman {rho:+.2f} "
            f"(p={p:.3f}, n={len(joined)}) -- a weak relationship · {period}",
            SOURCE_NOTE,
        )

    def draw_vs_dpm(fig, theme):
        ax = fig.subplots()
        r, rho, p, _ = correlate(joined, "mean_unabsorbed_min", "dollars_per_mile")
        charts.scatter(
            ax,
            joined["mean_unabsorbed_min"].tolist(),
            joined["dollars_per_mile"].tolist(),
            theme,
            labels=joined["airport"].tolist(),
            annotate=_annotated(joined, "dollars_per_mile"),
            sizes=joined["passengers"].tolist(),
            trend=True,
            color=theme.slot(1),
        )
        ax.set_xlabel("mean unabsorbed delay per departure (minutes)")
        ax.set_ylabel("raw dollars per mile")
        charts.titles(
            fig, ax, theme,
            "Against raw dollars per mile the relationship flips sign",
            f"Pearson {r:+.2f}, Spearman {rho:+.2f} -- the worst absorbers are "
            f"long-haul leisure airports, which look cheap per mile · {period}",
            SOURCE_NOTE,
        )

    def draw_ranking(fig, theme):
        ax = fig.subplots()
        top = joined.nlargest(15, "mean_unabsorbed_min")
        charts.hbar_ranking(
            ax,
            top["airport"].tolist(),
            top["mean_unabsorbed_min"].tolist(),
            theme,
            value_fmt=lambda v: f"{v:.1f} min",
            percent=False,
            reference=joined["mean_unabsorbed_min"].median(),
            reference_label="median airport",
        )
        ax.set_xlabel("mean unabsorbed delay per departure (minutes)")
        charts.titles(
            fig, ax, theme,
            "Where a late departure stays late",
            "Departure delay still present on arrival, averaged over every "
            f"departure · {period}",
            SOURCE_NOTE,
        )

    written = []
    written += render(draw_vs_index, out_dir / "unabsorbed-vs-price-index", figsize=(9, 6.5))
    written += render(draw_vs_dpm, out_dir / "unabsorbed-vs-dollars-per-mile", figsize=(9, 6.5))
    written += render(draw_ranking, out_dir / "unabsorbed-ranking", figsize=(9, 6.5))
    return written


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--months", nargs="+", default=["2025-01", "2025-02", "2025-03"])
    p.add_argument("--quarters", nargs="+", default=["2025Q1"])
    p.add_argument("--min-flights", type=int, default=2000)
    p.add_argument("--min-passengers", type=float, default=20000.0)
    p.add_argument("--out", type=Path, default=project_out("flights/week2_delay_vs_price"))
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    flights = add_absorption(FlightData().load(args.months))
    absorption = airport_absorption(flights, min_flights=args.min_flights)
    logging.info("absorption for %d airports over %d flights",
                 len(absorption), len(flights))

    fares = prepare_fares(FareData().load(args.quarters))
    prices = airport_fare_rates(fares, min_passengers=args.min_passengers)
    logging.info("fares for %d airports", len(prices))

    joined = absorption.merge(prices, on="airport", how="inner")
    logging.info("joined on %d airports present in both", len(joined))

    args.out.mkdir(parents=True, exist_ok=True)
    joined.to_csv(args.out / "delay_vs_price.csv", index=False)

    period = f"{args.quarters[0]}"
    written = make_charts(joined, args.out, period)

    net_absorbed = 1 - flights["unabsorbed_min"].sum() / flights["dep_delay_pos"].sum()
    late = flights[flights["dep_delay_pos"] >= 15]
    print(f"\n=== Unabsorbed delay vs price, {len(joined)} airports, {period} ===")
    print(f"mean departure delay   {flights['dep_delay_pos'].mean():5.1f} min per flight")
    print(f"mean unabsorbed        {flights['unabsorbed_min'].mean():5.1f} min per flight")
    print(f"network absorbs        {net_absorbed:5.1%} of all departure delay")
    print(f"of flights leaving 15+ min late, {(late['arr_delay'] < 15).mean():.1%} "
          f"still arrive on time")
    print()
    for y in ("price_index", "dollars_per_mile", "mean_fare_usd"):
        r, rho, pv, _ = correlate(joined, "mean_unabsorbed_min", y)
        print(f"unabsorbed vs {y:<18} pearson {r:+.3f}  spearman {rho:+.3f}  p={pv:.4f}")

    cols = ["airport", "flights", "mean_dep_delay_min", "mean_unabsorbed_min",
            "absorbed_share", "price_index", "dollars_per_mile"]
    print("\nworst absorbers:")
    print(joined.nlargest(10, "mean_unabsorbed_min")[cols]
          .to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\nbest absorbers:")
    print(joined.nsmallest(10, "mean_unabsorbed_min")[cols]
          .to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\nwrote:", ", ".join(str(w) for w in [args.out / "delay_vs_price.csv", *written]))


if __name__ == "__main__":
    main()
