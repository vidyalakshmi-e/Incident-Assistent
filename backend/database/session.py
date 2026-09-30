"""Engine / session management."""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config.settings import get_settings
from backend.models.entities import Base


@lru_cache
def get_engine(url: str | None = None) -> Engine:
    url = url or get_settings().database_url
    if url.startswith("sqlite:///"):
        Path(url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _):  # WAL lets the API read while the KB worker writes
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()
    return engine


def _add_missing_columns(engine: Engine) -> None:
    """create_all never alters an existing table, so a column added to a model later (e.g. feedback.rating)
    would be missing from a database created by an earlier version. Nullable columns are added in place."""
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have and col.nullable:
                    ddl = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))


def init_db(url: str | None = None) -> Engine:
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    return engine


def reset_db(url: str | None = None) -> Engine:
    """Drop and recreate all application tables (used by `build_index.py --fresh`)."""
    engine = get_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return engine


@lru_cache
def _factory(url: str | None = None) -> sessionmaker:
    return sessionmaker(bind=get_engine(url), expire_on_commit=False)


@contextmanager
def session_scope(url: str | None = None):
    s: Session = _factory(url)()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
