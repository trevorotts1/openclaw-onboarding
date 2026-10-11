// =============================================================================
// ui.mjs — the APPROVALS UI (U8)
// -----------------------------------------------------------------------------
// 75-drama-song-ad-factory/mini-app/approvals/ui.mjs
//
// The approval cards the client sees, built in the SAME page patterns U3 uses
// on `mini-app/ui/`: a plain `el()` builder, real <button>/<h2>/<p> nodes, no
// innerHTML anywhere, and every state carried by words (never by colour alone).
// It is NOT a second framework, scheduler or dashboard — three cards and the
// service's lines, nothing else.
//
// It RENDERS THE SERVICE'S LINES. The words are U2's; this file never rewords,
// truncates or reformats them. Whatever `serviceLines` arrives is emitted
// verbatim, in order, inside the studio-lines region. If a card's item is not
// approved the card shows the "Looks good" action; once approved it shows the
// recorded state and stays on the page.
//
// The view model (`approvalsView`) is pure data, so a check can assert on it
// with no browser; `renderApprovals` is the thin DOM wrapper over it.
// =============================================================================

//: The three cards, in the order U3 page 4 shows them.
export const APPROVAL_ITEMS = Object.freeze(["script", "song", "storyboard"]);

export const APPROVAL_HEADINGS = Object.freeze({
  script: "Approval 1 — the script",
  song: "Approval 2 — the song (pick 1 of 3)",
  storyboard: "Approval 3 — the storyboard",
});

export const APPROVAL_ACTIONS = Object.freeze({
  script: "Looks good — approve the script",
  song: "Looks good — use this song",
  storyboard: "Looks good — approve every shot",
});

/** One approval item -> its card view model. Pure. */
export function approvalCard(item) {
  const itemId = item.item_id;
  const answered = !!item.answer;
  return {
    item_id: itemId,
    version: item.version,
    heading: APPROVAL_HEADINGS[itemId] || itemId,
    status: answered ? "approved" : "awaiting",
    // Every state has words beside it — no state is carried by colour alone.
    status_text: answered
      ? `You answered "${item.answer.answer}". This stays on the page.`
      : "Waiting for your answer. Nothing is made until you say it looks good.",
    action_label: answered ? null : (APPROVAL_ACTIONS[itemId] || "Looks good"),
    notices_sent: (item.escalation && item.escalation.count) || 0,
  };
}

/**
 * The whole approvals view. `serviceLines` are emitted VERBATIM and in order —
 * they are U2's words, not this file's. `items` are the approval items the
 * store holds, ordered by the three-card order then by version.
 */
export function approvalsView({ items = [], serviceLines = [] } = {}) {
  const order = (a, b) => {
    const ia = APPROVAL_ITEMS.indexOf(a.item_id);
    const ib = APPROVAL_ITEMS.indexOf(b.item_id);
    return (ia === -1 ? APPROVAL_ITEMS.length : ia) - (ib === -1 ? APPROVAL_ITEMS.length : ib)
      || a.version - b.version;
  };
  return {
    lines: serviceLines.map((s) => String(s)), // verbatim; never reworded
    cards: [...items].sort(order).map(approvalCard),
  };
}

// ── the thin DOM wrapper (mirrors U3's el() builder) ─────────────────────────
/** Build a DOM tree for the view. `el` is injected so this is testable without
 *  a browser and so the page and the checks share the exact same builder. */
export function renderApprovals(doc, view) {
  const el = (tag, attrs = {}, children = []) => {
    const node = doc.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "text") node.textContent = v; // textContent, never innerHTML
      else node.setAttribute(k, v === true ? "" : String(v));
    }
    for (const c of [].concat(children)) node.append(c);
    return node;
  };

  const parts = [el("h1", { text: "Three things you approve" })];

  if (view.lines.length) {
    parts.push(el("div", { class: "card studio-lines" }, [
      el("h2", { text: "From your studio" }),
      ...view.lines.map((line) => el("p", { class: "studio-line", text: line })),
    ]));
  }

  for (const card of view.cards) {
    const body = [el("h2", { text: card.heading }), el("p", { class: "muted", text: card.status_text })];
    if (card.notices_sent) {
      body.push(el("p", {
        class: "muted",
        text: card.notices_sent === 1 ? "One nudge has been sent." : "A nudge and one reminder have been sent.",
      }));
    }
    if (card.action_label) {
      body.push(el("div", { class: "actions" }, [
        el("button", { class: "btn", type: "button", text: card.action_label,
          "data-item": card.item_id, "data-version": String(card.version) }),
      ]));
    }
    parts.push(el("div", { class: "card", "data-item": card.item_id }, body));
  }

  return el("div", { class: "approvals" }, parts);
}
