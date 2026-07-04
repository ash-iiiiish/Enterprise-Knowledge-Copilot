"""
Centralized application settings, loaded once from environment / .env.
All modules should import `settings` from here instead of calling os.getenv directly.
"""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_db"

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    max_verification_retries: int = 2

    # MCP
    mcp_sqlite_path: str = "enterprise_mcp.db"

    # Streamlit
    backend_url: str = "http://localhost:8000"

    @field_validator("database_url")
    @classmethod
    def _force_async_driver(cls, v: str) -> str:
        """SQLAlchemy's async engine requires an async DBAPI driver. If a
        sync psycopg2 URL slips into .env (e.g. copy-pasted from the
        original notebook), rewrite it to asyncpg instead of crashing at
        engine-creation time."""
        if v.startswith("postgresql+psycopg2://"):
            return v.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

