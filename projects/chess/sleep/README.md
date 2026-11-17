# Chess and sleep: do I win more after a longer night, or earlier in the day?

```bash
python projects/chess/sleep/run.py                          # last 180 days
python projects/chess/sleep/run.py --start 2026-08-01 --speeds blitz bullet
python projects/chess/sleep/run.py --rated --awake-bin 3
```

## The charts

Both have win rate up the side, with a draw counted as half a win, and a
dashed trend line **weighted by games**. A point built on one loss lands at
0%, and without weighting a handful of those would outweigh a point built on
ten games. Weighting by games makes the line the same as a fit through every
game, which is also how the correlation in the footer is computed (each game
scores 1, ½ or 0).

- **`win-rate-vs-sleep`:** hours asleep the night before (main sleep, from
  `common.health.nightly`) across. One point per night, sized by the games
  played after waking from it.
- **`win-rate-vs-hours-awake`:** hours between waking up and the start of the
  game across. One point per `--awake-bin` hours (default 2), sized by games.
  This measures tiredness directly: a session running from 10 p.m. to 1 a.m.
  spreads over 15–17 hours awake instead of being one point.

## Which night is "the night before"?

Games are matched to the **last main sleep that ended before the game
started**, not by calendar date. Late-night games therefore count against the
right night: a game at 1 a.m. on the 4th was played on the sleep you woke from
on the morning of the 3rd, about 17 hours earlier, because you haven't slept
since.

**Matching is done in UTC.** Lichess records game times in UTC. The sleep data
has UTC times too, alongside the local offset the watch used. The watch follows
your phone's time zone, so on a trip to the East Coast its local times move 3
hours while Lichess's don't. Comparing in UTC keeps the match right across
travel and clock changes. Hours awake are real elapsed hours, so a night when
the clocks go back is an hour longer, as it actually was.

Left out:
- **Games more than `--max-awake` hours after waking** (default 24). That
  usually means sleep wasn't recorded, and pairing the game with a stale night
  would be wrong.
- **Games from before sleep tracking started.** They have no night to pair
  with.
- **Games played during a wake-up in the middle of a recorded sleep**, such as
  a quick game during a short wake-up before dozing off again. There's no single "night before" or "time since waking" for
  those. The script prints how many there were.

## Results

Personal results aren't committed. Run the script to see them; it prints:
- games in the range and how many fell after a recorded night
- overall win rate
- win rate after nights of under 6, 6–7, 7–8 and 8+ hours
- win rate by hours awake, in `--awake-bin` steps
- the per-game correlation (Pearson, Spearman, p-value, n) of game score with
  hours asleep, and with hours awake

## Caveats

- **Games cluster.** Several games in one late session share one night, and
  tilt within a session can swamp any sleep effect. The per-game p-value
  treats games as independent, which overstates how sure it is.
- **Opponents are matched to your rating,** so over time win rate drifts back
  towards 50% whatever you do. A better or worse night shows up as a short-term
  swing at best.
- **Time of day is confounded.** Hours awake tracks the clock (late in your
  day is late in everyone's), and the opponents online at 1 a.m. aren't the
  ones online at 6 p.m.

## Outputs

`build/chess/sleep/`, for each of `win-rate-vs-sleep` and
`win-rate-vs-hours-awake`:
- a CSV with one row per point: hours asleep (or hours awake, the middle of
  the bin), games, wins, draws, losses, win rate
- the chart, in light and dark versions
