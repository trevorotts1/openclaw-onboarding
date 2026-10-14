/**
 * The one report data source (CWE-038, directive Section 24.1).
 *
 * Every format (record JSON, Markdown, print HTML, and the future
 * rendered PDF) is produced from this single model, which is built
 * once from the validated verdict revision, the frozen brief, and the
 * final cards. No format re-derives, rewrites, or re-scores anything:
 * scores, coverage, and the label are copied from the validated
 * verdict exactly as recorded; abstentions are read from the final
 * scoring cards exactly as recorded (a null score entry is an
 * abstention for that option); seat qualifications are printed exactly
 * as the caller recorded them and are never upgraded here.
 *
 * Honesty content carried by construction:
 * - the Section 7 label for every seat whose content appears, built by
 *   the canonical advisorProfileLabel from CWE-003;
 * - the four-authorizations separation notice (Section 1.2): a verdict
 *   export is an advisory record, never an action-plan approval and
 *   never an execution authorization;
 * - the provenance appendix lists evidence identifiers, kinds, and
 *   locators only. No evidence body or source text field exists in
 *   this model, so no export path can carry raw source material
 *   (including the private-scope Brunson source text barred by the
 *   CWE-012 condition 3): exports contain advisor perspective content
 *   and verdict data, never source text.
 *
 * Redaction (Section 24.4) is a transform of this model before any
 * rendering, so a redacted report is a separate identified artifact
 * whose body, metadata, appendix, and filename all derive from the
 * redacted model. Identity and hash fields are never rewritten by
 * redaction: a redacted export still binds to the exact verdict
 * revision it came from.
 */

import {
  advisorProfileLabel,
  canonicalHash,
  CONTRACT_PACKAGE_VERSION,
  SEAT_IDS,
  SEAT_ROSTER,
  type AdvisorCard,
  type CouncilCard,
  type DecisionBrief,
  type RatificationCard,
  type ScoredVerdict,
  type SeatId,
  type Verdict,
} from '../contracts/index.js';
import { ReportExportError } from './errors.js';

export interface RedactionReplacement {
  /** Literal string to remove wherever it appears in report content. */
  match: string;
  /** Replacement text; defaults to '[redacted]'. */
  replace_with?: string;
}

export interface RedactionProfile {
  profile_id: string;
  replacements: RedactionReplacement[];
}

export interface ReportContext {
  /** Host-supplied display date for the report header (Section 24.2 item 1). */
  report_date: string;
  /** Session mode as recorded by the host; null when not recorded. */
  session_mode: string | null;
  /**
   * Selected/observed route as the host records it. When the host does
   * not independently expose the underlying model identity, the
   * CWE-028 hidden-identity statement is the honest default.
   */
  route_display: string;
  /**
   * Per-seat source qualification exactly as recorded by the seat-pack
   * registry (for example 'bibliographic_only'). A seat with no entry
   * is reported as not recorded, never upgraded.
   */
  seat_qualifications: Partial<Record<SeatId, string>>;
}

export const DEFAULT_ROUTE_DISPLAY =
  'Selected route used; underlying model identity not independently exposed.';

export const SIMULATION_LABEL =
  'Simulated advisory perspectives. Every advisor voice in this report is an AI perspective inspired by the published work of the named person. It is not the individual and not an endorsement.';

export const AUTHORIZATION_NOTICE =
  'Authorization boundary: this report records an advisory council verdict only. It is not an action-plan approval and not an execution authorization. Any action proposal listed here requires its own separate approvals before anything is executed; a council verdict is never an execution credential.';

const DISPLAY_NAME_BY_SEAT: Readonly<Record<SeatId, string>> = Object.fromEntries(
  SEAT_ROSTER.map((entry) => [entry.seat_id, entry.display_name]),
) as Record<SeatId, string>;

export function seatDisplayName(seatId: SeatId): string {
  return DISPLAY_NAME_BY_SEAT[seatId];
}

export function seatLabel(seatId: SeatId): string {
  return advisorProfileLabel(DISPLAY_NAME_BY_SEAT[seatId]);
}

/**
 * The cards whose scores the verdict was computed from, using the same
 * rule as CWE-026 publication validation: ratification cards when they
 * exist, otherwise the round-2 advisor cards.
 */
export function scoringCardsOf(
  cards: readonly CouncilCard[],
): Array<AdvisorCard | RatificationCard> {
  const ratification = cards.filter(
    (c): c is RatificationCard => c.card_kind === 'ratification',
  );
  if (ratification.length > 0) return ratification;
  return cards.filter(
    (c): c is AdvisorCard => c.card_kind === 'advisor' && c.round === 2,
  );
}

/** Per-option abstaining seats, read from the scoring cards as recorded. */
export function abstentionsByOption(
  cards: readonly CouncilCard[],
): Map<string, SeatId[]> {
  const byOption = new Map<string, SeatId[]>();
  for (const card of scoringCardsOf(cards)) {
    for (const entry of card.option_scores) {
      if (entry.score !== null) continue;
      const list = byOption.get(entry.option_id) ?? [];
      if (!list.includes(card.seat_id)) list.push(card.seat_id);
      byOption.set(entry.option_id, list);
    }
  }
  for (const list of byOption.values()) {
    list.sort((a, b) => SEAT_IDS.indexOf(a) - SEAT_IDS.indexOf(b));
  }
  return byOption;
}

export interface ReportModelInput {
  verdict: Verdict;
  brief: DecisionBrief;
  final_cards: readonly CouncilCard[];
  context: ReportContext;
  redaction: RedactionProfile | null;
}

/** Model fields that redaction must never rewrite (identity and hashes). */
const REDACTION_PROTECTED_KEYS: ReadonlySet<string> = new Set([
  'schema_version',
  'session_id',
  'seat_id',
  'option_id',
  'evidence_id',
  'constraint_id',
  'action_id',
  'amendment_id',
  'proposing_seat_id',
  'report_revision_id',
  'verdict_content_sha256',
  'brief_sha256',
  'content_sha256',
  'sha256',
  'resolution_sha256',
  'input_manifest_sha256',
  'draft_resolution_sha256',
]);

function redactValue(value: unknown, replacements: RedactionReplacement[]): unknown {
  if (typeof value === 'string') {
    let out = value;
    for (const replacement of replacements) {
      out = out.split(replacement.match).join(replacement.replace_with ?? '[redacted]');
    }
    return out;
  }
  if (Array.isArray(value)) {
    return value.map((item) => redactValue(item, replacements));
  }
  if (value !== null && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, inner] of Object.entries(value as Record<string, unknown>)) {
      out[key] = REDACTION_PROTECTED_KEYS.has(key)
        ? inner
        : redactValue(inner, replacements);
    }
    return out;
  }
  return value;
}

/**
 * The deterministic report revision identity: the same validated
 * verdict revision under the same redaction profile always yields the
 * same report revision, and a redacted report is a distinct revision
 * from the unredacted one.
 */
export function reportRevisionId(args: {
  session_id: string;
  verdict_content_sha256: string;
  redaction_profile_id: string | null;
}): string {
  const hash = canonicalHash({
    session_id: args.session_id,
    verdict_content_sha256: args.verdict_content_sha256,
    redaction_profile_id: args.redaction_profile_id,
  });
  return `report-${hash.slice(0, 32)}`;
}

function scoredModel(input: ReportModelInput, verdict: ScoredVerdict) {
  const { brief, final_cards, context } = input;
  const abstentions = abstentionsByOption(final_cards);
  const optionLabel = new Map(brief.options.map((o) => [o.id, o]));
  const advisorCards = final_cards
    .filter((c): c is AdvisorCard => c.card_kind === 'advisor' && c.round === 2)
    .sort((a, b) => SEAT_IDS.indexOf(a.seat_id) - SEAT_IDS.indexOf(b.seat_id));
  const ratificationBySeat = new Map(
    final_cards
      .filter((c): c is RatificationCard => c.card_kind === 'ratification')
      .map((c) => [c.seat_id, c]),
  );
  const participatingSeatIds = SEAT_IDS.filter(
    (seatId) => brief.relevance_weights[seatId] !== undefined,
  );

  return {
    verdict_block: {
      result_kind: 'scored' as const,
      revision: verdict.verdict_revision,
      label: verdict.label,
      recommended_option_id: verdict.recommended_option_id,
      recommended_option_label:
        verdict.recommended_option_id !== null
          ? (optionLabel.get(verdict.recommended_option_id)?.label ?? null)
          : null,
      validation_status: verdict.validation_status,
      ratification_status: verdict.ratification_status,
      evidence_strength: verdict.evidence_strength,
      content_sha256: verdict.content_sha256,
      brief_sha256: verdict.brief_sha256,
    },
    score_table: verdict.option_scores.map((summary) => ({
      option_id: summary.option_id,
      option_label: optionLabel.get(summary.option_id)?.label ?? summary.option_id,
      option_kind: optionLabel.get(summary.option_id)?.kind ?? null,
      weighted_sum: summary.weighted_sum,
      denominator: summary.denominator,
      score: summary.score,
      display_score: summary.display_score,
      coverage: summary.coverage,
      spread: summary.spread,
      abstained_seat_ids: abstentions.get(summary.option_id) ?? [],
    })),
    main_reasons: [...verdict.main_reasons],
    strongest_dissent: verdict.strongest_dissent,
    prerequisites: [...verdict.prerequisites],
    hard_constraints: verdict.hard_constraint_findings.map((finding) => ({
      constraint_id: finding.constraint_id,
      option_id: finding.option_id,
      result: finding.result,
      checker: finding.checker,
      evidence_ids: [...finding.evidence_ids],
    })),
    amendments: {
      accepted: verdict.accepted_amendments,
      rejected: verdict.rejected_amendments,
    },
    ratification: {
      status: verdict.ratification_status,
      resolution_support: verdict.resolution_support,
    },
    action_proposals: verdict.action_proposals.map((proposal) => ({
      action_id: proposal.action_id,
      title: proposal.title,
      description: proposal.description,
      rationale: proposal.rationale,
      source_condition_ids: [...proposal.source_condition_ids],
      acceptance_criteria: [...proposal.acceptance_criteria],
      depends_on_action_ids: [...proposal.depends_on_action_ids],
      risk_class: proposal.risk_class,
      due_at: proposal.due_at,
      budget_limit: proposal.budget_limit,
      execution_authorization_required: proposal.execution_authorization_required,
    })),
    cheapest_informative_test: verdict.cheapest_informative_test,
    stop_criteria: [...verdict.stop_criteria],
    review_criteria: [...verdict.review_criteria],
    critical_unknowns: [...verdict.critical_unknowns],
    participating_seats: participatingSeatIds.map((seatId) => ({
      seat_id: seatId,
      display_name: seatDisplayName(seatId),
      label: seatLabel(seatId),
      qualification: context.seat_qualifications[seatId] ?? null,
      weight: brief.relevance_weights[seatId] ?? null,
    })),
    seats: advisorCards.map((card) => ({
      seat_id: card.seat_id,
      display_name: seatDisplayName(card.seat_id),
      label: seatLabel(card.seat_id),
      qualification: context.seat_qualifications[card.seat_id] ?? null,
      stance: card.stance,
      preferred_option_id: card.preferred_option_id,
      decisive_arguments: [...card.decisive_arguments],
      strongest_objection: card.strongest_objection,
      change_my_mind: card.change_my_mind,
      minority_position: card.minority_position,
      evidence_strength: card.evidence_strength,
      conditions: card.conditions.map((condition) => ({
        id: condition.id,
        description: condition.description,
        kind: condition.kind,
        blocking: condition.blocking,
        status: condition.status,
      })),
      abstained_option_ids: card.option_scores
        .filter((entry) => entry.score === null)
        .map((entry) => entry.option_id),
      resolution_stance: ratificationBySeat.get(card.seat_id)?.resolution_stance ?? null,
    })),
    consult: null,
  };
}

function consultModel(input: ReportModelInput, verdict: Verdict) {
  if (verdict.result_kind !== 'consult') {
    throw new ReportExportError(
      'EXPORT_VERDICT_INVALID',
      'verdict is neither a scored verdict nor a consult result',
    );
  }
  const card = verdict.consult_card;
  return {
    verdict_block: {
      result_kind: 'consult' as const,
      revision: verdict.verdict_revision,
      label: null,
      recommended_option_id: null,
      recommended_option_label: null,
      validation_status: verdict.validation_status,
      ratification_status: null,
      evidence_strength: null,
      content_sha256: verdict.content_sha256,
      brief_sha256: verdict.brief_sha256,
    },
    score_table: [],
    main_reasons: [],
    strongest_dissent: null,
    prerequisites: [],
    hard_constraints: [],
    amendments: { accepted: [], rejected: [] },
    ratification: { status: null, resolution_support: null },
    action_proposals: [],
    cheapest_informative_test: null,
    stop_criteria: [],
    review_criteria: [],
    critical_unknowns: [],
    participating_seats: [
      {
        seat_id: card.seat_id,
        display_name: seatDisplayName(card.seat_id),
        label: seatLabel(card.seat_id),
        qualification: input.context.seat_qualifications[card.seat_id] ?? null,
        weight: input.brief.relevance_weights[card.seat_id] ?? null,
      },
    ],
    seats: [],
    consult: {
      seat_id: card.seat_id,
      display_name: seatDisplayName(card.seat_id),
      label: seatLabel(card.seat_id),
      answer: card.answer,
      assumptions: [...card.assumptions],
      limits: [...card.limits],
      card_next_step: card.next_step,
      next_step: verdict.next_step,
    },
  };
}

/**
 * Build the one report model. Pure and deterministic: the same input
 * always yields the same model, and therefore the same bytes in every
 * format. The caller (the export service) runs CWE-026 publication
 * validation BEFORE calling this; the model copies validated data and
 * never re-derives a verdict.
 */
export function buildReportModel(input: ReportModelInput): Record<string, unknown> {
  const { verdict, brief, final_cards, context } = input;
  const packVersions = [
    ...new Set(final_cards.map((card) => card.pack_version)),
  ].sort();
  const base =
    verdict.result_kind === 'scored'
      ? scoredModel(input, verdict)
      : consultModel(input, verdict);
  const model: Record<string, unknown> = {
    schema_version: 'wise-elders.report/v1',
    artifact_kind: 'council_decision_report',
    product: 'Council of Wise Elders',
    report_revision_id: reportRevisionId({
      session_id: verdict.session_id,
      verdict_content_sha256: verdict.content_sha256,
      redaction_profile_id: input.redaction?.profile_id ?? null,
    }),
    redacted: input.redaction !== null,
    redaction_profile_id: input.redaction?.profile_id ?? null,
    session_id: verdict.session_id,
    decision_title: brief.question,
    report_date: context.report_date,
    display_timezone: brief.display_timezone,
    session_mode: context.session_mode,
    route_display: context.route_display,
    protocol_version: CONTRACT_PACKAGE_VERSION,
    source_pack_versions: packVersions,
    simulation_label: SIMULATION_LABEL,
    authorization_notice: AUTHORIZATION_NOTICE,
    brief: {
      brief_id: brief.brief_id,
      revision: brief.revision,
      facts: brief.facts.map((fact) => ({
        id: fact.id,
        statement: fact.statement,
        evidence_ids: [...fact.evidence_ids],
      })),
      assumptions: brief.assumptions.map((fact) => fact.statement),
      unknowns: brief.unknowns.map((fact) => fact.statement),
    },
    ...base,
    provenance: {
      evidence_manifest: brief.evidence_manifest.map((entry) => ({
        evidence_id: entry.evidence_id,
        source_kind: entry.source_kind,
        locator: entry.locator,
        sha256: entry.sha256,
      })),
      note: 'Identifiers, kinds, locators, and hashes only. No source text is reproduced in this export.',
    },
  };
  if (input.redaction === null) return model;
  for (const replacement of input.redaction.replacements) {
    if (replacement.match.length === 0) {
      throw new ReportExportError(
        'EXPORT_REQUEST_INVALID',
        'redaction replacement match must not be empty',
      );
    }
  }
  return redactValue(model, input.redaction.replacements) as Record<string, unknown>;
}

/**
 * Post-render redaction assertion (Section 24.4): no redaction target
 * may survive anywhere in the final bytes of an artifact, including
 * metadata and filenames. The service checks every artifact (and its
 * filename) and fails the export rather than shipping a leak.
 */
export function assertRedactionComplete(
  artifacts: Array<{ filename: string; bytes: string }>,
  redaction: RedactionProfile,
): void {
  for (const replacement of redaction.replacements) {
    for (const artifact of artifacts) {
      if (
        artifact.bytes.includes(replacement.match) ||
        artifact.filename.includes(replacement.match)
      ) {
        throw new ReportExportError(
          'EXPORT_REDACTION_INCOMPLETE',
          `redaction profile ${redaction.profile_id} did not remove a target string from ${artifact.filename}; the export was refused rather than shipped with private content`,
        );
      }
    }
  }
}
