#!/bin/sh
# Start script shared by Render and Docker Compose.
# Render's free plan has no pre-deploy command, so migrations run here. In Phase 1 a failed
# migration is logged loudly but does not stop the API: /v1/health must stay reachable so a
# wrong or paused database can be diagnosed with /v1/health/ready. Revisit once tables exist.
set -u
if [ -n "${DETOUR_DATABASE_URL:-}" ]; then
  if alembic upgrade head; then
    echo "migrations: ok"
  else
    echo "ERROR migrations failed; starting the API anyway, see /v1/health/ready" >&2
  fi
else
  echo "migrations: skipped (DETOUR_DATABASE_URL is not set)"
fi
exec uvicorn detour_api.main:create_app --factory --host 0.0.0.0 --port "${PORT:-8000}" --no-access-log
