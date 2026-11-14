# ADR 028 — Trip export and import as a file

- **Status:** **Proposed** on 2026-11-14, at the owner's request. Documentation only: nothing is
  built. It is the **second** manager feature of ADR 026, section 6 (item 25), after destinations
  outside the imported regions (ADR 027) and before Optimize (ADR 029). The owner confirms or
  changes the points in "Owner decisions".
- **Date:** 2026-11-14
- **Related:** [`026-trip-manager-first.md`](026-trip-manager-first.md),
  [`027-destinations-outside-imported-regions.md`](027-destinations-outside-imported-regions.md),
  [`023-trip-documents-on-the-device.md`](023-trip-documents.md),
  [`006-past-trips-archive.md`](006-past-trips-archive.md),
  [`010-phase-1-foundation-choices.md`](010-phase-1-monorepo-and-deployment.md),
  [`../data-model.md`](../data-model.md)

## Context

Detour has no accounts. An installation is anonymous and identified by a token kept in the phone's
secure store (D5, ADR 010). If the app is reinstalled or the phone is replaced, the new installation
cannot reach the old one's trips, so the trip history, which is now the point of the app (ADR 026),
is lost. Trip documents are worse off: they live only on the phone (ADR 023), so the server cannot
even back them up. ADR 026 item 25 therefore asks for a way to **take a trip out of the app as a
file and bring it back**, with no accounts.

What already exists and is reused:

- Every stop of a trip already carries a **snapshot** (name, point, times, length); a destination
  snapshot exists for every trip (ADR 006, ADR 027); the past-trip archive keeps its own day record
  (`app.trip_visit`, ADR 026 item 19).
- A **manual plan** (`profile = manual`) needs no recalculation and accepts any user place
  (ADR 021 amendment).
- Documents are files in the app's private storage with a record in the phone's SQLite database
  (ADR 023).
- The system share sheet and file picker are cross-platform Expo modules; no map tile or backend
  host is involved.

This is a new feature (CLAUDE.md rule 3). It adds no provider and no language model.

## Decision

### 1. What the file is

1. **One file with the extension `.detour`.** It is a zip archive holding `trip.json` (the trip) and,
   when the user asks, a `documents/` folder with the document files and `documents.json` (their
   records). A zip is used because documents are binary and can be large; the JSON stays readable
   with any zip tool, so the user is never locked in.
2. **`trip.json` carries `format: "detour-trip"`, `format_version: 1`, the export date and the
   app's version.** An import refuses a higher `format_version` than it knows, with a message that
   asks the user to update the app. Version 1 is never changed in place; a new shape gets a new
   number and an import of the old ones.
3. **What a trip file holds** (everything the user made or kept, nothing from our data):
   - the trip: title, destination snapshot (kind, name, point, country, provider reference as in
     ADR 027), length, start date, status (active or past) and, for a past trip, its archive date;
   - the chosen itinerary only (the other proposals are not exported): days with date and base city
     name and point, and for each stop its position, kind (sight, restaurant, café, own place),
     name, point, start time, length, whether the length is the user's, and whether it is locked;
   - the multi-city stops (name, point, days; ADR 024);
   - for a past trip, the visit record with the visited marks;
   - the user's display-name overrides as the names already shown (the snapshot is the truth);
   - for each document, if included: title, kind, link (trip, day, place or journey, by name and
     day), date, note, file name and type.
4. **What it does not hold:** proposals other than the chosen plan, change sets and versions,
   travel times, cover photos and their credits, reasons, the installation or token, or any `geo`
   identifier. Travel times are not data to carry: they are re-labelled as estimates on import and
   are routed again only if the user changes the order (ADR 013 rules). Cover photos are looked up
   again by the usual chain; a trip imported without one shows its illustration.

### 2. How the app produces it

5. **The server assembles `trip.json`; the phone adds the documents and the zip.**
   `GET /v1/trips/{id}/export` returns the trip as JSON in the shape of item 3 (authenticated as
   any trip read; an installation can export only its own trips). It makes no third-party call. The
   app then writes the zip with the documents it holds on the phone and hands it to the system
   share sheet (messages, mail, Drive, "save to files", a computer). **Nothing is uploaded by
   Detour**: the destination of the file is the user's choice.
6. **Where it is offered:** "Export trip" in a trip's menu (one trip) and **"Back up all trips"**
   under More (every trip in one file; the file holds `trips: [...]`). A past trip exports like any
   other, with its archive.
7. **Documents are optional, shown with their size.** The export sheet has a switch "Include
   documents (14 MB)". The sheet says plainly that the file then holds tickets, booking references
   and similar papers **unencrypted**, and that whoever receives the file can read them. It does
   not encrypt: a password the user forgets would defeat the purpose, and a key kept in the app
   would not survive a reinstall.

### 3. How the app brings it back

8. **`POST /v1/trips/import`** takes the contents of `trip.json` and **always creates a new trip**
   (new identifiers, a copy; never a merge, never an overwrite of an existing trip). The file may be
   imported again, on another phone or after a reinstall, and each import is its own copy. The
   response gives the new trip's identifier so the app can attach the documents to it.
9. **Everything comes back as the user's own data.** The destination becomes a `place` snapshot
   (ADR 027) if its provider reference no longer matches our data, and a city or area trip if its
   `geonames:` or `area:` reference still resolves to an available imported region (checked, not
   assumed). Each stop becomes a user place plus an item of a **manual** plan with its recorded
   time and length; it can be replaced by an imported sight again only when the user adds one.
   A trip with a manual plan has the normal manual-trip actions; it cannot be recalculated, as for
   any empty trip. Past trips come back as past, with their visit record.
10. **Validation before anything is written:** the file is parsed and checked as a whole, and an
    invalid or oversized one writes nothing. Limits: 50 MB for the file, 10 MB per document (as
    ADR 023), the existing per-installation limits (100 trips, 500 user places, 40 items a day),
    names up to 200 characters, points inside the world's range, dates and times well formed,
    document types from the app's list. Unknown fields are ignored; a missing required one rejects
    the file with the reason in words. `trip.json` is never executed or used as a path; document
    file names are replaced by generated names inside the app's private storage.
11. **Documents are attached after the trip exists.** The app writes each file into its private
    storage and records it against the new trip and the same link (day, place or journey, resolved
    by day and name; a link that no longer resolves falls back to the day, then to the trip). If
    writing a document fails, the trip stays, and the app lists the documents that were not
    restored.
12. **The import screen** opens from More ("Import a trip") or by opening a `.detour` file with the
    app. It shows what the file holds (trips, days, places, documents) before the user confirms.

### 4. Privacy, limits and what this is not

13. **The file is the user's own.** The backend sees `trip.json` only in the import call, from the
    user's installation, and does not log it or keep it beyond the rows it creates (no body is
    logged, as for every call).
14. **No account, no cloud sync, no sharing service.** Passing a file to a friend works, and
    imports as their own copy; Detour does not host, link or live-sync anything.
15. **Not a backup of the app's cache:** the read cache on the phone is rebuilt from the server and
    is not exported.

### 5. Dependencies

16. **Three small dependencies in the mobile app, all cross-platform:** `expo-sharing` (share a
    file), `expo-document-picker` (choose a file to import) and `fflate` (zip, MIT, pure
    JavaScript, no native code). The first two are Expo SDK modules added through their config
    plugins; no native project is edited and nothing is Android-only. `expo-file-system` is already
    used.

### 6. Build order (each step ends green: ruff, mypy, pytest, typecheck, lint, jest)

1. **Format and backend:** the `trip.json` models and a version constant; `GET /v1/trips/{id}/export`
   and the bulk variant; `POST /v1/trips/import` with validation and the limits; OpenAPI export and
   generated client. Round trip tested against synthetic trips: empty, planned, multi-city, place
   trip and past trip, all with the same stops, times and lengths after import.
2. **App, trip only:** export sheet, zip writer and share (no documents yet), import screen, file
   picker, preview and result.
3. **App, documents:** the switch with its size, files in the zip, restoring documents and links,
   the list of what could not be restored.
4. **Back up all trips and open-with** (the file type handler in the Expo config).
5. **Docs in the same change:** data model (the file format), architecture, design, brief, KPIs if
   affected, `app-plan.md`, CLAUDE.md.

## Owner decisions

| # | Question | Recommendation |
|---|---|---|
| 1 | A `.detour` zip file with `trip.json` and optional documents? | Yes (items 1 to 3). |
| 2 | Always import as a new copy, never merge or overwrite? | Yes (item 8). A re-import on the same phone gives a second copy, and the user deletes the one they do not want. |
| 3 | Imported stops become your own places in a manual plan, so an imported suggested plan can no longer be recalculated? | Yes (item 9): the file must work without our data and after a re-import changed identifiers. |
| 4 | Include documents only on request, with their size and a plain warning that they are unencrypted? | Yes, with the switch on by default so a reinstall does not lose them; encryption is not built (item 7). |
| 5 | Also "Back up all trips" in one file, not only one trip at a time? | Yes (item 6). |
| 6 | Add `expo-sharing`, `expo-document-picker` and `fflate` (item 16)? | Yes. |
| 7 | Leave out proposals other than the chosen plan, travel times and cover photos (item 4)? | Yes: they are rebuilt or not worth carrying. |

## Alternatives

| Alternative | Why not |
|---|---|
| Accounts and server-side sync | Out of scope: it needs sign-in, email, privacy duties and storage the free hosts do not offer (ADR 005, D5). A file gives the same safety without any of it. |
| Upload the export to our Supabase Storage and give a code | Personal papers would sit on a free-tier host with no accounts to protect them; a code is a bearer secret (ADR 023 already rules this out). |
| Export only `trip.json`, with no documents | Documents are the part that cannot be rebuilt, and only the phone holds them. |
| Encrypt the file with a password | A forgotten password defeats a backup, and a stored key does not survive a reinstall. Left out until the owner asks. |
| Keep imported stops as references into `geo` | The identifiers change on every re-import; a trip imported from a file must not depend on them. |
| Merge by trip identifier on import | Can silently overwrite edits made after the export; a copy is always safe. |
| One JSON file with documents as base64 | Grows by a third and is slow to parse on a phone. |

## Consequences

- A reinstall or a new phone no longer loses the history, documents included, with no account.
- Imported trips are manual: they show and keep everything the user had but do not offer
  "Suggest itineraries" again for the same trip.
- The file holds personal papers when documents are included; the app says so and the user decides
  where the file goes.
- A published file format is a promise: version 1 must keep importing in later versions.
- Three dependencies are added to the app; the API gains three endpoints and no migration (the
  import writes the tables that exist).
