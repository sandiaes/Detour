# Manual check: largest matrix the FOSSGIS Valhalla server accepts

One-time, by hand, in a normal browser (ADR 004, open item before Phase 3). Not code, not a test.

Each link asks for a walking-time matrix between N points in Florence (N x N cells). Click them
**in order, one at a time, waiting at least 10 seconds between clicks** (the server limits
requests per second). Stop at the first one that fails.

| Test | Cells | Link |
|---|---:|---|
| 2 x 2 | 4 | [open](https://valhalla1.openstreetmap.de/sources_to_targets?json=%7B%22sources%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%5D%2C%22targets%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%5D%2C%22costing%22%3A%22pedestrian%22%7D) |
| 10 x 10 | 100 | [open](https://valhalla1.openstreetmap.de/sources_to_targets?json=%7B%22sources%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.235%7D%5D%2C%22targets%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.235%7D%5D%2C%22costing%22%3A%22pedestrian%22%7D) |
| 25 x 25 | 625 | [open](https://valhalla1.openstreetmap.de/sources_to_targets?json=%7B%22sources%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2506%7D%5D%2C%22targets%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2506%7D%5D%2C%22costing%22%3A%22pedestrian%22%7D) |
| 50 x 50 | 2500 | [open](https://valhalla1.openstreetmap.de/sources_to_targets?json=%7B%22sources%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2558%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2558%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2558%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2558%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2558%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.261%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.261%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.261%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.261%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.261%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2662%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2662%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2662%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2662%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2662%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2714%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2714%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2714%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2714%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2714%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2766%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2766%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2766%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2766%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2766%7D%5D%2C%22targets%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2506%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2558%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2558%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2558%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2558%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2558%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.261%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.261%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.261%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.261%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.261%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2662%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2662%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2662%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2662%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2662%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2714%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2714%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2714%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2714%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2714%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2766%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2766%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2766%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2766%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2766%7D%5D%2C%22costing%22%3A%22pedestrian%22%7D) |

## How to read the result

- **Works:** the page shows JSON starting with `{"sources_to_targets":[[{"distance":...,"time":...`.
- **Refused:** JSON with `"error_code"` and `"error"` (for example a message about the number
  of locations or location pairs, or `429` / "too many requests"). Copy the whole message.
- **Page does not load or is blocked:** your work network may block the host. Note that and stop.

## What to send back

For each test: worked or not, roughly how many seconds it took, and the full error text if any.
Do not retry a refused test repeatedly. Do not share anything else from the page.

Why this matters: it shows whether a 50-place itinerary needs one request or many (the server
allows about one request per second per user). Date of the check: record it in ADR 004.

## Result of the first check (2026-11-12, by the owner)

| Test | Result |
|---|---|
| 2 x 2 | Worked, immediate |
| 10 x 10 (100 cells) | Worked, about 1 second |
| 25 x 25 (625 cells) | Refused: `error_code` 150, "Exceeded max locations: 100.000000" |
| 50 x 50 (2500 cells) | Refused: same error |

The error says "locations", but 25 + 25 locations is only 50, and 10 x 10 (100 cells) passed. The
simplest reading is a limit of **100 matrix cells** (sources x targets) per request, but this is
an inference. The two follow-up links separate the readings: if the server limits cells, the first
works and the second is refused.

## Optional follow-up (same rules: one at a time, 10 seconds apart)

| Test | What it shows | Link |
|---|---|---|
| 20 sources x 5 targets | 100 cells, 25 locations | [open](https://valhalla1.openstreetmap.de/sources_to_targets?json=%7B%22sources%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2454%7D%5D%2C%22targets%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%5D%2C%22costing%22%3A%22pedestrian%22%7D) |
| 11 sources x 10 targets | 110 cells, 21 locations | [open](https://valhalla1.openstreetmap.de/sources_to_targets?json=%7B%22sources%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2402%7D%5D%2C%22targets%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.235%7D%5D%2C%22costing%22%3A%22pedestrian%22%7D) |

## Result of the follow-up (2026-11-12, by the owner)

| Test | Result |
|---|---|
| 20 sources x 5 targets (100 cells, 25 locations) | Worked |
| 11 sources x 10 targets (110 cells, 21 locations) | Refused: `error_code` 150, "Exceeded max locations: 100.000000" |

Conclusion: the limit is **100 cells (sources x targets) per request**, whatever the number of locations.

**Unexplained observation.** The same pair (point 0 to point 1, 0.662 km) took 523 s in the
2 x 2 and 10 x 10 requests and 653 s in the 20 x 5 request. The distance was identical. The
responses named different algorithms (`timedistancematrix`, `costmatrix`) across requests, but the
cause of the 25% difference is not established.

## Distance check between cities (optional, same rules)

Tests whether the server accepts places hundreds of kilometres apart. Points are the centres of
Rome, Florence, Milan, Naples and Venice; the mainland only (no ferries). Click one at a time, 10
seconds apart. Send back worked or not, and the full error text if any.

| Test | Link |
|---|---|
| 5 x 5 cities, driving (25 cells) | [open](https://valhalla1.openstreetmap.de/sources_to_targets?json=%7B%22sources%22%3A%5B%7B%22lat%22%3A41.9028%2C%22lon%22%3A12.4964%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2558%7D%2C%7B%22lat%22%3A45.4642%2C%22lon%22%3A9.19%7D%2C%7B%22lat%22%3A40.8518%2C%22lon%22%3A14.2681%7D%2C%7B%22lat%22%3A45.4408%2C%22lon%22%3A12.3155%7D%5D%2C%22targets%22%3A%5B%7B%22lat%22%3A41.9028%2C%22lon%22%3A12.4964%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2558%7D%2C%7B%22lat%22%3A45.4642%2C%22lon%22%3A9.19%7D%2C%7B%22lat%22%3A40.8518%2C%22lon%22%3A14.2681%7D%2C%7B%22lat%22%3A45.4408%2C%22lon%22%3A12.3155%7D%5D%2C%22costing%22%3A%22auto%22%7D) |
| Rome to Milan only, driving (1 cell, the longest pair) | [open](https://valhalla1.openstreetmap.de/sources_to_targets?json=%7B%22sources%22%3A%5B%7B%22lat%22%3A41.9028%2C%22lon%22%3A12.4964%7D%5D%2C%22targets%22%3A%5B%7B%22lat%22%3A45.4642%2C%22lon%22%3A9.19%7D%5D%2C%22costing%22%3A%22auto%22%7D) |

## Result of the distance check (2026-11-12, by the owner)

Both tests (5 x 5 cities, and Rome to Milan alone) were refused with `error_code` 154:
"Path distance exceeds the max distance limit: 150000 meters". So a **matrix request is limited to
150 km** between places (in addition to the 100-cell limit).

## Single-route check (optional, same rules)

Tests whether the separate single-route request accepts long distances. Most of the response is
directions text; send only worked or not, plus `trip.summary.length` (km) and `trip.summary.time`
(seconds), or the full error text.

| Test | Link |
|---|---|
| Single driving route, Florence to Rome | [open](https://valhalla1.openstreetmap.de/route?json=%7B%22locations%22%3A%5B%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2558%7D%2C%7B%22lat%22%3A41.9028%2C%22lon%22%3A12.4964%7D%5D%2C%22costing%22%3A%22auto%22%7D) |
| Single driving route, Rome to Milan | [open](https://valhalla1.openstreetmap.de/route?json=%7B%22locations%22%3A%5B%7B%22lat%22%3A41.9028%2C%22lon%22%3A12.4964%7D%2C%7B%22lat%22%3A45.4642%2C%22lon%22%3A9.19%7D%5D%2C%22costing%22%3A%22auto%22%7D) |
