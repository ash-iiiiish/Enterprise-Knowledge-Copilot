# Enterprise Knowledge Copilot

An async, LangGraph-powered enterprise assistant that combines **RAG** over
your own documents, **MCP tools** (tickets, employee lookup, company
policies, internal knowledge), **Self-RAG / CRAG verification**, and a
**Streamlit chat UI** with live tool visibility and streamed, typed-out
answers.

```
Question → Classify (LLM) → ┬─ direct_path      → general knowledge answer
                             ├─ retrieval_path   → pgvector RAG (+ CRAG fallback to web search)
                             ├─ tool_path        → MCP tools (tickets / policies / employees / knowledge)
                             └─ both_path        → RAG + MCP tools, run in parallel, merged
                                    ↓
                          Self-RAG verification (retry loop, bounded)
                                    ↓
                         Answer + sources + persisted thread history
```

## Features

- **Async LangGraph workflow** — every node is a coroutine; a single graph
  run never blocks the event loop, so the FastAPI server serves concurrent
  chats without threading hacks.
- **Query classification** — an LLM decides per-question whether it needs
  document retrieval, MCP tools, both, or neither (`graph/nodes.py:classify_query`).
- **CRAG-style retrieval** — retrieved docs are graded for relevance; if none
  are relevant, the query is rewritten and a web search fills the gap, with a
  bounded retry loop (`app.config.max_verification_retries`).
- **Self-RAG verification** — the final answer is checked against its
  context before being shipped; unverified answers trigger a rewrite/retry.
- **MCP tool layer** (via [FastMCP](https://github.com/jlowin/fastmcp)):
  - `create_ticket` — raise a ticket (title, description, priority, assignee)
  - `list_tickets` — unfiltered ticket listing
  - `query_tickets` — filtered ticket search (assignee, creator, status,
    priority, date range — e.g. "tickets assigned by me today")
  - `get_employee_details` — employee lookup
  - `fetch_company_policy` — leave / WFH / notice-period policy lookup
  - `search_internal_knowledge` — onboarding / security / VPN knowledge base
  - `web_search` — DuckDuckGo fallback for anything else
- **Stemming-based tool router** (`mcp_server/client.py`) — a lightweight,
  non-LLM router that separates CREATE vs LIST vs QUERY ticket intents (so
  "show open tickets" doesn't accidentally create a ticket) and parses
  "today"/"yesterday", "assigned to me" vs "assigned by me", status, and
  priority straight out of the query text.
- **Tool-use transparency** — every MCP call returns `{tool_used, arguments,
  result}`, surfaced end-to-end through the API response and the Streamlit
  UI as a live "🔧 running `tool_name(args)`" badge.
- **Streaming, typed-out answers** — `POST /chat/stream` (SSE) streams
  routing info, the tool call (if any), and the answer token-by-token via
  `llm.astream()`.
- **Persistent chat threads** — conversations are stored in Postgres and
  browsable/resumable from the sidebar.
- **PDF ingestion** — upload PDFs, which are chunked, embedded, and stored
  in pgvector for retrieval.

## Tech stack

| Layer          | Tech |
|----------------|------|
| Orchestration  | [LangGraph](https://github.com/langchain-ai/langgraph) (async) |
| LLM            | [Groq](https://groq.com/) via `langchain-groq` |
| Embeddings     | `sentence-transformers/all-MiniLM-L6-v2` via `langchain-huggingface` |
| Vector store   | PostgreSQL + [pgvector](https://github.com/pgvector/pgvector) |
| Chat/thread DB | PostgreSQL via SQLAlchemy (async, `asyncpg`) |
| MCP tools      | [FastMCP](https://github.com/jlowin/fastmcp) + SQLite (`aiosqlite`) |
| API            | FastAPI |
| Frontend       | Streamlit |
| Web search     | `duckduckgo-search` |

## Project structure

```
app/
  main.py                FastAPI app + router registration
  config.py               Centralized settings (env-driven)
  logging_config.py
  api/
    routes_chat.py         POST /chat, POST /chat/stream (SSE)
    routes_ingest.py        POST /ingest (PDF upload)
    routes_threads.py       Thread history endpoints
    schemas.py               Pydantic request/response models

graph/
  state.py                 Shared LangGraph state (TypedDict)
  nodes.py                  All node implementations (classify, retrieve,
                            grade, generate, tool routing, verify, persist)
  routing.py                 Pure conditional-edge decision functions
  workflow.py                 Builds + compiles the LangGraph graph

mcp_server/
  server.py                 FastMCP server: tool definitions + SQLite schema
  client.py                  Stemming-based router + tool-call wrapper

core/
  llm.py                    Cached ChatGroq client
  embeddings.py              Cached HuggingFace embeddings client
  text_processing.py          Porter-stemmer helpers for keyword routing

db/
  models.py                 SQLAlchemy models (documents, threads, messages)
  session.py                  Async engine/session factory
  vector_repository.py         pgvector similarity search + storage
  thread_repository.py          Thread/message CRUD

ingestion/
  pdf_ingestor.py            PDF → chunks → embeddings → pgvector
  web_search.py                Async DuckDuckGo wrapper

frontend/
  streamlit_app.py           Chat UI: history sidebar, PDF upload,
                              streamed answers with live tool badge
```

## Setup

### Prerequisites

- Python 3.12+
- PostgreSQL with the [pgvector](https://github.com/pgvector/pgvector)
  extension enabled
- A [Groq API key](https://console.groq.com/)

### 1. Install dependencies

```bash
pip install -r requirements.txt
# or, if using uv/pyproject per-package:
pip install -e .
```

> The `mcp_server/` FastMCP layer only needs `fastmcp` and `aiosqlite`; the
> rest of the app's dependencies (`langgraph`, `langchain-groq`,
> `langchain-huggingface`, `sqlalchemy[asyncio]`, `asyncpg`, `pgvector`,
> `fastapi`, `uvicorn`, `streamlit`, `httpx`, `duckduckgo-search`, `nltk`)
> are used across `app/`, `graph/`, `core/`, `db/`, `ingestion/`.

### 2. Configure environment

Create a `.env` file in the repo root:

```env
# LLM
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile

# Embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIM=384

# Postgres (must have the pgvector extension enabled)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ai_db

# App
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO
MAX_VERIFICATION_RETRIES=2

# MCP (SQLite, separate from the Postgres knowledge base)
MCP_SQLITE_PATH=enterprise_mcp.db
MCP_DEFAULT_USER_ID=E001

# Streamlit
BACKEND_URL=http://localhost:8000
```

### 3. Enable pgvector on your Postgres database

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Tables (`documents`, `threads`, `messages`) are created automatically by
SQLAlchemy on first use; the MCP `tickets`/`employees` tables (SQLite) are
created and migrated automatically on first tool call.

### 4. Run the backend

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Run the frontend

```bash
streamlit run frontend/streamlit_app.py
```

Then open the Streamlit URL it prints (typically `http://localhost:8501`).

## API reference

| Method | Path                              | Description |
|--------|-----------------------------------|--------------|
| GET    | `/health`                         | Health check |
| POST   | `/api/v1/chat`                    | Ask a question; returns the full verified answer, sources, and which tool ran |
| POST   | `/api/v1/chat/stream`             | Same as above, but streamed as SSE (`routing` → `tool_call` → `token`× N → `done`). Skips the CRAG retry loop to start streaming immediately. |
| POST   | `/api/v1/ingest`                  | Upload one or more PDFs to embed into the knowledge base |
| GET    | `/api/v1/threads`                 | List chat threads |
| GET    | `/api/v1/threads/{id}/messages`   | Get a thread's message history |
| PATCH  | `/api/v1/threads/{id}`            | Rename a thread |
| DELETE | `/api/v1/threads/{id}`            | Delete a thread |

### Example: `/api/v1/chat`

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "show tickets assigned to me today"}'
```

```json
{
  "question": "show tickets assigned to me today",
  "answer": "...",
  "sources": ["external_tools:query_tickets"],
  "tool_used": "query_tickets",
  "verification": "YES",
  "thread_id": "..."
}
```

## Known limitations

- **No real auth/session model** — "my"/"me" in ticket queries resolves to
  a hardcoded `MCP_DEFAULT_USER_ID`, not an authenticated user.
- **Router is keyword/stem-based, not LLM-driven** — `mcp_server/client.py`
  uses Porter stemming for fast, deterministic routing rather than an LLM
  tool-call; it covers the documented intents but won't generalize to
  arbitrarily-phrased requests the way an LLM router would.
- **Streaming mode skips the CRAG/Self-RAG retry loop** — `/chat/stream` does
  a single retrieval/tool pass and streams immediately; use `/chat` when you
  need the fully verified, retry-capable answer.
- **Single-tenant knowledge base** — no per-department or per-corpus split
  for ingested documents.

## License

Add your license here.
