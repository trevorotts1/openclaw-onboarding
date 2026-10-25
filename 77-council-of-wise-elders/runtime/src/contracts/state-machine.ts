/**
 * Canonical session state machine (directive Sections 15.1 and 11.7).
 *
 * There are no unrestricted transitions by string assignment: every state
 * change goes through this table, carries an expected state_version
 * (optimistic concurrency), and names its actor. Mode paths differ: the
 * consult branch runs PREPARING -> CONSULTING -> VERIFYING -> COMPLETED and
 * never enters the round states; quick mode reaches ROUND_3 only when the
 * Section 10 skip predicate fails (the caller records which path was taken;
 * the table permits the DRAFT_RESOLUTION -> VERIFYING quick exit and the
 * DRAFT_RESOLUTION -> ROUND_3 full path).
 *
 * COMPLETED is immutable: no outgoing transitions. Archive is a separate
 * visibility flag on the record, never a state.
 */

import { ContractError } from './errors';
import {
  TERMINAL_STATES,
  type SessionMode,
  type SessionState,
} from './enums';

export type TransitionActor = 'owner' | 'system' | 'worker' | 'chair';

/** Forward processing transitions shared by scored modes, per mode. */
const MODE_PATHS: Record<SessionMode, Partial<Record<SessionState, SessionState[]>>> = {
  full: {
    DRAFT: ['READY'],
    READY: ['QUEUED'],
    QUEUED: ['PREPARING'],
    PREPARING: ['ROUND_1'],
    ROUND_1: ['CRUX_REVIEW'],
    CRUX_REVIEW: ['ROUND_2'],
    ROUND_2: ['DRAFT_RESOLUTION'],
    DRAFT_RESOLUTION: ['ROUND_3'],
    ROUND_3: ['VERIFYING'],
    VERIFYING: ['COMPLETED'],
  },
  selected: {
    DRAFT: ['READY'],
    READY: ['QUEUED'],
    QUEUED: ['PREPARING'],
    PREPARING: ['ROUND_1'],
    ROUND_1: ['CRUX_REVIEW'],
    CRUX_REVIEW: ['ROUND_2'],
    ROUND_2: ['DRAFT_RESOLUTION'],
    DRAFT_RESOLUTION: ['ROUND_3'],
    ROUND_3: ['VERIFYING'],
    VERIFYING: ['COMPLETED'],
  },
  quick: {
    DRAFT: ['READY'],
    READY: ['QUEUED'],
    QUEUED: ['PREPARING'],
    PREPARING: ['ROUND_1'],
    ROUND_1: ['CRUX_REVIEW'],
    CRUX_REVIEW: ['ROUND_2'],
    ROUND_2: ['DRAFT_RESOLUTION'],
    // Quick mode may skip Round 3 only under the Section 10 predicate;
    // both exits exist in the table, the engine records which was used.
    DRAFT_RESOLUTION: ['ROUND_3', 'VERIFYING'],
    ROUND_3: ['VERIFYING'],
    VERIFYING: ['COMPLETED'],
  },
  consult: {
    DRAFT: ['READY'],
    READY: ['QUEUED'],
    QUEUED: ['PREPARING'],
    PREPARING: ['CONSULTING'],
    CONSULTING: ['VERIFYING'],
    VERIFYING: ['COMPLETED'],
  },
  // Council sizes (W77S-MODES). No separate ratification pass: the verdict
  // is composed from the last completed round's advisor cards, so these
  // paths never enter ROUND_3. Each extra challenge pass re-enters
  // CRUX_REVIEW -> ROUND_2; the pass number lives in the job descriptor
  // round and the card's round, never in a new state value.
  light: {
    DRAFT: ['READY'],
    READY: ['QUEUED'],
    QUEUED: ['PREPARING'],
    PREPARING: ['ROUND_1'],
    ROUND_1: ['CRUX_REVIEW'],
    CRUX_REVIEW: ['ROUND_2'],
    ROUND_2: ['DRAFT_RESOLUTION'],
    DRAFT_RESOLUTION: ['VERIFYING'],
    VERIFYING: ['COMPLETED'],
  },
  medium: {
    DRAFT: ['READY'],
    READY: ['QUEUED'],
    QUEUED: ['PREPARING'],
    PREPARING: ['ROUND_1'],
    // A round-1 consensus stop may go straight to the resolution.
    ROUND_1: ['CRUX_REVIEW', 'DRAFT_RESOLUTION'],
    CRUX_REVIEW: ['ROUND_2'],
    // Re-entry: another challenge pass, or stop and compose the verdict.
    ROUND_2: ['CRUX_REVIEW', 'DRAFT_RESOLUTION'],
    DRAFT_RESOLUTION: ['VERIFYING'],
    VERIFYING: ['COMPLETED'],
  },
  heavy: {
    DRAFT: ['READY'],
    READY: ['QUEUED'],
    QUEUED: ['PREPARING'],
    PREPARING: ['ROUND_1'],
    ROUND_1: ['CRUX_REVIEW', 'DRAFT_RESOLUTION'],
    CRUX_REVIEW: ['ROUND_2'],
    ROUND_2: ['CRUX_REVIEW', 'DRAFT_RESOLUTION'],
    DRAFT_RESOLUTION: ['VERIFYING'],
    VERIFYING: ['COMPLETED'],
  },
};

/** States from which work is actively executing or awaiting execution. */
const ACTIVE_STATES: ReadonlySet<SessionState> = new Set([
  'READY',
  'QUEUED',
  'PREPARING',
  'ROUND_1',
  'CRUX_REVIEW',
  'ROUND_2',
  'DRAFT_RESOLUTION',
  'ROUND_3',
  'CONSULTING',
  'VERIFYING',
  'RESUMING',
]);

export function allowedTransitions(
  mode: SessionMode,
  from: SessionState,
): SessionState[] {
  const out = new Set<SessionState>(MODE_PATHS[mode][from] ?? []);
  if (ACTIVE_STATES.has(from)) {
    out.add('PAUSE_REQUESTED');
    out.add('CANCEL_REQUESTED');
    out.add('BLOCKED');
    out.add('FAILED');
  }
  if (from === 'PAUSE_REQUESTED') out.add('PAUSED');
  if (from === 'PAUSED') out.add('RESUMING');
  if (from === 'CANCEL_REQUESTED') out.add('CANCELLED');
  if (from === 'BLOCKED') out.add('RESUMING');
  // RESUMING returns to the recorded resume_phase; the exact target is
  // validated in assertTransition because it depends on the record.
  return [...out];
}

export function canTransition(
  mode: SessionMode,
  from: SessionState,
  to: SessionState,
  resumePhase: SessionState | null = null,
): boolean {
  if (TERMINAL_STATES.has(from)) return false;
  if (from === to) return false;
  if (from === 'RESUMING') {
    // Resume only to the checkpointed phase, which must itself be an
    // active processing state on this mode's path.
    return (
      resumePhase !== null &&
      to === resumePhase &&
      ACTIVE_STATES.has(to) &&
      to !== 'RESUMING'
    );
  }
  return allowedTransitions(mode, from).includes(to);
}

export interface TransitionRequest {
  mode: SessionMode;
  from: SessionState;
  to: SessionState;
  /** The record's current state_version; the transition consumes exactly it. */
  expectedVersion: number;
  currentVersion: number;
  actor: TransitionActor;
  resumePhase?: SessionState | null;
  /** Required when entering CANCEL_REQUESTED: bumps cancel_generation. */
  cancelGeneration?: number;
  currentCancelGeneration?: number;
}

/**
 * Validate a transition and return the next state_version. Throws a typed
 * ContractError (ILLEGAL_TRANSITION or VERSION_MISMATCH) on any violation.
 */
export function assertTransition(req: TransitionRequest): { stateVersion: number } {
  if (req.expectedVersion !== req.currentVersion) {
    throw new ContractError(
      'VERSION_MISMATCH',
      `State version mismatch: expected ${req.expectedVersion}, record is at ${req.currentVersion}`,
      'state_version',
    );
  }
  if (
    req.to === 'CANCEL_REQUESTED' &&
    (req.cancelGeneration === undefined ||
      req.currentCancelGeneration === undefined ||
      req.cancelGeneration !== req.currentCancelGeneration + 1)
  ) {
    throw new ContractError(
      'ILLEGAL_TRANSITION',
      'Entering CANCEL_REQUESTED requires cancel_generation to increase by exactly one',
      'cancel_generation',
    );
  }
  if (!canTransition(req.mode, req.from, req.to, req.resumePhase ?? null)) {
    throw new ContractError(
      'ILLEGAL_TRANSITION',
      `Illegal ${req.mode} transition ${req.from} -> ${req.to}`,
      'state',
    );
  }
  return { stateVersion: req.currentVersion + 1 };
}
