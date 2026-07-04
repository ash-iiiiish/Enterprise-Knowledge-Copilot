"""
LLM access layer.

Wraps langchain-groq's ChatGroq so the rest of the app only ever calls
`await get_llm().ainvoke(...)`. Keeping this in one place makes it trivial
to swap providers (Groq / OpenAI / Gemini) later.
"""
from functools import lru_cache

from langchain_groq import ChatGroq

from app.config import settings


@lru_cache
def get_llm(temperature: float = 0.0) -> ChatGroq:
    """Return a cached ChatGroq client. langchain chat models are async-native
    (ainvoke/astream), so no extra threading wrapper is required."""
    return ChatGroq(
        model=settings.groq_model,
        temperature=temperature,
        api_key=settings.groq_api_key,
    )
