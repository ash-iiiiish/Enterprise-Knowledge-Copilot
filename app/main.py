"""FastAPI application entrypoint.

Serves the JSON API under /api/v1 and the web UI (frontend/) at /.
Run with:  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_auth import router as auth_router
from app.api.routes_chat import router as chat_router
from app.api.routes_ingest import router as ingest_router
from app.api.routes_notifications import router as notifications_router
from app.api.routes_tasks import router as tasks_router
from app.api.routes_threads import router as threads_router
from app.api.routes_users import router as users_router
from app.config import settings
from app.logging_config import logger
from db.bootstrap import init_schema, seed_users
from db.task_repository import send_due_reminders

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


async def _reminder_loop() -> None:
    interval = settings.reminder_interval_minutes * 60
    while True:
        try:
            sent = await send_due_reminders()
            if sent:
                logger.info(f"Sent {sent} due-date reminder(s)")
        except Exception:
            logger.exception("Reminder loop iteration failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_schema()
    await seed_users()
    reminder_task = None
    if settings.reminder_interval_minutes > 0:
        reminder_task = asyncio.create_task(_reminder_loop())
    logger.info("Enterprise Knowledge Copilot ready")
    yield
    if reminder_task:
        reminder_task.cancel()


app = FastAPI(
    title="Enterprise Knowledge Copilot",
    description="Company assistant: task assignment with notifications, RAG over documents, MCP tools.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (auth_router, users_router, tasks_router, notifications_router, chat_router, threads_router, ingest_router):
    app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=True)
