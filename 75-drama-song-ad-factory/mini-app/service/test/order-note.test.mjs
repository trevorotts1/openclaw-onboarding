// ============================================================================
// order-note.test.mjs — an order says why it needs the client, and every answer
// travels with the question it answers (U-Z11 / S75-106)
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/order-note.test.mjs
//
// Proves:
//   1. a `needs_you` event stores its `reason` on the order as `note`, the
//      order route shows it, and `answer` clears it;
//   2. a `cancel` event stores its reason the same way;
//   3. the note is trimmed to one page line (300 characters) and a reason that
//      is not text never becomes a note;
//   4. an order whose answers arrive with `reply_ids` stores the brief read by
//      id, whatever position the answers are in;
//   5. an order from a page that sends no `reply_ids` still stores the brief by
//      position, exactly as before;
//   6. a `reply_ids` list that is not one id per answer is refused.
//
// No live end to end: nothing is minted, no order is placed against the real
// studio, nothing runs against a deployed Worker.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';

import { handle } from '../src/index.js';
import { buildKeyRecord, mintKey } from '../src/keys.js';
import { randomClientId } from '../src/ids.js';
import { get, memObjects, memStore, post } from './fakes.mjs';

const T0 = Date.UTC(2026, 9, 13, 12, 0, 0);
const GOOD_ENV = { DS_ENROLLMENT_SECRET: 'enrollment-secret-placeholder-for-tests' };

const NOTE_MAX_CHARS = 300;

const BRIEF_ANSWERS = {
  offer: 'Sweet Details Cookie-Decorating Class',
  link: 'https://sweetdetailsbakery.example.com/class',
  audience: 'Busy moms 30-50. They should book a Saturday seat.',
  character: 'Maya, around 38, curly dark hair, pink apron with a whisk on it.',
  photos: 'My pink whisk logo and the photo of last month\'s students.',
};

/** The card's order after U-E01: the four typed screens, the choices, photos last. */
const CARD_IDS = ['offer', 'link', 'audience', 'character', 'models', 'length', 'music',
  'look', 'checkpoints', 'spend', 'model', 'shape', 'photos', ''];
const CARD_REPLIES = [BRIEF_ANSWERS.offer, BRIEF_ANSWERS.link, BRIEF_ANSWERS.audience,
  BRIEF_ANSWERS.character, '1', '1', '1', '1', '1', '$25', '1', '1',
  BRIEF_ANSWERS.photos, 'yes'];

async function clientWithKey(store, kind = 'box') {
  const clientId = randomClientId();
  const minted = await mintKey();
  const record = await buildKeyRecord({ clientId, kind, secret: minted.secret, nowMs: T0 });
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));
  return { clientId, key: minted.secret };
}

async function postOrder(store, objects, key, body) {
  const res = await handle(post('/api/studio/orders', body, key), GOOD_ENV, store, objects);
  return { status: res.status, data: await res.json() };
}

async function postState(store, objects, key, orderId, body) {
  const res = await handle(post(`/api/studio/orders/${orderId}/state`, body, key), GOOD_ENV, store, objects);
  return { status: res.status, data: await res.json() };
}

async function getOrder(store, objects, key, orderId) {
  const res = await handle(get(`/api/studio/orders/${orderId}`, key), GOOD_ENV, store, objects);
  return { status: res.status, data: await res.json() };
}

/** An order already in production, so `needs_you` is a legal move. */
async function orderInProduction(store, objects, key) {
  const created = await postOrder(store, objects, key, { title: 'Spring Sale' });
  assert.equal(created.status, 201, JSON.stringify(created.data));
  const orderId = created.data.order.order_id;
  const claimed = await postState(store, objects, key, orderId, { event: 'claim' });
  assert.equal(claimed.status, 200, JSON.stringify(claimed.data));
  return orderId;
}

// ---------------------------------------------------------------------------
// 1-3. the note
// ---------------------------------------------------------------------------

test('order note: needs_you stores the reason, the order route shows it, answer clears it', async () => {
  const store = memStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store);
  const orderId = await orderInProduction(store, objects, key);

  const reason = 'Your order is paused until you have your client\'s OK to use their story.';
  const halted = await postState(store, objects, key, orderId, { event: 'needs_you', reason });
  assert.equal(halted.status, 200, JSON.stringify(halted.data));
  assert.equal(halted.data.order.state, 'needs_you');
  assert.equal(halted.data.order.note, reason);

  // the box's own record carries it, not just the response
  const stored = JSON.parse(await store.kvGet(`order:${clientId}:${orderId}`));
  assert.equal(stored.note, reason);

  // and the order route the page reads shows it
  const shown = await getOrder(store, objects, key, orderId);
  assert.equal(shown.status, 200);
  assert.equal(shown.data.order.note, reason);

  // the client has seen it and acted: answer clears it
  const answered = await postState(store, objects, key, orderId, { event: 'answer' });
  assert.equal(answered.status, 200, JSON.stringify(answered.data));
  assert.equal(answered.data.order.state, 'in_production');
  assert.equal('note' in answered.data.order, false);
  assert.equal('note' in JSON.parse(await store.kvGet(`order:${clientId}:${orderId}`)), false);
});

test('order note: cancel stores its reason too, trimmed to one page line', async () => {
  const store = memStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store);

  const created = await postOrder(store, objects, key, { title: 'Spring Sale' });
  const orderId = created.data.order.order_id;
  const reason = 'x'.repeat(NOTE_MAX_CHARS + 80);
  const cancelled = await postState(store, objects, key, orderId, { event: 'cancel', reason });
  assert.equal(cancelled.status, 200, JSON.stringify(cancelled.data));
  assert.equal(cancelled.data.order.state, 'cancelled');
  assert.equal(cancelled.data.order.note.length, NOTE_MAX_CHARS);

  const stored = JSON.parse(await store.kvGet(`order:${clientId}:${orderId}`));
  assert.equal(stored.note.length, NOTE_MAX_CHARS);
});

test('order note: a reason that is not text never becomes a note', async () => {
  const store = memStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store);
  const orderId = await orderInProduction(store, objects, key);

  const halted = await postState(store, objects, key, orderId, { event: 'needs_you', reason: { code: 'X' } });
  assert.equal(halted.status, 200, JSON.stringify(halted.data));
  assert.equal(halted.data.order.note, '');

  const stored = JSON.parse(await store.kvGet(`order:${clientId}:${orderId}`));
  assert.equal(stored.note, '');
});

// ---------------------------------------------------------------------------
// 4-6. every answer travels with its question id
// ---------------------------------------------------------------------------

test('order note: reply_ids read the brief by id, whatever order the answers arrive in', async () => {
  const store = memStore();
  const objects = memObjects();
  const { key } = await clientWithKey(store);

  const created = await postOrder(store, objects, key, {
    title: 'Card order', replies: CARD_REPLIES, reply_ids: CARD_IDS, upload_ids: [],
  });
  assert.equal(created.status, 201, JSON.stringify(created.data));
  assert.equal(created.data.order.brief_complete, true);
  assert.deepEqual(created.data.order.brief, {
    offer: BRIEF_ANSWERS.offer,
    link: BRIEF_ANSWERS.link,
    audience: BRIEF_ANSWERS.audience,
    character: BRIEF_ANSWERS.character,
    photos: BRIEF_ANSWERS.photos,
  });
  // the ids ride the order, so the box can compare them with its own card
  assert.deepEqual(created.data.order.reply_ids, CARD_IDS);
  // and the replies are still the replay channel, untouched
  assert.deepEqual(created.data.order.replies, CARD_REPLIES);

  // shuffled: the same answers, a different order, the same brief
  const shuffledIds = ['photos', 'character', 'audience', 'link', 'offer', ''];
  const shuffled = await postOrder(store, objects, key, {
    title: 'Shuffled',
    replies: [BRIEF_ANSWERS.photos, BRIEF_ANSWERS.character, BRIEF_ANSWERS.audience,
      BRIEF_ANSWERS.link, BRIEF_ANSWERS.offer, 'yes'],
    reply_ids: shuffledIds,
  });
  assert.equal(shuffled.data.order.brief_complete, true);
  assert.equal(shuffled.data.order.brief.offer, BRIEF_ANSWERS.offer);
  assert.equal(shuffled.data.order.brief.photos, BRIEF_ANSWERS.photos);
});

test('order note: an old page with no reply_ids still stores the brief by position', async () => {
  const store = memStore();
  const objects = memObjects();
  const { key } = await clientWithKey(store);

  const created = await postOrder(store, objects, key, {
    title: 'Old page', replies: [
      BRIEF_ANSWERS.offer, BRIEF_ANSWERS.link, BRIEF_ANSWERS.audience,
      BRIEF_ANSWERS.character, BRIEF_ANSWERS.photos, '1', 'yes',
    ],
  });
  assert.equal(created.status, 201);
  assert.equal(created.data.order.brief_complete, true);
  assert.equal(created.data.order.brief.offer, BRIEF_ANSWERS.offer);
  // no ids were sent, so none are invented
  assert.equal('reply_ids' in created.data.order, false);
});

test('order note: a reply_ids list that is not one id per answer is refused', async () => {
  const store = memStore();
  const objects = memObjects();
  const { key } = await clientWithKey(store);

  const short = await postOrder(store, objects, key, {
    title: 'Short', replies: ['a', 'b'], reply_ids: ['offer'],
  });
  assert.equal(short.status, 400);
  assert.equal(short.data.code, 'AF-DS-ORDER-INVALID');

  const notList = await postOrder(store, objects, key, {
    title: 'Not a list', replies: ['a'], reply_ids: 'offer',
  });
  assert.equal(notList.status, 400);

  const notText = await postOrder(store, objects, key, {
    title: 'Not text', replies: ['a'], reply_ids: [7],
  });
  assert.equal(notText.status, 400);
});
