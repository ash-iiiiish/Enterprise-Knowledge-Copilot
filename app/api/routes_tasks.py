"""Tasks REST API - the same business logic the chatbot's MCP tools use."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.schemas import CreateTaskRequest, UpdateTaskRequest
from app.security import get_current_user
from core.timeutil import parse_date
from db import task_repository as repo
from db.models import User
from db.session import get_session

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(400, str(exc))


@router.get("")
async def list_tasks(
    scope: str = Query("mine", pattern="^(mine|assigned_by_me|all)$"),
    status: Optional[str] = None,
    user: User = Depends(get_current_user),
) -> dict:
    try:
        tasks = await repo.query_tasks(user, scope=scope, status=status, limit=500)
    except repo.TaskError as exc:
        raise _bad(exc)
    return {"tasks": tasks}


@router.get("/stats")
async def stats(user: User = Depends(get_current_user)) -> dict:
    return await repo.task_stats(user)


@router.post("")
async def create_task(payload: CreateTaskRequest, user: User = Depends(get_current_user)) -> dict:
    from db.models import User as U

    try:
        refs = []
        async with get_session() as session:
            for uid in payload.assignee_ids:
                row = await session.get(U, uid)
                if not row or not row.is_active:
                    raise repo.TaskError("One of the selected people no longer exists.")
                refs.append(row.employee_id)
        return await repo.assign_tasks(
            user,
            title=payload.title,
            description=payload.description,
            assignees=refs,
            department=payload.department,
            priority=payload.priority,
            due_date=parse_date(payload.due_date),
        )
    except (repo.TaskError, ValueError) as exc:
        raise _bad(exc)


@router.patch("/{task_id}")
async def patch_task(task_id: int, payload: UpdateTaskRequest, user: User = Depends(get_current_user)) -> dict:
    reassign_ref = None
    try:
        if payload.assignee_id:
            async with get_session() as session:
                from db.models import User as U

                target = await session.get(U, payload.assignee_id)
                reassign_ref = target.employee_id if target else None
        return await repo.update_task(
            user,
            task_id,
            status=payload.status,
            priority=payload.priority,
            due_date=parse_date(payload.due_date),
            clear_due_date=payload.clear_due_date,
            title=payload.title,
            description=payload.description,
            reassign_to=reassign_ref,
        )
    except (repo.TaskError, ValueError) as exc:
        raise _bad(exc)


@router.delete("/{task_id}")
async def remove_task(task_id: int, user: User = Depends(get_current_user)) -> dict:
    try:
        await repo.delete_task(user, task_id)
    except repo.TaskError as exc:
        raise _bad(exc)
    return {"status": "deleted"}
