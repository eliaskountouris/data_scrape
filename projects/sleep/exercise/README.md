# Sleep and exercise — does a workout change that night's deep and REM sleep?

```bash
python -m common.health auth            # once
python projects/sleep/exercise/run.py   # last 180 days
python projects/sleep/exercise/run.py --start 2026-08-01 --end 2026-11-16
```

## The chart

`sleep-vs-exercise`, with days across:
- **purple**: deep sleep that night, in minutes (left axis)
- **light blue**: REM sleep that night, in minutes (left axis)
- **dark blue**: exercise that day, in hours (right axis)

**Each night is plotted on the day it started**, so a day's workout sits
beside the sleep that followed it. (Elsewhere in the toolkit nights are dated
by the morning you woke up; this project shifts them back one day.)

The two axes have unrelated scales, so where the lines cross means nothing.
Read the chart for timing (do sleep lines move after big exercise days?) and
the printed correlations for strength.

## Data

- **Sleep:** `common.health.nightly()`, main sleeps only. Nights recorded
  without stages are gaps, not zeros.
- **Exercise:** recorded workouts, through `common.health.daily_exercise()`.
  Your watch and phone often record the same workout twice. Overlapping
  sessions are merged into one bout, which counts once at the longest active
  duration any recording reports. Days with no workout are 0, since that's a
  real rest day.

## Results

Personal results aren't committed. Run the script to see them; it prints:
- how many days had a workout, and average exercise minutes per day
- deep and REM minutes after workout days vs after rest days
- the correlation (Pearson, Spearman, p-value, n) between exercise minutes and
  the following night's deep and REM sleep

## Caveats

- **Only recorded workouts count.** Active days without a logged session
  (a long walk, moving house) read as rest days.
- **Workout timing isn't separated.** A late-evening strength session may
  affect sleep differently from a morning walk.
- **Watch-estimated stages,** as in [`sunrise`](../sunrise/): useful for trends,
  not as absolute numbers.

## Outputs

`build/sleep/exercise/`: `days.csv` (one row per day) and `sleep-vs-exercise`
in light and dark versions.
