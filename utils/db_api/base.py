from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from data import config

ROOT_DIR = Path(__file__).resolve().parents[2]

engine = create_async_engine(config.DATABASE_URL)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def alembic_config(connection=None):
    """Alembic config pointing at the project's migrations folder (works from any cwd)."""
    from alembic.config import Config

    cfg = Config(str(ROOT_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT_DIR / "migrations"))
    if connection is not None:
        # env.py reuses this connection instead of opening its own
        cfg.attributes["connection"] = connection
    return cfg


def _upgrade(sync_connection) -> None:
    from alembic import command

    command.upgrade(alembic_config(sync_connection), "head")


async def init_db():
    """Bring the database schema up to date by running `alembic upgrade head`."""
    async with engine.begin() as conn:
        await conn.run_sync(_upgrade)
