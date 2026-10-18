// QC-backlog trigger for the Hybrid Council of Wise Elders supervisor
// (HYB-03). The supervisor raises an incident when either:
//   * the oldest unassigned receipt has been waiting MORE than 600s, or
//   * MORE than 3 units are waiting (i.e. 4 or more).
//
// Pure over injected time. Assigned receipts never contribute to the backlog.
export const QC_BACKLOG_SCHEMA = "wise-elders.hybrid-supervisor-qc-backlog/v1";
export const QC_OLDEST_UNASSIGNED_LIMIT_MS = 600_000;
export const QC_WAITING_LIMIT = 3;

function requireInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer, got ${String(value)}`);
  }
}

function requireReceipt(receipt, index) {
  if (!receipt || typeof receipt !== "object") {
    throw new TypeError(`receipts[${index}] must be an object`);
  }
  if (typeof receipt.id !== "string" || receipt.id.length === 0) {
    throw new TypeError(`receipts[${index}].id must be a non-empty string`);
  }
  requireInteger(receipt.received_at_ms, `receipts[${index}].received_at_ms`);
  if (receipt.assigned_at_ms !== null && receipt.assigned_at_ms !== undefined) {
    requireInteger(receipt.assigned_at_ms, `receipts[${index}].assigned_at_ms`);
  }
  return receipt;
}

export function evaluateQcBacklog({ now_ms, receipts = [] } = {}) {
  requireInteger(now_ms, "now_ms");
  if (!Array.isArray(receipts)) {
    throw new TypeError("receipts must be an array");
  }

  const waiting = receipts
    .map(requireReceipt)
    .filter((receipt) => receipt.assigned_at_ms === null || receipt.assigned_at_ms === undefined);

  let oldestReceivedAtMs = null;
  for (const receipt of waiting) {
    if (oldestReceivedAtMs === null || receipt.received_at_ms < oldestReceivedAtMs) {
      oldestReceivedAtMs = receipt.received_at_ms;
    }
  }
  const oldestAgeMs = oldestReceivedAtMs === null ? null : now_ms - oldestReceivedAtMs;

  const ageExceeded = oldestAgeMs !== null && oldestAgeMs > QC_OLDEST_UNASSIGNED_LIMIT_MS;
  const countExceeded = waiting.length > QC_WAITING_LIMIT;
  const reasons = [];
  if (ageExceeded) reasons.push("OLDEST_UNASSIGNED_OVER_600S");
  if (countExceeded) reasons.push("MORE_THAN_3_WAITING");

  return Object.freeze({
    schema: QC_BACKLOG_SCHEMA,
    evaluated_at_ms: now_ms,
    waiting_count: waiting.length,
    assigned_count: receipts.length - waiting.length,
    oldest_unassigned_received_at_ms: oldestReceivedAtMs,
    oldest_unassigned_age_ms: oldestAgeMs,
    oldest_limit_ms: QC_OLDEST_UNASSIGNED_LIMIT_MS,
    waiting_limit: QC_WAITING_LIMIT,
    age_exceeded: ageExceeded,
    count_exceeded: countExceeded,
    triggered: ageExceeded || countExceeded,
    trigger_reasons: Object.freeze(reasons),
  });
}
