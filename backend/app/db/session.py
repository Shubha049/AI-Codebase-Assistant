from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

_connect_args = {}
_engine_kwargs = {}
if settings.database_url.startswith("sqlite"):
    # Needed for SQLite + FastAPI's threaded request handling.
    _connect_args["check_same_thread"] = False
    # NullPool (a fresh connection per checkout, closed when returned)
    # instead of the default pooled connection: a long-lived pooled SQLite
    # connection can hold an implicit read transaction that predates a
    # schema change made by a *different* connection (e.g. an Alembic
    # migration run in the same process, as tests do) — SQLite won't
    # surface that change to the stale connection until it starts a new
    # transaction, which produced real, reproducible "no such table"
    # failures under the pooled default. Postgres/MySQL in production
    # don't hit this — pooling stays on for those.
    _engine_kwargs["poolclass"] = NullPool

engine = create_engine(settings.database_url, connect_args=_connect_args, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
