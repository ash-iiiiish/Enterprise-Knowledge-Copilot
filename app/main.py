"""FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_chat import router as chat_router
from app.api.routes_ingest import router as ingest_router
from app.api.routes_threads import router as threads_router
from app.config import settings
from app.logging_config import logger

app = FastAPI(
    title="Enterprise Knowledge Copilot",
    description="Async LangGraph-powered RAG + MCP tool copilot for enterprise docs.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api/v1")
app.include_router(ingest_router, prefix="/api/v1")
app.include_router(threads_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.on_event("startup")
async def on_startup() -> None:
    logger.info(f"Starting Enterprise Knowledge Copilot on {settings.app_host}:{settings.app_port}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=True)
