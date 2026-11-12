# ADR 002 — API and data-source strategy

- **Status:** Accepted on 2026-11-12.
- **Date:** 2026-11-12
- **Related:** [`../api-evaluation.md`](../api-evaluation.md), [`001-technology-stack.md`](001-technology-stack.md)
- **Amended by:** [`003-scope-opening-hours-and-attractions.md`](003-scope-opening-hours-and-attractions.md) (opening hours removed); [`004-fossgis-valhalla-demo-server.md`](004-fossgis-valhalla-demo-server.md) (uncached travel times may come from the FOSSGIS Valhalla server)

## Context

The product needs maps, destination and place search, attractions, restaurants,
travel times, and currency conversion, with a strong preference for free and open sources and
no LLM at runtime. Public transport, weather and photo storage had to be assessed as well.

What the official terms say, in short (details and sources in `api-evaluation.md`):

- **Community-run OSM services are not an application backend.** Public Nominatim forbids
  autocomplete and systematic queries and allows at most one request per second per
  application. Overpass guidance for regular use is about 100 queries and 10 MB per day. The
  FOSSGIS routing servers allow one request per second with no availability guarantee.
  `tile.openstreetmap.org` forbids bulk and offline use and may block without notice.
- **Open data is unrestricted in volume** but carries licence duties: OSM (ODbL, attribution
  and share-alike for derivative databases), GeoNames (CC BY 4.0), Wikidata (CC0), Overture
  Places (CDLA Permissive 2.0 and Apache 2.0), Foursquare OS Places (Apache 2.0).
- **No free source has reliable restaurant prices or ratings.** Google's price and rating
  fields are Enterprise-tier, may not be stored and must be shown on a Google map. Yelp offers
  a trial only.
- **Several free plans exclude commercial use:** Open-Meteo, Transitous, Stadia Maps,
  MapTiler, Transitland Explorer.
- **OpenFreeMap** allows commercial use with no request limits but gives no availability
  commitment.

## Decision

### 1. Strategy

1. **Import, do not call.** Places, restaurants, the gazetteer and the street
   network are imported per region into our own database and routing engine. Plan generation
   makes no third-party calls.
2. **Backend-only access.** The app calls our API and the tile host, nothing else.
3. **Adapters with named fallbacks.** Each external capability has one interface, a primary
   provider, a fallback, a daily budget counter, caching and an identifying User-Agent.
4. **Verified terms only.** A provider is adopted through an ADR that cites the official terms
   read on a stated date. A free trial is never the basis for a feature.
5. **Show provenance.** Estimated, unknown and user-entered values are labelled as such.

### 2. Provider selection for the MVP

| Capability | Primary | Fallback |
|---|---|---|
| Map rendering | MapLibre React Native | none |
| Map tiles | OpenFreeMap public instance; style URL served by the backend | Self-hosted PMTiles extract of the Protomaps basemap |
| Destination search | Own gazetteer from the GeoNames dump | Photon |
| Place and restaurant search | Own place table | Photon public instance through the backend, cached; then manual entry |
| Reverse geocoding | Nearest-place query on own data | Photon reverse |
| Attractions and restaurants | OpenStreetMap regional extract | Overture Places and Foursquare OS Places after the MVP |
| Notability signal | Wikidata, joined by the OSM `wikidata` tag, fetched at import | OSM tag signals only |
| Walking and driving times | FOSSGIS Valhalla server through a cached adapter (ADR 004); self-hosted Valhalla if S3 and the owner choose it | Straight-line estimate labelled as estimated |
| Countries and currencies | Static seed from GeoNames country data and mledoze/countries | none needed |
| Exchange rates | Frankfurter, fetched daily and stored | ECB daily reference rates; then fawazahmed0/exchange-api |
| Restaurant prices | User-entered price records | none; "No price data" |

### 3. Explicitly not in the MVP

| Capability | Position |
|---|---|
| Public transport, GTFS, GTFS-Realtime | Phase 10. Self-hosted MOTIS with feeds found through the Mobility Database, or Transitous if the project is open source and non-commercial. Realtime only after that. |
| Weather | Not a stated product goal. If approved later: MET Norway, or Open-Meteo while non-commercial. |
| Photo storage | Future phase. On-device first; Cloudflare R2 or Backblaze B2 for optional backup. |
| Provider restaurant prices and ratings | Not available on acceptable terms. |

### 4. Rejected

| Provider | Reason |
|---|---|
| Google Places and Routes | Storage forbidden; Google map required; billing beyond small free caps. |
| Yelp Places | Trial only; Enterprise application for consumer products. |
| Foursquare Places API | Pricing and terms could not be verified. |
| Public Nominatim, Overpass and FOSSGIS routing at runtime | Usage policies; development use only. |
| `tile.openstreetmap.org` | Usage policy; no offline; may block. |
| Stadia Maps Free, MapTiler Free | Non-commercial or personal use only; MapTiler logo required. |
| REST Countries API | Key-gated service for static data. |
| ExchangeRate-API open access | Redistribution ban and attribution, with no advantage over Frankfurter. |
| OpenTripMap | Doubtful maintenance; duplicates the OSM and Wikidata import. |
| MinIO | Community repository archived and unmaintained. |
| Supabase Free | Projects pause after a week of inactivity. |

### 5. Stage rules

| Stage | Rule |
|---|---|
| Development | Public community servers may be used by hand for exploration, never from automated tests or the app. |
| Personal production | The MVP selection above. Stay under half of any published or self-imposed limit. |
| Public commercial release | Replace or self-host every service marked REPLACE in `api-evaluation.md`: tiles with an availability commitment or self-hosted, self-hosted Photon and Frankfurter, no Open-Meteo free API, no Transitous. Obtain legal review of ODbL use. |

## Alternatives considered

| Alternative | Why not |
|---|---|
| Call hosted APIs at request time for places and routing | Quotas are small or terms exclude it; itineraries could not be stored or reproduced. |
| One commercial provider for everything (Google or similar) | Cost, storage bans and display restrictions conflict with the brief. |
| Hosted geocoder free tier as the primary search | Unnecessary once the gazetteer and place table are local; kept as fallback. |
| Planet-wide self-hosting from the start | Hardware far beyond a free or personal budget (for example, a planet geocoder import recommends 64–128 GB of RAM). |

## Consequences

**Positive**

- External API spend is zero and predictable.
- Plan generation is independent of third-party availability and quotas.
- Itineraries can be stored, cached and regenerated without breaching provider terms.

**Negative**

- An import pipeline to build, run and keep current.
- Coverage limited to imported regions.
- Restaurant data is only as good as OSM in each region; no ratings, no provider prices.
- Attribution and ODbL duties must be tracked.

**Risks**

- OpenFreeMap, the Photon public instance or the Frankfurter public API may change or stop;
  each has a named fallback.
- OSM coverage may be inadequate in a chosen region; the Phase 0 data quality report is the
  gate.

## Decision record

| ID | Decision | Status |
|---|---|---|
| D1 | The project is open source and non-commercial | Decided 2026-11-12. Transitous and Open-Meteo's free API become permissible, subject to their other conditions (published source, light usage, attribution). |
| D2 | Pilot regions: Japan, Italy, Central Europe (Austria, Czechia, Hungary at least) | Decided 2026-11-12 |
| D4 | Public transport after the MVP | Approved 2026-11-12 |
| D6 | Weather excluded from the MVP | Approved 2026-11-12 |
| D8 | OpenFreeMap now, PMTiles fallback rehearsed before release | Approved 2026-11-12 |
| D9 | Photos on-device first; cloud backup decided later | Approved 2026-11-12 |
| D10 | Prices from users only; no price inferred from venue type | Approved 2026-11-12 |
| D11 | Open-source licence and date the repository becomes public | **Open.** Needed before Transitous can be used. |

## Verification gaps

Sources that could not be read directly, and must be before they are relied on: Geofabrik's
terms and update cadence; the Valhalla API reference; the GeoNames dump readme; openrouteservice
plans; Foursquare Places API pricing; Geoapify's commercial-use wording (its pricing FAQ and its
terms disagree); Cloudflare R2's payment-method requirement. The list with timing is in
`api-evaluation.md`, section 15.
