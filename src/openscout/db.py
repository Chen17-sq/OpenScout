from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    pool_pre_ping=not _is_sqlite,
    future=True,
    # SQLite needs check_same_thread=False for FastAPI's threadpool.
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):
    """Enable FK enforcement on SQLite (off by default — would silently violate ondelete=CASCADE)."""
    if _is_sqlite:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a Session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
