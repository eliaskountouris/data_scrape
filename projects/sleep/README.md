# Sleep

Investigations into my own sleep, from the Google Health API (Fitbit), with
sunrise and weather from Open-Meteo where needed.

| project | question |
|---|---|
| [`sunrise/`](sunrise/) | Does sunrise change my deep and REM sleep? Plus an average-night model of each stage. |
| [`exercise/`](exercise/) | Does exercise change that night's deep and REM sleep? |
| [`average_bedtime/`](average_bedtime/) | Deep and REM timelines against my recent average bedtime and wake-up. |

```bash
python -m common.health auth                    # once (re-run when the token expires)
python projects/sleep/sunrise/run.py
python projects/sleep/exercise/run.py
python projects/sleep/average_bedtime/run.py
```

Every script takes `--start`/`--end` (default: the last 180 days ending
yesterday) and writes to `build/sleep/<project>/`.

## Shared code

[`shared.py`](shared.py) holds what the scripts here have in common: my home
location (San Francisco), the default date window, the shared command-line
options (`--start`, `--end`, `--out`, `--stages`, `--lat/--lon/--place`), and
loading sleep data through one Google Health client.

The reusable analysis and charts live in the toolkit, not here:
- `common.health`: `nightly`, `stage_segments`, `StageModel`, `daily_exercise`
- `common.stats`: `correlate`, `trailing_mean`
- `viz.sleep.stage_timeline`

Conventions across these projects:
- **Dating nights:** a night is dated by the morning I woke up. `exercise/`
  shifts it to the day the night started, so a workout lines up with the
  sleep after it.
- **Stage colours:** deep sleep is always purple and REM always light blue
  (`viz.stage_color`).
