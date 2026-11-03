import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from data import config as app_config
from utils.db_api import models  # noqa: F401  (registers tables on Base.metadata)
from utils.db_api.base import Base

config = context.config
target_metadata = Base.metadata

# Connection passed in by utils.db_api.base.init_db (programmatic upgrade)
external_connection = config.attributes.get("connection")

# Configure logging only for the CLI, so the bot's own logging setup is not replaced
if external_connection is None and config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def run_migrations_offline() -> None:
    context.configure(
        url=app_config.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    # Batch mode lets ALTER TABLE work on SQLite
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(app_config.DATABASE_URL)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
elif external_connection is not None:
    do_run_migrations(external_connection)
else:
    asyncio.run(run_async_migrations())
