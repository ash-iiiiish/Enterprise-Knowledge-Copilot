"""
MCP routing client.

`route()` is LLM-driven: the model picks a tool and fills in arguments from a
live catalog pulled off the FastMCP server, so a new @mcp.tool is routable
without touching this file.

Identity: every call is made on behalf of the signed-in user (`actor`). The
client injects `actor_id` into each tool call itself and hides that parameter
from the LLM, so a prompt like "act as the HR head" cannot impersonate anyone.

A small deterministic router (`_stem_route`) is the fallback when the LLM call
fails. It is read-only on purpose: it will list tasks but never create them.

Every call returns {"tool_used", "arguments", "result"} so the API and the UI
can show which tool actually ran.
"""
import json
import re
from datetime import timedelta
from typing import Any, Dict, List, Optional

from fastmcp import Client
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.logging_config import logger
from core.llm import get_llm
from core.text_processing import stem_tokens, stem_word
from core.timeutil import describe_today, today_local
from mcp_server.server import mcp

_HIDDEN_PARAMS = {"actor_id"}

_STATUS_STEMS = {
    stem_word("done"): "done",
    stem_word("completed"): "done",
    stem_word("finished"): "done",
    stem_word("progress"): "in_progress",
    stem_word("pending"): "todo",
    stem_word("open"): "todo",
    stem_word("todo"): "todo",
}
_PRIORITY_STEMS = {
    stem_word("urgent"): "urgent",
    stem_word("high"): "high",
    stem_word("medium"): "medium",
    stem_word("low"): "low",
}
_ASSIGNED_BY_ME = re.compile(r"(assign(ed)?|given|gave|created|sent)\s+(by|from)\s+me\b|\bi\s+assigned\b", re.IGNORECASE)


class ToolCallDecision(BaseModel):
    tool_name: str = Field(..., description="Name of the MCP tool to call")
    arguments: Dict[str, Any] = Field(default_factory=dict)


_ROUTING_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are the tool-routing step of a company assistant that HR and managers "
            "use to hand out work and that employees use to see and update it. Choose "
            "exactly ONE tool and the arguments to pass it.\n\n"
            "Today is {today}. The signed-in user is {user_name} (employee id "
            "{user_eid}, role: {user_role}). 'me'/'my'/'I' always refer to this user.\n\n"
            "Available tools:\n{tool_catalog}\n\n"
            "Rules:\n"
            "- Assigning, delegating, 'tell X to ...', 'give X a task', 'remind X', "
            "'ask everyone to ...' -> assign_task. Put the people in `assignees` "
            "(exactly as the user named them) or a team in `department` "
            "('everyone' for the whole company). Make `title` a short imperative "
            "phrase and put any extra detail in `description`.\n"
            "- 'remind me to ...' / 'add a task for myself' -> assign_task with "
            "assignees=['me'].\n"
            "- Showing tasks ('my tasks', 'what's pending', 'what did I assign', "
            "'is Priya done with ...', overdue) -> query_tasks. Use scope="
            "'assigned_by_me' for work the user handed out.\n"
            "- 'mark #12 done', 'I started task 5', 'move the deadline of #7 to ...' "
            "-> update_task. If the user names a task instead of giving its number, "
            "call query_tasks so they can see the matching task numbers.\n"
            "- Resolve relative dates ('Friday', 'tomorrow', 'next week') into ISO "
            "YYYY-MM-DD using today's date. Never invent a due date the user did not "
            "imply.\n"
            "- Only include arguments the tool accepts; omit anything not mentioned. "
            "Never include actor_id.\n"
            "- If nothing else fits, use web_search.\n"
            "Respond with a single JSON object with exactly these keys: tool_name "
            "(string, exactly one of the available tool names) and arguments (a JSON "
            "object).",
        ),
        ("human", "{query}"),
    ]
)


class EnterpriseMCPClient:
    def __init__(self) -> None:
        self._client = Client(mcp)
        self._tool_catalog: Optional[List[Dict[str, str]]] = None
        self._actor_tools: set = set()

    async def _load_tool_catalog(self) -> List[Dict[str, str]]:
        if self._tool_catalog is not None:
            return self._tool_catalog
        async with self._client:
            tools = await self._client.list_tools()
        catalog = []
        for t in tools:
            schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {}
            props = schema.get("properties", {})
            required = set(schema.get("required", []))
            params = ", ".join(
                f"{name}{'*' if name in required else ''}: {info.get('type', 'any')}"
                for name, info in props.items()
                if name not in _HIDDEN_PARAMS
            ) or "(no parameters)"
            if "actor_id" in props:
                self._actor_tools.add(t.name)
            catalog.append({"name": t.name, "description": (t.description or "").strip(), "params": params})
        self._tool_catalog = catalog
        return catalog

    async def call_tool(self, name: str, actor: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        for hidden in _HIDDEN_PARAMS:
            kwargs.pop(hidden, None)  # never trust the model for identity
        await self._load_tool_catalog()
        call_args = {**kwargs, "actor_id": actor["id"]} if name in self._actor_tools else dict(kwargs)
        async with self._client:
            result = await self._client.call_tool(name, call_args)
        data = getattr(result, "data", None)
        if data is None:
            try:
                data = json.loads(result.content[0].text)
            except Exception:
                data = {"result": str(result)}
        logger.info(f"MCP tool invoked: {name}({kwargs}) as {actor.get('employee_id')}")
        return {"tool_used": name, "arguments": kwargs, "result": data}

    async def _llm_decide(self, query: str, actor: Dict[str, Any]) -> Optional[ToolCallDecision]:
        """Ask the LLM which tool to call. Returns None if it picked nothing usable."""
        catalog = await self._load_tool_catalog()
        catalog_text = "\n".join(f"- {t['name']}({t['params']}): {t['description']}" for t in catalog)
        valid_names = {t["name"] for t in catalog}

        llm = get_llm().with_structured_output(ToolCallDecision, method="json_mode")
        decision: ToolCallDecision = await llm.ainvoke(
            _ROUTING_PROMPT.format_messages(
                today=describe_today(),
                user_name=actor["name"],
                user_eid=actor["employee_id"],
                user_role=actor["role"],
                tool_catalog=catalog_text,
                query=query,
            )
        )
        if decision.tool_name not in valid_names:
            logger.warning(f"LLM router chose unknown tool {decision.tool_name!r}; using fallback router")
            return None
        decision.arguments = {k: v for k, v in decision.arguments.items() if v not in (None, "", [])}
        return decision

    async def route(self, query: str, actor: Dict[str, Any]) -> Dict[str, Any]:
        decision: Optional[ToolCallDecision] = None
        try:
            decision = await self._llm_decide(query, actor)
        except Exception:
            logger.exception("LLM tool routing failed; falling back to stemming router")

        if decision is not None:
            # The model chose a tool: run exactly that one. If it fails, report the
            # failure instead of quietly running some other (read-only) tool.
            try:
                return await self.call_tool(decision.tool_name, actor, **decision.arguments)
            except Exception as exc:
                logger.exception(f"Tool {decision.tool_name} failed")
                return {"tool_used": decision.tool_name, "arguments": decision.arguments,
                        "result": {"error": f"The {decision.tool_name} tool failed: {exc}"}}
        try:
            return await self._stem_route(query, actor)
        except Exception as exc:
            logger.exception("Stemming fallback router also failed")
            return {"tool_used": None, "arguments": {}, "error": str(exc)}

    async def _stem_route(self, query: str, actor: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic, read-only fallback."""
        stems = stem_tokens(query)

        def has(k: str) -> bool:
            return stem_word(k) in stems

        if has("task") or has("ticket") or has("assignment") or has("todo"):
            args: Dict[str, Any] = {}
            if _ASSIGNED_BY_ME.search(query):
                args["scope"] = "assigned_by_me"
            for stem, status in _STATUS_STEMS.items():
                if stem in stems:
                    args["status"] = status
                    break
            for stem, pr in _PRIORITY_STEMS.items():
                if stem in stems:
                    args["priority"] = pr
                    break
            if has("overdue") or has("late"):
                args["overdue"] = True
            if has("today"):
                args["created_from"] = args["created_to"] = today_local().isoformat()
            elif has("yesterday"):
                y = (today_local() - timedelta(days=1)).isoformat()
                args["created_from"] = args["created_to"] = y
            return await self.call_tool("query_tasks", actor, **args)

        if has("policy") or has("leave"):
            return await self.call_tool("fetch_company_policy", actor, query=query)
        if has("knowledge") or has("onboarding"):
            return await self.call_tool("search_internal_knowledge", actor, query=query)
        return await self.call_tool("web_search", actor, query=query)


mcp_client = EnterpriseMCPClient()
