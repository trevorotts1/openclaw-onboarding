/**
 * CTR-158 export-finish regression. INTENTIONALLY UNEXECUTED in this lane:
 * Trevor owns the run.
 *
 * Runner (when the owner runs it):
 *   node --import tsx --test tests/ctr158-export-finish.test.ts
 *
 * Static source reads only: no browser, no HTTP, no PDF render, no provider,
 * Council, Telegram or KIE call. It pins:
 * - an empty acceptance list renders the model's honest note in BOTH Markdown
 *   and HTML, never a blank "Done when" label;
 * - the Markdown production export carries the same readiness, information
 *   needed, council unknown counts, and start-here fields as HTML;
 * - the question section states its recorded/shown unknown count where the
 *   de-duplication actually occurs;
 * - a bounded capability list states its total and shown count, so a hidden
 *   capability count cannot reappear.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { SEAT_IDS, type CouncilCard } from '../src/contracts/index.js';
import {
  buildReportModel,
  matchCapabilitiesToPlan,
  type InstallationCapabilitySnapshot,
} from '../src/reports/index.js';
import { renderMarkdown, renderPrintHtml } from '../src/reports/render.js';

const runtimeDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const readRuntime = (relative: string): string =>
  readFileSync(join(runtimeDir, relative), 'utf8');

const SESSION_ID = 'sess-ctr158';
const INSTALL_ID = 'install-ctr158';
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

const EMPTY_ACCEPTANCE_NOTE =
  'The saved record did not state how to know this step is finished. Decide your own finish line before starting.';

function advisorCard(seatId: (typeof SEAT_IDS)[number]): CouncilCard {
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
    conditions: [],
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

const BRIEF = {
  schema_version: 'wise-elders.brief/v1',
  brief_id: 'brief-ctr158',
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

function model(
  snapshot: InstallationCapabilitySnapshot | null = null,
): Record<string, unknown> {
  return buildReportModel({
    verdict: scoredVerdict('GO_WITH_CONDITIONS') as never,
    brief: BRIEF,
    final_cards: SEAT_IDS.map((seat) => advisorCard(seat)),
    context: {
      report_date: '2026-10-30',
      session_mode: 'light',
      route_display: 'route-1',
      seat_qualifications: {},
      installation_id: INSTALL_ID,
      capability_snapshot: snapshot,
    },
    redaction: null,
  }) as Record<string, unknown>;
}

function capabilitySnapshot(names: string[]): InstallationCapabilitySnapshot {
  return {
    schema_version: 'wise-elders.capability-snapshot/v1',
    installation_id: INSTALL_ID,
    captured_at: '2026-10-30',
    basis: 'at_export',
    items: names.map((name, index) => ({
      capability_id: `skill:${name}`,
      kind: 'skill',
      name,
      description: `Fixture capability ${index + 1}.`,
      availability: 'available_now',
      source: 'openclaw.skills',
      recorded_reference_ids: [],
    })),
    limitations: [],
  } as unknown as InstallationCapabilitySnapshot;
}

// 1: empty acceptance is never a blank label on either production export.
test('an empty acceptance list prints the model note in Markdown and HTML', () => {
  const built = model();
  const markdown = renderMarkdown(built);
  const html = renderPrintHtml(built);
  assert.equal(markdown.includes('Done when:\n\n'), false);
  assert.ok(markdown.includes(`Done when:\n- ${EMPTY_ACCEPTANCE_NOTE}`));
  assert.ok(html.includes(`Done when:</strong></p>`));
  assert.ok(html.includes(`<p class="note">${EMPTY_ACCEPTANCE_NOTE}</p>`));
});

// 2: Markdown carries the same reader-critical status fields as HTML.
test('Markdown prints readiness, information needed, and start here', () => {
  const built = model();
  const markdown = renderMarkdown(built);
  assert.ok(markdown.includes('Can you act on this yet? Ready'));
  assert.ok(markdown.includes('Information needed:'));
  assert.ok(markdown.includes("The council's unknown record:"));
  assert.ok(markdown.includes('Start here: Step 1 — Publish one weekly episode'));
});

// 3: the question section states its de-duplication count in both exports.
test('the question unknown count and note are printed in Markdown and HTML', () => {
  const built = model();
  const markdown = renderMarkdown(built);
  const html = renderPrintHtml(built);
  assert.ok(markdown.includes('recorded;'));
  assert.ok(markdown.includes('distinct shown.'));
  assert.ok(markdown.includes('were shown once.'));
  assert.ok(html.includes('recorded;'));
  assert.ok(html.includes('distinct shown.'));
  assert.ok(html.includes('were shown once.'));
});

// 4: a bounded capability list states its total and shown count.
test('a seven-match capability list shows six rows and states all seven', () => {
  const names = Array.from({ length: 7 }, (_, index) => `weekly-episode-tool-${index + 1}`);
  const snapshot = capabilitySnapshot(names);
  const matches = matchCapabilitiesToPlan(snapshot, [
    {
      action_id: 'act-1',
      title: 'Publish one weekly episode',
      description: `Use ${names.join(', ')} for the release.`,
    },
  ]);
  assert.equal(matches.length, 7);
  const built = model(snapshot);
  const tools = built.your_tools as Record<string, unknown>;
  assert.equal(tools.items_total, 7);
  assert.equal(tools.items_shown, 6);
  assert.equal((tools.items as unknown[]).length, 6);
  const markdown = renderMarkdown(built);
  const html = renderPrintHtml(built);
  const line =
    '7 exact-matched installed item(s) were found; 6 are listed here and 1 further item(s) are not shown.';
  assert.ok(markdown.includes(line));
  assert.ok(html.includes(line));
});

// 5: the stale redacted-cover comment states the actual no-image cover.
test('the service redacted-cover comment matches the no-image cover', () => {
  const source = readRuntime('src/reports/service.ts');
  assert.ok(source.includes('the cover prints'));
  assert.ok(source.includes('the redaction note and no image at all'));
  assert.equal(source.includes('falls back to the wordmark band'), false);
});
