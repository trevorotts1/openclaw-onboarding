/**
 * CWE-023 brief composition (directive Sections 9.1, 9.4, 11.6, 12.1).
 *
 * Composition is deterministic: the same draft and revision number
 * always produce the same DecisionBrief and therefore the same
 * canonical content hash. The composed brief is validated against the
 * CWE-003 canonical contract before it is saved anywhere.
 *
 * Honesty rules enforced here:
 * - Client statements, retrieved facts, assumptions, ranges, and
 *   unknowns stay distinguishable (T017): confirmed facts compose
 *   into facts; assumptions compose into assumptions; scaffold
 *   placeholders and explicit unknowns compose into unknowns, never
 *   into facts (T014).
 * - The client's preference is never composed in. The brief carries
 *   only private_preference_ref, the opaque ID of the separate
 *   preference record.
 * - Relevance weights freeze with the brief (Section 12.1): seats
 *   responsible for a triggered critical domain weigh 3, other panel
 *   seats weigh 2. A weight correction after freeze requires a new
 *   revision by construction, because any change changes the hash.
 */
import {
  canonicalHash,
  validateDecisionBrief,
  type DecisionBrief,
  type SeatId,
  type TypedFact,
} from '../contracts/index.js';
import { classifyIntakeDomains } from './classify.js';
import {
  IntakeError,
  type IntakeDraft,
  type IntakeFact,
} from './types.js';

function toTypedFact(fact: IntakeFact): TypedFact {
  return { id: fact.id, statement: fact.statement, evidence_ids: [...fact.evidence_ids] };
}

/** Compose the DecisionBrief for `revision` from the current draft. */
export function composeBrief(args: {
  draft: IntakeDraft;
  revision: number;
  createdAt: string;
}): DecisionBrief {
  const { draft, revision, createdAt } = args;
  const answers = draft.answers;
  if (answers.decision === null || answers.options === null) {
    throw new IntakeError(
      'INTAKE_NOT_READY',
      'The brief cannot be composed before the decision and its options are answered.',
    );
  }

  // Facts: retrieved confirmed facts first (they were here before the
  // questions), then client statements, in the order they were given.
  const facts: TypedFact[] = [
    ...draft.known_facts
      .filter((f) => f.origin === 'retrieved_confirmed')
      .map(toTypedFact),
    ...(answers.facts ?? [])
      .filter((f) => f.origin !== 'scaffold_unconfirmed')
      .map(toTypedFact),
  ];

  // Unknowns: the client's explicit unknowns, any unconfirmed scaffold
  // placeholders (never facts, T014), and explicit unknown answers.
  const unknowns: TypedFact[] = [...(answers.unknowns ?? [])];
  const scaffold: IntakeFact[] = [
    ...draft.known_facts.filter((f) => f.origin === 'scaffold_unconfirmed'),
    ...(answers.facts ?? []).filter((f) => f.origin === 'scaffold_unconfirmed'),
  ];
  for (const fact of scaffold) unknowns.push(toTypedFact(fact));
  if (answers.success?.explicit_unknown) {
    unknowns.push({
      id: 'unknown-success-outcome',
      statement: 'The success outcome is not yet known; the client stated this explicitly at intake.',
      evidence_ids: [],
    });
  }
  if (draft.constraints_explicit_unknown) {
    unknowns.push({
      id: 'unknown-constraints',
      statement: 'The applicable constraints are not yet known; the client stated this explicitly at intake.',
      evidence_ids: [],
    });
  }
  if (draft.facts_explicit_unknown) {
    unknowns.push({
      id: 'unknown-facts',
      statement: 'No facts are confirmed yet; the client stated this explicitly at intake.',
      evidence_ids: [],
    });
  }
  const panelSeatIds = draft.panel_seat_ids;
  const criticalDomains = classifyIntakeDomains({
    draft,
    panelSeatIds,
    professionalReviewArranged: draft.professional_review_arranged,
  });

  // Relevance weights (Section 12.1): 3 for a seat responsible for a
  // triggered critical domain, 2 for every other panel seat.
  const responsibleSeats = new Set(
    criticalDomains
      .map((d) => d.required_seat_id)
      .filter((s): s is SeatId => s !== null),
  );
  const relevanceWeights: Partial<Record<SeatId, number>> = {};
  for (const seatId of panelSeatIds ?? []) {
    relevanceWeights[seatId] = responsibleSeats.has(seatId) ? 3 : 2;
  }

  const brief: DecisionBrief = {
    schema_version: 'wise-elders.brief/v1',
    brief_id: draft.brief_id,
    session_id: draft.session_id,
    revision,
    question: answers.decision.statement,
    facts,
    assumptions: [...(answers.assumptions ?? [])],
    unknowns,
    constraints: (answers.constraints ?? []).map((c) => ({
      id: c.id,
      description: c.description,
      hard: c.hard,
      applies_to_option_ids: [...c.applies_to_option_ids],
    })),
    options: answers.options.map((o) => ({ ...o })),
    relevance_weights: relevanceWeights,
    critical_domains: criticalDomains,
    evidence_manifest: draft.evidence_manifest.map((e) => ({ ...e })),
    private_preference_ref: draft.preference_ref,
    created_at: createdAt,
    display_timezone: draft.display_timezone,
  };
  const check = validateDecisionBrief(brief);
  if (!check.ok) {
    throw new IntakeError('INTAKE_BRIEF_INVALID', 'The composed brief failed contract validation.', {
      issues: check.issues,
    });
  }
  return check.value;
}

/** The canonical content hash of a brief revision (Sections 11.6, 17). */
export function briefContentHash(brief: DecisionBrief): string {
  return canonicalHash(brief);
}

/**
 * The frozen evidence manifest hash recorded on the freeze record:
 * the canonical hash of exactly the brief's evidence manifest, the
 * manifest of authorized evidence assembled via CWE-022.
 */
export function evidenceManifestHash(brief: DecisionBrief): string {
  return canonicalHash({ evidence_manifest: brief.evidence_manifest });
}
