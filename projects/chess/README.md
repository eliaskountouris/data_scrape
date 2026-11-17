# Chess

Investigations into my own Lichess games, through `common.lichess`.

| project | question |
|---|---|
| [`sleep/`](sleep/) | Do I win more after a longer night's sleep, or earlier in my day? |

```bash
python projects/chess/sleep/run.py
```

Needs a Lichess token in `~/.config/data_scrape/lichess_token` (see the root
README). Projects that also use sleep need `python -m common.health auth`.
Output goes to `build/chess/<project>/`.
