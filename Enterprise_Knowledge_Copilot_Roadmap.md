
# Roadmap 1: Enterprise Knowledge Copilot (LangGraph + MCP + RAG)

## 1. Project Overview
Build a production-style AI assistant for enterprise documents (HR, Engineering, Compliance, Onboarding) with verified answers, citations, and refusal behavior when uncertain.

---

## 2. Tech Stack (FREE-FIRST)

### Core AI Stack
- LangChain (RAG + tools)
- LangGraph (workflow orchestration)
- LlamaIndex (optional indexing layer)
- Groq LLM (llama-3.1-8b / llama-3.3-70b)
- Sentence Transformers (embeddings - FREE local)

### Backend
- FastAPI (API layer)
- Python 3.10+
- Pydantic (schemas)

### Database
- PostgreSQL (Neon / Supabase FREE)
- pgvector (vector search)
- SQLAlchemy

### MCP Layer
- MCP Client inside LangGraph
- MCP Servers:
  - PostgreSQL MCP server
  - File system MCP server
  - Optional GitHub/Drive MCP server

### Frontend
- Streamlit (FREE deployment)
- Optional React later

### Observability
- LangSmith (free dev tier)

---

## 3. System Architecture

User → Streamlit UI → FastAPI → LangGraph Agent → MCP Tools → PostgreSQL + Vector DB → Response

---

## 4. Project Structure

enterprise_copilot/
│
├── app/
│   ├── main.py
│   ├── graph.py
│   ├── state.py
│   ├── config.py
│
├── nodes/
│   ├── router.py
│   ├── retriever.py
│   ├── grader.py
│   ├── generator.py
│   ├── verifier.py
│   ├── refusal.py
│
├── mcp_clients/
│   ├── postgres_client.py
│   ├── file_client.py
│
├── ingestion/
│   ├── load_docs.py
│   ├── chunking.py
│   ├── embeddings.py
│
├── db/
│   ├── models.py
│   ├── connection.py
│
├── frontend/
│   ├── streamlit_app.py
│
├── tests/
├── .env
└── requirements.txt

---

## 5. Step-by-Step Roadmap

### PHASE 1: Setup
- Setup FastAPI project
- Setup Streamlit UI
- Setup PostgreSQL (Neon/Supabase)

---

### PHASE 2: Document Ingestion
- Upload PDFs
- Chunk documents
- Create embeddings (SentenceTransformers)
- Store in pgvector

---

### PHASE 3: Basic RAG
- Implement retrieval
- Build simple QA system
- Add citations

---

### PHASE 4: LangGraph Workflow
Nodes:
- Router
- Retriever
- Document Grader (CRAG)
- Query Rewriter
- Generator
- Verifier
- Refusal Node

---

### PHASE 5: MCP Integration
- Connect PostgreSQL via MCP
- Connect file system MCP
- Add tool calling layer inside LangGraph

---

### PHASE 6: Logging + Feedback
- Store:
  - queries
  - retrieved chunks
  - confidence score
  - user feedback

---

### PHASE 7: Deployment

FREE STACK:
- Streamlit Community Cloud → frontend
- Neon Postgres → database
- Groq API → LLM
- Render → optional backend API

---

## 6. Deployment Flow

Streamlit → LangGraph → MCP → PostgreSQL → Response

---

## 7. Resume Highlights
- Built enterprise-grade RAG system with LangGraph
- Implemented MCP-based tool orchestration
- Designed CRAG verification pipeline
- Deployed full-stack AI assistant on free cloud stack
