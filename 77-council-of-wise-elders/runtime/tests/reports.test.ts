/**
 * CWE-038 validated report export service tests (directive Section
 * 24; binding B15).
 *
 * Primary-owned acceptance contracts (Section 35):
 * - T105: Markdown, JSON, and PDF agree on option scores, decisions,
 *   conditions, citations, and report revision. The PDF deliverable is
 *   registered not ready in this runtime (its approved renderer is not
 *   in the dependency bill; CWE-044 owns it), so agreement is proven
 *   across the three produced formats and the PDF refusal is proven
 *   typed and honest, never faked bytes.
 * - T059: retention or deletion racing an active export cannot expose
 *   a deleted private artifact (mid-export tombstone plus read-after-
 *   delete, both refused).
 * The export limb of T073 is owned by CWE-007; the authorization
 * negatives here exercise the CWE-007 ports this service composes.
 *
 * Fixture identity: cwe-038-synthetic-fixtures/v1. Contract tests over
 * synthetic fixtures; verification_level: contract_tested (34.3). The
 * golden verdict is the Section 32.2 fixture: weights [2,3,2,3,3,2,3,
 * 2,2] totaling 22, A = 132/22 = 6.0, B = 168/22 (display 7.6),
 * C = 145/22 (display 6.6), label GO, recommended B; and its Tiffany-
 * abstains variant (B = 150/19, coverage 19/22, WAIT with the
 * affordability prerequisite).
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
  type CriticalDomainRequirement,
  type DecisionBrief,
  type HostStamp,
  type ScopeFields,
  type ScoredVerdict,
  type SeatId,
  type SessionStateRecord,
} from '../src/contracts/index.js';
import {
  AuthorizationError,
  type TrustedPrincipal,
} from '../src/authorization/index.js';
import { buildSampleSession } from '../src/cli/fixture-transport.js';
import type { StoredSession } from '../src/cli/host-ports.js';
import { envelopeFromScope } from '../src/persistence/envelope.js';
import { CouncilStoreService } from '../src/persistence/store.js';
import {
  aggregateEvidenceStrength,
  buildScoredVerdict,
  summarizeMainReasons,
  summarizeStrongestDissent,
} from '../src/protocol/verdict.js';
import { analyzeDecision } from '../src/scoring/index.js';
import {
  createCwe006ExportJournal,
  createCwe006SessionLiveness,
  InMemoryExportJournal,
  ReportExportError,
  ReportExportService,
  InMemoryDeliverableRegistry,
  type ReportExportRequest,
  type SessionLivenessPort,
} from '../src/reports/index.js';
import { tempDataDir } from './helpers.js';

// ------------------------------------------------------------- fixtures

const HASH_B = 'b'.repeat(64);
const SESSION_ID = 'sess-fixture-1';

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
  stamped_at: '2026-10-14T02:05:00Z',
  source_status: 'verified',
};

const GOLDEN_WEIGHT_MAP: Partial<Record<SeatId, number>> = Object.fromEntries(
  SEAT_IDS.map((seatId, i) => [seatId, GOLDEN_WEIGHTS[i]]),
);

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

const ALL_BIBLIOGRAPHIC: Partial<Record<SeatId, string>> = Object.fromEntries(
  SEAT_IDS.map((seatId) => [seatId, 'bibliographic_only']),
);

function makeBrief(
  sessionId: string,
  overrides: Partial<DecisionBrief> = {},
): DecisionBrief {
  return {
    schema_version: 'wise-elders.brief/v1',
    brief_id: 'brief-fixture-1',
    session_id: sessionId,
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
      { evidence_id: 'ev-brunson-nms', sha256: 'c'.repeat(64), source_kind: 'book', locator: 'skill22:brunson-network-marketing-secrets' },
    ],
    private_preference_ref: null,
    created_at: '2026-10-14T02:00:00Z',
    display_timezone: 'America/New_York',
    ...overrides,
  } as DecisionBrief;
}

type ScoreTable = Record<string, Record<SeatId, number | null>>;

const GOLDEN_TABLE: ScoreTable = {
  A: { 'simon-sinek': 6, 'td-jakes': 5, 'oprah-winfrey': 6, 'tiffany-aliche': 8, 'russell-brunson': 5, 'michelle-obama': 6, 'brene-brown': 6, 'dennis-kimbro': 6, 'les-brown': 6 },
  B: { 'simon-sinek': 8, 'td-jakes': 8, 'oprah-winfrey': 7, 'tiffany-aliche': 6, 'russell-brunson': 9, 'michelle-obama': 8, 'brene-brown': 7, 'dennis-kimbro': 8, 'les-brown': 8 },
  C: { 'simon-sinek': 7, 'td-jakes': 9, 'oprah-winfrey': 7, 'tiffany-aliche': 3, 'russell-brunson': 8, 'michelle-obama': 6, 'brene-brown': 5, 'dennis-kimbro': 7, 'les-brown': 8 },
};

const TIFFANY_ABSTAINS_TABLE: ScoreTable = {
  ...GOLDEN_TABLE,
  B: { ...GOLDEN_TABLE.B, 'tiffany-aliche': null },
};

function advisorCard(
  seatId: SeatId,
  table: ScoreTable,
  sessionId: string,
  overrides: Partial<AdvisorCard> = {},
): AdvisorCard {
  return {
    schema_version: 'wise-elders.card/v1',
    card_kind: 'advisor',
    session_id: sessionId,
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
    host: { ...HOST_STAMP, session_id: sessionId },
    ...overrides,
  } as AdvisorCard;
}

function goldenCards(sessionId: string, table: ScoreTable = GOLDEN_TABLE): AdvisorCard[] {
  return SEAT_IDS.map((seatId) => advisorCard(seatId, table, sessionId));
}

function buildVerdictFromCards(
  cards: AdvisorCard[],
  brief: DecisionBrief,
): ScoredVerdict {
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

function makeService(liveness?: SessionLivenessPort) {
  const journal = new InMemoryExportJournal();
  const registry = new InMemoryDeliverableRegistry();
  const service = new ReportExportService({ journal, registry, liveness });
  return { service, journal, registry };
}

function goldenRequest(
  overrides: Partial<ReportExportRequest> = {},
): ReportExportRequest {
  const brief = makeBrief(SESSION_ID);
  const cards = goldenCards(SESSION_ID);
  const verdict = buildVerdictFromCards(cards, brief);
  return {
    request_id: 'req-fixture-1',
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
      report_date: '2026-10-14',
      session_mode: 'full',
      seat_qualifications: { ...ALL_BIBLIOGRAPHIC },
    },
    exported_at: '2026-10-14T12:00:00Z',
    ...overrides,
  };
}

function artifactBytes(result: { artifacts: Array<{ format: string; bytes: string }> }, format: string): string {
  const artifact = result.artifacts.find((a) => a.format === format);
  assert.ok(artifact, `missing artifact ${format}`);
  return artifact.bytes;
}

// ---------------------------------------------------------------- tests

test('golden verdict exports in all ready formats with the fixture numbers', async () => {
  const { service, journal } = makeService();
  const result = await service.exportReport(goldenRequest());
  assert.deepEqual(result.states, [
    'authorized',
    'validated',
    'rendered',
    'journaled',
    'registered',
  ]);
  assert.equal(result.verdict_revision, 1);

  const markdown = artifactBytes(result, 'markdown');
  assert.ok(markdown.includes('Verdict: GO'));
  assert.ok(markdown.includes('Recommendation: B (Pilot the revised offer)'));
  assert.ok(markdown.includes('| 132 | 22 | 6 | 6.0 | 100.00% |'));
  assert.ok(markdown.includes('| 168 | 22 | 7.6364 | 7.6 | 100.00% |'));
  assert.ok(markdown.includes('| 145 | 22 | 6.5909 | 6.6 | 100.00% |'));

  const record = JSON.parse(artifactBytes(result, 'record_json')) as {
    verdict_block: { label: string; recommended_option_id: string; content_sha256: string };
    score_table: Array<{ option_id: string; weighted_sum: number; display_score: number }>;
    report_revision_id: string;
  };
  assert.equal(record.verdict_block.label, 'GO');
  assert.equal(record.verdict_block.recommended_option_id, 'B');
  assert.equal(record.report_revision_id, result.report_revision_id);
  const bRow = record.score_table.find((row) => row.option_id === 'B');
  assert.equal(bRow?.weighted_sum, GOLDEN_EXPECTED.B.weighted_sum);
  assert.equal(bRow?.display_score, GOLDEN_EXPECTED.B.display_score);

  const html = artifactBytes(result, 'print_html');
  assert.ok(html.includes('Verdict: GO'));
  assert.ok(html.includes('7.6'));

  // Revision identity and verdict hash agree in every format (T105).
  for (const bytes of [markdown, html]) {
    assert.ok(bytes.includes(result.report_revision_id));
    assert.ok(bytes.includes(result.verdict_content_sha256));
  }
  assert.equal(record.verdict_block.content_sha256, result.verdict_content_sha256);

  // One journal record per format, naming who, revision, and format.
  const records = journal.records();
  assert.equal(records.length, 3);
  assert.deepEqual(
    records.map((r) => r.format).sort(),
    ['markdown', 'print_html', 'record_json'],
  );
  for (const entry of records) {
    assert.equal(entry.exporter_subject, 'owner-1');
    assert.equal(entry.verdict_revision, 1);
    assert.equal(entry.verdict_content_sha256, result.verdict_content_sha256);
    const artifact = result.artifacts.find((a) => a.format === entry.format);
    assert.equal(entry.artifact_sha256, artifact?.sha256);
  }
});

test('byte determinism: the same validated revision renders identical bytes twice', async () => {
  const { service } = makeService();
  const first = await service.exportReport(goldenRequest({ request_id: 'req-det-1' }));
  const second = await service.exportReport(goldenRequest({ request_id: 'req-det-2' }));
  for (const format of ['record_json', 'markdown', 'print_html']) {
    assert.equal(
      artifactBytes(first, format),
      artifactBytes(second, format),
      `${format} bytes differ across runs`,
    );
  }
  assert.equal(first.report_revision_id, second.report_revision_id);
});

test('T105: scores, decision, conditions, citations, and revision agree across formats', async () => {
  const brief = makeBrief(SESSION_ID);
  const cards = goldenCards(SESSION_ID);
  cards[3] = advisorCard('tiffany-aliche', GOLDEN_TABLE, SESSION_ID, {
    conditions: [
      {
        id: 'cond-pilot-budget',
        description: 'Pilot spend stays within the approved pilot budget.',
        kind: 'prerequisite',
        blocking: true,
        verification_method: 'receipt review',
        required_evidence: ['ev-1'],
        responsible_role: 'owner',
        due_at: null,
        status: 'open',
        depends_on: [],
      },
    ],
  });
  const verdict = buildVerdictFromCards(cards, brief);
  const { service } = makeService();
  const result = await service.exportReport(
    goldenRequest({ brief, final_cards: cards, verdict }),
  );
  const markdown = artifactBytes(result, 'markdown');
  const html = artifactBytes(result, 'print_html');
  const recordJson = artifactBytes(result, 'record_json');
  for (const bytes of [markdown, html, recordJson]) {
    assert.ok(bytes.includes('cond-pilot-budget'), 'condition id missing from a format');
    assert.ok(bytes.includes('doc:baseline-metrics'), 'citation locator missing from a format');
    assert.ok(bytes.includes('ev-brunson-nms'), 'provenance id missing from a format');
    assert.ok(bytes.includes(result.report_revision_id), 'report revision missing from a format');
  }
  // The provenance appendix carries identifiers and locators only: the
  // record's manifest entries have exactly the four recorded fields.
  const record = JSON.parse(recordJson) as {
    provenance: { evidence_manifest: Array<Record<string, unknown>> };
    sibling_artifacts: Array<{ format: string; status: string; sha256: string | null }>;
  };
  for (const entry of record.provenance.evidence_manifest) {
    assert.deepEqual(Object.keys(entry).sort(), [
      'evidence_id',
      'locator',
      'sha256',
      'source_kind',
    ]);
  }
  // The record binds the exact sibling bytes and names PDF not ready.
  const markdownArtifact = result.artifacts.find((a) => a.format === 'markdown');
  const sibling = record.sibling_artifacts.find((s) => s.format === 'markdown');
  assert.equal(sibling?.sha256, markdownArtifact?.sha256);
  const pdfSibling = record.sibling_artifacts.find((s) => s.format === 'pdf');
  assert.equal(pdfSibling?.status, 'not_ready');
  assert.equal(pdfSibling?.sha256, null);
});

test('invalid verdict refuses export: tampered score fails the exact-hash check', async () => {
  const { service, journal, registry } = makeService();
  const request = goldenRequest();
  const tampered = {
    ...request.verdict,
    option_scores: (request.verdict as ScoredVerdict).option_scores.map((o) =>
      o.option_id === 'B' ? { ...o, display_score: 9.9 } : o,
    ),
  } as ScoredVerdict;
  await assert.rejects(
    service.exportReport({ ...request, verdict: tampered }),
    (error: unknown) => {
      assert.ok(error instanceof ReportExportError);
      assert.equal(error.code, 'EXPORT_VERDICT_INVALID');
      assert.ok(error.failed_checks.includes('content_hash_exact'));
      return true;
    },
  );
  assert.equal(journal.records().length, 0);
  assert.equal(registry.listForSession(SESSION_ID).length, 0);
});

test('invalid verdict refuses export: a rehashed tamper still fails recomputation', async () => {
  const { service } = makeService();
  const request = goldenRequest();
  const base = request.verdict as ScoredVerdict;
  const tamperedBase = {
    ...base,
    option_scores: base.option_scores.map((o) =>
      o.option_id === 'B' ? { ...o, weighted_sum: 170 } : o,
    ),
  };
  const { content_sha256: _drop, ...rest } = tamperedBase;
  const tampered = { ...rest, content_sha256: canonicalHash(rest) } as ScoredVerdict;
  await assert.rejects(
    service.exportReport({ ...request, verdict: tampered }),
    (error: unknown) => {
      assert.ok(error instanceof ReportExportError);
      assert.equal(error.code, 'EXPORT_VERDICT_INVALID');
      assert.ok(error.failed_checks.includes('scores_recomputed'));
      return true;
    },
  );
});

test('superseded revision refuses export; incomplete export refuses without cards', async () => {
  const { service } = makeService();
  await assert.rejects(
    service.exportReport(goldenRequest({ current_verdict_revision: 2 })),
    (error: unknown) => {
      assert.ok(error instanceof ReportExportError);
      assert.equal(error.code, 'EXPORT_VERDICT_SUPERSEDED');
      return true;
    },
  );
  await assert.rejects(
    service.exportReport(goldenRequest({ final_cards: undefined })),
    (error: unknown) => {
      assert.ok(error instanceof ReportExportError);
      assert.equal(error.code, 'EXPORT_VERDICT_INCOMPLETE');
      return true;
    },
  );
});

test('Section 7 label appears for every seat in every format carrying advisor content', async () => {
  const { service } = makeService();
  const result = await service.exportReport(goldenRequest());
  const names: Record<SeatId, string> = {
    'simon-sinek': 'Simon Sinek',
    'td-jakes': 'T. D. Jakes',
    'oprah-winfrey': 'Oprah Winfrey',
    'tiffany-aliche': 'Tiffany Aliche',
    'russell-brunson': 'Russell Brunson',
    'michelle-obama': 'Michelle Obama',
    'brene-brown': 'Brené Brown',
    'dennis-kimbro': 'Dr. Dennis Kimbro',
    'les-brown': 'Les Brown',
  };
  for (const format of ['record_json', 'markdown', 'print_html']) {
    const bytes = artifactBytes(result, format);
    for (const seatId of SEAT_IDS) {
      const label = `AI perspective inspired by the published work of ${names[seatId]}. Not the individual and not an endorsement.`;
      assert.ok(bytes.includes(label), `${format} missing label for ${seatId}`);
    }
    // Qualification state printed exactly as recorded, never upgraded.
    assert.ok(bytes.includes('bibliographic_only'), `${format} missing qualification state`);
    // Four-authorizations separation is stated in every format.
    assert.ok(
      bytes.includes('not an execution authorization'),
      `${format} missing authorization separation`,
    );
  }
});

test('Tiffany-abstains variant exports its WAIT and prerequisite exactly (32.2)', async () => {
  const affordability: CriticalDomainRequirement = {
    schema_version: 'wise-elders.critical-domain-requirement/v1',
    domain: 'financial_feasibility',
    status: 'unresolved',
    trigger_evidence_ids: ['ev-1'],
    trigger_field_paths: [],
    required_seat_id: 'tiffany-aliche',
    required_checker: 'seat',
    unresolved_questions: ['Is the pilot affordable at committed cash levels?'],
    policy_version: 'policy-fixture-1',
  };
  const brief = makeBrief(SESSION_ID, { critical_domains: [affordability] });
  const cards = goldenCards(SESSION_ID, TIFFANY_ABSTAINS_TABLE);
  const verdict = buildVerdictFromCards(cards, brief);
  assert.equal(verdict.label, 'WAIT');
  const { service } = makeService();
  const result = await service.exportReport(
    goldenRequest({ brief, final_cards: cards, verdict }),
  );
  const markdown = artifactBytes(result, 'markdown');
  assert.ok(markdown.includes('Verdict: WAIT'));
  assert.ok(
    markdown.includes('Is the pilot affordable at committed cash levels?'),
    'the exact prerequisite must be exported',
  );
  // B row: sum 150 over 19, display 7.9, coverage 86.36%, Tiffany abstained.
  assert.ok(markdown.includes('| 150 | 19 | 7.8947 | 7.9 | 86.36% |'));
  assert.ok(markdown.includes('tiffany-aliche'));
  const record = JSON.parse(artifactBytes(result, 'record_json')) as {
    verdict_block: { label: string };
    score_table: Array<{
      option_id: string;
      weighted_sum: number;
      denominator: number;
      coverage: number;
      abstained_seat_ids: string[];
    }>;
    prerequisites: string[];
  };
  assert.equal(record.verdict_block.label, 'WAIT');
  const bRow = record.score_table.find((row) => row.option_id === 'B');
  assert.equal(bRow?.weighted_sum, GOLDEN_EXPECTED.B_TIFFANY_ABSTAINS.weighted_sum);
  assert.equal(bRow?.denominator, GOLDEN_EXPECTED.B_TIFFANY_ABSTAINS.denominator);
  assert.equal(bRow?.coverage, GOLDEN_EXPECTED.B_TIFFANY_ABSTAINS.coverage);
  assert.deepEqual(bRow?.abstained_seat_ids, ['tiffany-aliche']);
  assert.ok(
    record.prerequisites.includes('Is the pilot affordable at committed cash levels?'),
  );
});

test('authorization negatives: cross-scope and private non-owner exports refuse', async () => {
  const { service, journal } = makeService();
  const crossScope: TrustedPrincipal = { ...OWNER, company_id: 'company-other' };
  await assert.rejects(
    service.exportReport(goldenRequest({ principal: crossScope })),
    (error: unknown) => {
      assert.ok(error instanceof AuthorizationError);
      assert.equal(error.code, 'COUNCIL_CROSS_SCOPE');
      return true;
    },
  );
  const member: TrustedPrincipal = { ...OWNER, subject: 'member-2' };
  await assert.rejects(
    service.exportReport(
      goldenRequest({ principal: member, session_visibility: 'private' }),
    ),
    (error: unknown) => {
      assert.ok(error instanceof AuthorizationError);
      assert.equal(error.code, 'COUNCIL_PRIVATE_OWNER_REQUIRED');
      return true;
    },
  );
  // A support read of a private session never includes export.
  const support: TrustedPrincipal = {
    ...OWNER,
    subject: 'support-1',
    support_access: true,
  };
  await assert.rejects(
    service.exportReport(
      goldenRequest({ principal: support, session_visibility: 'private' }),
    ),
    (error: unknown) => {
      assert.ok(error instanceof AuthorizationError);
      assert.equal(error.code, 'COUNCIL_PRIVATE_OWNER_REQUIRED');
      return true;
    },
  );
  assert.equal(journal.records().length, 0);
  // Control: the owner can export the private session.
  const ok = await service.exportReport(
    goldenRequest({ session_visibility: 'private', formats: ['markdown'] }),
  );
  assert.equal(ok.artifacts.length, 1);
});

test('retry with the same request ID replays without a second journal record', async () => {
  const { service, journal } = makeService();
  const first = await service.exportReport(goldenRequest());
  const second = await service.exportReport(goldenRequest());
  assert.equal(journal.records().length, 3);
  for (const artifact of second.artifacts) {
    assert.equal(artifact.replayed, true);
    const original = first.artifacts.find((a) => a.format === artifact.format);
    assert.equal(artifact.bytes, original?.bytes);
    assert.equal(artifact.sha256, original?.sha256);
  }
});

test('PDF refuses as a typed not-ready deliverable naming the missing piece', async () => {
  const { service, journal } = makeService();
  for (const formats of [['pdf'], 'all'] as const) {
    await assert.rejects(
      service.exportReport(goldenRequest({ formats })),
      (error: unknown) => {
        assert.ok(error instanceof ReportExportError);
        assert.equal(error.code, 'EXPORT_FORMAT_NOT_READY');
        assert.ok(error.missing_piece?.includes('Playwright/Chromium'));
        return true;
      },
    );
  }
  assert.equal(journal.records().length, 0);
});

test('redacted team report is a separate identified artifact with no surviving target', async () => {
  const brief = makeBrief(SESSION_ID, {
    question: 'Should Acme Corp pilot the revised offer before a broad launch?',
  });
  const cards = goldenCards(SESSION_ID);
  cards[0] = advisorCard('simon-sinek', GOLDEN_TABLE, SESSION_ID, {
    decisive_arguments: ['Acme Corp has a measured conversion baseline.'],
  });
  const verdict = buildVerdictFromCards(cards, brief);
  const { service, journal } = makeService();
  const plain = await service.exportReport(
    goldenRequest({ brief, final_cards: cards, verdict, request_id: 'req-plain-1' }),
  );
  assert.ok(artifactBytes(plain, 'markdown').includes('Acme Corp'));

  const redacted = await service.exportReport(
    goldenRequest({
      brief,
      final_cards: cards,
      verdict,
      request_id: 'req-redacted-1',
      redaction: {
        profile_id: 'redact-team-1',
        replacements: [{ match: 'Acme Corp' }],
      },
    }),
  );
  assert.notEqual(redacted.report_revision_id, plain.report_revision_id);
  for (const artifact of redacted.artifacts) {
    assert.ok(!artifact.bytes.includes('Acme Corp'), `${artifact.format} leaked the redaction target`);
    assert.ok(artifact.filename.includes('-redacted'));
    assert.equal(artifact.redacted, true);
  }
  assert.ok(artifactBytes(redacted, 'markdown').includes('Redacted report: yes'));
  const record = JSON.parse(artifactBytes(redacted, 'record_json')) as {
    redacted: boolean;
    redaction_profile_id: string;
    verdict_block: { content_sha256: string };
  };
  assert.equal(record.redacted, true);
  assert.equal(record.redaction_profile_id, 'redact-team-1');
  // Identity is not redacted away: the artifact still binds the verdict.
  assert.equal(record.verdict_block.content_sha256, plain.verdict_content_sha256);
  const journalRecord = journal
    .records()
    .find((r) => r.request_id === 'req-redacted-1' && r.format === 'markdown');
  assert.equal(journalRecord?.redacted, true);
  assert.equal(journalRecord?.redaction_profile_id, 'redact-team-1');
});

test('T059: a deletion landing mid-export and a read after deletion both refuse', async () => {
  let calls = 0;
  const racingLiveness: SessionLivenessPort = {
    isSessionDeleted: () => {
      calls += 1;
      return calls > 1;
    },
  };
  const raced = makeService(racingLiveness);
  await assert.rejects(
    raced.service.exportReport(goldenRequest()),
    (error: unknown) => {
      assert.ok(error instanceof ReportExportError);
      assert.equal(error.code, 'EXPORT_SESSION_DELETED');
      return true;
    },
  );
  assert.equal(raced.journal.records().length, 0);
  assert.equal(raced.registry.listForSession(SESSION_ID).length, 0);

  const flag = { deleted: false };
  const steady = makeService({ isSessionDeleted: () => flag.deleted });
  const result = await steady.service.exportReport(
    goldenRequest({ formats: ['markdown'] }),
  );
  const deliverableId = result.artifacts[0].deliverable_id;
  const read = await steady.service.readDeliverable({
    principal: OWNER,
    deliverable_id: deliverableId,
  });
  assert.equal(read.bytes, result.artifacts[0].bytes);
  flag.deleted = true;
  await assert.rejects(
    steady.service.readDeliverable({ principal: OWNER, deliverable_id: deliverableId }),
    (error: unknown) => {
      assert.ok(error instanceof ReportExportError);
      assert.equal(error.code, 'EXPORT_SESSION_DELETED');
      return true;
    },
  );
  // Delete path (B15): owner deletes, later reads find nothing.
  flag.deleted = false;
  const deleted = await steady.service.deleteDeliverable({
    principal: OWNER,
    deliverable_id: deliverableId,
  });
  assert.equal(deleted, true);
  await assert.rejects(
    steady.service.readDeliverable({ principal: OWNER, deliverable_id: deliverableId }),
    (error: unknown) => {
      assert.ok(error instanceof ReportExportError);
      assert.equal(error.code, 'EXPORT_DELIVERABLE_NOT_FOUND');
      return true;
    },
  );
});

test('CWE-006 integration: exports journal through the real store and its tombstone blocks access (T059)', async () => {
  const sample = buildSampleSession();
  const scope = sample.scope;
  const spec = { ...sample.spec, visibility: 'company' as const };
  const state: SessionStateRecord = {
    schema_version: 'wise-elders.session-state/v1',
    session_id: spec.session_id,
    mode: spec.mode,
    state: 'DRAFT',
    state_version: 0,
    brief_revision: sample.brief.revision,
    resume_phase: null,
    cancel_generation: 0,
    revocation_generation: 0,
    attempt: 1,
    lease_epoch: 0,
    archived: false,
    updated_at: spec.created_at,
  };
  const stored: StoredSession = {
    spec,
    brief: sample.brief,
    scope,
    state,
    sample: false,
  };
  const envelope = envelopeFromScope(scope, 'owner-1', 'owner', 'write');
  const store = CouncilStoreService.open({
    dataDir: tempDataDir('cwe038-store'),
    clock: { nowUtc: () => '2026-10-14T12:00:00.000Z' },
    ids: { newId: () => 'id-cwe038-1' },
    envelope,
  });
  try {
    await store.createSession(stored);
    const journal = createCwe006ExportJournal(store, {
      tenant_id: scope.tenant_id,
      company_id: scope.company_id,
    });
    const registry = new InMemoryDeliverableRegistry();
    const service = new ReportExportService({
      journal,
      registry,
      liveness: createCwe006SessionLiveness(store),
    });
    const sessionId = spec.session_id;
    const brief = makeBrief(sessionId);
    const cards = goldenCards(sessionId);
    const verdict = buildVerdictFromCards(cards, brief);
    const principal: TrustedPrincipal = {
      tenant_id: scope.tenant_id,
      company_id: scope.company_id,
      installation_id: scope.installation_id,
      subject: 'owner-1',
      channel: 'browser',
      support_access: false,
    };
    const request: ReportExportRequest = {
      request_id: 'req-store-1',
      principal,
      session_id: sessionId,
      session_scope: scope,
      session_visibility: 'company',
      verdict,
      brief,
      final_cards: cards,
      current_verdict_revision: 1,
      formats: ['markdown'],
      context: {
        report_date: '2026-10-14',
        session_mode: 'full',
        seat_qualifications: { ...ALL_BIBLIOGRAPHIC },
      },
      exported_at: '2026-10-14T12:00:00Z',
    };
    const result = await service.exportReport(request);
    const events = await store.listEvents(sessionId);
    const exportEvents = events.filter(
      (e) => (e.payload as Record<string, unknown>).kind === 'report_export',
    );
    assert.equal(exportEvents.length, 1);
    assert.equal(exportEvents[0].event_type, 'operation_completed');
    assert.equal(
      (exportEvents[0].payload as Record<string, unknown>).format,
      'markdown',
    );
    assert.equal(
      (exportEvents[0].payload as Record<string, unknown>).exporter_subject,
      'owner-1',
    );
    const chain = store.repositories.journal.verifyChain(envelope, sessionId);
    assert.equal(chain.ok, true);

    store.repositories.deleteSession(
      envelopeFromScope(scope, 'owner-1', 'owner', 'delete'),
      sessionId,
    );
    await assert.rejects(
      service.readDeliverable({
        principal,
        deliverable_id: result.artifacts[0].deliverable_id,
      }),
      (error: unknown) => {
        assert.ok(error instanceof ReportExportError);
        assert.equal(error.code, 'EXPORT_SESSION_DELETED');
        return true;
      },
    );
    await assert.rejects(
      service.exportReport({ ...request, request_id: 'req-store-2' }),
      (error: unknown) => {
        assert.ok(error instanceof ReportExportError);
        assert.equal(error.code, 'EXPORT_SESSION_DELETED');
        return true;
      },
    );
  } finally {
    store.close();
  }
});
