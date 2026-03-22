"""SQLAlchemy database engine and session factory.

Provides a synchronous SQLite engine and a session factory for use by
Alembic migrations. Application runtime data access uses app.storage (raw
SQLite) to avoid breaking existing behaviour.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import Settings


def build_engine(settings: Settings):
    """Create a SQLAlchemy engine from application settings.

    Args:
        settings: Application settings containing the database path.

    Returns:
        SQLAlchemy Engine bound to the configured SQLite database.
    """
    url = f"sqlite:///{settings.sqlite_path}"
    return create_engine(url, connect_args={"check_same_thread": False})


def build_session_factory(settings: Settings):
    """Create a session factory for the configured database.

    Args:
        settings: Application settings containing the database path.

    Returns:
        Sessionmaker bound to the configured engine.
    """
    engine = build_engine(settings)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models."""
