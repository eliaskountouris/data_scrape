"""Week 0 -- do on-time arrivals still depart late?

Chains each aircraft's inbound arrival to its next departure using BTS on-time
data, then reports, per airport: of the flights that land on time there, how
often the aircraft departs late, and how often it is still late on arrival at
the next destination.

    python projects/flights/week0_delays/run.py --months 2025-01 2025-02

Outputs CSV tables and charts to ``build/flights/week0_delays/``.

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
    FlightData,
    airport_delay_rates,
    build_turnarounds,
    ground_time_curve,
    label_turnarounds,
)
from viz import charts, render  # noqa: E402

SOURCE_NOTE = "Source: US DOT / BTS Marketing Carrier On-Time Performance"

# A default set of large, structurally different US airports: legacy hubs, a
# low-cost hub, and a couple of notoriously weather-exposed ones.
DEFAULT_AIRPORTS = [
    "ATL", "DFW", "DEN", "ORD", "LAX", "CLT", "LAS", "PHX",
    "MCO", "SEA", "EWR", "SFO", "JFK", "BOS", "LGA", "MIA", "MDW", "BWI", 'YYZ'
]


def make_charts(rates: pd.DataFrame, curve: pd.DataFrame, out_dir: Path, period: str):
    """Three views: who is worst, how much is inherited, and why."""
    top = rates.head(15)

    def draw_ranking(fig, theme):
        ax = fig.subplots()
        charts.hbar_ranking(
            ax,
            top["airport"].tolist(),
            top["ot_dep_late_rate"].tolist(),
            theme,
            reference=rates["ot_dep_late_rate"].median(),
            reference_label="median airport",
        )
        ax.set_xlabel("share of turnarounds departing 15+ min late")
        charts.titles(
            fig, ax, theme,
            "On-time arrival, late departure",
            f"Of aircraft that land on time, the share that still leave late · {period}",
            SOURCE_NOTE,
        )

    def draw_dumbbell(fig, theme):
        ax = fig.subplots()
        d = rates.sort_values("late_dep_late_rate", ascending=False).head(15)
        charts.dumbbell(
            ax,
            d["airport"].tolist(),
            d["ot_dep_late_rate"].tolist(),
            d["late_dep_late_rate"].tolist(),
            theme,
            left_label="inbound arrived on time",
            right_label="inbound arrived late",
        )
        ax.set_xlabel("share of turnarounds departing 15+ min late")
        charts.titles(
            fig, ax, theme,
            "Most departure delay is inherited, not generated",
            f"Late-departure rate by how the aircraft arrived · {period}",
            SOURCE_NOTE,
            subtitle_y=1.075,  # the legend takes the row beneath the deck
            title_pad=46,
        )

    def draw_curve(fig, theme):
        ax = fig.subplots()
        x = [iv.left + (iv.right - iv.left) / 2 for iv in curve["ground_bucket"]]
        charts.line_curve(ax, x, curve["dep_late_rate"].tolist(), theme)
        ax.set_xlabel("scheduled ground time (minutes)")
        ax.set_ylabel("share departing 15+ min late")
        ax.set_ylim(0, max(curve["dep_late_rate"]) * 1.18)
        charts.percent_axis(ax, "y")
        charts.titles(
            fig, ax, theme,
            "Below 30 minutes on the ground, the schedule is the delay",
            f"On-time arrivals only, so nothing is inherited from the inbound leg · {period}",
            SOURCE_NOTE,
        )

    written = []
    written += render(draw_ranking, out_dir / "airport-ranking", figsize=(9, 6.5))
    written += render(draw_dumbbell, out_dir / "inherited-vs-generated", figsize=(9, 6.5))
    written += render(draw_curve, out_dir / "ground-time-curve", figsize=(9, 5.5))
    return written


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--months", nargs="+", default=["2025-01"], help="YYYY-MM keys")
    p.add_argument(
        "--airports", nargs="+", default=DEFAULT_AIRPORTS,
        help="IATA codes to analyse; pass 'all' for every airport",
    )
    p.add_argument("--late-min", type=float, default=15.0)
    p.add_argument("--min-turnarounds", type=int, default=300)
    p.add_argument("--out", type=Path, default=project_out("flights/week0_delays"))
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    airports = None if args.airports == ["all"] else args.airports

    flight_data = FlightData()
    flights = flight_data.load(args.months, airports=airports)
    logging.info("loaded %d flights over %s", len(flights), ", ".join(args.months))
    if airports is not None:
        logging.info(
            "provider routing:\n%s", flight_data.coverage(airports, flights)
        )

    turns = label_turnarounds(
        build_turnarounds(flights, airports=airports), late_min=args.late_min
    )
    logging.info("built %d turnarounds", len(turns))

    rates = airport_delay_rates(turns, min_turnarounds=args.min_turnarounds)
    curve = ground_time_curve(turns)

    args.out.mkdir(parents=True, exist_ok=True)
    rates.to_csv(args.out / "airport_delay_rates.csv", index=False)
    curve.to_csv(args.out / "ground_time_curve.csv", index=False)
    turns.to_parquet(args.out / "turnarounds.parquet", index=False)

    period = " to ".join(dict.fromkeys([args.months[0], args.months[-1]]))
    written = make_charts(rates, curve, args.out, period)

    on_time = turns[turns["in_on_time"]]
    late = turns[turns["in_late"]]
    print(f"\n=== Turnarounds at {len(rates)} airports, {period} ===")
    print(f"aircraft landed ON TIME  -> departs late {on_time['out_dep_late'].mean():6.1%}"
          f" | still late on arrival {on_time['out_arr_late'].mean():6.1%}")
    print(f"aircraft landed LATE     -> departs late {late['out_dep_late'].mean():6.1%}"
          f" | still late on arrival {late['out_arr_late'].mean():6.1%}")
    print()
    cols = ["airport", "turnarounds", "median_ground_min",
            "ot_dep_late_rate", "ot_arr_late_rate", "late_dep_late_rate", "lift"]
    print(rates[cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\nwrote:", ", ".join(str(w) for w in [args.out / "airport_delay_rates.csv", *written]))


if __name__ == "__main__":
    main()
