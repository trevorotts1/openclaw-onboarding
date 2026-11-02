// ============================================================================
// service-client-link.test.mjs — a link the service mints actually opens the page
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/service-client-link.test.mjs
//
// ST-11B (Fable repair plan, 2026-10-30). link.js mints a 256-bit key
// (keys.js KEY_BYTES = 32) and returns `#k=<64 lowercase hex>`; the page's
// service-client.js accepted exactly 32 hex, so a real minted link installed
// no studioService and the page stayed on "not connected" forever.
//
// These tests mint through the REAL producer, hand that exact fragment to the
// SHIPPED page module (location and fetch faked — no browser, no network) and
// then resolve the same key through the service's own authorization door
// (isolation.resolveKey). A 32-hex link minted before the key length changed
// must still work; malformed lengths must not.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';

import { mintLink } from '../src/link.js';
import { buildKeyRecord } from '../src/keys.js';
import { resolveKey } from '../src/isolation.js';
import { randomClientId } from '../src/ids.js';
import { memStore } from './fakes.mjs';

const ORIGIN = 'https://studio.example';
const T0 = Date.UTC(2026, 9, 30, 12, 0, 0);
const CLIENT_URL = new URL('../../ui/service-client.js', import.meta.url).href;

let importCount = 0;

/** Import a fresh copy of the shipped page module under a faked page. */
async function loadPage(hash) {
  const calls = [];
  globalThis.location = { hash, origin: ORIGIN };
  globalThis.fetch = async (path, init = {}) => {
    calls.push({ path: String(path), method: init.method || 'GET', headers: init.headers || {} });
    return { ok: true, status: 200, json: async () => ({ ok: true }) };
  };
  delete globalThis.studioService;
  importCount += 1;
  return { api: await import(`${CLIENT_URL}?v=${importCount}`), calls };
}

test('a freshly minted link opens the page and its key authorizes at the service', async () => {
  const store = memStore();
  const clientId = randomClientId();
  const minted = await mintLink(store, { clientId, origin: ORIGIN, rotate: false, nowMs: T0 });
  assert.equal(minted.ok, true);
  const secret = minted.link.slice(minted.link.indexOf('#k=') + 3);
  assert.match(secret, /^[0-9a-f]{64}$/, 'the producer mints 64 lowercase hex');

  const { api, calls } = await loadPage(`#k=${secret}&p=home`);
  assert.equal(api.linkKey(), secret, 'the page must read the key the service actually minted');
  assert.equal(api.personalLink(), `${ORIGIN}/#k=${secret}`);
  assert.ok(globalThis.studioService, 'a minted link must install studioService or the page stays "not connected"');

  await globalThis.studioService.getSession();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, '/api/studio/session', 'same-origin path, no key in the query string');
  assert.equal(calls[0].headers['x-ds-key'], secret, 'the key travels only in x-ds-key');
  assert.ok(!calls[0].path.includes(secret), 'the fragment key must never reach the request URL');

  const resolved = await resolveKey(store, secret);
  assert.equal(resolved.ok, true, 'the key the page accepted is the key the service authorizes');
  assert.equal(resolved.record.client_id, clientId);
  assert.equal(resolved.record.kind, 'link');
});

test('a legacy 32-hex link still opens the page and still resolves', async () => {
  const store = memStore();
  const clientId = randomClientId();
  const legacy = '0123456789abcdef0123456789abcdef';
  const record = await buildKeyRecord({ clientId, kind: 'link', label: 'personal link', secret: legacy, nowMs: T0 });
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));

  const { api } = await loadPage(`#k=${legacy}`);
  assert.equal(api.linkKey(), legacy);
  assert.ok(globalThis.studioService);
  assert.equal((await resolveKey(store, legacy)).ok, true, 'a legacy link key still resolves at the service');
});

test('malformed link keys install nothing and never reach the service', async () => {
  const cases = [
    ['no hash at all', ''],
    ['a hash without a key', '#p=questions'],
    ['an empty key', '#k='],
    ['31 hex (one short)', `#k=${'a'.repeat(31)}`],
    ['33 hex (one long)', `#k=${'a'.repeat(33)}`],
    ['63 hex (one short of a mint)', `#k=${'a'.repeat(63)}`],
    ['65 hex (one past a mint)', `#k=${'a'.repeat(65)}`],
    ['32 hex plus a non-hex character', `#k=${'a'.repeat(32)}z`],
    ['uppercase 64 hex', `#k=${'A'.repeat(64)}`],
    ['64 characters that are not hex', `#k=${'g'.repeat(64)}`],
    ['64 hex plus a trailing newline', `#k=${'a'.repeat(64)}%0A`],
  ];
  for (const [label, hash] of cases) {
    const { api, calls } = await loadPage(hash);
    assert.equal(api.linkKey(), null, label);
    assert.equal(api.personalLink(), null, label);
    assert.equal(globalThis.studioService, undefined, label);
    assert.equal(calls.length, 0, `${label} must not call the service`);
  }
});
