# ADR 023: Trip documents, kept on the device

- **Status:** **Proposed** on 2026-11-14, at the owner's request ("Lets build documents for now",
  step 5 of [ADR 021](021-trip-manager-redesign.md), Documents only). Built and tested in the
  mobile app only; no backend, API or database change. The owner confirms or changes the decisions
  below.
- **Date:** 2026-11-14
- **Related:** [`021-trip-manager-redesign.md`](021-trip-manager-redesign.md) (screen 08, "Documents";
  decision 13 and the "Not built" table), [`015-phase-5-mobile-shell.md`](015-phase-5-mobile-shell.md)
  (the on-device SQLite read cache), [`022-destination-and-attraction-photos.md`](022-destination-and-attraction-photos.md)
  (Supabase Storage for public photos), [`005-free-managed-hosting.md`](005-free-managed-hosting.md),
  [`../design.md`](../design.md)

## Context

The redesign asks for "a central area for tickets, bookings, transport documents and insurance",
where a document can also be associated with an attraction, a restaurant, a day or a transport leg
(reference screen 08). Two questions shape it: where the files live, and how a document refers to
the plan.

- Detour has **no accounts**: an installation is anonymous (D5), and a reinstalled app is a new
  installation that cannot reach the old one's trips. Server-side storage would therefore not
  survive a reinstall either.
- These are **personal papers** (tickets with names, booking references, insurance policies). The
  backend runs on free hosts (ADR 005); Supabase Storage's free plan has 1 GB in total, which ADR 022
  gives to public Wikimedia photos.
- Plans change: recalculation (ADR 018, 019) gives items new identifiers, and a past trip's plan is
  deleted (ADR 006). A link to an item identifier would break.

## Decision

1. **Documents stay on the phone.** The file is picked with the system picker and **copied into
   the app's private storage** (`Paths.document/documents/<trip id>/<document id>.<ext>`). Its entry
   (title, kind, link, file name, type, size, the copy's location, when it was added) is a row in a
   new `trip_document` table of the app's existing SQLite database (`detour-cache.db`), separate from
   the read cache: clearing or replacing the cache never touches documents. **Nothing is uploaded**;
   there is no endpoint, no table in `app`, and no new provider. The app says so where documents are
   added: "Documents stay on this phone only. They are not uploaded, and deleting the app or the
   trip deletes them."
2. **One new dependency: `expo-file-system` 58.0.13**, the version Expo SDK 58 pins. It is part of
   the Expo SDK and cross-platform (Android and iOS). Its `File.pickFileAsync` opens the system
   picker, `File.copy` keeps the copy, and `File.preview` opens it with the platform's viewer (an
   installed app on Android, Quick Look on iOS). No document-picker or sharing module is needed. It
   needs a new APK build.
3. **Files: PDFs and pictures** (`application/pdf`, `image/*`), which every phone can show. Other
   types are refused with a sentence saying so. No size limit beyond the phone's free space; the size
   is shown.
4. **Kinds:** Ticket, Booking, Transport, Insurance, Other. The list groups documents by kind in
   that order, newest first.
5. **What a document is about:** the whole trip, a day, a place of the plan (a visit or a meal), or
   a journey (the drive that starts a day at a new base city, ADR 016). A place is kept as a stable
   key (`place:<imported id>`, `user:<your place id>`, or `name:<name>` as a last resort) **with its
   name and day as they were when linked**, so the link still reads correctly after the plan
   changes, after new proposals, and on a past trip. A day or journey is kept by its day number.
5a. **Amended 2026-11-14 (ADR 021, decision 39):** a document may also have a **date** (ISO) and a
   **note** (at most 500 characters), both optional and stored in the same on-device record; the
   list shows the date when there is one. The tab filters by kind and sorts; "Add document" is two
   steps (how to add, then the form). Nothing else changes: still on the phone, nothing uploaded.
6. **Where documents appear:**
   - the trip's **Documents** tab (ADR 021): grouped by kind, each row with its title, what it is
     about and the file ("Schönbrunn Palace · day 1 · PDF · 245.0 kB"), and "Add a document";
   - a **place's details**: "Tickets and documents" (sights) or "Bookings and documents" (places to
     eat), only that place's documents, and "Attach a document", which starts linked to the place;
   - the **Add** sheet on a trip: "Document" is now enabled;
   - a **past trip**: a "Documents" button opens the same list (a past trip has no overview).
7. **A document's screen:** its kind, a picture shown in place for images, what it is about, the
   file name, type and size, and when it was added; **Open** (the phone's viewer), **Edit** (title,
   kind, link; the file stays), **Delete** (asks first, then removes the entry and the file).
8. **Deleting a trip deletes its documents and their files**, and the trip settings say so.
   Marking a trip as past keeps them.

## Alternatives

| Alternative | Why not |
|---|---|
| Supabase Storage through the backend (a private bucket, an `app.trip_document` table) | Would not survive a reinstall anyway (anonymous installations); puts personal papers on a free host; shares the 1 GB free quota with ADR 022's photos; needs upload endpoints, size limits and a new ADR for private storage |
| Store files as `bytea` in Postgres | Same objections, and the 500 MB free database would fill quickly |
| Keep only a link to the file where the user picked it (no copy) | A picked file's URI is often temporary (Android content URIs, iOS temporary copies); the document would stop opening |
| `expo-document-picker` and `expo-sharing` | Two more native modules for what `expo-file-system` 58 already does (pick, preview) |
| Link to an itinerary item identifier | Item identifiers change when the plan is recalculated, and a past trip has no items |

## Consequences

- Owner action: build and install a new APK (new native module).
- Documents are **not backed up**: a new phone or a reinstall starts without them, as it starts
  without the trips. Backup or sync would need accounts or an export, and its own ADR.
- Tests: `documents/model.test.ts`, `documents/store.test.ts` (memory and SQLite stores),
  `screens/Documents.test.tsx` (add with a place, cancel and refused types, journey links, open,
  edit, delete, a place's documents, the Add sheet, deleting a trip, past trips) and the
  accessibility test. Tests use an in-memory store and a fake file module (`testing/fakeFiles.ts`);
  the native file module itself is not exercised.
- **Not verified on a device:** picking, copying and opening files have not been tried on a phone;
  the Metro bundle builds.
- Notes, reservations (as structured data), photos and the trip summary remain "Not built" (ADR 021).
