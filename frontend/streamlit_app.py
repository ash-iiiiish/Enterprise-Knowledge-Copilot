"""
Streamlit UI for the Enterprise Knowledge Copilot.

Talks to the async FastAPI backend over HTTP (Streamlit's own execution
model is synchronous-per-rerun, so a plain httpx.Client is used here; all
the actual async work happens server-side in the FastAPI/LangGraph app).

Sidebar shows past chat threads (persisted in Postgres). Selecting one loads
its full message history and continues the same conversation; "New chat"
starts a fresh thread.

Run with:  streamlit run frontend/streamlit_app.py
"""
import os

import httpx
import streamlit as st


def _get_backend_url() -> str:
    """Resolve BACKEND_URL from (in order): st.secrets, env var, default.
    st.secrets raises StreamlitSecretNotFoundError if no secrets.toml exists
    at all, so it must be probed inside a try/except rather than via
    st.secrets.get(...), which still triggers the same parse internally."""
    try:
        if "BACKEND_URL" in st.secrets:
            return st.secrets["BACKEND_URL"]
    except Exception:
        pass
    return os.getenv("BACKEND_URL", "http://localhost:8000")


BACKEND_URL = _get_backend_url()
API = f"{BACKEND_URL}/api/v1"

st.set_page_config(page_title="Enterprise Knowledge Copilot", page_icon="🧠", layout="wide")

if "active_thread_id" not in st.session_state:
    st.session_state.active_thread_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []  # [{"role", "content", "sources", "verification"}]


def load_threads():
    try:
        resp = httpx.get(f"{API}/threads", timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        st.sidebar.error(f"Could not load history: {exc}")
        return []


def load_thread_messages(thread_id: str):
    try:
        resp = httpx.get(f"{API}/threads/{thread_id}/messages", timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        st.sidebar.error(f"Could not load thread: {exc}")
        return []


def select_thread(thread_id: str):
    st.session_state.active_thread_id = thread_id
    st.session_state.messages = [
        {
            "role": m["role"],
            "content": m["content"],
            "sources": m.get("sources", []),
            "verification": m.get("verification", ""),
        }
        for m in load_thread_messages(thread_id)
    ]


def new_chat():
    st.session_state.active_thread_id = None
    st.session_state.messages = []


# ---------------------------------------------------------------------------
# Sidebar: chat history + document ingestion
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("🧠 Enterprise Copilot")

    if st.button("➕ New chat", use_container_width=True):
        new_chat()

    st.subheader("History")
    threads = load_threads()

    if not threads:
        st.caption("No conversations yet.")

    for thread in threads:
        is_active = thread["id"] == st.session_state.active_thread_id
        cols = st.columns([5, 1])
        label = ("🟢 " if is_active else "") + thread["title"]
        if cols[0].button(label, key=f"thread_{thread['id']}", use_container_width=True):
            select_thread(thread["id"])
            st.rerun()
        if cols[1].button("🗑", key=f"del_{thread['id']}"):
            try:
                httpx.delete(f"{API}/threads/{thread['id']}", timeout=30)
                if is_active:
                    new_chat()
            except Exception as exc:
                st.error(f"Delete failed: {exc}")
            st.rerun()

    st.divider()
    st.subheader("📄 Ingest documents")
    uploaded_files = st.file_uploader("Upload PDF(s)", type=["pdf"], accept_multiple_files=True)

    if st.button("Ingest", disabled=not uploaded_files):
        with st.spinner("Chunking, embedding and storing in pgvector..."):
            files_payload = [
                ("files", (f.name, f.getvalue(), "application/pdf")) for f in uploaded_files
            ]
            try:
                resp = httpx.post(f"{API}/ingest", files=files_payload, timeout=120)
                resp.raise_for_status()
                for item in resp.json():
                    st.success(f"{item['filename']}: {item['chunks_ingested']} chunks stored")
            except Exception as exc:
                st.error(f"Ingestion failed: {exc}")

    st.divider()
    st.caption(f"Backend: {BACKEND_URL}")

# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------
st.title("Enterprise Knowledge Copilot")
st.caption("RAG + MCP tools + Self-RAG verification, powered by LangGraph")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg["role"] == "assistant":
            cols = st.columns(2)
            cols[0].caption(f"Sources: {', '.join(msg.get('sources', [])) or 'none'}")
            cols[1].caption(f"Verified: {msg.get('verification') or 'n/a'}")

question = st.chat_input("Ask about HR, engineering, compliance or onboarding docs...")

if question:
    with st.chat_message("user"):
        st.write(question)
    st.session_state.messages.append({"role": "user", "content": question, "sources": [], "verification": ""})

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                resp = httpx.post(
                    f"{API}/chat",
                    json={"question": question, "thread_id": st.session_state.active_thread_id},
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()
                answer = data.get("answer", "")
                sources = data.get("sources", [])
                verification = data.get("verification", "")
                st.session_state.active_thread_id = data.get("thread_id")
            except Exception as exc:
                answer, sources, verification = f"Error contacting backend: {exc}", [], ""

        st.write(answer)
        cols = st.columns(2)
        cols[0].caption(f"Sources: {', '.join(sources) or 'none'}")
        cols[1].caption(f"Verified: {verification or 'n/a'}")

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "sources": sources, "verification": verification}
    )
    st.rerun()
