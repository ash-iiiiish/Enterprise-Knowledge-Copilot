"""User CRUD + the fuzzy "who did they mean?" lookup the chatbot relies on."""
import difflib
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ROLES, User
from db.session import get_session


async def get_user_by_id(user_id: str) -> Optional[User]:
    async with get_session() as session:
        return await session.get(User, user_id)


async def get_user_by_email(email: str) -> Optional[User]:
    async with get_session() as session:
        res = await session.execute(select(User).where(func.lower(User.email) == email.strip().lower()))
        return res.scalar_one_or_none()


async def list_users(include_inactive: bool = False) -> List[User]:
    async with get_session() as session:
        stmt = select(User).order_by(User.employee_id)
        if not include_inactive:
            stmt = stmt.where(User.is_active.is_(True))
        return list((await session.execute(stmt)).scalars().all())


async def _next_employee_id(session: AsyncSession) -> str:
    res = await session.execute(select(User.employee_id))
    highest = 0
    for (eid,) in res.all():
        digits = "".join(ch for ch in eid if ch.isdigit())
        if digits:
            highest = max(highest, int(digits))
    return f"E{highest + 1:03d}"


async def create_user(
    *,
    name: str,
    email: str,
    password_hash: str,
    role: str = "employee",
    department: str = "General",
    job_title: str = "",
) -> User:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    async with get_session() as session:
        dup = await session.execute(select(User.id).where(func.lower(User.email) == email.strip().lower()))
        if dup.scalar_one_or_none():
            raise ValueError("A user with this email already exists")
        user = User(
            employee_id=await _next_employee_id(session),
            name=name.strip(),
            email=email.strip().lower(),
            password_hash=password_hash,
            role=role,
            department=department.strip() or "General",
            job_title=job_title.strip(),
        )
        session.add(user)
        await session.flush()
        return user


async def update_user(user_id: str, **fields: Any) -> Optional[User]:
    allowed = {"name", "role", "department", "job_title", "is_active", "password_hash"}
    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            return None
        for key, value in fields.items():
            if key in allowed and value is not None:
                if key == "role" and value not in ROLES:
                    raise ValueError(f"role must be one of {ROLES}")
                setattr(user, key, value)
        await session.flush()
        return user


async def count_users() -> int:
    async with get_session() as session:
        return (await session.execute(select(func.count()).select_from(User))).scalar_one()


async def list_departments() -> List[str]:
    async with get_session() as session:
        res = await session.execute(
            select(User.department).where(User.is_active.is_(True)).distinct().order_by(User.department)
        )
        return [d for (d,) in res.all() if d]


# --------------------------------------------------------------------------
# Resolving a free-text reference to a user. Used by the chatbot tools so HR
# can say "assign this to Priya" or "to E003" or "to priya@company.com".
# --------------------------------------------------------------------------

_ME_WORDS = {"me", "myself", "self", "i", "my"}


async def resolve_user(
    session: AsyncSession, ref: str, actor: Optional[User] = None
) -> Tuple[Optional[User], List[User]]:
    """Returns (match, candidates). `match` is set only when exactly one user
    is a confident hit; otherwise `candidates` holds the ambiguous/near
    matches so the caller can ask the person which one they meant."""
    ref = (ref or "").strip()
    if not ref:
        return None, []
    if actor is not None and ref.lower() in _ME_WORDS:
        return actor, []

    active = (await session.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
    low = ref.lower().lstrip("@")

    exact = [u for u in active if low in (u.employee_id.lower(), u.email.lower(), u.name.lower())]
    if len(exact) == 1:
        return exact[0], []

    # whole-word / prefix matches on name parts ("priya" -> "Priya Sharma")
    tokens = low.split()
    partial = [
        u
        for u in active
        if all(any(part.startswith(t) for part in u.name.lower().split()) for t in tokens)
    ]
    if len(partial) == 1:
        return partial[0], []
    if len(partial) > 1:
        return None, partial

    # typo tolerance: take the best fuzzy match only if it clearly beats the runner-up,
    # otherwise return the near matches so the caller asks instead of guessing.
    scored = sorted(
        ((difflib.SequenceMatcher(None, low, u.name.lower()).ratio(), u) for u in active),
        key=lambda pair: pair[0],
        reverse=True,
    )
    scored = [(r, u) for r, u in scored if r >= 0.75]
    if len(scored) == 1 or (len(scored) > 1 and scored[0][0] - scored[1][0] >= 0.06):
        return scored[0][1], []
    return None, [u for _, u in scored[:3]]


async def resolve_group(session: AsyncSession, department: str) -> List[User]:
    """'everyone' / 'all' -> every active user; otherwise a department."""
    q = select(User).where(User.is_active.is_(True))
    if department.strip().lower() not in ("all", "everyone", "everybody", "company", "*"):
        q = q.where(func.lower(User.department) == department.strip().lower())
    return list((await session.execute(q.order_by(User.employee_id))).scalars().all())


def user_brief(u: User) -> Dict[str, Any]:
    return {
        "id": u.id,
        "employee_id": u.employee_id,
        "name": u.name,
        "department": u.department,
        "role": u.role,
    }
