// Staffing comparison for the Hybrid Council of Wise Elders supervisor
// (HYB-03). Suggested, effective and actual counts are compared, and an
// underfill becomes an explicit exception carrying a reason and an expiry that
// can never outlive the next sweep.
//
// Pure: the caller injects `now_ms` and the next sweep due time.
export const STAFFING_SCHEMA = "wise-elders.hybrid-supervisor-staffing/v1";
export const UNDERFILL_DEFAULT_TTL_MS = 600_000;

function requireInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer, got ${String(value)}`);
  }
}

/**
 * compareStaffing({ now_ms, next_sweep_due_at_ms, suggested, actual, cap, reason, ttl_ms })
 *
 * effective = min(suggested, cap) — the cap is the policy ceiling (for example
 * max_total_agents). An exception is only raised when actual < effective, and
 * it always carries a reason. Its expiry is min(now + ttl, next sweep due), so
 * it cannot survive to hide the same underfill across a sweep boundary.
 */
export function compareStaffing({
  now_ms,
  next_sweep_due_at_ms,
  suggested,
  actual,
  cap = suggested,
  reason = "STAFFING_BELOW_EFFECTIVE",
  ttl_ms = UNDERFILL_DEFAULT_TTL_MS,
}) {
  requireInteger(now_ms, "now_ms");
  requireInteger(next_sweep_due_at_ms, "next_sweep_due_at_ms");
  requireInteger(suggested, "suggested");
  requireInteger(actual, "actual");
  requireInteger(cap, "cap");
  requireInteger(ttl_ms, "ttl_ms");

  const effective = Math.min(suggested, cap);
  const shortfall = Math.max(0, effective - actual);

  let underfill = null;
  if (shortfall > 0) {
    if (typeof reason !== "string" || reason.trim().length === 0) {
      throw new TypeError("an underfill exception requires a non-empty reason");
    }
    const expiresAtMs = Math.min(now_ms + ttl_ms, next_sweep_due_at_ms);
    underfill = Object.freeze({
      kind: "UNDERFILL",
      reason,
      opened_at_ms: now_ms,
      expires_at_ms: expiresAtMs,
      next_sweep_due_at_ms,
      suggested,
      effective,
      actual,
      shortfall,
    });
  }

  return Object.freeze({
    schema: STAFFING_SCHEMA,
    compared_at_ms: now_ms,
    suggested,
    effective,
    actual,
    cap,
    shortfall,
    verdict: underfill ? "UNDERFILLED" : "ADEQUATE",
    underfill,
  });
}

// An exception is live only until its expiry; the sweep boundary is the
// longest it is allowed to live.
export function isUnderfillExceptionActive(underfill, now_ms) {
  requireInteger(now_ms, "now_ms");
  if (!underfill) return false;
  return now_ms < underfill.expires_at_ms;
}
