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
  visible: [],          // those questions that are on now (shows_when), in card order
  visibleFrom: null,    // the questions list `visible` was built from
  qIndex: 0,            // which question screen
  picks: [],            // selected option number, as a string
  texts: [],            // typed answer for a free-text option
  replies: [],          // what the box replays: option number, or the typed text
  agnesRemembered: "unknown",   // session.agnes_remembered — "yes", "no", "unknown"
  agnesProgress: null,          // session.agnes_progress — the Agnes job's record
  locked: false,
  delivery: null,
  deliveryVerdict: null,
};

// ── which screens are on: the `shows_when` the card exports (SPEC B1) ────────
// Every screen the intake_card `studio-json` export carries a `shows_when`
// condition ({"purpose": [1]}, {"agnes_remembered": ["unknown","yes"],
// "length_s_max": 300}); the page evaluates it rather than guessing, so a screen
// a purpose never asks is never rendered. A condition this page does not know
// hides the screen — a question is never shown on a guess.
export function screenIsOn(screen, questions = [], answers = {}, agnesRemembered = "unknown") {
  const rule = screen && screen.shows_when;
  if (!rule || !Object.keys(rule).length) return true;
  const purpose = ((questions || []).find((q) => q.id === "purpose") || {}).options || [];
  for (const [key, allowed] of Object.entries(rule)) {
    const list = Array.isArray(allowed) ? allowed : [allowed];
    if (key === "purpose") {
      // A rule naming every purpose option (the export's `_EVERY_PURPOSE`) is no
      // restriction at all; a narrower one only bites once PURPOSE has an answer,
      // because until then there is no purpose to rule the screen out with.
      if (!purpose.length || list.length >= purpose.length) continue;
      const answer = answers.purpose;
      if (answer == null || answer === "") return false;
      if (!list.some((n) => String(n) === String(answer))) return false;
    } else if (key === "agnes_remembered") {
      if (!list.some((v) => String(v) === String(agnesRemembered || "unknown"))) return false;
    } else if (key === "length_s_max") {
      // 7- and 10-minute episodes are KIE-only, so AGNES is asked only while the
      // chosen length is one Agnes can make (SPEC A15, `length_s_max` 300 s).
      const seconds = chosenLengthSeconds(questions, answers);
      if (seconds == null || seconds > Number(allowed)) return false;
    } else {
      return false;
    }
  }
  return true;
}

// The length the client picked, in seconds, read off the option text the card
// itself offers ("60 seconds", "3 minutes + 60s and 90s clips") — never a second
// length table beside `length_formula`.
function chosenLengthSeconds(questions, answers) {
  for (const id of ["episode_length", "length"]) {
    const answer = answers[id];
    if (answer == null || answer === "") continue;
    const screen = (questions || []).find((q) => q.id === id);
    const option = ((screen && screen.options) || []).find((o) => String(o.n) === String(answer));
    const found = /(\d+)\s*(second|minute)/i.exec(String((option && option.text) || ""));
    return found ? Number(found[1]) * (/minute/i.test(found[2]) ? 60 : 1) : null;
  }
  return null;
}

// The screens that are on, in the card's own order: PURPOSE first, its one
// follow-up right after it, EPISODE LENGTH in LENGTH's own slot, SHAPE right
// after the length screen, AGNES after VIDEO STYLE — the placement of
// `intake_card._shaped` (METHOD-INTEGRATION 3.2), so the replies this page
// saves sit at the positions the bridge replays. The SET of screens comes only
// from `shows_when`; an unplaced screen lands last rather than vanishing.
function shapeScreens(questions, answers, agnesRemembered) {
  const on = (questions || []).filter((q) => screenIsOn(q, questions, answers, agnesRemembered));
  const get = (id) => on.find((q) => q.id === id);
  const out = [];
  const put = (q) => { if (q && !out.includes(q)) out.push(q); };
  put(get("purpose"));
  put(get("permission") || get("where"));
  for (const base of questions || []) {
    if (base.id === "length") {
      // EPISODE LENGTH for a campaign sits in LENGTH's own slot, and SHAPE
      // right behind it — at that position whether LENGTH itself is on or not,
      // because a campaign answers EPISODE LENGTH instead of LENGTH.
      put(get("episode_length") || get("length"));
      put(get("shape"));
      continue;
    }
    if (["purpose", "episode_length", "permission", "where", "shape", "agnes"].includes(base.id)) continue;
    put(get(base.id));
    if (base.id === "look") put(get("agnes"));
  }
  on.forEach(put);
  return out;
}

// The list rebuilt from the answers so far: the same walk `intake_card.
// conversation()` takes, reply by reply, so a saved draft replays identically.
export function visibleScreens(questions, replies = [], agnesRemembered = "unknown") {
  const answers = {};
  let list = shapeScreens(questions, answers, agnesRemembered);
  for (const reply of replies || []) {
    const at = Object.keys(answers).length;
    if (reply == null || reply === "" || at >= list.length) break;
    answers[list[at].id] = reply;
    list = shapeScreens(questions, answers, agnesRemembered);
  }
  return list;
}

// ── the Agnes progress line on the project card (SPEC A11) ───────────────────
// SPEC A11's own two sentences. The only reason the quota ledger writes today
// is the daily reset, so it carries its words here; any other reason is printed
// as it arrives — the page never invents a reason it was not given.
const WAITING_WORDS = { "agnes-quota-next-day": "waiting for tomorrow's Agnes time" };

function clockAt(iso) {
  const at = new Date(String(iso));
  if (Number.isNaN(at.getTime())) return "";
  const h = at.getHours();
  return `${h % 12 || 12}:${String(at.getMinutes()).padStart(2, "0")} ${h < 12 ? "am" : "pm"}`;
}

export function agnesProgressLine(progress) {
  if (!progress || typeof progress !== "object") return "";
  const total = Number(progress.clips_total);
  const done = Number(progress.clips_done);
  if (!Number.isFinite(total) || total <= 0 || !Number.isFinite(done)) return "";
  if (progress.waiting_reason) {
    const why = WAITING_WORDS[String(progress.waiting_reason)] || `waiting (${progress.waiting_reason})`;
    const at = clockAt(progress.next_continue_utc);
    return at ? `${why}, continues at ${at}` : why;
  }
  const low = Number(progress.eta_minutes_low);
  const high = Number(progress.eta_minutes_high);
  const eta = low > 0 ? low : high > 0 ? high : 0;
  if (!eta) return `Making your video clips: ${done} of ${total} done`;
  const h = Math.floor(eta / 60);
  const m = eta % 60;
  const left = h ? (m ? `${h} h ${m} min` : `${h} h`) : `${m} min`;
  return `Making your video clips: ${done} of ${total} done — about ${left} to go`;
}

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
  // The list is rebuilt from these replies (SPEC B1), so every index below is
  // an index into the list on display, never into the whole export.
  const list = visibleScreens(state.questions, replies || [], state.agnesRemembered);
  state.visible = list;
  state.visibleFrom = state.questions;
  state.picks = [];
  state.texts = [];
  (replies || []).forEach((r, i) => {
    const q = list[i];
    if (!q || r == null || r === "") return;
    const pick = q.options.find((o) => String(o.n) === String(r));
    if (pick) { state.picks[i] = String(pick.n); return; }
    const free = q.options.find(isFreeTextOption) || q.options[0];
    if (free) { state.picks[i] = String(free.n); state.texts[i] = String(r); }
  });
}

// The screens that are on right now. The list is rebuilt when the questions
// themselves change (or nothing has been built yet) — an answer changes it
// through `answerChanged`, never through a re-render, so an answer in progress
// is never thrown away by drawing the page again.
function screens() {
  if (state.questions.length && (state.visibleFrom !== state.questions || !state.visible.length)) {
    hydrateReplies(state.replies);
  }
  return state.visible;
}

function replyFor(i) {
  const q = state.visible[i];
  const pick = state.picks[i];
  if (!q || !pick) return "";
  const opt = q.options.find((o) => String(o.n) === String(pick));
  if (opt && isFreeTextOption(opt)) return String(state.texts[i] || "").trim();
  return String(pick);
}

const currentReplies = () => state.visible.map((_, i) => replyFor(i));

function firstUnanswered() {
  for (let i = 0; i < state.visible.length; i++) if (!replyFor(i)) return i;
  return state.visible.length;
}

function ensurePick(i) {
  const q = state.visible[i];
  if (q && !state.picks[i] && q.options.length === 1) state.picks[i] = String(q.options[0].n);
}

// One option was picked on screen `i`. PURPOSE rebuilds the list that follows
// it, so everything after that screen is dropped — the card does the same
// (SPEC B1: "every answer after it has to be given again").
function answerChanged(i, value) {
  state.picks[i] = value;
  if (state.visible[i] && state.visible[i].id === "purpose") {
    state.picks.length = i + 1;
    state.texts.length = i + 1;
  }
  state.replies = currentReplies();
  hydrateReplies(state.replies);
  state.qIndex = Math.min(i, Math.max(0, state.visible.length - 1));
  render();
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
  if (i + 1 >= state.visible.length) { setPage("recap"); return; }
  state.qIndex = i + 1;
  render();
}

async function startOrder() {
  await loadQuestions();
  if (!state.questions.length) { render(); return; }
  hydrateReplies(state.replies);
  state.replies = currentReplies();
  const next = firstUnanswered();
  if (next >= state.visible.length) { setPage("recap"); return; }
  state.qIndex = next;
  setPage("questions");
}

function goAnswer() {
  hydrateReplies(state.replies);
  state.qIndex = Math.min(firstUnanswered(), Math.max(0, state.visible.length - 1));
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

function answerBox(value, onInput, question) {
  const wrap = el("div", {});
  const id = "q-answer";
  // A story-brief answer is a sentence — an audience and an action, a character
  // description, a list of photos — so it gets room to be one. The BUDGET's
  // "a different maximum" is a dollar amount and stays a single line. The
  // question's own `typed` flag decides; the option text is never sniffed.
  const typed = Boolean(question && question.typed);
  wrap.append(el("label", { for: id, text: typed ? "Your answer, in your own words" : "Your answer" }));
  const box = typed
    ? el("textarea", { id, rows: "3", autocomplete: "off" })
    : el("input", { id, type: "text", autocomplete: "off" });
  box.value = value;
  box.addEventListener("input", () => onInput(box.value));
  wrap.append(box);
  return wrap;
}

function pageQuestions() {
  const list = screens();
  if (!list.length) {
    return [
      el("h1", { text: "Tell us about your video" }),
      el("div", { class: "refusal", text: "The questions are not here yet. Nothing you typed has been lost — go home and try again." }),
      el("div", { class: "actions" }, [secondary("Home", () => setPage("start"))]),
    ];
  }

  const i = Math.min(state.qIndex, list.length - 1);
  const q = list[i];
  ensurePick(i);
  const chosen = q.options.find((o) => String(o.n) === String(state.picks[i] || ""));

  const fieldset = el("fieldset", { class: "options" });
  fieldset.append(el("legend", { text: q.question }));
  if (q.example) fieldset.append(el("p", { class: "hint muted", text: `See a great answer: ${q.example}` }));
  for (const o of q.options) {
    const id = `q-${q.id}-${o.n}`;
    const input = el("input", { id, type: "radio", name: `q-${q.id}`, value: String(o.n) });
    if (String(state.picks[i]) === String(o.n)) input.checked = true;
    input.addEventListener("change", () => answerChanged(i, String(o.n)));
    fieldset.append(el("label", { class: "option", for: id }, [
      input,
      el("span", {}, [
        el("span", { class: "label", text: o.text }),
        o.detail ? el("span", { class: "hint", text: ` ${o.detail}` }) : null,
        o.price ? el("span", { class: "hint", text: ` ${o.price}` }) : null,
      ].filter(Boolean)),
    ]));
  }
  for (const text of q.supplementary_explanation || []) {
    fieldset.append(el("p", { class: "hint", text }));
  }
  if (chosen && isFreeTextOption(chosen)) {
    fieldset.append(answerBox(state.texts[i] || "", (v) => { state.texts[i] = v; }, q));
  }

  return [
    el("h1", { text: q.label || "Your question" }),
    el("p", { class: "muted", text: `${i + 1} of ${list.length}. Your answer saves when you tap Next.` }),
    el("div", { class: "card" }, [fieldset]),
    el("div", { class: "actions" }, [
      i > 0
        ? secondary("Back", () => { state.qIndex = i - 1; render(); })
        : secondary("Home", () => setPage("start")),
      primary(i + 1 >= list.length ? "Read the recap" : "Next", () => advance()),
    ]),
  ];
}

function pageRecap() {
  if (state.locked) return pageReceived();
  const list = screens();
  if (!list.length) {
    return [
      el("h1", { text: "Read this back, then lock it in" }),
      el("div", { class: "refusal", text: "There is nothing to recap yet. Start your order from the home screen." }),
      el("div", { class: "actions" }, [secondary("Home", () => setPage("start"))]),
    ];
  }

  const replies = currentReplies();
  const rows = list.map((q, i) => {
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

// The Agnes job's own record for this project (SPEC A11): the service reports
// it per project — keyed by order id, or as the record itself when there is one
// project — and until the service reports it at all, there is no line to show.
function progressFor(order) {
  const all = state.agnesProgress;
  if (!all || typeof all !== "object") return null;
  if (order && order.order_id && all[order.order_id]) return all[order.order_id];
  return Object.prototype.hasOwnProperty.call(all, "clips_total") ? all : null;
}

function progressNodes(order) {
  const line = agnesProgressLine(progressFor(order));
  return line ? [el("p", { text: line })] : [];
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
    ...progressNodes(order),
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
      // The remembered Agnes answer and the Agnes job's progress ride the same
      // session (W2-wiring-U3). Absent until that lands: "unknown" keeps AGNES
      // on the card (its shows_when names "unknown") and no progress line shows.
      state.agnesRemembered = session.agnes_remembered || "unknown";
      state.agnesProgress = session.agnes_progress || null;
    } catch (err) {
      announce(serviceMessage(err));
    }
    if (state.page === "questions" || state.page === "recap") {
      await loadQuestions();
      hydrateReplies(state.replies);
      const next = firstUnanswered();
      if (next >= state.visible.length) state.page = "recap";
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
