# ADR 031 — Photos: links to the user's own albums, and a cover from the phone

- **Status:** **Accepted** on 2026-11-16 (owner's answer to the Prompt 14 discussion: "go ahead with
  option A now", and a cover picture chosen from the phone), **built** 2026-11-16 and awaiting
  acceptance of the build. Mobile app only; no API, database or provider change. Checked by tests
  only, not on a device.
- **Date:** 2026-11-16
- **Phase:** 12 (Photos), replacing the storage design Prompt 14 asked for
- **Related:** [`023-trip-documents.md`](023-trip-documents.md) (documents on the phone),
  [`022-destination-and-attraction-photos.md`](022-destination-and-attraction-photos.md) (destination
  photos), [`028-trip-export-and-import.md`](028-trip-export-and-import.md) (the trip file),
  [`021-trip-manager-redesign.md`](021-trip-manager-redesign.md) (the Photos tab, step 5), D9 in
  `docs/app-plan.md` (photos on the device first)

## Context

The owner and their partner already keep one Google Photos album per trip. The owner's idea: link
that album to the trip in Detour and show its photos on the trip's Photos tab, with no storage in the
app, on the server or in Supabase.

What Google allows was read on **2026-11-16** from Google's own pages ✅:

- [Updates to the Google Photos APIs](https://developers.google.com/photos/support/updates) and the
  [release notes](https://developers.google.com/photos/support/release-notes): since **31 March 2025**
  the Library API's `photoslibrary.readonly`, `photoslibrary.sharing` and `photoslibrary` scopes are
  removed. `albums.list`, `albums.get`, `mediaItems.list`, `mediaItems.search` and the others return
  only what **the app itself created**
  ([albums.list](https://developers.google.com/photos/library/reference/rest/v1/albums/list)). The
  shared-album methods (`sharedAlbums.get`, `.join`, `.list`, …) have no supported scope any more
  ([sharedAlbums](https://developers.google.com/photos/library/reference/rest/v1/sharedAlbums)).
- The replacement is the [Picker API](https://developers.google.com/photos/picker/guides/media-items):
  the user picks single items in Google's own picker; each item's `baseUrl` lasts **60 minutes**, needs
  the user's OAuth token, and access ends when the picking session expires
  ([sessions](https://developers.google.com/photos/picker/reference/rest/v1/sessions)). Google advises
  against storing base URLs
  ([best practices](https://developers.google.com/photos/library/guides/best-practices)).

So an app cannot read an album the user made in Google Photos, shared or not, and cannot show a
lasting view of picked photos without keeping copies. Reading the album's public share page would
be scraping, outside any terms, and is excluded by CLAUDE.md (no provider without an ADR citing its
terms). Three options were put to the owner: (A) keep the album's link and open it in Google Photos;
(B) the Picker API with copies on the phone; (C) the system photo picker with copies on the phone.
The owner chose A, and asked in the same answer for a trip's cover to be choosable from the phone.

## Decision

1. **A trip has album links** (its Photos tab). The user pastes the link Google Photos gives under
   Share, Copy link (`https://photos.app.goo.gl/…`), optionally with a name ("Trip album" otherwise).
   Words around a pasted link are dropped (Google's share message has some); only an `https` address
   is kept; the same link cannot be added twice to a trip; up to 20 per trip. A link to another
   album service is accepted and labelled with its address (for an iPhone later); only Google Photos
   links are named "Google Photos".
2. **Detour never reads an album.** Pressing an album opens its link with the system
   (`Linking.openURL`): Android hands it to the Google Photos app when it is installed, otherwise
   to the browser. Detour makes **no network call** for it, uses **no Google API, no sign-in and no
   Google Cloud project**, and so adds no provider (CLAUDE.md rule 4) and no permission.
3. **Kept on the phone only**, like documents (ADR 023): a `trip_extra` table in the app's SQLite
   database (`trip_id`, `json` holding the album links and the phone cover). The backend stores
   nothing about albums or phone covers. A link to a shared album is a key to it (anyone with the
   link can open the album), so the screen says so where links are added.
4. **The bottom bar's Photos screen** lists every trip's albums, by trip; albums are added on the
   trip's Photos tab.
5. **A cover from the phone.** "Change photo" (the trip menu and the new-trip screen) has **Choose
   from your phone** above the destination photos. It opens the system file picker for one picture
   (`image/*`; on Android the picker also offers Google Photos and other installed sources), and the
   picture is **copied** into the app's private storage (`covers/`), because a picker's permission
   to read the original does not last. Each copy gets a new name, so a changed cover is never served
   from an old image cache; the previous copy is deleted. On the new-trip screen the picture is copied
   when chosen and becomes the trip's once the trip exists; a picture never used is deleted when the
   screen closes. The phone cover is shown instead of the destination photo on the trip card, the
   trip's header and the proposals, without a credit "i" (it is the user's own). If it can no longer
   be shown, the destination photo (or the illustration) is shown instead. Choosing a destination
   photo or **Automatic photo** removes the phone cover and deletes its copy. A place trip with no
   destination photos (ADR 027) can now have a cover too.
6. **Deleting a trip** deletes its album links and its cover copy with its documents.
7. **The trip file** (ADR 028) carries the album links in `albums.json`
   (`{format: "detour-albums", format_version: 1, albums: [{trip_index, name, url}]}`), always, since
   they are a few bytes of the user's own data; an import puts them back on the new trip, dropping a
   link that is not `https` or names no trip. **The cover picture is not exported** (it is a
   photo; the file stays small and the destination photo comes back on import).
8. No photo is shown inside Detour from an album, nothing is uploaded, and no permission is added
   (the picker needs none). No image classification or face recognition (Prompt 14's scope guards).

## Alternatives

| Option | Why not now |
|---|---|
| Show the album's photos inside Detour through the Library API | Not possible since 31 March 2025: apps read only what they created |
| Google Photos Picker API, copies on the phone (option B) | A Google Cloud project, Google sign-in in the app, a provider ADR; links last 60 minutes so copies are needed; adding photos later means picking again. The most work for the least reliable result |
| System photo picker, copies or thumbnails on the phone (option C) | Possible later for a few photos inside Detour (by day or on the map); not asked for now. Only photos on this phone, usually not the partner's |
| Reading the album's public share page | Scraping, outside any terms, and fragile |
| Scanning the phone's gallery by the trip's dates | Needs broad photo access, which Phase 9 removed and Prompt 14 excludes |
| Uploading the phone cover to the backend or Supabase Storage | The owner wants no storage there; the cover would also need a deletion path and a licence story |
| Keeping the album links on the server | They are keys to private albums; the phone is enough, and the trip file carries them between phones |

## Consequences

- The Photos tab no longer says "planned". Photos grouped by day or place, on the map, or a backup
  of photos are **not** built; they would need option C or B and their own ADR.
- A cover from the phone and the album links do not follow the trip to another phone except through
  the trip file, and the cover not even then (a new phone shows the destination photo).
- Clearing the app's data or uninstalling deletes the links and covers, as for documents.
- The Prompt 14 storage comparison (Supabase Storage, R2, B2) is not needed for this decision; it
  stays open for a later photo phase.
- Tests: `documents/extras.test.ts` (link cleaning, the store), `screens/TripPhotos.test.tsx` (the tab,
  the Photos screen, the phone cover, deleting a trip, the new-trip screen), `exchange/archive.test.ts`
  and `screens/Exchange.test.tsx` (album links in the trip file).
