/**
 * RP-046-3 proof battery for DEFECT-046-B (the D-018 live re-run on
 * the canary machine ended BLOCKED with all nine Round 1 seats
 * failed, in two families).
 *
 * Cause 1: operation leases expired 60 seconds after operation start
 * while multi-minute harness calls were still in flight. The
 * standalone engine claimed the lease and never renewed it. The
 * repair renews the claimed lease at the Section 15.8 heartbeat
 * cadence for the duration of the in-flight operation, by the
 * current fencing holder only (mirroring the CWE-027 runner's
 * dispatch heartbeat), without raising the 60s TTL or the 15s
 * cadence and without touching grants or retry counters.
 *
 * Cause 2: harness answers failed card validation (an out-of-enum
 * card_kind, and a response that was not valid JSON). Root cause in
 * the composed request and the parser: the request carried no
 * canonical card contract (no schema, no exact card_kind, no
 * JSON-only instruction), and the parser fed the whole response
 * text to JSON.parse, so prose around a valid card failed the
 * parse. The repair carries the full canonical card contract in
 * every composed request and locates the card JSON object inside
 * the response text before validation. Validation is NOT weakened:
 * an out-of-enum card_kind still fails and flows to the one
 * permitted repair, and a response with no JSON object still fails
 * as not valid JSON.
 *
 * Tests: (1) a transport call that exceeds the lease window
 * completes and its card commits, driven through the product's own
 * timing seams (a fake-clock lease provider and the engine's
 * injected timer port; production constants are never edited);
 * (1b) the same call with no heartbeat tick still loses its lease,
 * proving the TTL is unchanged and the renewal is what carries the
 * call; (2) a stale worker that lost fencing to a takeover still
 * cannot commit; (3) cancel during a long call prevents the late
 * completion from committing and settles the session CANCELLED;
 * (4) a prose-wrapped JSON card parses through extraction and
 * validates, and every composed request carries the canonical card
 * contract; (5) a JSON card with an out-of-enum card_kind still
 * FAILS validation after exactly one repair; (6) a non-JSON
 * response still fails as before; (7) end-to-end on this VM: a full
 * local session through the composed HARNESS path against a
 * fixture harness executable that sleeps beyond the test lease
 * window on every call and returns prose-wrapped cards, reaching
 * the golden validated verdict with provider requests counted by
 * the real budget ledger.
 */
import assert from 'node:assert/strict';
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
  canonicalHash,
  type DecisionBrief,
  type SessionSpec,
} from '../src/contracts/index.js';
import { parseCardResponseText } from '../src/cli/card-text.js';
import {
  CouncilEngine,
  type EngineTimers,
} from '../src/cli/engine.js';
import {
  buildSampleSession,
  DeterministicFixtureTransport,
} from '../src/cli/fixture-transport.js';
import type {
  CapacityLeaseProvider,
  ModelTransport,
  OperationLease,
  TransportRequest,
  TransportResponse,
} from '../src/cli/host-ports.js';
import { InProcessLeaseProvider } from '../src/cli/leases.js';
import { createLocalHost } from '../src/cli/local-host.js';
import { grantHost, tempDataDir, buildTestGrant } from './helpers.js';

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

/** Manual EngineTimers: registered callbacks fire only on tick(). */
class ManualTimers implements EngineTimers {
  private readonly callbacks = new Set<() => void>();
  every(_ms: number, fn: () => void): () => void {
    this.callbacks.add(fn);
    return () => {
      this.callbacks.delete(fn);
    };
  }
  tick(): void {
    for (const fn of [...this.callbacks]) fn();
  }
  get active(): number {
    return this.callbacks.size;
  }
}

function makeConsult(): {
  spec: SessionSpec;
  brief: DecisionBrief;
  scope: ReturnType<typeof buildSampleSession>['scope'];
} {
  const sample = buildSampleSession();
  const spec: SessionSpec = {
    ...clone(sample.spec),
    session_id: 'sess-rp0463-consult',
    mode: 'consult',
    seat_ids: ['oprah-winfrey'],
  };
  const brief: DecisionBrief = {
    ...clone(sample.brief),
    session_id: 'sess-rp0463-consult',
  };
  spec.brief_sha256 = canonicalHash(brief);
  return { spec, brief, scope: sample.scope };
}

async function blockedReason(
  engine: CouncilEngine,
  sessionId: string,
): Promise<string> {
  const events = await engine.listEvents(sessionId);
  const blocked = events.find((e) => e.event_type === 'session_blocked');
  assert.ok(blocked, 'a session_blocked event was recorded');
  return String((blocked!.payload as { reason?: unknown }).reason ?? '');
}

// ------------------------------------------------------------- (1)

test('rp0463 (1): a transport call exceeding the lease window completes and its card commits', async () => {
  const { spec, brief, scope } = makeConsult();
  let nowMs = 1_700_000_000_000;
  const timers = new ManualTimers();
  let heartbeatCalls = 0;
  const shared = new InProcessLeaseProvider(() => nowMs);
  const fakeClockLeases: CapacityLeaseProvider = {
    claim: (key, owner, ttl) => shared.claim(key, owner, ttl),
    heartbeat: (lease) => {
      heartbeatCalls += 1;
      return shared.heartbeat(lease);
    },
    assertCurrent: (lease) => shared.assertCurrent(lease),
    release: (lease) => shared.release(lease),
  };

  const fixture = new DeterministicFixtureTransport();
  const slowTransport: ModelTransport = {
    async generate(request: TransportRequest): Promise<TransportResponse> {
      // A 75 second call against a 60 second lease TTL: simulated
      // time advances in 15 second steps, and the engine's heartbeat
      // (driven here through its injected timer port, as a test
      // drives the CWE-027 runner's manual timers) renews the lease
      // at each step.
      for (let i = 0; i < 5; i++) {
        nowMs += 15_000;
        timers.tick();
      }
      return fixture.generate(request);
    },
  };
  const host = grantHost(tempDataDir('rp0463-long'), spec, scope, slowTransport);
  host.capacity = fakeClockLeases;
  const engine = new CouncilEngine(host, { timers });
  await engine.createSession({ spec, brief, scope });
  const done = await engine.startSession(spec.session_id, 'test-grant');
  assert.equal(done.state.state, 'COMPLETED');
  assert.ok(heartbeatCalls >= 5, `the lease was renewed during the call (${heartbeatCalls} renewals)`);
  const cards = await host.store.listCards(spec.session_id);
  assert.equal(cards.length, 1, 'the long call card committed');
  assert.equal(cards[0].seat_id, 'oprah-winfrey');
  assert.equal(host.budget.snapshot(spec.session_id).consumed.provider_requests, 1);
  assert.equal(timers.active, 0, 'the heartbeat stopped when the operation settled');
});

test('rp0463 (1b): without a heartbeat the same over-TTL call still loses its lease (TTL unchanged)', async () => {
  const { spec, brief, scope } = makeConsult();
  let nowMs = 1_700_000_000_000;
  const timers = new ManualTimers();
  const shared = new InProcessLeaseProvider(() => nowMs);
  const fixture = new DeterministicFixtureTransport();
  const slowTransport: ModelTransport = {
    async generate(request: TransportRequest): Promise<TransportResponse> {
      // 75 seconds pass with no heartbeat tick at all: the lease
      // genuinely expires, exactly as it did on the canary machine
      // before this repair existed.
      nowMs += 75_000;
      return fixture.generate(request);
    },
  };
  const host = grantHost(tempDataDir('rp0463-nobeat'), spec, scope, slowTransport);
  host.capacity = shared;
  const engine = new CouncilEngine(host, { timers });
  await engine.createSession({ spec, brief, scope });
  const done = await engine.startSession(spec.session_id, 'test-grant');
  assert.equal(done.state.state, 'BLOCKED');
  const reason = await blockedReason(engine, spec.session_id);
  assert.ok(reason.includes('expired at'), `the lease expiry is the recorded reason: ${reason}`);
  assert.equal((await host.store.listCards(spec.session_id)).length, 0);
  assert.equal(timers.active, 0, 'the heartbeat stopped when the operation settled');
});

// ------------------------------------------------------------- (2)

test('rp0463 (2): a stale worker that lost fencing to a takeover still cannot commit', async () => {
  const { spec, brief, scope } = makeConsult();
  class TakeoverLeases implements CapacityLeaseProvider {
    private readonly inner = new InProcessLeaseProvider();
    private claimed: OperationLease | null = null;
    claim(key: string, owner: string, ttl?: number): OperationLease {
      this.claimed = this.inner.claim(key, owner, ttl);
      return this.claimed;
    }
    heartbeat(lease: OperationLease): OperationLease {
      return this.inner.heartbeat(lease);
    }
    assertCurrent(lease: OperationLease): void {
      return this.inner.assertCurrent(lease);
    }
    release(lease: OperationLease): void {
      return this.inner.release(lease);
    }
    takeover(): void {
      assert.ok(this.claimed, 'the engine claimed its lease before dispatch');
      // A successor worker claims the same operation: the fencing
      // epoch moves and the in-flight worker is stale (T052).
      this.inner.claim(this.claimed!.operation_key, 'successor-worker');
    }
  }
  const leases = new TakeoverLeases();
  const fixture = new DeterministicFixtureTransport();
  const transport: ModelTransport = {
    async generate(request: TransportRequest): Promise<TransportResponse> {
      leases.takeover();
      return fixture.generate(request);
    },
  };
  const host = grantHost(tempDataDir('rp0463-takeover'), spec, scope, transport);
  host.capacity = leases;
  const engine = new CouncilEngine(host);
  await engine.createSession({ spec, brief, scope });
  const done = await engine.startSession(spec.session_id, 'test-grant');
  assert.equal(done.state.state, 'BLOCKED');
  const reason = await blockedReason(engine, spec.session_id);
  assert.ok(reason.includes('fenced out'), `the fencing refusal is the recorded reason: ${reason}`);
  assert.equal((await host.store.listCards(spec.session_id)).length, 0, 'the stale worker committed nothing');
  assert.equal(await engine.getVerdict(spec.session_id), null);
});

// ------------------------------------------------------------- (3)

test('rp0463 (3): cancel during a long call prevents the late completion from committing', async () => {
  const { spec, brief, scope } = makeConsult();
  const fixture = new DeterministicFixtureTransport();
  const holder: { engine?: CouncilEngine } = {};
  const transport: ModelTransport = {
    async generate(request: TransportRequest): Promise<TransportResponse> {
      // The owner cancels while this call is in flight; the call
      // then returns a perfectly valid card, too late.
      await holder.engine!.cancelSession(spec.session_id);
      return fixture.generate(request);
    },
  };
  const host = grantHost(tempDataDir('rp0463-cancel'), spec, scope, transport);
  const engine = new CouncilEngine(host);
  holder.engine = engine;
  await engine.createSession({ spec, brief, scope });
  const done = await engine.startSession(spec.session_id, 'test-grant');
  assert.equal(done.state.state, 'CANCELLED');
  assert.equal(
    (await host.store.listCards(spec.session_id)).length,
    0,
    'the late completion committed no card',
  );
  assert.equal(await engine.getVerdict(spec.session_id), null);
  // In-flight accounting is preserved, not erased (T054).
  assert.equal(host.budget.snapshot(spec.session_id).consumed.provider_requests, 1);
});

// ------------------------------------------------------------- (4)

test('rp0463 (4): prose-wrapped JSON cards parse through extraction and validate; the request carries the card contract', async () => {
  const sample = buildSampleSession();
  const fixture = new DeterministicFixtureTransport();
  const requests: TransportRequest[] = [];
  const proseWrap: ModelTransport = {
    async generate(request: TransportRequest): Promise<TransportResponse> {
      requests.push(request);
      const response = await fixture.generate(request);
      return {
        ...response,
        text:
          'Here is my assessment of the brief, in full.\n\n```json\n' +
          response.text +
          '\n```\n\nThat completes the card.',
      };
    },
  };
  const host = grantHost(tempDataDir('rp0463-prose'), sample.spec, sample.scope, proseWrap);
  const engine = new CouncilEngine(host);
  await engine.createSession({ ...sample, sample: true });
  const done = await engine.startSession(sample.spec.session_id, 'test-grant');
  assert.equal(done.state.state, 'COMPLETED');
  const verdict = await engine.getVerdict(sample.spec.session_id);
  assert.ok(verdict && verdict.result_kind === 'scored');
  if (!verdict || verdict.result_kind !== 'scored') return;
  assert.equal(verdict.label, 'WAIT');
  assert.equal(verdict.recommended_option_id, 'B');
  const byId = new Map(verdict.option_scores.map((s) => [s.option_id, s]));
  assert.equal(byId.get('A')?.weighted_sum, 132);
  assert.equal(byId.get('B')?.weighted_sum, 168);
  assert.equal(byId.get('C')?.weighted_sum, 145);
  assert.equal(host.budget.snapshot(sample.spec.session_id).consumed.provider_requests, 27);
  assert.equal((await host.store.listCards(sample.spec.session_id)).length, 27);
  // Every composed request carried the canonical card contract:
  // the exact card_kind for its purpose, the JSON-only instruction
  // in the system text, and the generated JSON Schema in the input.
  assert.equal(requests.length, 27);
  for (const request of requests) {
    const input = request.input as {
      output_contract?: { card_kind?: unknown; json_schema?: unknown };
    };
    assert.equal(input.output_contract?.card_kind, request.purpose);
    assert.equal(typeof input.output_contract?.json_schema, 'object');
    assert.ok(
      request.system.includes(`"card_kind" field must be exactly "${request.purpose}"`),
      'the system text names the exact card_kind',
    );
  }
});

test('rp0463 (4b): extraction locates the card object inside prose, fences, and brace-bearing text', () => {
  const direct = parseCardResponseText('{"card_kind":"advisor","n":1}');
  assert.ok(direct.ok);
  const wrapped = parseCardResponseText(
    'Reasoning first {see the brief} and then the card:\n```json\n{"card_kind":"advisor","note":"a } brace in a string"}\n```\nDone.',
  );
  assert.ok(wrapped.ok);
  if (wrapped.ok) {
    const value = wrapped.value as { card_kind?: unknown; note?: unknown };
    assert.equal(value.card_kind, 'advisor');
    assert.equal(value.note, 'a } brace in a string');
  }
  const none = parseCardResponseText('There is no structured answer here.');
  assert.equal(none.ok, false);
  // A bare JSON array still parses directly (historical semantics);
  // the validator, not the parser, rejects it as a card.
  const array = parseCardResponseText('[1,2,3]');
  assert.ok(array.ok);
});

// ------------------------------------------------------------- (5)

test('rp0463 (5): a JSON card with an out-of-enum card_kind still FAILS validation after the one repair', async () => {
  const { spec, brief, scope } = makeConsult();
  const fixture = new DeterministicFixtureTransport();
  let calls = 0;
  const wrongKind: ModelTransport = {
    async generate(request: TransportRequest): Promise<TransportResponse> {
      calls += 1;
      const response = await fixture.generate(request);
      return {
        ...response,
        text: response.text.replace(
          '"card_kind":"consult"',
          '"card_kind":"advisory-card"',
        ),
      };
    },
  };
  const host = grantHost(tempDataDir('rp0463-kind'), spec, scope, wrongKind);
  const engine = new CouncilEngine(host);
  await engine.createSession({ spec, brief, scope });
  const done = await engine.startSession(spec.session_id, 'test-grant');
  assert.equal(done.state.state, 'BLOCKED');
  const reason = await blockedReason(engine, spec.session_id);
  assert.ok(
    reason.includes(
      'invalid card after the permitted repair: card_kind: Invalid discriminator value',
    ),
    `the validator refusal is the recorded reason: ${reason}`,
  );
  assert.equal(calls, 2, 'the initial call plus exactly one permitted repair');
  const budget = host.budget.snapshot(spec.session_id);
  // The ledger counts every actual provider request toward the
  // session total whatever its kind (Section 15.9): the initial
  // call and the one repair are 2 provider requests, 1 of them an
  // output repair.
  assert.equal(budget.consumed.provider_requests, 2);
  assert.equal(budget.consumed.output_repairs, 1);
  assert.equal((await host.store.listCards(spec.session_id)).length, 0);
});

// ------------------------------------------------------------- (6)

test('rp0463 (6): a non-JSON response still fails as before', async () => {
  const { spec, brief, scope } = makeConsult();
  let calls = 0;
  const nonJson: ModelTransport = {
    async generate(): Promise<TransportResponse> {
      calls += 1;
      return {
        text: 'I cannot provide that answer in a structured form.',
        provider_request_id: `nonjson-${calls}`,
        reported_model_id: null,
        usage: { input_tokens: null, output_tokens: null },
      };
    },
  };
  const host = grantHost(tempDataDir('rp0463-nonjson'), spec, scope, nonJson);
  const engine = new CouncilEngine(host);
  await engine.createSession({ spec, brief, scope });
  const done = await engine.startSession(spec.session_id, 'test-grant');
  assert.equal(done.state.state, 'BLOCKED');
  const reason = await blockedReason(engine, spec.session_id);
  assert.ok(
    reason.includes('response is not valid JSON'),
    `the historical parse failure is the recorded reason: ${reason}`,
  );
  assert.equal(calls, 2, 'the initial call plus exactly one permitted repair');
  assert.equal((await host.store.listCards(spec.session_id)).length, 0);
});

// ------------------------------------------------------------- (7)

const E2E_SEAT_BY_DISPLAY_NAME: Record<string, string> = {
  'Simon Sinek': 'simon-sinek',
  'T. D. Jakes': 'td-jakes',
  'Oprah Winfrey': 'oprah-winfrey',
  'Tiffany Aliche': 'tiffany-aliche',
  'Russell Brunson': 'russell-brunson',
  'Michelle Obama': 'michelle-obama',
  'Brené Brown': 'brene-brown',
  'Dr. Dennis Kimbro': 'dennis-kimbro',
  'Les Brown': 'les-brown',
};
const E2E_SEAT_ORDER = [
  'simon-sinek',
  'td-jakes',
  'oprah-winfrey',
  'tiffany-aliche',
  'russell-brunson',
  'michelle-obama',
  'brene-brown',
  'dennis-kimbro',
  'les-brown',
];
/** Section 32.2 golden scores by seat index, per option. */
const E2E_GOLDEN: Record<string, number[]> = {
  A: [6, 5, 6, 8, 5, 6, 6, 6, 6],
  B: [8, 8, 7, 6, 9, 8, 7, 8, 8],
  C: [7, 9, 7, 3, 8, 6, 5, 7, 8],
};

function e2eHarnessScript(counterPath: string): string {
  return `#!/usr/bin/env node
const fs = require('node:fs');
if (process.argv[2] === '--help') process.exit(0); // transport capability probe, not a model call
// The fixture harness stands in for the client's harness binary at
// the delegate boundary. Every call sleeps 3000 ms, beyond the
// 2000 ms test lease window the host below composes, and answers
// with the card JSON wrapped in prose.
Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 3000);
fs.appendFileSync(${JSON.stringify(counterPath)}, 'call\\n');
let data = '';
process.stdin.on('data', (c) => { data += c; });
process.stdin.on('end', () => {
  const idx = data.lastIndexOf('\\n\\n');
  const system = data.slice(0, idx);
  const input = JSON.parse(data.slice(idx + 2));
  const names = ${JSON.stringify(E2E_SEAT_BY_DISPLAY_NAME)};
  const order = ${JSON.stringify(E2E_SEAT_ORDER)};
  const golden = ${JSON.stringify(E2E_GOLDEN)};
  const seat = names[input.seat_display_name];
  const seatIndex = order.indexOf(seat);
  const brief = input.brief;
  const ev = brief.evidence_manifest[0] ? brief.evidence_manifest[0].evidence_id : null;
  const scores = brief.options.map((o) => ({
    option_id: o.id,
    score: golden[o.id][seatIndex],
    rationale: 'e2e harness score for ' + o.id,
    evidence_ids: ev ? [ev] : [],
  }));
  const top = scores.reduce((a, b) => (b.score > a.score ? b : a));
  const base = {
    schema_version: 'wise-elders.card/v1',
    session_id: brief.session_id,
    brief_revision: brief.revision,
    seat_id: seat,
    input_manifest_sha256: input.input_manifest_sha256,
    pack_version: input.pack_version,
  };
  let card;
  if (system.includes('ratification round')) {
    card = {
      ...base,
      card_kind: 'ratification',
      round: 3,
      draft_resolution_sha256: input.draft_resolution.semantic_sha256,
      resolution_stance: 'support',
      stance: 'support',
      preferred_option_id: top.option_id,
      option_scores: scores,
      amendments: [],
      accepted_condition_ids: [],
      unresolved_objections: [],
      evidence_strength: 'medium',
    };
  } else {
    card = {
      ...base,
      card_kind: 'advisor',
      round: system.includes('focused challenge round') ? 2 : 1,
      stance: 'conditional',
      preferred_option_id: top.option_id,
      option_scores: scores,
      framework_applications: [{
        framework_id: 'e2e-harness-framework',
        source_evidence_ids: ev ? [ev] : [],
        case_evidence_ids: [],
        application: 'Applied the seat framework to the frozen brief only.',
        attribution_kind: 'blackceo_adaptation',
      }],
      decisive_arguments: ['The bounded option produces evidence first.'],
      strongest_objection: 'Retention evidence is not yet measured.',
      conditions: [],
      critical_unknowns: ['Measured retention for the pilot cohort.'],
      change_my_mind: 'Evidence the binding constraint no longer holds.',
      challenges_answered: (input.challenges_for_seat || []).map((c) => c.crux_id),
      quotes: [],
      evidence_strength: 'medium',
      minority_position: null,
    };
  }
  const wrapped =
    'Here is the completed card for this seat, with the reasoning stated first.\\n\\n' +
    JSON.stringify(card) +
    '\\n\\nThat is the full assessment.';
  process.stdout.write(JSON.stringify({
    result: wrapped,
    session_id: 'rp0463-e2e-harness-session',
    usage: { input_tokens: 11, output_tokens: 7 },
    modelUsage: { 'harness-reported-model': {} },
  }));
});
`;
}

/** Test lease window: claims live 2000 ms unless renewed. */
class ShortWindowLeases implements CapacityLeaseProvider {
  private readonly inner = new InProcessLeaseProvider();
  claim(key: string, owner: string): OperationLease {
    return this.inner.claim(key, owner, 2000);
  }
  heartbeat(lease: OperationLease): OperationLease {
    return this.inner.heartbeat(lease);
  }
  assertCurrent(lease: OperationLease): void {
    return this.inner.assertCurrent(lease);
  }
  release(lease: OperationLease): void {
    return this.inner.release(lease);
  }
}

test('rp0463 (7) e2e: a full session through the composed harness path, calls beyond the lease window, prose-wrapped cards, reaches the golden verdict', async () => {
  const home = mkdtempSync(join(tmpdir(), 'rp0463-e2e-home-'));
  mkdirSync(join(home, '.claude-nine'), { recursive: true });
  const binDir = join(home, '.local', 'bin');
  mkdirSync(binDir, { recursive: true });
  const counterPath = join(home, 'harness-calls.log');
  const exe = join(binDir, 'claude-nine');
  writeFileSync(exe, e2eHarnessScript(counterPath), 'utf8');
  chmodSync(exe, 0o755);

  const dataDir = tempDataDir('rp0463-e2e');
  const { host, routeDiscovery } = createLocalHost({
    dataDir,
    homeDir: home,
    env: { PATH: '/usr/bin:/bin' },
  });
  const info = (routeDiscovery ?? []).find((r) => r.route_id === 'claude-nine-configured');
  assert.ok(info && info.composed, 'the harness route is discovered and composed');
  // The test lease window: 2000 ms claims against 3000 ms calls.
  // Only the engine's heartbeat renewal (250 ms cadence in this
  // test, the engine's injected timing seam) keeps each operation's
  // lease current until its call settles. Margins are wide on
  // purpose: an earlier 400 ms window run flaked on this loaded VM
  // when a first tick was starved past the window (disclosed in the
  // RP-046-3 report); the production constants (60s TTL, 15s
  // cadence, a 4x margin) are untouched.
  host.capacity = new ShortWindowLeases();

  const sample = buildSampleSession();
  const spec = clone(sample.spec);
  spec.model_policy.route_id = 'claude-nine-configured';
  spec.model_policy.requested_model_id = null;
  const grant = buildTestGrant(spec, sample.scope);
  host.authorize = {
    async resolveRunGrant(ref: string, sessionId: string) {
      return ref === 'test-grant' && sessionId === spec.session_id ? grant : null;
    },
  };
  const engine = new CouncilEngine(host, { heartbeatMs: 250 });
  await engine.createSession({ spec, brief: sample.brief, scope: sample.scope });
  const done = await engine.startSession(spec.session_id, 'test-grant');
  if (done.state.state !== 'COMPLETED') {
    const reason = await blockedReason(engine, spec.session_id).catch(() => '');
    assert.fail(`the e2e session ended ${done.state.state}: ${reason}`);
  }
  const verdict = await engine.getVerdict(spec.session_id);
  assert.ok(verdict && verdict.result_kind === 'scored');
  if (!verdict || verdict.result_kind !== 'scored') return;
  assert.equal(verdict.label, 'WAIT');
  assert.equal(verdict.recommended_option_id, 'B');
  const byId = new Map(verdict.option_scores.map((s) => [s.option_id, s]));
  assert.equal(byId.get('A')?.score, 6.0);
  assert.equal(byId.get('B')?.display_score, 7.6);
  assert.equal(byId.get('C')?.display_score, 6.6);
  // Provider requests counted by the real budget ledger: 27 advisor
  // and ratification turns, and the harness executable was invoked
  // exactly 27 times at the delegate boundary.
  assert.equal(host.budget.snapshot(spec.session_id).consumed.provider_requests, 27);
  const harnessCalls = readFileSync(counterPath, 'utf8').trim().split('\n').length;
  assert.equal(harnessCalls, 27);
});
