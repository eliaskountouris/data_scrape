# Sleep vs sunrise — does the light outside change my deep and REM sleep?

```bash
python -m common.health auth            # once
python projects/sleep/sunrise/run.py                       # San Francisco, deep + REM
python projects/sleep/sunrise/run.py --start 2026-08-01
python projects/sleep/sunrise/run.py --stages deep rem light
python projects/sleep/sunrise/run.py --lat <lat> --lon <lon> --place <name>
```

The default window is the last 180 nights. Every chart and statistic is
produced once per stage in `--stages`. Deep sleep is always purple and REM
always light blue (`viz.stage_color`).

## Data

- **Sleep:** your own Google Health `sleep` sessions (Fitbit), fetched by
  `common.health.GoogleHealth` and collapsed to one row per night by
  `common.health.nightly`.
  - Each night is dated by the **morning you woke up**. That's also the only
    way the API lets you filter sleep, and it's the right date to pair with a
    sunrise.
  - Naps are dropped. On a night with two main sleeps, the longer one counts.
  - Nights recorded without stages (a loose band) have no deep-sleep figure.
    They're left blank rather than counted as zero.
- **Sun and weather:** that morning's sunrise, day length, sunshine and
  overnight low at `--lat/--lon` (default San Francisco), from Open-Meteo via
  `common.weather.OpenMeteoDaily`.

## What gets compared

Each stage, both in minutes and as a share of time asleep, against:

| driver | why |
|---|---|
| `sunrise_hour` | the question as asked |
| `daylight_h` | day length, the seasonal signal minus the clock shifts |
| `wake_after_sunrise_min` | whether you sleep through first light or wake before it |
| `bed_hour` | the main confounder (see below) |
| `temp_min_c` | bedroom temperature is a known deep-sleep factor |

## The average-night model

`common.health.StageModel` is my average night for a stage: for each minute
after falling asleep, the share of past nights I was in that stage at that
minute. Wherever more nights than not were in the stage (the 50% threshold),
it predicts the stage.

Time zero is sleep onset, the first non-awake stage. Only main sleeps with
stage data count, and minutes that fewer than 10 nights reached are never
predicted, so a few lie-ins can't define hour nine.

Its accuracy is scored with 5-fold cross-validation, so no night is predicted
by a model that saw it. The script prints, for each stage:
- the predicted windows (hours after falling asleep) and their peak share
- how many predicted minutes were right (precision)
- how many actual minutes it caught (recall)
- minute-level accuracy against always guessing "not in the stage"

**What to expect.** Deep sleep usually comes in regular windows early in the
night, so it's the easier stage to predict. REM's first period tends to be
regular, but later REM periods drift from night to night. They show up as
broad humps on `rem-model` that may never reach 50%, in which case the model
predicts only the first one. That isn't a bug: at those minutes REM is less
likely than not. To predict more REM, lower the threshold
(`StageModel("rem", threshold=0.35)`), at the cost of more wrong predictions.

## Results

Personal results aren't committed. Run the script to see them; it prints each
stage's correlations with every driver above, and the model scores.

## Caveats to keep in mind

- **Everything here drifts with the calendar.** Sunrise, day length,
  temperature and your schedule all change with the season, so any two of
  them will correlate. Look at `bed_hour` first: if late sunrises go with late
  bedtimes, the sunrise effect may just be a bedtime effect.
- **Daylight saving time jumps sunrise by an hour overnight** (Nov 1 2026, for
  example) while the light itself barely changes. `daylight_h` doesn't have
  that jump, so compare the two.
- **One person, one location.** If you travelled, those nights get the wrong
  sunrise. Trim the date range around trips.
- **Fitbit's stages are estimates** from heart rate and movement, not EEG.
  They're useful for trends within one person and unreliable as absolute
  numbers.

## Outputs

`build/sleep/sunrise/`:
- `nights.csv`, one row per night. It holds personal health data and lives in
  the gitignored `build/`.
- One folder per stage (`deep/`, `rem/`), each holding the same five charts,
  in light and dark versions:
  - `<stage>-timeline`: days across, time of day running up from midnight to
    noon. Grey bars are whole sleep sessions, the stage's stretches are drawn on
    top, and the yellow line is sunrise.
  - `<stage>-predicted`: the same, plus pink bars where the average-night model
    expected the stage but it didn't happen. That model is fitted on all
    nights, so a night slightly influences its own expectation; the scores
    above are the cross-validated ones.
  - `<stage>-model`: the average-night curve with the predicted windows shaded.
  - `<stage>-vs-sunrise`: one point per night, minutes in the stage against
    sunrise time.
  - `<stage>-over-time`: the stage's 7-night mean and sunrise across the
    season.
