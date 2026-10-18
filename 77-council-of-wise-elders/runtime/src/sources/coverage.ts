/**
 * Coverage classification and the Section 8.2 substantive gate (CWE-012).
 *
 * Coverage vocabulary is the directive's own: a publisher description
 * alone is bibliographic_only, not production-ready knowledge; substantial
 * primary teaching without full-book access makes a pack
 * primary_teaching_based; a required basis that cannot be substantiated
 * leaves the pack incomplete, and nobody fabricates a replacement.
 *
 * For Simon Sinek's required book and for each of T. D. Jakes' three
 * required books the directive sets the operational gate explicitly: at
 * least three independently traceable concepts supported by actual
 * accessed teaching, and at least one case demonstrating application
 * beyond a book blurb. This module applies the same gate to every
 * required work so no seat is held to a weaker standard.
 */

import { SEAT_ROSTER, type SeatId } from '../contracts/enums';
import {
  sourceVersionOf,
  type EvidenceUnit,
  type SourceRecord,
} from './schemas';
import { normalizeTitle, sameSpeaker } from './text';

export const MIN_TRACEABLE_CONCEPTS = 3;
export const MIN_APPLICATION_CASES = 1;

export type RequiredWorkKind =
  | 'book'
  | 'first_person_teaching'
  | 'documented_material';

export interface RequiredWork {
  work_key: string;
  title: string;
  kind: RequiredWorkKind;
  /** Jakes lens this work grounds, where the seat has lenses. */
  lens?: string;
}

/**
 * Required foundations per seat, from Section 7.2 to 7.10. Titles are
 * matched against source records by normalized title; a related work or
 * another book by the same author is not a substitute (Section 39.5).
 */
export const REQUIRED_FOUNDATIONS: Record<SeatId, readonly RequiredWork[]> = {
  'simon-sinek': [
    { work_key: 'start-with-why', title: 'Start with Why', kind: 'book' },
  ],
  'td-jakes': [
    { work_key: 'instinct', title: 'Instinct', kind: 'book', lens: 'instinct' },
    {
      work_key: 'disruptive-thinking',
      title: 'Disruptive Thinking',
      kind: 'book',
      lens: 'disruptive-thinking',
    },
    {
      work_key: 'dont-drop-the-mic',
      title: "Don't Drop the Mic",
      kind: 'book',
      lens: 'dont-drop-the-mic',
    },
  ],
  'oprah-winfrey': [
    {
      work_key: 'the-path-made-clear',
      title: 'The Path Made Clear',
      kind: 'book',
    },
    {
      work_key: 'verified-first-person',
      title: 'Verified first-person interviews and reflections',
      kind: 'first_person_teaching',
    },
  ],
  'tiffany-aliche': [
    {
      work_key: 'get-good-with-money',
      title: 'Get Good with Money',
      kind: 'book',
    },
  ],
  'russell-brunson': [
    { work_key: 'dotcom-secrets', title: 'DotCom Secrets', kind: 'book' },
    { work_key: 'expert-secrets', title: 'Expert Secrets', kind: 'book' },
  ],
  'michelle-obama': [
    { work_key: 'becoming', title: 'Becoming', kind: 'book' },
    {
      work_key: 'the-light-we-carry',
      title: 'The Light We Carry',
      kind: 'book',
    },
  ],
  'brene-brown': [
    { work_key: 'dare-to-lead', title: 'Dare to Lead', kind: 'book' },
    {
      work_key: 'braving',
      title: 'BRAVING documented material',
      kind: 'documented_material',
    },
  ],
  'dennis-kimbro': [
    {
      work_key: 'think-and-grow-rich-a-black-choice',
      title: 'Think and Grow Rich: A Black Choice',
      kind: 'book',
    },
    { work_key: 'the-wealth-choice', title: 'The Wealth Choice', kind: 'book' },
  ],
  'les-brown': [
    {
      work_key: 'its-not-over-until-you-win',
      title: "It's Not Over Until You Win",
      kind: 'book',
    },
    {
      work_key: 'verified-public-teaching',
      title: 'Verified public teaching',
      kind: 'first_person_teaching',
    },
  ],
};

export type WorkClass =
  | 'complete_book'
  | 'primary_teaching'
  | 'partial'
  | 'bibliographic_only'
  | 'missing';

export interface WorkCoverage {
  work_key: string;
  title: string;
  work_class: WorkClass;
  matched_source_ids: string[];
  traceable_concepts: number;
  application_cases: number;
  gate_met: boolean;
}

export type PackQualification =
  | 'substantive'
  | 'primary_teaching_based'
  | 'partial'
  | 'bibliographic_only'
  | 'incomplete';

function seatDisplayName(seatId: SeatId): string {
  return SEAT_ROSTER.find((s) => s.seat_id === seatId)?.display_name ?? seatId;
}

function recordMatchesWork(
  record: SourceRecord,
  work: RequiredWork,
  seatId: SeatId,
): boolean {
  if (work.kind === 'book') {
    return normalizeTitle(record.work_title) === normalizeTitle(work.title);
  }
  if (work.kind === 'documented_material') {
    return normalizeTitle(record.work_title).includes('braving');
  }
  // first_person_teaching: first-person material by the seat's person.
  if (!['interview', 'talk', 'transcript'].includes(record.source_type)) {
    return false;
  }
  const person = seatDisplayName(seatId);
  if (
    record.original_speaker !== null &&
    sameSpeaker(record.original_speaker, person)
  ) {
    return true;
  }
  return record.credited_authors.some((a) => sameSpeaker(a, person));
}

/** Marks that count as the author's own teaching for the gate. */
const TEACHING_MARKS = new Set([
  'direct_teaching',
  'paraphrase',
  'reported_example',
]);

export function computeWorkCoverage(
  seatId: SeatId,
  work: RequiredWork,
  records: readonly SourceRecord[],
  evidence: readonly EvidenceUnit[],
  /** Titles present only as bibliographic stubs (acknowledged, not ingested). */
  stubTitles: readonly string[] = [],
): WorkCoverage {
  const matched = records.filter((r) => recordMatchesWork(r, work, seatId));
  const substantive = matched.filter((r) => r.quality === 'primary_substantive');
  const sourceById = new Map(substantive.map((r) => [r.source_id, r]));

  // An evidence_id alone is not provenance. Each counted concept must
  // name an actual source-version and a locator present in that source
  // record. Duplicating one locator three times is not three
  // independently traceable concepts. BlackCEO-created adaptations and
  // third-party commentary never satisfy a primary-author foundation.
  const eligible = evidence.filter((u) => {
    const source = sourceById.get(u.source_id);
    if (!source || u.seat_id !== seatId || u.source_version !== sourceVersionOf(source)) {
      return false;
    }
    if (!TEACHING_MARKS.has(u.mark)) return false;
    if (!(u.paraphrase?.trim() || u.excerpt?.trim())) return false;
    const loc = u.locator.value.trim();
    return loc.length > 0 &&
      source.locators.some((candidate) =>
        candidate.kind === u.locator.kind && candidate.value.trim() === loc,
      );
  });
  const independentlyLocated = (kind: EvidenceUnit['kind']) => {
    const locators = new Set<string>();
    for (const unit of eligible) {
      if (unit.kind !== kind) continue;
      locators.add(JSON.stringify([
        unit.source_id, unit.locator.kind, unit.locator.value.trim(),
      ]));
    }
    return locators.size;
  };
  const concepts = independentlyLocated('concept');
  const cases = independentlyLocated('application_case');
  const gateMet =
    concepts >= MIN_TRACEABLE_CONCEPTS && cases >= MIN_APPLICATION_CASES;

  const stubbed = stubTitles.some((t) => {
    const n = normalizeTitle(t);
    return work.kind === 'documented_material'
      ? n.includes('braving')
      : n === normalizeTitle(work.title);
  });
  let workClass: WorkClass;
  if (matched.length === 0) {
    workClass = stubbed ? 'bibliographic_only' : 'missing';
  } else if (gateMet) {
    // 'book' describes the publication, not the breadth of ingestion.
    // Three grounded concepts and one example can support a primary-
    // teaching claim, but CANNOT prove the complete book was ingested.
    // Section 8.3 source records have no audited full-work ingestion
    // receipt. Until that proof is introduced, fail closed rather than
    // quietly upgrading primary teaching to complete-book coverage.
    workClass = 'primary_teaching';
  } else if (substantive.length > 0 || concepts > 0) {
    workClass = 'partial';
  } else {
    workClass = 'bibliographic_only';
  }

  return {
    work_key: work.work_key,
    title: work.title,
    work_class: workClass,
    matched_source_ids: matched.map((r) => r.source_id),
    traceable_concepts: concepts,
    application_cases: cases,
    gate_met: gateMet,
  };
}

export function computePackQualification(
  seatId: SeatId,
  records: readonly SourceRecord[],
  evidence: readonly EvidenceUnit[],
  stubTitles: readonly string[] = [],
): { qualification: PackQualification; works: WorkCoverage[] } {
  const works = REQUIRED_FOUNDATIONS[seatId].map((w) =>
    computeWorkCoverage(seatId, w, records, evidence, stubTitles)
  );
  let qualification: PackQualification;
  if (works.every((w) => w.work_class === 'complete_book')) {
    qualification = 'substantive';
  } else if (
    works.every(
      (w) => w.work_class === 'complete_book' || w.work_class === 'primary_teaching',
    )
  ) {
    qualification = 'primary_teaching_based';
  } else if (works.some((w) => w.work_class === 'missing')) {
    qualification = 'incomplete';
  } else if (
    works.some(
      (w) => w.work_class === 'partial' || w.work_class === 'primary_teaching',
    )
  ) {
    qualification = 'partial';
  } else {
    qualification = 'bibliographic_only';
  }
  return { qualification, works };
}
