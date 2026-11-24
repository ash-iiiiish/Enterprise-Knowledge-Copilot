// Tasks board: assigned to me / by me / all, with status actions and a "new task" form.
import { api, session } from "./api.js";
import { app } from "./state.js";
import { h, icon, avatar, openModal, toast, fmtDue, statusLabel, cap } from "./ui.js";

const COLS = [["todo", "To do"], ["in_progress", "In progress"], ["done", "Done"]];

export async function mount(root, params) {
  const me = app.user;
  let scope = "mine";
  let tasks = [];
  let focusId = Number(params.get("focus")) || null;
  const board = h("div", { class: "board" });
  const stats = h("div", { class: "stats" });
  const tabs = h("div", { class: "tabs", style: "width:fit-content;margin:0" });
  const page = h("section", { class: "page" }, h("div", { class: "container" },
    h("div", { class: "page-head" },
      h("div", null, h("h1", null, "Tasks"), h("p", null, me.role === "employee" ? "Work assigned to you. Move cards forward as you go — the person who assigned it is told automatically." : "Everything you’ve been given and everything you’ve handed out, in one place.")),
      h("button", { class: "btn btn-primary", type: "button", onclick: openNew, html: icon("plus") + " New task" })),
    stats, h("div", { class: "toolbar" }, tabs), board));
  root.replaceChildren(page);

  const scopes = [["mine", "Assigned to me"], ["assigned_by_me", "Assigned by me"], ...(me.role === "hr" ? [["all", "All tasks"]] : [])];
  function renderTabs() {
    tabs.replaceChildren(...scopes.map(([k, label]) => h("button", { type: "button", class: scope === k ? "active" : "", onclick: () => { scope = k; renderTabs(); load(); } }, label)));
  }

  async function load() {
    try {
      const [t, s] = await Promise.all([api.tasks(scope), api.taskStats()]);
      tasks = t.tasks; renderStats(s); renderBoard();
    } catch (ex) { toast("Couldn’t load tasks", ex.message, "error"); }
  }

  function renderStats(s) {
    const tile = (cls, ic, n, label) => h("div", { class: `stat ${cls}` }, h("span", { class: "si", html: icon(ic) }), h("div", null, h("b", null, String(n)), h("span", null, label)));
    stats.replaceChildren(tile("", "list", s.todo, "To do"), tile("", "clock", s.in_progress, "In progress"), tile("okk", "check", s.done, "Done"), tile("warn", "alert", s.overdue, "Overdue"));
  }

  async function setStatus(t, status) {
    try { await api.patchTask(t.id, { status }); toast(status === "done" ? "Nice — marked as done" : "Task updated", t.created_by && t.created_by.id !== me.id ? `${t.created_by.name} has been notified.` : "", "ok", 3200); load(); }
    catch (ex) { toast("Couldn’t update", ex.message, "error"); }
  }

  function card(t) {
    const isAssignee = t.assigned_to?.id === me.id;
    const isOwner = t.created_by?.id === me.id || me.role === "hr";
    const actions = [];
    if (isAssignee || isOwner) {
      if (t.status === "todo") actions.push(h("button", { class: "btn btn-soft btn-sm", type: "button", onclick: () => setStatus(t, "in_progress") }, "Start"));
      if (t.status !== "done") actions.push(h("button", { class: "btn btn-primary btn-sm", type: "button", onclick: () => setStatus(t, "done"), html: icon("check") + " Done" }));
      else actions.push(h("button", { class: "btn btn-ghost btn-sm", type: "button", onclick: () => setStatus(t, "todo") }, "Reopen"));
    }
    const el = h("article", { class: `tk${t.id === focusId ? " flash" : ""}`, id: `task-${t.id}` },
      h("div", { class: "tags" },
        h("span", { class: `pill ${t.priority}` }, t.priority),
        t.overdue ? h("span", { class: "pill overdue" }, "Overdue") : null,
        h("span", { class: "pill" , style: "background:#f3f5fa" }, `#${t.id}`)),
      h("h4", null, t.title),
      t.description ? h("p", { class: "desc" }, t.description) : null,
      h("div", { class: "tags" }, h("span", { class: "chip", html: icon("clock") + " " }, fmtDue(t.due_date)),
        t.via_chatbot ? h("span", { class: "bot-tag", html: icon("chat") + " via chatbot" }) : null),
      h("div", { class: "foot" },
        h("span", { class: "who-line", title: "Assigned by → to" }, avatar(t.created_by?.name, 26), "→", avatar(t.assigned_to?.name, 26),
          h("span", null, isAssignee ? `from ${t.created_by?.name?.split(" ")[0]}` : `to ${t.assigned_to?.name?.split(" ")[0]}`)),
        h("span", { class: "spacer" }),
        actions,
        isOwner ? h("button", { class: "icon-btn", style: "width:36px;height:36px;border-radius:10px", type: "button", "aria-label": "Delete task", html: icon("trash"), onclick: async () => {
          if (!confirm(`Delete “${t.title}”?`)) return;
          try { await api.deleteTask(t.id); load(); } catch (ex) { toast("Couldn’t delete", ex.message, "error"); }
        } }) : null));
    return el;
  }

  function renderBoard() {
    board.replaceChildren(...COLS.map(([key, label]) => {
      const items = tasks.filter((t) => t.status === key);
      return h("div", { class: `col ${key}` },
        h("div", { class: "col-head" }, h("span", { class: "dot" }), label, h("span", { class: "count" }, String(items.length))),
        h("div", { class: "col-body" }, items.length ? items.map(card) : h("div", { class: "col-empty" }, key === "done" ? "Nothing completed yet" : "Nothing here")));
    }));
    if (focusId) { document.getElementById(`task-${focusId}`)?.scrollIntoView({ block: "center", behavior: "smooth" }); focusId = null; }
  }

  // ------------------------------------------------------------- new task
  async function openNew() {
    let people = [];
    try { people = (await api.users()).filter((u) => u.id !== me.id || true); } catch {}
    const picked = new Set();
    const title = h("input", { class: "input", placeholder: "e.g. Prepare the Q3 sales report", required: true, maxlength: 200 });
    const desc = h("textarea", { class: "textarea", placeholder: "Optional details" });
    const prio = h("select", { class: "select" }, ["low", "medium", "high", "urgent"].map((p) => h("option", { value: p, selected: p === "medium" }, cap(p))));
    const today = new Date(); const iso = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const due = h("input", { class: "input", type: "date", min: iso(today) });
    const err = h("div", { class: "form-error", hidden: true, role: "alert" });

    const canAssign = me.role !== "employee";
    const depts = [...new Set(people.map((p) => p.department))].sort();
    const group = h("select", { class: "select" },
      h("option", { value: "" }, "— no team —"),
      (me.role === "hr" ? ["Everyone", ...depts] : depts.filter((d) => d === me.department)).map((d) => h("option", { value: d === "Everyone" ? "everyone" : d }, d === "Everyone" ? "Everyone in the company" : `${d} team`)));

    const list = h("div", { class: "picker-list" });
    const q = h("input", { class: "input", placeholder: "Search people…", "aria-label": "Search people", oninput: draw });
    function draw() {
      const term = q.value.toLowerCase();
      list.replaceChildren(...people.filter((p) => !term || p.name.toLowerCase().includes(term) || p.department.toLowerCase().includes(term)).map((p) =>
        h("label", { class: "pick" },
          h("input", { type: "checkbox", checked: picked.has(p.id), onchange: (e) => (e.target.checked ? picked.add(p.id) : picked.delete(p.id)) }),
          avatar(p.name, 34), h("span", null, h("b", null, p.id === me.id ? `${p.name} (me)` : p.name), h("small", null, `${p.job_title || cap(p.role)} · ${p.department}`)))));
    }
    draw();

    openModal("New task", (close) => {
      const submit = h("button", { class: "btn btn-primary", type: "button", onclick: async () => {
        err.hidden = true;
        if (!title.value.trim()) { err.textContent = "Give the task a title."; err.hidden = false; return; }
        submit.disabled = true;
        try {
          const r = await api.createTask({ title: title.value, description: desc.value, assignee_ids: [...picked], department: group.value || null, priority: prio.value, due_date: due.value || null });
          const n = r.notified?.length || 0;
          toast(r.count === 1 ? "Task created" : `${r.count} tasks created`, n ? `${n} ${n === 1 ? "person has" : "people have"} been notified.` : "Added to your list.", "ok");
          close(); scope = "assigned_by_me" === scope ? scope : (n ? "assigned_by_me" : "mine"); renderTabs(); load();
        } catch (ex) { err.textContent = ex.message; err.hidden = false; submit.disabled = false; }
      } }, "Create task");
      return {
        body: [
          h("div", { class: "field" }, h("label", null, "Title"), title),
          h("div", { class: "field" }, h("label", null, "Details"), desc),
          canAssign ? h("div", { class: "field" }, h("span", { class: "label" }, "Assign to"), h("div", { class: "picker" }, q, list), h("small", { style: "color:var(--muted)" }, "Leave empty to keep it for yourself.")) : h("p", { style: "color:var(--muted)" }, "This task will be added to your own list. Ask HR or your manager to assign work to others."),
          canAssign ? h("div", { class: "field" }, h("label", null, "…or a whole team"), group) : null,
          h("div", { class: "row2" }, h("div", { class: "field" }, h("label", null, "Priority"), prio), h("div", { class: "field" }, h("label", null, "Due date"), due)),
          err],
        foot: [h("button", { class: "btn btn-ghost", type: "button", onclick: close }, "Cancel"), submit],
      };
    });
  }

  renderTabs();
  await load();
  const onNotif = () => load();
  document.addEventListener("kc:notifications", onNotif);
  return () => document.removeEventListener("kc:notifications", onNotif);
}
