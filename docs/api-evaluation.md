# API and data-source evaluation

Research date: **2026-11-12**. Terms, quotas and prices change; every figure here must be
re-checked against the linked official page before a provider is wired in.

> **Update 2026-11-13 (ADR 017):** the app has no budgets, currencies or prices for now, so
> nothing in sections 5 (restaurant prices) and 11 (exchange rates) is used; Frankfurter is not
> wired in. The research is kept for the record.

## How to read this document

**Verification status** is stated per candidate:

| Mark | Meaning |
|---|---|
| ✅ Verified | The official page was fetched and read on the research date. |
| ◐ Partly verified | Some official pages were read; the gaps are named. |
| ⚠ Not verified | The official page could not be read. Figures come from search results and are flagged. Do not rely on them. |

**Suitability tiers** used throughout:

| Tier | Meaning |
|---|---|
| **DEV** | Development and prototyping only. The terms, quota or stability rule out shipping it. |
| **PERSONAL** | Acceptable for a small, personal, non-commercial production app. |
| **REPLACE** | Usable for PERSONAL, but must be replaced (or self-hosted, or paid for) before a public commercial release. |
| **ANY** | Open data or self-hosted open-source software. No provider quota; suitable at every stage, subject to licence obligations. |

"Card" means whether a payment card is required to start. "Exceeded" means what the provider
says happens above the free allowance.

## Headline findings

1. **The public OpenStreetMap-run services are not an app backend.** The Nominatim policy forbids
   autocomplete and systematic queries and caps use at 1 request/second for the whole
   application. The Overpass guidance for regular use is roughly 100 queries and 10 MB per day.
   The FOSSGIS routing servers allow 1 request/second with no availability guarantee. The
   architecture therefore imports open data into its own PostGIS database and self-hosts
   routing, instead of calling these services at runtime.
2. **No free source provides reliable restaurant prices or ratings.** The OSM wiki has no
   documented price-range key. Overture Places and Foursquare OS Places carry no hours, price or
   rating fields. Google exposes price level and rating only in its Enterprise SKUs (1,000 free
   calls per month per SKU) and forbids storing the results. Yelp offers a trial, not a free tier.
3. **Public transport has a licensing gate.** Transitous is free only for open-source,
   non-commercial, low-volume projects. Otherwise the route is self-hosting MOTIS with GTFS feeds
   whose licences must be checked one by one.
4. **"Free" weather is non-commercial.** Open-Meteo's free API is non-commercial only. MET Norway
   has no such restriction on the pages read but has a shorter forecast horizon.
5. **Several "free" plans exclude commercial use**: Stadia Maps, MapTiler, Transitland Explorer,
   Open-Meteo, Transitous. Geoapify and LocationIQ allow commercial use on their free plans with
   attribution.

## Summary matrix

| Capability | MVP choice | Tier | Fallback | Rejected or deferred |
|---|---|---|---|---|
| Map rendering | MapLibre React Native | ANY | none needed | expo-maps (Google/Apple) |
| Map tiles | OpenFreeMap public instance | REPLACE (no SLA) | Self-hosted PMTiles extract (Protomaps build) | tile.openstreetmap.org, MapTiler free, Stadia free |
| Destination search (cities, areas) | Own gazetteer from GeoNames dump | ANY | Photon | Nominatim public |
| Free-text place search | Own POI table, then Photon via backend proxy | PERSONAL / REPLACE | Self-hosted Photon; Geoapify free | Nominatim public (autocomplete forbidden) |
| Reverse geocoding | PostGIS nearest-place query on own data | ANY | Photon reverse | Nominatim public |
| Cities and admin areas | GeoNames dump | ANY | Overture divisions (polygons) | GeoNames web services |
| Attractions and POIs | OSM regional extract in PostGIS + Wikidata notability | ANY | Overture Places, FSQ OS Places (later) | Overpass at runtime, OpenTripMap |
| Restaurants | OSM regional extract | ANY | Overture Places, FSQ OS Places (later) | Google Places, Yelp, Foursquare Places API |
| Opening hours | Not used (out of scope, ADR 003) | n/a | n/a | n/a |
| Walking and driving routes, matrices | Self-hosted Valhalla per region | ANY | Straight-line estimate with confidence flag | FOSSGIS demo, GraphHopper free, ORS hosted (unverified) |
| Public transport | **Not in MVP** | n/a | Phase 10: self-hosted MOTIS or Transitous (if eligible) | Transitland free, Google Routes |
| GTFS / GTFS-Realtime | **Not in MVP** | n/a | Mobility Database catalog for feeds (Phase 10) | n/a |
| Weather | **Not in MVP** (not a stated product goal) | n/a | MET Norway, or Open-Meteo if non-commercial | OpenWeatherMap (not verified) |
| Country and currency data | Static seed: GeoNames `countryInfo` + mledoze/countries | ANY | n/a | REST Countries API |
| Exchange rates | Frankfurter, fetched daily by backend and stored | PERSONAL, ANY if self-hosted | ECB daily XML; fawazahmed0 | ExchangeRate-API open access |
| Photo storage (future) | On-device files + metadata | ANY | Cloudflare R2 or Backblaze B2 for backup | Supabase free, MinIO |

---

## 1. Map rendering and map tiles

### 1.1 MapLibre React Native — ✅ Verified (GitHub repository and docs source)

- **Use:** native vector map rendering in the app, on Android and iOS, from any MapLibre style URL.
- **Type:** open-source library, MIT. Not a hosted service.
- **Quota / card:** none.
- **Commercial use:** allowed (MIT).
- **Caching / storage:** no library restriction; the tile provider's terms apply.
- **Attribution:** the map's attribution control must stay visible; it carries the tile provider's and OSM's credit.
- **Coverage / quality:** depends on tiles. Current version v11.5.1 (2026-10-29). Requires React Native ≥ 0.80 and Android API ≥ 23. From v11 only the New Architecture is supported, which matches Expo SDK 55+.
- **Risks:** not part of the Expo SDK and not usable in Expo Go; a development build with the config plugin is required. Community-maintained. Offline-pack support was not confirmed in the pages read.
- **Exceeded:** n/a.
- **Fallback:** none planned. `expo-maps` is not a fallback: it is alpha and renders Google Maps on Android and Apple Maps on iOS, which needs a Google Cloud project and breaks the OSM-compatible data model.
- **MVP:** **Yes.**
- Sources: <https://github.com/maplibre/maplibre-react-native>, <https://github.com/maplibre/maplibre-react-native/releases>, <https://docs.expo.dev/versions/latest/sdk/maps/>

### 1.2 OpenFreeMap (public instance) — ✅ Verified

- **Use:** vector basemap tiles and ready-made MapLibre styles (Liberty, Bright, Positron and others).
- **Type:** free public instance funded by donations; fully open source (MIT) and self-hostable.
- **Quota:** "no limits on the number of map views or requests". No registration, no API key.
- **Card:** no.
- **Commercial use:** allowed ("Is commercial usage allowed? Yes.").
- **Caching / storage:** automated collection is forbidden except offline downloads of at most 3,000 tiles or 50 MB each, with at most 4 parallel requests and a unique User-Agent. Larger needs: contact them or use the weekly planet downloads.
- **Attribution:** required: "OpenFreeMap © OpenMapTiles Data from OpenStreetMap". MapLibre adds it automatically.
- **Coverage / quality:** global, OpenMapTiles schema, OSM data, weekly planet builds.
- **Risks:** run by one company; no SLA; the terms say the service is "as-is" and may be discontinued "at any time without notice". Funding depends on donations.
- **Exceeded:** no quota exists; abuse is covered by the user-conduct clause.
- **Fallback:** self-hosted PMTiles (1.3). The style URL must be delivered from the backend so it can be switched without an app release.
- **MVP:** **Yes.** Tier **REPLACE**: allowed commercially, but a commercial release needs a tile source with an availability commitment or self-hosting.
- Sources: <https://openfreemap.org/>, <https://openfreemap.org/tos/> (last updated 2026-10-14)

### 1.3 Protomaps basemap as PMTiles (self-hosted) — ✅ Verified

- **Use:** a single-file vector basemap archive served from static or object storage with HTTP range requests; regional extracts with `pmtiles extract --bbox`.
- **Type:** open data plus open-source tooling. The basemap is an ODbL Produced Work; the software is BSD.
- **Quota / card:** none from Protomaps. Costs are those of the chosen storage and bandwidth.
- **Commercial use:** allowed.
- **Caching / storage:** unrestricted; the file is yours to host.
- **Attribution:** OpenStreetMap attribution required.
- **Coverage / quality:** global daily builds at `maps.protomaps.com/builds`; zoom 0–15; each extra zoom level roughly doubles file size.
- **Risks:** you operate the hosting. The daily-build bucket keeps a limited history. Styles are a separate package (`@protomaps/basemaps`).
- **Exceeded:** n/a.
- **Fallback:** OpenFreeMap self-hosted, or a paid tile plan.
- **MVP:** **No — designated fallback.** Use it if OpenFreeMap becomes unreliable or before a commercial release.
- Sources: <https://docs.protomaps.com/>, <https://docs.protomaps.com/basemaps/downloads>, <https://docs.protomaps.com/guide/getting-started>

### 1.4 OpenStreetMap-operated tiles (`tile.openstreetmap.org`, `vector.openstreetmap.org`) — ✅ Verified

- **Use:** OSM's own raster and Shortbread vector tiles.
- **Type:** donated community infrastructure.
- **Quota:** no numeric quota; "We may block access, without notice, if your usage degrades the service."
- **Card:** no.
- **Commercial use:** not forbidden, but the policy warns commercial services that access may be withdrawn at any point.
- **Caching / storage:** must honour cache headers (or cache at least 7 days). Bulk downloading, prefetching and offline use are prohibited.
- **Attribution:** visible "© OpenStreetMap contributors".
- **Coverage / quality:** global, best-effort, "no SLA or guarantee".
- **Risks:** apps must send a distinct, stable User-Agent; library defaults are blocked. Any offline feature is ruled out.
- **Exceeded:** blocking without notice.
- **Fallback:** n/a.
- **MVP:** **No.** Tier **DEV** at most. The policy itself directs apps that cannot meet it to other OSM-derived services.
- Sources: <https://operations.osmfoundation.org/policies/tiles/>, <https://operations.osmfoundation.org/policies/vector/>

### 1.5 MapTiler Cloud (Free plan) — ◐ Partly verified

- **Use:** hosted vector/raster tiles, geocoding.
- **Type:** commercial free tier.
- **Quota:** the plan card was read; the numeric session and request allowances are rendered by script and were **not captured**.
- **Card:** "No credit card needed".
- **Commercial use:** free plan is "Suitable for testing, PoC, prototyping, personal, or non-commercial use"; commercial use requires a paid plan (Flex from $30/month).
- **Caching / storage:** not read.
- **Attribution:** MapTiler logo on the map is mandatory on the free plan, plus OSM attribution.
- **Coverage / quality:** global, high quality.
- **Risks:** the logo requirement, the non-commercial restriction, quota changes.
- **Exceeded:** not captured for the free plan.
- **Fallback:** OpenFreeMap.
- **MVP:** **No.** Tier **DEV / PERSONAL**.
- Source: <https://www.maptiler.com/cloud/pricing/>

### 1.6 Stadia Maps (Free plan) — ✅ Verified

- **Use:** hosted tiles, geocoding and routing billed in "credits".
- **Type:** commercial free tier.
- **Quota:** 200,000 credits/month, "No additional usage".
- **Card:** no (14-day Professional trial without a card, then the free plan).
- **Commercial use:** "Commercial use not allowed" on Free. Paid plans start at 1,000,000 credits/month.
- **Caching / storage:** not read.
- **Attribution:** required (details not read).
- **Risks:** non-commercial only.
- **Exceeded:** no additional usage on Free.
- **Fallback:** OpenFreeMap.
- **MVP:** **No.** Tier **DEV**.
- Source: <https://stadiamaps.com/pricing/>

---

## 2. Geocoding and reverse geocoding

The MVP resolves destinations against its own gazetteer (section 3.1) and searches its own POI
table first. External geocoders are used only for free-text places the local data cannot
resolve, always through the backend, with cached results.

### 2.1 Photon — ✅ Verified (public-instance terms and repository)

- **Use:** search-as-you-type geocoding and reverse geocoding on OSM data, for the "add a location or restaurant by name" flow.
- **Type:** open source (Apache 2.0), self-hostable; komoot runs a public instance at `photon.komoot.io`.
- **Re-read 2026-11-12 for Phase 2 (ADR 012):** home page terms unchanged ("please be fair - extensive usage will be throttled. We do not guarantee for the availability and usage might be subject of change in the future"); the repository README adds "Extensive usage will be throttled or completely banned" and "reserve the right to implement changes without notice". The API doc (`docs/api-v1.md`) confirms the parameters the adapter uses: `q`, `limit`, `lang`, `lat`/`lon`, `layer`, `countrycode`. A live call to `/api` timed out from the development environment, so the adapter's fixture follows the documented format.
- **Re-read 2026-11-13 for Phase 8 (ADR 019):** unchanged: the repository README still says "You are welcome to use the API for your project as long as the number of requests stay in a reasonable limit. Extensive usage will be throttled or completely banned. We do not give guarantees for availability and reserve the right to implement changes without notice." No new number. `docs/api-v1.md` documents the `osm_tag` result filter (now marked deprecated in favour of `include`/`exclude` category filters, whose categories depend on the installation) and an `extra` object of further tags in results. The restaurant search sends `osm_tag=amenity:restaurant` and `amenity:cafe` and filters the answer again; it does not read `extra`; the daily budget and cache are unchanged. A live call was not made from the build environment.
- **Quota:** no number. "You can use the API for your project, but please be fair - extensive usage will be throttled."
- **Card:** no.
- **Commercial use:** not addressed for the public instance. Treat as unsuitable for commercial load.
- **Caching / storage:** not restricted by the terms; data is ODbL.
- **Attribution:** OpenStreetMap.
- **Coverage / quality:** global, multilingual, typo-tolerant. Quality equals OSM address and POI coverage: strong in Europe, uneven elsewhere.
- **Risks:** "We do not guarantee for the availability and usage might be subject of change in the future." Self-hosting the planet needs about 95 GB of disk and 64 GB of RAM is recommended; Java 21+. Country-level dumps are published weekly and are far smaller.
- **Exceeded:** throttling or a ban.
- **Fallback:** self-hosted Photon with a country extract; Geoapify free plan.
- **MVP:** **Yes, as the second-line search behind local data.** Public instance: tier **PERSONAL / REPLACE**. Self-hosted: tier **ANY**.
- Sources: <https://photon.komoot.io/>, <https://github.com/komoot/photon>

### 2.2 Nominatim — ✅ Verified

- **Use:** forward and reverse geocoding on OSM data.
- **Type:** open source, self-hostable; OSMF runs a public instance.
- **Quota (public):** "an absolute maximum of 1 request per second", counted across all users of an application.
- **Card:** no.
- **Commercial use:** allowed in principle, with the warning that access may be withdrawn.
- **Caching / storage:** results "must be cached on your side" for bulk tasks; a proxy with caching is recommended for apps.
- **Attribution:** required; data is ODbL.
- **Coverage / quality:** global.
- **Risks:** **autocomplete is "strictly forbidden"**, as are systematic queries such as "downloading all POIs in an area". Apps must be able to switch service without a software update. The policy can change without notice.
- **Exceeded:** blocking or ban.
- **Fallback:** Photon; self-hosted Nominatim (planet: 128 GB RAM recommended, at least 1 TB disk; small extracts need far less, minimum 2 GB RAM).
- **MVP:** **No.** Public instance tier **DEV**. Keep as a possible low-volume reverse-geocoding fallback through the backend.
- Sources: <https://operations.osmfoundation.org/policies/nominatim/>, <https://nominatim.org/release-docs/latest/admin/Installation/>

### 2.3 Geoapify (Free plan) — ✅ Verified, with one inconsistency

- **Use:** hosted geocoding, reverse geocoding, autocomplete, Places, routing, built mainly on OSM.
- **Type:** commercial free tier.
- **Quota:** 3,000 credits/day (generally one request is one credit).
- **Card:** "No credit card required".
- **Commercial use:** the pricing FAQ says the Free plan may be used "for commercial websites, apps, and business projects, including in production". The Terms and Conditions say commercial use of the free package is allowed in production "with some limitations. Please contact us for details." **Resolve this in writing before any commercial use.**
- **Caching / storage:** for the Places API, "you are allowed to cache, store, and redistribute the results" with attribution.
- **Attribution:** "Powered by Geoapify" link plus OpenStreetMap; Geoapify attribution is mandatory on the free plan.
- **Coverage / quality:** global; OSM-level quality; 800+ place categories.
- **Risks:** terms allow suspension or change of the service at any time without notice.
- **Exceeded:** limits are "soft"; sustained overuse leads to an upgrade request and possibly a blocked account. The terms also reserve the right to suspend or apply overage charges.
- **Fallback:** LocationIQ; self-hosted Photon.
- **MVP:** **No.** Named **hosted fallback** for geocoding if Photon's public instance is unavailable. Tier **PERSONAL**, possibly commercial after written confirmation.
- Sources: <https://www.geoapify.com/pricing/>, <https://www.geoapify.com/terms-and-conditions/>, <https://www.geoapify.com/places-api/>

### 2.4 LocationIQ (Free plan) — ✅ Verified

- **Use:** hosted geocoding and reverse geocoding.
- **Type:** commercial free tier.
- **Quota:** 5,000 requests/day, 2 requests/second, 60 requests/minute.
- **Card:** not stated on the pricing page ("Free sign up").
- **Commercial use:** "Limited Commercial Use": allowed with a prominent link back to LocationIQ.
- **Caching / storage:** not stated on the pricing page.
- **Attribution:** the link back, plus underlying data attribution.
- **Coverage / quality:** global, OSM-based.
- **Risks:** soft limits apply to premium plans only; free-plan overage behaviour is not stated.
- **Exceeded:** not stated for Free.
- **Fallback:** Geoapify.
- **MVP:** **No.** Second hosted fallback. Tier **PERSONAL**.
- Source: <https://locationiq.com/pricing>

### 2.5 Pelias (self-hosted) — ◐ Partly verified (repository only)

- **Use:** self-hosted geocoder with autocomplete over OSM, OpenAddresses, Who's on First and GeoNames.
- **Type:** open source, MIT. Needs Elasticsearch 7 or 8.
- **Quota / card:** none.
- **Risks:** operational weight (Elasticsearch plus several services). Hardware needs for large builds were not read.
- **MVP:** **No.** Heavier than Photon for the same job.
- Source: <https://github.com/pelias/pelias>

---

## 3. Cities and administrative areas

### 3.1 GeoNames (data dump) — ◐ Partly verified (terms and web-service pages read; dump readme host not reachable)

- **Use:** the destination gazetteer: populated places with population, country, admin1/admin2 codes, alternate names, time zone; and country metadata including currency code.
- **Type:** open data, daily database export.
- **Quota:** none for the dump. The **web services** are limited to 10,000 credits/day and 1,000/hour per username; "An exception is thrown when the limit is exceeded."
- **Card:** no.
- **Commercial use:** "commercial usage is allowed".
- **Caching / storage:** unrestricted for the dump.
- **Attribution:** CC BY 4.0: credit GeoNames with a link.
- **Coverage / quality:** global; over 13 million features, 5.2 million populated places. Quality is good for cities and towns, weaker for small localities and neighbourhood boundaries. Point data only: no polygons.
- **Risks:** provided "as is"; file names and columns of the dump (`cities*.zip`, `admin1CodesASCII`, `countryInfo.txt`) are recalled from the standard readme and **must be confirmed** when the import is built.
- **Exceeded:** n/a for the dump.
- **Fallback:** Overture divisions; OSM `place=*` nodes from the regional extract.
- **MVP:** **Yes (dump only).** Tier **ANY**. The web services are not used.
- Sources: <https://www.geonames.org/export/>, <https://www.geonames.org/about.html>, <https://www.geonames.org/export/web-services.html>

### 3.2 Overture Maps — divisions theme — ✅ Verified

- **Use:** polygons and hierarchy for countries, regions, counties, localities and neighbourhoods; needed when the destination is an area ("Andalusia") and POIs must be clipped to it.
- **Type:** open data (GeoParquet releases).
- **Quota / card:** none.
- **Commercial use:** allowed under ODbL.
- **Caching / storage:** allowed; ODbL share-alike applies to derivative databases.
- **Attribution:** "© OpenStreetMap contributors, Overture Maps Foundation."
- **Coverage / quality:** more than 5.8 million division features with subtypes from country down to microhood.
- **Risks:** the schema evolves between releases; large files need DuckDB or similar tooling to extract a region.
- **Exceeded:** n/a.
- **Fallback:** OSM administrative boundary relations from the regional extract.
- **MVP:** **No — first candidate when area polygons are needed.** The MVP can clip by OSM admin boundaries already present in the extract. Tier **ANY**.
- Sources: <https://docs.overturemaps.org/guides/divisions/>, <https://docs.overturemaps.org/attribution/>

---

## 4. Tourist attractions and points of interest

### 4.1 OpenStreetMap regional extracts (Geofabrik) — ◐ Partly verified (ODbL and tag documentation read; Geofabrik's download-server text reported by the owner on 2026-11-12, not read by the assistant)

- **Use:** the primary source of attractions, restaurants, cuisine tags and the street network, imported per region into PostGIS.
- **Type:** open data, ODbL. Geofabrik publishes regional `.osm.pbf` extracts.
- **Quota / card:** none stated. Owner-reported text from the download server (2026-11-12; the page URL was not given, the assistant could not open it): "Our download server at https://download.geofabrik.de has excerpts and derived data from the OpenStreetMap dataset available for free download. Most of these files are updated every day – any change you upload to OpenStreetMap should be on our download server the next day." The owner found **no limit or request about automated downloads** in the pages read; the pages were not searched exhaustively by the assistant.
- **Licence statement (owner-reported, same date):** "All OpenStreetMap derived data on the download server is licensed under the Open Database License 1.0. You may use the data for any purpose, but you have to acknowledge OpenStreetMap as the data source. Derived databases have to retain the same license." This matches `docs/data-model.md` section 6.
- **Commercial use:** "The ODbL allows you to use the OSM data for any purpose you like. This includes personal, community, educational, commercial or governmental."
- **Caching / storage:** allowed. If an adapted OSM database is used publicly, it is a Derivative Database and must be offered under ODbL on request. Independent data kept alongside (user trips, prices, notes, photos) forms a Collective Database and is not affected. See `docs/data-model.md`.
- **Attribution:** "© OpenStreetMap contributors" with a link to the copyright page, visible without interaction; a splash screen or a corner of the map are both acceptable.
- **Coverage / quality:** global. Attractions are well mapped in tourist areas. Restaurants: presence is good in cities, `cuisine` is common, `opening_hours` is patchy and can be stale. There is no popularity or rating signal.
- **Measured (spike S2, 2026-11-12):** extract sizes for Austria, Czechia, Hungary, Italy and Japan are 0.33–2.57 GB (6.9 GB together); see `docs/spikes/s2-data-findings.md`. Downloads from `download.geofabrik.de` worked with an identifying User-Agent, and the Phase 2 import workflow downloaded the Austria extract (2026-11-12). Terms and cadence: see the owner-reported text above.
- **Risks:** data quality varies by country; tags are free-form; the import pipeline is ours to maintain.
- **Exceeded:** n/a.
- **Fallback:** Overture Places and FSQ OS Places to fill coverage gaps.
- **MVP:** **Yes.** Tier **ANY**.
- Sources: <https://osmfoundation.org/wiki/Licence/Licence_and_Legal_FAQ>, <https://osmfoundation.org/wiki/Licence/Attribution_Guidelines>, <https://wiki.openstreetmap.org/wiki/Key:tourism>, <https://wiki.openstreetmap.org/wiki/Key:cuisine>

### 4.2 Overpass API (public instances) — ✅ Verified

- **Use:** ad-hoc queries of OSM data by tag and area.
- **Type:** open-source software; community-run public servers.
- **Quota:** main instance: under 10,000 queries and 1 GB per day is fine for one-off use; "If you set something up that uses the Overpass API regularly, then divide those numbers by 100", and an app's usage is the sum over all its users.
- **Card:** no.
- **Commercial use:** "Commercial use should use self-hosted or paid Overpass servers."
- **Caching / storage:** caching is expected; data is ODbL.
- **Attribution:** OpenStreetMap.
- **Coverage / quality:** global, near-live OSM.
- **Risks:** overload and load shedding; a unique User-Agent is required; other public instances have their own, changeable policies.
- **Exceeded:** HTTP 429 or 406; pause 30 seconds; repeated abuse is blocked.
- **Fallback:** regional extract import (4.1).
- **MVP:** **No.** Tier **DEV**: useful for exploring tag coverage of a pilot region during development.
- Sources: <https://wiki.openstreetmap.org/wiki/Overpass_API>, <https://dev.overpass-api.de/overpass-doc/en/preface/commons.html>

### 4.3 Wikidata — ✅ Verified

- **Use:** a notability signal for attractions (number of Wikipedia language editions, instance-of class), joined through the OSM `wikidata=*` tag. This replaces the ratings that free sources do not have.
- **Type:** open data.
- **Quota:** no fixed number on the pages read; clients must send a descriptive User-Agent, back off on HTTP 429 and respect the Wikimedia-wide rate limits. Dumps are recommended for large extractions; the query service is for narrowly scoped queries.
- **Card:** no.
- **Commercial use:** allowed; "All structured data ... is released into the public domain under Creative Commons Zero."
- **Caching / storage:** unrestricted.
- **Attribution:** not required (CC0); crediting is good practice.
- **Coverage / quality:** excellent for notable sights, absent for ordinary POIs and almost all restaurants.
- **Risks:** notability is not the same as "worth visiting"; bias towards well-documented regions.
- **Exceeded:** HTTP 429 with `Retry-After`.
- **Fallback:** OSM-only signals (`tourism=attraction`, `heritage=*`, presence of `wikipedia=*`).
- **MVP:** **Yes**, fetched at region-import time, never at request time. Tier **ANY**.
- Sources: <https://www.wikidata.org/wiki/Wikidata:Data_access>, <https://www.wikidata.org/wiki/Wikidata:Licensing>, <https://wiki.openstreetmap.org/wiki/Key:wikidata>

### 4.4 Overture Maps — places theme — ✅ Verified

- **Use:** supplementary POI and business coverage (names, categories, addresses, websites, phones, existence confidence).
- **Type:** open data.
- **Quota / card:** none.
- **Commercial use:** allowed. Published under CDLA Permissive 2.0 and Apache 2.0; "It contains no OpenStreetMap data and carries none of the share-alike obligations of the Open Database License".
- **Caching / storage:** allowed.
- **Attribution:** Overture Maps Foundation and the source listed per record.
- **Coverage / quality:** tens of millions of places; October 2026 counts include Meta (60.3 M), BrightQuery (15.8 M), Microsoft (5.9 M) and Foursquare (3.8 M). A `confidence` score separates reliable records from doubtful ones. **No opening-hours, price or rating field.**
- **Risks:** schema churn (the `categories` property was removed in the September 2026 release in favour of `taxonomy` and `basic_category`); matching against OSM records is our problem.
- **Exceeded:** n/a.
- **Fallback:** FSQ OS Places.
- **MVP:** **No.** Add after the MVP if OSM restaurant coverage in a pilot region proves thin. Tier **ANY**.
- Sources: <https://docs.overturemaps.org/guides/places/>, <https://docs.overturemaps.org/schema/reference/places/place/>

### 4.5 Foursquare Open Source Places — ✅ Verified

- **Use:** supplementary global POI list with categories.
- **Type:** open data, Apache 2.0.
- **Quota:** none stated; access is through the Foursquare Places Portal with an account and access token (an Iceberg catalog), which replaced the public S3 bucket.
- **Card:** not stated.
- **Commercial use:** allowed under Apache 2.0.
- **Caching / storage:** allowed.
- **Attribution:** required per the Apache 2.0 notice in the access documentation.
- **Coverage / quality:** "100M+" POIs in 200+ countries with 1,000+ categories. The published schema has name, location, address, category, website, phone, `date_closed` and `unresolved_flags`. **It has no hours, price, rating, photo or tip columns.**
- **Risks:** the delivery mechanism has already changed once; account required.
- **Exceeded:** n/a.
- **Fallback:** Overture Places (which already includes a Foursquare-derived subset).
- **MVP:** **No.** Tier **ANY**.
- Sources: <https://opensource.foursquare.com/os-places/>, <https://docs.foursquare.com/data-products/docs/access-fsq-os-places>, <https://docs.foursquare.com/data-products/docs/places-os-data-schema>

### 4.6 OpenTripMap — ◐ Partly verified (product page only)

- **Use:** hosted tourist-POI API built from OSM, Wikidata and Wikipedia.
- **Type:** hosted API over ODbL data.
- **Quota / card:** the price page was not read; unknown.
- **Commercial use:** not stated on the product page.
- **Caching / storage:** "You can pre-fetch, index, store, or cache data".
- **Attribution:** ODbL.
- **Coverage / quality:** "over 10 million tourist attractions and facilities".
- **Risks:** the site footer reads "© 2019" and the documentation page returned no content; maintenance status is doubtful. It adds nothing that the OSM + Wikidata import does not already give.
- **MVP:** **No.**
- Source: <https://dev.opentripmap.org/product>

---

## 5. Restaurants, place search, prices and ratings (commercial APIs)

### 5.1 Google Places API (New) — ✅ Verified

- **Use:** place search and details including `priceLevel`, `priceRange`, `rating` and `regularOpeningHours`.
- **Type:** paid, with a monthly free cap per SKU.
- **Quota:** free monthly calls per SKU: 10,000 (Essentials), 5,000 (Pro), 1,000 (Enterprise). `priceLevel`, `priceRange`, `rating`, `userRatingCount` and `regularOpeningHours` are all **Enterprise** fields, so 1,000 free Place Details calls per month. Beyond that, Place Details Enterprise is listed at $20.00 per 1,000.
- **Card:** a billing account is required by Google's billing model (not re-confirmed verbatim on the pages read).
- **Commercial use:** allowed.
- **Caching / storage:** "You must not pre-fetch, cache, or store Places API content beyond the allowed exceptions, although the place_id is exempt".
- **Attribution:** Google logo and third-party attributions; "Places API results displayed on a map must be shown on a Google Map".
- **Coverage / quality:** the best available for restaurants, hours and price level.
- **Risks:** incompatible with this design on three counts: results cannot be stored in the itinerary database, they cannot be drawn on a MapLibre/OSM map, and cost is uncapped above the free allowance.
- **Exceeded:** billed.
- **MVP:** **No. Rejected.**
- Sources: <https://developers.google.com/maps/billing-and-pricing/pricing>, <https://developers.google.com/maps/billing-and-pricing/overview>, <https://developers.google.com/maps/documentation/places/web-service/data-fields>, <https://developers.google.com/maps/documentation/places/web-service/policies>

### 5.2 Foursquare Places API — ⚠ Not verified

- **Use:** place search and details; price, rating, hours, photos and tips as premium fields.
- **Type:** commercial, usage-priced.
- **Quota:** the official pricing page could not be read. Search results conflict: some cite 10,000 free "Pro" calls per month, a later source cites 500 after a June 2026 pricing change. Premium fields appear to be billed from the first call.
- **Card / caching / attribution:** not verified.
- **Risks:** unknown terms; pricing has changed recently.
- **MVP:** **No.** Not selectable until the official pricing and licence terms are read.
- Unverified pointers: <https://docs.foursquare.com/developer/reference/v2-pricing>, <https://foursquare.com/pricing/>

### 5.3 Yelp Places API — ◐ Partly verified

- **Use:** business search with `price` ("$$") and ratings.
- **Type:** paid plans with a free trial ("start your free trial"). No free tier is described.
- **Quota / card:** plan details not captured.
- **Commercial use:** consumer-product use requires a "Yelp Places Enterprise application".
- **Caching / attribution:** display requirements apply; details not captured.
- **Coverage / quality:** strong in North America, uneven elsewhere.
- **MVP:** **No. Rejected**: a trial is not a basis for an MVP.
- Sources: <https://docs.developer.yelp.com/docs/places-intro>, <https://docs.developer.yelp.com/docs/getting-started>

**Conclusion for restaurants:** the MVP uses OSM for restaurant existence, location and cuisine.
Opening hours are out of scope (ADR 003). Price comes from the user; see section 13.

---

## 6. Opening hours

> **Not used.** Out of scope since ADR 003 (2026-11-12). This section is kept only as a record of
> what was read; its MVP verdict no longer applies.

### 6.1 OSM `opening_hours` tag — ✅ Verified (tag documentation)

- **Use:** deciding whether an attraction or restaurant is open in a candidate time slot.
- **Type:** open data (part of 4.1); parsing is done by a library in the backend.
- **Quota / card:** none.
- **Commercial use / storage / attribution:** as OSM (ODbL).
- **Coverage / quality:** partial. Many POIs have no value; values can be outdated; seasonal and holiday rules are common in tourist areas.
- **Risks:** "The syntax is quite complex". The wiki notes that some consumer apps "will fail with more complex data" and gives an example that "fails on openingh (Aug 2026)". Public-holiday rules (`PH`) need a per-country holiday calendar, and the meaning of `24/7` on holidays is disputed.
- **Exceeded:** n/a.
- **Fallback:** a three-state result — `open`, `closed`, `unknown`. Unknown is never treated as closed; it lowers the item's confidence and is shown to the user, who can override the hours for an item.
- **MVP:** **Yes.** The parser library is chosen in a Phase 0 spike from the implementations listed on the wiki. If none is adequate, support a strict subset (weekday ranges, time ranges, `24/7`, `off`) and return `unknown` for everything else. Public holidays are ignored in the MVP and flagged.
- Source: <https://wiki.openstreetmap.org/wiki/Key:opening_hours>

---

## 7. Walking and driving routes, route matrices

### 7.1 Valhalla (self-hosted) — ◐ Partly verified (repository and Docker README; API reference page not reachable)

- **Use:** walking, driving and cycling routes and time/distance matrices for the planner; route geometry for the map.
- **Type:** open source, MIT. Docker images `ghcr.io/valhalla/valhalla` and `ghcr.io/valhalla/valhalla-scripted`; tiles are built from OSM PBF files dropped into a mounted directory.
- **Quota / card:** none.
- **Commercial use:** allowed.
- **Caching / storage:** unrestricted; results derive from ODbL data.
- **Attribution:** OpenStreetMap.
- **Coverage / quality:** wherever a region has been imported. The README lists "time+distance matrix computation, isochrones, elevation sampling, map matching and tour optimization". One tile set serves all travel modes. Time-zone data is needed for time-dependent routing.
- **Risks:** we run it. Memory and build-time figures for a regional extract were not found in the pages read and must be measured in a spike. Matrix request limits and endpoint details must be confirmed from the API reference.
- **Exceeded:** n/a.
- **Fallback:** straight-line distance × detour factor ÷ mode speed, marked `estimated` (see `docs/architecture.md`).
- **MVP:** **Yes.** Tier **ANY**.
- Sources: <https://github.com/valhalla/valhalla>, <https://github.com/valhalla/valhalla/blob/master/docker/README.md>

### 7.2 OSRM (self-hosted) — ✅ Verified

- **Use:** routes and a `table` (matrix) service.
- **Type:** open source, BSD-2-Clause; Docker image available.
- **Quota / card:** none.
- **Coverage / quality:** very fast. One preprocessed graph per profile. Planet car profile needs around 123 GiB of RAM at runtime (2021 figures); "sizes scale roughly linear with input data size".
- **Risks:** separate datasets for foot, car and bike multiply memory and build time; no time-zone or schedule awareness.
- **MVP:** **No.** Kept as the alternative engine if the Valhalla spike disappoints.
- Sources: <https://github.com/Project-OSRM/osrm-backend>, <https://github.com/Project-OSRM/osrm-backend/wiki/Disk-and-Memory-Requirements>

### 7.3 FOSSGIS public routing servers (OSRM and Valhalla demos) — ✅ Verified

- **Use:** public routing endpoints `routing.openstreetmap.de` and `valhalla1.openstreetmap.de`.
- **Type:** donation-funded community service.
- **Quota:** at most one request per second.
- **Card:** no.
- **Commercial use:** allowed only when the service is not an essential part of the online offering; high-traffic sites may not use it.
- **Caching / storage:** bulk downloading is prohibited.
- **Attribution:** OpenStreetMap; a valid identifying User-Agent is mandatory.
- **Risks:** "Wir garantieren keine Verfügbarkeit" (no availability guarantee); each service is a single server; permission can be withdrawn at any time. The Valhalla maintainers state the demo "won't be usable for any production service for third parties", and matrix calls are among the most tightly limited.
- **Exceeded:** blocking.
- **MVP:** **No.** Tier **DEV**, for trying requests before the local container is up.
- Sources: <https://fossgis.de/arbeitsgruppen/osm-server/nutzungsbedingungen/>, <https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server>, <https://github.com/valhalla/valhalla/discussions/3373>

### 7.4 openrouteservice (hosted) — ⚠ Not verified

- **Use:** hosted directions, matrix, isochrones.
- **Type:** free hosted plan from HeiGIT; the engine is open source and self-hostable.
- **Quota:** the plans page redirects to an account site that could not be read. Search results give, for the free Standard plan, Directions 2,000/day and Matrix 500/day at 40/minute, with a matrix cap of 3,500 elements per request; other results differ.
- **Card / commercial use / caching / attribution:** not verified.
- **MVP:** **No.** The most plausible **hosted fallback** for routing, but only after its plan and terms pages are read.
- Unverified pointer: <https://openrouteservice.org/plans/>

### 7.5 GraphHopper Directions API (Free plan) — ◐ Partly verified

- **Use:** hosted routing, matrix, optimisation.
- **Type:** commercial free tier; the routing engine is Apache 2.0, and the Matrix API is described as part of the commercial offering.
- **Quota:** 500 credits/day, at most 5 locations per request, 1 vehicle.
- **Card:** "No credit card required."
- **Commercial use:** the plan table has a "For Commercial Use" row whose value for Free was not readable in the fetched page.
- **Risks:** five locations per request is too small for itinerary matrices.
- **MVP:** **No.** Tier **DEV**.
- Sources: <https://www.graphhopper.com/pricing/>, <https://github.com/graphhopper/graphhopper>

---

## 8. Public transport, GTFS and GTFS-Realtime

Public transport is **not in the MVP**. The findings below fix the options for Phase 10.

### 8.1 Transitous — ✅ Verified

- **Use:** door-to-door public-transport journey planning through the MOTIS 2 API at `api.transitous.org`.
- **Type:** community-run free service on open data and open-source software.
- **Quota:** no hard number, but "Many requests (> 720 requests / 24h) of type /plan, /one-to-many, /one-to-all" must be coordinated with the operators.
- **Card:** no.
- **Commercial use:** "commercial use is not allowed". Eligibility requires **all** of: the project is open source, is not commercial, is light on resources, and follows the usage policy.
- **Caching / storage:** scraping through the API is unnecessary; the source dataset can be downloaded.
- **Attribution:** a visible link to <https://transitous.org/sources/>, plus each source's conditions and OSM attribution. A User-Agent with app name, version and contact is required.
- **Coverage / quality:** international, wherever open GTFS feeds exist; quality follows the feeds.
- **Risks:** "best-effort basis"; the operators "reserve the right to stop providing it to any consumer at any time".
- **Exceeded:** access can be removed.
- **Fallback:** self-hosted MOTIS (8.2).
- **MVP:** **No.** Phase 10 option **only if** the project is published as open source and stays non-commercial. Tier **PERSONAL / REPLACE**.
- Sources: <https://transitous.org/>, <https://transitous.org/api/>

### 8.2 MOTIS (self-hosted) — ✅ Verified (repository)

- **Use:** self-hosted multimodal routing from GTFS feeds plus an OSM extract; also consumes GTFS-RT.
- **Type:** open source, MIT. Latest release seen: v2.11.4. Inputs: one `osm.pbf`, multiple GTFS or NeTEx feeds, GTFS-RT and SIRI real-time feeds. REST API with an OpenAPI description.
- **Quota / card:** none.
- **Commercial use:** allowed for the software; **each GTFS feed carries its own licence**.
- **Coverage / quality:** exactly the feeds loaded.
- **Risks:** feed discovery, licence review and refresh are ongoing work; resource needs are not documented in the pages read.
- **MVP:** **No.** Phase 10 default if Transitous is not permitted. Tier **ANY** (subject to feed licences).
- Sources: <https://github.com/motis-project/motis>, <https://github.com/motis-project/motis/blob/master/docs/setup.md>

### 8.3 OpenTripPlanner (self-hosted) — ◐ Partly verified (repository)

- **Use:** self-hosted multimodal trip planner from GTFS and OSM, GraphQL APIs, real-time updates.
- **Type:** open source (LGPL, inferred from the licence file in the repository), Java.
- **Risks:** JVM memory footprint; Java version and memory guidance were not read.
- **MVP:** **No.** Alternative to MOTIS.
- Source: <https://github.com/opentripplanner/OpenTripPlanner>

### 8.4 Transitland — ✅ Verified

- **Use:** hosted REST API for stops, routes and departures; hosted transit routing; feed archive.
- **Type:** commercial with free plans.
- **Quota:** Explorer (free): REST 5,000/month, routing 1,000/month, **no commercial use**. Hobbyist/Academic (free by application): REST 50,000/month, routing 100,000/month, no commercial use. Pay As You Go: 10,000 free per month for each of REST and routing, then metered ($1.50 per 1,000 REST requests; routing from $2.00 per 1,000 units), commercial use included.
- **Card:** not stated; Pay As You Go is metered billing.
- **Caching / storage:** governed by the terms and by each feed's licence.
- **Attribution:** "Transitland" name or logo with a link to the terms page, visible to end users, plus feed attributions.
- **Risks:** routing units multiply quickly (a transit route costs 2 units, a matrix 4).
- **Exceeded:** metered on PAYG; not stated for free plans.
- **MVP:** **No.** Tier **DEV**.
- Sources: <https://www.transit.land/plans-pricing/>, <https://www.transit.land/terms>

### 8.5 Mobility Database — ✅ Verified

- **Use:** finding GTFS, GTFS-Realtime and GBFS feed URLs for a region when self-hosting MOTIS.
- **Type:** open catalog maintained by MobilityData.
- **Quota:** not stated. "Everyone has free access"; an account is needed to use the API.
- **Card:** no.
- **Commercial use:** the FAQ answers "Yes" and points to its terms. Catalog metadata is CC0; "Individual transit feeds are subject to the terms & conditions of their own respective data provider."
- **Coverage / quality:** 6,000+ feeds from 100+ countries, checked daily for updates.
- **Risks:** feed licences vary; some real-time feeds need their own API keys.
- **MVP:** **No.** Phase 10. Tier **ANY** for the catalog.
- Sources: <https://mobilitydatabase.org/>, <https://mobilitydatabase.org/faq>, <https://github.com/MobilityData/mobility-database-catalogs>

### 8.6 GTFS Schedule and GTFS Realtime (standards) — ◐ Partly verified

- GTFS Schedule describes static timetables; GTFS Realtime carries `TripUpdate`, `VehiclePosition` and `Alert` messages (newer additions include `Shape` and `TripModifications`).
- **Relevance:** schedule data is enough for planning days ahead. Realtime only matters on the travel day and is **out of scope until after Phase 10**; MOTIS can consume it when needed.
- Sources: <https://gtfs.org/documentation/overview/>, <https://gtfs.org/documentation/realtime/reference/>

### 8.7 Google Routes API (transit) — ◐ Partly verified

- Transit routing is a paid Routes SKU inside the same billing model as section 5.1. **Rejected** for the same reasons.
- Source: <https://developers.google.com/maps/billing-and-pricing/pricing>

---

## 9. Weather

Weather is not among the stated product goals. It is evaluated because the brief asks for it,
and it is **excluded from the MVP**. If approved later it is an informational overlay only.

### 9.1 Open-Meteo — ✅ Verified

- **Use:** forecast up to 16 days, historical and climate data, by coordinate.
- **Type:** free non-commercial API; paid commercial plans; server is open source (AGPLv3) and self-hostable.
- **Quota:** "Less than 10'000 API calls per day, 5'000 per hour and 600 per minute"; 300,000 calls/month. No API key on the free tier.
- **Card:** no.
- **Commercial use:** **not allowed on the free API.** Non-commercial includes "Private or non-profit websites or apps that do not have subscriptions or advertising"; apps with subscriptions or advertisements are commercial.
- **Caching / storage:** not restricted on the pages read.
- **Attribution:** CC BY 4.0; a link must be shown next to the data.
- **Coverage / quality:** global, multiple national models.
- **Risks:** a change in the app's business model changes its eligibility.
- **Exceeded:** "We reserve the right to block applications and IP addresses that misuse our service".
- **Fallback:** MET Norway.
- **MVP:** **No.** If weather is approved: tier **PERSONAL / REPLACE**.
- Sources: <https://open-meteo.com/en/terms>, <https://open-meteo.com/en/pricing>, <https://open-meteo.com/en/licence>, <https://open-meteo.com/en/docs>

### 9.2 MET Norway Locationforecast — ✅ Verified

- **Use:** forecast "for any given coordinate for the next nine days".
- **Type:** free open government data service.
- **Quota:** keep total traffic below 20 requests/second per application; more "requires special agreement".
- **Card:** no.
- **Commercial use:** no non-commercial restriction appears in the terms or licence pages read. Data is under NLOD 2.0 and CC BY 4.0.
- **Caching / storage:** caching is required: do not repeat a request before its `Expires` time; use `If-Modified-Since`. Coordinates must be truncated to at most 4 decimals (5+ returns 403 on new products).
- **Attribution:** credit "MET Norway" with a link to the licence.
- **Coverage / quality:** global coordinates accepted; highest resolution in the Nordics.
- **Risks:** "There are no guarantees of delivery ... or possibilities to obtain an SLA." A unique identifying User-Agent is mandatory; mobile apps must not fetch while not in use, and a proxy is recommended, which matches the backend-only rule here.
- **Exceeded:** throttling or blocking without warning.
- **Fallback:** Open-Meteo.
- **MVP:** **No.** If weather is approved, this is the commercially safe default. Tier **PERSONAL**, commercial-compatible on the terms read.
- Sources: <https://api.met.no/doc/TermsOfService>, <https://api.met.no/doc/License>, <https://api.met.no/weatherapi/locationforecast/2.0/documentation>

OpenWeatherMap was not evaluated (its pages were not read).

---

## 10. Country and currency data

### 10.1 Static seed: GeoNames `countryInfo` and mledoze/countries — ◐ Partly verified

- **Use:** country list, ISO codes, default currency per country, currency name and symbol. Loaded once into the database and refreshed with releases.
- **Type:** open data. GeoNames is CC BY 4.0. mledoze/countries is ODbL 1.0 (flags excluded) and lists `currencies` keyed by ISO 4217 code with `name` and `symbol`, in JSON, YAML, CSV and XML.
- **Quota / card:** none.
- **Commercial use:** allowed under both licences.
- **Attribution:** GeoNames credit; ODbL notice for mledoze/countries.
- **Coverage / quality:** all countries and territories; changes are rare.
- **Risks:** the GeoNames `countryInfo.txt` column list was not re-read. Currency symbols and number formatting per locale should come from the platform's `Intl` support, to be confirmed in Phase 1.
- **MVP:** **Yes.** Tier **ANY**.
- Sources: <https://github.com/mledoze/countries>, <https://www.geonames.org/export/>

### 10.2 REST Countries (API) — ◐ Partly verified

- **Use:** hosted country data API.
- **Finding:** the service now presents a v5 API that uses a bearer API key ("Get an API key") with plans; "The free tier covers most prototypes and small apps". Plan limits were not read.
- **MVP:** **No.** A network dependency and an account for data that changes a few times a year is unjustified.
- Source: <https://restcountries.com/>

---

## 11. Exchange rates

**Not used since ADR 017 (2026-11-13): the app has no currencies.** Kept for the record.

Rates were to be used only to compare a restaurant price with the user's budget in another currency.
They are **reference rates**: the UI must label converted amounts as approximate.

### 11.1 Frankfurter — ✅ Verified

- **Use:** daily reference rates, fetched once a day by the backend and stored.
- **Type:** free public API; open source (MIT) and self-hostable with Docker.
- **Quota:** "There are no quotas. Requests are rate-limited to prevent abuse, but there are no monthly or daily caps." No API key.
- **Card:** no.
- **Commercial use:** "Yes. Blended rates are Frankfurter's own calculation and free to use. Direct queries to individual provider endpoints remain subject to each provider's terms."
- **Caching / storage:** "Storing daily observations locally for caching or historical analytics is encouraged".
- **Attribution:** none stated for blended rates; individual providers' terms apply to provider-specific endpoints.
- **Coverage / quality:** 219 currencies from 111 central banks and official sources; history to 1948; "These are reference rates, not live market quotes."
- **Risks:** a single-maintainer public service; the API moved from v1 to v2.
- **Exceeded:** rate limiting.
- **Fallback:** ECB XML (11.2), then fawazahmed0 (11.4); or self-host Frankfurter.
- **MVP:** **Yes.** Tier **PERSONAL**; **ANY** when self-hosted.
- Sources: <https://frankfurter.dev/>, <https://github.com/lineofflight/frankfurter>

### 11.2 European Central Bank euro reference rates — ✅ Verified

- **Use:** authoritative daily EUR-based rates as XML or CSV.
- **Type:** open publication.
- **Quota / card:** none stated.
- **Commercial use / storage:** free use provided that the information "must appear accurately and the ECB must be cited as the source".
- **Coverage / quality:** major currencies against the euro only; "usually updated at around 16:00 CET every working day, except on TARGET closing days".
- **Risks:** "published for information purposes only. Using the rates for transaction purposes is strongly discouraged." Limited currency list.
- **MVP:** **No — first fallback.** Tier **ANY**.
- Sources: <https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html>, <https://www.ecb.europa.eu/services/disclaimer/html/index.en.html>

### 11.3 ExchangeRate-API open access endpoint — ✅ Verified

- **Use:** keyless daily rates.
- **Quota:** rate limited; one request per day (or hour) is always safe; HTTP 429 for 20 minutes when limited.
- **Commercial use:** allowed for "personal or commercial currency conversion purposes".
- **Caching / storage:** caching allowed; "not allowed to re-distribute it".
- **Attribution:** required.
- **MVP:** **No.** The redistribution ban and attribution add constraints Frankfurter does not have.
- Source: <https://www.exchangerate-api.com/docs/free>

### 11.4 fawazahmed0/exchange-api — ✅ Verified (repository)

- **Use:** static daily rate files on a CDN, with a secondary Cloudflare host.
- **Type:** open data, CC0-1.0. "No Rate limits" (project's own claim).
- **Risks:** no SLA; the project itself says "Please include Fallback mechanism in your code"; sources of the rates are not documented in the page read.
- **MVP:** **No — second fallback.**
- Source: <https://github.com/fawazahmed0/exchange-api>

---

## 12. Photo storage (future phase)

Photos are not in the MVP. The data model reserves the tables (see `docs/data-model.md`).

### 12.1 On-device storage — ✅ Verified (Expo module documentation)

- **Use:** keep photo files in the app's own storage and reference them from the local SQLite database; pick images with the system picker.
- **Type:** local; no provider.
- **Quota / card:** device storage.
- **Risks:** photos are lost with the device unless backed up. On Android, "full access to the media library ... is allowed only for apps that require broad access to photos" under Google Play's photo and video permissions policy, so the app must use the picker instead of broad library access. EXIF location handling needs explicit care.
- **MVP:** not applicable. **Recommended first step of the photo phase.** Tier **ANY**.
- Sources: <https://docs.expo.dev/versions/latest/sdk/imagepicker/>, <https://docs.expo.dev/versions/latest/sdk/media-library/>, <https://docs.expo.dev/versions/latest/sdk/sqlite/>

### 12.2 Cloudflare R2 — ✅ Verified (pricing page)

- **Use:** S3-compatible object storage for optional cloud backup.
- **Quota:** free each month: 10 GB-month storage, 1 million Class A operations, 10 million Class B operations; egress is free. The free tier applies to Standard storage only.
- **Card:** not stated on the pricing page; **confirm before choosing**.
- **Commercial use:** allowed.
- **Exceeded:** billed: $0.015 per GB-month, $4.50 per million Class A, $0.36 per million Class B.
- **Risks:** uncapped billing beyond the free tier.
- **Tier:** **PERSONAL** within the free tier; commercial-capable when paid.
- Source: <https://developers.cloudflare.com/r2/pricing/>

### 12.3 Backblaze B2 — ✅ Verified (pricing page)

- **Quota:** "First 10GB storage is always free"; then $6.95 per TB per 30 days; free egress up to 3× stored data.
- **Card:** not stated.
- **Tier:** **PERSONAL** within the free allowance.
- Source: <https://www.backblaze.com/cloud-storage/pricing>

### 12.4 Supabase Storage (Free plan) — ✅ Verified

- **Quota:** 1 GB file storage, 500 MB database, 5 GB egress; limit of 2 active projects.
- **Risks:** "Free projects are paused after 1 week of inactivity."
- **Tier:** **DEV**.
- Source: <https://supabase.com/pricing>

### 12.5 Self-hosted S3-compatible storage — ✅ Verified (repositories)

- **MinIO:** the community repository was archived on 2026-04-25 and states "THIS REPOSITORY IS NO LONGER MAINTAINED"; the community edition is source-only (AGPLv3). **Do not adopt.**
- **SeaweedFS:** Apache 2.0, with an S3 gateway. Candidate for local development if an S3 API is needed.
- Sources: <https://github.com/minio/minio>, <https://github.com/seaweedfs/seaweedfs>

---

## 13. Feasibility of restaurant price categories

### What the sources actually provide

| Source | Price information | Rating | Usable in this app |
|---|---|---|---|
| OpenStreetMap | No documented price-range key (`Key:price_range` has no wiki page). `fee=*` concerns entrance fees. | None | Existence, cuisine, hours only |
| Overture Places | None in the schema | None | Coverage only |
| Foursquare OS Places | None in the schema | None | Coverage only |
| Google Places | `priceLevel`, `priceRange` (Enterprise SKU) | Yes (Enterprise SKU) | No: storage forbidden, Google map required |
| Yelp | `price` ("$$") | Yes | No: trial only, Enterprise for consumer apps |
| Foursquare Places API | Premium field (not verified) | Premium (not verified) | Not selectable until verified |

**Conclusion:** provider price data is unavailable for the MVP and must not be simulated.
Ratings are not shown at all. The price model is therefore user-driven, with a provider slot
kept for the future.

### Proposed transparent price model

Every price shown is one **price record** with these attributes:

| Attribute | Values |
|---|---|
| `kind` | `provider_level`, `user_expected`, `user_actual` |
| `amount` | decimal, or null for a level-only provider record |
| `level` | 1–4, only when a provider supplies a level |
| `currency` | ISO 4217 code |
| `basis` | `per_person` or `total` (with `party_size` when total) |
| `source` | `user`, or the provider's name |
| `confidence` | `high` (user actual), `medium` (user expected), `low` (provider level or old record), `none` |
| `recorded_at` | timestamp; an FX snapshot is stored when a conversion is made |

**Displayed price category** for a restaurant, in order of precedence:

1. The user's recorded **actual** price (per person), confidence high.
2. The user's **expected** price or budget for that restaurant, confidence medium.
3. A **provider** level, if a licensed provider is ever added, confidence low.
4. Otherwise **"No price data"**. Nothing is inferred from cuisine or venue type in the MVP.

**Category bands** (budget / moderate / upscale / fine dining) are computed from the per-person
amount against band thresholds that the user can adjust per trip, in the trip currency. The
default thresholds are a product decision recorded in `docs/product-brief.md`, not provider data.

**Budget fit** compares the per-person amount, converted with the stored daily reference rate,
against the user's meal budget, and is labelled approximate whenever a conversion was involved.

The full schema is in `docs/data-model.md`.

---

## 14. Providers by suitability tier

**Development only (DEV):** public Overpass; public Nominatim; FOSSGIS OSRM and Valhalla demo
servers; `tile.openstreetmap.org`; GraphHopper Free; Stadia Maps Free; Transitland Explorer;
Supabase Free.

**Small personal production (PERSONAL):** OpenFreeMap public instance; Photon public instance;
Frankfurter public API; Geoapify Free; LocationIQ Free; MET Norway; Open-Meteo Free
(non-commercial only); Transitous (open-source and non-commercial only); Cloudflare R2 and
Backblaze B2 free allowances; MapTiler Free.

**Must be replaced, self-hosted or paid before a public commercial release (REPLACE):**
OpenFreeMap public instance (allowed, but no availability commitment); Photon public instance;
Open-Meteo Free; Transitous; Frankfurter public API (self-host it); Geoapify Free until the
commercial-use wording is confirmed in writing.

**Suitable at every stage (ANY):** MapLibre React Native; OSM extracts; GeoNames dump; Wikidata;
Overture; Foursquare OS Places; self-hosted Valhalla, MOTIS, Photon, PMTiles and Frankfurter;
mledoze/countries; ECB reference rates. ODbL share-alike and attribution obligations still apply.

## 15. Verification gaps to close before implementation

| Item | Why it matters | When |
|---|---|---|
| Geofabrik extract terms and cadence | Primary data pipeline | Phase 0. **Closed on 2026-11-12 from the owner's report** (not read by the assistant, which cannot reach the host): free download under ODbL with OSM credit, most files updated daily, no automated-download limit found. Re-check the page before any scheduled or larger-volume use |
| Valhalla resource needs for Japan, Austria, Czechia and Hungary (Italy measured in S3) | Sizing the routing container if self-hosted | Only if self-hosting is chosen |
| GeoNames dump readme (file names, columns) | Gazetteer import | Phase 2. **Still open**: `download.geonames.org` is not reachable from the development environment. The importer validates the layouts it reads and stops on a mismatch; the first real run of the workflow confirms or refutes them |
| openrouteservice plans and terms | Only hosted routing fallback worth having | Before adopting |
| Foursquare Places API pricing and terms | Only if a provider price source is ever wanted | Before adopting |
| Geoapify commercial-use wording | Pricing FAQ and terms disagree | Before commercial use |
| Cloudflare R2 payment-method requirement | Photo phase | Photo phase |
| MapLibre React Native offline packs | Offline maps, if ever wanted | Post-MVP |
