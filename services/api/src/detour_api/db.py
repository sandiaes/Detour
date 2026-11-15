"""Database access. Foundation only: connectivity and schema checks, no tables yet."""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError

EXPECTED_SCHEMAS = ("app", "geo")


# PostGIS lives in the ``extensions`` schema on Supabase and in ``public`` elsewhere. Putting both
# on the search path makes ``geometry`` and ``ST_*`` resolve either way; a schema that does not
# exist in the path is ignored by PostgreSQL.
SEARCH_PATH = "public, extensions"


# The pool. A request holds one connection, and several helpers open a second one while it is
# still open (the travel-time cache, the provider budget counter, the background name lookup), so a
# pool of 2 with no overflow stalled for the 30 s pool timeout whenever two requests overlapped
# (2026-11-15). Up to 10 connections is still far below the Supabase Free pooler's limit; a stall
# now fails after 10 s, not 30.
POOL_SIZE = 4
POOL_MAX_OVERFLOW = 6
POOL_TIMEOUT_SECONDS = 10


def make_engine(url: str) -> Engine:
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=POOL_SIZE,
        max_overflow=POOL_MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT_SECONDS,
        connect_args={"connect_timeout": 5},
    )

    @event.listens_for(engine, "connect")
    def _set_search_path(dbapi_connection: Any, _: Any) -> None:
        dbapi_connection.execute(f"SET search_path TO {SEARCH_PATH}")
        dbapi_connection.commit()  # a SET inside an open transaction would be rolled back

    return engine


@dataclass
class DatabaseCheck:
    status: str  # "ok", "unavailable" or "not_configured"
    schemas: list[str] = field(default_factory=list)
    postgis: str | None = None
    error_type: str | None = None


def check_database(engine: Engine | None) -> DatabaseCheck:
    """Connect, run a trivial query, and report which schemas and PostGIS version exist."""
    if engine is None:
        return DatabaseCheck(status="not_configured")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            rows = conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name = ANY(:names)"
                ),
                {"names": list(EXPECTED_SCHEMAS)},
            )
            schemas = sorted(r[0] for r in rows)
            postgis = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
            ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        # Only the exception class leaves this function: its message may name hosts or users.
        return DatabaseCheck(status="unavailable", error_type=type(exc).__name__)
    return DatabaseCheck(status="ok", schemas=schemas, postgis=postgis)
