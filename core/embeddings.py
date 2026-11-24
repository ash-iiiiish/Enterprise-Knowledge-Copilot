"""
Embeddings access layer.

Two interchangeable backends running the same model (all-MiniLM-L6-v2, 384-d):
  fastembed   - ONNX runtime, small and fast on CPU. Default; fits free hosting.
  huggingface - sentence-transformers via langchain-huggingface (needs PyTorch).
Embedding is CPU-bound and synchronous, so every call is pushed to a worker
thread to keep the event loop free.
"""
import asyncio
from functools import lru_cache
from typing import List

from app.config import settings


@lru_cache
def _client():
    if settings.embedding_backend == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(model_name=settings.embedding_model)
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=settings.embedding_model)


def _embed_many(texts: List[str]) -> List[List[float]]:
    client = _client()
    if settings.embedding_backend == "huggingface":
        return client.embed_documents(texts)
    return [vec.tolist() for vec in client.embed(texts)]


async def embed_query(text: str) -> List[float]:
    return (await asyncio.to_thread(_embed_many, [text]))[0]


async def embed_documents(texts: List[str]) -> List[List[float]]:
    return await asyncio.to_thread(_embed_many, texts)
