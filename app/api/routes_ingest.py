"""Knowledge base: upload documents (HR / managers), list and remove them."""
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.schemas import IngestResponse
from app.security import get_current_user, require_roles
from db.models import User
from db.vector_repository import delete_source, list_sources
from ingestion.pdf_ingestor import ingest_pdf

router = APIRouter(tags=["ingest"])

_ALLOWED = {".pdf", ".txt", ".md"}
_MAX_BYTES = 15 * 1024 * 1024


@router.post("/ingest", response_model=List[IngestResponse])
async def ingest(files: List[UploadFile] = File(...), user: User = Depends(require_roles("hr", "manager"))):
    """Ingest once, available to everyone. Uploading a file whose name already exists
    replaces the old version (new chunks go in first, then the old ones are removed)."""
    responses: List[IngestResponse] = []
    for upload in files:
        name = upload.filename or "document.pdf"
        suffix = Path(name).suffix.lower()
        if suffix not in _ALLOWED:
            raise HTTPException(400, f"{name}: only PDF, TXT and MD files are supported.")
        data = await upload.read()
        if len(data) > _MAX_BYTES:
            raise HTTPException(413, f"{name} is larger than 15 MB.")
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        started = datetime.now(timezone.utc)
        try:
            count = await ingest_pdf(tmp_path, source_name=name, uploaded_by=user.name)
        finally:
            os.unlink(tmp_path)
        replaced = await delete_source(name, before=started) > 0
        responses.append(IngestResponse(filename=name, chunks_ingested=count, replaced=replaced))
    return responses


@router.get("/documents")
async def documents(_: User = Depends(get_current_user)) -> dict:
    return {"documents": await list_sources()}


@router.delete("/documents")
async def remove_document(source: str, _: User = Depends(require_roles("hr"))) -> dict:
    return {"deleted_chunks": await delete_source(source)}
