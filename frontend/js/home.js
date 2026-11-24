// Landing page: explains why the Copilot is useful, then a big centred chat button.
import { robot, plane, bubble, logoMark } from "./art.js";
import { icon, $$ } from "./ui.js";
import { app } from "./state.js";

const FEATURES = [
  ["list", "Assign work by chatting", "Type “assign the Q3 report to Priya by Friday” and the Copilot creates the task with an owner, priority and due date."],
  ["bell", "Instant notifications", "The right person is told the moment a task lands — bell, pop-up and optional email — plus reminders before and after the deadline."],
  ["book", "Answers from your documents", "Upload policies and handbooks once. Ask in plain language and get answers pulled straight from them, with sources."],
  ["shield", "Verified, not guessed", "Every answer is checked against its context before it reaches you. Weak matches trigger a rewrite and a web fallback."],
  ["wrench", "Real tools through MCP", "Employee lookup, company policies, task updates — the Copilot calls actual tools instead of making things up."],
  ["users", "Built around roles", "HR assigns to anyone, managers to their teams, employees to themselves. Everyone sees only what they should."],
];

const STEPS = [
  ["Ask in plain language", "No forms, no commands. Just say what you need, the way you would to a colleague.", "“Assign the sales deck to Sneha by Friday, high priority.”"],
  ["The Copilot picks the path", "It decides whether to search your documents, call a tool, or both — then runs it for you.", "documents → tools → verified answer"],
  ["Everyone is in the loop", "The assignee is notified, you get a confirmation card, and status changes flow back to you.", "Sneha is notified · you see progress live"],
];

const FAQ = [
  ["Why assign tasks through the chatbot instead of WhatsApp?", "In a group chat a task is just a message. Here it is stored with an owner, due date and status, the assignee is notified directly, and reminders go out before the deadline. Nothing gets buried and nobody has to chase."],
  ["Who is allowed to assign tasks?", "HR can assign to any person, a department, or the whole company. Managers can assign to individuals or to their own department. Employees can create tasks for themselves. The server enforces this — the chatbot cannot bypass it."],
  ["How does it answer questions from company documents?", "Documents (PDF, TXT, MD) uploaded to the Knowledge base are split into chunks and embedded into a vector database. Your question retrieves the most relevant chunks, the answer is generated from them, and a verification step checks it is actually supported. If nothing relevant is found, it rewrites the query and falls back to a web search."],
  ["How do people get informed about new tasks?", "Instantly in the app (the bell icon and a pop-up), and by email if SMTP is configured. A background job also sends reminders when a task is due within a day or overdue."],
  ["Are my conversations private?", "Yes. Chat history is stored per user and only the owner can open it."],
  ["Do I need any technical knowledge?", "None. If you can write a message to a colleague you can use it. The Tasks page offers the same features with a normal form if you prefer clicking."],
];

const tick = icon("check");

export function mount(root) {
  root.innerHTML = `
  <section class="hero" id="top">
    <div class="container hero-grid">
      <div>
        <div class="checks">
          <span class="check"><i>${tick}</i> Tasks assigned inside the chat</span>
          <span class="check"><i>${tick}</i> No more WhatsApp forwarding</span>
        </div>
        <h1>Boost Team Productivity with Our Intelligent <span class="hl">Copilot</span> Platform</h1>
        <p class="lead">One workspace where HR assigns work, every employee is notified instantly, and anyone can get verified answers from company documents — just by asking.</p>
        <div class="hero-cta">
          <button class="btn btn-primary btn-lg" data-go="chat">${icon("chat")} Open Chatbot</button>
          <button class="btn btn-ghost btn-lg" data-scroll-to="why">See why it helps</button>
        </div>
      </div>
      <div class="hero-art">
        ${robot("hero")}
        <div class="speech">${logoMark("sp")}<span>Hey, how can we help you?</span></div>
        <div class="float-bubble">${bubble("hb")}</div>
      </div>
    </div>
  </section>

  <section class="section tint" id="why">
    <div class="container">
      <div class="section-head">
        <span class="eyebrow">${icon("sparkle", 'width="18" height="18"')} Why Enterprise Copilot</span>
        <h2>Stop losing work in <span class="hl">group chats</span></h2>
        <p>Company tasks are still handed out on WhatsApp and answered by whoever happens to be online. The Copilot turns that into one accountable, searchable system.</p>
      </div>
      <div class="ba">
        <article class="ba-card before">
          <h3>Before <span class="tag">WhatsApp &amp; email</span></h3>
          <ul>
            <li><i>${icon("x")}</i>Tasks buried under hundreds of messages</li>
            <li><i>${icon("x")}</i>No clear owner, due date or status</li>
            <li><i>${icon("x")}</i>“Seen” doesn’t mean done — endless follow-ups</li>
            <li><i>${icon("x")}</i>Policy questions interrupt HR all day</li>
          </ul>
        </article>
        <article class="ba-card after">
          <h3>After <span class="tag">Enterprise Copilot</span></h3>
          <ul>
            <li><i>${tick}</i>Say it once in the chat — the task is created</li>
            <li><i>${tick}</i>Each person is notified instantly, with reminders</li>
            <li><i>${tick}</i>Progress tracked on a live task board</li>
            <li><i>${tick}</i>Policy and document answers on demand, with sources</li>
          </ul>
        </article>
      </div>
      <div class="features" style="margin-top:34px">
        ${FEATURES.map(([ic, t, d]) => `<article class="feature"><div class="fi">${icon(ic)}</div><h3>${t}</h3><p>${d}</p></article>`).join("")}
      </div>
    </div>
  </section>

  <section class="section" id="how">
    <div class="container">
      <div class="section-head">
        <span class="eyebrow">${icon("zap", 'width="18" height="18"')} How it works</span>
        <h2>From a sentence to <span class="hl">done</span> in three steps</h2>
      </div>
      <div class="steps">
        ${STEPS.map(([t, d, ex]) => `<article class="step"><h3>${t}</h3><p>${d}</p><div class="demo-line">${ex}</div></article>`).join("")}
      </div>
    </div>
  </section>

  <section class="cta-band" id="start">
    <div class="cta-plane">${plane("cp")}</div>
    <div class="cta-bubble-a">${bubble("ca")}</div>
    <div class="cta-bubble-b">${bubble("cb")}</div>
    <div class="container">
      <span class="eyebrow">${icon("chat", 'width="18" height="18"')} Ready when you are</span>
      <h2>Ready to talk to your <span class="hl">Copilot</span>?</h2>
      <p>Ask a question, hand out a task or check what’s due — everything starts in the chat.</p>
      <div class="cta-center">
        <button class="btn btn-primary btn-chat" data-go="chat">${icon("chat")} Open Chatbot</button>
        <span class="cta-note" id="ctaNote"></span>
      </div>
    </div>
  </section>

  <section class="section tint" id="faq">
    <div class="container faq-wrap">
      <div class="faq-plane">${plane("fp")}</div>
      <div class="section-head" style="margin-bottom:54px">
        <h2>Answers to Your Most<br>Frequently Asked Questions</h2>
      </div>
      <div class="faq-list">
        ${FAQ.map(([q, a], i) => `
          <div class="faq-item${i === 1 ? " open" : ""}">
            <button class="faq-q" type="button" aria-expanded="${i === 1}"><span>${q}</span><span class="pm" aria-hidden="true"></span></button>
            <div class="faq-a"><div><p>${a}</p></div></div>
          </div>`).join("")}
        <div class="faq-bubble">${bubble("fb")}</div>
      </div>
    </div>
  </section>`;

  const note = root.querySelector("#ctaNote");
  note.textContent = app.user ? `Signed in as ${app.user.name}` : "You’ll be asked to sign in first.";

  root.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => app.navigate("#/" + b.dataset.go)));
  root.querySelectorAll("[data-scroll-to]").forEach((b) => b.addEventListener("click", () => document.getElementById(b.dataset.scrollTo)?.scrollIntoView({ behavior: "smooth" })));
  $$(".faq-item", root).forEach((item) => {
    item.querySelector(".faq-q").addEventListener("click", () => {
      const open = !item.classList.contains("open");
      item.classList.toggle("open", open);
      item.querySelector(".faq-q").setAttribute("aria-expanded", String(open));
    });
  });
  return () => {};
}
