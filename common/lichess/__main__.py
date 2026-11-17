"""Command line for the Lichess source.

    python -m common.lichess games 2026-01-01 2026-01-31            # your games
    python -m common.lichess games 2026-01-01 2026-01-31 --user someone --csv out.csv
    python -m common.lichess ratings
"""

from __future__ import annotations

import argparse
import logging

from .client import Lichess


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m common.lichess")
    sub = parser.add_subparsers(dest="cmd", required=True)

    games = sub.add_parser("games", help="fetch a player's games and print a summary")
    games.add_argument("start", help="YYYY-MM-DD (UTC)")
    games.add_argument("end", help="YYYY-MM-DD (inclusive)")

    ratings = sub.add_parser("ratings", help="rating history per time control")

    for p in (games, ratings):
        p.add_argument("--user", help="Lichess username (default: the token's owner)")
        p.add_argument("--csv", help="also write the table to this file")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    li = Lichess()
    if args.cmd == "games":
        df = li.load_games(args.start, args.end, user=args.user)
        print(f"{len(df)} games")
        if len(df):
            print(df.groupby("speed")["result"].value_counts().unstack(fill_value=0).to_string())
    else:
        df = li.rating_history(args.user)
        print(df.groupby("perf").tail(1).to_string(index=False))
    if args.csv and len(df):
        df.to_csv(args.csv, index=False)
        print(f"wrote {args.csv}")


if __name__ == "__main__":
    main()
