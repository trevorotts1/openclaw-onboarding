// ============================================================================
// approvals-api.test.mjs — the four approvals routes (U3)
//
// Prove for W1-studio-service-U3: publish -> list -> answer -> second answer
// 409; the same version twice is one item; another client's key cannot read or
// answer; a bad stage or file name is refused. Plus the file stream route.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';
import { approvalsRoute, approvalKey, approvalFilePath, exactFileRouteUrl, validatePublish } from '../src/approvals-api.js';
import { decisionPath, intentPath, stagingPath } from '../src/approval-store.js';
import { memR2Bucket, memStore } from './fakes.mjs';

const CLIENT_A = `c-${'a'.repeat(32)}`;
const CLIENT_B = `c-${'b'.repeat(32)}`;
const ORDER = 'r_ab12cd34';
const NOW = 1760000000000;

// Staged-file fixture: 4096 bytes of 0x07. FILE_SHA256 is script-computed
// (work tmp/staged_sha.txt), never typed. The service verifies staged bytes
// against the declared digest at finalize, so fixture and bytes must agree.
const FILE_SHA256 = 'c9ac7b0624824f844f6c7f3d50fab9741a8914e878467e8daaedca143a34d90b';
const FILE_BYTES = Buffer.alloc(4096, 7);

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
  const bucket = memR2Bucket();
  const env = {
    ...R2_ENV,
    DRAMA_STUDIO: bucket,
  };
  return { store, env, bucket };
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

/** Complete the staged upload the publish presigned, then finalize to ready. */
async function stageAndFinalize(ctx, body = PUBLISH_BODY) {
  await ctx.bucket.put(
    stagingPath(CLIENT_A, ORDER, body.stage, body.version, body.files[0].name),
    FILE_BYTES,
    { httpMetadata: { contentType: body.files[0].content_type }, sha256: FILE_SHA256 },
  );
  const res = await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals/${body.stage}/${body.version}/finalize`, body: {} });
  assert.equal(res.status, 201);
  return res.json();
}

const PUBLISH_BODY = {
  stage: 'script',
  version: 1,
  text: 'Two people meet at a laundromat.',
  choices: [{ n: 1, label: 'Option one' }],
  files: [{ name: 'script.mp3', content_type: 'audio/mpeg', bytes: 4096, sha256: FILE_SHA256 }],
};

test('publish stores one item and hands back presigned PUTs', async () => {
  const ctx = await setup();
  const res = await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, body: PUBLISH_BODY });
  assert.equal(res.status, 201);
  const out = await res.json();
  assert.equal(out.ok, true);
  assert.equal(out.created, true);
  assert.equal(out.item.stage, 'script');
  assert.equal(out.item.version, 1);
  assert.equal(out.item.text, PUBLISH_BODY.text);
  assert.deepEqual(out.item.choices, PUBLISH_BODY.choices);
  assert.match(out.item.presentation_digest, /^[0-9a-f]{64}$/); // CONTRACT_EXPECTATION_CHANGE: publish binds a presentation digest
  assert.equal(out.item.ready, false); // CONTRACT_EXPECTATION_CHANGE: ready only after finalize
  assert.deepEqual(out.item.files, [
    { name: 'script.mp3', url: null, content_type: 'audio/mpeg', bytes: 4096, sha256: FILE_SHA256 },
  ]); // CONTRACT_EXPECTATION_CHANGE: files carry digest, no URL until ready
  assert.equal(out.item.answer, null);
  assert.equal(out.item.created_at, NOW);
  assert.equal(out.uploads.length, 1);
  assert.equal(out.uploads[0].method, 'PUT');
  assert.equal(out.uploads[0].name, 'script.mp3');
  assert.match(
    out.uploads[0].url,
    new RegExp(`clients/${CLIENT_A}/orders/${ORDER}/approvals-v2/script-v1/staging/script\\.mp3`),
  ); // CONTRACT_EXPECTATION_CHANGE: staging path carries revision
  const intentRaw = await ctx.bucket.get(intentPath(CLIENT_A, ORDER, 'script', 1)); // CONTRACT_EXPECTATION_CHANGE: authority lives in R2 intent, not KV
  const stored = JSON.parse(await intentRaw.text());
  assert.equal(stored.stage, 'script');
  assert.equal(stored.version, 1);
  assert.equal(await ctx.bucket.get(decisionPath(CLIENT_A, ORDER, 'script', 1)), null);
});

test('the same stage and version twice is one item, created:false', async () => {
  const ctx = await setup();
  const first = await (await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, body: PUBLISH_BODY })).json();
  const res = await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, body: PUBLISH_BODY });
  assert.equal(res.status, 200);
  const second = await res.json();
  assert.equal(second.created, false);
  assert.deepEqual(second.item, first.item);
  const intentRaw = await ctx.bucket.get(intentPath(CLIENT_A, ORDER, 'script', 1)); // FIXTURE: observe the R2 authority, not KV
  assert.ok(intentRaw !== null);
  assert.equal(await ctx.bucket.get(decisionPath(CLIENT_A, ORDER, 'script', 1)), null);
});

test('list returns this order\'s items with files mapped to the file route', async () => {
  const ctx = await setup();
  const pub = await (await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, body: PUBLISH_BODY })).json();
  await stageAndFinalize(ctx);
  const res = await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, method: 'GET' });
  assert.equal(res.status, 200);
  const out = await res.json();
  assert.equal(out.items.length, 1);
  assert.equal(out.items[0].stage, 'script');
  assert.equal(out.items[0].answer, null);
  assert.deepEqual(out.items[0].files, [
    { name: 'script.mp3', url: exactFileRouteUrl(ORDER, 'script', 1, pub.item.presentation_digest, 'script.mp3'), content_type: 'audio/mpeg', bytes: 4096, sha256: FILE_SHA256 },
  ]); // CONTRACT_EXPECTATION_CHANGE: files map to the exact revision route with digest
});

test('first answer wins: a second answer is refused with APPROVAL_ANSWER_TAKEN', async () => {
  const ctx = await setup();
  await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, body: PUBLISH_BODY });
  await stageAndFinalize(ctx);
  const answerPath = `/api/studio/orders/${ORDER}/approvals/script/answer`;

  const first = await call(ctx, { path: answerPath, body: { version: 1, value: 'approve' }, kind: 'link' });
  assert.equal(first.status, 200);
  const firstBody = await first.json();
  assert.equal(firstBody.ok, true);
  assert.equal(firstBody.answer.value, 'approve');
  assert.equal(firstBody.answer.by, 'link');
  assert.equal(firstBody.answer.at, NOW);
  assert.equal(firstBody.answer.stage, 'script'); // CONTRACT_EXPECTATION_CHANGE: the decision carries the full envelope
  assert.equal(firstBody.answer.version, 1); // CONTRACT_EXPECTATION_CHANGE
  assert.match(firstBody.answer.presentation_digest, /^[0-9a-f]{64}$/); // CONTRACT_EXPECTATION_CHANGE
  assert.match(firstBody.answer.decision_id, /^d_[0-9a-f]{32}$/); // CONTRACT_EXPECTATION_CHANGE

  const second = await call(ctx, { path: answerPath, body: { version: 1, value: 'no, change it' }, kind: 'link' });
  assert.equal(second.status, 409);
  const refused = await second.json();
  assert.equal(refused.ok, false);
  assert.equal(refused.code, 'APPROVAL_ANSWER_TAKEN');

  const decisionRaw = await ctx.bucket.get(decisionPath(CLIENT_A, ORDER, 'script', 1)); // CONTRACT_EXPECTATION_CHANGE: the decision lives in R2
  const stored = JSON.parse(await decisionRaw.text());
  assert.equal(stored.value, 'approve');
  assert.equal(stored.by, 'link');
  assert.equal(stored.at, NOW);
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
    kind: 'link',
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
    { ...PUBLISH_BODY, files: [{ name: 'script.mp3', content_type: 'audio/mpeg', bytes: 4096 }] }, // FIXTURE: no sha256 must be refused
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
  const pub = await (await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, body: PUBLISH_BODY })).json();
  await stageAndFinalize(ctx);
  const digest = pub.item.presentation_digest;
  const fileUrl = exactFileRouteUrl(ORDER, 'script', 1, digest, 'script.mp3'); // CONTRACT_EXPECTATION_CHANGE: media is addressed by revision and digest

  const res = await call(ctx, {
    path: fileUrl,
    method: 'GET',
  });
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('Content-Type'), 'audio/mpeg');
  assert.equal(res.headers.get('Cache-Control'), 'no-store');
  assert.equal(res.headers.get('X-DS-SHA256'), FILE_SHA256); // CONTRACT_EXPECTATION_CHANGE: the served bytes bind the declared digest
  assert.deepEqual(Buffer.from(await res.arrayBuffer()), FILE_BYTES); // CONTRACT_EXPECTATION_CHANGE: exact frozen bytes

  const legacy = await call(ctx, { // CONTRACT_EXPECTATION_CHANGE: the revisionless route is refused by name, never searched
    path: `/api/studio/orders/${ORDER}/approvals/script/file/script.mp3`,
    method: 'GET',
  });
  assert.equal(legacy.status, 400);
  assert.equal((await legacy.json()).code, 'APPROVAL_REVISION_REQUIRED');

  const missing = await call(ctx, {
    path: exactFileRouteUrl(ORDER, 'script', 1, digest, 'nope.mp3'),
    method: 'GET',
  });
  assert.equal(missing.status, 404);
  assert.equal((await missing.json()).code, 'AF-DS-FILE-MISSING');

  const badName = await call(ctx, { path: exactFileRouteUrl(ORDER, 'script', 1, digest, 'a%2Fb.mp3'), method: 'GET' });
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

test('list fails closed when the bucket has no list shape (legacy storage)', async () => {
  // CONTRACT_EXPECTATION_CHANGE (task-mandated mutation guard): a bucket without
  // list() is the pre-migration store; the list route answers 503
  // APPROVAL_STORAGE_UNAVAILABLE, never a false empty list. Quoted cover:
  // answers.json (b) step 5 + QC harness check 7 (storage outage 503) +
  // I-STAGE-T07MEDIA-r1 STORAGE MIGRATION cell (no KV fallback).
  const ctx = await setup();
  ctx.env.DRAMA_STUDIO = { get: ctx.bucket.get.bind(ctx.bucket), put: ctx.bucket.put.bind(ctx.bucket) };
  const res = await call(ctx, { path: `/api/studio/orders/${ORDER}/approvals`, method: 'GET' });
  assert.equal(res.status, 503);
  assert.equal((await res.json()).code, 'APPROVAL_STORAGE_UNAVAILABLE');
});
