# Multilingual place names

Status: **built, awaiting acceptance** (2026-11-14, [ADR 025](decisions/025-multilingual-place-names.md)).
Code: `services/api/src/detour_api/names/`; migration `0013_multilingual_place_names`; tests
`tests/test_names_resolver.py`, `tests/test_names_matching.py`, `tests/test_names_db.py`; the app's
place screen (`PlaceDetailScreen.tsx`, "Edit display name").

The goal: show a reliable English-facing name whenever one exists, and always keep the original local
name. **Proper names are not translated.** Established, official or community-curated English names
come first; romanizations and transliterations only where they are safe, and always labelled.
Nothing here uses a language model, a translation service or a paid provider (CLAUDE.md rules 1 and
4).

## 1. Source priority (English interface)

One resolver (`names/resolver.py`) for every language, script and country. The steps and their
confidence are configuration (`names/config.py`, `NAMES_VERSION`), not code spread across the app.

| # | Step | Name type | Confidence | Where it comes from |
|---|---|---|---|---|
| 1 | `user_override` | `user_override` | 1.00 | `app.place_name_override` (this installation only) |
| 2 | `provider_official_en` | `official_english` | 0.99 | A provider record that marks an English name official. **No current source fills it** (OSM has no such marking); reserved for e.g. an operator feed |
| 3 | `wikidata_label_en` | `established_english` | 0.98 | Wikidata English label (`geo.place_name`) |
| 4 | `enwiki_title` | `established_english` | 0.97 | English Wikipedia sitelink title, a trailing "(qualifier)" removed (kept as an alias) |
| 5 | `osm_name_en` | `established_english` | 0.93 | OpenStreetMap `name:en` |
| 6 | `osm_official_name_en` | `official_english` | 0.85 | OSM `official_name:en` |
| 6a | `osm_brand_en` | `localized_brand` | 0.85 | OSM `brand:en` (businesses) |
| 7 | `osm_short_name_en` | `established_english` | 0.85 | OSM `short_name:en` |
| 8 | `osm_int_name` | `official_romanization` / `established_english` | 0.85 | OSM `int_name`, **only when written in Latin letters** (int_name is not assumed to be English) |
| 9 | `provider_romanization` | `official_romanization` | 0.85 | `name:<lang>-Latn`, `name:<lang>_rm`, `name:zh-Latn-pinyin`, `name:zh_pinyin` (the original's own language first) |
| 10 | `transliteration_specific` | `automatic_transliteration` | 0.70 | Made by Detour, language-specific (section 4) |
| – | `machine_translation` | `machine_translation` | 0.50 | **Never produced.** A stored one is ignored while `ALLOW_MACHINE_TRANSLATION` is false |
| 11 | `transliteration_generic` | `automatic_transliteration` | 0.35 | Made by Detour, generic tables, the last resort |
| 12 | `original` | `original` | – | The provider's local name |

If no step has a name, the original local name is shown. A name is never invented to fill the field.

### Classes of place

The class decides which steps may be used (`config.CLASS_STEPS`, `config.place_class`):

| Class | Places | Steps |
|---|---|---|
| `landmark` | Attractions (default) | All |
| `natural` | Peaks, lakes, waterfalls, glaciers | All |
| `settlement` | Cities, areas, countries | All; the local name is the item's native label (below) |
| `transport` | Stations, airports, ferry terminals | All but generic transliteration and `brand:en` |
| `business` | Restaurants, cafés, hotels, shops | Override, official English, `official_name:en`, `brand:en`, Latin `int_name`, original. **No** Wikidata or Wikipedia name, no `name:en` (usually a mapper's translation), no romanization, no transliteration: those remain search aliases |
| `street` | Streets (not imported today) | Override, official English, `official_name:en`, original |

The category is translated separately: the app shows the place's kind in English ("Attraction",
"Restaurant", "Café") from a fixed table, never as part of the name.

### Conflicts

When two candidates at or above 0.90 disagree: a candidate its source marks official wins; otherwise
the step order does. The other is kept as an alias (`aliases`) and the conflict is logged as
`place_name_conflict` with the place and both names. An override is never a conflict.

## 2. Matching places to Wikidata

`names/matching.py`, `names/enrich.py`. Identifiers first; never a similar name alone.

1. The QID Detour already holds: the OSM `wikidata` tag (`geo.place_signal.wikidata_id`), an area's
   `wikidata` tag, or a QID stored by an earlier lookup (`geo.place_name_lookup.qid`).
2. A Wikipedia page's item: the OSM `wikipedia` tag (`de:Festung Hohensalzburg`) asked of Wikidata
   by sitelink (`wbgetentities&sites=dewiki&titles=…`), so no other wiki is called.
3. A provider's external id: a city's GeoNames id through Wikidata's P1566; exactly one hit is used,
   none or several are recorded as such.
4. **Coordinates, a controlled fallback** (operator command only, `--coordinate-match`): a
   `nearcoord` search for the name around the place, then every rule must hold:
   the candidate has coordinates within the class's distance (landmark 300 m, business 100 m,
   transport 500 m, natural 2 km, settlement 10 km); its country (P17, read as an ISO code through
   P297) is the place's; its nearest gazetteer city is the place's; it is not of a class that is never
   a place (person, work, disambiguation page, taxon …); the place's normalised local name **equals**
   one of its labels or aliases in any language (after accent and ASCII folding); and exactly one
   candidate passes. Two passing candidates are ambiguous and neither is used.

## 3. Translation versus transliteration

Different things, kept apart by the name type:

| | Example | Type | Shown as |
|---|---|---|---|
| Established English name | Himeji Castle | `established_english` | The name |
| Romanized local name, from the source | Himejijō | `official_romanization` | The name |
| Romanized by Detour | Gyeongbokgung (from 경복궁) | `automatic_transliteration` | The name, with "Automatically romanized" |
| Original local name | 姫路城 | `original` | The second line |
| Machine translation | – | `machine_translation` | Never made |

A generated name is never labelled official (`auto_generated: true` in the API).

## 4. Language and script handling

The script comes from Unicode character names (`names/scripts.py`, ISO 15924 codes); the language
only from the source (`name:uk` equal to `name`), never guessed from the script. Language tags are
BCP 47 (`ja`, `ja-Latn`, `zh-Latn`, `und`).

Transliteration (`names/translit.py`), only where the reading follows from the letters:

| Script | Adapter | Level |
|---|---|---|
| Japanese kana (no kanji) | Hepburn, long vowel mark as macron | Specific (0.70) |
| Korean Hangul | Revised Romanization with the linking and ㄴ/ㄹ rules | Specific |
| Greek | ELOT 743 (simplified, accents dropped) | Specific |
| Cyrillic, language known | Russian/Belarusian BGN/PCGN without diacritics; Ukrainian national 2010; Bulgarian Streamlined; Serbian and Macedonian official Latin | Specific |
| Cyrillic, language unknown | The Russian table | Generic (0.35) |
| Georgian, Armenian | National tables | Generic |
| Devanagari | Letter by letter, final schwa dropped for Hindi, Marathi, Nepali | Generic |
| **Han (hanzi, kanji, hanja), Arabic and Urdu, Hebrew, Thai, Lao, Khmer, Burmese, Tibetan, other scripts** | **None**: the reading cannot be inferred | – |

Rules: Japanese kanji is never transliterated without a verified reading (only a source's
`name:ja-Latn` gives one). Chinese prefers the English name, then the source's Pinyin. Korean prefers
the English name, then the source's Revised Romanization, then Detour's. Thai, Arabic, Urdu, Hindi,
Greek and Cyrillic prefer English and the source's romanization first. A mixed name ("Café Москва")
keeps its Latin part; a name with any letter of an unsafe script ("Café 東京") is not transliterated
at all.

Latin-script languages (German, Spanish, Portuguese, French, Italian …): the established English name
if one exists, otherwise the original. Nothing is translated word by word. ASCII forms (Mönchsberg →
moenchsberg, Großglockner → grossglockner) are generated **for search only**; the Unicode name is
displayed.

## 5. Display

| Case | Line 1 | Line 2 | Note |
|---|---|---|---|
| Reliable English name | Hohensalzburg Fortress | Festung Hohensalzburg | |
| Known by its original name | Kunsthistorisches Museum | – | |
| Restaurant | Stiftskulinarium St. Peter | – | Kind line: "Restaurant" |
| Romanized by Detour | Gyeongbokgung | 경복궁 | "Automatically romanized" |
| No reliable English name | the original | – | |

The API returns `names` (`PlaceName`: `display`, `local`, `local_lang`, `type`, `source`,
`confidence`, `auto_generated`, `user_override`) on place search results, the place detail and every
itinerary item of an imported place. An item's `display_name` stays the stored snapshot (so a later
change of data cannot rewrite an accepted plan); `names` is resolved when the plan is read.

## 6. Search

Search is normalised separately from display (`textnorm.normalize_text`, `names/search.py`): Unicode
NFC, case folding, accents removed from Latin letters only, punctuation and whitespace collapsed, and
the German and Scandinavian ASCII spellings as extra forms. A place is found by its local name,
`name:en`, every other `name:*`, `int_name`, the source's romanizations, `official_name`,
`short_name`, `alt_name`, `old_name`, `brand`, Detour's transliteration (search only), and every name
stored from Wikidata (English label and aliases, Wikipedia title, labels in the local language). The
stored values are never modified by normalisation.

## 7. Storage and caching

* **OpenStreetMap and GeoNames names are not copied.** They stay in `geo.place.names_i18n`,
  `geo.place_source.tags` and `geo.city`, and are read from there. `geo.place.alias_norm` holds their
  normalised search forms only.
* **`geo.place_name`** holds what Wikidata gives: per entity (place, city, area), the English label,
  the English Wikipedia title, up to 5 aliases per language and the labels in English, `mul` and the
  local language. Never a provider answer. Primary key (entity, language, source, normalised value).
  Licence CC0 (Wikidata, sitelinks included).
* **`geo.place_name_lookup`** is the negative cache: `found`, `no_english` (an item with no English
  label or article) or `no_item`, with a retry date 90 days on. Network failures record nothing.
* **Lazy resolution:** names are fetched in the background after a trip is created, generated or read
  (the trip's cities, area, planned places and visited places), at most 100 entities a run, under
  their own advisory lock. Plan generation never waits for it and never calls Wikidata.
* **Retention:** stored names expire after 90 days. `prune` deletes expired names that nothing in the
  app names any more; names of places in itineraries, past-trip visits, overrides and trips' cities
  and areas are kept and refreshed when their lookup is due. Names and lookups of entities gone from
  `geo` are deleted.
* **Provider unavailable:** reads use stored names even after they expire, then the original. Trip
  generation is never blocked.

## 8. User overrides

`PUT /v1/places/{id}/display-name` (`{"name": "…"}`) and `DELETE` to undo; "Edit display name" on the
place screen. An override takes precedence over every provider name, applies to that place only (its
identifier, not similar names) and to that installation only, keeps the original name (recorded with
`approved_at`) and is reversible. The installation's plan snapshots that name the place follow; a new
generation takes it too.

## 9. Backfill

```bash
python -m detour_api.importer names austria --no-network
```

```bash
python -m detour_api.importer names austria --places 2000
```

The first rebuilds search aliases from the data already imported (no network; migration `0013`
already did this once). The second also looks up names for everything trips reference and for 2,000
of the region's attractions with a QID or Wikipedia tag, then prunes; `--coordinate-match` adds the
controlled coordinate fallback. The JSON report lists counts, the reasons for misses, the first 50
unresolved entities, the pruned rows and the tables' size.

## 10. Known limitations

* No source fills step 2 (official English provider name) today.
* `official_name:*`, `short_name:*`, `brand:*`, `alt_name` and `old_name` are kept only by imports run
  after this change; Austria needs one re-import to have them (search aliases from `name:*` exist
  already).
* Korean romanization handles the linking and ㄴ/ㄹ rules only, not every assimilation of Revised
  Romanization (e.g. nasalisation of ㄱ before ㄴ); the result is labelled as automatic.
* Kana long vowels written with a vowel letter (きょうと) stay as written (Kyouto, not Kyōto).
* Devanagari's inherent vowel is kept inside words (only a final one is dropped); Hindi names without an
  English or romanized name may read stiffly. Generic level, labelled.
* Thai, Arabic, Urdu, Persian and Hebrew names without an English or romanized name are shown in
  their script only.
* A city's local name needs a Wikidata label in the language most of its places are tagged in; a city
  without imported places gets its `mul` label or none.
* The coordinate fallback is not run in the background: places without a QID or a Wikipedia tag get
  Wikidata names only when the operator runs it.
* The Wikidata fixtures in the tests are written in the documented answer shapes, not recorded:
  Wikidata answered 429 to the development environment's shared address.
