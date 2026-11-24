"""Password hashing, JWT issuing and FastAPI auth dependencies.

Only the standard library (hashlib.scrypt) is used for passwords and PyJWT for
tokens, so there are no heavy native dependencies to install on free hosts.
"""
import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from db.models import User
from db.user_repository import get_user_by_id

_bearer = HTTPBearer(auto_error=False)

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload: Dict = {
        "sub": user.id,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(hours=settings.access_token_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> str:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    return payload["sub"]


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        user_id = decode_token(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = await get_user_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or disabled")
    return user


def require_roles(*roles: str) -> Callable:
    async def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to do that")
        return user

    return dep


def user_public(user: User) -> Dict:
    return {
        "id": user.id,
        "employee_id": user.employee_id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "department": user.department,
        "job_title": user.job_title,
        "is_active": user.is_active,
    }
