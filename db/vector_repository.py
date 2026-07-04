"""
Async repository for document/vector operations (pgvector similarity search)
over the single enterprise knowledge base.

All DB calls are async (asyncpg driver under SQLAlchemy's async engine), so
this module never blocks the event loop.
"""
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document as LCDocument
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.embeddings import embed_query
from db.models import Document
from db.session import get_session


async def store_document(session: AsyncSession, content: str, metadata: Optional[dict] = None) -> int:
    vector = await embed_query(content)
    doc = Document(content=content, embedding=vector, doc_metadata=metadata or {})
    session.add(doc)
    await session.flush()
    return doc.id


async def store_documents_bulk(content_metadata: List[Dict[str, Any]]) -> List[int]:
    """Embed + insert many chunks in one transaction. Each item needs
    keys: content, metadata (optional)."""
    ids: List[int] = []
    async with get_session() as session:
        for item in content_metadata:
            doc_id = await store_document(session, content=item["content"], metadata=item.get("metadata"))
            ids.append(doc_id)
    return ids


async def search_documents(query: str, k: int = 5) -> List[LCDocument]:
    """Cosine/L2 nearest-neighbour search over pgvector, returned as
    LangChain Document objects so downstream nodes stay framework-agnostic."""
    query_vector = await embed_query(query)

    async with get_session() as session:
        stmt = select(Document).order_by(Document.embedding.l2_distance(query_vector)).limit(k)
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return [LCDocument(page_content=row.content, metadata=row.doc_metadata or {}) for row in rows]
