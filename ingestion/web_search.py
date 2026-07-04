"""Async wrapper around duckduckgo-search (sync library) for the web-search
fallback used both by the MCP `web_search` tool and the CRAG rewrite/search
node in the graph."""
import asyncio
from typing import List


def _search_sync(query: str, max_results: int) -> List[str]:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return ["duckduckgo-search not installed; web search unavailable."]

    try:
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=max_results))
        return [f"{h.get('title', '')}: {h.get('body', '')}" for h in hits] or [
            "No web results found."
        ]
    except Exception as exc:  # network issues, rate limits, etc.
        return [f"Web search failed: {exc}"]


async def duckduckgo_search(query: str, max_results: int = 5) -> List[str]:
    return await asyncio.to_thread(_search_sync, query, max_results)
