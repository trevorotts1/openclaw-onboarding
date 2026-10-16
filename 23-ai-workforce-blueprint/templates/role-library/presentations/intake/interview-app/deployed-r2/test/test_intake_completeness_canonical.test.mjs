// Item 13 (S3) regression gate: POST /api/intake validates against the
// CANONICAL record shape. The upsell flags WANT_SALES_CHECKOUT and
// WANT_VSL_PAGE live in pre_presentation_capture (the PRES-006 contract,
// ANSWER_STORE_TARGETS, the session assembler, the hosted page, and the
// box-side writer all agree). The completeness gate used to read them out
// of deck_brief, so a canonically shaped direct POST always 422'd on two
// fields that were present in their canonical section.
//
//   node --test deployed-r2/test/test_intake_completeness_canonical.test.mjs

import { test } from "node:test";
import assert from "node:assert/strict";
import { R2Shim, WorkerHarness } from "../../test/pres024_env.mjs";
import worker from "../src/index.js";

function makeHarness() {
  const env = { STORE: new R2Shim(), INTAKE_ADMIN_TOKEN: "admin-tok" };
  return new WorkerHarness(worker, env);
}

function canonicalIntake() {
  return {
    interview_confirmed: true,
    source: "presentation-interview-app",
    intake_session_id: "intake-canonical-1",
    company_id: "acme",
    installation_id: "install-test",
    presentation_id: "presentation-test",
    run_id: "run-canonical-1",
    presentation_type: "from_scratch",
    deck_brief: {
      OFFER_NAME: "The Momentum Method",
      NAMED_METHODOLOGY: "Three-Move Pipeline",
      TRANSFORMATION_PROMISE: "stuck to closing",
      TIME_TO_RESULT: "8 weeks",
      AUDIENCE: "women entrepreneurs 35-55",
      CTA_ACTION: "book a call",
      TONE: "Inspirational",
      FINAL_PRICE: "$497",
    },
    pre_presentation_capture: {
      PRESENTATION_TYPE: "from_scratch",
      WANT_SALES_CHECKOUT: "yes",
      WANT_VSL_PAGE: "no",
    },
    intake: {},
    answers: {},
  };
}

test("canonical shape: upsell flags in pre_presentation_capture are accepted (201)", async () => {
  const h = makeHarness();
  const res = await h.handle("POST", "/api/intake", {
    token: "admin-tok",
    body: { file_name: "intake.json", intake: canonicalIntake() },
  });
  assert.equal(res.status, 201, "canonical record must store: " + JSON.stringify(res.body));
  assert.equal(res.body.status, "stored");
});

test("missing upsell flag 422s naming the canonical pre_presentation_capture path", async () => {
  const h = makeHarness();
  const intake = canonicalIntake();
  delete intake.pre_presentation_capture.WANT_VSL_PAGE;
  const res = await h.handle("POST", "/api/intake", {
    token: "admin-tok",
    body: { file_name: "intake.json", intake },
  });
  assert.equal(res.status, 422, JSON.stringify(res.body));
  assert.ok(res.body.missing.includes("pre_presentation_capture.WANT_VSL_PAGE"),
    "missing must name the canonical path: " + JSON.stringify(res.body.missing));
  assert.ok(!res.body.missing.some((m) => m.startsWith("deck_brief.WANT_")),
    "missing must never name a deck_brief upsell path: " + JSON.stringify(res.body.missing));
});

test("upsell flags misplaced in deck_brief do not satisfy the gate", async () => {
  const h = makeHarness();
  const intake = canonicalIntake();
  intake.deck_brief.WANT_SALES_CHECKOUT = intake.pre_presentation_capture.WANT_SALES_CHECKOUT;
  intake.deck_brief.WANT_VSL_PAGE = intake.pre_presentation_capture.WANT_VSL_PAGE;
  delete intake.pre_presentation_capture.WANT_SALES_CHECKOUT;
  delete intake.pre_presentation_capture.WANT_VSL_PAGE;
  const res = await h.handle("POST", "/api/intake", {
    token: "admin-tok",
    body: { file_name: "intake.json", intake },
  });
  assert.equal(res.status, 422, JSON.stringify(res.body));
  assert.ok(res.body.missing.includes("pre_presentation_capture.WANT_SALES_CHECKOUT"));
  assert.ok(res.body.missing.includes("pre_presentation_capture.WANT_VSL_PAGE"));
});
