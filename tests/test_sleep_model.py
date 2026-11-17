"""The average-night stage model. Synthetic nights, no network."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.health.sleep_model import Night, StageModel, _runs  # noqa: E402


def night(day, deep_ranges, length=480, onset_hour=1):
    grid = np.zeros(length, dtype=bool)
    for a, b in deep_ranges:
        grid[a:b] = True
    date = pd.Timestamp(day)
    return Night(date, date + pd.Timedelta(hours=onset_hour), grid, length)


# 20 nights, all deep 20-50 min after onset; half also deep 110-140.
NIGHTS = [night(f"2026-09-{d:02d}", [(20, 50)] + ([(110, 140)] if d % 2 else []))
          for d in range(1, 21)]


def test_curve_is_share_of_nights_in_stage():
    m = StageModel(smooth_min=1, min_nights=1).fit(NIGHTS)
    assert m.predict_proba([30, 120, 300]).tolist() == [1.0, 0.5, 0.0]


def test_windows_where_more_nights_than_not():
    m = StageModel(smooth_min=1, min_nights=1, threshold=0.5).fit(NIGHTS)
    w = m.windows()
    assert w[["start_min", "end_min"]].values.tolist() == [[20, 50], [110, 140]]
    m.threshold = 0.6
    assert len(m.windows()) == 1


def test_thin_tail_is_not_predicted():
    long = NIGHTS + [night("2026-10-01", [(500, 540)], length=600)]
    m = StageModel(smooth_min=1, min_nights=5).fit(long)
    assert m.predict_proba([520])[0] == 0.0     # one lie-in can't define hour nine


def test_missed_is_predicted_minus_actual():
    m = StageModel(smooth_min=1, min_nights=1).fit(NIGHTS)
    miss = m.missed([NIGHTS[1]])                # an even night: no second block
    assert len(miss) == 1
    row = miss.iloc[0]
    assert row["minutes"] == 30
    assert row["start_local"] == NIGHTS[1].onset + pd.Timedelta(minutes=110)
    assert m.missed([NIGHTS[0]]).empty          # an odd night had both blocks


def test_evaluate_is_cross_validated_and_beats_baseline():
    # second block on 15 of 20 nights, so every training fold still sees it
    nights = [night(f"2026-09-{d:02d}", [(20, 50)] + ([(110, 140)] if d % 4 else []))
              for d in range(1, 21)]
    s = StageModel(smooth_min=1, min_nights=1).evaluate(nights, folds=5)
    assert s["nights"] == 20
    assert s["accuracy"] > s["baseline_accuracy"]
    assert s["recall"] == 1.0                   # every deep minute falls in a window
    assert s["precision"] == pytest.approx((30 * 20 + 30 * 15) / (60 * 20))


def test_evaluate_never_lets_a_night_predict_itself():
    """Folds made only of nights with a rare block can't learn it from the
    others -- the score has to show that, not hide it."""
    s = StageModel(smooth_min=1, min_nights=1).evaluate(NIGHTS, folds=4)
    assert s["recall"] < 1.0


def test_runs():
    assert _runs(np.array([0, 1, 1, 0, 1], bool)) == [(1, 3), (4, 5)]
    assert _runs(np.array([], bool)) == []


def test_fit_needs_data():
    with pytest.raises(ValueError):
        StageModel().fit([])
