"""Alembic environment.

Dual-path schema management
---------------------------
For SQLite (local + small deploys) we use `openscout/migrations.py` —
idempotent `ALTER TABLE ADD COLUMN` runs that don't need a version table.
For Postgres (prod scale) we use Alembic, which carries proper version
history and reversible migrations. Both paths are dispatched from
`openscout init-db`; the CLI branches on the `DATABASE_URL` prefix.

This `env.py` reads `DATABASE_URL` from `openscout.config.settings`
(itself a `pydantic-settings` instance hydrated from env + .env), so the
URL never gets baked into `alembic.ini`. To override at the command line,
just set `DATABASE_URL=postgresql+psycopg://...` before invoking alembic.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from openscout.config import settings
from openscout.models import Base

# Alembic Config object — exposes values from alembic.ini.
config = context.config

# Pull DATABASE_URL from settings (env / .env / Keychain) and stamp it onto
# the alembic config so engine_from_config picks it up. We do this here rather
# than hard-coding `sqlalchemy.url` in alembic.ini.
config.set_main_option("sqlalchemy.url", settings.database_url)

# Set up loggers from alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate target — every table in Base.metadata.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emits SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # render_as_batch makes SQLite-compatible ALTERs; harmless on PG.
        render_as_batch=url is not None and url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects + applies)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=is_sqlite,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
