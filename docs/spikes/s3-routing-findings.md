# Spike S3 — Valhalla for Italy: findings

- **Date:** 2026-11-12
- **Method:** pyvalhalla 3.9.1 on a GitHub Actions runner (workflow "Spike S3 routing", run 1).
  Tiles built from the Geofabrik Italy extract; 50 x 50 matrices timed with the service limits
  raised. Code: `spikes/s3-routing/` (throwaway). Figures were copied from the run summary by
  the owner.
- **Caveats:** one machine, one run. Built without the optional admin and timezone databases.
  Italy only; Japan (a larger extract) and the other countries are unmeasured.

## Machine

2 CPUs, 7,932 MB RAM, about 30 GB free disk.

## Tile build

| Item | Result |
|---|---|
| Extract | 2,252.1 MB (downloaded in 371 s) |
| Build time | 907 s |
| Peak memory of the build | 7,832 MB (of 7,932 MB available) |
| Exit status | 0 |
| Tiles on disk | 2,369.1 MB in 1,591 files |

The build succeeded using almost all the machine's memory. That shows it fits in 8 GB, not what
the minimum is. Building on a larger or smaller machine was not tried.

## Serving: 50 x 50 matrices (2,500 cells)

| Case | Median ms | Unreachable cells | Process memory MB |
|---|---:|---:|---:|
| City, pedestrian | 888.7 | 0 of 2,500 | 533.7 |
| City, driving | 742.4 | 320 of 2,500 | 543.8 |
| Between Italian cities, driving | 9,420.1 | 98 of 2,500 | 1,795.2 |

Graph load took 0.01 s. The 320 unreachable driving cells inside one city are **unexplained**
(possibly points snapped to pedestrian-only or disconnected streets). Phase 3 must treat a null
cell as "no routed time" and fall back to a labelled estimate.

## What this means

- Building tiles for Italy needs about 8 GB of RAM and a quarter of an hour on two CPUs. The
  build can run in GitHub Actions; only the 2.4 GB of tiles need to be served.
- Serving Italy needs roughly 2.4 GB of disk and between about 0.5 GB and 1.8 GB of process
  memory for the matrices tested, plus the operating system. Whether a free host offers that has
  **not been checked**.
- Self-hosting therefore stays a realistic fallback to the FOSSGIS server (ADR 004), for Italy
  at least.
