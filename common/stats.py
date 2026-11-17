"""Small statistics helpers shared by project scripts.

Deliberately dependency-free (no scipy): the toolkit reports correlations
with their sample size and a p-value so a weak relationship is never quoted
without the context that it's weak.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import pandas as pd


class Correlation(NamedTuple):
    pearson: float
    spearman: float
    p: float          # two-sided, for the Spearman coefficient
    n: int

    def __str__(self) -> str:
        return (f"pearson {self.pearson:+.3f}  spearman {self.spearman:+.3f}  "
                f"p={self.p:.4f}  n={self.n}")


def correlate(df: pd.DataFrame, x: str, y: str) -> Correlation:
    """Pearson and Spearman correlation of two columns, rows with NaN dropped.

    The p-value uses the t approximation for Spearman's rho with a normal
    tail, which is accurate from roughly n = 30 up; below that treat it as
    indicative only.
    """
    d = df[[x, y]].dropna()
    n = len(d)
    if n < 3:
        return Correlation(float("nan"), float("nan"), float("nan"), n)
    pearson = d[x].corr(d[y])
    # Spearman is Pearson on average ranks (ties share a rank) -- the same
    # thing scipy computes, without needing scipy, which pandas' own
    # method="spearman" quietly imports.
    spearman = d[x].rank().corr(d[y].rank())
    if abs(spearman) < 1:
        t = spearman * math.sqrt((n - 2) / (1 - spearman**2))
        p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))
    else:
        p = 0.0
    return Correlation(pearson, spearman, p, n)


def correlation_table(df: pd.DataFrame, xs, y: str) -> pd.DataFrame:
    """One row per column in ``xs``: its correlation with ``y``."""
    return pd.DataFrame(
        [{"driver": x, **correlate(df, x, y)._asdict()} for x in xs]
    )


def trailing_mean(values: pd.Series, days: int = 14, min_periods: int = 7,
                  include_current: bool = False) -> pd.Series:
    """For each date, the mean of ``values`` over the previous ``days`` days.

    ``values`` is indexed by date; missing dates simply don't count, and the
    result has a row for every calendar day in the range. By
    default the current day is excluded, so each day is compared with the
    two weeks *before* it rather than partly with itself. A day with fewer
    than ``min_periods`` values in its window gets NaN rather than an average
    of two or three points.
    """
    s = values.copy()
    s.index = pd.DatetimeIndex(s.index).normalize()
    s = s.groupby(level=0).mean()                     # one value per date
    s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))
    # "14D" with closed="left" is [D-14, D): the 14 days before D.
    # closed="right" is (D-14, D]: the 13 before plus D itself.
    return s.rolling(f"{days}D", closed="right" if include_current else "left",
                     min_periods=min_periods).mean()
