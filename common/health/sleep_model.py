"""An average-night model of one sleep stage.

For every minute after falling asleep, the share of past nights that were in
the stage at that minute. That curve *is* the model: it predicts the stage
wherever the share reaches ``threshold`` (default 0.5, "more nights than not").

    model = StageModel("deep").fit(sleep)
    model.predict_proba([30, 120, 300])     # minutes after falling asleep
    model.windows()                         # when it predicts deep sleep
    model.evaluate(sleep)                   # cross-validated, by night
    model.missed(sleep)                     # predicted, but didn't happen

Time zero is **sleep onset**, the start of the first non-awake stage, not
when the session started, so minutes spent falling asleep don't shift the
whole night. Only main sleeps with stage data are used; naps have a different
structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .sleep import main_sleeps, stage_table


@dataclass
class Night:
    """One main sleep on a one-minute grid starting at onset."""

    night: pd.Timestamp          # wake-up date
    onset: pd.Timestamp          # local wall clock
    in_stage: np.ndarray         # bool per minute after onset
    end_min: int                 # minutes from onset to the end of the session


def nights_on_grid(sleep: pd.DataFrame, stage: str = "deep") -> list[Night]:
    """Main-sleep sessions with stage data, as minute-by-minute arrays."""
    df = main_sleeps(sleep)
    if "type" in df:
        df = df[df["type"].eq("STAGES")]
    stages = stage_table(df)
    out = []
    for _, segs in stages.groupby("session", sort=False):
        asleep = segs[segs["stage"] != "awake"]
        if asleep.empty:
            continue
        onset = asleep["start_local"].min()
        end_min = int((segs["end_local"].max() - onset) / pd.Timedelta(minutes=1))
        grid = np.zeros(max(end_min, 0), dtype=bool)
        for a, b in zip(*(segs.loc[segs["stage"] == stage.lower(), c]
                          for c in ("start_local", "end_local"))):
            lo = max(int((a - onset) / pd.Timedelta(minutes=1)), 0)
            grid[lo:int((b - onset) / pd.Timedelta(minutes=1))] = True
        out.append(Night(segs["night"].iloc[0], onset, grid, end_min))
    return sorted(out, key=lambda n: n.onset)


@dataclass
class StageModel:
    """Share of nights in ``stage`` at each minute after sleep onset.

    ``smooth_min`` evens out the curve with a centred rolling mean. Past the
    point where fewer than ``min_nights`` nights are still asleep the
    probability is set to 0, so a handful of long lie-ins can't make the model
    predict deep sleep at hour nine.
    """

    stage: str = "deep"
    threshold: float = 0.5
    smooth_min: int = 9
    min_nights: int = 10
    curve: pd.Series = field(default=None, repr=False)      # p by minute
    nights_at: pd.Series = field(default=None, repr=False)  # nights still asleep

    # -- fitting -------------------------------------------------------------
    def fit(self, sleep: pd.DataFrame | list[Night]) -> "StageModel":
        nights = sleep if isinstance(sleep, list) else nights_on_grid(sleep, self.stage)
        if not nights:
            raise ValueError(f"no main sleeps with {self.stage} stage data to fit on")
        length = max(n.end_min for n in nights)
        hits = np.zeros(length)
        count = np.zeros(length)
        for n in nights:
            hits[: len(n.in_stage)] += n.in_stage
            count[: n.end_min] += 1
        with np.errstate(invalid="ignore", divide="ignore"):
            p = np.where(count > 0, hits / count, 0.0)
        p = pd.Series(p).rolling(self.smooth_min, center=True, min_periods=1).mean()
        p[count < self.min_nights] = 0.0
        self.curve = p.rename_axis("minute").rename("p")
        self.nights_at = pd.Series(count, name="nights").rename_axis("minute")
        return self

    # -- prediction ----------------------------------------------------------
    def predict_proba(self, minutes) -> np.ndarray:
        """Chance of being in the stage ``minutes`` after falling asleep."""
        self._check()
        m = np.asarray(minutes, dtype=int)
        inside = (m >= 0) & (m < len(self.curve))
        out = np.zeros(m.shape)
        out[inside] = self.curve.to_numpy()[m[inside]]
        return out

    def predict(self, minutes) -> np.ndarray:
        return self.predict_proba(minutes) >= self.threshold

    def windows(self) -> pd.DataFrame:
        """Each stretch the model predicts the stage, in minutes after onset."""
        self._check()
        runs = _runs(self.curve.to_numpy() >= self.threshold)
        p = self.curve.to_numpy()
        return pd.DataFrame(
            [{"start_min": a, "end_min": b, "peak_p": p[a:b].max()} for a, b in runs],
            columns=["start_min", "end_min", "peak_p"],
        )

    def predicted(self, sleep: pd.DataFrame | list[Night]) -> pd.DataFrame:
        """Predicted stretches laid onto each real night (clipped to its end)."""
        return self._segments(sleep, lambda n, pred: pred)

    def missed(self, sleep: pd.DataFrame | list[Night]) -> pd.DataFrame:
        """Minutes the model predicted the stage but the night wasn't in it."""
        return self._segments(sleep, lambda n, pred: pred & ~n.in_stage[: len(pred)])

    # -- evaluation ----------------------------------------------------------
    def evaluate(self, sleep: pd.DataFrame | list[Night], folds: int = 5) -> dict:
        """Minute-level scores, cross-validated so no night predicts itself.

        Nights are split into ``folds`` groups by date order; each group is
        scored by a model fitted on the others. ``baseline_accuracy`` is what
        "never in the stage" would score, the number to beat.
        """
        nights = sleep if isinstance(sleep, list) else nights_on_grid(sleep, self.stage)
        tp = fp = fn = tn = 0
        for k in range(folds):
            test = nights[k::folds]
            train = [n for i, n in enumerate(nights) if i % folds != k]
            model = StageModel(self.stage, self.threshold, self.smooth_min,
                               self.min_nights).fit(train)
            for n in test:
                pred = model.predict(np.arange(n.end_min))
                actual = np.zeros(n.end_min, dtype=bool)
                actual[: len(n.in_stage)] = n.in_stage[: n.end_min]
                tp += int((pred & actual).sum())
                fp += int((pred & ~actual).sum())
                fn += int((~pred & actual).sum())
                tn += int((~pred & ~actual).sum())
        total = tp + fp + fn + tn
        precision = tp / (tp + fp) if tp + fp else float("nan")
        recall = tp / (tp + fn) if tp + fn else float("nan")
        return {
            "nights": len(nights),
            "accuracy": (tp + tn) / total,
            "baseline_accuracy": (fp + tn) / total,
            "precision": precision,      # predicted deep minutes that were deep
            "recall": recall,            # deep minutes the model caught
            "f1": 2 * precision * recall / (precision + recall),
        }

    # -- internals -----------------------------------------------------------
    def _segments(self, sleep, pick) -> pd.DataFrame:
        self._check()
        nights = sleep if isinstance(sleep, list) else nights_on_grid(sleep, self.stage)
        rows = []
        for n in nights:
            pred = self.predict(np.arange(n.end_min))
            for a, b in _runs(pick(n, pred)):
                rows.append({
                    "night": n.night,
                    "start_local": n.onset + pd.Timedelta(minutes=int(a)),
                    "end_local": n.onset + pd.Timedelta(minutes=int(b)),
                    "minutes": b - a,
                })
        return pd.DataFrame(rows, columns=["night", "start_local", "end_local", "minutes"])

    def _check(self) -> None:
        if self.curve is None:
            raise RuntimeError("call fit() first")


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """``[start, end)`` index pairs for each run of True."""
    m = np.concatenate([[False], np.asarray(mask, bool), [False]])
    edges = np.flatnonzero(np.diff(m.astype(int)))
    return list(zip(edges[::2], edges[1::2]))
