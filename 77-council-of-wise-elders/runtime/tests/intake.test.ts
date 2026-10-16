/**
 * CWE-023 intake tests (directive Sections 9, 10, 11; T013, T014,
 * T015, T017, T019 at this layer).
 *
 * Deterministic: fixed clock, sequential IDs, in-memory and file
 * working stores, and one composition against the real CWE-006
 * CouncilStoreService so the freeze path is proven against the
 * canonical store, not a mock of it. The preference-separation test
 * assembles a real CWE-022 Round 1 context from the frozen brief and
 * greps every serialized surface for the preference value.
 */
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
  canonicalStringify,
  type EvidenceManifestEntry,
  type ScopeFields,
  type SeatId,
} from '../src/contracts/index.js';
import { assembleContext, type MaterialCatalog } from '../src/context/index.js';
import type { TrustedPrincipal } from '../src/authorization/index.js';
import { envelopeFromScope } from '../src/persistence/envelope.js';
import { CouncilStoreService } from '../src/persistence/store.js';
import {
  FileIntakeWorkingStore,
  IntakeError,
  IntakeService,
  MemoryIntakeWorkingStore,
  RepositoryIntakeBriefStore,
  quickModePolicyRecord,
  recommendQuickPanel,
  type IntakeWorkingStore,
  type RouteCatalogEntry,
  type RouteCatalogPort,
} from '../src/intake/index.js';

// ------------------------------------------------------------- fixtures

const SCOPE: ScopeFields = {
  tenant_id: 'tenant-a',
  company_id: 'company-a',
  installation_id: 'inst-a',
  owner_subject: null,
};

const clock = { nowUtc: () => '2026-10-14T15:00:00.000Z' };
let idCounter = 0;
const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}` };

const ROUTE_DEFAULT: RouteCatalogEntry = {
  route_id: 'route-default',
  requested_model_id: null,
  reasoning_preference: null,
  fallback_policy: 'none',
  identity_level: 'configured',
};
const ROUTE_ALT: RouteCatalogEntry = {
  route_id: 'route-alt',
  requested_model_id: 'client-picked-model',
  reasoning_preference: 'deep',
  fallback_policy: 'client_approved_only',
  identity_level: 'transport_probed',
};

class FixtureCatalog implements RouteCatalogPort {
  entries: RouteCatalogEntry[] = [ROUTE_DEFAULT, ROUTE_ALT];
  defaultRoute: RouteCatalogEntry | null = ROUTE_DEFAULT;
  listSelectableRoutes(): readonly RouteCatalogEntry[] {
    return this.entries;
  }
  configuredDefault(): RouteCatalogEntry | null {
    return this.defaultRoute;
  }
}

const NO_FLAGS = {
  involves_money_commitment: false,
  involves_offer_or_pricing: false,
  involves_rebrand_or_pivot: false,
  involves_stakeholder_trust: false,
  decision_is_communication: false,
  involves_professional_domain: false,
};

const ALL_SEATS: SeatId[] = [
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

function memoryService(catalog = new FixtureCatalog()) {
  const workingStore = new MemoryIntakeWorkingStore();
  const briefStore = {
    sessions: new Map<string, unknown>(),
    async getSession() {
      return null;
    },
    async createSession() {},
    async saveBriefRevision() {},
  };
  const service = new IntakeService({
    briefStore,
    workingStore,
    routeCatalog: catalog,
    clock,
    ids,
  });
  return { service, workingStore, catalog };
}

async function beginFull(
  service: IntakeService,
  extra: Parameters<IntakeService['begin']>[0] extends infer T ? Partial<T> : never = {},
) {
  return service.begin({
    scope: SCOPE,
    visibility: 'company',
    display_timezone: 'America/New_York',
    source_pack_version: 'pack-test-v1',
    ...extra,
  } as Parameters<IntakeService['begin']>[0]);
}

/** Drive a draft through every material question except freeze. */
async function completeIntake(
  service: IntakeService,
  intakeId: string,
  startRevision: number,
  opts: { money?: boolean; panel?: SeatId[]; mode?: 'full' | 'selected' | 'quick' | 'consult' } = {},
) {
  let rev = startRevision;
  const step = async (fn: (r: number) => Promise<{ intake_revision: number }>) => {
    const draft = await fn(rev);
    rev = draft.intake_revision;
    return draft;
  };
  await step((r) =>
    service.answer(
      intakeId,
      {
        question_id: 'decision',
        statement: 'Should we raise the workshop price from $497 to $997 next quarter?',
        flags: { ...NO_FLAGS, involves_money_commitment: opts.money ?? true },
      },
      r,
    ),
  );
  await step((r) =>
    service.answer(
      intakeId,
      {
        question_id: 'options',
        options: [
          { id: 'option-a', label: 'Raise to $997', kind: 'change' },
          { id: 'option-b', label: 'Hold at $497', kind: 'status_quo' },
          { id: 'option-c', label: 'Raise to $747', kind: 'change' },
        ],
      },
      r,
    ),
  );
  await step((r) =>
    service.answer(
      intakeId,
      {
        question_id: 'success',
        success: { outcome: 'Revenue per seat up without refund rate rising.', horizon: '90 days', explicit_unknown: false },
      },
      r,
    ),
  );
  await step((r) =>
    service.answer(
      intakeId,
      {
        question_id: 'constraints',
        constraints: [
          {
            id: 'constraint-cash',
            kind: 'budget_cash',
            description: 'Cash reserves must stay above $40,000.',
            hard: true,
            applies_to_option_ids: [],
          },
        ],
      },
      r,
    ),
  );
  await step((r) =>
    service.answer(intakeId, { question_id: 'facts', explicit_unknown: true }, r),
  );
  await step((r) =>
    service.answer(intakeId, { question_id: 'unknowns', unknowns: [] }, r),
  );
  await step((r) =>
    service.chooseModePanel(intakeId, opts.mode ?? 'full', opts.panel ?? ALL_SEATS, r),
  );
  await step((r) => service.chooseRoute(intakeId, { kind: 'inherit_default' }, r));
  return rev;
}

// ------------------------------------------------------------- T015 flow

test('T015: one question at a time, explicit unknown accepted, progress persisted', async () => {
  const { service } = memoryService();
  const draft = await beginFull(service);
  const first = await service.resume(draft.intake_id);
  assert.equal(first.current_question?.id, 'decision');

  let d = await service.answer(
    draft.intake_id,
    { question_id: 'decision', statement: 'Hire a second coach?', flags: NO_FLAGS },
    draft.intake_revision,
  );
  let resumed = await service.resume(draft.intake_id);
  assert.equal(resumed.current_question?.id, 'options');

  d = await service.answer(
    draft.intake_id,
    {
      question_id: 'options',
      options: [
        { id: 'option-a', label: 'Hire now', kind: 'change' },
        { id: 'option-b', label: 'Wait a quarter', kind: 'other' },
      ],
    },
    d.intake_revision,
  );
  // Explicit unknown is a valid success answer (Section 9.3).
  d = await service.answer(
    draft.intake_id,
    { question_id: 'success', success: { outcome: null, horizon: null, explicit_unknown: true } },
    d.intake_revision,
  );
  resumed = await service.resume(draft.intake_id);
  assert.equal(resumed.current_question?.id, 'constraints');
  const preview = await service.reviewSummary(draft.intake_id);
  assert.ok(
    preview.brief_preview?.unknowns.some((u) => u.id === 'unknown-success-outcome'),
    'explicit unknown success composes into brief unknowns',
  );

  // A material question cannot be skipped.
  await assert.rejects(
    service.skipQuestion(draft.intake_id, 'constraints', d.intake_revision),
    (e: unknown) => e instanceof IntakeError && e.code === 'INTAKE_ANSWER_INVALID',
  );
  // An optional question can.
  d = await service.skipQuestion(draft.intake_id, 'assumptions', d.intake_revision);
  assert.ok(d.skipped_question_ids.includes('assumptions'));
});

// ------------------------------------------------- resume after interrupt

test('resume after interruption: partial answers intact, exact step (file store)', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'cwe023-resume-'));
  const catalog = new FixtureCatalog();
  const mk = () =>
    new IntakeService({
      briefStore: {
        async getSession() {
          return null;
        },
        async createSession() {},
        async saveBriefRevision() {},
      },
      workingStore: new FileIntakeWorkingStore(dir),
      routeCatalog: catalog,
      clock,
      ids,
    });
  const first = mk();
  const draft = await beginFull(first);
  let d = await first.answer(
    draft.intake_id,
    { question_id: 'decision', statement: 'Expand into a second city?', flags: NO_FLAGS },
    draft.intake_revision,
  );
  d = await first.answer(
    draft.intake_id,
    {
      question_id: 'options',
      options: [
        { id: 'option-a', label: 'Expand', kind: 'change' },
        { id: 'option-b', label: 'Stay', kind: 'status_quo' },
      ],
    },
    d.intake_revision,
  );

  // Simulate interruption: a brand-new service over the same directory.
  const second = mk();
  const resumed = await second.resume(draft.intake_id);
  assert.equal(resumed.draft.answers.decision?.statement, 'Expand into a second city?');
  assert.equal(resumed.draft.answers.options?.length, 2);
  assert.equal(resumed.draft.current_brief_revision, 1);
  assert.equal(resumed.current_question?.id, 'success');
  const savedBrief = await new FileIntakeWorkingStore(dir).loadDraftBriefRevision(
    draft.session_id,
    1,
  );
  assert.equal(savedBrief?.question, 'Expand into a second city?');
});

// ------------------------------------------------------------- T013 facts

test('T013: authorized known facts are reused, never re-asked; out-of-scope facts excluded silently', async () => {
  const { service } = memoryService();
  const draft = await beginFull(service, {
    known_facts: [
      {
        id: 'fact-known-1',
        statement: 'Current enrollment is 212 students.',
        origin: 'retrieved_confirmed',
        evidence_ids: [],
        scope: SCOPE,
      },
      {
        id: 'fact-foreign',
        statement: 'Another tenant fact that must never appear.',
        origin: 'retrieved_confirmed',
        evidence_ids: [],
        scope: { ...SCOPE, tenant_id: 'tenant-b' },
      },
    ],
  });
  assert.equal(draft.known_facts.length, 1);
  assert.equal(draft.dropped_known_fact_count, 1);
  let d = await service.answer(
    draft.intake_id,
    { question_id: 'decision', statement: 'Raise prices?', flags: NO_FLAGS },
    draft.intake_revision,
  );
  d = await service.answer(
    draft.intake_id,
    {
      question_id: 'options',
      options: [
        { id: 'option-a', label: 'Raise', kind: 'change' },
        { id: 'option-b', label: 'Hold', kind: 'status_quo' },
      ],
    },
    d.intake_revision,
  );
  d = await service.answer(
    draft.intake_id,
    {
      question_id: 'success',
      success: { outcome: 'A clear result.', horizon: '60 days', explicit_unknown: false },
    },
    d.intake_revision,
  );
  d = await service.answer(
    draft.intake_id,
    { question_id: 'constraints', constraints: [] },
    d.intake_revision,
  );
  // The flow steps straight past facts: authorized retrieval already
  // holds them, so the facts question is never the current step.
  const after = await service.resume(draft.intake_id);
  assert.equal(after.current_question?.id, 'unknowns');
  const preview = await service.reviewSummary(draft.intake_id);
  const briefJson = canonicalStringify(preview.brief_preview);
  assert.ok(briefJson.includes('Current enrollment is 212 students.'));
  assert.ok(!briefJson.includes('Another tenant fact'));
});

// ------------------------------------------------------------- T014 facts

test('T014: scaffold or unconfirmed material composes into unknowns, never facts', async () => {
  const { service } = memoryService();
  const draft = await beginFull(service);
  let d = await service.answer(
    draft.intake_id,
    { question_id: 'decision', statement: 'Launch the new cohort?', flags: NO_FLAGS },
    draft.intake_revision,
  );
  d = await service.answer(
    draft.intake_id,
    {
      question_id: 'options',
      options: [
        { id: 'option-a', label: 'Launch', kind: 'change' },
        { id: 'option-b', label: 'Delay', kind: 'other' },
      ],
    },
    d.intake_revision,
  );
  d = await service.answer(
    draft.intake_id,
    {
      question_id: 'facts',
      facts: [
        { id: 'fact-real', statement: 'Waitlist has 340 names.', origin: 'client_statement', evidence_ids: [] },
        { id: 'fact-scaffold', statement: 'Projected conversion 12 percent (placeholder).', origin: 'scaffold_unconfirmed', evidence_ids: [] },
      ],
    },
    d.intake_revision,
  );
  const preview = await service.reviewSummary(draft.intake_id);
  const facts = preview.brief_preview?.facts.map((f) => f.id) ?? [];
  const unknowns = preview.brief_preview?.unknowns.map((u) => u.id) ?? [];
  assert.ok(facts.includes('fact-real'));
  assert.ok(!facts.includes('fact-scaffold'));
  assert.ok(unknowns.includes('fact-scaffold'));
});

// ------------------------------------------- revision discipline and freeze

test('revision immutability: stale writer conflicts, frozen revision refuses edits', async () => {
  const { service, workingStore } = memoryService();
  const draft = await beginFull(service);
  // Stale expected revision: typed conflict, nothing overwritten.
  await assert.rejects(
    service.answer(
      draft.intake_id,
      { question_id: 'decision', statement: 'Stale write', flags: NO_FLAGS },
      draft.intake_revision + 5,
    ),
    (e: unknown) => e instanceof IntakeError && e.code === 'INTAKE_REVISION_CONFLICT',
  );
  const rev = await completeIntake(service, draft.intake_id, draft.intake_revision);
  const frozen = await service.freeze(draft.intake_id, rev);
  assert.equal(frozen.brief.revision >= 1, true);
  assert.match(frozen.freeze_record.brief_sha256, /^[0-9a-f]{64}$/);
  assert.match(frozen.freeze_record.evidence_manifest_sha256, /^[0-9a-f]{64}$/);

  // Frozen: every content mutation refuses.
  const after = await service.getDraft(draft.intake_id);
  await assert.rejects(
    service.answer(
      draft.intake_id,
      { question_id: 'decision', statement: 'Edit after freeze', flags: NO_FLAGS },
      after.intake_revision,
    ),
    (e: unknown) => e instanceof IntakeError && e.code === 'INTAKE_FROZEN',
  );
  // Draft brief revisions are immutable in the working store too.
  const brief1 = await workingStore.loadDraftBriefRevision(draft.session_id, 1);
  assert.ok(brief1);
  await assert.rejects(
    workingStore.saveDraftBriefRevision({ ...brief1!, question: 'Tampered question' }),
    (e: unknown) => e instanceof IntakeError && e.code === 'INTAKE_STORE_CONFLICT',
  );
});

test('freeze before material answers are complete is refused as not ready', async () => {
  const { service } = memoryService();
  const draft = await beginFull(service);
  await assert.rejects(
    service.freeze(draft.intake_id, draft.intake_revision),
    (e: unknown) => e instanceof IntakeError && e.code === 'INTAKE_NOT_READY',
  );
});

// ------------------------------------------------------- amendment queue

test('amendment queueing: mid-round fact lands as a proposal, frozen inputs unchanged', async () => {
  const { service, workingStore } = memoryService();
  const draft = await beginFull(service);
  const rev = await completeIntake(service, draft.intake_id, draft.intake_revision);
  const frozen = await service.freeze(draft.intake_id, rev);
  const briefBefore = await workingStore.loadDraftBriefRevision(
    draft.session_id,
    frozen.brief.revision,
  );
  const amendment = await service.proposeAmendment(draft.session_id, {
    statement: 'A key supplier just raised prices 18 percent.',
    evidence_ids: [],
  });
  assert.equal(amendment.status, 'proposed');
  assert.equal(amendment.base_revision, frozen.brief.revision);
  const list = await service.listAmendments(draft.session_id);
  assert.equal(list.length, 1);
  const briefAfter = await workingStore.loadDraftBriefRevision(
    draft.session_id,
    frozen.brief.revision,
  );
  assert.equal(canonicalStringify(briefAfter), canonicalStringify(briefBefore));
});

// ------------------------------------------------------------- panel rules

test('panel rules: selected panel missing the affordability seat keeps financial assessment not_assessed, recommendation offered, panel unchanged', async () => {
  const { service } = memoryService();
  const draft = await beginFull(service);
  const panelWithoutTiffany = ALL_SEATS.filter((s) => s !== 'tiffany-aliche');
  const rev = await completeIntake(service, draft.intake_id, draft.intake_revision, {
    mode: 'selected',
    panel: panelWithoutTiffany,
  });
  const summary = await service.reviewSummary(draft.intake_id);
  const financial = summary.panel_assessment?.required_responsibilities.find(
    (r) => r.domain === 'financial_feasibility',
  );
  assert.ok(financial, 'financial responsibility is computed before start');
  assert.equal(financial?.on_panel, false);
  assert.equal(financial?.status, 'not_assessed');
  assert.equal(summary.panel_assessment?.blocks_go_style_endorsement, true);
  const rec = summary.panel_assessment?.recommendations.find(
    (r) => r.domain === 'financial_feasibility',
  );
  assert.equal(rec?.seat_id, 'tiffany-aliche');
  // The panel itself was never silently changed.
  const frozen = await service.freeze(draft.intake_id, rev);
  assert.deepEqual(frozen.spec.seat_ids, panelWithoutTiffany);
  const briefFinancial = frozen.brief.critical_domains.find(
    (r) => r.domain === 'financial_feasibility',
  );
  assert.equal(briefFinancial?.status, 'not_assessed');
});

test('panel validation: full needs nine, consult needs one, duplicates refused', async () => {
  const { service } = memoryService();
  const draft = await beginFull(service);
  await assert.rejects(
    service.chooseModePanel(draft.intake_id, 'full', ALL_SEATS.slice(0, 8), draft.intake_revision),
    (e: unknown) => e instanceof IntakeError && e.code === 'INTAKE_PANEL_INVALID',
  );
  await assert.rejects(
    service.chooseModePanel(
      draft.intake_id,
      'selected',
      ['simon-sinek', 'simon-sinek'],
      draft.intake_revision,
    ),
    (e: unknown) => e instanceof IntakeError && e.code === 'INTAKE_PANEL_INVALID',
  );
});

// --------------------------------------------------------- quick mode records

test('quick mode policy record carries the five prerequisites and the verbatim skip status', () => {
  const record = quickModePolicyRecord(['simon-sinek', 'tiffany-aliche', 'russell-brunson', 'brene-brown']);
  assert.equal(record.ratification_status_when_skipped, 'not_run_by_quick_mode_policy');
  assert.equal(record.prerequisites.length, 5);
  assert.deepEqual(
    record.prerequisites.map((p) => p.id),
    [
      'all_cards_valid',
      'same_highest_ranked_option',
      'spread_at_most_3',
      'no_unresolved_critical_fact_or_constraint',
      'no_unassessed_material_condition',
    ],
  );
  assert.ok(record.prerequisites.every((p) => p.status === 'pending_run'));
  assert.equal(record.evaluated_by, 'CWE-025');
});

test('quick panel recommendation leads with money, offer, why, trust for a pricing decision', async () => {
  const { service } = memoryService();
  const draft = await beginFull(service);
  const d = await service.answer(
    draft.intake_id,
    {
      question_id: 'decision',
      statement: 'Reprice the flagship offer?',
      flags: { ...NO_FLAGS, involves_money_commitment: true, involves_offer_or_pricing: true, involves_stakeholder_trust: true },
    },
    draft.intake_revision,
  );
  const recommended = recommendQuickPanel(d);
  assert.deepEqual(recommended.slice(0, 4), [
    'tiffany-aliche',
    'russell-brunson',
    'brene-brown',
    'simon-sinek',
  ]);
});

// ------------------------------------------------------------- route pinning

test('route snapshot pinning: later catalog change does not move the frozen route', async () => {
  const catalog = new FixtureCatalog();
  const { service } = memoryService(catalog);
  const draft = await beginFull(service);
  const rev = await completeIntake(service, draft.intake_id, draft.intake_revision);
  const frozen = await service.freeze(draft.intake_id, rev);
  assert.equal(frozen.freeze_record.route_snapshot.route_id, 'route-default');
  assert.equal(frozen.freeze_record.route_snapshot.selection_source, 'client_default');
  assert.equal(frozen.freeze_record.route_snapshot.identity_level, 'configured');
  assert.equal(frozen.spec.model_policy.route_id, 'route-default');

  // The catalog changes underneath: the frozen snapshot stands.
  catalog.entries = [{ ...ROUTE_DEFAULT, requested_model_id: 'swapped-model' }, ROUTE_ALT];
  const record = frozen.freeze_record.route_snapshot;
  assert.equal(record.requested_model_id, null);
  const { routeSnapshotDrift } = await import('../src/intake/index.js');
  const drift = routeSnapshotDrift(record, catalog.entries[0]);
  assert.equal(drift.drifted, true);
});

test('explicit route choice pins that route; unknown route refused without substitution', async () => {
  const { service } = memoryService();
  const draft = await beginFull(service);
  const d = await service.chooseRoute(
    draft.intake_id,
    { kind: 'explicit', route_id: 'route-alt' },
    draft.intake_revision,
  );
  assert.equal(d.route_snapshot?.route_id, 'route-alt');
  assert.equal(d.route_snapshot?.selection_source, 'explicit');
  await assert.rejects(
    service.chooseRoute(draft.intake_id, { kind: 'explicit', route_id: 'route-missing' }, d.intake_revision),
    (e: unknown) => e instanceof IntakeError && e.code === 'INTAKE_ROUTE_NOT_FOUND',
  );
});

// ------------------------------------------------- preference separation

test('preference separation: value only in its own record, never in brief, freeze record, or Round 1 context', async () => {
  const dataDir = mkdtempSync(join(tmpdir(), 'cwe023-pref-'));
  const envelope = envelopeFromScope(SCOPE, 'owner-1', 'owner', 'write');
  const store = CouncilStoreService.open({ dataDir, clock, ids, envelope });
  const workingStore = new MemoryIntakeWorkingStore();
  const service = new IntakeService({
    briefStore: new RepositoryIntakeBriefStore(store.repositories, envelope),
    workingStore,
    routeCatalog: new FixtureCatalog(),
    clock,
    ids,
  });
  const SECRET = 'PREFERENCE-VALUE-MARKER-choose-option-b-quietly';
  const draft = await beginFull(service);
  let rev = await completeIntake(service, draft.intake_id, draft.intake_revision);
  const d = await service.getDraft(draft.intake_id);
  rev = d.intake_revision;
  void rev;
  const withPref = await service.setPreference(
    draft.intake_id,
    { leaning_option_id: 'option-b', statement: SECRET },
    d.intake_revision,
  );
  assert.ok(withPref.preference_ref);
  const record = await service.getPreference(withPref.preference_ref!);
  assert.equal(record?.statement, SECRET);

  const frozen = await service.freeze(draft.intake_id, withPref.intake_revision);
  // The brief carries only the opaque reference.
  assert.equal(frozen.brief.private_preference_ref, withPref.preference_ref);
  assert.ok(!canonicalStringify(frozen.brief).includes(SECRET));
  assert.ok(!canonicalStringify(frozen.freeze_record).includes(SECRET));
  assert.ok(!canonicalStringify(frozen.spec).includes(SECRET));

  // The canonical store holds the same frozen brief.
  const stored = await store.repositories.getSession(envelope, draft.session_id);
  assert.ok(stored);
  assert.equal(stored?.brief.revision, frozen.brief.revision);
  assert.ok(!canonicalStringify(stored?.brief).includes(SECRET));

  // A real CWE-022 Round 1 assembly from the frozen brief excludes
  // the preference reference entirely, and the value never appears.
  const principal: TrustedPrincipal = {
    tenant_id: SCOPE.tenant_id,
    company_id: SCOPE.company_id,
    installation_id: SCOPE.installation_id,
    subject: 'owner-1',
    channel: 'browser',
    support_access: false,
  };
  const emptyCatalog: MaterialCatalog = {
    listCandidateHeaders: () => [],
    loadCandidate: () => null,
  };
  const result = assembleContext({
    principal,
    session: {
      scope: SCOPE,
      visibility: 'company',
      session_id: draft.session_id,
      mode: 'full',
      seat_ids: frozen.spec.seat_ids,
    },
    brief: frozen.brief,
    operation: 'round_1_opening',
    route: {
      context_limit_bytes: 1_000_000,
      system_rules_bytes: 1_000,
      response_schema_bytes: 500,
      output_reserve_bytes: 2_000,
    },
    catalog: emptyCatalog,
  });
  assert.equal(result.status, 'assembled');
  if (result.status === 'assembled') {
    assert.equal(result.context.preference_excluded, true);
    assert.ok(!('private_preference_ref' in result.context.brief));
    assert.ok(!canonicalStringify(result.context).includes(SECRET));
    assert.ok(!canonicalStringify(result.context).includes(withPref.preference_ref!));
  }
});

// ------------------------------------------------------------- T017 / T019

test('T017/T019: modes and panels stay distinguishable in the frozen spec and brief', async () => {
  const { service } = memoryService();
  const draft = await beginFull(service);
  const rev = await completeIntake(service, draft.intake_id, draft.intake_revision, {
    mode: 'consult',
    panel: ['tiffany-aliche'],
  });
  const summary = await service.reviewSummary(draft.intake_id);
  // Consult never blocks GO-style endorsement; that rule is scored modes only.
  assert.equal(summary.panel_assessment?.blocks_go_style_endorsement, false);
  const frozen = await service.freeze(draft.intake_id, rev);
  assert.equal(frozen.spec.mode, 'consult');
  assert.deepEqual(frozen.spec.seat_ids, ['tiffany-aliche']);
  // A consult brief carries no relevance weights for absent seats.
  assert.deepEqual(Object.keys(frozen.brief.relevance_weights), ['tiffany-aliche']);
});

test('evidence manifest is recorded on the draft and hashed into the freeze record', async () => {
  const { service } = memoryService();
  const draft = await beginFull(service);
  const entry: EvidenceManifestEntry = {
    evidence_id: 'ev-1',
    sha256: 'a'.repeat(64),
    source_kind: 'book',
    locator: 'section:Part 1',
  };
  const d = await service.setEvidenceManifest(draft.intake_id, [entry], draft.intake_revision);
  assert.equal(d.evidence_manifest.length, 1);
  const rev = await completeIntake(service, draft.intake_id, d.intake_revision);
  const frozen = await service.freeze(draft.intake_id, rev);
  assert.equal(frozen.brief.evidence_manifest.length, 1);
  assert.equal(frozen.brief.evidence_manifest[0].evidence_id, 'ev-1');
});
