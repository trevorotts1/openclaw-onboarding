// ============================================================================
// wiring.test.mjs — Drama Studio service: index.js dispatches and serves the
// page (DSF W2-studio-wiring-U1)
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/wiring.test.mjs
//
// Proves the BUILD-PLAN acceptance for W2-studio-wiring-U1:
//   `/` returns the page from a fake assets binding; the link, page and
//   approvals routes reach their modules; orders keep the replies and clear
//   the draft; a link key can only cancel; the 6th wrong pairing from one IP
//   is locked.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';

import worker, { handle } from '../src/index.js';
import { buildKeyRecord, mintKey } from '../src/keys.js';
import { randomClientId } from '../src/ids.js';
import { memObjects, memStore } from './fakes.mjs';

const ORIGIN = 'https://studio.example';
const ADMIN_KEY = 'admin-key-placeholder-for-tests';
const GOOD_ENV = { DS_ADMIN_KEY: ADMIN_KEY };

// ---------------------------------------------------------------------------
// Adapters shaped exactly like the bindings worker.fetch builds
// ---------------------------------------------------------------------------

function nsOf(store) {
  return {
    get: async (k) => store.kvGet(k),
    put: async (k, v, opts) => store.kvPut(k, v, opts && opts.expirationTtl),
    delete: async (k) => store.kvDelete(k),
    list: async ({ prefix }) => ({ keys: (await store.kvList(prefix)).map((name) => ({ name })), list_complete: true }),
  };
}

function bucketOf(objects) {
  return {
    get: async (p) => {
      const found = await objects.objectGet(p);
      return found ? { text: async () => found.value } : null;
    },
    put: async (p, v) => objects.objectPut(p, v),
  };
}

function bindingEnv(store, objects, assets) {
  return { ...GOOD_ENV, DS_STUDIO: nsOf(store), DRAMA_STUDIO: bucketOf(objects), DS_UPLOAD_ASSETS: assets };
}

/** An assets binding that records the paths it was asked for. */
function assetsBinding(files) {
  const asked = [];
  return {
    asked,
    fetch: async (req) => {
      const path = new URL(req.url).pathname;
      asked.push(path);
      const body = files[path];
      if (body === undefined) return new Response('not found', { status: 404 });
      return new Response(body, { status: 200, headers: { 'Content-Type': 'text/html' } });
    },
  };
}

// ---------------------------------------------------------------------------
// Requests and keys
// ---------------------------------------------------------------------------

function req(method, path, body, { key, ip } = {}) {
  const headers = { 'content-type': 'application/json' };
  if (key) headers['x-ds-key'] = key;
  if (ip) headers['CF-Connecting-IP'] = ip;
  return new Request(`${ORIGIN}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
}

async function mintedKey(store, clientId, kind) {
  const minted = await mintKey();
  const record = await buildKeyRecord({ clientId, kind, secret: minted.secret, nowMs: Date.now() });
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));
  return minted.secret;
}

/** A client with a box key, a machine key and a personal link key. */
async function studio() {
  const store = memStore();
  const objects = memObjects();
  const clientId = randomClientId();
  const box = await mintedKey(store, clientId, 'box');
  const machine = await mintedKey(store, clientId, 'machine');
  const link = await mintedKey(store, clientId, 'link');
  return { store, objects, clientId, box, machine, link };
}

const call = (request, s, env) => handle(request, env || GOOD_ENV, s.store, s.objects);

// ---------------------------------------------------------------------------
// Static pages — the whole reason the phone works at all
// ---------------------------------------------------------------------------

test('wiring: GET / serves the studio page from the assets binding, with the service headers', async () => {
  const assets = assetsBinding({ '/index.html': '<html>studio</html>' });
  const response = await worker.fetch(new Request(`${ORIGIN}/`), bindingEnv(memStore(), memObjects(), assets));

  assert.equal(response.status, 200);
  assert.equal(await response.text(), '<html>studio</html>');
  assert.deepEqual(assets.asked, ['/index.html'], '/ is the page');
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
  assert.match(response.headers.get('Content-Security-Policy'), /frame-ancestors 'none'/);
  assert.match(response.headers.get('Content-Security-Policy'), /connect-src 'self' https:\/\/\*\.r2\.cloudflarestorage\.com/);
});

test('wiring: /admin and /uploads map onto their own files, everything else passes through', async () => {
  const assets = assetsBinding({
    '/admin/index.html': '<html>admin</html>',
    '/upload/index.html': '<html>upload</html>',
    '/studio.js': 'window.studio = 1;',
  });
  const env = bindingEnv(memStore(), memObjects(), assets);

  for (const [path, file, body] of [
    ['/admin', '/admin/index.html', '<html>admin</html>'],
    ['/uploads', '/upload/index.html', '<html>upload</html>'],
    ['/studio.js', '/studio.js', 'window.studio = 1;'],
  ]) {
    const response = await worker.fetch(new Request(`${ORIGIN}${path}`), env);
    assert.equal(response.status, 200, path);
    assert.equal(await response.text(), body, path);
    assert.equal(assets.asked[assets.asked.length - 1], file, path);
  }

  // An API route is never handed to the assets binding.
  const health = await worker.fetch(new Request(`${ORIGIN}/api/studio/health`), env);
  assert.equal(health.status, 200);
  assert.equal((await health.json()).ok, true);
  assert.ok(!assets.asked.includes('/api/studio/health'), 'API routes stay in handle()');
});

// ---------------------------------------------------------------------------
// Dispatch — the three modules answer their own paths
// ---------------------------------------------------------------------------

test('wiring: link, page and approvals routes reach their modules through index.js', async () => {
  const s = await studio();

  // link.js — a machine key mints the personal link.
  const minted = await call(req('POST', '/api/studio/link', { rotate: true }, { key: s.machine }), s);
  assert.equal(minted.status, 200);
  assert.match((await minted.json()).link, /^https:\/\/studio\.example\/#k=[0-9a-f]{64}$/);

  // link.js — the admin route needs no key at all.
  const admin = await call(req('POST', '/api/studio/admin/link', { admin_key: ADMIN_KEY, client_id: s.clientId }), s);
  assert.equal(admin.status, 200);
  assert.match((await admin.json()).link, /#k=/);

  // page-api.js — the session route.
  const session = await call(req('GET', '/api/studio/session', undefined, { key: s.link }), s);
  assert.equal(session.status, 200);
  const seen = await session.json();
  assert.equal(seen.client_id, s.clientId);
  assert.equal(seen.key_kind, 'link');
  assert.deepEqual(seen.orders, []);

  // approvals-api.js — the list route answers for an order the box owns.
  const created = await call(req('POST', '/api/studio/orders', { title: 'Spring Sale' }, { key: s.box }), s);
  assert.equal(created.status, 201);
  const orderId = (await created.json()).order.order_id;
  const approvals = await call(req('GET', `/api/studio/orders/${orderId}/approvals`, undefined, { key: s.link }), s);
  assert.equal(approvals.status, 200);
  assert.deepEqual((await approvals.json()).items, []);
});

// ---------------------------------------------------------------------------
// Orders keep the answers
// ---------------------------------------------------------------------------

test('wiring: an order keeps the replies and upload ids, and Lock it in clears the draft', async () => {
  const s = await studio();

  const saved = await call(req('PUT', '/api/studio/draft', { replies: ['1', '2'] }, { key: s.link }), s);
  assert.equal(saved.status, 200);
  const withDraft = await call(req('GET', '/api/studio/session', undefined, { key: s.link }), s);
  assert.deepEqual((await withDraft.json()).draft.replies, ['1', '2']);

  const created = await call(
    req('POST', '/api/studio/orders', { title: 'Spring Sale', replies: ['1', '2', 'yes'], upload_ids: ['u_1'] }, { key: s.link }),
    s,
  );
  assert.equal(created.status, 201);
  const order = (await created.json()).order;
  assert.deepEqual(order.replies, ['1', '2', 'yes'], 'the answers survive on the order');
  assert.deepEqual(order.upload_ids, ['u_1']);

  const after = await call(req('GET', '/api/studio/orders/' + order.order_id, undefined, { key: s.machine }), s);
  assert.deepEqual((await after.json()).order.replies, ['1', '2', 'yes'], 'the box reads the answers back');

  const cleared = await call(req('GET', '/api/studio/session', undefined, { key: s.link }), s);
  assert.equal((await cleared.json()).draft, null, 'the draft is gone once the order is locked in');

  // A body that breaks the SPEC §4 limits never becomes an order.
  const oversize = await call(req('POST', '/api/studio/orders', { title: 'x', replies: ['y'.repeat(2001)] }, { key: s.link }), s);
  assert.equal(oversize.status, 400);
  assert.equal((await oversize.json()).code, 'AF-DS-ORDER-INVALID');
});

// ---------------------------------------------------------------------------
// A link key may only cancel
// ---------------------------------------------------------------------------

test('wiring: a link key can cancel its order and post no other state event', async () => {
  const s = await studio();
  const created = await call(req('POST', '/api/studio/orders', { title: 'Spring Sale', replies: ['1'] }, { key: s.link }), s);
  const orderId = (await created.json()).order.order_id;

  const claim = await call(req('POST', `/api/studio/orders/${orderId}/state`, { event: 'claim' }, { key: s.link }), s);
  assert.equal(claim.status, 403);
  assert.equal((await claim.json()).code, 'AF-DS-LINK-KIND');

  const cancelled = await call(req('POST', `/api/studio/orders/${orderId}/cancel`, {}, { key: s.link }), s);
  assert.equal(cancelled.status, 200);
  assert.equal((await cancelled.json()).order.state, 'cancelled');
});

test('wiring: a deliver event stores the https delivery link on the order', async () => {
  const s = await studio();
  /** waiting -> in_production -> ready, so the order can be delivered. */
  const readyOrder = async (title) => {
    const created = await call(req('POST', '/api/studio/orders', { title, replies: ['1'] }, { key: s.box }), s);
    const orderId = (await created.json()).order.order_id;
    for (const event of ['claim', 'ready']) {
      const moved = await call(req('POST', `/api/studio/orders/${orderId}/state`, { event }, { key: s.box }), s);
      assert.equal(moved.status, 200, event);
    }
    return orderId;
  };

  const orderId = await readyOrder('Spring Sale');
  const delivered = await call(
    req('POST', `/api/studio/orders/${orderId}/state`, { event: 'deliver', delivery: { url: 'https://media.example/v/1', kind: 'ghl' } }, { key: s.box }),
    s,
  );
  assert.equal(delivered.status, 200);
  assert.deepEqual((await delivered.json()).order.delivery, { url: 'https://media.example/v/1', kind: 'ghl' });

  // An http URL is never stored.
  const otherId = await readyOrder('Second Sale');
  const dropped = await call(
    req('POST', `/api/studio/orders/${otherId}/state`, { event: 'deliver', delivery: { url: 'http://media.example/v/2', kind: 'r2' } }, { key: s.box }),
    s,
  );
  assert.equal(dropped.status, 200);
  assert.equal((await dropped.json()).order.delivery, undefined);
});

// ---------------------------------------------------------------------------
// The pairing lock is per caller, so a wrong code can lock it at all
// ---------------------------------------------------------------------------

test('wiring: the 6th wrong pairing code from one IP is locked', async () => {
  const store = memStore();
  const objects = memObjects();
  const env = GOOD_ENV;
  const ip = '203.0.113.9';

  for (let i = 0; i < 5; i++) {
    const wrong = await handle(req('POST', '/api/studio/pair', { code: 'AAAA-1111' }, { ip }), env, store, objects);
    assert.equal(wrong.status, 403, `try ${i + 1} is refused`);
    assert.notEqual((await wrong.json()).code, 'AF-DS-PAIR-LOCKED', `try ${i + 1} is not the lock yet`);
  }

  const locked = await handle(req('POST', '/api/studio/pair', { code: 'AAAA-1111' }, { ip }), env, store, objects);
  assert.equal(locked.status, 403);
  assert.equal((await locked.json()).code, 'AF-DS-PAIR-LOCKED');

  // A different address is unaffected — the lock belongs to the caller.
  const otherIp = await handle(req('POST', '/api/studio/pair', { code: 'AAAA-1111' }, { ip: '203.0.113.10' }), env, store, objects);
  assert.equal(otherIp.status, 403);
  assert.notEqual((await otherIp.json()).code, 'AF-DS-PAIR-LOCKED');
});
