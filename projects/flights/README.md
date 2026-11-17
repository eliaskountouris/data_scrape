# Flights

The weekly flight investigations, all built on `common.flights` (US DOT / BTS
on-time records and the DB1B fare survey).

| project | question |
|---|---|
| [`week0_delays/`](week0_delays/) | Do aircraft that land on time still depart late? |
| [`week1_prices/`](week1_prices/) | How expensive is each airport to fly out of, corrected for route length? |
| [`week2_delay_vs_price/`](week2_delay_vs_price/) | How much departure delay reaches the passenger, and does it track price? |

Outputs go to `build/flights/<project>/`. The raw downloads are cached once
under `build/cache/` and shared by all three.
