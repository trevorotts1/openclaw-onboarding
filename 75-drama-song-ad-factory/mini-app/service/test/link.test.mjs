// ============================================================================
// link.test.mjs — Drama Studio service: personal link keys (DSF W1-studio-service-U1)
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/link.test.mjs
//
// Proves the BUILD-PLAN acceptance for W1-studio-service-U1:
//   mint returns a `#k=` link; a second call without rotate returns
//   `exists: true`; rotate revokes the old key (resolveKey ->
//   AF-DS-KEY-REVOKED); a link-kind caller is refused; the admin route mints
//   for a given client.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';

import { AF_LINK_KIND, linkRoute, mintLink } from '../src/link.js';
import { buildKeyRecord, mintKey } from '../src/keys.js';
import { resolveKey } from '../src/isolation.js';
import { randomClientId } from '../src/ids.js';
import { memStore } from './fakes.mjs';

const T0 = Date.UTC(2026, 9, 13, 12, 0, 0);
const ORIGIN = 'https://studio.example';
const ADMIN_KEY = 'admin-key-placeholder-for-tests';

/** The ctx shape W2 passes to every new route module (link/page/approvals). */
function makeCtx(store, opts = {}) {
  return {
    store,
    env: opts.env || {},
    auth: opts.auth,
    body: opts.body || {},
    url: new URL(`${ORIGIN}${opts.path || '/'}`),
    nowMs: opts.nowMs ?? T0,
    ok: (data, status = 200) =>
      new Response(JSON.stringify({ ok: true, ...data }), { status, headers: { 'content-type': 'application/json' } }),
    fail: (status, code, message) =>
      new Response(JSON.stringify({ ok: false, code, message }), { status, headers: { 'content-type': 'application/json' } }),
    isAdmin: opts.isAdmin,
  };
}

function post(path, body) {
  return new Request(`${ORIGIN}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
}

async function machineAuth(store, kind = 'machine') {
  const clientId = randomClientId();
  const minted = await mintKey();
  const record = await buildKeyRecord({ clientId, kind, secret: minted.secret, nowMs: T0 });
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));
  return { ok: true, client_id: clientId, record };
}

async function pointerOf(store, clientId) {
  const raw = await store.kvGet(`link:${clientId}`);
  return raw ? JSON.parse(raw) : null;
}

// ---------------------------------------------------------------------------
// mintLink
// ---------------------------------------------------------------------------

test('mintLink mints a link with the key in the fragment, storing only a fingerprint', async () => {
  const store = memStore();
  const clientId = randomClientId();

  const out = await mintLink(store, { clientId, origin: ORIGIN, rotate: false, nowMs: T0 });
  assert.equal(out.ok, true);
  assert.match(out.link, /^https:\/\/studio\.example\/#k=[0-9a-f]{64}$/, 'the link must carry #k=<128-bit key>');

  const secret = out.link.slice(out.link.indexOf('#k=') + 3);
  const pointer = await pointerOf(store, clientId);
  assert.ok(pointer, 'link:<client_id> pointer must exist');
  const record = JSON.parse(await store.kvGet(`key:${pointer.fingerprint}`));
  assert.equal(record.kind, 'link');
  assert.equal(record.status, 'active');
  assert.equal(record.client_id, clientId);
  assert.equal(pointer.created_at, T0);
  // SPEC §3: only the fingerprint is stored, never the key itself.
  for (const value of store._mem.values()) {
    assert.ok(!String(value).includes(secret), 'the raw link key must never be stored');
  }
});

test('mintLink: a second call without rotate returns exists:true and stores nothing new', async () => {
  const store = memStore();
  const clientId = randomClientId();
  const first = await mintLink(store, { clientId, origin: ORIGIN, rotate: false, nowMs: T0 });
  const firstPointer = await pointerOf(store, clientId);

  const second = await mintLink(store, { clientId, origin: ORIGIN, rotate: false, nowMs: T0 + 60_000 });
  assert.deepEqual(second, { ok: true, link: null, exists: true });
  assert.deepEqual(await pointerOf(store, clientId), firstPointer, 'the active pointer must not move');
  assert.equal(await store.kvGet(`key:${firstPointer.fingerprint}`) !== null, true);
  assert.equal((await store.kvList('key:')).length, 1, 'no second key may be minted');
  assert.notEqual(second.link, first.link);
});

test('mintLink: rotate revokes the old key and moves the pointer', async () => {
  const store = memStore();
  const clientId = randomClientId();
  const first = await mintLink(store, { clientId, origin: ORIGIN, rotate: false, nowMs: T0 });
  const firstSecret = first.link.slice(first.link.indexOf('#k=') + 3);
  const oldPointer = await pointerOf(store, clientId);

  const rotated = await mintLink(store, { clientId, origin: ORIGIN, rotate: true, nowMs: T0 + 60_000 });
  assert.ok(rotated.link && rotated.link.includes('#k='), 'rotate must return a fresh link');
  const newSecret = rotated.link.slice(rotated.link.indexOf('#k=') + 3);
  assert.notEqual(newSecret, firstSecret);

  const oldKey = await resolveKey(store, firstSecret);
  assert.equal(oldKey.ok, false, 'the old link must stop working at once');
  assert.equal(oldKey.code, 'AF-DS-KEY-REVOKED');

  const newKey = await resolveKey(store, newSecret);
  assert.equal(newKey.ok, true, 'the new link must resolve');
  assert.equal(newKey.record.kind, 'link');

  const newPointer = await pointerOf(store, clientId);
  assert.notEqual(newPointer.fingerprint, oldPointer.fingerprint, 'the pointer must be replaced');
  const oldRecord = JSON.parse(await store.kvGet(`key:${oldPointer.fingerprint}`));
  assert.equal(oldRecord.status, 'revoked', 'the old record must be marked revoked');
});

// ---------------------------------------------------------------------------
// linkRoute
// ---------------------------------------------------------------------------

test('linkRoute: a machine key mints through POST /api/studio/link', async () => {
  const store = memStore();
  const auth = await machineAuth(store, 'machine');
  const ctx = makeCtx(store, { auth, path: '/api/studio/link', body: { rotate: false } });

  const res = await linkRoute(post('/api/studio/link', { rotate: false }), ctx);
  const json = await res.json();
  assert.equal(res.status, 200);
  assert.equal(json.ok, true);
  assert.match(json.link, /^https:\/\/studio\.example\/#k=[0-9a-f]{64}$/);

  const again = await linkRoute(
    post('/api/studio/link', { rotate: false }),
    makeCtx(store, { auth, path: '/api/studio/link', body: { rotate: false } }),
  );
  const againJson = await again.json();
  assert.equal(againJson.link, null);
  assert.equal(againJson.exists, true);
});

test('linkRoute: a link-kind caller is refused 403 AF-DS-LINK-KIND', async () => {
  const store = memStore();
  const auth = await machineAuth(store, 'link');
  const res = await linkRoute(
    post('/api/studio/link', { rotate: false }),
    makeCtx(store, { auth, path: '/api/studio/link', body: { rotate: false } }),
  );
  const json = await res.json();
  assert.equal(res.status, 403);
  assert.equal(json.ok, false);
  assert.equal(json.code, AF_LINK_KIND);
  assert.equal(await pointerOf(store, auth.client_id), null, 'nothing may be minted for a refused caller');
});

test('linkRoute: the admin route mints for a given client and always rotates', async () => {
  const store = memStore();
  const clientId = randomClientId();
  const ctx = () =>
    makeCtx(store, {
      path: '/api/studio/admin/link',
      body: { admin_key: ADMIN_KEY, client_id: clientId },
      isAdmin: (env, presented) => Boolean(env && env.DS_ADMIN_KEY && presented === env.DS_ADMIN_KEY),
      env: { DS_ADMIN_KEY: ADMIN_KEY },
    });

  const res = await linkRoute(post('/api/studio/admin/link', { admin_key: ADMIN_KEY, client_id: clientId }), ctx());
  const json = await res.json();
  assert.equal(res.status, 200);
  assert.equal(json.ok, true);
  assert.match(json.link, /^https:\/\/studio\.example\/#k=[0-9a-f]{64}$/);
  const pointer = await pointerOf(store, clientId);
  assert.ok(pointer, 'the admin mint must store the pointer');

  // A second admin mint always rotates: the first link dies.
  const firstSecret = json.link.slice(json.link.indexOf('#k=') + 3);
  const second = await linkRoute(post('/api/studio/admin/link', { admin_key: ADMIN_KEY, client_id: clientId }), ctx());
  const secondJson = await second.json();
  assert.notEqual(secondJson.link, json.link);
  assert.equal((await resolveKey(store, firstSecret)).code, 'AF-DS-KEY-REVOKED');
  assert.notEqual((await pointerOf(store, clientId)).fingerprint, pointer.fingerprint, 'the pointer must move');
});

test('linkRoute: a wrong admin key is refused', async () => {
  const store = memStore();
  const res = await linkRoute(
    post('/api/studio/admin/link', { admin_key: 'wrong', client_id: randomClientId() }),
    makeCtx(store, {
      path: '/api/studio/admin/link',
      body: { admin_key: 'wrong', client_id: randomClientId() },
      isAdmin: (env, presented) => Boolean(env && env.DS_ADMIN_KEY && presented === env.DS_ADMIN_KEY),
      env: { DS_ADMIN_KEY: ADMIN_KEY },
    }),
  );
  const json = await res.json();
  assert.equal(res.status, 403);
  assert.equal(json.code, 'AF-DS-ADMIN-REFUSED');
});

test('linkRoute: another path or method is not its own (null)', async () => {
  const store = memStore();
  const auth = await machineAuth(store, 'machine');
  assert.equal(await linkRoute(post('/api/studio/session'), makeCtx(store, { auth, path: '/api/studio/session' })), null);
  assert.equal(
    await linkRoute(new Request(`${ORIGIN}/api/studio/link`, { method: 'GET' }), makeCtx(store, { auth, path: '/api/studio/link' })),
    null,
    'a GET on its own path is not this module answering',
  );
});
