# Week 2 — unabsorbed delay vs price

```bash
python projects/flights/week2_delay_vs_price/run.py --months 2025-01 2025-02 2025-03 --quarters 2025Q1
```

Joins the two datasets already in the toolkit: how much departure delay actually
reaches the passenger, against how expensive the airport is to fly out of.

## Unabsorbed delay

A flight that pushes back 30 minutes late and still lands on time cost nobody
anything — the schedule had enough padding to swallow it. A flight that pushes
back 30 late and lands 30 late passed the whole delay through.

For a flight leaving `D` minutes late and arriving `A` minutes late:

| case | unabsorbed |
|---|---|
| `A ≤ 0` — arrived on time or early | 0 |
| `0 < A < D` — partly caught up | `A` |
| `A ≥ D` — no catch-up | `D` |

So **`unabsorbed = clip(A, 0, D)`**, and `absorbed = D − unabsorbed`.

Two deliberate choices:

- **The cap at `D`.** A flight that leaves 10 late and lands 40 late picked up
  30 minutes *en route* — airspace, weather, holding. That is not something the
  origin airport did, so attribution stops at the delay it actually caused.
- **Flights leaving on time contribute 0**, and stay in the denominator. The
  metric is the airport's contribution to passenger lateness *per departure*,
  not per late departure. (The conditional version is reported too, as
  `mean_unabsorbed_given_late_min`.)

Attributed to the **origin**, matching `direction="origin"` in the fare analysis,
so both sides of the join mean "flying out of this airport".

## What 2025 Q1 shows

1.61M flights, 101 airports present in both datasets.

| | |
|---|---|
| mean departure delay | 14.7 min per flight |
| mean unabsorbed | 12.5 min per flight |
| network absorbs | **15.3%** of all departure delay |
| flights leaving 15+ min late that still arrive on time | **20.6%** |

So roughly one late departure in five is rescued by schedule padding, and about
one minute in seven of all departure delay never reaches a passenger.

**Worst absorbers** — EYW 22.5 min, SRQ 20.0, BZN 19.9, SYR 18.9, PBI 18.8,
ALB 18.6, DCA 18.5. Mostly small leisure and short-runway fields; DCA is the
one big airport in the group.

**Best absorbers** — OAK 5.7 min, ANC 6.1, SJC 6.4, LGB 6.4, HNL 7.6, OGG 7.7.
West-coast and Hawaii airports, where long stage lengths give the schedule room
to make time back.

## The relationship with price is weak

| price measure | Pearson | Spearman | p |
|---|---|---|---|
| `price_index` (distance-controlled) | **+0.14** | **+0.27** | 0.005 |
| `dollars_per_mile` (raw) | −0.23 | −0.17 | 0.094 |
| `mean_fare_usd` | −0.06 | −0.00 | 0.987 |

Read carefully:

- Against the honest price measure the relationship is **positive but weak** —
  statistically significant at n=101, but Spearman +0.27 explains about 7% of
  the rank variance. Expensive airports pass through slightly more delay; that
  is a tendency, not a rule, and the scatter is a cloud.
- Against **raw dollars per mile the sign flips negative**, which is an artifact,
  not a finding. The worst absorbers are long-haul leisure airports (EYW, SRQ,
  PBI, BZN) whose long routes make their per-mile fare look low. This is the
  same distance confound `price_index` exists to remove — see
  [week 1](../week1_prices/).
- Against mean fare there is nothing at all.

The airports that break the pattern are the informative ones. PIE and SFB are
among the cheapest airports in the country (index 0.41, 0.43) *and* among the
worst absorbers (16.8, 16.1 min) — ultra-low-cost carriers run thin schedules
with little padding. ANC is mildly expensive (1.11) and the second-best absorber.

## Outputs

`build/flights/week2_delay_vs_price/` — `delay_vs_price.csv` and three charts in light
and dark:

- `unabsorbed-vs-price-index` — the headline scatter, points sized by passengers
- `unabsorbed-vs-dollars-per-mile` — the same data against the raw shorthand, where the sign flips
- `unabsorbed-ranking` — worst absorbers, with the median airport marked

## Caveats

- **Correlation across airports is not a mechanism.** Both price and delay
  absorption are driven by route length, carrier mix and airport size; nothing
  here isolates a causal path, and no control beyond distance is applied.
- **Periods are aligned but not identical.** Fares are surveyed per quarter and
  attached to the whole quarter's flights, so within-quarter timing is lost.
- **Q1 only**, and Q1 is a weather-heavy quarter. Absolute unabsorbed minutes
  will be lower in the autumn.
- Unabsorbed delay says nothing about **cancellations**, which are excluded
  entirely and are a worse outcome than any late arrival.
- Schedule padding is a choice, not a virtue: an airline can absorb delay by
  scheduling longer block times, which shows up here as good absorption and to
  the passenger as a slower flight.
