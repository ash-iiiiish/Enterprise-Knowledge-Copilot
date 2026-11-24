"""
SQLAlchemy ORM models.

- `documents`: the enterprise knowledge base (chunk content + pgvector
  embedding + metadata).
- `users`: employees. `role` is one of hr | manager | employee.
- `tasks`: work items assigned to a user by another user (or by the chatbot on
  someone's behalf). This replaces the old SQLite "tickets" table so the whole
  app lives in one database and can be deployed statelessly.
- `notifications`: in-app inbox. Created whenever a task is assigned/updated.
- `threads` + `messages`: chat history, scoped per user.
"""
import uuid
from datetime import date, datetime
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings

ROLES = ("hr", "manager", "employee")
TASK_STATUSES = ("todo", "in_progress", "done")
TASK_PRIORITIES = ("low", "medium", "high", "urgent")


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class Document(Base):
    """A single embedded chunk of an ingested enterprise document."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any] = mapped_column(Vector(settings.embedding_dim))
    doc_metadata: Mapped[Any] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    employee_id: Mapped[str] = mapped_column(String, unique=True, index=True)  # E001, E002 ...
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="employee")
    department: Mapped[str] = mapped_column(String, default="General")
    job_title: Mapped[str] = mapped_column(String, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="todo", index=True)
    priority: Mapped[str] = mapped_column(String, default="medium")
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    assigned_to: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    via_chatbot: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reminded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "is_read"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String, default="info")  # task_assigned | task_updated | task_done | reminder
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text, default="")
    task_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Thread(Base):
    """One chat conversation. Shown in the sidebar history list."""

    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    title: Mapped[str] = mapped_column(String, default="New chat")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Message(Base):
    """One turn (user question or assistant answer) inside a thread."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    thread_id: Mapped[str] = mapped_column(String, ForeignKey("threads.id"), index=True)
    role: Mapped[str] = mapped_column(String)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[Any] = mapped_column(JSON, default=list)
    verification: Mapped[str] = mapped_column(String, default="")
    tool_used: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tool_result: Mapped[Any] = mapped_column(JSON, nullable=True)  # task cards survive reloads
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
