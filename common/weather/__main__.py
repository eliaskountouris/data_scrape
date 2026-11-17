"""Command line for weather and daylight.

    python -m common.weather daily 37.7749 -122.4194 2026-11-01 2026-11-16
    python -m common.weather hourly 37.7749 -122.4194 2026-11-16 2026-11-16 --csv out.csv
"""

from __future__ import annotations

import argparse
import logging

from .openmeteo import Location, OpenMeteoDaily, OpenMeteoHourly


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m common.weather")
    parser.add_argument("granularity", choices=["daily", "hourly"])
    parser.add_argument("lat", type=float)
    parser.add_argument("lon", type=float)
    parser.add_argument("start", help="YYYY-MM-DD")
    parser.add_argument("end", help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--name", help="label for the location column")
    parser.add_argument("--csv", help="write every column to this file")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    source = OpenMeteoDaily() if args.granularity == "daily" else OpenMeteoHourly()
    df = source.load_range(Location(args.lat, args.lon, args.name), args.start, args.end)
    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"wrote {len(df)} rows to {args.csv}")
    cols = (["date", "sunrise", "sunset", "daylight_h", "temp_max_c", "temp_min_c",
             "precip_mm", "weather"] if args.granularity == "daily"
            else ["time", "temp_c", "precip_mm", "cloud_pct", "is_day", "weather"])
    print(df[[c for c in cols if c in df]].to_string(index=False, max_rows=40))


if __name__ == "__main__":
    main()
