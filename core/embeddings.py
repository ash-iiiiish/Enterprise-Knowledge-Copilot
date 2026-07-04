"""
Embeddings access layer.

HuggingFaceEmbeddings (sentence-transformers) is CPU-bound and synchronous.
To keep the rest of the codebase asyncio-first, every call here is pushed to
a worker thread via asyncio.to_thread so it never blocks the event loop.
"""
import asyncio
from functools import lru_cache
from typing import List

from langchain_huggingface import HuggingFaceEmbeddings

from app.config import settings


@lru_cache
def _embeddings_client() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=settings.embedding_model)


async def embed_query(text: str) -> List[float]:
    return await asyncio.to_thread(_embeddings_client().embed_query, text)


async def embed_documents(texts: List[str]) -> List[List[float]]:
    return await asyncio.to_thread(_embeddings_client().embed_documents, texts)
