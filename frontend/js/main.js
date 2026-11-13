// App shell: hash router, header/footer, scroll effects, notification bell.
import { api, session, setUnauthorizedHandler } from "./api.js";
import { app } from "./state.js";
import { logoMark } from "./art.js";
import { $, $$, h, icon, avatar, toast, timeAgo, cap } from "./ui.js";

const VIEWS = {
  home: () => import("./home.js"),
  login: () => import("./auth.js"),
  chat: () => import("./chat.js"),
  tasks: () => import("./tasks.js"),
  knowledge: () => import("./knowledge.js"),
  team: () => import("./team.js"),
};
const PROTECTED = new Set(["chat", "tasks", "knowledge", "team"]);
const roleLabel = (r) => (r === "hr" ? "HR" : cap(r));
const brandHtml = (id) => `${logoMark(id)}<span>Enterprise <b>Copilot</b></span>`;

let cleanup = null;
let pendingScroll = null;
let pollTimer = null;
let seenNotifIds = null;
let unread = 0;
let notifItems = [];

// ---------------------------------------------------------------- routing
function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?");
  return { name: path || "home", params: new URLSearchParams(query) };
}

async function route() {
  const { name, params } = parseHash();
  let view = VIEWS[name] ? name : "home";
  if (PROTECTED.has(view) && !app.user) { app.navigate(`#/login?next=${view}`); return; }
  if (view === "team" && !app.isStaff()) { toast("Not available", "The Team page is for HR and managers.", "error"); app.navigate("#/chat"); return; }
  if (view === "login" && app.user) { app.navigate("#/chat"); return; }

  if (cleanup) { try { cleanup(); } catch {} cleanup = null; }
  const root = $("#view");
  root.replaceChildren(h("div", { class: "loading" }, h("div", { class: "spinner blue" })));
  const mod = await VIEWS[view]();
  root.replaceChildren();
  cleanup = (await mod.mount(root, params)) || null;

  document.body.dataset.view = view;
  closeMobileNav();
  highlightNav(view);
  if (pendingScroll) { const id = pendingScroll; pendingScroll = null; requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" })); }
  else window.scrollTo({ top: 0 });
  updateScrollUi();
}

function highlightNav(view) {
  $$("#nav [data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === view));
  $(".nav-dd-btn").classList.toggle("active", ["chat", "tasks", "knowledge", "team"].includes(view));
}

// ----------------------------------------------------------------- header
function renderHeader() {
  $("#brand").innerHTML = brandHtml("hb");
  $("#burger").innerHTML = icon("menu");
  $$("#nav [data-roles]").forEach((a) => a.classList.toggle("hidden-role", !app.isStaff()));

  const box = $("#headerActions");
  box.replaceChildren();
  if (app.user) {
    const bellBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Notifications", "aria-haspopup": "true", html: icon("bell") });
    if (unread) bellBtn.append(h("span", { class: "dot" }, unread > 9 ? "9+" : String(unread)));
    const bellWrap = h("div", { style: "position:relative" }, bellBtn);
    bellBtn.addEventListener("click", (e) => { e.stopPropagation(); togglePopover(bellWrap, notifPanel); });

    const chipBtn = h("button", { class: "user-chip", type: "button", "aria-haspopup": "true" },
      avatar(app.user.name, 38), h("span", { class: "who" }, h("b", null, app.user.name), h("small", null, `${roleLabel(app.user.role)} · ${app.user.department}`)));
    const chipWrap = h("div", { style: "position:relative" }, chipBtn);
    chipBtn.addEventListener("click", (e) => { e.stopPropagation(); togglePopover(chipWrap, userMenu); });

    box.append(bellWrap, chipWrap, h("button", { class: "btn btn-primary hide-m", type: "button", onclick: () => app.navigate("#/chat"), html: icon("chat") + " Open Chatbot" }));
  } else {
    box.append(
      h("button", { class: "link-strong hide-m", type: "button", onclick: () => app.navigate("#/login") }, "Sign in"),
      h("button", { class: "btn btn-primary", type: "button", onclick: () => app.navigate("#/chat"), html: icon("chat") + " Open Chatbot" }));
  }
  $$("#siteFooter .staff-only").forEach((a) => (a.parentElement.hidden = !app.isStaff()));
}

let headerDirty = false;
function closePopovers() { $$(".popover").forEach((p) => p.remove()); if (headerDirty) { headerDirty = false; renderHeader(); } }
function togglePopover(anchor, build) {
  const had = anchor.querySelector(".popover");
  closePopovers();
  if (!had) anchor.append(build());
}
document.addEventListener("click", (e) => { if (!e.target.closest(".popover")) closePopovers(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePopovers(); });

function userMenu() {
  return h("div", { class: "popover", style: "width:280px" },
    h("div", { class: "menu-head" }, h("b", null, app.user.name), h("small", null, `${roleLabel(app.user.role)} · ${app.user.email || app.user.employee_id}`)),
    h("div", { class: "menu-list" },
      h("button", { type: "button", onclick: () => { closePopovers(); app.navigate("#/tasks"); }, html: icon("list") + " My tasks" }),
      h("button", { type: "button", onclick: () => { closePopovers(); app.navigate("#/chat"); }, html: icon("chat") + " Chatbot" }),
      h("button", { type: "button", onclick: logout, html: icon("logout") + " Sign out" })));
}

const KIND_ICON = { task_assigned: "list", task_updated: "edit", task_done: "check", reminder: "clock" };
function notifPanel() {
  const list = h("div", { class: "popover-list" });
  if (!notifItems.length) list.append(h("div", { class: "popover-empty" }, "You’re all caught up."));
  for (const n of notifItems) {
    list.append(h("button", { class: `notif ${n.kind}${n.is_read ? "" : " unread"}`, type: "button", onclick: async () => {
      closePopovers();
      if (!n.is_read) { api.readOne(n.id).catch(() => {}); }
      app.navigate("#/tasks" + (n.task_id ? `?focus=${n.task_id}` : ""));
      pollNotifications(true);
    } },
      h("span", { class: "ico", html: icon(KIND_ICON[n.kind] || "bell") }),
      h("span", null, h("b", null, n.title), n.body ? h("p", null, n.body) : null, h("time", null, timeAgo(n.created_at)))));
  }
  return h("div", { class: "popover" },
    h("div", { class: "popover-head" }, h("h4", null, "Notifications"),
      unread ? h("button", { type: "button", onclick: async () => { await api.readAll(); pollNotifications(true); closePopovers(); } }, "Mark all read") : null),
    list);
}

async function pollNotifications(silent = false) {
  if (!app.user) return;
  try {
    const data = await api.notifications();
    const fresh = seenNotifIds ? data.items.filter((n) => !seenNotifIds.has(n.id) && !n.is_read) : [];
    seenNotifIds = new Set(data.items.map((n) => n.id));
    if (!silent) fresh.slice(0, 3).forEach((n) => toast(n.title, n.body.split("\n")[0], n.kind === "reminder" ? "error" : "info"));
    if (fresh.length) document.dispatchEvent(new CustomEvent("kc:notifications", { detail: fresh }));
    if (data.unread !== unread || data.items.length !== notifItems.length || fresh.length) { unread = data.unread; notifItems = data.items; if ($(".popover")) headerDirty = true; else renderHeader(); }
    else { notifItems = data.items; }
  } catch { /* offline or logged out */ }
}
app.refreshNotifications = () => { seenNotifIds = null; unread = 0; notifItems = []; clearInterval(pollTimer); if (app.user) { pollNotifications(true); pollTimer = setInterval(() => !document.hidden && pollNotifications(), 8000); } };

function logout() {
  closePopovers();
  session.set(null); app.user = null; unread = 0; notifItems = []; seenNotifIds = null; clearInterval(pollTimer);
  renderHeader(); app.navigate("#/");
}
setUnauthorizedHandler(() => { if (app.user) { logout(); toast("Session expired", "Please sign in again.", "error"); } });
app.refreshHeader = renderHeader;

// ----------------------------------------------------------------- footer
function renderFooter() {
  const arrow = icon("arrowR");
  $("#siteFooter").innerHTML = `
    <div class="container">
      <div class="footer-grid">
        <div>
          <a class="brand" href="#/">${brandHtml("fb")}</a>
          <p class="tag">An AI teammate for your company: assign tasks, notify people, and answer questions from your own documents.</p>
          <div class="socials">
            <a href="https://github.com/ash-iiiiish" target="_blank" rel="noopener" aria-label="GitHub">${icon("github")}</a>
          </div>
        </div>
        <div>
          <h4>Navigation</h4>
          <ul class="flinks">
            <li><a href="#/" data-scroll="top">${arrow} Home</a></li>
            <li><a href="#/" data-scroll="why">${arrow} Why Copilot</a></li>
            <li><a href="#/" data-scroll="how">${arrow} How it works</a></li>
            <li><a href="#/" data-scroll="faq">${arrow} FAQ</a></li>
          </ul>
        </div>
        <div>
          <h4>Workspace</h4>
          <ul class="flinks">
            <li><a href="#/chat">${arrow} Chatbot</a></li>
            <li><a href="#/tasks">${arrow} Tasks</a></li>
            <li><a href="#/knowledge">${arrow} Knowledge base</a></li>
            <li><a href="#/team" data-roles="hr manager" class="staff-only">${arrow} Team</a></li>
          </ul>
        </div>
        <div>
          <h4>Under the hood</h4>
          <ul class="stack">
            <li>${icon("layers")}<span>LangGraph<small>Async routing, CRAG &amp; Self-RAG</small></span></li>
            <li>${icon("wrench")}<span>MCP tools<small>Tasks, employees, policies</small></span></li>
            <li>${icon("book")}<span>pgvector + FastAPI<small>Documents and history in Postgres</small></span></li>
          </ul>
        </div>
      </div>
      <div class="copyright">Copyright © ${new Date().getFullYear()} Enterprise Knowledge Copilot. All rights reserved.</div>
    </div>`;
  $$("#siteFooter .staff-only").forEach((a) => (a.parentElement.hidden = !app.isStaff()));
}

// ----------------------------------------------------- global interactions
function goHomeAndScroll(id) {
  const { name } = parseHash();
  if (name === "home") { document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }); return; }
  pendingScroll = id; app.navigate("#/");
}
document.addEventListener("click", (e) => {
  const a = e.target.closest("[data-scroll]");
  if (a) { e.preventDefault(); goHomeAndScroll(a.dataset.scroll); closeMobileNav(); }
});

function closeMobileNav() { $("#nav").classList.remove("open"); $("#burger").setAttribute("aria-expanded", "false"); }
$("#burger").addEventListener("click", () => { const open = $("#nav").classList.toggle("open"); $("#burger").setAttribute("aria-expanded", String(open)); });
const dd = $("#workspaceMenu");
$(".nav-dd-btn", dd).addEventListener("click", (e) => { e.stopPropagation(); const open = dd.classList.toggle("open"); e.currentTarget.setAttribute("aria-expanded", String(open)); });
document.addEventListener("click", (e) => { if (!e.target.closest("#workspaceMenu")) dd.classList.remove("open"); });
$$("#workspaceMenu a").forEach((a) => a.addEventListener("click", () => dd.classList.remove("open")));

$("#toTop").innerHTML = `<span>${icon("arrowUp")}</span>`;
$("#toTop").addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
function updateScrollUi() {
  const max = document.documentElement.scrollHeight - innerHeight;
  $("#progress").style.width = (max > 0 ? (scrollY / max) * 100 : 0) + "%";
  $("#siteHeader").classList.toggle("scrolled", scrollY > 8);
  $("#toTop").classList.toggle("show", scrollY > 600);
}
addEventListener("scroll", updateScrollUi, { passive: true });
addEventListener("resize", updateScrollUi);
addEventListener("hashchange", route);

// -------------------------------------------------------------------- boot
(async function boot() {
  renderHeader();
  try { app.config = await api.config(); } catch {}
  if (session.token) {
    try { const me = await api.me(); app.user = me.user; session.departments = me.departments; }
    catch { session.set(null); }
  }
  renderHeader(); renderFooter();
  app.refreshNotifications();
  await route();
})();
