/**
 * CWE-025 tests, part 1: the pure deliberation services in
 * src/protocol/challenge.ts and src/protocol/ratification.ts (crux
 * extraction, draft composition, the quick-mode skip gate, and the
 * completion assembly), exercised over crafted committed-card records
 * and CWE-023's real frozen policy record. No provider calls.
 *
 * Section 35 contracts exercised here:
 * - T021: full mode keeps all nine seats; a missing card blocks
 *   completion in place and never converts the session to a smaller
 *   mode.
 * - T022: the quick-mode ratification-skip gate (CWE-023's five
 *   frozen prerequisites, evaluated by CWE-025) passes only on a
 *   fully compliant record; a tie, a wide spread, an unresolved
 *   critical domain, a critical abstention, and a dropped blocking
 *   condition each fail it.
 * - T023: a selected-mode outcome names its subset exactly (panel and
 *   active weights); consult outcomes are covered in part 2.
 * - T038 (service half): crux extraction derives every challenge from
 *   the committed opening record; nothing is fabricated.
 * - T039: unanimity yields the labeled adversarial test, never a
 *   fabricated dispute.
 * - T045: a missing seat is accounted missing, never an abstention;
 *   an explicit abstention card is accounted an abstention and is
 *   never counted missing.
 * - T046/T147: support is counted only against the exact draft hash;
 *   a material amendment is material even when labeled nonmaterial,
 *   transfers no support, and creates no fourth round.
 * - T048 (completion half): unresolved disagreement completes
 *   honestly through the analysis label; no round beyond 3 exists.
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  canonicalHash,
  GOLDEN_WEIGHTS,
  SEAT_IDS,
  type AdvisorCard,
  type Amendment,
  type CouncilCard,
  type DecisionBrief,
  type HostStamp,
  type RatificationCard,
  type SeatId,
  type SessionSpec,
} from '../src/contracts/index.js';
import { quickModePolicyRecord } from '../src/intake/panel.js';
import {
  assignedCruxesFor,
  extractCruxes,
  unanimityStressCrux,
} from '../src/protocol/challenge.js';
import {
  assembleDeliberationOutcome,
  composeDraftResolution,
  deriveCriticalDomainApplicability,
  evaluateQuickModeSkip,
} from '../src/protocol/ratification.js';
import {
  assessAmendment,
  computeResolutionSupport,
  draftResolutionSemanticHash,
  findMisboundRatificationCards,
} from '../src/protocol/verdict.js';
import { analyzeDecision } from '../src/scoring/index.js';

// ------------------------------------------------------------- fixtures

const SESSION_ID = 'sess-later-1';
const PACK_VERSION = 'pack-test-1.0.0';

const OPTIONS = [
  { id: 'A', label: 'Keep the current offer', kind: 'status_quo' as const },
  { id: 'B', label: 'Pilot the revised offer', kind: 'bounded_test' as const },
  { id: 'C', label: 'Launch the revised offer broadly', kind: 'change' as const },
];

function briefFor(panel: readonly SeatId[], overrides: Partial<DecisionBrief> = {}): DecisionBrief {
  return {
    schema_version: 'wise-elders.brief/v1',
    brief_id: 'brief-later-1',
    session_id: SESSION_ID,
    revision: 1,
    question: 'Should we pilot the revised offer before a broad launch?',
    facts: [
      { id: 'fact-1', statement: 'Current offer converts at a measured baseline.', evidence_ids: ['ev-case-1'] },
    ],
    assumptions: [
      { id: 'asm-1', statement: 'Pilot capacity exists for one cohort.', evidence_ids: [] },
    ],
    unknowns: [
      { id: 'unk-1', statement: 'Pilot cohort retention is not yet measured.', evidence_ids: [] },
    ],
    constraints: [
      {
        id: 'con-1',
        description: 'Pilot spend must stay within the approved budget.',
        hard: true,
        applies_to_option_ids: ['B', 'C'],
      },
    ],
    options: OPTIONS.map((o) => ({ ...o })),
    relevance_weights: Object.fromEntries(
      panel.map((seatId) => [seatId, GOLDEN_WEIGHTS[SEAT_IDS.indexOf(seatId)]]),
    ),
    critical_domains: [],
    evidence_manifest: [
      { evidence_id: 'ev-case-1', sha256: canonicalHash({ case: 1 }), source_kind: 'client_document' as const, locator: 'doc:baseline' },
    ],
    private_preference_ref: 'pref-marker-SECRET-025',
    created_at: '2026-10-14T02:00:00Z',
    display_timezone: 'America/New_York',
    ...overrides,
  };
}

function specFor(mode: SessionSpec['mode'], panel: readonly SeatId[], brief: DecisionBrief): SessionSpec {
  return {
    schema_version: 'wise-elders.session/v1',
    session_id: SESSION_ID,
    mode,
    visibility: 'company',
    brief_revision: 1,
    brief_sha256: canonicalHash(brief),
    options: OPTIONS.map((o) => ({ ...o })),
    seat_ids: [...panel],
    model_policy: {
      selection: 'explicit',
      route_id: 'route-a',
      requested_model_id: 'model-selected-by-client',
      reasoning_preference: null,
      fallback_policy: 'none',
    },
    source_pack_version: PACK_VERSION,
    execution_policy: 'advisory_only',
    created_at: '2026-10-14T02:00:00Z',
    display_timezone: 'America/New_York',
  };
}

function hostStamp(seatId: SeatId, round: number): HostStamp {
  return {
    scope: {
      tenant_id: 'tenant-a',
      company_id: 'company-a',
      installation_id: 'install-a',
      owner_subject: 'owner-1',
    },
    operation_id: `op-${seatId}-${round}`,
    route_id: 'route-a',
    session_id: SESSION_ID,
    stamped_at: '2026-10-14T12:00:00.000Z',
    source_status: 'unverified',
  };
}

interface AdvisorSpec {
  scores: Record<string, number | null>;
  preferred?: string | null;
  stance?: AdvisorCard['stance'];
  conditions?: AdvisorCard['conditions'];
  challenges?: string[];
  unknowns?: string[];
}

function advisorCard(seatId: SeatId, round: 1 | 2, spec: AdvisorSpec): AdvisorCard {
  const scores = OPTIONS.map((o) => ({
    option_id: o.id,
    score: spec.scores[o.id] ?? null,
    rationale: `Seat ${seatId} round ${round} rationale for ${o.id}.`,
    evidence_ids: [] as string[],
  }));
  const top = [...scores]
    .filter((s) => s.score !== null)
    .sort((a, b) => (b.score as number) - (a.score as number))[0];
  return {
    schema_version: 'wise-elders.card/v1',
    session_id: SESSION_ID,
    brief_revision: 1,
    seat_id: seatId,
    input_manifest_sha256: canonicalHash({ seat: seatId, round }),
    pack_version: PACK_VERSION,
    card_kind: 'advisor',
    round,
    stance: spec.stance ?? 'conditional',
    preferred_option_id: spec.preferred === undefined ? (top?.option_id ?? null) : spec.preferred,
    option_scores: scores,
    framework_applications: [],
    decisive_arguments: [`Seat ${seatId} decisive argument.`],
    strongest_objection: `Seat ${seatId} strongest objection.`,
    conditions: spec.conditions ?? [],
    critical_unknowns: spec.unknowns ?? [],
    change_my_mind: 'Measured evidence that the binding constraint no longer holds.',
    challenges_answered: spec.challenges ?? [],
    quotes: [],
    evidence_strength: 'medium',
    minority_position: null,
    host: hostStamp(seatId, round),
  };
}

function ratificationCard(
  seatId: SeatId,
  draftSha: string,
  spec: AdvisorSpec & {
    resolution_stance?: RatificationCard['resolution_stance'];
    amendments?: Amendment[];
  },
): RatificationCard {
  const base = advisorCard(seatId, 2, spec);
  return {
    schema_version: 'wise-elders.card/v1',
    session_id: SESSION_ID,
    brief_revision: 1,
    seat_id: seatId,
    input_manifest_sha256: canonicalHash({ seat: seatId, round: 3 }),
    pack_version: PACK_VERSION,
    card_kind: 'ratification',
    round: 3,
    draft_resolution_sha256: draftSha,
    resolution_stance: spec.resolution_stance ?? 'support',
    stance: base.stance,
    preferred_option_id: base.preferred_option_id,
    option_scores: base.option_scores,
    amendments: spec.amendments ?? [],
    accepted_condition_ids: [],
    unresolved_objections: [],
    evidence_strength: 'medium',
    host: hostStamp(seatId, 3),
  };
}

const BLOCKING_CONDITION: AdvisorCard['conditions'][number] = {
  id: 'cond-block-1',
  description: 'Pilot cohort capacity must be confirmed before any launch spend.',
  kind: 'evidence_required',
  blocking: true,
  verification_method: 'Confirm cohort capacity with the operations lead.',
  required_evidence: ['Written capacity confirmation'],
  responsible_role: 'operations',
  due_at: null,
  status: 'open',
  depends_on: [],
};

// ---------------------------------------------------------------- cruxes

test('cruxes: spread, blocking condition, and preference split extract deterministically with a ceiling of three', () => {
  const brief = briefFor(SEAT_IDS);
  const cards = [
    advisorCard('simon-sinek', 1, { scores: { A: 8, B: 2, C: 5 }, preferred: 'A' }),
    advisorCard('td-jakes', 1, { scores: { A: 7, B: 9, C: 5 }, preferred: 'B', conditions: [BLOCKING_CONDITION] }),
    advisorCard('oprah-winfrey', 1, { scores: { A: 8, B: 8, C: 5 }, preferred: 'B' }),
    advisorCard('tiffany-aliche', 1, { scores: { A: 7, B: 8, C: 5 }, preferred: 'B' }),
  ];
  const cruxes = extractCruxes(cards, brief, SEAT_IDS);
  assert.ok(cruxes.length >= 2 && cruxes.length <= 3, 'up to three cruxes');
  assert.deepEqual(cruxes.map((c) => c.crux_id), cruxes.map((_, i) => `crux-${i + 1}`));

  const numbers = cruxes.find((c) => c.origin === 'score_spread');
  assert.ok(numbers, 'a 7-point spread on B is a numbers crux');
  assert.equal(numbers.type, 'numbers');
  assert.equal(numbers.option_id, 'B');
  assert.deepEqual([...numbers.responsible_seats].sort(), ['simon-sinek', 'td-jakes']);
  assert.ok(numbers.competing_claims.some((claim) => claim.includes('scores option B at 2')));
  assert.ok(numbers.competing_claims.some((claim) => claim.includes('scores option B at 9')));

  const values = cruxes.find((c) => c.origin === 'preference_split');
  assert.ok(values, 'split preferences are a values crux');
  assert.equal(values.type, 'values');
  assert.ok(values.responsible_seats.includes('simon-sinek'));

  // Determinism: the same record extracts the identical crux set.
  assert.deepEqual(extractCruxes(cards, brief, SEAT_IDS), cruxes);
  // No fabricated dissent: every crux's claims come from recorded values.
  for (const crux of cruxes) {
    assert.equal(crux.adversarial_test, false);
    assert.ok(crux.responsible_seats.length >= 1);
  }
});

test('cruxes: a blocking condition on the leading option is an execution crux with the condition as its test', () => {
  const brief = briefFor(SEAT_IDS);
  const cards = [
    advisorCard('simon-sinek', 1, { scores: { A: 5, B: 8, C: 5 }, preferred: 'B' }),
    advisorCard('td-jakes', 1, { scores: { A: 5, B: 9, C: 5 }, preferred: 'B', conditions: [BLOCKING_CONDITION] }),
    advisorCard('oprah-winfrey', 1, { scores: { A: 5, B: 7, C: 5 }, preferred: 'B' }),
  ];
  const cruxes = extractCruxes(cards, brief, SEAT_IDS);
  const execution = cruxes.find((c) => c.origin === 'blocking_condition');
  assert.ok(execution, 'blocking condition on the leading option is extracted');
  assert.equal(execution.type, 'execution');
  assert.equal(execution.option_id, 'B');
  assert.equal(execution.resolution_test, BLOCKING_CONDITION.verification_method);
  assert.ok(execution.needed_evidence.includes('Written capacity confirmation'));
  assert.ok(execution.responsible_seats.includes('td-jakes'));
});

test('T039: unanimity invokes the labeled adversarial test and never fabricates dissent', () => {
  const brief = briefFor(SEAT_IDS);
  const cards = [
    advisorCard('simon-sinek', 1, { scores: { A: 5, B: 9, C: 6 }, preferred: 'B' }),
    advisorCard('td-jakes', 1, { scores: { A: 6, B: 8, C: 5 }, preferred: 'B' }),
    advisorCard('oprah-winfrey', 1, { scores: { A: 4, B: 9, C: 7 }, preferred: 'B' }),
  ];
  const stress = unanimityStressCrux(cards, brief, SEAT_IDS);
  assert.ok(stress, 'unanimity produces the stress test');
  assert.equal(stress.origin, 'unanimity_stress_test');
  assert.equal(stress.adversarial_test, true);
  assert.ok(stress.competing_claims[0].includes('prefer option B'));
  assert.ok(stress.competing_claims[1].includes('strongest neglected alternative'));
  assert.ok(stress.resolution_test.includes('adversarial testing, not genuine dissent'));

  const cruxes = extractCruxes(cards, brief, SEAT_IDS);
  assert.equal(cruxes.length, 1, 'the stress test is the only crux in a unanimous, tight record');
  assert.equal(cruxes[0].adversarial_test, true);

  // A split panel never gets a stress crux.
  const split = [
    advisorCard('simon-sinek', 1, { scores: { A: 9, B: 4, C: 5 }, preferred: 'A' }),
    advisorCard('td-jakes', 1, { scores: { A: 4, B: 9, C: 5 }, preferred: 'B' }),
  ];
  assert.equal(unanimityStressCrux(split, brief, SEAT_IDS), null);
  assert.ok(extractCruxes(split, brief, SEAT_IDS).every((c) => !c.adversarial_test));
});

test('T038 (service half): assignments come only from the extracted record', () => {
  const brief = briefFor(SEAT_IDS);
  const cards = [
    advisorCard('simon-sinek', 1, { scores: { A: 8, B: 2, C: 5 }, preferred: 'A' }),
    advisorCard('td-jakes', 1, { scores: { A: 6, B: 9, C: 6 }, preferred: 'B' }),
  ];
  const cruxes = extractCruxes(cards, brief, SEAT_IDS);
  assert.ok(cruxes.length > 0);
  for (const crux of cruxes) {
    for (const seatId of crux.responsible_seats) {
      assert.ok(
        assignedCruxesFor(cruxes, seatId).some((c) => c.crux_id === crux.crux_id),
        'assignment is symmetric with the crux record',
      );
    }
  }
  // A seat outside every crux has no assignment, and that is a planned
  // state, not an error (its fresh card is still required, T149).
  assert.deepEqual(assignedCruxesFor(cruxes, 'les-brown'), []);
});

// ------------------------------------------------------------------ draft

test('draft: the recommendation is CWE-026 arithmetic; duplicate conditions merge without losing sources', () => {
  const brief = briefFor(SEAT_IDS);
  const shared = { ...BLOCKING_CONDITION, id: 'cond-shared-a', blocking: false };
  const sharedTwin = { ...BLOCKING_CONDITION, id: 'cond-shared-b', blocking: false };
  const round2 = [
    advisorCard('simon-sinek', 2, { scores: { A: 5, B: 9, C: 5 }, preferred: 'B', conditions: [shared] }),
    advisorCard('td-jakes', 2, { scores: { A: 5, B: 8, C: 5 }, preferred: 'B', conditions: [sharedTwin] }),
    advisorCard('oprah-winfrey', 2, { scores: { A: 6, B: 7, C: 5 }, preferred: 'B' }),
  ];
  const composition = composeDraftResolution({
    brief,
    active_seat_ids: SEAT_IDS,
    round2Cards: round2,
  });
  assert.equal(composition.draft.recommended_option_id, 'B');
  assert.equal(composition.draft.actions.length, 1, 'the duplicate condition merged into one action');
  assert.deepEqual(
    [...composition.action_source_condition_ids[0]].sort(),
    ['cond-shared-a', 'cond-shared-b'],
    'both source condition IDs survive the merge',
  );
  // The semantic hash is CWE-026's and recomputes exactly.
  assert.equal(
    draftResolutionSemanticHash(composition.draft),
    composition.draft.semantic_sha256,
  );
  // The draft's limits are the brief's hard constraints, verbatim.
  assert.deepEqual(composition.draft.limits, [
    'Pilot spend must stay within the approved budget.',
  ]);
  // Determinism: composing again yields the identical draft and hash.
  const again = composeDraftResolution({ brief, active_seat_ids: SEAT_IDS, round2Cards: round2 });
  assert.deepEqual(again.draft, composition.draft);
});

test('applicability derivation matches the publication validator shape', () => {
  const brief = briefFor(SEAT_IDS, {
    critical_domains: [
      {
        schema_version: 'wise-elders.critical-domain-requirement/v1',
        domain: 'financial_feasibility',
        status: 'unresolved',
        trigger_evidence_ids: [],
        trigger_field_paths: ['constraints.con-1'],
        required_seat_id: 'tiffany-aliche',
        required_checker: 'seat',
        unresolved_questions: ['Can the client fund the pilot without destabilizing the foundation?'],
        policy_version: 'policy-1',
      },
    ],
  });
  assert.deepEqual(deriveCriticalDomainApplicability(brief), [
    { domain: 'financial_feasibility', option_id: 'B' },
    { domain: 'financial_feasibility', option_id: 'C' },
  ]);
});

// --------------------------------------------------------------- quick gate

const QUICK_PANEL: SeatId[] = ['simon-sinek', 'tiffany-aliche', 'russell-brunson', 'brene-brown'];

function quickCards(bScores: Record<SeatId, number>, tweak?: (seatId: SeatId, card: AdvisorCard) => AdvisorCard) {
  const round1 = QUICK_PANEL.map((seatId) =>
    advisorCard(seatId, 1, { scores: { A: 5, B: bScores[seatId], C: 5 }, preferred: 'B' }),
  );
  let round2 = QUICK_PANEL.map((seatId) =>
    advisorCard(seatId, 2, { scores: { A: 5, B: bScores[seatId], C: 5 }, preferred: 'B' }),
  );
  if (tweak) round2 = round2.map((card) => tweak(card.seat_id, card));
  return { round1, round2 };
}

function quickGate(
  round1: AdvisorCard[],
  round2: AdvisorCard[],
  briefOverrides: Partial<DecisionBrief> = {},
) {
  const brief = briefFor(QUICK_PANEL, briefOverrides);
  const composition = composeDraftResolution({
    brief,
    active_seat_ids: QUICK_PANEL,
    round2Cards: round2,
  });
  return {
    brief,
    composition,
    evaluation: evaluateQuickModeSkip({
      policy: quickModePolicyRecord(QUICK_PANEL),
      brief,
      round1Cards: round1,
      round2Cards: round2,
      draft: composition.draft,
      draft_action_source_condition_ids: composition.action_source_condition_ids,
    }),
  };
}

test('T022: the skip gate passes only when all five frozen prerequisites hold', () => {
  const { round1, round2 } = quickCards({
    'simon-sinek': 9, 'tiffany-aliche': 8, 'russell-brunson': 9, 'brene-brown': 8,
  });
  const { evaluation } = quickGate(round1, round2);
  assert.equal(evaluation.skip, true);
  assert.deepEqual(
    evaluation.prerequisites.map((p) => p.id),
    [
      'all_cards_valid',
      'same_highest_ranked_option',
      'spread_at_most_3',
      'no_unresolved_critical_fact_or_constraint',
      'no_unassessed_material_condition',
    ],
    'the evaluated prerequisites are exactly CWE-023\'s frozen five',
  );
  assert.ok(evaluation.prerequisites.every((p) => p.satisfied));
  assert.equal(evaluation.ratification_status_when_skipped, 'not_run_by_quick_mode_policy');
});

test('T022 negatives: tie, spread, unresolved domain, critical abstention, and dropped condition each fail the gate', () => {
  const base = {
    'simon-sinek': 9, 'tiffany-aliche': 8, 'russell-brunson': 9, 'brene-brown': 8,
  } as Record<SeatId, number>;

  // A tie inside one card: no unique highest-ranked option.
  {
    const { round1, round2 } = quickCards(base, (seatId, card) =>
      seatId === 'simon-sinek'
        ? advisorCard(seatId, 2, { scores: { A: 9, B: 9, C: 5 }, preferred: 'B' })
        : card,
    );
    const { evaluation } = quickGate(round1, round2);
    assert.equal(evaluation.skip, false);
    assert.equal(evaluation.prerequisites[1].satisfied, false, 'tie fails prerequisite 2');
  }
  // Spread of 5 on the common option.
  {
    const { round1, round2 } = quickCards({ ...base, 'brene-brown': 4 });
    const { evaluation } = quickGate(round1, round2);
    assert.equal(evaluation.skip, false);
    assert.equal(evaluation.prerequisites[2].satisfied, false, 'spread 5 fails prerequisite 3');
  }
  // An unresolved critical domain.
  {
    const { round1, round2 } = quickCards(base);
    const { evaluation } = quickGate(round1, round2, {
      critical_domains: [
        {
          schema_version: 'wise-elders.critical-domain-requirement/v1',
          domain: 'financial_feasibility',
          status: 'unresolved',
          trigger_evidence_ids: [],
          trigger_field_paths: [],
          required_seat_id: 'tiffany-aliche',
          required_checker: 'seat',
          unresolved_questions: ['Is the pilot affordable?'],
          policy_version: 'policy-1',
        },
      ],
    });
    assert.equal(evaluation.skip, false);
    assert.equal(evaluation.prerequisites[3].satisfied, false, 'unresolved domain fails prerequisite 4');
  }
  // A critical abstention: the required reviewer scores the top option null.
  {
    const { round1, round2 } = quickCards(base, (seatId, card) =>
      seatId === 'tiffany-aliche'
        ? advisorCard(seatId, 2, { scores: { A: 5, B: null, C: 5 }, preferred: 'A' })
        : card,
    );
    const { evaluation } = quickGate(round1, round2, {
      critical_domains: [
        {
          schema_version: 'wise-elders.critical-domain-requirement/v1',
          domain: 'financial_feasibility',
          status: 'assessed',
          trigger_evidence_ids: [],
          trigger_field_paths: [],
          required_seat_id: 'tiffany-aliche',
          required_checker: 'seat',
          unresolved_questions: [],
          policy_version: 'policy-1',
        },
      ],
    });
    assert.equal(evaluation.skip, false);
    assert.equal(evaluation.prerequisites[3].satisfied, false, 'critical abstention fails prerequisite 4');
    assert.ok(evaluation.prerequisites[3].detail.includes('abstained'));
  }
  // A blocking condition dropped from the draft.
  {
    const { round1, round2 } = quickCards(base, (seatId, card) =>
      seatId === 'simon-sinek'
        ? advisorCard(seatId, 2, { scores: { A: 5, B: 9, C: 5 }, preferred: 'B', conditions: [BLOCKING_CONDITION] })
        : card,
    );
    // Compose a draft that omits the blocking condition (a chair edit).
    const brief = briefFor(QUICK_PANEL);
    const evaluation = evaluateQuickModeSkip({
      policy: quickModePolicyRecord(QUICK_PANEL),
      brief,
      round1Cards: round1,
      round2Cards: round2,
      draft: {
        schema_version: 'wise-elders.draft-resolution/v1',
        session_id: SESSION_ID,
        brief_revision: 1,
        revision: 1,
        recommended_option_id: 'B',
        actions: [],
        prerequisites: [],
        limits: [],
        semantic_sha256: canonicalHash({ edited: true }),
      },
    });
    assert.equal(evaluation.skip, false);
    assert.equal(evaluation.prerequisites[4].satisfied, false, 'dropped blocking condition fails prerequisite 5');
  }
  // A missing card.
  {
    const { round1, round2 } = quickCards(base);
    const { evaluation } = quickGate(round1, round2.slice(0, 3));
    assert.equal(evaluation.skip, false);
    assert.equal(evaluation.prerequisites[0].satisfied, false, 'missing card fails prerequisite 1');
  }
});

// -------------------------------------------------------------- completion

function fullRecord(missingRound2Seat?: SeatId) {
  const brief = briefFor(SEAT_IDS);
  const spec = specFor('full', SEAT_IDS, brief);
  const scores = { A: 5, B: 9, C: 6 };
  const round1 = SEAT_IDS.map((seatId) => advisorCard(seatId, 1, { scores, preferred: 'B' }));
  const round2 = SEAT_IDS
    .filter((seatId) => seatId !== missingRound2Seat)
    .map((seatId) => advisorCard(seatId, 2, { scores, preferred: 'B' }));
  const composition = composeDraftResolution({ brief, active_seat_ids: SEAT_IDS, round2Cards: round2 });
  const round3 = SEAT_IDS.map((seatId) =>
    ratificationCard(seatId, composition.draft.semantic_sha256, { scores, preferred: 'B' }),
  );
  return { brief, spec, cards: [...round1, ...round2, ...round3] as CouncilCard[], composition };
}

test('T021: full mode with one missing Round 2 card completes nothing and keeps all nine seats', () => {
  const { brief, spec, cards } = fullRecord('les-brown');
  const outcome = assembleDeliberationOutcome({ spec, brief, cards });
  assert.equal(outcome.status, 'incomplete');
  if (outcome.status !== 'incomplete') return;
  assert.equal(outcome.mode, 'full');
  assert.deepEqual(outcome.panel_seat_ids, [...SEAT_IDS], 'the panel is still all nine seats');
  assert.deepEqual(outcome.missing, [{ round: 2, seat_id: 'les-brown' }]);
  assert.equal(outcome.accounting.round2['les-brown'], 'missing');
  assert.ok(!('verdict' in outcome), 'no verdict is assembled from a partial full panel');
});

test('full mode complete record: verdict assembles, publishes, and counts support on the exact hash', () => {
  const { brief, spec, cards, composition } = fullRecord();
  const outcome = assembleDeliberationOutcome({
    spec, brief, cards, draft_composition: composition,
  });
  assert.equal(outcome.status, 'complete');
  if (outcome.status !== 'complete') return;
  assert.equal(outcome.verdict.recommended_option_id, 'B');
  assert.equal(outcome.ratification_status, 'ratified');
  assert.equal(outcome.publication.publishable, true);
  assert.ok(outcome.resolution_support);
  assert.equal(outcome.resolution_support.resolution_sha256, composition.draft.semantic_sha256);
  assert.equal(outcome.resolution_support.support, 22, 'all nine weights support the exact draft');
  assert.equal(outcome.accounting.round3['td-jakes'], 'card');
});

test('T045 + T023: selected mode accounts a missing seat as missing and an abstention as an abstention', () => {
  const panel: SeatId[] = ['simon-sinek', 'tiffany-aliche', 'russell-brunson', 'brene-brown'];
  const brief = briefFor(panel);
  const spec = specFor('selected', panel, brief);
  const scores = { A: 5, B: 9, C: 6 };
  const round1 = panel.map((seatId) => advisorCard(seatId, 1, { scores, preferred: 'B' }));
  const round2 = panel.map((seatId) => advisorCard(seatId, 2, { scores, preferred: 'B' }));
  const composition = composeDraftResolution({ brief, active_seat_ids: panel, round2Cards: round2 });
  const sha = composition.draft.semantic_sha256;
  const round3 = [
    ratificationCard('simon-sinek', sha, { scores, preferred: 'B' }),
    // An explicit abstention: a returned card, stance and stance on
    // the resolution both abstain, every score null.
    ratificationCard('tiffany-aliche', sha, {
      scores: { A: null, B: null, C: null },
      preferred: null,
      stance: 'abstain',
      resolution_stance: 'abstain',
    }),
    ratificationCard('russell-brunson', sha, { scores, preferred: 'B' }),
    // brene-brown: no ratification card at all.
  ];
  const outcome = assembleDeliberationOutcome({
    spec, brief, cards: [...round1, ...round2, ...round3], draft_composition: composition,
  });
  assert.equal(outcome.status, 'complete');
  if (outcome.status !== 'complete') return;
  // T023: the outcome names its subset exactly.
  assert.deepEqual(outcome.panel_seat_ids, panel);
  assert.deepEqual(
    Object.keys(outcome.verdict.active_weights).sort(),
    [...panel].sort(),
    'active weights cover exactly the selected subset',
  );
  // T045: missing is missing; abstention is abstention; neither is
  // relabeled as the other.
  assert.equal(outcome.accounting.round3['brene-brown'], 'missing');
  assert.equal(outcome.accounting.round3['tiffany-aliche'], 'explicit_abstention');
  assert.deepEqual(outcome.analysis.missing_seat_ids, ['brene-brown']);
  const optionB = outcome.analysis.options.find((o) => o.option_id === 'B');
  assert.ok(optionB);
  assert.deepEqual(optionB.abstained_seat_ids, ['tiffany-aliche']);
  assert.ok(!optionB.scored_seat_ids.includes('brene-brown'));
  // Support counts the abstention under abstention, on the exact hash.
  assert.ok(outcome.resolution_support);
  assert.equal(outcome.resolution_support.abstention, GOLDEN_WEIGHTS[SEAT_IDS.indexOf('tiffany-aliche')]);
});

test('T046 + T147: support never transfers to a changed hash; a material amendment marks the plan unratified and creates no fourth round', () => {
  const { brief, composition } = fullRecord();
  const sha = composition.draft.semantic_sha256;
  const cards = SEAT_IDS.map((seatId) =>
    ratificationCard(seatId, sha, { scores: { A: 5, B: 9, C: 6 }, preferred: 'B' }),
  );
  // Counted against a DIFFERENT (amended) hash, the same cards count
  // for nothing: every seat is misbound and every count is zero.
  const amendedSha = canonicalHash({ amended: 'draft' });
  const support = computeResolutionSupport(cards, brief.relevance_weights, amendedSha);
  assert.deepEqual(
    [support.support, support.conditional_support, support.opposition, support.abstention],
    [0, 0, 0, 0],
  );
  assert.deepEqual(findMisboundRatificationCards(cards, amendedSha), [...SEAT_IDS]);

  // A material change is material even when its proposer labels it
  // nonmaterial, and it never creates a fourth round or a dispatch.
  const assessment = assessAmendment({
    target_path: 'recommended_option_id',
    claimed_materiality: 'nonmaterial',
  });
  assert.equal(assessment.materiality, 'material');
  assert.equal(assessment.support_transfers, false);
  assert.equal(assessment.ratification_status_if_published, 'material_change_unratified');
  assert.equal(assessment.creates_fourth_round, false);
  assert.equal(assessment.dispatch_allowed, false);

  // Completion over cards carrying a proposed material amendment:
  // the verdict is marked material_change_unratified.
  const briefFull = briefFor(SEAT_IDS);
  const spec = specFor('full', SEAT_IDS, briefFull);
  const scores = { A: 5, B: 9, C: 6 };
  const round1 = SEAT_IDS.map((seatId) => advisorCard(seatId, 1, { scores, preferred: 'B' }));
  const round2 = SEAT_IDS.map((seatId) => advisorCard(seatId, 2, { scores, preferred: 'B' }));
  const composition2 = composeDraftResolution({ brief: briefFull, active_seat_ids: SEAT_IDS, round2Cards: round2 });
  const amendment: Amendment = {
    amendment_id: 'amd-1',
    proposing_seat_id: 'simon-sinek',
    target_path: 'recommended_option_id',
    old_value: 'B',
    new_value: 'C',
    statement: 'Recommend C instead of B.',
    reason: 'A recorded reason.',
    evidence_ids: [],
    materiality: 'nonmaterial',
    disposition: 'proposed',
    reviewer_reason: null,
  };
  const round3 = SEAT_IDS.map((seatId) =>
    ratificationCard(seatId, composition2.draft.semantic_sha256, {
      scores,
      preferred: 'B',
      amendments: seatId === 'simon-sinek' ? [amendment] : [],
    }),
  );
  const outcome = assembleDeliberationOutcome({
    spec, brief: briefFull, cards: [...round1, ...round2, ...round3], draft_composition: composition2,
  });
  assert.equal(outcome.status, 'complete');
  if (outcome.status !== 'complete') return;
  assert.equal(outcome.ratification_status, 'material_change_unratified');
  assert.equal(outcome.verdict.ratification_status, 'material_change_unratified');
});

test('T048 (completion half): unresolved disagreement completes honestly, with the tradeoff preserved and no invented round', () => {
  const panel: SeatId[] = ['simon-sinek', 'td-jakes'];
  const brief = briefFor(panel);
  const spec = specFor('selected', panel, brief);
  // A durable split: the two seats score opposite options highly and
  // neither record can change the other's mind. The deliberation
  // completes as the analysis labels it; nothing iterates further.
  const round1 = [
    advisorCard('simon-sinek', 1, { scores: { A: 9, B: 3, C: 5 }, preferred: 'A' }),
    advisorCard('td-jakes', 1, { scores: { A: 3, B: 9, C: 5 }, preferred: 'B' }),
  ];
  const round2 = [
    advisorCard('simon-sinek', 2, { scores: { A: 9, B: 3, C: 5 }, preferred: 'A' }),
    advisorCard('td-jakes', 2, { scores: { A: 3, B: 9, C: 5 }, preferred: 'B' }),
  ];
  const composition = composeDraftResolution({ brief, active_seat_ids: panel, round2Cards: round2 });
  const round3 = [
    ratificationCard('simon-sinek', composition.draft.semantic_sha256, { scores: { A: 9, B: 3, C: 5 }, preferred: 'A', resolution_stance: 'oppose' }),
    ratificationCard('td-jakes', composition.draft.semantic_sha256, { scores: { A: 3, B: 9, C: 5 }, preferred: 'B' }),
  ];
  const outcome = assembleDeliberationOutcome({
    spec, brief, cards: [...round1, ...round2, ...round3], draft_composition: composition,
  });
  assert.equal(outcome.status, 'complete');
  if (outcome.status !== 'complete') return;
  // The dissent is preserved verbatim in the verdict, not smoothed.
  assert.equal(outcome.verdict.strongest_dissent, 'Seat simon-sinek strongest objection.');
  assert.ok(outcome.resolution_support);
  assert.equal(outcome.resolution_support.opposition, GOLDEN_WEIGHTS[SEAT_IDS.indexOf('simon-sinek')]);
  // The analysis itself is the only scoring path used.
  const direct = analyzeDecision({
    options: brief.options,
    active_seat_ids: panel,
    weights: brief.relevance_weights,
    scores: round3.flatMap((c) => c.option_scores.map((s) => ({ option_id: s.option_id, seat_id: c.seat_id, score: s.score }))),
    critical_domains: brief.critical_domains,
    critical_domain_applicability: deriveCriticalDomainApplicability(brief),
  });
  assert.equal(outcome.verdict.label, direct.label);
  assert.equal(outcome.verdict.recommended_option_id, direct.recommended_option_id);
});
