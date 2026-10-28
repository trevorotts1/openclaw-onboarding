/**
 * CWE-004 engine tests: the deliberation pipeline against the CWE-003
 * contracts, driven by the deterministic fixture transport (golden
 * scores) and by deliberately failing transports. Every assertion is
 * about contract-visible behavior: states, verdict contents, budget
 * accounting, and persisted artifacts.
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  canonicalHash,
  type DecisionBrief,
  type SessionSpec,
} from '../src/contracts/index.js';
import { CouncilEngine } from '../src/cli/engine.js';
import { CouncilError } from '../src/cli/errors.js';
import {
  buildSampleSession,
  DeterministicFixtureTransport,
} from '../src/cli/fixture-transport.js';
import type {
  ModelTransport,
  TransportRequest,
  TransportResponse,
} from '../src/cli/host-ports.js';
import { createLocalHost } from '../src/cli/local-host.js';
import { grantHost, tempDataDir, buildTestGrant } from './helpers.js';

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

/** Wraps a transport and counts calls per seat and round. */
class CountingTransport implements ModelTransport {
  calls: Array<{ seat_id: string; round: number | null; purpose: string }> = [];
  constructor(private readonly inner: ModelTransport) {}
  async generate(request: TransportRequest): Promise<TransportResponse> {
    this.calls.push({
      seat_id: request.seat_id,
      round: request.round,
      purpose: request.purpose,
    });
    return this.inner.generate(request);
  }
}

test('engine: full sample run reproduces the golden scores and an honest WAIT', async () => {
  const sample = buildSampleSession();
  const host = grantHost(tempDataDir('engine-full'), sample.spec, sample.scope);
  const engine = new CouncilEngine(host);
  await engine.createSession({ ...sample, sample: true });
  const done = await engine.startSession(sample.spec.session_id, 'test-grant');
  assert.equal(done.state.state, 'COMPLETED');
  const verdict = await engine.getVerdict(sample.spec.session_id);
  assert.ok(verdict);
  assert.equal(verdict.result_kind, 'scored');
  if (verdict.result_kind !== 'scored') return;
  // The fixture brief leaves financial_feasibility unresolved, so the
  // label must be WAIT even though option B scores in the GO band.
  assert.equal(verdict.label, 'WAIT');
  assert.equal(verdict.recommended_option_id, 'B');
  const byId = new Map(verdict.option_scores.map((s) => [s.option_id, s]));
  assert.equal(byId.get('A')?.weighted_sum, 132);
  assert.equal(byId.get('A')?.score, 6.0);
  assert.equal(byId.get('B')?.weighted_sum, 168);
  assert.equal(byId.get('B')?.display_score, 7.6);
  assert.equal(byId.get('C')?.weighted_sum, 145);
  assert.equal(byId.get('C')?.display_score, 6.6);
  assert.equal(byId.get('C')?.spread, 6);
  assert.equal(verdict.ratification_status, 'ratified');
  assert.ok(verdict.resolution_support);
  assert.equal(verdict.resolution_support.support, 16);
  assert.equal(verdict.resolution_support.conditional_support, 6);
  assert.ok(
    verdict.prerequisites.includes(
      'Is the pilot affordable at committed cash levels?',
    ),
  );
  // 27 provider requests: 9 seats x 3 rounds, all inside the ceiling.
  const budget = host.budget.snapshot(sample.spec.session_id);
  assert.equal(budget.consumed.provider_requests, 27);
});

test('engine: start refuses without a resolvable grant and dispatches nothing', async () => {
  const sample = buildSampleSession();
  const counting = new CountingTransport(new DeterministicFixtureTransport());
  const { host } = createLocalHost({
    dataDir: tempDataDir('engine-nogrant'),
    transports: [{ routeId: sample.spec.model_policy.route_id, transport: counting }],
  });
  const engine = new CouncilEngine(host);
  await engine.createSession({ ...sample, sample: true });
  await assert.rejects(
    () => engine.startSession(sample.spec.session_id, 'no-such-grant'),
    (err: unknown) =>
      err instanceof CouncilError && err.code === 'RUN_AUTHORIZATION_REQUIRED',
  );
  assert.equal(counting.calls.length, 0);
  const session = await engine.getSession(sample.spec.session_id);
  assert.equal(session.state.state, 'DRAFT');
});

test('engine: an uncomposed route refuses before any state change', async () => {
  const sample = buildSampleSession();
  const { host } = createLocalHost({ dataDir: tempDataDir('engine-noroute') });
  const grant = buildTestGrant(sample.spec, sample.scope);
  host.authorize = {
    async resolveRunGrant(ref: string, sid: string) {
      return ref === 'test-grant' && sid === sample.spec.session_id ? grant : null;
    },
  };
  const engine = new CouncilEngine(host);
  await engine.createSession({ ...sample, sample: true });
  await assert.rejects(
    () => engine.startSession(sample.spec.session_id, 'test-grant'),
    (err: unknown) =>
      err instanceof CouncilError && err.code === 'COUNCIL_ROUTE_UNAVAILABLE',
  );
  const session = await engine.getSession(sample.spec.session_id);
  assert.equal(session.state.state, 'DRAFT');
});

test('engine: a failing seat blocks visibly, and resume reuses completed cards', async () => {
  const sample = buildSampleSession();
  const dataDir = tempDataDir('engine-blocked');
  const failing: ModelTransport = {
    async generate(request: TransportRequest): Promise<TransportResponse> {
      if (request.seat_id === 'td-jakes') {
        throw new Error('fixture transport failure for td-jakes');
      }
      return new DeterministicFixtureTransport().generate(request);
    },
  };
  const host1 = grantHost(dataDir, sample.spec, sample.scope, failing);
  const engine1 = new CouncilEngine(host1);
  await engine1.createSession({ ...sample, sample: true });
  const blocked = await engine1.startSession(sample.spec.session_id, 'test-grant');
  assert.equal(blocked.state.state, 'BLOCKED');
  assert.equal(blocked.state.resume_phase, 'ROUND_1');
  assert.equal(await engine1.getVerdict(sample.spec.session_id), null);
  const partial = await host1.store.listCards(sample.spec.session_id);
  assert.equal(partial.filter((c) => c.card_kind === 'advisor' && c.round === 1).length, 8);

  // Resume in a fresh host over the same store: the eight completed
  // Round 1 cards are reused, never re-spent (Section 15.3).
  const counting = new CountingTransport(new DeterministicFixtureTransport());
  const host2 = grantHost(dataDir, sample.spec, sample.scope, counting);
  const engine2 = new CouncilEngine(host2);
  const done = await engine2.resumeSession(sample.spec.session_id, 'test-grant');
  assert.equal(done.state.state, 'COMPLETED');
  const round1Calls = counting.calls.filter((c) => c.round === 1);
  assert.equal(round1Calls.length, 1);
  assert.equal(round1Calls[0].seat_id, 'td-jakes');
  const verdict = await engine2.getVerdict(sample.spec.session_id);
  assert.ok(verdict);
});

test('engine: consult mode returns a consult result with no invented scores', async () => {
  const sample = buildSampleSession();
  const spec: SessionSpec = {
    ...clone(sample.spec),
    session_id: 'sess-consult-1',
    mode: 'consult',
    seat_ids: ['oprah-winfrey'],
  };
  const brief: DecisionBrief = { ...clone(sample.brief), session_id: 'sess-consult-1' };
  spec.brief_sha256 = canonicalHash(brief);
  const host = grantHost(tempDataDir('engine-consult'), spec, sample.scope);
  const engine = new CouncilEngine(host);
  await engine.createSession({ spec, brief, scope: sample.scope });
  const done = await engine.startSession('sess-consult-1', 'test-grant');
  assert.equal(done.state.state, 'COMPLETED');
  const verdict = await engine.getVerdict('sess-consult-1');
  assert.ok(verdict);
  assert.equal(verdict.result_kind, 'consult');
  if (verdict.result_kind !== 'consult') return;
  assert.ok(verdict.next_step.length > 0);
  assert.equal('option_scores' in verdict, false);
  assert.equal(host.budget.snapshot('sess-consult-1').consumed.provider_requests, 1);
});

test('engine: quick mode skips Round 3 only when the Section 10 predicate holds', async () => {
  const sample = buildSampleSession();
  // Unanimous transport: every seat prefers B with tight scores.
  const unanimous: ModelTransport = {
    async generate(request: TransportRequest): Promise<TransportResponse> {
      const input = request.input as {
        brief: DecisionBrief;
        input_manifest_sha256: string;
        pack_version: string;
      };
      const brief = input.brief;
      const card = {
        schema_version: 'wise-elders.card/v1',
        session_id: brief.session_id,
        brief_revision: brief.revision,
        seat_id: request.seat_id,
        input_manifest_sha256: input.input_manifest_sha256,
        pack_version: input.pack_version,
        card_kind: 'advisor',
        round: request.round ?? 1,
        stance: 'support',
        preferred_option_id: 'B',
        option_scores: brief.options.map((o) => ({
          option_id: o.id,
          score: o.id === 'B' ? 8 : o.id === 'A' ? 5 : 6,
          rationale: 'Unanimous fixture rationale.',
          evidence_ids: ['ev-1'],
        })),
        framework_applications: [],
        decisive_arguments: ['The pilot is the bounded next step.'],
        strongest_objection: 'Retention is still unmeasured.',
        conditions: [],
        critical_unknowns: [],
        change_my_mind: 'Evidence the pilot cannot be staffed.',
        challenges_answered: [],
        quotes: [],
        evidence_strength: 'medium',
        minority_position: null,
      };
      return {
        text: JSON.stringify(card),
        provider_request_id: `unanimous-${request.seat_id}-${request.round}`,
        reported_model_id: 'unanimous-fixture',
        usage: { input_tokens: null, output_tokens: null },
      };
    },
  };
  const spec: SessionSpec = {
    ...clone(sample.spec),
    session_id: 'sess-quick-1',
    mode: 'quick',
  };
  const brief: DecisionBrief = clone(sample.brief);
  brief.session_id = 'sess-quick-1';
  brief.critical_domains = brief.critical_domains.map((d) => ({
    ...d,
    status: 'assessed' as const,
    unresolved_questions: [],
  }));
  spec.brief_sha256 = canonicalHash(brief);
  const host = grantHost(
    tempDataDir('engine-quick'),
    spec,
    sample.scope,
    unanimous,
  );
  const engine = new CouncilEngine(host);
  await engine.createSession({ spec, brief, scope: sample.scope });
  const done = await engine.startSession('sess-quick-1', 'test-grant');
  assert.equal(done.state.state, 'COMPLETED');
  const verdict = await engine.getVerdict('sess-quick-1');
  assert.ok(verdict && verdict.result_kind === 'scored');
  if (!verdict || verdict.result_kind !== 'scored') return;
  assert.equal(verdict.ratification_status, 'not_run_by_quick_mode_policy');
  assert.equal(verdict.resolution_support, null);
  // CWE-050 reconciliation disclosure: this assertion previously
  // expected 'GO' under the CWE-004 engine's retired behavior of
  // emitting an empty hard-constraint findings list (CWE-026
  // divergence (a)). Under the canonical CWE-026 semantics the sample
  // brief's hard constraint con-1 (applies to B and C) has no recorded
  // check, so it is an `unknown` finding and blocks an unconditional
  // GO: the label is WAIT, still recommending B, with the unchecked
  // constraint named as a prerequisite. The quick-skip assertions above
  // (the subject of this test) are unchanged.
  assert.equal(verdict.label, 'WAIT');
  assert.equal(verdict.recommended_option_id, 'B');
  assert.ok(
    verdict.hard_constraint_findings.some(
      (f) => f.constraint_id === 'con-1' && f.option_id === 'B' && f.result === 'unknown',
    ),
  );
  const cards = await host.store.listCards('sess-quick-1');
  assert.equal(cards.filter((c) => c.card_kind === 'ratification').length, 0);
});

test('engine: pause and cancel on a DRAFT session fail honestly and change nothing', async () => {
  const sample = buildSampleSession();
  const host = grantHost(tempDataDir('engine-pause'), sample.spec, sample.scope);
  const engine = new CouncilEngine(host);
  await engine.createSession({ ...sample, sample: true });
  // Drive the session to READY through a start that cannot proceed past
  // admission is not possible; instead verify pause guards: a DRAFT
  // session cannot pause (illegal transition surfaces as an error).
  await assert.rejects(() => engine.pauseSession(sample.spec.session_id));
  const cancelled = await engine.cancelSession(sample.spec.session_id).catch((e) => e);
  // DRAFT cannot cancel either (no active work exists); the typed error
  // is the honest surface, and the session remains DRAFT.
  assert.ok(cancelled instanceof Error);
  const session = await engine.getSession(sample.spec.session_id);
  assert.equal(session.state.state, 'DRAFT');
});

test('engine: replay returns committed events only and spends nothing', async () => {
  const sample = buildSampleSession();
  const counting = new CountingTransport(new DeterministicFixtureTransport());
  const host = grantHost(
    tempDataDir('engine-replay'),
    sample.spec,
    sample.scope,
    counting,
  );
  const engine = new CouncilEngine(host);
  await engine.createSession({ ...sample, sample: true });
  await engine.startSession(sample.spec.session_id, 'test-grant');
  const callsBefore = counting.calls.length;
  const events = await engine.replaySession(sample.spec.session_id);
  assert.ok(events.some((e) => e.event_type === 'verdict_validated'));
  assert.equal(counting.calls.length, callsBefore);
});
