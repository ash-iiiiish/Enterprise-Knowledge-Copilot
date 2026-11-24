// Chatbot workspace: history sidebar, streamed answers, task cards.
// Documents are NOT ingested here: the knowledge base is one shared library managed
// on its own page, so every chat (and every user) reads the same documents.
import { api, streamChat } from "./api.js";
import { app } from "./state.js";
import { robot, logoMark } from "./art.js";
import { h, $, icon, avatar, renderMarkdown, toast, fmtDue, statusLabel, firstName, cap } from "./ui.js";

const SUGGESTIONS = {
  hr: [
    ["list", "Assign a task to everyone", "Assign everyone to complete the security awareness training by Friday, high priority"],
    ["users", "Hand work to one person", "Assign the Q3 hiring report to Priya Sharma by next Monday"],
    ["alert", "What's overdue?", "Show overdue tasks"],
    ["book", "Ask about policy", "What is our work from home policy?"],
  ],
  manager: [
    ["list", "Assign to my team", "Assign Priya Sharma to review the release checklist by tomorrow, urgent"],
    ["flag", "What's still open?", "Show open tasks that I assigned"],
    ["clock", "My own tasks", "Show my pending tasks"],
    ["book", "Ask about policy", "How many paid leaves do employees get?"],
  ],
  employee: [
    ["clock", "What's on my plate?", "Show my pending tasks"],
    ["check", "Finish a task", "Mark task #1 as done"],
    ["plus", "Remind me", "Remind me to submit my timesheet tomorrow"],
    ["book", "Ask about policy", "What is the notice period policy?"],
  ],
};

const TASK_TOOLS = new Set(["assign_task", "update_task", "query_tasks"]);
const RETRY_LABELS = {
  rewriting_query: "Rewriting the search query…",
  web_search_fallback: "Nothing relevant in the documents — searching the web…",
  revising_answer: "Double-checking the answer…",
};

function argsPreview(args = {}) {
  const parts = Object.entries(args).filter(([, v]) => v != null && v !== "").slice(0, 4)
    .map(([k, v]) => `${k}=${typeof v === "string" ? v.slice(0, 28) : JSON.stringify(v).slice(0, 28)}`);
  return parts.join(", ");
}

// ------------------------------------------------------------ task cards
const personLine = (u, notified) => h("span", { class: "who-line" }, avatar(u?.name || "?", 26), u?.name || "Unknown",
  notified ? h("span", { class: "sent", html: icon("check") + " Notified" }) : null);

function taskRow(t, { showAssignee = true, notified = false } = {}) {
  return h("div", { class: "trow" },
    h("span", { class: "id" }, `#${t.id}`),
    h("div", { class: "main" }, h("b", null, t.title), h("small", null, fmtDue(t.due_date))),
    h("span", { class: `pill ${t.overdue ? "overdue" : t.status}` }, t.overdue ? "Overdue" : statusLabel[t.status] || t.status),
    h("span", { class: `pill ${t.priority}` }, t.priority),
    showAssignee ? personLine(t.assigned_to, notified) : null);
}

function resultCard(tool, result) {
  if (!result) return null;
  if (result.error) {
    return h("div", { class: "tcard err" }, h("div", { class: "tcard-head" }, h("span", { class: "ci", html: icon("alert") }), "That didn’t go through"),
      h("div", { class: "trow" }, h("div", { class: "main" }, h("b", { style: "font-weight:400" }, result.error))));
  }
  const goTasks = h("a", { onclick: () => app.navigate("#/tasks") }, "Open Tasks →");
  if (tool === "assign_task") {
    const notifiedIds = new Set((result.notified || []).map((u) => u.id));
    const n = result.count || 0;
    return h("div", { class: "tcard" },
      h("div", { class: "tcard-head" }, h("span", { class: "ci", html: icon("check") }), n === 1 ? "Task assigned" : `${n} tasks assigned`),
      (result.tasks || []).map((t) => taskRow(t, { notified: notifiedIds.has(t.assigned_to?.id) })),
      h("div", { class: "tcard-foot" }, h("span", null, notifiedIds.size ? `${notifiedIds.size} ${notifiedIds.size === 1 ? "person was" : "people were"} notified` : "Saved to your own list"), goTasks));
  }
  if (tool === "update_task") {
    const t = result.task;
    return h("div", { class: "tcard" },
      h("div", { class: "tcard-head" }, h("span", { class: "ci", html: icon("check") }), result.changes?.length ? `Task #${t.id} updated` : `Task #${t.id} — no changes`),
      taskRow(t),
      result.changes?.length ? h("div", { class: "tcard-foot" }, h("span", null, result.changes.join(" · ")), goTasks) : null);
  }
  if (tool === "query_tasks") {
    const list = result.tasks || [];
    if (!list.length) return h("div", { class: "tcard" }, h("div", { class: "tcard-head" }, h("span", { class: "ci info", html: icon("list") }), "No matching tasks"));
    return h("div", { class: "tcard" },
      h("div", { class: "tcard-head" }, h("span", { class: "ci info", html: icon("list") }), `${result.count} ${result.count === 1 ? "task" : "tasks"}`),
      list.slice(0, 8).map((t) => taskRow(t)),
      h("div", { class: "tcard-foot" }, h("span", null, list.length > 8 ? `Showing 8 of ${list.length}` : ""), goTasks));
  }
  return null;
}

// -------------------------------------------------------------- the view
export async function mount(root, params) {
  const user = app.user;
  let threads = [];
  let activeId = null;
  let filter = "";
  let abort = null;
  let streaming = false;

  const botAvatar = () => h("span", { class: "bot-av", html: logoMark("ma" + Math.random().toString(36).slice(2, 7)) });

  // ----- skeleton
  const threadList = h("div", { class: "thread-list", role: "list" });
  const search = h("input", { class: "input", type: "search", placeholder: "Search chats", "aria-label": "Search chats", oninput: (e) => { filter = e.target.value.toLowerCase(); renderThreads(); } });
  const kbCount = h("small", null, "Shared with everyone");
  const kbCard = h("a", { class: "kb-card", href: "#/knowledge" }, h("span", { html: icon("book") }),
    h("span", null, h("b", null, "Knowledge base"), kbCount), h("span", { class: "go", html: icon("arrowR") }));

  const side = h("aside", { class: "chat-side", "aria-label": "Conversations" },
    h("div", { class: "side-top" },
      h("button", { class: "btn btn-primary", type: "button", onclick: () => { newChat(); closeSide(); }, html: icon("plus") + " New chat" }),
      h("div", { class: "searchbox" }, h("span", { html: icon("search") }), search)),
    h("div", { class: "side-label" }, "Recent chats"),
    threadList,
    h("div", { class: "side-foot" }, kbCard));

  const title = h("h2", null, "New chat");
  const scroller = h("div", { class: "chat-scroll", role: "log", "aria-live": "polite" });
  const input = h("textarea", { rows: 1, placeholder: "Ask or assign a task…", "aria-label": "Message", onkeydown: (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(); }
  }, oninput: () => { autosize(); syncSend(); } });
  const sendBtn = h("button", { class: "send", type: "button", "aria-label": "Send", onclick: () => (streaming ? abort?.abort() : submit()), html: icon("send") });
  const composer = h("div", { class: "composer-wrap" },
    h("div", { class: "composer" }, input, sendBtn),
    h("p", { class: "composer-hint" }, "Copilot can make mistakes. Task assignments notify people immediately."));

  const scrim = h("div", { class: "side-scrim", hidden: true, onclick: () => closeSide() });
  const shell = h("section", { class: "chat-shell" },
    side, scrim,
    h("div", { class: "chat-main" },
      h("div", { class: "chat-bar" },
        h("button", { class: "icon-btn side-toggle", type: "button", "aria-label": "Show conversations", onclick: () => openSide(), html: icon("menu") }),
        title, h("span", { class: "badge-online" }, "Online")),
      scroller, composer));
  root.replaceChildren(shell);

  function openSide() { shell.classList.add("side-open"); scrim.hidden = false; }
  function closeSide() { shell.classList.remove("side-open"); scrim.hidden = true; }
  function autosize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 180) + "px"; }
  function syncSend() { sendBtn.disabled = !streaming && !input.value.trim(); }
  function nearBottom() { return scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 140; }
  function toBottom(force = false) { if (force || nearBottom()) scroller.scrollTop = scroller.scrollHeight; }
  function setStreaming(on) {
    streaming = on;
    sendBtn.innerHTML = on ? `<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="3"/></svg>` : icon("send");
    sendBtn.setAttribute("aria-label", on ? "Stop" : "Send");
    syncSend();
  }

  // ----- thread list
  function renderThreads() {
    threadList.replaceChildren();
    const shown = threads.filter((t) => t.title.toLowerCase().includes(filter));
    if (!shown.length) threadList.append(h("div", { class: "side-empty" }, filter ? "No chats match." : "No conversations yet."));
    for (const t of shown) {
      const row = h("div", { class: `thread${t.id === activeId ? " active" : ""}`, role: "listitem", tabindex: 0,
        onclick: () => { openThread(t.id); closeSide(); },
        onkeydown: (e) => { if (e.key === "Enter") openThread(t.id); },
        ondblclick: async () => {
          const name = prompt("Rename chat", t.title);
          if (name && name.trim()) { await api.renameThread(t.id, name.trim()); t.title = name.trim(); renderThreads(); if (t.id === activeId) title.textContent = t.title; }
        } },
        h("span", { class: "t", title: t.title }, t.title),
        h("button", { class: "del", type: "button", "aria-label": `Delete ${t.title}`, html: icon("trash"), onclick: async (e) => {
          e.stopPropagation();
          if (!confirm("Delete this conversation?")) return;
          try { await api.deleteThread(t.id); } catch (ex) { toast("Couldn’t delete", ex.message, "error"); return; }
          threads = threads.filter((x) => x.id !== t.id);
          if (t.id === activeId) newChat(); else renderThreads();
        } }));
      threadList.append(row);
    }
  }
  async function loadThreads() {
    try { threads = await api.threads(); } catch (ex) { toast("Couldn’t load history", ex.message, "error"); }
    renderThreads();
  }

  // ----- message rendering
  function prettySources(sources = []) {
    const out = [];
    for (const s of sources) {
      if (s === "vector_db") out.push("Knowledge base");
      else if (s.startsWith("external_tools")) continue;
    }
    return out;
  }
  function metaRow(m) {
    const chips = [];
    if (m.tool_used) chips.push(h("span", { class: "chip tool", html: icon("wrench") + ` ${m.tool_used}` }));
    for (const s of prettySources(m.sources)) chips.push(h("span", { class: "chip", html: icon("book") + ` ${s}` }));
    if (!TASK_TOOLS.has(m.tool_used) && String(m.verification || "").toUpperCase().startsWith("YES")) chips.push(h("span", { class: "chip ok", html: icon("shield") + " Verified" }));
    chips.push(h("button", { class: "chip chip-btn", type: "button", html: icon("copy") + " Copy", onclick: async (e) => {
      try { await navigator.clipboard.writeText(m.content); e.currentTarget.innerHTML = icon("check") + " Copied"; } catch { toast("Copy failed", "", "error"); }
    } }));
    return h("div", { class: "meta" }, chips);
  }
  function userMsg(text) { return h("div", { class: "msg user" }, h("div", { class: "bubble-user" }, text)); }
  function botMsg(m) {
    const body = h("div", { class: "bot-body" }, h("div", { class: "md", html: renderMarkdown(m.content) }));
    return h("div", { class: "msg" }, botAvatar(), h("div", { class: "bubble-bot" }, body, resultCard(m.tool_used, m.tool_result), metaRow(m)));
  }

  function showEmpty() {
    const items = SUGGESTIONS[user.role] || SUGGESTIONS.employee;
    const hour = new Date().getHours();
    const greet = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
    scroller.replaceChildren(h("div", { class: "empty" },
      h("div", { html: robot("em") }),
      h("h2", null, `${greet}, ${firstName(user.name)}`),
      h("p", null, user.role === "employee" ? "Ask me anything about the company, or check on your tasks." : "Tell me who should do what, and I’ll assign it and let them know."),
      h("div", { class: "suggest" }, items.map(([ic, t, q]) =>
        h("button", { type: "button", onclick: () => { input.value = q; autosize(); syncSend(); input.focus(); } },
          h("span", { class: "si", html: icon(ic) }), h("span", null, h("b", null, t), h("span", { class: "d" }, q)))))));
  }

  function newChat() {
    if (streaming) abort?.abort();
    activeId = null; title.textContent = "New chat"; renderThreads(); showEmpty(); input.focus();
  }

  async function openThread(id) {
    if (streaming) abort?.abort();
    activeId = id;
    const t = threads.find((x) => x.id === id);
    title.textContent = t?.title || "Chat";
    renderThreads();
    scroller.replaceChildren(h("div", { class: "loading" }, h("div", { class: "spinner blue" })));
    try {
      const msgs = await api.messages(id);
      const col = h("div", { class: "chat-col" }, msgs.map((m) => (m.role === "user" ? userMsg(m.content) : botMsg(m))));
      scroller.replaceChildren(col);
      toBottom(true);
    } catch (ex) { toast("Couldn’t open chat", ex.message, "error"); newChat(); }
  }

  // ----- sending
  async function submit() {
    const text = input.value.trim();
    if (!text || streaming) return;
    input.value = ""; autosize();

    let col = scroller.querySelector(".chat-col");
    if (!col) { col = h("div", { class: "chat-col" }); scroller.replaceChildren(col); }
    col.append(userMsg(text));

    const status = h("div", { class: "status-line" }, h("span", { class: "typing" }, h("i"), h("i"), h("i")), h("span", { class: "st" }, "Thinking…"));
    const md = h("div", { class: "md" });
    const body = h("div", { class: "bot-body", hidden: true }, md);
    const extra = h("div");
    const wrap = h("div", { class: "bubble-bot" }, status, body, extra);
    col.append(h("div", { class: "msg" }, botAvatar(), wrap));
    toBottom(true);

    abort = new AbortController();
    setStreaming(true);
    let answer = "", toolUsed = null, toolResult = null, sources = [], verification = "", gotThread = activeId, failed = false;
    let raf = 0;
    const paint = () => { raf = 0; md.innerHTML = renderMarkdown(answer); md.classList.add("caret-blink"); toBottom(); };
    const setStatus = (html) => { status.querySelector(".st").innerHTML = html; };

    try {
      for await (const { event, data } of streamChat(text, activeId, abort.signal)) {
        if (event === "thread") { gotThread = data.thread_id; }
        else if (event === "routing") {
          setStatus(data.need_tools && data.need_retrieval ? "Checking documents and tools…" : data.need_tools ? "Picking the right tool…" : data.need_retrieval ? "Searching company documents…" : "Thinking…");
        } else if (event === "tool_call") {
          toolUsed = data.tool_used; if (data.result !== undefined) toolResult = data.result;
          const st = status.querySelector(".st"); st.textContent = "Running "; st.append(h("code", null, `${toolUsed}(${argsPreview(data.arguments)})`), "…");
        } else if (event === "retry") { setStatus(RETRY_LABELS[data.stage] || "Retrying…"); }
        else if (event === "token") {
          if (!answer) { status.hidden = true; body.hidden = false; }
          answer += data.text; if (!raf) raf = requestAnimationFrame(paint);
        } else if (event === "done") {
          sources = data.sources || []; toolUsed = data.tool_used || toolUsed; toolResult = data.tool_result ?? toolResult; verification = data.verification || "";
          gotThread = data.thread_id || gotThread;
        } else if (event === "error") { failed = true; answer = answer || `Sorry — something went wrong: ${data.detail}`; }
      }
    } catch (ex) {
      if (ex.name === "AbortError") { answer = answer || "Stopped."; } else { failed = true; answer = answer || `I couldn’t reach the server: ${ex.message}`; }
    } finally {
      if (raf) cancelAnimationFrame(raf);
      status.hidden = true; body.hidden = false; md.classList.remove("caret-blink");
      md.innerHTML = renderMarkdown(answer || "…");
      if (failed) body.style.borderColor = "#f4c1c6";
      const m = { content: answer, tool_used: toolUsed, tool_result: toolResult, sources, verification };
      extra.replaceChildren(...[resultCard(toolUsed, toolResult), failed ? null : metaRow(m)].filter(Boolean));
      setStreaming(false); abort = null; toBottom(true);
      if (gotThread && gotThread !== activeId) { activeId = gotThread; }
      await loadThreads();
      const t = threads.find((x) => x.id === activeId); if (t) title.textContent = t.title;
      input.focus();
    }
  }

  async function loadKbInfo() {
    try {
      const { documents } = await api.documents();
      kbCount.textContent = documents.length ? `${documents.length} ${documents.length === 1 ? "document" : "documents"} · shared` : (app.isStaff() ? "Empty — add documents" : "No documents yet");
    } catch { /* keep default text */ }
  }

  // ----- go
  syncSend();
  showEmpty();
  const ask = params?.get("ask");
  if (ask) { input.value = ask; autosize(); syncSend(); }
  loadKbInfo();
  await loadThreads();
  input.focus();
  return () => { abort?.abort(); };
}
