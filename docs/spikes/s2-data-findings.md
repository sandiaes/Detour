# Spike S2 — Data quality and size: findings

- **Date:** 2026-11-12
- **Method:** Geofabrik regional extracts filtered with osmium and imported with osm2pgsql into
  PostGIS 16 on a GitHub Actions runner (run 1 of workflow "Spike S2 data quality"). Code:
  `spikes/s2-data/` (throwaway). Figures below were copied from the run's summary by the owner.
- **Caveats:** a simplified spike table, not the final `geo` schema. Objects mapped as both a
  node and a way are not de-duplicated. Geofabrik's terms and update cadence were **not** read
  (still a gap in `api-evaluation.md` section 15). The first query counted every `historic=*`
  object; see ADR 003.

## Extract and import sizes

| Country | Extract (MB) | Filtered (MB) | Rows | Table + indexes (MB) |
|---|---:|---:|---:|---:|
| Austria | 815.2 | 7.0 | 107,154 | 18.8 |
| Czechia | 952.5 | 7.0 | 141,362 | 24.7 |
| Hungary | 329.7 | 3.0 | 44,449 | 7.8 |
| Italy | 2,252.1 | 20.9 | 301,297 | 51.9 |
| Japan | 2,573.8 | 12.9 | 234,510 | 41.9 |
| **Total** | **6,923** | | | **145.1** |

Supabase Free allows 500 MB of database (`app-plan.md` section 1, read 2026-11-12). The 145 MB
is before the ADR 003 exclusions (which remove most `historic=*` rows) and before the final
schema, the `app` schema and database overhead.

## Quality (before the ADR 003 selection rule)

Restaurants:

| Country | Total | Named | Name EN | Name w/o Latin letters | Cuisine | Wikidata | Website |
|---|---:|---:|---:|---:|---:|---:|---:|
| Austria | 26,504 | 98% | 0% | 0% | 54% | 2% | 48% |
| Czechia | 17,826 | 94% | 1% | 0% | 36% | 1% | 38% |
| Hungary | 9,160 | 94% | 2% | 0% | 35% | 0% | 31% |
| Italy | 118,565 | 91% | 1% | 0% | 38% | 0% | 17% |
| Japan | 141,003 | 95% | 22% | 79% | 49% | 0% | 9% |

Attractions (all `historic=*` included): named 26–71%, English name 1–14%, Wikidata link 4–47%.
Japan: 68% of attraction names and 79% of restaurant names contain no Latin letters, and
`name:ja-Latn` or `name:ja_rm` exist for only 2–4%. The Phase 2 display rule must show the local
name and must not invent romanisations.

Opening-hours coverage was measured (restaurants 13–49%, attractions 1–4%) and is no longer
needed (ADR 003).

## Most common subclasses

- Austria: restaurant 21,038; wayside shrine 17,129; wayside cross 15,338; boundary stone 9,942;
  memorial 8,957; bomb crater 8,096; viewpoint 5,549; cafe 5,466; `tourism=attraction` 3,193.
- Czechia: wayside cross 34,969; memorial 30,337; boundary stone 24,030; restaurant 13,540;
  wayside shrine 9,465; viewpoint 5,788; `tourism=attraction` 3,104; ruins 1,907.
- Hungary: memorial 11,623; wayside cross 6,730; restaurant 6,608; viewpoint 2,762; cafe 2,552;
  `tourism=attraction` 2,310; museum 1,848; castle 886.
- Italy: restaurant 78,245; cafe 40,320; wayside shrine 28,373; `historic=building` 25,110;
  memorial 20,100; viewpoint 15,639; ruins 12,461; `tourism=attraction` 8,875;
  archaeological site 8,345.
- Japan: restaurant 111,645; memorial 33,120; cafe 29,358; wayside shrine 20,402;
  `tourism=attraction` 8,387; viewpoint 7,204; museum 6,778; archaeological site 3,514.

## What this decides, and what it does not

- Database size does not rule out Supabase Free for the `geo` data. D3 stays open because the
  API server and Valhalla still need a host (spike S3).
- Region readiness thresholds are the owner's decision; the numbers above are the input.
- Extract sizes (6.9 GB in total, Italy 2.25 GB, Japan 2.57 GB) are the inputs for S3.
