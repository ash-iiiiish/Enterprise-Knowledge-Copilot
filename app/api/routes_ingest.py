"""/ingest endpoint: upload one or more PDFs into the single enterprise
knowledge base (chunk + embed + store)."""
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, UploadFile

from app.api.schemas import IngestResponse
from ingestion.pdf_ingestor import ingest_pdf

router = APIRouter(tags=["ingest"])


@router.post("/ingest", response_model=List[IngestResponse])
async def ingest(files: List[UploadFile] = File(...)):
    responses: List[IngestResponse] = []

    for upload in files:
        suffix = Path(upload.filename or "document.pdf").suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await upload.read())
            tmp_path = tmp.name

        chunk_count = await ingest_pdf(tmp_path)
        responses.append(
            IngestResponse(filename=upload.filename or tmp_path, chunks_ingested=chunk_count)
        )

    return responses
