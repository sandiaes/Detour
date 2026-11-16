# Security

Threat model and controls for Detour as it is used now: one owner, a sideloaded Android APK
(ADR 008), a public API on a Render free web service, a Supabase Free database (ADR 005), no accounts
(app plan D5). Last reviewed 2026-11-15 (Phase 9). Privacy is in [`privacy.md`](privacy.md).

## 1. What is worth protecting

| Asset | Why |
|---|---|
| The owner's trips, stops, stays and visited history (`app` schema) | Personal, and the only copy apart from backups |
| Documents on the phone | Personal papers (tickets, insurance) |
| The shared daily budgets for Photon, FOSSGIS and Wikimedia | Spending them stops search, routing and photos for the owner, and abuses public community servers |
| The database (500 MB, connections) and Render's free hours | Exhausting them takes the service down |
| Secrets: database URL, token secret, Supabase service key | Full access to the data |

## 2. Threats and controls

### 2.1 Keys in the app binary

**There are none.** The only build-time value is the backend's public URL
(`EXPO_PUBLIC_DETOUR_API_URL`); the map style URL and credits come from `GET /v1/config`. Provider
calls are made by the backend, so no Photon, Wikimedia, routing or Supabase key exists in the app.
Checked in Phase 9: no key-shaped string in `apps/mobile/src` or `packages/shared/src`, and the
repository's `.env.example` holds placeholders only. Anything in an APK can be read by whoever has
the file, so this must stay true: a provider that needs a key goes behind the backend (CLAUDE.md).

### 2.2 Unauthorised use of the public API

The API is on the internet without accounts. Anyone who learns its address can register an
installation (`POST /v1/installations`) and use every endpoint for their own installation.

| Control | Detail |
|---|---|
| Installation token | `dt1.<id>.<HMAC-SHA256>` signed with `DETOUR_TOKEN_SECRET` (32+ characters, production refuses to start without it). It only proves "the same installation as before"; each installation sees only its own trips (tested: `test_trips_need_a_token_and_belong_to_one_installation`) |
| Request limits (Phase 9) | Per installation: 300 a minute, burst 150. Registrations: 20 an hour for the whole service, burst 10. Photos and cover previews: 600 a minute shared (the image view sends no token). Over a limit: `429` with `Retry-After`, code `rate_limited`. In memory, per process (one process on Render); a restart refills them. Settings `DETOUR_RATE_LIMIT_*`, `DETOUR_REGISTRATIONS_*`, `DETOUR_IMAGE_REQUESTS_*` |
| Size limits | 100 trips per installation, 5 plans per trip; imports refused above the file limits (ADR 028); Optimize refuses more than 200 stops |
| Provider budgets | Daily call budgets in `app.provider_usage` (Photon 300, FOSSGIS 1,500, Wikimedia 3,000), reserved before each call; a circuit breaker after failures |

**Residual risk:** an attacker who registers 20 installations an hour can still create data and use
part of the provider budgets each day. Acceptable for a personal service; if abuse is ever seen in the
logs, lower the registration limit or put the API behind a secret header the owner's build sends (a
build-time value, not a key to a third party).

### 2.3 Location permission

The app never asks for the phone's location: no screen uses it. MapLibre's and Expo's libraries
declare location and "draw over other apps" permissions; Phase 9 removes them from the APK with
`android.blockedPermissions` in `app.json` (checked with `npx expo config --type introspect`). A map
pin is placed by hand; coordinates are typed or come from a search result.

### 2.4 Documents on the phone

Stored in the app's private storage (other apps cannot read them on an unrooted phone). Not
uploaded. Android cloud backup is off (`allowBackup: false`, Phase 9). **Lost on uninstall** and
when their trip is deleted. The app says so where documents are added.

### 2.5 `.detour` export files (ADR 028)

A zip of `trip.json` and, if chosen, the documents, **unencrypted**. Anyone who gets the file can read
the trips and documents in it. The app says so before exporting. Import treats every file as untrusted:
at most 50 MB per file, a JSON entry at most 8 MB unpacked, a document at most 10 MB, a strict schema
(unknown fields refused), one transaction (a bad file writes nothing), always imported as a new copy.

### 2.6 Cached provider data and its licence

`geo` holds imported OpenStreetMap and GeoNames data and cached travel times, names and photos with
their source and licence records (data model). It holds no user data. Photos are served by the API
from Supabase Storage with their credits.

### 2.7 Log leakage

API logs are JSON lines with the method, **path without the query string**, status and duration; no
headers, bodies or tokens. Secrets and connection strings are redacted from any log field and from
exception text (`logging.py`, tested). HTTP client libraries (`httpx`, `httpcore`, and since Phase 9
`httpx2`, `httpcore2`) are kept at WARNING because they log full URLs. The app has no `console.log`
in production code. Workflows never echo the database URL; it is passed as an environment variable.

### 2.8 The APK signing key

Until the owner adds the signing secrets, the APK is signed with the **public React Native debug key**,
which anyone can use: a file signed with it could be installed over Detour. Phase 9 adds an opt-in
project key (the "Create signing key" workflow, the four `DETOUR_KEY*` secrets, and
`plugins/withReleaseSigning.js`). Switching keys needs one uninstall; see
[`android-release.md`](android-release.md). Install Detour only from the repository's own Actions
artifacts.

### 2.9 Secrets

Database URL and token secret live in Render's environment; the import and backup workflows read
`DETOUR_IMPORT_DATABASE_URL` from GitHub secrets; the Supabase service key is on Render only. None is
in the repository. Rotating `DETOUR_TOKEN_SECRET` makes every installation register again and **lose
access to its trips** (they stay in the database under the old installation): do not rotate it
without exporting first.

### 2.9a Codes that add a phone (ADR 034)

A phone joins a person with a **link code** (8 letters from a 32-letter alphabet without 0, O, 1
and I: 40 bits; one use; 10 minutes; a new code cancels the unused one) or the **recovery code** (26
letters: 130 bits; until replaced). Only an HMAC-SHA256 of each code, keyed with
`DETOUR_TOKEN_SECRET`, is stored, so a copy of the database does not allow guessing offline.
`POST /v1/installations/join` is limited to 5 tries per phone (then one every 2 minutes) and 20 an
hour for the whole service (`DETOUR_JOIN_ATTEMPTS_*`), so at most about 480 guesses a day against a
code space of 2^40 with at most one live code per person. A wrong, used or expired code all answer
the same `code_invalid`.

- **A stolen or lost phone:** remove it under More, Your phones from another phone, or use the
  recovery code on a new phone, which signs out every other phone and deletes unused link codes. A
  removed phone's token is refused with 401 `device_removed` within a minute (at once in the process
  that removed it); the phone then starts again as a new, empty person.
- **A phone cannot be taken over by its own codes:** a phone already joined by others cannot move
  to another person (409 `has_other_devices`), so its phones are never left without their trips.
- **Residual risk:** whoever sees the screen of an unlocked phone with Detour can make a link code
  and join a phone of theirs. Treat the app like the phone itself. There is no email fallback: a
  person who loses every phone and the recovery code cannot get the trips back, except from an
  export file.
- **Invite codes** (step 3) link two people so they can share trips: same format, lifetime and
  limits as a link code (they share the `POST /v1/people/link` and `/join` buckets), hashed with
  their own purpose, so an invite code cannot add a phone and a link code cannot link a person.
  A linked person sees only your name and the trips you share with them; only a trip's owner can
  share it, stop sharing it or delete it.
- **Trip files** (step 5): covers chosen from a phone live in a **private** bucket read only by the
  backend with the service key and served to the trip's members through the API (no public or
  signed link leaves the backend). Uploads are decoded and re-encoded with Pillow (at most 10 MB in,
  at most 60 megapixels, a JPEG of at most 1600 px out, no EXIF), so a file that is not a picture,
  and the picture's location, never reach the bucket. All trip files together are capped at
  `DETOUR_TRIP_FILES_BUDGET_BYTES` (250 MB; 409 `storage_full`).
- **Shared documents** (step 6) use the same private bucket and checks of membership. They are kept
  as uploaded (no re-encoding: a ticket's code must stay readable), so the server checks the first
  bytes against the type the phone names (PDF, JPEG, PNG, WebP, GIF, HEIC) and refuses anything else;
  at most 10 MB each. A document's id is chosen by the phone; an id already used on another trip is
  refused. Readable by the Supabase project's owner (encryption at rest only; owner, question 4).
- **Rotating `DETOUR_TOKEN_SECRET`** invalidates every token and every stored code hash (the app
  registers again by itself; recovery codes must be made again).

### 2.10 Deletion of trips and local data

Deleting a trip deletes its plans, stops, stays and visits on the server and its documents on the
phone. Uninstalling deletes everything on the phone. Removing the server data of an installation is a
two-statement SQL step (see [`privacy.md`](privacy.md), section 5).

## 3. The repository is public (2026-11-15, ADR 007 addendum)

- The code, the documents and the whole git history are public. Checked before the switch: no
  secret anywhere in the history. The owner's commit email addresses are in it.
- **Actions logs, run summaries and artifacts are public.** Workflows must never print or upload
  anything secret or personal: the backup is encrypted and its summary carries no counts; the signing
  key goes straight into the secrets; the database URL is passed as an environment variable and never
  echoed; GitHub masks secret values in logs. The APK artifact contains the backend's address, which
  is therefore public: the request limits (section 2.2) are what protects the API.
- **Secrets stay private.** Workflows that use them run on `push`, `schedule` and
  `workflow_dispatch` only; CI has no `pull_request` trigger, so a fork's pull request runs nothing
  with this repository's secrets.
- Recommended settings (GitHub Docs, read 2026-11-15; they appear once the repository is public):
  Settings, sidebar section **Security and quality**, **Advanced Security**: Enable **Secret
  Protection**, then Enable **Push protection** inside it. Settings, **Actions**, **General**,
  "Approval for running fork pull request workflows from contributors": **Require approval for all
  external contributors** (the default is first-time contributors only).

## 4. Supabase notes

The API connects as the database owner through the session pooler; Row Level Security is not used
because no client talks to Supabase directly (the app only calls the Detour API). The Supabase anon
and service keys are therefore not in the app. If anything ever calls Supabase's REST API directly,
RLS must be enabled first.

## 5. Open items for the owner

1. Decide when to switch to the project's own signing key (one uninstall; export first).
2. The providers' contact: the User-Agent links to the repository, which resolves now that it is
   public.
3. Keep the request limits on: the API address is public (in the APK artifact).
