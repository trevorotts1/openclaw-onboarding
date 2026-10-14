/**
 * CWE-022 tests: authorized retrieval and bounded context assembly
 * (directive Sections 8, 9, 13).
 *
 * Acceptance proofs in this file:
 * - a denied caller never touches the catalog (session gate first);
 * - cross-tenant and cross-company material cannot appear in output,
 *   counts, digests, or error text, and its content is never loaded;
 * - private material requires its owner; company scope alone never
 *   retrieves it; user_private sources are owner-only and never enter
 *   a distributable assembly (CWE-012 condition 3);
 * - revoked sources are excluded (Section 8.6); only frozen-manifest
 *   evidence with a matching canonical hash is admitted;
 * - assembly fits a small synthetic limit exactly, respects item
 *   boundaries, returns the typed CONTEXT_TOO_SMALL readiness result
 *   when the minimum cannot fit, and is deterministic (byte-identical
 *   payload, equal content hash);
 * - provenance labels survive end to end, never upgraded;
 * - client_preference_private is never part of Round 1 context, while
 *   legitimate values and constraints are.
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  canonicalHash,
  canonicalStringify,
  type DecisionBrief,
  type EvidenceManifestEntry,
  type ScopeFields,
  type SeatId,
} from '../src/contracts/index.js';
import {
  AuthorizationError,
  type TrustedPrincipal,
} from '../src/authorization/index.js';
import type {
  EvidenceUnit,
  SourceRecord,
} from '../src/sources/index.js';
import {
  assembleContext,
  retrieveAuthorizedMaterial,
  verifyContextHash,
  assertPackagesValid,
  ContextError,
  type AssembleContextRequest,
  type CandidateHeader,
  type MaterialCandidate,
  type MaterialCatalog,
} from '../src/context/index.js';

// ------------------------------------------------------------- fixtures

const TENANT = 'tenant-a';
const COMPANY = 'company-a';
const INSTALL = 'inst-a';
const OWNER = 'owner-1';

const COMPANY_SCOPE: ScopeFields = {
  tenant_id: TENANT,
  company_id: COMPANY,
  installation_id: INSTALL,
  owner_subject: null,
};
const OWNER_SCOPE: ScopeFields = { ...COMPANY_SCOPE, owner_subject: OWNER };

function principal(overrides: Partial<TrustedPrincipal> = {}): TrustedPrincipal {
  return {
    tenant_id: TENANT,
    company_id: COMPANY,
    installation_id: INSTALL,
    subject: OWNER,
    channel: 'browser',
    support_access: false,
    ...overrides,
  };
}

function source(overrides: Partial<SourceRecord> = {}): SourceRecord {
  return {
    source_id: 'src-sinek-start-with-why',
    work_id: 'work-start-with-why',
    work_title: 'Start with Why',
    credited_authors: ['Simon Sinek'],
    original_speaker: 'Simon Sinek',
    source_type: 'book',
    publisher_or_host: 'Portfolio',
    edition_or_publication_date: '2009',
    retrieved_at: '2026-10-14T00:00:00Z',
    canonical_url: null,
    private_asset_id: null,
    content_sha256: canonicalHash({ record: 'start-with-why' }),
    rights_status: 'reference_only',
    allowed_scope: 'shared_pack',
    locators: [{ kind: 'section', value: 'Part 1' }],
    quality: 'unverified',
    ...overrides,
  };
}

function unit(
  src: SourceRecord,
  overrides: Partial<EvidenceUnit> = {},
): EvidenceUnit {
  return {
    evidence_id: 'ev-sinek-why-1',
    source_id: src.source_id,
    source_version: src.version ?? src.content_sha256,
    locator: { kind: 'section', value: 'Part 1, Chapter 1' },
    kind: 'concept',
    mark: 'direct_teaching',
    original_speaker: 'Simon Sinek',
    excerpt: null,
    paraphrase: 'Leaders who start with why inspire action.',
    claim_ids: ['claim-why-1'],
    seat_id: 'simon-sinek',
    ...overrides,
  };
}

function candidate(
  src: SourceRecord,
  evidenceUnit: EvidenceUnit,
  scope: ScopeFields = COMPANY_SCOPE,
  visibility: 'company' | 'private' = 'company',
): MaterialCandidate {
  const header: CandidateHeader = {
    evidence_id: evidenceUnit.evidence_id,
    seat_id: evidenceUnit.seat_id,
    scope,
    visibility,
    source_id: src.source_id,
    allowed_scope: src.allowed_scope,
    sha256: canonicalHash(evidenceUnit),
  };
  return { header, source: src, unit: evidenceUnit };
}

class SpyCatalog implements MaterialCatalog {
  listCalls = 0;
  readonly loadedIds: string[] = [];
  constructor(private readonly candidates: readonly MaterialCandidate[]) {}
  listCandidateHeaders(): readonly CandidateHeader[] {
    this.listCalls += 1;
    return this.candidates.map((c) => c.header);
  }
  loadCandidate(evidenceId: string): MaterialCandidate | null {
    this.loadedIds.push(evidenceId);
    return this.candidates.find((c) => c.header.evidence_id === evidenceId) ?? null;
  }
}

function manifestOf(...candidates: MaterialCandidate[]): EvidenceManifestEntry[] {
  return candidates.map((c) => ({
    evidence_id: c.unit.evidence_id,
    sha256: c.header.sha256,
    source_kind: 'book' as const,
    locator: `${c.unit.locator.kind}:${c.unit.locator.value}`,
  }));
}

const PREFERENCE_REF = 'pref-marker-ref-99';

function brief(manifest: EvidenceManifestEntry[]): DecisionBrief {
  return {
    schema_version: 'wise-elders.brief/v1',
    brief_id: 'brief-1',
    session_id: 'session-1',
    revision: 1,
    question: 'Should we expand the workshop program next quarter?',
    facts: [
      { id: 'fact-1', statement: 'Current workshops run at full capacity.', evidence_ids: [] },
    ],
    assumptions: [],
    unknowns: [],
    constraints: [
      {
        id: 'constraint-1',
        description: 'Expansion must not exceed the approved budget.',
        hard: true,
        applies_to_option_ids: ['option-a'],
      },
    ],
    options: [
      { id: 'option-a', label: 'Expand', kind: 'change' },
      { id: 'option-b', label: 'Hold', kind: 'status_quo' },
    ],
    relevance_weights: {},
    critical_domains: [],
    evidence_manifest: manifest,
    private_preference_ref: PREFERENCE_REF,
    created_at: '2026-10-14T00:00:00Z',
    display_timezone: 'America/New_York',
  };
}

const BIG_ROUTE = {
  context_limit_bytes: 1_000_000,
  system_rules_bytes: 1_000,
  response_schema_bytes: 500,
  output_reserve_bytes: 2_000,
};

function assembleRequest(
  overrides: Partial<AssembleContextRequest> = {},
): AssembleContextRequest {
  const sinekSource = source();
  const sinekUnit = unit(sinekSource);
  const sinek = candidate(sinekSource, sinekUnit);
  return {
    principal: principal(),
    session: {
      scope: COMPANY_SCOPE,
      visibility: 'company',
      session_id: 'session-1',
      mode: 'selected',
      seat_ids: ['simon-sinek'],
    },
    brief: brief(manifestOf(sinek)),
    operation: 'round_2_response',
    route: BIG_ROUTE,
    catalog: new SpyCatalog([sinek]),
    ...overrides,
  };
}

// ------------------------------------------------------- session gate

test('session gate: cross-tenant principal is denied before the catalog is touched', () => {
  const catalog = new SpyCatalog([]);
  assert.throws(
    () =>
      retrieveAuthorizedMaterial({
        principal: principal({ tenant_id: 'tenant-b' }),
        session: { scope: COMPANY_SCOPE, visibility: 'company' },
        manifest: [],
        catalog,
      }),
    (error: unknown) =>
      error instanceof AuthorizationError && error.code === 'COUNCIL_CROSS_SCOPE',
  );
  assert.equal(catalog.listCalls, 0);
  assert.deepEqual(catalog.loadedIds, []);
});

test('session gate: private session requires its owner, company membership is not enough', () => {
  const catalog = new SpyCatalog([]);
  assert.throws(
    () =>
      retrieveAuthorizedMaterial({
        principal: principal({ subject: 'teammate-1' }),
        session: { scope: OWNER_SCOPE, visibility: 'private' },
        manifest: [],
        catalog,
      }),
    (error: unknown) =>
      error instanceof AuthorizationError &&
      error.code === 'COUNCIL_PRIVATE_OWNER_REQUIRED',
  );
  assert.equal(catalog.listCalls, 0);
});

test('session gate: host-granted support read of a private session is reported as support', () => {
  const result = retrieveAuthorizedMaterial({
    principal: principal({ subject: 'support-1', support_access: true }),
    session: { scope: OWNER_SCOPE, visibility: 'private' },
    manifest: [],
    catalog: new SpyCatalog([]),
  });
  assert.equal(result.access_via, 'support');
  assert.deepEqual(result.items, []);
});

// ---------------------------------------------------- scope negatives

function foreignCandidate(
  scopeOverrides: Partial<ScopeFields>,
  seatId: SeatId = 'simon-sinek',
): MaterialCandidate {
  const src = source({
    source_id: 'src-foreign-1',
    work_id: 'work-foreign-1',
    work_title: 'ZZFOREIGNZZ Title',
    content_sha256: canonicalHash({ record: 'foreign' }),
  });
  const evidenceUnit = unit(src, {
    evidence_id: 'ev-foreign-1',
    paraphrase: 'ZZFOREIGNZZ secret content',
    seat_id: seatId,
  });
  return candidate(src, evidenceUnit, { ...COMPANY_SCOPE, ...scopeOverrides });
}

test('cross-tenant material never appears in output, counts, digests, or loads', () => {
  const mine = candidate(source(), unit(source()));
  const foreign = foreignCandidate({ tenant_id: 'tenant-b' });
  const catalog = new SpyCatalog([mine, foreign]);
  const result = retrieveAuthorizedMaterial({
    principal: principal(),
    session: { scope: COMPANY_SCOPE, visibility: 'company' },
    // Worst case: the frozen manifest names the foreign evidence too.
    manifest: manifestOf(mine, foreign),
    catalog,
  });
  assert.deepEqual(result.items.map((i) => i.evidence_id), ['ev-sinek-why-1']);
  assert.deepEqual(Object.keys(result).sort(), ['access_via', 'items']);
  const serialized = canonicalStringify(result);
  assert.ok(!serialized.includes('ZZFOREIGNZZ'));
  assert.ok(!serialized.includes('ev-foreign-1'));
  assert.ok(!serialized.includes('src-foreign-1'));
  assert.ok(!serialized.includes(foreign.header.sha256));
  assert.deepEqual(catalog.loadedIds, ['ev-sinek-why-1']);
});

test('cross-company material never appears in output or loads', () => {
  const mine = candidate(source(), unit(source()));
  const foreign = foreignCandidate({ company_id: 'company-b' });
  const catalog = new SpyCatalog([foreign, mine]);
  const result = retrieveAuthorizedMaterial({
    principal: principal(),
    session: { scope: COMPANY_SCOPE, visibility: 'company' },
    manifest: manifestOf(mine, foreign),
    catalog,
  });
  assert.deepEqual(result.items.map((i) => i.evidence_id), ['ev-sinek-why-1']);
  assert.ok(!canonicalStringify(result).includes('ZZFOREIGNZZ'));
  assert.deepEqual(catalog.loadedIds, ['ev-sinek-why-1']);
});

test('private material without owner access is never loaded; the owner retrieves it', () => {
  const privateScope: ScopeFields = { ...COMPANY_SCOPE, owner_subject: 'owner-2' };
  const src = source();
  const privateItem = candidate(src, unit(src), privateScope, 'private');
  const manifest = manifestOf(privateItem);

  const catalog = new SpyCatalog([privateItem]);
  const asOther = retrieveAuthorizedMaterial({
    principal: principal({ subject: OWNER }),
    session: { scope: COMPANY_SCOPE, visibility: 'company' },
    manifest,
    catalog,
  });
  assert.deepEqual(asOther.items, []);
  assert.deepEqual(catalog.loadedIds, []);

  const asOwner = retrieveAuthorizedMaterial({
    principal: principal({ subject: 'owner-2' }),
    session: { scope: COMPANY_SCOPE, visibility: 'company' },
    manifest,
    catalog: new SpyCatalog([privateItem]),
  });
  assert.equal(asOwner.items.length, 1);
});

test('user_private source scope is owner-only even inside a company session', () => {
  const src = source({ allowed_scope: 'user_private' });
  const theirsScope: ScopeFields = { ...COMPANY_SCOPE, owner_subject: 'owner-2' };
  const item = candidate(src, unit(src), theirsScope, 'company');
  const manifest = manifestOf(item);
  const result = retrieveAuthorizedMaterial({
    principal: principal({ subject: OWNER }),
    session: { scope: COMPANY_SCOPE, visibility: 'company' },
    manifest,
    catalog: new SpyCatalog([item]),
  });
  assert.deepEqual(result.items, []);
  const asOwner = retrieveAuthorizedMaterial({
    principal: principal({ subject: 'owner-2' }),
    session: { scope: COMPANY_SCOPE, visibility: 'company' },
    manifest,
    catalog: new SpyCatalog([item]),
  });
  assert.equal(asOwner.items.length, 1);
});

test('revoked sources are excluded from retrieval (Section 8.6)', () => {
  const mine = candidate(source(), unit(source()));
  const result = retrieveAuthorizedMaterial({
    principal: principal(),
    session: { scope: COMPANY_SCOPE, visibility: 'company' },
    manifest: manifestOf(mine),
    catalog: new SpyCatalog([mine]),
    options: { revokedSourceIds: new Set(['src-sinek-start-with-why']) },
  });
  assert.deepEqual(result.items, []);
});

test('evidence outside the frozen manifest, or with a mismatched hash, is not admitted', () => {
  const mine = candidate(source(), unit(source()));
  const notInManifest = retrieveAuthorizedMaterial({
    principal: principal(),
    session: { scope: COMPANY_SCOPE, visibility: 'company' },
    manifest: [],
    catalog: new SpyCatalog([mine]),
  });
  assert.deepEqual(notInManifest.items, []);
  const wrongHash = retrieveAuthorizedMaterial({
    principal: principal(),
    session: { scope: COMPANY_SCOPE, visibility: 'company' },
    manifest: [{ ...manifestOf(mine)[0], sha256: canonicalHash({ other: 'x' }) }],
    catalog: new SpyCatalog([mine]),
  });
  assert.deepEqual(wrongHash.items, []);
});

test('a tampered admitted candidate fails with a generic error carrying no item data', () => {
  const src = source();
  const good = unit(src);
  const tampered = candidate(
    src,
    { ...good, paraphrase: 'ZZTAMPERZZ rewritten after hashing' },
  );
  // Header hash is computed over the ORIGINAL unit; the catalog returns
  // a different unit under the same header.
  const lying: MaterialCandidate = {
    header: candidate(src, good).header,
    source: src,
    unit: tampered.unit,
  };
  assert.throws(
    () =>
      retrieveAuthorizedMaterial({
        principal: principal(),
        session: { scope: COMPANY_SCOPE, visibility: 'company' },
        manifest: manifestOf(candidate(src, good)),
        catalog: new SpyCatalog([lying]),
      }),
    (error: unknown) => {
      assert.ok(error instanceof ContextError);
      assert.equal(error.code, 'CONTEXT_CANDIDATE_INVALID');
      assert.ok(!error.message.includes('ZZTAMPERZZ'));
      assert.ok(!error.message.includes('ev-sinek-why-1'));
      return true;
    },
  );
});

// ------------------------------------------------- distributable bar

function brunsonPrivateCandidate(): MaterialCandidate {
  const src = source({
    source_id: 'src-brunson-nms',
    work_id: 'work-nms',
    work_title: 'Network Marketing Secrets',
    credited_authors: ['Russell Brunson'],
    original_speaker: 'Russell Brunson',
    content_sha256: canonicalHash({ record: 'nms' }),
    allowed_scope: 'user_private',
    quality: 'unverified',
  });
  const evidenceUnit = unit(src, {
    evidence_id: 'ev-brunson-nms-1',
    seat_id: 'russell-brunson',
    original_speaker: 'Russell Brunson',
    paraphrase: 'Private seat material.',
  });
  const scope: ScopeFields = { ...COMPANY_SCOPE, owner_subject: OWNER };
  return candidate(src, evidenceUnit, scope, 'company');
}

test('user_private Brunson material is barred from distributable assemblies', () => {
  const brunson = brunsonPrivateCandidate();
  const request = assembleRequest({
    session: {
      scope: COMPANY_SCOPE,
      visibility: 'company',
      session_id: 'session-1',
      mode: 'selected',
      seat_ids: ['russell-brunson'],
    },
    brief: brief(manifestOf(brunson)),
    catalog: new SpyCatalog([brunson]),
    distributable: true,
  });
  const distributed = assembleContext(request);
  assert.equal(distributed.status, 'assembled');
  if (distributed.status === 'assembled') {
    assert.equal(distributed.context.distributable, true);
    assert.deepEqual(distributed.context.items, []);
    assert.ok(!canonicalStringify(distributed.context).includes('ev-brunson-nms-1'));
  }
  const internal = assembleContext({ ...request, distributable: false });
  assert.equal(internal.status, 'assembled');
  if (internal.status === 'assembled') {
    assert.equal(internal.context.items.length, 1);
    assert.equal(internal.context.items[0].provenance.allowed_scope, 'user_private');
  }
});

// --------------------------------------------------------- provenance

test('provenance labels are preserved end to end and never upgraded', () => {
  const cases: Array<{
    quality: SourceRecord['quality'];
    verification: 'verified' | 'unverified';
  }> = [
    { quality: 'unverified', verification: 'unverified' },
    { quality: 'bibliographic_only', verification: 'unverified' },
    { quality: 'secondary', verification: 'unverified' },
    { quality: 'primary_substantive', verification: 'verified' },
  ];
  for (const { quality, verification } of cases) {
    const src = source({ quality });
    const item = candidate(src, unit(src));
    const result = assembleContext(
      assembleRequest({
        brief: brief(manifestOf(item)),
        catalog: new SpyCatalog([item]),
      }),
    );
    assert.equal(result.status, 'assembled');
    if (result.status !== 'assembled') continue;
    const [assembled] = result.context.items;
    assert.equal(assembled.provenance.quality, quality);
    assert.equal(assembled.provenance.verification_status, verification);
    assert.equal(assembled.provenance.source_id, 'src-sinek-start-with-why');
    assert.equal(assembled.provenance.source_version, src.content_sha256);
    assert.deepEqual(assembled.provenance.locator, {
      kind: 'section',
      value: 'Part 1, Chapter 1',
    });
    assert.equal(assembled.provenance.rights_status, 'reference_only');
    // The frozen manifest entry survives into the assembly unchanged.
    assert.deepEqual(result.context.evidence_manifest, manifestOf(item));
    assert.ok(verifyContextHash(result.context));
  }
});

// ------------------------------------------------------ fit and bounds

function twoItemSetup() {
  const src = source();
  const unit1 = unit(src);
  const unit2 = unit(src, {
    evidence_id: 'ev-sinek-why-2',
    paraphrase: 'People do not buy products; they buy why the product exists.',
    locator: { kind: 'section', value: 'Part 2, Chapter 3' },
  });
  const c1 = candidate(src, unit1);
  const c2 = candidate(src, unit2);
  return { c1, c2, manifest: manifestOf(c1, c2) };
}

test('assembly fits a small synthetic limit exactly and respects item boundaries', () => {
  const { c1, c2, manifest } = twoItemSetup();
  const full = assembleContext(
    assembleRequest({ brief: brief(manifest), catalog: new SpyCatalog([c1, c2]) }),
  );
  assert.equal(full.status, 'assembled');
  if (full.status !== 'assembled') return;
  assert.equal(full.context.items.length, 2);

  // Exact fit: budget equals the measured payload, byte for byte.
  const reserves =
    BIG_ROUTE.system_rules_bytes +
    BIG_ROUTE.response_schema_bytes +
    BIG_ROUTE.output_reserve_bytes;
  const exact = assembleContext(
    assembleRequest({
      brief: brief(manifest),
      catalog: new SpyCatalog([c1, c2]),
      route: { ...BIG_ROUTE, context_limit_bytes: full.byte_length + reserves },
    }),
  );
  assert.equal(exact.status, 'assembled');
  if (exact.status === 'assembled') {
    assert.equal(exact.byte_length, exact.budget_bytes);
    assert.equal(exact.byte_length, full.byte_length);
  }

  // One byte less: the discretionary item is dropped whole, never cut.
  const tighter = assembleContext(
    assembleRequest({
      brief: brief(manifest),
      catalog: new SpyCatalog([c1, c2]),
      route: { ...BIG_ROUTE, context_limit_bytes: full.byte_length + reserves - 1 },
    }),
  );
  assert.equal(tighter.status, 'assembled');
  if (tighter.status === 'assembled') {
    assert.equal(tighter.context.items.length, 1);
    assert.equal(tighter.context.items[0].text, c1.unit.paraphrase);
    assert.ok(tighter.byte_length <= tighter.budget_bytes);
  }
});

test('seat input budgets cap discretionary items for that seat only', () => {
  const { c1, c2, manifest } = twoItemSetup();
  const result = assembleContext(
    assembleRequest({
      brief: brief(manifest),
      catalog: new SpyCatalog([c1, c2]),
      seat_budgets: { 'simon-sinek': 1 },
    }),
  );
  assert.equal(result.status, 'assembled');
  if (result.status === 'assembled') {
    // The mandatory first item stays; the second exceeds the seat cap.
    assert.deepEqual(result.context.items.map((i) => i.evidence_id), ['ev-sinek-why-1']);
  }
});

test('CONTEXT_TOO_SMALL when the minimum valid brief plus pack cannot fit', () => {
  const sinekSrc = source();
  const sinek = candidate(sinekSrc, unit(sinekSrc));
  const brunsonSrc = source({
    source_id: 'src-brunson-tfs',
    work_id: 'work-traffic-secrets',
    work_title: 'Traffic Secrets',
    credited_authors: ['Russell Brunson'],
    original_speaker: 'Russell Brunson',
    content_sha256: canonicalHash({ record: 'traffic' }),
  });
  const brunson = candidate(
    brunsonSrc,
    unit(brunsonSrc, {
      evidence_id: 'ev-brunson-tfs-1',
      seat_id: 'russell-brunson',
      original_speaker: 'Russell Brunson',
    }),
  );
  const manifest = manifestOf(sinek, brunson);
  const reserves =
    BIG_ROUTE.system_rules_bytes +
    BIG_ROUTE.response_schema_bytes +
    BIG_ROUTE.output_reserve_bytes;

  const fullSession: AssembleContextRequest['session'] = {
    scope: COMPANY_SCOPE,
    visibility: 'company',
    session_id: 'session-1',
    mode: 'selected',
    seat_ids: ['simon-sinek', 'russell-brunson'],
  };
  const fullMin = assembleContext(
    assembleRequest({ session: fullSession, brief: brief(manifest), catalog: new SpyCatalog([sinek, brunson]) }),
  );
  assert.equal(fullMin.status, 'assembled');
  if (fullMin.status !== 'assembled') return;

  const consultSession: AssembleContextRequest['session'] = {
    ...fullSession,
    mode: 'consult',
    seat_ids: ['simon-sinek'],
  };
  const consultMin = assembleContext(
    assembleRequest({ session: consultSession, brief: brief(manifest), catalog: new SpyCatalog([sinek, brunson]) }),
  );
  assert.equal(consultMin.status, 'assembled');
  if (consultMin.status !== 'assembled') return;
  assert.ok(consultMin.byte_length < fullMin.byte_length);

  // Budget fits the consult minimum exactly but not the selected-mode
  // minimum: typed readiness result, consult offered, nothing shrunk.
  const tooSmall = assembleContext(
    assembleRequest({
      session: fullSession,
      brief: brief(manifest),
      catalog: new SpyCatalog([sinek, brunson]),
      route: { ...BIG_ROUTE, context_limit_bytes: consultMin.byte_length + reserves },
    }),
  );
  assert.equal(tooSmall.status, 'context_too_small');
  if (tooSmall.status === 'context_too_small') {
    assert.equal(tooSmall.readiness, 'CONTEXT_TOO_SMALL');
    assert.equal(tooSmall.mode, 'selected');
    assert.equal(tooSmall.minimum_required_bytes, fullMin.byte_length);
    assert.equal(tooSmall.available_bytes, consultMin.byte_length);
    assert.deepEqual(tooSmall.supported_lower_context_modes, ['consult']);
  }

  // A budget below even the brief alone offers no lower mode.
  const hopeless = assembleContext(
    assembleRequest({
      session: fullSession,
      brief: brief(manifest),
      catalog: new SpyCatalog([sinek, brunson]),
      route: { ...BIG_ROUTE, context_limit_bytes: reserves + 10 },
    }),
  );
  assert.equal(hopeless.status, 'context_too_small');
  if (hopeless.status === 'context_too_small') {
    assert.deepEqual(hopeless.supported_lower_context_modes, []);
  }
});

// -------------------------------------------------------- determinism

test('assembly is deterministic: byte-identical payload and equal hash across runs and catalog orderings', () => {
  const { c1, c2, manifest } = twoItemSetup();
  const first = assembleContext(
    assembleRequest({ brief: brief(manifest), catalog: new SpyCatalog([c1, c2]) }),
  );
  const second = assembleContext(
    assembleRequest({ brief: brief(manifest), catalog: new SpyCatalog([c2, c1]) }),
  );
  assert.equal(first.status, 'assembled');
  assert.equal(second.status, 'assembled');
  if (first.status === 'assembled' && second.status === 'assembled') {
    assert.equal(canonicalStringify(first.context), canonicalStringify(second.context));
    assert.equal(first.context_sha256, second.context_sha256);
    assert.equal(first.byte_length, second.byte_length);
  }
});

// --------------------------------------------------- preference rule

test('Round 1 context excludes the private preference; values and constraints remain', () => {
  const round1 = assembleContext(assembleRequest({ operation: 'round_1_opening' }));
  assert.equal(round1.status, 'assembled');
  if (round1.status !== 'assembled') return;
  const serialized = canonicalStringify(round1.context);
  assert.ok(!serialized.includes(PREFERENCE_REF));
  assert.ok(!('private_preference_ref' in round1.context.brief));
  assert.equal(round1.context.preference_excluded, true);
  // Legitimate values and constraints are brief content and stay.
  assert.ok(serialized.includes('must not exceed the approved budget'));
  assert.ok(serialized.includes('Should we expand the workshop program'));

  const round2 = assembleContext(assembleRequest({ operation: 'round_2_response' }));
  assert.equal(round2.status, 'assembled');
  if (round2.status === 'assembled') {
    assert.equal(round2.context.preference_excluded, false);
    assert.equal(round2.context.brief.private_preference_ref, PREFERENCE_REF);
  }
});

// ---------------------------------------------------- package preflight

test('package preflight runs the CWE-012 validator and fails generically', () => {
  const src = source();
  const evidenceUnit = unit(src);
  assertPackagesValid([
    { seat_id: 'simon-sinek', pack_version: 'v1', sources: [src], evidence: [evidenceUnit] },
  ]);
  const orphan = unit(src, { evidence_id: 'ev-orphan-1', source_id: 'src-not-carried' });
  assert.throws(
    () =>
      assertPackagesValid([
        { seat_id: 'simon-sinek', pack_version: 'v1', sources: [src], evidence: [orphan] },
      ]),
    (error: unknown) => {
      assert.ok(error instanceof ContextError);
      assert.equal(error.code, 'CONTEXT_PACKAGE_INVALID');
      assert.ok(!error.message.includes('src-not-carried'));
      return true;
    },
  );
});
