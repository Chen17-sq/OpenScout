"""Shared pytest fixtures.

We point the test runs at an in-memory SQLite so we don't touch the real DB.
"""

import os

import pytest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"


@pytest.fixture(scope="session", autouse=True)
def _init_in_memory_db():
    from openscout.db import engine
    from openscout.migrations import upgrade_schema
    from openscout.models import Base

    Base.metadata.create_all(engine)
    upgrade_schema(engine)
    yield
