/**
 * CWE-023 deterministic critical-domain classification from structured
 * intake facts (directive Section 12.7).
 *
 * Classification reads ONLY structured intake material: the decision
 * flags answered with the decision question, and the typed constraint
 * kinds. No keyword guessing, no model proposal surface at intake:
 * a model may propose tags during an authorized intake step elsewhere,
 * but nothing here can remove a domain these facts trigger.
 *
 * The composition mirrors the frozen semantics CWE-026 owns for
 * scoring (T143): the fixed reviewer table from Section 12.7, canonical
 * domain order, and freeze-time status: a domain with recorded open
 * questions is `unresolved`; otherwise `not_assessed` (nothing has
 * assessed it yet). The panel overlay lives in panel.ts: a triggered
 * domain whose responsible seat is not on the chosen panel stays
 * `not_assessed` in the frozen brief as well, because the assessment
 * the verdict would need cannot happen.
 *
 * CWE-050 reconciliation note: CWE-026 implements
 * classifyCriticalDomains(brief, policyVersion) over signals for its
 * scoring fixtures. This module derives the signals from intake and
 * freezes the resulting requirements INTO the brief, which is the
 * artifact scoring reads; the two compositions must agree on the
 * fixed table and status rules above.
 */
import {
  CRITICAL_DOMAINS,
  criticalDomainRequirementSchema,
  type CriticalDomain,
  type CriticalDomainRequirement,
  type SeatId,
} from '../contracts/index.js';
import {
  CRITICAL_DOMAIN_POLICY_VERSION,
  IntakeError,
  type IntakeDraft,
} from './types.js';

/** Fixed reviewer table from Section 12.7. Never a model choice. */
export const CRITICAL_DOMAIN_REVIEWERS: Readonly<
  Record<
    CriticalDomain,
    {
      required_seat_id: SeatId | null;
      required_checker: 'seat' | 'qualified_professional';
      reviewer_note: string;
    }
  >
> = {
  financial_feasibility: {
    required_seat_id: 'tiffany-aliche',
    required_checker: 'seat',
    reviewer_note:
      'Tiffany Aliche reviews affordability; missing affordability evidence or a financial-review abstention prevents a GO-style endorsement of the exposed option.',
  },
  demand_and_delivery: {
    required_seat_id: 'russell-brunson',
    required_checker: 'seat',
    reviewer_note:
      'Russell Brunson reviews whether demand evidence and delivery capacity support the option.',
  },
  purpose_and_commitments: {
    required_seat_id: 'simon-sinek',
    required_checker: 'seat',
    reviewer_note:
      'Simon Sinek reviews purpose and commitments; a real violated commitment disqualifies its option unless a legitimately approved revision resolves it.',
  },
  trust_and_stakeholders: {
    required_seat_id: 'brene-brown',
    required_checker: 'seat',
    reviewer_note:
      'Brené Brown reviews trust and stakeholders, with Michelle Obama and Oprah Winfrey when relevant; privacy and consent failures are hard constraints.',
  },
  communication: {
    required_seat_id: 'td-jakes',
    required_checker: 'seat',
    reviewer_note:
      "T. D. Jakes reviews communication through the communication lens of his single seat.",
  },
  qualified_professional_review: {
    required_seat_id: null,
    required_checker: 'qualified_professional',
    reviewer_note:
      'A qualified professional reviews; no celebrity seat substitutes, and no professional conclusion is certified by model vote.',
  },
};

/** The open question each triggered domain carries into the brief. */
const DOMAIN_OPEN_QUESTIONS: Readonly<Record<CriticalDomain, string>> = {
  financial_feasibility:
    'Can the client make this commitment without destabilizing the foundation that supports their life and business?',
  demand_and_delivery:
    'Who wants this, how will they find it, and can the client deliver what the option promises?',
  purpose_and_commitments:
    'Does this decision express why the business exists, and is it consistent with the commitments already made?',
  trust_and_stakeholders:
    'What difficult conversation or vulnerable action is being avoided, and what would trustworthy leadership require?',
  communication:
    'How must this decision be communicated to the people affected, and will they understand it?',
  qualified_professional_review:
    'Which qualified professional review is required before this decision can be acted on?',
};

interface DomainSignal {
  domain: CriticalDomain;
  factIds: Set<string>;
  fieldPaths: Set<string>;
}

/**
 * Derive the triggered domains from the draft's structured answers.
 * Pure and deterministic: the same draft always yields the same set.
 */
export function deriveSignals(draft: IntakeDraft): Map<CriticalDomain, DomainSignal> {
  const signals = new Map<CriticalDomain, DomainSignal>();
  const add = (domain: CriticalDomain, fieldPath: string, factId?: string): void => {
    let signal = signals.get(domain);
    if (!signal) {
      signal = { domain, factIds: new Set(), fieldPaths: new Set() };
      signals.set(domain, signal);
    }
    signal.fieldPaths.add(fieldPath);
    if (factId) signal.factIds.add(factId);
  };

  const flags = draft.answers.decision?.flags;
  if (flags) {
    if (flags.involves_money_commitment) add('financial_feasibility', 'answers.decision.flags.involves_money_commitment');
    if (flags.involves_offer_or_pricing) add('demand_and_delivery', 'answers.decision.flags.involves_offer_or_pricing');
    if (flags.involves_rebrand_or_pivot) add('purpose_and_commitments', 'answers.decision.flags.involves_rebrand_or_pivot');
    if (flags.involves_stakeholder_trust) add('trust_and_stakeholders', 'answers.decision.flags.involves_stakeholder_trust');
    if (flags.decision_is_communication) add('communication', 'answers.decision.flags.decision_is_communication');
    if (flags.involves_professional_domain) add('qualified_professional_review', 'answers.decision.flags.involves_professional_domain');
  }
  for (const constraint of draft.answers.constraints ?? []) {
    const path = `answers.constraints.${constraint.id}`;
    if (constraint.kind === 'budget_cash') add('financial_feasibility', path, constraint.id);
    if (constraint.kind === 'capacity') add('demand_and_delivery', path, constraint.id);
    if (constraint.kind === 'obligation') add('purpose_and_commitments', path, constraint.id);
    if (constraint.kind === 'prohibition') add('trust_and_stakeholders', path, constraint.id);
  }
  return signals;
}

/**
 * Compose the frozen critical-domain requirements for a brief.
 *
 * `panelSeatIds` applies the Section 12.7 panel overlay: a triggered
 * domain whose responsible seat is not on the panel stays
 * `not_assessed`. For qualified_professional_review the overlay is the
 * arranged flag: unarranged professional review is `not_assessed`.
 */
export function classifyIntakeDomains(args: {
  draft: IntakeDraft;
  panelSeatIds: readonly SeatId[] | null;
  professionalReviewArranged: boolean | null;
}): CriticalDomainRequirement[] {
  const signals = deriveSignals(args.draft);
  const requirements: CriticalDomainRequirement[] = [];
  for (const domain of CRITICAL_DOMAINS) {
    const signal = signals.get(domain);
    if (!signal) continue;
    const reviewer = CRITICAL_DOMAIN_REVIEWERS[domain];
    const openQuestions = [DOMAIN_OPEN_QUESTIONS[domain]];
    let status: CriticalDomainRequirement['status'] =
      openQuestions.length > 0 ? 'unresolved' : 'not_assessed';
    if (reviewer.required_checker === 'qualified_professional') {
      if (args.professionalReviewArranged !== true) status = 'not_assessed';
    } else if (
      args.panelSeatIds !== null &&
      reviewer.required_seat_id !== null &&
      !args.panelSeatIds.includes(reviewer.required_seat_id)
    ) {
      status = 'not_assessed';
    }
    const requirement: CriticalDomainRequirement = {
      schema_version: 'wise-elders.critical-domain-requirement/v1',
      domain,
      status,
      trigger_evidence_ids: [...signal.factIds],
      trigger_field_paths: [...signal.fieldPaths],
      required_seat_id: reviewer.required_seat_id,
      required_checker: reviewer.required_checker,
      unresolved_questions: openQuestions,
      policy_version: CRITICAL_DOMAIN_POLICY_VERSION,
    };
    const parsed = criticalDomainRequirementSchema.safeParse(requirement);
    if (!parsed.success) {
      throw new IntakeError(
        'INTAKE_BRIEF_INVALID',
        `Classified requirement for ${domain} failed contract validation.`,
        { issues: parsed.error.issues.map((i) => i.message) },
      );
    }
    requirements.push(parsed.data);
  }
  return requirements;
}
