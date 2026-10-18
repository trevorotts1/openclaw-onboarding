// Incident / action journal for the Hybrid Council of Wise Elders supervisor
// (HYB-03). IDs are deterministic sequences (INC-000001, ACT-000001) so they
// are stable across a restart; counters are cumulative and are part of the
// serialized durable state, never recomputed from the retained window.
//
// Pure reducers: the caller owns persistence and the clock.
export const JOURNAL_SCHEMA = "wise-elders.hybrid-supervisor-journal/v1";
export const ACTION_OUTCOMES = Object.freeze(["PENDING", "SUCCEEDED", "FAILED"]);

function requireInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer, got ${String(value)}`);
  }
}

function requireJournal(journal) {
  if (!journal || journal.schema !== JOURNAL_SCHEMA) {
    throw new TypeError(`journal must be a ${JOURNAL_SCHEMA} object`);
  }
  requireInteger(journal.next_incident_seq, "journal.next_incident_seq");
  requireInteger(journal.next_action_seq, "journal.next_action_seq");
  return journal;
}

function pad(seq) {
  return String(seq).padStart(6, "0");
}

function bumpCounters(counters, patch) {
  const next = { ...counters };
  for (const [key, delta] of Object.entries(patch)) {
    requireInteger(counters[key] ?? 0, `counters.${key}`);
    next[key] = (counters[key] ?? 0) + delta;
  }
  return Object.freeze(next);
}

export function createJournal() {
  return Object.freeze({
    schema: JOURNAL_SCHEMA,
    next_incident_seq: 1,
    next_action_seq: 1,
    incidents: Object.freeze([]),
    actions: Object.freeze([]),
    counters: Object.freeze({
      incidents: 0,
      actions: 0,
      attempts: 0,
      retries: 0,
      succeeded: 0,
      failed: 0,
    }),
  });
}

export function appendIncident(journal, { at_ms, kind, severity = "WARNING", detail = null } = {}) {
  requireJournal(journal);
  requireInteger(at_ms, "at_ms");
  if (typeof kind !== "string" || kind.length === 0) {
    throw new TypeError("incident kind must be a non-empty string");
  }
  if (typeof severity !== "string" || severity.length === 0) {
    throw new TypeError("incident severity must be a non-empty string");
  }
  const incident = Object.freeze({
    id: `INC-${pad(journal.next_incident_seq)}`,
    at_ms,
    kind,
    severity,
    detail,
  });
  const next = Object.freeze({
    ...journal,
    next_incident_seq: journal.next_incident_seq + 1,
    incidents: Object.freeze([...journal.incidents, incident]),
    counters: bumpCounters(journal.counters, { incidents: 1 }),
  });
  return Object.freeze({ journal: next, incident });
}

export function appendAction(
  journal,
  { at_ms, kind, target = null, payload = null } = {},
) {
  requireJournal(journal);
  requireInteger(at_ms, "at_ms");
  if (typeof kind !== "string" || kind.length === 0) {
    throw new TypeError("action kind must be a non-empty string");
  }
  const action = Object.freeze({
    id: `ACT-${pad(journal.next_action_seq)}`,
    at_ms,
    kind,
    target,
    payload,
    outcome: "PENDING",
    attempts: Object.freeze([]),
  });
  const next = Object.freeze({
    ...journal,
    next_action_seq: journal.next_action_seq + 1,
    actions: Object.freeze([...journal.actions, action]),
    counters: bumpCounters(journal.counters, { actions: 1 }),
  });
  return Object.freeze({ journal: next, action });
}

// recordAttempt records an OBSERVED outcome for one action. The first attempt
// is an attempt, every later one is a retry; both success and failure are kept
// so the journal never claims an outcome it did not observe.
export function recordAttempt(journal, { action_id, at_ms, outcome, detail = null } = {}) {
  requireJournal(journal);
  requireInteger(at_ms, "at_ms");
  if (!["SUCCEEDED", "FAILED"].includes(outcome)) {
    throw new RangeError(`attempt outcome must be SUCCEEDED or FAILED, got ${String(outcome)}`);
  }
  const index = journal.actions.findIndex((action) => action.id === action_id);
  if (index === -1) {
    throw new RangeError(`unknown action id ${JSON.stringify(action_id)}`);
  }
  const prior = journal.actions[index];
  const attempt = Object.freeze({ at_ms, outcome, detail });
  const attempts = Object.freeze([...prior.attempts, attempt]);
  const updated = Object.freeze({ ...prior, outcome, attempts });
  const actions = Object.freeze([
    ...journal.actions.slice(0, index),
    updated,
    ...journal.actions.slice(index + 1),
  ]);
  const isRetry = prior.attempts.length > 0;
  const next = Object.freeze({
    ...journal,
    actions,
    counters: bumpCounters(journal.counters, {
      attempts: 1,
      retries: isRetry ? 1 : 0,
      succeeded: outcome === "SUCCEEDED" ? 1 : 0,
      failed: outcome === "FAILED" ? 1 : 0,
    }),
  });
  return Object.freeze({ journal: next, action: updated, attempt, retry: isRetry });
}

export function serializeJournal(journal) {
  requireJournal(journal);
  return JSON.stringify(journal);
}

// Restart path: rebuild durable state, counters included. A corrupt journal is
// a hard error rather than a silently truncated history.
export function parseJournal(text) {
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new Error(`incident journal is not valid JSON: ${error.message}`);
  }
  if (parsed?.schema !== JOURNAL_SCHEMA) {
    throw new Error(`incident journal schema must be ${JOURNAL_SCHEMA}`);
  }
  return Object.freeze({
    ...parsed,
    incidents: Object.freeze((parsed.incidents ?? []).map((entry) => Object.freeze({ ...entry }))),
    actions: Object.freeze(
      (parsed.actions ?? []).map((entry) =>
        Object.freeze({
          ...entry,
          attempts: Object.freeze((entry.attempts ?? []).map((attempt) => Object.freeze({ ...attempt }))),
        }),
      ),
    ),
    counters: Object.freeze({ ...parsed.counters }),
  });
}
