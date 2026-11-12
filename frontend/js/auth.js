// Sign in / create account.
import { api, session } from "./api.js";
import { app } from "./state.js";
import { h, toast } from "./ui.js";

export function mount(root, params) {
  let mode = "login";
  const next = params.get("next") || "chat";

  const card = h("div", { class: "auth-card" });
  root.replaceChildren(h("section", { class: "auth" }, card));

  function render() {
    const err = h("div", { class: "form-error", hidden: true, role: "alert" });
    const email = h("input", { class: "input", type: "email", name: "email", autocomplete: "email", placeholder: "you@company.com", required: true });
    const pass = h("input", { class: "input", type: "password", name: "password", autocomplete: mode === "login" ? "current-password" : "new-password", placeholder: mode === "login" ? "Your password" : "At least 6 characters", required: true, minlength: 6 });
    const name = h("input", { class: "input", name: "name", autocomplete: "name", placeholder: "Your full name", required: true, minlength: 2 });
    const dept = h("input", { class: "input", name: "department", placeholder: "e.g. Engineering", value: "General" });
    const submit = h("button", { class: "btn btn-primary", type: "submit" }, mode === "login" ? "Sign in" : "Create account");

    const form = h("form", { novalidate: false, onsubmit: async (e) => {
      e.preventDefault();
      err.hidden = true; submit.disabled = true;
      try {
        const res = mode === "login"
          ? await api.login(email.value, pass.value)
          : await api.register({ name: name.value, email: email.value, password: pass.value, department: dept.value || "General" });
        session.set(res.token);
        const me = await api.me();
        app.user = me.user; session.departments = me.departments;
        app.refreshHeader(); app.refreshNotifications();
        toast(`Welcome${mode === "login" ? " back" : ""}, ${res.user.name.split(" ")[0]}`, "", "ok", 2800);
        app.navigate("#/" + next);
      } catch (ex) {
        err.textContent = ex.message; err.hidden = false;
      } finally { submit.disabled = false; }
    } },
      mode === "register" ? h("div", { class: "field" }, h("label", null, "Full name"), name) : null,
      h("div", { class: "field" }, h("label", null, "Work email"), email),
      h("div", { class: "field" }, h("label", null, "Password"), pass),
      mode === "register" ? h("div", { class: "field" }, h("label", null, "Department"), dept) : null,
      err, submit);

    const tabs = h("div", { class: "tabs", role: "tablist" },
      h("button", { type: "button", class: mode === "login" ? "active" : "", role: "tab", onclick: () => { mode = "login"; render(); } }, "Sign in"),
      app.config.allow_signup ? h("button", { type: "button", class: mode === "register" ? "active" : "", role: "tab", onclick: () => { mode = "register"; render(); } }, "Create account") : null);

    card.replaceChildren(
      h("h1", null, mode === "login" ? "Welcome back" : "Join your team"),
      h("p", { class: "sub" }, mode === "login" ? "Sign in to open the Copilot." : "Create an employee account to get started."),
      tabs, form);
    (mode === "login" ? email : name).focus();
  }
  render();
  return () => {};
}
