/**
 * CWE-026 verdict services: assembly, exact-hash publication
 * validation, resolution support, client response separation, and
 * material amendments (directive Sections 11.5, 11.6, 12.8, 14.6).
 *
 * Fixture identity: cwe-026-synthetic-fixtures/v1. Contract tests over
 * synthetic cards; verification_level: contract_tested (Section 34.3).
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  canonicalHash,
  GOLDEN_EXPECTED,
  GOLDEN_WEIGHTS,
  SEAT_IDS,
  type AdvisorCard,
  type CouncilCard,
  type DecisionBrief,
  type DraftResolution,
  type HostStamp,
  type RatificationCard,
  type ScoredVerdict,
  type SeatId,
} from '../src/contracts/index.js';
import { buildSampleSession } from '../src/cli/fixture-transport.js';
import { CouncilEngine } from '../src/cli/engine.js';
import {
  aggregateEvidenceStrength,
  assessAmendment,
  buildScoredVerdict,
  computeResolutionSupport,
  draftResolutionSemanticHash,
  findMisboundRatificationCards,
  recordClientVerdictResponse,
  summarizeMainReasons,
  summarizeStrongestDissent,
  validateVerdictForPublication,
  verdictContentHash,
} from '../src/protocol/verdict.js';
import { analyzeDecision } from '../src/scoring/index.js';
import { grantHost, tempDataDir } from './helpers.js';

const HASH_B = 'b'.repeat(64);

const HOST_STAMP: HostStamp = {
  scope: {
    tenant_id: 'tenant-fixture',
    company_id: 'company-fixture',
    installation_id: 'install-fixture',
    owner_subject: null,
  },
  operation_id: 'op-fixture-1',
  route_id: 'route-fixture-1',
  session_id: 'sess-fixture-1',
  stamped_at: '2026-10-14T02:05:00Z',
  source_status: 'verified',
};

const GOLDEN_WEIGHT_MAP: Partial<Record<SeatId, number>> = Object.fromEntries(
  SEAT_IDS.map((seatId, i) => [seatId, GOLDEN_WEIGHTS[i]]),
);

function makeBrief(overrides: Partial<DecisionBrief> = {}): DecisionBrief {
  return {
    schema_version: 'wise-elders.brief/v1',
    brief_id: 'brief-fixture-1',
    session_id: 'sess-fixture-1',
    revision: 1,
    question: 'Should we pilot the revised offer before a broad launch?',
    facts: [
      { id: 'fact-1', statement: 'Current offer converts at a measured baseline.', evidence_ids: ['ev-1'] },
    ],
    assumptions: [],
    unknowns: [],
    constraints: [],
    options: [
      { id: 'A', label: 'Keep the current offer', kind: 'status_quo' },
      { id: 'B', label: 'Pilot the revised offer', kind: 'bounded_test' },
      { id: 'C', label: 'Launch the revised offer broadly', kind: 'change' },
    ],
    relevance_weights: { ...GOLDEN_WEIGHT_MAP },
    critical_domains: [],
    evidence_manifest: [
      { evidence_id: 'ev-1', sha256: HASH_B, source_kind: 'client_document', locator: 'doc:baseline-metrics' },
    ],
    private_preference_ref: null,
    created_at: '2026-10-14T02:00:00Z',
    display_timezone: 'America/New_York',
    ...overrides,
  } as DecisionBrief;
}

const GOLDEN_TABLE: Record<string, Record<SeatId, number>> = {
  A: { 'simon-sinek': 6, 'td-jakes': 5, 'oprah-winfrey': 6, 'tiffany-aliche': 8, 'russell-brunson': 5, 'michelle-obama': 6, 'brene-brown': 6, 'dennis-kimbro': 6, 'les-brown': 6 },
  B: { 'simon-sinek': 8, 'td-jakes': 8, 'oprah-winfrey': 7, 'tiffany-aliche': 6, 'russell-brunson': 9, 'michelle-obama': 8, 'brene-brown': 7, 'dennis-kimbro': 8, 'les-brown': 8 },
  C: { 'simon-sinek': 7, 'td-jakes': 9, 'oprah-winfrey': 7, 'tiffany-aliche': 3, 'russell-brunson': 8, 'michelle-obama': 6, 'brene-brown': 5, 'dennis-kimbro': 7, 'les-brown': 8 },
};

function advisorCard(
  seatId: SeatId,
  table: Record<string, Record<SeatId, number | null>>,
  overrides: Partial<AdvisorCard> = {},
): AdvisorCard {
  return {
    schema_version: 'wise-elders.card/v1',
    card_kind: 'advisor',
    session_id: 'sess-fixture-1',
    brief_revision: 1,
    round: 2,
    seat_id: seatId,
    input_manifest_sha256: HASH_B,
    pack_version: 'pack-fixture-1.0.0',
    stance: 'conditional',
    preferred_option_id: 'B',
    option_scores: ['A', 'B', 'C'].map((optionId) => ({
      option_id: optionId,
      score: table[optionId][seatId],
      rationale: `Fixture rationale for ${optionId} from ${seatId}.`,
      evidence_ids: ['ev-1'],
    })),
    framework_applications: [],
    decisive_arguments: [`Decisive argument from ${seatId}.`],
    strongest_objection: `Strongest objection from ${seatId}.`,
    conditions: [],
    critical_unknowns: [],
    change_my_mind: 'Measured evidence to the contrary.',
    challenges_answered: [],
    quotes: [],
    evidence_strength: 'medium',
    minority_position: null,
    host: HOST_STAMP,
    ...overrides,
  } as AdvisorCard;
}

function goldenCards(): AdvisorCard[] {
  return SEAT_IDS.map((seatId) => advisorCard(seatId, GOLDEN_TABLE));
}

function buildGoldenVerdict(cards: AdvisorCard[], brief: DecisionBrief): ScoredVerdict {
  const analysis = analyzeDecision({
    options: brief.options,
    active_seat_ids: SEAT_IDS,
    weights: brief.relevance_weights,
    scores: cards.flatMap((card) =>
      card.option_scores.map((s) => ({
        option_id: s.option_id,
        seat_id: card.seat_id,
        score: s.score,
      })),
    ),
    critical_domains: brief.critical_domains,
  });
  return buildScoredVerdict({
    analysis,
    session_id: brief.session_id,
    verdict_revision: 1,
    brief_sha256: canonicalHash(brief),
    weights: brief.relevance_weights,
    evidence_strength: aggregateEvidenceStrength(cards),
    hard_constraint_findings: [],
    main_reasons: summarizeMainReasons(cards, analysis.recommended_option_id),
    strongest_dissent: summarizeStrongestDissent(cards, analysis.recommended_option_id),
    accepted_amendments: [],
    rejected_amendments: [],
    critical_unknowns: [],
    prerequisites: analysis.prerequisites_needed,
    action_proposals: [],
    cheapest_informative_test: null,
    stop_criteria: [],
    review_criteria: [],
    resolution_support: null,
    ratification_status: 'not_required',
  });
}

test('golden verdict assembles and passes exact-hash publication validation', () => {
  const brief = makeBrief();
  const cards = goldenCards();
  const verdict = buildGoldenVerdict(cards, brief);
  assert.equal(verdict.label, 'GO');
  assert.equal(verdict.recommended_option_id, 'B');
  assert.equal(verdict.content_sha256, verdictContentHash(verdict));
  const b = verdict.option_scores.find((o) => o.option_id === 'B');
  assert.ok(b);
  assert.equal(b.weighted_sum, GOLDEN_EXPECTED.B.weighted_sum);
  assert.equal(b.display_score, GOLDEN_EXPECTED.B.display_score);

  const validation = validateVerdictForPublication({
    verdict,
    brief,
    final_cards: cards,
    require_final_cards: true,
  });
  assert.equal(validation.publishable, true, JSON.stringify(validation.checks));
  for (const check of validation.checks) {
    assert.notEqual(check.status, 'fail', `${check.name}: ${check.detail}`);
  }
});

test('a tampered revision fails the exact-hash check even with valid schema', () => {
  const brief = makeBrief();
  const cards = goldenCards();
  const verdict = buildGoldenVerdict(cards, brief);
  const tampered = {
    ...verdict,
    option_scores: verdict.option_scores.map((o) =>
      o.option_id === 'B' ? { ...o, display_score: 9.9 } : o,
    ),
  } as ScoredVerdict;
  const validation = validateVerdictForPublication({
    verdict: tampered,
    brief,
    final_cards: cards,
    require_final_cards: true,
  });
  assert.equal(validation.publishable, false);
  const hashCheck = validation.checks.find((c) => c.name === 'content_hash_exact');
  assert.equal(hashCheck?.status, 'fail');
});

test('a rehashed tamper still fails arithmetic recomputation from the final cards', () => {
  const brief = makeBrief();
  const cards = goldenCards();
  const verdict = buildGoldenVerdict(cards, brief);
  const tamperedBase = {
    ...verdict,
    option_scores: verdict.option_scores.map((o) =>
      o.option_id === 'B' ? { ...o, weighted_sum: 170 } : o,
    ),
  };
  const { content_sha256: _drop, ...rest } = tamperedBase;
  const tampered = {
    ...rest,
    content_sha256: canonicalHash(rest),
  } as unknown as ScoredVerdict;
  const validation = validateVerdictForPublication({
    verdict: tampered,
    brief,
    final_cards: cards,
    require_final_cards: true,
  });
  assert.equal(validation.publishable, false);
  const hashCheck = validation.checks.find((c) => c.name === 'content_hash_exact');
  assert.equal(hashCheck?.status, 'pass'); // the hash was honestly recomputed
  const recompute = validation.checks.find((c) => c.name === 'scores_recomputed');
  assert.equal(recompute?.status, 'fail'); // and it still does not publish
});

test('an unverified final attribution blocks release even when scoring is exact (T047)', () => {
  const brief = makeBrief();
  const cards = goldenCards();
  cards[0] = advisorCard('simon-sinek', GOLDEN_TABLE, {
    quotes: [
      {
        quote_id: 'q-1',
        text: 'A quotation that never passed verification.',
        evidence_id: 'ev-1',
        locator: 'doc:baseline-metrics',
        verification_status: 'candidate',
      },
    ],
  });
  const verdict = buildGoldenVerdict(cards, brief);
  const validation = validateVerdictForPublication({
    verdict,
    brief,
    final_cards: cards,
    require_final_cards: true,
  });
  assert.equal(validation.publishable, false);
  const attribution = validation.checks.find((c) => c.name === 'attribution_verified');
  assert.equal(attribution?.status, 'fail');
  const recompute = validation.checks.find((c) => c.name === 'scores_recomputed');
  assert.equal(recompute?.status, 'pass'); // earlier checks passing does not rescue it
});

test('resolution support counts bind to the exact draft hash (11.6, 12.8)', () => {
  const brief = makeBrief();
  const draftBase = {
    schema_version: 'wise-elders.draft-resolution/v1' as const,
    session_id: 'sess-fixture-1',
    brief_revision: 1,
    revision: 1,
    recommended_option_id: 'B',
    actions: ['Run the bounded pilot.'],
    prerequisites: [],
    limits: ['Pilot spend stays within the approved budget.'],
  };
  const semanticHash = draftResolutionSemanticHash({
    ...draftBase,
    semantic_sha256: '0'.repeat(64),
  } as DraftResolution);
  const draft: DraftResolution = { ...draftBase, semantic_sha256: semanticHash };

  const stances: Record<SeatId, 'support' | 'conditional_support' | 'oppose' | 'abstain'> = {
    'simon-sinek': 'support',
    'td-jakes': 'support',
    'oprah-winfrey': 'conditional_support',
    'tiffany-aliche': 'support',
    'russell-brunson': 'support',
    'michelle-obama': 'conditional_support',
    'brene-brown': 'support',
    'dennis-kimbro': 'oppose',
    'les-brown': 'abstain',
  };
  const ratificationCards: RatificationCard[] = SEAT_IDS.map((seatId) => ({
    schema_version: 'wise-elders.card/v1',
    card_kind: 'ratification',
    session_id: 'sess-fixture-1',
    brief_revision: 1,
    round: 3,
    seat_id: seatId,
    input_manifest_sha256: HASH_B,
    pack_version: 'pack-fixture-1.0.0',
    draft_resolution_sha256: semanticHash,
    resolution_stance: stances[seatId],
    stance: 'support',
    preferred_option_id: 'B',
    option_scores: ['A', 'B', 'C'].map((optionId) => ({
      option_id: optionId,
      score: GOLDEN_TABLE[optionId][seatId],
      rationale: 'Fixture ratification rationale.',
      evidence_ids: ['ev-1'],
    })),
    amendments: [],
    accepted_condition_ids: [],
    unresolved_objections: [],
    evidence_strength: 'medium',
    host: HOST_STAMP,
  }));

  const support = computeResolutionSupport(
    ratificationCards,
    GOLDEN_WEIGHT_MAP,
    semanticHash,
  );
  // Weighted counts by hand: support 2+3+3+3+3 = 14 (Sinek, Jakes,
  // Tiffany, Russell, Brené); conditional 2+2 = 4 (Oprah, Michelle);
  // opposition 2 (Kimbro); abstention 2 (Les Brown).
  assert.deepEqual(support, {
    resolution_sha256: semanticHash,
    support: 14,
    conditional_support: 4,
    opposition: 2,
    abstention: 2,
  });
  assert.deepEqual(findMisboundRatificationCards(ratificationCards, semanticHash), []);

  const cards: AdvisorCard[] = goldenCards();
  const analysis = analyzeDecision({
    options: brief.options,
    active_seat_ids: SEAT_IDS,
    weights: brief.relevance_weights,
    scores: ratificationCards.flatMap((card) =>
      card.option_scores.map((s) => ({
        option_id: s.option_id,
        seat_id: card.seat_id,
        score: s.score,
      })),
    ),
  });
  const verdict = buildScoredVerdict({
    analysis,
    session_id: brief.session_id,
    verdict_revision: 1,
    brief_sha256: canonicalHash(brief),
    weights: brief.relevance_weights,
    evidence_strength: 'medium',
    hard_constraint_findings: [],
    main_reasons: summarizeMainReasons(cards, 'B'),
    strongest_dissent: summarizeStrongestDissent(cards, 'B'),
    accepted_amendments: [],
    rejected_amendments: [],
    critical_unknowns: [],
    prerequisites: [],
    action_proposals: [],
    cheapest_informative_test: null,
    stop_criteria: [],
    review_criteria: [],
    resolution_support: support,
    ratification_status: 'ratified',
  });
  const allCards: CouncilCard[] = [...cards, ...ratificationCards];
  const validation = validateVerdictForPublication({
    verdict,
    brief,
    final_cards: allCards,
    draft_resolution: draft,
    require_final_cards: true,
  });
  assert.equal(validation.publishable, true, JSON.stringify(validation.checks));
  const binding = validation.checks.find((c) => c.name === 'ratification_bound');
  assert.equal(binding?.status, 'pass');

  // One card re-bound to a different draft hash breaks publication.
  const misbound = ratificationCards.map((card, i) =>
    i === 0 ? { ...card, draft_resolution_sha256: 'f'.repeat(64) } : card,
  );
  assert.deepEqual(findMisboundRatificationCards(misbound, semanticHash), ['simon-sinek']);
  const validation2 = validateVerdictForPublication({
    verdict,
    brief,
    final_cards: [...cards, ...misbound],
    draft_resolution: draft,
    require_final_cards: true,
  });
  assert.equal(validation2.publishable, false);
  assert.equal(
    validation2.checks.find((c) => c.name === 'ratification_bound')?.status,
    'fail',
  );
});

test('material amendments never inherit support; editorial ones keep the hash (12.8)', () => {
  const budgetIncrease = assessAmendment({
    target_path: 'limits',
    claimed_materiality: 'nonmaterial',
  });
  assert.equal(budgetIncrease.materiality, 'material'); // a late budget increase
  assert.equal(budgetIncrease.support_transfers, false);
  assert.equal(budgetIncrease.may_apply_editorially, false);
  assert.equal(
    budgetIncrease.ratification_status_if_published,
    'material_change_unratified',
  );
  assert.equal(budgetIncrease.creates_fourth_round, false);
  assert.equal(budgetIncrease.dispatch_allowed, false);

  const ownerChange = assessAmendment({
    target_path: 'assigned_agent_id',
    claimed_materiality: 'nonmaterial',
  });
  assert.equal(ownerChange.materiality, 'material'); // changed execution owner

  const weakenedPrerequisite = assessAmendment({
    target_path: 'prerequisites',
    claimed_materiality: 'nonmaterial',
  });
  assert.equal(weakenedPrerequisite.materiality, 'material');

  const typo = assessAmendment({
    target_path: 'citation.format',
    claimed_materiality: 'nonmaterial',
  });
  assert.equal(typo.materiality, 'nonmaterial'); // harmless typo class
  assert.equal(typo.support_transfers, true);
  assert.equal(typo.may_apply_editorially, true);

  const claimedMaterial = assessAmendment({
    target_path: 'label',
    claimed_materiality: 'material',
  });
  assert.equal(claimedMaterial.materiality, 'material'); // claim is honored
});

test('client accept, reject, and defer are separate records that never alter the verdict', () => {
  const brief = makeBrief();
  const verdict = buildGoldenVerdict(goldenCards(), brief);
  const before = canonicalHash(verdict as unknown as Record<string, unknown>);
  for (const response of ['accepted', 'rejected', 'deferred'] as const) {
    const record = recordClientVerdictResponse(
      verdict,
      response,
      'client-owner-1',
      '2026-10-14T03:00:00Z',
    );
    assert.equal(record.response, response);
    assert.equal(record.alters_verdict, false);
    assert.equal(record.verdict_content_sha256, verdict.content_sha256);
    assert.equal(record.verdict_revision, verdict.verdict_revision);
  }
  const after = canonicalHash(verdict as unknown as Record<string, unknown>);
  assert.equal(after, before); // the historical recommendation is untouched
});

test('agreement: CWE-026 analysis reproduces the CWE-004 core engine verdict on the golden sample', async () => {
  const sample = buildSampleSession();
  const host = grantHost(tempDataDir('cwe026-agreement'), sample.spec, sample.scope);
  const engine = new CouncilEngine(host);
  await engine.createSession({ ...sample, sample: true });
  await engine.startSession(sample.spec.session_id, 'test-grant');
  const verdict = (await engine.getVerdict(sample.spec.session_id)) as ScoredVerdict | null;
  assert.ok(verdict && verdict.result_kind === 'scored');
  // The core's stored summaries are the golden numbers.
  for (const optionId of ['A', 'B', 'C'] as const) {
    const summary = verdict.option_scores.find((o) => o.option_id === optionId);
    const expected = GOLDEN_EXPECTED[optionId];
    assert.ok(summary);
    assert.equal(summary.weighted_sum, expected.weighted_sum);
    assert.equal(summary.denominator, expected.denominator);
    assert.equal(summary.score, expected.score);
    assert.equal(summary.display_score, expected.display_score);
    assert.equal(summary.coverage, expected.coverage);
    assert.equal(summary.spread, expected.spread);
  }
  // Feed the engine's own final (ratification) cards into CWE-026.
  const cards = await host.store.listCards(sample.spec.session_id);
  const ratification = cards.filter(
    (c): c is RatificationCard => c.card_kind === 'ratification',
  );
  assert.equal(ratification.length, 9);
  const analysis = analyzeDecision({
    options: sample.brief.options,
    active_seat_ids: SEAT_IDS,
    weights: sample.brief.relevance_weights,
    scores: ratification.flatMap((card) =>
      card.option_scores.map((s) => ({
        option_id: s.option_id,
        seat_id: card.seat_id,
        score: s.score,
      })),
    ),
    critical_domains: sample.brief.critical_domains,
  });
  for (const mine of analysis.options) {
    const core = verdict.option_scores.find((o) => o.option_id === mine.option_id);
    assert.ok(core);
    assert.deepEqual(
      {
        weighted_sum: mine.weighted_sum,
        denominator: mine.denominator,
        score: mine.score,
        display_score: mine.display_score,
        coverage: mine.coverage,
        spread: mine.spread,
      },
      {
        weighted_sum: core.weighted_sum,
        denominator: core.denominator,
        score: core.score,
        display_score: core.display_score,
        coverage: core.coverage,
        spread: core.spread,
      },
    );
  }
  // The sample brief carries an unresolved financial domain, so both
  // the core and CWE-026 withhold an unconditional GO: WAIT, recommend B.
  assert.equal(verdict.label, 'WAIT');
  assert.equal(analysis.label, verdict.label);
  assert.equal(analysis.recommended_option_id, verdict.recommended_option_id);
});
