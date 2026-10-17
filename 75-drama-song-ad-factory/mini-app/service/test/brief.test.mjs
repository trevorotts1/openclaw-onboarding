// ============================================================================
// brief.test.mjs — the story brief an order carries (DSR-105)
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/brief.test.mjs
//
// The chat intake asks for the offer, the link, the audience, the character
// and the photos; the studio page asked only the nine production choices, so a
// run started here had no brief and no document said where one would come from.
// intake_card.py now asks those five first, and the service reads them back
// out of the leading replies onto the order record.
//
// Proves four things:
//   1. the ids this service reads are the card's FIRST five questions, checked
//      against the committed ui/questions.json -- the same file the page is
//      served, which questions-drift.mjs regenerates from intake_card.py, so a
//      reordering of the card turns this test red instead of silently moving
//      the brief onto the wrong answers;
//   2. an order posted with the brief stores it and reads it back;
//   3. an order WITHOUT the brief is not refused -- the answers are the
//      client's work -- but is stored clearly marked incomplete, naming what
//      is missing;
//   4. the nine-choice flow still works end to end in a fixture: fourteen
//      replies, a complete brief, a waiting order, and the replies untouched.
//
// No live end to end: nothing is minted, no order is placed against the real
// studio, nothing runs against a deployed Worker.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { BRIEF_QUESTION_IDS, BRIEF_REQUIRED_IDS, handle, readBrief } from '../src/index.js';
import { buildKeyRecord, mintKey } from '../src/keys.js';
import { randomClientId } from '../src/ids.js';
import { memObjects, memStore, post } from './fakes.mjs';

const T0 = Date.UTC(2026, 9, 13, 12, 0, 0);
const GOOD_ENV = { DS_ENROLLMENT_SECRET: 'enrollment-secret-placeholder-for-tests' };

const HERE = dirname(fileURLToPath(import.meta.url));
const QUESTIONS_JSON = resolve(HERE, '..', '..', 'ui', 'questions.json');

async function clientWithKey(store, kind = 'link') {
  const clientId = randomClientId();
  const minted = await mintKey();
  const record = await buildKeyRecord({ clientId, kind, secret: minted.secret, nowMs: T0 });
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));
  return { clientId, key: minted.secret };
}

/** The fourteen replies a client gives on the page: five typed, nine picked. */
const BRIEF_ANSWERS = {
  offer: 'Sweet Details Cookie-Decorating Class',
  link: 'https://sweetdetailsbakery.example.com/class',
  audience: 'Busy moms 30-50. They should book a Saturday seat.',
  character: 'Maya, around 38, curly dark hair, pink apron with a whisk on it.',
  photos: 'My pink whisk logo and the photo of last month\'s students.',
};

function fullReplies() {
  // five typed brief answers, then AI MODELS / LENGTH / MUSIC / LOOK / MODEL /
  // BUDGET / STORYBOARD / SONG / SCRIPT -- the same shape intake_card.py asks.
  return [
    BRIEF_ANSWERS.offer,
    BRIEF_ANSWERS.link,
    BRIEF_ANSWERS.audience,
    BRIEF_ANSWERS.character,
    BRIEF_ANSWERS.photos,
    '1', '1', '1', '1', '1', '$25', '1', '1', '1',
    'yes',
  ];
}

async function postOrder(store, objects, key, body) {
  const res = await handle(post('/api/studio/orders', body, key), GOOD_ENV, store, objects);
  return { status: res.status, data: await res.json() };
}

// ---------------------------------------------------------------------------
// 1. the ids are the card's first five questions
// ---------------------------------------------------------------------------

test('brief: the ids this service reads are the card\'s first five questions', () => {
  const committed = JSON.parse(readFileSync(QUESTIONS_JSON, 'utf8'));
  const leading = committed.questions.slice(0, BRIEF_QUESTION_IDS.length).map((q) => q.id);
  assert.deepEqual(leading, BRIEF_QUESTION_IDS,
    'the committed questions.json no longer opens with the brief; readBrief would read the wrong replies');
  // the five before them are the production choices, so nothing was dropped
  assert.equal(committed.question_count, committed.questions.length);
  assert.ok(committed.questions.length > BRIEF_QUESTION_IDS.length);

  // and the page is told which screens are typed, so it shows a text box and
  // never a menu, without sniffing the option wording
  const typed = committed.questions.filter((q) => q.typed).map((q) => q.id);
  assert.deepEqual(typed, BRIEF_QUESTION_IDS);
  for (const q of committed.questions.filter((x) => x.typed)) {
    assert.equal(q.options.length, 1, q.id);
    assert.match(q.options[0].detail, /^reply with/i, q.id);
  }
});

test('brief: readBrief takes the typed answers, trims them and names what is missing', () => {
  const full = readBrief(fullReplies());
  assert.equal(full.complete, true, `expected a complete brief, missing ${full.missing}`);
  assert.deepEqual(full.missing, []);
  assert.equal(full.brief.offer, BRIEF_ANSWERS.offer);
  assert.equal(full.brief.photos, BRIEF_ANSWERS.photos);

  const thin = readBrief(['  ', '', 'Busy moms 30-50. Book a seat.', null, undefined, '1']);
  assert.equal(thin.complete, false);
  assert.deepEqual(thin.missing, ['offer', 'link', 'character']);
  assert.deepEqual(Object.keys(thin.brief), ['audience']);

  // a bare number is an option pick, never somebody's offer: a page loaded
  // before this fix sends the nine choices as numbers and must not be read as
  // a brief
  const legacy = readBrief(['1', '2', '1', '1', '3', '$25']);
  assert.equal(legacy.complete, false);
  assert.deepEqual(legacy.brief, {});
  assert.deepEqual(legacy.missing, BRIEF_REQUIRED_IDS);

  // photos is asked and stored but never required
  const noPhotos = readBrief([BRIEF_ANSWERS.offer, BRIEF_ANSWERS.link, BRIEF_ANSWERS.audience,
    BRIEF_ANSWERS.character, 'none']);
  assert.equal(noPhotos.complete, true);
  assert.equal(noPhotos.brief.photos, 'none');

  assert.deepEqual(BRIEF_REQUIRED_IDS, ['offer', 'link', 'audience', 'character']);
  assert.ok(!BRIEF_REQUIRED_IDS.includes('photos'), 'photos must stay optional');
});

// ---------------------------------------------------------------------------
// 2. an order carrying the brief stores it and reads it back
// ---------------------------------------------------------------------------

test('brief: an order with the brief stores it beside the replies, and it reads back', async () => {
  const store = memStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store);

  const replies = fullReplies();
  const created = await postOrder(store, objects, key, { title: 'Spring Sale', replies, upload_ids: [] });
  assert.equal(created.status, 201, JSON.stringify(created.data));

  assert.equal(created.data.order.brief_complete, true);
  assert.deepEqual(created.data.order.brief_missing, []);
  assert.deepEqual(created.data.order.brief, {
    offer: BRIEF_ANSWERS.offer,
    link: BRIEF_ANSWERS.link,
    audience: BRIEF_ANSWERS.audience,
    character: BRIEF_ANSWERS.character,
    photos: BRIEF_ANSWERS.photos,
  });
  // the replies are the replay channel and are never rewritten
  assert.deepEqual(created.data.order.replies, replies);

  // and it is still on the stored record the box polls, not just the response
  const orderId = created.data.order.order_id;
  const stored = JSON.parse(await store.kvGet(`order:${clientId}:${orderId}`));
  assert.equal(stored.brief.offer, BRIEF_ANSWERS.offer);
  assert.equal(stored.brief.character, BRIEF_ANSWERS.character);
  assert.equal(stored.brief_complete, true);
  assert.deepEqual(stored.replies, replies);
});

// ---------------------------------------------------------------------------
// 3. an order WITHOUT the brief is marked incomplete, never silently complete
// ---------------------------------------------------------------------------

test('brief: an order without the brief is stored clearly marked incomplete', async () => {
  const store = memStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store);

  // the nine production choices only -- exactly what the page sent before DSR-105
  const created = await postOrder(store, objects, key, {
    title: 'Old page order', replies: ['1', '1', '1', '1', '1', '$25', '1', '1', '1', 'yes'],
  });
  assert.equal(created.status, 201, 'the client\'s answers are never refused');
  assert.equal(created.data.order.brief_complete, false);
  assert.deepEqual(created.data.order.brief_missing, BRIEF_REQUIRED_IDS);
  assert.deepEqual(created.data.order.brief, {}, 'nothing may be invented for a brief nobody gave');

  const orderId = created.data.order.order_id;
  const stored = JSON.parse(await store.kvGet(`order:${clientId}:${orderId}`));
  assert.equal(stored.brief_complete, false);
  assert.deepEqual(stored.brief_missing, BRIEF_REQUIRED_IDS);

  // an empty order is incomplete too, not an error and not a complete brief
  const empty = await postOrder(store, objects, key, { title: 'Nothing yet', replies: [] });
  assert.equal(empty.status, 201);
  assert.equal(empty.data.order.brief_complete, false);
  assert.deepEqual(empty.data.order.brief_missing, BRIEF_REQUIRED_IDS);
});

test('brief: a half-answered brief names only the half that is missing', async () => {
  const store = memStore();
  const objects = memObjects();
  const { key } = await clientWithKey(store);

  const created = await postOrder(store, objects, key, {
    title: 'Half a brief',
    replies: [BRIEF_ANSWERS.offer, BRIEF_ANSWERS.link, BRIEF_ANSWERS.audience,
      '', BRIEF_ANSWERS.photos, '1', '1', '1', '1', '1', '$25', '1', '1', '1', 'yes'],
  });
  assert.equal(created.data.order.brief_complete, false);
  assert.deepEqual(created.data.order.brief_missing, ['character']);
  assert.equal(created.data.order.brief.offer, BRIEF_ANSWERS.offer);
  assert.equal('character' in created.data.order.brief, false);
});

// ---------------------------------------------------------------------------
// 4. the nine-choice flow still works end to end in a fixture
// ---------------------------------------------------------------------------

test('brief: the fourteen-question flow still ends in a waiting order', async () => {
  const store = memStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store);

  // the draft is saved and then locked in, exactly as the page does it
  const draft = await handle(
    new Request('https://studio.example/api/studio/draft', {
      method: 'PUT',
      headers: { 'content-type': 'application/json', 'x-ds-key': key },
      body: JSON.stringify({ replies: fullReplies().slice(0, -1) }),
    }), GOOD_ENV, store, objects);
  assert.equal(draft.status, 200, JSON.stringify(await draft.json()));

  const created = await postOrder(store, objects, key, {
    title: 'Drama video 2026-10-13', replies: fullReplies(), upload_ids: [],
  });
  assert.equal(created.status, 201);
  assert.equal(created.data.order.state, 'waiting');
  assert.equal(created.data.order.replies.length, 15, 'five brief, nine choices, one yes');
  assert.equal(created.data.order.brief_complete, true);

  // Lock it in ends the draft, and the inbox the box polls carries the brief
  const session = await handle(
    new Request('https://studio.example/api/studio/session', { headers: { 'x-ds-key': key } }),
    GOOD_ENV, store, objects);
  const seen = await session.json();
  assert.equal(seen.draft, null, 'Lock it in clears the draft');
  assert.equal(seen.orders[0].brief_complete, true);
  assert.equal(seen.orders[0].brief.offer, BRIEF_ANSWERS.offer);
  assert.equal(clientId, seen.client_id);
});
