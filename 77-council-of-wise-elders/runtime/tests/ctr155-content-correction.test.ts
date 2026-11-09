/**
 * CTR-155 content-correction regression. INTENTIONALLY UNEXECUTED in this
 * lane: the single integrator / Trevor owns the run.
 *
 * Runner (when the integrator runs it):
 *   node --import tsx --test tests/ctr155-content-correction.test.ts
 *
 * It pins the twelve CTR-151 review findings that belong to this lane's three
 * source files. Every fixture string below is copied byte-for-byte from the
 * saved session's own records (council.db, session
 * sess-77660e75-314a-4d97-b64e-d53e21d2a047), not invented:
 * - the six brief unknowns in council_brief_revisions.revision = 1;
 * - the ten verdict critical_unknowns (five paraphrase facts + five
 *   "Unknown: ..." restatements);
 * - the two distinct advisor thresholds (T. D. Jakes and Tiffany Aliche).
 */

import assert from 'node:assert/strict';
import test from 'node:test';

import { SEAT_IDS, type CouncilCard } from '../src/contracts/index.js';
import {
  buildReportModel,
  matchCapabilitiesToPlan,
  validateCapabilitySnapshot,
  type InstallationCapabilitySnapshot,
} from '../src/reports/index.js';
import { cardContractLines } from '../src/cli/card-contract.js';

const SESSION_ID = 'sess-77660e75-314a-4d97-b64e-d53e21d2a047';
const HASH = 'a'.repeat(64);

/** council_brief_revisions.revision = 1, json_extract(brief_json,'$.unknowns'). */
const BRIEF_UNKNOWNS = [
  'The current subscriber count, view counts and watch-time hours are not stated.',
  'The current upload cadence, and whether the channel is dormant, are not stated.',
  'Whether the client appears on camera is not stated.',
  'The weekly production hours available for scripting, shooting and editing are not stated.',
  'The target topic and keyword set, and whether this audience searches YouTube for them, are not stated.',
  'Any budget for YouTube ads is not stated.',
];

/** council_verdicts.verdict_json, json_extract(...,'$.critical_unknowns'). */
const VERDICT_UNKNOWNS = [
  'Current subscriber base, views, and watch time are unknown, so compounding potential cannot be judged.',
  'Current upload cadence and whether the channel is dormant are unknown.',
  'Weekly production hours for scripting, shooting, and editing are unknown.',
  'Target topics and whether the audience searches YouTube for them are unknown.',
  'On-camera presence and ad budget are unknown.',
  'Unknown: weekly production hours for scripting, shooting, and editing.',
  'Unknown: current upload cadence and whether the channel is dormant.',
  'Unknown: whether the client appears on camera.',
  'Unknown: target topic and keyword set and whether this audience searches YouTube for them.',
  'Unknown: any budget for YouTube ads.',
];

const THRESHOLD_TWO_EPISODES =
  'Owner reviews two consecutive weekly repurposed episodes before increasing volume.';
const THRESHOLD_FOUR_EPISODES =
  'No YouTube ad spend until at least four repurposed episodes show acceptable retention and click-through.';

function advisorCard(
  seatId: (typeof SEAT_IDS)[number],
  conditions: Array<Record<string, unknown>> = [],
): CouncilCard {
  return {
    card_kind: 'advisor',
    seat_id: seatId,
    round: 2,
    session_id: SESSION_ID,
    pack_version: 'pack-1',
    stance: 'conditional',
    preferred_option_id: 'opt-a',
    option_scores: [
      { option_id: 'opt-a', score: 8, rationale: 'fixture', evidence_ids: [] },
      { option_id: 'opt-b', score: 5, rationale: 'fixture', evidence_ids: [] },
    ],
    decisive_arguments: [`${seatId} argument`],
    strongest_objection: `${seatId} objection`,
    change_my_mind: `${seatId}: measured evidence to the contrary.`,
    conditions,
    critical_unknowns: [],
    minority_position: null,
    evidence_strength: 'low',
    input_manifest_sha256: HASH,
    brief_revision: 1,
    schema_version: 'wise-elders.card/v1',
    framework_applications: [],
    challenges_answered: [],
    quotes: [],
  } as unknown as CouncilCard;
}

function condition(
  id: string,
  blocking: boolean,
  description: string,
  kind = 'prerequisite',
): Record<string, unknown> {
  return {
    id,
    description,
    kind,
    blocking,
    verification_method: 'owner review',
    required_evidence: [],
    responsible_role: 'owner',
    due_at: null,
    status: 'open',
    depends_on: [],
  };
}

const BRIEF = {
  schema_version: 'wise-elders.brief/v1',
  brief_id: 'brief-ctr155',
  session_id: SESSION_ID,
  revision: 1,
  question: 'What is the best way to grow the BlackCEO YouTube channel?',
  facts: [],
  assumptions: [],
  unknowns: BRIEF_UNKNOWNS.map((statement, index) => ({
    id: `u-${index + 1}`,
    statement,
    evidence_ids: [],
  })),
  constraints: [],
  options: [
    { id: 'opt-a', label: 'Repurpose the archive', kind: 'bounded_test' },
    { id: 'opt-b', label: 'Run search tutorials', kind: 'change' },
  ],
  relevance_weights: Object.fromEntries(SEAT_IDS.map((seat) => [seat, 1])),
  critical_domains: [],
  evidence_manifest: [],
  private_preference_ref: null,
  created_at: '2026-10-30T10:00:00Z',
  display_timezone: 'America/New_York',
} as never;

interface VerdictOptions {
  label?: string;
  ratification_status?: string;
  hard_constraint_findings?: Array<Record<string, unknown>>;
  action_proposals?: Array<Record<string, unknown>>;
}

function verdict(options: VerdictOptions = {}): unknown {
  return {
    schema_version: 'wise-elders.verdict/v1',
    result_kind: 'scored',
    session_id: SESSION_ID,
    verdict_revision: 1,
    recommended_option_id: 'opt-a',
    label: options.label ?? 'WAIT',
    option_scores: [
      { option_id: 'opt-a', score: 8.4, display_score: 8.4, weighted_sum: 151, denominator: 18, coverage: 1, spread: 1 },
      { option_id: 'opt-b', score: 7.1, display_score: 7.1, weighted_sum: 128, denominator: 18, coverage: 1, spread: 4 },
    ],
    active_weights: Object.fromEntries(SEAT_IDS.map((seat) => [seat, 1])),
    evidence_strength: 'low',
    hard_constraint_findings: options.hard_constraint_findings ?? [],
    main_reasons: ['Repurposing uses owned assets.'],
    strongest_dissent: 'The archive may be stale.',
    accepted_amendments: [],
    rejected_amendments: [],
    critical_unknowns: VERDICT_UNKNOWNS,
    prerequisites: [],
    action_proposals: options.action_proposals ?? [
      {
        action_id: 'act-1',
        session_id: SESSION_ID,
        verdict_revision: 1,
        title: 'Publish one weekly episode',
        description: 'Publish one repurposed episode each week.',
        rationale: 'Proposed in the council draft resolution.',
        source_condition_ids: [],
        department_id: null,
        assigned_agent_id: null,
        sop_id: null,
        persona_id: null,
        acceptance_criteria: [],
        budget_limit: null,
        due_at: null,
        depends_on_action_ids: [],
        risk_class: 'medium',
        execution_authorization_required: true,
      },
    ],
    cheapest_informative_test: '',
    stop_criteria: [],
    review_criteria: [],
    resolution_support: null,
    validation_status: 'valid',
    ratification_status: options.ratification_status ?? 'not_required',
    brief_sha256: HASH,
    content_sha256: 'b'.repeat(64),
  };
}

function conditionsBySeat(): Partial<Record<(typeof SEAT_IDS)[number], Array<Record<string, unknown>>>> {
  return {
    'td-jakes': [condition('cond-jakes', true, THRESHOLD_TWO_EPISODES)],
    'tiffany-aliche': [condition('cond-tiffany', false, THRESHOLD_FOUR_EPISODES, 'safeguard')],
  };
}

function model(
  verdictOptions: VerdictOptions = {},
  conditions = conditionsBySeat(),
): Record<string, unknown> {
  return buildReportModel({
    verdict: verdict(verdictOptions) as never,
    brief: BRIEF,
    final_cards: SEAT_IDS.map((seat) => advisorCard(seat, conditions[seat] ?? [])),
    context: {
      report_date: '2026-10-30',
      session_mode: 'light',
      route_display: 'route-1',
      seat_qualifications: {},
      installation_id: 'install-ctr155',
      capability_snapshot: null,
    },
    redaction: null,
  }) as Record<string, unknown>;
}

// 1-2: canonical Information needed from the exact saved strings.
test('Information needed is the six brief unknowns, verdict restatements retained separately', () => {
  const built = model();
  const summary = built.summary as Record<string, unknown>;
  assert.deepEqual(summary.information_needed, BRIEF_UNKNOWNS);
  assert.equal(summary.information_needed_count, 6);
  assert.equal(summary.information_needed_shown, 6);
  assert.equal(summary.information_needed_source, 'brief');
  assert.deepEqual(summary.verdict_only_additions, []);
  assert.match(String(summary.information_needed_note), /brief recorded 6 unknown/);
  assert.match(String(summary.information_needed_note), /restated them 10 times/);
  const council = summary.council_unknowns as string[];
  assert.equal(summary.council_unknowns_count, 10);
  assert.equal(summary.council_unknowns_shown, council.length);
  assert.ok(council.length < 10, 'the "Unknown:" restatements collapsed');
  assert.ok(
    council.some((line) => line.startsWith('Unknown:') === false),
    'the un-framed council facts are retained',
  );
});

test('the question block reports totals versus shown and never merges the two thresholds', () => {
  const built = model();
  const context = built.question_and_context as Record<string, unknown>;
  const unknowns = context.unknowns as string[];
  assert.equal(context.unknowns_count, 16);
  assert.equal(context.unknowns_shown, unknowns.length);
  assert.ok(unknowns.length < 16, 'framed repeats were shown once');
  const normalized = unknowns.map((line) =>
    line.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim(),
  );
  assert.equal(new Set(normalized).size, normalized.length, 'no duplicate rows');
  assert.ok(unknowns.includes(BRIEF_UNKNOWNS[3]));
  assert.match(String(context.unknowns_note), /repeated unknown statement/);
  const readiness = (built.decision_vs_readiness as Record<string, unknown>)
    .readiness as Record<string, unknown>;
  const blockers = readiness.blockers as Array<Record<string, unknown>>;
  const safeguards = readiness.safeguards as Array<Record<string, unknown>>;
  assert.equal(blockers[0].text, THRESHOLD_TWO_EPISODES);
  assert.equal(safeguards[0].text, THRESHOLD_FOUR_EPISODES);
});

// 3-4: readiness eligibility and explicit reasons.
test('readiness is never ready for DONT_DO_IT, RESHAPE, WAIT or INSUFFICIENT_EVIDENCE', () => {
  for (const label of ['DONT_DO_IT', 'RESHAPE', 'WAIT', 'INSUFFICIENT_EVIDENCE']) {
    const built = model({ label }, {});
    const readiness = (built.decision_vs_readiness as Record<string, unknown>)
      .readiness as Record<string, unknown>;
    assert.equal(readiness.status, 'not_ready', `${label} is not ready`);
    const reasons = readiness.status_reasons as string[];
    assert.ok(
      reasons.some((line) => line.includes('never reported as ready')),
      `${label} names the verdict as the reason`,
    );
  }
});

test('only GO and GO_WITH_CONDITIONS can be ready, and only when nothing blocks', () => {
  const go = model({ label: 'GO' }, {});
  assert.equal(
    ((go.decision_vs_readiness as Record<string, unknown>).readiness as Record<string, unknown>)
      .status,
    'ready',
  );
  const conditions = model({ label: 'GO_WITH_CONDITIONS' });
  assert.equal(
    ((conditions.decision_vs_readiness as Record<string, unknown>).readiness as Record<string, unknown>)
      .status,
    'blocked',
  );
});

test('an unresolved or failed hard constraint on the recommended option blocks readiness', () => {
  for (const result of ['unknown', 'fail']) {
    const built = model({
      label: 'GO',
      hard_constraint_findings: [
        { constraint_id: 'c-advice', option_id: 'opt-a', result, checker: 'deterministic_code', evidence_ids: [] },
        { constraint_id: 'c-advice', option_id: 'opt-b', result: 'pass', checker: 'deterministic_code', evidence_ids: [] },
      ],
    }, {});
    const readiness = (built.decision_vs_readiness as Record<string, unknown>)
      .readiness as Record<string, unknown>;
    assert.equal(readiness.status, 'blocked');
    assert.equal(readiness.hard_constraint_count, 1);
    const findings = readiness.hard_constraint_findings as Array<Record<string, unknown>>;
    assert.equal(findings[0].constraint_id, 'c-advice');
    assert.ok(
      (readiness.status_reasons as string[]).some((line) => line.includes('recommended option')),
    );
  }
});

test('pending, rejected and material-change-unratified ratification block readiness', () => {
  for (const status of ['pending', 'rejected', 'material_change_unratified']) {
    const built = model({ label: 'GO', ratification_status: status }, {});
    const readiness = (built.decision_vs_readiness as Record<string, unknown>)
      .readiness as Record<string, unknown>;
    assert.equal(readiness.status, 'blocked', `${status} blocks`);
    assert.equal((readiness.ratification as Record<string, unknown>).blocks_readiness, true);
  }
  const clean = model({ label: 'GO', ratification_status: 'not_required' }, {});
  assert.equal(
    ((clean.decision_vs_readiness as Record<string, unknown>).readiness as Record<string, unknown>)
      .status,
    'ready',
  );
});

// 5: no silent 8-row cut.
test('every blocker and safeguard is listed and the counts equal the lists', () => {
  const many: Partial<Record<(typeof SEAT_IDS)[number], Array<Record<string, unknown>>>> = {};
  for (const seat of SEAT_IDS) {
    many[seat] = [
      condition(`${seat}-block-a`, true, `${seat} blocking A`),
      condition(`${seat}-block-b`, true, `${seat} blocking B`),
      condition(`${seat}-guard`, false, `${seat} safeguard`, 'safeguard'),
    ];
  }
  const built = model({ label: 'GO_WITH_CONDITIONS' }, many);
  const readiness = (built.decision_vs_readiness as Record<string, unknown>)
    .readiness as Record<string, unknown>;
  const blockers = readiness.blockers as unknown[];
  const safeguards = readiness.safeguards as unknown[];
  assert.equal(blockers.length, 18);
  assert.equal(safeguards.length, 9);
  assert.equal(readiness.blocker_count, 18);
  assert.equal(readiness.blocker_shown, 18);
  assert.equal(readiness.safeguard_count, 9);
  assert.equal(readiness.safeguard_shown, 9);
});

// 6: the plain-language rule belongs to the advisor schema only.
test('PLAIN_LANGUAGE_RULE is sent for advisor cards only', () => {
  const advisor = cardContractLines('advisor', []).join('\n');
  const ratification = cardContractLines('ratification', null).join('\n');
  const consult = cardContractLines('consult', null).join('\n');
  assert.match(advisor, /plain language/);
  assert.equal(/plain language/.test(ratification), false);
  assert.equal(/plain language/.test(consult), false);
});

// 7: word-boundary truncation with an ellipsis, no dangling function word.
test('a shortened description never ends in a half word or a dangling article', () => {
  // CTR-156: the old fixture put "and a" AFTER the 320-char cut, so the
  // trailing-function-word strip was never exercised. Put the tail right
  // before the cut: 63 "word " repeats are 315 chars, "and a" then straddles
  // the 319-char budget, so the strip must remove a real "and a".
  const long = `${'word '.repeat(63)}and a${' tail word'.repeat(12)}`;
  const snapshot = validateCapabilitySnapshot({
    schema_version: 'wise-elders.capability-snapshot/v1',
    installation_id: 'install-ctr155',
    captured_at: '2026-10-30',
    basis: 'at_export',
    items: [
      {
        capability_id: 'skill:test',
        kind: 'skill',
        name: 'test',
        description: long,
        availability: 'available_now',
        source: 'openclaw.skills',
        recorded_reference_ids: [],
      },
    ],
    limitations: [],
  });
  const description = snapshot.items[0].description as string;
  assert.ok(description.length <= 320);
  assert.ok(description.endsWith('…'));
  assert.equal(/\b(?:and|a|an|the|to|of|for|with)\s*…$/.test(description), false);
  assert.equal(/publishin|wor…$/.test(description), false);
  // The function-word tail that straddled the cut is gone, not merely hidden
  // behind the ellipsis.
  assert.equal(/(?:^|\s)(?:and|a)(?:\s|…)/.test(description), false);
  // Every kept word before the ellipsis is a whole word from the source.
  assert.ok(
    description
      .slice(0, -1)
      .trim()
      .split(/\s+/)
      .every((word) => word === 'word'),
  );
});

// 8: applies_to_all_options is set equality, not a length comparison.
test('applies_to_all_options needs every option once and no extra id', () => {
  const withConstraint = (ids: string[]) =>
    ({
      ...(BRIEF as unknown as Record<string, unknown>),
      constraints: [
        {
          id: 'con-1',
          description: 'Recorded constraint.',
          hard: true,
          applies_to_option_ids: ids,
        },
      ],
    }) as never;
  const block = (ids: string[]) =>
    (buildReportModel({
      verdict: verdict() as never,
      brief: withConstraint(ids),
      final_cards: SEAT_IDS.map((seat) => advisorCard(seat)),
      context: {
        report_date: '2026-10-30',
        session_mode: 'light',
        route_display: 'route-1',
        seat_qualifications: {},
        installation_id: 'install-ctr155',
        capability_snapshot: null,
      },
      redaction: null,
    }).question_and_context as Record<string, unknown>).constraints as Array<Record<string, unknown>>;
  assert.equal(block(['opt-a', 'opt-b'])[0].applies_to_all_options, true);
  assert.equal(block(['opt-a', 'opt-a'])[0].applies_to_all_options, false);
  assert.equal(block(['opt-a', 'opt-b', 'opt-c'])[0].applies_to_all_options, false);
  assert.equal(block(['opt-a'])[0].applies_to_all_options, false);
});

// 9: per-action match basis, never a capability-wide overclaim.
test('a mixed match records the basis per step', () => {
  const snapshot = {
    schema_version: 'wise-elders.capability-snapshot/v1',
    installation_id: 'install-ctr155',
    captured_at: '2026-10-30',
    basis: 'at_export',
    items: [
      {
        capability_id: 'skill:pilot-helper',
        kind: 'skill',
        name: 'pilot-helper',
        description: 'Runs a small pilot.',
        availability: 'available_now',
        source: 'openclaw.skills',
        recorded_reference_ids: [],
      },
    ],
    limitations: [],
  } as unknown as InstallationCapabilitySnapshot;
  const matches = matchCapabilitiesToPlan(snapshot, [
    {
      action_id: 'act-1',
      title: 'Record the result',
      description: 'Record the result.',
      department_id: 'pilot-helper',
    },
    {
      action_id: 'act-2',
      title: 'Run pilot-helper on the offer',
      description: 'Use pilot-helper for one pilot.',
    },
  ]);
  assert.equal(matches.length, 1);
  assert.equal(matches[0].match_basis, 'mixed');
  assert.deepEqual(matches[0].recorded_reference_action_ids, ['act-1']);
  assert.deepEqual(matches[0].named_in_step_action_ids, ['act-2']);
  const perAction = matches[0].matched_actions;
  assert.deepEqual(
    perAction.map((action) => [action.action_id, action.basis]),
    [
      ['act-1', 'recorded_reference'],
      ['act-2', 'named_in_step'],
    ],
  );
  assert.ok(matches[0].match_evidence.every((line) => /^act-\d+: /.test(line)));
  assert.deepEqual(matches[0].shared_terms, []);
});

// 10: one start step plus an honest parallel-eligible note.
test('Start here names one step and the parallel note never invents dependencies', () => {
  const twoIndependent = [
    {
      action_id: 'act-1',
      title: 'Publish one weekly episode',
      description: 'Publish it.',
      rationale: 'Shared recorded rationale.',
      source_condition_ids: [],
      department_id: null,
      assigned_agent_id: null,
      sop_id: null,
      persona_id: null,
      acceptance_criteria: [],
      budget_limit: null,
      due_at: null,
      depends_on_action_ids: [],
      risk_class: 'medium',
      execution_authorization_required: true,
    },
    {
      action_id: 'act-2',
      title: 'Record retention',
      description: 'Record it.',
      rationale: 'Shared recorded rationale.',
      source_condition_ids: [],
      department_id: null,
      assigned_agent_id: null,
      sop_id: null,
      persona_id: null,
      acceptance_criteria: [],
      budget_limit: null,
      due_at: null,
      depends_on_action_ids: [],
      risk_class: 'low',
      execution_authorization_required: true,
    },
  ];
  const parallel = (model({ label: 'GO', action_proposals: twoIndependent }).plan as Record<string, unknown>);
  assert.equal(parallel.start_here_step_number, 1);
  assert.deepEqual(parallel.parallel_eligible_step_numbers, [1, 2]);
  assert.match(String(parallel.parallel_eligible_note), /can run in parallel/);
  assert.equal(parallel.shared_why, 'Shared recorded rationale.');
  assert.deepEqual(parallel.shared_why_applies_to_step_numbers, [1, 2]);

  const chained = twoIndependent.map((proposal, index) =>
    index === 1 ? { ...proposal, depends_on_action_ids: ['act-1'] } : proposal,
  );
  const sequential = model({ label: 'GO', action_proposals: chained }).plan as Record<string, unknown>;
  assert.deepEqual(sequential.parallel_eligible_step_numbers, [1]);
  assert.equal(sequential.parallel_eligible_note, null);
  const steps = sequential.steps as Array<Record<string, unknown>>;
  assert.deepEqual(steps[1].depends_on_step_numbers, [1]);
});

// 11: missing criterion has a sentence, never an empty label.
test('an unstated finish line has a concise display sentence and an honest count', () => {
  const plan = model().plan as Record<string, unknown>;
  const steps = plan.steps as Array<Record<string, unknown>>;
  assert.equal(steps[0].done_when_status, 'not_recorded');
  assert.equal(
    steps[0].done_when_display,
    'Not recorded. Decide your own finish line before starting.',
  );
  assert.equal(plan.done_when_not_recorded_count, 1);
  assert.equal(plan.done_when_recorded_count, 0);
});

// 12: decision headline grammar.
test('the decision headline is two plain sentences', () => {
  const decision = (model({ label: 'GO_WITH_CONDITIONS' }).decision_vs_readiness as Record<
    string,
    unknown
  >).decision as Record<string, unknown>;
  assert.match(
    String(decision.headline),
    /^The council verdict was Go, with conditions\. It recommends Repurpose the archive\.$/,
  );
});
