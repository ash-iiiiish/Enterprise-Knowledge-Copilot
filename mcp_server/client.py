"""
MCP routing client.

`route()` is now LLM-driven: it asks the model to pick a tool and fill in
arguments from a live catalog of tool names/descriptions/parameters pulled
straight off the FastMCP server, so a new @mcp.tool in server.py is
automatically routable without touching this file. This generalizes to
arbitrarily-phrased requests the stemming router couldn't ("could you pull
up whatever's been assigned to me since yesterday?").

The original stemming router (`_stem_route`, `_ticket_intent`,
`_parse_ticket_filters`) is kept as a deterministic fallback for when the
LLM call fails, times out, or returns something we can't use (unknown tool
name, bad JSON) - so tool routing degrades gracefully instead of hard
failing if Groq is unreachable.

Every call goes through `call_tool`, which always returns a
{"tool_used": ..., "arguments": ..., "result": ...} envelope so callers
(graph nodes, API responses, the frontend) can show which tool actually ran
instead of guessing from the answer text.
"""
import json
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastmcp import Client
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.config import settings
from app.logging_config import logger
from core.llm import get_llm
from core.text_processing import stem_word, stem_tokens
from mcp_server.server import init_db, mcp

# --------------------------------------------------------------------------
# Intent vocabularies (stemmed)
# --------------------------------------------------------------------------

_CREATE_STEMS = {stem_word(w) for w in ("create", "raise", "log", "submit", "file")}
_LIST_STEMS = {stem_word(w) for w in ("list", "show", "all", "view")}
_QUERY_SIGNAL_STEMS = {
    stem_word(w) for w in ("assign", "today", "yesterday", "my", "me", "status", "priority")
}

_STATUS_STEMS = {
    stem_word("open"): "open",
    stem_word("closed"): "closed",
    stem_word("close"): "closed",
    stem_word("progress"): "in_progress",
    stem_word("pending"): "in_progress",
    stem_word("working"): "in_progress",
}

_PRIORITY_STEMS = {
    stem_word("urgent"): "urgent",
    stem_word("high"): "high",
    stem_word("medium"): "medium",
    stem_word("normal"): "medium",
    stem_word("low"): "low",
}

_ASSIGNED_TO_ME = re.compile(r"assign(ed)?\s+to\s+me\b", re.IGNORECASE)
_ASSIGNED_BY_ME = re.compile(r"assign(ed)?\s+by\s+me\b", re.IGNORECASE)
_CREATED_BY_ME = re.compile(r"(created|raised|filed|opened)\s+by\s+me\b", re.IGNORECASE)
_MY_TICKETS = re.compile(r"\bmy\s+ticket", re.IGNORECASE)

# "open" is ambiguous on its own: a CREATE verb ("open a ticket") vs a status
# adjective ("show open tickets" / "open tickets from today"). Stems alone
# can't tell these apart, so this phrase pattern - "open" directly followed
# by an article and/or "new" - disambiguates the CREATE-verb usage. Bare
# "open ticket(s)" with no article falls through to the normal status-value
# handling in _ticket_intent instead.
_OPEN_AS_CREATE_VERB = re.compile(r"\bopen\s+(?:a|an|new)\s+(?:new\s+)?(ticket|issue)s?\b", re.IGNORECASE)


def _today_iso() -> str:
    return date.today().isoformat()


def _yesterday_iso() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


def _parse_ticket_filters(query: str, default_user: str) -> Dict[str, Any]:
    """Turn free text into query_tickets() filter kwargs. Phrase regexes are
    checked first (word order matters for "assigned to" vs "assigned by"),
    then falls back to stem-based single-keyword matches for status/priority/
    date, which don't depend on order."""
    stems = stem_tokens(query)
    filters: Dict[str, Any] = {}

    if _ASSIGNED_TO_ME.search(query):
        filters["assigned_to"] = default_user
    if _ASSIGNED_BY_ME.search(query) or _CREATED_BY_ME.search(query):
        filters["created_by"] = default_user
    if not filters and _MY_TICKETS.search(query):
        # Plain "my tickets" with no assigned/created qualifier - default to
        # "tickets I raised", which is the more common meaning in practice.
        filters["created_by"] = default_user

    if stem_word("today") in stems:
        filters["date_from"] = filters["date_to"] = _today_iso()
    elif stem_word("yesterday") in stems:
        filters["date_from"] = filters["date_to"] = _yesterday_iso()

    for stem, status in _STATUS_STEMS.items():
        if stem in stems:
            filters["status"] = status
            break

    for stem, priority in _PRIORITY_STEMS.items():
        if stem in stems:
            filters["priority"] = priority
            break

    return filters


def _ticket_intent(query: str, stems: set) -> str:
    """Fallback-path intent split (CREATE vs LIST vs QUERY) used when the LLM
    router is unavailable. QUERY/LIST are checked before CREATE on purpose: e.g.
    "show open tickets" contains the CREATE-adjacent word "open", but
    "show"/"open"-as-status here clearly means read, not write.

    A concrete status or priority value (open/closed/high/urgent/...) also
    counts as a QUERY signal, not just the literal words "status"/"priority" -
    otherwise "show open tickets" would fall through to LIST and silently
    drop the status filter instead of actually filtering by it.

    Exception: "open a/an/new ticket" is unambiguously a CREATE phrase (see
    _OPEN_AS_CREATE_VERB), so it's checked first and short-circuits the
    status-value logic above."""
    if _OPEN_AS_CREATE_VERB.search(query):
        return "create"

    has_query_signal = bool(
        stems & (_QUERY_SIGNAL_STEMS | _STATUS_STEMS.keys() | _PRIORITY_STEMS.keys())
    )
    has_list_signal = bool(stems & _LIST_STEMS)
    has_create_signal = bool(stems & _CREATE_STEMS)

    if has_query_signal:
        return "query"
    if has_list_signal:
        return "list"
    if has_create_signal:
        return "create"
    # Ambiguous mention of "ticket"/"issue" with no other signal - default to
    # showing tickets rather than silently creating one on the user's behalf.
    return "list"


class ToolCallDecision(BaseModel):
    tool_name: str = Field(..., description="Name of the MCP tool to call")
    arguments: Dict[str, Any] = Field(default_factory=dict)


_ROUTING_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a tool-routing assistant for an enterprise copilot. Given the "
            "user's request, choose exactly ONE tool to call and the keyword "
            "arguments to pass it.\n\n"
            "Today's date is {today}. The current user's employee id is "
            "'{default_user}' - use it for any argument that refers to \"me\"/\"my\" "
            "(e.g. tickets assigned to me -> assigned_to='{default_user}'; tickets "
            "I raised / assigned by me -> created_by='{default_user}').\n\n"
            "Available tools:\n{tool_catalog}\n\n"
            "Rules:\n"
            "- Only include arguments the chosen tool actually accepts; omit anything "
            "not mentioned or not implied by the request.\n"
            "- For tickets: use query_tickets whenever ANY filter is implied (an "
            "assignee, a creator, a status, a priority, or a date/time reference like "
            "\"today\"/\"yesterday\"); use list_tickets only for a completely "
            "unfiltered listing; use create_ticket only when the user is clearly "
            "asking to open/log/raise/submit/file a NEW ticket, not when they're "
            "asking to see existing ones.\n"
            "- Dates must be ISO format (YYYY-MM-DD).\n"
            "- If nothing else fits, use web_search.\n"
            "Respond with a single JSON object with exactly these keys: "
            "tool_name (string, must be exactly one of the available tool names), "
            "arguments (a JSON object of keyword arguments for that tool).",
        ),
        ("human", "{query}"),
    ]
)


class EnterpriseMCPClient:
    def __init__(self) -> None:
        self._client = Client(mcp)
        self._ready = False
        self._tool_catalog: Optional[List[Dict[str, str]]] = None

    async def _ensure_ready(self) -> None:
        if not self._ready:
            await init_db()
            self._ready = True

    async def _load_tool_catalog(self) -> List[Dict[str, str]]:
        """Introspect the FastMCP server for its live tool list so the LLM
        router's prompt always reflects what's actually callable - add a new
        @mcp.tool in server.py and it shows up here automatically."""
        if self._tool_catalog is not None:
            return self._tool_catalog

        await self._ensure_ready()
        async with self._client:
            tools = await self._client.list_tools()

        catalog = []
        for t in tools:
            schema = getattr(t, "inputSchema", None) or {}
            props = schema.get("properties", {})
            required = set(schema.get("required", []))
            params = ", ".join(
                f"{name}{'*' if name in required else ''}: {info.get('type', 'any')}"
                for name, info in props.items()
            ) or "(no parameters)"
            catalog.append(
                {
                    "name": t.name,
                    "description": (t.description or "").strip(),
                    "params": params,
                }
            )
        self._tool_catalog = catalog
        return catalog

    async def call_tool(self, name: str, **kwargs: Any) -> Dict[str, Any]:
        await self._ensure_ready()
        async with self._client:
            result = await self._client.call_tool(name, kwargs)
        data = getattr(result, "data", None)
        if data is None:
            try:
                data = json.loads(result.content[0].text)
            except Exception:
                data = {"result": str(result)}

        logger.info("MCP tool invoked: %s(%s)", name, kwargs)
        return {"tool_used": name, "arguments": kwargs, "result": data}

    async def _llm_route(self, query: str) -> Optional[Dict[str, Any]]:
        catalog = await self._load_tool_catalog()
        catalog_text = "\n".join(
            f"- {t['name']}({t['params']}): {t['description']}" for t in catalog
        )
        valid_names = {t["name"] for t in catalog}

        llm = get_llm().with_structured_output(ToolCallDecision, method="json_mode")
        decision: ToolCallDecision = await llm.ainvoke(
            _ROUTING_PROMPT.format_messages(
                today=_today_iso(),
                default_user=settings.mcp_default_user_id,
                tool_catalog=catalog_text,
                query=query,
            )
        )

        if decision.tool_name not in valid_names:
            logger.warning(
                "LLM router chose unknown tool %r; falling back to stemming router",
                decision.tool_name,
            )
            return None

        # Drop null/empty-string args - a chatty LLM will sometimes include
        # every parameter with null instead of omitting the ones it doesn't
        # want to set, which would otherwise overwrite tool defaults.
        args = {k: v for k, v in decision.arguments.items() if v not in (None, "")}
        return await self.call_tool(decision.tool_name, **args)

    async def route(self, query: str) -> Dict[str, Any]:
        try:
            result = await self._llm_route(query)
            if result is not None:
                return result
        except Exception:
            logger.exception("LLM tool routing failed; falling back to stemming router")

        try:
            return await self._stem_route(query)
        except Exception as exc:
            logger.exception("Stemming fallback router also failed")
            return {"tool_used": None, "arguments": {}, "error": str(exc)}

    async def _stem_route(self, query: str) -> Dict[str, Any]:
        """Deterministic fallback used only when the LLM router is
        unavailable (network error, malformed response, unknown tool name).
        No LLM call, so it always works, but only covers the intents it was
        explicitly written for - see module docstring."""
        query_stems = stem_tokens(query)

        def has(k: str) -> bool:
            return stem_word(k) in query_stems

        if has("ticket") or has("issue"):
            intent = _ticket_intent(query, query_stems)

            if intent == "list":
                return await self.call_tool("list_tickets")

            if intent == "query":
                filters = _parse_ticket_filters(query, settings.mcp_default_user_id)
                return await self.call_tool("query_tickets", **filters)

            # intent == "create"
            return await self.call_tool(
                "create_ticket",
                title="Auto Ticket",
                description=query,
                created_by=settings.mcp_default_user_id,
            )

        if has("policy") or has("leave"):
            return await self.call_tool("fetch_company_policy", query=query)

        if has("employee"):
            return await self.call_tool("get_employee_details", employee_id="E001")

        if has("knowledge") or has("onboarding"):
            return await self.call_tool("search_internal_knowledge", query=query)

        return await self.call_tool("web_search", query=query)


mcp_client = EnterpriseMCPClient()
