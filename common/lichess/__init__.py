"""common.lichess -- a player's games and rating history from Lichess.

    from common.lichess import Lichess

    li = Lichess()                                    # token optional, see client.py
    games = li.load_games("2026-01-01", "2026-03-31") # your own games
    ratings = li.rating_history()

Your token lives in ``~/.config/data_scrape/lichess_token`` (or ``$LICHESS_TOKEN``).
"""

from .client import (
    TOKEN_PATH,
    UNPLAYED,
    Lichess,
    LichessError,
    flatten_games,
    flatten_rating_history,
    lichess_token,
    local_time,
)

__all__ = [
    "Lichess",
    "LichessError",
    "lichess_token",
    "flatten_games",
    "flatten_rating_history",
    "local_time",
    "TOKEN_PATH",
    "UNPLAYED",
]
