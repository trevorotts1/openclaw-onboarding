/**
 * Frozen critical-domain classification (directive Section 12.7, CWE-026).
 *
 * classifyCriticalDomains is a deterministic rule service over structured
 * intake facts and constraint tags. It runs BEFORE Round 1 and its output
 * is frozen inside the reviewed brief (the brief's critical_domains), so
 * scoring later reads a fixed classification, never a re-derived one.
 *
 * Rules held here:
 * - The required reviewer for each domain is a fixed table from Section
 *   12.7, never a model choice. No celebrity seat substitutes for a
 *   qualified professional review.
 * - A model may PROPOSE a domain tag, and a proposal triggers the domain.
 *   A model removal request can never silently remove a triggered
 *   domain: removals of triggered domains are reported as rejected, and
 *   the domain stays.
 * - Trigger facts and field paths are recorded on every requirement, so
 *   the freeze is traceable (test contract T143).
 * - Classification can be per-option: a signal that names option IDs
 *   restricts the domain to those options; no option list means the
 *   domain applies to every option.
 *
 * This module is a pure service: no host, network, filesystem, clock, or
 * random dependency. It consumes the CWE-003 contracts read-only.
 */

import {
  canonicalHash,
  ContractError,
  CRITICAL_DOMAINS,
  criticalDomainRequirementSchema,
  type CriticalDomain,
  type CriticalDomainRequirement,
  type DecisionBrief,
  type SeatId,
} from '../contracts/index.js';

/** Fixed reviewer table from Section 12.7. */
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
      'T. D. Jakes reviews communication through the communication lens of his single seat.',
  },
  qualified_professional_review: {
    required_seat_id: null,
    required_checker: 'qualified_professional',
    reviewer_note:
      'A qualified professional reviews; no celebrity seat substitutes, and no professional conclusion is certified by model vote.',
  },
};

/** One structured signal that a critical domain may be triggered. */
export interface CriticalDomainSignal {
  domain: CriticalDomain;
  /**
   * Where the signal came from. Intake facts and constraint tags are the
   * authoritative triggers; a model proposal also triggers, but a model
   * can never remove (see model_removal_requests on the input).
   */
  origin: 'intake_fact' | 'constraint_tag' | 'model_proposal';
  /** Structured intake fact IDs that triggered the domain. */
  trigger_fact_ids: string[];
  /** Field paths that triggered the domain, for example constraints.con-1. */
  trigger_field_paths: string[];
  /** Options the domain applies to; empty means every option. */
  applies_to_option_ids: string[];
  /** Questions already known to be open at freeze time. */
  open_questions: string[];
}

export interface CriticalDomainClassificationInput {
  signals: CriticalDomainSignal[];
  /** The frozen policy version recorded on every requirement. */
  policy_version: string;
  /**
   * Domains a model asked to remove. A removal never takes effect on a
   * triggered domain; each such request is returned in rejected_removals.
   */
  model_removal_requests?: CriticalDomain[];
}

/** Per-option applicability of a domain; absence of pairs means global. */
export interface CriticalDomainApplicability {
  domain: CriticalDomain;
  option_id: string;
}

export interface CriticalDomainClassification {
  /** Schema-valid frozen requirements, in canonical domain order. */
  requirements: CriticalDomainRequirement[];
  /** Option restrictions; a domain with no pairs applies to all options. */
  applicability: CriticalDomainApplicability[];
  /** One deterministic explanation per triggered domain. */
  explanations: string[];
  /** Model removal requests that targeted a triggered domain. */
  rejected_removals: CriticalDomain[];
  /** Canonical hash of the frozen requirements (traceability, T143). */
  classification_sha256: string;
}

function unionInto(target: Set<string>, values: readonly string[]): void {
  for (const value of values) target.add(value);
}

/**
 * Classify critical domains from structured signals. Pure and
 * deterministic: the same input always yields the same frozen output.
 */
export function classifyCriticalDomains(
  input: CriticalDomainClassificationInput,
): CriticalDomainClassification {
  if (!input.policy_version) {
    throw new ContractError(
      'SCHEMA_VALIDATION',
      'classifyCriticalDomains requires a policy_version',
      'policy_version',
    );
  }
  const byDomain = new Map<
    CriticalDomain,
    {
      factIds: Set<string>;
      fieldPaths: Set<string>;
      optionIds: Set<string>;
      questions: Set<string>;
      origins: Set<string>;
    }
  >();
  for (const signal of input.signals) {
    if (!CRITICAL_DOMAINS.includes(signal.domain)) {
      throw new ContractError(
        'UNKNOWN_ENUM_VALUE',
        `unknown critical domain ${String(signal.domain)}`,
        'signals.domain',
      );
    }
    let entry = byDomain.get(signal.domain);
    if (!entry) {
      entry = {
        factIds: new Set(),
        fieldPaths: new Set(),
        optionIds: new Set(),
        questions: new Set(),
        origins: new Set(),
      };
      byDomain.set(signal.domain, entry);
    }
    unionInto(entry.factIds, signal.trigger_fact_ids);
    unionInto(entry.fieldPaths, signal.trigger_field_paths);
    unionInto(entry.optionIds, signal.applies_to_option_ids);
    unionInto(entry.questions, signal.open_questions);
    entry.origins.add(signal.origin);
  }

  const requirements: CriticalDomainRequirement[] = [];
  const applicability: CriticalDomainApplicability[] = [];
  const explanations: string[] = [];
  for (const domain of CRITICAL_DOMAINS) {
    const entry = byDomain.get(domain);
    if (!entry) continue;
    const reviewer = CRITICAL_DOMAIN_REVIEWERS[domain];
    const unresolvedQuestions = [...entry.questions];
    const requirement: CriticalDomainRequirement = {
      schema_version: 'wise-elders.critical-domain-requirement/v1',
      domain,
      // Frozen before Round 1 nothing has been assessed yet: a domain
      // with known open questions is unresolved, otherwise not_assessed.
      status: unresolvedQuestions.length > 0 ? 'unresolved' : 'not_assessed',
      trigger_evidence_ids: [...entry.factIds],
      trigger_field_paths: [...entry.fieldPaths],
      required_seat_id: reviewer.required_seat_id,
      required_checker: reviewer.required_checker,
      unresolved_questions: unresolvedQuestions,
      policy_version: input.policy_version,
    };
    const parsed = criticalDomainRequirementSchema.safeParse(requirement);
    if (!parsed.success) {
      throw new ContractError(
        'SCHEMA_VALIDATION',
        `classified requirement for ${domain} failed schema validation: ${parsed.error.issues
          .map((i) => i.message)
          .join('; ')}`,
        'requirements',
      );
    }
    requirements.push(parsed.data);
    for (const optionId of entry.optionIds) {
      applicability.push({ domain, option_id: optionId });
    }
    const triggers = [...entry.fieldPaths, ...entry.factIds].join(', ') || 'no recorded trigger';
    explanations.push(
      `${domain} triggered by ${triggers} (origins: ${[...entry.origins].join(', ')}); required reviewer: ${
        reviewer.required_seat_id ?? 'qualified professional'
      } (${reviewer.required_checker}). ${reviewer.reviewer_note}`,
    );
  }

  const rejectedRemovals = (input.model_removal_requests ?? []).filter((domain) =>
    byDomain.has(domain),
  );

  return {
    requirements,
    applicability,
    explanations,
    rejected_removals: rejectedRemovals,
    classification_sha256: canonicalHash(requirements),
  };
}

/**
 * Per-option critical-domain applicability derived from a frozen brief
 * (CWE-050 consolidation: this is the ONE implementation; the copies
 * that lived in protocol/verdict.ts and protocol/ratification.ts were
 * byte-identical and now import this). A requirement whose trigger
 * paths name brief constraints (the canonical `constraints.<id>`
 * dialect) applies to the options those constraints apply to; a
 * requirement with no such restriction contributes no pairs and is
 * global (absence of pairs means global).
 */
export function deriveCriticalDomainApplicability(
  brief: DecisionBrief,
): CriticalDomainApplicability[] {
  const pairs: CriticalDomainApplicability[] = [];
  const constraintOptions = new Map<string, string[]>(
    brief.constraints.map((c) => [c.id, c.applies_to_option_ids]),
  );
  for (const requirement of brief.critical_domains) {
    const restricted = new Set<string>();
    for (const path of requirement.trigger_field_paths) {
      const match = /^constraints\.([A-Za-z0-9-]+)$/.exec(path);
      if (!match) continue;
      const optionIds = constraintOptions.get(match[1]);
      if (optionIds && optionIds.length > 0) {
        for (const id of optionIds) restricted.add(id);
      }
    }
    for (const optionId of restricted) {
      pairs.push({ domain: requirement.domain, option_id: optionId });
    }
  }
  return pairs;
}
