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
 *
 * CTR-146 adds reader-facing projections to the same model: a plain
 * summary, the question and its context, each advisor's contribution,
 * the recorded rounds (and what actually changed between them), the
 * verdict with its recorded uncertainty, an ordered plan built from the
 * stored action proposals, a reading guide, and the installed skills and
 * departments that match the plan. Every new field is a projection of
 * already-validated data plus static connective wording; nothing is
 * re-scored, re-ranked, inferred, or invented. A capability snapshot is
 * bound to this session's installation and refused when it is not.
 *
 * CTR-155 corrects the reader projection against the saved record: the
 * brief's unknowns are the canonical Information needed list, readiness is
 * never "ready" for any verdict except GO / GO_WITH_CONDITIONS, unresolved
 * hard constraints and blocking ratification states are stated as
 * readiness reasons, and no list is silently cut to eight rows.
 */

import {
  advisorProfileLabel,
  canonicalHash,
  CONTRACT_PACKAGE_VERSION,
  MODE_ROUND_POLICY,
  SEAT_IDS,
  SEAT_ROSTER,
  type AdvisorCard,
  type CouncilCard,
  type CouncilSize,
  type DecisionBrief,
  type RatificationCard,
  type ScoredVerdict,
  type SeatId,
  type Verdict,
} from '../contracts/index.js';
import {
  assertSnapshotInstallation,
  CAPABILITY_SNAPSHOT_LIMITS,
  matchCapabilitiesToPlan,
  validateCapabilitySnapshot,
  type CapabilityPlanMatch,
  type InstallationCapabilitySnapshot,
} from './capability-snapshot.js';
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
   * True when the exported session is one of the shipped sample
   * sessions (the stored session's sample flag, carried into the export
   * by the host; CWE-048 F-047-1). Sample exports carry the SAMPLE
   * badge on every rendered surface.
   */
  sample?: boolean;
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

  /**
   * CTR-146: the trusted installation this report belongs to. A
   * capability snapshot is attached only when this matches the
   * snapshot's own installation; otherwise the snapshot is refused
   * rather than risking another installation's catalog in a client
   * export. Optional so existing callers keep their exact behaviour
   * (the tools section is then reported as not recorded).
   */
  installation_id?: string | null;

  /**
   * CTR-146: the sitting's own mode-selection provenance, when the host
   * recorded it (`selectMode` returns mode, source, reason). Null means
   * the saved record does not state why this sitting size was chosen —
   * the report says exactly that and never invents a chair rationale.
   */
  mode_selection?: {
    mode: string;
    source: 'client' | 'auto';
    reason: string;
  } | null;

  /**
   * CTR-146: plain-language seat descriptors read from the shipped
   * advisor profile (`role`, `owned_question`). Absent entries simply
   * omit the focus line; nothing is guessed.
   */
  seat_descriptors?: Partial<
    Record<SeatId, { lane: string | null; owned_question: string | null }>
  >;

  /**
   * CTR-146: the installation capability snapshot (skills and
   * departments) used for the reader-facing "Your installed tools"
   * section. Validated here; never executed, never a catalog dump.
   */
  capability_snapshot?: InstallationCapabilitySnapshot | null;
}

/** CTR-146: the exact Council image the report cover may use. */
export const COUNCIL_COVER_IMAGE_REFERENCE = 'assets/seats/cover.png';

/** CTR-146: every printable character is at least this size. */
export const REPORT_MIN_FONT_PT = 14;

/**
 * Cover images are embedded in the print document, so the data URI is
 * capped well under the 6.3 MB shipped original. Asset wiring supplies a
 * compressed derivative; the original is not embedded here.
 */
export const COVER_IMAGE_DATA_URI_MAX_CHARS = 900_000;

const COVER_IMAGE_DATA_URI_RE =
  /^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/;

const VERDICT_LABEL_TEXT: Readonly<Record<string, string>> = {
  GO: 'Go',
  GO_WITH_CONDITIONS: 'Go, with conditions',
  RESHAPE: 'Reshape the plan',
  DONT_DO_IT: 'Do not do it',
  WAIT: 'Wait',
  INSUFFICIENT_EVIDENCE: 'Not enough evidence yet',
};

const STANCE_TEXT: Readonly<Record<string, string>> = {
  support: 'supports it',
  conditional: 'supports it with conditions',
  oppose: 'opposes it',
  abstain: 'abstained',
};

const RESOLUTION_STANCE_TEXT: Readonly<Record<string, string>> = {
  support: 'supported the final resolution',
  conditional_support: 'supported the final resolution with conditions',
  oppose: 'opposed the final resolution',
  abstain: 'abstained on the final resolution',
};

const EVIDENCE_STRENGTH_TEXT: Readonly<Record<string, string>> = {
  low: 'limited',
  medium: 'moderate',
  high: 'strong',
};

const RISK_TEXT: Readonly<Record<string, string>> = {
  low: 'Low risk',
  medium: 'Medium risk',
  high: 'High risk',
  critical: 'Critical risk',
};

const CONDITION_STATUS_TEXT: Readonly<Record<string, string>> = {
  open: 'still open',
  satisfied: 'already met',
  waived_by_owner: 'waived by the owner',
  unresolved: 'still unresolved',
};

const RATIFICATION_TEXT: Readonly<Record<string, string>> = {
  not_required: 'Ratification was not required for this sitting.',
  pending: 'Ratification was still pending when this report was made.',
  ratified: 'The council ratified the final resolution.',
  not_run_by_quick_mode_policy: 'This sitting size does not run a ratification round.',
  material_change_unratified: 'The resolution changed materially after ratification.',
  rejected: 'The council rejected the final resolution.',
};

/** The reading guide printed in every report. Static, true, no claims. */
export const HOW_TO_USE_REPORT: readonly string[] = [
  'Start with the summary, then read the plan. The detail below it is there when you want to check the reasoning.',
  'Each advisor is an AI perspective inspired by a published body of work. It is not the person named and it is not an endorsement.',
  'The council recommendation is advice. Every action still needs its own approval before anyone acts on it.',
  'If the facts change, convene the council again with the new facts. This report stays as the record of this sitting.',
  'After you act, come back to the review items: they say what to measure and when to look again.',
];

export const DEFAULT_ROUTE_DISPLAY =
  'Selected route used; underlying model identity not independently exposed.';

export const SIMULATION_LABEL =
  'Simulated advisory perspectives. Every advisor voice in this report is an AI perspective inspired by the published work of the named person. It is not the individual and not an endorsement.';

export const AUTHORIZATION_NOTICE =
  'Authorization boundary: this report records an advisory council verdict only. It is not an action-plan approval and not an execution authorization. Any action proposal listed here requires its own separate approvals before anything is executed; a council verdict is never an execution credential.';

export const SAMPLE_NOTICE =
  'SAMPLE: this report was exported from one of the shipped sample sessions. Its content is sample material shipped with the package, not a verdict on a real decision.';

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
  // CTR-146 identity fields: redaction never rewrites an installation
  // binding or a capability id.
  'installation_id',
  'capability_id',
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
  // CTR-146: the reader-facing advisor section shows each seat's LAST
  // recorded advisor card. Earlier rounds are compared in the debate
  // section; nothing here re-scores or re-ranks.
  const advisorCards = latestAdvisorCards(final_cards);
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
      abstained_seat_names: (abstentions.get(summary.option_id) ?? []).map((seatId) =>
        seatDisplayName(seatId),
      ),
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
      round: card.round,
      lane: context.seat_descriptors?.[card.seat_id]?.lane ?? null,
      owned_question: context.seat_descriptors?.[card.seat_id]?.owned_question ?? null,
      stance: card.stance,
      preferred_option_id: card.preferred_option_id,
      preferred_option_label:
        card.preferred_option_id !== null
          ? (optionLabel.get(card.preferred_option_id)?.label ?? null)
          : null,
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

// ---------------------------------------------------------------------
// CTR-146 reader-facing projections
//
// Every value below is copied from the validated verdict, the frozen
// brief, or the committed cards. The only new text is static connective
// wording ("The council recommends", "Saved record does not state…").
// Nothing is re-scored, re-ranked, inferred, or invented.
// ---------------------------------------------------------------------

function latestAdvisorCards(cards: readonly CouncilCard[]): AdvisorCard[] {
  const latest = new Map<SeatId, AdvisorCard>();
  for (const card of cards) {
    if (card.card_kind !== 'advisor') continue;
    const current = latest.get(card.seat_id);
    if (current === undefined || card.round > current.round) {
      latest.set(card.seat_id, card);
    }
  }
  return SEAT_IDS.map((seatId) => latest.get(seatId)).filter(
    (card): card is AdvisorCard => card !== undefined,
  );
}

function advisorRounds(
  cards: readonly CouncilCard[],
): Array<{ round: number; cards: AdvisorCard[] }> {
  const byRound = new Map<number, Map<SeatId, AdvisorCard>>();
  for (const card of cards) {
    if (card.card_kind !== 'advisor') continue;
    const seats = byRound.get(card.round) ?? new Map<SeatId, AdvisorCard>();
    if (!seats.has(card.seat_id)) seats.set(card.seat_id, card);
    byRound.set(card.round, seats);
  }
  return [...byRound.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([round, seats]) => ({
      round,
      cards: SEAT_IDS.map((seatId) => seats.get(seatId)).filter(
        (card): card is AdvisorCard => card !== undefined,
      ),
    }));
}

function optionText(
  optionId: string | null,
  brief: DecisionBrief,
): string | null {
  if (optionId === null) return null;
  const option = brief.options.find((entry) => entry.id === optionId);
  return option?.label ?? optionId;
}

function verdictText(label: string | null): string | null {
  if (label === null) return null;
  return VERDICT_LABEL_TEXT[label] ?? label;
}

function stanceText(stance: string): string {
  return STANCE_TEXT[stance] ?? stance;
}

function resolutionStanceText(stance: string | null): string | null {
  if (stance === null) return null;
  return RESOLUTION_STANCE_TEXT[stance] ?? stance;
}

function evidenceStrengthText(strength: string | null): string | null {
  if (strength === null) return null;
  return EVIDENCE_STRENGTH_TEXT[strength] ?? strength;
}

function riskText(risk: string): string {
  return RISK_TEXT[risk] ?? risk;
}

function conditionStatusText(status: string): string {
  return CONDITION_STATUS_TEXT[status] ?? status;
}

function ratificationText(status: string | null): string | null {
  if (status === null) return null;
  return RATIFICATION_TEXT[status] ?? status;
}

function moneyText(limit: { amount_minor: number; currency: string } | null): string | null {
  if (limit === null) return null;
  return `${(limit.amount_minor / 100).toFixed(2)} ${limit.currency}`;
}

function roundPolicyFor(
  mode: string | null,
): {
  seats: number;
  min_rounds: number;
  max_rounds: number;
  stop_from_round: number | null;
  text: string;
} | null {
  if (mode !== 'light' && mode !== 'medium' && mode !== 'heavy') return null;
  const policy = MODE_ROUND_POLICY[mode as CouncilSize];
  const rounds =
    policy.min_rounds === policy.max_rounds
      ? `${policy.min_rounds} rounds`
      : `${policy.min_rounds} to ${policy.max_rounds} rounds`;
  return {
    seats: policy.seats,
    min_rounds: policy.min_rounds,
    max_rounds: policy.max_rounds,
    stop_from_round: policy.stop_from_round,
    text: `${rounds}, all ${policy.seats} advisors in each round.`,
  };
}

const CONDITION_KIND_TEXT: Readonly<Record<string, string>> = {
  evidence_required: 'Evidence needed',
  external_action: 'External action',
  prerequisite: 'Prerequisite',
  safeguard: 'Safeguard',
};

/**
 * Normalized form used ONLY to drop exact repeats. Distinct recorded
 * thresholds stay distinct: "two consecutive weekly episodes" and "at
 * least four repurposed episodes" are different rules and both survive.
 */
function normalizeStatement(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function dedupeStatements(items: readonly string[]): { kept: string[]; removed: number } {
  const seen = new Set<string>();
  const kept: string[] = [];
  let removed = 0;
  for (const raw of items) {
    const text = raw.trim();
    if (text === '') continue;
    const key = normalizeStatement(text);
    if (key === '') continue;
    if (seen.has(key)) {
      removed += 1;
      continue;
    }
    seen.add(key);
    kept.push(text);
  }
  return { kept, removed };
}

/**
 * CTR-155: the transparent frames the SAME fact is wrapped in when it is
 * restated. Removing exactly these — never a content word, never a number,
 * never a threshold — is the only normalization applied to an unknown.
 */
const UNKNOWN_PREFIX_FRAMES: readonly RegExp[] = [
  /^unknown\s*[:,-]\s*/i,
  /^the\s+/i,
];
const UNKNOWN_SUFFIX_FRAMES: readonly RegExp[] = [
  /\s*,?\s*(?:which|that)?\s*(?:is|are)\s+(?:still\s+)?(?:unknown|not\s+stated|not\s+recorded|unclear)\s*\.?$/i,
  /\s*[:,-]\s*$/,
];

function unknownCore(text: string): string {
  let out = text.trim().replace(/\s+/g, ' ');
  let changed = true;
  while (changed) {
    changed = false;
    for (const frame of UNKNOWN_PREFIX_FRAMES) {
      const next = out.replace(frame, '');
      if (next !== out) {
        out = next;
        changed = true;
      }
    }
    for (const frame of UNKNOWN_SUFFIX_FRAMES) {
      const next = out.replace(frame, '');
      if (next !== out) {
        out = next;
        changed = true;
      }
    }
    out = out.trim();
  }
  return out;
}

/**
 * Drop repeats of an unknown after transparent frames are removed, so
 * "Unknown: weekly production hours ..." collapses into "Weekly production
 * hours ... are unknown" while two different thresholds stay two entries.
 */
function dedupeUnknownStatements(items: readonly string[]): {
  kept: string[];
  removed: number;
} {
  const seen = new Set<string>();
  const kept: string[] = [];
  let removed = 0;
  for (const raw of items) {
    const text = raw.trim();
    if (text === '') continue;
    const key = normalizeStatement(unknownCore(text));
    if (key === '') continue;
    if (seen.has(key)) {
      removed += 1;
      continue;
    }
    seen.add(key);
    kept.push(text);
  }
  return { kept, removed };
}

const UNKNOWN_CONTENT_STOPWORDS: ReadonlySet<string> = new Set([
  'about', 'after', 'again', 'against', 'also', 'and', 'any', 'are', 'because',
  'been', 'before', 'being', 'between', 'both', 'but', 'can', 'could', 'does',
  'doing', 'each', 'for', 'from', 'further', 'have', 'having', 'into', 'its',
  'itself', 'more', 'most', 'must', 'not', 'now', 'off', 'once', 'only',
  'other', 'our', 'out', 'over', 'own', 'same', 'should', 'some', 'such',
  'than', 'that', 'the', 'their', 'them', 'then', 'there', 'these', 'they',
  'this', 'those', 'through', 'too', 'under', 'until', 'very', 'was', 'were',
  'what', 'when', 'where', 'which', 'while', 'who', 'whom', 'why', 'will',
  'with', 'would', 'you', 'your',
]);

function unknownContentWords(text: string): string[] {
  return normalizeStatement(unknownCore(text))
    .split(' ')
    .filter((word) => word.length > 3 && !UNKNOWN_CONTENT_STOPWORDS.has(word));
}

interface CanonicalUnknowns {
  information_needed: string[];
  source: 'brief' | 'verdict' | 'none';
  verdict_only_additions: string[];
  council_restatements: string[];
  council_restatements_removed: number;
  council_recorded_count: number;
}

/**
 * CTR-155: the brief's own unknowns are the canonical INFORMATION NEEDED
 * list. The council's critical unknowns are the same facts restated in
 * verdict form, so they stay in the model as the council's record rather
 * than printing a second, near-identical list.
 *
 * A verdict statement is appended only when it names no content word from
 * any brief unknown at all: that is the narrowest safe test for "this is a
 * fact the brief never recorded". No stemming, no scoring, no paraphrase
 * generation, and no threshold merge.
 *
 * ponytail: zero-content-word overlap is the ceiling; upgrade to explicit
 * fact ids if the verdict contract ever carries them.
 */
function canonicalUnknowns(
  briefUnknowns: readonly string[],
  verdictUnknowns: readonly string[],
): CanonicalUnknowns {
  const brief = dedupeUnknownStatements(briefUnknowns);
  const council = dedupeUnknownStatements(verdictUnknowns);
  if (brief.kept.length === 0) {
    return {
      information_needed: council.kept,
      source: council.kept.length > 0 ? 'verdict' : 'none',
      verdict_only_additions: [],
      council_restatements: council.kept,
      council_restatements_removed: council.removed,
      council_recorded_count: verdictUnknowns.filter((text) => text.trim() !== '').length,
    };
  }
  const briefWords = new Set(
    brief.kept.flatMap((statement) => unknownContentWords(statement)),
  );
  const additions: string[] = [];
  for (const statement of council.kept) {
    const words = unknownContentWords(statement);
    if (words.every((word) => !briefWords.has(word))) additions.push(statement);
  }
  return {
    information_needed: [...brief.kept, ...additions],
    source: 'brief',
    verdict_only_additions: additions,
    council_restatements: council.kept,
    council_restatements_removed: council.removed,
    council_recorded_count: verdictUnknowns.filter((text) => text.trim() !== '').length,
  };
}

interface ProjectedCondition {
  condition_id: string;
  advisor: string;
  text: string;
  kind: string;
  kind_text: string;
  blocking: boolean;
  status: string;
  status_text: string;
}

/** Conditions still standing on each seat's last saved card. */
function openConditions(finalCards: readonly CouncilCard[]): ProjectedCondition[] {
  const out: ProjectedCondition[] = [];
  for (const card of latestAdvisorCards(finalCards)) {
    for (const condition of card.conditions) {
      if (condition.status !== 'open' && condition.status !== 'unresolved') continue;
      out.push({
        condition_id: condition.id,
        advisor: seatDisplayName(card.seat_id),
        text: condition.description,
        kind: condition.kind,
        kind_text: CONDITION_KIND_TEXT[condition.kind] ?? condition.kind,
        blocking: condition.blocking,
        status: condition.status,
        status_text: conditionStatusText(condition.status),
      });
    }
  }
  return out;
}

const READY_ELIGIBLE_VERDICTS: ReadonlySet<string> = new Set([
  'GO',
  'GO_WITH_CONDITIONS',
]);

const RATIFICATION_BLOCKS_READINESS: ReadonlySet<string> = new Set([
  'pending',
  'rejected',
  'material_change_unratified',
]);

/**
 * CTR-151/CTR-155: the reader must see the DECISION and the READINESS as two
 * separate things. The verdict is what the council advised; readiness is
 * whether the recorded conditions, the recommended option's hard-constraint
 * checks, and ratification let anyone act yet.
 *
 * CTR-155 corrections:
 * - only GO and GO_WITH_CONDITIONS may ever be called ready; WAIT,
 *   INSUFFICIENT_EVIDENCE, RESHAPE and DONT_DO_IT are always not_ready, with
 *   the verdict named as the reason;
 * - failed or unresolved hard constraints on the recommended option and a
 *   pending/rejected/material-change ratification block readiness;
 * - every blocker and safeguard is listed (no 8-row cut), with totals equal
 *   to the lists;
 * - each reason is stated explicitly, never a broad invented approval.
 */
function readinessBlock(
  finalCards: readonly CouncilCard[],
  verdict: Verdict,
): Record<string, unknown> {
  if (verdict.result_kind !== 'scored') {
    return {
      status: 'not_applicable',
      headline: 'A consultation records advice only, so there is no plan readiness to report.',
      status_reasons: ['This record is a consultation, not a scored decision with a plan.'],
      blockers: [],
      safeguards: [],
      blocker_count: 0,
      safeguard_count: 0,
      blocker_shown: 0,
      safeguard_shown: 0,
      hard_constraint_findings: [],
      hard_constraint_count: 0,
      hard_constraint_fail_count: 0,
      hard_constraint_unknown_count: 0,
      ratification: { status: null, status_text: null, blocks_readiness: false },
      note: 'Readiness does not apply to a consultation.',
    };
  }
  const open = openConditions(finalCards);
  const blockers = open.filter((condition) => condition.blocking);
  const safeguards = open.filter((condition) => !condition.blocking);
  const labelText = verdictText(verdict.label) ?? verdict.label;
  const eligible = READY_ELIGIBLE_VERDICTS.has(verdict.label);

  // CTR-155: a hard constraint that failed or could not be resolved for the
  // RECOMMENDED option is a readiness fact, not hidden behind the verdict.
  const recommendedId = verdict.recommended_option_id;
  const hardFindings = (recommendedId === null ? [] : verdict.hard_constraint_findings)
    .filter(
      (finding) =>
        finding.option_id === recommendedId &&
        (finding.result === 'fail' || finding.result === 'unknown'),
    )
    .map((finding) => ({
      constraint_id: finding.constraint_id,
      option_id: finding.option_id,
      result: finding.result,
      result_text:
        finding.result === 'fail'
          ? 'Failed the check'
          : 'The saved evidence could not resolve this check',
      checker: finding.checker,
      evidence_ids: [...finding.evidence_ids],
    }));
  const hardFailCount = hardFindings.filter(
    (finding) => finding.result === 'fail',
  ).length;
  const hardUnknownCount = hardFindings.filter(
    (finding) => finding.result === 'unknown',
  ).length;

  const ratificationStatus = verdict.ratification_status;
  const ratificationBlocks = RATIFICATION_BLOCKS_READINESS.has(ratificationStatus);
  const ratification = {
    status: ratificationStatus,
    status_text: ratificationText(ratificationStatus),
    blocks_readiness: ratificationBlocks,
  };

  const statusReasons: string[] = [];
  if (!eligible) {
    statusReasons.push(
      `The council verdict was ${labelText}, which is never reported as ready to act.`,
    );
  }
  if (blockers.length > 0) {
    statusReasons.push(
      `${blockers.length} open blocking condition(s) still stand.`,
    );
  }
  if (hardFindings.length > 0) {
    statusReasons.push(
      `${hardFailCount} hard constraint check(s) failed and ${hardUnknownCount} could not be resolved for the recommended option.`,
    );
  }
  if (ratificationBlocks) {
    statusReasons.push(
      ratificationText(ratificationStatus) ??
        `Ratification status ${ratificationStatus} blocks readiness.`,
    );
  }
  const notReady =
    !eligible ||
    blockers.length > 0 ||
    hardFindings.length > 0 ||
    ratificationBlocks;
  const status: 'not_ready' | 'blocked' | 'ready_with_conditions' | 'ready' =
    !eligible
      ? 'not_ready'
      : notReady
        ? 'blocked'
        : safeguards.length > 0
          ? 'ready_with_conditions'
          : 'ready';
  const headline =
    status === 'not_ready'
      ? `Not ready to act: the council verdict was ${labelText}.`
      : status === 'blocked'
        ? `Not ready yet: ${statusReasons.join(' ')}`
        : status === 'ready_with_conditions'
          ? `Ready with conditions: the verdict was ${labelText}, ${safeguards.length} recorded safeguard(s) still apply, and no blocker, unresolved hard constraint or ratification issue is recorded.`
          : `Ready: the verdict was ${labelText} and no open blocker, unresolved hard constraint for the recommended option, or ratification issue is recorded.`;
  if (status === 'ready' || status === 'ready_with_conditions') {
    // CTR-156: state the ACTUAL recorded label. The old sentence hardcoded
    // "Go", which misstated a GO_WITH_CONDITIONS sitting that was eligible
    // with no blockers.
    statusReasons.unshift(
      `The verdict was ${labelText} and no open blocker, unresolved hard constraint for the recommended option, or ratification issue is recorded.`,
    );
  }
  return {
    status,
    headline,
    status_reasons: statusReasons,
    blockers,
    safeguards,
    // Totals and shown lists are identical because nothing is cut. The
    // separate fields stay explicit for any future display subset.
    blocker_count: blockers.length,
    safeguard_count: safeguards.length,
    blocker_shown: blockers.length,
    safeguard_shown: safeguards.length,
    hard_constraint_findings: hardFindings,
    hard_constraint_count: hardFindings.length,
    hard_constraint_fail_count: hardFailCount,
    hard_constraint_unknown_count: hardUnknownCount,
    ratification,
    note: "Readiness is separate from the decision. A verdict is advice; a blocker is a recorded condition that is not met yet, and a hard constraint check is the council's own pass/fail test.",
  };
}


/**
 * CTR-146: the optional cover image is a transport concern, not report
 * content. Asset wiring produces a compressed derivative; the service
 * validates it here and hands it to the print renderer, so the record
 * JSON never carries image bytes.
 */
export function assertCoverImageDataUri(value: string | null | undefined): string | null {
  const candidate = value?.trim() ?? '';
  if (candidate === '') return null;
  if (!COVER_IMAGE_DATA_URI_RE.test(candidate)) {
    throw new ReportExportError(
      'EXPORT_REQUEST_INVALID',
      'cover_image_data_uri must be a base64 data URI for a png, jpeg, or webp image; asset wiring owns producing it',
    );
  }
  if (candidate.length > COVER_IMAGE_DATA_URI_MAX_CHARS) {
    throw new ReportExportError(
      'EXPORT_REQUEST_INVALID',
      `cover_image_data_uri is ${candidate.length} characters; the report limit is ${COVER_IMAGE_DATA_URI_MAX_CHARS}. Supply a compressed derivative of ${COUNCIL_COVER_IMAGE_REFERENCE}.`,
    );
  }
  return candidate;
}

function reportStyleBlock(): Record<string, unknown> {
  return {
    schema_version: 'wise-elders.report-style/v1',
    min_font_pt: REPORT_MIN_FONT_PT,
    cover_image_reference: COUNCIL_COVER_IMAGE_REFERENCE,
  };
}

function capabilitySnapshotOf(
  context: ReportContext,
): InstallationCapabilitySnapshot | null {
  if (!context.capability_snapshot) return null;
  try {
    const snapshot = validateCapabilitySnapshot(context.capability_snapshot);
    assertSnapshotInstallation(snapshot, context.installation_id);
    return snapshot;
  } catch (error) {
    throw new ReportExportError(
      'EXPORT_REQUEST_INVALID',
      error instanceof Error ? error.message : 'the capability snapshot is not valid',
    );
  }
}

function summaryBlock(args: {
  verdict: Verdict;
  brief: DecisionBrief;
  seats: Array<{
    display_name: string;
    stance: string;
    change_my_mind: string;
  }>;
  recommendationLabel: string | null;
  mainReasons: string[];
  strongestDissent: string | null;
  /** CTR-155: the brief's own unknowns are the canonical Information needed. */
  briefUnknowns: string[];
  criticalUnknowns: string[];
  scoreTable: Array<{
    option_label: string;
    coverage: number | null;
    abstained_seat_ids: string[];
  }>;
  hardConstraints: Array<{ result: string }>;
}): Record<string, unknown> {
  const { verdict } = args;
  if (verdict.result_kind === 'consult') {
    return {
      verdict_label: null,
      verdict_label_text: null,
      recommendation_option_id: null,
      recommendation_text: null,
      in_short: verdict.consult_card.answer,
      reasons: [],
      biggest_concern: null,
      ratification_text: null,
      confidence: {
        evidence_strength: null,
        evidence_strength_text: null,
        notes: [],
      },
      what_would_change_the_answer: [],
      what_would_change_the_answer_count: 0,
      what_would_change_the_answer_shown: 0,
      what_would_change_the_answer_removed: 0,
      information_needed: [],
      information_needed_count: 0,
      information_needed_shown: 0,
      information_needed_source: 'none',
      information_needed_note: null,
      // Present on the consult branch too: the shared reader contract reads
      // these fields on every summary, so an absent key must not be read as
      // an empty array by a renderer that calls `.length`.
      verdict_only_additions: [] as string[],
      council_unknowns: [],
      council_unknowns_count: 0,
      council_unknowns_shown: 0,
      council_unknowns_removed: 0,
    };
  }

  const label = verdict.label;
  const labelText = verdictText(label);
  const recommendationText =
    args.recommendationLabel ?? 'No option was recommended.';
  // CTR-151: decision first, in one short sentence, using only recorded
  // values. The old sentence repeated the label twice and buried the
  // recommendation behind it.
  const inShort =
    args.recommendationLabel !== null
      ? `The verdict was ${labelText ?? label}. The council recommends ${args.recommendationLabel}.`
      : `The verdict was ${labelText ?? label}. The council did not recommend an option.`;

  const uncertainty: string[] = [];
  const strength = evidenceStrengthText(verdict.evidence_strength);
  if (strength !== null) {
    uncertainty.push(`The council rated its evidence as ${strength}.`);
  }
  const lowCoverage = args.scoreTable
    .filter((row) => row.coverage !== null && row.coverage < 1)
    .sort((a, b) => (a.coverage ?? 0) - (b.coverage ?? 0))[0];
  if (lowCoverage !== undefined) {
    uncertainty.push(
      `Coverage was ${((lowCoverage.coverage ?? 0) * 100).toFixed(2)}% on ${lowCoverage.option_label}.`,
    );
  } else if (args.scoreTable.length > 0) {
    uncertainty.push('Every participating seat scored every option.');
  }
  const abstainers = new Set<string>();
  for (const row of args.scoreTable) {
    for (const seatId of row.abstained_seat_ids) abstainers.add(seatIdDisplayName(seatId));
  }
  if (abstainers.size > 0) {
    uncertainty.push(`${[...abstainers].join(', ')} abstained on at least one option.`);
  }
  const unknownConstraints = args.hardConstraints.filter(
    (finding) => finding.result === 'unknown',
  ).length;
  if (unknownConstraints > 0) {
    uncertainty.push(
      `${unknownConstraints} hard constraint check(s) could not be resolved from the saved evidence.`,
    );
  }

  // CTR-151/CTR-155: two different questions get two different lists. What
  // would change an advisor's mind is decision advice; the information
  // needed is the brief's own unknown record, with any genuinely new
  // council fact appended. Nothing is sliced, so a count can never exceed
  // the rows the reader is given.
  const changeMyMind = dedupeStatements(
    args.seats.map((seat) => seat.change_my_mind),
  ).kept;
  const info = canonicalUnknowns(args.briefUnknowns, args.criticalUnknowns);
  const informationNeeded = info.information_needed;
  let informationNeededNote: string | null = null;
  if (info.source === 'brief') {
    const briefCount = args.briefUnknowns.filter((text) => text.trim() !== '').length;
    const additionText =
      info.verdict_only_additions.length > 0
        ? `, plus ${info.verdict_only_additions.length} council fact(s) the brief did not record`
        : '';
    informationNeededNote =
      `The brief recorded ${briefCount} unknown(s); the council restated them ${info.council_recorded_count} times, ` +
      `leaving ${info.council_restatements.length} unique council statement(s). The brief's unknowns are the information needed${additionText}.`;
  } else if (info.source === 'verdict') {
    informationNeededNote =
      `The brief recorded no unknown; the council's ${informationNeeded.length} critical unknown(s) are the information needed.`;
  }

  return {
    verdict_label: label,
    verdict_label_text: labelText,
    recommendation_option_id: verdict.recommended_option_id,
    recommendation_text: recommendationText,
    in_short: inShort,
    reasons: dedupeStatements(args.mainReasons).kept,
    biggest_concern: args.strongestDissent,
    ratification_text: ratificationText(verdict.ratification_status),
    confidence: {
      evidence_strength: verdict.evidence_strength,
      evidence_strength_text: evidenceStrengthText(verdict.evidence_strength),
      notes: uncertainty,
    },
    what_would_change_the_answer: changeMyMind,
    // CTR-156: count is the number of RECORDED non-empty seat statements
    // BEFORE frame de-duplication; shown is the de-duplicated list; removed
    // is the difference. All three are printed from these fields, so a count
    // can never be read as larger than the rows without the collapse being
    // stated. No statement is dropped beyond an exact frame-normalised repeat.
    what_would_change_the_answer_count: args.seats.filter(
      (seat) => seat.change_my_mind.trim() !== '',
    ).length,
    what_would_change_the_answer_shown: changeMyMind.length,
    what_would_change_the_answer_removed:
      args.seats.filter((seat) => seat.change_my_mind.trim() !== '').length -
      changeMyMind.length,
    information_needed: informationNeeded,
    information_needed_count: informationNeeded.length,
    information_needed_shown: informationNeeded.length,
    information_needed_source: info.source,
    information_needed_note: informationNeededNote,
    verdict_only_additions: info.verdict_only_additions,
    council_unknowns: info.council_restatements,
    // CTR-156 semantics, printed explicitly: `count` is the recorded total
    // BEFORE frame de-duplication (10 on the saved sitting); `shown` is the
    // distinct rows (8); `removed` is the collapsed repeats (2). A reader
    // shows `shown` rows and states `removed`, never prints `count` as if it
    // were the row count.
    council_unknowns_count: info.council_recorded_count,
    council_unknowns_shown: info.council_restatements.length,
    council_unknowns_removed: info.council_restatements_removed,
  };
}

function seatIdDisplayName(seatId: string): string {
  return SEAT_IDS.includes(seatId as SeatId)
    ? seatDisplayName(seatId as SeatId)
    : seatId;
}

/**
 * CTR-155: a constraint applies to every option only when the recorded ids
 * are EXACTLY the option set: every option once, no duplicate, no unknown id.
 * Equal length alone proved nothing because the validator does not require
 * real or unique ids.
 */
function appliesToAllOptions(
  brief: DecisionBrief,
  optionIds: readonly string[],
): boolean {
  const options = new Set(brief.options.map((option) => option.id));
  if (options.size === 0) return false;
  const seen = new Set<string>();
  for (const optionId of optionIds) {
    if (!options.has(optionId) || seen.has(optionId)) return false;
    seen.add(optionId);
  }
  return seen.size === options.size;
}

function questionBlock(brief: DecisionBrief, verdict: Verdict): Record<string, unknown> {
  // CTR-151/CTR-155: the brief's unknown and the council's critical unknown
  // were printed back to back even when they said the same thing. Repeats
  // are shown once after transparent frames are removed ("Unknown: ...",
  // "... are unknown", "... is not stated"); different statements, and
  // different thresholds, are never merged. Totals stay explicit.
  const briefUnknowns = brief.unknowns.map((fact) => fact.statement);
  const councilUnknowns =
    verdict.result_kind === 'scored' ? verdict.critical_unknowns : [];
  const unknowns = dedupeUnknownStatements([
    ...briefUnknowns,
    ...councilUnknowns,
  ]);
  const recordedTotal =
    briefUnknowns.filter((text) => text.trim() !== '').length +
    councilUnknowns.filter((text) => text.trim() !== '').length;
  return {
    question: brief.question,
    facts: brief.facts.map((fact) => ({
      statement: fact.statement,
      evidence_ids: [...fact.evidence_ids],
    })),
    assumptions: brief.assumptions.map((fact) => fact.statement),
    unknowns: unknowns.kept,
    unknowns_count: recordedTotal,
    unknowns_shown: unknowns.kept.length,
    unknowns_note:
      unknowns.removed > 0
        ? `${unknowns.removed} repeated unknown statement(s) were shown once.`
        : null,
    constraints: brief.constraints.map((constraint) => ({
      description: constraint.description,
      hard: constraint.hard,
      applies_to_option_labels: constraint.applies_to_option_ids.map(
        (optionId) => optionText(optionId, brief) ?? optionId,
      ),
      applies_to_all_options: appliesToAllOptions(
        brief,
        constraint.applies_to_option_ids,
      ),
    })),
    options: brief.options.map((option) => ({
      option_id: option.id,
      option_label: option.label,
      option_kind: option.kind,
    })),
  };
}

function advisorContributions(
  cards: readonly CouncilCard[],
  brief: DecisionBrief,
  context: ReportContext,
): Record<string, unknown>[] {
  return latestAdvisorCards(cards).map((card) => {
    const descriptor = context.seat_descriptors?.[card.seat_id];
    return {
      seat_id: card.seat_id,
      display_name: seatDisplayName(card.seat_id),
      label: seatLabel(card.seat_id),
      lane: descriptor?.lane ?? null,
      owned_question: descriptor?.owned_question ?? null,
      qualification: context.seat_qualifications[card.seat_id] ?? null,
      round: card.round,
      stance: card.stance,
      stance_text: stanceText(card.stance),
      preferred_option_id: card.preferred_option_id,
      preferred_option_label: optionText(card.preferred_option_id, brief),
      what_they_argued: [...card.decisive_arguments],
      strongest_objection: card.strongest_objection,
      what_would_change_their_mind: card.change_my_mind,
      minority_position: card.minority_position,
      confidence_text: evidenceStrengthText(card.evidence_strength),
      conditions: card.conditions.map((condition) => ({
        id: condition.id,
        description: condition.description,
        kind: condition.kind,
        blocking: condition.blocking,
        status_text: conditionStatusText(condition.status),
      })),
      resolution_stance_text: resolutionStanceText(
        cards.find(
          (entry): entry is RatificationCard =>
            entry.card_kind === 'ratification' && entry.seat_id === card.seat_id,
        )?.resolution_stance ?? null,
      ),
    };
  });
}

function debateBlock(
  cards: readonly CouncilCard[],
  brief: DecisionBrief,
  context: ReportContext,
): Record<string, unknown> {
  const rounds = advisorRounds(cards);
  const policy = roundPolicyFor(context.session_mode);
  const highest = rounds.length > 0 ? rounds[rounds.length - 1].round : null;
  const notes: string[] = [];

  if (rounds.length === 0) {
    notes.push('No advisor cards are saved in this record, so the debate cannot be reconstructed.');
  } else if (rounds.length === 1) {
    notes.push(
      `Only one round of advisor cards is saved in this record (round ${rounds[0].round}), so a before-and-after comparison is not possible.`,
    );
  } else {
    notes.push(`${rounds.length} rounds of advisor cards are saved in this record.`);
  }

  const modeSelection = context.mode_selection ?? null;
  if (modeSelection !== null) {
    notes.push(
      `Sitting size: ${modeSelection.mode} (${modeSelection.source === 'client' ? 'chosen by the client' : 'chosen automatically'}). Recorded reason: ${modeSelection.reason}`,
    );
  } else if (policy !== null) {
    notes.push(
      `Sitting size: ${context.session_mode}. ${policy.text} The saved record does not state why this size was chosen.`,
    );
  } else if (context.session_mode !== null) {
    notes.push(
      `Sitting size recorded as ${context.session_mode}. The saved record does not state why this size was chosen.`,
    );
  } else {
    notes.push('The saved record does not state the sitting size.');
  }

  if (policy !== null && highest !== null) {
    notes.push(
      highest >= policy.max_rounds
        ? `The saved cards reach the ${policy.max_rounds}-round ceiling for this size.`
        : `The saved cards stop before the ${policy.max_rounds}-round ceiling for this size.`,
    );
  }
  notes.push(
    'The saved record contains no chair note explaining a stop decision; only the cards above are recorded.',
  );

  const changes: Array<Record<string, unknown>> = [];
  for (let index = 1; index < rounds.length; index += 1) {
    const previous = new Map(rounds[index - 1].cards.map((card) => [card.seat_id, card]));
    for (const card of rounds[index].cards) {
      const before = previous.get(card.seat_id);
      if (before === undefined) continue;
      const changedOption = before.preferred_option_id !== card.preferred_option_id;
      const changedStance = before.stance !== card.stance;
      if (!changedOption && !changedStance) continue;
      changes.push({
        round: rounds[index].round,
        seat_id: card.seat_id,
        display_name: seatDisplayName(card.seat_id),
        from_option_label: optionText(before.preferred_option_id, brief),
        to_option_label: optionText(card.preferred_option_id, brief),
        from_stance_text: stanceText(before.stance),
        to_stance_text: stanceText(card.stance),
        changed_option: changedOption,
        changed_stance: changedStance,
      });
    }
  }

  const latest = latestAdvisorCards(cards);
  const byOption = new Map<string, string[]>();
  const abstained: string[] = [];
  for (const card of latest) {
    if (card.stance === 'abstain') abstained.push(seatDisplayName(card.seat_id));
    const key = card.preferred_option_id ?? '';
    const list = byOption.get(key) ?? [];
    list.push(seatDisplayName(card.seat_id));
    byOption.set(key, list);
  }
  const positions = [...byOption.entries()]
    .sort((a, b) => {
      if (a[0] === '') return 1;
      if (b[0] === '') return -1;
      return a[0].localeCompare(b[0]);
    })
    .map(([optionId, names]) => ({
      option_id: optionId === '' ? null : optionId,
      option_label: optionId === '' ? 'No stated preference' : optionText(optionId, brief),
      seat_names: names,
    }));

  if (rounds.length > 0) {
    if (positions.filter((entry) => entry.option_id !== null).length > 1) {
      notes.push('The council split on which option to prefer; the groups are listed below.');
    } else {
      notes.push(
        'The council did not split on which option to prefer; the disagreement is in the reasoning and objections each advisor recorded.',
      );
    }
  }

  // CTR-151: how much of the round-by-round detail actually differs. When
  // no seat changed, the reader is told once instead of reading the same
  // nine positions again for every saved round.
  const roundSupport = rounds.map((entry, index) => {
    const counts: Record<'support' | 'conditional' | 'oppose' | 'abstain', number> = {
      support: 0,
      conditional: 0,
      oppose: 0,
      abstain: 0,
    };
    for (const card of entry.cards) counts[card.stance] += 1;
    const previous = index > 0 ? rounds[index - 1] : null;
    const identicalToPrevious =
      previous !== null &&
      previous.cards.length === entry.cards.length &&
      entry.cards.every((card) => {
        const before = previous.cards.find((candidate) => candidate.seat_id === card.seat_id);
        return (
          before !== undefined &&
          before.stance === card.stance &&
          before.preferred_option_id === card.preferred_option_id
        );
      });
    return {
      round: entry.round,
      support: counts.support,
      conditional: counts.conditional,
      oppose: counts.oppose,
      abstain: counts.abstain,
      identical_to_previous: identicalToPrevious,
    };
  });

  return {
    rounds_saved: rounds.length,
    highest_round: highest,
    mode: context.session_mode,
    mode_selection: modeSelection,
    round_policy: policy,
    rounds: rounds.map((entry) => ({
      round: entry.round,
      seats: entry.cards.map((card) => ({
        seat_id: card.seat_id,
        display_name: seatDisplayName(card.seat_id),
        stance: card.stance,
        stance_text: stanceText(card.stance),
        preferred_option_id: card.preferred_option_id,
        preferred_option_label: optionText(card.preferred_option_id, brief),
      })),
    })),
    round_support: roundSupport,
    condensed_note:
      rounds.length > 1 && changes.length === 0
        ? 'No advisor changed position between the saved rounds, so the earlier rounds repeat the same positions. Read the final positions below; the earlier rounds add no new stance.'
        : null,
    changes,
    positions,
    abstained_names: abstained,
    notes,
  };
}

function orderedActions(
  proposals: ScoredVerdict['action_proposals'],
): {
  actions: ScoredVerdict['action_proposals'];
  ordered_by_dependencies: boolean;
  missing_dependency_ids: string[];
} {
  const originalIndex = new Map(proposals.map((proposal, index) => [proposal.action_id, index]));
  const known = new Set(proposals.map((proposal) => proposal.action_id));
  const missing = new Set<string>();
  const dependencies = new Map<string, string[]>();
  const dependents = new Map<string, string[]>();
  for (const proposal of proposals) {
    const deps = proposal.depends_on_action_ids.filter((actionId) => {
      if (!known.has(actionId)) {
        missing.add(actionId);
        return false;
      }
      return true;
    });
    dependencies.set(proposal.action_id, deps);
    for (const dep of deps) {
      const list = dependents.get(dep) ?? [];
      list.push(proposal.action_id);
      dependents.set(dep, list);
    }
  }
  const indegree = new Map(
    proposals.map((proposal) => [
      proposal.action_id,
      (dependencies.get(proposal.action_id) ?? []).length,
    ]),
  );
  const byOriginal = (a: string, b: string): number =>
    (originalIndex.get(a) ?? 0) - (originalIndex.get(b) ?? 0);
  const ready = proposals
    .map((proposal) => proposal.action_id)
    .filter((actionId) => (indegree.get(actionId) ?? 0) === 0)
    .sort(byOriginal);
  const orderedIds: string[] = [];
  while (ready.length > 0) {
    const actionId = ready.shift() as string;
    orderedIds.push(actionId);
    const next = [...(dependents.get(actionId) ?? [])].sort(byOriginal);
    for (const dependent of next) {
      const remaining = (indegree.get(dependent) ?? 0) - 1;
      indegree.set(dependent, remaining);
      if (remaining === 0) {
        ready.push(dependent);
        ready.sort(byOriginal);
      }
    }
  }
  const ordered_by_dependencies = orderedIds.length === proposals.length;
  if (!ordered_by_dependencies) {
    for (const proposal of proposals) {
      if (!orderedIds.includes(proposal.action_id)) orderedIds.push(proposal.action_id);
    }
  }
  const byId = new Map(proposals.map((proposal) => [proposal.action_id, proposal]));
  return {
    actions: orderedIds
      .map((actionId) => byId.get(actionId))
      .filter((proposal) => proposal !== undefined),
    ordered_by_dependencies,
    missing_dependency_ids: [...missing].sort(),
  };
}

function planBlock(
  verdict: Verdict,
  brief: DecisionBrief,
  helpfulToolsByAction: ReadonlyMap<string, readonly string[]> = new Map(),
): Record<string, unknown> {
  if (verdict.result_kind !== 'scored') {
    return {
      steps: [],
      step_count: 0,
      ordering: 'recorded_order',
      prerequisites: [],
      cheapest_test: null,
      cheapest_test_status: 'not_recorded',
      cheapest_test_note: 'A consultation records no action plan and no test.',
      stop_if: [],
      stop_if_status: 'not_recorded',
      review_criteria: [],
      review_criteria_status: 'not_recorded',
      dependency_note: 'A consultation records no action steps.',
      start_with_step_numbers: [],
      start_here_step_number: null,
      parallel_eligible_step_numbers: [],
      parallel_eligible_note: null,
      shared_why: null,
      shared_why_applies_to_step_numbers: [],
      done_when_recorded_count: 0,
      done_when_not_recorded_count: 0,
    };
  }
  const ordered = orderedActions(verdict.action_proposals);
  const stepNumber = new Map(
    ordered.actions.map((proposal, index) => [proposal.action_id, index + 1]),
  );
  const stopIf = dedupeStatements(verdict.stop_criteria).kept;
  const reviewCriteria = dedupeStatements(verdict.review_criteria).kept;
  // When every step carries the same recorded rationale, say it once.
  const rationales = ordered.actions
    .map((proposal) => proposal.rationale.trim())
    .filter((text) => text !== '');
  const sharedWhy =
    rationales.length > 1 && rationales.every((text) => text === rationales[0])
      ? rationales[0]
      : null;
  const startWith = ordered.actions
    .map((proposal, index) => ({ proposal, index }))
    .filter(
      ({ proposal }) =>
        proposal.depends_on_action_ids.filter((actionId) => stepNumber.has(actionId))
          .length === 0,
    )
    .map(({ index }) => index + 1);
  // CTR-155: one clear first recorded action, plus the honest fact that more
  // than one step may have no recorded dependency. No dependency is invented
  // and the recorded order is never reordered beyond the saved chain.
  const startHere = startWith.length > 0 ? startWith[0] : null;
  const parallelEligible = [...startWith];
  const parallelNote =
    parallelEligible.length > 1
      ? `Steps ${parallelEligible.join(', ')} record no dependency on another saved step, so they can run in parallel. The order below is still the recorded order.`
      : null;
  const steps = ordered.actions.map((proposal, index) => {
      const deps = proposal.depends_on_action_ids
        .map((actionId) => stepNumber.get(actionId))
        .filter((step): step is number => step !== undefined);
      const doneWhen = dedupeStatements(proposal.acceptance_criteria).kept;
      return {
        step_number: index + 1,
        action_id: proposal.action_id,
        title: proposal.title,
        what_to_do: proposal.description,
        why: proposal.rationale,
        depends_on_step_numbers: deps,
        depends_on_missing_action_ids: proposal.depends_on_action_ids.filter(
          (actionId) => !stepNumber.has(actionId),
        ),
        done_when: doneWhen,
        // CTR-151: an empty list is an honest gap, not a blank label. The
        // reader gets a sentence saying the record did not state a finish
        // line; no criterion, metric, or deadline is invented here.
        done_when_status: doneWhen.length > 0 ? 'recorded' : 'not_recorded',
        done_when_note:
          doneWhen.length > 0
            ? null
            : 'The saved record did not state how to know this step is finished. Decide your own finish line before starting.',
        // A renderer always has a concise sentence, never an empty label.
        done_when_display:
          doneWhen.length > 0
            ? doneWhen.join('; ')
            : 'Not recorded. Decide your own finish line before starting.',
        why_is_shared: sharedWhy !== null,
        risk_class: proposal.risk_class,
        risk_text: riskText(proposal.risk_class),
        due_date: proposal.due_at === null ? null : proposal.due_at.slice(0, 10),
        budget_text: moneyText(proposal.budget_limit),
        recorded_department_id: proposal.department_id,
        recorded_sop_id: proposal.sop_id,
        recorded_persona_id: proposal.persona_id,
        recorded_agent_id: proposal.assigned_agent_id,
        needs_separate_approval: proposal.execution_authorization_required,
        approval_text: proposal.execution_authorization_required
          ? 'This step needs its own approval before anyone acts on it.'
          : null,
        helpful_tool_names: [...(helpfulToolsByAction.get(proposal.action_id) ?? [])],
      };
    });
  const doneWhenNotRecorded = steps.filter(
    (step) => step.done_when_status === 'not_recorded',
  ).length;
  return {
    steps,
    step_count: steps.length,
    ordering: ordered.ordered_by_dependencies
      ? 'recorded_dependencies'
      : 'recorded_order',
    start_with_step_numbers: startWith,
    start_here_step_number: startHere,
    parallel_eligible_step_numbers: parallelEligible,
    parallel_eligible_note: parallelNote,
    shared_why: sharedWhy,
    shared_why_applies_to_step_numbers:
      sharedWhy === null ? [] : steps.map((step) => step.step_number),
    done_when_recorded_count: steps.length - doneWhenNotRecorded,
    done_when_not_recorded_count: doneWhenNotRecorded,
    prerequisites: dedupeStatements(verdict.prerequisites).kept,
    cheapest_test: verdict.cheapest_informative_test,
    cheapest_test_status:
      verdict.cheapest_informative_test !== null &&
      verdict.cheapest_informative_test.trim() !== ''
        ? 'recorded'
        : 'not_recorded',
    cheapest_test_note:
      verdict.cheapest_informative_test !== null &&
      verdict.cheapest_informative_test.trim() !== ''
        ? null
        : 'The saved record did not name a cheapest useful test. Pick the smallest test that would settle the biggest unknown before spending more.',
    stop_if: stopIf,
    stop_if_status: stopIf.length > 0 ? 'recorded' : 'not_recorded',
    review_criteria: reviewCriteria,
    review_criteria_status: reviewCriteria.length > 0 ? 'recorded' : 'not_recorded',
    dependency_note: ordered.ordered_by_dependencies
      ? null
      : 'The recorded dependencies contain a cycle, so the steps are listed in their recorded order.',
    brief_options: brief.options.map((option) => ({
      option_id: option.id,
      option_label: option.label,
    })),
  };
}

function toolsBlock(verdict: Verdict, context: ReportContext): Record<string, unknown> {
  const snapshot = capabilitySnapshotOf(context);
  if (snapshot === null) {
    return {
      status: 'not_recorded',
      snapshot_date: null,
      basis: null,
      basis_text: null,
      items: [] as CapabilityPlanMatch[],
      items_total: 0,
      items_shown: 0,
      note: 'This report does not list installed skills or departments because no verified inventory was recorded for this saved report.',
      limitations: [] as string[],
    };
  }
  const basisText =
    snapshot.basis === 'at_sitting'
      ? `Recorded at the sitting on ${snapshot.captured_at}.`
      : `Checked on this installation on ${snapshot.captured_at}.`;
  const proposals =
    verdict.result_kind === 'scored'
      ? verdict.action_proposals.map((proposal) => ({
          action_id: proposal.action_id,
          title: proposal.title,
          description: proposal.description,
          department_id: proposal.department_id,
          sop_id: proposal.sop_id,
          persona_id: proposal.persona_id,
          assigned_agent_id: proposal.assigned_agent_id,
        }))
      : [];
  // CTR-158: the matcher returns every exact match. The reader-facing list
  // keeps the display bound, and the total/shown fields make any bound
  // visible on the HTML and Markdown exports.
  const allItems = matchCapabilitiesToPlan(snapshot, proposals);
  const items = allItems.slice(0, CAPABILITY_SNAPSHOT_LIMITS.max_matched_steps);
  const base = {
    snapshot_date: snapshot.captured_at,
    basis: snapshot.basis,
    basis_text: basisText,
    items_total: allItems.length,
    items_shown: items.length,
    limitations: [...snapshot.limitations],
  };
  if (proposals.length === 0) {
    return {
      ...base,
      status: 'no_plan',
      items: [] as CapabilityPlanMatch[],
      note: 'This sitting recorded no action steps, so no installed tool is linked to a step.',
    };
  }
  if (items.length === 0) {
    return {
      ...base,
      status: 'no_match',
      items: [] as CapabilityPlanMatch[],
      note: 'No installed skill or department on this installation is recorded in, or named by, any step of this plan. Nothing is suggested rather than guessing from shared words. Ask your OpenClaw agent if you want to look for one.',
    };
  }
  return {
    ...base,
    status: 'matched',
    items,
    note: 'These helpers are already installed on this box because the plan records them or a step names them exactly. Installed is not the same as operational, and a match is a suggestion, not a promise that the tool can run a step for you; confirm with your OpenClaw agent before relying on it.',
  };
}


export interface ReaderProjectionInput {
  verdict: Verdict;
  brief: DecisionBrief;
  final_cards: readonly CouncilCard[];
  /**
   * Only a live export has installation context. A session read passes
   * nothing: the tools section then reports "not recorded" rather than
   * borrowing a catalog from another installation.
   */
  context?: ReportContext | null;
}

/**
 * CTR-156: ONE reader projection, built from the corrected model, consumed by
 * both the report renderer and the chamber. Every field is a projection of
 * already-validated saved data plus static connective wording: nothing is
 * re-scored, re-ranked, inferred, or invented. The same function is called by
 * buildReportModel (export path) and by the session read (chamber path), so
 * the two surfaces cannot tell the reader two different stories.
 */
export function buildReaderProjection(
  input: ReaderProjectionInput,
): Record<string, unknown> {
  const { verdict, brief, final_cards } = input;
  const context: ReportContext = input.context ?? {
    report_date: '',
    session_mode: null,
    route_display: '',
    seat_qualifications: {},
    installation_id: null,
    capability_snapshot: null,
  };
  const optionLabel = new Map(brief.options.map((option) => [option.id, option]));
  const abstentions = abstentionsByOption(final_cards);
  const summarySeats = latestAdvisorCards(final_cards).map((card) => ({
    display_name: seatDisplayName(card.seat_id),
    stance: card.stance,
    change_my_mind: card.change_my_mind,
  }));
  const readerSummary = summaryBlock({
    verdict,
    brief,
    seats: summarySeats,
    recommendationLabel:
      verdict.result_kind === 'scored' && verdict.recommended_option_id !== null
        ? (optionLabel.get(verdict.recommended_option_id)?.label ?? null)
        : null,
    mainReasons: verdict.result_kind === 'scored' ? verdict.main_reasons : [],
    strongestDissent:
      verdict.result_kind === 'scored' ? verdict.strongest_dissent : null,
    briefUnknowns: brief.unknowns.map((fact) => fact.statement),
    criticalUnknowns:
      verdict.result_kind === 'scored' ? verdict.critical_unknowns : [],
    scoreTable:
      verdict.result_kind === 'scored'
        ? verdict.option_scores.map((row) => ({
            option_label: optionLabel.get(row.option_id)?.label ?? row.option_id,
            coverage: row.coverage,
            abstained_seat_ids: abstentions.get(row.option_id) ?? [],
          }))
        : [],
    hardConstraints:
      verdict.result_kind === 'scored'
        ? verdict.hard_constraint_findings.map((finding) => ({ result: finding.result }))
        : [],
  });
  const tools = toolsBlock(verdict, context);
  const readiness = readinessBlock(final_cards, verdict);
  const scoredVerdict = verdict.result_kind === 'scored' ? verdict : null;
  const recommendationLabel =
    scoredVerdict !== null && scoredVerdict.recommended_option_id !== null
      ? (optionLabel.get(scoredVerdict.recommended_option_id)?.label ?? null)
      : null;
  // CTR-155: two sentences, so the verdict and the recommendation cannot be
  // misparsed as one run-on sentence.
  const decisionHeadline =
    scoredVerdict === null
      ? 'A consultation records advice, not a scored decision.'
      : recommendationLabel !== null
        ? `The council verdict was ${verdictText(scoredVerdict.label) ?? scoredVerdict.label}. It recommends ${recommendationLabel}.`
        : `The council verdict was ${verdictText(scoredVerdict.label) ?? scoredVerdict.label}. It did not recommend an option.`;
  const toolItems = Array.isArray(tools.items)
    ? (tools.items as CapabilityPlanMatch[])
    : [];
  const helpfulToolsByAction = new Map<string, string[]>();
  for (const item of toolItems) {
    const label = `${item.name} (${item.kind})`;
    for (const actionId of item.matched_action_ids) {
      const list = helpfulToolsByAction.get(actionId) ?? [];
      list.push(label);
      helpfulToolsByAction.set(actionId, list);
    }
  }
  return {
    reader_projection_version: 1,
    summary: readerSummary,
    // CTR-151/CTR-156: the decision and the readiness are separate facts,
    // stated once each, so a screen and the PDF cannot tell the reader two
    // different stories.
    decision_vs_readiness: {
      decision: {
        verdict_label: scoredVerdict?.label ?? null,
        verdict_label_text: scoredVerdict ? verdictText(scoredVerdict.label) : null,
        recommendation_option_id: scoredVerdict?.recommended_option_id ?? null,
        recommendation_text: recommendationLabel,
        headline: decisionHeadline,
      },
      readiness,
      distinction_note:
        'The decision is the council advice. Readiness is whether the recorded conditions, the recommended option hard-constraint checks, and ratification let you act now. They can disagree: a GO can still be blocked, and only GO or GO_WITH_CONDITIONS is ever eligible to be called ready.',
    },
    plan: planBlock(verdict, brief, helpfulToolsByAction),
    your_tools: tools,
    // The order the reader should meet this material in. Detail comes last.
    reader_order: [
      'summary',
      'decision_vs_readiness',
      'plan',
      'question_and_context',
      'advisor_contributions',
      'debate',
      'your_tools',
      'how_to_use',
      'provenance',
    ],
  };
}

export function buildReportModel(input: ReportModelInput): Record<string, unknown> {
  const { verdict, brief, final_cards, context } = input;
  const packVersions = [
    ...new Set(final_cards.map((card) => card.pack_version)),
  ].sort();
  const base =
    verdict.result_kind === 'scored'
      ? scoredModel(input, verdict)
      : consultModel(input, verdict);
  // CTR-156: the export and the chamber read the same projection.
  const projection = buildReaderProjection({ verdict, brief, final_cards, context });
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
    installation_id: context.installation_id ?? null,
    decision_title: brief.question,
    report_date: context.report_date,
    display_timezone: brief.display_timezone,
    session_mode: context.session_mode,
    sample: context.sample === true,
    sample_notice: context.sample === true ? SAMPLE_NOTICE : null,
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
    // CTR-146 reader-facing projections. Additive: every field above is
    // unchanged, so record-JSON consumers keep their exact contract.
    report_style: reportStyleBlock(),
    // CTR-156: summary, decision_vs_readiness, plan, your_tools and
    // reader_order all come from the ONE reader projection that the chamber
    // also consumes. No format re-derives them.
    ...projection,
    question_and_context: questionBlock(brief, verdict),
    advisor_contributions: advisorContributions(final_cards, brief, context),
    debate: debateBlock(final_cards, brief, context),
    how_to_use: [...HOW_TO_USE_REPORT],
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
