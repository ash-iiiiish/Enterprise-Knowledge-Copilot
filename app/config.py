"""
Centralized application settings, loaded once from environment / .env.
All modules should import `settings` from here instead of calling os.getenv directly.
"""
import secrets
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"

    # Embeddings
    #   fastembed    -> ONNX runtime, ~150MB RAM, no PyTorch. Use this for free hosting.
    #   huggingface  -> sentence-transformers (needs `pip install sentence-transformers`)
    # Both run the same model, so vectors are interchangeable.
    embedding_backend: str = "fastembed"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # Database (Postgres + pgvector). Neon / Supabase URLs are accepted as-is.
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_db"

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    max_verification_retries: int = 2
    app_timezone: str = "Asia/Kolkata"  # used for "today", "tomorrow", due dates
    cors_origins: str = "*"  # comma-separated list, or *

    # Auth
    # Set SECRET_KEY in production. If unset, a random key is generated at boot,
    # which means everyone is logged out whenever the server restarts.
    secret_key: str = ""
    access_token_hours: int = 24 * 7
    allow_signup: bool = True  # self-registration creates an `employee`

    # Demo accounts are opt-in and require an explicitly configured password.
    seed_demo_users: bool = False
    demo_password: str = ""
    admin_email: str = ""  # optional: create this HR admin on first boot
    admin_password: str = ""
    admin_name: str = "HR Admin"

    # Notifications
    reminder_interval_minutes: int = 30  # 0 disables the due-date reminder loop
    # Optional email delivery (any SMTP server, e.g. Gmail app password).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    app_public_url: str = ""  # included in notification emails if set

    @field_validator("database_url")
    @classmethod
    def _force_async_driver(cls, v: str) -> str:
        """SQLAlchemy's async engine requires an async DBAPI driver. Managed
        providers (Neon, Supabase, Render) hand out plain `postgres://` or
        `postgresql://` URLs, so rewrite them to asyncpg."""
        for prefix in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
            if v.startswith(prefix):
                v = "postgresql+asyncpg://" + v[len(prefix):]
                break
        # asyncpg does not understand libpq query params that Neon/Supabase add.
        if v.startswith("postgresql+asyncpg://") and "?" in v:
            base, query = v.split("?", 1)
            kept = []
            ssl_required = False
            for part in query.split("&"):
                key = part.split("=", 1)[0]
                if key == "sslmode":
                    ssl_required = part.split("=", 1)[1] not in ("disable", "allow", "prefer")
                elif key in ("channel_binding", "options"):
                    continue
                else:
                    kept.append(part)
            if ssl_required and not any(p.startswith("ssl=") for p in kept):
                kept.append("ssl=require")
            v = base + ("?" + "&".join(kept) if kept else "")
        return v

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()] or ["*"]

    @property
    def jwt_secret(self) -> str:
        return self.secret_key or _RUNTIME_SECRET


_RUNTIME_SECRET = secrets.token_urlsafe(48)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
