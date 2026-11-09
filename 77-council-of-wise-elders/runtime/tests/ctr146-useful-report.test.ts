/**
 * CTR-146 regression (UNEXECUTED in this lane; Trevor owns running tests).
 *
 * Runner:
 *   node --import tsx --test tests/ctr146-useful-report.test.ts
 *
 * It pins three things the reader report must never lose:
 * 1. round evidence comes from the saved cards only: the round count is
 *    the count of recorded rounds, and a change is reported only when the
 *    same seat's saved card actually changed;
 * 2. the capability snapshot is names/descriptions only, excludes
 *    template folders, refuses another installation's snapshot, and no
 *    SKILL.md body/prompt text can reach the report;
 * 3. every printable font size in the print document is at least 14pt,
 *    and the plan uses recorded dependencies for step order.
 */

import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { SEAT_IDS, type CouncilCard } from '../src/contracts/index.js';
import {
  assertSnapshotInstallation,
  buildReportModel,
  CapabilitySnapshotError,
  discoverInstallationCapabilities,
  matchCapabilitiesToPlan,
  renderPrintHtml,
  type InstallationCapabilitySnapshot,
} from '../src/reports/index.js';

const SESSION_ID = 'sess-ctr146-1';
const HASH = 'a'.repeat(64);

const brief = {
  schema_version: 'wise-elders.brief/v1',
  brief_id: 'brief-ctr146-1',
  session_id: SESSION_ID,
  revision: 1,
  question: 'Should we pilot the revised offer?',
  facts: [
    { id: 'fact-1', statement: 'The current offer has a measured baseline.', evidence_ids: ['ev-1'] },
  ],
  assumptions: [],
  unknowns: [],
  constraints: [],
  options: [
    { id: 'A', label: 'Keep the current offer', kind: 'status_quo' },
    { id: 'B', label: 'Pilot the revised offer', kind: 'bounded_test' },
  ],
  relevance_weights: Object.fromEntries(SEAT_IDS.map((seat) => [seat, 2])),
  critical_domains: [],
  evidence_manifest: [
    { evidence_id: 'ev-1', sha256: HASH, source_kind: 'client_document', locator: 'doc:baseline' },
  ],
  private_preference_ref: null,
  created_at: '2026-10-30T10:00:00Z',
  display_timezone: 'America/New_York',
} as never;

function card(seatId: (typeof SEAT_IDS)[number], round: number, preferred: 'A' | 'B'): CouncilCard {
  return {
    card_kind: 'advisor',
    seat_id: seatId,
    round,
    session_id: SESSION_ID,
    pack_version: 'pack-1',
    stance: 'conditional',
    preferred_option_id: preferred,
    option_scores: [
      { option_id: 'A', score: 5, rationale: 'fixture', evidence_ids: [] },
      { option_id: 'B', score: 8, rationale: 'fixture', evidence_ids: [] },
    ],
    decisive_arguments: [`${seatId} argument`],
    strongest_objection: `${seatId} objection`,
    change_my_mind: 'Measured evidence to the contrary.',
    conditions: [],
    critical_unknowns: [],
    minority_position: null,
    evidence_strength: 'medium',
    input_manifest_sha256: HASH,
    brief_revision: 1,
    schema_version: 'wise-elders.card/v1',
    framework_applications: [],
    challenges_answered: [],
    quotes: [],
    host: {
      scope: {},
      operation_id: 'op-1',
      route_id: 'route-1',
      session_id: SESSION_ID,
      stamped_at: '2026-10-30T10:00:00Z',
      source_status: 'verified',
    },
  } as unknown as CouncilCard;
}

function cards(): CouncilCard[] {
  const out: CouncilCard[] = [];
  for (const seat of SEAT_IDS) {
    out.push(card(seat, 1, seat === 'simon-sinek' ? 'A' : 'B'));
    out.push(card(seat, 2, 'B'));
  }
  return out;
}

const verdict = {
  schema_version: 'wise-elders.verdict/v1',
  result_kind: 'scored',
  session_id: SESSION_ID,
  verdict_revision: 1,
  recommended_option_id: 'B',
  label: 'GO',
  option_scores: [
    { option_id: 'A', score: 5, display_score: 5, weighted_sum: 90, denominator: 18, coverage: 1, spread: 2 },
    { option_id: 'B', score: 8, display_score: 8, weighted_sum: 144, denominator: 18, coverage: 1, spread: 1 },
  ],
  active_weights: Object.fromEntries(SEAT_IDS.map((seat) => [seat, 2])),
  evidence_strength: 'medium',
  hard_constraint_findings: [],
  main_reasons: ['The pilot is the only bounded test available.'],
  strongest_dissent: 'The pilot needs a named owner.',
  accepted_amendments: [],
  rejected_amendments: [],
  critical_unknowns: ['Is the pilot affordable this quarter?'],
  prerequisites: ['Name the pilot owner.'],
  action_proposals: [
    {
      action_id: 'act-2',
      session_id: SESSION_ID,
      verdict_revision: 1,
      title: 'Launch the pilot',
      description: 'Run the pilot with the recorded budget.',
      rationale: 'It is the cheapest informative test.',
      source_condition_ids: [],
      department_id: 'dept-ai-ceo',
      assigned_agent_id: null,
      sop_id: null,
      persona_id: null,
      acceptance_criteria: ['Pilot is live for fourteen days.'],
      budget_limit: null,
      due_at: null,
      depends_on_action_ids: ['act-1'],
      risk_class: 'medium',
      execution_authorization_required: true,
    },
    {
      action_id: 'act-1',
      session_id: SESSION_ID,
      verdict_revision: 1,
      title: 'Name the pilot owner',
      description: 'Pick one accountable owner.',
      rationale: 'Nothing runs without an owner.',
      source_condition_ids: [],
      department_id: null,
      assigned_agent_id: null,
      sop_id: null,
      persona_id: null,
      acceptance_criteria: ['An owner is named in writing.'],
      budget_limit: null,
      due_at: null,
      depends_on_action_ids: [],
      risk_class: 'low',
      execution_authorization_required: true,
    },
  ],
  cheapest_informative_test: 'Run the pilot for fourteen days.',
  stop_criteria: ['Stop if the pilot budget is exceeded.'],
  review_criteria: ['Review conversion after fourteen days.'],
  resolution_support: null,
  validation_status: 'valid',
  ratification_status: 'not_required',
  brief_sha256: HASH,
  content_sha256: 'b'.repeat(64),
} as never;

function build(snapshot: InstallationCapabilitySnapshot | null) {
  return buildReportModel({
    verdict: verdict as never,
    brief: brief as never,
    final_cards: cards(),
    context: {
      report_date: '2026-10-30',
      session_mode: 'medium',
      route_display: 'route-1',
      seat_qualifications: Object.fromEntries(SEAT_IDS.map((seat) => [seat, 'bibliographic_only'])),
      installation_id: 'install-ctr146',
      capability_snapshot: snapshot,
    },
    redaction: null,
  });
}

test('round evidence is the saved rounds only and changes need a real card change', () => {
  const model = build(null) as Record<string, unknown>;
  const debate = model.debate as Record<string, unknown>;
  assert.equal(debate.rounds_saved, 2);
  assert.equal(debate.highest_round, 2);
  const changes = debate.changes as Array<Record<string, unknown>>;
  assert.equal(changes.length, 1);
  assert.equal(changes[0].seat_id, 'simon-sinek');
  assert.equal(changes[0].from_option_label, 'Keep the current offer');
  assert.equal(changes[0].to_option_label, 'Pilot the revised offer');
  // No invented chair rationale: with no recorded mode_selection and no
  // chair note, the report says the record does not state one.
  const notes = (debate.notes as string[]).join(' ');
  assert.ok(notes.includes('does not state why this size was chosen'));
  assert.ok(notes.includes('no chair note'));
});

test('the plan follows recorded dependencies, not recorded array order', () => {
  const model = build(null) as Record<string, unknown>;
  const plan = model.plan as Record<string, unknown>;
  assert.equal(plan.ordering, 'recorded_dependencies');
  const steps = plan.steps as Array<Record<string, unknown>>;
  assert.equal(steps[0].action_id, 'act-1');
  assert.equal(steps[1].action_id, 'act-2');
  assert.deepEqual(steps[1].depends_on_step_numbers, [1]);
});

test('the capability snapshot is names/descriptions only and never leaks a skill body', () => {
  const root = mkdtempSync(join(tmpdir(), 'ctr146-cap-'));
  try {
    const skills = join(root, 'skills');
    mkdirSync(join(skills, '12-pilot-helper'), { recursive: true });
    writeFileSync(
      join(skills, '12-pilot-helper', 'SKILL.md'),
      [
        '---',
        'name: pilot-helper',
        'description: Runs a small pilot and records the result.',
        '---',
        '',
        'SECRET-PROMPT: never copy this into a report.',
      ].join('\n'),
    );
    mkdirSync(join(skills, '_template'), { recursive: true });
    writeFileSync(
      join(skills, '_template', 'SKILL.md'),
      '---\nname: template\ndescription: template only\n---\n',
    );
    mkdirSync(join(root, 'agents', 'dept-ai-ceo'), { recursive: true });
    writeFileSync(join(root, 'agents', 'dept-ai-ceo', 'models.json'), '{}');
    mkdirSync(join(root, 'agents', 'dept-template-only'), { recursive: true });

    const snapshot = discoverInstallationCapabilities({
      openclaw_root: root,
      installation_id: 'install-ctr146',
      captured_at: '2026-10-30',
    });
    assert.deepEqual(
      snapshot.items.map((item) => item.capability_id),
      ['department:dept-ai-ceo', 'skill:pilot-helper'],
    );
    const serialized = JSON.stringify(snapshot);
    assert.equal(serialized.includes('SECRET-PROMPT'), false);
    assert.equal(serialized.includes('template only'), false);

    const model = build(snapshot) as Record<string, unknown>;
    const tools = model.your_tools as Record<string, unknown>;
    assert.equal(tools.status, 'matched');
    const items = tools.items as Array<Record<string, unknown>>;
    assert.equal(items[0].capability_id, 'department:dept-ai-ceo');
    assert.equal(items[0].match_basis, 'recorded_reference');
    assert.equal(JSON.stringify(model).includes('SECRET-PROMPT'), false);

    const other = { ...snapshot, installation_id: 'install-other' };
    assert.throws(
      () => assertSnapshotInstallation(other, 'install-ctr146'),
      (error: unknown) => error instanceof CapabilitySnapshotError,
    );

    const matches = matchCapabilitiesToPlan(snapshot, [
      {
        action_id: 'act-1',
        title: 'Name the pilot owner',
        description: 'Pick one accountable owner.',
      },
    ]);
    assert.equal(matches.length, 0);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test('every printable font size is at least 14pt and no small-print class survives', () => {
  const model = build(null) as Record<string, unknown>;
  const html = renderPrintHtml(model);
  const sizes = [...html.matchAll(/font-size:\s*([0-9]+(?:\.[0-9]+)?)pt/g)].map((m) =>
    Number(m[1]),
  );
  assert.ok(sizes.length > 0);
  assert.ok(sizes.every((size) => size >= 14), `small font sizes: ${sizes.join(', ')}`);
  assert.ok(html.includes('Verdict: GO'));
  assert.ok(html.includes('Your plan'));
  assert.ok(html.includes('What each advisor said'));
  assert.ok(html.includes('How the debate went'));
  assert.ok(html.includes('Skills and departments on your OpenClaw'));
});
