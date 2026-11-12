# ADR 005 — Free, managed hosting without a server of the owner's

- **Status:** **Accepted** on 2026-11-12 (owner approval), including a roughly one-minute cold start
  and no automatic backups of `app` data. Decides D3.
- **Date:** 2026-11-12
- **Related:** [`004-fossgis-valhalla-demo-server.md`](004-fossgis-valhalla-demo-server.md),
  [`001-technology-stack.md`](001-technology-stack.md), [`../app-plan.md`](../app-plan.md) (D3, D14),
  [`../spikes/s2-data-findings.md`](../spikes/s2-data-findings.md)

## Context

The owner has no server and wants free, managed services (D14). Routing no longer needs a server
of ours (ADR 004). Three things still need a home: the PostgreSQL/PostGIS database, the small
FastAPI planning API, and the job that imports region data into the database.

Verification marks: ✅ read on the official page on 2026-11-12; ◐ partly read; ✗ not read.

## What the official sources say

### Database: Supabase Free

- ✅ "500 MB database size (Shared CPU • 500 MB RAM)"; "Limit of 2 active projects"; "5 GB egress";
  "Free projects are paused after 1 week of inactivity"; automatic backups "Not included" on Free.
  <https://supabase.com/pricing>
- ✅ "Compute resources on the Free plan are subject to change." Free Nano: 60 database
  connections. <https://supabase.com/docs/guides/platform/compute-and-disk>
- ◐ PostGIS: the extension page says to enable it in the dashboard and does not mention plans, so
  availability on Free is **not stated**; to be confirmed when the first project is created.
  <https://supabase.com/docs/guides/database/extensions/postgis>
- ✅ Direct connections are IPv6; the shared pooler (session mode port 5432, transaction mode port
  6543) is IPv4 on every plan; the IPv4 add-on needs Pro. The page recommends direct connection
  for migrations and dumps, and session mode for third-party tools. A bulk load from an
  IPv4-only runner would use the **session-mode pooler**. This mapping is a reading of the page,
  not a stated recommendation. <https://supabase.com/docs/guides/database/connecting-to-postgres>
- ✅ Terms 2(a): use "is limited to Customer's internal business purposes and the features and
  functionalities specified in the Order". Whether a personal hobby app fits this wording is the
  owner's call; this is literal text, not legal advice. <https://supabase.com/terms>
- ✅ Edge Functions use Deno and TypeScript; Python is not mentioned. The FastAPI backend cannot
  run there as written. <https://supabase.com/docs/guides/functions>

### API server

- Render, ✅: Free web services (Python among the listed runtimes); "Do not use them for production
  applications" but suited to "a hobby project"; spin down after 15 minutes without traffic and
  "spinning back up … takes about one minute"; 750 free instance hours per month; ephemeral
  filesystem; "Render might restart a Free web service at any time"; may suspend a service that
  initiates "an uncommonly high volume" of traffic (examples: external database, external APIs);
  free plan 512 MB RAM; without a payment method, free services are suspended if outbound
  bandwidth is used up. Free Render Postgres expires after 30 days, so it is **not** an option for
  the database. <https://render.com/docs/free>, <https://render.com/pricing>
- Vercel Hobby, ◐: "personal, non-commercial use" (fits D1); FastAPI appears among the
  frameworks on the pricing page; function duration and memory limits were **not read**.
  <https://vercel.com/pricing>
- Koyeb ✗ (page read but no free-tier terms found), Fly.io ✗ (page not reachable), Google Cloud
  Run ✗ (pricing page body empty; docs host not allowed). None can be recommended.

### Import job: GitHub Actions

- ✅ GitHub Free: $12 of included compute usage per month (guide: $300 covers 50,000 minutes on a
  standard Linux runner at $0.006 per minute, so $12 is about 2,000 minutes), 500 MB of artifact
  storage shared with Packages. Standard runners in **public** repositories are free; private
  repositories draw from the $12.
  <https://docs.github.com/en/billing/concepts/product-billing/github-actions>
- ✅ Standard Linux runner: 4 CPUs, 16 GB RAM in public repositories; 2 CPUs, 8 GB RAM in private
  ones; 14 GB SSD in both. Jobs may run up to 6 hours.
  <https://docs.github.com/en/actions/reference/runners/github-hosted-runners>,
  <https://docs.github.com/en/actions/reference/limits>
- The spike runs showed that this repository is private (2 CPUs, 7.9 GB RAM).
- ✗ Not found: whether scheduled workflows are disabled after inactivity.

## Proposed decision

1. **Database:** Supabase Free, with `geo` and `app` as separate schemas. Spike S2 sized the
   imported `geo` data at about 145 MB before the ADR 003 filter.
2. **API server:** a Render free web service running the FastAPI backend. The app shows a
   "waking the server" state during the roughly one-minute cold start. Vercel Hobby stays a
   candidate only if its limits are read and suit the planner.
3. **Region import:** a manually started GitHub Actions workflow (as in spike S2) builds the
   `geo` tables in a temporary PostGIS service and loads them into Supabase through the
   session-mode pooler. Only the data loaded into Supabase persists; nothing is stored on the
   runner.
4. **Travel times:** the FOSSGIS routing adapter (ADR 004) running on the API server; cached
   results are stored in Supabase.
5. **Backups:** Supabase Free has none. `geo` can be rebuilt by the import workflow; the `app`
   data (trips, prices, notes) cannot. A scheduled export of the `app` schema is needed or
   accepted as a risk by the owner.

## Alternatives

| Alternative | Why not chosen |
|---|---|
| Firebase | Its databases are not PostGIS and the planner needs spatial SQL; its server-side functions were not verified. |
| Supabase Edge Functions as the API | Deno and TypeScript only; would replace the Python stack of ADR 001. |
| Render Postgres | The free database expires after 30 days. |
| Self-hosted Valhalla and server | No server available; S3 shows Italy needs about 8 GB RAM to build and 2.4 GB of tiles. |

## Risks and open items

- **Supabase terms wording** ("internal business purposes") needs the owner's judgement.
- **Cold start** of about one minute after 15 idle minutes; the first request of a session is slow.
- **Free tiers can change** ("subject to change"); every limit above must be re-read before use.
- **Actions minutes:** private-repository runs draw from about 2,000 minutes a month. Making the
  repository public (D11) would make standard runner minutes free and give 4 CPUs and 16 GB; that
  is a separate decision.
- **Artifact storage** is only 500 MB, so large build outputs cannot be kept as artifacts.
- **Pause after one week of inactivity** on Supabase; unpausing is manual and its procedure was
  not found on the pages read.
- **IPv4 assumption:** that GitHub-hosted runners are IPv4-only was not verified; the pooler works
  either way.
- ~~PostGIS availability on the Free plan is unconfirmed.~~ **Confirmed 2026-11-12:** the owner
  enabled the PostGIS extension from the dashboard on a Supabase Free project while following
  `../deployment.md` step 3. (Reported by the owner; the `/v1/health/ready` version string was not
  reported.)
