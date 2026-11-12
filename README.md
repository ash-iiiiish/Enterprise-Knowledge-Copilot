# Enterprise Knowledge Copilot

A company assistant where **HR hands out work by chatting** — and the right people are
notified automatically instead of the task getting lost in a WhatsApp group — and where
anyone can ask questions that are answered from the company's own documents.

Built with an async **LangGraph** workflow (RAG + CRAG + Self-RAG verification),
**MCP tools** (FastMCP), **FastAPI**, **Postgres + pgvector**, and a plain HTML/CSS/JS web UI
(no build step) served by the same server.

> **Say it once in the chat →** *"Assign the Q3 sales report to Sneha by Friday, high priority"*
> → a task is created → Sneha gets a notification (bell + pop-up, optional email) →
> she moves it to *Done* → you're notified back.

## What's in the app

| Page | What it does |
|------|--------------|
| **Home** | Landing page: why the Copilot is useful, how it works, FAQ, and a big **Open Chatbot** button. Header + footer link to every section. |
| **Chatbot** | The one front door. Per-user chat history sidebar (search, rename, delete), streamed answers, live "running tool…" status, task cards inside the conversation, sources / verified badges. Read-only link to the Knowledge base — no uploading here. |
| **Tasks** | Kanban board (To do / In progress / Done), tabs *Assigned to me / by me / All (HR)*, stats, a "New task" form with assignee picker. |
| **Knowledge base** | The shared company library. HR/managers add documents once (PDF, TXT, MD); everyone can browse them and click **Ask** to chat about one. Re-uploading a file with the same name replaces it. |
| **Team** | HR adds people, changes roles, deactivates accounts. |
| **Notifications** | Bell icon + toast in the app; optional email; reminders when a task is due within a day or overdue. |

### How the pieces fit together

| Concept | Scope | Who changes it |
|---|---|---|
| **Knowledge base** | Company-wide. One pgvector store, independent of any chat. | HR / managers upload; HR removes |
| **Chatbot** | One assistant for everyone. Reads the knowledge base and calls the task tools on the signed-in user's behalf. | – |
| **Chat sessions (threads)** | Private to the user. Hold conversation memory only, never documents. | The owner |
| **Tasks** | Shared records with role-based visibility; the chatbot and the Tasks page are two UIs over the same data. | Per the role table below |

So when HR ingests the schemes once, any employee asking in a brand-new chat gets answers from them — nothing is re-ingested and nobody needs access to HR's session.

### Roles

| | HR | Manager | Employee |
|---|---|---|---|
| Assign to a person | anyone | anyone | only themselves |
| Assign to a department / everyone | any / **everyone** | own department | – |
| See tasks | all | ones they're part of | ones they're part of |
| Change status of a task | assignee, creator, HR | assignee, creator | assignee, creator |
| Edit / reassign / delete | yes | tasks they created | their own self-created tasks (no reassigning) |
| Upload documents | yes | yes | – |
| Manage team | yes | view | – |

These rules are enforced **on the server** (`db/task_repository.py`) for both the REST API and
the chatbot, so a prompt can't talk the assistant into exceeding someone's permissions.

## How a chat message flows

```
Question → Classify (LLM) → ┬─ direct_path     → general answer
                            ├─ retrieval_path  → pgvector RAG (+ CRAG: rewrite + web fallback)
                            ├─ tool_path       → MCP tools (tasks / employees / policies)
                            └─ both_path       → RAG + tools in parallel, merged
                                   ↓
              Self-RAG verification (bounded retries)   ← skipped for write actions
                                   ↓
              Answer + sources + persisted thread  →  streamed to the UI over SSE
```

Task tools (`assign_task`, `query_tasks`, `update_task`) are in `mcp_server/server.py`. The MCP client
injects the signed-in user's id into every call and hides it from the model — see
`mcp_server/README.md`.

## Quick start

### Option A — Docker (easiest)

```bash
cp .env.example .env          # put your GROQ_API_KEY in it (free: https://console.groq.com)
docker compose up --build
```

Open <http://localhost:8000>.

### Option B — local Python

You need Python 3.11+ and a Postgres with the **pgvector** extension (e.g. `docker run -p 5432:5432
-e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=ai_db pgvector/pgvector:pg16`).

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # set GROQ_API_KEY and DATABASE_URL
uvicorn app.main:app --reload
```

Tables, the pgvector extension, small migrations and the first users are all created on start-up.

### Initial admin account

Demo accounts are disabled by default. Configure `ADMIN_EMAIL` and `ADMIN_PASSWORD` before starting
the app to create or refresh the designated HR account. Self-registration, if enabled, only creates
employee accounts. Set `ALLOW_SIGNUP=false` to require HR to add each account from the Team page.

`SEED_DEMO_USERS=true` is available only for private demo deployments and requires a `DEMO_PASSWORD`.
The sign-in page does not display demo account details. Existing demo users in a database are not
automatically deleted or disabled when demo seeding is turned off; sign in as your configured HR
account and deactivate any unwanted accounts from the Team page.

### Loading your real team

Sign in as the configured HR admin and open **Team → Add member**. Add each person with their real
name, work email, department, job title, role, and a temporary password. The app hashes passwords
before storing them. Existing sample users are not automatically deleted; deactivate them from the
Team page. There is no CSV importer or invitation/password-reset email flow yet. If you don't want
people registering their own employee accounts, set `ALLOW_SIGNUP=false`.

### Email notifications

The app emails task assignments, task updates, and due-date reminders; it does not email account
invitations. Add your SMTP provider settings to `.env`:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-sender@gmail.com
SMTP_PASSWORD=your-provider-app-password
SMTP_FROM=your-sender@gmail.com
APP_PUBLIC_URL=https://your-app.example.com
```

Port `587` uses STARTTLS. For Gmail, use a Google App Password (with 2-Step Verification enabled),
not your normal account password. Keep SMTP credentials private and do not commit `.env`. Recreate
the app after changing environment settings with `docker compose up -d --build`; for local Python,
restart Uvicorn. Check `docker compose logs -f app` if the SMTP provider rejects delivery.

## Configuration

Everything is an environment variable — see [`.env.example`](.env.example) for the full list. The ones
that matter: `GROQ_API_KEY`, `DATABASE_URL`, `SECRET_KEY` (set it, otherwise everyone is logged out on
each restart), `EMBEDDING_BACKEND` (`fastembed` is small and PyTorch-free; `huggingface` uses
sentence-transformers if you install it), `APP_TIMEZONE`, and optional `SMTP_*` for email notifications.
`postgres://…`, `sslmode=require` and Neon/Supabase style URLs are normalised automatically.

## REST API

All under `/api/v1`, JSON, `Authorization: Bearer <token>` (interactive docs at `/docs`).

| | |
|---|---|
| `POST /auth/login`, `/auth/register`, `GET /auth/me` | sign in / sign up / current user |
| `GET /users`, `POST /users`, `PATCH /users/{id}` | directory; HR manages members |
| `GET /tasks?scope=mine\|assigned_by_me\|all`, `POST /tasks`, `PATCH`/`DELETE /tasks/{id}`, `GET /tasks/stats` | tasks |
| `GET /notifications`, `POST /notifications/read-all`, `POST /notifications/{id}/read` | inbox |
| `POST /chat`, `POST /chat/stream` (SSE) | ask the Copilot |
| `GET /threads`, `GET /threads/{id}/messages`, `PATCH`/`DELETE /threads/{id}` | per-user chat history |
| `POST /ingest` (replaces same-named files), `GET`/`DELETE /documents` | knowledge base |

SSE events from `/chat/stream`: `thread`, `routing`, `tool_call`, `retry`, `token`, `done`, `error`.

## Tests

```bash
pytest                                  # pure tests (security, routing); DB tests are skipped
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ekc_test pytest   # everything
```

The database tests create users and tasks, so they only run against a database you name explicitly in
`TEST_DATABASE_URL` — never your real `DATABASE_URL`. They cover assignment, fuzzy name matching,
department/company broadcasts, every permission rule, notifications, status flow, visibility and reminders.

## Project layout

```
app/        FastAPI app, config, auth (security.py), API routers (api/)
core/       LLM + embeddings access, notifier (email), timezone helpers, text processing
db/         SQLAlchemy models, bootstrap (schema + seed), repositories (users, tasks, threads, vectors)
graph/      LangGraph state, nodes, routing, workflow
mcp_server/ FastMCP tools (server.py) and the LLM-driven router client (client.py)
ingestion/  Document loading/chunking/embedding, web search
frontend/   index.html, css/app.css, js/*.js (ES modules), vendor/ (marked, DOMPurify)
scripts/    init_db, reset_documents
tests/
```

## Notes

- Replaced from the previous version: the Streamlit UI (now `frontend/`), and the SQLite *tickets* table
  (tickets are now *tasks* in Postgres, so the whole app is stateless and easy to host).
- Uploaded filenames are stored as the document source, so answers can cite them.
- Free-hosting walkthrough (Postgres on Neon, app on a free web host) is the next step; the image
  already honours `$PORT` and runs as a non-root user.
