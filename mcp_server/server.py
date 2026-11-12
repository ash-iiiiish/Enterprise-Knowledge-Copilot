"""
FastMCP tool server.

Task tools are thin wrappers over db/task_repository.py, the same code the
REST API uses. Every task tool takes an `actor_id`: the authenticated user on
whose behalf the call is made. The MCP client injects it from the logged-in
session and hides it from the LLM, so the model can never act as someone else.

Tools return {"error": "..."} instead of raising, so the assistant can explain
the problem ("Priya is ambiguous: Priya Sharma, Priya Rao") in plain language.
"""
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from core.text_processing import stem_text, stem_word
from core.timeutil import parse_date
from db import task_repository as tasks
from db.session import get_session
from db.user_repository import get_user_by_id, resolve_user, user_brief, list_users

mcp = FastMCP("enterprise-knowledge-copilot-tools")

# Tools that change data. The graph skips answer-verification for these (there
# is no document to "ground" a confirmation against) and never retries them.
WRITE_TOOLS = {"assign_task", "update_task"}

_COMPANY_POLICIES = {
    "leave": "Employees get 24 paid leaves per year.",
    "work_from_home": "WFH allowed 2 days per week.",
    "notice_period": "Notice period is 60 days.",
}

_INTERNAL_KNOWLEDGE = {
    "onboarding": "New employees must complete training within 7 days.",
    "security": "MFA is mandatory for all systems.",
    "vpn": "VPN access required outside office network.",
}


async def _actor(actor_id: Optional[str]):
    user = await get_user_by_id(actor_id) if actor_id else None
    if not user or not user.is_active:
        raise tasks.TaskError("I can't tell who you are - please sign in again.")
    return user


@mcp.tool
async def assign_task(
    title: str,
    assignees: Optional[List[str]] = None,
    department: Optional[str] = None,
    description: str = "",
    priority: str = "medium",
    due_date: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Assign a task and notify the people it is assigned to.

    - title: short task title (required)
    - assignees: list of people - names, employee ids (E003) or emails. Use ["me"]
      for the current user. Omit when assigning to a department or everyone.
    - department: a department name, or "everyone" for the whole company (HR only).
    - description: extra detail, optional.
    - priority: low | medium | high | urgent
    - due_date: ISO date YYYY-MM-DD, optional. Resolve words like "Friday" or
      "next Monday" into a concrete date using today's date.
    One task is created per person; each gets an in-app (and email) notification.
    """
    try:
        actor = await _actor(actor_id)
        return await tasks.assign_tasks(
            actor,
            title=title,
            description=description,
            assignees=assignees or [],
            department=department,
            priority=priority,
            due_date=parse_date(due_date),
            via_chatbot=True,
        )
    except (tasks.TaskError, ValueError) as exc:
        return {"error": str(exc)}


@mcp.tool
async def query_tasks(
    scope: str = "mine",
    assigned_to: Optional[str] = None,
    assigned_by: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    overdue: bool = False,
    due_from: Optional[str] = None,
    due_to: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Search tasks. All filters are optional and combined with AND.

    - scope: "mine" (assigned to the current user, default), "assigned_by_me"
      (tasks the current user handed out) or "all" (HR only).
    - assigned_to / assigned_by: a person's name, employee id, email or "me".
      When given they replace `scope`.
    - status: todo | in_progress | done
    - priority: low | medium | high | urgent
    - overdue: true for tasks past their due date and not done
    - due_from / due_to: ISO dates (inclusive) on the due date
    - created_from / created_to: ISO dates (inclusive) on when it was assigned.
      For "today" pass today's date for both.
    """
    try:
        actor = await _actor(actor_id)
        rows = await tasks.query_tasks(
            actor,
            scope=scope,
            assigned_to=assigned_to,
            assigned_by=assigned_by,
            status=status,
            priority=priority,
            overdue=bool(overdue),
            due_from=parse_date(due_from),
            due_to=parse_date(due_to),
            created_from=parse_date(created_from),
            created_to=parse_date(created_to),
        )
        return {"count": len(rows), "tasks": rows}
    except (tasks.TaskError, ValueError) as exc:
        return {"error": str(exc)}


@mcp.tool
async def update_task(
    task_id: int,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    due_date: Optional[str] = None,
    reassign_to: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Change a task: mark it todo / in_progress / done, or (for whoever assigned
    it, and HR) change its priority, due date or assignee. The other party is
    notified automatically.
    """
    try:
        actor = await _actor(actor_id)
        return await tasks.update_task(
            actor,
            int(task_id),
            status=status,
            priority=priority,
            due_date=parse_date(due_date),
            reassign_to=reassign_to,
        )
    except (tasks.TaskError, ValueError) as exc:
        return {"error": str(exc)}


@mcp.tool
async def get_employee_details(employee: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
    """Look up a colleague by name, employee id (E002) or email."""
    async with get_session() as session:
        actor = await get_user_by_id(actor_id) if actor_id else None
        match, candidates = await resolve_user(session, employee, actor)
    if match:
        return {"employee": {**user_brief(match), "email": match.email, "job_title": match.job_title}}
    if candidates:
        return {"error": "Several people match.", "candidates": [user_brief(c) for c in candidates]}
    return {"error": "Employee not found"}


@mcp.tool
async def list_employees(department: Optional[str] = None) -> Dict[str, Any]:
    """List employees, optionally only one department."""
    users = await list_users()
    if department:
        users = [u for u in users if u.department.lower() == department.strip().lower()]
    return {"count": len(users), "employees": [user_brief(u) for u in users]}


@mcp.tool
async def fetch_company_policy(query: str) -> Dict[str, Any]:
    """Leave, work-from-home and notice-period policy lookup."""
    query_stems = set(stem_text(query).split())
    for key, value in _COMPANY_POLICIES.items():
        key_stems = stem_text(key.replace("_", " ")).split()
        if any(stem_word(k) in query_stems for k in key_stems):
            return {"policy": value}
    return {"policy": "No matching policy found"}


@mcp.tool
async def search_internal_knowledge(query: str) -> Dict[str, Any]:
    """Onboarding, security and VPN knowledge base."""
    query_stems = set(stem_text(query).split())
    results = [v for k, v in _INTERNAL_KNOWLEDGE.items() if stem_word(k) in query_stems]
    return {"results": results or ["No relevant knowledge found"]}


@mcp.tool
async def web_search(query: str) -> Dict[str, Any]:
    """Public web search for anything else."""
    from ingestion.web_search import duckduckgo_search

    results = await duckduckgo_search(query)
    return {"query": query, "results": results}


if __name__ == "__main__":
    mcp.run()
