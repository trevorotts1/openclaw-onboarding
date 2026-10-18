import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  POLICY_FIELDS,
  POLICY_SCHEMA_ID,
  POLICY_SCHEMA_PATH,
  defaultPolicy,
  readPolicySchema,
  validatePolicy,
} from "../policy.mjs";
import { NATIVE_ADAPTER_BINDING } from "../supervisor.mjs";

const EXPECTED = Object.freeze({
  full_sweep_interval_seconds: 600,
  health_tick_seconds: 60,
  heartbeat_suspect_after_seconds: 180,
  max_concurrent_workflows: 50,
  max_agents_per_workflow: 10,
  max_total_agents: 500,
  require_independent_non_author_review: true,
  require_exact_head_checks: true,
  require_atomic_expected_head_merge_guard: true,
  standing_repository_merge_authorized: true,
  vercel_required: false,
  cloudflare_build_required: true,
  customer_remote_access_opt_in: true,
  explicit_stop_disables_automatic_engineering_restart: true,
});

test("policy schema file is versioned wise-elders.hybrid-supervisor-policy/v2", () => {
  const raw = JSON.parse(readFileSync(POLICY_SCHEMA_PATH, "utf8"));
  assert.equal(raw.$id, "wise-elders.hybrid-supervisor-policy/v2");
  assert.equal(raw.$id, POLICY_SCHEMA_ID);
  assert.equal(raw.properties.schema.const, POLICY_SCHEMA_ID);
});

test("policy carries document_version 2.4 and stays TEMPLATE_NOT_BOUND", () => {
  const policy = defaultPolicy();
  assert.equal(policy.document_version, "2.4");
  assert.equal(policy.binding_status, "TEMPLATE_NOT_BOUND");
});

test("policy carries the exact v2.4 embedded field set and values", () => {
  const policy = defaultPolicy();
  assert.deepEqual([...POLICY_FIELDS].sort(), Object.keys(EXPECTED).sort());
  for (const [key, value] of Object.entries(EXPECTED)) {
    assert.equal(policy[key], value, key);
  }
  // No extra governed field may creep in unseen.
  assert.deepEqual(
    Object.keys(policy).sort(),
    ["binding_status", "document_version", "schema", ...Object.keys(EXPECTED)].sort(),
  );
});

test("the schema is the single source of truth for the embedded example", () => {
  const schema = readPolicySchema();
  for (const [key, value] of Object.entries(schema.properties)) {
    const rule = value;
    if (Object.hasOwn(rule, "const")) {
      assert.equal(defaultPolicy()[key], rule.const, `${key} must come from its const`);
    }
  }
});

test("validatePolicy rejects drift, unknown fields and a bound template", () => {
  const policy = defaultPolicy();
  assert.deepEqual(validatePolicy(policy), { ok: true, errors: [] });

  assert.equal(validatePolicy({ ...policy, full_sweep_interval_seconds: 300 }).ok, false);
  assert.equal(validatePolicy({ ...policy, binding_status: "BOUND" }).ok, false);
  assert.equal(validatePolicy({ ...policy, unexpected_field: true }).ok, false);
  const missing = { ...policy };
  delete missing.max_total_agents;
  assert.equal(validatePolicy(missing).ok, false);
});

test("native-adapter binding is an explicit UNKNOWN in this unit", () => {
  assert.equal(NATIVE_ADAPTER_BINDING.status, "UNKNOWN");
  assert.equal(NATIVE_ADAPTER_BINDING.bound, false);
  assert.match(NATIVE_ADAPTER_BINDING.reason, /later unit/);
});
