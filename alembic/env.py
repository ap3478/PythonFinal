"""Alembic environment for assignment14.

This script is run by ``alembic`` for every migration command. It pulls the
target database URL from the environment (so the same migrations run against
both local Docker Postgres and CI Postgres without code changes) and points
``target_metadata`` at the project's SQLAlchemy ``Base`` so autogenerate works.
"""

from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import all model modules so they register on Base.metadata.
from app.database import Base  # noqa: E402
import app.models  # noqa: F401,E402  -- side-effect: registers models

config = context.config

# Override the URL in alembic.ini with the one from the environment, if set.
db_url = os.getenv("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using a live engine."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
