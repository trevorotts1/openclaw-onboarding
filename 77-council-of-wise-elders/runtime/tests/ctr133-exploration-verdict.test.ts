// CTR-133 runtime regression source. NOT EXECUTED by the implementer.
//
// Run by Trevor (or an independent reviewer) with the runtime's own dev
// tooling, for example:
//   npx tsx --test tests/ctr133-exploration-verdict.test.ts
//
// Cases:
//   1. a placeholder-only option is ineligible and can never be recommended;
//   2. a legacy scored GO_WITH_CONDITIONS verdict on the placeholder is
//      blocked at the publication boundary;
//   3. genuine indecision (unscored placeholder, null recommendation,
//      INSUFFICIENT_EVIDENCE) stays a distinct, publishable state.

import assert from 'node:assert/strict';
import test from 'node:test';

import { SEAT_IDS } from '../src/contracts/index.js';
import type {
  DecisionBrief,
  ScoredVerdict,
} from '../src/contracts/index.js';
import { analyzeDecision } from '../src/scoring/decision.js';
import {
  assessExplorationExport,
  validateVerdictForPublication,
} from '../src/protocol/verdict.js';
import {
  EXPLORATION_OPTION_ID,
  EXPLORATION_OPTION_LABEL,
} from '../src/brief/exploration.js';

function placeholderBrief(): DecisionBrief {
  return {
    schema_version: 'wise-elders.brief/v1',
    brief_id: 'brief-ctr133',
    session_id: 'sess-ctr133',
    revision: 1,
    question: 'WHAT THE BEST WAY TO GROM MY INSTAGRAM FOLLOWING',
    facts: [],
    assumptions: [],
    unknowns: [],
    constraints: [],
    options: [
      { id: EXPLORATION_OPTION_ID, label: EXPLORATION_OPTION_LABEL, kind: 'other' },
    ],
    relevance_weights: Object.fromEntries(SEAT_IDS.map((seat) => [seat, 1])),
    critical_domains: [],
    evidence_manifest: [],
    private_preference_ref: null,
    created_at: '2026-10-30T10:58:12.852Z',
    display_timezone: 'America/New_York',
  } as unknown as DecisionBrief;
}

function scoredPlaceholderVerdict(): ScoredVerdict {
  return {
    schema_version: 'wise-elders.verdict/v1',
    result_kind: 'scored',
    session_id: 'sess-ctr133',
    verdict_revision: 1,
    recommended_option_id: EXPLORATION_OPTION_ID,
    label: 'GO_WITH_CONDITIONS',
    option_scores: [
      {
        option_id: EXPLORATION_OPTION_ID,
        score: 7.388888888888889,
        display_score: 7.4,
        weighted_sum: 66.5,
        denominator: 9,
        coverage: 1,
        spread: 1,
      },
    ],
    active_weights: Object.fromEntries(SEAT_IDS.map((seat) => [seat, 1])),
    evidence_strength: 'medium',
    hard_constraint_findings: [],
    main_reasons: [],
    strongest_dissent: null,
    accepted_amendments: [],
    rejected_amendments: [],
    critical_unknowns: [],
    prerequisites: [],
    action_proposals: [],
    cheapest_informative_test: null,
    stop_criteria: [],
    review_criteria: [],
    resolution_support: null,
    validation_status: 'valid',
    ratification_status: 'not_required',
    brief_sha256: '0'.repeat(64),
    content_sha256: '0'.repeat(64),
  } as unknown as ScoredVerdict;
}

test('placeholder-only option is ineligible and never recommended', () => {
  const analysis = analyzeDecision({
    options: [
      { id: EXPLORATION_OPTION_ID, label: EXPLORATION_OPTION_LABEL, kind: 'other' },
    ],
    active_seat_ids: SEAT_IDS,
    weights: Object.fromEntries(SEAT_IDS.map((seat) => [seat, 1])),
    scores: SEAT_IDS.map((seat) => ({
      option_id: EXPLORATION_OPTION_ID,
      seat_id: seat,
      score: 7.388888888888889,
    })),
    missing_seat_ids: [],
  });

  assert.equal(analysis.options[0].eligible, false);
  assert.match(analysis.options[0].eligibility_reasons.join(' '), /unresolved exploration candidate/);
  assert.equal(analysis.leading_option_id, null);
  assert.equal(analysis.recommended_option_id, null);
  assert.equal(analysis.label, 'INSUFFICIENT_EVIDENCE');
});

test('legacy scored GO_WITH_CONDITIONS placeholder fails publication', () => {
  const verdict = scoredPlaceholderVerdict();
  const brief = placeholderBrief();

  const problems = assessExplorationExport(verdict, brief);
  assert.equal(problems.length >= 2, true);
  assert.match(problems.join(' '), /received score/);
  assert.match(problems.join(' '), /no recommendation may be exported/);

  const publication = validateVerdictForPublication({ verdict, brief });
  assert.equal(publication.publishable, false);
  const gate = publication.checks.find((check) => check.name === 'exploration_not_scored');
  assert.equal(gate?.status, 'fail');
  assert.match(gate?.detail ?? '', /unresolved exploration candidate/);
});

test('genuine indecision stays distinct and is not blocked by the placeholder gate', () => {
  const verdict = {
    ...scoredPlaceholderVerdict(),
    recommended_option_id: null,
    label: 'INSUFFICIENT_EVIDENCE',
    option_scores: [
      {
        option_id: EXPLORATION_OPTION_ID,
        score: null,
        display_score: null,
        weighted_sum: 0,
        denominator: 0,
        coverage: 0,
        spread: null,
      },
    ],
  } as unknown as ScoredVerdict;
  const brief = placeholderBrief();

  assert.deepEqual(assessExplorationExport(verdict, brief), []);
  const publication = validateVerdictForPublication({ verdict, brief });
  const gate = publication.checks.find((check) => check.name === 'exploration_not_scored');
  assert.equal(gate?.status, 'pass');
});
