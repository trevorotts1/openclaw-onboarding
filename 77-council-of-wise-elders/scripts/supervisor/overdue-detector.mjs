// Independent overdue detector (HYB-04).
//
// A live PID is NOT evidence that the scheduled sweep happened. This detector
// fires SUPERVISOR_OVERDUE at due + 30s regardless of whether the supervisor
// process is alive, so a wedged-but-running supervisor is still caught.
//
// Pure: injected time and injected liveness observation only.
export const OVERDUE_SCHEMA = "wise-elders.hybrid-supervisor-overdue/v1";
export const SUPERVISOR_OVERDUE = "SUPERVISOR_OVERDUE";
export const OVERDUE_GRACE_MS = 30_000;

function requireInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer, got ${String(value)}`);
  }
}

export function detectOverdue({
  now_ms,
  due_at_ms,
  pid_alive = null,
  grace_ms = OVERDUE_GRACE_MS,
}) {
  requireInteger(now_ms, "now_ms");
  requireInteger(due_at_ms, "due_at_ms");
  requireInteger(grace_ms, "grace_ms");
  if (pid_alive !== null && typeof pid_alive !== "boolean") {
    throw new TypeError("pid_alive must be a boolean or null");
  }

  const overdueAtMs = due_at_ms + grace_ms;
  const overdue = now_ms >= overdueAtMs;
  const events = overdue
    ? [
        Object.freeze({
          type: SUPERVISOR_OVERDUE,
          at_ms: overdueAtMs,
          observed_at_ms: now_ms,
          due_at_ms,
          pid_alive,
          independent_of_pid: true,
        }),
      ]
    : [];

  return Object.freeze({
    schema: OVERDUE_SCHEMA,
    observed_at_ms: now_ms,
    due_at_ms,
    grace_ms,
    overdue_at_ms: overdueAtMs,
    overdue,
    pid_alive,
    independent_of_pid: true,
    events: Object.freeze(events),
  });
}
