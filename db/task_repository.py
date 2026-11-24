"""
Task assignment, status tracking and notifications.

This module is the single place where the business rules live. Both the REST
API (the Tasks page) and the chatbot's MCP tools call into it, so a task
assigned by typing "assign the Q3 report to Priya by Friday" behaves exactly
like one created from the form.

Permissions
  hr        assign to anyone / any department / the whole company; see all tasks
  manager   assign to anyone or to their own department; see tasks they are part of
  employee  create tasks for themselves only; see tasks they are part of
The assignee can always move their own task through todo -> in_progress -> done.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.notifier import send_emails_in_background
from core.timeutil import today_local
from db.models import TASK_PRIORITIES, TASK_STATUSES, Notification, Task, User
from db.session import get_session
from db.user_repository import resolve_group, resolve_user, user_brief

_STATUS_ALIASES = {
    "todo": "todo", "to do": "todo", "to_do": "todo", "open": "todo", "pending": "todo", "new": "todo",
    "in_progress": "in_progress", "in progress": "in_progress", "started": "in_progress",
    "working": "in_progress", "ongoing": "in_progress", "wip": "in_progress",
    "done": "done", "complete": "done", "completed": "done", "closed": "done", "finished": "done",
}


class TaskError(Exception):
    """A problem the person can fix (bad name, no permission...). The message
    is safe to show to users and to feed back to the LLM."""


def norm_status(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = str(value).strip().lower().replace("-", "_")
    out = _STATUS_ALIASES.get(key) or _STATUS_ALIASES.get(key.replace("_", " "))
    if not out:
        raise TaskError(f"Unknown status '{value}'. Use one of: {', '.join(TASK_STATUSES)}.")
    return out


def norm_priority(value: Optional[str]) -> str:
    v = (value or "medium").strip().lower()
    return v if v in TASK_PRIORITIES else "medium"


# --------------------------------------------------------------------------
# Serialisation
# --------------------------------------------------------------------------


async def _users_by_id(session: AsyncSession, ids: set) -> Dict[str, User]:
    if not ids:
        return {}
    rows = (await session.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return {u.id: u for u in rows}


def _serialize(task: Task, users: Dict[str, User]) -> Dict[str, Any]:
    today = today_local()
    overdue = bool(task.due_date and task.status != "done" and task.due_date < today)
    a, c = users.get(task.assigned_to), users.get(task.created_by)
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description or "",
        "status": task.status,
        "priority": task.priority,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "overdue": overdue,
        "assigned_to": user_brief(a) if a else None,
        "created_by": user_brief(c) if c else None,
        "via_chatbot": task.via_chatbot,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


async def _serialize_many(session: AsyncSession, tasks: List[Task]) -> List[Dict[str, Any]]:
    ids = {t.assigned_to for t in tasks} | {t.created_by for t in tasks}
    users = await _users_by_id(session, ids)
    return [_serialize(t, users) for t in tasks]


def _due_phrase(due: Optional[date]) -> str:
    if not due:
        return "no due date"
    delta = (due - today_local()).days
    if delta == 0:
        return "due today"
    if delta == 1:
        return "due tomorrow"
    if delta < 0:
        return f"{-delta} day(s) overdue"
    return f"due {due.strftime('%a %d %b')}"


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------


def _notify(session: AsyncSession, outbox: list, user: User, kind: str, title: str, body: str, task_id: int):
    session.add(Notification(user_id=user.id, kind=kind, title=title, body=body, task_id=task_id))
    outbox.append((user.email, title, body))


async def list_notifications(user_id: str, unread_only: bool = False, limit: int = 50) -> Dict[str, Any]:
    async with get_session() as session:
        q = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            q = q.where(Notification.is_read.is_(False))
        rows = (await session.execute(q.order_by(Notification.id.desc()).limit(limit))).scalars().all()
        unread = (
            await session.execute(
                select(Notification.id).where(Notification.user_id == user_id, Notification.is_read.is_(False))
            )
        ).all()
        return {
            "unread": len(unread),
            "items": [
                {
                    "id": n.id,
                    "kind": n.kind,
                    "title": n.title,
                    "body": n.body,
                    "task_id": n.task_id,
                    "is_read": n.is_read,
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                }
                for n in rows
            ],
        }


async def mark_notification_read(user_id: str, notification_id: int) -> None:
    async with get_session() as session:
        await session.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.user_id == user_id)
            .values(is_read=True)
        )


async def mark_all_read(user_id: str) -> None:
    async with get_session() as session:
        await session.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True)
        )


# --------------------------------------------------------------------------
# Assigning
# --------------------------------------------------------------------------


async def assign_tasks(
    actor: User,
    *,
    title: str,
    description: str = "",
    assignees: Optional[List[str]] = None,
    department: Optional[str] = None,
    priority: str = "medium",
    due_date: Optional[date] = None,
    via_chatbot: bool = False,
) -> Dict[str, Any]:
    """Create one task per recipient and notify each of them.

    `assignees` are free-text references (name / employee id / email / "me").
    `department` may be a department name or "everyone" (HR only for the latter).
    Raises TaskError with a human-readable message when something can't be
    resolved unambiguously - nothing is created in that case.
    """
    title = (title or "").strip()
    if not title:
        raise TaskError("A task needs a title.")
    if due_date and due_date < today_local():
        raise TaskError(f"The due date {due_date.isoformat()} is in the past.")

    async with get_session() as session:
        actor_row = await session.get(User, actor.id)
        recipients: Dict[str, User] = {}

        for ref in assignees or []:
            match, candidates = await resolve_user(session, ref, actor_row)
            if match:
                recipients[match.id] = match
            elif candidates:
                names = ", ".join(f"{u.name} ({u.employee_id})" for u in candidates)
                raise TaskError(f"'{ref}' is ambiguous. Did you mean: {names}?")
            else:
                raise TaskError(f"I couldn't find anyone matching '{ref}'.")

        if department:
            group = await resolve_group(session, department)
            if not group:
                raise TaskError(f"No active employees found in '{department}'.")
            is_everyone = department.strip().lower() in ("all", "everyone", "everybody", "company", "*")
            if actor_row.role == "employee":
                raise TaskError("Only HR or managers can assign tasks to a team.")
            if actor_row.role == "manager" and (
                is_everyone or department.strip().lower() != actor_row.department.lower()
            ):
                raise TaskError("Managers can assign to individuals or to their own department. Ask HR to assign company-wide.")
            for u in group:
                recipients[u.id] = u

        if not recipients:
            recipients[actor_row.id] = actor_row  # "remind me to ..." -> a task for yourself

        if actor_row.role == "employee" and any(uid != actor_row.id for uid in recipients):
            raise TaskError("Employees can only create tasks for themselves. Ask HR or your manager to assign work to others.")

        prio = norm_priority(priority)
        outbox: list = []
        created: List[Task] = []
        for user in recipients.values():
            task = Task(
                title=title,
                description=(description or "").strip(),
                priority=prio,
                due_date=due_date,
                created_by=actor_row.id,
                assigned_to=user.id,
                via_chatbot=via_chatbot,
            )
            session.add(task)
            created.append(task)
        await session.flush()

        for task in created:
            user = recipients[task.assigned_to]
            if user.id != actor_row.id:
                body = f"{task.title} — {task.priority} priority, {_due_phrase(task.due_date)}."
                if task.description:
                    body += f"\n{task.description}"
                _notify(session, outbox, user, "task_assigned", f"New task from {actor_row.name}", body, task.id)

        result = {
            "count": len(created),
            "tasks": await _serialize_many(session, created),
            "notified": [user_brief(u) for u in recipients.values() if u.id != actor_row.id],
        }
    send_emails_in_background(outbox)
    return result


# --------------------------------------------------------------------------
# Updating
# --------------------------------------------------------------------------


async def update_task(
    actor: User,
    task_id: int,
    *,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    due_date: Optional[date] = None,
    clear_due_date: bool = False,
    title: Optional[str] = None,
    description: Optional[str] = None,
    reassign_to: Optional[str] = None,
) -> Dict[str, Any]:
    new_status = norm_status(status)
    async with get_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise TaskError(f"Task #{task_id} doesn't exist.")
        actor_row = await session.get(User, actor.id)
        is_assignee = task.assigned_to == actor_row.id
        is_owner = task.created_by == actor_row.id or actor_row.role == "hr"
        if not (is_assignee or is_owner):
            raise TaskError("You can only update tasks that are assigned to you or that you created.")

        wants_edit = any(
            v is not None for v in (priority, due_date, title, description, reassign_to)
        ) or clear_due_date
        if wants_edit and not is_owner:
            raise TaskError("Only the person who assigned the task (or HR) can edit its details. You can change its status.")

        users = await _users_by_id(session, {task.assigned_to, task.created_by})
        assignee, creator = users[task.assigned_to], users[task.created_by]
        outbox: list = []
        changes: List[str] = []

        if new_status and new_status != task.status:
            task.status = new_status
            task.completed_at = datetime.now(timezone.utc) if new_status == "done" else None
            changes.append(f"status → {new_status.replace('_', ' ')}")
        if priority is not None:
            task.priority = norm_priority(priority)
            changes.append(f"priority → {task.priority}")
        if title:
            task.title = title.strip()
            changes.append("title updated")
        if description is not None:
            task.description = description.strip()
            changes.append("description updated")
        if clear_due_date:
            task.due_date = None
            changes.append("due date removed")
        elif due_date is not None:
            task.due_date = due_date
            task.last_reminded_at = None
            changes.append(f"due date → {due_date.isoformat()}")
        if reassign_to:
            match, candidates = await resolve_user(session, reassign_to, actor_row)
            if not match:
                names = ", ".join(u.name for u in candidates)
                raise TaskError(f"Couldn't resolve '{reassign_to}'." + (f" Did you mean: {names}?" if names else ""))
            if actor_row.role == "employee":
                raise TaskError("Employees can't reassign tasks.")
            if match.id != task.assigned_to:
                task.assigned_to = match.id
                task.last_reminded_at = None
                changes.append(f"reassigned to {match.name}")
                _notify(
                    session, outbox, match, "task_assigned", f"New task from {actor_row.name}",
                    f"{task.title} — {task.priority} priority, {_due_phrase(task.due_date)}.", task.id,
                )
                if assignee.id != actor_row.id:
                    _notify(session, outbox, assignee, "task_updated", "A task was reassigned",
                            f"“{task.title}” was moved to {match.name}.", task.id)
                assignee = match

        if not changes:
            return {"task": (await _serialize_many(session, [task]))[0], "changes": []}

        await session.flush()
        await session.refresh(task)  # pick up the server-side updated_at
        summary = "; ".join(changes)
        if is_assignee and creator.id != actor_row.id:
            kind = "task_done" if task.status == "done" and new_status == "done" else "task_updated"
            verb = "completed" if kind == "task_done" else "updated"
            _notify(session, outbox, creator, kind, f"{actor_row.name} {verb} a task", f"“{task.title}”: {summary}.", task.id)
        elif not is_assignee and assignee.id != actor_row.id and not reassign_to:
            _notify(session, outbox, assignee, "task_updated", f"{actor_row.name} updated your task", f"“{task.title}”: {summary}.", task.id)

        result = {"task": (await _serialize_many(session, [task]))[0], "changes": changes}
    send_emails_in_background(outbox)
    return result


async def delete_task(actor: User, task_id: int) -> None:
    async with get_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise TaskError(f"Task #{task_id} doesn't exist.")
        actor_row = await session.get(User, actor.id)
        if task.created_by != actor_row.id and actor_row.role != "hr":
            raise TaskError("Only the person who created the task (or HR) can delete it.")
        await session.delete(task)


# --------------------------------------------------------------------------
# Querying
# --------------------------------------------------------------------------


async def query_tasks(
    actor: User,
    *,
    scope: str = "mine",  # mine | assigned_by_me | all
    assigned_to: Optional[str] = None,
    assigned_by: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    overdue: bool = False,
    due_from: Optional[date] = None,
    due_to: Optional[date] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    async with get_session() as session:
        actor_row = await session.get(User, actor.id)
        q = select(Task)

        if assigned_to:
            match, cand = await resolve_user(session, assigned_to, actor_row)
            if not match:
                raise TaskError(f"Couldn't resolve '{assigned_to}'." + (f" Did you mean: {', '.join(u.name for u in cand)}?" if cand else ""))
            q = q.where(Task.assigned_to == match.id)
        if assigned_by:
            match, cand = await resolve_user(session, assigned_by, actor_row)
            if not match:
                raise TaskError(f"Couldn't resolve '{assigned_by}'." + (f" Did you mean: {', '.join(u.name for u in cand)}?" if cand else ""))
            q = q.where(Task.created_by == match.id)

        if not assigned_to and not assigned_by:
            if scope == "assigned_by_me":
                q = q.where(Task.created_by == actor_row.id)
            elif scope == "all" and actor_row.role == "hr":
                pass
            else:
                q = q.where(Task.assigned_to == actor_row.id)

        # Visibility: HR sees everything; everyone else only tasks they're part of.
        if actor_row.role != "hr":
            q = q.where(or_(Task.assigned_to == actor_row.id, Task.created_by == actor_row.id))

        st = norm_status(status)
        if st:
            q = q.where(Task.status == st)
        if priority:
            q = q.where(Task.priority == norm_priority(priority))
        if overdue:
            q = q.where(Task.status != "done", Task.due_date.is_not(None), Task.due_date < today_local())
        if due_from:
            q = q.where(Task.due_date >= due_from)
        if due_to:
            q = q.where(Task.due_date <= due_to)
        if created_from:
            q = q.where(Task.created_at >= datetime.combine(created_from, datetime.min.time(), timezone.utc))
        if created_to:
            q = q.where(Task.created_at < datetime.combine(created_to + timedelta(days=1), datetime.min.time(), timezone.utc))

        q = q.order_by(Task.status == "done", Task.due_date.is_(None), Task.due_date, Task.id.desc()).limit(limit)
        rows = (await session.execute(q)).scalars().all()
        return await _serialize_many(session, list(rows))


async def task_stats(actor: User) -> Dict[str, int]:
    mine = await query_tasks(actor, scope="mine", limit=1000)
    given = await query_tasks(actor, scope="assigned_by_me", limit=1000)
    return {
        "todo": sum(t["status"] == "todo" for t in mine),
        "in_progress": sum(t["status"] == "in_progress" for t in mine),
        "done": sum(t["status"] == "done" for t in mine),
        "overdue": sum(t["overdue"] for t in mine),
        "assigned_by_me_open": sum(t["status"] != "done" for t in given if t["assigned_to"] and t["assigned_to"]["id"] != actor.id),
    }


# --------------------------------------------------------------------------
# Due-date reminders (called periodically by the app's background loop)
# --------------------------------------------------------------------------


async def send_due_reminders() -> int:
    """Notify assignees about tasks that are overdue or due within a day.
    Each task is reminded at most once per ~20 hours."""
    today = today_local()
    horizon = today + timedelta(days=1)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=20)
    outbox: list = []
    sent = 0
    async with get_session() as session:
        q = select(Task).where(
            Task.status != "done",
            Task.due_date.is_not(None),
            Task.due_date <= horizon,
            or_(Task.last_reminded_at.is_(None), Task.last_reminded_at < cutoff),
        )
        tasks = (await session.execute(q)).scalars().all()
        users = await _users_by_id(session, {t.assigned_to for t in tasks})
        for t in tasks:
            user = users.get(t.assigned_to)
            if not user or not user.is_active:
                continue
            title = "Task overdue" if t.due_date < today else "Task due soon"
            _notify(session, outbox, user, "reminder", title, f"{t.title} — {_due_phrase(t.due_date)}.", t.id)
            t.last_reminded_at = datetime.now(timezone.utc)
            sent += 1
    send_emails_in_background(outbox)
    return sent
