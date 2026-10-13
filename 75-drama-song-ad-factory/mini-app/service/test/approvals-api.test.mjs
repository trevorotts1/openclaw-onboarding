// ============================================================================
// approvals-api.test.mjs — the four approvals routes (U3)
//
// Prove for W1-studio-service-U3: publish -> list -> answer -> second answer
// 409; the same version twice is one item; another client's key cannot read or
// answer; a bad stage or file name is refused. Plus the file stream route.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';
import { approvalsRoute, approvalKey, approvalFilePath, validatePublish } from '../src/approvals-api.js';
import { memStore } from './fakes.mjs';

const CLIENT_A = `c-${'a'.repeat(32)}`;
const CLIENT_B = `c-${'b'.repeat(32)}`;
const ORDER = 'r_ab12cd34';
const NOW = 1760000000000;

const R2_ENV = {
  R2_ACCOUNT_ID: 'f'.repeat(32),
  R2_ACCESS_KEY_ID: 'test-access-key',
  R2_SECRET_ACCESS_KEY: 'test-secret-key',
};

async function setup({ orderFor = [CLIENT_A] } = {}) {
  const store = memStore();
  for (const cid of orderFor) {
    await store.kvPut(`order:${cid}:${ORDER}`, JSON.stringify({ order_id: ORDER, client_id: cid, state: 'waiting' }));
  }
  const objects = new Map();
  const env = {
    ...R2_ENV,
    DRAMA_STUDIO: { get: async (p) => (objects.has(p) ? objects.get(p) : null), _objects: objects },
  };
  return { store, env, objects };
}

function call(routeCtx, { path, method = 'POST', body, clientId = CLIENT_A, kind = 'machine' } = {}) {
  const headers = { 'content-type': 'application/json' };
  const request = new Request(`https://studio.example${path}`, {
    method,
    headers,
    body: method === 'GET' ? undefined : JSON.stringify(body || {}),
  });
  const ctx = {
    ...routeCtx,
    body: body || {},
    url: new URL(request.url),
    nowMs: NOW,
    auth: { ok: true, client_id: clientId, record: { client_id: clientId, kind } },
  };
  return approvalsRoute(request, ctx);
}

const PUBLISH_BODY = {
  stage: 'script',
  version: 1,
  text: 'Two people meet at a laundromat.',
  choices: [{ n: 1, label: 'Option one' }],
  files: [{ name: 'script.mp3', content_type: 'audio/mpeg', bytes: 4096 }],
};

test('publish stores one item and hands back presigned PUTs', async () => {
  const ctx = await setup();
  const res = await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, body: PUBLISH_BODY });
  assert.equal(res.status, 201);
  const out = await res.json();
  assert.equal(out.ok, true);
  assert.equal(out.created, true);
  assert.deepEqual(out.item, {
    stage: 'script',
    version: 1,
    text: PUBLISH_BODY.text,
    choices: PUBLISH_BODY.choices,
    files: ['script.mp3'],
    answer: null,
    created_at: NOW,
  });
  assert.equal(out.uploads.length, 1);
  assert.equal(out.uploads[0].method, 'PUT');
  assert.equal(out.uploads[0].name, 'script.mp3');
  assert.match(
    out.uploads[0].url,
    new RegExp(`clients/${CLIENT_A}/orders/${ORDER}/approvals/script-v1/script\\.mp3`),
  );
  const stored = JSON.parse(await ctx.store.kvGet(approvalKey(CLIENT_A, ORDER, 'script', 1)));
  assert.equal(stored.answer, null);
});

test('the same stage and version twice is one item, created:false', async () => {
  const ctx = await setup();
  const first = await (await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, body: PUBLISH_BODY })).json();
  const res = await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, body: PUBLISH_BODY });
  assert.equal(res.status, 200);
  const second = await res.json();
  assert.equal(second.created, false);
  assert.deepEqual(second.item, first.item);
  const keys = (await ctx.store.kvList(`approval:${CLIENT_A}:${ORDER}:`)).filter((k) => k.includes(':script:'));
  assert.equal(keys.length, 1);
});

test('list returns this order\'s items with files mapped to the file route', async () => {
  const ctx = await setup();
  await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, body: PUBLISH_BODY });
  const res = await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, method: 'GET' });
  assert.equal(res.status, 200);
  const out = await res.json();
  assert.equal(out.items.length, 1);
  assert.equal(out.items[0].stage, 'script');
  assert.equal(out.items[0].answer, null);
  assert.deepEqual(out.items[0].files, [
    { name: 'script.mp3', url: `/api/studio/orders/${ORDER}/approvals/script/file/script.mp3` },
  ]);
});

test('first answer wins: a second answer is refused with APPROVAL_ANSWER_TAKEN', async () => {
  const ctx = await setup();
  await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, body: PUBLISH_BODY });
  const answerPath = `/api/studio/orders/${ORDER}/approvals/script/answer`;

  const first = await call(ctx, { path: answerPath, body: { version: 1, value: 'approve' }, kind: 'link' });
  assert.equal(first.status, 200);
  assert.deepEqual(await first.json(), { ok: true, answer: { value: 'approve', by: 'link', at: NOW } });

  const second = await call(ctx, { path: answerPath, body: { version: 1, value: 'no, change it' }, kind: 'machine' });
  assert.equal(second.status, 409);
  const refused = await second.json();
  assert.equal(refused.ok, false);
  assert.equal(refused.code, 'APPROVAL_ANSWER_TAKEN');

  const stored = JSON.parse(await ctx.store.kvGet(approvalKey(CLIENT_A, ORDER, 'script', 1)));
  assert.deepEqual(stored.answer, { value: 'approve', by: 'link', at: NOW });
});

test('another client\'s key cannot read or answer this order', async () => {
  const ctx = await setup();
  await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, body: PUBLISH_BODY });

  const read = await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, method: 'GET', clientId: CLIENT_B });
  assert.equal(read.status, 404);

  const answer = await call(ctx, {
    path: `/api/studio/orders/${ORDER}/approvals/script/answer`,
    body: { version: 1, value: 'approve' },
    clientId: CLIENT_B,
  });
  assert.equal(answer.status, 404);
  assert.equal((await answer.json()).code, 'AF-DS-ORDER-MISSING');

  const publish = await call(ctx, {
    path: `/api/studio/orders/${ORDER}/approvals`,
    body: PUBLISH_BODY,
    clientId: CLIENT_B,
  });
  assert.equal(publish.status, 404);
  assert.equal(await ctx.store.kvGet(approvalKey(CLIENT_B, ORDER, 'script', 1)), null);
});

test('a bad stage, file name, content type or size is refused', async () => {
  const ctx = await setup();
  const path = `/api/studio/orders/${ORDER}/approvals`;
  const cases = [
    { ...PUBLISH_BODY, stage: 'lighting' },
    { ...PUBLISH_BODY, files: [{ name: '../evil.png', content_type: 'image/png', bytes: 10 }] },
    { ...PUBLISH_BODY, files: [{ name: '..', content_type: 'image/png', bytes: 10 }] },
    { ...PUBLISH_BODY, files: [{ name: 'cut.mp4', content_type: 'video/mp4', bytes: 10 }] },
    { ...PUBLISH_BODY, files: [{ name: 'cut.mp3', content_type: 'audio/mpeg', bytes: 30 * 1024 * 1024 }] },
    { ...PUBLISH_BODY, version: 0 },
  ];
  for (const body of cases) {
    const res = await call(ctx, { path, body });
    assert.equal(res.status, 400, JSON.stringify(body));
    assert.equal((await res.json()).code, 'APPROVAL_BAD_INPUT');
  }
  assert.equal((await ctx.store.kvList(`approval:${CLIENT_A}:${ORDER}:`)).length, 0);
  assert.equal(validatePublish(PUBLISH_BODY).ok, true);
});

test('only the machine, box and link kinds get the routes their SPEC allows', async () => {
  const ctx = await setup();
  const publishPath = `/api/studio/orders/${ORDER}/approvals`;
  const answerPath = `/api/studio/orders/${ORDER}/approvals/script/answer`;

  const linkPublish = await call(ctx, { path: publishPath, body: PUBLISH_BODY, kind: 'link' });
  assert.equal(linkPublish.status, 403);
  assert.equal((await linkPublish.json()).code, 'AF-DS-LINK-KIND');

  await call(ctx, { path: publishPath, body: PUBLISH_BODY, kind: 'box' });
  const boxAnswer = await call(ctx, { path: answerPath, body: { version: 1, value: 'GO' }, kind: 'box' });
  assert.equal(boxAnswer.status, 403);

  const machinePublish = await call(ctx, { path: publishPath, body: { ...PUBLISH_BODY, stage: 'song', version: 2 }, kind: 'machine' });
  assert.equal(machinePublish.status, 201);
  const linkList = await call(ctx, { path: publishPath, method: 'GET', kind: 'link' });
  assert.equal(linkList.status, 200);
});

test('the file route streams the object with no-store and 404s when absent', async () => {
  const ctx = await setup();
  await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, body: PUBLISH_BODY });
  const path = approvalFilePath(CLIENT_A, ORDER, 'script', 1, 'script.mp3');
  ctx.env.DRAMA_STUDIO._objects.set(path, { body: 'AUDIO', httpMetadata: { contentType: 'audio/mpeg' } });

  const res = await call(ctx, {
    path: `/api/studio/orders/${ORDER}/approvals/script/file/script.mp3`,
    method: 'GET',
  });
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('Content-Type'), 'audio/mpeg');
  assert.equal(res.headers.get('Cache-Control'), 'no-store');
  assert.equal(await res.text(), 'AUDIO');

  const missing = await call(ctx, {
    path: `/api/studio/orders/${ORDER}/approvals/script/file/nope.mp3`,
    method: 'GET',
  });
  assert.equal(missing.status, 404);
  assert.equal((await missing.json()).code, 'AF-DS-FILE-MISSING');

  const badName = await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals/script/file/a%2Fb.mp3`, method: 'GET' });
  assert.equal(badName.status, 400);
});

test('a missing order and a path that is not an approval route', async () => {
  const ctx = await setup({ orderFor: [] });
  const publish = await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, body: PUBLISH_BODY });
  assert.equal(publish.status, 404);
  assert.equal((await publish.json()).code, 'AF-DS-ORDER-MISSING');

  const other = await setup();
  const list = await call(other, { path: '/api/studio/orders/r_x', method: 'GET' });
  assert.equal(list, null);
  const orders = await call(other, { path: '/api/studio/orders', method: 'GET' });
  assert.equal(orders, null);
  const answerOnList = await call(other, { path: `/api/studio/orders/${ORDER}/approvals`, method: 'GET' });
  assert.equal(answerOnList.status, 200);
});
