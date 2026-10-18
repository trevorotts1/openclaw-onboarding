import assert from 'node:assert/strict';
import test from 'node:test';
import {
  REQUIRED_FOUNDATIONS,
  computePackQualification,
  computeWorkCoverage,
} from '../src/sources/coverage.js';
import type { EvidenceUnit, SourceRecord } from '../src/sources/schemas.js';

const seat = 'simon-sinek' as const;
const work = REQUIRED_FOUNDATIONS[seat][0]!;
const hash = 'a'.repeat(64);

function source(quality: SourceRecord['quality'] = 'primary_substantive'): SourceRecord {
  return {
    source_id: 'sinek-original',
    work_id: 'start-with-why-original',
    work_title: 'Start with Why',
    credited_authors: ['Simon Sinek'],
    original_speaker: null,
    source_type: 'book',
    publisher_or_host: 'Example publisher',
    edition_or_publication_date: '2026',
    retrieved_at: '2026-10-17T12:00:00Z',
    canonical_url: 'https://example.org/original',
    private_asset_id: null,
    content_sha256: hash,
    rights_status: 'reference_only',
    allowed_scope: 'shared_pack',
    quality,
    locators: [
      { kind: 'page', value: 'p. 11' },
      { kind: 'page', value: 'p. 12' },
      { kind: 'page', value: 'p. 13' },
      { kind: 'page', value: 'p. 14' },
    ],
  };
}

function unit(
  index: number,
  page: number,
  patch: Partial<EvidenceUnit> = {},
): EvidenceUnit {
  return {
    evidence_id: `evidence-${index}`,
    source_id: 'sinek-original',
    source_version: hash,
    locator: { kind: 'page', value: `p. ${page}` },
    kind: 'concept',
    mark: 'paraphrase',
    original_speaker: null,
    excerpt: null,
    paraphrase: `Independently located teaching number ${index}`,
    claim_ids: [],
    seat_id: seat,
    ...patch,
  };
}

const genuineCandidate = [
  unit(1, 11), unit(2, 12), unit(3, 13),
  unit(4, 14, { kind: 'application_case', mark: 'reported_example' }),
];

test('three located concepts and one located case qualify PRIMARY teaching, not a complete book', () => {
  const row = computeWorkCoverage(seat, work, [source()], genuineCandidate);
  assert.equal(row.traceable_concepts, 3);
  assert.equal(row.application_cases, 1);
  assert.equal(row.gate_met, true);
  assert.equal(row.work_class, 'primary_teaching',
    'a book source type and four excerpt-sized locators cannot prove full-book ingestion');
  const pack = computePackQualification(seat, [source()], genuineCandidate);
  assert.equal(pack.qualification, 'primary_teaching_based');
  assert.notEqual(pack.qualification, 'substantive');
});

test('repeating the same source locator is not independent concept coverage', () => {
  const clones = [unit(1, 11), unit(2, 11), unit(3, 11), genuineCandidate[3]!];
  const row = computeWorkCoverage(seat, work, [source()], clones);
  assert.equal(row.traceable_concepts, 1);
  assert.equal(row.application_cases, 1);
  assert.equal(row.gate_met, false);
});

test('unverified derivative notes cannot be promoted by large concept counts', () => {
  const row = computeWorkCoverage(seat, work, [source('unverified')], genuineCandidate);
  assert.equal(row.traceable_concepts, 0);
  assert.equal(row.application_cases, 0);
  assert.equal(row.work_class, 'bibliographic_only');
  assert.equal(row.gate_met, false);
});

test('a made-up locator outside the source record does not count', () => {
  const row = computeWorkCoverage(seat, work, [source()], [
    unit(1, 11), unit(2, 12), unit(3, 99), genuineCandidate[3]!,
  ]);
  assert.equal(row.traceable_concepts, 2);
  assert.equal(row.gate_met, false);
});

test('BlackCEO adaptations and third-party commentary never satisfy the primary teaching bar', () => {
  const row = computeWorkCoverage(seat, work, [source()], [
    unit(1, 11, { mark: 'blackceo_adaptation' }),
    unit(2, 12, { mark: 'third_party_commentary' }),
    unit(3, 13),
    unit(4, 14, { kind: 'application_case', mark: 'blackceo_adaptation' }),
  ]);
  assert.equal(row.traceable_concepts, 1);
  assert.equal(row.application_cases, 0);
  assert.equal(row.gate_met, false);
});

test('stale source version, missing teaching text and another seat cannot count', () => {
  const row = computeWorkCoverage(seat, work, [source()], [
    unit(1, 11, { source_version: 'b'.repeat(64) }),
    unit(2, 12, { excerpt: null, paraphrase: null }),
    unit(3, 13, { seat_id: 'td-jakes' }),
    genuineCandidate[3]!,
  ]);
  assert.equal(row.traceable_concepts, 0);
  assert.equal(row.application_cases, 1);
  assert.equal(row.gate_met, false);
});
