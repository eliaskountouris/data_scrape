"""Lichess flattening, token handling and month caching. No network."""

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.cache import Cache  # noqa: E402
from common.lichess import (  # noqa: E402
    Lichess,
    LichessError,
    flatten_games,
    flatten_rating_history,
    lichess_token,
    local_time,
)


def game(id_, created, white="me", black="opp", winner="white", status="resign",
         analysis=False):
    g = {
        "id": id_, "rated": True, "variant": "standard", "speed": "blitz",
        "perf": "blitz", "createdAt": created, "lastMoveAt": created + 60_000,
        "status": status, "source": "pool",
        "players": {
            "white": {"user": {"name": white, "id": white.lower()}, "rating": 1500,
                      "ratingDiff": 6},
            "black": {"user": {"name": black, "id": black.lower()}, "rating": 1400,
                      "ratingDiff": -6},
        },
        "opening": {"eco": "D30", "name": "Queen's Gambit Declined", "ply": 4},
        "moves": "d4 d5 c4 e6 Nf3",
        "clocks": [18003, 18003, 17547, 17800, 17000],
        "pgn": "[Event \"x\"]\n\n1. d4 d5 *",
        "clock": {"initial": 180, "increment": 2, "totalTime": 260},
        "fullId": id_ + "SECRET",
    }
    if winner:
        g["winner"] = winner
    if analysis:
        for side, acc in (("white", 91), ("black", 74)):
            g["players"][side]["analysis"] = {"inaccuracy": 1, "mistake": 0,
                                              "blunder": 2, "acpl": 30, "accuracy": acc}
    return g


T0 = int(dt.datetime(2026, 3, 4, 12, tzinfo=dt.timezone.utc).timestamp() * 1000)


def test_flatten_from_players_side():
    df = flatten_games([game("a", T0, white="Me"), game("b", T0, white="other", black="ME")], "me")
    assert list(df["color"]) == ["white", "black"]
    assert list(df["result"]) == ["win", "loss"]          # white won both
    assert list(df["my_rating"]) == [1500, 1400]
    assert list(df["opp_rating_diff"]) == [-6, 6]
    row = df.iloc[0]
    assert row["played_at"] == pd.Timestamp("2026-03-04 12:00", tz="UTC")
    assert row["plies"] == 5 and row["initial_s"] == 180 and row["opening_eco"] == "D30"
    assert json.loads(row["clocks"])[2] == 17547
    assert row["url"] == "https://lichess.org/a"
    assert "fullId" not in df and not df.astype(str).apply(
        lambda c: c.str.contains("SECRET")).any().any()


def test_draws_unplayed_and_analysis():
    df = flatten_games([
        game("d", T0, winner=None, status="draw"),
        game("x", T0, winner=None, status="aborted"),
        game("z", T0, analysis=True),
    ], "me")
    assert df["result"].iloc[0] == "draw" and pd.isna(df["result"].iloc[1])
    z = df.iloc[2]
    assert (z["my_accuracy"], z["opp_accuracy"], z["my_blunders"]) == (91, 74, 2)
    assert pd.isna(df.iloc[0]["my_accuracy"])


def test_rating_history_months_are_zero_based():
    df = flatten_rating_history([
        {"name": "Blitz", "points": [[2026, 0, 31, 1500], [2026, 10, 15, 1379]]},
        {"name": "Atomic", "points": []},
    ])
    assert df["date"].tolist() == [pd.Timestamp("2026-01-31"), pd.Timestamp("2026-11-15")]
    assert set(df["perf"]) == {"Blitz"}
    assert flatten_rating_history([]).columns.tolist() == ["date", "perf", "rating"]


def test_local_time():
    s = pd.Series(pd.to_datetime([T0], unit="ms", utc=True))
    assert local_time(s, "America/Los_Angeles").iloc[0] == pd.Timestamp("2026-03-04 04:00")


def test_token_sources(tmp_path, monkeypatch):
    monkeypatch.delenv("LICHESS_TOKEN", raising=False)
    path = tmp_path / "lichess_token"
    assert lichess_token(path) is None
    with pytest.raises(LichessError):
        lichess_token(path, required=True)
    path.write_text("lip_abc\n")
    assert lichess_token(path) == "lip_abc"
    monkeypatch.setenv("LICHESS_TOKEN", "lip_env")
    assert lichess_token(path) == "lip_env"
    monkeypatch.setenv("LICHESS_TOKEN", "not-a-token")
    with pytest.raises(LichessError):
        lichess_token(path)


class FakeLichess(Lichess):
    """Serves canned months instead of streaming from lichess.org."""

    def __init__(self, months, **kw):
        super().__init__(token="", **kw)
        self.months, self.calls = months, []

    def _download(self, key):
        self.calls.append(key)
        dest = self.cache.path(f"raw/{key}.ndjson")
        month = key.rsplit("/", 1)[1]
        dest.write_text("".join(json.dumps(g) + "\n" for g in self.months.get(month, [])))
        return dest


def test_load_games_range_caching_and_unplayed(tmp_path):
    def ms(y, m, d):
        return int(dt.datetime(y, m, d, 3, tzinfo=dt.timezone.utc).timestamp() * 1000)
    months = {
        "2026-02": [game("feb", ms(2026, 2, 27))],
        "2026-03": [game("early", ms(2026, 3, 1)), game("ab", ms(2026, 3, 5), status="aborted"),
                    game("late", ms(2026, 3, 20))],
        "2026-04": [],
    }
    li = FakeLichess(months, cache=Cache(tmp_path), today=dt.date(2026, 4, 10))
    df = li.load_games("2026-02-28", "2026-04-30", user="Me")
    assert df["id"].tolist() == ["early", "late"]       # range-trimmed, aborted dropped
    assert li.load_games("2026-03-01", "2026-03-31", user="me",
                         include_unplayed=True)["id"].tolist() == ["early", "ab", "late"]
    # March is closed and came from parquet the second time; April is open.
    assert li.calls.count("me/games/2026-03") == 1
    li.load_games("2026-04-01", "2026-04-30", user="me")
    assert li.calls.count("me/games/2026-04") == 2


def test_me_needs_a_token(tmp_path, monkeypatch):
    monkeypatch.delenv("LICHESS_TOKEN", raising=False)
    monkeypatch.setattr("common.lichess.client.TOKEN_PATH", tmp_path / "none")
    with pytest.raises(LichessError):
        Lichess(token="", cache=Cache(tmp_path)).me()
