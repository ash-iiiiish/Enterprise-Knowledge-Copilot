"""Login, self-registration and "who am I"."""
from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import LoginRequest, RegisterRequest
from app.config import settings
from app.security import create_access_token, get_current_user, hash_password, user_public, verify_password
from db.models import User
from db.user_repository import create_user, get_user_by_email, list_departments

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(payload: LoginRequest) -> dict:
    user = await get_user_by_email(payload.email)
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return {"token": create_access_token(user), "user": user_public(user)}


@router.post("/register")
async def register(payload: RegisterRequest) -> dict:
    if not settings.allow_signup:
        raise HTTPException(403, "Self-registration is disabled. Ask HR to create your account.")
    try:
        user = await create_user(
            name=payload.name,
            email=payload.email,
            password_hash=hash_password(payload.password),
            role="employee",
            department=payload.department,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"token": create_access_token(user), "user": user_public(user)}


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return {"user": user_public(user), "departments": await list_departments()}


@router.get("/config")
async def public_config() -> dict:
    """Lets the login screen know whether to show 'Create account'."""
    return {"allow_signup": settings.allow_signup}
