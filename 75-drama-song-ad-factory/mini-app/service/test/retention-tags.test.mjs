// ============================================================================
// retention-tags.test.mjs — Drama Studio service: every stored object carries a
// retention kind the table knows (S75-083)
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/retention-tags.test.mjs
//
// THE DEFECT THIS PINS. retention.js named eleven kinds, and nothing in
// production wrote any of them: every real object reached the sweep as an
// unknown kind and was kept forever (AF-DS-RET-UNKNOWN-KIND -> keep).
//
// THE CHECK. Scan every production writer under src/ for the retention tag it
// emits (withRetentionKind's kind argument) and print the intersection with
// RETENTION_RULES. Every written kind must resolve. Before the fix that list is
// empty, which is the failure this test exists to make loud.
//
// The service's own `kind` field is a DIFFERENT vocabulary — a key's role
// ('link' | 'box' | 'machine', keys.js) and a delivery's transport ('ghl' |
// 'r2', index.js) — and it is deliberately not renamed: stored records keep
// their meaning and the retention tag lives beside them.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  AF_RET_UNKNOWN_KIND,
  RETENTION_RULES,
  orderRetentionKind,
  retentionVerdict,
  withRetentionKind,
} from '../src/retention.js';
import { writeInbox } from '../src/inbox.js';
import { writeOperatorRecord } from '../src/lifecycle.js';
import { registerSubscription, subscriptionKey } from '../src/push.js';
import { enrollClient } from '../src/isolation.js';
import { buildKeyRecord, mintKey } from '../src/keys.js';
import { randomClientId } from '../src/ids.js';
import { handle } from '../src/index.js';
import { memObjects, memStore, post } from './fakes.mjs';

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const T0 = 1_700_000_000_000;

/** Every expected production writer of a retention-managed stored object. */
const WRITERS = [
  'index.js',
  'inbox.js',
  'isolation.js',
  'lifecycle.js',
  'page-api.js',
  'push.js',
  'uploads.js',
];

/**
 * Every `withRetentionKind(...)` call's argument text in one source file,
 * paren-balanced so an object literal's commas and braces do not confuse it.
 */
function tagCalls(src) {
  const NAME = 'withRetentionKind(';
  const out = [];
  let i = src.indexOf(NAME);
  while (i !== -1) {
    let depth = 0;
    let j = i + NAME.length - 1;
    for (; j < src.length; j++) {
      const c = src[j];
      if (c === "'") {
        for (j++; j < src.length && src[j] !== "'"; j++) {
          if (src[j] === '\\') j++;
        }
        continue;
      }
      if (c === '(') depth++;
      else if (c === ')') {
        depth--;
        if (depth === 0) break;
      }
    }
    out.push(src.slice(i + NAME.length, j));
    i = src.indexOf(NAME, j + 1);
  }
  return out;
}

/** The kind expression of one `withRetentionKind(record, <kind>)` call: the text
 *  after the last top-level comma, so an object literal's commas never confuse it. */
function kindExpr(arg) {
  let depth = 0;
  let last = -1;
  for (let i = 0; i < arg.length; i++) {
    const c = arg[i];
    if (c === "'") {
      for (i++; i < arg.length && arg[i] !== "'"; i++) {
        if (arg[i] === '\\') i++;
      }
      continue;
    }
    if (c === '(' || c === '{' || c === '[') depth++;
    else if (c === ')' || c === '}' || c === ']') depth--;
    else if (c === ',' && depth === 0) last = i;
  }
  return arg.slice(last + 1).trim();
}

function scanWriters() {
  const perFile = {};
  const literals = new Set();
  const computed = new Set();
  for (const name of readdirSync(SRC)) {
    if (!name.endsWith('.js')) continue;
    // retention.js DEFINES the writer-side helper; it stores nothing.
    if (name === 'retention.js') continue;
    const calls = tagCalls(readFileSync(join(SRC, name), 'utf8'));
    if (!calls.length) continue;
    perFile[name] = calls.length;
    for (const arg of calls) {
      const expr = kindExpr(arg);
      const quoted = [...expr.matchAll(/'([a-z0-9_]+)'/g)].map((m) => m[1]);
      if (quoted.length) quoted.forEach((kind) => literals.add(kind));
      else computed.add(expr);
    }
  }
  return { perFile, literals, computed };
}

test('retention tags: every kind a production writer emits resolves in RETENTION_RULES', (t) => {
  const { perFile, literals, computed } = scanWriters();

  t.diagnostic(`writer files emitting a retention tag: ${JSON.stringify(perFile)}`);
  t.diagnostic(`kinds written: ${JSON.stringify([...literals].sort())}`);
  t.diagnostic(`computed tags (order state): ${JSON.stringify([...computed])}`);

  // The regression: before the fix, no writer emitted any tag at all.
  assert.ok(literals.size > 0, 'no production writer emits a retention kind');

  // Every writer of a retention-managed object carries the tag.
  for (const name of WRITERS) {
    assert.ok(perFile[name] >= 1, `${name} writes a stored object but emits no retention kind`);
  }

  // Every written kind is a table name, so no real object falls to
  // AF-DS-RET-UNKNOWN-KIND -> keep.
  const unresolved = [...literals].filter((kind) => !Object.prototype.hasOwnProperty.call(RETENTION_RULES, kind));
  assert.deepEqual(unresolved, [], 'a written kind is absent from RETENTION_RULES');

  // A tag computed from the record's state is the one computed form; both of its
  // answers resolve (and the behavioural test below proves it reaches storage).
  assert.ok(computed.size > 0, 'the order tag must be computed at the writer');
  for (const expr of computed) assert.match(expr, /orderRetentionKind\(/);
  for (const state of ['waiting', 'delivered']) {
    const kind = orderRetentionKind({ state });
    assert.ok(Object.prototype.hasOwnProperty.call(RETENTION_RULES, kind), `order tag for ${state} resolves`);
    assert.notEqual(retentionVerdict(kind, { createdAtMs: T0, eventAtMs: T0, nowMs: T0 }).code, AF_RET_UNKNOWN_KIND);
  }

  // A name the table does not know is refused at the writer, as keys.js refuses
  // an unknown key kind.
  assert.throws(() => withRetentionKind({}, 'mystery'), new RegExp(AF_RET_UNKNOWN_KIND));
});

// ---------------------------------------------------------------------------
// The tags really land in what is stored
// ---------------------------------------------------------------------------

function storedRecord(raw) {
  const record = JSON.parse(raw);
  assert.ok(record.retention_kind, 'the stored record carries no retention kind');
  assert.notEqual(
    retentionVerdict(record.retention_kind, { createdAtMs: T0, eventAtMs: T0, nowMs: T0 }).code,
    AF_RET_UNKNOWN_KIND,
    `stored kind ${record.retention_kind} does not resolve`,
  );
  return record;
}

test('retention tags: the module writers store a resolving kind', async () => {
  const store = memStore();
  const objects = memObjects();
  const clientId = randomClientId();

  await writeInbox(objects, { clientId, nowMs: T0, orders: [] });
  const inbox = await objects.objectGet(`clients/${clientId}/inbox.json`);
  assert.equal(storedRecord(inbox.value).retention_kind, 'project_object');

  const operator = await writeOperatorRecord(store, { clientId, line: 'one line', nowMs: T0 });
  assert.equal(storedRecord(await store.kvGet(operator.key)).retention_kind, 'status_record');

  const sub = await registerSubscription(store, {
    clientId,
    subscription: { endpoint: 'https://push.example/1', keys: { p256dh: 'a', auth: 'b' } },
    userAgent: 'test',
    nowMs: T0,
    entropyHex: 'ab'.repeat(12),
  });
  assert.equal(sub.ok, true);
  assert.equal(
    storedRecord(await store.kvGet(subscriptionKey(clientId, sub.record.subscription_id))).retention_kind,
    'push_subscription',
  );

  const enrolled = await enrollClient(store, { env: { DS_ENROLLMENT_SECRET: 's3cret' }, presentedSecret: 's3cret', nowMs: T0 });
  assert.equal(enrolled.ok, true);
  assert.equal(storedRecord(await store.kvGet(`client:${enrolled.client_id}`)).retention_kind, 'enrollment_record');
});

test('retention tags: an order record is tagged by its state, and its delivery copy by its transport', async () => {
  const store = memStore();
  const objects = memObjects();
  const clientId = randomClientId();
  const minted = await mintKey();
  const keyRecord = await buildKeyRecord({ clientId, kind: 'box', secret: minted.secret, nowMs: T0 });
  await store.kvPut(`key:${keyRecord.fingerprint}`, JSON.stringify(keyRecord));

  const created = await handle(
    post('/api/studio/orders', { title: 'Spring Sale', replies: ['1'] }, minted.secret),
    {},
    store,
    objects,
  );
  assert.equal(created.status, 201);
  const orderId = (await created.json()).order.order_id;

  assert.equal(storedRecord(await store.kvGet(`order:${clientId}:${orderId}`)).retention_kind, 'waiting_unclaimed');

  for (const event of ['claim', 'ready']) {
    const moved = await handle(post(`/api/studio/orders/${orderId}/state`, { event }, minted.secret), {}, store, objects);
    assert.equal(moved.status, 200, event);
  }
  assert.equal(storedRecord(await store.kvGet(`order:${clientId}:${orderId}`)).retention_kind, 'status_record');

  const delivered = await handle(
    post(`/api/studio/orders/${orderId}/state`, {
      event: 'deliver',
      delivery: { url: 'https://media.example/v/1', kind: 'r2' },
    }, minted.secret),
    {},
    store,
    objects,
  );
  assert.equal(delivered.status, 200);
  const order = storedRecord(await store.kvGet(`order:${clientId}:${orderId}`));
  assert.equal(order.delivery.retention_kind, 'r2_fallback_video', 'the R2 copy is the 7-day class');
});
