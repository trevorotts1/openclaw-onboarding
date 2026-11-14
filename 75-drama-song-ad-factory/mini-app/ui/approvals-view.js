// =============================================================================
// approvals-view.js — the three approval cards on the phone (W1-studio-page-U3)
// -----------------------------------------------------------------------------
// mini-app/ui/approvals-view.js
//
// `renderApprovalsFor(order, root)` asks the page's service client
// (globalThis.studioService, installed by service-client.js) for the order's
// approvals and draws one card per item into `root`. It resolves with the items
// it rendered.
//
// `mini-app/approvals/ui.mjs` holds an older card model but that folder is NOT
// served to the phone, so nothing is imported from it: the headings are this
// page's own plain words (a second revision is named), and the same rules are
// kept here — a plain `el()` builder, `textContent` only (never `innerHTML`),
// and every state carried in words.
//
// Buttons and the exact value each one sends (SPEC §4):
//   script      Looks great        -> "approve"
//               Change something   -> the typed text
//   song        Pick this one      -> "1" .. "3" (which of the players)
//   storyboard  Approve all        -> "GO"
//               Change this shot   -> "shot N: <text>"
//
// ST5 — MEDIA IS FETCHED, NOT HOT-LINKED.
// Every file URL the service hands back sits behind the same `x-ds-key`
// authentication as every other route, so an <audio src> or <img src> pointed
// straight at it is answered 401. This module reads each file through the
// client's `fetchApprovalMedia` (same-origin fetch with the page's link key
// when that method is absent), turns it into a local `blob:` URL, and only
// then attaches it. The served digest (X-DS-SHA256) and byte count must match
// the listing's files[] entry before an answer unlocks; a mismatch says so in
// words and keeps the controls disabled. A 400 APPROVAL_REVISION_REQUIRED
// means the address is stale, so the listing is re-read and the cards repaint
// instead of calling it a media outage. An answer button stays disabled until
// the browser has actually decoded the picture or reached a playable audio
// state; a file that fails says so in words and keeps the controls disabled.
// A media error after readiness disables them again. Blob URLs are reused
// across repaints and revoked when the cards are replaced, removed from the
// page, or the page is left. Only the exact five-segment approval-file route
// is fetched: an item can never point the page at another origin.
//
// The first answer wins: a second answer comes back as HTTP 409
// APPROVAL_ANSWER_TAKEN and the card says it was already answered elsewhere.
//
// Checked by checks/approvals-view-check.mjs (fake service + DOM shim).
// =============================================================================

// The page's link key parser — T07 owns service-client.js (32 or 64 hex).
import { linkKey } from "./service-client.js";

// The page's own heading words. A card past its first version says so, so the
// client can tell a first look from a second one.
const STAGE_WORDS = Object.freeze({
  script: "Your script",
  song: "Your song — pick 1 of 3",
  storyboard: "Your storyboard",
});

function headingFor(item) {
  const base = STAGE_WORDS[item.stage] || `Your ${item.stage}`;
  const version = Number(item.version);
  return version > 1 ? `${base} (revision ${version})` : base;
}

// The order the three cards are shown in (same as ui.mjs APPROVAL_ITEMS).
const STAGE_ORDER = Object.freeze(["script", "song", "storyboard"]);

const WAITING = "Waiting for your answer. Nothing is made until you say it looks good.";

// The service's exact approval-file route (approvals-api.js: fileRouteUrl):
// stage, positive integer version, 64-hex presentation digest, file name.
// Anything else — another origin, another path, a revisionless address — is
// refused before fetching.
const MEDIA_ROUTE = /^\/api\/studio\/orders\/[^/]+\/approvals\/[^/]+\/[1-9][0-9]*\/[0-9a-f]{64}\/file\/[A-Za-z0-9._-]{1,80}$/;

const el = (tag, attrs = {}, children = []) => {
  const node = globalThis.document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "text") node.textContent = v;
    else node.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of [].concat(children)) if (c) node.append(c);
  return node;
};

const cardKey = (item) => `${item.stage}:${item.version}`;

const errText = (err) => (err && (err.message || err.code)) || "an unknown error";

// HTTP 409 / APPROVAL_ANSWER_TAKEN — someone (page, Telegram or terminal) already answered.
const isTaken = (err) => !!err && (
  err.code === "APPROVAL_ANSWER_TAKEN"
  || Number(err.status) === 409
  || Number(err.statusCode) === 409
  || /APPROVAL_ANSWER_TAKEN/.test(String(err.message || ""))
);

function announce(text) {
  const doc = globalThis.document;
  const status = doc && doc.getElementById ? doc.getElementById("status") : null;
  if (status) status.textContent = text;
}

function actionBtn(text, fn, disabled = false) {
  const b = el("button", { class: "btn", type: "button", text });
  if (disabled) b.setAttribute("disabled", "disabled");
  b.addEventListener("click", fn);
  return b;
}

function enable(node) {
  if (!node) return;
  if (typeof node.removeAttribute === "function") node.removeAttribute("disabled");
  else if (node.attrs) delete node.attrs.disabled;
  else node.disabled = false;
}

function disable(node) {
  if (!node) return;
  if (typeof node.setAttribute === "function") node.setAttribute("disabled", "disabled");
  else if (node.attrs) node.attrs.disabled = "disabled";
  else node.disabled = true;
}

// What the card says once an answer is recorded. The recorded value is the
// service's own ("approve", "GO", a song number, or the typed sentence), so the
// sentence is chosen from it and never from a guess about the answerer.
function answerWords(item) {
  const value = item.answer && item.answer.value != null ? String(item.answer.value) : "";
  if (item.stage === "song" && /^[1-9][0-9]*$/.test(value)) {
    return `You picked version ${value}.`;
  }
  if (value === "approve" || value === "GO") {
    return "Approved. We are moving to the next step.";
  }
  return "Your changes were sent. A new version will appear here.";
}

function messageCard(heading, text) {
  return el("div", { class: "card approval-card" }, [
    el("h2", { text: heading }),
    el("p", { class: "muted", text }),
  ]);
}

// ── authenticated media ──────────────────────────────────────────────────────
function named(message, code) {
  const err = new Error(message);
  err.code = code || "APPROVAL_MEDIA_UNAVAILABLE";
  return err;
}

/** One authenticated same-origin read of one approval file; resolves with a blob. */
async function fetchMedia(file) {
  const entry = file || {};
  const wantSha = typeof entry.sha256 === "string" && /^[0-9a-fA-F]{64}$/.test(entry.sha256)
    ? entry.sha256.toLowerCase()
    : null;
  const wantBytes = Number.isFinite(Number(entry.bytes)) && Number(entry.bytes) >= 0
    ? Number(entry.bytes)
    : null;
  const checkBody = (blob, servedSha) => {
    if (wantSha) {
      const gotSha = typeof servedSha === "string" ? servedSha.toLowerCase() : null;
      if (!gotSha) {
        throw named("The studio did not sign that file, so it stays locked.", "APPROVAL_MEDIA_DIGEST");
      }
      if (gotSha !== wantSha) {
        throw named("That file did not match the studio's record, so it stays locked.", "APPROVAL_MEDIA_DIGEST");
      }
    }
    if (wantBytes != null && blob && Number.isFinite(Number(blob.size)) && Number(blob.size) !== wantBytes) {
      throw named("That file arrived incomplete, so it stays locked.", "APPROVAL_MEDIA_BYTES");
    }
    return blob;
  };
  const svc = globalThis.studioService;
  if (svc && typeof svc.fetchApprovalMedia === "function") {
    const got = await svc.fetchApprovalMedia(entry.url);
    if (!got || !got.blob) throw named("That file came back empty.", "APPROVAL_MEDIA_EMPTY");
    return checkBody(got.blob, got.sha256);
  }
  const key = linkKey();
  if (!key) throw named("The studio link is not on this page any more.", "APPROVAL_NO_KEY");
  if (typeof entry.url !== "string" || !MEDIA_ROUTE.test(entry.url)) {
    throw named("That media address is not this studio's approval route.", "APPROVAL_MEDIA_REFUSED");
  }
  const res = await fetch(entry.url, { headers: { "x-ds-key": key }, cache: "no-store" });
  if (!res.ok) {
    if (Number(res.status) === 400) {
      const data = await res.json().catch(() => null);
      if (data && data.code === "APPROVAL_REVISION_REQUIRED") {
        const err = new Error(data.message || "That approval changed.");
        err.code = "APPROVAL_REVISION_REQUIRED";
        err.status = 400;
        throw err;
      }
    }
    throw named(`The studio answered ${res.status} for that file.`, "APPROVAL_MEDIA_HTTP");
  }
  const blob = await res.blob();
  const servedSha = res.headers && typeof res.headers.get === "function"
    ? res.headers.get("x-ds-sha256")
    : null;
  return checkBody(blob, servedSha);
}

// A stale address (HTTP 400 APPROVAL_REVISION_REQUIRED) is a listing problem,
// not a media outage: the listing is re-read and the cards repaint.
const isRevisionRequired = (err) => !!err && (
  err.code === "APPROVAL_REVISION_REQUIRED"
  || /APPROVAL_REVISION_REQUIRED/.test(String(err.message || ""))
);

// Metadata says only that the browser read the header; HAVE_FUTURE_DATA (3) is
// the first state that says it can actually start playing.
const PLAYABLE_READY_STATE = 3;

function imageReady(img) {
  if (typeof img.decode === "function") return img.decode();
  if (img.complete && Number(img.naturalWidth) > 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const off = () => {
      if (typeof img.removeEventListener !== "function") return;
      img.removeEventListener("load", ok);
      img.removeEventListener("error", bad);
    };
    const ok = () => { off(); resolve(); };
    const bad = () => {
      off();
      reject(named("The browser could not decode that picture.", "APPROVAL_MEDIA_DECODE"));
    };
    if (typeof img.addEventListener !== "function") { resolve(); return; }
    img.addEventListener("load", ok);
    img.addEventListener("error", bad);
  });
}

function audioReady(player) {
  if (player && player.error) {
    return Promise.reject(named("The browser could not play that file.", "APPROVAL_MEDIA_DECODE"));
  }
  if (typeof player.readyState === "number" && player.readyState >= PLAYABLE_READY_STATE) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const off = () => {
      if (typeof player.removeEventListener !== "function") return;
      for (const e of ["canplay", "canplaythrough"]) player.removeEventListener(e, ok);
      for (const e of ["error", "abort"]) player.removeEventListener(e, bad);
    };
    const ok = () => { off(); resolve(); };
    const bad = () => {
      off();
      reject(named("The browser could not play that file.", "APPROVAL_MEDIA_DECODE"));
    };
    if (typeof player.addEventListener !== "function") { resolve(); return; }
    for (const e of ["canplay", "canplaythrough"]) player.addEventListener(e, ok);
    for (const e of ["error", "abort"]) player.addEventListener(e, bad);
  });
}

function detachNode(ctx, node) {
  if (!node) return;
  ctx.nodes.delete(node);
  try {
    if (typeof node.pause === "function") node.pause();
    if (typeof node.removeAttribute === "function") node.removeAttribute("src");
  } catch {
    // A node that is already gone cannot be reset; its URL is revoked anyway.
  }
}

/** Revoke every blob this render owns. Called on repaint, removal and pagehide. */
function disposeMedia(ctx) {
  ctx.generation += 1;
  for (const node of [...ctx.nodes]) detachNode(ctx, node);
  for (const url of ctx.media.values()) {
    try {
      if (globalThis.URL && typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(url);
    } catch {
      // Nothing left to revoke.
    }
  }
  ctx.media.clear();
}

function disposeContext(ctx) {
  ctx.disposed = true;
  disposeMedia(ctx);
}

/** The blob URL for one file, fetched once per render generation and reused. */
async function mediaUrl(ctx, file) {
  const cached = ctx.media.get(file.url);
  if (cached) return cached;
  const blob = await fetchMedia(file);
  if (ctx.disposed) return null;
  if (!globalThis.URL || typeof URL.createObjectURL !== "function") {
    throw named("This browser cannot hold the media in memory.", "APPROVAL_MEDIA_BLOB");
  }
  const url = URL.createObjectURL(blob);
  ctx.media.set(file.url, url);
  return url;
}

async function hydrateMedia(ctx, job, generation) {
  try {
    const url = await mediaUrl(ctx, job.file);
    if (!url || generation !== ctx.generation || ctx.disposed) return;
    job.node.setAttribute("src", url);
    ctx.nodes.add(job.node);
    if (typeof job.node.load === "function") job.node.load();
    await (job.kind === "image" ? imageReady(job.node) : audioReady(job.node));
    if (generation !== ctx.generation || ctx.disposed) return;
    if (typeof ctx.target.contains === "function" && !ctx.target.contains(job.node)) {
      detachNode(ctx, job.node);
      return;
    }
    if (typeof job.node.addEventListener === "function") {
      job.node.addEventListener("error", () => {
        if (ctx.disposed || generation !== ctx.generation) return;
        disable(job.button);
        if (job.gate) {
          job.gate.failed = true;
          disable(job.gate.approveButton);
        }
        mediaFailed(ctx, job.item);
      });
    }
    enable(job.button);
    if (job.gate) {
      job.gate.pending -= 1;
      if (job.gate.pending === 0 && !job.gate.failed) enable(job.gate.approveButton);
    }
  } catch (err) {
    if (generation !== ctx.generation || ctx.disposed) return;
    if (isRevisionRequired(err)) {
      reloadStaleCard(ctx, job.item, errText(err));
      return;
    }
    if (job.gate) {
      job.gate.pending -= 1;
      job.gate.failed = true;
      disable(job.gate.approveButton);
    }
    disable(job.button);
    mediaFailed(ctx, job.item);
  }
}

function reloadStaleCard(ctx, item, text) {
  const line = `That approval changed (${text}). Asking the studio for the newest version…`;
  const card = ctx.cards.get(cardKey(item));
  if (card) card.append(el("p", { class: "refusal", text: line }));
  announce(line);
  reloadApprovalsInto(ctx);
}

async function reloadApprovalsInto(ctx) {
  const svc = globalThis.studioService;
  if (!svc || typeof svc.listApprovals !== "function" || ctx.disposed) return;
  const token = ++ctx.reloadSeq;
  if (typeof ctx.target.contains !== "function") return;
  let raw;
  try {
    raw = await svc.listApprovals(ctx.orderId);
  } catch {
    return; // The old cards stay; the next repaint will try again.
  }
  if (ctx.disposed || token !== ctx.reloadSeq) return;
  if (live.get(ctx.target) !== ctx) return;
  const items = (Array.isArray(raw) ? raw : (raw && Array.isArray(raw.items) ? raw.items : []))
    .slice()
    .sort((a, b) => (STAGE_ORDER.indexOf(a.stage) - STAGE_ORDER.indexOf(b.stage))
      || (Number(a.version) - Number(b.version)));
  if (!items.length) return;
  ctx.items = items;
  if (!ctx.disposed && live.get(ctx.target) === ctx) paint(ctx);
}

function mediaFailed(ctx, item) {
  const key = cardKey(item);
  const card = ctx.cards.get(key);
  if (!card) return;
  if (ctx.failed.has(key)) return; // one notice per card until the next paint
  ctx.failed.add(key);
  card.append(el("p", { class: "refusal", text: "This file would not load." }));
  card.append(el("div", { class: "actions" }, [
    // A fresh paint re-runs the load: a file that never arrived is fetched
    // again, and the answer unlocks once every file on the card is ready.
    actionBtn("Try again", () => { paint(ctx); return Promise.resolve(); }),
  ]));
  card.append(el("p", { class: "muted", text: "If it still will not load, answer in your chat instead." }));
  announce("This file would not load.");
}

// ── removed-root cleanup ─────────────────────────────────────────────────────
// studio.js builds a fresh approvals slot per navigation but never calls a
// teardown; the view watches for its own roots leaving the document so their
// blob URLs are revoked even when the next paint never touches them.
const live = new Map();
let detachWatch = null;
let renderSeq = 0;

const nodeHolds = (parent, node) => {
  if (!parent || !node) return false;
  if (parent === node) return true;
  if (typeof parent.contains === "function") {
    try { return parent.contains(node); } catch { return false; }
  }
  return false;
};

function stopWatchIfIdle() {
  if (live.size || !detachWatch) return;
  try { detachWatch.disconnect(); } catch { /* already gone */ }
  detachWatch = null;
}

function watchRemovals() {
  if (detachWatch || typeof globalThis.MutationObserver !== "function") return;
  const doc = globalThis.document;
  const scope = doc && (doc.body || doc.documentElement);
  if (!scope) return;
  detachWatch = new globalThis.MutationObserver((records) => {
    for (const [root, ctx] of [...live]) {
      const gone = (records || []).some((rec) => (rec.removedNodes || [])
        .some((n) => nodeHolds(n, root)));
      if (!gone) continue;
      disposeContext(ctx);
      live.delete(root);
    }
    stopWatchIfIdle();
  });
  detachWatch.observe(scope, { childList: true, subtree: true });
}

if (typeof globalThis.addEventListener === "function") {
  globalThis.addEventListener("pagehide", () => {
    for (const ctx of live.values()) disposeContext(ctx);
    live.clear();
    stopWatchIfIdle();
  });
}

// ── the three card bodies ────────────────────────────────────────────────────
function scriptControls(ctx, item) {
  const id = `change-${item.stage}-${item.version}`;
  const input = el("input", { id, type: "text", autocomplete: "off" });
  input.value = "";
  return [
    el("label", { class: "hint", for: id, text: "What should change? Type it here." }),
    input,
    el("div", { class: "actions" }, [
      actionBtn("Looks great", () => submit(ctx, item, "approve")),
      actionBtn("Change something", () => {
        const value = String(input.value || "").trim();
        if (!value) {
          announce("Write what should change, then tap Change something.");
          return Promise.resolve();
        }
        return submit(ctx, item, value);
      }),
    ]),
  ];
}

function songControls(ctx, item) {
  const key = cardKey(item);
  const files = Array.isArray(item.files) ? item.files : [];
  const choices = Array.isArray(item.choices) ? item.choices : [];
  const gate = ctx.gates.get(key) || { pending: 0, failed: false, approveButton: null };
  const options = files.length
    ? files.slice(0, 3).map((f, i) => ({ n: i + 1, file: f, label: choices[i] ? choices[i].label : null }))
    : choices.map((c, i) => ({
      n: Number.isFinite(Number(c.n)) && Number(c.n) > 0 ? Number(c.n) : i + 1,
      file: null, label: c.label,
    }));

  if (!options.length) {
    return [el("p", {
      class: "muted",
      text: "The three song versions are not on this page yet. They appear here as soon as the studio finishes them.",
    })];
  }

  const rows = options.map((o) => {
    // preload=metadata so the browser actually reports readiness; "none" would
    // sit at readyState 0 forever and never enable the pick.
    const player = o.file ? el("audio", { controls: true, preload: "metadata" }) : null;
    const pick = actionBtn("Pick this one", () => submit(ctx, item, String(o.n)), Boolean(o.file));
    if (o.file) {
      gate.pending += 1;
      ctx.jobs.push({ item, file: o.file, node: player, button: pick, gate, kind: "audio" });
    }
    return el("div", { class: "media-row" }, [
      player,
      o.label ? el("p", { class: "hint", text: `Version ${o.n}: ${o.label}` }) : null,
      pick,
    ]);
  });

  ctx.gates.set(key, gate);
  return [el("fieldset", { class: "options" }, [
    el("legend", { text: "Listen to each one, then pick the version you want." }),
    ...rows,
  ])];
}

function storyboardControls(ctx, item) {
  const key = cardKey(item);
  const files = Array.isArray(item.files) ? item.files : [];
  const shots = files.length
    ? files.map((f, i) => ({ n: i + 1, file: f }))
    : [{ n: 1, file: null }];
  const gate = ctx.gates.get(key) || { pending: 0, failed: false, approveButton: null };

  const rows = shots.map((s) => {
    const id = `shot-${item.version}-${s.n}`;
    const input = el("input", { id, type: "text", autocomplete: "off" });
    input.value = "";
    const still = s.file ? el("img", { alt: `Shot ${s.n} of the storyboard` }) : null;
    const change = actionBtn("Change this shot", () => {
      const value = String(input.value || "").trim();
      if (!value) {
        announce("Write what should change, then tap Change this shot.");
        return Promise.resolve();
      }
      return submit(ctx, item, `shot ${s.n}: ${value}`);
    }, Boolean(s.file));
    if (s.file) {
      gate.pending += 1;
      ctx.jobs.push({ item, file: s.file, node: still, button: change, gate, kind: "image" });
    }
    return el("div", { class: "media-row" }, [
      still,
      el("label", { class: "hint", for: id, text: `What should change in shot ${s.n}?` }),
      input,
      change,
    ]);
  });

  const approve = actionBtn("Approve all", () => submit(ctx, item, "GO"), files.length > 0);
  gate.approveButton = approve;
  ctx.gates.set(key, gate);

  return [
    el("fieldset", { class: "options" }, [
      el("legend", { text: "Every shot, in order." }),
      ...rows,
    ]),
    el("div", { class: "actions" }, [approve]),
  ];
}

// ── one card ─────────────────────────────────────────────────────────────────
function cardFor(ctx, item) {
  const heading = headingFor(item);
  const body = [el("h2", { text: heading })];

  if (item.text) body.push(el("p", { class: "approval-text", text: String(item.text) }));

  if (item.answer && item.answer.value != null && item.answer.value !== "") {
    body.push(el("p", { class: "complete", text: answerWords(item) }));
  } else {
    body.push(el("p", { class: "muted", text: WAITING }));
    if (item.stage === "script") body.push(...scriptControls(ctx, item));
    else if (item.stage === "song") body.push(...songControls(ctx, item));
    else if (item.stage === "storyboard") body.push(...storyboardControls(ctx, item));
    else body.push(el("p", { class: "muted", text: `Nothing to answer for ${item.stage} yet.` }));
  }

  const card = el("div", {
    class: "card approval-card",
    "data-stage": String(item.stage),
    "data-version": String(item.version),
  }, body);
  ctx.cards.set(cardKey(item), card);
  return card;
}

function paint(ctx) {
  if (ctx.disposed) return;
  // Cards are replaced, so the previous blobs' nodes are detached; the blob
  // URLs themselves stay in ctx.media until the render is disposed.
  for (const node of [...ctx.nodes]) detachNode(ctx, node);
  ctx.generation += 1;
  ctx.cards = new Map();
  ctx.gates = new Map();
  ctx.jobs = [];
  ctx.failed = new Set();
  const cards = ctx.items.length
    ? ctx.items.map((item) => cardFor(ctx, item))
    : [messageCard("Your approvals", "Nothing is waiting for your approval right now.")];
  ctx.target.replaceChildren(...cards);
  const generation = ctx.generation;
  for (const job of ctx.jobs) hydrateMedia(ctx, job, generation);
  ctx.jobs = [];
}

function showNotice(ctx, item, text) {
  const card = ctx.cards.get(cardKey(item));
  if (card) card.append(el("p", { class: "refusal", text }));
  announce(text);
}

async function submit(ctx, item, value) {
  announce("Saving your answer…");
  try {
    const resp = await globalThis.studioService.answerApproval(ctx.orderId, item.stage, item.version, value);
    const recorded = resp && resp.answer;
    item.answer = recorded && recorded.value != null
      ? recorded
      : { value, by: "page", at: new Date().toISOString() };
    announce(`Answered: ${value}`);
    paint(ctx);
  } catch (err) {
    if (isTaken(err)) showNotice(ctx, item, "This was already answered, from your chat or another device. Nothing more to do here.");
    else showNotice(ctx, item, `That answer was not saved (${errText(err)}). Nothing was lost — try again.`);
  }
}

/** Revoke this render's blob URLs when its owner tears the cards down. */
export function disposeApprovals(root) {
  const ctx = live.get(root);
  if (!ctx) return;
  disposeContext(ctx);
  live.delete(root);
  stopWatchIfIdle();
}

// ── the entry point ──────────────────────────────────────────────────────────
export async function renderApprovalsFor(order, root) {
  const doc = globalThis.document;
  const target = root || (doc && doc.getElementById
    ? (doc.getElementById("approvals") || doc.getElementById("main"))
    : null);
  if (!target) throw new Error("approvals-view: nowhere to render (pass a root element)");

  // A newer render for the same slot supersedes the previous one and owns its
  // media from here on.
  const previous = live.get(target);
  if (previous) disposeContext(previous);
  live.delete(target);

  const orderId = order && (order.order_id || order.id);
  if (!orderId) {
    target.replaceChildren(messageCard("Your approvals", "Approvals appear here once your order is running."));
    return [];
  }

  const svc = globalThis.studioService;
  if (!svc || typeof svc.listApprovals !== "function") {
    target.replaceChildren(messageCard(
      "Your approvals",
      "This page is not connected to the studio yet, so no approvals can be shown.",
    ));
    return [];
  }

  const ctx = {
    token: ++renderSeq,
    orderId,
    items: [],
    target,
    cards: new Map(),
    gates: new Map(),
    jobs: [],
    media: new Map(),
    nodes: new Set(),
    failed: new Set(),
    generation: 0,
    reloadSeq: 0,
    disposed: false,
  };
  live.set(target, ctx);
  watchRemovals();

  let raw;
  try {
    raw = await svc.listApprovals(orderId);
  } catch (err) {
    if (live.get(target) !== ctx) return []; // superseded while in flight
    disposeContext(ctx);
    live.delete(target);
    stopWatchIfIdle();
    target.replaceChildren(messageCard(
      "Your approvals",
      `Your approvals could not be loaded (${errText(err)}). Try again in a moment.`,
    ));
    return [];
  }

  // Navigation replaced this slot while the list was in flight: paint nothing
  // and create no blob.
  if (live.get(target) !== ctx || ctx.disposed) return [];

  ctx.items = (Array.isArray(raw) ? raw : (raw && Array.isArray(raw.items) ? raw.items : []))
    .slice()
    .sort((a, b) => (STAGE_ORDER.indexOf(a.stage) - STAGE_ORDER.indexOf(b.stage))
      || (Number(a.version) - Number(b.version)));
  paint(ctx);
  return ctx.items;
}
