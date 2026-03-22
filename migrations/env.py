"""Alembic environment configuration.

Imports ORM model metadata so that autogenerate can detect schema drift.
The database URL is resolved from environment / alembic.ini at runtime,
allowing CI and local dev to target different SQLite paths.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import ORM models so they register against Base.metadata for autogenerate.
from app.db import Base
from app.db.models import AuditLogEntry, Item, LlmCallLog  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Allow overriding the database URL via SQLITE_PATH env var (used in tests).
_sqlite_path = os.environ.get("SQLITE_PATH")
if _sqlite_path:
    config.set_main_option("sqlalchemy.url", f"sqlite:///{_sqlite_path}")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection required).

    Emits SQL to stdout rather than executing it against a database.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
