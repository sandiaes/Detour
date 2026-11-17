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
| Computed travel times are walking or driving only; some are straight-line estimates, labelled. A train, bus or ferry is entered by hand as a transport leg, with the length the user knows (or "time not entered") | FOSSGIS server limits; no public-transport routing | ADR 004, ADR 013, ADR 032 |
| Without a car, Optimize walks every computed leg, however long; the preview names the walks over 2 km | Owner decision of 2026-11-16 | ADR 032 |
| Add a place's suggested days (recalculation) cannot plan a day that has a transport leg; it names the day, and the user chooses the day and time | Not built in the first step | ADR 032 |
| Photos only where Wikidata or Wikipedia has a free photo; otherwise an illustration | Licence rules | ADR 022 |
| Names are never translated; a romanized name says so | Honest data | ADR 025 |

## Features not built

| Not built | Status |
|---|---|
| **Public transport routing** | Not built: legs are entered by hand (ADR 032). Phase 10 (Transitous or nothing) is not started |
| Suggested transit time for a leg | Not built; manual legs only (ADR 032) |
| **Weather** | After the MVP; needs an ADR (D6) |
| **Sync between phones, accounts, sharing** | Parked (D5); a trip moves between phones as a `.detour` file (ADR 028) |
| **Offline maps** | Not in the MVP; the map needs a connection, the day list works from the saved copy |
| **Map** tab | A flat world map of the cities of your trips (been and going); it needs the map host, so it is blank offline |
| Your own photos **inside** Detour (by day, place or on the map) | Not built: a trip links its Google Photos albums, which open in Google Photos; Google no longer lets apps read albums they did not create (ADR 031) |
| A cover chosen from the phone on another phone | Not carried by the trip file; the destination photo comes back (ADR 031) |
| Notes, a trip summary, taking a photo of a document with the camera | Shown as not built where they would go (the Add sheet, a place's details, Add document) |
| Saved places, travel preferences, archive (hide) a trip | Dropped by the owner (ADR 021, decision 104); not planned |
| iPhone | Phase 11, on the owner's Mac ([`ios-readiness.md`](ios-readiness.md)) |
| Editing while offline | The saved copy is read-only; changes need a connection (ADR 015) |

## Your data

| Limitation | What to do |
|---|---|
| **Documents live on the phone only** and are deleted by an uninstall | "Back up all trips" with documents ([`backups.md`](backups.md)) |
| Export files are not encrypted | Keep them private ([`privacy.md`](privacy.md)) |
| A reinstall is a new installation: old trips are not visible | Import the backup file |
| The database has no backups of its own (Supabase Free) | The daily "Back up app data" workflow, when Actions runs |
| Trip files made before 2026-11-16 (version 1) carry no stays, transport legs or Car choice | An import of such a file has a car and no stays; files exported now (version 2) carry all three (ADR 032) |

## Hosting

| Limitation | Effect |
|---|---|
| Render free: sleeps after 15 idle minutes | An UptimeRobot monitor pings every 5 minutes; if it is missing or a check fails the first request takes about a minute ("Waking the server"). It uses 744 of the 750 free hours: no second Free web service in the workspace |
| Supabase Free: may pause after low activity over 7 days | "The database is paused…": unpause it in the Supabase dashboard; the UptimeRobot monitor and the daily backup keep it active |
| GitHub Actions: free in the public repository, but a schedule is switched off after 60 days without a commit | Re-enable "Back up app data" on its Actions page after a quiet two months |
| Signed with the public debug key until the owner adds a key | [`android-release.md`](android-release.md), section 5 |
