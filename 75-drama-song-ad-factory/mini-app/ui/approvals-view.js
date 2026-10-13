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
// `mini-app/approvals/ui.mjs` holds the same card model but that folder is NOT
// served to the phone, so nothing is imported from it: the headings are copied
// verbatim, and its rules are kept here — a plain `el()` builder, `textContent`
// only (never `innerHTML`), and every state carried in words.
//
// Buttons and the exact value each one sends (SPEC §4):
//   script      Looks great        -> "approve"
//               Change something   -> the typed text
//   song        Pick this one      -> "1" .. "3" (which of the players)
//   storyboard  Approve all        -> "GO"
//               Change this shot   -> "shot N: <text>"
//
// The first answer wins: a second answer comes back as HTTP 409
// APPROVAL_ANSWER_TAKEN and the card says "Already answered".
//
// Checked by checks/approvals-view-check.mjs (fake service + DOM shim).
// =============================================================================

// Copied from mini-app/approvals/ui.mjs (APPROVAL_HEADINGS) — that path is not
// served to the phone, so the words travel with this file.
const APPROVAL_HEADINGS = Object.freeze({
  script: "Approval 1 — the script",
  song: "Approval 2 — the song (pick 1 of 3)",
  storyboard: "Approval 3 — the storyboard",
});

// The order the three cards are shown in (same as ui.mjs APPROVAL_ITEMS).
const STAGE_ORDER = Object.freeze(["script", "song", "storyboard"]);

const WAITING = "Waiting for your answer. Nothing is made until you say it looks good.";

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

function actionBtn(text, fn) {
  const b = el("button", { class: "btn", type: "button", text });
  b.addEventListener("click", fn);
  return b;
}

const answerWords = (item) =>
  `You answered: “${item.answer.value}”. That answer is recorded and stays on the page.`;

function messageCard(heading, text) {
  return el("div", { class: "card approval-card" }, [
    el("h2", { text: heading }),
    el("p", { class: "muted", text }),
  ]);
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
  const files = Array.isArray(item.files) ? item.files : [];
  const choices = Array.isArray(item.choices) ? item.choices : [];
  const options = files.length
    ? files.slice(0, 3).map((f, i) => ({
      n: i + 1, url: f.url, label: choices[i] ? choices[i].label : null,
    }))
    : choices.map((c, i) => ({
      n: Number.isFinite(Number(c.n)) && Number(c.n) > 0 ? Number(c.n) : i + 1,
      url: null, label: c.label,
    }));

  if (!options.length) {
    return [el("p", {
      class: "muted",
      text: "The three song versions are not on this page yet. They appear here as soon as the studio finishes them.",
    })];
  }

  const rows = options.map((o) => el("div", { class: "option" }, [
    o.url ? el("audio", { controls: true, preload: "none", src: o.url }) : null,
    o.label ? el("p", { class: "hint", text: `Version ${o.n}: ${o.label}` }) : null,
    actionBtn("Pick this one", () => submit(ctx, item, String(o.n))),
  ]));

  return [el("fieldset", { class: "options" }, [
    el("legend", { text: "Listen to each one, then pick the version you want." }),
    ...rows,
  ])];
}

function storyboardControls(ctx, item) {
  const files = Array.isArray(item.files) ? item.files : [];
  const shots = files.length
    ? files.map((f, i) => ({ n: i + 1, url: f.url }))
    : [{ n: 1, url: null }];

  const rows = shots.map((s) => {
    const id = `shot-${item.version}-${s.n}`;
    const input = el("input", { id, type: "text", autocomplete: "off" });
    input.value = "";
    return el("div", { class: "option" }, [
      s.url ? el("img", { src: s.url, alt: `Shot ${s.n} of the storyboard` }) : null,
      el("label", { class: "hint", for: id, text: `What should change in shot ${s.n}?` }),
      input,
      actionBtn("Change this shot", () => {
        const value = String(input.value || "").trim();
        if (!value) {
          announce("Write what should change, then tap Change this shot.");
          return Promise.resolve();
        }
        return submit(ctx, item, `shot ${s.n}: ${value}`);
      }),
    ]);
  });

  return [
    el("fieldset", { class: "options" }, [
      el("legend", { text: "Every shot, in order." }),
      ...rows,
    ]),
    el("div", { class: "actions" }, [actionBtn("Approve all", () => submit(ctx, item, "GO"))]),
  ];
}

// ── one card ─────────────────────────────────────────────────────────────────
function cardFor(ctx, item) {
  const heading = APPROVAL_HEADINGS[item.stage] || `Approval — ${item.stage}`;
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
  ctx.cards = new Map();
  const cards = ctx.items.length
    ? ctx.items.map((item) => cardFor(ctx, item))
    : [messageCard("Your approvals", "Nothing is waiting for your approval right now.")];
  ctx.target.replaceChildren(...cards);
}

function showNotice(ctx, item, text) {
  const card = ctx.cards.get(cardKey(item));
  if (card) card.append(el("p", { class: "refusal", text }));
  announce(text);
}

async function submit(ctx, item, value) {
  announce("Saving your answer…");
  try {
    await globalThis.studioService.answerApproval(ctx.orderId, item.stage, item.version, value);
    item.answer = { value, by: "page", at: new Date().toISOString() };
    announce(`Answered: ${value}`);
    paint(ctx);
  } catch (err) {
    if (isTaken(err)) showNotice(ctx, item, "Already answered");
    else showNotice(ctx, item, `That answer was not saved (${errText(err)}). Nothing was lost — try again.`);
  }
}

// ── the entry point ──────────────────────────────────────────────────────────
export async function renderApprovalsFor(order, root) {
  const doc = globalThis.document;
  const target = root || (doc && doc.getElementById
    ? (doc.getElementById("approvals") || doc.getElementById("main"))
    : null);
  if (!target) throw new Error("approvals-view: nowhere to render (pass a root element)");

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

  let raw;
  try {
    raw = await svc.listApprovals(orderId);
  } catch (err) {
    target.replaceChildren(messageCard(
      "Your approvals",
      `Your approvals could not be loaded (${errText(err)}). Try again in a moment.`,
    ));
    return [];
  }

  const items = (Array.isArray(raw) ? raw : (raw && Array.isArray(raw.items) ? raw.items : []))
    .slice()
    .sort((a, b) => (STAGE_ORDER.indexOf(a.stage) - STAGE_ORDER.indexOf(b.stage))
      || (Number(a.version) - Number(b.version)));

  const ctx = { orderId, items, target, cards: new Map() };
  paint(ctx);
  return items;
}
