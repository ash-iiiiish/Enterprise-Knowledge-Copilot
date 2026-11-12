// Small DOM + UI helpers. All dynamic text goes through textContent (via h())
// so user-supplied strings can never inject markup.

const ICONS = {
  plus: "M12 5v14M5 12h14",
  chat: "M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z",
  check: "M5 12.5l4.5 4.5L19 7.5",
  x: "M6 6l12 12M18 6L6 18",
  bell: "M18 16v-5a6 6 0 1 0-12 0v5l-2 2h16zM10 21h4",
  send: "M22 2L11 13M22 2l-7 20-4-9-9-4z",
  clip: "M21 11l-9 9a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-4.5-4.5",
  menu: "M4 6h16M4 12h16M4 18h16",
  logout: "M9 4H5v16h4M16 8l4 4-4 4M20 12H9",
  copy: "M9 9h11v11H9zM5 15V4h11",
  wrench: "M14.7 6.3a4 4 0 0 0-5 5L3 18l3 3 6.7-6.7a4 4 0 0 0 5-5l-2.5 2.5-2.7-.7-.7-2.7z",
  clock: "M12 7v5l3 2M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z",
  users: "M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9.5 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM21 20v-1a4 4 0 0 0-3-3.9M16 4.1a3.5 3.5 0 0 1 0 6.8",
  book: "M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 19V5M8 7h7",
  file: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5",
  arrowR: "M5 12h14M13 6l6 6-6 6",
  arrowUp: "M12 19V5M6 11l6-6 6 6",
  alert: "M12 8v5M12 17h.01M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  flag: "M5 21V4M5 4h11l-2 4 2 4H5",
  upload: "M12 16V4M7 9l5-5 5 5M4 20h16",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  zap: "M13 2L4 14h7l-1 8 9-12h-7z",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  github: "M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22",
  layers: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17.500l9 5 9-5",
  link: "M10 14a4 4 0 0 0 5.700 0l3-3a4 4 0 0 0-5.700-5.700l-1 1M14 10a4 4 0 0 0-5.700 0l-3 3a4 4 0 0 0 5.700 5.700l1-1",
  sparkle: "M12 3l2 5.500L19.500 10 14 12l-2 5.500L10 12 4.500 10 10 8.500zM19 16l.8 2.200L22 19l-2.200.8L19 22l-.8-2.200L16 19l2.200-.8z",
  edit: "M4 20h4L19 9l-4-4L4 16zM13.500 6.500l4 4",
  eye: "M2 12s3.500-7 10-7 10 7 10 7-3.500 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
};

export function icon(name, extra = "") {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ${extra}><path d="${ICONS[name] || ""}"/></svg>`;
}

/** h("div", {class:"x", onclick:fn}, "text", childEl) -> HTMLElement */
export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v; // only ever called with static/trusted markup
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return el;
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const PALETTE = ["#2f6bff", "#7a3fd0", "#0a8f6f", "#e0731a", "#d63a6a", "#0a7a99", "#5b6bdf", "#b4532a"];
export function avatar(name = "?", size = 40) {
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase() || "?";
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return h("span", { class: "avatar", style: `--size:${size}px;background:${PALETTE[hash % PALETTE.length]}`, "aria-hidden": "true" }, initials);
}

export function renderMarkdown(text) {
  const raw = window.marked ? window.marked.parse(text || "", { breaks: true, gfm: true }) : (text || "");
  return window.DOMPurify ? window.DOMPurify.sanitize(raw, { ADD_ATTR: ["target"] }) : "";
}

export function toast(title, body = "", kind = "info", ms = 5200) {
  const root = $("#toasts");
  const el = h("div", { class: `toast ${kind}`, role: "status" }, h("div", null, h("b", null, title), body ? h("p", null, body) : null));
  root.append(el);
  setTimeout(() => { el.style.transition = "opacity .3s, transform .3s"; el.style.opacity = "0"; el.style.transform = "translateX(30px)"; setTimeout(() => el.remove(), 320); }, ms);
}

/** Opens a modal. `build(close)` must return {body, foot}. Resolves nothing; callers use callbacks. */
export function openModal(title, build) {
  const root = $("#modalRoot");
  const prevFocus = document.activeElement;
  const close = () => { backdrop.remove(); document.removeEventListener("keydown", onKey); prevFocus?.focus?.(); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  const { body, foot } = build(close);
  const modal = h("div", { class: "modal", role: "dialog", "aria-modal": "true", "aria-label": title },
    h("div", { class: "modal-head" }, h("h3", null, title), h("button", { class: "x-btn", type: "button", "aria-label": "Close", onclick: close, html: icon("x") })),
    h("div", { class: "modal-body" }, body),
    foot ? h("div", { class: "modal-foot" }, foot) : null,
  );
  const backdrop = h("div", { class: "modal-backdrop", onmousedown: (e) => { if (e.target === backdrop) close(); } }, modal);
  root.append(backdrop);
  document.addEventListener("keydown", onKey);
  (modal.querySelector("input,textarea,select,button.btn") || modal).focus();
  return close;
}

export function timeAgo(iso) {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 172800) return "yesterday";
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function fmtDue(iso) {
  if (!iso) return "No due date";
  const d = new Date(iso + "T00:00:00");
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.round((d - today) / 86400000);
  if (diff === 0) return "Due today";
  if (diff === 1) return "Due tomorrow";
  if (diff === -1) return "Due yesterday";
  return "Due " + d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

export const statusLabel = { todo: "To do", in_progress: "In progress", done: "Done" };
export const cap = (s = "") => s.charAt(0).toUpperCase() + s.slice(1);
export const firstName = (n = "") => n.split(" ")[0];
