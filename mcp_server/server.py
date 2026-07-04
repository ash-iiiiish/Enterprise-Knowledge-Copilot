from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiosqlite
from fastmcp import FastMCP

from app.config import settings
from core.text_processing import stem_text, stem_word

mcp = FastMCP("enterprise-knowledge-copilot-tools")

DB_PATH = settings.mcp_sqlite_path

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

_VALID_PRIORITIES = {"low", "medium", "high", "urgent"}
_VALID_STATUSES = {"open", "in_progress", "closed"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_ticket_columns(db: aiosqlite.Connection) -> None:
    """Add new ticket columns to a pre-existing tickets table without
    dropping any existing rows. Safe to call on every startup - each
    ALTER TABLE is only attempted if the column doesn't already exist,
    so this works whether the DB was just created above or already has
    ticket rows from before this schema change."""
    async with db.execute("PRAGMA table_info(tickets)") as cursor:
        existing_cols = {row[1] async for row in cursor}

    migrations = {
        "created_by": "ALTER TABLE tickets ADD COLUMN created_by TEXT",
        "assigned_to": "ALTER TABLE tickets ADD COLUMN assigned_to TEXT",
        "priority": "ALTER TABLE tickets ADD COLUMN priority TEXT DEFAULT 'medium'",
        "created_at": "ALTER TABLE tickets ADD COLUMN created_at TEXT",
    }
    for col, ddl in migrations.items():
        if col not in existing_cols:
            await db.execute(ddl)

    # Backfill created_at for any pre-existing rows so date filtering
    # ("today", date ranges) doesn't silently exclude old tickets.
    await db.execute(
        "UPDATE tickets SET created_at = ? WHERE created_at IS NULL",
        (_now_iso(),),
    )


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id TEXT PRIMARY KEY,
                name TEXT,
                role TEXT,
                department TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                status TEXT,
                created_by TEXT,
                assigned_to TEXT,
                priority TEXT DEFAULT 'medium',
                created_at TEXT
            )
            """
        )
        await _ensure_ticket_columns(db)
        await db.execute(
            """
            INSERT OR IGNORE INTO employees (id, name, role, department)
            VALUES ('E001', 'Jordan Rivera', 'Software Engineer', 'Engineering')
            """
        )
        await db.commit()


@mcp.tool
async def get_employee_details(employee_id: str) -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, role, department FROM employees WHERE id = ?",
            (employee_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if not row:
        return {"error": "Employee not found"}
    return dict(row)


@mcp.tool
async def create_ticket(
    title: str,
    description: str,
    created_by: Optional[str] = None,
    assigned_to: Optional[str] = None,
    priority: str = "medium",
    status: str = "open",
) -> Dict[str, Any]:
    """Create a ticket. `created_by` is who raised it, `assigned_to` is who
    it's assigned to (may be left unset until triaged). `priority` is one
    of low/medium/high/urgent (defaults to medium if given anything else)."""
    priority = priority.lower() if priority and priority.lower() in _VALID_PRIORITIES else "medium"
    status = status.lower() if status and status.lower() in _VALID_STATUSES else "open"
    created_at = _now_iso()

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO tickets
                (title, description, status, created_by, assigned_to, priority, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title, description, status, created_by, assigned_to, priority, created_at),
        )
        await db.commit()
        return {
            "ticket_id": cursor.lastrowid,
            "status": status,
            "created_by": created_by,
            "assigned_to": assigned_to,
            "priority": priority,
            "created_at": created_at,
        }


@mcp.tool
async def list_tickets() -> Dict[str, Any]:
    """Unfiltered ticket listing - kept simple on purpose. For anything with
    filters (assignee, creator, status, priority, date range) use
    `query_tickets` instead."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, title, description, status, created_by, assigned_to,
                   priority, created_at
            FROM tickets ORDER BY id DESC
            """
        ) as cursor:
            rows = await cursor.fetchall()
    return {"tickets": [dict(r) for r in rows]}


@mcp.tool
async def query_tickets(
    assigned_to: Optional[str] = None,
    created_by: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Filtered ticket search. All filters are optional and combined with AND.

    - assigned_to / created_by: employee id (exact match)
    - status: open | in_progress | closed
    - priority: low | medium | high | urgent
    - date_from / date_to: ISO date strings (YYYY-MM-DD), inclusive, matched
      against the ticket's created_at date. Pass the same value for both to
      filter to a single day (e.g. "today" -> date_from=date_to=today's date).
    """
    clauses: List[str] = []
    params: List[Any] = []

    if assigned_to:
        clauses.append("assigned_to = ?")
        params.append(assigned_to)
    if created_by:
        clauses.append("created_by = ?")
        params.append(created_by)
    if status:
        clauses.append("status = ?")
        params.append(status.lower())
    if priority:
        clauses.append("priority = ?")
        params.append(priority.lower())
    if date_from:
        clauses.append("date(created_at) >= date(?)")
        params.append(date_from)
    if date_to:
        clauses.append("date(created_at) <= date(?)")
        params.append(date_to)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = (
        "SELECT id, title, description, status, created_by, assigned_to, "
        f"priority, created_at FROM tickets {where} ORDER BY id DESC"
    )

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

    tickets = [dict(r) for r in rows]
    return {
        "tickets": tickets,
        "count": len(tickets),
        "filters_applied": {
            "assigned_to": assigned_to,
            "created_by": created_by,
            "status": status,
            "priority": priority,
            "date_from": date_from,
            "date_to": date_to,
        },
    }


@mcp.tool
async def fetch_company_policy(query: str) -> Dict[str, Any]:
    query_stems = set(stem_text(query).split())
    for key, value in _COMPANY_POLICIES.items():
        key_stems = stem_text(key.replace("_", " ")).split()
        if any(stem_word(k) in query_stems for k in key_stems):
            return {"policy": value}
    return {"policy": "No matching policy found"}


@mcp.tool
async def search_internal_knowledge(query: str) -> Dict[str, Any]:
    query_stems = set(stem_text(query).split())
    results = [v for k, v in _INTERNAL_KNOWLEDGE.items() if stem_word(k) in query_stems]
    return {"results": results or ["No relevant knowledge found"]}


@mcp.tool
async def web_search(query: str) -> Dict[str, Any]:
    from ingestion.web_search import duckduckgo_search
    results = await duckduckgo_search(query)
    return {"query": query, "results": results}


if __name__ == "__main__":
    import asyncio

    asyncio.run(init_db())
    mcp.run()
