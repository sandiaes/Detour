# Known limitations

What Detour does not do, as of Phase 9 (2026-11-15). Each item says why and where it is decided.
Things that are out of scope for good (booking, payments, hotel availability, flight prices, any
language model) are in the [product brief](product-brief.md), section 8.

## Coverage and data

| Limitation | Why | Where |
|---|---|---|
| **Suggestions only in imported regions: Austria and Italy** (Czechia and Hungary not imported yet) | Sights come from the project's own OpenStreetMap import; other places can be trips, but empty ones | ADR 009, ADR 027 |
| **Japan is not imported**; areas in Japan are planned as single cities | Non-Latin names and rail travel (no public transport) | App plan D2, D4; ADR 016 |
| No opening hours: a place may be closed at the planned time | Out of scope | ADR 003 |
| No prices, budgets or currencies | Owner's decision | ADR 017 |
| No restaurant data in the import; no cuisine or meal type | Restaurants are your own places, through Photon or by hand | ADR 026 |
| Visit lengths are defaults by kind of place | No trustworthy source | Brief, section 7 |
| Travel times are walking or driving only; some are straight-line estimates, labelled | FOSSGIS server limits, no public transport | ADR 004, ADR 013 |
| Photos only where Wikidata or Wikipedia has a free photo; otherwise an illustration | Licence rules | ADR 022 |
| Names are never translated; a romanized name says so | Honest data | ADR 025 |

## Features not built

| Not built | Status |
|---|---|
| **Public transport** | After the MVP, Phase 10 (Transitous or nothing) |
| Suggested transit time for a leg | Not built; manual legs only (ADR 032) |
| **Weather** | After the MVP; needs an ADR (D6) |
| **Sync between phones, accounts, sharing** | Parked (D5); a trip moves between phones as a `.detour` file (ADR 028) |
| **Offline maps** | Not in the MVP; the map needs a connection, the day list works from the saved copy |
| **Explore** tab | Shows "Explore is planned"; needs a product decision and possibly a provider ADR |
| Your own photos **inside** Detour (by day, place or on the map) | Not built: a trip links its Google Photos albums, which open in Google Photos; Google no longer lets apps read albums they did not create (ADR 031) |
| A cover chosen from the phone on another phone | Not carried by the trip file; the destination photo comes back (ADR 031) |
| Saved places, travel preferences, archive (hide) a trip, notes, trip summary | Shown as not built in More or the trip (ADR 021, "Not built") |
| iPhone | Phase 11, on the owner's Mac ([`ios-readiness.md`](ios-readiness.md)) |
| Editing while offline | The saved copy is read-only; changes need a connection (ADR 015) |

## Your data

| Limitation | What to do |
|---|---|
| **Documents live on the phone only** and are deleted by an uninstall | "Back up all trips" with documents ([`backups.md`](backups.md)) |
| Export files are not encrypted | Keep them private ([`privacy.md`](privacy.md)) |
| A reinstall is a new installation: old trips are not visible | Import the backup file |
| The database has no backups of its own (Supabase Free) | The daily "Back up app data" workflow, when Actions runs |
| Stays are not in export files | Add them again after an import (ADR 030) |

## Hosting

| Limitation | Effect |
|---|---|
| Render free: sleeps after 15 idle minutes | An UptimeRobot monitor pings every 5 minutes; if it is missing or a check fails the first request takes about a minute ("Waking the server"). It uses 744 of the 750 free hours: no second Free web service in the workspace |
| Supabase Free: may pause after low activity over 7 days | "The database is paused…": unpause it in the Supabase dashboard; the UptimeRobot monitor and the daily backup keep it active |
| GitHub Actions: free in the public repository, but a schedule is switched off after 60 days without a commit | Re-enable "Back up app data" on its Actions page after a quiet two months |
| Signed with the public debug key until the owner adds a key | [`android-release.md`](android-release.md), section 5 |
