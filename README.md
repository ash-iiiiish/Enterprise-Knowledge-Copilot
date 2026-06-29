# Enterprise Knowledge Copilot with Verified Answers

## Overview

A production-style AI assistant for enterprise knowledge across HR,
engineering, compliance, and onboarding documentation.

## Features

-   Multi-step LangGraph workflow
-   Query routing
-   RAG with PostgreSQL + pgvector
-   Self-RAG / CRAG document grading
-   Answer verification and refusal on low confidence
-   Source citations and confidence scoring
-   Retrieval trace logging
-   User/session/feedback management
-   FastAPI backend and Streamlit frontend
-   MCP-ready architecture

## Tech Stack

-   LangChain
-   LangGraph
-   PostgreSQL
-   pgvector
-   FastAPI
-   Streamlit
-   SQLAlchemy
-   OpenAI/Groq/Gemini
-   Docker

## Architecture

User → Router → Retriever → Document Grader → (Rewrite if needed) →
Generator → Verifier → Response

## Database

-   users
-   sessions
-   documents
-   chunks
-   retrieval_traces
-   feedback

## Future Improvements

-   Multi-agent orchestration
-   Slack and Google Drive MCP servers
-   SSO authentication
-   RBAC

## Resume Highlights

-   Built a production-style enterprise AI copilot with LangGraph and
    PostgreSQL.
-   Implemented Self-RAG/CRAG, citation scoring, answer validation, and
    retrieval trace logging.
