# Sleep stages against my recent bedtime and wake-up time

```bash
python -m common.health auth                         # once
python projects/sleep/average_bedtime/run.py         # deep + REM, last 180 days
python projects/sleep/average_bedtime/run.py --window 14 --min-nights 7
python projects/sleep/average_bedtime/run.py --windows 1 3 7 11 14 17 21
python projects/sleep/average_bedtime/run.py --stages deep rem light
```

## The charts

One per stage (`deep-timeline`, `rem-timeline`), the same layout as
[`sunrise`](../sunrise/): days across, time of day running up from midnight to noon.
Grey bars are whole sleep sessions and the stage's stretches sit on top (deep
purple, REM light blue).

Two lines, each averaged over the **14 days before** each day:
- **dark blue:** average bedtime, the start of the night's main sleep
- **red:** average wake-up, the end of the night's main sleep

Both come from `common.health.nightly`, in local wall-clock time. The averaging
works the same way for both:
- The day itself is excluded, so each day is compared with the fortnight
  leading up to it, not partly with itself.
- The line only appears once at least 7 of the previous 14 mornings have data.
  Before that, an "average" would rest on two or three nights.
- Every calendar day gets a value, including days with no sleep recorded, as
  long as the window holds 7 mornings.

### Multi-window variant

`deep-timeline-windows` and `rem-timeline-windows` show the same chart with
bedtime and wake-up averaged over **1, 3, 7, 11, 14, 17 and 21 days**, so you
can see how much smoothing each window does:
- **Line styles:** the 1-day and 21-day lines are solid; the ones between are
  dotted.
- **Colours:** blues for bedtime and reds for wake-up, each a gradient by
  window length. In the light chart the longest window is darkest. In the dark
  chart the gradient runs the other way, so the 21-day line is still the
  strongest against the background.
- **Legend:** lists 1 and 21 days, plus one entry for the dotted group, so it
  doesn't grow to 14 entries.

A "1-day average" is simply the previous night's time, so that line is the raw
day-to-day noise the longer windows smooth away. The 14-day window needs 7
nights, as above; every other window needs half its length in nights (rounded
up) before it's drawn. `--windows` sets the list. Clock-change labels are off
on this variant, because the 1-day line jumps by more than half an hour most
nights.

The lines are computed by `common.stats.trailing_mean`, and the chart is drawn
by `viz.sleep.stage_timeline`; both are reusable.

## Results

Personal results aren't committed. Run the script to see them; it prints, for
bedtime and wake-up:
- the average over every night in the range
- the range the 14-day average moves through
- its latest value

The charts show how those averages move over the period and where each night's
deep and REM sleep fell relative to them.

## Outputs

`build/sleep/average_bedtime/`:
- `sleep_times.csv`, with each day's bedtime and wake-up and their averages for every window.
- `deep-timeline` and `rem-timeline`, in light and dark versions.
- `deep-timeline-windows` and `rem-timeline-windows`, the multi-window
  variant, in light and dark versions.
