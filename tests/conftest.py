"""Shared test setup.

Database tests create users/tasks, so they only run when TEST_DATABASE_URL points
at a *disposable* Postgres (with pgvector). They never touch DATABASE_URL.

    TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ekc_test pytest
"""
import os
import uuid

import pytest

if os.getenv("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

HAVE_DB = bool(os.getenv("TEST_DATABASE_URL"))
needs_db = pytest.mark.skipif(not HAVE_DB, reason="set TEST_DATABASE_URL to run database tests")


@pytest.fixture(scope="session")
async def schema():
    if not HAVE_DB:
        pytest.skip("TEST_DATABASE_URL not set")
    from db.bootstrap import init_schema

    await init_schema()


@pytest.fixture
async def people(schema):
    """A fresh HR user, manager, two engineers and one designer per test."""
    from db.user_repository import create_user

    tag = uuid.uuid4().hex[:6]

    async def make(name, role, dept):
        return await create_user(name=f"{name} {tag}", email=f"{name.lower()}.{tag}@test.io", password_hash="x", role=role, department=dept)

    class P:  # noqa: D401 - simple namespace
        pass

    p = P()
    p.tag = tag
    p.hr = await make("Hana", "hr", "Human Resources")
    p.mgr = await make("Marco", "manager", f"Eng{tag}")
    p.eng1 = await make("Priya", "employee", f"Eng{tag}")
    p.eng2 = await make("Pavan", "employee", f"Eng{tag}")
    p.des = await make("Dana", "employee", f"Design{tag}")
    return p
