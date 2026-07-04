"""
One-off async script to create the pgvector extension and all tables.

Run with:  python -m scripts.init_db
"""
import asyncio

from sqlalchemy import text

from app.logging_config import logger
from db.models import Base
from db.session import engine


async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema ready (pgvector extension + tables).")


if __name__ == "__main__":
    asyncio.run(init_models())
