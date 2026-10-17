// S2 (FIX-PLAN Item 13 addendum) wiring proof, fully local: the branded
// page (pages/index.html) is executed in a minimal DOM stub against the
// REAL deployed-r2 worker (in-memory R2 shim). The test opens the page
// through a bridge-minted capability link, answers every question through
// the page's OWN form logic (its builders, its serialize(), its session
// POSTs), completes, and then asserts, in order:
//   1. the page's completion screen reports the honest state (Saved and
//      queued, NOT started) while the outbox is merely queued;
//   2. the intake the box bridge fetches is the canonical record: brief
//      fields in deck_brief, upsell flags in pre_presentation_capture,
//      the declined-reason waiver captured, and derived_field_provenance
//      stamped for the six derived fields;
//   3. once the box-side fetch flips the outbox to worker_accepted, the
//      page's own polling shows Worker accepted.
// No live deploy is involved; this is the repo-state proof that the live
// fix is a deploy of these files.
//   node --test test/test_branded_page_session_flow.test.mjs

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { R2Shim, WorkerHarness } from "./pres024_env.mjs";
import worker from "../deployed-r2/src/index.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE_HTML = readFileSync(path.join(HERE, "../pages/index.html"), "utf8");
const QUESTIONS_JSON = JSON.parse(readFileSync(path.join(HERE, "../pages/questions.json"), "utf8"));
const SCRIPT = PAGE_HTML.match(/<script>([\s\S]*?)<\/script>/)[1];

// ---------------------------------------------------------------------------
// Minimal DOM stub: exactly the surface pages/index.html uses.
// ---------------------------------------------------------------------------
const ALL_ELEMENTS = [];

class El {
  constructor(tag) {
    this.tagName = String(tag || "div").toUpperCase();
    this.children = [];
    this.parent = null;
    this.attributes = {};
    this.className = "";
    this._text = "";
    this._html = "";
    this.style = {};
    this.value = "";
    this.disabled = false;
    this.files = null;
    ALL_ELEMENTS.push(this);
  }
  get firstChild() { return this.children[0] || null; }
  get lastChild() { return this.children[this.children.length - 1] || null; }
  get previousElementSibling() {
    if (!this.parent) return null;
    const i = this.parent.children.indexOf(this);
    return i > 0 ? this.parent.children[i - 1] : null;
  }
  appendChild(c) { if (c) { c.parent = this; this.children.push(c); } return c; }
  removeChild(c) {
    const i = this.children.indexOf(c);
    if (i >= 0) this.children.splice(i, 1);
    if (c) c.parent = null;
    return c;
  }
  setAttribute(k, v) { this.attributes[k] = String(v); if (k === "class") this.className = String(v); }
  getAttribute(k) { return k in this.attributes ? this.attributes[k] : (k === "class" && this.className ? this.className : null); }
  set textContent(v) { this.children = []; this._text = String(v == null ? "" : v); }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  set innerHTML(v) {
    this.children = [];
    this._html = String(v == null ? "" : v);
    const m = this._html.match(/^\s*<(\w+)((?:\s+[\w-]+="[^"]*")*)\s*>/);
    if (m) {
      const child = new El(m[1]);
      const re = /([\w-]+)="([^"]*)"/g;
      let a;
      while ((a = re.exec(m[2])) !== null) child.setAttribute(a[1], a[2]);
      this.appendChild(child);
    }
  }
  get innerHTML() { return this._html; }
  focus() { this._focused = true; }
  click() { if (typeof this.onclick === "function") this.onclick(); }
  addEventListener() {}
  querySelector(sel) { return queryAll(this, sel)[0] || null; }
  querySelectorAll(sel) { return queryAll(this, sel); }
}

function matchesSimple(elm, simple) {
  let s = simple.trim();
  if (!s) return false;
  let notDisabled = false;
  if (s.endsWith(":not(:disabled)")) { notDisabled = true; s = s.slice(0, -":not(:disabled)".length); }
  const attrM = s.match(/\[([\w-]+)=([^\]]+)\]/);
  if (attrM) {
    if (elm.getAttribute(attrM[1]) !== attrM[2].replace(/^"|"$/g, "")) return false;
    s = s.replace(attrM[0], "");
  }
  const parts = s.split(".");
  const tag = parts[0];
  if (tag && elm.tagName !== tag.toUpperCase()) return false;
  for (const cls of parts.slice(1)) {
    if (cls && !String(elm.className || "").split(/\s+/).includes(cls)) return false;
  }
  if (notDisabled && elm.disabled) return false;
  return true;
}

function queryAll(root, sel) {
  const simples = String(sel).split(",");
  const out = [];
  const walk = (n) => {
    for (const c of n.children) {
      if (simples.some((s) => matchesSimple(c, s))) out.push(c);
      walk(c);
    }
  };
  walk(root);
  return out;
}

function* walkAll(root) {
  for (const c of root.children) { yield c; yield* walkAll(c); }
}
function findIn(root, pred) { for (const e of walkAll(root)) if (pred(e)) return e; return null; }
function findAllIn(root, pred) { const out = []; for (const e of walkAll(root)) if (pred(e)) out.push(e); return out; }
const hasClass = (e, cls) => String(e.className || "").split(/\s+/).includes(cls);

// ---------------------------------------------------------------------------
// Harness: mint a session, then run the page against the real worker.
// ---------------------------------------------------------------------------
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, what, timeoutMs = 8000) {
  const t0 = Date.now();
  for (;;) {
    const v = fn();
    if (v) return v;
    if (Date.now() - t0 > timeoutMs) throw new Error("timeout waiting for: " + what);
    await sleep(25);
  }
}

test("branded page drives a minted session end to end into the canonical record", async () => {
  ALL_ELEMENTS.length = 0;
  const env = { STORE: new R2Shim(), INTAKE_ADMIN_TOKEN: "admin-tok" };
  const h = new WorkerHarness(worker, env);

  const questionsPayload = { question_set: "standard", questions: QUESTIONS_JSON.questions };
  const mint = await h.handle("POST", "/api/sessions", {
    token: "admin-tok",
    body: {
      run_id: "run-page-flow", box_id: "box1", questions_payload: questionsPayload,
      company_id: "acme", installation_id: "install-test", presentation_id: "presentation-test",
      want_confirm_code: true,
    },
  });
  assert.equal(mint.status, 201, "mint: " + JSON.stringify(mint.body));
  const token = mint.body.token;
  const confirmCode = mint.body.confirm_code;
  assert.ok(token && confirmCode, "mint returns token + confirm code");

  // -- DOM + page globals -----------------------------------------------------
  const stage = new El("div"); stage.setAttribute("id", "stage");
  const app = new El("main"); app.setAttribute("id", "app");
  const intro = new El("div"); intro.className = "intro";
  app.appendChild(intro); app.appendChild(stage);
  const exitBtn = new El("button"); exitBtn.setAttribute("id", "exitBtn");
  const body = new El("body");
  const documentStub = {
    getElementById: (id) => ALL_ELEMENTS.find((e) => e.getAttribute("id") === id) || null,
    createElement: (tag) => new El(tag),
    body,
    addEventListener: () => {},
  };
  const fetchStub = async (url, opts = {}) => {
    const res = await h.handle(opts.method || "GET", url, {
      body: opts.body ? JSON.parse(opts.body) : null,
    });
    return { ok: res.ok, status: res.status, json: async () => res.body, text: async () => JSON.stringify(res.body) };
  };
  const sandbox = {
    console, setTimeout, clearTimeout, URLSearchParams, Blob, AbortController,
    document: documentStub,
    location: { pathname: "/s/" + token, search: "" },
    fetch: fetchStub,
  };
  sandbox.window = sandbox;
  sandbox.window.location = sandbox.location;
  sandbox.window.confirm = () => true;
  sandbox.window.close = () => {};
  sandbox.window.scrollTo = () => {};
  sandbox.URL = URL;
  URL.createObjectURL = () => "blob:stub";
  URL.revokeObjectURL = () => {};
  vm.createContext(sandbox);
  vm.runInContext(SCRIPT, sandbox, { filename: "pages-index.html.js" });

  // -- Drive the page's own form logic ----------------------------------------
  const promptEl = () => findIn(stage, (e) => e.tagName === "H1" && hasClass(e, "prompt"));
  const currentQid = () => {
    const p = promptEl();
    if (!p) return null;
    const q = QUESTIONS_JSON.questions.find((x) => x.prompt === p.innerHTML);
    return q ? q.id : null;
  };
  const primaryBtn = () => findIn(stage, (e) => e.tagName === "BUTTON" && hasClass(e, "primary") && !e.disabled)
    || findIn(stage, (e) => e.tagName === "BUTTON" && hasClass(e, "primary"));

  const PLAN = {
    presentation_type: { choice: "From scratch" },
    offer_name: { text: "The Momentum Method" },
    named_methodology: { text: "The Three-Move Pipeline System" },
    transformation_promise: { text: "stuck and overwhelmed to clear, confident, closing" },
    time_to_result: { text: "8 weeks" },
    audience: { text: "women entrepreneurs, 35-55, tired of inconsistent clients" },
    cta_action: { text: "book a call" },
    brand_primary: { logoNone: true },
    image_links: { skip: true },
    tone: { text: "Inspirational" },
    final_price: { text: "$497" },
    speech_speed_preference: { choice: "Default pace" },
    want_sales_checkout: { choice: "Yes, build the sales page" },
    want_vsl_page: { choice: "No thank you" },
    vsl_page_declined_reason: { text: "we have no hosted video yet" },
    want_email_sequences: { choice: "No thank you" },
    email_sequences_declined_reason: { text: "we already send our own emails" },
    want_motion_graphics: { choice: "No thank you" },
    motion_graphics_declined_reason: { text: "our brand team handles all motion in-house" },
    run_mode: { skip: true },
    ollama_plan: { skip: true },
    deepseek_variant: { skip: true },
    openrouter_model: { skip: true },
    client_notes: { skip: true },
  };

  const answeredOrder = [];
  for (let step = 0; step < 40; step++) {
    // Wait for ANY screen (confirm, question, review, done), then dispatch.
    await until(() => promptEl() || documentStub.getElementById("sessionStatus"), "any screen");
    const status = documentStub.getElementById("sessionStatus");
    if (status) break;
    const p = promptEl();
    if (p && p.innerHTML.includes("One quick")) {
      const input = findIn(stage, (e) => e.tagName === "INPUT");
      input.value = confirmCode;
      primaryBtn().click();
      await until(() => currentQid() || documentStub.getElementById("sessionStatus"), "first question after confirm");
      continue;
    }
    if (p && p.innerHTML.includes("ready to")) {
      primaryBtn().click(); // Submit my brief
      await until(() => documentStub.getElementById("sessionStatus"), "completion screen");
      break;
    }
    const qid = currentQid();
    assert.ok(qid, "unrecognized screen prompt: " + (p ? p.innerHTML : "(none)"));
    const plan = PLAN[qid];
    assert.ok(plan, "no plan for question " + qid);
    answeredOrder.push(qid);
    if (plan.skip) {
      const skip = findIn(stage, (e) => e.tagName === "BUTTON" && hasClass(e, "ghost"));
      assert.ok(skip, "skip button for " + qid);
      skip.click();
    } else if (plan.logoNone) {
      const nb = findIn(stage, (e) => e.tagName === "BUTTON" && e.textContent.includes("No logo on file"));
      assert.ok(nb, "no-logo button");
      nb.click();
      await until(() => { const b = primaryBtn(); return b && !b.disabled; }, "continue enabled after logo");
      primaryBtn().click();
    } else if (plan.choice) {
      const opt = findIn(stage, (e) => e.tagName === "BUTTON" && hasClass(e, "opt") && e.textContent.includes(plan.choice));
      assert.ok(opt, "choice '" + plan.choice + "' for " + qid);
      opt.click();
      await until(() => { const b = primaryBtn(); return b && !b.disabled; }, "continue enabled after choice");
      primaryBtn().click();
    } else if (plan.text) {
      const ta = findIn(stage, (e) => e.tagName === "TEXTAREA") || findIn(stage, (e) => e.tagName === "INPUT");
      assert.ok(ta, "text field for " + qid);
      ta.value = plan.text;
      if (typeof ta.oninput === "function") ta.oninput();
      await until(() => { const b = primaryBtn(); return b && !b.disabled; }, "continue enabled after text");
      primaryBtn().click();
    }
    // Wait for the screen to change (server round-trip inside advance()).
    const prev = qid;
    await until(() => currentQid() !== prev || documentStub.getElementById("sessionStatus")
      || (promptEl() && promptEl().innerHTML.includes("ready to")), "advance past " + qid);
  }

  // The declined-reason waiver was asked (conditional), the sales one was not.
  assert.ok(answeredOrder.includes("vsl_page_declined_reason"), "waiver question asked: " + answeredOrder.join(","));
  assert.ok(!answeredOrder.includes("sales_checkout_declined_reason"), "sales waiver not asked when accepted");

  // 1. Honest queued state: saved + queued, never "started".
  const statusEl = await until(() => documentStub.getElementById("sessionStatus"), "status line");
  assert.ok(statusEl.textContent.includes("Saved and queued"), "queued copy: " + statusEl.textContent);
  const noteEl = documentStub.getElementById("sessionNote");
  assert.ok(noteEl && noteEl.textContent.includes("has not started yet"), "queued note honest: " + (noteEl || {}).textContent);

  // 2. The box-side fetch returns the canonical record.
  const fetched = await h.handle("GET",
    "/api/intake?id=" + encodeURIComponent(mint.body.intake_session_id)
    + "&company_id=acme&installation_id=install-test&presentation_id=presentation-test"
    + "&run_id=" + encodeURIComponent(mint.body.run_id),
    { token: "admin-tok" });
  assert.equal(fetched.status, 200, "scoped intake fetch: " + JSON.stringify(fetched.body));
  const rec = fetched.body.intake;
  assert.equal(rec.deck_brief.OFFER_NAME, "The Momentum Method");
  assert.equal(rec.deck_brief.TONE, "Inspirational");
  assert.equal(rec.pre_presentation_capture.WANT_SALES_CHECKOUT, "yes");
  assert.equal(rec.pre_presentation_capture.WANT_VSL_PAGE, "no");
  assert.equal(rec.pre_presentation_capture.VSL_PAGE_DECLINED_REASON, "we have no hosted video yet");
  assert.ok(!("WANT_SALES_CHECKOUT" in rec.deck_brief), "upsell flag must not land in deck_brief");
  assert.equal(rec.answers.want_vsl_page, "no");
  assert.equal(rec.presentation_type, "from_scratch");
  const prov = rec.derived_field_provenance || {};
  assert.deepEqual(Object.keys(prov).sort(),
    ["AUDIENCE_COMPOSITION_NOTE", "DARK_OK", "GROUNDED_CONTENT", "HOOK_SEED", "REPRESENTATION_MIX", "VISUAL_MIX"]);
  assert.equal(prov.REPRESENTATION_MIX.source, "audience");
  assert.equal(prov.AUDIENCE_COMPOSITION_NOTE.source, "audience");
  assert.equal(prov.GROUNDED_CONTENT.source, "offer_name");
  assert.equal(prov.VISUAL_MIX.source, "constant");
  assert.equal(prov.DARK_OK.source, "constant");
  assert.equal(prov.HOOK_SEED.source, "transformation_promise");
  for (const k of Object.keys(prov)) assert.ok(prov[k].rule && prov[k].rule.length > 10, "rule text for " + k);

  // 3. The fetch flipped the outbox; the page's own poll shows it.
  const accepted = await until(
    () => { const s = documentStub.getElementById("sessionStatus"); return s && s.textContent.includes("Worker accepted") ? s : null; },
    "page shows Worker accepted", 9000);
  assert.ok(accepted.textContent.includes("Worker accepted"));
  const note2 = documentStub.getElementById("sessionNote");
  assert.ok(note2 && note2.textContent.includes("deck build has started"), "accepted note: " + (note2 || {}).textContent);
});

test("standalone mode (no token): honest NOT SUBMITTED outcome + page-stamped provenance", async () => {
  ALL_ELEMENTS.length = 0;
  const stage = new El("div"); stage.setAttribute("id", "stage");
  const app = new El("main"); app.setAttribute("id", "app");
  const intro = new El("div"); intro.className = "intro";
  app.appendChild(intro); app.appendChild(stage);
  const exitBtn = new El("button"); exitBtn.setAttribute("id", "exitBtn");
  const body = new El("body");
  const documentStub = {
    getElementById: (id) => ALL_ELEMENTS.find((e) => e.getAttribute("id") === id) || null,
    createElement: (tag) => new El(tag),
    body,
    addEventListener: () => {},
  };
  let capturedBlob = null;
  const sandbox = {
    console, setTimeout, clearTimeout, URLSearchParams, Blob, AbortController,
    document: documentStub,
    location: { pathname: "/", search: "" },
    fetch: async () => { throw new Error("standalone no-sink flow must not fetch"); },
  };
  sandbox.window = sandbox;
  sandbox.window.location = sandbox.location;
  sandbox.window.confirm = () => true;
  sandbox.window.close = () => {};
  sandbox.window.scrollTo = () => {};
  sandbox.URL = URL;
  URL.createObjectURL = (blob) => { capturedBlob = blob; return "blob:stub"; };
  URL.revokeObjectURL = () => {};
  vm.createContext(sandbox);
  vm.runInContext(SCRIPT, sandbox, { filename: "pages-index.html.js" });

  const promptEl = () => findIn(stage, (e) => e.tagName === "H1" && hasClass(e, "prompt"));
  const currentQid = () => {
    const p = promptEl();
    if (!p) return null;
    const q = QUESTIONS_JSON.questions.find((x) => x.prompt === p.innerHTML);
    return q ? q.id : null;
  };
  const primaryBtn = () => findIn(stage, (e) => e.tagName === "BUTTON" && hasClass(e, "primary") && !e.disabled)
    || findIn(stage, (e) => e.tagName === "BUTTON" && hasClass(e, "primary"));
  const PLAN = {
    presentation_type: { choice: "From scratch" },
    offer_name: { text: "The Momentum Method" },
    named_methodology: { text: "The Three-Move Pipeline System" },
    transformation_promise: { text: "stuck and overwhelmed to clear, confident, closing" },
    time_to_result: { text: "8 weeks" },
    audience: { text: "women entrepreneurs, 35-55, tired of inconsistent clients" },
    cta_action: { text: "book a call" },
    brand_primary: { logoNone: true },
    image_links: { skip: true },
    tone: { text: "Inspirational" },
    final_price: { text: "$497" },
    speech_speed_preference: { choice: "Default pace" },
    want_sales_checkout: { choice: "Yes, build the sales page" },
    want_vsl_page: { choice: "No thank you" },
    vsl_page_declined_reason: { text: "we have no hosted video yet" },
    want_email_sequences: { choice: "No thank you" },
    email_sequences_declined_reason: { text: "we already send our own emails" },
    want_motion_graphics: { choice: "No thank you" },
    motion_graphics_declined_reason: { text: "our brand team handles all motion in-house" },
    run_mode: { skip: true },
    ollama_plan: { skip: true },
    deepseek_variant: { skip: true },
    openrouter_model: { skip: true },
    client_notes: { skip: true },
  };

  for (let step = 0; step < 40; step++) {
    if (stage.textContent.includes("Not submitted yet")) break;
    await until(() => promptEl() || stage.textContent.includes("Not submitted yet"), "a screen");
    if (stage.textContent.includes("Not submitted yet")) break;
    const p = promptEl();
    if (!p) { await sleep(25); continue; }
    if (p.innerHTML.includes("ready to")) { primaryBtn().click(); continue; }
    const qid = currentQid();
    assert.ok(qid, "unrecognized screen prompt: " + p.innerHTML);
    const plan = PLAN[qid];
    assert.ok(plan, "no plan for " + qid);
    if (plan.skip) {
      findIn(stage, (e) => e.tagName === "BUTTON" && hasClass(e, "ghost")).click();
    } else if (plan.logoNone) {
      findIn(stage, (e) => e.tagName === "BUTTON" && e.textContent.includes("No logo on file")).click();
      primaryBtn().click();
    } else if (plan.choice) {
      findIn(stage, (e) => e.tagName === "BUTTON" && hasClass(e, "opt") && e.textContent.includes(plan.choice)).click();
      primaryBtn().click();
    } else if (plan.text) {
      const ta = findIn(stage, (e) => e.tagName === "TEXTAREA") || findIn(stage, (e) => e.tagName === "INPUT");
      ta.value = plan.text;
      if (typeof ta.oninput === "function") ta.oninput();
      primaryBtn().click();
    }
    await sleep(10);
  }

  // The completion screen tells the truth: nothing was submitted.
  assert.ok(stage.textContent.includes("Not submitted yet"), "honest heading: " + stage.textContent.slice(0, 200));
  assert.ok(stage.textContent.includes("nothing was submitted"), "honest body copy");
  assert.ok(!stage.textContent.includes("✓ Submitted"), "never claims Submitted");

  // The backup file itself is labeled and carries provenance + canonical shape.
  assert.ok(capturedBlob, "a backup download happened");
  const payload = JSON.parse(await capturedBlob.text());
  assert.equal(payload.submission_status, "NOT_SUBMITTED");
  assert.equal(payload.deck_brief.OFFER_NAME, "The Momentum Method");
  assert.equal(payload.pre_presentation_capture.WANT_SALES_CHECKOUT, "yes");
  assert.equal(payload.pre_presentation_capture.WANT_VSL_PAGE, "no");
  assert.equal(payload.pre_presentation_capture.VSL_PAGE_DECLINED_REASON, "we have no hosted video yet");
  const prov = payload.derived_field_provenance || {};
  assert.deepEqual(Object.keys(prov).sort(),
    ["AUDIENCE_COMPOSITION_NOTE", "DARK_OK", "GROUNDED_CONTENT", "HOOK_SEED", "REPRESENTATION_MIX", "VISUAL_MIX"]);
  assert.equal(prov.HOOK_SEED.source, "transformation_promise");
  assert.equal(prov.VISUAL_MIX.source, "constant");
});
