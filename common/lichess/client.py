"""Lichess -- a player's games and rating history from the public Lichess API.

Games are exported from one streaming endpoint::

    GET https://lichess.org/api/games/user/{username}     (ndjson, one game a line)

Game data is public, so a token is optional. With your own token, exports of
your own games run about three times faster, and private details such as
computer-analysis accuracy are included. The token is read from
``$LICHESS_TOKEN`` or ``~/.config/data_scrape/lichess_token`` (see
:func:`lichess_token`). Create one at https://lichess.org/account/oauth/token;
no scopes are needed for reading games.

Games are cached by ``"<user>/games/<YYYY-MM>"`` (UTC months, by game start).
A finished month never changes, so it's cached forever; the current month is
re-fetched on every load.

Reference: https://lichess.org/api
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from ..paths import CONFIG_ROOT
from ..periods import month_is_closed, months_between, parse_month
from ..sources.base import Source

log = logging.getLogger(__name__)

API_ROOT = "https://lichess.org"

#: Where :func:`lichess_token` looks when ``$LICHESS_TOKEN`` isn't set.
TOKEN_PATH = CONFIG_ROOT / "lichess_token"

#: Game states that never became a game.
UNPLAYED = frozenset({"aborted", "created", "started", "noStart"})

#: Days after a month ends before it's cached for good (a game started just
#: before midnight UTC may still be in progress).
LAG_DAYS = 1


class LichessError(RuntimeError):
    """Raised when a token is required but missing or malformed."""


def lichess_token(path: Path | None = None, required: bool = False) -> str | None:
    """The personal API token, or ``None`` if there isn't one.

    Looks at ``$LICHESS_TOKEN`` first, then ``path`` (default
    ``~/.config/data_scrape/lichess_token``). Lichess tokens start ``lip_``.
    """
    token = os.environ.get("LICHESS_TOKEN")
    path = path or TOKEN_PATH
    if not token and path.exists():
        token = path.read_text().strip()
    if token and not token.startswith("lip_"):
        raise LichessError(f"{path} doesn't hold a Lichess token (they start 'lip_')")
    if required and not token:
        raise LichessError(
            f"no Lichess token: set $LICHESS_TOKEN or save one to {path} "
            "(create it at https://lichess.org/account/oauth/token)"
        )
    return token or None


def _ms(day: dt.date) -> int:
    return int(dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc).timestamp() * 1000)


class Lichess(Source):
    """A Lichess player's games.

    >>> li = Lichess()
    >>> games = li.load_games("2026-01-01", "2026-03-31")          # your own
    >>> games = li.load_games("2026-01-01", "2026-03-31", user="DrNykterstein")
    >>> ratings = li.rating_history()
    """

    name = "lichess"

    def __init__(
        self,
        *args,
        token: str | None = None,
        today: dt.date | None = None,
        **kwargs,
    ) -> None:
        # Lichess asks for one request at a time; the stream itself is the slow part.
        kwargs.setdefault("min_interval", 1.0)
        super().__init__(*args, **kwargs)
        self.token = token if token is not None else lichess_token()
        self._today = today
        self._me: str | None = None

    @property
    def today(self) -> dt.date:
        return self._today or dt.date.today()

    def _headers(self, accept: str = "application/json") -> dict:
        h = {"Accept": accept}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    # -- public API --------------------------------------------------------
    def me(self) -> str:
        """The username the token belongs to."""
        if self._me is None:
            if not self.token:
                raise LichessError(
                    "pass user= or set up a token so I know who 'you' are "
                    f"(see {TOKEN_PATH} in common/lichess/client.py)"
                )
            body = self.fetcher.get_json(f"{API_ROOT}/api/account", headers=self._headers())
            self._me = body["username"]
        return self._me

    def load_games(
        self,
        start: dt.date | str,
        end: dt.date | str,
        user: str | None = None,
        *,
        include_unplayed: bool = False,
    ) -> pd.DataFrame:
        """Every game ``user`` (default: you) started in the inclusive UTC-date
        range, oldest first. See :func:`flatten_games` for the columns."""
        user = (user or self.me()).lower()
        start_d, end_d = pd.Timestamp(start).date(), pd.Timestamp(end).date()
        frames = [self.load(f"{user}/games/{m}") for m in months_between(start_d, end_d)]
        frames = [f for f in frames if len(f)]
        if not frames:
            return pd.DataFrame()
        # Months without, say, any analysed game have all-empty columns; drop
        # them before concatenating so they don't decide the dtypes, then put
        # every column back.
        columns = list(dict.fromkeys(c for f in frames for c in f.columns))
        out = pd.concat([f.dropna(axis=1, how="all") for f in frames], ignore_index=True)
        out = out.reindex(columns=columns)
        day = out["played_at"].dt.tz_convert("UTC").dt.normalize().dt.tz_localize(None)
        keep = (day >= pd.Timestamp(start_d)) & (day <= pd.Timestamp(end_d))
        if not include_unplayed:
            keep &= ~out["status"].isin(UNPLAYED)
        return out.loc[keep].sort_values("played_at").reset_index(drop=True)

    def rating_history(self, user: str | None = None) -> pd.DataFrame:
        """One row per day a rating changed: ``date``, ``perf`` (Blitz,
        Rapid...), ``rating``. Always fetched fresh; it's one small request."""
        user = user or self.me()
        body = self.fetcher.get_json(
            f"{API_ROOT}/api/user/{user}/rating-history", headers=self._headers()
        )
        return flatten_rating_history(body)

    # -- Source hooks ------------------------------------------------------
    def _is_final(self, key: str) -> bool:
        return month_is_closed(key.rsplit("/", 1)[1], LAG_DAYS, self.today)

    def _download(self, key: str) -> Path:
        dest = self.cache.path(f"raw/{key}.ndjson")
        if dest.exists() and self._is_final(key):
            return dest
        user, _, month = key.split("/")
        first, nxt = parse_month(month)
        params = {
            "since": _ms(first),
            "until": _ms(nxt) - 1,
            "sort": "dateAsc",
            "pgnInJson": "true",
            "opening": "true",
            "clocks": "true",
            "evals": "true",
            "accuracy": "true",
        }
        resp = self.fetcher.get(
            f"{API_ROOT}/api/games/user/{user}",
            params=params,
            headers=self._headers("application/x-ndjson"),
            stream=True,
        )
        tmp = dest.with_suffix(".ndjson.part")
        n = 0
        with resp, open(tmp, "w") as fh:
            for line in resp.iter_lines(decode_unicode=True):
                if line:
                    fh.write(line + "\n")
                    n += 1
        tmp.replace(dest)
        log.info("[%s] %s: %d games", self.name, key, n)
        return dest

    def _parse(self, raw: Path) -> pd.DataFrame:
        user = raw.parent.parent.name  # raw/<user>/games/<month>.ndjson
        games = [json.loads(line) for line in raw.read_text().splitlines() if line.strip()]
        return flatten_games(games, user)


# -- flattening ------------------------------------------------------------

def _player(p: dict) -> dict:
    user = p.get("user") or {}
    analysis = p.get("analysis") or {}
    return {
        "name": user.get("name") or ("AI level %s" % p["aiLevel"] if "aiLevel" in p else None),
        "rating": p.get("rating"),
        "rating_diff": p.get("ratingDiff"),
        "provisional": bool(p.get("provisional", False)),
        "accuracy": analysis.get("accuracy"),
        "acpl": analysis.get("acpl"),
        "inaccuracies": analysis.get("inaccuracy"),
        "mistakes": analysis.get("mistake"),
        "blunders": analysis.get("blunder"),
    }


def flatten_games(games: Sequence[dict], user: str) -> pd.DataFrame:
    """One row per game, seen from ``user``'s side of the board.

    Columns: ``id``, ``url``, ``played_at``/``ended_at`` (UTC), ``rated``,
    ``variant``, ``speed``, ``perf``, ``source``, ``status``, ``initial_s``,
    ``increment_s``, ``opening_eco``/``opening_name``/``opening_ply``,
    ``plies`` and ``moves`` (SAN, space-separated), ``clocks`` (JSON list of
    centiseconds, one per ply), ``pgn``; then ``color``, ``result``
    (win/loss/draw) and ``my_*``/``opp_*`` for name, rating, rating_diff,
    provisional, accuracy, acpl, inaccuracies, mistakes, blunders. The
    analysis columns are only filled for games with computer analysis.
    """
    if not games:
        return pd.DataFrame()
    user = user.lower()
    rows = []
    for g in games:
        players = g.get("players", {})
        white, black = _player(players.get("white", {})), _player(players.get("black", {}))
        color = "white" if (white["name"] or "").lower() == user else "black"
        me, opp = (white, black) if color == "white" else (black, white)
        winner = g.get("winner")
        if g.get("status") in UNPLAYED:
            result = None
        elif winner is None:
            result = "draw"
        else:
            result = "win" if winner == color else "loss"
        clock = g.get("clock") or {}
        opening = g.get("opening") or {}
        moves = g.get("moves") or ""
        row = {
            "id": g["id"],
            "url": f"{API_ROOT}/{g['id']}",
            "played_at": g.get("createdAt"),
            "ended_at": g.get("lastMoveAt"),
            "rated": bool(g.get("rated", False)),
            "variant": g.get("variant"),
            "speed": g.get("speed"),
            "perf": g.get("perf"),
            "source": g.get("source"),
            "status": g.get("status"),
            "initial_s": clock.get("initial"),
            "increment_s": clock.get("increment"),
            "opening_eco": opening.get("eco"),
            "opening_name": opening.get("name"),
            "opening_ply": opening.get("ply"),
            "plies": len(moves.split()),
            "moves": moves,
            "clocks": json.dumps(g["clocks"]) if "clocks" in g else None,
            "pgn": g.get("pgn"),
            "color": color,
            "result": result,
        }
        row.update({f"my_{k}": v for k, v in me.items()})
        row.update({f"opp_{k}": v for k, v in opp.items()})
        rows.append(row)

    df = pd.DataFrame(rows)
    for col in ("played_at", "ended_at"):
        df[col] = pd.to_datetime(df[col], unit="ms", utc=True)
    return df


def flatten_rating_history(body: Sequence[dict]) -> pd.DataFrame:
    """Lichess's ``[{name, points: [[y, m0, d, r], ...]}]`` as tidy rows.
    (The API's months are zero-based.)"""
    rows = [
        {"date": pd.Timestamp(y, m + 1, d), "perf": perf["name"], "rating": r}
        for perf in body
        for y, m, d, r in perf.get("points", [])
    ]
    if not rows:
        return pd.DataFrame(columns=["date", "perf", "rating"])
    return pd.DataFrame(rows).sort_values(["perf", "date"]).reset_index(drop=True)


def local_time(stamps: pd.Series, tz: str) -> pd.Series:
    """UTC timestamps as naive wall-clock time in ``tz`` (e.g.
    ``"America/Los_Angeles"``), for hour-of-day questions."""
    return stamps.dt.tz_convert(tz).dt.tz_localize(None)
