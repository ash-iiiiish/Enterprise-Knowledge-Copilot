"""
Async MCP client used by the LangGraph workflow.

Connects to the FastMCP server defined in mcp_server/server.py using
FastMCP's in-memory transport (no subprocess/socket needed since both
live in the same process) and exposes a single high-level `route(query)`
coroutine that mirrors the old keyword-routing MCPClient, but now backed
by real MCP tool calls.
"""
import json
from typing import Any, Dict

from fastmcp import Client

from app.logging_config import logger
from core.text_processing import stem_word, stem_tokens
from mcp_server.server import init_db, mcp


class EnterpriseMCPClient:
    """Thin async wrapper around a FastMCP Client bound to our in-process server."""

    def __init__(self) -> None:
        self._client = Client(mcp)
        self._ready = False

    async def _ensure_ready(self) -> None:
        if not self._ready:
            await init_db()
            self._ready = True

    async def call_tool(self, name: str, **kwargs: Any) -> Dict[str, Any]:
        await self._ensure_ready()
        async with self._client:
            result = await self._client.call_tool(name, kwargs)
        # FastMCP tool results are content blocks; unwrap to plain dict/text.
        data = getattr(result, "data", None)
        if data is not None:
            return data
        try:
            return json.loads(result.content[0].text)
        except Exception:
            return {"result": str(result)}

    async def route(self, query: str) -> Dict[str, Any]:
        """Best-effort keyword routing to the right MCP tool, mirroring the
        original prototype's behaviour but via real async tool calls.
        Matching is done on stemmed tokens so "tickets"/"issues"/"leaves"
        etc. route the same as their base forms."""
        query_stems = stem_tokens(query)

        def has(keyword: str) -> bool:
            return stem_word(keyword) in query_stems

        try:
            if has("ticket") or has("issue"):
                return await self.call_tool(
                    "create_ticket", title="Auto Ticket", description=query
                )

            if has("policy") or has("leave"):
                return await self.call_tool("fetch_company_policy", query=query)

            if has("employee"):
                return await self.call_tool("get_employee_details", employee_id="E001")

            if has("knowledge") or has("onboarding"):
                return await self.call_tool("search_internal_knowledge", query=query)

            return await self.call_tool("web_search", query=query)
        except Exception as exc:
            logger.exception("MCP tool call failed")
            return {"error": str(exc)}


mcp_client = EnterpriseMCPClient()