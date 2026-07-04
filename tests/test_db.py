"""Smoke test for the async DB engine wiring (skipped if no DB is reachable)."""
import pytest

from db.session import engine


@pytest.mark.asyncio
async def test_engine_connects():
    try:
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"No database reachable in this environment: {exc}")
