# ADR 022 — Destination and attraction photos (Wikimedia Commons, Supabase Storage)

- **Status:** **Proposed**, 2026-11-14. Owner direction of 2026-11-14: photos for attractions and for
  cities and destinations; Supabase Storage for the files; the user can choose the trip's photo when
  creating a trip (screen 13, "Change photo"); if none is chosen, one is fetched automatically.
  **Not accepted until the Wikimedia terms below have been read and recorded** (CLAUDE.md, rule 4).
- **Date:** 2026-11-14
- **Related:** [`021-trip-manager-redesign.md`](021-trip-manager-redesign.md) (decision 13: covers
  are illustrations until an image source has an ADR; this ADR is that ADR),
  [`002-api-strategy.md`](002-api-strategy.md) (D9, photo storage), [`005-free-managed-hosting.md`](005-free-managed-hosting.md),
  [`011-attraction-selection-rule-v2.md`](011-attraction-selection-rule-v2.md) (the `wikidata` tag),
  [`../data-model.md`](../data-model.md) section 8, [`../design.md`](../design.md)

## Context

Trip cards, the trip header and the place detail screen show an illustrated cover because Detour has
no image source (ADR 021, decision 13). The owner wants real photos of destinations and attractions,
and wants to pick the trip's photo, as the reference screen 13 shows.

Constraints that shape the choice: no LLM or generated images (rule 1); no new provider without an
ADR citing its terms and the date they were read (rule 4); never invent data, so no photo where the
source has none (rule 5); the app calls only the backend and the tile host; plan generation makes no
third-party call except Valhalla travel times (ADR 004); `geo` and `app` stay separate and no
foreign key crosses them; Supabase Free is the host (ADR 005).

## Terms read for this ADR

| Source | Finding | Read on | Status |
|---|---|---|---|
| Wikidata licensing, <https://www.wikidata.org/wiki/Wikidata:Licensing> | "All structured data ... is released into the public domain under Creative Commons Zero." Page last edited 2026-09-24 | 2026-11-14 | **Read** |
| Supabase pricing and Storage pricing, <https://supabase.com/pricing>, <https://supabase.com/docs/guides/storage/management/pricing> | Free plan: 1 GB file storage, 50 MB maximum upload, 5 GB cached egress, 5 GB egress; image transformations not included on Free; free projects pause after a week of inactivity. No date shown on the pages | 2026-11-14 | **Read** |
| Wikimedia Foundation User-Agent policy, <https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy> | What a compliant User-Agent must contain | | **Not read**: the host was outside this cloud session's network allowlist |
| Wikimedia API rate limits, <https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits> | Limits for identified clients and for `upload.wikimedia.org`. A web search snippet says they are new in 2026 and subject to change | | **Not read**, same reason |
| Commons "Reusing content outside Wikimedia", <https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia> | Attribution each licence requires | | **Not read**, same reason |
| MediaWiki API etiquette, <https://www.mediawiki.org/wiki/API:Etiquette> | Concurrency guidance | | **Not read**, same reason |

The four unread pages must be read, and this table completed, before the status becomes Accepted
and before any code calls Wikimedia. Until then everything below that depends on them (the
concurrency limit, the exact attribution text, the User-Agent form) is a design intention, not a
verified rule.

## Decision

### Source

1. **Photos come from Wikimedia Commons**, found through Wikidata. For a place: the image property
   (P18) of its Wikidata item, which the import already holds as `geo.place_signal.wikidata_id`. For a
   city: its Wikidata item, matched through the GeoNames ID property (GeoNames carries no Wikidata
   ID); an area or country uses the item's image or page banner. No other image provider is added.
2. **Licences accepted:** CC0, public domain marks, CC BY and CC BY-SA. Anything else (non-commercial,
   no-derivatives, unknown, unparseable) is rejected and the place or city has no photo.
3. **Quality gate:** JPEG or PNG only (no SVG: flags and maps), landscape, at least 1,200 px wide,
   not already marked hidden. A destination that fails it has no automatic photo and keeps the
   illustration.
4. **Nothing is shown when the source has nothing.** No stock photo, no photo of a neighbour, no
   generated image. The illustrated cover stays as the fallback everywhere.

### Storage and size

5. **One stored rendition per image**: JPEG, longest side 1,080 px, quality about 75, progressive,
   target at most 150 KB (an estimate to confirm on real files; a full-width phone cover is about
   1,080 px wide). The app scales it down for thumbnails. Resizing happens in the backend
   (Pillow, pinned), because Supabase image transformations are not on the Free plan.
6. **Budget: at most 4,000 stored images**, about 600 MB at 150 KB, inside the 1 GB Free allowance
   with room for growth. At that size 5 GB of cached egress is roughly 30,000 image downloads a
   month before the on-device cache is counted. Both figures are estimates until measured; the
   resolver reports the stored bytes and refuses to go past the cap.
7. **Files live in a public Supabase Storage bucket** (`photos`), written by the backend with a
   service key kept in Render's settings (never in the repository). The object key is the image id.
8. **The app does not talk to Supabase.** `GET /v1/images/{id}` streams the object with
   `Cache-Control: public, max-age=31536000, immutable`; the app caches it on the device. This keeps
   the rule "the app calls only the backend and the tile host". (Alternative: add the storage host to
   that rule as a media host. Not chosen, to avoid changing an architecture rule for a convenience.)

### Data

9. **`geo.image`** (migration `0009`): `id`, `source` (`wikimedia_commons`), `commons_file`,
   `source_url`, `wikidata_id`, `author`, `licence` (short name), `licence_url`, `width`, `height`,
   `bytes`, `blurhash`, `storage_key`, `fetched_date`, `hidden` (bool). Author and licence come from
   the file's Commons metadata, stored as text with HTML removed. Images are independently licensed
   content, not part of the ODbL OSM data; the table carries each licence.
10. **`geo.image_lookup`**: `kind` (`place`, `city`), `ref_id`, `status` (`found`, `none`, `rejected`),
    `image_id`, `checked_date`. A negative result is stored and not retried for 90 days.
11. **`app.trip.cover_image_id`** (nullable `uuid`): the chosen or automatic cover. No foreign key
    (it crosses schemas); the API checks the identifier. Deleting a trip never deletes an image.
12. **API:** `Trip` (list and detail) and the destination search result gain a nullable
    `cover_image {id, url, blurhash, attribution {text, licence, url}}`. A place or itinerary item
    gains the same `image`. The trips list needs no extra request per card.

### Fetching: when and by whom

13. **Never during plan generation and never from the app.** Images are resolved by:
    - **an import step** (`python -m detour_api.importer images <region>` and the "Import region"
      workflow): cities of the region, then places in score order up to the cap, reading Wikidata in
      batches with one identifying User-Agent, low concurrency, a timeout, backoff on 429, and a
      daily call counter, like every other adapter (`adapters/wikimedia.py`);
    - **a background resolve after a trip is created or itineraries are generated**, for the
      destination and for the planned places that have none yet and are not marked `none`. It runs
      after the response is returned.
14. **Automatic cover.** When the user chooses no photo, the trip's cover is the destination's image
    from `geo.image_lookup`. If that has not been resolved yet, the background resolve fills it in
    and the app shows the illustration until then; the trip is never blocked on a photo.
15. **Choosing a photo (screen 13, "Change photo").** After a destination is chosen, the control opens a
    sheet of up to 12 candidates from Commons for that destination: the destination's own image,
    then freely licensed images from the item's Commons category, passing the same licence and quality
    gate. `GET /v1/destinations/{id}/cover-candidates` returns them through the adapter (cache for a
    week, the same budget counter). The thumbnails shown in the sheet are fetched by the backend and
    returned as small previews, so the app still talks only to the backend. Choosing one stores it
    (download, resize, upload, a `geo.image` row) and sets `cover_image_id` on create. The cover can
    be changed later from the trip menu ("Change photo" on the trip header).
16. **No own-photo upload in this ADR.** Using a photo from the phone is the Photos step (ADR 021,
    step 5; `data-model.md` section 8) and stays on the device.

### Screens

17. **Trips list card and trip header:** the cover photo, with a dark gradient under the name and the
    dates for legibility. No cover image: the illustration, as today.
18. **Place detail:** a photo above the name when the place has one, with the credit line ("Photo:
    author, licence, Wikimedia Commons") that opens the file page. No photo: today's cover, no empty
    frame.
19. **Itinerary day thumbnails** may use the photo of the day's first sight (today they are
    illustrations). **Map markers stay as designed** (ADR 021, "quiet markers"): no photos on the map.
    A selected stop's expanded area may show a small thumbnail.
20. **Credits:** an "Image credits" list under More lists every image the app shows, with author,
    licence and link, next to the OpenStreetMap, GeoNames and tile attributions.
21. **Hiding a wrong photo:** `geo.image.hidden` removes it from every screen; the owner sets it by
    hand (a command, no screen). The place or city then has none until a new lookup.

## Alternatives

| Alternative | Why not |
|---|---|
| Unsplash or Pexels for destination covers | Destination mood shots only; API terms require hotlinking or download tracking; adds a second provider for no attraction coverage |
| Google, Foursquare or other place photos | Paid or premium fields; caching restrictions; fails rule 4 on cost |
| Mapillary | Street-level, needs a token, uneven quality |
| Generated images | Banned by rule 1 |
| Hotlink `upload.wikimedia.org` from the app | Breaks "the app calls only the backend and the tile host"; Wikimedia discourages it; the photo vanishes if the file is renamed |
| Store only metadata, redirect to Wikimedia at request time | Same objection, plus a third-party call in the request path |
| Store images in the database | Counts against the 500 MB database allowance, which the `geo` data needs |
| Own photos from the phone as the cover | Needs the Photos step and an upload path; not asked for here |
| Fetch every attraction's photo at import | Thousands of calls and stored bytes for places no plan uses; the cap and the resolve-on-plan rule avoid that |

## Consequences

- **Coverage is unmeasured.** Many attractions will show no photo. A short spike must count, for one
  imported region, how many places and cities have an image, the licence mix and the share that
  passes the quality gate, before the import step is built. No region has been imported into the real
  database yet, so the spike runs on a region import first.
- New dependencies (Pillow, a blurhash encoder, `expo-image` in the app) are cross-platform and not
  generative-AI; `tools/check_dependencies.py` must pass. `expo-image` needs a one-line check against
  the "no Android-only native dependency" rule: it is an Expo SDK module for both platforms.
- New secrets: the Supabase service key and the bucket name, in Render's settings and in
  `.env.example` as empty names.
- A new adapter, `adapters/wikimedia.py`, with the usual contract tests against recorded responses.
  No test calls Wikimedia.
- The Supabase project's weekly pause (ADR 005) pauses image storage too; the cache headers and the
  on-device cache keep shown images visible, and the illustration covers the rest.
- Attribution work is permanent: every shown photo needs its credit; an image without a stored
  author and licence is not shown.
- Documents changed in the same commit: `design.md`, `data-model.md`, ADR 021 (a pointer),
  CLAUDE.md. `architecture.md`, `api-evaluation.md` and `.env.example` change when the code does.
- Build order, each step awaiting the owner's acceptance: (1) read the unread terms and run the
  coverage spike; (2) migration, adapter, resolver and the image endpoint; (3) app: covers, place
  detail, credits; (4) "Change photo" on new trip and in the trip menu.
