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
| `.github/workflows` | `ci.yml`, `android-apk.yml`, and the throwaway Phase 0 spike workflows |
| `spikes`, `docs/spikes` | Phase 0 throwaway code and findings; not part of the product |

## What CI does

Workflow `CI` (`.github/workflows/ci.yml`) runs on every push:

| Job | Checks |
|---|---|
| API | `ruff check`, `ruff format --check`, `mypy` (strict), `pytest` with coverage against a **PostGIS service** (`postgis/postgis:18-3.7`): migrations, schemas, connectivity. Database tests fail instead of skipping (`DETOUR_REQUIRE_DB_TESTS=1`) |
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

## Database tests

Four tests (migrations, schemas, readiness) need a PostgreSQL server. Without one they are
skipped locally. To run them, point `DETOUR_TEST_DATABASE_URL` at any server on which the user can
create databases; each test creates and drops its own scratch database:

```bash
export DETOUR_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
pytest services/api
```

A plain PostgreSQL works for these; the one test that needs PostGIS runs only in CI.

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
- The app has no navigation, state or form library yet; they are chosen in Phase 5 and recorded in
  an ADR.
- Logs are JSON on stdout with secrets redacted (`detour_api/logging.py`). Request logs carry the
  method, path (never the query string), status and duration; never headers or bodies.
