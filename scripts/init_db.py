"""
One-off async script: create the pgvector extension, all tables, apply small
column migrations and seed the first users.

Run with:  python -m scripts.init_db
(The app does the same thing on every start-up, so this is optional.)
"""
import asyncio

from db.bootstrap import init_schema, seed_users


async def main() -> None:
    await init_schema()
    await seed_users()


if __name__ == "__main__":
    asyncio.run(main())
