/**
 * CTR-156 integrated-UX regression. INTENTIONALLY UNEXECUTED in this lane:
 * Trevor owns the run.
 *
 * Runner (when the owner runs it):
 *   node --import tsx --test tests/ctr156-integrated-ux.test.ts
 *
 * Static source reads only: no browser, no HTTP, no PDF render, no provider,
 * Council, Telegram or KIE call. It pins:
 * - the ONE shared reader projection consumed by both the report renderer and
 *   the chamber, including the consult branch's explicit empty counters;
 * - readiness separate from the verdict (only GO / GO_WITH_CONDITIONS can be
 *   ready; WAIT / RESHAPE / DONT_DO_IT / INSUFFICIENT_EVIDENCE never are);
 * - the actual label text in a ready reason (no hardcoded "Go");
 * - honest count / shown / removed semantics for what-would-change and the
 *   council unknown record;
 * - exact per-step capability evidence, and zero generic-word association;
 * - the redacted cover emitting no portrait and no roster name;
 * - the service read carrying `reader_projection` and the chamber reading it.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { SEAT_IDS, type CouncilCard } from '../src/contracts/index.js';
import {
  buildReaderProjection,
  buildReportModel,
  matchCapabilitiesToPlan,
  validateCapabilitySnapshot,
  type InstallationCapabilitySnapshot,
} from '../src/reports/index.js';
import { renderPrintHtml } from '../src/reports/render.js';

const runtimeDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const readRuntime = (relative: string): string =>
  readFileSync(join(runtimeDir, relative), 'utf8');

const SESSION_ID = 'sess-ctr156';
const HASH = 'a'.repeat(64);

const BRIEF_UNKNOWNS = [
  'The current subscriber count and watch-time hours are not stated.',
  'The weekly production hours available for editing are not stated.',
];
const VERDICT_UNKNOWNS = [
  'Current subscriber base and watch time are unknown.',
  'Unknown: weekly production hours available for editing.',
  'Unknown: current subscriber base and watch time.',
];

function advisorCard(
  seatId: (typeof SEAT_IDS)[number],
  options: {
    conditions?: Array<Record<string, unknown>>;
    changeMyMind?: string;
  } = {},
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
    change_my_mind: options.changeMyMind ?? `${seatId}: measured evidence to the contrary.`,
    conditions: options.conditions ?? [],
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

function condition(id: string, blocking: boolean, description: string, kind = 'prerequisite') {
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
  brief_id: 'brief-ctr156',
  session_id: SESSION_ID,
  revision: 1,
  question: 'Should the channel keep the weekly upload?',
  facts: [],
  assumptions: [],
  unknowns: BRIEF_UNKNOWNS.map((statement, index) => ({
    id: `u-${index + 1}`,
    statement,
    evidence_ids: [],
  })),
  constraints: [],
  options: [
    { id: 'opt-a', label: 'Keep the weekly upload', kind: 'bounded_test' },
    { id: 'opt-b', label: 'Run a two-week test', kind: 'change' },
  ],
  relevance_weights: Object.fromEntries(SEAT_IDS.map((seat) => [seat, 1])),
  critical_domains: [],
  evidence_manifest: [],
  private_preference_ref: null,
  created_at: '2026-10-30T10:00:00Z',
  display_timezone: 'America/New_York',
} as never;

function scoredVerdict(label: string): unknown {
  return {
    schema_version: 'wise-elders.verdict/v1',
    result_kind: 'scored',
    session_id: SESSION_ID,
    verdict_revision: 1,
    recommended_option_id: 'opt-a',
    label,
    option_scores: [
      { option_id: 'opt-a', score: 8.4, display_score: 8.4, weighted_sum: 151, denominator: 18, coverage: 1, spread: 1 },
      { option_id: 'opt-b', score: 7.1, display_score: 7.1, weighted_sum: 128, denominator: 18, coverage: 1, spread: 4 },
    ],
    active_weights: Object.fromEntries(SEAT_IDS.map((seat) => [seat, 1])),
    evidence_strength: 'low',
    hard_constraint_findings: [],
    main_reasons: ['Keeping the cadence protects the audience.'],
    strongest_dissent: 'The archive may be stale.',
    accepted_amendments: [],
    rejected_amendments: [],
    critical_unknowns: VERDICT_UNKNOWNS,
    prerequisites: [],
    action_proposals: [
      {
        action_id: 'act-1',
        session_id: SESSION_ID,
        verdict_revision: 1,
        title: 'Publish one weekly episode',
        description: 'Publish one repurposed episode each week.',
        rationale: 'Recorded in the draft resolution.',
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
    ratification_status: 'not_required',
    brief_sha256: HASH,
    content_sha256: 'b'.repeat(64),
  };
}

function consultVerdict(): unknown {
  const card = {
    card_kind: 'consult',
    seat_id: 'simon-sinek',
    session_id: SESSION_ID,
    round: 1,
    pack_version: 'pack-1',
    question: 'What should I ask my agent first?',
    answer: 'Ask for the saved record before anything else.',
    assumptions: ['The saved record exists.'],
    limits: ['This is advice only.'],
    next_step: 'Open the saved record.',
    evidence_ids: [],
    input_manifest_sha256: HASH,
    brief_revision: 1,
    schema_version: 'wise-elders.card/v1',
  };
  return {
    schema_version: 'wise-elders.verdict/v1',
    result_kind: 'consult',
    session_id: SESSION_ID,
    verdict_revision: 1,
    consult_card: card,
    next_step: card.next_step,
    validation_status: 'valid',
    brief_sha256: HASH,
    content_sha256: 'b'.repeat(64),
  };
}

function cards(options: { tiffanySafeguard?: boolean; sameChangeMind?: boolean } = {}) {
  const same = options.sameChangeMind === true;
  return SEAT_IDS.map((seat) =>
    advisorCard(seat, {
      changeMyMind: same ? 'The same recorded statement.' : undefined,
      conditions:
        options.tiffanySafeguard === true && seat === 'tiffany-aliche'
          ? [condition('cond-tiffany', false, 'Review retention after four episodes.', 'safeguard')]
          : [],
    }),
  );
}

function scoredModel(
  label = 'GO_WITH_CONDITIONS',
  options: { tiffanySafeguard?: boolean; sameChangeMind?: boolean } = {},
) {
  return buildReportModel({
    verdict: scoredVerdict(label) as never,
    brief: BRIEF,
    final_cards: cards(options),
    context: {
      report_date: '2026-10-30',
      session_mode: 'light',
      route_display: 'route-1',
      seat_qualifications: {},
      installation_id: 'install-ctr156',
      capability_snapshot: null,
    },
    redaction: null,
  }) as Record<string, unknown>;
}

// 1: ONE projection; the report model spreads exactly it.
test('the report summary, plan and readiness are the shared reader projection', () => {
  const verdict = scoredVerdict('GO_WITH_CONDITIONS') as never;
  const projection = buildReaderProjection({
    verdict,
    brief: BRIEF,
    final_cards: cards({ tiffanySafeguard: true }),
    context: null,
  });
  const built = scoredModel('GO_WITH_CONDITIONS', { tiffanySafeguard: true });
  assert.deepEqual(built.summary, projection.summary);
  assert.deepEqual(built.decision_vs_readiness, projection.decision_vs_readiness);
  assert.deepEqual(built.plan, projection.plan);
  assert.deepEqual(built.your_tools, projection.your_tools);
  assert.equal(projection.reader_projection_version, 1);
});

// 2: consult branch carries the same counter keys (no undefined .length).
test('a consult summary carries explicit empty counters', () => {
  const built = buildReportModel({
    verdict: consultVerdict() as never,
    brief: BRIEF,
    final_cards: [],
    context: {
      report_date: '2026-10-30',
      session_mode: 'consult',
      route_display: 'route-1',
      seat_qualifications: {},
      installation_id: 'install-ctr156',
      capability_snapshot: null,
    },
    redaction: null,
  }) as Record<string, unknown>;
  const summary = built.summary as Record<string, unknown>;
  assert.deepEqual(summary.verdict_only_additions, []);
  assert.equal(summary.council_unknowns_removed, 0);
  assert.equal(summary.what_would_change_the_answer_removed, 0);
  assert.ok(Array.isArray(summary.information_needed));
  assert.ok(Array.isArray(summary.council_unknowns));
});

// 3: readiness never "ready" outside GO / GO_WITH_CONDITIONS.
test('WAIT, RESHAPE, DONT_DO_IT and INSUFFICIENT_EVIDENCE are never ready', () => {
  for (const label of ['WAIT', 'RESHAPE', 'DONT_DO_IT', 'INSUFFICIENT_EVIDENCE']) {
    const built = scoredModel(label);
    const readiness = (built.decision_vs_readiness as Record<string, unknown>)
      .readiness as Record<string, unknown>;
    assert.equal(readiness.status, 'not_ready', label);
    assert.ok(
      (readiness.status_reasons as string[]).some((reason) => reason.includes('never reported as ready')),
      label,
    );
  }
});

// 4: a ready reason states the actual label, not a hardcoded "Go".
test('an eligible GO_WITH_CONDITIONS with only safeguards is ready and says so', () => {
  const built = scoredModel('GO_WITH_CONDITIONS', { tiffanySafeguard: true });
  const readiness = (built.decision_vs_readiness as Record<string, unknown>)
    .readiness as Record<string, unknown>;
  assert.equal(readiness.status, 'ready_with_conditions');
  assert.match((readiness.status_reasons as string[])[0], /Go, with conditions/);
  assert.equal((readiness.status_reasons as string[])[0].includes('The verdict is Go'), false);
});

// 5: honest what-would-change count / shown / removed.
test('what-would-change count is larger than shown only with an explicit removed count', () => {
  const built = scoredModel('GO_WITH_CONDITIONS', { sameChangeMind: true });
  const summary = built.summary as Record<string, unknown>;
  assert.equal(summary.what_would_change_the_answer_count, 9);
  assert.equal(summary.what_would_change_the_answer_shown, 1);
  assert.equal(summary.what_would_change_the_answer_removed, 8);
});

// 6: the council unknown record keeps total / collapsed / distinct explicit.
test('council unknown counts are total, removed and distinct shown', () => {
  const built = scoredModel();
  const summary = built.summary as Record<string, unknown>;
  assert.equal(summary.council_unknowns_count, 3);
  assert.equal(summary.council_unknowns_shown, 2);
  assert.equal(summary.council_unknowns_removed, 1);
  assert.equal((summary.information_needed as unknown[]).length, 2);
});

// 7: exact per-step tool basis; no generic-word association.
test('a generic word never links a tool, and an exact name does with evidence', () => {
  const snapshot = {
    schema_version: 'wise-elders.capability-snapshot/v1',
    installation_id: 'install-ctr156',
    captured_at: '2026-10-30',
    basis: 'at_export',
    items: [
      {
        capability_id: 'skill:backup-protocol',
        kind: 'skill',
        name: 'backup-protocol',
        description: 'Run a backup before every search and publish step.',
        availability: 'available_now',
        source: 'openclaw.skills',
        recorded_reference_ids: [],
      },
      {
        capability_id: 'skill:weekly-episode',
        kind: 'skill',
        name: 'weekly-episode',
        description: 'Packages one episode.',
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
      title: 'Publish one weekly episode',
      description: 'Publish one repurposed episode each week.',
    },
  ]);
  assert.deepEqual(matches.map((match) => match.capability_id), ['skill:weekly-episode']);
  assert.equal(matches[0].match_basis, 'named_in_step');
  assert.deepEqual(matches[0].shared_terms, []);
  assert.ok(matches[0].match_evidence.every((line) => /^act-1: /.test(line)));
  assert.equal(matches[0].matched_actions[0].basis, 'named_in_step');
});

// 8: the redacted cover emits no image and no roster name.
test('a redacted report cover prints no portrait bytes and no seat name', () => {
  const base = scoredModel();
  const redacted = { ...base, redacted: true, redaction_profile_id: 'profile-1' };
  const html = renderPrintHtml(redacted);
  const cover = html.split('Part 1')[0];
  assert.equal(html.includes('data:image'), false);
  assert.equal(html.includes('<figure class="seat-portrait"'), false);
  assert.equal(cover.includes('Simon Sinek'), false);
  assert.match(html, /Redacted report: portraits and seat names are not printed/);
});

// 9: render consumes the corrected model; the old shared-terms branch is gone.
test('both renderers use exact match evidence and no shared-terms sentence', () => {
  const renderSource = readRuntime('src/reports/render.ts');
  assert.equal(renderSource.includes('shares the terms'), false);
  assert.match(renderSource, /matched_actions/);
  assert.match(renderSource, /match_evidence/);
  assert.match(renderSource, /capabilityBasisLines/);
  assert.match(renderSource, /pushReadinessHtml/);
  assert.match(renderSource, /pushInformationHtml/);
  assert.match(renderSource, /start_here_step_number/);
});

// 10: the service read carries the projection and the chamber consumes it.
test('the session read projects the shared model and the chamber reads it', () => {
  const frontDoor = readRuntime('src/service/front-door.ts');
  assert.match(frontDoor, /sessionReaderProjection/);
  assert.match(frontDoor, /reader_projection: readerProjection/);
  assert.match(frontDoor, /buildReaderProjection/);
  const chamber = readRuntime('public/chamber/chamber-advisory.js');
  assert.match(chamber, /rec\.reader_projection/);
  const live = readRuntime('public/chamber/chamber-live.js');
  assert.match(live, /body\.reader_projection/);
  assert.match(live, /reader_projection: body\.reader_projection/);
  assert.match(chamber, /decision_vs_readiness/);
  assert.match(chamber, /Can you act on this yet\?/);
  assert.match(chamber, /Information needed/);
  assert.match(chamber, /start_here_step_number/);
  assert.match(chamber, /paintReadiness/);
  assert.match(chamber, /paintCouncilUnknowns/);
});
