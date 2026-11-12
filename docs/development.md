# Development

Detour is developed **CI first**: every check runs in GitHub Actions on GitHub-hosted runners, and
Claude Code cloud sessions can run the same commands. Nothing requires a local Windows toolchain.
A local Docker Compose stack exists for any machine that can run it, but it is optional.

## Repository layout

| Path | What it is |
|---|---|
| `apps/mobile` | Expo SDK 58 + TypeScript app with MapLibre React Native |
| `services/api` | Python 3.13 + FastAPI backend, Alembic migrations, tests |
| `packages/shared` | `openapi.json` (exported from the API) and the generated typed client `@detour/shared` |
| `infrastructure` | Docker Compose: PostgreSQL with PostGIS, and the API |
| `tools` | Repository checks (dependency policy) |
| `render.yaml` | Render Blueprint for the API ([`deployment.md`](deployment.md)) |
| `services/api/src/detour_api/importer` | Region import, gazetteer import, report and gates (Phase 2) |
| `services/api/src/detour_api/travel`, `adapters/valhalla.py` | Travel-time service, request planner, estimator and the FOSSGIS Valhalla adapter (Phase 3) |
| `services/api/src/detour_api/planner`, `repo/planning.py` | Planning engine v1: scoring, duration table, sequencer, validator, reason templates (Phase 4, ADR 014) |
| `.github/workflows` | `ci.yml`, `import-region.yml` (manual), `android-apk.yml`, and the throwaway Phase 0 spike workflows |
| `spikes`, `docs/spikes` | Phase 0 throwaway code and findings; not part of the product |

## What CI does

Workflow `CI` (`.github/workflows/ci.yml`) runs on every push:

| Job | Checks |
|---|---|
| API | `ruff check`, `ruff format --check`, `mypy` (strict), `pytest` with coverage against a **PostGIS service** (`postgis/postgis:18-3.7`) with `osm2pgsql` and `osmium-tool` installed: migrations, the real region import on a synthetic extract, search, trips, constraints, index use. Database tests fail instead of skipping (`DETOUR_REQUIRE_DB_TESTS=1`) |
| JavaScript | `prettier --check`, contract drift check (regenerate the types, `git diff --exit-code`), `tsc`, `eslint`, `jest` |
| Policy | `tools/check_dependencies.py`: no LLM or generative-AI library in any manifest or lock file |
| Compose | Builds and starts the Compose stack, calls `/v1/health` and `/v1/health/ready` |

Workflow `Android APK` (`android-apk.yml`) is started by hand and uploads `detour.apk` as an
artifact; see [`deployment.md`](deployment.md) steps 7 to 9. It builds the release variant with the
JavaScript bundled in (ADR 008 addendum), not an `expo-dev-client` build, because that needs a
development server the owner does not have.

## Working without installing anything

1. Edit files on GitHub or in a Claude Code cloud session on a branch.
2. Push. Read the result in the repository's **Actions** tab.
3. Download the APK from the Android APK run when you want it on the phone.

## Commands

Run from the repository root unless noted. These are what CI runs; use them in a cloud session or
on any machine with Node 22 and Python 3.13.

```bash
npm ci                          # install the JavaScript workspaces
npm run format:check            # prettier (npm run format to fix)
npm run typecheck               # tsc in apps/mobile and packages/shared
npm run lint                    # eslint in apps/mobile
npm test                        # jest in apps/mobile
```

```bash
python -m venv services/api/.venv && . services/api/.venv/bin/activate
pip install -e "services/api[dev]"
cd services/api
ruff check . ../../tools && ruff format --check . ../../tools
mypy
pytest
```

When the API's endpoints or models change, refresh the contract and the generated types, and
commit both:

```bash
python services/api/scripts/export_openapi.py   # writes packages/shared/openapi.json
npm run generate                                # writes packages/shared/src/schema.d.ts
```

CI fails if either file is stale (`test_committed_contract_matches_the_application` and the drift
step).

## Planner golden files

`tests/test_planner_engine.py` compares the engine's output for five fixture trips with
`tests/fixtures/planner/golden/*.json`, byte for byte. The candidates are synthetic
(`tests/fixtures/planner/make_candidates.py`; invented places, never imported). After an
intended change to the engine, its configuration or the duration table (bump `CONFIG_VERSION`),
rewrite them and review the diff:

```bash
cd services/api
pytest tests/test_planner_engine.py --update-golden
```

## Database tests

Most of the API tests (migrations, constraints, the import, search, trips) need a PostgreSQL
server **with PostGIS and pg_trgm** and, for the import tests, `osm2pgsql` and `osmium`
(`apt-get install postgresql-16-postgis-3 osm2pgsql osmium-tool` on Ubuntu). Without a server they
are skipped locally. Point `DETOUR_TEST_DATABASE_URL` at a server on which the user can create
databases and extensions; each test creates and drops its own scratch database:

```bash
export DETOUR_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
pytest services/api
```

The suite runs the real import once per session on `tests/fixtures/region-sample.osm` (invented
map data that hits every case of the selection rule) and GeoNames-shaped files, then clones that
database for each API test. Nothing in the tests calls a network service: Photon is replaced by a
stub transport, and `tests/fixtures/photon-documented-response.json` follows the format in
Photon's API documentation (it is not a live recording). The FOSSGIS Valhalla adapter is the same:
`tests/valhalla_stub.py` stands in for the server and `tests/fixtures/valhalla/` holds
fixtures: real responses the owner recorded by hand (`*-recorded.json`) and a few documented-format ones (`*-documented.json`). The routing adapter stays off in the `test`
environment unless a transport is injected, so no test or CI run can reach the server.

## End-to-end test (Android emulator)

`.github/workflows/e2e-android.yml` builds an x86_64 release APK with `DETOUR_E2E=1` (allows plain
HTTP to the CI runner only), seeds a database with `python -m tests.e2e_seed` (the API tests'
invented fixture region plus synthetic sights, Testburg), starts the API with routing and Photon
off, and runs `apps/mobile/e2e/trip-flow.yaml` with Maestro on an API 34 emulator. It runs on pull
requests that touch the app, the API or the workflow, on pushes to main, and by hand. Reports are
uploaded as an artifact. Component tests (`npm test`) cover the same flow with a fake server.

## Running an import locally

Needs a PostGIS for the target (migrated: `alembic upgrade head` with `DETOUR_DATABASE_URL`), a
second throwaway PostGIS database for staging, and the two tools. A downloaded extract can be used
instead of downloading:

```bash
export DETOUR_IMPORT_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/detour
export DETOUR_STAGING_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/staging
python -m detour_api.importer gazetteer AT
python -m detour_api.importer region austria --pbf austria-latest.osm.pbf --out-dir out
python -m detour_api.seed --print-token   # optional: the labelled seed trip, development only
```

Never point `region` at the staging database as the target, and never import into the production
database from a laptop: use the workflow ([`deployment.md`](deployment.md), "Importing a region").
The public community servers are never called by the import except the Geofabrik and GeoNames
download hosts, which the import workflow uses with an identifying User-Agent.

## Optional: the local Docker Compose stack

For a machine that can run Docker. Not needed for development.

```bash
cp .env.example .env
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build --wait
curl http://127.0.0.1:8000/v1/health
curl http://127.0.0.1:8000/v1/health/ready
docker compose --env-file .env -f infrastructure/docker-compose.yml down --volumes
```

The database port is bound to `127.0.0.1` only. The API container runs the migrations at start.
The interactive API documentation is at `http://127.0.0.1:8000/v1/docs`.

## Running the app against a backend

`EXPO_PUBLIC_DETOUR_API_URL` is the only build-time value; the map style URL and credits come from
the backend. Expo Go cannot run this app (MapLibre is a native library); only an APK built by the
workflow can. To change the tile provider, change `DETOUR_MAP_STYLE_URL` on the backend: no app
release is needed.

## Configuration

All backend settings are environment variables prefixed `DETOUR_`; see [`.env.example`](../.env.example).
Secrets are set in the hosting providers' settings only ([`deployment.md`](deployment.md)). In
`production`, the API refuses to start without `DETOUR_TOKEN_SECRET` (32 characters or more).

## Conventions

- Versions are pinned exactly (`pyproject.toml`, `package.json`, `package-lock.json`); upgrades
  are planned tasks. The pins are recorded in ADR 001 (addendum) and ADR 010.
- `starlette.testclient` prints a deprecation notice asking for a package called `httpx2`. It is
  not adopted: it was not vetted, `httpx` 0.28.1 works, and the warning is filtered for that one
  message in `pyproject.toml`. Revisit as a planned dependency task.
- The app has no navigation, state or form library (ADR 015).
- Logs are JSON on stdout with secrets redacted (`detour_api/logging.py`). Request logs carry the
  method, path (never the query string), status and duration; never headers or bodies.
