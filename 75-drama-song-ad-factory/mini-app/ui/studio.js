// =============================================================================
// Drama Song Ad Factory mini-app — the order flow on the page
// -----------------------------------------------------------------------------
// mini-app/ui/studio.js
//
// HOME -> one question per screen (the draft saves after every answer) ->
// RECAP -> "Lock it in" -> ORDER RECEIVED, then the PROJECT page (status
// timeline, approvals, delivery link) and the premiere.
//
// WHAT THIS FILE DELIBERATELY DOES NOT DO
//   * It asks no question of its own. Every question comes from
//     getQuestions() — the intake_card.py `studio-json` export served as
//     /questions.json, the only place questions are defined (SPEC §5).
//   * It keeps no store of its own beyond the screen on display. Drafts,
//     orders and approvals live in the service; this page reads and writes
//     them through globalThis.studioService (service-client.js).
//   * It carries no client id of its own — the id is whatever the service
//     reports in `session.client_id`.
//
// HASH ROUTING KEEPS THE KEY. The URL is `#k=<key>&p=<page>`; navigation
// rewrites `p` and preserves `k` (SPEC §3 — the personal key lives in the
// fragment and must never be dropped by routing).
//
// Accessibility contract (asserted by checks/a11y-check.mjs):
//   * every control is a native <button>, <input type="radio"> or <a>;
//   * every input has a real <label>; every icon-only region has a name;
//   * focus order is source order (no positive tabindex anywhere);
//   * changing page MOVES FOCUS to the new page heading;
//   * every state change is announced in the polite live region;
//   * no state is carried by motion or colour alone — each has words too.
// =============================================================================
import { studio, serviceConnected, ServiceUnavailableError } from "./api-client.js";
import { encode, toElement } from "./qr.js";
import { verifyDownload, triggerSave } from "./download.js";

// ── sibling modules, each owned by another unit ──────────────────────────────
// service-client.js (W1-studio-page-U1) installs globalThis.studioService;
// approvals-view.js (W1-studio-page-U3) exports renderApprovalsFor(order, root).
// Each import is guarded so the page and its checks still run on a branch where
// that file has not landed yet: without the service the page says "not
// connected" in words, without the view the project page says approvals are not
// here yet. The moment the file exists, the import succeeds and the feature is
// on — nothing is skipped silently after that.
let renderApprovalsFor = null;

async function loadSiblingModules() {
  try { await import("./service-client.js"); } catch { /* not on this branch yet */ }
  try { ({ renderApprovalsFor } = await import("./approvals-view.js")); } catch { /* same */ }
}

// ── the version-0 option surface ─────────────────────────────────────────────
// NOT USED BY ANY SCREEN ANYMORE: the page asks getQuestions() instead (see the
// header). It stays exported only because checks/ui-contract.mjs imports it and
// asserts on it, and that file is not this unit's to edit — deleting it means
// updating ui-contract.mjs first (named in the PR body for the conductor).
export const DEFAULT_OPTIONS = {
  questions: [
    { id: "offer", label: "What are we promoting?", hint: "Your offer and its link.",
      choices: [] },
    { id: "audience", label: "Who is it for, and what should they do?", hint: "One sentence.",
      choices: [] },
    { id: "character", label: "Who stars in your video?", hint: "Describe them, or bring back a saved one.",
      choices: [{ id: "new", label: "Create a new character" }, { id: "saved", label: "Use one I saved before" }] },
    { id: "length", label: "How long should it run?", hint: "Longer runs also come with 60- and 90-second clips.",
      choices: [
        { id: "60", label: "60 seconds" }, { id: "180", label: "3 minutes" },
        { id: "300", label: "5 minutes" }, { id: "600", label: "10 minutes" }] },
    { id: "music", label: "What does your song feel like?", hint: "The style the composer writes in.",
      choices: [
        { id: "soul-rise", label: "Soul Rise", hint: "Warm and uplifting" },
        { id: "quiet-drive", label: "Quiet Drive", hint: "Steady and confident" },
        { id: "bright-clap", label: "Bright Clap", hint: "Upbeat, clap-along" }] },
    { id: "look", label: "How should every shot look?", hint: "Pick the style you want to see.",
      choices: [
        { id: "lifelike-3d", label: "Lifelike 3D", hint: "Real and cinematic" },
        { id: "2d-painted", label: "2D Hand-Painted", hint: "Warm storybook" },
        { id: "sketch-to-life", label: "Sketch to Life", hint: "A sketch comes alive" },
        { id: "canvas-to-life", label: "Canvas to Life", hint: "A painted canvas comes alive" },
        { id: "canvas-to-3d", label: "Canvas to 3D", hint: "A canvas turns 3D" }] },
    { id: "model", label: "Pick the quality level", hint: "The video model that films it.",
      choices: [
        { id: "standard", label: "Standard", hint: "Fastest, lowest cost" },
        { id: "high", label: "High", hint: "Recommended balance" },
        { id: "premium", label: "Premium", hint: "Best picture, highest cost" }] },
    { id: "budget", label: "Set your ceiling", hint: "The most this run may spend, with a redo allowance.",
      choices: [{ id: "recommended", label: "The recommended budget" },
        { id: "custom", label: "A number I will give you" }] },
  ],
  looks: [
    { id: "lifelike-3d", label: "Lifelike 3D", sampleUrl: "https://studio.example.com/samples/lifelike-3d" },
    { id: "2d-painted", label: "2D Hand-Painted", sampleUrl: "https://studio.example.com/samples/2d-painted" },
    { id: "sketch-to-life", label: "Sketch to Life", sampleUrl: "https://studio.example.com/samples/sketch-to-life" },
    { id: "canvas-to-life", label: "Canvas to Life", sampleUrl: "https://studio.example.com/samples/canvas-to-life" },
    { id: "canvas-to-3d", label: "Canvas to 3D", sampleUrl: "https://studio.example.com/samples/canvas-to-3d" },
  ],
  songs: [
    { id: "a", label: "Version A", hint: "Slower, piano-led, with a gentle build", audioUrl: "https://studio.example.com/songs/a" },
    { id: "b", label: "Version B", hint: "Warm start that lifts into a bright chorus", audioUrl: "https://studio.example.com/songs/b" },
    { id: "c", label: "Version C", hint: "Upbeat from the first note, bouncy rhythm", audioUrl: "https://studio.example.com/songs/c" },
  ],
};

// The five pages. The ids are the contract checks/ui-contract.mjs asserts on:
// `start` is the home screen, `approvals` is the project screen (status,
// approvals and delivery live together there), `delivery` is the premiere.
const PAGES = [
  { id: "start", label: "Home", title: "Welcome to your studio" },
  { id: "questions", label: "Questions", title: "Tell us about your video" },
  { id: "recap", label: "Recap", title: "Read this back, then lock it in" },
  { id: "approvals", label: "Project", title: "Your project and approvals" },
  { id: "delivery", label: "Premiere", title: "Your finished video" },
];

// Plain words for every order state the service can report (lifecycle.js).
const STATUS_WORDS = {
  waiting: "Waiting for the studio to start",
  in_production: "In production",
  needs_you: "Needs you",
  ready: "Ready for you",
  delivered: "Delivered",
  done: "Finished",
  cancelled: "Cancelled",
  expired: "Expired",
};
const TIMELINE = ["waiting", "in_production", "needs_you", "ready", "delivered", "done"];

const state = {
  page: "start",
  clientId: null,       // session.client_id — the service's id, never a hard-coded one
  optionLine: "",
  orders: [],
  order: null,          // the project on screen
  questions: [],        // from getQuestions()
  qIndex: 0,            // which question screen
  picks: [],            // selected option number, as a string
  texts: [],            // typed answer for a free-text option
  replies: [],          // what the box replays: option number, or the typed text
  locked: false,
  delivery: null,
  deliveryVerdict: null,
};

const el = (tag, attrs = {}, children = []) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "text") node.textContent = v;
    else node.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of [].concat(children)) node.append(c);
  return node;
};

const main = () => document.getElementById("main");

function announce(text) {
  const status = document.getElementById("status");
  if (status) status.textContent = text;
}

// Move focus to the freshly rendered page heading — the screen-reader cue that
// the page changed. The heading is a real <h1> made focusable for exactly this.
function focusHeading() {
  const h = main().querySelector("h1");
  if (h) { h.setAttribute("tabindex", "-1"); h.focus(); }
}

// ── hash routing: `#k=<key>&p=<page>`, and `k` is never dropped ──────────────
function readHash() {
  const raw = location.hash.replace(/^#/, "");
  const params = new URLSearchParams(raw);
  const page = params.get("p") || (PAGES.some((p) => p.id === raw) ? raw : "");
  return { key: params.get("k") || "", page };
}

function personalLink() {
  const { key } = readHash();
  return key ? `${location.origin}/#k=${key}` : "";
}

function setPage(id) {
  state.page = id;
  render();
  const { key } = readHash();
  const params = new URLSearchParams();
  if (key) params.set("k", key);
  params.set("p", id);
  const next = `#${params.toString()}`;
  if (location.hash !== next) history.replaceState(null, "", next);
}

// ── chrome ───────────────────────────────────────────────────────────────────
function renderNav() {
  const nav = document.getElementById("steps-nav");
  nav.replaceChildren(...PAGES.map((p) => {
    const b = el("button", { type: "button", text: p.label });
    if (p.id === state.page) b.setAttribute("aria-current", "page");
    b.addEventListener("click", () => setPage(p.id));
    return b;
  }));
}

function renderProgress() {
  const idx = PAGES.findIndex((p) => p.id === state.page);
  const pct = Math.round((idx / (PAGES.length - 1)) * 100);
  const rail = document.getElementById("rail");
  rail.setAttribute("aria-valuenow", String(pct));
  document.getElementById("rail-fill").style.width = `${pct}%`;
  document.getElementById("step-label").textContent = `Step ${idx + 1} of ${PAGES.length}: ${PAGES[idx].label}`;
}

// ── the service, in the words this page shows when it is not there ───────────
function svc() {
  const s = globalThis.studioService;
  if (!s) throw new ServiceUnavailableError();
  return s;
}

async function loadQuestions() {
  if (state.questions.length) return;
  try {
    const out = await svc().getQuestions();
    const list = out && Array.isArray(out.questions) ? out.questions : [];
    state.questions = list;
    if (!list.length) announce("The questions are not available right now. Nothing was lost — try again.");
  } catch (err) {
    announce(serviceMessage(err));
  }
}

// A reply is the option number as a string, or — for an option the card reads
// as typed text ("Reply with …") — exactly what the client typed (SPEC §5).
const isFreeTextOption = (o) => /^reply with/i.test(String(o.detail || "").trim());

function hydrateReplies(replies) {
  state.picks = [];
  state.texts = [];
  replies.forEach((r, i) => {
    const q = state.questions[i];
    if (!q || r == null || r === "") return;
    const pick = q.options.find((o) => String(o.n) === String(r));
    if (pick) { state.picks[i] = String(pick.n); return; }
    const free = q.options.find(isFreeTextOption) || q.options[0];
    if (free) { state.picks[i] = String(free.n); state.texts[i] = String(r); }
  });
}

function replyFor(i) {
  const q = state.questions[i];
  const pick = state.picks[i];
  if (!q || !pick) return "";
  const opt = q.options.find((o) => String(o.n) === String(pick));
  if (opt && isFreeTextOption(opt)) return String(state.texts[i] || "").trim();
  return String(pick);
}

const currentReplies = () => state.questions.map((_, i) => replyFor(i));

function firstUnanswered() {
  for (let i = 0; i < state.questions.length; i++) if (!replyFor(i)) return i;
  return state.questions.length;
}

function ensurePick(i) {
  const q = state.questions[i];
  if (q && !state.picks[i] && q.options.length === 1) state.picks[i] = String(q.options[0].n);
}

async function saveDraft() {
  try {
    await svc().saveDraft({ replies: state.replies });
    announce("Saved. Your answers are safe.");
  } catch (err) {
    announce(serviceMessage(err));
  }
}

async function advance() {
  const i = state.qIndex;
  const value = replyFor(i);
  if (!value) {
    announce(state.picks[i] ? "Type your answer first." : "Pick one of the options first.");
    return;
  }
  state.replies = currentReplies();
  await saveDraft();
  if (i + 1 >= state.questions.length) { setPage("recap"); return; }
  state.qIndex = i + 1;
  render();
}

async function startOrder() {
  await loadQuestions();
  if (!state.questions.length) { render(); return; }
  hydrateReplies(state.replies);
  state.replies = currentReplies();
  const next = firstUnanswered();
  if (next >= state.questions.length) { setPage("recap"); return; }
  state.qIndex = next;
  setPage("questions");
}

function goAnswer() {
  hydrateReplies(state.replies);
  state.qIndex = Math.min(firstUnanswered(), state.questions.length - 1);
  setPage("questions");
}

const statusWords = (order) => STATUS_WORDS[order && order.state] || "In progress";

function openProject(order) {
  state.order = order;
  setPage("approvals");
}

// ── pages ────────────────────────────────────────────────────────────────────
function pageHome() {
  const link = personalLink();
  const nodes = [el("h1", { text: "Welcome to your studio" })];

  if (!serviceConnected()) {
    nodes.push(el("div", { class: "refusal", text: new ServiceUnavailableError().message }));
  }

  nodes.push(el("div", { class: "card" }, [
    el("h2", { text: "Start a drama video" }),
    el("p", { text: "Answer the studio's questions one screen at a time. Your answers save as you go, so you can close this page and come back." }),
    el("div", { class: "actions" }, [primary("Order a new video", () => startOrder())]),
  ]));

  if (state.optionLine) {
    nodes.push(el("div", { class: "panel" }, [el("p", { text: state.optionLine })]));
  }

  nodes.push(el("div", { class: "card" }, [el("h2", { text: "Your projects" }), ...projectList()]));

  if (link) {
    nodes.push(el("div", { class: "card" }, [
      el("h2", { text: "Your studio link" }),
      qrSurface(link, "your studio link"),
    ]));
  } else if (serviceConnected()) {
    nodes.push(el("p", { class: "muted", text: "Open this page from your personal link and your studio QR code appears here." }));
  }

  return nodes;
}

function projectList() {
  if (!state.orders.length) {
    return [el("p", { class: "muted", text: "Nothing here yet. Your first project appears the moment you lock in an order." })];
  }
  return [el("ul", {}, state.orders.map((o) => {
    const li = el("li", {});
    const b = el("button", {
      type: "button", class: "btn secondary",
      text: `${o.title || "Your video"} — ${statusWords(o)}`,
    });
    b.addEventListener("click", () => openProject(o));
    li.append(b);
    return li;
  }))];
}

function answerBox(value, onInput) {
  const wrap = el("div", {});
  const id = "q-answer";
  wrap.append(el("label", { for: id, text: "Your answer" }));
  const input = el("input", { id, type: "text", autocomplete: "off" });
  input.value = value;
  input.addEventListener("input", () => onInput(input.value));
  wrap.append(input);
  return wrap;
}

function pageQuestions() {
  if (!state.questions.length) {
    return [
      el("h1", { text: "Tell us about your video" }),
      el("div", { class: "refusal", text: "The questions are not here yet. Nothing you typed has been lost — go home and try again." }),
      el("div", { class: "actions" }, [secondary("Home", () => setPage("start"))]),
    ];
  }

  const i = state.qIndex;
  const q = state.questions[i];
  ensurePick(i);
  const chosen = q.options.find((o) => String(o.n) === String(state.picks[i] || ""));

  const fieldset = el("fieldset", { class: "options" });
  fieldset.append(el("legend", { text: q.question }));
  if (q.example) fieldset.append(el("p", { class: "hint muted", text: `See a great answer: ${q.example}` }));
  for (const o of q.options) {
    const id = `q-${q.id}-${o.n}`;
    const input = el("input", { id, type: "radio", name: `q-${q.id}`, value: String(o.n) });
    if (String(state.picks[i]) === String(o.n)) input.checked = true;
    input.addEventListener("change", () => { state.picks[i] = String(o.n); render(); });
    fieldset.append(el("label", { class: "option", for: id }, [
      input,
      el("span", {}, [
        el("span", { class: "label", text: o.text }),
        o.detail ? el("span", { class: "hint", text: ` ${o.detail}` }) : null,
        o.price ? el("span", { class: "hint", text: ` ${o.price}` }) : null,
      ].filter(Boolean)),
    ]));
  }
  if (chosen && isFreeTextOption(chosen)) {
    fieldset.append(answerBox(state.texts[i] || "", (v) => { state.texts[i] = v; }));
  }

  return [
    el("h1", { text: q.label || "Your question" }),
    el("p", { class: "muted", text: `${i + 1} of ${state.questions.length}. Your answer saves when you tap Next.` }),
    el("div", { class: "card" }, [fieldset]),
    el("div", { class: "actions" }, [
      i > 0
        ? secondary("Back", () => { state.qIndex = i - 1; render(); })
        : secondary("Home", () => setPage("start")),
      primary(i + 1 >= state.questions.length ? "Read the recap" : "Next", () => advance()),
    ]),
  ];
}

function pageRecap() {
  if (state.locked) return pageReceived();
  if (!state.questions.length) {
    return [
      el("h1", { text: "Read this back, then lock it in" }),
      el("div", { class: "refusal", text: "There is nothing to recap yet. Start your order from the home screen." }),
      el("div", { class: "actions" }, [secondary("Home", () => setPage("start"))]),
    ];
  }

  const replies = currentReplies();
  const rows = state.questions.map((q, i) => {
    const li = el("li", {});
    const b = el("button", {
      type: "button", class: "btn secondary",
      text: `${i + 1}. ${q.label}: ${replies[i] || "not answered yet"}`,
    });
    b.addEventListener("click", () => { state.qIndex = i; setPage("questions"); });
    li.append(b);
    return li;
  });
  const missing = replies.some((r) => !r);

  return [
    el("h1", { text: "Read this back, then lock it in" }),
    missing ? el("div", { class: "refusal", text: "One line is still empty. Tap it to answer before locking in." }) : null,
    el("div", { class: "card" }, [el("h2", { text: "Your recap" }), el("ol", {}, rows)]),
    el("p", { class: "muted", text: "Tap any line to change it. Locking it in sends your answers to the studio — nothing starts before that." }),
    el("div", { class: "actions" }, [
      missing ? null : primary("Lock it in", () => lockIn()),
      secondary("Change an answer", () => goAnswer()),
    ].filter(Boolean)),
  ].filter(Boolean);
}

async function lockIn() {
  try {
    const out = await svc().lockIn({
      title: `Drama video ${new Date().toISOString().slice(0, 10)}`,
      replies: [...currentReplies(), "yes"],
      upload_ids: [],
    });
    state.locked = true;
    if (out && out.order) {
      state.order = out.order;
      state.orders = [out.order, ...state.orders.filter((o) => o.order_id !== out.order.order_id)];
      if (out.option_line) state.optionLine = out.option_line;
    }
    announce("Order received. Your answers are with the studio.");
  } catch (err) {
    announce(serviceMessage(err));
    return;
  }
  render();
}

function pageReceived() {
  return [
    el("h1", { text: "Order received" }),
    el("div", { class: "complete", text: "Your order is in. The studio picks it up within about two minutes and plays your answers back exactly as you gave them." }),
    el("div", { class: "actions" }, [
      primary("See my project", () => setPage("approvals")),
      secondary("Back to home", () => setPage("start")),
    ]),
  ];
}

function timelineFor(order) {
  const at = TIMELINE.indexOf(order.state);
  if (at < 0) return [el("p", { class: "muted", text: `Status: ${statusWords(order)}` })];
  return [el("ol", {}, TIMELINE.map((s, i) => el("li", {
    text: `${STATUS_WORDS[s]}${i < at ? " — finished" : i === at ? " — now" : " — not yet"}`,
  })))];
}

function pageProject() {
  const order = state.order || state.orders[0];
  const nodes = [el("h1", { text: "Your project" })];

  if (!order) {
    nodes.push(el("p", { class: "muted", text: "No project yet. Lock in an order and it shows up here with its status." }));
    nodes.push(el("div", { class: "actions" }, [secondary("Back to home", () => setPage("start"))]));
    return nodes;
  }

  nodes.push(el("div", { class: "card" }, [
    el("h2", { text: order.title || "Your video" }),
    el("p", { text: `Status: ${statusWords(order)}` }),
    ...timelineFor(order),
  ]));

  const approvalsCard = el("div", { class: "card" }, [el("h2", { text: "Your approvals" })]);
  const slot = el("div", {});
  approvalsCard.append(slot);
  if (renderApprovalsFor) {
    Promise.resolve(renderApprovalsFor(order, slot))
      .then((ret) => {
        if (ret && !slot.childNodes.length) {
          if (Array.isArray(ret)) slot.append(...ret); else slot.append(ret);
        }
      })
      .catch((err) => {
        slot.replaceChildren(el("p", { class: "refusal", text: `The approvals could not be loaded (${err.message}). Try again.` }));
      });
  } else {
    slot.append(el("p", { class: "muted", text: "Approvals appear here as soon as the studio sends them. Nothing waits on this page — you will get a message too." }));
  }
  nodes.push(approvalsCard);

  const url = order.delivery && order.delivery.url;
  if (url) {
    nodes.push(el("div", { class: "card" }, [
      el("h2", { text: "Your finished video" }),
      el("p", {}, [el("a", { href: url, rel: "noopener", text: url })]),
      el("div", { class: "actions" }, [primary("Watch it now", () => {
        state.delivery = { masterUrl: url, clips: [], qrPayload: url };
        state.deliveryVerdict = null;
        setPage("delivery");
      })]),
    ]));
  }

  nodes.push(el("div", { class: "actions" }, [secondary("Back to home", () => setPage("start"))]));
  return nodes;
}

function qrSurface(url, what) {
  const wrap = el("div", { class: "qr-surface" });
  try {
    const matrix = encode(url);
    const svg = toElement(matrix, { scale: 6 });
    svg.setAttribute("aria-label", `QR code for ${what}. The same link is written out below.`);
    wrap.append(svg);
  } catch (err) {
    wrap.append(el("p", { class: "refusal", text: `The code could not be drawn (${err.message}). Use the link below.` }));
  }
  wrap.append(el("p", { class: "qr-link" }, [
    el("span", { class: "muted", text: "Or open it directly: " }),
    el("a", { href: url, rel: "noopener", text: url }),
  ]));
  wrap.append(el("ol", { class: "qr-steps" }, [
    el("li", { text: "Open your phone's camera." }),
    el("li", { text: "Point it at the code above." }),
    el("li", { text: "Tap the link that appears." }),
  ]));
  return wrap;
}

function pageDelivery() {
  const d = state.delivery;
  if (!d) {
    return [
      el("h1", { text: "Your finished video" }),
      el("p", { class: "muted", text: "Nothing is ready to watch yet. Your premiere lands here the moment the studio finishes." }),
      el("div", { class: "card" }, [
        el("h2", { text: "Where it will be" }),
        el("p", { text: "The finished video, the 60- and 90-second clips, a ready-to-post kit and a code you can scan to watch on your phone." }),
      ]),
    ];
  }

  const verdict = state.deliveryVerdict;
  const checkBtn = secondary("Check the download before saving", async () => {
    announce("Checking the download…");
    state.deliveryVerdict = await verifyDownload(d.masterUrl, {
      fetchImpl: (...args) => (
        serviceConnected() && globalThis.studioService.fetchDelivery
          ? globalThis.studioService.fetchDelivery(...args)
          : fetch(...args)
      ),
      expectedBytes: d.masterBytes ?? null,
    });
    announce(state.deliveryVerdict.ok
      ? "That link gives a real file. You can save it."
      : "That link is not a real download. See the note above the button.");
    render();
  });

  const saveBtn = primary("Download my video", () => {
    triggerSave(d.masterUrl, "05 - Video Captioned.mp4");
    announce("Saving your video.");
  });
  if (!verdict?.ok) {
    saveBtn.disabled = true;
    saveBtn.setAttribute("aria-disabled", "true");
    saveBtn.title = "Check the link first — a redirect is not a download";
  }

  return [
    el("h1", { text: "Your finished video" }),
    verdict && !verdict.ok ? el("p", { class: "refusal", text: `This link is not an actual download: ${verdict.reasons.join("; ")}.` }) : null,
    verdict?.ok ? el("p", { class: "complete", text: `Real file: ${verdict.receivedBytes} bytes, ${verdict.contentType}.` }) : null,
    el("div", { class: "card" }, [
      el("h2", { text: "Watch and save" }),
      el("p", { text: "Check the link first. A link that only redirects is not a download — you would get a page instead of your video." }),
      el("div", { class: "actions" }, [checkBtn, saveBtn]),
    ]),
    d.clips?.length ? el("div", { class: "card" }, [
      el("h2", { text: "Clips for social media" }),
      el("ul", {}, d.clips.map((c) => el("li", { text: `${c.label} — ${c.url}` }))),
    ]) : null,
    d.qrPayload ? el("div", { class: "card" }, [
      el("h2", { text: "Watch it on your phone" }),
      qrSurface(d.qrPayload, "your finished video"),
    ]) : null,
  ].filter(Boolean);
}

function primary(label, onClick) {
  const b = el("button", { class: "btn", type: "button", text: label });
  b.addEventListener("click", onClick);
  return b;
}
function secondary(label, onClick) {
  const b = el("button", { class: "btn secondary", type: "button", text: label });
  b.addEventListener("click", onClick);
  return b;
}
function serviceMessage(err) {
  if (err instanceof ServiceUnavailableError) return err.message;
  return `Something went wrong saving that (${err.message}). Nothing was lost — try again.`;
}

// ── render ───────────────────────────────────────────────────────────────────
const RENDERERS = {
  start: pageHome, questions: pageQuestions, recap: pageRecap,
  approvals: pageProject, delivery: pageDelivery,
};

export function render() {
  renderNav();
  renderProgress();
  main().replaceChildren(...RENDERERS[state.page]());
  focusHeading();
}

async function boot() {
  await loadSiblingModules();

  const fromHash = readHash();
  state.page = PAGES.some((p) => p.id === fromHash.page) ? fromHash.page : "start";

  if (serviceConnected()) {
    try {
      const session = await studio.getSession({ clientId: state.clientId });
      state.clientId = session.client_id || state.clientId;
      state.optionLine = session.option_line || "";
      state.orders = Array.isArray(session.orders) ? session.orders : [];
      state.replies = Array.isArray(session.draft && session.draft.replies)
        ? [...session.draft.replies] : [];
    } catch (err) {
      announce(serviceMessage(err));
    }
    if (state.page === "questions" || state.page === "recap") {
      await loadQuestions();
      hydrateReplies(state.replies);
      const next = firstUnanswered();
      if (next >= state.questions.length) state.page = "recap";
      else if (state.page === "questions") state.qIndex = next;
    }
  } else {
    announce(new ServiceUnavailableError().message);
  }

  render();
  window.addEventListener("hashchange", () => {
    const { page } = readHash();
    if (PAGES.some((p) => p.id === page) && page !== state.page) { state.page = page; render(); }
  });
}

if (typeof document !== "undefined") boot();

export { state, PAGES };
