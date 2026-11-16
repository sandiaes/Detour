# Privacy

What Detour keeps, where, for how long, and how to delete it. Written for the owner, who is also its
only user (ADR 004 addendum: the owner and one other person at most). Last reviewed 2026-11-15
(Phase 9). The threat model is in [`security.md`](security.md); backups in [`backups.md`](backups.md).

## 1. In one paragraph

Detour has no accounts. The app registers an anonymous **installation** and keeps its token in the
phone's secure storage. Trips, plans, your own places and stays are stored on the backend (Supabase,
schema `app`) under that installation. **Documents (tickets, bookings, insurance) never leave the
phone** unless you put them in an export file yourself. The app talks only to the Detour backend and
the map tile host; searches that need an outside service (Photon, Wikidata, Commons, the routing
server) are made by the backend, without your installation or trip.

## 2. What is stored where

| Data | Where | Who can read it | How long |
|---|---|---|---|
| Installation token | Phone, secure storage (Android Keystore) | The app | Until uninstall |
| Trips, days, stops, times, your own places, stays, visited marks | Backend database (Supabase Free, EU North), schema `app` | Anyone holding your token; the owner of the Supabase project | Until you delete the trip; your own places until deleted (see 5) |
| A copy of what the app last read (trip list, plans) | Phone, SQLite `detour-cache.db`, table `cache` | The app | Replaced on each read; cleared if the installation changes |
| Documents: files and their titles, links, dates, notes | Phone, the app's private files and table `trip_document` | The app | Until you delete them or the trip, or uninstall |
| Links to your photo albums; a cover picture chosen from the phone (a copy) | Phone, table `trip_extra` and the app's private `covers/` folder (ADR 031) | The app; the album itself stays in Google Photos under its own sharing | Until you remove them or the trip, or uninstall |
| Export files (`.detour`) | Wherever you send them (share sheet) | Whoever gets the file | Your choice |
| Request logs | Render (the API host) | The owner of the Render account | Render's log retention |
| Provider usage counters | Backend, `app.provider_usage` | Owner | Kept (a row a provider a day) |
| Daily backup of `app` (when Actions runs) | GitHub Actions artifact | Collaborators of the private repository | 30 days |

**Not collected:** no name, email, phone number, contacts, location, advertising identifier,
analytics or crash reporting. The APK asks for no permission beyond the internet: the location and
"draw over other apps" permissions that libraries declare are removed from the build (Phase 9).

## 3. Documents stay on this phone (ADR 023)

- They are copied into the app's private storage and are **never uploaded**.
- **Uninstalling the app deletes them**, and so does deleting their trip. Android's automatic cloud
  backup is switched off for Detour (Phase 9), so they are not in a Google backup either.
- The only way to keep them across a reinstall or a new phone is **"Back up all trips" with
  documents** (More) or **Export trip** with documents. The `.detour` file is a plain zip:
  **the documents in it are not encrypted** (ADR 028). Keep the file somewhere private, and delete
  copies you no longer need.

## 4. What outside services see

| Service | Called by | What it receives |
|---|---|---|
| OpenFreeMap (tiles) | The app | Map tile requests for the area on screen, the phone's IP address |
| Photon (search) | The backend | The words you search and a point to bias the search; never your installation or trip |
| FOSSGIS Valhalla (travel times) | The backend | Pairs of coordinates of stops; no names, installation or trip |
| Wikidata, Commons, Wikipedia (names, photos) | The backend | Identifiers of public places and photo files |
| Render, Supabase, GitHub | Host the backend, database, builds and backups | Everything stored there (section 2) |

The backend's requests carry an identifying User-Agent that names the project, as the providers ask.

## 5. Deleting

| To delete | How | What remains |
|---|---|---|
| A trip | Trip menu, Settings, Delete trip (confirmation) | Its documents and their files, its album links and its cover picture are deleted on the phone; on the server its plans, stops, stays and visits go. Your own places used by it stay (they belong to the installation) |
| A document | The document, Delete (confirmation) | Nothing |
| Everything on the phone | Uninstall Detour | The server data stays, but nothing can reach it any more (the token is gone) |
| Everything on the server | No button. In Supabase's SQL editor, with the "Installation" identifier from Settings, run `DELETE FROM app.trip WHERE installation_id = '<id>';` then `DELETE FROM app.installation WHERE id = '<id>';` (in that order: a stop still using one of your places blocks the second statement; tried on a scratch database in Phase 9) | Backups made before, for up to 30 days |

The "Installation" identifier is shown in Settings. A reinstalled app is a new installation: its old
trips cannot be reached from the phone, only restored from an export file.

## 6. Licences of cached provider data

Imported and cached data keeps its licence, and the app shows the credits: OpenStreetMap (ODbL),
GeoNames (CC BY 4.0), photos from Wikimedia Commons with author and licence on each photo and in
"Image credits", travel times from the FOSSGIS server (cached in `geo.travel_time`). Export files carry
your own trips and stops as snapshots (name and point), which is your data; they carry no photos.
They do carry the links to your photo albums (ADR 031): anyone with a shared album's link can open
the album, so treat the file like the link.
