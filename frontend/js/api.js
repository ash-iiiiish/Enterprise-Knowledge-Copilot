// Thin API client. Token lives in localStorage; a 401 anywhere logs the user out.
const BASE = "/api/v1";
const KEY = "kc_token";

export const session = {
  token: (() => { try { return localStorage.getItem(KEY); } catch { return null; } })(),
  user: null,
  departments: [],
  set(token) { this.token = token; try { token ? localStorage.setItem(KEY, token) : localStorage.removeItem(KEY); } catch {} },
};

let onUnauthorized = () => {};
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };

async function request(path, { method = "GET", json, form, auth = true } = {}) {
  const headers = {};
  if (auth && session.token) headers.Authorization = `Bearer ${session.token}`;
  let body;
  if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  if (form) body = form;
  const res = await fetch(BASE + path, { method, headers, body });
  if (res.status === 401 && auth) { onUnauthorized(); throw new Error("Please sign in again."); }
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d) => d.msg).join("; ") : `Request failed (${res.status})`);
  }
  return data;
}

export const api = {
  config: () => request("/auth/config", { auth: false }),
  login: (email, password) => request("/auth/login", { method: "POST", json: { email, password }, auth: false }),
  register: (p) => request("/auth/register", { method: "POST", json: p, auth: false }),
  me: () => request("/auth/me"),

  users: () => request("/users"),
  addUser: (p) => request("/users", { method: "POST", json: p }),
  editUser: (id, p) => request(`/users/${id}`, { method: "PATCH", json: p }),

  tasks: (scope = "mine") => request(`/tasks?scope=${scope}`),
  taskStats: () => request("/tasks/stats"),
  createTask: (p) => request("/tasks", { method: "POST", json: p }),
  patchTask: (id, p) => request(`/tasks/${id}`, { method: "PATCH", json: p }),
  deleteTask: (id) => request(`/tasks/${id}`, { method: "DELETE" }),

  notifications: () => request("/notifications"),
  readAll: () => request("/notifications/read-all", { method: "POST" }),
  readOne: (id) => request(`/notifications/${id}/read`, { method: "POST" }),

  threads: () => request("/threads"),
  messages: (id) => request(`/threads/${id}/messages`),
  deleteThread: (id) => request(`/threads/${id}`, { method: "DELETE" }),
  renameThread: (id, title) => request(`/threads/${id}`, { method: "PATCH", json: { title } }),

  documents: () => request("/documents"),
  deleteDocument: (source) => request(`/documents?source=${encodeURIComponent(source)}`, { method: "DELETE" }),
  ingest: (files) => { const f = new FormData(); files.forEach((file) => f.append("files", file)); return request("/ingest", { method: "POST", form: f }); },
};

/** POST /chat/stream and yield {event, data} frames as they arrive. */
export async function* streamChat(question, threadId, signal) {
  const res = await fetch(BASE + "/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.token}` },
    body: JSON.stringify({ question, thread_id: threadId || null }),
    signal,
  });
  if (res.status === 401) { onUnauthorized(); throw new Error("Please sign in again."); }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try { const j = await res.json(); if (typeof j.detail === "string") msg = j.detail; } catch {}
    throw new Error(msg);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, idx); buf = buf.slice(idx + 2);
      let event = "message"; const data = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trim());
      }
      let payload = {};
      try { payload = data.length ? JSON.parse(data.join("\n")) : {}; } catch {}
      yield { event, data: payload };
    }
  }
}
