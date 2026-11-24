"""Smoke test for the async DB engine wiring (skipped if no DB is configured)."""
import pytest
from sqlalchemy import text

from tests.conftest import needs_db


@needs_db
async def test_engine_connects(schema):
    from db.session import engine

    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT 1"))).scalar_one() == 1
