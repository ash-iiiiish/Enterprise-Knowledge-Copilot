"""Directory (for picking assignees) and HR user management."""
from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import CreateUserRequest, UpdateUserRequest
from app.security import get_current_user, hash_password, require_roles, user_public
from db.models import User
from db.user_repository import create_user, list_users, update_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def directory(user: User = Depends(get_current_user)) -> list:
    """Everyone active; handy for the assignee picker. Employees get a trimmed
    view (no email) so the directory isn't a contact-harvesting tool."""
    rows = await list_users(include_inactive=user.role == "hr")
    out = []
    for u in rows:
        item = user_public(u)
        if user.role == "employee":
            item.pop("email", None)
        out.append(item)
    return out


@router.post("")
async def add_user(payload: CreateUserRequest, _: User = Depends(require_roles("hr"))) -> dict:
    try:
        u = await create_user(
            name=payload.name,
            email=payload.email,
            password_hash=hash_password(payload.password),
            role=payload.role,
            department=payload.department,
            job_title=payload.job_title,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return user_public(u)


@router.patch("/{user_id}")
async def edit_user(user_id: str, payload: UpdateUserRequest, me: User = Depends(require_roles("hr"))) -> dict:
    if user_id == me.id and (payload.role not in (None, "hr") or payload.is_active is False):
        raise HTTPException(400, "You can't demote or deactivate your own account.")
    try:
        u = await update_user(user_id, **payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not u:
        raise HTTPException(404, "User not found")
    return user_public(u)
