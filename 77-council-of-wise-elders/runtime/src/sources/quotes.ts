/**
 * Quotation verification (Section 8.4) and the CWE-012 acceptance tests
 * T004, T011, and the quotation half of T012.
 *
 * The validator verifies the tuple (quoted_text, original_speaker,
 * source_id, source_version, locator) against the ORIGINAL source
 * record, never against a concatenation of all advisor files. A match in
 * a different advisor's corpus does not pass; it is reported as its own
 * diagnostic so the failure is attributable. A quote that appears only
 * in earlier generated rounds is rejected: repetition is not external
 * verification.
 *
 * A string match alone cannot prove entailment of an argument, and this
 * module never claims it does. Paraphrase relevance remains an
 * independent semantic review (Section 8.4), outside this deterministic
 * check.
 */

import type { SeatId } from '../contracts/enums';
import type { VerifiedQuoteCandidate } from '../contracts/schemas';
import {
  errorDiagnostic,
  sourceVersionOf,
  type Diagnostic,
  type EvidenceUnit,
  type SourceRecord,
} from './schemas';
import { locatorMatches, normalizeQuotedText, sameSpeaker } from './text';

/** The five-tuple a quotation claim must prove (Section 8.4). */
export interface QuoteTuple {
  quoted_text: string;
  original_speaker: string;
  source_id: string;
  source_version: string;
  locator: string;
}

export interface QuoteCorpus {
  records: readonly SourceRecord[];
  evidence: readonly EvidenceUnit[];
}

export type QuoteAudience = 'shared_pack' | 'tenant' | 'user_private';

export interface QuoteContext {
  /** Where the verified quote would be released. */
  audience: QuoteAudience;
  /** Source IDs withdrawn under Section 8.6. */
  revokedSourceIds?: ReadonlySet<string>;
  /**
   * Other seats' corpora, consulted ONLY to attribute a failure: text
   * found there is named as found in another seat and still rejected.
   */
  otherSeatCorpora?: Partial<Record<SeatId, QuoteCorpus>>;
  /**
   * Text of earlier generated rounds for this session. A quote whose
   * only occurrence is here is rejected (Section 8.4).
   */
  generatedRoundsText?: readonly string[];
}

export interface QuoteVerification {
  status: 'verified' | 'rejected';
  diagnostics: Diagnostic[];
}

function rejected(diagnostics: Diagnostic[]): QuoteVerification {
  return { status: 'rejected', diagnostics };
}

/** The speaker an evidence unit speaks in: unit, then record, then author. */
function unitSpeaker(unit: EvidenceUnit, record: SourceRecord): string | null {
  return unit.original_speaker ?? record.original_speaker ??
    record.credited_authors[0] ?? null;
}

function excerptContains(unit: EvidenceUnit, normalizedQuote: string): boolean {
  return unit.excerpt !== null &&
    normalizeQuotedText(unit.excerpt).includes(normalizedQuote);
}

/**
 * Verify one quotation tuple against one seat's corpus. Every rejection
 * names the exact boundary that caused it; an expected rejection is only
 * meaningful when the intended boundary is the cause (Section 35.1).
 */
export function verifyQuotation(
  tuple: QuoteTuple,
  corpus: QuoteCorpus,
  context: QuoteContext,
): QuoteVerification {
  const diagnostics: Diagnostic[] = [];
  const fail = (code: string, message: string) => {
    diagnostics.push(errorDiagnostic(code, message));
    return rejected(diagnostics);
  };

  if (tuple.locator.trim().length === 0) {
    return fail(
      'QUOTE_MISSING_LOCATOR',
      'A quotation without a locator cannot be verified.',
    );
  }
  const record = corpus.records.find((r) => r.source_id === tuple.source_id);
  if (!record) {
    return fail(
      'QUOTE_SOURCE_UNKNOWN',
      `No source record ${tuple.source_id} exists in this seat's corpus.`,
    );
  }
  if (context.revokedSourceIds?.has(record.source_id)) {
    return fail(
      'QUOTE_SOURCE_REVOKED',
      `Source ${record.source_id} has been revoked and cannot ground a quotation.`,
    );
  }
  const expectedVersion = sourceVersionOf(record);
  if (tuple.source_version !== expectedVersion) {
    return fail(
      'QUOTE_VERSION_MISMATCH',
      `Quote names source version ${tuple.source_version}; the record's version is ${expectedVersion}.`,
    );
  }

  const normalizedQuote = normalizeQuotedText(tuple.quoted_text);
  const textMatches = corpus.evidence.filter(
    (u) =>
      u.kind === 'quotation' && u.source_id === record.source_id &&
      u.source_version === expectedVersion && excerptContains(u, normalizedQuote),
  );
  if (textMatches.length === 0) {
    // Attribute the failure precisely; none of these paths passes.
    if (context.otherSeatCorpora) {
      for (const [seat, other] of Object.entries(context.otherSeatCorpora)) {
        const found = (other?.evidence ?? []).some(
          (u) => u.kind === 'quotation' && excerptContains(u, normalizedQuote),
        );
        if (found) {
          return fail(
            'QUOTE_FOUND_IN_OTHER_SEAT',
            `The quoted text exists in the ${seat} corpus, not in this seat's source. A match in a different advisor's file does not pass.`,
          );
        }
      }
    }
    const inGenerated = (context.generatedRoundsText ?? []).some((t) =>
      normalizeQuotedText(t).includes(normalizedQuote)
    );
    if (inGenerated) {
      return fail(
        'QUOTE_ONLY_IN_GENERATED_ROUNDS',
        'The quote appears only in earlier generated rounds. Repetition is not external verification.',
      );
    }
    return fail(
      'QUOTE_TEXT_NOT_IN_SOURCE',
      'The quoted text is not present in the named source version.',
    );
  }

  const speakerMatches = textMatches.filter((u) => {
    const speaker = unitSpeaker(u, record);
    return speaker !== null && sameSpeaker(speaker, tuple.original_speaker);
  });
  if (speakerMatches.length === 0) {
    const actual = unitSpeaker(textMatches[0], record);
    return fail(
      'QUOTE_WRONG_SPEAKER',
      `The text is spoken by ${actual ?? '(unrecorded)'} in the source, not by ${tuple.original_speaker}.`,
    );
  }
  const locatorOk = speakerMatches.some((u) =>
    locatorMatches(tuple.locator, u.locator)
  );
  if (!locatorOk) {
    return fail(
      'QUOTE_LOCATOR_MISMATCH',
      `Locator ${tuple.locator} does not locate this quotation in source ${record.source_id}.`,
    );
  }

  // Rights and scope decide where a verified quote may be released.
  if (context.audience === 'shared_pack') {
    if (record.allowed_scope !== 'shared_pack') {
      return fail(
        'QUOTE_SCOPE_VIOLATION',
        `Source ${record.source_id} is scoped ${record.allowed_scope} and cannot be quoted into a shared pack.`,
      );
    }
    if (
      record.rights_status !== 'licensed_distribution' &&
      record.rights_status !== 'public_domain'
    ) {
      return fail(
        'QUOTE_RIGHTS_NOT_DISTRIBUTABLE',
        `Rights status ${record.rights_status} does not permit releasing a verbatim excerpt in a shared pack.`,
      );
    }
  } else if (record.rights_status === 'reference_only') {
    return fail(
      'QUOTE_RIGHTS_NOT_DISTRIBUTABLE',
      'A reference_only source may be paraphrased with provenance, never quoted verbatim.',
    );
  }

  return { status: 'verified', diagnostics };
}

/**
 * Verify a CWE-003 VerifiedQuoteCandidate from an advisor card. The
 * candidate names an evidence_id; the evidence unit supplies the source,
 * version, and locator the tuple is built from, and the card's seat
 * supplies the speaker the quote is attributed to. The caller resolves
 * the attributed speaker (the seat's display name or the speaker the
 * card asserts) and passes it explicitly.
 */
export function verifyQuoteCandidate(
  candidate: VerifiedQuoteCandidate,
  attributedSpeaker: string,
  corpus: QuoteCorpus,
  context: QuoteContext,
): QuoteVerification {
  const unit = corpus.evidence.find(
    (u) => u.evidence_id === candidate.evidence_id,
  );
  if (!unit) {
    return rejected([
      errorDiagnostic(
        'QUOTE_EVIDENCE_UNKNOWN',
        `Evidence ${candidate.evidence_id} is not in this seat's corpus.`,
      ),
    ]);
  }
  return verifyQuotation(
    {
      quoted_text: candidate.text,
      original_speaker: attributedSpeaker,
      source_id: unit.source_id,
      source_version: unit.source_version,
      locator: candidate.locator,
    },
    corpus,
    context,
  );
}
