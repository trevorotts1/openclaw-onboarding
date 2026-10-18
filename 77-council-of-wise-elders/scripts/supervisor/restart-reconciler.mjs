// Restart reconciliation and the persisted rolling restart budget (HYB-04).
//
// Reuses the wave-1 constants (3 restarts / 30 minutes) so there is one source
// of truth, and makes the budget durable: the ledger can be serialized to disk
// and parsed on the next boot. Reconciliation reads the DURABLE pending-action
// list, so work queued before a crash is resumed rather than lost.
import { RESTART_LIMIT, RESTART_WINDOW_MS } from "./supervisor.mjs";

export const RESTART_LEDGER_SCHEMA = "wise-elders.hybrid-supervisor-restart-ledger/v1";

function requireInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer, got ${String(value)}`);
  }
}

function requireLedger(ledger) {
  if (!ledger || ledger.schema !== RESTART_LEDGER_SCHEMA) {
    throw new TypeError(`ledger must be a ${RESTART_LEDGER_SCHEMA} object`);
  }
  requireInteger(ledger.next_pending_seq, "ledger.next_pending_seq");
  return ledger;
}

function withCounters(ledger, patch) {
  const counters = { ...ledger.counters };
  for (const [key, delta] of Object.entries(patch)) {
    counters[key] = (counters[key] ?? 0) + delta;
  }
  return Object.freeze(counters);
}

export function createRestartLedger() {
  return Object.freeze({
    schema: RESTART_LEDGER_SCHEMA,
    restarts: Object.freeze([]),
    pending_actions: Object.freeze([]),
    next_pending_seq: 1,
    counters: Object.freeze({ restarts: 0, refused: 0, reconciliations: 0 }),
  });
}

// At most RESTART_LIMIT restarts in any rolling RESTART_WINDOW_MS window.
// A refusal is still recorded as a durable counter so it is auditable.
export function recordRestart(ledger, { at_ms }) {
  requireLedger(ledger);
  requireInteger(at_ms, "at_ms");
  const inWindow = ledger.restarts.filter((restart) => at_ms - restart < RESTART_WINDOW_MS);
  if (inWindow.length >= RESTART_LIMIT) {
    return Object.freeze({
      allowed: false,
      reason: "RESTART_BUDGET_EXHAUSTED",
      restarts_in_window: inWindow.length,
      limit: RESTART_LIMIT,
      window_ms: RESTART_WINDOW_MS,
      ledger: Object.freeze({
        ...ledger,
        counters: withCounters(ledger, { refused: 1 }),
      }),
    });
  }
  return Object.freeze({
    allowed: true,
    reason: "RESTART_RECORDED",
    restarts_in_window: inWindow.length + 1,
    limit: RESTART_LIMIT,
    window_ms: RESTART_WINDOW_MS,
    ledger: Object.freeze({
      ...ledger,
      restarts: Object.freeze([...ledger.restarts, at_ms]),
      counters: withCounters(ledger, { restarts: 1 }),
    }),
  });
}

export function addPendingAction(ledger, { at_ms, kind, payload = null }) {
  requireLedger(ledger);
  requireInteger(at_ms, "at_ms");
  if (typeof kind !== "string" || kind.length === 0) {
    throw new TypeError("pending action kind must be a non-empty string");
  }
  const action = Object.freeze({
    id: `PEND-${String(ledger.next_pending_seq).padStart(6, "0")}`,
    at_ms,
    kind,
    payload,
    state: "PENDING",
  });
  return Object.freeze({
    ledger: Object.freeze({
      ...ledger,
      next_pending_seq: ledger.next_pending_seq + 1,
      pending_actions: Object.freeze([...ledger.pending_actions, action]),
    }),
    action,
  });
}

// Restart path: reads the durable pending actions and returns them for resume.
export function reconcileAfterRestart(ledger, { now_ms }) {
  requireLedger(ledger);
  requireInteger(now_ms, "now_ms");
  const pending = ledger.pending_actions.map((action) => Object.freeze({ ...action }));
  return Object.freeze({
    schema: RESTART_LEDGER_SCHEMA,
    reconciled_at_ms: now_ms,
    pending_action_count: pending.length,
    pending_actions: Object.freeze(pending),
    actions_to_resume: Object.freeze(pending.map((action) => action.id)),
    ledger: Object.freeze({
      ...ledger,
      counters: withCounters(ledger, { reconciliations: 1 }),
    }),
  });
}

export function serializeRestartLedger(ledger) {
  requireLedger(ledger);
  return JSON.stringify(ledger);
}

export function parseRestartLedger(text) {
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new Error(`restart ledger is not valid JSON: ${error.message}`);
  }
  if (parsed?.schema !== RESTART_LEDGER_SCHEMA) {
    throw new Error(`restart ledger schema must be ${RESTART_LEDGER_SCHEMA}`);
  }
  return Object.freeze({
    ...parsed,
    restarts: Object.freeze([...(parsed.restarts ?? [])]),
    pending_actions: Object.freeze(
      (parsed.pending_actions ?? []).map((action) => Object.freeze({ ...action })),
    ),
    counters: Object.freeze({ ...parsed.counters }),
  });
}
