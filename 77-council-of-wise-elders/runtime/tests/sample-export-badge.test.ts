/**
 * CWE-048 closeout, F-047-1: SAMPLE badge in sample exports.
 *
 * CWE-047 acceptance finding: the two shipped sample sessions export
 * through the shared report path, and every CLI surface labels them
 * SAMPLE, but the exported report files themselves (Markdown, record
 * JSON, print HTML) carried no SAMPLE marking. This test proves the
 * stored session's sample flag now rides through the export request
 * and the report context into the model, and that every rendered
 * surface of a sample export carries the badge while a non-sample
 * export gains none.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  canonicalHash,
  GOLDEN_WEIGHTS,
  SEAT_IDS,
  type AdvisorCard,
  type DecisionBrief,
  type HostStamp,
  type ScopeFields,
  type ScoredVerdict,
  type SeatId,
} from '../src/contracts/index.js';
import type { TrustedPrincipal } from '../src/authorization/index.js';
import { runCli, type CliIo } from '../src/cli/dispatcher.js';
import {
  aggregateEvidenceStrength,
  buildScoredVerdict,
  summarizeMainReasons,
  summarizeStrongestDissent,
} from '../src/protocol/verdict.js';
import { analyzeDecision } from '../src/scoring/index.js';
import {
  InMemoryDeliverableRegistry,
  InMemoryExportJournal,
  ReportExportService,
  type ReportExportRequest,
} from '../src/reports/index.js';
import { tempDataDir } from './helpers.js';

const HASH_B = 'b'.repeat(64);
const SESSION_ID = 'sess-badge-fixture';

const HOST_STAMP: HostStamp = {
  scope: {
    tenant_id: 'tenant-fixture',
    company_id: 'company-fixture',
    installation_id: 'install-fixture',
    owner_subject: null,
  },
  operation_id: 'op-fixture-1',
  route_id: 'route-fixture-1',
  session_id: SESSION_ID,
  stamped_at: '2026-10-16T05:05:00Z',
  source_status: 'verified',
};

const SCOPE: ScopeFields = {
  tenant_id: 'tenant-fixture',
  company_id: 'company-fixture',
  installation_id: 'install-fixture',
  owner_subject: 'owner-1',
};

const OWNER: TrustedPrincipal = {
  tenant_id: 'tenant-fixture',
  company_id: 'company-fixture',
  installation_id: 'install-fixture',
  subject: 'owner-1',
  channel: 'browser',
  support_access: false,
};

const GOLDEN_WEIGHT_MAP: Partial<Record<SeatId, number>> = Object.fromEntries(
  SEAT_IDS.map((seatId, i) => [seatId, GOLDEN_WEIGHTS[i]]),
);

function makeBrief(): DecisionBrief {
  return {
    schema_version: 'wise-elders.brief/v1',
    brief_id: 'brief-badge-fixture',
    session_id: SESSION_ID,
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
    created_at: '2026-10-16T05:00:00Z',
    display_timezone: 'America/New_York',
  } as DecisionBrief;
}

const SCORES: Record<string, number> = { A: 6, B: 8, C: 7 };

function advisorCard(seatId: SeatId): AdvisorCard {
  return {
    schema_version: 'wise-elders.card/v1',
    card_kind: 'advisor',
    session_id: SESSION_ID,
    brief_revision: 1,
    round: 2,
    seat_id: seatId,
    input_manifest_sha256: HASH_B,
    pack_version: 'pack-fixture-1.0.0',
    stance: 'conditional',
    preferred_option_id: 'B',
    option_scores: ['A', 'B', 'C'].map((optionId) => ({
      option_id: optionId,
      score: SCORES[optionId],
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
    host: { ...HOST_STAMP },
  } as AdvisorCard;
}

function makeRequest(sample: boolean | undefined): ReportExportRequest {
  const brief = makeBrief();
  const cards = SEAT_IDS.map((seatId) => advisorCard(seatId));
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
  const verdict: ScoredVerdict = buildScoredVerdict({
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
  return {
    request_id: `req-badge-${sample === true ? 'sample' : 'plain'}`,
    principal: OWNER,
    session_id: SESSION_ID,
    session_scope: SCOPE,
    session_visibility: 'company',
    verdict,
    brief,
    final_cards: cards,
    current_verdict_revision: 1,
    formats: ['record_json', 'markdown', 'print_html'],
    context: {
      report_date: '2026-10-16',
      session_mode: 'full',
      ...(sample === undefined ? {} : { sample }),
    },
    exported_at: '2026-10-16T09:00:00Z',
  };
}

function makeService(): ReportExportService {
  return new ReportExportService({
    journal: new InMemoryExportJournal(),
    registry: new InMemoryDeliverableRegistry(),
  });
}

function artifactBytes(
  result: { artifacts: Array<{ format: string; bytes: string }> },
  format: string,
): string {
  const artifact = result.artifacts.find((a) => a.format === format);
  assert.ok(artifact, `missing artifact ${format}`);
  return artifact.bytes;
}

test('F-047-1: a sample export carries the SAMPLE badge in markdown, record JSON, and print HTML', async () => {
  const result = await makeService().exportReport(makeRequest(true));
  const markdown = artifactBytes(result, 'markdown');
  const printHtml = artifactBytes(result, 'print_html');
  const recordJson = artifactBytes(result, 'record_json');
  assert.ok(markdown.includes('Sample session: SAMPLE'), 'markdown header badge missing');
  assert.ok(markdown.includes('SAMPLE: this report was exported from one of the shipped sample sessions'), 'markdown sample notice missing');
  assert.ok(printHtml.includes('Sample session: SAMPLE'), 'print HTML header badge missing');
  assert.ok(printHtml.includes('SAMPLE: this report was exported from one of the shipped sample sessions'), 'print HTML sample notice missing');
  const record = JSON.parse(recordJson) as { sample?: unknown; sample_notice?: unknown };
  assert.equal(record.sample, true);
  assert.equal(typeof record.sample_notice, 'string');
  assert.ok(String(record.sample_notice).startsWith('SAMPLE:'));
});

test('F-047-1: a non-sample export gains no SAMPLE badge on any surface', async () => {
  const result = await makeService().exportReport(makeRequest(undefined));
  for (const format of ['markdown', 'print_html', 'record_json']) {
    const bytes = artifactBytes(result, format);
    assert.ok(!bytes.includes('SAMPLE'), `${format} must not contain SAMPLE for a non-sample export`);
  }
  const record = JSON.parse(artifactBytes(result, 'record_json')) as {
    sample?: unknown;
    sample_notice?: unknown;
  };
  assert.equal(record.sample, false);
  assert.equal(record.sample_notice, null);
});

function capture(): { io: CliIo; out: () => string; err: () => string } {
  let outText = '';
  let errText = '';
  return {
    io: {
      out: (t) => {
        outText += t;
      },
      err: (t) => {
        errText += t;
      },
    },
    out: () => outText,
    err: () => errText,
  };
}

test('F-047-1: the CLI export of a shipped sample session carries the badge end to end', async () => {
  const dir = tempDataDir('badge-sample-cli');
  let c = capture();
  assert.equal(await runCli(['sample', 'run', '--json', '--data-dir', dir], c.io), 0);

  c = capture();
  assert.equal(
    await runCli(['export', 'sess-fixture-1', '--format', 'md', '--data-dir', dir], c.io),
    0,
  );
  assert.ok(c.out().includes('Sample session: SAMPLE'), 'CLI markdown export badge missing');
  assert.ok(c.out().includes('SAMPLE: this report was exported from one of the shipped sample sessions'));

  c = capture();
  assert.equal(
    await runCli(['export', 'sess-fixture-1', '--format', 'json', '--data-dir', dir], c.io),
    0,
  );
  const record = JSON.parse(c.out()) as { sample?: unknown };
  assert.equal(record.sample, true);
});
