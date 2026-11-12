"""Database access. Foundation only: connectivity and schema checks, no tables yet."""

from dataclasses import dataclass, field

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

EXPECTED_SCHEMAS = ("app", "geo")


def make_engine(url: str) -> Engine:
    # Small pool: the Supabase Free pooler and the 512 MB Render instance are both tight.
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=0,
        connect_args={"connect_timeout": 5},
    )


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
