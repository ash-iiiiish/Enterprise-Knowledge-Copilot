"""
Async PDF ingestion pipeline: load -> chunk -> embed -> store in pgvector.

PyPDFLoader / RecursiveCharacterTextSplitter are CPU/IO-bound sync libraries,
so the load+split step runs in a worker thread; embedding + DB writes are
natively async via core.embeddings / db.vector_repository.

Single-tenant enterprise store: everything ingested here goes into the same
knowledge base (no source_type/corpus split).
"""
import asyncio
from typing import List

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.logging_config import logger
from db.vector_repository import store_documents_bulk


def _load_and_split(file_path: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    loader = PyPDFLoader(file_path)
    documents = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = splitter.split_documents(documents)
    return [c.page_content for c in chunks]


async def ingest_pdf(file_path: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> int:
    """Ingest a single PDF and return the number of chunks stored."""
    chunk_texts = await asyncio.to_thread(_load_and_split, file_path, chunk_size, chunk_overlap)

    payload = [
        {"content": text, "metadata": {"source": file_path, "chunk_index": i}}
        for i, text in enumerate(chunk_texts)
    ]
    ids = await store_documents_bulk(payload)
    logger.info(f"Ingested {len(ids)} chunks from {file_path}")
    return len(ids)


async def ingest_pdfs(file_paths: List[str]) -> int:
    """Ingest multiple PDFs concurrently."""
    counts = await asyncio.gather(*[ingest_pdf(fp) for fp in file_paths])
    return sum(counts)
