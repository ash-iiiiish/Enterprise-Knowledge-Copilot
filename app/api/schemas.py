"""Pydantic request/response models for the FastAPI layer."""
from typing import List, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    thread_id: Optional[str] = None  # omit to start a new thread


class ChatResponse(BaseModel):
    question: str
    answer: str
    sources: List[str] = []
    verification: str = ""
    thread_id: str


class IngestResponse(BaseModel):
    filename: str
    chunks_ingested: int


class ThreadSummary(BaseModel):
    id: str
    title: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    sources: List[str] = []
    verification: str = ""
    created_at: Optional[str] = None


class RenameThreadRequest(BaseModel):
    title: str
