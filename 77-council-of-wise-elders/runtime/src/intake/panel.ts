/**
 * CWE-023 panel rules for the four intake modes (directive Sections
 * 10 and 12.7).
 *
 * For selected and quick panels the required critical responsibilities
 * are computed and displayed BEFORE start. A panel missing a critical
 * responsibility keeps that assessment `not_assessed`, which blocks a
 * GO-style endorsement downstream where that assessment is necessary.
 * The system may RECOMMEND including the responsible seat; it never
 * silently changes the client's chosen panel. The client may retain
 * the subset; the missing assessment stays visible.
 *
 * Quick mode records its Round 3 skip prerequisites verbatim at
 * freeze (Section 10 gate). The skip DECISION is evaluated on the
 * run's cards by CWE-025 (T022); this module records the prerequisites
 * and the exact status string a skip must carry, it does not evaluate
 * them.
 */
import {
  SEAT_IDS,
  type CriticalDomain,
  type CriticalDomainRequirement,
  type SeatId,
  type SessionMode,
} from '../contracts/index.js';
import { CRITICAL_DOMAIN_REVIEWERS } from './classify.js';
import { IntakeError, type IntakeDraft } from './types.js';

/** Validate a chosen panel against the mode's seat-count rules. */
export function validatePanel(
  mode: SessionMode,
  seatIds: readonly SeatId[],
): void {
  const fail = (message: string): never => {
    throw new IntakeError('INTAKE_PANEL_INVALID', message, {
      mode,
      seat_ids: [...seatIds],
    });
  };
  const unique = new Set(seatIds);
  if (unique.size !== seatIds.length) fail('The panel contains a duplicate seat.');
  for (const seatId of seatIds) {
    if (!(SEAT_IDS as readonly string[]).includes(seatId)) {
      fail(`Unknown seat ${seatId}.`);
    }
  }
  switch (mode) {
    case 'full':
      if (seatIds.length !== SEAT_IDS.length) {
        fail('Full mode keeps all nine seats.');
      }
      break;
    case 'selected':
      if (seatIds.length < 2 || seatIds.length > 8) {
        fail('Selected mode requires 2 to 8 seats.');
      }
      break;
    case 'quick':
      if (seatIds.length !== 4) {
        fail('Quick mode requires exactly four named seats.');
      }
      break;
    case 'consult':
      if (seatIds.length !== 1) {
        fail('Consult mode requires exactly one seat.');
      }
      break;
    case 'light':
      if (seatIds.length !== SEAT_IDS.length) {
        fail('Light mode keeps all nine seats.');
      }
      break;
    case 'medium':
    case 'heavy':
      if (seatIds.length !== SEAT_IDS.length) {
        fail(`${mode === 'medium' ? 'Medium' : 'Heavy'} mode keeps all nine seats.`);
      }
      break;
  }
}

export interface RequiredResponsibility {
  readonly domain: CriticalDomain;
  readonly required_seat_id: SeatId | null;
  readonly required_checker: 'seat' | 'qualified_professional';
  readonly reviewer_note: string;
  /** Whether the chosen panel covers this responsibility. */
  readonly on_panel: boolean;
  /**
   * Effective pre-start status. A missing responsibility stays
   * `not_assessed`; a covered one is `unresolved` until the run's
   * assessment exists.
   */
  readonly status: 'not_assessed' | 'unresolved';
}

export interface PanelRecommendation {
  readonly domain: CriticalDomain;
  readonly seat_id: SeatId;
  readonly message: string;
}

/**
 * The quick-mode ratification gate, recorded verbatim at freeze
 * (Section 10). Prerequisites are pending until CWE-025 evaluates
 * them against the run's actual cards.
 */
export interface QuickModePolicyRecord {
  readonly seat_ids: readonly SeatId[];
  /** The exact status recorded when Round 3 is skipped. */
  readonly ratification_status_when_skipped: 'not_run_by_quick_mode_policy';
  readonly prerequisites: readonly {
    readonly id: string;
    readonly text: string;
    readonly status: 'pending_run';
  }[];
  readonly evaluated_by: 'CWE-025';
}

export function quickModePolicyRecord(seatIds: readonly SeatId[]): QuickModePolicyRecord {
  return {
    seat_ids: [...seatIds],
    ratification_status_when_skipped: 'not_run_by_quick_mode_policy',
    prerequisites: [
      {
        id: 'all_cards_valid',
        text: 'All four opening and challenge cards are valid.',
        status: 'pending_run',
      },
      {
        id: 'same_highest_ranked_option',
        text: 'All four seats have the same highest-ranked eligible option.',
        status: 'pending_run',
      },
      {
        id: 'spread_at_most_3',
        text: 'The Round 2 score spread on that option is at most 3.',
        status: 'pending_run',
      },
      {
        id: 'no_unresolved_critical_fact_or_constraint',
        text: 'No critical fact or constraint remains unresolved.',
        status: 'pending_run',
      },
      {
        id: 'no_unassessed_material_condition',
        text: 'The final plan introduces no material condition or amendment the seats have not assessed.',
        status: 'pending_run',
      },
    ],
    evaluated_by: 'CWE-025',
  };
}

export interface PanelAssessment {
  readonly mode: SessionMode;
  readonly seat_ids: readonly SeatId[];
  readonly required_responsibilities: readonly RequiredResponsibility[];
  readonly missing_critical_domains: readonly CriticalDomain[];
  readonly recommendations: readonly PanelRecommendation[];
  /**
   * True when a triggered critical domain stays not_assessed in a
   * scored mode, so a GO-style endorsement is blocked downstream
   * where that assessment is necessary (Section 12.7). Consults
   * explain limitations rather than manufacturing a panel score, so
   * this is always false for consult.
   */
  readonly blocks_go_style_endorsement: boolean;
  readonly quick_mode_policy: QuickModePolicyRecord | null;
}

/**
 * Compute the pre-start panel assessment. Pure: reads the draft's
 * mode, panel, triggered domains, and professional-review flag, and
 * changes nothing. Recommendations are offered; the panel is the
 * client's and stays exactly as chosen.
 */
export function assessPanel(args: {
  mode: SessionMode;
  seatIds: readonly SeatId[];
  requirements: readonly CriticalDomainRequirement[];
  professionalReviewArranged: boolean | null;
}): PanelAssessment {
  validatePanel(args.mode, args.seatIds);
  const responsibilities: RequiredResponsibility[] = [];
  const recommendations: PanelRecommendation[] = [];
  const missing: CriticalDomain[] = [];
  for (const requirement of args.requirements) {
    const reviewer = CRITICAL_DOMAIN_REVIEWERS[requirement.domain];
    let onPanel: boolean;
    if (reviewer.required_checker === 'qualified_professional') {
      onPanel = args.professionalReviewArranged === true;
    } else {
      onPanel =
        reviewer.required_seat_id !== null &&
        args.seatIds.includes(reviewer.required_seat_id);
    }
    if (!onPanel) missing.push(requirement.domain);
    responsibilities.push({
      domain: requirement.domain,
      required_seat_id: reviewer.required_seat_id,
      required_checker: reviewer.required_checker,
      reviewer_note: reviewer.reviewer_note,
      on_panel: onPanel,
      status: onPanel ? 'unresolved' : 'not_assessed',
    });
    if (!onPanel && reviewer.required_seat_id !== null) {
      recommendations.push({
        domain: requirement.domain,
        seat_id: reviewer.required_seat_id,
        message: `Consider including ${reviewer.required_seat_id}: the ${requirement.domain} assessment is required for this decision and stays not_assessed without that seat. The panel is unchanged unless you change it.`,
      });
    }
  }
  return {
    mode: args.mode,
    seat_ids: [...args.seatIds],
    required_responsibilities: responsibilities,
    missing_critical_domains: missing,
    recommendations,
    blocks_go_style_endorsement:
      args.mode !== 'consult' && missing.length > 0,
    quick_mode_policy:
      args.mode === 'quick' ? quickModePolicyRecord(args.seatIds) : null,
  };
}

/**
 * Recommend a quick panel by decision relevance (Section 10): seats
 * responsible for triggered critical domains first (financial exposure
 * always offers Tiffany Aliche; an offer or acquisition decision
 * always offers Russell Brunson), then the remaining roster in order.
 * A recommendation only: the client selects or accepts the panel.
 */
export function recommendQuickPanel(draft: IntakeDraft): SeatId[] {
  const chosen: SeatId[] = [];
  const flags = draft.answers.decision?.flags;
  const push = (seat: SeatId): void => {
    if (!chosen.includes(seat) && chosen.length < 4) chosen.push(seat);
  };
  if (flags?.involves_money_commitment) push('tiffany-aliche');
  if (flags?.involves_offer_or_pricing) push('russell-brunson');
  if (flags?.involves_rebrand_or_pivot) push('simon-sinek');
  if (flags?.involves_stakeholder_trust) push('brene-brown');
  if (flags?.decision_is_communication) push('td-jakes');
  for (const seat of SEAT_IDS) push(seat);
  return chosen;
}

