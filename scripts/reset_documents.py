"""
One-off async script to drop and recreate ONLY the `documents` table.

Use this when you see errors like:
    asyncpg.exceptions.UndefinedColumnError: column documents.created_at does not exist

That means the `documents` table in your Postgres DB was created against an
older version of db/models.py (e.g. before a column was added/removed) and
Base.metadata.create_all() does not retroactively alter existing tables -
it only creates ones that are missing entirely.

This is safe to run for the knowledge-base table specifically: it only
drops `documents` (your ingested PDF chunks), NOT `threads` or `messages`
(your chat history), which are left untouched. You will need to
re-ingest your PDFs afterwards.

Run with:  python -m scripts.reset_documents
"""
import asyncio

from sqlalchemy import text

from app.logging_config import logger
from db.models import Base, Document
from db.session import engine


async def reset_documents() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(lambda sync_conn: Document.__table__.drop(sync_conn, checkfirst=True))
        await conn.run_sync(lambda sync_conn: Document.__table__.create(sync_conn, checkfirst=True))
    logger.info("`documents` table dropped and recreated with the current schema. Re-ingest your PDFs now.")


if __name__ == "__main__":
    asyncio.run(reset_documents())