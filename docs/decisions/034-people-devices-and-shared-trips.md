# ADR 034 — People, devices and shared trips

- **Status:** **Proposed** on 2026-11-16 (owner request: "a user for myself and my girlfriend, and
  to set a trip up with her, or solo"; also shared documents and the other things kept only on the
  phone). **Step 1 (people and devices) is built** (2026-11-16, owner: "Go with codes, start step
  1"), awaiting acceptance; checked by tests only, not on a device; migration `0024` not yet run in
  production. **Step 2 (trip membership) is built** (2026-11-16, owner: "Lets start phase 2"),
  awaiting acceptance, tests only, migration `0025` not yet run in production; no visible change.
  **Step 3 (names, partner links and sharing) is built** (2026-11-16, owner: "go ahead with step
  3"), awaiting acceptance, tests only, migration `0026` not yet run in production.
  **Step 4 (safe edits by two people) is built** (2026-11-16, owner: "step 4 go"), awaiting
  acceptance, tests only, migration `0027` not yet run in production.
  **Step 5 (album links and covers on the server) is built** (2026-11-16, owner: "go with step 5"),
  awaiting acceptance, tests only, migration `0028` not yet run in production; the `trip-files`
  bucket was created by the owner on 2026-11-16 (private). Owner's answers of 2026-11-16 to section 9: questions 2 to 6 answered
  (recorded there and in the decisions); question 1 (codes or a sign-in provider) is still open.
- **Date:** 2026-11-16
- **Changes when accepted:** D5 in `docs/app-plan.md` (anonymous installation, no accounts), the
  product brief's exclusion "user accounts, sharing and multi-device sync", and parts of ADR 023
  (documents on the phone only), ADR 031 (album links and phone cover on the phone only), ADR 010
  decision 3 (stateless tokens) and ADR 033 (`DETOUR_OWNER_INSTALLATION_IDS`).
- **Related:** [`010`](010-phase-1-foundation-choices.md), [`022`](022-destination-and-attraction-photos.md)
  (Supabase Storage), [`023`](023-trip-documents-on-the-device.md), [`028`](028-trip-export-and-import.md),
  [`031`](031-photo-albums-and-phone-covers.md), [`../privacy.md`](../privacy.md),
  [`../security.md`](../security.md), [`../backups.md`](../backups.md)

## Context

Today the unit of identity is the **installation**: a phone registers anonymously and gets a signed
token `dt1.<installation id>.<HMAC>` (ADR 010). Every `app` row hangs off `installation_id`
(`trip`, `user_place`, `place_name_override`, …; about 190 references in `repo/`). Consequences:

- Two people cannot see the same trip. A trip can only be passed along as a `.detour` copy (ADR 028),
  after which the two copies drift apart.
- A new phone or a reinstall is a stranger: the old trips are unreachable except through an export.
- Documents (ADR 023), album links and the phone cover (ADR 031) live in the phone's SQLite and
  files, so even an exported-and-imported trip loses them unless the user chose to put documents in
  the file.

The owner wants **two people** (the owner and their partner), each with their own trips, able to plan
a trip **together or alone**, and to have the shared trip's documents, albums and cover on both
phones. That matches ADR 004's "the owner and one other person at most", so no provider usage rule
changes. The app is still not distributed (ADR 008), and the API is still public on the internet.

Constraints that shape the design:

- **No new provider without an ADR** (CLAUDE.md rule 4). Email sign-in needs an email sender; Google
  sign-in needs a Google Cloud project and a native module (an ADR for each). A design that needs
  neither is preferred.
- **Free hosts** (ADR 005): Render free web service (cold starts, no long-lived connections worth
  relying on), Supabase Free (500 MB database, 1 GB Storage, 5 GB egress; figures from ADR 022, read
  2026-11-14, to be **re-read** before step 5). ADR 022 already budgets up to about 700 MB of the 1 GB
  for Wikimedia photos.
- **The repository is public** (ADR 007 addendum): nothing personal in workflows or logs.
- **Offline matters**: documents are needed at a station or a gate, often without a signal.

## Decision (proposed)

### 1. A person, with devices

1. New table `app.person` (`id`, `display_name` 1 to 40 characters, `created_at`). No email, phone
   number or password: the name is only what the other person sees ("Ana changed day 2").
2. `app.installation` gains `person_id` (not null after the migration) and `revoked_at`. **An
   installation is now a device of a person.** The token format does not change; the API resolves
   the person from the installation and refuses a revoked one (401 `device_removed`). Because the
   token is stateless, this needs one lookup per request: kept in the existing in-process "seen" map
   (`deps.py`) for at most 60 seconds, so a removed device stops within a minute.
3. **The migration gives every existing installation its own person**, so the owner's current phone
   becomes "person 1" with all its trips. Nothing is lost and nothing has to be redone.
4. A fresh install starts as a new, anonymous person, exactly as today (no sign-up screen). The first
   screen of More gains "Your name" (optional, asked once when sharing starts).

### 2. Joining a device to a person: codes, not passwords

No email, no sign-in provider. Three kinds of code, all generated by the backend from a CSPRNG and
stored only as a hash:

| Code | Made by | Typed on | Lifetime | What it does |
|---|---|---|---|---|
| Link code | A phone you already use | Your new or reinstalled phone | One use, 10 minutes | That phone becomes one of yours |
| Recovery code | You, once, kept on paper or in a password manager | A phone, when none of yours is at hand | Until replaced; using it asks you to make a new one | That phone becomes one of yours; your other phones are signed out |
| Invite code | Your phone | Your partner's phone | One use, 10 minutes | Links the two people (once, ever) |

A short code is safe because it expires in minutes, works once, and allows only a few attempts; the
recovery code lives long, so it is long.

5. **Add a device** (More, "Your devices", "Add a phone"): the backend issues a one-time **link code**
   (8 characters from a 31-letter unambiguous alphabet, about 40 bits), valid **10 minutes**, single
   use, shown as text and as a QR code. On the new phone, the first screen offers "I already use
   Detour" and the code; entering it moves that installation to the person. At most 5 attempts per
   installation per 10 minutes and 20 per hour for the service (`abuse.py`), so guessing is hopeless.
   Only a hash of the code is stored.
6. **Recovery code**, for a lost or wiped phone: created on request (More, "Recovery code"), 128 bits
   shown once as 26 characters in groups, to be written down or kept in a password manager. Stored as
   a hash. Entering it on a new phone joins it to the person and **revokes the other devices**
   (a stolen phone stays out). It is not consumed by use, but the app then asks for a new one at
   once, and making a new recovery code invalidates the old one. Without a recovery code and without
   a phone still signed in, the account cannot be recovered (there is no email to fall back on);
   the `.detour` export remains the last resort.
7. **Your devices** lists the person's devices (model name if the app sends it, added, last seen) with
   "Remove". A person always keeps at least one device.

This replaces "a reinstall loses everything" for anyone who saved a recovery code or still has a
second phone; `.detour` export (ADR 028) stays as the offline backup.

### 3. Partners, and who a trip belongs to

8. **A partner link** between two people (`app.person_link`: `person_a`, `person_b`, `created_at`),
   made once: one person shows an **invite code** (same rules as a link code: 8 characters, 10
   minutes, single use, QR), the other enters it under More, "People", "Add someone". Either can
   remove the link; removing it does not remove anyone from trips already shared (section 4 decides
   those). The model allows more than one link, but the app and the limits are written for two
   people (at most 5 links per person).
9. `app.trip.installation_id` becomes **`owner_person_id`** (the person who created it) and a new
   table **`app.trip_member`** (`trip_id`, `person_id`, `role`, `added_at`, `added_by`) holds who can
   see and change the trip. The owner is always a member. **Every trip read and write is authorised
   by membership**, in one place (`repo/trips.py`'s trip lookup), instead of by installation.
10. **Roles: `owner` and `editor` only.** An editor can do everything the owner can except delete
    the trip, remove the owner, or change who is a member. No read-only viewer role (nobody asked for
    one; it would double the tests).
11. **Solo is the default.** A new trip has one member. The new-trip screen gains "Who's going":
    "Just me" (selected) or a linked person's name; the trip menu gains "Share with …" and
    "Stop sharing" for existing trips. A person who has no partner link sees no sharing control.
12. **What each person keeps for themselves** (not shared through a trip):
    - `app.user_place` moves from installation to **person**, but a place used by a shared trip is
      readable by every member of that trip (it is in the plan). A member who adds a place to a
      shared trip creates it under their own person. The 500 limit is per person.
    - `app.place_name_override` (ADR 025) moves to the person: "Edit display name" is personal.
    - The read cache and the "Back up all trips" export stay per phone; export of a shared trip
      exports it as it is, and its import is always a new, solo trip (ADR 028 unchanged).
13. **Leaving and deleting.** "Leave trip" (editor): the trip disappears from that person's list and
    history; nothing in the trip changes. "Delete trip" (owner only): for everyone, after a
    confirmation naming the other members. "Stop sharing" (owner): removes the other members. A
    member removed this way gets nothing back automatically; the owner can offer "Give them a copy",
    which runs the export and import server-side into a solo trip of theirs (same rules as ADR 028).
14. **Past trips and history.** A shared past trip appears in each member's Past tab. Reopening
    (ADR 006) follows the role rules: any member can reopen.
15. **Owner-only actions** (ADR 033's region import and removal): `DETOUR_OWNER_INSTALLATION_IDS`
    becomes `DETOUR_OWNER_PERSON_IDS`, so all the owner's phones qualify. The old variable is read
    as a fallback (mapped to persons) for one release.

### 4. Two people editing the same trip

There is no real-time channel (Render free cold-starts and sleeps; a socket would add a provider or
a host). The design aims for **no silent loss**, not for live collaboration.

16. **Every write to a plan states the version it was made on.** `app.itinerary.version` exists and
    change sets already refuse a stale base (`change_set_stale`). Item edits, adding by day and time
    (`.../days/{n}/items`), transport legs, stays, stops, Optimize and undo gain an `expected_version`
    (body field) or `If-Match` header; a mismatch is **409 `plan_changed`** with the current version.
    Trip-level fields (name, dates, cover, car) get the same with `app.trip.updated_at` as an ETag.
    The app answers a 409 by refetching and saying "Ana changed this plan; your change was not saved.
    Try again." For the two-person case this is rare and always safe.
17. **Who changed what.** `app.itinerary_version` gains `changed_by` (person) and the change's code
    (`item_added`, `item_moved`, `optimized`, …, the codes already used by change sets). The trip
    overview shows one line, "Changed by Ana, 20 minutes ago", for a change made by someone else since
    this person last opened the trip (`app.trip_member.last_seen_version`). No notification, no feed.
18. **Freshness without push.** The app already refetches on focus and on pull-to-refresh. It adds a
    cheap `GET /v1/trips/changes?since=<timestamp>` (trip ids and versions only) called when the app
    comes to the foreground and every 60 seconds while a shared trip is on screen. No push
    notifications (that would be a provider: FCM).
19. **Undo** stays per itinerary and shared: undo restores the previous version whoever made it,
    with the same 409 rule. The cap stays 30 (5 for a past trip).

### 5. What moves off the phone

| Today on the phone only | Proposed | Why |
|---|---|---|
| Album links (`trip_extra`, ADR 031) | **Server**: `app.trip_album` (`trip_id`, `url`, `name`, `added_by`, `position`) | A few hundred bytes; both people need them; nothing to protect beyond the link itself (the screen already warns a shared link opens the album) |
| Cover picture from the phone (`covers/`, ADR 031) | **Server**: resized on the phone to at most 1600 px JPEG (about 200 to 400 kB), stored in a **private** Storage bucket `trip-files`, served only through the API to members | Both people should see the same cover |
| Documents (ADR 023) | **Per document**: a toggle "Upload to the trip" on Add document, **on by default** on every trip, solo or shared (owner, 2026-11-16); off keeps it "Only on this phone" (as now). The toggle can be changed later on the document's screen (upload, or remove the server copy and keep the phone's) | Tickets are often bought by one person and used by both; a new phone gets them back |
| Read cache (`cache`) | Stays on the phone, per person (cleared when the person changes, as today per installation) | It is a cache |
| Export files | Unchanged | Still the offline backup |

Shared documents in detail:

20. **Storage:** the private Supabase Storage bucket `trip-files`, written and read **only by the
    backend** with the service key (the app never talks to Supabase, per the architecture rules).
    Path `trips/<trip id>/<document id>`. Row `app.trip_document` with the fields of ADR 023's record
    (title, kind, link, date, note, file name, type, size, `sha256`, `uploaded_by`, `created_at`).
21. **Endpoints:** `GET/POST/PATCH/DELETE /v1/trips/{id}/documents`, `GET .../documents/{doc}/file`
    (streams the file to members; no public or signed URL leaves the backend, so a leaked link opens
    nothing). Upload is a multipart POST.
22. **Limits:** PDF and images only (as ADR 023); **10 MB a file** (as ADR 028's import limit), and a
    **storage budget of 250 MB for all documents and covers** (`app.provider_usage`-style counter;
    over it, new uploads are refused with "Storage is full; keep this one on the phone"). ADR 022's
    photo budget comes down from 4,000 to 3,000 images (about 450 to 525 MB) so the two fit in 1 GB.
    Usage is shown under More.
23. **Offline:** every shared document of a trip whose dates are within 14 days, or which is open, is
    **downloaded to the phone** into the existing documents folder and marked "Available offline";
    others download when opened. The SQLite `trip_document` table becomes a local copy keyed by the
    server id, plus the phone-only documents.
24. **Encryption:** Supabase encrypts storage at rest; files are served only through the
    membership-checked API over HTTPS. **No end-to-end encryption** in this step: it needs a key per
    trip handed between phones (through the link codes), and a lost key loses every document. It is
    recorded as a later option (section 7). The privacy page says plainly that the owner of the
    Supabase project can read shared documents, and "Only on this phone" remains for anything the
    user does not want on the server.
25. **Moving existing documents:** a trip's Documents tab offers "Share these with the trip" once,
    listing the phone-only documents; nothing is uploaded without that tap.
26. **Backups:** the daily "Back up app data" workflow covers the `app` rows, not the bucket. A
    weekly encrypted archive of the bucket is added to the same workflow (same encryption as today),
    or, if its size is a problem for Actions artifacts, the owner keeps the "Back up all trips with
    documents" export. Decided in step 5.

### 6. API shape (summary)

| Endpoint | Purpose |
|---|---|
| `GET /v1/me`, `PATCH /v1/me` | The person (name), their devices, partner links, recovery code status |
| `POST /v1/me/link-codes`, `POST /v1/installations/link` | Add a device |
| `POST /v1/me/recovery-code`, `POST /v1/installations/recover` | Recovery |
| `DELETE /v1/me/devices/{id}` | Remove a device |
| `POST /v1/me/invite-codes`, `POST /v1/people/link`, `DELETE /v1/people/{id}` | Partner link |
| `GET/POST/DELETE /v1/trips/{id}/members`, `POST /v1/trips/{id}/leave` | Sharing a trip |
| `GET /v1/trips/changes?since=` | Freshness |
| `.../documents`, `.../albums`, `.../cover` | Section 5 |

Every existing endpoint keeps its path; `installation_id` disappears from responses in favour of
`owner` and `members` on `Trip`. OpenAPI and the generated client are regenerated as usual.

## Step 1 as built (2026-11-16)

Differences from the plan above, all to keep step 1 small and leave every existing query as it is:

- **A person's id is the id of its first installation** (no `owner_person_id` yet). The API's
  `Session.installation_id` is now the caller's person (the data owner) and `Session.device_id` the
  phone; every repository query that filters by `installation_id` therefore sees the person's trips
  from any phone. Joining moves the joining phone's trips, places and display-name overrides to the
  person's id (checked against the 100-trip and 500-place limits; refused with 409 `limit_reached`
  otherwise, moving nothing). Step 2 renames the columns.
- **One endpoint for both codes**, `POST /v1/installations/join`, told apart by length (8 or 26
  letters, spaces and hyphens ignored); `GET /v1/me`, `POST /v1/me/link-codes`,
  `POST /v1/me/recovery-code`, `DELETE /v1/me/devices/{id}`. `GET /v1/installations/me` adds
  `person_id` (null when the database is unreachable) and answers 401 `device_removed` for a removed
  phone; the app keys its saved copy by person, so joining clears the old person's copy.
- **No display name yet**: it is only needed once two people share (step 3). Phones are "This
  phone", "Phone 2" …; no device model is sent (it would need `expo-device`).
- **No QR code** (typed codes only) and no "I already use Detour" first screen: More, Your phones
  has "Use a code on this phone".
- `DETOUR_OWNER_INSTALLATION_IDS` keeps its name: it is compared with the caller's person, which is
  the owner's first phone's id, so all of the owner's joined phones qualify. Renaming waits for step 2.
- A removed phone is refused within 60 seconds (the person of a phone is cached that long in each
  process; the process that removed it forgets at once).
- Codes are stored as HMAC-SHA256 with `DETOUR_TOKEN_SECRET`, so rotating the secret also cancels
  link and recovery codes.

Files: migration `0024_people_and_devices.py`; `repo/people.py`, `routers/people.py`,
`models/people.py`, `deps.py` (`resolve_device`, `forget_devices`), `abuse.py` (join limits);
the app's `screens/DevicesScreen.tsx`, `domain/devices.ts`, `api/connect.ts` (`personId`),
`data/DataProvider.tsx`. Tests: `test_people.py`, `test_migration_0024.py`, `test_abuse.py`,
`screens/Devices.test.tsx`.

## Step 2 as built (2026-11-16)

- Migration `0025`: `app.trip.installation_id` is now `owner_person_id`, `app.user_place` and
  `app.place_name_override` have `person_id`, all fks to `app.person`; `app.trip_member` with one
  `owner` per trip, filled for every existing trip, and a trigger that adds the owner when a trip is
  inserted (so imports, the seed and tests need no change).
- The API's `Session.person_id` replaces `installation_id`. Every query that found a trip, plan,
  day, item, change set, stay or visit "of this installation" now asks for membership
  (`EXISTS (SELECT 1 FROM app.trip_member tm WHERE tm.trip_id = t.id AND tm.person_id = :p)`);
  creating counts and stamps the owner; updates rely on the membership check made first.
- `DELETE /v1/trips/{id}` is the owner's only: a member gets 403 `not_trip_owner` (owner, question 2).
- A place on a shared trip is read with the plan (by id), so the partner's restaurant shows for both;
  each person's list of own places stays their own. A display-name override is personal but also
  rewrites the stored names of the trips the person is a member of, which the partner then sees
  (until step 3 decides otherwise).
- Joining a phone (step 1) also moves its memberships; where both people were members of one trip,
  one row stays and the owner role wins.
- `Trip` responses do not show members or role yet (step 3). Tests: `test_trip_members.py`,
  `test_migration_0025.py`.

## Step 3 as built (2026-11-16)

- Migration `0026`: `app.person.display_name`, `app.person_link`, `app.link_code.kind`
  (`device` or `invite`).
- API: `PATCH /v1/me` (name), `GET /v1/me` adds `display_name` and `people`;
  `POST /v1/me/invite-codes`, `POST /v1/people/link` (400 `code_invalid`, 409 `already_linked`,
  `own_invite`, `limit_reached`), `DELETE /v1/people/{id}`; `TripCreate.share_with` ("Who's going",
  409 `not_linked`); `POST /v1/trips/{id}/members` and `DELETE /v1/trips/{id}/members/{person}`
  (leave with your own id; the owner cannot leave, 409 `owner_cannot_leave`; owner-only actions 403
  `not_trip_owner`); `Trip.role` and `Trip.members` (name, role, `you`).
- App: More, People; Who's going; Who's on this trip in trip settings (Share, Stop sharing, Leave;
  Delete only for the owner); "With Ana" on trip cards. Leaving deletes the trip's documents on that
  phone, as deleting does.
- **Not built:** "Give them a copy" (decision 13): the owner can export the trip instead (ADR 028).
  Display-name overrides still rewrite stored names on shared trips (see step 2).
- Tests: `test_sharing.py`, `screens/Sharing.test.tsx`, the Who's going test in
  `CreateTripScreen.test.tsx`.

## Step 4 as built (2026-11-16)

- **Version check:** `If-Match: "<plan version>"` on `POST /v1/itineraries/{id}/days/{n}/items`,
  `PATCH` and `DELETE /v1/items/{id}` and `DELETE /v1/itineraries/{id}`; a different version is
  409 `plan_changed` with `current_version`. The plan row is locked while it is checked, so two
  changes at the same moment are applied one after the other and the second is refused. `PATCH
  /v1/trips/{id}` takes the trip's `updated_at` (409 `trip_changed`). The header is optional: a
  call without it is not checked (older builds, scripts). Change sets, Optimize and undo already
  refuse a stale preview (`change_set_stale`). Stays are separate rows and are not checked.
- **The app** sends the version of the plan it holds with every direct plan change (Add with day
  and time, Edit time and length, lock, remove, transport legs); on `plan_changed` it forgets its
  copy and says "Someone else changed this plan after you opened it…". It does not send the trip's
  `updated_at` yet (selecting a plan would be refused after any other trip change).
- **Who changed it:** migration `0027` adds `app.itinerary.changed_by` and `changed_at` and
  `app.trip.updated_by`, filled by triggers from a transaction setting (`detour.person`) the API
  sets at the start of every transaction. `Itinerary.last_change` (person, name, `you`, time).
  A shared trip's overview shows "Changed by Ana 5 minutes ago" when the last change was someone
  else's (always, not only since you last opened it: simpler, and still true).
- **Freshness:** no `GET /v1/trips/changes` endpoint. A shared trip's overview reads the plan and
  the trips again every 60 seconds and when the app comes back to the foreground.
- Tests: `test_concurrency.py`, `screens/Concurrency.test.tsx`.

## Step 5 as built (2026-11-16)

Supabase's Free plan was **re-read on 2026-11-16** ✅ (<https://supabase.com/pricing>,
<https://supabase.com/docs/guides/storage/management/pricing>,
<https://supabase.com/docs/guides/storage/uploads/file-limits>): "1 GB file storage", "Max file
upload size | 50 MB" ("For Free projects, the limit can't exceed 50 MB"), "5 GB egress" and "5 GB
cached egress", "Free projects are paused after 1 week of inactivity". No date on the pages. Whether
private buckets are available on Free is not stated on these pages; the owner created the private
`trip-files` bucket on the Free project on 2026-11-16 (no public flag, no policies, file size limit
unset, so Supabase's 50 MB applies), which settles it.

- Migration `0028`: `app.trip_album`, `app.trip_file` (kind `cover` now, `document` for step 6) and
  `app.trip_file_orphan` (objects to remove after a change commits).
- API: `GET/POST /v1/trips/{id}/albums`, `PATCH/DELETE .../albums/{album}` (409 `album_exists`,
  `limit_reached`; allowed on past trips); `PUT/GET/DELETE /v1/trips/{id}/own-cover` with the
  picture as base64 in JSON (the app has no binary upload path; a cover is small), re-encoded to a
  JPEG of at most 1600 px without EXIF (no location), 10 MB in at most, a 250 MB budget for all trip
  files (409 `storage_full`), 503 `storage_unavailable` without the bucket; `Trip.own_cover`.
  Members only; a cover change bumps the trip's `updated_at` (so "who changed it" records it).
- Storage: the private `trip-files` bucket through `SupabaseImageStore(private=True)`, read on the
  `authenticated` path with the service key; never a public or signed URL.
- App: album changes go to the server first, then the phone's copy; a cover chosen on the phone is
  shown at once and uploaded; `syncTrip` (on the trips list, the Photos screen and a trip's Photos
  tab, at most every 5 minutes per trip) uploads albums and covers an older build kept only on the
  phone, downloads a cover chosen on another phone and drops one removed elsewhere. The phone's copy
  keeps them visible offline. The wording no longer says "stays on this phone".
- **Not built here:** iPhone HEIC pictures are refused by the server (`not_a_picture`; Pillow reads
  JPEG, PNG and WebP). The phone does not shrink the picture before uploading (it would need a new
  native module); the server does.
- Tests: `test_trip_files.py`, `TripPhotos.test.tsx` (server albums, upload, download),
  `util/base64.test.ts`.

## Build order (each step shippable and tested on its own)

1. **People and devices** (migration: `app.person`, `installation.person_id`, `revoked_at`; one
   person per existing installation). Link codes, recovery code, Your devices. Owner ids by person.
   Visible result: the owner can put Detour on a second phone (or reinstall) and keep everything.
2. **Trip membership** (migration: `owner_person_id`, `app.trip_member` filled with the owner;
   `user_place` and `place_name_override` to person). Every repository query moves from
   installation to membership; a test, like the cross-schema one, fails if a query in `repo/` still
   filters by `installation_id`. No visible change yet.
3. **Partner link and sharing**: invite codes, People screen, "Who's going", Share, Leave, Stop
   sharing, Give them a copy. Visible result: the trip appears on both phones.
4. **Safe concurrent edits**: `expected_version` and ETags everywhere, 409 `plan_changed` in the
   app, `changed_by`, "Changed by …", `/v1/trips/changes`.
5. **Albums and cover on the server** (small; proves the private bucket and streaming).
6. **Shared documents**: table, bucket, upload, offline copies, "Share these with the trip",
   storage budget, ADR 022 budget amendment, backup of the bucket.
7. Documents: `privacy.md`, `security.md` (codes, revocation, the bucket), `backups.md`,
   `data-model.md`, `architecture.md`, `design.md` (People, Devices, Who's going, the sharing badge on
   a trip card), `product-brief.md`, `app-plan.md` D5, CLAUDE.md; E2E flow for linking two
   installations (the E2E seed can create two).

Steps 1 and 2 are the bulk of the risk (every query changes owner); 3 to 6 are mostly additive.

## 7. Alternatives

| Alternative | Why not (now) |
|---|---|
| **Supabase Auth** with email magic links or Google sign-in | A sign-in provider and, for email, a mail sender: each needs an ADR, terms read on the official pages, and for Google a Cloud project and a native module. Brings passwords/emails into the data for two people who can scan a QR code from each other's phone. Remains the upgrade path if Detour ever has more users |
| **Google Sign-In** | Same, plus an Android-specific native dependency (needs its own ADR) |
| **Keep anonymous installations, share a trip by a trip-level code** | Works for one shared trip, but each phone still loses everything on reinstall, and "my trips on my two phones" is not solved |
| **Shared via `.detour` files only** (today) | Two copies that drift; no live trip |
| **End-to-end encrypted documents** | The safest for personal papers, but key management across phones and recovery is the hardest part of the whole plan; a lost key is lost tickets. Can be added later per document without changing the sharing model |
| **Documents stay phone-only, sent between phones by the share sheet** | No server cost, but the partner's copy is not linked to the trip and goes stale |
| **Real-time sync (websockets, Supabase Realtime, CRDTs)** | A new channel on hosts that sleep; overkill for two people who rarely edit the same day at the same minute. The version check guarantees nothing is silently lost |
| **Viewer role** | Not asked for |

## 8. Consequences

- The biggest change since Phase 2 to the `app` schema and to every trip query. Steps 1 and 2 need a
  careful migration test on a copy of production (the backup restore in `backups.md`).
- Privacy changes in substance: shared documents and covers are on the server, readable by the
  Supabase project owner. "Only on this phone" stays available.
- Security: two new attack surfaces (link/invite codes, recovery code), rate-limited and hashed; a
  stolen phone is removed from Your devices or by using the recovery code.
- Storage: a 250 MB budget for documents and covers; ADR 022's image budget is lowered.
- `.detour` export stays the offline backup and the way to give a trip to someone not linked.
- iOS later: nothing here is Android-specific (QR display uses `react-native-svg`, already present;
  scanning a QR needs the camera and a module, so step 1 accepts typed codes only, scanning later).

## 9. Questions for the owner

**Answers of 2026-11-16:** 1 open (the owner asked for the codes to be explained; section 2 now has
the table). 2: both edit, the creator deletes (as proposed). 3: upload by default, as a toggle on
Add document, on by default. 4: encryption at rest on the server is acceptable; no end-to-end
encryption. 5: solo trips are never visible to the partner unless shared. 6: a shared past trip
stays in both histories, with no per-person hiding.

1. **Sign-in:** codes and a recovery code (proposed, no provider), or email/Google sign-in through
   Supabase Auth (a provider ADR first)?
2. **Roles:** both people full editors of a shared trip, with only the creator able to delete it
   (proposed)? Or both equal, including deleting?
3. **Documents default:** upload by default (proposed: shared trip and solo trip alike, so a new phone
   gets them back), or only when the trip is shared, or always ask per document?
4. **Encryption:** is "encrypted at rest by Supabase, readable by the project owner (you)" acceptable
   for tickets and insurance, or should end-to-end encryption come first?
5. **Your solo trips:** never visible to your partner unless shared (proposed), or should linked
   people see each other's trip list?
6. **Leaving a shared trip as a past trip:** stays in both histories (proposed). Should either person
   be able to hide it from their own history without leaving?
