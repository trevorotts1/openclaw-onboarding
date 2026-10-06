// PRES-009 — tenant identity + isolation tests (pure helpers, no runtime).
//   node --test test/test_tenant.mjs

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  isValidOpaqueId,
  opaqueIdError,
  mintRunId,
  mintIntakeSessionId,
  questionSchemaFingerprint,
  tenantFromRequest,
  planLegacySessionMigration,
  planLegacyIntakeMigration,
} from "../worker/src/tenant.js";

// ── opaque ids: reject invalid, never sanitize ──────────────────────────────

test("isValidOpaqueId accepts well-formed ids", () => {
  assert.ok(isValidOpaqueId("company-a"));
  assert.ok(isValidOpaqueId("run-abc123"));
  assert.ok(isValidOpaqueId("A1.2_3-x"));
  assert.ok(isValidOpaqueId("ab1")); // minimum 3
});

test("isValidOpaqueId REJECTS traversal, separators, empty, control chars", () => {
  assert.ok(!isValidOpaqueId(""));
  assert.ok(!isValidOpaqueId("ab")); // too short
  assert.ok(!isValidOpaqueId("a".repeat(65))); // too long
  assert.ok(!isValidOpaqueId("../etc"));
  assert.ok(!isValidOpaqueId("a/../b"));
  assert.ok(!isValidOpaqueId(".."));
  assert.ok(!isValidOpaqueId("a/b"));
  assert.ok(!isValidOpaqueId("a\\b"));
  assert.ok(!isValidOpaqueId("/abs"));
  assert.ok(!isValidOpaqueId("a\0b"));
  assert.ok(!isValidOpaqueId(" leading"));
  assert.ok(!isValidOpaqueId("-leading")); // must start alphanumeric
  assert.ok(!isValidOpaqueId(".hidden"));
  assert.ok(!isValidOpaqueId(123));
  assert.ok(!isValidOpaqueId(null));
  assert.ok(!isValidOpaqueId(undefined));
  assert.ok(!isValidOpaqueId({}));
});

test("opaqueIdError names the field and never returns null for invalid ids", () => {
  const err = opaqueIdError("company_id", "../escape");
  assert.ok(typeof err === "string");
  assert.match(err, /company_id/);
  assert.equal(opaqueIdError("company_id", "ok-id"), null);
});

// ── server-minted ids ───────────────────────────────────────────────────────

test("mintRunId/mintIntakeSessionId are unique, valid opaque ids with prefixes", () => {
  const a = mintRunId();
  const b = mintRunId();
  assert.notEqual(a, b);
  assert.ok(a.startsWith("run-"));
  assert.ok(isValidOpaqueId(a));
  const s1 = mintIntakeSessionId();
  const s2 = mintIntakeSessionId();
  assert.notEqual(s1, s2);
  assert.ok(s1.startsWith("isn-"));
  assert.ok(isValidOpaqueId(s1));
});

// ── schema fingerprint: wording-free, structure-sensitive ───────────────────

test("questionSchemaFingerprint ignores prompt wording, is sensitive to ids/kinds/order/required", () => {
  const base = {
    question_set: "standard",
    questions: [
      { id: "offer", order: 1, prompt: "Your offer?", kind: "text", required: true },
      { id: "tone", order: 2, prompt: "Tone?", kind: "text", required: true },
    ],
  };
  const reworded = {
    question_set: "standard",
    questions: [
      { id: "offer", order: 1, prompt: "Tell us your offer please", kind: "text", required: true },
      { id: "tone", order: 2, prompt: "How should it sound?", kind: "text", required: true },
    ],
  };
  assert.equal(questionSchemaFingerprint(base), questionSchemaFingerprint(reworded));

  const reordered = { question_set: "standard", questions: [base.questions[1], base.questions[0]] };
  assert.notEqual(questionSchemaFingerprint(base), questionSchemaFingerprint(reordered));

  const added = { question_set: "standard", questions: [...base.questions, { id: "extra", order: 3, prompt: "?" }] };
  assert.notEqual(questionSchemaFingerprint(base), questionSchemaFingerprint(added));

  const kindChanged = { question_set: "standard", questions: [{ ...base.questions[0], kind: "enum" }, base.questions[1]] };
  assert.notEqual(questionSchemaFingerprint(base), questionSchemaFingerprint(kindChanged));
});

// ── tenant extraction: precise rejections ───────────────────────────────────

test("tenantFromRequest extracts valid tuple; lists per-field errors for invalid", () => {
  const ok = tenantFromRequest({ company_id: "co-1", installation_id: "inst-1", presentation_id: "pres-1" });
  assert.ok(ok.ok);
  assert.deepEqual(ok.tenant, { company_id: "co-1", installation_id: "inst-1", presentation_id: "pres-1" });

  const bad = tenantFromRequest({ company_id: "../x", installation_id: "", presentation_id: 7 });
  assert.ok(!bad.ok);
  assert.equal(bad.errors.length, 3);
  assert.match(bad.errors[0], /company_id/);
  assert.match(bad.errors[1], /installation_id/);
  assert.match(bad.errors[2], /presentation_id/);
});

// ── legacy session migration: unambiguous backfills, ambiguous quarantines ──

test("planLegacySessionMigration backfills single-box run_ids and quarantines multi-box reuse", () => {
  const rows = [
    // run-1 minted twice by the SAME box -> unambiguous
    { token: "t1", run_id: "run-1", box_id: "box-a" },
    { token: "t2", run_id: "run-1", box_id: "box-a" },
    // run-2 seen under TWO boxes -> the PRES-009 collision itself
    { token: "t3", run_id: "run-2", box_id: "box-a" },
    { token: "t4", run_id: "run-2", box_id: "box-b" },
    // run-3 single box but garbage box id -> cannot attribute
    { token: "t5", run_id: "run-3", box_id: "../weird" },
  ];
  const plan = planLegacySessionMigration(rows);
  assert.deepEqual(plan.backfills.map((b) => b.token).sort(), ["t1", "t2"]);
  assert.ok(plan.backfills.every((b) => b.installation_id === "box-a"));
  const quarantinedTokens = plan.quarantined.map((q) => q.token).sort();
  assert.deepEqual(quarantinedTokens, ["t3", "t4", "t5"]);
  assert.ok(plan.quarantined.every((q) => typeof q.reason === "string" && q.reason.length > 0));
});

test("planLegacyIntakeMigration backfills only rows carrying a full valid tuple", () => {
  const good = {
    session_id: "isn-1",
    intake_json: JSON.stringify({
      company_id: "co-1", installation_id: "in-1", presentation_id: "p-1", run_id: "run-1",
    }),
  };
  const missing = { session_id: "isn-2", intake_json: JSON.stringify({ company_id: "co-1" }) };
  const corrupt = { session_id: "isn-3", intake_json: "{not json" };
  const traversal = {
    session_id: "isn-4",
    intake_json: JSON.stringify({
      company_id: "co-1", installation_id: "../../etc", presentation_id: "p-1", run_id: "run-1",
    }),
  };
  const plan = planLegacyIntakeMigration([good, missing, corrupt, traversal]);
  assert.deepEqual(plan.backfills.map((b) => b.session_id), ["isn-1"]);
  assert.deepEqual(plan.quarantined.map((q) => q.session_id).sort(), ["isn-2", "isn-3", "isn-4"]);
  assert.ok(plan.quarantined.every((q) => q.remediation && q.remediation.length > 0));
});