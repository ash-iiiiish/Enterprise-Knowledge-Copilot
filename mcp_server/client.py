"""
MCP routing client.

`route()` is a lightweight, stemming-based intent router - it never calls an
LLM, so it has to do its own (limited) intent separation instead of blindly
mapping "the query mentions 'ticket'" -> create_ticket. See `_ticket_intent`
for the CREATE vs LIST vs QUERY split, and `_parse_ticket_filters` for how
"today" / "my" / "assigned to me" / "status" get turned into real filters
for `query_tickets`.

Every call goes through `call_tool`, which now always returns a
{"tool_used": ..., "arguments": ..., "result": ...} envelope so callers
(graph nodes, API responses, the frontend) can show which tool actually ran
instead of guessing from the answer text.
"""
import json
import re
from datetime import date, timedelta
from typing import Any, Dict, Optional

from fastmcp import Client

from app.config import settings
from app.logging_config import logger
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
    """Decide CREATE vs LIST vs QUERY for a query already known to be
    ticket-related. QUERY/LIST are checked before CREATE on purpose: e.g.
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


class EnterpriseMCPClient:
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
        data = getattr(result, "data", None)
        if data is None:
            try:
                data = json.loads(result.content[0].text)
            except Exception:
                data = {"result": str(result)}

        logger.info("MCP tool invoked: %s(%s)", name, kwargs)
        return {"tool_used": name, "arguments": kwargs, "result": data}

    async def route(self, query: str) -> Dict[str, Any]:
        query_stems = stem_tokens(query)

        def has(k: str) -> bool:
            return stem_word(k) in query_stems

        try:
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

        except Exception as exc:
            logger.exception("MCP tool call failed")
            return {"tool_used": None, "arguments": {}, "error": str(exc)}


mcp_client = EnterpriseMCPClient()
