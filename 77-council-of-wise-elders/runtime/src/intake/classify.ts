/**
 * CWE-023 deterministic critical-domain classification from structured
 * intake facts (directive Section 12.7), reconciled by CWE-050.
 *
 * Classification reads ONLY structured intake material: the decision
 * flags answered with the decision question, and the typed constraint
 * kinds. No keyword guessing, no model proposal surface at intake:
 * a model may propose tags during an authorized intake step elsewhere,
 * but nothing here can remove a domain these facts trigger.
 *
 * CWE-050 reconciliation (CWE-023 carried item, decided for ONE
 * implementation): the composition is scoring/critical-domains.ts
 * `classifyCriticalDomains` (CWE-026), including its fixed Section
 * 12.7 reviewer table. This module now only (1) derives
 * CriticalDomainSignal[] from the intake draft, (2) calls the canonical
 * classifier with the intake policy version, and (3) applies the
 * intake panel overlay: a triggered domain whose responsible seat is
 * not on the chosen panel stays `not_assessed` in the frozen brief,
 * because the assessment the verdict would need cannot happen; an
 * unarranged qualified-professional review is likewise `not_assessed`.
 * The overlay is intake's Section 12.7 panel concern and stays here.
 *
 * Trigger-path dialect: constraint triggers are recorded in the
 * canonical `constraints.<id>` form (the dialect the ONE applicability
 * derivation in scoring/critical-domains.ts consumes), so briefs frozen
 * by intake carry applicability the completion side can recompute.
 * Decision-flag paths keep the `answers.decision.flags.<name>` form;
 * no derivation consumes them. Disclosure: briefs frozen by this
 * reconciled classifier differ in constraint trigger paths (and
 * therefore in canonical brief hash) from briefs frozen by the
 * pre-reconciliation intake classifier; no production briefs exist,
 * and the golden fixtures remain the arbiter.
 */
import {
  CRITICAL_DOMAINS,
  type CriticalDomain,
  type CriticalDomainRequirement,
  type SeatId,
} from '../contracts/index.js';
import {
  classifyCriticalDomains,
  CRITICAL_DOMAIN_REVIEWERS,
  type CriticalDomainSignal,
} from '../scoring/critical-domains.js';
import {
  CRITICAL_DOMAIN_POLICY_VERSION,
  type IntakeDraft,
} from './types.js';

// The reviewer table lives once, in scoring/critical-domains.ts
// (CWE-026). Re-exported so existing intake consumers keep working.
export { CRITICAL_DOMAIN_REVIEWERS };

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
 * Constraint field paths use the canonical `constraints.<id>` dialect.
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
    const path = `constraints.${constraint.id}`;
    if (constraint.kind === 'budget_cash') add('financial_feasibility', path, constraint.id);
    if (constraint.kind === 'capacity') add('demand_and_delivery', path, constraint.id);
    if (constraint.kind === 'obligation') add('purpose_and_commitments', path, constraint.id);
    if (constraint.kind === 'prohibition') add('trust_and_stakeholders', path, constraint.id);
  }
  return signals;
}

/**
 * Compose the frozen critical-domain requirements for a brief by
 * delegating to the ONE canonical classifier (CWE-026) and applying
 * the intake panel overlay (see the module header).
 */
export function classifyIntakeDomains(args: {
  draft: IntakeDraft;
  panelSeatIds: readonly SeatId[] | null;
  professionalReviewArranged: boolean | null;
}): CriticalDomainRequirement[] {
  const derived = deriveSignals(args.draft);
  const signals: CriticalDomainSignal[] = [];
  for (const domain of CRITICAL_DOMAINS) {
    const signal = derived.get(domain);
    if (!signal) continue;
    signals.push({
      domain,
      origin: [...signal.factIds].length > 0 ? 'constraint_tag' : 'intake_fact',
      trigger_fact_ids: [...signal.factIds],
      trigger_field_paths: [...signal.fieldPaths],
      applies_to_option_ids: [],
      open_questions: [DOMAIN_OPEN_QUESTIONS[domain]],
    });
  }
  const { requirements } = classifyCriticalDomains({
    signals,
    policy_version: CRITICAL_DOMAIN_POLICY_VERSION,
  });
  // Intake panel overlay (Section 12.7): the canonical classifier has
  // no panel knowledge; a domain whose assessment cannot happen on
  // this panel freezes as not_assessed.
  return requirements.map((requirement) => {
    const reviewer = CRITICAL_DOMAIN_REVIEWERS[requirement.domain];
    let status = requirement.status;
    if (reviewer.required_checker === 'qualified_professional') {
      if (args.professionalReviewArranged !== true) status = 'not_assessed';
    } else if (
      args.panelSeatIds !== null &&
      reviewer.required_seat_id !== null &&
      !args.panelSeatIds.includes(reviewer.required_seat_id)
    ) {
      status = 'not_assessed';
    }
    return status === requirement.status ? requirement : { ...requirement, status };
  });
}
