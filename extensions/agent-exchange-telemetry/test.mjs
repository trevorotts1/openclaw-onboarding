// Focused behaviour checks for agent-exchange-telemetry.
// Runs with no live gateway: the plugin is driven through its exported core
// (beforeToolCall / afterToolCall / handleAgentEvent) with host-shaped events.
// Every case named in the B19 acceptance list is exercised here.
//
//   node extensions/agent-exchange-telemetry/test.mjs
//
// Assert-based, no framework, no network, no provider, no client box.

import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import registerPlugin, { createTelemetry, mintExchangeId, BOUNDS, TOOL_MATCHER } from './dist/index.js';

const ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'hq-b-B19-'));
const COMPANY = 'company-test';
const INSTALL = 'installation-test';

let passed = 0;
const failures = [];

function check(name, fn) {
  try {
    fn();
    passed += 1;
    process.stdout.write(`ok   ${name}\n`);
  } catch (error) {
    failures.push({ name, error });
    process.stdout.write(`FAIL ${name}\n     ${error && error.message}\n`);
  }
}

function lane(name) {
  const dir = path.join(ROOT, name);
  return {
    dir: path.join(dir, 'correlation'),
    outboxDir: path.join(dir, 'outbox'),
    root: dir,
  };
}

function makeTelemetry(laneRef, extra = {}) {
  const { config: extraConfig, ...rest } = extra;
  return createTelemetry({
    config: { companyId: COMPANY, installationId: INSTALL, ...(extraConfig ?? {}) },
    dir: laneRef.dir,
    outboxDir: laneRef.outboxDir,
    logger: { warn() {}, error() {} },
    ...rest,
  });
}

/** Every byte the plugin wrote under this lane's workspace. */
function allWritten(laneRef) {
  const out = [];
  const walk = (dir) => {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir)) {
      const full = path.join(dir, entry);
      if (fs.statSync(full).isDirectory()) walk(full);
      else out.push({ file: full, body: fs.readFileSync(full, 'utf8') });
    }
  };
  walk(laneRef.root);
  return out;
}

function outboxFiles(laneRef, exchangeId, phase) {
  const wanted = `exchange_${exchangeId}_${phase}.json`;
  return fs.existsSync(laneRef.outboxDir)
    ? fs.readdirSync(laneRef.outboxDir).filter((n) => n === wanted)
    : [];
}

function readOutbox(laneRef, exchangeId, phase) {
  const files = outboxFiles(laneRef, exchangeId, phase);
  if (files.length === 0) return null;
  return JSON.parse(fs.readFileSync(path.join(laneRef.outboxDir, files[0]), 'utf8'));
}

/** Host-shaped before event/context for a sessions_send from a caller. */
function beforeEvent(sessionKey, runId, toolCallId, toolName, message) {
  return [
    { toolName, params: { message, sessionKey: 'agent:requested:target' }, runId, toolCallId },
    { toolName, sessionKey, runId, toolCallId, agentId: sessionKey.split(':')[1] },
  ];
}

function afterEvent(sessionKey, runId, toolCallId, toolName, details, error) {
  const event = {
    toolName,
    params: { message: 'req' },
    runId,
    toolCallId,
    ...(error ? { error } : { result: { content: [{ type: 'text', text: JSON.stringify(details) }], details } }),
  };
  return [event, { toolName, sessionKey, runId, toolCallId }];
}

function lifecycleEvent(runId, sessionKey, data) {
  return { runId, seq: 1, stream: 'lifecycle', ts: Date.now(), data, sessionKey };
}

const CALLER = 'agent:public:subagent:t1';
const TARGET = 'agent:marketing:subagent:t2';

// ── 0. Matcher and module shape ─────────────────────────────────────────
check('matcher is exactly the two native tool names', () => {
  assert.deepEqual([...TOOL_MATCHER], ['sessions_send', 'sessions_spawn']);
});

check('exchangeId is 64 lowercase hex from the length-prefixed tuple', () => {
  const id = mintExchangeId(['inst', 'sess', 'run', 'call']);
  assert.match(id, /^[0-9a-f]{64}$/);
  // Same tuple => same id (order-independent of arrival, stable across retries).
  assert.equal(id, mintExchangeId(['inst', 'sess', 'run', 'call']));
  // Different tuple => different id, and tuple order matters.
  assert.notEqual(id, mintExchangeId(['inst', 'run', 'sess', 'call']));
});

check('missing identity mints no exchangeId', () => {
  assert.equal(mintExchangeId(['inst', 'sess', '', 'call']), null);
  assert.equal(mintExchangeId(['inst', null, 'run', 'call']), null);
});

// ── 1. Q06 synchronous reply ────────────────────────────────────────────
check('Q06 synchronous ok/reply: requested then replied, one envelope each', () => {
  const l = lane('sync');
  const t = makeTelemetry(l, { config: { publicSessionKeys: ['agent:public:subagent:t1'] } });
  const b = beforeEvent(CALLER, 'run-1', 'call-1', 'sessions_send', 'please send the report');
  t.beforeToolCall(...b);
  const a = afterEvent(CALLER, 'run-1', 'call-1', 'sessions_send', {
    status: 'ok',
    runId: 'run-1',
    sessionKey: TARGET,
    reply: 'report sent',
  });
  const res = t.afterToolCall(...a);
  assert.equal(res.phase, 'replied');
  const id = mintExchangeId([INSTALL, CALLER, 'run-1', 'call-1']);
  assert.equal(outboxFiles(l, id, 'requested').length, 1);
  assert.equal(outboxFiles(l, id, 'replied').length, 1);
  const replied = readOutbox(l, id, 'replied');
  assert.equal(replied.event.sourceKey, `exchange:${id}:replied`);
  assert.equal(replied.event.phase, undefined); // phase is carried by sourceKey, not a duplicate field
  assert.equal(replied.event.kind, 'exchange');
  assert.equal(replied.event.payload.message, 'report sent');
  assert.equal(replied.event.payload.nativeStatus, 'ok');
  assert.equal(replied.event.payload.correlationStatus, 'linked');
  assert.equal(replied.event.payload.toolName, 'sessions_send');
  assert.equal(replied.event.payload.toolCallId, 'call-1');
  assert.equal(replied.event.payload.callerRunId, 'run-1');
  assert.equal(replied.event.payload.targetSessionKey, TARGET);
});

check('synchronous reply is recorded as returned, never as delivered', () => {
  const l = lane('sync-delivered');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-d', 'call-d', 'sessions_send', 'hi'));
  t.afterToolCall(...afterEvent(CALLER, 'run-d', 'call-d', 'sessions_send', {
    status: 'ok', runId: 'run-d', sessionKey: TARGET, reply: 'done',
  }));
  const rec = t.records()[0];
  assert.equal(rec.replyState, 'returned');
  assert.equal(rec.delivered, false);
});

// ── 2. Q06 async / queued / spawn reply ─────────────────────────────────
check('Q06 queued followup: accepted binds the receiver run, terminal reply joins', () => {
  const l = lane('queued');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-q', 'call-q', 'sessions_send', 'q'));
  const res = t.afterToolCall(...afterEvent(CALLER, 'run-q', 'call-q', 'sessions_send', {
    status: 'accepted', runId: 'run-target-q', sessionKey: TARGET, targetDisposition: 'queued',
    delivery: { status: 'pending' }, watched: true,
  }));
  assert.equal(res.phase, 'accepted');
  const id = mintExchangeId([INSTALL, CALLER, 'run-q', 'call-q']);
  assert.equal(readOutbox(l, id, 'accepted').event.payload.nativeStatus, 'accepted');
  // Terminal arrives later on the bound receiver run.
  const term = t.handleAgentEvent(lifecycleEvent('run-target-q', TARGET, {
    phase: 'end', executionSettled: true, terminalReply: { disposition: 'visible', text: 'async answer' },
  }));
  assert.equal(term.ok, true);
  assert.equal(outboxFiles(l, id, 'replied').length, 1);
  const replied = readOutbox(l, id, 'replied');
  assert.equal(replied.event.payload.message, 'async answer');
  assert.equal(replied.event.payload.sourceHook, 'lifecycle');
  const rec = t.records()[0];
  assert.equal(rec.replyState, 'generated');
  assert.equal(rec.delivered, false);
});

check('spawn admission binds child run and joins its terminal reply', () => {
  const l = lane('spawn');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-s', 'call-s', 'sessions_spawn', 'do the thing'));
  t.afterToolCall(...afterEvent(CALLER, 'run-s', 'call-s', 'sessions_spawn', {
    status: 'accepted', childSessionKey: 'agent:research:subagent:c1', runId: 'run-child-c1',
    mode: 'async', expectsCompletionMessage: true,
  }));
  const id = mintExchangeId([INSTALL, CALLER, 'run-s', 'call-s']);
  const accepted = readOutbox(l, id, 'accepted');
  assert.equal(accepted.event.payload.targetSessionKey, 'agent:research:subagent:c1');
  assert.equal(accepted.event.payload.targetRunId, 'run-child-c1');
  t.handleAgentEvent(lifecycleEvent('run-child-c1', 'agent:research:subagent:c1', {
    phase: 'end', executionSettled: true, terminalReply: { disposition: 'visible', text: 'child done' },
  }));
  assert.equal(readOutbox(l, id, 'replied').event.payload.message, 'child done');
});

check('notify-only queued (runStarted:false) never fabricates a join', () => {
  const l = lane('notify');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-n', 'call-n', 'sessions_send', 'note'));
  t.afterToolCall(...afterEvent(CALLER, 'run-n', 'call-n', 'sessions_send', {
    status: 'queued', sessionKey: TARGET, notificationId: 'note-1', durability: 'process', runStarted: false,
  }));
  const id = mintExchangeId([INSTALL, CALLER, 'run-n', 'call-n']);
  const rec = t.records()[0];
  assert.equal(rec.targetRunId, null);
  assert.equal(rec.correlationStatus, 'unsupported');
  assert.equal(readOutbox(l, id, 'accepted').event.payload.correlationStatus, 'unsupported');
  // A terminal for some other run cannot attach to it.
  t.handleAgentEvent(lifecycleEvent('some-other-run', TARGET, { phase: 'end', executionSettled: true }));
  assert.equal(outboxFiles(l, id, 'replied').length, 0);
});

// ── 3. Q06 steer-unjoinable ─────────────────────────────────────────────
check('Q06 steer-unjoinable: uncertain, target run not bound, terminal cannot join', () => {
  const l = lane('steer');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-st', 'call-st', 'sessions_send', 'steer me'));
  const res = t.afterToolCall(...afterEvent(CALLER, 'run-st', 'call-st', 'sessions_send', {
    status: 'accepted', runId: 'send-operation-id', sessionKey: TARGET, targetDisposition: 'steered',
    delivery: { status: 'pending' },
  }));
  assert.equal(res.phase, 'uncertain');
  const id = mintExchangeId([INSTALL, CALLER, 'run-st', 'call-st']);
  const rec = t.records()[0];
  assert.equal(rec.targetRunId, null);
  assert.equal(rec.conflicts.length, 0);
  const uncertain = readOutbox(l, id, 'uncertain');
  assert.equal(uncertain.event.payload.correlationStatus, 'unresolved');
  assert.equal(uncertain.event.payload.targetDisposition, 'steered');
  // The steered operation id must never act as a receiver run for terminal text.
  t.handleAgentEvent(lifecycleEvent('send-operation-id', TARGET, {
    phase: 'end', executionSettled: true, terminalReply: { disposition: 'visible', text: 'not my reply' },
  }));
  assert.equal(outboxFiles(l, id, 'replied').length, 0);
});

// ── 4. Q06 missing identity ─────────────────────────────────────────────
check('Q06 missing identity: uncorrelated health, no exchangeId, no persistence', () => {
  const l = lane('no-identity');
  const t = makeTelemetry(l);
  const res = t.beforeToolCall({ toolName: 'sessions_send', params: { message: 'x' } }, { toolName: 'sessions_send' });
  assert.equal(res.ok, false);
  assert.equal(res.reason, 'uncorrelated');
  assert.equal(t.health.uncorrelated, 1);
  assert.equal(t.records().length, 0);
  assert.equal(fs.existsSync(l.outboxDir) ? fs.readdirSync(l.outboxDir).length : 0, 0);
});

check('missing toolCallId alone still refuses to guess a sender', () => {
  const l = lane('no-toolcall');
  const t = makeTelemetry(l);
  const res = t.beforeToolCall(
    { toolName: 'sessions_send', params: {} },
    { toolName: 'sessions_send', sessionKey: CALLER, runId: 'run-x' },
  );
  assert.equal(res.reason, 'uncorrelated');
});

// ── 5. Q06 out-of-order arrivals ────────────────────────────────────────
check('Q06 terminal-before-link: metadata only, then joins once when accepted arrives', () => {
  const l = lane('ooo-terminal-first');
  const observed = new Map([['run-ooo', { disposition: 'visible', text: 'late but public' }]]);
  const t = makeTelemetry(l, {
    config: { publicSessionKeys: [CALLER] },
    observeRunTerminal: (runId) => observed.get(runId),
  });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-ooo', 'call-ooo', 'sessions_send', 'will reply'));
  // Terminal arrives first.
  const early = t.handleAgentEvent(lifecycleEvent('run-ooo', TARGET, {
    phase: 'end', executionSettled: true, terminalReply: { disposition: 'visible', text: 'late but public' },
  }));
  assert.deepEqual(early, { ok: true, orphan: true, runId: 'run-ooo' });
  const id = mintExchangeId([INSTALL, CALLER, 'run-ooo', 'call-ooo']);
  assert.equal(outboxFiles(l, id, 'replied').length, 0, 'no reply may be emitted before linkage');
  // Nothing on disk may carry the pre-link terminal text.
  for (const { body } of allWritten(l)) {
    assert.equal(body.includes('late but public'), false, 'orphan terminal text leaked to disk');
  }
  // Link arrives second and the exact run receipt is recovered.
  t.afterToolCall(...afterEvent(CALLER, 'run-ooo', 'call-ooo', 'sessions_send', {
    status: 'accepted', runId: 'run-ooo', sessionKey: TARGET, targetDisposition: 'queued',
  }));
  assert.equal(outboxFiles(l, id, 'replied').length, 1);
  assert.equal(readOutbox(l, id, 'replied').event.payload.message, 'late but public');
  // Exactly one replied source key; no second envelope.
  assert.equal(outboxFiles(l, id, 'replied').length, 1);
});

check('Q06 terminal-before-link with no observation seam records reply-unobserved', () => {
  const l = lane('ooo-terminal-first-no-seam');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-ns', 'call-ns', 'sessions_send', 'x'));
  t.handleAgentEvent(lifecycleEvent('run-ns', TARGET, {
    phase: 'end', executionSettled: true, terminalReply: { disposition: 'visible', text: 'unrecoverable' },
  }));
  t.afterToolCall(...afterEvent(CALLER, 'run-ns', 'call-ns', 'sessions_send', {
    status: 'accepted', runId: 'run-ns', sessionKey: TARGET,
  }));
  const id = mintExchangeId([INSTALL, CALLER, 'run-ns', 'call-ns']);
  const replied = readOutbox(l, id, 'replied');
  assert.equal(replied.event.payload.message, null);
  assert.equal(t.records()[0].replyState, 'unobserved');
  for (const { body } of allWritten(l)) {
    assert.equal(body.includes('unrecoverable'), false, 'unobserved text must not be saved');
  }
});

check('Q06 after-before-before out of order: same exchange, one envelope per phase', () => {
  const l = lane('ooo-after-first');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  // Result observed first (no before yet).
  t.afterToolCall(...afterEvent(CALLER, 'run-oo', 'call-oo', 'sessions_send', {
    status: 'ok', runId: 'run-oo', sessionKey: TARGET, reply: 'out of order reply',
  }));
  const id = mintExchangeId([INSTALL, CALLER, 'run-oo', 'call-oo']);
  assert.equal(outboxFiles(l, id, 'requested').length, 0);
  // Before arrives second.
  t.beforeToolCall(...beforeEvent(CALLER, 'run-oo', 'call-oo', 'sessions_send', 'out of order request'));
  assert.equal(outboxFiles(l, id, 'requested').length, 1);
  assert.equal(outboxFiles(l, id, 'replied').length, 1);
  assert.equal(t.records().length, 1);
});

check('terminal for an unknown run never attaches to the newest record', () => {
  const l = lane('no-nearest');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-known', 'call-k', 'sessions_send', 'a'));
  t.afterToolCall(...afterEvent(CALLER, 'run-known', 'call-k', 'sessions_send', {
    status: 'accepted', runId: 'run-known', sessionKey: TARGET,
  }));
  const id = mintExchangeId([INSTALL, CALLER, 'run-known', 'call-k']);
  t.handleAgentEvent(lifecycleEvent('run-unknown', TARGET, {
    phase: 'end', executionSettled: true, terminalReply: { disposition: 'visible', text: 'someone elses text' },
  }));
  assert.equal(outboxFiles(l, id, 'replied').length, 0);
  for (const { body } of allWritten(l)) {
    assert.equal(body.includes('someone elses text'), false);
  }
});

// ── 6. Lifecycle terminal gating ────────────────────────────────────────
check('finishing is not terminal and never carries executionSettled', () => {
  const l = lane('finishing');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-fin', 'call-fin', 'sessions_send', 'x'));
  t.afterToolCall(...afterEvent(CALLER, 'run-fin', 'call-fin', 'sessions_send', {
    status: 'accepted', runId: 'run-fin', sessionKey: TARGET,
  }));
  const res = t.handleAgentEvent(lifecycleEvent('run-fin', TARGET, { phase: 'finishing' }));
  assert.equal(res.ok, false); // finishing is not a terminal phase, and never settles
  const id = mintExchangeId([INSTALL, CALLER, 'run-fin', 'call-fin']);
  assert.equal(outboxFiles(l, id, 'replied').length, 0);
});

check('receiver session mismatch is a conflict, not a join', () => {
  const l = lane('mismatch');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-mm', 'call-mm', 'sessions_send', 'x'));
  t.afterToolCall(...afterEvent(CALLER, 'run-mm', 'call-mm', 'sessions_send', {
    status: 'accepted', runId: 'run-mm', sessionKey: TARGET,
  }));
  const res = t.handleAgentEvent(lifecycleEvent('run-mm', 'agent:other:subagent:z', {
    phase: 'end', executionSettled: true, terminalReply: { disposition: 'visible', text: 'wrong receiver' },
  }));
  assert.equal(res.reason, 'receiver-mismatch');
  const id = mintExchangeId([INSTALL, CALLER, 'run-mm', 'call-mm']);
  assert.equal(outboxFiles(l, id, 'replied').length, 0);
  for (const { body } of allWritten(l)) assert.equal(body.includes('wrong receiver'), false);
});

check('error terminal without a visible reply records replied with null text', () => {
  const l = lane('error-terminal');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-er', 'call-er', 'sessions_send', 'x'));
  t.afterToolCall(...afterEvent(CALLER, 'run-er', 'call-er', 'sessions_send', {
    status: 'accepted', runId: 'run-er', sessionKey: TARGET,
  }));
  t.handleAgentEvent(lifecycleEvent('run-er', TARGET, { phase: 'error', executionSettled: true, terminalReply: { disposition: 'silent' } }));
  const id = mintExchangeId([INSTALL, CALLER, 'run-er', 'call-er']);
  const replied = readOutbox(l, id, 'replied');
  assert.equal(replied.event.payload.message, null);
  assert.equal(t.records()[0].replyState, 'unobserved');
});

// ── 7. Q06 uncertain send ───────────────────────────────────────────────
check('Q06 timeout/error with sentBeforeError is uncertain, never safely unsent', () => {
  const l = lane('uncertain');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-u', 'call-u', 'sessions_send', 'x'));
  t.afterToolCall(...afterEvent(CALLER, 'run-u', 'call-u', 'sessions_send', {
    status: 'timeout', runId: 'run-u', error: 'timed out', sentBeforeError: true, sessionKey: TARGET,
  }));
  const id = mintExchangeId([INSTALL, CALLER, 'run-u', 'call-u']);
  const phaseFile = readOutbox(l, id, 'uncertain');
  assert.equal(phaseFile.event.payload.nativeStatus, 'timeout');
  assert.equal(phaseFile.event.payload.correlationStatus, 'unresolved');
});

check('error before any send is failed, not uncertain', () => {
  const l = lane('failed');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-f', 'call-f', 'sessions_send', 'x'));
  t.afterToolCall(...afterEvent(CALLER, 'run-f', 'call-f', 'sessions_send', {
    status: 'error', runId: 'run-f', error: 'no such session', sentBeforeError: false,
  }));
  const id = mintExchangeId([INSTALL, CALLER, 'run-f', 'call-f']);
  assert.equal(readOutbox(l, id, 'failed').event.payload.nativeStatus, 'error');
  assert.equal(outboxFiles(l, id, 'uncertain').length, 0);
});

check('an unsupported native status is a diagnostic, never accepted into the envelope', () => {
  const l = lane('unsupported-status');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-us', 'call-us', 'sessions_send', 'x'));
  const res = t.afterToolCall(...afterEvent(CALLER, 'run-us', 'call-us', 'sessions_send', {
    status: 'brand_new_status', runId: 'run-us', reply: 'nope',
  }));
  assert.equal(res.reason, 'unsupported-native-status');
  assert.equal(t.health.unsupportedNative, 1);
  const id = mintExchangeId([INSTALL, CALLER, 'run-us', 'call-us']);
  assert.equal(outboxFiles(l, id, 'replied').length, 0);
  for (const { body } of allWritten(l)) assert.equal(body.includes('nope'), false);
});

// ── 8. Privacy: suppression BEFORE persistence and outbox ───────────────
check('private direct hq-* caller: no request or reply text anywhere on disk', () => {
  const l = lane('private-direct');
  const t = makeTelemetry(l);
  const secret = 'PRIVATE-OWNER-TEXT-1';
  t.beforeToolCall(...beforeEvent('agent:ceo:hq-chat:session-1', 'run-p', 'call-p', 'sessions_send', secret));
  t.afterToolCall(...afterEvent('agent:ceo:hq-chat:session-1', 'run-p', 'call-p', 'sessions_send', {
    status: 'ok', runId: 'run-p', sessionKey: 'agent:research:subagent:r1', reply: secret,
  }));
  const id = mintExchangeId([INSTALL, 'agent:ceo:hq-chat:session-1', 'run-p', 'call-p']);
  const replied = readOutbox(l, id, 'replied');
  assert.equal(replied.event.payload.message, null);
  const requested = readOutbox(l, id, 'requested');
  assert.equal(requested.event.payload.message, null);
  for (const { body } of allWritten(l)) assert.equal(body.includes(secret), false, 'private text reached disk');
});

check('grandchild under an independent subagent key inherits private ancestry', () => {
  const l = lane('private-grandchild');
  const t = makeTelemetry(l);
  const secret = 'PRIVATE-GRANDCHILD-TEXT-2';
  // Generation 1: private root spawns an independent subagent key.
  t.beforeToolCall(...beforeEvent('agent:ceo:hq-chat:root', 'run-g1', 'call-g1', 'sessions_spawn', 'go'));
  t.afterToolCall(...afterEvent('agent:ceo:hq-chat:root', 'run-g1', 'call-g1', 'sessions_spawn', {
    status: 'accepted', childSessionKey: 'agent:research:subagent:child', runId: 'run-child',
  }));
  // Generation 2: the child (key gives no hint of its private parent) spawns again.
  t.beforeToolCall(...beforeEvent('agent:research:subagent:child', 'run-g2', 'call-g2', 'sessions_spawn', 'go deeper'));
  t.afterToolCall(...afterEvent('agent:research:subagent:child', 'run-g2', 'call-g2', 'sessions_spawn', {
    status: 'accepted', childSessionKey: 'agent:ops:subagent:grandchild', runId: 'run-grandchild',
  }));
  // Generation 3: the grandchild sends a message and gets a reply.
  t.beforeToolCall(...beforeEvent('agent:ops:subagent:grandchild', 'run-g3', 'call-g3', 'sessions_send', secret));
  t.afterToolCall(...afterEvent('agent:ops:subagent:grandchild', 'run-g3', 'call-g3', 'sessions_send', {
    status: 'ok', runId: 'run-g3', sessionKey: 'agent:legal:subagent:x', reply: secret,
  }));
  const id = mintExchangeId([INSTALL, 'agent:ops:subagent:grandchild', 'run-g3', 'call-g3']);
  const replied = readOutbox(l, id, 'replied');
  assert.notEqual(replied, null, 'the exchange must still be captured, minus text');
  assert.equal(replied.event.payload.message, null);
  assert.equal(readOutbox(l, id, 'requested').event.payload.message, null);
  for (const { body } of allWritten(l)) assert.equal(body.includes(secret), false, 'grandchild text reached disk');
});

check('terminal-before-link under private ancestry keeps text out of persistence', () => {
  const l = lane('private-ooo');
  const secret = 'PRIVATE-OOO-TEXT-3';
  const t = makeTelemetry(l);
  t.beforeToolCall(...beforeEvent('agent:ceo:hq-chat:r', 'run-po', 'call-po', 'sessions_send', secret));
  // Terminal with visible text arrives before the linking result.
  t.handleAgentEvent(lifecycleEvent('run-po', 'agent:research:subagent:r', {
    phase: 'end', executionSettled: true, terminalReply: { disposition: 'visible', text: secret },
  }));
  t.afterToolCall(...afterEvent('agent:ceo:hq-chat:r', 'run-po', 'call-po', 'sessions_send', {
    status: 'accepted', runId: 'run-po', sessionKey: 'agent:research:subagent:r',
  }));
  const id = mintExchangeId([INSTALL, 'agent:ceo:hq-chat:r', 'run-po', 'call-po']);
  assert.equal(readOutbox(l, id, 'replied').event.payload.message, null);
  for (const { body } of allWritten(l)) assert.equal(body.includes(secret), false, 'terminal-before-link private text reached disk');
});

check('unknown ancestry is metadata only, never presumed public', () => {
  const l = lane('unknown');
  const secret = 'UNKNOWN-ANCESTRY-TEXT-4';
  const t = makeTelemetry(l); // no publicSessionKeys, no link to a public root
  t.beforeToolCall(...beforeEvent('agent:finance:subagent:u1', 'run-un', 'call-un', 'sessions_send', secret));
  t.afterToolCall(...afterEvent('agent:finance:subagent:u1', 'run-un', 'call-un', 'sessions_send', {
    status: 'ok', runId: 'run-un', sessionKey: 'agent:ops:subagent:u2', reply: secret,
  }));
  const id = mintExchangeId([INSTALL, 'agent:finance:subagent:u1', 'run-un', 'call-un']);
  assert.equal(readOutbox(l, id, 'requested').event.payload.message, null);
  assert.equal(readOutbox(l, id, 'replied').event.payload.message, null);
  assert.equal(readOutbox(l, id, 'accepted'), null);
  for (const { body } of allWritten(l)) assert.equal(body.includes(secret), false, 'unknown-ancestry text reached disk');
  // The exchange is still recorded as coverage metadata.
  assert.equal(readOutbox(l, id, 'replied').event.taskId, null);
});

check('a model-authored task id in params cannot launder privacy into capture', () => {
  const l = lane('launder');
  const secret = 'LAUNDERED-TEXT-5';
  const t = makeTelemetry(l);
  const [event, ctx] = beforeEvent('agent:ceo:hq-chat:s', 'run-l', 'call-l', 'sessions_send', secret);
  t.beforeToolCall({ ...event, params: { ...event.params, taskId: 'task-123', label: 'public task' } }, ctx);
  t.afterToolCall(...afterEvent('agent:ceo:hq-chat:s', 'run-l', 'call-l', 'sessions_send', {
    status: 'ok', runId: 'run-l', sessionKey: 'agent:x:subagent:y', reply: secret, taskId: 'task-123',
  }));
  const id = mintExchangeId([INSTALL, 'agent:ceo:hq-chat:s', 'run-l', 'call-l']);
  const replied = readOutbox(l, id, 'replied');
  assert.equal(replied.event.payload.message, null);
  assert.equal(replied.event.taskId, null);
  for (const { body } of allWritten(l)) assert.equal(body.includes(secret), false);
});

// ── 9. Success control: trusted public ancestry still captures ──────────
check('trusted public ancestry is the success control and does capture text', () => {
  const l = lane('public-control');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  const text = 'PUBLIC-TASK-TEXT-OK';
  t.beforeToolCall(...beforeEvent(CALLER, 'run-pub', 'call-pub', 'sessions_send', text));
  t.afterToolCall(...afterEvent(CALLER, 'run-pub', 'call-pub', 'sessions_send', {
    status: 'ok', runId: 'run-pub', sessionKey: TARGET, reply: text,
  }));
  const id = mintExchangeId([INSTALL, CALLER, 'run-pub', 'call-pub']);
  assert.equal(readOutbox(l, id, 'requested').event.payload.message, text);
  assert.equal(readOutbox(l, id, 'replied').event.payload.message, text);
  assert.equal(t.records()[0].privacy, 'public');
});

check('a public target reached through the ancestry map still captures', () => {
  const l = lane('public-linked');
  const t = makeTelemetry(l, { config: { publicSessionKeys: ['agent:board:root'] } });
  // Private classification propagates transitively, and so does public: the root
  // is public, so its proven descendant chain stays public.
  t.beforeToolCall(...beforeEvent('agent:board:root', 'run-r1', 'call-r1', 'sessions_spawn', 'go'));
  t.afterToolCall(...afterEvent('agent:board:root', 'run-r1', 'call-r1', 'sessions_spawn', {
    status: 'accepted', childSessionKey: 'agent:eng:subagent:c', runId: 'run-rc',
  }));
  assert.equal(t.ancestry.classify('agent:eng:subagent:c'), 'public');
});

// ── 10. Duplicate and conflict handling ─────────────────────────────────
check('same observation twice dedupes through the exchange phase key', () => {
  const l = lane('dedupe');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  const args = afterEvent(CALLER, 'run-dd', 'call-dd', 'sessions_send', {
    status: 'ok', runId: 'run-dd', sessionKey: TARGET, reply: 'same reply',
  });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-dd', 'call-dd', 'sessions_send', 'x'));
  t.afterToolCall(...args);
  const first = t.afterToolCall(...args);
  assert.equal(first.phase, 'replied');
  const id = mintExchangeId([INSTALL, CALLER, 'run-dd', 'call-dd']);
  assert.equal(outboxFiles(l, id, 'replied').length, 1, 'a duplicate must not append a second envelope');
  // The phase was already proven, so the same observation is not re-emitted.
  const rec = t.records()[0];
  assert.equal(Object.keys(rec.emits).filter((k) => k === 'replied').length, 1);
});

check('same phase key with different content is a diagnostic conflict, not an overwrite', () => {
  const l = lane('conflict');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-cf', 'call-cf', 'sessions_send', 'x'));
  t.afterToolCall(...afterEvent(CALLER, 'run-cf', 'call-cf', 'sessions_send', {
    status: 'ok', runId: 'run-cf', sessionKey: TARGET, reply: 'first content',
  }));
  // A second, different outcome for the same phase.
  t.afterToolCall(...afterEvent(CALLER, 'run-cf', 'call-cf', 'sessions_send', {
    status: 'ok', runId: 'run-cf', sessionKey: TARGET, reply: 'different content',
  }));
  const id = mintExchangeId([INSTALL, CALLER, 'run-cf', 'call-cf']);
  assert.equal(readOutbox(l, id, 'replied').event.payload.message, 'first content');
  assert.equal(t.records()[0].conflicts.length >= 1, true);
  assert.equal(t.health.conflicts >= 1, true);
});

// ── 11. Restart ─────────────────────────────────────────────────────────
check('restart does not lose a pending join', () => {
  const l = lane('restart-lose');
  const first = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  first.beforeToolCall(...beforeEvent(CALLER, 'run-rs', 'call-rs', 'sessions_send', 'x'));
  first.afterToolCall(...afterEvent(CALLER, 'run-rs', 'call-rs', 'sessions_send', {
    status: 'accepted', runId: 'run-target-rs', sessionKey: TARGET,
  }));
  // Process restarts: a fresh telemetry object over the same workspace.
  const second = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  const res = second.handleAgentEvent(lifecycleEvent('run-target-rs', TARGET, {
    phase: 'end', executionSettled: true, terminalReply: { disposition: 'visible', text: 'survived restart' },
  }));
  assert.equal(res.ok, true);
  const id = mintExchangeId([INSTALL, CALLER, 'run-rs', 'call-rs']);
  assert.equal(readOutbox(l, id, 'replied').event.payload.message, 'survived restart');
});

check('restart does not duplicate an already-proven join', () => {
  const l = lane('restart-dup');
  const first = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  first.beforeToolCall(...beforeEvent(CALLER, 'run-rd', 'call-rd', 'sessions_send', 'x'));
  first.afterToolCall(...afterEvent(CALLER, 'run-rd', 'call-rd', 'sessions_send', {
    status: 'ok', runId: 'run-rd', sessionKey: TARGET, reply: 'once only',
  }));
  const second = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  const id = mintExchangeId([INSTALL, CALLER, 'run-rd', 'call-rd']);
  const before = fs.readdirSync(l.outboxDir).length;
  // Replay of the same result after restart.
  second.afterToolCall(...afterEvent(CALLER, 'run-rd', 'call-rd', 'sessions_send', {
    status: 'ok', runId: 'run-rd', sessionKey: TARGET, reply: 'once only',
  }));
  second.handleAgentEvent(lifecycleEvent('run-rd', TARGET, {
    phase: 'end', executionSettled: true, terminalReply: { disposition: 'visible', text: 'once only' },
  }));
  assert.equal(fs.readdirSync(l.outboxDir).length, before, 'restart replay appended new envelopes');
  assert.equal(readOutbox(l, id, 'replied').event.payload.message, 'once only');
});

// ── 12. Boundedness ─────────────────────────────────────────────────────
check('correlation store is bounded by entry count and reports degradation', () => {
  const l = lane('bounds-entries');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] }, bounds: { ...BOUNDS, maxEntries: 3 } });
  for (let i = 0; i < 6; i += 1) {
    t.beforeToolCall(...beforeEvent(CALLER, `run-b${i}`, `call-b${i}`, 'sessions_send', 'x'));
  }
  assert.equal(t.store.size() <= 3, true, `store grew past its bound: ${t.store.size()}`);
  assert.equal(t.store.health.dropped >= 1, true);
  assert.equal(t.store.health.degraded, true);
});

check('correlation store is bounded by bytes and reports degradation', () => {
  const l = lane('bounds-bytes');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] }, bounds: { ...BOUNDS, maxBytes: 700 } });
  for (let i = 0; i < 10; i += 1) {
    t.beforeToolCall(...beforeEvent(CALLER, `run-by${i}`, `call-by${i}`, 'sessions_send', 'x'));
  }
  assert.equal(t.store.byteSize() <= 700, true, `store bytes past bound: ${t.store.byteSize()}`);
  assert.equal(t.store.health.dropped >= 1, true);
});

check('outbox is bounded and sets degraded rather than blocking', () => {
  const l = lane('bounds-outbox');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] }, bounds: { ...BOUNDS, outboxMaxFiles: 2 } });
  for (let i = 0; i < 5; i += 1) {
    t.beforeToolCall(...beforeEvent(CALLER, `run-o${i}`, `call-o${i}`, 'sessions_send', 'x'));
  }
  const files = fs.readdirSync(l.outboxDir).filter((n) => !n.endsWith('.diagnostic.json'));
  assert.equal(files.length <= 2, true, `outbox grew past bound: ${files.length}`);
  assert.equal(t.outbox.health.degraded, true);
  assert.equal(t.outbox.health.dropped >= 1, true);
});

check('outbox rejects an oversize payload by encoded bytes, not string length', () => {
  const l = lane('bounds-payload');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] }, bounds: { ...BOUNDS, outboxPayloadBytes: 400 } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-big', 'call-big', 'sessions_send', 'z'.repeat(2000)));
  const id = mintExchangeId([INSTALL, CALLER, 'run-big', 'call-big']);
  assert.equal(outboxFiles(l, id, 'requested').length, 0);
  assert.equal(t.outbox.health.dropped >= 1, true);
  assert.equal(t.outbox.health.degraded, true);
});

// ── 13. Passivity: hook failures never disturb the call ─────────────────
check('a handler failure is swallowed and reports only a health fact', () => {
  const l = lane('passive');
  const t = makeTelemetry(l);
  const res = t.beforeToolCall(null, null);
  assert.equal(res.ok, false);
  assert.equal(typeof res.reason, 'string');
  // The hooks as registered are void: they return undefined to the host.
  const module = fs.readFileSync(new URL('./dist/index.js', import.meta.url), 'utf8');
  assert.equal(module.includes('api.on(\'before_tool_call\''), true);
  assert.equal(module.includes('registerTool'), false, 'must not replace or register tools');
  assert.equal(module.includes('api.registerTool'), false, 'must not replace or register tools');
});

// ── 14. registration shape on the installed plugin surface ──────────────
check('registration uses the exact native hook names, matcher and subscription id', () => {
  const l = lane('registration');
  const registered = { on: [], subscriptions: [], tools: 0 };
  const host = {
    id: 'agent-exchange-telemetry',
    rootDir: l.root,
    pluginConfig: { companyId: COMPANY, installationId: INSTALL, publicSessionKeys: [CALLER] },
    logger: { warn() {}, error() {} },
    on: (hookName, handler, opts) => registered.on.push({ hookName, handler, opts }),
    agent: { events: { registerAgentEventSubscription: (sub) => registered.subscriptions.push(sub) } },
    registerTool: () => { registered.tools += 1; },
  };
  const telemetry = registerPlugin(host);
  assert.notEqual(telemetry, null);
  assert.deepEqual(registered.on.map((h) => h.hookName), ['before_tool_call', 'after_tool_call']);
  for (const h of registered.on) assert.deepEqual([...h.opts.matcher], ['sessions_send', 'sessions_spawn']);
  assert.equal(registered.tools, 0, 'registration must register no tool');
  assert.equal(registered.subscriptions.length, 1);
  const sub = registered.subscriptions[0];
  assert.equal(sub.id, 'hq-exchange-terminal');
  assert.deepEqual([...sub.streams], ['lifecycle']);
  assert.equal(typeof sub.handle, 'function');
  // Registered handlers resolve to void, so the business call always proceeds.
  const beforeRes = registered.on[0].handler(...beforeEvent(CALLER, 'run-reg', 'call-reg', 'sessions_send', 'hi'));
  const afterRes = registered.on[1].handler(...afterEvent(CALLER, 'run-reg', 'call-reg', 'sessions_send', { status: 'ok', runId: 'run-reg', sessionKey: TARGET, reply: 'yo' }));
  assert.equal(beforeRes, undefined);
  assert.equal(afterRes, undefined);
  assert.equal(typeof sub.handle(lifecycleEvent('run-reg', TARGET, { phase: 'end', executionSettled: true })), 'undefined');
  // The observation lands in the workspace the trusted config named.
  const id = mintExchangeId([INSTALL, CALLER, 'run-reg', 'call-reg']);
  const files = fs.readdirSync(path.join(l.root, 'hq-telemetry', 'outbox'));
  assert.equal(files.includes(`exchange_${id}_requested.json`), true);
  assert.equal(files.includes(`exchange_${id}_replied.json`), true);
});

check('executionSettled absent on a terminal-shaped phase is not treated as terminal', () => {
  const l = lane('settled-required');
  const t = makeTelemetry(l, { config: { publicSessionKeys: [CALLER] } });
  t.beforeToolCall(...beforeEvent(CALLER, 'run-se', 'call-se', 'sessions_send', 'x'));
  t.afterToolCall(...afterEvent(CALLER, 'run-se', 'call-se', 'sessions_send', {
    status: 'accepted', runId: 'run-se', sessionKey: TARGET,
  }));
  const res = t.handleAgentEvent(lifecycleEvent('run-se', TARGET, { phase: 'end' }));
  assert.deepEqual(res, { ok: false, reason: 'not-settled' });
  const id = mintExchangeId([INSTALL, CALLER, 'run-se', 'call-se']);
  assert.equal(outboxFiles(l, id, 'replied').length, 0);
});

// ── Report ──────────────────────────────────────────────────────────────
process.stdout.write(`\n${passed} passed, ${failures.length} failed\n`);
if (failures.length > 0) {
  for (const { name, error } of failures) process.stdout.write(`- ${name}: ${error && error.message}\n`);
  process.exitCode = 1;
}
fs.rmSync(ROOT, { recursive: true, force: true });
