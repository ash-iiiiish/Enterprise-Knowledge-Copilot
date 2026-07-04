"""
Real FastMCP server for the enterprise tools that used to live in the
notebook's plain `MCPClient` class (tools/main.py in the original project).

Every tool is now a genuine async MCP tool, backed by aiosqlite so no
call ever blocks the event loop. Run standalone with:

    python -m mcp_server.server

or import `mcp` and mount it in-process (see mcp_server/client.py).
"""
from typing import Any, Dict

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
                status TEXT
            )
            """
        )
        # seed a demo employee so get_employee_details has something to return
        await db.execute(
            """
            INSERT OR IGNORE INTO employees (id, name, role, department)
            VALUES ('E001', 'Jordan Rivera', 'Software Engineer', 'Engineering')
            """
        )
        await db.commit()


@mcp.tool
async def get_employee_details(employee_id: str) -> Dict[str, Any]:
    """Look up an employee's name, role and department by their ID."""
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
async def create_ticket(title: str, description: str) -> Dict[str, Any]:
    """File a new support/IT ticket and return its generated ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO tickets (title, description, status) VALUES (?, ?, ?)",
            (title, description, "open"),
        )
        await db.commit()
        return {"ticket_id": cursor.lastrowid, "status": "created"}


@mcp.tool
async def fetch_company_policy(query: str) -> Dict[str, Any]:
    """Return the company policy that best matches the query (leave, WFH, notice period)."""
    query_stems = set(stem_text(query).split())
    for key, value in _COMPANY_POLICIES.items():
        key_stems = stem_text(key.replace("_", " ")).split()
        if any(stem_word(k) in query_stems for k in key_stems):
            return {"policy": value}
    return {"policy": "No matching policy found"}


@mcp.tool
async def search_internal_knowledge(query: str) -> Dict[str, Any]:
    """Search the internal knowledge base (onboarding, security, VPN, etc.)."""
    query_stems = set(stem_text(query).split())
    results = [v for k, v in _INTERNAL_KNOWLEDGE.items() if stem_word(k) in query_stems]
    return {"results": results or ["No relevant knowledge found"]}


@mcp.tool
async def web_search(query: str) -> Dict[str, Any]:
    """Fallback external web search tool (used when nothing internal matches)."""
    from ingestion.web_search import duckduckgo_search

    results = await duckduckgo_search(query)
    return {"query": query, "results": results}


if __name__ == "__main__":
    import asyncio

    asyncio.run(init_db())
    mcp.run()