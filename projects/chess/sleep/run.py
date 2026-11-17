"""Chess and sleep -- do I win more after a longer night, or early in the day?

Two scatter plots, both with win rate up the side and a draw counted as half a
win:

* ``win-rate-vs-sleep``: hours asleep the night before across. One point per
  night, sized by how many games followed it.
* ``win-rate-vs-hours-awake``: hours since waking when the game started
  across. One point per ``--awake-bin`` hours (default 2), sized by games.

    python projects/chess/sleep/run.py
    python projects/chess/sleep/run.py --start 2026-08-01 --speeds blitz bullet

"The night before" a game is the last main sleep that ended before it started
(and ended no more than ``--max-awake`` hours earlier), so a 1 a.m. game counts
against the night before it, 17 hours after waking, rather than the night
after. Matching is done in UTC, so travel and clock changes can't shift it.

Needs a one-time ``python -m common.health auth`` and a Lichess token (see the
root README). Writes each chart and its CSV to ``build/chess/sleep/``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.ticker import MultipleLocator

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))   # repo root

from common import project_out  # noqa: E402
from common.health import GoogleHealth, nightly  # noqa: E402
from common.lichess import Lichess  # noqa: E402
from common.stats import correlate  # noqa: E402
from viz import charts, render  # noqa: E402

SOURCE_NOTE = "Source: Lichess API, Google Health API (sleep)"

POINTS = {"win": 1.0, "draw": 0.5, "loss": 0.0}

#: Buckets for the printed sleep summary.
SLEEP_BUCKETS = [0, 6, 7, 8, 24]


def games_after_sleep(games: pd.DataFrame, nights: pd.DataFrame,
                      max_awake_h: float = 24) -> pd.DataFrame:
    """Each game joined to the sleep that preceded it.

    ``games`` from :meth:`Lichess.load_games`, ``nights`` from
    :func:`common.health.nightly`. Matching is done in UTC (Lichess's
    ``played_at`` against the sleep's ``bed_time``/``wake_time``), so it stays
    right across clock changes and travel, when the watch's local time zone
    moves. Adds the night's columns, ``asleep_h`` (that night's sleep),
    ``awake_h`` (hours from waking to the game's start) and ``points``
    (1, 0.5 or 0).

    Dropped: games with no sleep ending in the ``max_awake_h`` hours before
    them (no data, or an all-nighter), and games played during a wake-up in
    the middle of a recorded sleep (a quick game during a short wake-up before
    dozing off again). Those have no single "night before" or "time since
    waking"; their count is in ``attrs["during_sleep"]``.
    """
    g = games.sort_values("played_at")
    n = nights[["night", "bed_time", "wake_time", "wake_local", "asleep_min"]].dropna()
    # the most recent bedtime before each game: if that sleep hadn't ended yet,
    # the game was played during it
    latest_bed = pd.merge_asof(g[["played_at"]], n.sort_values("bed_time"),
                               left_on="played_at", right_on="bed_time",
                               direction="backward")
    during = (latest_bed["played_at"] < latest_bed["wake_time"]).to_numpy()
    g = g.loc[~during]
    out = pd.merge_asof(g, n.drop(columns="bed_time").sort_values("wake_time"),
                        left_on="played_at", right_on="wake_time",
                        direction="backward", tolerance=pd.Timedelta(hours=max_awake_h))
    out = out.dropna(subset=["night"]).reset_index(drop=True)
    out["asleep_h"] = out["asleep_min"] / 60
    out["awake_h"] = (out["played_at"] - out["wake_time"]).dt.total_seconds() / 3600
    out["points"] = out["result"].map(POINTS)
    out.attrs["during_sleep"] = int(during.sum())
    return out


def score(results: pd.Series) -> float:
    """Win rate with a draw counted as half a win."""
    return results.map(POINTS).mean()


def _tally(groups) -> pd.DataFrame:
    return groups.agg(
        games=("result", "size"),
        wins=("result", lambda r: (r == "win").sum()),
        draws=("result", lambda r: (r == "draw").sum()),
        losses=("result", lambda r: (r == "loss").sum()),
        win_rate=("result", score),
    )


def per_night(joined: pd.DataFrame) -> pd.DataFrame:
    """One row per night: hours asleep and how the following games went."""
    out = _tally(joined.groupby("night"))
    out.insert(0, "asleep_h", joined.groupby("night")["asleep_h"].first())
    return out.reset_index()


def per_awake_bin(joined: pd.DataFrame, width: float = 2) -> pd.DataFrame:
    """One row per ``width``-hour stretch of time awake. ``awake_h`` is the
    middle of the stretch, so a 2-hour bin from 14 to 16 hours sits at 15."""
    start = (np.floor(joined["awake_h"] / width) * width).rename("awake_from_h")
    out = _tally(joined.groupby(start))
    out.insert(0, "awake_h", out.index + width / 2)
    return out.reset_index()


def per_game(joined: pd.DataFrame, x: str):
    """Correlation of ``x`` with each game's points. Every game counts once, the
    same weighting as the charts' trend lines."""
    return correlate(joined, x, "points") if len(joined) > 2 else None


def draw(fig, theme, points: pd.DataFrame, x: str, c, xlabel: str, note: str,
         xstep: float | None = None) -> None:
    """Win rate against ``points[x]``, sized and trend-weighted by games.
    ``xstep`` puts x ticks on multiples of it (e.g. the bin edges)."""
    ax = fig.subplots()
    charts.scatter(ax, points[x].tolist(), points["win_rate"].tolist(), theme,
                   sizes=points["games"].tolist(), max_size=260,
                   trend=len(points) > 2, weights=points["games"].tolist())
    charts.percent_axis(ax, "y")
    ax.set_ylim(-0.05, 1.05)
    if xstep:
        ax.xaxis.set_major_locator(MultipleLocator(xstep))
    ax.set_xlabel(xlabel)
    ax.set_ylabel("win rate (draws count as half)")
    stats = (f"\nper game: Pearson {c.pearson:+.2f}, Spearman {c.spearman:+.2f} "
             f"(p={c.p:.2f}), n={c.n}") if c else ""
    charts.titles(fig, ax, theme, "Win rate", source=f"{SOURCE_NOTE} · {note}{stats}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    yesterday = dt.date.today() - dt.timedelta(days=1)
    p.add_argument("--start", default=str(yesterday - dt.timedelta(days=180)),
                   help="first day (default: 180 days before --end)")
    p.add_argument("--end", default=str(yesterday), help="last day (default: yesterday)")
    p.add_argument("--user", help="Lichess username (default: the token's owner)")
    p.add_argument("--speeds", nargs="+", help="only these time controls, e.g. blitz rapid")
    p.add_argument("--rated", action="store_true", help="rated games only")
    p.add_argument("--max-awake", type=float, default=24,
                   help="ignore games more than this many hours after waking (default: 24)")
    p.add_argument("--awake-bin", type=float, default=2,
                   help="hours per point on the hours-awake chart (default: 2)")
    p.add_argument("--out", type=Path, default=project_out("chess/sleep"))
    return p


def write(out: Path, stem: str, points: pd.DataFrame, x: str, c, xlabel: str,
          note: str, xstep: float | None = None) -> list[Path]:
    csv = out / f"{stem}.csv"
    points.to_csv(csv, index=False)
    return [csv, *render(lambda fig, theme: draw(fig, theme, points, x, c, xlabel, note, xstep),
                         out / stem, figsize=(10, 6.5))]


def print_buckets(joined: pd.DataFrame, col: str, edges, fmt) -> None:
    for bucket, grp in joined.groupby(pd.cut(joined[col], edges, right=False), observed=True):
        print(f"  {fmt(bucket.left, bucket.right):<20} "
              f"{score(grp['result']):4.0%} over {len(grp)} games")


def main() -> None:
    args = parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args.out.mkdir(parents=True, exist_ok=True)

    games = Lichess().load_games(args.start, args.end, user=args.user)
    if games.empty:
        sys.exit(f"no games between {args.start} and {args.end}")
    if args.speeds:
        games = games[games["speed"].isin(args.speeds)]
    if args.rated:
        games = games[games["rated"]]
    # a day of sleep before the range, so the first day's games have a night
    start = dt.date.fromisoformat(args.start) - dt.timedelta(days=1)
    sleep = GoogleHealth().load_range("sleep", start, args.end)
    if sleep.empty:
        sys.exit(f"no sleep data between {start} and {args.end}")

    joined = games_after_sleep(games, nightly(sleep), args.max_awake)
    if joined.empty:
        sys.exit("no games fell after a recorded night of sleep")

    nights = per_night(joined)
    awake = per_awake_bin(joined, args.awake_bin)
    c_sleep, c_awake = per_game(joined, "asleep_h"), per_game(joined, "awake_h")
    w = args.awake_bin
    written = write(args.out, "win-rate-vs-sleep", nights, "asleep_h", c_sleep,
                    "hours asleep the night before", "one point per night, sized by games")
    written += write(args.out, "win-rate-vs-hours-awake", awake, "awake_h", c_awake,
                     "hours since waking up when the game started",
                     f"one point per {w:g} hours awake, sized by games",
                     xstep=w * max(1, round(4 / w)))      # bin edges, about every 4 h

    print(f"\n=== Chess vs sleep, {args.start} – {args.end} ===")
    print(f"games                 {len(games)} ({len(joined)} after a recorded night, "
          f"over {len(nights)} nights)")
    if joined.attrs.get("during_sleep"):
        print(f"                      {joined.attrs['during_sleep']} left out: played during a "
              "wake-up in the middle of a recorded sleep")
    print(f"overall win rate      {score(joined['result']):.0%}")
    print("by sleep the night before:")
    print_buckets(joined, "asleep_h", SLEEP_BUCKETS,
                  lambda lo, hi: f"under {hi:g} h" if lo == 0
                  else (f"{lo:g} h or more" if hi == 24 else f"{lo:g}–{hi:g} h"))
    if c_sleep:
        print(f"  per game: {c_sleep}")
    print("by hours awake:")
    edges = list(np.arange(0, args.max_awake + w, w))
    print_buckets(joined, "awake_h", edges, lambda lo, hi: f"{lo:g}–{hi:g} h awake")
    if c_awake:
        print(f"  per game: {c_awake}")
    print("\nwrote:", ", ".join(str(p) for p in written))


if __name__ == "__main__":
    main()
