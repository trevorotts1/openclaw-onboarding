/**
 * Session read carries cards and the verdict (H-state).
 *
 * Runner:
 *   node --import tsx --test tests/chamber-session-cards.test.ts
 *
 * card_accepted frames carry only seat_id and round, so the chamber can show
 * stances, lines and the verdict only if GET /council/<id> returns them.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

import { repositorySessionReader, type CouncilSessionSource } from '../src/service/events.js';
import { CouncilFrontDoor } from '../src/service/front-door.js';
import { buildServiceIdentity } from '../src/service/identity.js';
import type { AuthorizationEnvelope } from '../src/persistence/envelope.js';

const envelope = { tenant_id: 't', company_id: 'c' } as unknown as AuthorizationEnvelope;
const stored = {
  spec: { session_id: 's1', mode: 'full', created_at: '2026-10-19T10:00:00Z', seat_ids: ['simon-sinek'] },
  brief: { question: 'Should we?', options: [{ id: 'A', label: 'Yes', kind: 'change' }] },
  scope: { tenant_id: 't', company_id: 'c' },
  state: { state: 'ROUND_1' },
  sample: false,
};
const cards = [
  { card_kind: 'advisor', seat_id: 'simon-sinek', round: 1, stance: 'support', preferred_option_id: 'A', decisive_arguments: ['Because why.'] },
];
const verdict = { result_kind: 'scored', label: 'GO', recommended_option_id: 'A', main_reasons: ['r'], option_scores: [] };

function source(extra: Record<string, unknown>): CouncilSessionSource {
  return { getSession: (_e: unknown, id: string) => (id === 's1' ? stored : null), ...extra } as unknown as CouncilSessionSource;
}

test('reader adds cards and verdict when the source has them', () => {
  const seen: unknown[][] = [];
  const reader = repositorySessionReader({
    repositories: source({
      listCards: (e: unknown, id: string) => { seen.push(['cards', e, id]); return cards; },
      getVerdict: (e: unknown, id: string) => { seen.push(['verdict', e, id]); return verdict; },
    }),
    envelope,
  });
  const record = reader.read('s1') as Record<string, unknown>;
  assert.deepEqual(record.cards, cards);
  assert.deepEqual(record.verdict, verdict);
  assert.deepEqual(seen, [['cards', envelope, 's1'], ['verdict', envelope, 's1']]);
  assert.equal(record.session_id, 's1');
  assert.equal(record.state, stored.state);
});

test('verdict is null when there is none yet, cards may be empty', () => {
  const reader = repositorySessionReader({
    repositories: source({ listCards: () => [], getVerdict: () => null }),
    envelope,
  });
  const record = reader.read('s1') as Record<string, unknown>;
  assert.deepEqual(record.cards, []);
  assert.equal(record.verdict, null);
});

test('a source without them leaves the record unchanged: no cards or verdict key', () => {
  const reader = repositorySessionReader({ repositories: source({}), envelope });
  const record = reader.read('s1') as Record<string, unknown>;
  assert.deepEqual(Object.keys(record).sort(), ['authority', 'brief', 'sample', 'scope', 'session_id', 'spec', 'state']);
  assert.equal('cards' in record, false);
  assert.equal('verdict' in record, false);
  // Only one of the two present: only that key is added.
  const onlyCards = repositorySessionReader({ repositories: source({ listCards: () => cards }), envelope }).read('s1') as Record<string, unknown>;
  assert.equal('verdict' in onlyCards, false);
  assert.deepEqual(onlyCards.cards, cards);
  assert.equal(reader.read('missing'), null);
});

test('GET /council/<id> through the front door serves cards and verdict', async () => {
  const reader = repositorySessionReader({
    repositories: source({ listCards: () => cards, getVerdict: () => verdict }),
    envelope,
  });
  const door = new CouncilFrontDoor({
    identity: buildServiceIdentity({
      tenant_id: 'tenant-h', company_id: 'company-h', data_dir: 'h-data', started_at: '2026-10-19T12:00:00.000Z',
    }),
    ports: [0],
    sessionReader: reader,
  });
  const started = await door.start();
  assert.equal(started.outcome, 'started');
  try {
    const res = await fetch(`${started.origin}/council/s1`);
    assert.equal(res.status, 200);
    const body = (await res.json()) as { session: Record<string, unknown> };
    assert.deepEqual(body.session.cards, cards);
    assert.deepEqual(body.session.verdict, verdict);
    assert.equal((body.session.brief as { question: string }).question, 'Should we?');
    assert.equal((await fetch(`${started.origin}/council/nope`)).status, 404);
  } finally {
    await door.stop();
  }
});
