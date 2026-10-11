// ============================================================================
// service.test.mjs — Drama Studio service (U2) runnable check
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/service.test.mjs
//
// Every assertion here is a rule from the approved plan (sections 3.10, 3.10A,
// 3.11, 3.15). The three SECURITY proofs live in
// prove/prove_service_boundaries.mjs; this file is the behavior suite around
// them.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';

import { isClientId, ownsPath, randomClientId, scopePath } from '../src/ids.js';
import {
  AF_PAIR_EXPIRED, AF_PAIR_LOCKED, AF_PAIR_WRONG, attemptPairing, buildKeyRecord,
  mintKey, mintPairingCode,
} from '../src/keys.js';
import { AF_ENROLL_REFUSED, AF_ISO_CROSS, AF_ISO_SCOPE, authorizeClient, enrollClient, resolveKey } from '../src/isolation.js';
import { checkIn, inboxLine, readInbox, writeInbox } from '../src/inbox.js';
import {
  AF_UP_CAPABILITY, AF_UP_CROSS, AF_UP_FORMAT, AF_UP_SIZE, acceptUpload, validateUpload,
} from '../src/uploads.js';
import { DAY_MS, RETENTION_RULES, dueForDeletion, retentionVerdict } from '../src/retention.js';
import {
  AF_STATE_ILLEGAL, AF_STATE_TERMINAL, operatorRecordCount, resolveOrderState, transition,
  writeOperatorRecord,
} from '../src/lifecycle.js';
import { AF_OPT_APPROVAL, AF_OPT_INVALID, optionLine, setOption, staleVerdict } from '../src/options.js';
import { SERVICE_VERSION, handle } from '../src/index.js';
import { get, memObjects, memStore, post } from './fakes.mjs';

const T0 = Date.UTC(2026, 9, 10, 12, 0, 0);

async function clientWithKey(store, kind = 'link') {
  const clientId = randomClientId();
  const minted = await mintKey();
  const record = await buildKeyRecord({ clientId, kind, secret: minted.secret, nowMs: T0 });
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));
  return { clientId, key: minted.secret, record };
}

const GOOD_ENV = {
  DS_ENROLLMENT_SECRET: 'enrollment-secret-placeholder-for-tests',
  DS_ADMIN_KEY: 'admin-key-placeholder-for-tests',
  R2_ACCOUNT_ID: 'fakeaccountid',
  R2_ACCESS_KEY_ID: 'fakeaccesskey',
  R2_SECRET_ACCESS_KEY: 'fakesecret',
  DRAMA_STUDIO_BUCKET: 'drama-studio',
};

// ---------------------------------------------------------------------------
// ids — the studio invents the identifier; no names in paths
// ---------------------------------------------------------------------------

test('ids: the studio invents a name-free client id', () => {
  const id = randomClientId();
  assert.ok(isClientId(id), `${id} must match c-<32 hex>`);
  assert.ok(!/[^c0-9a-f-]/.test(id), 'no name characters may appear in a client id');
});

test('ids: scopePath keeps every object under the client, and refuses traversal', () => {
  const id = randomClientId();
  assert.equal(scopePath(id, 'intake', 'a.png'), `clients/${id}/intake/a.png`);
  assert.throws(() => scopePath(id, '..', 'other'), /AF-DS-ID-TRAVERSAL/);
  assert.throws(() => scopePath('some-client-slug'), /AF-DS-ID-INVALID/);
  assert.ok(ownsPath(id, `clients/${id}/inbox.json`));
  assert.ok(!ownsPath(id, `clients/${randomClientId()}/inbox.json`));
});

// ---------------------------------------------------------------------------
// keys — only fingerprints are stored
// ---------------------------------------------------------------------------

test('keys: minting returns the secret once and stores only a fingerprint', async () => {
  const { secret, fingerprint } = await mintKey();
  assert.equal(secret.length, 64);
  assert.equal(fingerprint.length, 64);
  assert.notEqual(secret, fingerprint);
  assert.ok(!fingerprint.includes(secret));
});

test('keys: pairing code shape, single use, 5-try lock and 15-minute life', async () => {
  const { code, fingerprint } = await mintPairingCode();
  assert.match(code, /^[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$/, 'no 0/O/1/I/L may appear');
  let record = { client_id: 'c-' + 'a'.repeat(32), fingerprint, exp: T0 + 15 * 60 * 1000, tries: 0, status: 'open' };

  let attempt = await attemptPairing(record, 'ZZZZ-ZZZZ', T0);
  assert.equal(attempt.ok, false);
  assert.equal(attempt.code, AF_PAIR_WRONG);
  record = attempt.record;

  for (let i = 0; i < 4; i += 1) record = (await attemptPairing(record, 'ZZZZ-ZZZZ', T0)).record;
  assert.equal(record.status, 'locked', 'the 5th wrong try locks the code');
  assert.equal((await attemptPairing(record, code, T0)).code, AF_PAIR_LOCKED);

  const fresh = { ...record, tries: 0, status: 'open' };
  assert.equal((await attemptPairing(fresh, code, T0 + 16 * 60 * 1000)).code, AF_PAIR_EXPIRED);
  const good = await attemptPairing(fresh, code, T0);
  assert.equal(good.ok, true);
  assert.equal(good.record.status, 'burned');
});

// ---------------------------------------------------------------------------
// isolation — the load-bearing rule (see also prove/)
// ---------------------------------------------------------------------------

test('isolation: key resolution refuses malformed, unknown and revoked keys', async () => {
  const store = memStore();
  assert.equal((await resolveKey(store, 'short')).code, 'AF-DS-KEY-MALFORMED');
  assert.equal((await resolveKey(store, 'f'.repeat(64))).code, 'AF-DS-KEY-UNKNOWN');

  const { key, record } = await clientWithKey(store, 'box');
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify({ ...record, status: 'revoked' }));
  assert.equal((await resolveKey(store, key)).code, 'AF-DS-KEY-REVOKED');
});

test('isolation: a key claiming another client is refused, and the record wins', async () => {
  const store = memStore();
  const a = await clientWithKey(store);
  const b = await clientWithKey(store);

  const cross = await authorizeClient(store, a.key, b.clientId);
  assert.equal(cross.ok, false);
  assert.equal(cross.code, AF_ISO_CROSS);

  const own = await authorizeClient(store, a.key, a.clientId);
  assert.equal(own.ok, true);
  assert.equal(own.client_id, a.clientId);

  // A claim-free request still resolves to the key's OWN client.
  const silent = await authorizeClient(store, a.key, undefined);
  assert.equal(silent.client_id, a.clientId);
});

test('isolation: enrollment registers a new client and can never adopt an existing one', async () => {
  const store = memStore();
  const env = { DS_ENROLLMENT_SECRET: GOOD_ENV.DS_ENROLLMENT_SECRET };

  assert.equal((await enrollClient({ store, env, presentedSecret: 'wrong', nowMs: T0 })).code, AF_ENROLL_REFUSED);
  assert.equal((await enrollClient({ store, env: {}, presentedSecret: GOOD_ENV.DS_ENROLLMENT_SECRET, nowMs: T0 })).code, AF_ENROLL_REFUSED);

  const existing = await clientWithKey(store);
  const adopt = await enrollClient({
    store, env, presentedSecret: GOOD_ENV.DS_ENROLLMENT_SECRET,
    claimedClientId: existing.clientId, nowMs: T0,
  });
  assert.equal(adopt.ok, false);
  assert.equal(adopt.code, AF_ENROLL_REFUSED);

  const fresh = await enrollClient({ store, env, presentedSecret: GOOD_ENV.DS_ENROLLMENT_SECRET, nowMs: T0 });
  assert.equal(fresh.ok, true);
  assert.ok(isClientId(fresh.client_id));
});

// ---------------------------------------------------------------------------
// inbox
// ---------------------------------------------------------------------------

test('inbox: one line when an order waits, nothing when it does not', async () => {
  const objects = memObjects();
  assert.equal(inboxLine([]), null);
  assert.equal(inboxLine([{ order_id: 'r_1', state: 'in_production', title: 'x' }]), null);
  assert.equal(
    inboxLine([{ order_id: 'r_123', state: 'waiting', title: 'Spring Sale' }]),
    'DRAMA_ORDER r_123 "Spring Sale"',
  );
  assert.equal(
    inboxLine([{ order_id: 'r_1', state: 'waiting', title: 'a "quoted" title' }]),
    'DRAMA_ORDER r_1 "a \'quoted\' title"',
    'a title cannot break out of the quoted line',
  );

  const clientId = randomClientId();
  await writeInbox(objects, {
    clientId, nowMs: T0,
    orders: [{ order_id: 'r_1', state: 'waiting', title: 'One' }, { order_id: 'r_2', state: 'delivered', title: 'Two' }],
  });
  const inbox = await readInbox(objects, clientId);
  assert.equal(inbox.waiting.length, 1, 'only waiting orders reach the box');
  assert.equal(objects._mem.has(`clients/${clientId}/inbox.json`), true);
});

test('inbox: a check-in records the moment even when nothing is waiting', async () => {
  const store = memStore();
  const objects = memObjects();
  const clientId = randomClientId();
  const result = await checkIn(store, objects, { clientId, nowMs: T0, orders: [] });
  assert.equal(result.line, null);
  assert.equal(await store.kvGet(`checkin:${clientId}`), String(T0));
});

// ---------------------------------------------------------------------------
// uploads
// ---------------------------------------------------------------------------

test('uploads: shape rejections always name their code', () => {
  const base = { channel: 'image', filename: 'p.png', sizeBytes: 1024, contentType: 'image/png', headerBytes: [0x89, 0x50, 0x4e, 0x47] };
  assert.equal(validateUpload(base).ok, true);
  assert.equal(validateUpload({ ...base, channel: 'exe' }).code, 'AF-DS-UP-REJECT-FIELD');
  assert.equal(validateUpload({ ...base, filename: 'p.svg' }).code, AF_UP_FORMAT);
  assert.equal(validateUpload({ ...base, sizeBytes: 999 * 1024 * 1024 }).code, AF_UP_SIZE);
  assert.equal(validateUpload({ ...base, headerBytes: [0x00, 0x01, 0x02, 0x03] }).code, AF_UP_FORMAT);
  assert.equal(validateUpload({ ...base, headerBytes: undefined }).code, 'AF-DS-UP-REJECT-FIELD');
});

test('uploads: bytes never ride the Worker — a scoped presigned PUT comes back', async () => {
  const store = memStore();
  const clientId = randomClientId();
  const body = { channel: 'video', filename: 'clip.mp4', size_bytes: 2048, content_type: 'video/mp4', header_bytes: [0, 0, 0, 24, 102, 116, 121, 112] };

  const noCreds = await acceptUpload({ store, env: {}, clientId, body, nowUtc: 'x' });
  assert.equal(noCreds.code, AF_UP_CAPABILITY);
  assert.equal(noCreds.status, 503);

  const okRes = await acceptUpload({ store, env: GOOD_ENV, clientId, body, nowUtc: 'x' });
  assert.equal(okRes.ok, true);
  assert.equal(okRes.upload.method, 'PUT');
  assert.match(okRes.upload.url, /X-Amz-Signature=/);
  assert.ok(okRes.object_path.startsWith(`clients/${clientId}/intake/`), 'the object is scoped to the owner');
  assert.ok(!okRes.object_path.includes('..'));

  const job = await store.kvGet(`upload:${clientId}:${okRes.upload_id}`);
  assert.equal(JSON.parse(job).status, 'queued');

  const cross = await acceptUpload({ store, env: GOOD_ENV, clientId, body: { ...body, client_id: randomClientId() }, nowUtc: 'x' });
  assert.equal(cross.code, AF_UP_CROSS);
});

// ---------------------------------------------------------------------------
// retention — section 3.15
// ---------------------------------------------------------------------------

test('retention: each class is deleted when the plan says, and never-delete is proven', () => {
  const day = DAY_MS;
  assert.equal(retentionVerdict('intake_answer', { eventAtMs: T0, nowMs: T0 + day }).delete, true, 'intake goes at pickup');
  assert.equal(retentionVerdict('approval_file', { eventAtMs: T0, nowMs: T0 }).delete, true, 'approval goes at stage approval');
  assert.equal(retentionVerdict('r2_fallback_video', { eventAtMs: T0, nowMs: T0 + 7 * day - 1 }).keep, true);
  assert.equal(retentionVerdict('r2_fallback_video', { eventAtMs: T0, nowMs: T0 + 7 * day }).delete, true);
  assert.equal(retentionVerdict('status_record', { eventAtMs: T0, nowMs: T0 + 30 * day }).delete, true);
  assert.equal(retentionVerdict('waiting_unclaimed', { createdAtMs: T0, nowMs: T0 + 45 * day }).delete, true);
  assert.equal(retentionVerdict('project_object', { createdAtMs: T0, nowMs: T0 + 45 * day }).delete, true);

  for (const kind of ['enrollment_record', 'delivery_receipt', 'ghl_media']) {
    const v = retentionVerdict(kind, { createdAtMs: T0, eventAtMs: T0, nowMs: T0 + 3650 * day });
    assert.equal(v.delete, false, `${kind} must never be deleted`);
    assert.equal(v.never, true);
    assert.ok(RETENTION_RULES[kind].never);
  }
  assert.equal(retentionVerdict('mystery', { nowMs: T0 }).code, 'AF-DS-RET-UNKNOWN-KIND');
});

test('retention: a sweep partitions never-delete items out of the delete list', () => {
  const day = DAY_MS;
  const out = dueForDeletion([
    { kind: 'enrollment_record', path: 'clients/x/enrollment.json', created_at_ms: T0 },
    { kind: 'delivery_receipt', path: 'clients/x/receipt.json', created_at_ms: T0 },
    { kind: 'ghl_media', path: 'clients/x/ghl.json', created_at_ms: T0 },
    { kind: 'r2_fallback_video', path: 'clients/x/video.mp4', event_at_ms: T0 },
    { kind: 'status_record', path: 'clients/x/status.json', event_at_ms: T0 },
  ], T0 + 400 * day);
  assert.deepEqual(out.delete.sort(), ['clients/x/status.json', 'clients/x/video.mp4']);
  assert.equal(out.never.length, 3);
  assert.ok(!out.delete.some((p) => out.never.includes(p)));
});

// ---------------------------------------------------------------------------
// lifecycle — states, timers, precedence
// ---------------------------------------------------------------------------

test('lifecycle: the approved moves, and nothing moves out of a terminal state', () => {
  const waiting = { state: 'waiting', order_id: 'r_1', created_at: T0 };
  assert.equal(transition(waiting, 'claim', { nowMs: T0 }).order.state, 'in_production');
  assert.equal(transition(waiting, 'cancel', { nowMs: T0 }).order.state, 'cancelled');

  const cancelled = transition(waiting, 'cancel', { nowMs: T0 }).order;
  const after = transition(cancelled, 'claim', { nowMs: T0 });
  assert.equal(after.code, AF_STATE_TERMINAL);

  const running = transition(waiting, 'claim', { nowMs: T0 }).order;
  assert.equal(transition(running, 'deliver', { nowMs: T0 }).code, AF_STATE_ILLEGAL, 'no skipping to delivery');

  const paid = { ...running, paid_started: true };
  assert.equal(transition(paid, 'cancel', { nowMs: T0 }).code, AF_STATE_ILLEGAL, 'after spending, cancel is not offered');
});

test('lifecycle: timer precedence — cancelled wins, then acceptance, then 14 days', () => {
  const day = DAY_MS;
  const cancelled = { state: 'cancelled', delivered_at: T0 - 40 * day, created_at: T0 - 60 * day };
  assert.equal(resolveOrderState(cancelled, T0).state, 'cancelled', 'a terminal state is never overwritten');

  assert.equal(resolveOrderState({ state: 'delivered', delivered_at: T0, accepted_at: T0 + day }, T0 + 2 * day).reason, 'accepted');
  assert.equal(resolveOrderState({ state: 'delivered', delivered_at: T0, downloaded_at: T0 + day }, T0 + 2 * day).reason, 'downloaded');
  assert.equal(resolveOrderState({ state: 'delivered', delivered_at: T0 }, T0 + 13 * day).state, 'delivered');
  assert.equal(resolveOrderState({ state: 'delivered', delivered_at: T0 }, T0 + 14 * day).reason, 'done-timer-14d');
  assert.equal(resolveOrderState({ state: 'waiting', created_at: T0 }, T0 + 45 * day).state, 'expired');
});

// ---------------------------------------------------------------------------
// options — the real-wait text, and Option 3 behind a recorded approval
// ---------------------------------------------------------------------------

test('options: the four approved strings are reproduced verbatim', () => {
  const threeHours = T0 - 3 * 60 * 60 * 1000;
  assert.equal(
    optionLine({ option: 1, last_check_in: threeHours }, T0),
    'Your crew starts when you open Claude Code on your computer. Last check-in: 3 hours ago.',
  );
  assert.equal(
    optionLine({ option: 2, last_check_in: T0 - 60 * 1000 }, T0),
    'Your crew is watching. Orders start within about 2 minutes while your computer is on. Last check-in: 1 minute ago.',
  );
  assert.equal(
    optionLine({ option: 3, last_check_in: T0 - 2 * 60 * 1000 }, T0),
    'Your crew starts automatically within about 2 minutes while your computer is on and awake. Last check-in: 2 minutes ago.',
  );

  const stale = staleVerdict({
    record: { option: 2, timezone: 'UTC' }, lastCheckMs: T0 - 31 * 60 * 1000, hasWaitingOrder: true, nowMs: T0,
  });
  assert.equal(stale.stale, true);
  assert.match(stale.page_line, /^Your computer has not checked in since .*Your order is safe and starts when it is back\.$/);
  assert.match(stale.operator_line, /with an order waiting$/);
  assert.equal(staleVerdict({ record: {}, lastCheckMs: T0, hasWaitingOrder: false, nowMs: T0 }).stale, false);
});

test('options: Option 3 refuses without a recorded approval, and accepts with one', () => {
  assert.equal(setOption({}, 9, { nowMs: T0 }).code, AF_OPT_INVALID);
  assert.equal(setOption({}, 3, { nowMs: T0, approval: null }).code, AF_OPT_APPROVAL);
  assert.equal(setOption({}, 3, { nowMs: T0, approval: { option3: true } }).code, AF_OPT_APPROVAL, 'approval must name the client');
  const okRes = setOption({}, 3, { nowMs: T0, approval: { option3: true, client_name: 'Example Client' } });
  assert.equal(okRes.ok, true);
  assert.equal(okRes.record.option, 3);
});

// ---------------------------------------------------------------------------
// rule 3 — one operator record per client per day
// ---------------------------------------------------------------------------

test('rule 3: a second same-day operator record REPLACES the first, never stacks', async () => {
  const store = memStore();
  const clientId = randomClientId();

  const first = await writeOperatorRecord(store, { clientId, line: 'first line', nowMs: T0 });
  assert.equal(first.created, true);

  const second = await writeOperatorRecord(store, { clientId, line: 'second line', nowMs: T0 + 60 * 60 * 1000 });
  assert.equal(second.created, false, 'same day must not create a second record');
  assert.equal(second.replaced, true);
  assert.equal(await operatorRecordCount(store, clientId, T0), 1);

  const keys = [...store._mem.keys()].filter((k) => k.startsWith(`ops:${clientId}:`));
  assert.equal(keys.length, 1, 'exactly one stored record for the day');
  assert.equal(JSON.parse(store._mem.get(keys[0])).line, 'second line');

  const nextDay = await writeOperatorRecord(store, { clientId, line: 'tomorrow', nowMs: T0 + DAY_MS });
  assert.equal(nextDay.created, true);
  assert.equal([...store._mem.keys()].filter((k) => k.startsWith(`ops:${clientId}:`)).length, 2);
});

// ---------------------------------------------------------------------------
// the service entry — the routes U3/U4/U12 consume
// ---------------------------------------------------------------------------

test('service: health, enrollment, check-in, order and the cross-client read refusal', async () => {
  const store = memStore();
  const objects = memObjects();

  const health = await handle(get('/api/studio/health'), GOOD_ENV, store, objects);
  assert.equal(health.status, 200);
  assert.equal((await health.json()).version, SERVICE_VERSION);

  const badEnroll = await handle(post('/api/studio/enroll', { enrollment_secret: 'nope' }), GOOD_ENV, store, objects);
  assert.equal(badEnroll.status, 403);

  const enrolled = await handle(post('/api/studio/enroll', { enrollment_secret: GOOD_ENV.DS_ENROLLMENT_SECRET }), GOOD_ENV, store, objects);
  assert.equal(enrolled.status, 201);
  const box = await enrolled.json();
  assert.ok(isClientId(box.client_id));

  const noKey = await handle(post('/api/studio/checkin', {}), GOOD_ENV, store, objects);
  assert.equal(noKey.status, 401);

  const checkin = await handle(post('/api/studio/checkin', { orders: [{ order_id: 'r_9', state: 'waiting', title: 'Spring Sale' }] }, box.key), GOOD_ENV, store, objects);
  assert.equal((await checkin.json()).line, 'DRAMA_ORDER r_9 "Spring Sale"');

  const created = await handle(post('/api/studio/orders', { title: 'Spring Sale' }, box.key), GOOD_ENV, store, objects);
  assert.equal(created.status, 201);
  const order = (await created.json()).order;
  assert.equal(order.state, 'waiting');
  assert.equal(order.availability, 'not-delivered');

  // A DIFFERENT client's key cannot open this order. It is not a 500, not an
  // empty 200 — it is a refusal.
  const other = await handle(post('/api/studio/enroll', { enrollment_secret: GOOD_ENV.DS_ENROLLMENT_SECRET }), GOOD_ENV, store, objects);
  const otherBox = await other.json();
  const cross = await handle(get(`/api/studio/orders/${order.order_id}`, otherBox.key), GOOD_ENV, store, objects);
  assert.equal(cross.status, 404);
  assert.equal((await cross.json()).code, 'AF-DS-ORDER-MISSING');

  // The owner still sees it.
  const own = await handle(get(`/api/studio/orders/${order.order_id}`, box.key), GOOD_ENV, store, objects);
  assert.equal(own.status, 200);
});

test('service: pairing — admin mints, the code burns once, a machine key comes back', async () => {
  const store = memStore();
  const objects = memObjects();
  const { clientId } = await clientWithKey(store);

  const refused = await handle(post('/api/studio/admin/pairing-code', { admin_key: 'wrong', client_id: clientId }), GOOD_ENV, store, objects);
  assert.equal(refused.status, 403);

  const minted = await handle(post('/api/studio/admin/pairing-code', { admin_key: GOOD_ENV.DS_ADMIN_KEY, client_id: clientId }), GOOD_ENV, store, objects);
  assert.equal(minted.status, 201);
  const { code } = await minted.json();
  assert.match(code, /^[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$/);

  const paired = await handle(post('/api/studio/pair', { code, computer_name: 'Example Mac' }), GOOD_ENV, store, objects);
  assert.equal(paired.status, 201);
  const machine = await paired.json();
  assert.equal(machine.client_id, clientId);
  assert.ok(machine.key.length >= 32);

  const again = await handle(post('/api/studio/pair', { code }), GOOD_ENV, store, objects);
  assert.equal(again.status, 403, 'the code is single use');
});

test('service: the option line is served, and Option 3 is refused without approval', async () => {
  const store = memStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store);
  await store.kvPut(`checkin:${clientId}`, String(Date.now()));

  const line = await handle(get('/api/studio/options', key), GOOD_ENV, store, objects);
  assert.equal((await line.json()).option, 1);

  const noAdmin = await handle(post('/api/studio/options', { admin_key: 'wrong', option: 3, target_client_id: clientId }), GOOD_ENV, store, objects);
  assert.equal(noAdmin.status, 403);
  assert.equal((await noAdmin.json()).code, 'AF-DS-ADMIN-REFUSED');

  const refused = await handle(post('/api/studio/options', { admin_key: GOOD_ENV.DS_ADMIN_KEY, option: 3, target_client_id: clientId }), GOOD_ENV, store, objects);
  assert.equal(refused.status, 403);
  assert.equal((await refused.json()).code, AF_OPT_APPROVAL);

  const accepted = await handle(post('/api/studio/options', {
    admin_key: GOOD_ENV.DS_ADMIN_KEY, option: 3, target_client_id: clientId,
    approval: { option3: true, client_name: 'Example Client' },
  }), GOOD_ENV, store, objects);
  assert.equal(accepted.status, 200);
  assert.equal((await accepted.json()).option, 3);
});

test('isolation: readOwnObject refuses a path outside the caller scope', async () => {
  const objects = memObjects();
  const a = randomClientId();
  const b = randomClientId();
  await objects.objectPut(`clients/${b}/secret.json`, 'b-only');
  const { readOwnObject } = await import('../src/isolation.js');
  const attempt = await readOwnObject(objects, a, `clients/${b}/secret.json`);
  assert.equal(attempt.ok, false);
  assert.equal(attempt.code, AF_ISO_SCOPE);
});
