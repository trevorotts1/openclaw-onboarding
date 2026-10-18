import assert from "node:assert/strict";
import { test } from "node:test";
import {
  STAFFING_SCHEMA,
  compareStaffing,
  isUnderfillExceptionActive,
} from "../staffing.mjs";

const NOW = 2_000_000;
const NEXT_SWEEP = NOW + 90_000;

test("effective count is clamped by the policy cap", () => {
  const result = compareStaffing({
    now_ms: NOW,
    next_sweep_due_at_ms: NEXT_SWEEP,
    suggested: 12,
    cap: 10,
    actual: 10,
  });
  assert.equal(result.schema, STAFFING_SCHEMA);
  assert.equal(result.suggested, 12);
  assert.equal(result.effective, 10);
  assert.equal(result.actual, 10);
  assert.equal(result.shortfall, 0);
  assert.equal(result.verdict, "ADEQUATE");
  assert.equal(result.underfill, null);
});

test("underfill carries a reason and expires no later than the next sweep", () => {
  const result = compareStaffing({
    now_ms: NOW,
    next_sweep_due_at_ms: NEXT_SWEEP,
    suggested: 12,
    cap: 10,
    actual: 4,
    reason: "AGENTS_UNRESPONSIVE",
    ttl_ms: 10 * 60 * 1000,
  });
  assert.equal(result.verdict, "UNDERFILLED");
  assert.equal(result.shortfall, 6);
  const exception = result.underfill;
  assert.equal(exception.kind, "UNDERFILL");
  assert.equal(exception.reason, "AGENTS_UNRESPONSIVE");
  assert.equal(exception.opened_at_ms, NOW);
  assert.ok(exception.expires_at_ms <= NEXT_SWEEP);
  assert.equal(exception.expires_at_ms, NEXT_SWEEP);

  // Active the millisecond before the sweep, inactive AT the sweep.
  assert.equal(isUnderfillExceptionActive(exception, NEXT_SWEEP - 1), true);
  assert.equal(isUnderfillExceptionActive(exception, NEXT_SWEEP), false);
  assert.equal(isUnderfillExceptionActive(exception, NEXT_SWEEP + 1), false);
});

test("a short ttl still expires before the next sweep", () => {
  const result = compareStaffing({
    now_ms: NOW,
    next_sweep_due_at_ms: NEXT_SWEEP,
    suggested: 5,
    actual: 3,
    reason: "TEMPORARY",
    ttl_ms: 30_000,
  });
  assert.equal(result.underfill.expires_at_ms, NOW + 30_000);
  assert.equal(isUnderfillExceptionActive(result.underfill, NOW + 30_000), false);
});

test("an underfill without a reason is refused", () => {
  assert.throws(
    () =>
      compareStaffing({
        now_ms: NOW,
        next_sweep_due_at_ms: NEXT_SWEEP,
        suggested: 5,
        actual: 1,
        reason: "  ",
      }),
    /non-empty reason/,
  );
});

test("the next sweep due time is required, so expiry cannot be unbounded", () => {
  assert.throws(
    () => compareStaffing({ now_ms: NOW, suggested: 5, actual: 1, reason: "x" }),
    /next_sweep_due_at_ms/,
  );
});
