"""Test setup: dummy config and a throwaway SQLite database migrated with alembic."""
import asyncio
import os
import tempfile

import pytest

_DB_DIR = tempfile.mkdtemp(prefix="finance-bot-tests-")
# Must be set before any project module reads data.config
os.environ["BOT_TOKEN"] = "123456:TEST-TOKEN-FOR-TESTS-ONLY-0000000000"
os.environ["ADMINS"] = "7"
os.environ["ip"] = "localhost"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + os.path.join(_DB_DIR, "test.db").replace("\\", "/")

from sqlalchemy import delete  # noqa: E402

from utils.db_api.base import Base, engine, init_db  # noqa: E402


async def _migrate():
    await init_db()
    await engine.dispose()


asyncio.run(_migrate())


@pytest.fixture(autouse=True)
async def clean_db():
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(delete(table))
    yield
    # Connections are bound to the per-test event loop
    await engine.dispose()
