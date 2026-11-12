// People directory. HR can add members, change roles and deactivate; managers can view.
import { api } from "./api.js";
import { app } from "./state.js";
import { h, icon, avatar, openModal, toast, cap } from "./ui.js";

export async function mount(root) {
  const me = app.user;
  const isHr = me.role === "hr";
  let users = [];
  let q = "";
  const body = h("tbody");
  const search = h("input", { class: "input", style: "max-width:340px", placeholder: "Search people…", "aria-label": "Search people", oninput: (e) => { q = e.target.value.toLowerCase(); draw(); } });
  const page = h("section", { class: "page" }, h("div", { class: "container" },
    h("div", { class: "page-head" },
      h("div", null, h("h1", null, "Team"), h("p", null, isHr ? "Add people, set roles and manage access. Roles decide who can assign work." : "Everyone you can assign work to.")),
      isHr ? h("button", { class: "btn btn-primary", type: "button", onclick: openAdd, html: icon("plus") + " Add member" }) : null),
    h("div", { class: "toolbar" }, search),
    h("div", { class: "card table-card" }, h("table", { class: "tbl" },
      h("thead", null, h("tr", null, ["Person", "Role", "Department", "Status"].map((c) => h("th", null, c)))), body))));
  root.replaceChildren(page);

  async function load() {
    try { users = await api.users(); draw(); } catch (ex) { toast("Couldn’t load team", ex.message, "error"); }
  }

  function draw() {
    const rows = users.filter((u) => !q || u.name.toLowerCase().includes(q) || u.department.toLowerCase().includes(q) || (u.email || "").toLowerCase().includes(q));
    body.replaceChildren(...rows.map((u) => {
      const roleCell = isHr && u.id !== me.id
        ? h("select", { class: "select", "aria-label": `Role for ${u.name}`, onchange: async (e) => {
            try { await api.editUser(u.id, { role: e.target.value }); toast("Role updated", `${u.name} is now ${e.target.value}.`, "ok", 2800); u.role = e.target.value; }
            catch (ex) { toast("Couldn’t change role", ex.message, "error"); e.target.value = u.role; }
          } }, ["employee", "manager", "hr"].map((r) => h("option", { value: r, selected: r === u.role }, r === "hr" ? "HR" : cap(r))))
        : h("span", { class: `pill role ${u.role}` }, u.role === "hr" ? "HR" : u.role);
      const statusCell = isHr && u.id !== me.id
        ? h("button", { class: `btn btn-sm ${u.is_active ? "btn-soft" : "btn-ghost"}`, type: "button", onclick: async () => {
            try { await api.editUser(u.id, { is_active: !u.is_active }); u.is_active = !u.is_active; draw(); } catch (ex) { toast("Couldn’t update", ex.message, "error"); }
          } }, u.is_active ? "Active" : "Inactive")
        : h("span", { class: `pill ${u.is_active ? "done" : "todo"}` }, u.is_active ? "Active" : "Inactive");
      return h("tr", { class: u.is_active ? "" : "off" },
        h("td", null, h("div", { class: "person" }, avatar(u.name, 44), h("div", null, h("b", null, u.id === me.id ? `${u.name} (you)` : u.name), h("small", null, [u.job_title, u.email, u.employee_id].filter(Boolean).join(" · "))))),
        h("td", null, roleCell), h("td", null, u.department), h("td", null, statusCell));
    }));
    if (!rows.length) body.append(h("tr", null, h("td", { colspan: 4 }, h("div", { class: "empty-card" }, "No people match your search."))));
  }

  function openAdd() {
    const f = {
      name: h("input", { class: "input", required: true, placeholder: "Full name" }),
      email: h("input", { class: "input", type: "email", required: true, placeholder: "name@company.com" }),
      password: h("input", { class: "input", type: "text", required: true, minlength: 6, placeholder: "Temporary password" }),
      department: h("input", { class: "input", placeholder: "e.g. Engineering", value: "General" }),
      job_title: h("input", { class: "input", placeholder: "e.g. Software Engineer" }),
      role: h("select", { class: "select" }, ["employee", "manager", "hr"].map((r) => h("option", { value: r }, r === "hr" ? "HR" : cap(r)))),
    };
    const err = h("div", { class: "form-error", hidden: true, role: "alert" });
    openModal("Add team member", (close) => {
      const save = h("button", { class: "btn btn-primary", type: "button", onclick: async () => {
        err.hidden = true; save.disabled = true;
        try {
          await api.addUser(Object.fromEntries(Object.entries(f).map(([k, el]) => [k, el.value])));
          toast("Member added", `${f.name.value} can sign in now.`, "ok"); close(); load();
        } catch (ex) { err.textContent = ex.message; err.hidden = false; save.disabled = false; }
      } }, "Add member");
      return { body: [
        h("div", { class: "row2" }, h("div", { class: "field" }, h("label", null, "Full name"), f.name), h("div", { class: "field" }, h("label", null, "Job title"), f.job_title)),
        h("div", { class: "field" }, h("label", null, "Work email"), f.email),
        h("div", { class: "row2" }, h("div", { class: "field" }, h("label", null, "Department"), f.department), h("div", { class: "field" }, h("label", null, "Role"), f.role)),
        h("div", { class: "field" }, h("label", null, "Password"), f.password), err],
        foot: [h("button", { class: "btn btn-ghost", type: "button", onclick: close }, "Cancel"), save] };
    });
  }

  await load();
  return () => {};
}
