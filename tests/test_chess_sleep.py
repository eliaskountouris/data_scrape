"""Pairing games with the night before. No network.

All matching is in UTC, so fixtures are written as Pacific wall-clock times
(as you'd remember them) and converted.
"""

import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("chess_sleep", ROOT / "projects/chess/sleep/run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def utc(*local, tz="America/Los_Angeles"):
    return pd.to_datetime(list(local)).tz_localize(tz).tz_convert("UTC")


def nights(beds, wakes, asleep_min, tz="America/Los_Angeles"):
    bed, wake = utc(*beds, tz=tz), utc(*wakes, tz=tz)
    return pd.DataFrame({
        "night": pd.to_datetime([w[:10] for w in wakes]),
        "bed_time": bed, "wake_time": wake,
        "wake_local": wake.tz_convert(tz).tz_localize(None),
        "asleep_min": asleep_min,
    })


NIGHTS = nights(["2026-09-03 02:00", "2026-09-04 01:30"],
                ["2026-09-03 08:14", "2026-09-04 09:30"], [332.0, 480.0])


def games(*local_times, results=None, tz="America/Los_Angeles"):
    return pd.DataFrame({"played_at": utc(*local_times, tz=tz),
                         "result": results or ["win"] * len(local_times)})


def test_late_night_game_counts_against_the_previous_morning():
    j = run.games_after_sleep(games("2026-09-03 22:00", "2026-09-04 01:11", "2026-09-04 10:00"),
                              NIGHTS)
    assert j["night"].dt.strftime("%m-%d").tolist() == ["09-03", "09-03", "09-04"]
    assert j["awake_h"].round(2).tolist() == [13.77, 16.95, 0.5]


def test_game_too_long_after_waking_or_before_any_sleep_is_dropped():
    j = run.games_after_sleep(games("2026-09-02 20:00", "2026-09-05 12:00"), NIGHTS,
                              max_awake_h=24)
    assert j.empty


def test_game_played_during_a_recorded_sleep_is_dropped_and_counted():
    j = run.games_after_sleep(games("2026-09-04 01:00", "2026-09-04 09:00", "2026-09-04 11:00"),
                              NIGHTS)
    # 01:00 is before bed (counts against the 3rd); 09:00 is mid-sleep; 11:00 is after waking
    assert j["awake_h"].round(2).tolist() == [16.77, 1.5]
    assert j.attrs["during_sleep"] == 1


def test_travel_sleep_in_another_time_zone_still_lines_up():
    # Slept in New York, woke 08:00 Eastern = 05:00 Pacific; played at 06:00
    # Pacific. In local-vs-local terms that looks like a game before waking.
    east = nights(["2026-11-06 23:00"], ["2026-11-07 08:00"], [500.0], tz="America/New_York")
    j = run.games_after_sleep(games("2026-11-07 06:00"), east)
    assert j["awake_h"].tolist() == [1.0] and j.attrs["during_sleep"] == 0


def test_clock_change_night():
    # Nov 1 2026: clocks go back at 2 a.m. Bed 00:30 PDT, wake 08:00 PST is
    # 8.5 real hours; a game at 08:30 PST is half an hour after waking.
    n = nights(["2026-11-01 00:30"], ["2026-11-01 08:00"], [480.0])
    j = run.games_after_sleep(games("2026-11-01 08:30"), n)
    assert j["awake_h"].tolist() == [0.5]
    assert (n["wake_time"] - n["bed_time"]).iloc[0] == pd.Timedelta(hours=8.5)


def test_per_night_scores_draws_as_half():
    j = run.games_after_sleep(
        games("2026-09-03 21:00", "2026-09-03 21:10", "2026-09-03 21:20",
              results=["win", "draw", "loss"]), NIGHTS)
    row = run.per_night(j).iloc[0]
    assert (row["games"], row["wins"], row["draws"], row["losses"]) == (3, 1, 1, 1)
    assert row["win_rate"] == 0.5 and row["asleep_h"] == 332 / 60


def test_awake_bins():
    j = run.games_after_sleep(games("2026-09-03 09:00", "2026-09-03 09:30", "2026-09-03 23:00",
                                    results=["win", "loss", "draw"]), NIGHTS)
    b = run.per_awake_bin(j, width=2)
    assert b["awake_h"].tolist() == [1.0, 15.0]
    assert b["games"].tolist() == [2, 1] and b["win_rate"].tolist() == [0.5, 0.5]
