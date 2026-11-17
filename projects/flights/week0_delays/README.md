# Week 0 — do on-time arrivals still depart late?

```bash
python projects/flights/week0_delays/run.py --months 2025-01 2025-02
python projects/flights/week0_delays/run.py --months 2025-01 --airports all
```

## Data

US DOT / BTS *Marketing Carrier On-Time Performance* — one row per scheduled
domestic flight, public domain, no API key. Roughly 540k flights/month,
published on a ~2 month lag. Fetched by `common.flights.BTSOnTime`.

**US domestic segments only** — 329 airports, all of them American. Non-US
airports (YYZ, LHR, ...) have zero rows even when a US carrier flies there, so
they cannot be analysed from this source. `build_turnarounds` logs a warning
naming any requested airport the feed doesn't cover rather than dropping it
silently.

## Method

A **turnaround** is two consecutive flights by the same tail number where the
first one's destination is the second one's origin. Chaining them makes the
question answerable: an aircraft lands at an airport, and we watch what its next
flight does. Implemented in `common.flights.turnaround`.

Details that matter:

- Flights are ordered by **scheduled departure timestamp**. Actual times in the
  feed are local `HHMM` values that wrap at midnight and can't be sorted.
- The date on a BTS row is the **departure** date, so a red-eye whose scheduled
  arrival clock reads earlier than its departure clock landed the next day.
  Ground time is computed against the corrected arrival.
- Ground time is measured in the turn airport's own local clock — the inbound's
  scheduled arrival and the outbound's scheduled departure are both local to
  that airport, so no timezone conversion is needed.
- Cancelled and diverted flights are dropped; turns longer than 8 hours are
  aircraft parked overnight, not turnarounds.
- "Late" is the DOT definition: 15+ minutes.

## What January 2025 shows

Across 18 large US airports (194,562 turnarounds):

| aircraft landed | departs late | still late on arrival |
|---|---|---|
| **on time** | 10.1% | 11.3% |
| **late** | 59.0% | 52.1% |

Three findings:

1. **An on-time arrival mostly stays on time.** Only ~1 in 10 on-time arrivals
   turns into a late departure, and the late departure usually doesn't survive
   the next leg — a third to a half of those flights recover en route.

2. **Departure delay is overwhelmingly inherited, not generated on the ground.**
   A late inbound is 4.5–8.5× more likely to produce a late departure than an
   on-time one. Airports differ more in this ratio than in their absolute rate:
   LGA and LAS run a clean operation until a late aircraft shows up, at which
   point they have nothing left to absorb it. MIA, DEN and DFW leak more from
   on-time arrivals but degrade less sharply.

3. **Below 30 minutes of scheduled ground time, the schedule itself is the
   delay.** Restricted to on-time arrivals — so nothing is inherited — the
   late-departure rate is flat at ~8% for any turn of 30 minutes or more, then
   climbs monotonically as turns get shorter:

   | scheduled ground | departs late | median departure delay |
   |---|---|---|
   | 30+ min | 8% | −4 min |
   | 25–30 min | 28% | +3 min |
   | 20–25 min | 49% | +14 min |
   | 15–20 min | 58% | +19 min |
   | 10–15 min | 67% | +24 min |
   | under 5 min | 86% | +36 min |

   These sub-30 turns are only ~1% of all turnarounds, but their outcome is
   close to deterministic: the aircraft was never going to make it.

## Outputs

`build/flights/week0_delays/` — `airport_rates.csv`, `ground_time_curve.csv`,
`turnarounds.parquet`, and three charts in light and dark:

- `airport-ranking` — of on-time arrivals, the share departing late, by airport
- `inherited-vs-generated` — that rate against the late-inbound rate
- `ground-time-curve` — late-departure rate vs. scheduled ground time

## Caveats

- Only US domestic flights on reporting carriers; no international legs, so an
  aircraft's chain breaks when it leaves the country — a jet that turns at YYZ
  disappears from the data and reappears on its next US departure.
- Tail numbers are occasionally reused or misreported, which produces a few
  impossible pairings; negative ground times are dropped.
- A month is a season, not a year. January is weather-heavy; re-running on
  February 2025 gives lower absolute rates with the same ratios.
