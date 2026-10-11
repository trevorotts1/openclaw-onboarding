// =============================================================================
// approvals.prove.mjs — the U8 runnable proofs (the CLEAN control)
// -----------------------------------------------------------------------------
// 75-drama-song-ad-factory/mini-app/approvals/prove/approvals.prove.mjs
//
// One command, real exit codes, no framework:
//
//   node 75-drama-song-ad-factory/mini-app/approvals/prove/approvals.prove.mjs
//   exit 0 = every case passed, 2 = a named case failed
//
// Five cases, one per owned behaviour plus the UI:
//   C1 FIRST ANSWER WINS           — a loser answer is refused, the record untouched
//   C2 VERSION DEDUP               — same version = one item; new version = a new item
//   C3 ONE NUDGE THAN REMINDER...  — exactly ["nudge","reminder"] then null forever
//   C4 PRODUCER HAND-OFF REFUSES   — a real non-zero exit, stdout empty
//   C5 UI RENDERS THE SERVICE LINES— verbatim, in order, no reword
//
// Each case is paired with its planted-bad control in ./planted-bad.sh, which
// mutates a LOCAL COPY of approvals.mjs, shows the matching case turn RED
// (exit 2), then restores and shows this clean run GREEN (exit 0).
// =============================================================================
import { spawnSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import * as A from "../approvals.mjs";
import { approvalsView, renderApprovals } from "../ui.mjs";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const CLI = fileURLToPath(new URL("../producer-handoff.mjs", import.meta.url));
const CID = "c1";

function assert(cond, msg) { if (!cond) throw new Error(msg || "assertion failed"); }
function eq(a, b, msg) {
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    throw new Error(`${msg || "not equal"}: got ${JSON.stringify(a)}, want ${JSON.stringify(b)}`);
  }
}

let fails = 0;
function check(name, fn) {
  try { fn(); process.stdout.write(`PASS ${name}\n`); }
  catch (e) { fails += 1; process.stdout.write(`FAIL ${name} :: ${e && e.message ? e.message : e}\n`); }
}

// ── C1 FIRST ANSWER WINS ─────────────────────────────────────────────────────
export function c1_firstAnswerWins() {
  check("C1_FIRST_ANSWER_WINS", () => {
    const s = A.memoryStore();
    A.registerItem(s, { clientId: CID, itemId: "script", version: 1 });
    const first = A.recordAnswer(s, { clientId: CID, itemId: "script", version: 1, answer: "approved" });
    assert(first.ok && first.recorded, "the first answer must be recorded");
    const second = A.recordAnswer(s, { clientId: CID, itemId: "script", version: 1, answer: "change the ending" });
    assert(second.ok === false, "a second competing answer must be refused, not accepted");
    assert(second.code === A.CODE.ANSWER_TAKEN, `refused by name, got ${second.code}`);
    const rec = s.get(`approval:${CID}:script:1`);
    assert(rec.answer.answer === "approved", "the recorded answer must be untouched");
  });
}

// ── C2 VERSION DEDUP ─────────────────────────────────────────────────────────
export function c2_versionDedup() {
  check("C2_VERSION_DEDUP", () => {
    const s = A.memoryStore();
    const a = A.registerItem(s, { clientId: CID, itemId: "script", version: 1 });
    const b = A.registerItem(s, { clientId: CID, itemId: "script", version: 1 });
    assert(a.created === true && b.created === false, "the same version must not create a second item");
    eq(s.list(`approval:${CID}:script`).length, 1, "exactly one approval item for v1");
    const c = A.registerItem(s, { clientId: CID, itemId: "script", version: 2 });
    assert(c.created === true, "a genuinely new version must create a new item");
    eq(s.list(`approval:${CID}:script`).length, 2, "two approval items after a new version");
  });
}

// ── C3 ONE NUDGE, THEN REMINDER, THEN SILENCE ────────────────────────────────
export function c3_oneNudgeThenReminderThenSilence() {
  check("C3_NUDGE_REMINDER_SILENCE", () => {
    const s = A.memoryStore();
    A.registerItem(s, { clientId: CID, itemId: "script", version: 1 });
    const notices = [];
    for (let i = 0; i < 5; i += 1) {
      notices.push(A.escalate(s, { clientId: CID, itemId: "script", version: 1 }).notice);
    }
    // Strict per element: a removed cap yields undefined, not null, so a loose
    // (JSON) comparison would hide the defect.
    const expected = ["nudge", "reminder", null, null, null];
    for (let i = 0; i < expected.length; i += 1) {
      assert(notices[i] === expected[i],
        `event ${i}: got ${String(notices[i])}, want ${String(expected[i])}`);
    }
    // The stored ladder also stops at two — no third write ever happens.
    eq(s.get(`approval:${CID}:script:1`).escalation.count, 2,
      "no more than two notices are ever recorded");
    // An answered item is always silent, even if events keep arriving.
    A.recordAnswer(s, { clientId: CID, itemId: "script", version: 1, answer: "approved" });
    eq(A.escalate(s, { clientId: CID, itemId: "script", version: 1 }).notice, null,
      "an answered item never escalates");
  });
}

// ── C4 PRODUCER HAND-OFF REFUSES UNAPPROVED ──────────────────────────────────
export function c4_producerHandoffRefuses() {
  check("C4_PRODUCER_HANDOFF_REFUSES", () => {
    const dir = mkdtempSync(join(tmpdir(), "u8-approvals-"));
    const storePath = join(dir, "approvals.json");
    const s = A.fileStore(storePath);
    A.registerItem(s, { clientId: CID, itemId: "script", version: 1 });

    const before = A.producerPayload(s, { clientId: CID, itemId: "script", version: 1 });
    assert(before.ok === false && before.code === A.CODE.NOT_APPROVED, "an unapproved item must be refused");

    const args = [CLI, "--store", storePath, "--client-id", CID, "--item", "script", "--version", "1"];
    const r = spawnSync(process.execPath, args, { encoding: "utf8" });
    assert(r.status !== 0, `the CLI must exit non-zero, got ${r.status}`);
    eq(r.status, A.REFUSED_EXIT, "the CLI uses the existing refusal exit code");
    assert(r.stdout.trim() === "", "nothing is handed to the producer on a refusal");

    // Positive control on the same instrument: once approved, it goes through.
    A.recordAnswer(s, { clientId: CID, itemId: "script", version: 1, answer: "approved" });
    const r2 = spawnSync(process.execPath, args, { encoding: "utf8" });
    eq(r2.status, 0, "an approved item is handed off with exit 0");
    const payload = JSON.parse(r2.stdout);
    eq(payload.answer, "approved", "the hand-off carries the recorded answer");
  });
}

// ── C5 UI RENDERS THE SERVICE'S LINES VERBATIM ───────────────────────────────
export function c5_uiRendersServiceLines() {
  check("C5_UI_RENDERS_SERVICE_LINES", () => {
    const line = "Your crew is watching. Orders start within about 2 minutes while your computer is on. Last check-in: 1 minute ago.";
    const items = [{ item_id: "script", version: 1, answer: null, escalation: { count: 1, last_at: 0 } }];
    const view = approvalsView({ items, serviceLines: [line] });
    eq(view.lines, [line], "the service's line is rendered verbatim, in order");
    eq(view.cards[0].status, "awaiting", "an unanswered card is awaiting");
    assert(view.cards[0].action_label, "an unanswered card shows the Looks-good action");

    const tree = renderApprovals(fakeDoc(), view);
    const flat = flatten(tree);
    assert(flat.includes(line), "the line reaches the DOM as text");
    assert(flat.includes("Approval 1 — the script"), "the card heading reaches the DOM");
    assert(!flat.includes("<"), "no markup was smuggled in as text");

    // The approved card shows the recorded state and no action.
    const view2 = approvalsView({ items: [{ item_id: "script", version: 1, answer: { answer: "approved" }, escalation: { count: 2 } }] });
    eq(view2.cards[0].status, "approved", "an approved card says so");
    eq(view2.cards[0].action_label, null, "an approved card offers no second answer");
  });
}

// ── a dependency-free DOM stand-in (the checks own no browser) ───────────────
function fakeDoc() {
  const mk = (tag) => ({
    tagName: tag, children: [], attrs: {}, textContent: "",
    append(c) { this.children.push(c); },
    setAttribute(k, v) { this.attrs[k] = v; },
  });
  return { createElement: mk };
}
function flatten(node) {
  const own = node.textContent || "";
  return own + node.children.map(flatten).join(" ");
}

// ── run ──────────────────────────────────────────────────────────────────────
c1_firstAnswerWins();
c2_versionDedup();
c3_oneNudgeThenReminderThenSilence();
c4_producerHandoffRefuses();
c5_uiRendersServiceLines();

process.stdout.write(fails === 0
  ? "ALL PASS — the four behaviours and the UI are green\n"
  : `${fails} FAILED\n`);
process.exit(fails === 0 ? 0 : 2);
