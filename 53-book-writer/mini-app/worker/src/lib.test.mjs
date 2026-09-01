// ============================================================================
// lib.test.mjs — U02 Worker core self-test (node --test, pure logic only)
//
// Covers the master-plan contract for the Worker core:
//   - a VALID token passes token validation + misfit + order enforcement
//   - tampered / expired / unknown / consumed (replayed) token → 401 reason
//   - misfit (wrong slug or phase vs the binding) → 401
//   - order enforcement: skipping ahead or going backwards → 401
//   - per-step dedupe: first submit INCR == 1 (accepted); replay > 1 (rejected)
//   - config load + SPA inject + 401 page shapes
//
// No Cloudflare bindings: all logic runs through an in-memory fake `store`.
// ============================================================================

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  validateTokenRow,
  checkMisfit,
  assertPhaseAllowed,
  lookupToken,
  loadPhaseConfig,
  loadRunState,
  consumeStep,
  markBindingConsumed,
  loadAppShell,
  SPA_INJECT_TEMPLATE,
  render401,
  tokenKey,
  consumeStepKey,
  configObjectPath,
} from './lib.js';

// ---------------------------------------------------------------------------
// In-memory fake `store` adapter (mirrors the Cloudflare binding surface)
// ---------------------------------------------------------------------------
class FakeStore {
  constructor() {
    this.kv = new Map();
    this.objects = new Map();
    this.ctr = new Map();
  }
  async kvGet(key) {
    return this.kv.has(key) ? this.kv.get(key) : null;
  }
  async kvPut(key, val) {
    this.kv.set(key, val);
  }
  async incr(key) {
    const next = (this.ctr.get(key) || 0) + 1;
    this.ctr.set(key, next);
    return next;
  }
  async objectGet(path) {
    return this.objects.has(path) ? this.objects.get(path) : null;
  }
  seedObject(path, value) {
    this.objects.set(path, { value: JSON.stringify(value) });
  }
  seedObjectRaw(path, raw) {
    this.objects.set(path, { value: raw });
  }
}

const NOW = Date.now();
const FUTURE = NOW + 60 * 60 * 1000; // +1h

function validBinding(over = {}) {
  return {
    client_id: 'client_FAKE_A',
    location_id: 'loc_a_fake',
    slug: 'fake-a',
    phase_id: 'P0-INTAKE',
    run_id: 'run_test_1',
    exp: FUTURE,
    status: 'open',
    mode: 'full',
    ...over,
  };
}

// ---------------------------------------------------------------------------
// Token validation
// ---------------------------------------------------------------------------

test('valid token passes', () => {
  const v = validateTokenRow(validBinding(), NOW);
  assert.equal(v.ok, true);
});

test('null / missing token → UNKNOWN (401)', () => {
  assert.deepEqual(validateTokenRow(null, NOW), { ok: false, reason: 'UNKNOWN' });
  assert.deepEqual(validateTokenRow(undefined, NOW), { ok: false, reason: 'UNKNOWN' });
});

test('tampered token (missing required field) → MALFORMED (401)', () => {
  const row = validBinding();
  delete row.location_id; // a request-injected/forged destination must not survive
  assert.deepEqual(validateTokenRow(row, NOW), { ok: false, reason: 'MALFORMED' });
});

test('tampered token (bad status value) → MALFORMED (401)', () => {
  const row = validBinding({ status: 42 });
  assert.deepEqual(validateTokenRow(row, NOW), { ok: false, reason: 'MALFORMED' });
});

test('expired token → EXPIRED (401)', () => {
  const row = validBinding({ exp: NOW - 1 });
  assert.deepEqual(validateTokenRow(row, NOW), { ok: false, reason: 'EXPIRED' });
});

test('consumed token (already used) → CONSUMED (401)', () => {
  const row = validBinding({ status: 'consumed' });
  assert.deepEqual(validateTokenRow(row, NOW), { ok: false, reason: 'CONSUMED' });
});

test('done token (intake complete) → CONSUMED (401)', () => {
  const row = validBinding({ status: 'done' });
  assert.deepEqual(validateTokenRow(row, NOW), { ok: false, reason: 'CONSUMED' });
});

test('non-numeric exp → MALFORMED (401)', () => {
  const row = validBinding({ exp: 'tomorrow' });
  assert.deepEqual(validateTokenRow(row, NOW), { ok: false, reason: 'MALFORMED' });
});

// ---------------------------------------------------------------------------
// Misfit: binding is the SOLE authority for destination
// ---------------------------------------------------------------------------

test('matching slug + phase → ok', () => {
  const row = validBinding({ slug: 'fake-a', phase_id: 'GATE-1-title' });
  assert.deepEqual(checkMisfit(row, 'fake-a', 'GATE-1-title'), { ok: true });
});

test('wrong slug (token swapped to another client) → MISFIT (401)', () => {
  const row = validBinding({ slug: 'fake-a' });
  assert.deepEqual(checkMisfit(row, 'fake-b', 'P0-INTAKE'), { ok: false, reason: 'MISFIT' });
});

test('wrong phase → MISFIT (401)', () => {
  const row = validBinding({ slug: 'fake-a', phase_id: 'P0-INTAKE' });
  assert.deepEqual(checkMisfit(row, 'fake-a', 'GATE-1-title'), { ok: false, reason: 'MISFIT' });
});

// ---------------------------------------------------------------------------
// Order enforcement (resume-aware)
// ---------------------------------------------------------------------------

test('first phase with no run state → ok', () => {
  assert.deepEqual(assertPhaseAllowed(null, 'P0-INTAKE'), { ok: true });
});

test('non-first phase with no run state → ORDER (401)', () => {
  assert.deepEqual(assertPhaseAllowed(null, 'GATE-1-title'), { ok: false, reason: 'ORDER' });
});

test('same phase in progress (resume) → ok', () => {
  const state = {
    phase_order: ['P0-INTAKE', 'GATE-1-title'],
    current_phase: 'GATE-1-title',
  };
  assert.deepEqual(assertPhaseAllowed(state, 'GATE-1-title'), { ok: true });
});

test('next phase in sequence → ok', () => {
  const state = {
    phase_order: ['P0-INTAKE', 'GATE-1-title'],
    current_phase: 'P0-INTAKE',
  };
  assert.deepEqual(assertPhaseAllowed(state, 'GATE-1-title'), { ok: true });
});

test('skipping ahead (intake → gate2) → ORDER (401)', () => {
  const state = {
    phase_order: ['P0-INTAKE', 'GATE-1-title', 'GATE-2-outline'],
    current_phase: 'P0-INTAKE',
  };
  assert.deepEqual(assertPhaseAllowed(state, 'GATE-2-outline'), { ok: false, reason: 'ORDER' });
});

test('going backwards → ORDER (401)', () => {
  const state = {
    phase_order: ['P0-INTAKE', 'GATE-1-title'],
    current_phase: 'GATE-1-title',
  };
  assert.deepEqual(assertPhaseAllowed(state, 'P0-INTAKE'), { ok: false, reason: 'ORDER' });
});

test('unknown phase → UNKNOWN_PHASE (401)', () => {
  const state = {
    phase_order: ['P0-INTAKE', 'GATE-1-title'],
    current_phase: 'P0-INTAKE',
  };
  assert.deepEqual(assertPhaseAllowed(state, 'GATE-999-nope'), { ok: false, reason: 'UNKNOWN_PHASE' });
});

// ---------------------------------------------------------------------------
// Per-step dedupe (single-use per step; replay idempotent)
// ---------------------------------------------------------------------------

test('first submit → INCR == 1 (accepted)', async () => {
  const store = new FakeStore();
  const n = await consumeStep(store, 'run_test_1', 'P0-INTAKE', 'first_name');
  assert.equal(n, 1);
});

test('replay of a consumed step → INCR > 1 (rejected)', async () => {
  const store = new FakeStore();
  const k = consumeStepKey('run_test_1', 'P0-INTAKE', 'first_name');
  await store.incr(k); // a previous submit already consumed this step
  const n = await consumeStep(store, 'run_test_1', 'P0-INTAKE', 'first_name');
  assert.ok(n > 1, 'replay must return a count > 1 so the caller rejects it');
});

test('distinct steps do not collide (dedupe is per-step)', async () => {
  const store = new FakeStore();
  const a = await consumeStep(store, 'run_test_1', 'P0-INTAKE', 'first_name');
  const b = await consumeStep(store, 'run_test_1', 'P0-INTAKE', 'last_name');
  assert.equal(a, 1);
  assert.equal(b, 1); // separate step key, not blocked by the first
});

test('markBindingConsumed flips status so a later lookup fails', async () => {
  const store = new FakeStore();
  const token = 'tok_a';
  await store.kvPut(tokenKey(token), JSON.stringify(validBinding()));
  await markBindingConsumed(store, token, 'consumed');
  const row = await lookupToken(store, token);
  assert.equal(row.status, 'consumed');
  assert.deepEqual(validateTokenRow(row, NOW), { ok: false, reason: 'CONSUMED' });
});

// ---------------------------------------------------------------------------
// Config + SPA assembly
// ---------------------------------------------------------------------------

test('loadPhaseConfig reads the versioned per-client config path', async () => {
  const store = new FakeStore();
  store.seedObject('config/fake-a/P0-INTAKE:full.json', { id: 'P0-INTAKE', fields: [] });
  const cfg = await loadPhaseConfig(store, 'fake-a', 'P0-INTAKE', 'full');
  assert.deepEqual(cfg, { id: 'P0-INTAKE', fields: [] });
});

test('configObjectPath: P0-INTAKE carries the mode variant; gates do not', () => {
  assert.equal(configObjectPath('fake-a', 'P0-INTAKE', 'full'), 'config/fake-a/P0-INTAKE:full.json');
  assert.equal(configObjectPath('fake-a', 'P0-INTAKE', '4x3x3'), 'config/fake-a/P0-INTAKE:4x3x3.json');
  assert.equal(configObjectPath('fake-a', 'GATE-1-title', null), 'config/fake-a/GATE-1-title.json');
});

test('loadRunState parses a seeded run row', async () => {
  const store = new FakeStore();
  store.kv.set('run:run_test_1', JSON.stringify({ phase_order: ['P0-INTAKE'], current_phase: 'P0-INTAKE' }));
  const st = await loadRunState(store, 'run_test_1');
  assert.equal(st.current_phase, 'P0-INTAKE');
});

test('loadAppShell follows the pointer-flip atomic unit', async () => {
  const store = new FakeStore();
  store.seedObject('app/latest', { version: 'v1' });
  store.seedObjectRaw('app/v1/index.html', '<!doctype html><html><body>HOLDER</body></html>');
  const shell = await loadAppShell(store);
  assert.match(shell, /HOLDER/);
});

test('loadAppShell returns null when no pointer / bad version', async () => {
  const store = new FakeStore(); // nothing seeded
  assert.equal(await loadAppShell(store), null);
  store.seedObject('app/latest', { nope: true });
  assert.equal(await loadAppShell(store), null);
});

test('SPA_INJECT_TEMPLATE injects config + context JSON safely', () => {
  const shell = '<html><head></head><body><div id="app"></div></body></html>';
  const configJson = JSON.stringify({ id: 'P0-INTAKE', title: 'a"quote' });
  const contextJson = JSON.stringify({ slug: 'fake-a', run_id: 'run_x' });
  const doc = SPA_INJECT_TEMPLATE(shell, configJson, contextJson);
  assert.match(doc, /<script id="bw-bootstrap"/);
  assert.match(doc, /type="application\/json"/);
  assert.match(doc, /&quot;/); // inner quote was HTML-attribute-escaped
  assert.match(doc, /data-config="{&quot;id&quot;/); // JSON present + escaped, never raw "
  assert.match(doc, /fake-a/);
  assert.match(doc, /<\/body>/);
});

// ---------------------------------------------------------------------------
// 401 page (fail-closed: no config, no form)
// ---------------------------------------------------------------------------

test('render401 produces an HTML 401 page', () => {
  const html = render401('EXPIRED');
  assert.match(html, /<html/i);
  assert.match(html, /expired/i);
  assert.doesNotMatch(html, /<form/i); // no form surface on a 401
});
