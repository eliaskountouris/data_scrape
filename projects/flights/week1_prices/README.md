# Week 1 — how expensive is each airport to fly out of?

```bash
python projects/flights/week1_prices/run.py --quarters 2025Q1
python projects/flights/week1_prices/run.py --quarters 2024Q3 2024Q4 --direction either
```

## Data

US DOT / BTS **DB1B Origin & Destination Survey** — a 10% random sample of all
US airline tickets, published quarterly, public domain, no API key. Each row is
a group of tickets for one origin-destination market with the fare paid and the
distance covered. Fetched by `common.flights.DB1BMarket`.

Two properties shape the code:

- The raw quarter is **~1.8 GB of CSV (7.3M rows)**. It is read in chunks and
  aggregated on the way in to market × carrier × coupons × bulk-flag, which
  collapses to ~195k rows without losing any passenger-weighted average.
- **`passengers` is a sampling weight, not a row count.** Every average is
  weighted by it.

**US domestic markets only**, same as the on-time feed — no non-US airport can
be analysed from this source.

## The measurement problem

The obvious shorthand — average dollars per mile out of an airport — is mostly
a measure of *route length*, not price level. Fares have a large fixed
component, so cents per mile falls steeply with distance:

| trip distance | dollars per mile | mean fare |
|---|---|---|
| under 250 mi | $0.771 | $146 |
| 250–500 | $0.454 | $169 |
| 500–750 | $0.301 | $187 |
| 750–1000 | $0.213 | $187 |
| 1000–1500 | $0.177 | $211 |
| 1500–2000 | $0.153 | $263 |
| 2000–3000 | $0.126 | $304 |
| 3000+ | $0.104 | $397 |

A 7.4× spread. An airport whose network is short-haul heavy looks expensive
even when every one of its fares is unremarkable.

So the run reports two numbers:

`dollars_per_mile`
: The raw shorthand, passenger-weighted. Easy to explain, but reflects the
  airport's distance mix as much as its pricing.

`price_index`
: The same fares compared against what the national market charges for trips of
  the same length. 1.00 is exactly average; 1.15 means passengers pay 15% more
  than comparable-distance trips cost elsewhere. **This is the number to rank
  airports by.**

Cleaning before either: bulk fares excluded (DOT's own guidance — negotiated
and opaque tickets whose recorded price is not what a passenger paid), markets
under 100 miles dropped (the mile denominator is too small to mean anything),
and the top and bottom 0.1% of dollars-per-mile trimmed as keying errors.

## What 2025 Q1 shows

103 airports above 20,000 sampled passengers.

**Most expensive**

| airport | $/mi | median trip | price index |
|---|---|---|---|
| STT (St Thomas) | 0.186 | 2,319 mi | **1.34** |
| BHM (Birmingham) | 0.328 | 1,201 mi | 1.26 |
| LIT (Little Rock) | 0.303 | 1,352 mi | 1.23 |
| EYW (Key West) | 0.241 | 1,538 mi | 1.23 |
| XNA (NW Arkansas) | 0.292 | 1,222 mi | 1.20 |
| DFW | 0.272 | 1,525 mi | 1.13 |

**Cheapest**

| airport | $/mi | median trip | price index |
|---|---|---|---|
| PIE (St Pete–Clearwater) | 0.089 | 912 mi | **0.41** |
| SFB (Sanford) | 0.097 | 914 mi | 0.43 |
| PGD (Punta Gorda) | 0.093 | 1,063 mi | 0.48 |
| AZA (Phoenix–Mesa) | 0.100 | 1,082 mi | 0.49 |
| LGB (Long Beach) | 0.251 | 2,143 mi | 0.77 |
| MDW (Chicago Midway) | 0.204 | 1,300 mi | 0.79 |

Three findings:

1. **The cheap end is one airline's strategy, not geography.** PIE, SFB, PGD
   and AZA are all Allegiant bases, all with a ~100% nonstop share, all at
   0.41–0.49. They are secondary fields near a major metro, served point-to-point
   by an ultra-low-cost carrier — roughly half the national rate for the trip
   length.

2. **The expensive end is thin competition.** Mid-size cities with one dominant
   carrier and few nonstops — BHM, LIT, XNA, MSN, GSP — cluster at 1.18–1.26
   with nonstop shares near 0.35–0.46. DFW is the exception that proves it: a
   huge airport at 1.13 with a 0.90 nonstop share, which is the fortress-hub
   premium rather than a lack of flights.

3. **The correction matters, but not uniformly.** The two measures correlate at
   0.66, yet controlling for distance moves the median airport **17 places out
   of 103**. The extreme case is STT: 93rd on raw dollars per mile, 1st on the
   index — long overwater routes make its per-mile figure look modest while its
   fares are the highest in the country for the distance. BUR moves the other
   way, 6th to 86th.

## Outputs

`build/flights/week1_prices/` — `airport_fare_rates.csv`,
`national_baseline.csv`, and three charts in light and dark:

- `price-index-ranking` — most and least expensive airports, diverging from 1.00
- `distance-curve` — the national dollars-per-mile curve, i.e. why the index exists
- `raw-vs-adjusted` — the two measures against each other, biggest movers labelled

## Caveats

- **A 10% sample.** Airports below the 20,000-passenger floor are dropped;
  those just above it still carry wide error bars.
- **Q1 is a season.** Leisure markets (EYW, STT, Florida) price very differently
  across the year. Run several quarters before drawing conclusions about them.
- **Fares are what was paid, not what was advertised.** DB1B has no fare-class
  or ancillary detail, so a $79 ultra-low-cost ticket plus $120 of bag and seat
  fees counts as $79. That biases the cheap end downward — the Allegiant bases
  are genuinely cheap on base fare, but the gap to the network average is
  narrower than 0.41 suggests.
- **The index compares an airport against the national average including
  itself.** With 103 airports that is negligible; it would not be for a small
  band.
- Distance bands are fixed-width in miles, so within-band mix still leaks a
  little into the index.
