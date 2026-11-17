"""Command line for the Google Health source.

    python -m common.health auth                        # one-time browser sign-in
    python -m common.health pull steps 2026-01-01 2026-01-31
"""

from __future__ import annotations

import argparse
import logging

from .auth import GoogleHealthAuth
from .google import COMMON_TYPES, GoogleHealth


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m common.health")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("auth", help="sign in and save a refresh token")

    pull = sub.add_parser("pull", help="fetch one data type and print a summary")
    pull.add_argument("data_type", help=f"e.g. {', '.join(COMMON_TYPES[:6])}")
    pull.add_argument("start", help="YYYY-MM-DD")
    pull.add_argument("end", help="YYYY-MM-DD (inclusive)")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.cmd == "auth":
        auth = GoogleHealthAuth()
        auth.login()
        print(f"signed in; token saved to {auth.token_path}")
    else:
        df = GoogleHealth().load_range(args.data_type, args.start, args.end)
        print(f"{len(df)} rows")
        if len(df):
            print(df.head(10).to_string())


if __name__ == "__main__":
    main()
