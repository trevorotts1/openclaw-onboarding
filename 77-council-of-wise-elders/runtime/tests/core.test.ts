/**
 * CWE-004 foundation unit tests: paths, budget ledger, operation
 * leases, and the local SQLite store. These exercise the real
 * implementations against real files in temporary directories.
 */
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import { DEFAULT_COUNCIL_SETTINGS } from '../src/contracts/index.js';
import { InProcessBudgetLedger } from '../src/cli/budget.js';
import { CouncilEngine } from '../src/cli/engine.js';
import { CouncilError } from '../src/cli/errors.js';
import { buildSampleSession } from '../src/cli/fixture-transport.js';
import { InProcessLeaseProvider } from '../src/cli/leases.js';
import { LocalSqliteStore } from '../src/cli/local-store.js';
import { defaultDataDir, resolveDataDir } from '../src/cli/paths.js';
import { grantHost, tempDataDir } from './helpers.js';

// ---------------------------------------------------------------- paths

test('paths: XDG default, env override, explicit override, skill-tree rejection', () => {
  const env = { XDG_DATA_HOME: '/tmp/xdg-test' } as NodeJS.ProcessEnv;
  assert.equal(
    defaultDataDir(env),
    join('/tmp/xdg-test', 'blackceo', 'wise-elders'),
  );
  assert.equal(
    resolveDataDir({ env: { BLACKCEO_COUNCIL_DATA_DIR: '/tmp/from-env' } as NodeJS.ProcessEnv }),
    '/tmp/from-env',
  );
  assert.equal(
    resolveDataDir({ override: '/tmp/from-flag', env: {} as NodeJS.ProcessEnv }),
    '/tmp/from-flag',
  );
  assert.throws(
    () =>
      resolveDataDir({
        override: '/skills/77-council-of-wise-elders/state',
        env: {} as NodeJS.ProcessEnv,
        skillRoot: '/skills/77-council-of-wise-elders',
      }),
    (err: unknown) => err instanceof CouncilError && err.code === 'COUNCIL_INVALID_INPUT',
  );
});

// ---------------------------------------------------------------- budget

test('budget: session ceiling is shared across request kinds', () => {
  const ledger = new InProcessBudgetLedger({
    ...DEFAULT_COUNCIL_SETTINGS,
    max_session_provider_requests: 3,
  });
  ledger.commit(ledger.reserve({ session_id: 's1', operation_key: 'a', kind: 'provider_request' }));
  ledger.commit(ledger.reserve({ session_id: 's1', operation_key: 'b', kind: 'output_repair' }));
  ledger.commit(ledger.reserve({ session_id: 's1', operation_key: 'c', kind: 'transport_retry' }));
  assert.throws(
    () => ledger.reserve({ session_id: 's1', operation_key: 'd', kind: 'provider_request' }),
    (err: unknown) => err instanceof CouncilError && err.code === 'COUNCIL_BUDGET_EXHAUSTED',
  );
  const snap = ledger.snapshot('s1');
  assert.equal(snap.consumed.provider_requests, 3);
  assert.equal(snap.consumed.output_repairs, 1);
  assert.equal(snap.consumed.transport_retries, 1);
});

test('budget: re-reserving the same operation is idempotent', () => {
  const ledger = new InProcessBudgetLedger();
  const first = ledger.reserve({ session_id: 's1', operation_key: 'op-1', kind: 'provider_request' });
  const second = ledger.reserve({ session_id: 's1', operation_key: 'op-1', kind: 'provider_request' });
  assert.equal(first, second);
  assert.equal(ledger.snapshot('s1').reserved, 1);
});

test('budget: unknown provider completion stays counted, never free', () => {
  const ledger = new InProcessBudgetLedger();
  const reservation = ledger.reserve({ session_id: 's1', operation_key: 'op-1', kind: 'provider_request' });
  ledger.markProviderCompletionUnknown(reservation);
  const snap = ledger.snapshot('s1');
  assert.equal(snap.unknown, 1);
  assert.equal(snap.consumed.provider_requests, 1);
  assert.equal(snap.reserved, 0);
});

test('budget: release frees an undispatched reservation', () => {
  const ledger = new InProcessBudgetLedger({
    ...DEFAULT_COUNCIL_SETTINGS,
    max_session_provider_requests: 1,
  });
  const held = ledger.reserve({ session_id: 's1', operation_key: 'op-1', kind: 'provider_request' });
  ledger.release(held);
  const next = ledger.reserve({ session_id: 's1', operation_key: 'op-2', kind: 'provider_request' });
  assert.ok(next);
  assert.equal(ledger.snapshot('s1').consumed.provider_requests, 0);
});

// ---------------------------------------------------------------- leases

test('leases: claim, heartbeat, fencing by newer epoch, expiry, release', () => {
  let now = 1_000_000;
  const leases = new InProcessLeaseProvider(() => now);
  const first = leases.claim('op-1', 'worker-a');
  leases.assertCurrent(first);
  const renewed = leases.heartbeat(first);
  assert.equal(renewed.expires_at_ms, now + 60_000);
  const second = leases.claim('op-1', 'worker-b');
  assert.equal(second.epoch, first.epoch + 1);
  assert.throws(
    () => leases.assertCurrent(first),
    (err: unknown) => err instanceof CouncilError && err.code === 'COUNCIL_LEASE_LOST',
  );
  leases.assertCurrent(second);
  now += 61_000;
  assert.throws(
    () => leases.assertCurrent(second),
    (err: unknown) => err instanceof CouncilError && err.code === 'COUNCIL_LEASE_LOST',
  );
  const third = leases.claim('op-1', 'worker-c');
  leases.release(third);
  assert.throws(
    () => leases.assertCurrent(third),
    (err: unknown) => err instanceof CouncilError && err.code === 'COUNCIL_LEASE_LOST',
  );
});

// ---------------------------------------------------------------- store

test('store: session round trip, state compare-and-swap conflict, database file location', async () => {
  const dataDir = tempDataDir('store');
  const store = new LocalSqliteStore(dataDir);
  assert.ok(existsSync(join(dataDir, 'council.db')));
  const sample = buildSampleSession();
  const state = {
    schema_version: 'wise-elders.session-state/v1' as const,
    session_id: sample.spec.session_id,
    mode: sample.spec.mode,
    state: 'DRAFT' as const,
    state_version: 0,
    brief_revision: 1,
    resume_phase: null,
    cancel_generation: 0,
    revocation_generation: 0,
    attempt: 1,
    lease_epoch: 0,
    archived: false,
    updated_at: '2026-10-14T02:00:00Z',
  };
  await store.createSession({ ...sample, state, sample: true });
  const loaded = await store.getSession(sample.spec.session_id);
  assert.ok(loaded);
  assert.equal(loaded.sample, true);
  assert.equal(loaded.state.state, 'DRAFT');
  await store.updateState({ ...state, state: 'READY', state_version: 1 }, 0);
  await assert.rejects(
    () => store.updateState({ ...state, state: 'QUEUED', state_version: 1 }, 0),
    (err: unknown) => err instanceof CouncilError && err.code === 'COUNCIL_STATE_CONFLICT',
  );
  store.close();
});

test('store: events are sequenced in order and cards are unique per logical operation', async () => {
  const dataDir = tempDataDir('store-events');
  const sample = buildSampleSession();
  const host = grantHost(dataDir, sample.spec, sample.scope);
  const engine = new CouncilEngine(host);
  await engine.createSession({ ...sample, sample: true });
  const done = await engine.startSession(sample.spec.session_id, 'test-grant');
  assert.equal(done.state.state, 'COMPLETED');
  const events = await host.store.listEvents(sample.spec.session_id);
  assert.ok(events.length > 10);
  events.forEach((event, index) => assert.equal(event.sequence, index + 1));
  const cards = await host.store.listCards(sample.spec.session_id);
  assert.equal(cards.length, 27); // 9 seats x (round 1 + round 2 + ratification)
  const first = cards[0];
  await assert.rejects(() => host.store.saveCard(first));
  const verdict = await host.store.getVerdict(sample.spec.session_id);
  assert.ok(verdict);
  const round1 = cards.find((c) => c.card_kind === 'advisor' && c.round === 1);
  assert.ok(round1);
  const checkpoint = await host.store.getCheckpoint(
    sample.spec.session_id,
    'round-1',
    round1.seat_id,
    round1.input_manifest_sha256,
  );
  assert.ok(checkpoint);
  assert.equal(checkpoint.status, 'accepted');
  assert.ok(checkpoint.provider_request_id?.startsWith('fixture-req-'));
});
