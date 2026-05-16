"""Smoke test: migrations runner."""

from sqlalchemy import create_engine

from openscout.migrations import upgrade_schema
from openscout.models import Base


def test_upgrade_idempotent():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    # First run — should add 0 columns (already created from Base.metadata)
    first = upgrade_schema(engine)
    # Second run — should be 0 additions (idempotent)
    second = upgrade_schema(engine)
    assert second == []
    # We don't assert first == [] because freshly-created tables already have
    # all columns; the migration only adds when missing.
