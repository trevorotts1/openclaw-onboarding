/**
 * Synthetic fixtures for the CWE-012 test suite.
 *
 * Every string here is invented fixture data, written for this suite and
 * labeled as such. No fixture text is a real quotation, a real source
 * excerpt, or a real biographical claim; the fixtures exist to exercise
 * validator boundaries, never to stand in for source material.
 */

import { sha256Hex } from '../contracts/sha256.js';
import type { PackInput } from './packs.js';

function fixtureRecord(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    publisher_or_host: 'Fixture Publisher',
    edition_or_publication_date: 'Fixture edition',
    retrieved_at: '2026-10-14T00:00:00.000Z',
    canonical_url: null,
    private_asset_id: null,
    rights_status: 'licensed_distribution',
    allowed_scope: 'shared_pack',
    quality: 'primary_substantive',
    version: 'fixture-v1',
    ...overrides,
  };
}

function concept(
  id: string,
  sourceId: string,
  seat: string,
  page: string,
  mark: string,
  text: string,
): Record<string, unknown> {
  return {
    evidence_id: id,
    source_id: sourceId,
    source_version: 'fixture-v1',
    locator: { kind: 'page', value: page },
    kind: 'concept',
    mark,
    original_speaker: null,
    excerpt: mark === 'paraphrase' ? null : text,
    paraphrase: mark === 'paraphrase' ? text : null,
    claim_ids: [],
    seat_id: seat,
  };
}

function applicationCase(
  id: string,
  sourceId: string,
  seat: string,
  page: string,
): Record<string, unknown> {
  return {
    evidence_id: id,
    source_id: sourceId,
    source_version: 'fixture-v1',
    locator: { kind: 'page', value: page },
    kind: 'application_case',
    mark: 'reported_example',
    original_speaker: null,
    excerpt: null,
    paraphrase: 'Fixture application case narrative with a located source.',
    claim_ids: [],
    seat_id: seat,
  };
}

/** A valid minimal substantive pack: Simon Sinek, Start with Why. */
export function validSinekPack(): PackInput {
  const sourceId = 'src-sinek-swy-fixture';
  const record = fixtureRecord({
    source_id: sourceId,
    work_id: 'start-with-why',
    work_title: 'Start with Why',
    credited_authors: ['Simon Sinek'],
    original_speaker: null,
    source_type: 'book',
    content_sha256: sha256Hex(new TextEncoder().encode('FIXTURE source text for Start with Why')),
    locators: [
      { kind: 'page', value: '41' },
      { kind: 'page', value: '87' },
      { kind: 'page', value: '112' },
      { kind: 'page', value: '150' },
    ],
  });
  const evidence = [
    concept('ev-sinek-concept-1', sourceId, 'simon-sinek', '41', 'direct_teaching',
      'Fixture excerpt one: why comes before what in the fixture teaching.'),
    concept('ev-sinek-concept-2', sourceId, 'simon-sinek', '87', 'paraphrase',
      'Fixture paraphrase two: the circle runs why, how, what from inside out.'),
    concept('ev-sinek-concept-3', sourceId, 'simon-sinek', '112', 'reported_example',
      'Fixture example three: a company in the fixture text leads with belief.'),
    applicationCase('ev-sinek-case-1', sourceId, 'simon-sinek', '150'),
    {
      evidence_id: 'ev-sinek-quote-1',
      source_id: sourceId,
      source_version: 'fixture-v1',
      locator: { kind: 'page', value: '41' },
      kind: 'quotation',
      mark: 'direct_teaching',
      original_speaker: null,
      excerpt: 'Fixture sentence: start with why.',
      paraphrase: null,
      claim_ids: [],
      seat_id: 'simon-sinek',
    },
  ];
  return {
    folder: 'simon-sinek',
    profile: {
      seat_id: 'simon-sinek',
      name: 'Simon Sinek',
      profile_label:
        'AI perspective inspired by the published work of Simon Sinek. Not the individual and not an endorsement.',
      source_basis: [{ basis: 'book', title: 'Start with Why' }],
      pack_version: '1.0.0-fixture',
      pack_status: 'ready',
    },
    sources: { records: [{ ...record, evidence }] },
    coverage: { covered: { concepts: 3, application_cases: 1 } },
    frameworks: {
      items: [
        {
          name: 'Fixture framework',
          attribution_kind: 'source_principle',
          source_evidence_ids: ['ev-sinek-concept-1'],
        },
        { name: 'Fixture adaptation', attribution_kind: 'blackceo_adaptation' },
      ],
    },
    evals: {
      cases: [
        { type: 'strong_fit' },
        { type: 'weak_fit' },
        { type: 'missing_evidence' },
        { type: 'apparent_agreement' },
        { type: 'overreach' },
      ],
    },
  };
}

/** Oprah pack whose one quotation is spoken by a guest, not by Oprah (T004). */
export function oprahGuestPack(): PackInput {
  const sourceId = 'src-oprah-pmc-fixture';
  const record = fixtureRecord({
    source_id: sourceId,
    work_id: 'the-path-made-clear',
    work_title: 'The Path Made Clear',
    credited_authors: ['Oprah Winfrey'],
    original_speaker: null,
    source_type: 'book',
    content_sha256: sha256Hex(new TextEncoder().encode('FIXTURE source text for The Path Made Clear')),
    locators: [{ kind: 'page', value: '77' }],
  });
  const evidence = [
    {
      evidence_id: 'ev-oprah-quote-1',
      source_id: sourceId,
      source_version: 'fixture-v1',
      locator: { kind: 'page', value: '77' },
      kind: 'quotation',
      mark: 'direct_teaching',
      original_speaker: 'Fixture Guest',
      excerpt: 'Fixture guest sentence: the path clears as you walk it.',
      paraphrase: null,
      claim_ids: [],
      seat_id: 'oprah-winfrey',
    },
  ];
  return {
    folder: 'oprah-winfrey',
    profile: {
      seat_id: 'oprah-winfrey',
      name: 'Oprah Winfrey',
      profile_label:
        'AI perspective inspired by the published work of Oprah Winfrey. Not the individual and not an endorsement.',
      source_basis: [{ basis: 'book', title: 'The Path Made Clear' }],
      pack_version: '1.0.0-fixture',
      pack_status: 'in_progress',
    },
    sources: { records: [{ ...record, evidence }] },
    coverage: { covered: { concepts: 0, application_cases: 0 } },
  };
}

/** A valid Jakes pack: three books, three lenses, one seat. */
export function validJakesPack(): PackInput {
  const books = [
    { key: 'instinct', title: 'Instinct', lens: 'instinct' },
    { key: 'disruptive', title: 'Disruptive Thinking', lens: 'disruptive-thinking' },
    { key: 'mic', title: "Don't Drop the Mic", lens: 'dont-drop-the-mic' },
  ];
  const records = books.map((book) => {
    const sourceId = `src-jakes-${book.key}-fixture`;
    const evidence = [
      concept(`ev-jakes-${book.key}-c1`, sourceId, 'td-jakes', '11', 'direct_teaching',
        `Fixture excerpt for ${book.title}: teaching point one.`),
      concept(`ev-jakes-${book.key}-c2`, sourceId, 'td-jakes', '22', 'paraphrase',
        `Fixture paraphrase for ${book.title}: teaching point two.`),
      concept(`ev-jakes-${book.key}-c3`, sourceId, 'td-jakes', '33', 'reported_example',
        `Fixture example for ${book.title}: teaching point three.`),
      applicationCase(`ev-jakes-${book.key}-case`, sourceId, 'td-jakes', '44'),
    ];
    return {
      ...fixtureRecord({
        source_id: sourceId,
        work_id: `work-${book.key}`,
        work_title: book.title,
        credited_authors: ['T. D. Jakes'],
        original_speaker: null,
        source_type: 'book',
        content_sha256: sha256Hex(
          new TextEncoder().encode(`FIXTURE source text for ${book.title}`),
        ),
        locators: ['11', '22', '33', '44'].map((value) => ({ kind: 'page', value })),
      }),
      evidence,
    };
  });
  return {
    folder: 'td-jakes',
    profile: {
      seat_id: 'td-jakes',
      name: 'T. D. Jakes',
      profile_label:
        'AI perspective inspired by the published work of T. D. Jakes. Not the individual and not an endorsement.',
      lenses: ['instinct', 'disruptive-thinking', 'dont-drop-the-mic'],
      votes: 1,
      source_basis: books.map((b) => ({ basis: 'book', title: b.title })),
      pack_version: '1.0.0-fixture',
      pack_status: 'ready',
    },
    sources: { records },
    coverage: { covered: { concepts: 9, application_cases: 3 } },
    evals: {
      cases: [
        { type: 'strong_fit' },
        { type: 'weak_fit' },
        { type: 'missing_evidence' },
        { type: 'apparent_agreement' },
        { type: 'overreach' },
      ],
    },
  };
}

/** Deep clone helper for negative-fixture mutations. */
export function clonePack(pack: PackInput): PackInput {
  return JSON.parse(JSON.stringify(pack)) as PackInput;
}
