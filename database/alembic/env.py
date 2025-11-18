from logging.config import fileConfig
import sys
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add project root to path so we can import our models
# env.py is now at database/alembic/env.py, so we need 3 levels up to reach root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Import our database models and configuration
from database.models.base import Base, DATABASE_URL, engine

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the database URL from our config (overrides alembic.ini)
config.set_main_option('sqlalchemy.url', DATABASE_URL)

# Import all models to ensure they're registered with Base.metadata
# This is required for autogenerate to detect all tables
from database.models.core import Source, TimeseriesData, TimeIndex, MarketCalendar
from database.models.quality import ValidationRule, Anomaly, AuditLog, TimeseriesArchive
from database.models.analytics import Lineage, Feature, Forecast, BacktestResult, MLModel

# Set target_metadata for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Use our existing engine from base.py instead of creating a new one
    # This ensures we use the same connection pool configuration
    connectable = engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Enable compare_type to detect column type changes
            compare_type=True,
            # Enable compare_server_default to detect default value changes
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
