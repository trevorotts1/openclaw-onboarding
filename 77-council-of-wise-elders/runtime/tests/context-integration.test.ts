/**
 * CWE-022 integration tests: composition with the real CWE-006 scoped
 * store, and retrieval behavior against the real CWE-011 export data.
 *
 * Store proof: a session created in the real CouncilStoreService is
 * assembled from its stored frozen brief and scope; a principal from
 * another tenant is stopped by the CWE-007 gate; an unknown session
 * fails closed with CONTEXT_SESSION_UNAVAILABLE.
 *
 * Real-data proof: the actual CWE-011 russell-brunson export package.
 * Its records carry export-only fields beyond the Section 8.3 contract
 * (the CWE-012 condition 4 drift, reconciled by the integration
 * runner's adapter at CWE-050), so this test extracts the canonical
 * Section 8.3 subset, exactly as that adapter will, and proves: the
 * Network Marketing Secrets record is user_private, parses under the
 * real CWE-012 schema, and is barred from a distributable assembly
 * while remaining retrievable by its owner in a non-distributable one.
 * The other six records do not parse as exported: every one of them
 * lacks a retrieved_at stamp, and the two absent-work records (DotCom
 * Secrets, Expert Secrets, the D-008 supply gaps) also lack a content
 * hash. The test pins that drift field by field instead of papering
 * over it; stamping honest values is the exporter's v2 work, not
 * something an adapter may invent.
 */
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import {
  canonicalHash,
  type DecisionBrief,
  type EvidenceManifestEntry,
  type ScopeFields,
  type SessionStateRecord,
  type SessionSpec,
} from '../src/contracts/index.js';
import type { StoredSession } from '../src/cli/host-ports.js';
import type { TrustedPrincipal } from '../src/authorization/index.js';
import { envelopeFromScope } from '../src/persistence/envelope.js';
import { CouncilStoreService } from '../src/persistence/store.js';
import { sourceRecordSchema, type SourceRecord } from '../src/sources/index.js';
import {
  assembleContext,
  assembleStoredSessionContext,
  ContextError,
  type CandidateHeader,
  type MaterialCandidate,
  type MaterialCatalog,
} from '../src/context/index.js';

// ------------------------------------------------------------- fixtures

const SCOPE: ScopeFields = {
  tenant_id: 'tenant-a',
  company_id: 'company-a',
  installation_id: 'inst-a',
  owner_subject: null,
};
const clock = { nowUtc: () => '2026-10-14T12:00:00.000Z' };
let idCounter = 0;
const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}` };

function tempDir(label: string): string {
  return mkdtempSync(join(tmpdir(), `cwe022-${label}-`));
}

const UNIT_TEXT = 'Leaders who start with why inspire action.';

function manifestEntry(): EvidenceManifestEntry {
  return {
    evidence_id: 'ev-sinek-why-1',
    sha256: canonicalHash(unitFixture()),
    source_kind: 'book',
    locator: 'section:Part 1, Chapter 1',
  };
}

function unitFixture() {
  return {
    evidence_id: 'ev-sinek-why-1',
    source_id: 'src-sinek-start-with-why',
    source_version: canonicalHash({ record: 'start-with-why' }),
    locator: { kind: 'section' as const, value: 'Part 1, Chapter 1' },
    kind: 'concept' as const,
    mark: 'direct_teaching' as const,
    original_speaker: 'Simon Sinek',
    excerpt: null,
    paraphrase: UNIT_TEXT,
    claim_ids: ['claim-why-1'],
    seat_id: 'simon-sinek' as const,
  };
}

function storedSession(): StoredSession {
  const brief: DecisionBrief = {
    schema_version: 'wise-elders.brief/v1',
    brief_id: 'brief-1',
    session_id: 'session-ctx-1',
    revision: 1,
    question: 'Should we expand the workshop program next quarter?',
    facts: [],
    assumptions: [],
    unknowns: [],
    constraints: [],
    options: [{ id: 'option-a', label: 'Expand', kind: 'change' }],
    relevance_weights: {},
    critical_domains: [],
    evidence_manifest: [manifestEntry()],
    private_preference_ref: null,
    created_at: '2026-10-14T00:00:00Z',
    display_timezone: 'America/New_York',
  };
  const spec: SessionSpec = {
    schema_version: 'wise-elders.session/v1',
    session_id: 'session-ctx-1',
    mode: 'consult',
    visibility: 'company',
    brief_revision: 1,
    brief_sha256: canonicalHash(brief),
    options: brief.options,
    seat_ids: ['simon-sinek'],
    model_policy: {
      selection: 'client_default',
      route_id: 'route-1',
      requested_model_id: null,
      reasoning_preference: null,
      fallback_policy: 'none',
    },
    source_pack_version: 'pack-v1',
    execution_policy: 'advisory_only',
    created_at: '2026-10-14T00:00:00Z',
    display_timezone: 'America/New_York',
  };
  const state: SessionStateRecord = {
    schema_version: 'wise-elders.session-state/v1',
    session_id: 'session-ctx-1',
    mode: 'consult',
    state: 'DRAFT',
    state_version: 0,
    brief_revision: 1,
    resume_phase: null,
    cancel_generation: 0,
    revocation_generation: 0,
    attempt: 1,
    lease_epoch: 0,
    archived: false,
    updated_at: '2026-10-14T00:00:00Z',
  };
  return { spec, brief, scope: SCOPE, state, sample: false };
}

function sinekCatalog(): MaterialCatalog {
  const evidenceUnit = unitFixture();
  const source: SourceRecord = {
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
  };
  const header: CandidateHeader = {
    evidence_id: evidenceUnit.evidence_id,
    seat_id: 'simon-sinek',
    scope: SCOPE,
    visibility: 'company',
    source_id: source.source_id,
    allowed_scope: 'shared_pack',
    sha256: canonicalHash(evidenceUnit),
  };
  const candidate: MaterialCandidate = { header, source, unit: evidenceUnit };
  return {
    listCandidateHeaders: () => [header],
    loadCandidate: (id) => (id === header.evidence_id ? candidate : null),
  };
}

const ROUTE = {
  context_limit_bytes: 1_000_000,
  system_rules_bytes: 1_000,
  response_schema_bytes: 500,
  output_reserve_bytes: 2_000,
};

function ownerPrincipal(overrides: Partial<TrustedPrincipal> = {}): TrustedPrincipal {
  return {
    tenant_id: 'tenant-a',
    company_id: 'company-a',
    installation_id: 'inst-a',
    subject: 'owner-1',
    channel: 'browser',
    support_access: false,
    ...overrides,
  };
}

// ---------------------------------------------------------------- store

test('assembly composes with the real CWE-006 scoped store end to end', async () => {
  const dataDir = tempDir('store');
  const service = CouncilStoreService.open({
    dataDir,
    clock,
    ids,
    envelope: envelopeFromScope(SCOPE, 'owner-1', 'owner', 'write'),
  });
  try {
    await service.createSession(storedSession());
    const result = await assembleStoredSessionContext(service, {
      session_id: 'session-ctx-1',
      principal: ownerPrincipal(),
      operation: 'consult',
      route: ROUTE,
      catalog: sinekCatalog(),
    });
    assert.equal(result.status, 'assembled');
    if (result.status === 'assembled') {
      assert.equal(result.context.items.length, 1);
      assert.equal(result.context.items[0].text, UNIT_TEXT);
      assert.equal(result.context.mode, 'consult');
      assert.deepEqual(result.context.evidence_manifest, [manifestEntry()]);
    }

    // A principal from another tenant is stopped at the CWE-007 gate
    // even though the store resolved the session in its own envelope.
    await assert.rejects(
      assembleStoredSessionContext(service, {
        session_id: 'session-ctx-1',
        principal: ownerPrincipal({ tenant_id: 'tenant-b' }),
        operation: 'consult',
        route: ROUTE,
        catalog: sinekCatalog(),
      }),
      (error: unknown) =>
        error instanceof Error && error.name === 'AuthorizationError',
    );

    // Unknown session: fails closed, indistinguishable from out of scope.
    await assert.rejects(
      assembleStoredSessionContext(service, {
        session_id: 'session-missing',
        principal: ownerPrincipal(),
        operation: 'consult',
        route: ROUTE,
        catalog: sinekCatalog(),
      }),
      (error: unknown) =>
        error instanceof ContextError && error.code === 'CONTEXT_SESSION_UNAVAILABLE',
    );
  } finally {
    service.close();
  }
});

// ------------------------------------------------------- real CWE-011

const CANONICAL_FIELDS = [
  'source_id',
  'work_id',
  'work_title',
  'credited_authors',
  'original_speaker',
  'source_type',
  'publisher_or_host',
  'edition_or_publication_date',
  'retrieved_at',
  'canonical_url',
  'private_asset_id',
  'content_sha256',
  'rights_status',
  'allowed_scope',
  'locators',
  'quality',
] as const;

function canonicalSubset(raw: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const field of CANONICAL_FIELDS) out[field] = raw[field] ?? null;
  return out;
}

// The real CWE-011 export package is external data: it is not in this
// repository, `git rev-list --all --objects` carries no copy of it, and
// it must never be fabricated. When it is genuinely absent the real-data
// test SKIPS with this path named instead of erroring or passing on
// absent data.
const CWE011_EXPORTS_DIR =
  process.env.CWE011_EXPORTS_DIR ??
  fileURLToPath(new URL('../../../../../cwe-011/exports', import.meta.url));
const BRUNSON_SOURCES = join(CWE011_EXPORTS_DIR, 'russell-brunson', 'sources.json');

function loadBrunsonRecords(): Array<Record<string, unknown>> {
  const parsed = JSON.parse(
    readFileSync(BRUNSON_SOURCES, 'utf8'),
  ) as { sources: Array<Record<string, unknown>> };
  return parsed.sources;
}

test('real CWE-011 Brunson package: private-scope record barred from distributable assembly', (t) => {
  if (!existsSync(BRUNSON_SOURCES)) {
    t.skip(
      `real CWE-011 export unavailable: ${BRUNSON_SOURCES} (set CWE011_EXPORTS_DIR to a real export package; it is external data and is never fabricated)`,
    );
    return;
  }
  const rawRecords = loadBrunsonRecords();
  assert.equal(rawRecords.length, 7);
  const parsed = rawRecords.map((raw) => ({
    raw,
    result: sourceRecordSchema.safeParse(canonicalSubset(raw)),
  }));
  const failures = parsed.filter((p) => !p.result.success);
  // Six records fail as exported, and the failing fields are pinned:
  // every failing record lacks retrieved_at; the two absent works also
  // lack a content hash. Only the NMS record parses clean.
  assert.deepEqual(
    failures.map((f) => f.raw.source_id).sort(),
    [
      'src-russell-brunson-dotcom-secrets',
      'src-russell-brunson-expert-secrets',
      'src-russell-brunson-lead-funnels',
      'src-russell-brunson-the-funnel-hackers-cookbook',
      'src-russell-brunson-the-marketing-secrets-blackbook',
      'src-russell-brunson-traffic-secrets',
    ],
  );
  for (const failure of failures) {
    if (!failure.result.success) {
      const paths = failure.result.error.issues.map((i) => i.path.join('.'));
      assert.ok(paths.includes('retrieved_at'), `expected retrieved_at failure for ${failure.raw.source_id}`);
      const absent = String(failure.raw.source_id).includes('dotcom-secrets') ||
        String(failure.raw.source_id).includes('expert-secrets');
      assert.equal(paths.includes('content_sha256'), absent);
    }
  }

  const nms = parsed.find(
    (p) => p.raw.source_id === 'src-russell-brunson-network-marketing-secrets',
  );
  assert.ok(nms && nms.result.success);
  if (!nms.result.success) return;
  const record: SourceRecord = nms.result.data;
  assert.equal(record.allowed_scope, 'user_private');
  assert.equal(record.quality, 'unverified');
  assert.equal(record.rights_status, 'reference_only');

  const evidenceUnit = {
    evidence_id: 'ev-brunson-nms-real-1',
    source_id: record.source_id,
    source_version: record.version ?? record.content_sha256,
    locator: record.locators[0],
    kind: 'concept' as const,
    mark: 'direct_teaching' as const,
    original_speaker: record.original_speaker,
    excerpt: null,
    paraphrase: 'Private seat source material from the real export.',
    claim_ids: ['claim-nms-1'],
    seat_id: 'russell-brunson' as const,
  };
  const ownerScope: ScopeFields = { ...SCOPE, owner_subject: 'owner-1' };
  const header: CandidateHeader = {
    evidence_id: evidenceUnit.evidence_id,
    seat_id: 'russell-brunson',
    scope: ownerScope,
    visibility: 'company',
    source_id: record.source_id,
    allowed_scope: record.allowed_scope,
    sha256: canonicalHash(evidenceUnit),
  };
  const candidate: MaterialCandidate = { header, source: record, unit: evidenceUnit };
  const catalog: MaterialCatalog = {
    listCandidateHeaders: () => [header],
    loadCandidate: (id) => (id === header.evidence_id ? candidate : null),
  };
  const manifest: EvidenceManifestEntry[] = [
    {
      evidence_id: evidenceUnit.evidence_id,
      sha256: header.sha256,
      source_kind: 'book',
      locator: 'section:real-export',
    },
  ];
  const briefFor: DecisionBrief = {
    schema_version: 'wise-elders.brief/v1',
    brief_id: 'brief-real-1',
    session_id: 'session-real-1',
    revision: 1,
    question: 'How should the funnel offer be structured?',
    facts: [],
    assumptions: [],
    unknowns: [],
    constraints: [],
    options: [{ id: 'option-a', label: 'Proceed', kind: 'change' }],
    relevance_weights: {},
    critical_domains: [],
    evidence_manifest: manifest,
    private_preference_ref: null,
    created_at: '2026-10-14T00:00:00Z',
    display_timezone: 'America/New_York',
  };
  const baseRequest = {
    principal: ownerPrincipal(),
    session: {
      scope: SCOPE,
      visibility: 'company' as const,
      session_id: 'session-real-1',
      mode: 'selected' as const,
      seat_ids: ['russell-brunson' as const],
    },
    brief: briefFor,
    operation: 'round_2_response' as const,
    route: ROUTE,
    catalog,
  };

  const distributed = assembleContext({ ...baseRequest, distributable: true });
  assert.equal(distributed.status, 'assembled');
  if (distributed.status === 'assembled') {
    assert.deepEqual(distributed.context.items, []);
  }
  const internal = assembleContext({ ...baseRequest, distributable: false });
  assert.equal(internal.status, 'assembled');
  if (internal.status === 'assembled') {
    assert.equal(internal.context.items.length, 1);
    const [item] = internal.context.items;
    assert.equal(item.provenance.source_id, 'src-russell-brunson-network-marketing-secrets');
    assert.equal(item.provenance.allowed_scope, 'user_private');
    assert.equal(item.provenance.quality, 'unverified');
    assert.equal(item.provenance.verification_status, 'unverified');
  }
});
