"""Shared pytest fixtures.

We point the test runs at an in-memory SQLite so we don't touch the real DB.

Note on threading: jobs.py spawns a background thread that opens its own
session. Default SQLite `:memory:` gives each new connection a fresh DB,
so we install a `StaticPool` here — one shared connection, schema visible
to every thread.
"""

import os

import pytest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"


@pytest.fixture(scope="session", autouse=True)
def _init_in_memory_db():
    # Reconfigure the engine to use StaticPool so the background-thread tests
    # (test_jobs.py) see the same in-memory schema. Done at import time before
    # the first session is checked out.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from openscout import db as db_mod
    from openscout.migrations import upgrade_schema
    from openscout.models import Base

    db_mod.engine.dispose()
    new_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    db_mod.engine = new_engine
    db_mod.SessionLocal = sessionmaker(
        bind=new_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )

    Base.metadata.create_all(new_engine)
    upgrade_schema(new_engine)
    yield
