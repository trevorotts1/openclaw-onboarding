/**
 * relay_brain_validation.js — Rescue Rangers Relay Brain edge-validation patch.
 *
 * Topic-4 FIX 4-B (kills R2 "the advertised 9-field validation is NOT enforced"):
 *   The client AGENTS.md template says "The escalation payload MUST carry all nine
 *   fields -- partial payloads are rejected." The live Relay Brain's ONLY input
 *   check is `missing_message`. Thin tickets (e.g. the CC's 3-field notifySystem
 *   payload) sail through with degraded context. This module is the drop-in
 *   validator that enforces the full nine-field contract at the edge.
 *
 * Topic-4 FIX 4-D (kills R4 "return leg covers Mac-tunnel boxes only"):
 *   handleStatusQuery() implements the NEW Relay Brain `status` branch a client
 *   agent polls outbound-only ({action:"status", ticketId}) on its next heartbeat
 *   turns until answered — works identically on VPS and Mac (no inbound path).
 *
 * DESIGN LAW (from the spec):
 *   "never drop a distress call on a technicality." A payload with missing fields
 *   is REJECTED-to-SENDER (an error response) AND still POSTED-to-operator as a
 *   degraded ticket flagged INCOMPLETE. A missing field never silences a box in
 *   trouble; it only flags the operator that context is thin.
 *
 * WIRING (deferred — do NOT redeploy live n8n from the repo):
 *   Paste the body of this module into the "Relay Brain" n8n Code node, replacing
 *   the single `missing_message` guard in the `escalate` branch with a call to
 *   validateEscalation(payload), and add a `status` case that calls
 *   handleStatusQuery(payload, lookup). The staging-test + pre-change JSON export
 *   ritual (already practiced in fleet-heartbeat/scripts/) is MANDATORY before any
 *   live redeploy. See RELAY-BRAIN-PATCH.md.
 *
 * PURE + DEP-FREE: no imports, no network, no n8n globals — every function is a
 * pure transform of its inputs, so it runs under plain `node` for the self-test
 * and drops unchanged into the Code node (which is also plain JS).
 */

'use strict';

// The nine advertised fields (must match rescue_ledger.NINE_FIELDS).
const NINE_FIELDS = [
  'person', 'clientName', 'agentName', 'boxName', 'boxType',
  'openclawVersion', 'problem', 'alreadyTried', 'returnTo',
];

// boxType is a closed vocabulary (matches the AGENTS.md field guide).
const VALID_BOX_TYPES = ['VPS', 'Mac Mini', 'MacBook Pro'];

function _isNonEmpty(v) {
  return typeof v === 'string' ? v.trim().length > 0 : (v !== null && v !== undefined && v !== '');
}

/**
 * Classify + validate an inbound `escalate` payload.
 *
 * Returns an object:
 *   {
 *     ok: boolean,             // true when the payload is a fully valid contract form
 *     kind: string,            // 'full' | 'resolution' | 'system-sweep' | 'incomplete'
 *     degraded: boolean,       // true when accepted but context is thin
 *     postTicket: boolean,     // true => still post a ticket to the operator group
 *     incomplete: boolean,     // true => flag the ticket INCOMPLETE
 *     missingFields: string[], // which of the nine were absent/empty
 *     warnings: string[],      // non-fatal issues (e.g. bad boxType)
 *     error: string|null,      // 'missing_fields' | 'missing_message' | null
 *     normalized: object,      // a nine-field object safe to persist (short forms mapped up)
 *   }
 *
 * Contract:
 *   - RESOLUTION SIGNAL (`problem` starts with "RESOLVED:") — a sanctioned short
 *     form that CLOSES an existing ticket; ok:true, postTicket:false.
 *   - CC notifySystem SHORT FORM ({agent, message}) — a sanctioned legacy short
 *     form; accepted but degraded:true (the preferred long-term fix is upgrading
 *     notify.ts to the full nine-field form). Mapped up into `normalized`.
 *   - FULL escalate — all nine fields non-empty => ok:true. Any missing =>
 *     ok:false, error:'missing_fields', but postTicket:true + incomplete:true so
 *     the distress call is NEVER dropped.
 */
function validateEscalation(payload) {
  const p = payload && typeof payload === 'object' ? payload : {};
  const result = {
    ok: false, kind: 'incomplete', degraded: false, postTicket: true,
    incomplete: false, missingFields: [], warnings: [], error: null,
    normalized: {},
  };

  const problemStr = typeof p.problem === 'string' ? p.problem.trim() : '';

  // (1) RESOLUTION SIGNAL — sanctioned short form that closes a ticket.
  if (/^RESOLVED:/i.test(problemStr)) {
    result.ok = true;
    result.kind = 'resolution';
    result.postTicket = false; // closes an existing ticket, does not open a new one
    result.normalized = {
      clientName: p.clientName || '', agentName: p.agentName || '', problem: problemStr,
    };
    if (!_isNonEmpty(p.clientName)) {
      result.warnings.push('resolution signal missing clientName — cannot match a ticket');
    }
    return result;
  }

  // (2) CC notifySystem SHORT FORM — sanctioned legacy automated-sweep shape.
  //     {action:'escalate', agent, message} with none of the nine present.
  const looksSystemSweep =
    _isNonEmpty(p.agent) && _isNonEmpty(p.message) &&
    !_isNonEmpty(p.person) && !_isNonEmpty(p.problem) && !_isNonEmpty(p.boxName);
  if (looksSystemSweep) {
    result.ok = true;
    result.kind = 'system-sweep';
    result.degraded = true;         // thin context — flag it, do not reject
    result.postTicket = true;
    result.normalized = {
      person: 'operator', clientName: p.clientName || 'command-center',
      agentName: p.agent, boxName: p.boxName || 'command-center', boxType: p.boxType || 'VPS',
      openclawVersion: 'n/a', problem: p.message,
      alreadyTried: 'n/a (automated sweep alert)', returnTo: p.returnTo || '',
    };
    result.warnings.push(
      'CC notifySystem short form — upgrade notify.ts to the full nine-field ' +
      'payload for ONE fleet-wide contract (FIX 4-B)');
    return result;
  }

  // (3) FULL escalate — enforce all nine fields.
  const missing = NINE_FIELDS.filter((f) => !_isNonEmpty(p[f]));
  const normalized = {};
  NINE_FIELDS.forEach((f) => { normalized[f] = _isNonEmpty(p[f]) ? String(p[f]).trim() : ''; });
  result.normalized = normalized;

  // boxType vocabulary check (non-fatal — warn, still accept the ticket).
  if (_isNonEmpty(p.boxType) && VALID_BOX_TYPES.indexOf(String(p.boxType).trim()) === -1) {
    result.warnings.push(
      `boxType '${p.boxType}' not one of ${VALID_BOX_TYPES.join(' / ')}`);
    result.degraded = true;
  }

  if (missing.length === 0) {
    result.ok = true;
    result.kind = 'full';
    result.postTicket = true;
    return result;
  }

  // Missing fields: REJECT-to-SENDER but POST-to-OPERATOR (never drop the call).
  result.ok = false;
  result.kind = 'incomplete';
  result.incomplete = true;
  result.degraded = true;
  result.postTicket = true;
  result.missingFields = missing;
  // Preserve the legacy `missing_message` signal when it is specifically `problem`.
  result.error = (missing.length === 1 && missing[0] === 'problem')
    ? 'missing_message' : 'missing_fields';
  return result;
}

/**
 * Build the plain-text ticket header the Relay Brain posts to the Fixer topic,
 * extended with an INCOMPLETE flag + the missing-fields line when degraded.
 * `meta` = {ticketId, status, incomplete, missingFields}.
 */
function buildTicketHeader(normalized, meta) {
  const n = normalized || {};
  const m = meta || {};
  const status = (m.status || 'OPEN').toUpperCase();
  const lines = [
    `Ticket: ${m.ticketId || '(new)'}`,
    `Status: ${status}${m.incomplete ? '  [INCOMPLETE]' : ''}`,
    `Person: ${n.person || '(unknown)'}`,
    `Agent: ${n.agentName || '(unknown)'}`,
    `Client: ${n.clientName || '(unknown)'}`,
    `Box: ${n.boxName || '(unknown)'}`,
    `BoxType: ${n.boxType || '(unknown)'}`,
  ];
  if (m.incomplete && Array.isArray(m.missingFields) && m.missingFields.length) {
    lines.push(`Missing fields: ${m.missingFields.join(', ')}`);
  }
  return lines.join('\n');
}

/**
 * FIX 4-D — the NEW Relay Brain `status` branch (VPS-safe return leg).
 * A client agent polls {action:"status", ticketId} outbound-only; the relay reads
 * the queue/ledger via `lookup(ticketId)` (returns a ticket object or null) and
 * answers whether the ticket is answered/resolved yet + the answer if present.
 *
 * `lookup` is injected so this stays pure/testable; in n8n it reads
 * $getWorkflowStaticData('global') (transport buffer) or the operator ledger
 * export. Returns a small object the client agent can act on.
 */
function handleStatusQuery(payload, lookup) {
  const p = payload && typeof payload === 'object' ? payload : {};
  const ticketId = p.ticketId || p.ticket_id || '';
  if (!_isNonEmpty(ticketId)) {
    return { ok: false, error: 'missing_ticketId', status: 'unknown' };
  }
  let ticket = null;
  try {
    ticket = typeof lookup === 'function' ? lookup(ticketId) : null;
  } catch (e) {
    return { ok: false, error: 'lookup_failed', status: 'unknown', ticketId };
  }
  if (!ticket) {
    return { ok: true, found: false, status: 'not_found', ticketId };
  }
  const st = String(ticket.status || 'open');
  const answered = st === 'answered' || st === 'resolved' || !!ticket.answer;
  return {
    ok: true,
    found: true,
    ticketId,
    status: st,
    answered,
    resolved: st === 'resolved',
    answer: answered ? (ticket.answer || '') : '',
  };
}

// -------------------------------------------------------------------------
// Deterministic self-test (no n8n, no network): `node relay_brain_validation.js --self-test`
// -------------------------------------------------------------------------
function selfTest() {
  const assert = (cond, msg) => { if (!cond) { throw new Error('FAIL: ' + msg); } };
  console.log('[relay_brain_validation] self-test: nine-field enforcement, short forms, ' +
    'incomplete-but-not-dropped, boxType, status branch');

  // full valid payload
  const full = {
    action: 'escalate', person: 'Owner', clientName: 'acme', agentName: 'Aria',
    boxName: 'acme-mac', boxType: 'Mac Mini', openclawVersion: '2026.5.22',
    problem: 'gateway down', alreadyTried: '1) doctor', returnTo: '123',
  };
  let r = validateEscalation(full);
  assert(r.ok && r.kind === 'full' && r.missingFields.length === 0, 'full payload accepted');
  assert(r.postTicket === true && r.incomplete === false, 'full payload posts a clean ticket');
  console.log('  full case: PASS (all nine present => ok, clean ticket)');

  // missing several fields => not ok, but STILL posts a degraded INCOMPLETE ticket
  const thin = { action: 'escalate', clientName: 'acme', problem: 'help' };
  r = validateEscalation(thin);
  assert(r.ok === false, 'thin payload not ok');
  assert(r.error === 'missing_fields', 'thin payload flags missing_fields');
  assert(r.postTicket === true && r.incomplete === true, 'thin payload STILL posts INCOMPLETE (never dropped)');
  assert(r.missingFields.indexOf('person') !== -1 && r.missingFields.indexOf('boxType') !== -1,
    'missing list names the absent fields');
  console.log('  incomplete case: PASS (rejected-to-sender + posted-to-operator, flagged INCOMPLETE)');

  // exactly-one missing (problem) preserves the legacy missing_message signal
  const noProblem = { ...full }; delete noProblem.problem;
  r = validateEscalation(noProblem);
  assert(r.ok === false && r.error === 'missing_message', 'sole missing problem => missing_message');
  console.log('  missing_message case: PASS (legacy signal preserved for empty problem)');

  // resolution signal short form closes a ticket, does not open one
  r = validateEscalation({ action: 'escalate', clientName: 'acme', agentName: 'Aria',
    problem: 'RESOLVED: restarted the gateway' });
  assert(r.ok && r.kind === 'resolution' && r.postTicket === false, 'resolution closes, does not open');
  console.log('  resolution case: PASS (RESOLVED: short form recognized)');

  // CC notifySystem short form accepted but degraded + mapped up to nine fields
  r = validateEscalation({ action: 'escalate', agent: 'CC Sweep',
    message: 'stuck-in-progress task 42' });
  assert(r.ok && r.kind === 'system-sweep' && r.degraded === true, 'system sweep accepted+degraded');
  assert(r.normalized.person === 'operator' && r.normalized.problem === 'stuck-in-progress task 42',
    'system sweep mapped up to a nine-field ticket');
  assert(r.warnings.some((w) => /notify\.ts/.test(w)), 'warns to upgrade notify.ts');
  console.log('  system-sweep case: PASS (legacy CC shape whitelisted + flagged for upgrade)');

  // bad boxType warns but does not drop
  const badBox = { ...full, boxType: 'Raspberry Pi' };
  r = validateEscalation(badBox);
  assert(r.ok === true && r.degraded === true, 'bad boxType still accepted');
  assert(r.warnings.some((w) => /boxType/.test(w)), 'bad boxType produces a warning');
  console.log('  boxType case: PASS (unknown boxType warns, does not drop)');

  // ticket header renders the INCOMPLETE flag + missing line
  const hdr = buildTicketHeader(validateEscalation(thin).normalized,
    { ticketId: 'tkt-7', status: 'open', incomplete: true, missingFields: ['person', 'boxType'] });
  assert(/\[INCOMPLETE\]/.test(hdr) && /Missing fields: person, boxType/.test(hdr),
    'header shows INCOMPLETE + missing fields');
  console.log('  header case: PASS (INCOMPLETE flag + missing-fields line)');

  // status branch (VPS return leg)
  const store = { 'tkt-1': { status: 'answered', answer: 'kickstart the gateway' },
    'tkt-2': { status: 'open' } };
  const lookup = (id) => store[id] || null;
  let s = handleStatusQuery({ action: 'status', ticketId: 'tkt-1' }, lookup);
  assert(s.ok && s.found && s.answered && s.answer === 'kickstart the gateway', 'answered ticket returns the answer');
  s = handleStatusQuery({ action: 'status', ticketId: 'tkt-2' }, lookup);
  assert(s.ok && s.found && s.answered === false, 'open ticket not yet answered');
  s = handleStatusQuery({ action: 'status', ticketId: 'nope' }, lookup);
  assert(s.ok && s.found === false && s.status === 'not_found', 'unknown ticket => not_found');
  s = handleStatusQuery({ action: 'status' }, lookup);
  assert(s.ok === false && s.error === 'missing_ticketId', 'status query needs a ticketId');
  console.log('  status-branch case: PASS (outbound-only VPS/Mac return leg)');

  console.log('[relay_brain_validation] self-test: PASS');
  return 0;
}

module.exports = {
  NINE_FIELDS,
  VALID_BOX_TYPES,
  validateEscalation,
  buildTicketHeader,
  handleStatusQuery,
  selfTest,
};

if (require.main === module) {
  if (process.argv.indexOf('--self-test') !== -1) {
    try {
      process.exit(selfTest());
    } catch (e) {
      console.error(String(e && e.stack ? e.stack : e));
      process.exit(1);
    }
  } else {
    console.log('Rescue Rangers Relay Brain validation patch. Run with --self-test.');
    process.exit(0);
  }
}
