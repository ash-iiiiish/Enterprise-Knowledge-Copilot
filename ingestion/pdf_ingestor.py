"""
Async ingestion pipeline: load -> chunk -> embed -> store in pgvector.
Supports PDF, TXT and MD. Everything goes into one shared knowledge base;
each chunk remembers the original filename so the UI can list documents.
"""
import asyncio
from pathlib import Path
from typing import List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from app.logging_config import logger
from db.vector_repository import store_documents_bulk


def _read_text(file_path: str) -> str:
    if Path(file_path).suffix.lower() == ".pdf":
        reader = PdfReader(file_path)
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    return Path(file_path).read_text(encoding="utf-8", errors="ignore")


def _load_and_split(file_path: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    text = _read_text(file_path)
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return [c for c in splitter.split_text(text) if c.strip()]


async def ingest_pdf(
    file_path: str,
    source_name: Optional[str] = None,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    uploaded_by: Optional[str] = None,
) -> int:
    """Ingest one file and return the number of chunks stored."""
    chunk_texts = await asyncio.to_thread(_load_and_split, file_path, chunk_size, chunk_overlap)
    source = source_name or Path(file_path).name
    payload = [
        {"content": text, "metadata": {"source": source, "chunk_index": i, "uploaded_by": uploaded_by}}
        for i, text in enumerate(chunk_texts)
    ]
    ids = await store_documents_bulk(payload)
    logger.info(f"Ingested {len(ids)} chunks from {source}")
    return len(ids)
