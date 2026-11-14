# ADR 025 — Multilingual place names

- **Status:** **Proposed; built and awaiting acceptance.** Requested by the owner on 2026-11-14 (the
  task brief "universal multilingual place-name resolution"); tried on fixtures only, not on the
  production database.
- **Date:** 2026-11-14
- **Related:** [`../multilingual-place-names.md`](../multilingual-place-names.md) (the full
  description), [`022-destination-and-attraction-photos.md`](022-destination-and-attraction-photos.md)
  (the Wikimedia adapter, its terms, queue and budget),
  [`021-trip-manager-redesign.md`](021-trip-manager-redesign.md) (decision 40: English names from
  `name:en`), [`011-attraction-selection-rule-v2.md`](011-attraction-selection-rule-v2.md) (the
  `wikidata` tag), [`../data-model.md`](../data-model.md)

## Context

Detour shows a place's OpenStreetMap `name:en` when it exists, else the local name (ADR 021,
decision 40). That covers 463 of Austria's 26,244 places (production, read 2026-11-14), and nothing
in a non-Latin script without `name:en`. Of the same places, 4,951 carry a Wikidata QID whose English
label is the established English name in most cases, and the Japan pilot will be mostly kanji. The
owner asked for a universal resolver: established English names first, the local name always kept,
safe romanization only, nothing invented, no translation of proper names, user corrections.

Constraints: no LLM or generative AI (rule 1); no new provider without an ADR with terms (rule 4);
never invent data (rule 5); plan generation makes no third-party call except Valhalla (ADR 004);
`geo` and `app` separate with no foreign key across them.

## Decision

1. **One resolver with a fixed hierarchy** (override; official English from the provider; Wikidata
   English label; English Wikipedia title; OSM `name:en`, `official_name:en`, `brand:en`,
   `short_name:en`, Latin `int_name`; the source's romanization; language-specific transliteration;
   generic transliteration; the original), confidence values centralised in `names/config.py`, steps
   restricted by class of place. Businesses keep their own name unless an official English, English
   brand or international name exists.
2. **No new provider.** Names come from Wikidata through the existing Wikimedia adapter (ADR 022: the
   same User-Agent, single queue, `maxlag`, `Retry-After`, daily budget), with `wbgetentities`
   (`props=labels|aliases|sitelinks`, `sitefilter=enwiki`, only the needed languages) and the
   Wikidata search Detour already uses for GeoNames ids, plus `nearcoord` and `wbgetclaims` for the
   operator-only coordinate fallback. The English Wikipedia title is read from Wikidata's sitelink;
   no Wikipedia host is called for names. Wikidata data is CC0 (terms read 2026-11-14, ADR 022).
3. **Transliteration only where the reading follows from the letters** (kana, Hangul, Greek,
   Cyrillic with a known language as specific; Cyrillic of unknown language, Georgian, Armenian,
   Devanagari as generic), computed on the fly, never stored, always labelled "Automatically
   romanized". Han characters, Arabic script, Hebrew, Thai and the other scripts are never
   transliterated. No machine translation is made; the type exists and is ignored by default.
4. **Storage:** OSM and GeoNames names stay where the import put them. New `geo.place_name` (Wikidata
   names, CC0, with expiry), `geo.place_name_lookup` (including negative answers, retried after 90
   days), `app.place_name_override` (user data, per installation) and `geo.place.alias_norm` (search
   forms). No provider payloads. Migration `0013`.
5. **Lazy, non-blocking enrichment:** in the background after a trip is created, generated or read,
   and by the `names` command; never in plan generation. Reads use stored names even when expired,
   then the original.
6. **Matching by identifiers first** (QID, Wikipedia sitelink, GeoNames id); coordinates only as a
   controlled, operator-run fallback with distance, country, city, class and exact-name rules and
   refusal of ambiguity.
7. **User override** ("Edit display name"): per installation and per place, reversible, the original
   kept, propagated to that installation's plan snapshots.
8. **API:** `PlaceName` (`names`) on place search results, place detail and itinerary items;
   `PUT`/`DELETE /v1/places/{id}/display-name`. `display_name` snapshots are unchanged in meaning.

## Alternatives

* **Machine translation (a provider or a local model):** rejected: rule 1, a paid provider, and
  proper names must not be translated.
* **A Unicode-wide transliteration library (Unidecode, anyascii):** rejected: it transliterates kanji
  by Chinese readings and Arabic without vowels, which reads as invented; Unidecode is GPL.
* **Copying all OSM names into the new table:** rejected: it duplicates ODbL data and multiplies
  rows; the resolver reads them where they are.
* **Fetching Wikidata names during the import for every QID:** deferred: the lazy run covers what
  users see; the `names` command can do a whole region when wanted.
* **A per-country rule table:** rejected: one resolver; the local language is read from the data
  (`name:<lang>` equal to `name`).

## Consequences

* New search forms make search find places by any name the data gives; the place search query gains
  a subquery over `geo.place_name` and an extra `LIKE` on `alias_norm` (trigram index).
* Wikimedia requests grow by about one per 50 entities; they share ADR 022's daily budget (3,000).
* `geo` grows by a few hundred bytes per enriched entity; Austria fully enriched is under 2 MB.
* An Austria re-import is needed for the newly kept tags (`official_name:*`, `short_name:*`,
  `brand:*`, `alt_name`, `old_name`); until then those steps are empty there.
* The CLAUDE.md working rule "tests accompany every phase" is met by the resolver, matching, adapter
  parsing, database and app tests; the Wikidata fixtures are in the documented shape, not recorded.

## Built (2026-11-14)

`services/api/src/detour_api/names/` (`config`, `scripts`, `translit`, `records`, `resolver`,
`matching`, `search`, `store`, `enrich`, `background`, `api`), the adapter's name questions in
`adapters/wikimedia.py`, migration `0013`, the importer's `alias_norm` and kept tags, the `names`
command, the API changes above, and the app's name lines and "Edit display name" on the place
screen. Not yet run against the production database.
