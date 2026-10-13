// ============================================================================
// page-api.test.mjs — runnable check for the page's data routes (W1 U2)
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/page-api.test.mjs
//
// Proves the four things BUILD-PLAN.md U2 asks for, plus the ctx contract W2
// wires: session stays inside the caller's own client, the draft round-trips
// through R2, oversize answers are refused before any write, and the `{}` no-
// delete marker reads back as no draft.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';

import { buildKeyRecord, mintKey } from '../src/keys.js';
import { authorizeClient } from '../src/isolation.js';
import { randomClientId, scopePath } from '../src/ids.js';
import { AF_DRAFT_KIND, AF_ORDER_INVALID, MAX_REPLIES, MAX_REPLY_CHARS, deleteDraft, pageRoute, validateReplies } from '../src/page-api.js';
import { memObjects, memStore } from './fakes.mjs';

const T0 = Date.UTC(2026, 9, 13, 12, 0, 0);

const OK_HEADERS = { 'Content-Type': 'application/json; charset=utf-8' };

/** The same two shapes index.js hands every module as ctx.ok / ctx.fail. */
function ok(data, status = 200) {
  return new Response(JSON.stringify({ ok: true, ...data }), { status, headers: OK_HEADERS });
}
function fail(status, code, message) {
  return new Response(JSON.stringify({ ok: false, code, message }), { status, headers: OK_HEADERS });
}

function put(path, body, key) {
  const headers = { 'content-type': 'application/json' };
  if (key) headers['x-ds-key'] = key;
  return new Request(`https://studio.example${path}`, { method: 'PUT', headers, body: JSON.stringify(body || {}) });
}

function get(path, key) {
  const headers = key ? { 'x-ds-key': key } : {};
  return new Request(`https://studio.example${path}`, { method: 'GET', headers });
}

async function clientWithKey(store, kind = 'link', clientId = randomClientId()) {
  const minted = await mintKey();
  const record = await buildKeyRecord({ clientId, kind, secret: minted.secret, nowMs: T0 });
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));
  return { clientId, key: minted.secret, record };
}

async function makeCtx(store, objects, key) {
  const auth = await authorizeClient(store, key);
  assert.equal(auth.ok, true, `key must authorize: ${auth.code || ''}`);
  return {
    store,
    objects,
    auth,
    body: {},
    url: new URL('https://studio.example/'),
    nowMs: T0,
    ok,
    fail,
    project: (order) => ({ order_id: order.order_id, client_id: order.client_id, state: order.state, projected: true }),
  };
}

async function putOrder(store, clientId, orderId, createdAt) {
  await store.kvPut(
    `order:${clientId}:${orderId}`,
    JSON.stringify({ order_id: orderId, client_id: clientId, title: 'your video', state: 'waiting', created_at: createdAt, updated_at: createdAt }),
  );
}

async function json(response) {
  return JSON.parse(await response.text());
}

// ---------------------------------------------------------------------------
// validateReplies — the SPEC §4 limits
// ---------------------------------------------------------------------------

test('validateReplies: a normal answer set passes with its upload ids', () => {
  const out = validateReplies(['1', '2', 'yes'], ['u_1']);
  assert.deepEqual(out, { ok: true, replies: ['1', '2', 'yes'], uploadIds: ['u_1'] });
});

test('validateReplies: no upload ids still answers ok with an empty list', () => {
  assert.deepEqual(validateReplies(['1']), { ok: true, replies: ['1'], uploadIds: [] });
});

test('validateReplies: oversize and wrong-shaped answers are refused with one code', () => {
  const tooMany = Array.from({ length: MAX_REPLIES + 1 }, (_, i) => String(i));
  const cases = [
    validateReplies(tooMany),
    validateReplies(['x'.repeat(MAX_REPLY_CHARS + 1)]),
    validateReplies([42]),
    validateReplies('1,2,3'),
    validateReplies(['1'], Array.from({ length: 11 }, (_, i) => `u_${i}`)),
    validateReplies(['1'], [7]),
  ];
  for (const out of cases) {
    assert.equal(out.ok, false);
    assert.equal(out.code, AF_ORDER_INVALID);
    assert.equal(typeof out.message, 'string');
  }
});

// ---------------------------------------------------------------------------
// GET /api/studio/session
// ---------------------------------------------------------------------------

test('session: lists only this client\'s orders, newest first, projected through ctx.project', async () => {
  const store = memStore();
  const objects = memObjects();
  const me = await clientWithKey(store, 'link');
  const other = await clientWithKey(store, 'link');

  await putOrder(store, me.clientId, 'r_old', T0 - 60000);
  await putOrder(store, me.clientId, 'r_new', T0);
  // Another client's order under the same prefix shape must stay invisible.
  await putOrder(store, other.clientId, 'r_secret', T0);
  await store.kvPut(`client:${me.clientId}`, JSON.stringify({ client_id: me.clientId, option: 2, created_at: T0 }));

  const ctx = await makeCtx(store, objects, me.key);
  ctx.url = new URL('https://studio.example/api/studio/session');
  const res = await pageRoute(get('/api/studio/session', me.key), ctx);
  const body = await json(res);

  assert.equal(res.status, 200);
  assert.equal(body.ok, true);
  assert.equal(body.client_id, me.clientId);
  assert.equal(body.key_kind, 'link');
  assert.equal(body.option, 2);
  assert.match(body.option_line, /Your crew is watching\./);
  assert.deepEqual(body.orders.map((o) => o.order_id), ['r_new', 'r_old']);
  assert.ok(body.orders.every((o) => o.projected === true), 'every order must pass through ctx.project');
  assert.ok(!body.orders.some((o) => o.order_id === 'r_secret'), 'another client\'s order must be invisible');
  assert.equal(body.draft, null);
});

test('session: never returns more than 20 orders', async () => {
  const store = memStore();
  const objects = memObjects();
  const me = await clientWithKey(store, 'link');
  for (let i = 0; i < 25; i++) await putOrder(store, me.clientId, `r_${i}`, T0 + i);

  const ctx = await makeCtx(store, objects, me.key);
  ctx.url = new URL('https://studio.example/api/studio/session');
  const body = await json(await pageRoute(get('/api/studio/session', me.key), ctx));

  assert.equal(body.orders.length, 20);
  assert.equal(body.orders[0].order_id, 'r_24');
  assert.equal(body.orders[19].order_id, 'r_5');
});

test('session: the option line carries the real last check-in', async () => {
  const store = memStore();
  const objects = memObjects();
  const me = await clientWithKey(store, 'link');
  await store.kvPut(`client:${me.clientId}`, JSON.stringify({ client_id: me.clientId, option: 3 }));
  await objects.objectPut(`checkin:${me.clientId}`, String(T0));

  const ctx = await makeCtx(store, objects, me.key);
  ctx.url = new URL('https://studio.example/api/studio/session');
  const body = await json(await pageRoute(get('/api/studio/session', me.key), ctx));

  assert.equal(body.option, 3);
  assert.match(body.option_line, /Last check-in: just now\.$/);
});

// ---------------------------------------------------------------------------
// PUT /api/studio/draft
// ---------------------------------------------------------------------------

test('draft: round-trips through R2 and shows up on the next session', async () => {
  const store = memStore();
  const objects = memObjects();
  const me = await clientWithKey(store, 'link');

  const saved = await makeCtx(store, objects, me.key);
  saved.body = { replies: ['1', '2'], upload_ids: ['u_9'] };
  saved.url = new URL('https://studio.example/api/studio/draft');
  const savedRes = await pageRoute(put('/api/studio/draft', saved.body, me.key), saved);
  assert.deepEqual(await json(savedRes), { ok: true, updated_at: T0 });

  const shown = await makeCtx(store, objects, me.key);
  shown.url = new URL('https://studio.example/api/studio/session');
  const body = await json(await pageRoute(get('/api/studio/session', me.key), shown));
  assert.deepEqual(body.draft, { replies: ['1', '2'], updated_at: T0 });

  // The stored object sits in this client's own scope and nowhere else.
  assert.ok(objects._mem.has(scopePath(me.clientId, 'draft.json')));
});

test('draft: oversize replies are refused and nothing is written', async () => {
  const store = memStore();
  const objects = memObjects();
  const me = await clientWithKey(store, 'link');

  const ctx = await makeCtx(store, objects, me.key);
  ctx.body = { replies: Array.from({ length: MAX_REPLIES + 1 }, (_, i) => String(i)) };
  ctx.url = new URL('https://studio.example/api/studio/draft');
  const res = await pageRoute(put('/api/studio/draft', ctx.body, me.key), ctx);
  const body = await json(res);

  assert.equal(res.status, 400);
  assert.deepEqual(body, { ok: false, code: AF_ORDER_INVALID, message: body.message });
  assert.equal(objects._mem.size, 0, 'a refused draft must not reach storage');
});

test('draft: a reply over the character limit is refused', async () => {
  const store = memStore();
  const objects = memObjects();
  const me = await clientWithKey(store, 'link');

  const ctx = await makeCtx(store, objects, me.key);
  ctx.body = { replies: ['x'.repeat(MAX_REPLY_CHARS + 1)] };
  ctx.url = new URL('https://studio.example/api/studio/draft');
  const res = await pageRoute(put('/api/studio/draft', ctx.body, me.key), ctx);

  assert.equal(res.status, 400);
  assert.equal((await json(res)).code, AF_ORDER_INVALID);
  assert.equal(objects._mem.size, 0);
});

test('draft: a box key cannot save the client\'s answers', async () => {
  const store = memStore();
  const objects = memObjects();
  const box = await clientWithKey(store, 'box');

  const ctx = await makeCtx(store, objects, box.key);
  ctx.body = { replies: ['1'] };
  ctx.url = new URL('https://studio.example/api/studio/draft');
  const res = await pageRoute(put('/api/studio/draft', ctx.body, box.key), ctx);

  assert.equal(res.status, 403);
  assert.equal((await json(res)).code, AF_DRAFT_KIND);
  assert.equal(objects._mem.size, 0);
});

// ---------------------------------------------------------------------------
// The `{}` marker — R2 has no delete
// ---------------------------------------------------------------------------

test('draft: an empty marker and a missing object both read as no draft', async () => {
  const store = memStore();
  const objects = memObjects();
  const me = await clientWithKey(store, 'link');

  const ctx = await makeCtx(store, objects, me.key);
  ctx.url = new URL('https://studio.example/api/studio/session');

  assert.equal((await json(await pageRoute(get('/api/studio/session', me.key), ctx))).draft, null, 'nothing stored yet');

  await deleteDraft(objects, me.clientId);
  assert.deepEqual(await objects.objectGet(scopePath(me.clientId, 'draft.json')), { value: '{}' });
  assert.equal((await json(await pageRoute(get('/api/studio/session', me.key), ctx))).draft, null, 'the {} marker reads as no draft');

  // One draft of another client's is still invisible.
  const other = await clientWithKey(store, 'link');
  await objects.objectPut(scopePath(other.clientId, 'draft.json'), JSON.stringify({ replies: ['9'], updated_at: T0 }));
  assert.equal((await json(await pageRoute(get('/api/studio/session', me.key), ctx))).draft, null);
});

test('draft: a round-trip followed by deleteDraft clears it', async () => {
  const store = memStore();
  const objects = memObjects();
  const me = await clientWithKey(store, 'machine');

  const saved = await makeCtx(store, objects, me.key);
  saved.body = { replies: ['1'] };
  saved.url = new URL('https://studio.example/api/studio/draft');
  await pageRoute(put('/api/studio/draft', saved.body, me.key), saved);

  await deleteDraft(objects, me.clientId);

  const shown = await makeCtx(store, objects, me.key);
  shown.url = new URL('https://studio.example/api/studio/session');
  assert.equal((await json(await pageRoute(get('/api/studio/session', me.key), shown))).draft, null);
});

// ---------------------------------------------------------------------------
// Routing
// ---------------------------------------------------------------------------

test('pageRoute: answers only its own paths and methods', async () => {
  const store = memStore();
  const objects = memObjects();
  const me = await clientWithKey(store, 'link');
  const ctx = await makeCtx(store, objects, me.key);

  ctx.url = new URL('https://studio.example/api/studio/health');
  assert.equal(await pageRoute(get('/api/studio/health', me.key), ctx), null);

  ctx.url = new URL('https://studio.example/api/studio/session');
  assert.equal(await pageRoute(put('/api/studio/session', {}, me.key), ctx), null, 'PUT on the session path is not ours');
});
