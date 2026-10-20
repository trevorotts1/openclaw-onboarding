/**
 * RP-046-4 proof battery for DEFECT-046-C (the D-021 attempt 4 live
 * session blocked in Round 1: four seats produced validator-accepted
 * cards, five seats returned parseable JSON whose CONTENT failed the
 * strict card schema even after the one permitted repair).
 *
 * The defect is conveyance, not validation: the opaque-ID rule and
 * the UTC ISO 8601 due_at rule exist only as zod refinements and
 * never reach the generated JSON Schema the model sees; the complete
 * required-field list existed only inside that schema; a Round 1
 * call conveyed no challenge issuance at all; and the repair turn
 * forwarded only the validator's error strings, never restating the
 * original constraints Section 15.5 requires it to carry. The repair
 * (src/cli/card-contract.ts, consumed by CouncilEngine) states the
 * exact contract for THIS call in prose in every composed request
 * and restates it in full in the repair instruction. The validator,
 * the schemas, the single permitted repair, the ledger, and the
 * lease behavior are unchanged.
 *
 * Fixture provenance (full record:
 * cwe-046/rp-046-4/fixtures/PROVENANCE.md): the raw failing payloads
 * were never persisted anywhere (Section 16.6: raw provider bodies
 * are memory-only), so the five failing payloads below are
 * RECONSTRUCTED from the verbatim failure strings in attempt 4's
 * session_blocked receipt, on otherwise-valid card bodies carrying
 * demo-2's verified identity values including the per-seat input
 * hashes read from the Mini's durable store. The four accepted cards
 * are RETRIEVED byte-faithful from that store's cards table and live
 * under tests/fixtures/rp0464/ as positive controls. The teeth test
 * proves each reconstruction fails the UNCHANGED validator with
 * exactly its seat's recorded live failure strings.
 *
 * Tests: (0) teeth, validator level: every regression fixture fails
 * with exactly the recorded live issues; (1) per-seat dispatch: the
 * recorded bad payload first, a conforming card on repair, reaches a
 * validator-accepted card, and the repair instruction the double
 * received carries the class-specific missing elements (the exact
 * card_kind value, this call's challenge issuance, the ISO format
 * demand with its example, the complete required-field list) plus
 * the verbatim failure and the completeness demand; (2) Round 2
 * conveyance: a seat assigned a crux is told the exact issued
 * challenge IDs; (3) control: a double that repeats the bad payload
 * on the repair still blocks the session with the verbatim failure,
 * proving nothing was weakened; (4) the four retrieved accepted cards
 * still validate untouched; (5) end to end through the composed
 * harness path (the RP-046-3 pattern): a fixture harness executable
 * answers every call, the session completes with the golden verdict,
 * the real ledger counts exactly 27 provider requests, and every
 * prompt the harness received carries the strengthened contract.
 */
import assert from 'node:assert/strict';
import {
  chmodSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import {
  validateCard,
  validateCardAuthor,
} from '../src/contracts/index.js';
import {
  DUE_AT_EXAMPLE,
  requiredCardFields,
} from '../src/cli/card-contract.js';
import { CouncilEngine } from '../src/cli/engine.js';
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

// ------------------------------------------------------------ fixtures

/** Demo-2 per-seat input hashes, read from the Mini store checkpoints. */
const DEMO2_INPUT_SHA: Record<string, string> = {
  'simon-sinek':
    '2e04933efa83d1184678e00d148a8fc17e5a3768d20a2bf451a4e671b487379b',
  'td-jakes':
    '5817d8209f6a92ae14d62446fbe928fda58a31d03eb458ca8473bce9e28ec226',
  'oprah-winfrey':
    '87e01369fcfeb8946749203c7ae7df7e904cf56c3deb8ebda03e1d502d308167',
  'tiffany-aliche':
    'ae008fc6ed4a42d8ce5cd64ba924990089b159a1574fc995af0b42f97e33f145',
  'les-brown':
    '235aff9e24727f0fc3dfe0498fdbb3bda997bf3bf5b3f1545a2fb7afedc5b894',
};

/** The recorded live post-repair failure strings, per seat, verbatim. */
const LIVE_ISSUES: Record<string, string[]> = {
  'simon-sinek': [
    "card_kind: Invalid discriminator value. Expected 'advisor' | 'ratification' | 'consult'",
  ],
  'td-jakes': [
    'challenges_answered.0: must be an opaque ID (no names, text, or secrets)',
    'challenges_answered.1: must be an opaque ID (no names, text, or secrets)',
    'challenges_answered.2: must be an opaque ID (no names, text, or secrets)',
  ],
  'les-brown': [
    'challenges_answered.0: must be an opaque ID (no names, text, or secrets)',
    'challenges_answered.1: must be an opaque ID (no names, text, or secrets)',
    'challenges_answered.2: must be an opaque ID (no names, text, or secrets)',
  ],
  'oprah-winfrey': [
    'conditions.0.due_at: must be a UTC ISO 8601 timestamp',
    'conditions.1.due_at: must be a UTC ISO 8601 timestamp',
    'conditions.2.due_at: must be a UTC ISO 8601 timestamp',
  ],
  'tiffany-aliche': [
    'framework_applications: Invalid input: expected array, received undefined',
    'decisive_arguments: Invalid input: expected array, received undefined',
    'strongest_objection: Invalid input: expected string, received undefined',
    'conditions: Invalid input: expected array, received undefined',
    'critical_unknowns: Invalid input: expected array, received undefined',
    'change_my_mind: Invalid input: expected string, received undefined',
    'challenges_answered: Invalid input: expected array, received undefined',
    'quotes: Invalid input: expected array, received undefined',
    'evidence_strength: Invalid option: expected one of "low"|"medium"|"high"',
    'minority_position: Invalid input: expected string, received undefined',
  ],
};

/**
 * An otherwise-valid advisor card body (field shapes modeled on the
 * four retrieved accepted cards) carrying demo-2's verified identity
 * values. Each seat's defect is injected by the caller, exactly as
 * recorded. These literals mirror the fixture files of record under
 * cwe-046/rp-046-4/fixtures/.
 */
function reconstructedBase(seat: string): Record<string, unknown> {
  return {
    schema_version: 'wise-elders.card/v1',
    session_id: 'sess-canary-demo-2',
    brief_revision: 1,
    seat_id: seat,
    input_manifest_sha256: DEMO2_INPUT_SHA[seat],
    pack_version: 'v1.0.0',
    card_kind: 'advisor',
    round: 1,
    stance: 'conditional',
    preferred_option_id: 'B',
    option_scores: [
      { option_id: 'A', score: 6, rationale: 'Reconstructed fixture body: plausible score rationale.', evidence_ids: ['ev-1'] },
      { option_id: 'B', score: 8, rationale: 'Reconstructed fixture body: plausible score rationale.', evidence_ids: ['ev-1'] },
      { option_id: 'C', score: 5, rationale: 'Reconstructed fixture body: plausible score rationale.', evidence_ids: ['ev-1'] },
    ],
    framework_applications: [
      {
        framework_id: 'reconstructed-fixture-framework',
        source_evidence_ids: ['ev-1'],
        case_evidence_ids: [],
        application: 'Reconstructed fixture body: plausible framework application.',
        attribution_kind: 'blackceo_adaptation',
      },
    ],
    decisive_arguments: ['Reconstructed fixture body: a decisive argument.'],
    strongest_objection: 'Reconstructed fixture body: the strongest objection.',
    conditions: [],
    critical_unknowns: ['Reconstructed fixture body: a critical unknown.'],
    change_my_mind: 'Reconstructed fixture body: what would change this position.',
    challenges_answered: [],
    quotes: [],
    evidence_strength: 'medium',
    minority_position: null,
  };
}

function reconstructedFailure(seat: string): Record<string, unknown> {
  const card = reconstructedBase(seat);
  if (seat === 'simon-sinek') {
    // Any out-of-enum value yields the identical recorded string;
    // the exact live value was never persisted.
    card.card_kind = 'advisory';
  } else if (seat === 'td-jakes') {
    card.challenges_answered = [
      'Instinct lens challenge',
      'Disruptive Thinking challenge',
      "Don't Drop the Mic challenge",
    ];
  } else if (seat === 'les-brown') {
    card.challenges_answered = [
      'The limiting-belief challenge',
      'The resilience challenge',
      'The committed-action challenge',
    ];
  } else if (seat === 'oprah-winfrey') {
    const condition = (n: number, due: string) => ({
      id: `cond-${n}`,
      description: `Reconstructed fixture condition ${n}.`,
      kind: 'prerequisite',
      blocking: true,
      verification_method: 'Owner confirms the evidence exists.',
      required_evidence: ['ev-1'],
      responsible_role: 'owner',
      due_at: due,
      status: 'open',
      depends_on: [],
    });
    card.conditions = [
      condition(1, '2026-11-01'),
      condition(2, '2026-12-01'),
      condition(3, '2027-01-15'),
    ];
  } else if (seat === 'tiffany-aliche') {
    for (const field of [
      'framework_applications',
      'decisive_arguments',
      'strongest_objection',
      'conditions',
      'critical_unknowns',
      'change_my_mind',
      'challenges_answered',
      'quotes',
      'evidence_strength',
      'minority_position',
    ]) {
      delete card[field];
    }
  }
  return card;
}

const FAILED_SEATS = Object.keys(LIVE_ISSUES);

// ------------------------------------------------------------ doubles

/**
 * Scripted transport double: for the target seat's Round 1 advisor
 * call it returns the recorded bad payload first; on the repair call
 * (and every other call) it delegates to the deterministic fixture
 * transport, which answers with a conforming card. Every request is
 * recorded so the test can assert on the exact repair instruction
 * the double received.
 */
class ScriptedSeatTransport implements ModelTransport {
  readonly seen: TransportRequest[] = [];
  private readonly inner = new DeterministicFixtureTransport();
  constructor(
    private readonly seat: string,
    private readonly badPayload: unknown,
    private readonly repeatBadOnRepair = false,
  ) {}
  async generate(request: TransportRequest): Promise<TransportResponse> {
    this.seen.push(request);
    const isTarget =
      request.seat_id === this.seat &&
      request.purpose === 'advisor' &&
      request.round === 1;
    const isRepair = request.system.includes(
      'Your previous output failed validation',
    );
    if (isTarget && (!isRepair || this.repeatBadOnRepair)) {
      return {
        text: JSON.stringify(this.badPayload),
        provider_request_id: `scripted-bad-${this.seen.length}`,
        reported_model_id: null,
        usage: { input_tokens: null, output_tokens: null },
      };
    }
    return this.inner.generate(request);
  }
  callsFor(seat: string, round: number): TransportRequest[] {
    return this.seen.filter(
      (r) => r.seat_id === seat && r.purpose === 'advisor' && r.round === round,
    );
  }
  repairFor(seat: string, round: number): TransportRequest | undefined {
    return this.callsFor(seat, round).find((r) =>
      r.system.includes('Your previous output failed validation'),
    );
  }
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

// ------------------------------------------------------------- (0) teeth

test('rp0464 (0) teeth: each regression fixture fails the unchanged validator with exactly its recorded live failure strings', () => {
  for (const seat of FAILED_SEATS) {
    const result = validateCardAuthor(reconstructedFailure(seat));
    assert.equal(result.ok, false, `${seat}: the fixture must fail validation`);
    if (!result.ok) {
      assert.deepEqual(
        result.issues.map((i) => `${i.path}: ${i.message}`),
        LIVE_ISSUES[seat],
        `${seat}: the fixture's failures must equal the recorded live strings`,
      );
    }
  }
});

// ------------------------------------------------------------- (1) repair drives

for (const seat of FAILED_SEATS) {
  test(`rp0464 (1) ${seat}: the recorded bad payload reaches a validator-accepted card through the strengthened repair`, async () => {
    const sample = buildSampleSession();
    const transport = new ScriptedSeatTransport(
      seat,
      reconstructedFailure(seat),
    );
    const host = grantHost(
      tempDataDir(`rp0464-${seat}`),
      sample.spec,
      sample.scope,
      transport,
    );
    const engine = new CouncilEngine(host);
    await engine.createSession({ ...sample, sample: true });
    const done = await engine.startSession(sample.spec.session_id, 'test-grant');
    assert.equal(
      done.state.state,
      'COMPLETED',
      `the session completes once ${seat} repairs`,
    );
    // Exactly two calls for the seat's Round 1 operation: the bad
    // first answer and the one permitted repair.
    const calls = transport.callsFor(seat, 1);
    assert.equal(calls.length, 2, 'initial call plus exactly one repair');
    // The seat's repaired card was accepted and stored.
    const cards = await host.store.listCards(sample.spec.session_id);
    assert.ok(
      cards.some((c) => c.seat_id === seat && c.card_kind === 'advisor' && c.round === 1),
      `a validator-accepted Round 1 card for ${seat} is stored`,
    );
    // The repair instruction the double received: the validator's
    // verbatim failure for this seat, the full contract restated,
    // and the explicit completeness demand.
    const repair = transport.repairFor(seat, 1);
    assert.ok(repair, 'the double received a repair request');
    const system = repair!.system;
    for (const issue of LIVE_ISSUES[seat]) {
      assert.ok(
        system.includes(issue),
        `the repair carries the verbatim failure: ${issue}`,
      );
    }
    assert.ok(system.includes('The contract for this call, restated in full:'));
    assert.ok(
      system.includes('"card_kind" field must be exactly "advisor"'),
      'the repair restates the single exact card_kind for this call',
    );
    assert.ok(
      system.includes('Return the complete corrected card only'),
      'the repair demands the complete corrected card only',
    );
    // Class-specific elements the live conveyance lacked:
    if (seat === 'td-jakes' || seat === 'les-brown') {
      assert.ok(
        system.includes(
          'challenges_answered: no challenges have been issued to you for this call, so challenges_answered must be an empty array []',
        ),
        'the repair states this call\'s challenge issuance (none in Round 1)',
      );
      assert.ok(
        system.includes('must be an opaque ID'),
        'the repair carries the validator\'s opaque-ID failure verbatim',
      );
      assert.ok(
        system.includes('Every ID string in the card must be an opaque ID'),
        'the repair restates the opaque-ID format rule',
      );
    }
    if (seat === 'oprah-winfrey') {
      assert.ok(
        system.includes('conditions[].due_at'),
        'the repair names the due_at rule',
      );
      assert.ok(
        system.includes(DUE_AT_EXAMPLE),
        'the repair gives the concrete UTC ISO 8601 example',
      );
      assert.ok(
        system.includes('use null when no date is required'),
        'the repair states the null guidance',
      );
    }
    if (seat === 'tiffany-aliche') {
      assert.ok(
        system.includes(requiredCardFields('advisor').join(', ')),
        'the repair restates the complete required-field list',
      );
      for (const field of [
        'framework_applications',
        'decisive_arguments',
        'strongest_objection',
        'conditions',
        'critical_unknowns',
        'change_my_mind',
        'challenges_answered',
        'quotes',
        'evidence_strength',
        'minority_position',
      ]) {
        assert.ok(
          system.includes(field),
          `the repair's field list names ${field}`,
        );
      }
    }
    // The first (unrepaired) request already carried the strengthened
    // contract in its output_contract and system text.
    const first = calls[0];
    const firstInput = first.input as {
      output_contract?: { card_kind?: unknown; instruction?: unknown };
    };
    assert.equal(firstInput.output_contract?.card_kind, 'advisor');
    assert.equal(typeof firstInput.output_contract?.instruction, 'string');
    assert.ok(
      String(firstInput.output_contract?.instruction).includes(
        requiredCardFields('advisor').join(', '),
      ),
      'the composed request states the complete required-field list in prose',
    );
    assert.ok(
      first.system.includes('Return exactly one JSON object and nothing else'),
      'the composed system text carries the contract instruction',
    );
  });
}

// ------------------------------------------------------------- (2) Round 2 issuance

test('rp0464 (2): a seat assigned a crux is told the exact issued challenge IDs for its Round 2 call', async () => {
  const sample = buildSampleSession();
  const requests: TransportRequest[] = [];
  const fixture = new DeterministicFixtureTransport();
  const recording: ModelTransport = {
    async generate(request: TransportRequest): Promise<TransportResponse> {
      requests.push(request);
      return fixture.generate(request);
    },
  };
  const host = grantHost(tempDataDir('rp0464-round2'), sample.spec, sample.scope, recording);
  const engine = new CouncilEngine(host);
  await engine.createSession({ ...sample, sample: true });
  const done = await engine.startSession(sample.spec.session_id, 'test-grant');
  assert.equal(done.state.state, 'COMPLETED');
  // The golden Round 1 spread on option C (3 vs 9) issues exactly one
  // crux, assigned to td-jakes and tiffany-aliche (the engine's
  // deterministic crux extraction, unchanged).
  const round2 = requests.filter((r) => r.purpose === 'advisor' && r.round === 2);
  assert.equal(round2.length, 9);
  for (const request of round2) {
    const input = request.input as {
      challenges_for_seat?: Array<{ crux_id: string }>;
    };
    const assigned = (input.challenges_for_seat ?? []).map((c) => c.crux_id);
    if (assigned.length > 0) {
      assert.ok(
        request.system.includes(
          `challenges_answered must contain exactly the challenge IDs issued to you for this call, copied verbatim, and nothing else: ${assigned.join(', ')}`,
        ),
        `${request.seat_id}: the exact issued IDs are conveyed`,
      );
    } else {
      assert.ok(
        request.system.includes(
          'challenges_answered: no challenges have been issued to you for this call',
        ),
        `${request.seat_id}: an empty issuance is stated, not left to guessing`,
      );
    }
  }
  const jakes = round2.find((r) => r.seat_id === 'td-jakes');
  assert.ok(jakes, 'td-jakes received a Round 2 call');
  assert.ok(
    jakes!.system.includes('crux-1'),
    'the issued crux ID itself reaches the seat that must answer it',
  );
});

// ------------------------------------------------------------- (3) control

test('rp0464 (3) control: a double that repeats the bad payload on the repair still blocks, validator unweakened', async () => {
  const sample = buildSampleSession();
  const transport = new ScriptedSeatTransport(
    'simon-sinek',
    reconstructedFailure('simon-sinek'),
    true,
  );
  const host = grantHost(tempDataDir('rp0464-control'), sample.spec, sample.scope, transport);
  const engine = new CouncilEngine(host);
  await engine.createSession({ ...sample, sample: true });
  const done = await engine.startSession(sample.spec.session_id, 'test-grant');
  assert.equal(done.state.state, 'BLOCKED');
  const reason = await blockedReason(engine, sample.spec.session_id);
  assert.ok(
    reason.includes(
      'simon-sinek: Seat simon-sinek (round-1) returned an invalid card after the permitted repair: card_kind: Invalid discriminator value',
    ),
    `the verbatim live failure shape is the recorded reason: ${reason}`,
  );
  assert.equal(
    transport.callsFor('simon-sinek', 1).length,
    2,
    'still exactly one permitted repair, never a second',
  );
  const cards = await host.store.listCards(sample.spec.session_id);
  assert.equal(
    cards.filter((c) => c.seat_id === 'simon-sinek').length,
    0,
    'no card was committed for the non-conforming seat',
  );
});

// ------------------------------------------------------------- (4) positive controls

test('rp0464 (4): the four retrieved accepted cards from the live session still validate untouched', () => {
  const here = dirname(fileURLToPath(import.meta.url));
  for (const seat of [
    'russell-brunson',
    'michelle-obama',
    'brene-brown',
    'dennis-kimbro',
  ]) {
    const card = JSON.parse(
      readFileSync(join(here, 'fixtures', 'rp0464', `accepted-${seat}.json`), 'utf8'),
    ) as Record<string, unknown>;
    const full = validateCard(card);
    assert.equal(
      full.ok,
      true,
      `${seat}: the retrieved live card validates under the unchanged validator`,
    );
    const { host: _host, ...author } = card;
    const authorResult = validateCardAuthor(author);
    assert.equal(
      authorResult.ok,
      true,
      `${seat}: the retrieved author payload validates untouched`,
    );
  }
});

// ------------------------------------------------------------- (5) harness e2e

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

function e2eHarnessScript(counterPath: string, promptPath: string): string {
  return `#!/usr/bin/env node
const fs = require('node:fs');
if (process.argv[2] === '--help') process.exit(0); // transport capability probe, not a model call
// The fixture harness stands in for the client's harness binary at
// the delegate boundary. It records every prompt it receives (so
// the test can assert on the conveyance the model side actually
// saw) and answers with a conforming golden card as plain JSON.
let data = '';
process.stdin.on('data', (c) => { data += c; });
process.stdin.on('end', () => {
  fs.appendFileSync(${JSON.stringify(counterPath)}, 'call\\n');
  fs.appendFileSync(${JSON.stringify(promptPath)}, JSON.stringify(data) + '\\n');
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
  process.stdout.write(JSON.stringify({
    result: JSON.stringify(card),
    session_id: 'rp0464-e2e-harness-session',
    usage: { input_tokens: 11, output_tokens: 7 },
    modelUsage: { 'harness-reported-model': {} },
  }));
});
`;
}

test('rp0464 (5) e2e: a full session through the composed harness path reaches the golden verdict, and every prompt carries the strengthened contract', async () => {
  const home = mkdtempSync(join(tmpdir(), 'rp0464-e2e-home-'));
  mkdirSync(join(home, '.claude-nine'), { recursive: true });
  const binDir = join(home, '.local', 'bin');
  mkdirSync(binDir, { recursive: true });
  const counterPath = join(home, 'harness-calls.log');
  const promptPath = join(home, 'harness-prompts.jsonl');
  const exe = join(binDir, 'claude-nine');
  writeFileSync(exe, e2eHarnessScript(counterPath, promptPath), 'utf8');
  chmodSync(exe, 0o755);

  const dataDir = tempDataDir('rp0464-e2e');
  const { host, routeDiscovery } = createLocalHost({
    dataDir,
    homeDir: home,
    env: { PATH: '/usr/bin:/bin' },
  });
  const info = (routeDiscovery ?? []).find(
    (r) => r.route_id === 'claude-nine-configured',
  );
  assert.ok(info && info.composed, 'the harness route is discovered and composed');

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
  const engine = new CouncilEngine(host);
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
  // Exact ledger counts: 27 provider requests, no repairs needed,
  // and the harness executable was invoked exactly 27 times.
  const budget = host.budget.snapshot(spec.session_id);
  assert.equal(budget.consumed.provider_requests, 27);
  assert.equal(budget.consumed.output_repairs, 0);
  const harnessCalls = readFileSync(counterPath, 'utf8').trim().split('\n').length;
  assert.equal(harnessCalls, 27);
  // Every prompt the harness received carries the strengthened
  // contract conveyance for its call.
  const prompts = readFileSync(promptPath, 'utf8')
    .trim()
    .split('\n')
    .map((line) => JSON.parse(line) as string);
  assert.equal(prompts.length, 27);
  const advisorFields = requiredCardFields('advisor').join(', ');
  for (const prompt of prompts) {
    assert.ok(
      prompt.includes('Return exactly one JSON object and nothing else'),
      'every harness prompt carries the JSON-only contract opening',
    );
    assert.ok(
      prompt.includes(advisorFields) ||
        prompt.includes(requiredCardFields('ratification').join(', ')),
      'every harness prompt states its complete required-field list in prose',
    );
  }
  const round1Prompts = prompts.filter((p) =>
    p.includes('Return one AdvisorCard matching the supplied schema'),
  );
  assert.equal(round1Prompts.length, 9);
  for (const prompt of round1Prompts) {
    assert.ok(
      prompt.includes(
        'challenges_answered: no challenges have been issued to you for this call, so challenges_answered must be an empty array []',
      ),
      'every Round 1 harness prompt states the empty challenge issuance',
    );
    assert.ok(
      prompt.includes(DUE_AT_EXAMPLE),
      'every Round 1 harness prompt carries the due_at format example',
    );
    assert.ok(
      prompt.includes('"card_kind" field must be exactly "advisor"'),
      'every Round 1 harness prompt states the single exact card_kind',
    );
  }
});
