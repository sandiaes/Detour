# ADR 022 — Destination and attraction photos (Wikimedia Commons, Supabase Storage)

- **Status:** **Accepted** on 2026-11-14 (owner: "Approved, lets do this", after the terms below were
  recorded). Owner direction of 2026-11-14: photos for attractions and for cities and destinations;
  Supabase Storage for the files; the user can choose the trip's photo when creating a trip (screen 13,
  "Change photo"); if none is chosen, one is fetched automatically. The user's own photos stay for
  the later Photos step. The build awaits acceptance step by step (see Consequences).
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
| Wikimedia Foundation User-Agent policy, <https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy> | Scripts "should use an informative User-Agent string with contact information, or they may be blocked without notice". Format `<client name>/<version> (<contact information>) <library>/<version>`; contact is an email, a website or a wiki user. Including "bot" in the string is recommended. Do not copy a browser's string; do not use generic agents such as "curl" or "Python-urllib"; defaults like `python-requests/x` may be blocked | 2026-11-14 | **Read** (text pasted by the owner; the host was outside this session's network allowlist) |
| Wikimedia API rate limits, <https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits> | Limits are being deployed in 2026. A client with a compliant User-Agent and no login: 200 requests per minute; unidentified: 10 per minute. Clients should limit concurrent requests to 3 or fewer and respect `Retry-After` on HTTP 429; with no header, wait at least five seconds or back off exponentially. 429 and 503 may carry it. **The page says nothing about `upload.wikimedia.org` image downloads** | 2026-11-14 | **Read** (pasted by the owner) |
| Commons "Reusing content outside Wikimedia", <https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia> | Most Commons content may be reused without asking the licensor, subject to its licence: some licences require attributing the creator, identifying the licence (sometimes linking its terms) and sharing modifications alike. Public domain needs no strict attribution but it is recommended. Wikimedia gives no warranty of the licence data; other rights (trademark, personality, privacy) may apply independently. **The pasted text does not list per-licence attribution wording** | 2026-11-14 | **Read** (pasted by the owner) |
| MediaWiki API etiquette, <https://www.mediawiki.org/wiki/API:Etiquette> | No hard speed limit on reads, but requests in series rather than in parallel are safe; batch many titles in one request with `\|`; use gzip; use `maxlag` for non-interactive tasks; cache what can be cached; use GET; exponential backoff on `ratelimited` | 2026-11-14 | **Read** (pasted by the owner) |

What the pages do not settle, and how this ADR handles it: image-file download limits are not
stated, so the adapter downloads one image at a time with a pause and backs off on 429 or 503; the
exact attribution wording per licence is not given, so each stored image shows author, licence name
with its link, the file page link and, because the stored file is resized, the words "resized"; the
licence data is Wikimedia's own and unwarranted, so the licence allow-list in decision 2 is applied
mechanically and a wrong licence is handled by `geo.image.hidden` (decision 21).

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
   `bytes`, `color`, `storage_key`, `fetched_date`, `hidden` (bool). Author and licence come from
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
      workflow): cities of the region, then places in score order up to the cap
      (`adapters/wikimedia.py`), under the rules the terms above set: a User-Agent of the form
      `Detour-bot/<version> (+https://github.com/sandiaes/Detour) httpx/<version>` (configuration, the
      repository URL as contact, no personal email); requests in series, never more than 3 at once
      (the adapter uses 1); up to 50 titles or items per request with `|`; gzip; `maxlag` on
      non-interactive runs; `Retry-After` obeyed on 429 and 503, otherwise at least five seconds then
      exponential backoff; a timeout; a cache; and a daily call counter, like every other adapter. The
      configured rate stays far below 200 requests a minute;
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
- New dependencies (Pillow, pinned, in the backend; `expo-image` in the app) are cross-platform and not
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

## Amendments

**2026-11-14, step 2 built** (migration `0009`, `adapters/wikimedia.py`, `images/`, the `images`
command and the "Resolve images" workflow, `GET /v1/images/{id}`):

- **`color` instead of a blurhash.** The placeholder while a photo loads is the image's average
  colour (`#rrggbb`), computed with Pillow. A blurhash would need another dependency for a
  marginal gain. `geo.image.color` replaces `blurhash` in decision 9.
- **The thumbnail host is `thumb.wikimedia.org`**, not `upload.wikimedia.org`: the Commons API
  returned that host for a 1,280 px thumbnail on 2026-11-14 (the recorded fixture shows it). The
  adapter downloads only from those two hosts, follows the URL the API gives, never follows
  redirects, and caps the download size. The thumbnail width (1,280) is assumed to be one of
  Wikimedia's standard steps; the first real run confirms it, and a refusal shows as a failed
  download, not as a wrong picture.
- **Pilot figures** (2026-11-14, Austria, 45 places from the import's review sample, so small and
  probably biased): 43 had an image on Wikidata; all 43 were JPEG; 30 passed the licence and
  quality gate. The real coverage is the first report of the resolver.
- **Cities** are matched through the GeoNames-ID property with one search request each; an item is
  used only when exactly one matches.
- **Not built yet in step 2:** the `cover_image` and `image` fields in the API, the automatic cover
  after a trip is created, the candidates endpoint and "Change photo" (steps 3 and 4). The
  Supabase Storage request shapes follow its Storage API and are unchecked against the live
  service.

**2026-11-14, first real run** ("Resolve images", Austria, dry run): every request was answered with
the `maxlag` error, so nothing was resolved (cities 4 requests, places 4 more, then "servers are
lagged"). The adapter gave up after four tries. It now waits for a lagged server (up to 10 tries,
the server's `Retry-After` obeyed with at least 5 s, otherwise 5, 10, 20, 40 and then 60 s), names
the lag the server reported when it gives up, and reads the limit from
`DETOUR_WIKIMEDIA_MAXLAG_SECONDS` (default 5 at that point). Wikimedia's replica lag read from this session at the
same hour was about 1 s, so the cause of the run's lag is unknown; the next report will say.

**2026-11-14, second run** (after the patience fix): ten refusals for the cities and ten for the places,
over about seven minutes each, with a reported lag of 13.95 s and 14.8 s against the limit of 5 s.
So the lag was persistent, not a blip. The default `maxlag` is now **30 s**. The reasoning, and what
is not known: the terms pages read for this ADR name `maxlag` as good practice for non-interactive
tasks but give no required value (the 5 in the etiquette page is an example); the request volume of a
resolver run is small (one request per second, batches of 50); and a limit of 5 s cannot be met
when the reported lag sits at 14 s. Why Wikidata reported that lag is not established (the replica
lag read from this session at about the same time was about 1 s; Wikidata may include other lag
sources in the figure, which was not checked). A limit of 30 s still stops the run when the
servers are really struggling, and `DETOUR_WIKIMEDIA_MAXLAG_SECONDS=5` restores the strict value.

**2026-11-14, third run: the first real coverage figures** ("Resolve images", Austria, dry run, 20
most populous cities and the 100 best-scored attractions; the downloads worked, so Wikimedia's
`thumb.wikimedia.org` host and the 1,280 px width are confirmed):

| | Asked | Photo | No image on the item | No Wikidata item matched | Rejected |
|---|---|---|---|---|---|
| Cities | 20 | 7 (35 %) | 7 | 5 | 1 (too small) |
| Attractions | 100 | 76 (76 %) | 0 | 0 | 24: 16 not landscape, 5 too small, 2 licence, 1 no author |

- **Size:** 83 stored photos, 14.46 MB, on average 174 KB, above the 150 KB estimate of decision 5.
  At 4,000 images that is about 700 MB of the 1 GB allowance. The size can be brought down (quality
  or longest side) if the headroom matters.
- **The attractions were the best-scored 100 with a Wikidata tag**, so 76 % is an upper bound for
  Austria, not an average; the rest of the 4,690 tagged attractions are less notable.
- **Cities are the weak part.** Only 35 % of the 20 largest cities got a photo: a city item often
  has no image property, and for five the GeoNames-ID search found no single item. A fallback chain
  (image, then page banner, then the Commons category of the item) and trying the next candidate
  after a rejected one would raise it. That is also the candidate list "Change photo" needs.
- **Portrait photos are the main rejection for attractions** (16 of 24): towers and churches are
  photographed upright. The landscape rule suits covers; for a detail screen a portrait photo may
  be acceptable. Not changed: it is a design choice for the owner.
- **Bug found by this run:** a dry run wrote `geo.image` and `geo.image_lookup` rows although it
  keeps no files, which would have made a later real run skip those 83 places and leave their photos
  unstored. Fixed: a dry run now takes back what it wrote (`discard_runs`), and a real run first
  checks every image row against storage with a HEAD request and fetches missing files again
  (`repair_missing`, reported under `repair`). The 83 rows already in the database are repaired by
  the first real run.

**2026-11-14, the storage key.** Supabase's API-keys page (read 2026-11-14) says the new secret key
(`sb_secret_...`, the replacement of the legacy `service_role` key, elevated, bypasses row level
security, backend use only) is not a JWT and must be sent in the `apikey` header, not as
`Authorization: Bearer`; legacy keys are JWTs (`eyJ...`) and are being deprecated by the end of
2026. The page does not mention Storage, so whether the new key works with
`/storage/v1/object/...` is untested. The store now sends `apikey` always and the bearer header only
for a legacy JWT key. The `photos` bucket was created on 2026-11-14 (public, JPEG only, 2 MB a file).

**2026-11-14, step 3 built** (API fields and the three screens; awaits acceptance; tried on recorded
responses and fixtures only, not on a device):

- **API:** `Trip.cover_image` (the photo the user chose in `app.trip.cover_image_id`, else the one
  found for the destination city, never a hidden one) and `Item.image` (the photo found for the
  imported place) are a `Photo`: `id`, `url` (a path on this API, `/v1/images/{id}`), `color`,
  `width`, `height` and a `credit` (author, licence, licence URL, file page URL and a credit line
  from one fixed template). The list and detail of trips and the itinerary and item reads carry
  them; no request is added per card.
- **Area destinations have no automatic photo yet:** `geo.admin_area` carries no Wikidata item, so
  a trip to "Austria" shows the illustration until the import keeps the areas' `wikidata` tag.
- **The automatic cover reads what the resolver stored.** Resolving a destination right after a trip
  is created (decision 14, the background resolve) is not built; the cities of an imported region
  are resolved by the "Resolve images" workflow.
- **App:** `Cover` takes a `photo` and shows it from the API's address over its average colour with
  the existing scrim, and falls back to the illustration when there is no photo or no API address.
  `PhotoCredit` (author, licence, "Wikimedia Commons (resized)", opening the file page) sits under
  the hero of a place and at the end of a trip overview, the screens that show the photo; the trips
  list card shows the photo without a credit (it opens to the overview, which has it).
- **The React Native `Image` is used, not `expo-image`** (decision 5's mention): no new dependency
  was needed to show a JPEG from an address, and the backend already sends long cache headers.
  `expo-image` can be added later if the disk cache proves too weak.
- **Not built:** the "Image credits" list of decision 20, day thumbnails with photos (decision 19),
  portrait photos for attractions, and the candidate list for "Change photo" (step 4).
