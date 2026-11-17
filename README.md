# data_scrape

A toolkit for scraping public datasets and visualizing them, grown one weekly
project at a time.

```
common/           the scraping library
  paths.py          the one place output locations are defined
  cache.py          on-disk cache for downloaded artifacts
  http.py           polite retrying HTTP client
  schema.py         TableSchema: a dataset's column contract
  providers.py      Provider / ProviderRegistry / DataFacade dispatch
  sources/base.py   Source base class: download -> parse -> parquet
  periods.py        "YYYY-MM" month keys and when a month is safe to cache
  stats.py          correlations reported with n and a p-value
  flights/          flight data behind one interface (see below)
  weather/          weather + sunrise/sunset for any coordinate (Open-Meteo)
  health/           your own Google Health data (OAuth), sleep helpers, stage model
  lichess/          a player's Lichess games and rating history
viz/              the visualization library (theme, matplotlib charts, manim)
projects/         one folder per investigation, grouped by area
  flights/          the weekly flight projects
  sleep/            the sleep projects, sharing shared.py
  chess/            Lichess projects (games against sleep)
tests/            unit tests for the logic that fails silently
build/            everything generated (gitignored)
  cache/            raw downloads + parsed parquet
  <project>/        that project's tables and charts
  media/            rendered manim output
```

Nothing outside `common/paths.py` hardcodes an output path, so the whole
generated tree is one `.gitignore` line and a clean rebuild is `rm -rf build/`.
Paths are absolute, so a script writes to the same place regardless of the
directory it was invoked from. `$SCRAPE_BUILD` relocates the root.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'          # add ',manim' for animations, ',html' for scraping HTML
```

## Design

**`common/`** — a `Source` subclass declares only where raw bytes come from
(`_download`) and how to tidy them (`_parse`). The base class handles the polite
HTTP session (retries, exponential backoff, rate limiting), the on-disk cache,
and a parquet layer so parsing happens exactly once. Re-running a scrape is free
and offline. Generic machinery sits at the top level; per-dataset helpers go in
a subpackage like `common/flights/`.

**`viz/`** — one validated palette in `theme.py`, consumed by role rather than
by hex, so light and dark stay in sync. `render()` draws a figure once and
saves both modes. The manim scenes pull from the same palette, so an animation
and a static chart of the same data are the same chart.

House rules, applied by `render()` to every chart so no script has to remember
them:
- **No title or subtitle.** The axes, legend and source line explain the chart.
- **Legend entries capitalise every word** (`Asleep (Any Stage)`). Acronyms
  keep their case.
- **Signed bottom left** with the author and the date it was generated
  (`Elias Kountouris 2026/11/17`). `$SCRAPE_AUTHOR` overrides the name.
- **Time runs forward** on every axis: left to right, or bottom to top.
- **The plot area is centred** in the image: the narrower side is padded
  until the margins either side of the axes match (`charts.centered_bbox`).

**`projects/`** — one folder per investigation, holding the integration script
that wires `common` and `viz` together plus a writeup of what it found.
Investigations are grouped by area (`projects/flights/`, `projects/sleep/`, `projects/chess/`),
and `build/` mirrors the same layout. Glue shared by one area's scripts lives
in that area's `shared.py`; anything reusable beyond the area gets promoted
into `common/` or `viz/`.

## Using the toolkit from your own scripts

After `pip install -e .`, any script anywhere on the machine can import these.
Each is a plain function or class that takes and returns DataFrames.

**Data**

| import | what it gives you |
|---|---|
| `common.weather.OpenMeteoDaily().load_range(loc, start, end)` | daily weather, sunrise, sunset, day length for any coordinate |
| `common.weather.OpenMeteoHourly().load_range(loc, start, end)` | hourly weather with an `is_day` flag |
| `common.health.GoogleHealth().load_range(type, start, end)` | any Google Health data type (`steps`, `sleep`, `heart-rate`...) |
| `common.health.nightly(sleep)` | one row per night: bed/wake time (local and UTC), minutes in each stage |
| `common.health.stage_table(sleep)` / `stage_segments(sleep, "deep")` | every stage stretch, or just one stage's |
| `common.health.daily_exercise(exercise, start, end)` / `exercise_bouts(exercise)` | exercise minutes per day, or each distinct workout, with double-recorded sessions merged |
| `common.lichess.Lichess().load_games(start, end, user=None)` | every game a player started in the range, from their side of the board (result, ratings, opening, moves, clocks, accuracy) |
| `common.lichess.Lichess().rating_history(user=None)` | one row per day a rating changed, per time control |
| `common.health.StageModel("deep").fit(sleep)` | average-night model of any stage: `predict_proba`, `windows`, `missed`, cross-validated `evaluate` |
| `common.flights.FlightData()` / `FareData()` | US flight on-time and fare records |
| `common.stats.correlate(df, x, y)` | Pearson, Spearman, p-value and n in one result |
| `common.stats.trailing_mean(series, days=14, min_periods=7)` | per day, the mean of the previous N days (current day excluded) |

**Charts** (`from viz import charts, render`)

| function | draws |
|---|---|
| `render(draw, out_stem)` | runs your `draw(fig, theme)` in light and dark, applies the house rules, saves PNGs |
| `charts.dual_axis_lines(ax, theme, left=[...], right=[...])` | lines over dates on two y axes (e.g. minutes and hours), one shared legend |
| `viz.sleep.stage_timeline(ax, theme, stage, segments, sessions, lines=..., missed=...)` | a sleep-stage timeline straight from `common.health` tables, stage colours applied |
| `charts.day_timeline(...)` | days across, time of day up: rounded bars per event, muted bars behind, extra bar layers, reference lines |
| `charts.scatter`, `line_curve`, `hbar_ranking`, `diverging_hbar`, `dumbbell` | the standard forms |
| `charts.rounded_bar`, `hours_since`, `clock_axis`, `axes_aspect` | the pieces `day_timeline` is built from |
| `charts.titles(fig, ax, theme, ..., source=...)` | the source line |

A complete example:

```python
from common.health import GoogleHealth, stage_segments
from common.weather import Location, OpenMeteoDaily
from viz import charts, render

sleep = GoogleHealth().load_range("sleep", "2026-10-01", "2026-11-16")
rem = stage_segments(sleep, "rem")
sun = OpenMeteoDaily().load_range(Location(37.7749, -122.4194, "SF"), "2026-10-01", "2026-11-16")

def draw(fig, theme):
    ax = fig.subplots()
    charts.day_timeline(
        ax, theme, rem["night"],
        charts.hours_since(rem["start_local"], rem["night"]),
        charts.hours_since(rem["end_local"], rem["night"]),
        bar_label="rem sleep",
        lines=[("sunrise", sun["date"], charts.hours_since(sun["sunrise"], sun["date"]), None)],
    )
    charts.titles(fig, ax, theme, "REM sleep", source="Source: Google Health API")

render(draw, "rem-timeline")
```

There are also command-line tools for quick pulls:
`python -m common.weather daily <lat> <lon> <start> <end> [--csv out.csv]` and
`python -m common.health pull <type> <start> <end>` and
`python -m common.lichess games <start> <end> [--user name]`.

## Adding a source

```python
from common.sources.base import Source

class MySource(Source):
    name = "mysource"                  # -> build/cache/mysource/

    def _download(self, key):
        return self.fetcher.download(URL.format(key=key), name=f"raw/{key}.csv")

    def _parse(self, raw):
        return pd.read_csv(raw).rename(columns=...)
```

`MySource().load("2025-01")` then downloads once, parses once, and reads parquet
forever after.

A source that can be asked about a period still in progress overrides
`_is_final(key)`: open periods are re-fetched every load and never written to
parquet, so a half-finished month can't get frozen into the cache.

## Weather, sunrise and sunset

```python
from common.weather import Location, OpenMeteoDaily, OpenMeteoHourly

nyc = Location(40.7128, -74.0060, "NYC")
days  = OpenMeteoDaily().load_range(nyc, "2025-01-01", "2025-12-31")
hours = OpenMeteoHourly().load_range([nyc, (51.5, -0.13)], "2025-06-01", "2025-06-07")
```

Daily rows hold `sunrise`/`sunset` (local wall clock, plus `*_utc`),
`daylight_h`, `sunshine_h`, temperatures, precipitation, wind and a readable
`weather` label. Hourly rows add `is_day`. Units are in the column names;
`DailyWeatherSchema.describe()` lists them. During polar night or polar day,
`sunrise` and `sunset` are `NaT`.

Data comes from [Open-Meteo](https://open-meteo.com/) (free, no key, CC BY 4.0,
so credit "Weather data by Open-Meteo.com" on published charts). Months that
ended a week or more ago come from the ERA5 archive (1940 onwards) and are
cached. More recent months come from the forecast endpoint and are re-fetched
on every load; they reach up to 16 days ahead, and those future days are
forecasts.

## Google Health

Your own Fitbit / Pixel Watch data through the
[Google Health API](https://developers.google.com/health), which replaced the
Fitbit Web API in November 2026. It needs a one-time sign-in:

1. `pip install -e '.[health]'`
2. In Google Cloud console: create a project, enable the **Google Health API**,
   set up the OAuth consent screen with yourself as a test user, then create an
   OAuth client of type **Desktop app**.
3. Save its JSON as `~/.config/data_scrape/google_client_secret.json` (or set
   `$GOOGLE_HEALTH_CLIENT_SECRETS`).
4. `python -m common.health auth`. This opens a browser and saves a refresh
   token beside the client secret, outside `build/` so a clean rebuild doesn't
   sign you out.

```python
from common.health import GoogleHealth

gh = GoogleHealth()
steps = gh.load_range("steps", "2026-01-01", "2026-03-31")
sleep = gh.load_range("sleep", "2026-03-01", "2026-03-31")
hr    = gh.load_range("heart-rate", "2026-03-01", "2026-03-07")
```

Or from the shell: `python -m common.health pull steps 2026-01-01 2026-01-31`.

**Sleep helpers** turn raw `sleep` sessions into tidy tables: `nightly()` gives
one row per night, `stage_table()` gives every stage stretch, and
`stage_segments(sleep, "deep")` gives one stage's stretches. **`StageModel`**
fits an average night for any stage: the share of nights in that stage at each
minute after falling asleep. It predicts the stage wherever that share is 50%
or more, and its `evaluate()` method is cross-validated by night.

Any API data type works, in kebab case (`daily-resting-heart-rate`,
`oxygen-saturation`, ...). Rows get time columns that depend on the type:
interval types (steps, sleep) get `start_time`/`end_time` in UTC plus
`start_local`/`end_local`; sample types (heart rate, weight) get `time` and
`time_local`; daily types get `date`. Value fields are flattened to snake_case,
and nested lists such as sleep stages are kept as JSON strings. Data is cached
by month under `build/cache/google_health/`. The current month is re-fetched
for 3 days after it ends, to pick up late device syncs.

## Lichess

`common.lichess.Lichess` reads a player's games from the
[Lichess API](https://lichess.org/api). Games are public, so it works without a
token for any username. With your own token it also knows who "you" are (so
`user` can be left out), exports your games about three times faster and
includes computer-analysis accuracy.

1. Create a token at https://lichess.org/account/oauth/token. It needs no scopes.
2. Save it, outside the repo:
   `install -m 600 /dev/stdin ~/.config/data_scrape/lichess_token`, paste it,
   then Ctrl-D. Or set `$LICHESS_TOKEN`.

```python
from common.lichess import Lichess, local_time

li = Lichess()
games = li.load_games("2026-01-01", "2026-03-31")             # your games
games["hour"] = local_time(games["played_at"], "America/Los_Angeles").dt.hour
ratings = li.rating_history()                                  # date, perf, rating
```

Each game row is seen from the player's side: `color`, `result`
(win/loss/draw) and `my_*`/`opp_*` columns for name, rating, rating change and,
for analysed games, accuracy, average centipawn loss and mistake counts. It
also carries the time control, opening (ECO, name), the moves in SAN, clock
times per ply (JSON) and the full PGN. Aborted games are dropped unless you pass
`include_unplayed=True`.

Times are UTC, and months are UTC months. Finished months are cached for good
under `build/cache/lichess/`; the current month is re-fetched on every load.

## Getting flight data

Two datasets, one interface. Ask a facade for periods and airports; it works out
which providers can serve them, validates each against a schema, and returns one
frame:

```python
from common.flights import FlightData, FareData

flights = FlightData().load(["2025-01"], airports=["ATL", "YYZ"])   # on-time, monthly
fares   = FareData().load(["2025Q1"],   airports=["ATL", "YYZ"])    # prices, quarterly

print(FlightData().coverage(["ATL", "YYZ"], flights))
# ATL: bts_ontime
# YYZ: NO PROVIDER

FareData(provider_names=["db1b_market"])            # or pin specific providers
```

Period strings differ because the upstream feeds do — on-time data is monthly,
the fare survey quarterly. Everything else about the two interfaces is identical.

The machinery is generic (`common/providers.py`, `common/schema.py`); each
dataset binds three class attributes to it:

| | |
|---|---|
| `TableSchema` | a dataset's column contract. `FlightSchema` and `FareSchema` subclass it; required columns are enforced on load, optional ones backfilled |
| `Provider` | ABC one upstream source implements: `name`, `coverage`, `load_records(periods)`. `FlightProvider` / `FareProvider` narrow it |
| `ProviderRegistry` | `Mapping` of name → provider class; providers self-register with `@registry.register` |
| `DataFacade` | what callers use — routes, validates, concatenates. `FlightData` / `FareData` |
| `Coverage` | which provider served each airport; `str()` renders the routing report |

Three things this buys:

- **Analysis never learns where a row came from.** `build_turnarounds` works the
  same on any source, because every provider is validated against
  `FlightSchema` before it reaches the analysis layer.
- **Gaps are loud.** An airport nobody covers is warned about by name, quoting
  what the registered providers *do* cover, instead of vanishing into a filter.
- **Contract violations fail early.** A provider that forgets `name` or
  `coverage` raises at class-definition time; one missing a required column
  raises `SchemaError` on load, not as a `KeyError` three modules later.

`load()` deliberately returns each provider's **complete** frame rather than
rows filtered to `airports` — chaining an aircraft's flights needs its whole
day, including legs that never touch the airports of interest. `airports`
selects providers, not rows.

### Adding a provider

```python
from common.flights import FlightProvider, flight_registry

@flight_registry.register
class NavCanadaOnTime(FlightProvider):
    name = "navcanada"
    coverage = "Canadian airports"

    def might_cover(self, airport):        # optional cheap prefilter
        return airport.startswith("Y")

    def load_records(self, periods):
        return ...                         # a frame matching FlightSchema
```

Add its module to the registry's `builtin_modules` and every existing script
picks it up — no caller changes. `FlightSchema.describe()` prints the columns to
target. Intermediate bases that only narrow the contract declare
`class X(Provider, abstract=True)` to opt out of the `name`/`coverage` check.

### Current coverage

| dataset | provider | covers |
|---|---|---|
| on-time | `bts_ontime` | US domestic segments on DOT-reporting carriers |
| fares | `db1b_market` | US domestic itinerary markets, 10% ticket sample |

No non-US airport is served by either — Canadian and European equivalents have
no free flight-level feed, so `YYZ` and friends need a paid provider added
behind this interface.

## Projects

Grouped by area. Projects in one area share data and code: the sleep projects
share `projects/sleep/shared.py` (home location, date-range arguments, data
loading), and the flight weeks share `common.flights`.

### [`flights/`](projects/flights/)

| | |
|---|---|
| [`week0_delays`](projects/flights/week0_delays/) | Do aircraft that land on time still depart late? Delay propagation across turnarounds at US airports. |
| [`week1_prices`](projects/flights/week1_prices/) | How expensive is each airport to fly out of? Dollars per mile, corrected for route length. |
| [`week2_delay_vs_price`](projects/flights/week2_delay_vs_price/) | How much departure delay actually reaches the passenger, and does it track price? |

### [`sleep/`](projects/sleep/)

| | |
|---|---|
| [`sunrise`](projects/sleep/sunrise/) | Does sunrise change my deep and REM sleep? Sleep stages against San Francisco sunrise, plus an average-night model of each stage. |
| [`exercise`](projects/sleep/exercise/) | Does exercise change that night's deep and REM sleep? |
| [`average_bedtime`](projects/sleep/average_bedtime/) | Deep and REM timelines against my average bedtime and wake-up time, over 14 days or a range of windows. |

### [`chess/`](projects/chess/)

| | |
|---|---|
| [`sleep`](projects/chess/sleep/) | Do I win more after a longer night? Lichess win rate against hours asleep the night before, and against hours since waking, with late-night games matched to the right night. |
