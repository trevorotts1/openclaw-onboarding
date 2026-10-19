/**
 * CWE-050 export-v2 adapter tests, proven against the ACTUAL CWE-011
 * export files at ~/workspace/skill77/cwe-011/exports/ (the same path
 * convention CWE-022's integration test uses). The adapter must load
 * the real exports through the accepted CWE-022 context path WITHOUT
 * loosening the strict CWE-012 schema.
 *
 * Standing facts these tests pin (verified against the files):
 * - 26 source records: 14 present, 12 absent (the verifiably absent
 *   works: Oprah and Les Brown entirely; Jakes Disruptive Thinking and
 *   Don't Drop the Mic; Brunson DotCom Secrets and Expert Secrets;
 *   Brown Dare to Lead and the documented BRAVING material; Kimbro
 *   Think and Grow Rich: A Black Choice; Tiffany's documented
 *   financial-wholeness teaching).
 * - 1,317 evidence units: 240 concepts, 1,077 quote candidates, ALL
 *   quotes verification_status 'candidate' (zero verified quotations).
 */
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { canonicalHash, type DecisionBrief } from '../src/contracts/index.js';
import { assembleContext } from '../src/context/index.js';
import {
  sourceRecordSchema,
  evidenceUnitSchema,
} from '../src/sources/schemas.js';
import {
  adaptSkill22Export,
  createAdaptedMaterialCatalog,
} from '../src/sources/export-v2.js';
import type { TrustedPrincipal } from '../src/authorization/index.js';

const EXPORTS_DIR =
  process.env.CWE011_EXPORTS_DIR ??
  fileURLToPath(new URL('../../../../../cwe-011/exports', import.meta.url));

// The real CWE-011 export package is external data: it is not in this
// repository and must never be fabricated. When it is genuinely absent
// these real-data tests SKIP naming the exact missing path, instead of
// erroring or passing on absent data. Set CWE011_EXPORTS_DIR to point
// at a real package to run them.
const EXPORT_MANIFEST = join(EXPORTS_DIR, 'export-manifest.json');

function skipWithoutRealExport(t: { skip(reason?: string): void }): boolean {
  if (existsSync(EXPORT_MANIFEST)) return false;
  t.skip(
    `real CWE-011 export unavailable: ${EXPORTS_DIR} (first required file ${EXPORT_MANIFEST}; set CWE011_EXPORTS_DIR to a real export package; it is external data and is never fabricated)`,
  );
  return true;
}

const SCOPE = {
  tenant_id: 'tenant-a',
  company_id: 'company-a',
  installation_id: 'inst-a',
  owner_subject: 'owner-1',
};

function ownerPrincipal(): TrustedPrincipal {
  return {
    tenant_id: 'tenant-a',
    company_id: 'company-a',
    installation_id: 'inst-a',
    subject: 'owner-1',
    channel: 'browser',
    support_access: false,
  };
}

test('adapter: real CWE-011 exports adapt under the strict schema, unloosened', (t) => {
  if (skipWithoutRealExport(t)) return;
  const adapted = adaptSkill22Export(EXPORTS_DIR);
  const { report } = adapted;
  assert.equal(report.records_seen, 26);
  assert.equal(report.records_adapted, 14);
  assert.equal(report.absences.length, 12);
  assert.deepEqual(
    report.absences.map((a) => a.source_id).sort(),
    [
      'src-brene-brown-dare-to-lead',
      'src-brene-brown-documented-braving-material',
      'src-dennis-kimbro-think-and-grow-rich-a-black-choice',
      'src-les-brown-its-not-over-until-you-win',
      'src-les-brown-verified-public-teaching',
      'src-oprah-winfrey-the-path-made-clear',
      'src-oprah-winfrey-verified-first-person-interviews-and-reflections',
      'src-russell-brunson-dotcom-secrets',
      'src-russell-brunson-expert-secrets',
      'src-td-jakes-disruptive-thinking',
      'src-td-jakes-dont-drop-the-mic',
      'src-tiffany-aliche-documented-financial-wholeness-teaching',
    ],
  );
  // Every absence keeps the export's own gap note; nothing is invented.
  for (const absence of report.absences) assert.ok(absence.gaps.length > 0);
  // Every adapted record passes the strict schema as exported by CWE-012.
  for (const record of adapted.records) {
    assert.equal(sourceRecordSchema.safeParse(record).success, true, record.source_id);
  }
  for (const unit of adapted.units) {
    assert.equal(evidenceUnitSchema.safeParse(unit).success, true, unit.evidence_id);
  }
  // The export-only bookkeeping fields were dropped, and are reported.
  for (const field of ['status', 'record_status', 'artifacts', 'gaps', 'coverage_label']) {
    assert.ok(report.dropped_fields.includes(field), `expected ${field} in dropped_fields`);
  }
});

test('adapter: retrieved_at basis is honest (one verbatim, the rest the export date)', (t) => {
  if (skipWithoutRealExport(t)) return;
  const adapted = adaptSkill22Export(EXPORTS_DIR);
  const nms = adapted.records.find(
    (r) => r.source_id === 'src-russell-brunson-network-marketing-secrets',
  );
  assert.ok(nms);
  assert.equal(nms.retrieved_at, '2026-06-26');
  assert.equal(
    adapted.report.retrieved_at_basis[nms.source_id],
    'record_verbatim',
  );
  assert.equal(nms.allowed_scope, 'user_private');
  const others = adapted.records.filter((r) => r.source_id !== nms.source_id);
  assert.ok(others.length > 0);
  for (const record of others) {
    assert.equal(record.retrieved_at, adapted.report.exported_at, record.source_id);
    assert.equal(adapted.report.retrieved_at_basis[record.source_id], 'export_package');
  }
  // Quality labels are carried verbatim, never upgraded.
  for (const record of adapted.records) assert.equal(record.quality, 'unverified');
});

test('adapter: candidate quote text is withheld; concepts load as paraphrase', (t) => {
  if (skipWithoutRealExport(t)) return;
  const adapted = adaptSkill22Export(EXPORTS_DIR);
  assert.equal(adapted.report.units_seen, 1317);
  assert.equal(adapted.report.units_adapted, 1317);
  assert.equal(adapted.report.concept_units, 240);
  assert.equal(adapted.report.quote_units_text_withheld, 1077);
  const quotes = adapted.units.filter((u) => u.kind === 'quotation');
  assert.equal(quotes.length, 1077);
  for (const quote of quotes) {
    assert.equal(quote.excerpt, null);
    assert.equal(quote.paraphrase, null);
  }
  const concepts = adapted.units.filter((u) => u.kind === 'concept');
  assert.equal(concepts.length, 240);
  for (const concept of concepts) {
    assert.ok(concept.paraphrase && concept.paraphrase.length > 0);
    assert.equal(concept.excerpt, null);
  }
  // The catalog offers only loadable units: the 240 concepts.
  const catalog = createAdaptedMaterialCatalog(adapted, { scope: SCOPE });
  assert.equal(catalog.listCandidateHeaders().length, 240);
});

test('adapter: adapted material loads through the accepted CWE-022 context path', (t) => {
  if (skipWithoutRealExport(t)) return;
  const adapted = adaptSkill22Export(EXPORTS_DIR);
  const catalog = createAdaptedMaterialCatalog(adapted, { scope: SCOPE });
  // Pick a shared_pack concept unit (Brunson Traffic Secrets) and an
  // NMS (user_private) concept unit from the adapted set.
  const traffic = adapted.units.find(
    (u) => u.source_id === 'src-russell-brunson-traffic-secrets' && u.kind === 'concept',
  );
  const nmsUnit = adapted.units.find(
    (u) =>
      u.source_id === 'src-russell-brunson-network-marketing-secrets' &&
      u.kind === 'concept',
  );
  assert.ok(traffic && nmsUnit);
  const brief: DecisionBrief = {
    schema_version: 'wise-elders.brief/v1',
    brief_id: 'brief-adapter-1',
    session_id: 'session-adapter-1',
    revision: 1,
    question: 'How should the funnel offer be structured?',
    facts: [],
    assumptions: [],
    unknowns: [],
    constraints: [],
    options: [{ id: 'option-a', label: 'Proceed', kind: 'change' }],
    relevance_weights: {},
    critical_domains: [],
    evidence_manifest: [traffic, nmsUnit].map((u) => ({
      evidence_id: u.evidence_id,
      sha256: canonicalHash(u),
      source_kind: 'book' as const,
      locator: `${u.locator.kind}:${u.locator.value}`,
    })),
    private_preference_ref: null,
    created_at: '2026-10-14T00:00:00Z',
    display_timezone: 'America/New_York',
  };
  const base = {
    principal: ownerPrincipal(),
    session: {
      scope: SCOPE,
      visibility: 'company' as const,
      session_id: 'session-adapter-1',
      mode: 'selected' as const,
      seat_ids: ['russell-brunson' as const],
    },
    brief,
    operation: 'round_2_response' as const,
    route: {
      context_limit_bytes: 1_000_000,
      system_rules_bytes: 1_000,
      response_schema_bytes: 500,
      output_reserve_bytes: 2_000,
    },
    catalog,
  };
  // Internal assembly: both items load, text is the export's summary,
  // provenance quality stays 'unverified' (never upgraded).
  const internal = assembleContext({ ...base, distributable: false });
  assert.equal(internal.status, 'assembled');
  if (internal.status === 'assembled') {
    assert.equal(internal.context.items.length, 2);
    for (const item of internal.context.items) {
      assert.equal(item.provenance.quality, 'unverified');
    }
  }
  // Distributable assembly: the user_private NMS item is barred
  // (CWE-012 condition 3); the shared_pack item still loads.
  const distributed = assembleContext({ ...base, distributable: true });
  assert.equal(distributed.status, 'assembled');
  if (distributed.status === 'assembled') {
    assert.equal(distributed.context.items.length, 1);
    assert.equal(
      distributed.context.items[0].provenance.source_id,
      'src-russell-brunson-traffic-secrets',
    );
  }
});
