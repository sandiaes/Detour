# ADR 027 — Destinations outside the imported regions

- **Status:** **Accepted** on 2026-11-14: the owner confirmed all five points of "Owner decisions"
  as recommended. **Built** the same day (see "As built"), awaiting acceptance. It is the **first**
  manager feature of ADR 026, section 6 (item 24), before trip export (ADR 028) and Optimize
  (ADR 029).
- **Date:** 2026-11-14
- **Related:** [`026-trip-manager-first.md`](026-trip-manager-first.md),
  [`002-api-strategy.md`](002-api-strategy.md) and
  [`012-phase-2-data-and-search-choices.md`](012-phase-2-data-and-search-choices.md) (Photon behind an adapter),
  [`009-region-readiness-thresholds.md`](009-region-readiness-thresholds.md),
  [`022-destination-and-attraction-photos.md`](022-destination-and-attraction-photos.md),
  [`024-multi-city-trips.md`](024-multi-city-trips.md),
  [`006-past-trips-archive.md`](006-past-trips-archive.md),
  [`../data-model.md`](../data-model.md)

## Context

A trip can be created today only for a city or area found in the imported data, and only if its
region has passed the readiness gates (`409 region_not_available` otherwise). Most of the world is
not imported, and the owner now keeps trips as a manager and a history (ADR 026): they want to
create a trip for **any place** and fill it by hand, with a map, days, documents and places they
add, without any suggestion.

What already exists and is reused:

- **Destination search** (`GET /v1/destinations/search`) returns the gazetteer's cities and areas
  (GeoNames, all imported countries) with `planning_available` and an `unavailable_reason`, plus an
  `external` block from **Photon** (layers city, locality, county, state), cached and budgeted
  (ADR 012). The app shows unavailable results greyed out and ignores the external block.
- **User places** (`app.user_place`, sources `manual_pin` and `search_result`) hold a name and a
  point without any `geo` row; **manual plans** need no recalculation (ADR 021 amendment).
- **Photon** is an approved provider, **Wikimedia** is approved for photos (ADR 022). This ADR adds
  no provider and no language model.

This is a new feature (CLAUDE.md rule 3).

## Decision

### 1. What a trip to such a place is

1. **A "place trip" is an empty trip by nature.** It can be created for any place the destination
   search finds, from the gazetteer or from Photon, whether or not its region is imported or
   available. It has a map, days, documents (on the phone), and the places the user adds. It
   offers **no suggestions**: "Suggest itineraries", "Optimize across cities" and place
   suggestions with days are not offered, and the API refuses them with `409
   destination_not_plannable`.
2. **An imported destination keeps working as today.** A city or area in an *available* region is
   still a normal trip: empty or with suggested itineraries. Nothing changes for it.
3. **The new-trip screen.** Search shows every result. Results that can be planned offer both
   buttons. Results that cannot (outside available regions, or from Photon) offer only **Start
   with an empty trip**; "Suggest itineraries" is disabled with the reason in words ("no sight
   data for this place yet"), as for an area in Japan today. The greyed-out, unselectable result
   is gone.

### 2. How the destination is stored

4. **A new destination kind `place`.** `app.trip.destination_kind` gains `place`. For this kind
   `destination_ref` is a text reference **with its provider**: `photon:N123` (an OSM node, way or
   relation as Photon gives it) or `geonames:2761369`. The trip row already keeps the **name and
   the point** as a snapshot, so nothing needs a `geo` row. A `country_iso2` column is added
   (nullable, Photon's `countrycode` or the gazetteer's country) for display and for the photo
   lookup. No foreign key crosses the schemas (a test enforces it today).
5. **The snapshot is the truth.** The name is the one the user saw when choosing (English-facing
   where the source gives one; never machine-translated; ADR 025). If the place later becomes
   part of an imported region, the trip stays a place trip: the user can create a new trip to get
   suggestions. This is simpler and never rewrites a user's trip.
6. **Multi-city trips (ADR 024) are not extended.** Their stops are `geo.city` rows. A trip with
   several cities outside the data is left for a later ADR; until then the user makes one trip per
   place or a place trip with places added across the area.

### 3. Adding places to a place trip

7. **"Add a place" searches around the trip's point.** The local search runs with the
   destination's point and a radius (imported sights and cities, if the point happens to lie in an
   imported region), and **Photon is asked when nothing local answers**, biased to the point and
   with sight-like layers and OSM tags (tourism, historic, leisure, natural and the like; the
   exact tag list is fixed in the build and recorded in `architecture.md`). A result becomes a
   user place of kind `location` (`source = search_result`, provider `photon`), a pin and manual
   entry work as today. Restaurants and cafés are unchanged (ADR 026 item 13).
8. **Choosing the day and time** is the existing manual step; nothing is recalculated.
9. **Travel times between stops** keep the labelled-estimate rule: the travel-time service
   (ADR 013) may call the routing adapter within its rate rules, otherwise the estimate is
   labelled, as for any trip. Nothing is invented.

### 4. The cover photo

10. **Same chain, shorter input.** The resolver (ADR 022) finds a photo through a Wikidata item.
    A Photon result may carry a Wikidata tag in its OSM extra tags; if it does, the existing chain
    runs (item, image property, English Wikipedia lead image, Commons category). The **build checks
    what Photon actually returns** and records it; the ADR does not assume it. If no item is
    known, the trip shows its illustration and **"Change photo"** still works: candidates are
    searched by the destination's name through the existing backend preview, with the credit shown
    as everywhere. No new source, no guessing: a wrong city's photo is worse than the illustration.

### 5. History, documents and what else changes

11. **Archive.** A past place trip keeps its days as any trip (ADR 026 item 19). The map's "each
    city once" row for the destination is written from the snapshot (kind `city`, no `geo`
    reference).
12. **Documents** are on the phone and unchanged (ADR 023).
13. **Export** (ADR 028) will carry the snapshot (name, point, country, provider reference), so a
    place trip survives a reinstall.
14. **Optimize** (ADR 029) treats the rule "stops stay in their own city" by distance when a stop
    has no `geo` city: stops further than a fixed radius from the trip's point (to be set in ADR
    029's build) count as a different place. To be reflected there when built.
15. **Limits and budget.** Destination search through Photon is one call per distinct query and
    shares the daily budget and cache of ADR 012; when it is used up or Photon is down, the
    gazetteer results and a **manual destination** (a name and a pin or typed coordinates, like a
    manual user place) still work. A trip needs a name and a point; it never needs the network
    once created.
16. **Privacy.** The query goes to Photon from the backend, never the app; no installation
    identifier or trip data is sent (as for every Photon call).

### 6. Build order (each step ends green: ruff, mypy, pytest, typecheck, lint, jest)

1. **Data and API:** migration (`destination_kind` gains `place`, `country_iso2`), `TripCreate`
   for a place (name, point, provider reference, country), validation of the reference format,
   `destination_not_plannable` on generate, place suggestions and cover lookups for the other
   kinds, archive snapshot, OpenAPI export and generated client.
2. **Search:** destination search returns Photon results as selectable `place` candidates (and
   their rate and cache behaviour is tested against the recorded-response stub, never the
   network); "Add a place" gets the Photon fallback biased to the trip's point.
3. **App:** the new-trip screen (results, which buttons, reasons), manual destination, the trip
   overview and menu hiding the suggestion actions, "Add a place" copy, "Change photo".
4. **Docs in the same change:** data model, architecture (destination and place search),
   design, brief, KPIs if affected, CLAUDE.md.

## Owner decisions (confirmed 2026-11-14: 1 yes, 2 no, 3 yes, 4 yes, 5 yes)

| # | Question | Recommendation |
|---|---|---|
| 1 | Should a place **inside an unavailable imported region** (gazetteer city, region not yet passing gates) also become a place trip? | Yes: it is the same empty trip, and it removes today's dead-end greyed-out results. |
| 2 | When a region later becomes available, convert existing place trips to normal city trips? | No: keep them as they are (decision 5). |
| 3 | Multi-city trips outside the data? | Not now (decision 6). |
| 4 | Accept the illustration (and "Change photo") when no Wikidata item is known, rather than guessing a photo from the name? | Yes (decision 10). |
| 5 | Manual destination (name and pin) when Photon is unavailable? | Yes (decision 15). |

## As built (2026-11-14, awaiting acceptance)

Migration `0016_place_destinations`. Backend and app tested on synthetic fixtures; **not run against
the production database** and not tried on a device.

- **API.** `POST /v1/trips` takes `destination_kind: "place"` with `destination_ref` (`photon:N123`,
  `geonames:123`, `area:<uuid>` or `manual`, checked by pattern), `destination_name`,
  `destination_lat`, `destination_lon` and an optional `destination_country`; those fields are
  refused for any other kind. `Trip.destination` gains `country_iso2`. Generating, place
  suggestions and recalculation of such a trip answer `409 destination_not_plannable`. The archive
  writes the destination's city row from the snapshot (`geo_place_ref` null).
  `GET /v1/destinations/search` gains `also_if_found` (with `include_external`: ask Photon even
  when the imported data answers).
- **App.** The new-trip search shows every result; one with no sight data (region not available,
  Japanese areas, Photon, manual) says so and offers only the empty trip. An unplannable gazetteer
  place becomes a place trip with `geonames:` or `area:` as reference; a plannable one stays a city
  or area trip. "Search more widely" asks Photon; "Enter it by hand" takes a name and typed
  coordinates. A place trip has no "Add another city", and its trip menu and settings offer no
  proposals.
- **Deviations from the draft.** (a) **Change photo** is offered only for a place from the
  gazetteer (its city or area photo candidates and automatic photo); a Photon or manual place keeps
  the illustration, with no name search, because a free-text photo search can show another place
  (decision 10 and the alternatives table already ruled that out). Whether a Photon result carries
  a Wikidata tag is **not yet checked**: the adapter does not request the extra tags, so no Photon
  place gets a photo. (b) **Manual destination** takes typed coordinates; there is no map pin yet.
  (c) **Add a place** uses the existing flow, which already searches around the trip's point and
  offers "Search more widely" through Photon; the sight-only layer and tag restriction of decision
  7 is not built, and a result becomes a user place as before.
- **Not built.** Optimize's own-city rule and the export's snapshot fields (ADRs 029 and 028) are
  those ADRs' work.

## Alternatives

| Alternative | Why not |
|---|---|
| Import more regions until the world is covered | Impossible within the 500 MB database (ADR 005), and the owner no longer needs the data for manual trips. |
| Store the destination as a `user_place` | A trip's destination is part of the trip row today and is shown on the cover before any place exists; a snapshot on the trip is simpler and keeps one rule. |
| Resolve a Photon result to the nearest `geo.city` | Wrong for small places, and it would silently turn a trip into a plannable one with data that does not cover it. |
| Let such trips ask for suggestions from Photon | Photon is a community server with a small daily budget (ADR 012) and cannot rank sights; that would be a generator without data. |
| Guess the cover photo from the name by free-text search | Risks showing another place's photo; the illustration is honest. |

## Consequences

- Any place in the world can be a trip. Suggestions remain a feature of imported regions only, and
  the app says why when they are not offered.
- A trip's destination can now be a free-text snapshot with a provider reference: it is not
  checked against our data, and searching it again later may return different results.
- Photon's daily budget is spent also on destination search; the manual destination is the
  fallback.
- Stops outside any imported region have no `geo` city, so features that use the city (the
  archive's city rows, Optimize's own-city rule, the planner's per-city logic) must use the snapshot
  and distance; each is listed above.
- A migration adds one enum value and one column, and is reversible only by deleting place trips.
