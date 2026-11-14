// ============================================================================
// reply-format.test.mjs — an option pick travels with its text (S75-059)
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/reply-format.test.mjs
//
// Since S75-059 the page sends a picked option as "<n>. <option text>" instead
// of the bare number, so the box can compare the text after the number with its
// own card and ask the client when the card no longer matches instead of
// quietly choosing a different option (the box half is U-K04).
//
// That changes what arrives at the two places in the service that read replies:
//   * validateReplies — the size/type gate. Must take the new shape as text and
//     hand it on unchanged.
//   * readBrief — it turns the first five replies into the brief the factory
//     reads. An option pick was never the client's own words, in either shape.
//
// No live end to end: nothing is minted against a running studio.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';

import { OPTION_PICK_REPLY, readBrief, handle } from '../src/index.js';
import { validateReplies } from '../src/page-api.js';
import { buildKeyRecord, mintKey } from '../src/keys.js';
import { randomClientId } from '../src/ids.js';
import { memObjects, memStore, post } from './fakes.mjs';

const T0 = Date.UTC(2026, 9, 13, 12, 0, 0);
const GOOD_ENV = { DS_ENROLLMENT_SECRET: 'enrollment-secret-placeholder-for-tests' };

const TYPED = {
  offer: 'A cookie-decorating class',
  link: 'https://bakery.example.com/class',
  audience: 'Busy parents 30-50. They should book a Saturday seat.',
  character: 'Maya, about 38, curly dark hair, pink apron.',
  photos: 'The pink whisk logo and last month\'s students.',
};

/** Five typed brief answers, then picks in the S75-059 wire shape. */
function numberedReplies() {
  return [
    TYPED.offer, TYPED.link, TYPED.audience, TYPED.character, TYPED.photos,
    '1. Recommended setup', '1. 60 seconds', '2. R&B Flow', '3. Sketch to Life (Hybrid)',
    '4. Google Veo 3.1', '1. A different maximum', '1. Yes, show me first',
    '2. No, just make it', '1. Yes, show me first',
    'yes',
  ];
}

async function clientWithKey(store) {
  const clientId = randomClientId();
  const minted = await mintKey();
  const record = await buildKeyRecord({ clientId, kind: 'link', secret: minted.secret, nowMs: T0 });
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));
  return { clientId, key: minted.secret };
}

// ---------------------------------------------------------------------------
// 1. the gate takes the new shape as text, unchanged
// ---------------------------------------------------------------------------

test('reply format: validateReplies keeps "<n>. <option text>" exactly as sent', () => {
  const replies = numberedReplies();
  const checked = validateReplies(replies, []);
  assert.equal(checked.ok, true, JSON.stringify(checked));
  assert.deepEqual(checked.replies, replies, 'the gate rewrote the client\'s answers');
  assert.match(checked.replies[7], /^2\. R&B Flow$/);
});

test('reply format: the gate still refuses what it refused before', () => {
  assert.equal(validateReplies('not a list', []).ok, false);
  assert.equal(validateReplies([2], []).ok, false);
  assert.equal(validateReplies(['x'.repeat(2001)], []).ok, false);
});

// ---------------------------------------------------------------------------
// 2. an option pick is never the brief, in either shape
// ---------------------------------------------------------------------------

test('reply format: readBrief takes the typed answers and drops every option pick', () => {
  const read = readBrief(numberedReplies());
  assert.equal(read.complete, true, `missing ${read.missing}`);
  assert.deepEqual(read.brief, TYPED, 'a pick leaked into the brief');

  // The page older than S75-059 sent the same picks as bare numbers.
  const legacy = readBrief(['1', '2', '1', '1', '3', '$25']);
  assert.deepEqual(legacy.brief, {}, 'a bare number was read as the brief');
  assert.equal(legacy.complete, false);
});

test('reply format: a numbered answer at a brief slot is a pick, not typed words', () => {
  // The five brief screens are typed, so this cannot come from the page today.
  // If a numbered pick ever lands in a brief slot it must not become the brief.
  const read = readBrief(['1. Coffee class', TYPED.link, TYPED.audience, TYPED.character, TYPED.photos]);
  assert.equal('offer' in read.brief, false, 'an option text was stored as the offer');
  assert.deepEqual(read.missing, ['offer']);
});

test('reply format: typed words a client numbered themselves stay out, an inner number is kept', () => {
  // A leading "<n>. " is the wire shape of a pick; inside a sentence it is prose.
  const read = readBrief([TYPED.offer, 'Ads for 1. small shops and 2. bakeries',
    TYPED.audience, TYPED.character, TYPED.photos]);
  assert.equal(read.brief.link, 'Ads for 1. small shops and 2. bakeries');
  assert.equal(read.complete, true);
});

test('reply format: the pick pattern is the one the page sends', () => {
  assert.equal(OPTION_PICK_REPLY.test('1'), true);
  assert.equal(OPTION_PICK_REPLY.test('1. R&B Flow'), true);
  assert.equal(OPTION_PICK_REPLY.test('R&B Flow'), false);
  assert.equal(OPTION_PICK_REPLY.test('1.2 million views'), false);
  assert.equal(OPTION_PICK_REPLY.test('3 apples a day'), false);
});

// ---------------------------------------------------------------------------
// 3. an order posted in the new shape stores the replies untouched
// ---------------------------------------------------------------------------

test('reply format: an order keeps the numbered replies and still carries the brief', async () => {
  const store = memStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store);

  const replies = numberedReplies();
  const res = await handle(post('/api/studio/orders', { title: 'Spring Sale', replies, upload_ids: [] }, key),
    GOOD_ENV, store, objects);
  assert.equal(res.status, 201);
  const data = await res.json();
  assert.deepEqual(data.order.replies, replies, 'the replay channel was rewritten');
  assert.equal(data.order.brief_complete, true);
  assert.deepEqual(data.order.brief, TYPED);

  const stored = JSON.parse(await store.kvGet(`order:${clientId}:${data.order.order_id}`));
  assert.deepEqual(stored.replies, replies);
  assert.equal(stored.brief.offer, TYPED.offer);
});
