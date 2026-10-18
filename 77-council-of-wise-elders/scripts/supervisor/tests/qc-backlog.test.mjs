import assert from "node:assert/strict";
import { test } from "node:test";
import {
  QC_BACKLOG_SCHEMA,
  QC_OLDEST_UNASSIGNED_LIMIT_MS,
  QC_WAITING_LIMIT,
  evaluateQcBacklog,
} from "../qc-backlog.mjs";

const NOW = 4_000_000;

function receipt(id, ageMs, assignedAtMs = null) {
  return { id, received_at_ms: NOW - ageMs, assigned_at_ms: assignedAtMs };
}

test("the limits are 600s and more-than-3 waiting", () => {
  assert.equal(QC_OLDEST_UNASSIGNED_LIMIT_MS, 600_000);
  assert.equal(QC_WAITING_LIMIT, 3);
});

test("an empty backlog never triggers", () => {
  const result = evaluateQcBacklog({ now_ms: NOW, receipts: [] });
  assert.equal(result.schema, QC_BACKLOG_SCHEMA);
  assert.equal(result.triggered, false);
  assert.deepEqual(result.trigger_reasons, []);
  assert.equal(result.oldest_unassigned_age_ms, null);
});

test("age trigger is strict: 600s does not, 601s does", () => {
  const atLimit = evaluateQcBacklog({ now_ms: NOW, receipts: [receipt("r1", 600_000)] });
  assert.equal(atLimit.oldest_unassigned_age_ms, 600_000);
  assert.equal(atLimit.age_exceeded, false);
  assert.equal(atLimit.triggered, false);

  const overLimit = evaluateQcBacklog({ now_ms: NOW, receipts: [receipt("r1", 600_001)] });
  assert.equal(overLimit.age_exceeded, true);
  assert.equal(overLimit.triggered, true);
  assert.deepEqual(overLimit.trigger_reasons, ["OLDEST_UNASSIGNED_OVER_600S"]);
});

test("count trigger is strict: 3 waiting does not, 4 does", () => {
  const three = evaluateQcBacklog({
    now_ms: NOW,
    receipts: [receipt("r1", 1), receipt("r2", 2), receipt("r3", 3)],
  });
  assert.equal(three.waiting_count, 3);
  assert.equal(three.count_exceeded, false);
  assert.equal(three.triggered, false);

  const four = evaluateQcBacklog({
    now_ms: NOW,
    receipts: [receipt("r1", 1), receipt("r2", 2), receipt("r3", 3), receipt("r4", 4)],
  });
  assert.equal(four.waiting_count, 4);
  assert.equal(four.count_exceeded, true);
  assert.deepEqual(four.trigger_reasons, ["MORE_THAN_3_WAITING"]);
});

test("assigned receipts are excluded from backlog pressure", () => {
  const result = evaluateQcBacklog({
    now_ms: NOW,
    receipts: [
      receipt("old-assigned", 900_000, NOW - 1),
      receipt("new", 1),
      receipt("newer", 2),
      receipt("newest", 3),
      receipt("still-new", 4),
    ],
  });
  assert.equal(result.waiting_count, 4);
  assert.equal(result.assigned_count, 1);
  assert.equal(result.oldest_unassigned_age_ms, 4);
  assert.equal(result.count_exceeded, true);
  assert.equal(result.age_exceeded, false);
});

test("both triggers report both reasons", () => {
  const result = evaluateQcBacklog({
    now_ms: NOW,
    receipts: [receipt("r1", 601_000), receipt("r2", 1), receipt("r3", 2), receipt("r4", 3)],
  });
  assert.equal(result.triggered, true);
  assert.deepEqual(result.trigger_reasons, [
    "OLDEST_UNASSIGNED_OVER_600S",
    "MORE_THAN_3_WAITING",
  ]);
});
