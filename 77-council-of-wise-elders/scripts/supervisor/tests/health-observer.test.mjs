import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { HEALTH_SCHEMA, nextHealthTickAt, observeHealth } from "../health-observer.mjs";
import { defaultPolicy } from "../policy.mjs";

const policy = defaultPolicy();
const NOW = 5_000_000;
const here = dirname(fileURLToPath(import.meta.url));

function observe(overrides = {}) {
  return observeHealth({
    now_ms: NOW,
    policy,
    heartbeat: { last_seen_ms: NOW - 5_000 },
    sweep: { running_started_at_ms: null, gate: null },
    leader: { lease_expires_at_ms: NOW + 30_000 },
    ...overrides,
  });
}

test("a clean snapshot is HEALTHY and makes zero LLM calls", () => {
  const health = observe();
  assert.equal(health.schema, HEALTH_SCHEMA);
  assert.equal(health.verdict, "HEALTHY");
  assert.deepEqual(health.reasons, ["ALL_SIGNALS_WITHIN_POLICY"]);
  assert.equal(health.llm_calls, 0);
});

test("the observer is deterministic for identical injected time and snapshot", () => {
  assert.deepEqual(observe(), observe());
  assert.deepEqual(observe({ now_ms: NOW + 1 }), observe({ now_ms: NOW + 1 }));
});

test("heartbeat ages into SUSPECT after one tick and DEGRADED at 180s", () => {
  assert.equal(observe({ heartbeat: { last_seen_ms: NOW - 60_000 } }).verdict, "HEALTHY");
  assert.equal(observe({ heartbeat: { last_seen_ms: NOW - 60_001 } }).verdict, "SUSPECT");
  assert.equal(observe({ heartbeat: { last_seen_ms: NOW - 180_000 } }).verdict, "SUSPECT");
  const stale = observe({ heartbeat: { last_seen_ms: NOW - 180_001 } });
  assert.equal(stale.verdict, "DEGRADED");
  assert.ok(stale.reasons.includes("HEARTBEAT_STALE"));

  const missing = observe({ heartbeat: { last_seen_ms: null } });
  assert.equal(missing.verdict, "DEGRADED");
  assert.ok(missing.reasons.includes("HEARTBEAT_MISSING"));
});

test("sweeps over 120s and slots past due+30s are DEGRADED", () => {
  const running = observe({ sweep: { running_started_at_ms: NOW - 120_001, gate: null } });
  assert.equal(running.verdict, "DEGRADED");
  assert.ok(running.reasons.includes("SWEEP_RUNTIME_EXCEEDED"));

  const onTime = observe({ sweep: { running_started_at_ms: NOW - 120_000, gate: { overdue_by_ms: 30_000 } } });
  assert.equal(onTime.verdict, "HEALTHY");

  const overdue = observe({ sweep: { running_started_at_ms: null, gate: { overdue_by_ms: 30_001 } } });
  assert.equal(overdue.verdict, "DEGRADED");
  assert.ok(overdue.reasons.includes("SWEEP_UNHEALTHY_GATE_EXCEEDED"));
});

test("an expired leader lease is DEGRADED", () => {
  const expired = observe({ leader: { lease_expires_at_ms: NOW } });
  assert.equal(expired.verdict, "DEGRADED");
  assert.ok(expired.reasons.includes("LEADER_LEASE_EXPIRED"));
  assert.equal(observe({ leader: { is_leader: false } }).verdict, "DEGRADED");
});

test("health ticks are 60s and do not depend on observation duration", () => {
  assert.equal(policy.health_tick_seconds, 60);
  assert.equal(nextHealthTickAt({ now_ms: NOW, policy }), NOW + 60_000);
  assert.equal(nextHealthTickAt({ now_ms: NOW + 59_999, policy }), NOW + 119_999);
});

test("the health observer module contains no model, network or clock call", () => {
  const source = readFileSync(join(here, "..", "health-observer.mjs"), "utf8");
  for (const forbidden of ["fetch(", "http://", "https://", "import(\"node:http", "import \"node:http", "Date.now", "Math.random", "anthropic", "openai"]) {
    assert.equal(source.includes(forbidden), false, `health observer must not use ${forbidden}`);
  }
});
