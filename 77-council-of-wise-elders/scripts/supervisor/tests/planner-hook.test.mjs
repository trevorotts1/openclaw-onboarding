import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  FULL_SWEEP_INTERVAL_MS,
  PLANNER_HOOK_SCHEMA,
  completeFullSweep,
  createFullSweepHook,
  nextFullSweepDueAt,
  planFullSweep,
} from "../planner-hook.mjs";

const ANCHOR = 1_000_000;
const here = dirname(fileURLToPath(import.meta.url));

test("the hook is pinned to the fixed ten-minute cadence", () => {
  const hook = createFullSweepHook({ anchor_ms: ANCHOR });
  assert.equal(hook.schema, PLANNER_HOOK_SCHEMA);
  assert.equal(hook.cadence_ms, FULL_SWEEP_INTERVAL_MS);
  assert.equal(FULL_SWEEP_INTERVAL_MS, 600_000);
  assert.throws(() => createFullSweepHook({ anchor_ms: ANCHOR, cadence_ms: 300_000 }), /cadence/);
});

test("sweep due times stay on the fixed anchor across irregular lateness", () => {
  let hook = createFullSweepHook({ anchor_ms: ANCHOR });
  const lateness = [0, 1, 29_999, 30_001, 599_999, 600_000, 17];
  const dueTimes = [];
  for (let cycle = 0; cycle < 20; cycle += 1) {
    const now = hook.planner_state.next_due_at_ms + lateness[cycle % lateness.length];
    const planned = planFullSweep(hook, { now_ms: now });
    assert.equal(planned.decision.kind, "SCHEDULED");
    dueTimes.push(planned.decision.due_at_ms);
    assert.equal((planned.decision.due_at_ms - ANCHOR) % 600_000, 0);
    hook = completeFullSweep(planned.hook, {
      kind: planned.decision.kind,
      finished_at_ms: now + 12_345 * (cycle % 5),
    }).hook;
  }
  for (let index = 1; index < dueTimes.length; index += 1) {
    assert.ok(dueTimes[index] > dueTimes[index - 1]);
    assert.equal((dueTimes[index] - dueTimes[index - 1]) % 600_000, 0);
  }
  assert.equal((hook.planner_state.next_due_at_ms - ANCHOR) % 600_000, 0);
});

test("an EXTRA sweep never consumes or moves the scheduled slot", () => {
  const hook = createFullSweepHook({ anchor_ms: ANCHOR });
  const planned = planFullSweep(hook, { now_ms: ANCHOR - 1, extra_requested: true });
  assert.equal(planned.decision.kind, "EXTRA");
  assert.equal(planned.decision.consumes_scheduled_slot, false);
  assert.equal(planned.hook.planner_state.next_due_at_ms, ANCHOR);
});

test("nextFullSweepDueAt is anchor-derived, not finish-derived", () => {
  const hook = createFullSweepHook({ anchor_ms: ANCHOR });
  assert.equal(nextFullSweepDueAt(hook, ANCHOR - 1), ANCHOR);
  assert.equal(nextFullSweepDueAt(hook, ANCHOR), ANCHOR);
  assert.equal(nextFullSweepDueAt(hook, ANCHOR + 1), ANCHOR + 600_000);
  assert.equal(nextFullSweepDueAt(hook, ANCHOR + 1_900_000), ANCHOR + 2_400_000);
});

test("the planner stays pure: no clocks and no timers in either planner module", () => {
  for (const file of ["planner-hook.mjs", "sweep-planner.mjs"]) {
    const source = readFileSync(join(here, "..", file), "utf8");
    // Strip comments so the purity CONTRACT text does not count as a clock call.
    const code = source
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
    for (const forbidden of ["Date.now", "performance.now", "setTimeout", "setInterval", "new Date"]) {
      assert.equal(code.includes(forbidden), false, `${file} must not use ${forbidden}`);
    }
    assert.equal(code.includes("node:fs"), false, `${file} must not touch the filesystem`);
  }
});
