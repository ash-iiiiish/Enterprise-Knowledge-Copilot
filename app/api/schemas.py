"""Pydantic request/response models for the FastAPI layer."""
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    thread_id: Optional[str] = None  # omit to start a new thread


class ChatResponse(BaseModel):
    question: str
    answer: str
    sources: List[str] = []
    tool_used: Optional[str] = None
    tool_result: Any = None
    verification: str = ""
    thread_id: str


class IngestResponse(BaseModel):
    filename: str
    chunks_ingested: int
    replaced: bool = False


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
    tool_used: Optional[str] = None
    tool_result: Any = None
    created_at: Optional[str] = None


class RenameThreadRequest(BaseModel):
    title: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    email: str = Field(..., min_length=5, max_length=120)
    password: str = Field(..., min_length=6, max_length=128)
    department: str = "General"


class CreateUserRequest(RegisterRequest):
    role: str = "employee"
    job_title: str = ""


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    is_active: Optional[bool] = None


class CreateTaskRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    assignee_ids: List[str] = []  # user ids
    department: Optional[str] = None  # or a whole team / "everyone"
    priority: str = "medium"
    due_date: Optional[str] = None  # YYYY-MM-DD


class UpdateTaskRequest(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    clear_due_date: bool = False
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[str] = None
