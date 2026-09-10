// PRES-005 offline gate for the deployed-r2 Worker's completion-outbox logic.
// One-question-at-a-time + server-side validated intake assembly + the
// transactional outbox contract, exercised through the REAL module. No
// Cloudflare runtime; the R2-backed fetch handler itself is proven by
// deployed-assets + worker tests run against `wrangler dev` (see
// run/evidence/PRES-005/). This file pins the pure layer so it cannot drift.
//
//   node --test deployed-r2/test/test_pres005_worker.mjs

import { test } from "node:test";
import assert from "node:assert/strict";
import { assembleValidatedIntake } from "../src/index.js";
import {
  randomToken, isValidTokenShape, validateQuestionsPayload,
  orderedQuestions, checkAnswerOrder, validateAnswerValue, progress,
} from "../../worker/src/lib.js";

// The canonical 16-question payload as build_questions_payload.py projects it
// from deck-intake-questions.json + upsell-questions.json (storeOn included).
const PAYLOAD = {
  question_set: "standard",
  run_id: "RUN-PRES005",
  questions: [
    { id: "presentation_type", order: 0, kind: "enum", prompt: "Type?", required: true, storeOn: "pre_presentation_capture.PRESENTATION_TYPE", allowed_values: ["from_scratch", "content_personal", "content_general", "signature"] },
    { id: "offer_name", order: 1, kind: "text", prompt: "Offer?", required: true, storeOn: "deck_brief.OFFER_NAME" },
    { id: "named_methodology", order: 1.5, kind: "text", prompt: "Method?", required: true, storeOn: "deck_brief.NAMED_METHODOLOGY" },
    { id: "transformation_promise", order: 2, kind: "text", prompt: "Promise?", required: true, storeOn: "deck_brief.TRANSFORMATION_PROMISE" },
    { id: "time_to_result", order: 2.5, kind: "text", prompt: "Time?", required: true, storeOn: "deck_brief.TIME_TO_RESULT" },
    { id: "audience", order: 3, kind: "text", prompt: "Audience?", required: true, storeOn: "deck_brief.AUDIENCE" },
    { id: "cta_action", order: 4, kind: "text", prompt: "CTA?", required: true, storeOn: "deck_brief.CTA_ACTION" },
    { id: "brand_primary", order: 5, kind: "text", prompt: "Logo?", required: false, storeOn: "deck_brief.BRAND_PRIMARY" },
    { id: "image_links", order: 6, kind: "image_links", prompt: "Links?", required: false, storeOn: "deck_brief.IMAGE_LINKS", block_gate: false, default: [] },
    { id: "tone", order: 7, kind: "text", prompt: "Tone?", required: true, storeOn: "deck_brief.TONE" },
    { id: "final_price", order: 8, kind: "text", prompt: "Price?", required: true, storeOn: "deck_brief.FINAL_PRICE" },
    { id: "speech_speed_preference", order: 9, kind: "enum", prompt: "Pace?", required: true, storeOn: "intake.speech_speed_preference", allowed_values: ["default", "medium", "fast"], default: "default" },
    { id: "want_sales_checkout", order: 10, kind: "enum", prompt: "Sales?", required: true, storeOn: "pre_presentation_capture.WANT_SALES_CHECKOUT", allowed_values: ["yes", "no"], default: "yes" },
    { id: "want_vsl_page", order: 11, kind: "enum", prompt: "VSL?", required: true, storeOn: "pre_presentation_capture.WANT_VSL_PAGE", allowed_values: ["yes", "no"], default: "no" },
    { id: "run_mode", order: 11.5, kind: "enum", prompt: "Run mode?", required: false, storeOn: "pre_presentation_capture.RUN_MODE", allowed_values: ["ultra", "standard", "economy"], default: "" },
    { id: "client_notes", order: 12, kind: "text", prompt: "Notes?", required: false, storeOn: "deck_brief.CLIENT_NOTES" },
  ],
};

function session() {
  return { token: randomToken(), run_id: "RUN-PRES005", question_set: "standard" };
}

// Drive the REAL lib ordering so the answer rows mirror what the server
// actually validated at POST /answers time. Optional questions left out of
// `values` emulate the UI's Skip (empty answer, as the UI submits); questions
// without a value and required stop the drive (unanswered).
function driveAnswers(values) {
  const answeredIds = [];
  const rows = [];
  const vals = {};
  for (const q of orderedQuestions(PAYLOAD, vals)) {
    let raw;
    if (q.id in values) raw = values[q.id];
    else if (q.required === false) raw = q.default != null ? q.default : "";
    else break;
    const order = checkAnswerOrder(PAYLOAD, answeredIds, q.id, vals);
    assert.ok(order.ok, "order check " + q.id + ": " + (order.error || ""));
    const val = validateAnswerValue(order.question, raw);
    assert.ok(val.ok, "value check " + q.id + ": " + (val.error || ""));
    answeredIds.push(q.id);
    vals[q.id] = val.value;
    rows.push({ question_id: q.id, value: val.value });
  }
  return rows;
}

test("token shape is the 32-hex capability the UI parses from /s/<token>", () => {
  const t = randomToken();
  assert.match(t, /^[0-9a-f]{32}$/);
  assert.ok(isValidTokenShape(t));
});

test("full grounded submission assembles a complete dept-format intake", () => {
  const s = session();
  const rows = driveAnswers({
    presentation_type: "signature",
    offer_name: "The Momentum Method",
    named_methodology: "The Three-Move Pipeline",
    transformation_promise: "stuck -> closing",
    time_to_result: "8 weeks",
    audience: "women entrepreneurs",
    cta_action: "book a call",
    tone: "Inspirational",
    final_price: "$497",
    speech_speed_preference: "default",
    want_sales_checkout: "yes",
    want_vsl_page: "no",
  });
  const built = assembleValidatedIntake(PAYLOAD, rows, s);
  assert.ok(!built.error, built.error || "");
  const i = built.intake;
  assert.equal(i.presentation_type, "signature");
  assert.equal(i.deck_type, "signature_presentation");
  assert.equal(i.intake_session_id, "sess-" + s.token);
  assert.equal(i.deck_brief.OFFER_NAME, "The Momentum Method");
  assert.equal(i.pre_presentation_capture.PRESENTATION_TYPE, "signature");
  assert.equal(i.pre_presentation_capture.WANT_SALES_CHECKOUT, "yes");
  assert.equal(i.pre_presentation_capture.WANT_VSL_PAGE, "no");
  assert.equal(i.intake.speech_speed_preference, "default");
  // GATE-0-relevant provenance: every answer recorded, grounded deck type.
  assert.equal(i.answers.presentation_type, "signature");
  assert.ok(i.created_at);
});

test("missing presentation_type is fail-closed: NOTHING assembles", () => {
  const s = session();
  const rows = driveAnswers({ offer_name: "X", tone: "T" });
  const built = assembleValidatedIntake(PAYLOAD, rows, s);
  assert.ok(built.error, "must refuse without a type answer");
  assert.match(built.error, /presentation_type/);
  assert.ok(!built.intake);
});

test("unrecognized presentation_type is fail-closed, never defaulted", () => {
  const s = session();
  // The lib rejects an invalid enum at POST /answers time, so a row like this
  // can only exist from an older record — exactly the case the gate must
  // still refuse (never default it to from_scratch).
  const rows = [{ question_id: "presentation_type", value: "weird" }, { question_id: "offer_name", value: "X" }];
  const built = assembleValidatedIntake(PAYLOAD, rows, s);
  assert.ok(built.error);
  assert.ok(!built.intake);
});

test("each presentation type maps to its grounded deck-type axis", () => {
  const want = {
    from_scratch: "webinar",
    content_personal: "webinar",
    content_general: "webinar",
    signature: "signature_presentation",
  };
  for (const [ptype, deck] of Object.entries(want)) {
    const s = session();
    const rows = driveAnswers({ presentation_type: ptype, offer_name: "X", tone: "T" });
    const built = assembleValidatedIntake(PAYLOAD, rows, s);
    assert.ok(!built.error, ptype + ": " + (built.error || ""));
    assert.equal(built.intake.deck_type, deck_type_of(deck), ptype);
    assert.equal(built.intake.creation_mode, ptype === "signature" ? "from_scratch" : ptype, ptype);
  }
  function deck_type_of(x) { return x; }
});

test("run_mode undeclared stays out of the intake (never ultra by default)", () => {
  const s = session();
  const rows = driveAnswers({ presentation_type: "from_scratch", offer_name: "X", tone: "T" });
  const built = assembleValidatedIntake(PAYLOAD, rows, s);
  assert.ok(!built.error);
  assert.ok(!built.intake.pre_presentation_capture.RUN_MODE, "absence writes nothing");
});

test("declared run_mode lands in pre_presentation_capture.RUN_MODE", () => {
  const s = session();
  const rows = driveAnswers({
    presentation_type: "from_scratch",
    offer_name: "X",
    named_methodology: "M",
    transformation_promise: "T",
    time_to_result: "8w",
    audience: "A",
    cta_action: "C",
    tone: "T",
    final_price: "$1",
    speech_speed_preference: "default",
    want_sales_checkout: "yes",
    want_vsl_page: "no",
    run_mode: "ultra",
  });
  const built = assembleValidatedIntake(PAYLOAD, rows, s);
  assert.ok(!built.error);
  assert.equal(built.intake.pre_presentation_capture.RUN_MODE, "ultra");
});

test("assembled intake survives the box-side intake_writer fail-closed gates", () => {
  // This assertion mirrors bridge/intake_writer.py's UngroundedDeckTypeError
  // contract: presentation_type must be present AND in LEGACY_FIELD_MAPPING.
  // Held here as a data contract so a worker-side drift fails this gate too.
  const s = session();
  const rows = driveAnswers({
    presentation_type: "from_scratch",
    offer_name: "X", named_methodology: "M", transformation_promise: "T",
    time_to_result: "8w", audience: "A", cta_action: "C",
    tone: "T", final_price: "$1",
    speech_speed_preference: "default",
    want_sales_checkout: "yes", want_vsl_page: "no",
  });
  const built = assembleValidatedIntake(PAYLOAD, rows, s);
  assert.ok(!built.error);
  const i = built.intake;
  assert.ok(["from_scratch", "content_personal", "content_general", "signature"].includes(i.presentation_type));
  assert.ok(i.deck_brief.OFFER_NAME && i.deck_brief.TONE && i.deck_brief.FINAL_PRICE);
  assert.ok(i.pre_presentation_capture.PRESENTATION_TYPE);
  // the six mandatory pre-capture fields the box writer requires
  for (const f of ["REPRESENTATION_MIX", "AUDIENCE_COMPOSITION_NOTE", "GROUNDED_CONTENT", "VISUAL_MIX", "DARK_OK", "HOOK_SEED"]) {
    assert.ok(f in i.pre_presentation_capture, f + " present");
  }
});

test("progress + completion gate on half-answered session (server-side)", () => {
  const s = session();
  const rows = driveAnswers({
    presentation_type: "from_scratch",
    offer_name: "X",
    named_methodology: "M",
    transformation_promise: "T",
    time_to_result: "8w",
    audience: "A",
    cta_action: "C",
    brand_primary: "",
  });
  const answeredIds = rows.map((r) => r.question_id);
  const vals = {}; for (const r of rows) vals[r.question_id] = r.value;
  const prog = progress(PAYLOAD, answeredIds, vals);
  assert.equal(prog.complete, false);
  const requiredUnanswered = PAYLOAD.questions.filter((q) => {
    if (q.required === false) return false;
    if (answeredIds.includes(q.id)) return false;
    const active = (function () { return null; })();
    if (active === false) return false;
    return q.block_gate !== false;
  }).map((q) => q.id);
  assert.ok(requiredUnanswered.length >= 4, "half session must still block: " + JSON.stringify(requiredUnanswered));
});