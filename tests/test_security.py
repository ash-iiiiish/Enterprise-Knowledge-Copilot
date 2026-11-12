"""Password hashing and JWT helpers (pure, no database)."""
import asyncio

import jwt
import pytest

from app.config import settings
from app.security import create_access_token, decode_token, hash_password, verify_password


class _U:
    id = "user-123"
    role = "hr"


def test_password_roundtrip_and_salting():
    h1, h2 = hash_password("s3cret!"), hash_password("s3cret!")
    assert h1 != h2  # random salt
    assert verify_password("s3cret!", h1)
    assert not verify_password("wrong", h1)
    assert not verify_password("s3cret!", "garbage")


def test_token_roundtrip():
    assert decode_token(create_access_token(_U())) == "user-123"


def test_token_rejected_when_tampered_or_wrong_key():
    token = create_access_token(_U())
    with pytest.raises(jwt.PyJWTError):
        decode_token(token[:-2] + "xx")
    forged = jwt.encode({"sub": "user-123"}, "not-the-key", algorithm="HS256")
    with pytest.raises(jwt.PyJWTError):
        decode_token(forged)


def test_database_url_is_normalised_for_asyncpg():
    from app.config import Settings

    s = Settings(database_url="postgresql://u:p@host/db?sslmode=require&channel_binding=require")
    assert s.database_url == "postgresql+asyncpg://u:p@host/db?ssl=require"
    assert Settings(database_url="postgres://u:p@h/d").database_url.startswith("postgresql+asyncpg://")


def test_public_auth_config_does_not_disclose_demo_credentials():
    from app.api.routes_auth import public_config

    assert asyncio.run(public_config()) == {"allow_signup": settings.allow_signup}


def test_demo_accounts_are_disabled_by_default(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("SEED_DEMO_USERS", raising=False)
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    config = Settings(_env_file=None)
    assert not config.seed_demo_users
    assert not config.demo_password
