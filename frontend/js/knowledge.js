// Knowledge base: ONE shared company library. HR/managers add a document once;
// it is embedded into the shared vector store and every user can ask about it in
// any chat, now or later. Chats never own documents - they only read this library.
import { api } from "./api.js";
import { app } from "./state.js";
import { h, icon, toast, timeAgo } from "./ui.js";

const typeOf = (name) => (name.split(".").pop() || "file").toLowerCase();
const pct = (n) => n.toLocaleString();

export async function mount(root) {
  const me = app.user;
  const staff = app.isStaff();
  let docs = [];
  let filter = "";

  // ----- upload (staff only)
  const input = h("input", { type: "file", accept: ".pdf,.txt,.md", multiple: true, hidden: true,
    onchange: (e) => upload([...e.target.files]).finally(() => (e.target.value = "")) });
  const pickBtn = h("button", { class: "btn btn-primary btn-sm", type: "button", onclick: () => input.click(), html: icon("upload") + " Add documents" });
  const dropBar = staff ? h("div", { class: "kb-drop",
      ondragover: (e) => { e.preventDefault(); dropBar.classList.add("over"); },
      ondragleave: () => dropBar.classList.remove("over"),
      ondrop: (e) => { e.preventDefault(); dropBar.classList.remove("over"); upload([...e.dataTransfer.files]); } },
    h("span", { class: "di", html: icon("upload") }),
    h("div", { class: "grow" }, h("b", null, "Add once, everyone can use it"),
      h("small", null, "Drop PDF, TXT or MD files here (15 MB max). Re-uploading a file with the same name replaces the old version.")),
    pickBtn, input) : null;

  // ----- layout
  const stats = h("div", { class: "kb-stats" });
  const search = h("input", { class: "input", type: "search", placeholder: "Search documents", "aria-label": "Search documents",
    oninput: (e) => { filter = e.target.value.toLowerCase(); renderList(); } });
  const toolbar = h("div", { class: "kb-toolbar" }, h("div", { class: "searchbox" }, h("span", { html: icon("search") }), search));
  const list = h("div", { class: "card kb-list" }, h("div", { class: "loading" }, h("div", { class: "spinner blue" })));

  root.replaceChildren(h("section", { class: "page" }, h("div", { class: "container" },
    h("div", { class: "page-head" },
      h("div", null, h("h1", null, "Knowledge base"),
        h("p", null, "The company’s shared library. Documents are added once and are available to everyone, in every chat — no one has to upload them again."))),
    stats, dropBar, toolbar, list)));

  function renderStats() {
    const chunks = docs.reduce((n, d) => n + d.chunks, 0);
    const latest = docs.map((d) => d.added).filter(Boolean).sort().pop();
    const tile = (ic, value, label) => h("div", { class: "kb-stat" }, h("span", { class: "si", html: icon(ic) }), h("div", null, h("b", null, value), h("small", null, label)));
    stats.replaceChildren(
      tile("file", pct(docs.length), docs.length === 1 ? "document" : "documents"),
      tile("layers", pct(chunks), "searchable passages"),
      tile("clock", latest ? timeAgo(latest) : "—", "last updated"));
  }

  function row(d) {
    const t = typeOf(d.source);
    const by = d.uploaded_by ? ` by ${d.uploaded_by}` : "";
    return h("div", { class: "doc" },
      h("span", { class: `fi ft-${t}` }, h("em", null, t.toUpperCase())),
      h("div", { class: "grow" }, h("b", null, d.source), h("small", null, `${pct(d.chunks)} passages · added ${timeAgo(d.added)}${by}`)),
      h("button", { class: "btn btn-ghost btn-sm", type: "button", title: "Open a new chat about this document",
        onclick: () => app.navigate(`#/chat?ask=${encodeURIComponent(`Summarize the document “${d.source}” and list the key points.`)}`), html: icon("chat") + " Ask" }),
      me.role === "hr" ? h("button", { class: "btn btn-danger btn-sm", type: "button", onclick: async () => {
        if (!confirm(`Remove “${d.source}” from the knowledge base? It will disappear for everyone.`)) return;
        try { await api.deleteDocument(d.source); toast("Removed", d.source, "ok", 2500); await load(); } catch (ex) { toast("Couldn’t remove", ex.message, "error"); }
      } }, "Remove") : null);
  }

  function renderList() {
    toolbar.hidden = !docs.length;
    if (!docs.length) {
      list.replaceChildren(h("div", { class: "empty-card" },
        h("div", { class: "empty-ico", html: icon("book") }),
        h("h3", null, "Nothing here yet"),
        h("p", null, staff ? "Add your first policy, scheme or handbook above. It becomes available to every employee straight away." : "No documents have been added yet. HR will publish them here.")));
      return;
    }
    const shown = docs.filter((d) => d.source.toLowerCase().includes(filter));
    list.replaceChildren(...(shown.length ? shown.map(row) : [h("div", { class: "empty-card" }, "No documents match your search.")]));
  }

  async function load() {
    try { docs = (await api.documents()).documents; renderStats(); renderList(); }
    catch (ex) { list.replaceChildren(h("div", { class: "empty-card" }, ex.message)); }
  }

  async function upload(files) {
    if (!files.length) return;
    pickBtn.disabled = true; pickBtn.replaceChildren(h("span", { class: "spinner" }), " Processing…");
    try {
      const res = await api.ingest(files);
      res.forEach((r) => toast(r.filename, `${r.replaced ? "Updated" : "Added"} · ${r.chunks_ingested} passages`, "ok"));
      await load();
    } catch (ex) { toast("Upload failed", ex.message, "error"); }
    finally { pickBtn.disabled = false; pickBtn.innerHTML = icon("upload") + " Add documents"; }
  }

  await load();
  return () => {};
}
