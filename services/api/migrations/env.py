"""Alembic environment. The database URL is read from DETOUR_DATABASE_URL.

The version table stays in the default schema (``public``) so that ``geo`` and ``app`` contain
only the project's own tables.
"""

import os

from alembic import context
from sqlalchemy import create_engine, pool

from detour_api.settings import normalize_database_url

config = context.config


def _url() -> str:
    raw = os.environ.get("DETOUR_DATABASE_URL")
    if not raw:
        raise SystemExit("DETOUR_DATABASE_URL is not set; cannot run migrations")
    return normalize_database_url(raw)


def run_migrations_offline() -> None:
    context.configure(url=_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
