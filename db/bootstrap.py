"""Idempotent schema setup + first-run seeding. Runs on every app start.

`Base.metadata.create_all` only creates *missing* tables, so columns added in
later versions (threads.user_id, messages.tool_used/tool_result) are applied
with `ADD COLUMN IF NOT EXISTS`. Existing data is never dropped.
"""
from sqlalchemy import text

from app.config import settings
from app.logging_config import logger
from app.security import hash_password
from db.models import Base
from db.session import engine
from db.user_repository import count_users, create_user, get_user_by_email, update_user

_MIGRATIONS = [
    "ALTER TABLE threads ADD COLUMN IF NOT EXISTS user_id VARCHAR",
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS tool_used VARCHAR",
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS tool_result JSON",
    "CREATE INDEX IF NOT EXISTS ix_threads_user_id ON threads (user_id)",
]

_DEMO_USERS = [
    ("Ashish Kumar", "hr@company.com", "hr", "Technical", "HR Manager"),
    ("John Doe", "rohan@company.com", "manager", "Frontend", "Engineering Manager"),
    ("Rohan", "priya@company.com", "employee", "Frontend", "Software Engineer"),
    ("Priya Sharma", "priya@company.com", "employee", "Frontend", "Software Engineer"),
    ("Priya Sharma", "priya@company.com", "employee", "Frontend", "Software Engineer"),
    ("Rohan Mehta", "rohan@company.com", "manager", "Backend", "Engineering Manager"),
    ("Arjun Singh", "arjun@company.com", "employee", "Backend", "Software Engineer"),
]


async def init_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in _MIGRATIONS:
            await conn.execute(text(stmt))
    logger.info("Database schema ready.")


async def seed_users() -> None:
    is_first_run = await count_users() == 0
    if settings.admin_email and settings.admin_password:
        existing = await get_user_by_email(settings.admin_email)
        password_hash = hash_password(settings.admin_password)
        if existing:
            await update_user(existing.id, role="hr", password_hash=password_hash)
        else:
            await create_user(
                name=settings.admin_name,
                email=settings.admin_email,
                password_hash=password_hash,
                role="hr",
                department="Human Resources",
                job_title="HR Admin",
            )
        logger.info(f"Ensured configured HR admin {settings.admin_email}")
    if is_first_run and settings.seed_demo_users:
        if not settings.demo_password:
            raise RuntimeError("DEMO_PASSWORD must be set when SEED_DEMO_USERS is enabled.")
        pw = hash_password(settings.demo_password)
        for name, email, role, dept, title in _DEMO_USERS:
            try:
                await create_user(name=name, email=email, password_hash=pw, role=role, department=dept, job_title=title)
            except ValueError:
                pass
        logger.info("Seeded demo users (password from DEMO_PASSWORD).")
