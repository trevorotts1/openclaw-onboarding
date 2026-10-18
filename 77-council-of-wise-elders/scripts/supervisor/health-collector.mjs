// Deterministic health COLLECTION for the Hybrid Council of Wise Elders
// supervisor (HYB-03). The wave-1 health-observer decides a verdict from a
// snapshot; this module produces that snapshot and the significant-change
// delta between two of them.
//
// Pure over injected time and injected observations: no Date.now, no timers,
// no network, no PID probes. The caller (or the host adapter) performs the
// probing and passes the result in, which keeps the collection reproducible in
// tests with fake time.
import { SWEEP_UNHEALTHY_GATE_MS } from "./sweep-planner.mjs";

export const HEALTH_COLLECTION_SCHEMA =
  "wise-elders.hybrid-supervisor-health-collection/v1";

export const COLLECTION_VERDICTS = Object.freeze(["HEALTHY", "SUSPECT", "DEGRADED"]);
export const SUBJECT_KINDS = Object.freeze(["native", "process", "tool"]);
export const LIVENESS_STATES = Object.freeze(["ALIVE", "DEAD", "UNKNOWN"]);

const VERDICT_RANK = Object.freeze({ HEALTHY: 0, SUSPECT: 1, DEGRADED: 2 });

function requireInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer, got ${String(value)}`);
  }
}

function requireSubject(subject, index) {
  if (!subject || typeof subject !== "object") {
    throw new TypeError(`subjects[${index}] must be an object`);
  }
  if (typeof subject.id !== "string" || subject.id.length === 0) {
    throw new TypeError(`subjects[${index}].id must be a non-empty string`);
  }
  if (!SUBJECT_KINDS.includes(subject.kind)) {
    throw new RangeError(`subjects[${index}].kind must be one of ${SUBJECT_KINDS.join(", ")}`);
  }
  if (!LIVENESS_STATES.includes(subject.liveness)) {
    throw new RangeError(
      `subjects[${index}].liveness must be one of ${LIVENESS_STATES.join(", ")}`,
    );
  }
  return subject;
}

function sortedFaults(faults) {
  return Object.freeze(
    [...faults].sort(
      (a, b) => a.code.localeCompare(b.code) || String(a.detail).localeCompare(String(b.detail)),
    ),
  );
}

function diffPrevious(previous, current) {
  if (!previous || typeof previous !== "object") return Object.freeze([]);

  const changes = [];
  const before = new Map(
    (Array.isArray(previous.subjects) ? previous.subjects : []).map((s) => [s.id, s]),
  );
  for (const subject of current.subjects) {
    const prior = before.get(subject.id);
    if (!prior) {
      changes.push({ kind: "SUBJECT_ADDED", subject: subject.id, from: null, to: subject.liveness });
      continue;
    }
    if (prior.liveness !== subject.liveness) {
      changes.push({
        kind: "LIVENESS_CHANGED",
        subject: subject.id,
        from: prior.liveness,
        to: subject.liveness,
      });
    }
  }
  for (const id of before.keys()) {
    if (!current.subjects.some((s) => s.id === id)) {
      changes.push({ kind: "SUBJECT_REMOVED", subject: id, from: before.get(id).liveness, to: null });
    }
  }

  const priorFaults = new Set(
    (Array.isArray(previous.faults) ? previous.faults : []).map((f) => f.code),
  );
  const currentFaults = new Set(current.faultCodes);
  for (const code of currentFaults) {
    if (!priorFaults.has(code)) changes.push({ kind: "FAULT_ADDED", code, from: null, to: code });
  }
  for (const code of priorFaults) {
    if (!currentFaults.has(code)) changes.push({ kind: "FAULT_CLEARED", code, from: code, to: null });
  }

  const priorDue = previous.signals?.next_due_at_ms ?? null;
  if (priorDue !== current.nextDue) {
    changes.push({ kind: "DUE_RESCHEDULED", from: priorDue, to: current.nextDue });
  }

  return Object.freeze(
    changes
      .sort((a, b) => a.kind.localeCompare(b.kind) || String(a.subject ?? a.code ?? "").localeCompare(String(b.subject ?? b.code ?? "")))
      .map((change) => Object.freeze(change)),
  );
}

/**
 * collectHealth({ now_ms, subjects, due, previous })
 *   subjects: [{ id, kind: "native"|"process"|"tool", liveness: "ALIVE"|"DEAD"|"UNKNOWN" }]
 *   due:      { next_due_at_ms }
 *   previous: a prior collectHealth() result, or null
 *
 * Verdict rules: DEAD subject or overdue sweep -> DEGRADED; UNKNOWN subject,
 * missing due time, or a sweep inside its 30s gate -> SUSPECT.
 */
export function collectHealth({ now_ms, subjects, due = {}, previous = null }) {
  requireInteger(now_ms, "now_ms");
  if (!Array.isArray(subjects)) {
    throw new TypeError("subjects must be an array");
  }

  const faults = [];
  let verdict = "HEALTHY";
  const escalate = (next, code, detail) => {
    faults.push(Object.freeze({ code, detail }));
    if (VERDICT_RANK[next] > VERDICT_RANK[verdict]) verdict = next;
  };

  const normalized = Object.freeze(
    subjects
      .map(requireSubject)
      .map((subject) =>
        Object.freeze({ id: subject.id, kind: subject.kind, liveness: subject.liveness }),
      )
      .sort((a, b) => a.kind.localeCompare(b.kind) || a.id.localeCompare(b.id)),
  );

  for (const subject of normalized) {
    if (subject.liveness === "DEAD") escalate("DEGRADED", "SUBJECT_DEAD", subject.id);
    else if (subject.liveness === "UNKNOWN") escalate("SUSPECT", "SUBJECT_UNKNOWN", subject.id);
  }

  const nextDue = due.next_due_at_ms ?? null;
  let overdueByMs = null;
  if (nextDue === null) {
    escalate("SUSPECT", "DUE_UNKNOWN", null);
  } else {
    requireInteger(nextDue, "due.next_due_at_ms");
    overdueByMs = now_ms - nextDue;
    if (overdueByMs > SWEEP_UNHEALTHY_GATE_MS) {
      escalate("DEGRADED", "DUE_OVERDUE", overdueByMs);
    } else if (overdueByMs > 0) {
      escalate("SUSPECT", "DUE_LATE", overdueByMs);
    }
  }

  const frozenFaults = sortedFaults(faults);
  const changes = diffPrevious(previous, {
    subjects: normalized,
    faultCodes: frozenFaults.map((fault) => fault.code),
    nextDue,
  });

  return Object.freeze({
    schema: HEALTH_COLLECTION_SCHEMA,
    observed_at_ms: now_ms,
    verdict,
    subjects: normalized,
    faults: frozenFaults,
    changes,
    significant_change: changes.length > 0,
    signals: Object.freeze({
      subject_count: normalized.length,
      next_due_at_ms: nextDue,
      overdue_by_ms: overdueByMs,
      unhealthy_gate_ms: SWEEP_UNHEALTHY_GATE_MS,
    }),
    llm_calls: 0,
  });
}
