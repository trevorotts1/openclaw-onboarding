/**
 * Deliberation engine (CWE-004 foundation).
 *
 * Runs a council session end to end against the injected host ports and
 * the CWE-003 canonical contracts: frozen brief in, validated cards,
 * deterministic crux extraction, a code-composed draft resolution,
 * ratification, deterministic scoring (contracts scoring module; the
 * chair's prose never changes arithmetic, Section 14.4), and a
 * validated verdict out.
 *
 * Scope honesty: the production round protocol depth is CWE-024
 * (openings) and CWE-025 (challenge, draft resolution, ratification),
 * verdict validation depth is CWE-026, and the durable worker lifecycle
 * that carries this engine across processes is CWE-027. This foundation
 * engine executes the same state machine and contracts in-process for
 * the standalone adapter and for isolated tests, with the same budget,
 * lease, cancellation, and idempotency rules, so those units compose a
 * proven core instead of a sketch.
 *
 * Hard rules held here:
 * - No provider request is admitted without a resolved run grant
 *   (CWE-049's service issues grants; without one, start refuses with
 *   RUN_AUTHORIZATION_REQUIRED and nothing is dispatched).
 * - Every request is reserved in the budget ledger before dispatch and
 *   counted toward the 50-request session ceiling whatever its kind.
 * - A card is committed only while its operation lease is current and
 *   the session's cancellation generation has not moved; late results
 *   are fenced out, never published.
 * - Completed operations are never redone: a stored card for the same
 *   logical operation (session, round, seat, input hash) is reused on
 *   resume instead of spending again (Section 15.3).
 * - Raw provider bodies are memory-only (Section 16.6): only validated
 *   cards, safe receipts, and hashes are persisted.
 * - A missing seat is a visible BLOCKED partial result, never a
 *   silently completed smaller council (Section 10).
 */

import {
  canonicalHash,
  computeOptionScore,
  labelForScore,
  validateCard,
  validateCardAgainstBrief,
  validateCardAuthor,
  validateDecisionBrief,
  validateSessionSpec,
  validateVerdict,
  assertTransition,
  SEAT_ROSTER,
  type AdvisorCard,
  type CardAuthor,
  type ConsultCard,
  type CouncilCard,
  type CouncilEvent,
  type CouncilSettings,
  type DecisionBrief,
  type DraftResolution,
  type RatificationCard,
  type RatificationStatus,
  type ResolutionSupport,
  type RunGrant,
  type ScopeFields,
  type SeatId,
  type SessionSpec,
  type SessionState,
  type SessionStateRecord,
  type Verdict,
  type VerdictLabel,
} from '../contracts/index.js';
import { DEFAULT_COUNCIL_SETTINGS } from '../contracts/index.js';
import { deriveHardConstraintFindings } from '../scoring/decision.js';
import { CouncilError, invalidInput } from './errors.js';
import type {
  BudgetReservation,
  CouncilHost,
  OperationLease,
  StoredSession,
  TransportRequest,
} from './host-ports.js';

/** Section 7 owned questions, used as seat focus in prompt assembly. */
export const SEAT_FOCUS: Record<SeatId, string> = {
  'simon-sinek':
    'Does this decision express why the business exists, and are the proposed actions consistent with that purpose?',
  'td-jakes':
    'What opportunity or capacity is the client sensing, what established assumption needs challenging, and how can the vision be communicated effectively?',
  'oprah-winfrey':
    'What is the real intention behind this choice, and how does it affect the people it is supposed to serve?',
  'tiffany-aliche':
    'Can the client make this commitment without destabilizing the foundation that supports their life and business?',
  'russell-brunson':
    'Who wants this, how will they find it, and what credible path turns interest into a purchase?',
  'michelle-obama':
    'How can the client move forward with confidence and integrity while considering the people affected?',
  'brene-brown':
    'What difficult conversation or vulnerable action is being avoided, and what would trustworthy leadership require?',
  'dennis-kimbro':
    'Does the decision build enduring capability, ownership, and wealth, or merely create more activity?',
  'les-brown':
    'Is the obstacle a real constraint, a skill gap, or a limiting belief, and what meaningful action comes next?',
};

/**
 * The Section 14.2 opening-round system text. CWE-050 consolidation:
 * this is the SINGLE source for the round system texts; the protocol
 * executors (opening, challenge, ratification, consult) import these
 * constants instead of carrying their own copies.
 */
export const OPENING_SYSTEM = [
  'You are an AI advisory perspective inspired by the approved published-work pack.',
  'You are not the individual. Apply the seat\'s specific responsibility.',
  'Use only supplied facts and authorized evidence. Label assumptions and unknowns.',
  'Evaluate every listed option and generate justified evaluative scores.',
  'Do not fabricate external facts, quotations, measured results, or source IDs.',
  'Do not assume any other seat agrees. Do not execute actions.',
  'Return one AdvisorCard matching the supplied schema, with concrete application,',
  'strongest objection, necessary conditions, and what would change your position.',
].join('\n');

export const CHALLENGE_SYSTEM = [
  'You are an AI advisory perspective inspired by the approved published-work pack.',
  'You are not the individual. This is the focused challenge round.',
  'Answer the cruxes assigned to your seat using the supplied evidence.',
  'Return a Round 2 AdvisorCard: confirm or update your position, and explain',
  'every changed score. A changed score without an explanation is invalid.',
  'Do not fabricate facts, quotations, or source IDs. Do not execute actions.',
].join('\n');

export const RATIFICATION_SYSTEM = [
  'You are an AI advisory perspective inspired by the approved published-work pack.',
  'You are not the individual. This is the ratification round.',
  'Judge the exact draft resolution identified by its semantic hash.',
  'Return one RatificationCard: support, conditional support, opposition, or',
  'abstention for that resolution, final option scores, amendments, and any',
  'unresolved objections. Support never transfers to a changed resolution.',
].join('\n');

export const CONSULT_SYSTEM = [
  'You are an AI advisory perspective inspired by the approved published-work pack.',
  'You are not the individual. This is a one-seat consult, not a council vote.',
  'Answer the question from your seat\'s responsibility using supplied evidence.',
  'Return one ConsultCard. Do not invent options, scores, or consensus.',
].join('\n');

interface SeatFailure {
  seat_id: SeatId;
  round: number;
  message: string;
}

interface Crux {
  crux_id: string;
  type: 'fact' | 'numbers' | 'values' | 'execution';
  option_id: string;
  competing_claims: string[];
  responsible_seats: SeatId[];
  needed_evidence: string;
  resolution_test: string;
}

export class CouncilEngine {
  private readonly host: CouncilHost;
  private readonly settings: CouncilSettings;
  private readonly ownerId: string;

  constructor(
    host: CouncilHost,
    options: { settings?: CouncilSettings; ownerId?: string } = {},
  ) {
    this.host = host;
    this.settings = options.settings ?? DEFAULT_COUNCIL_SETTINGS;
    this.ownerId = options.ownerId ?? 'local-engine';
  }

  // -------------------------------------------------------------- sessions

  async createSession(input: {
    spec: SessionSpec;
    brief: DecisionBrief;
    scope: ScopeFields;
    sample?: boolean;
  }): Promise<StoredSession> {
    const specResult = validateSessionSpec(input.spec);
    if (!specResult.ok) {
      throw invalidInput(
        `Session spec failed validation: ${specResult.issues.map((i) => `${i.path}: ${i.message}`).join('; ')}`,
      );
    }
    const briefResult = validateDecisionBrief(input.brief);
    if (!briefResult.ok) {
      throw invalidInput(
        `Decision brief failed validation: ${briefResult.issues.map((i) => `${i.path}: ${i.message}`).join('; ')}`,
      );
    }
    const spec = specResult.value;
    const brief = briefResult.value;
    if (spec.session_id !== brief.session_id) {
      throw invalidInput('Session spec and brief disagree on session_id.');
    }
    if (spec.brief_revision !== brief.revision) {
      throw invalidInput('Session spec brief_revision does not match the brief revision.');
    }
    if (canonicalHash(brief) !== spec.brief_sha256) {
      throw invalidInput(
        'spec.brief_sha256 does not match the canonical hash of the supplied brief.',
      );
    }
    for (const seatId of spec.seat_ids) {
      const weight = brief.relevance_weights[seatId];
      if (weight === undefined) {
        throw invalidInput(
          `Brief is missing a frozen relevance weight for seat ${seatId} (Section 12.1).`,
        );
      }
    }
    if (await this.host.store.getSession(spec.session_id)) {
      throw new CouncilError(
        'COUNCIL_STATE_CONFLICT',
        `Session ${spec.session_id} already exists.`,
        { retryable: false, exitCode: 3 },
      );
    }
    const state: SessionStateRecord = {
      schema_version: 'wise-elders.session-state/v1',
      session_id: spec.session_id,
      mode: spec.mode,
      state: 'DRAFT',
      state_version: 0,
      brief_revision: brief.revision,
      resume_phase: null,
      cancel_generation: 0,
      revocation_generation: 0,
      attempt: 1,
      lease_epoch: 0,
      archived: false,
      updated_at: this.host.clock.nowUtc(),
    };
    const stored: StoredSession = {
      spec,
      brief,
      scope: input.scope,
      state,
      sample: input.sample ?? false,
    };
    await this.host.store.createSession(stored);
    await this.emit(stored, 'session_created', 'owner', {
      mode: spec.mode,
      sample: stored.sample,
    });
    return stored;
  }

  async getSession(sessionId: string): Promise<StoredSession> {
    const session = await this.host.store.getSession(sessionId);
    if (!session) {
      throw new CouncilError(
        'COUNCIL_SESSION_NOT_FOUND',
        `No council session exists with ID ${sessionId}.`,
        { retryable: false, action: 'Check the session ID and try again.', exitCode: 3 },
      );
    }
    return session;
  }

  async listEvents(sessionId: string, afterSequence = 0): Promise<CouncilEvent[]> {
    await this.getSession(sessionId);
    return this.host.store.listEvents(sessionId, afterSequence);
  }

  /** Replay is a read of committed events only; it spends nothing. */
  async replaySession(sessionId: string): Promise<CouncilEvent[]> {
    return this.listEvents(sessionId, 0);
  }

  async getVerdict(sessionId: string): Promise<Verdict | null> {
    await this.getSession(sessionId);
    return this.host.store.getVerdict(sessionId);
  }

  // -------------------------------------------------------------- lifecycle

  async startSession(sessionId: string, grantRef: string): Promise<StoredSession> {
    let session = await this.getSession(sessionId);
    if (session.state.state !== 'DRAFT') {
      throw new CouncilError(
        'COUNCIL_STATE_CONFLICT',
        `Session ${sessionId} is ${session.state.state}, not DRAFT. Use resume for paused or blocked work.`,
        { retryable: false, exitCode: 3 },
      );
    }
    await this.admit(session, grantRef);
    session = await this.transition(session, 'READY', 'owner');
    session = await this.transition(session, 'QUEUED', 'system');
    session = await this.transition(session, 'PREPARING', 'system');
    return this.runPipeline(session);
  }

  async resumeSession(sessionId: string, grantRef: string): Promise<StoredSession> {
    let session = await this.getSession(sessionId);
    const from = session.state.state;
    if (from !== 'PAUSED' && from !== 'BLOCKED') {
      throw new CouncilError(
        'COUNCIL_STATE_CONFLICT',
        `Session ${sessionId} is ${from}; only PAUSED or BLOCKED sessions resume.`,
        { retryable: false, exitCode: 3 },
      );
    }
    await this.admit(session, grantRef);
    const resumePhase = session.state.resume_phase ?? 'PREPARING';
    session = await this.transition(session, 'RESUMING', 'owner');
    session = await this.transition(session, resumePhase, 'system', { resumePhase });
    return this.runPipeline(session);
  }

  async pauseSession(sessionId: string): Promise<StoredSession> {
    const session = await this.getSession(sessionId);
    const current = session.state.state;
    let next = await this.transition(session, 'PAUSE_REQUESTED', 'owner');
    next = await this.transition(
      next,
      'PAUSED',
      'system',
      {},
      { resumePhase: current },
    );
    await this.emit(next, 'session_paused', 'owner', { resume_phase: current });
    return next;
  }

  async cancelSession(sessionId: string): Promise<StoredSession> {
    let session = await this.getSession(sessionId);
    session = await this.transition(session, 'CANCEL_REQUESTED', 'owner');
    session = await this.transition(session, 'CANCELLED', 'system');
    await this.emit(session, 'session_cancelled', 'owner', {
      cancel_generation: session.state.cancel_generation,
    });
    return session;
  }

  // -------------------------------------------------------------- admission

  private async admit(session: StoredSession, grantRef: string): Promise<RunGrant> {
    const grant = await this.host.authorize.resolveRunGrant(
      grantRef,
      session.spec.session_id,
    );
    if (!grant) {
      throw new CouncilError(
        'RUN_AUTHORIZATION_REQUIRED',
        'No valid run authorization was found for this session. A council run spends the client\'s inference allowance, so it cannot start without a real grant (Section 25.6).',
        {
          retryable: false,
          action:
            'Create a run preview and approve it through the run-authorization service (CWE-049), then start with that grant reference.',
          exitCode: 3,
        },
      );
    }
    const problems: string[] = [];
    if (grant.session_id !== session.spec.session_id) problems.push('grant is for a different session');
    if (grant.brief_sha256 !== session.spec.brief_sha256) problems.push('grant brief hash does not match the frozen brief');
    if (grant.mode !== session.spec.mode) problems.push('grant mode does not match the session mode');
    if (grant.purpose !== 'council_run') problems.push('grant purpose is not council_run');
    if (grant.status !== 'active') problems.push(`grant status is ${grant.status}`);
    if (
      grant.scope.tenant_id !== session.scope.tenant_id ||
      grant.scope.company_id !== session.scope.company_id ||
      grant.scope.installation_id !== session.scope.installation_id
    ) {
      problems.push('grant scope does not match the session scope');
    }
    if (Date.parse(grant.expires_at) <= Date.parse(this.host.clock.nowUtc())) {
      problems.push('grant has expired');
    }
    for (const seatId of session.spec.seat_ids) {
      if (!grant.seat_ids.includes(seatId)) problems.push(`grant does not cover seat ${seatId}`);
    }
    if (problems.length > 0) {
      throw new CouncilError(
        'RUN_AUTHORIZATION_REQUIRED',
        `The supplied run grant cannot admit this session: ${problems.join('; ')}.`,
        {
          retryable: false,
          action: 'Approve a preview that matches this exact session, brief, mode, and seats.',
          exitCode: 3,
        },
      );
    }
    // Transport preflight: fail before any state change if the selected
    // route has no adapter composed in this host (Sections 13.6, 17.3).
    if (!this.host.transportRegistry.resolve(session.spec.model_policy.route_id)) {
      throw new CouncilError(
        'COUNCIL_ROUTE_UNAVAILABLE',
        `No transport is registered for route ${session.spec.model_policy.route_id}. The selected route is never silently replaced.`,
        {
          retryable: false,
          action:
            'Compose a transport for the selected route (CWE-009/CWE-010), or start a reviewed rerun with another route.',
          exitCode: 3,
        },
      );
    }
    return grant;
  }

  // -------------------------------------------------------------- state

  private async emit(
    session: StoredSession,
    eventType: CouncilEvent['event_type'],
    actor: CouncilEvent['actor'],
    payload: Record<string, unknown>,
  ): Promise<void> {
    await this.host.events.publish({
      schema_version: 'wise-elders.event/v1',
      event_id: this.host.ids.newId(),
      session_id: session.spec.session_id,
      event_type: eventType,
      tenant_id: session.scope.tenant_id,
      company_id: session.scope.company_id,
      owner_subject: session.scope.owner_subject,
      actor,
      payload: session.sample ? { ...payload, sample: true } : payload,
      created_at: this.host.clock.nowUtc(),
    });
  }

  private async transition(
    session: StoredSession,
    to: SessionState,
    actor: 'owner' | 'system' | 'worker' | 'chair',
    opts: { resumePhase?: SessionState | null } = {},
    recordOverrides: { resumePhase?: SessionState | null } = {},
  ): Promise<StoredSession> {
    const fresh = (await this.host.store.getSession(session.spec.session_id)) ?? session;
    const current = fresh.state;
    const isCancel = to === 'CANCEL_REQUESTED';
    const { stateVersion } = assertTransition({
      mode: fresh.spec.mode,
      from: current.state,
      to,
      expectedVersion: current.state_version,
      currentVersion: current.state_version,
      actor,
      resumePhase: opts.resumePhase ?? current.resume_phase,
      cancelGeneration: isCancel ? current.cancel_generation + 1 : undefined,
      currentCancelGeneration: isCancel ? current.cancel_generation : undefined,
    });
    const next: SessionStateRecord = {
      ...current,
      state: to,
      state_version: stateVersion,
      cancel_generation: isCancel
        ? current.cancel_generation + 1
        : current.cancel_generation,
      resume_phase:
        recordOverrides.resumePhase !== undefined
          ? recordOverrides.resumePhase
          : to === 'RESUMING' || TERMINAL_LIKE.has(to)
            ? current.resume_phase
            : current.resume_phase,
      updated_at: this.host.clock.nowUtc(),
    };
    await this.host.store.updateState(next, current.state_version);
    const updated = { ...fresh, state: next };
    await this.emit(updated, 'session_state_changed', actor, {
      from: current.state,
      to,
    });
    return updated;
  }

  private async block(
    session: StoredSession,
    resumePhase: SessionState,
    reason: string,
  ): Promise<StoredSession> {
    const next = await this.transition(session, 'BLOCKED', 'system', {}, { resumePhase });
    await this.emit(next, 'session_blocked', 'system', { reason, resume_phase: resumePhase });
    return next;
  }

  /** True when an external control (pause/cancel) should stop dispatch. */
  private async controlStop(sessionId: string): Promise<'paused' | 'cancelled' | null> {
    const fresh = await this.host.store.getSession(sessionId);
    if (!fresh) return 'cancelled';
    const state = fresh.state.state;
    if (state === 'PAUSED' || state === 'PAUSE_REQUESTED') return 'paused';
    if (state === 'CANCELLED' || state === 'CANCEL_REQUESTED') return 'cancelled';
    return null;
  }

  // -------------------------------------------------------------- pipeline

  private async runPipeline(sessionIn: StoredSession): Promise<StoredSession> {
    let session = sessionIn;
    for (;;) {
      const state = session.state.state;
      if (state === 'COMPLETED' || state === 'CANCELLED' || state === 'FAILED') {
        return session;
      }
      if (state === 'PAUSED' || state === 'BLOCKED') return session;
      switch (state) {
        case 'PREPARING':
          session = await this.transition(
            session,
            session.spec.mode === 'consult' ? 'CONSULTING' : 'ROUND_1',
            'system',
          );
          break;
        case 'CONSULTING': {
          const failure = await this.runConsult(session);
          if (failure) return this.block(session, 'CONSULTING', failure.message);
          session = await this.transition(session, 'VERIFYING', 'system');
          break;
        }
        case 'ROUND_1': {
          const failures = await this.runAdvisorRound(session, 1);
          if (failures.length > 0) {
            return this.block(
              session,
              'ROUND_1',
              `Round 1 incomplete: ${failures.map((f) => `${f.seat_id}: ${f.message}`).join('; ')}`,
            );
          }
          session = await this.transition(session, 'CRUX_REVIEW', 'chair');
          break;
        }
        case 'CRUX_REVIEW': {
          const cruxes = await this.computeCruxes(session);
          for (const crux of cruxes) {
            await this.emit(session, 'crux_identified', 'chair', { ...crux });
          }
          session = await this.transition(session, 'ROUND_2', 'system');
          break;
        }
        case 'ROUND_2': {
          const failures = await this.runAdvisorRound(session, 2);
          if (failures.length > 0) {
            return this.block(
              session,
              'ROUND_2',
              `Round 2 incomplete: ${failures.map((f) => `${f.seat_id}: ${f.message}`).join('; ')}`,
            );
          }
          session = await this.transition(session, 'DRAFT_RESOLUTION', 'chair');
          break;
        }
        case 'DRAFT_RESOLUTION': {
          const draft = await this.composeDraft(session);
          await this.emit(session, 'resolution_drafted', 'chair', {
            recommended_option_id: draft.recommended_option_id,
            semantic_sha256: draft.semantic_sha256,
          });
          if (session.spec.mode === 'quick' && (await this.quickSkipApplies(session, draft))) {
            session = await this.transition(session, 'VERIFYING', 'system');
          } else {
            session = await this.transition(session, 'ROUND_3', 'system');
          }
          break;
        }
        case 'ROUND_3': {
          const failures = await this.runRatification(session);
          if (failures.length > 0) {
            return this.block(
              session,
              'ROUND_3',
              `Ratification incomplete: ${failures.map((f) => `${f.seat_id}: ${f.message}`).join('; ')}`,
            );
          }
          session = await this.transition(session, 'VERIFYING', 'system');
          break;
        }
        case 'VERIFYING': {
          const verdict = await this.buildVerdict(session);
          await this.host.store.saveVerdict(verdict);
          await this.emit(session, 'verdict_validated', 'system', {
            verdict_revision: verdict.verdict_revision,
            result_kind: verdict.result_kind,
          });
          session = await this.transition(session, 'COMPLETED', 'system');
          return session;
        }
        default:
          return session;
      }
      const stop = await this.controlStop(session.spec.session_id);
      if (stop) {
        const fresh = await this.getSession(session.spec.session_id);
        return fresh;
      }
    }
  }

  // -------------------------------------------------------------- operations

  private operationKey(session: StoredSession, phase: string, seatId: SeatId, inputSha: string): string {
    const s = session.scope;
    return [
      'op',
      s.installation_id,
      s.tenant_id,
      session.spec.session_id,
      `a${session.state.attempt}`,
      phase,
      seatId,
      inputSha.slice(0, 16),
    ].join(':');
  }

  private inputManifestSha(
    session: StoredSession,
    purpose: string,
    seatId: SeatId,
    round: number | null,
    packVersion: string,
  ): string {
    return canonicalHash({
      session_id: session.spec.session_id,
      brief_sha256: session.spec.brief_sha256,
      purpose,
      seat_id: seatId,
      round,
      pack_version: packVersion,
      evidence_ids: session.brief.evidence_manifest.map((e) => e.evidence_id),
    });
  }

  /**
   * Execute one provider operation with reservation, lease, fencing,
   * bounded repair, and idempotent reuse. Returns the validated author
   * payload, or throws a SeatFailure-shaped CouncilError.
   */
  private async runOperation(
    session: StoredSession,
    purpose: 'advisor' | 'ratification' | 'consult',
    round: 1 | 2 | 3 | null,
    seatId: SeatId,
    extraInput: Record<string, unknown>,
    validateExtra?: (author: CardAuthor) => string | null,
  ): Promise<CardAuthor> {
    const pack = await this.host.evidence.loadSeatPack(seatId);
    const packVersion = pack?.pack_version ?? session.spec.source_pack_version;
    const inputSha = this.inputManifestSha(session, purpose, seatId, round, packVersion);
    const roundKey = purpose === 'consult' ? 0 : (round ?? 0);
    const existing = await this.host.store.findCard(
      session.spec.session_id,
      roundKey,
      seatId,
      inputSha,
    );
    if (existing) {
      const { host: _hostStamp, ...author } = existing as unknown as Record<
        string,
        unknown
      >;
      return author as unknown as CardAuthor;
    }
    const transport = this.host.transportRegistry.resolve(
      session.spec.model_policy.route_id,
    );
    if (!transport) {
      throw new CouncilError(
        'COUNCIL_ROUTE_UNAVAILABLE',
        `No transport is registered for route ${session.spec.model_policy.route_id}.`,
        { retryable: false, exitCode: 3 },
      );
    }
    const phase =
      purpose === 'consult' ? 'consult' : purpose === 'ratification' ? 'round-3' : `round-${round}`;
    const opKey = this.operationKey(session, phase, seatId, inputSha);
    const lease: OperationLease = this.host.capacity.claim(opKey, this.ownerId);
    await this.host.store.saveCheckpoint({
      schema_version: 'wise-elders.job-checkpoint/v1',
      installation_id: session.scope.installation_id,
      tenant_id: session.scope.tenant_id,
      session_id: session.spec.session_id,
      attempt: session.state.attempt,
      brief_revision: session.brief.revision,
      phase,
      seat_id: seatId,
      input_sha256: inputSha,
      pack_version: packVersion,
      model_policy_revision: 0,
      status: 'reserved',
      provider_request_id: null,
      usage: { input_tokens: null, output_tokens: null, provider_requests: 0 },
      committed_at: null,
    });

    const system =
      purpose === 'consult'
        ? CONSULT_SYSTEM
        : purpose === 'ratification'
          ? RATIFICATION_SYSTEM
          : round === 2
            ? CHALLENGE_SYSTEM
            : OPENING_SYSTEM;
    const requestInput: Record<string, unknown> = {
      brief: session.brief,
      seat_focus: SEAT_FOCUS[seatId],
      seat_display_name:
        SEAT_ROSTER.find((s) => s.seat_id === seatId)?.display_name ?? seatId,
      pack_briefing: pack?.briefing_text ?? null,
      input_manifest_sha256: inputSha,
      pack_version: packVersion,
      ...extraInput,
    };

    let reservation: BudgetReservation | null = null;
    try {
      reservation = this.host.budget.reserve({
        session_id: session.spec.session_id,
        operation_key: opKey,
        kind: 'provider_request',
      });
      let attempt = 0;
      let repairs = 0;
      let lastIssues: string[] = [];
      for (;;) {
        attempt += 1;
        const request: TransportRequest = {
          purpose,
          session_id: session.spec.session_id,
          seat_id: seatId,
          round: round as 1 | 2 | 3 | null,
          route_id: session.spec.model_policy.route_id,
          model_policy: session.spec.model_policy,
          system:
            repairs > 0
              ? `${system}\nYour previous output failed validation: ${lastIssues.join('; ')}. Return a corrected card only.`
              : system,
          input: requestInput,
        };
        let response;
        try {
          response = await transport.generate(request);
        } catch (err) {
          const e = err as { retryable?: boolean; unknownCompletion?: boolean; message?: string };
          if (e.unknownCompletion) {
            this.host.budget.markProviderCompletionUnknown(reservation);
            reservation = null;
            await this.saveCheckpointStatus(session, phase, seatId, inputSha, packVersion, 'provider_completion_unknown', null);
            throw new CouncilError(
              'COUNCIL_TRANSPORT_FAILED',
              `Provider completion is unknown for seat ${seatId} (${phase}). The reservation is retained and the request is not replayed automatically.`,
              { retryable: false, exitCode: 3 },
            );
          }
          if (
            e.retryable &&
            attempt <= this.settings.max_transport_retries_per_request
          ) {
            const retryReservation = this.host.budget.reserve({
              session_id: session.spec.session_id,
              operation_key: `${opKey}:retry:${attempt}`,
              kind: 'transport_retry',
            });
            this.host.budget.commit(retryReservation);
            continue;
          }
          this.host.budget.commit(reservation);
          reservation = null;
          await this.saveCheckpointStatus(session, phase, seatId, inputSha, packVersion, 'failed', null);
          throw new CouncilError(
            'COUNCIL_TRANSPORT_FAILED',
            `Transport failed for seat ${seatId} (${phase}): ${e.message ?? 'unknown error'}`,
            { retryable: false, exitCode: 3 },
          );
        }
        // Parse and validate the author payload.
        let author: CardAuthor | null = null;
        let issues: string[] = [];
        try {
          const parsed: unknown = JSON.parse(response.text);
          const shape = validateCardAuthor(parsed);
          if (!shape.ok) {
            issues = shape.issues.map((i) => `${i.path}: ${i.message}`);
          } else {
            const against = validateCardAgainstBrief(shape.value, session.brief);
            if (!against.ok) {
              issues = against.issues.map((i) => `${i.path}: ${i.message}`);
            } else if (shape.value.seat_id !== seatId) {
              issues = [`seat_id: card claims seat ${shape.value.seat_id}, expected ${seatId}`];
            } else if (shape.value.input_manifest_sha256 !== inputSha) {
              issues = ['input_manifest_sha256: card does not match the frozen input manifest'];
            } else {
              const extraIssue = validateExtra?.(shape.value) ?? null;
              if (extraIssue) {
                issues = [extraIssue];
              } else {
                author = shape.value;
              }
            }
          }
        } catch {
          issues = ['response is not valid JSON'];
        }
        if (author) {
          // Fence check before commit: lease current, no cancellation.
          this.host.capacity.assertCurrent(lease);
          const fresh = await this.host.store.getSession(session.spec.session_id);
          if (
            !fresh ||
            fresh.state.cancel_generation !== session.state.cancel_generation ||
            fresh.state.state === 'CANCEL_REQUESTED' ||
            fresh.state.state === 'CANCELLED'
          ) {
            this.host.budget.commit(reservation);
            reservation = null;
            await this.saveCheckpointStatus(session, phase, seatId, inputSha, packVersion, 'cancelled', response.provider_request_id);
            throw new CouncilError(
              'COUNCIL_STATE_CONFLICT',
              `Session was cancelled while seat ${seatId} (${phase}) was in flight; the late result was fenced out.`,
              { retryable: false, exitCode: 3 },
            );
          }
          const stamped: CouncilCard = {
            ...author,
            host: {
              scope: session.scope,
              operation_id: opKey,
              route_id: session.spec.model_policy.route_id,
              session_id: session.spec.session_id,
              stamped_at: this.host.clock.nowUtc(),
              source_status: 'not_applicable',
            },
          } as CouncilCard;
          const full = validateCard(stamped);
          if (!full.ok) {
            issues = full.issues.map((i) => `${i.path}: ${i.message}`);
          } else {
            await this.host.store.saveCard(full.value);
            await this.saveCheckpointStatus(session, phase, seatId, inputSha, packVersion, 'accepted', response.provider_request_id);
            await this.emit(session, 'card_accepted', 'worker', {
              seat_id: seatId,
              round: roundKey,
              operation_id: opKey,
            });
            await this.emit(session, 'operation_completed', 'worker', {
              operation_id: opKey,
              provider_request_id: response.provider_request_id,
            });
            this.host.budget.commit(reservation);
            reservation = null;
            return author;
          }
        }
        // Invalid output: at most one same-route repair per operation.
        lastIssues = issues;
        if (repairs >= this.settings.max_output_repairs_per_original_operation) {
          this.host.budget.commit(reservation);
          reservation = null;
          await this.saveCheckpointStatus(session, phase, seatId, inputSha, packVersion, 'failed', null);
          throw new CouncilError(
            'COUNCIL_CARD_INVALID',
            `Seat ${seatId} (${phase}) returned an invalid card after the permitted repair: ${issues.join('; ')}`,
            { retryable: false, exitCode: 3 },
          );
        }
        repairs += 1;
        const repairReservation = this.host.budget.reserve({
          session_id: session.spec.session_id,
          operation_key: `${opKey}:repair:${repairs}`,
          kind: 'output_repair',
        });
        this.host.budget.commit(repairReservation);
      }
    } finally {
      if (reservation) this.host.budget.release(reservation);
      this.host.capacity.release(lease);
    }
  }

  private async saveCheckpointStatus(
    session: StoredSession,
    phase: string,
    seatId: SeatId,
    inputSha: string,
    packVersion: string,
    status: 'accepted' | 'failed' | 'cancelled' | 'provider_completion_unknown',
    providerRequestId: string | null,
  ): Promise<void> {
    await this.host.store.saveCheckpoint({
      schema_version: 'wise-elders.job-checkpoint/v1',
      installation_id: session.scope.installation_id,
      tenant_id: session.scope.tenant_id,
      session_id: session.spec.session_id,
      attempt: session.state.attempt,
      brief_revision: session.brief.revision,
      phase,
      seat_id: seatId,
      input_sha256: inputSha,
      pack_version: packVersion,
      model_policy_revision: 0,
      status,
      provider_request_id: providerRequestId,
      usage: { input_tokens: null, output_tokens: null, provider_requests: 1 },
      committed_at: status === 'accepted' ? this.host.clock.nowUtc() : null,
    });
  }

  // -------------------------------------------------------------- rounds

  private async runAdvisorRound(
    session: StoredSession,
    round: 1 | 2,
  ): Promise<SeatFailure[]> {
    const cruxes = round === 2 ? await this.computeCruxes(session) : [];
    const failures: SeatFailure[] = [];
    for (const seatId of session.spec.seat_ids) {
      const stop = await this.controlStop(session.spec.session_id);
      if (stop) break;
      const assigned = cruxes
        .filter((c) => c.responsible_seats.includes(seatId))
        .map((c) => ({
          crux_id: c.crux_id,
          question: `Resolve with evidence: ${c.resolution_test}`,
        }));
      try {
        await this.runOperation(session, 'advisor', round, seatId, {
          ...(round === 2
            ? { crux_summary: cruxes, challenges_for_seat: assigned }
            : {}),
        });
      } catch (err) {
        failures.push({
          seat_id: seatId,
          round,
          message: err instanceof Error ? err.message : String(err),
        });
      }
    }
    return failures;
  }

  private async runConsult(session: StoredSession): Promise<SeatFailure | null> {
    const seatId = session.spec.seat_ids[0];
    try {
      await this.runOperation(session, 'consult', null, seatId, {});
      return null;
    } catch (err) {
      return {
        seat_id: seatId,
        round: 0,
        message: err instanceof Error ? err.message : String(err),
      };
    }
  }

  private async runRatification(session: StoredSession): Promise<SeatFailure[]> {
    const draft = await this.composeDraft(session);
    const failures: SeatFailure[] = [];
    for (const seatId of session.spec.seat_ids) {
      const stop = await this.controlStop(session.spec.session_id);
      if (stop) break;
      try {
        await this.runOperation(
          session,
          'ratification',
          3,
          seatId,
          {
            draft_resolution: {
              recommended_option_id: draft.recommended_option_id,
              semantic_sha256: draft.semantic_sha256,
            },
          },
          (author) =>
            author.card_kind === 'ratification' &&
            author.draft_resolution_sha256 !== draft.semantic_sha256
              ? 'draft_resolution_sha256: ratification card is bound to a different draft resolution hash'
              : null,
        );
      } catch (err) {
        failures.push({
          seat_id: seatId,
          round: 3,
          message: err instanceof Error ? err.message : String(err),
        });
      }
    }
    return failures;
  }

  private async cardsOfKind<T extends CouncilCard>(
    session: StoredSession,
    kind: T['card_kind'],
    round?: number,
  ): Promise<T[]> {
    const cards = await this.host.store.listCards(session.spec.session_id);
    return cards.filter((c) => {
      if (c.card_kind !== kind) return false;
      if (round === undefined) return true;
      if (c.card_kind === 'consult') return round === 0;
      return c.round === round;
    }) as T[];
  }

  /** Deterministic crux extraction from valid Round 1 cards (max 3). */
  private async computeCruxes(session: StoredSession): Promise<Crux[]> {
    const cards = await this.cardsOfKind<AdvisorCard>(session, 'advisor', 1);
    const cruxes: Crux[] = [];
    for (const option of session.brief.options) {
      const scored = cards
        .map((c) => ({
          seat_id: c.seat_id,
          score: c.option_scores.find((s) => s.option_id === option.id)?.score ?? null,
        }))
        .filter((s) => s.score !== null) as Array<{ seat_id: SeatId; score: number }>;
      if (scored.length < 2) continue;
      const values = scored.map((s) => s.score);
      const spread = Math.max(...values) - Math.min(...values);
      if (spread >= 4) {
        const sorted = [...scored].sort((a, b) => a.score - b.score);
        cruxes.push({
          crux_id: `crux-${cruxes.length + 1}`,
          type: 'numbers',
          option_id: option.id,
          competing_claims: [
            `${sorted[0].seat_id} scores option ${option.id} at ${sorted[0].score}`,
            `${sorted[sorted.length - 1].seat_id} scores option ${option.id} at ${sorted[sorted.length - 1].score}`,
          ],
          responsible_seats: [sorted[0].seat_id, sorted[sorted.length - 1].seat_id],
          needed_evidence: `Evidence that resolves the ${spread}-point spread on option ${option.id}.`,
          resolution_test: `Re-score option ${option.id} after examining the spread's decisive facts.`,
        });
      }
    }
    if (cruxes.length === 0) {
      const preferred = new Map<string, SeatId[]>();
      for (const card of cards) {
        if (card.preferred_option_id) {
          const list = preferred.get(card.preferred_option_id) ?? [];
          list.push(card.seat_id);
          preferred.set(card.preferred_option_id, list);
        }
      }
      if (preferred.size > 1) {
        const [first, second] = [...preferred.entries()];
        cruxes.push({
          crux_id: 'crux-1',
          type: 'values',
          option_id: first[0],
          competing_claims: [
            `${first[1].join(', ')} prefer option ${first[0]}`,
            `${second[1].join(', ')} prefer option ${second[0]}`,
          ],
          responsible_seats: [...first[1].slice(0, 1), ...second[1].slice(0, 1)],
          needed_evidence: 'The decisive fact or value that separates the two preferred options.',
          resolution_test: 'Each responsible seat states what evidence would change its preference.',
        });
      }
    }
    return cruxes.slice(0, 3);
  }

  // -------------------------------------------------------------- draft and verdict

  private scoreEntries(
    session: StoredSession,
    cards: Array<AdvisorCard | RatificationCard>,
    optionId: string,
  ): Array<{ seat_id: string; weight: number; score: number | null }> {
    return session.spec.seat_ids.map((seatId) => {
      const card = cards.find((c) => c.seat_id === seatId);
      const score =
        card?.option_scores.find((s) => s.option_id === optionId)?.score ?? null;
      return {
        seat_id: seatId,
        weight: session.brief.relevance_weights[seatId] ?? 1,
        score,
      };
    });
  }

  private async composeDraft(session: StoredSession): Promise<DraftResolution> {
    const round2 = await this.cardsOfKind<AdvisorCard>(session, 'advisor', 2);
    const totalWeight = session.spec.seat_ids.reduce(
      (sum, seatId) => sum + (session.brief.relevance_weights[seatId] ?? 1),
      0,
    );
    let recommended: string | null = null;
    let best = -Infinity;
    for (const option of session.brief.options) {
      const result = computeOptionScore(
        this.scoreEntries(session, round2, option.id),
        totalWeight,
      );
      if (result.score !== null && result.score > best) {
        best = result.score;
        recommended = option.id;
      }
    }
    const conditions = new Map<string, string>();
    for (const card of round2) {
      if (card.preferred_option_id === recommended) {
        for (const condition of card.conditions) {
          conditions.set(condition.description, condition.description);
        }
      }
    }
    const unresolved = session.brief.critical_domains
      .filter((d) => d.status !== 'assessed')
      .flatMap((d) => d.unresolved_questions);
    const base = {
      schema_version: 'wise-elders.draft-resolution/v1' as const,
      session_id: session.spec.session_id,
      brief_revision: session.brief.revision,
      revision: 1,
      recommended_option_id: recommended ?? session.brief.options[0].id,
      actions: [...conditions.values()].slice(0, 5),
      prerequisites: unresolved,
      limits: session.brief.constraints
        .filter((c) => c.hard)
        .map((c) => c.description),
    };
    const semantic = canonicalHash(base);
    return { ...base, semantic_sha256: semantic };
  }

  private async quickSkipApplies(
    session: StoredSession,
    draft: DraftResolution,
  ): Promise<boolean> {
    const round2 = await this.cardsOfKind<AdvisorCard>(session, 'advisor', 2);
    if (round2.length !== session.spec.seat_ids.length) return false;
    const top = round2[0]?.preferred_option_id;
    if (!top || !round2.every((c) => c.preferred_option_id === top)) return false;
    if (top !== draft.recommended_option_id) return false;
    const scores = round2
      .map((c) => c.option_scores.find((s) => s.option_id === top)?.score ?? null)
      .filter((s): s is number => s !== null);
    if (scores.length !== round2.length) return false;
    if (Math.max(...scores) - Math.min(...scores) > 3) return false;
    if (session.brief.critical_domains.some((d) => d.status !== 'assessed')) {
      return false;
    }
    return true;
  }

  private async buildVerdict(session: StoredSession): Promise<Verdict> {
    if (session.spec.mode === 'consult') {
      const cards = await this.cardsOfKind<ConsultCard>(session, 'consult');
      const card = cards[0];
      if (!card) {
        throw new CouncilError(
          'COUNCIL_VERDICT_NOT_READY',
          'Consult completed without a validated consult card.',
          { retryable: false, exitCode: 3 },
        );
      }
      const base = {
        schema_version: 'wise-elders.verdict/v1' as const,
        result_kind: 'consult' as const,
        session_id: session.spec.session_id,
        verdict_revision: 1,
        consult_card: card,
        next_step: card.next_step,
        validation_status: 'valid' as const,
        brief_sha256: session.spec.brief_sha256,
      };
      const verdict: Verdict = { ...base, content_sha256: canonicalHash(base) };
      const check = validateVerdict(verdict);
      if (!check.ok) {
        throw new CouncilError(
          'COUNCIL_INTERNAL',
          `Consult result failed final validation: ${check.issues.map((i) => i.message).join('; ')}`,
          { retryable: false, exitCode: 1 },
        );
      }
      return verdict;
    }

    const ratification = await this.cardsOfKind<RatificationCard>(session, 'ratification');
    const round2 = await this.cardsOfKind<AdvisorCard>(session, 'advisor', 2);
    const finalCards: Array<AdvisorCard | RatificationCard> =
      ratification.length > 0 ? ratification : round2;
    const totalWeight = session.spec.seat_ids.reduce(
      (sum, seatId) => sum + (session.brief.relevance_weights[seatId] ?? 1),
      0,
    );
    const summaries = session.brief.options.map((option) => {
      const result = computeOptionScore(
        this.scoreEntries(session, finalCards, option.id),
        totalWeight,
      );
      return {
        option_id: option.id,
        score: result.score,
        display_score: result.display_score,
        weighted_sum: result.weighted_sum,
        denominator: result.denominator,
        coverage: result.coverage,
        spread: result.spread,
      };
    });
    // CWE-050 reconciliation (CWE-026 divergences (a), (b), (c);
    // CWE-026's analysis is canonical): hard-constraint findings are
    // derived and applied, never an empty list; a confirmed FAIL
    // disqualifies its option before labels; coverage below the 80
    // percent gate is INSUFFICIENT_EVIDENCE with no recommendation,
    // regardless of unresolved domains; WAIT is for adequate coverage
    // blocked by an unresolved domain or an unchecked hard constraint.
    const findings = deriveHardConstraintFindings(session.brief);
    const disqualified = new Set(
      findings.filter((f) => f.result === 'fail').map((f) => f.option_id),
    );
    const ranked = [...summaries]
      .filter((s) => s.score !== null && !disqualified.has(s.option_id))
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    const top = ranked[0] ?? null;
    const unresolvedDomains = session.brief.critical_domains.filter(
      (d) => d.status !== 'assessed',
    );
    let label: VerdictLabel;
    let recommended: string | null = top?.option_id ?? null;
    if (!top) {
      label = 'INSUFFICIENT_EVIDENCE';
      recommended = null;
    } else if ((top.coverage ?? 0) < 0.8) {
      label = 'INSUFFICIENT_EVIDENCE';
      recommended = null;
    } else if (
      unresolvedDomains.length > 0 ||
      findings.some((f) => f.option_id === top.option_id && f.result === 'unknown')
    ) {
      label = 'WAIT';
    } else {
      label = labelForScore(top.score ?? 0);
      const blocking = round2.some(
        (c) =>
          c.preferred_option_id === top.option_id &&
          c.conditions.some((cond) => cond.blocking),
      );
      if (label === 'GO' && blocking) label = 'GO_WITH_CONDITIONS';
    }
    const reasons: string[] = [];
    for (const card of round2) {
      if (card.preferred_option_id === recommended) {
        for (const arg of card.decisive_arguments) {
          if (!reasons.includes(arg) && reasons.length < 3) reasons.push(arg);
        }
      }
    }
    if (
      ranked.length > 1 &&
      top &&
      ranked[1].score !== null &&
      top.score !== null &&
      top.score - ranked[1].score <= 0.25 &&
      reasons.length < 3
    ) {
      reasons.push(
        `Near tie with option ${ranked[1].option_id} (within 0.25 points): the tradeoff is preserved rather than decided by rounding.`,
      );
    }
    const dissent =
      round2
        .filter((c) => c.preferred_option_id !== recommended)
        .sort((a, b) => {
          const sa = a.option_scores.find((s) => s.option_id === recommended)?.score ?? 10;
          const sb = b.option_scores.find((s) => s.option_id === recommended)?.score ?? 10;
          return sa - sb;
        })[0]?.strongest_objection ?? null;
    const unknowns = [
      ...new Set(round2.flatMap((c) => c.critical_unknowns)),
    ].slice(0, 10);
    const prerequisites = [
      ...new Set([
        ...unresolvedDomains.flatMap((d) => d.unresolved_questions),
        // An unchecked hard constraint on the recommended option is a
        // named prerequisite, as in CWE-026's analysis (Section 12.3).
        ...(recommended
          ? findings
              .filter((f) => f.option_id === recommended && f.result === 'unknown')
              .map(
                (f) =>
                  `Hard constraint ${f.constraint_id} has not been checked for option ${f.option_id}.`,
              )
          : []),
        ...round2.flatMap((c) =>
          c.conditions.filter((cond) => cond.blocking).map((cond) => cond.description),
        ),
      ]),
    ];
    const draft = await this.composeDraft(session);
    const proposals = draft.actions.map((action, index) => ({
      action_id: `act-${session.spec.session_id}-${index + 1}`,
      session_id: session.spec.session_id,
      verdict_revision: 1,
      title: action,
      description: action,
      rationale:
        'Proposed in the council draft resolution. Requires separate action-plan approval before any task is created; a council vote is not an execution credential.',
      source_condition_ids: round2.flatMap((c) =>
        c.conditions.filter((cond) => cond.description === action).map((cond) => cond.id),
      ),
      department_id: null,
      assigned_agent_id: null,
      sop_id: null,
      persona_id: null,
      acceptance_criteria: [] as string[],
      budget_limit: null,
      due_at: null,
      depends_on_action_ids: [] as string[],
      risk_class: 'medium' as const,
      execution_authorization_required: true as const,
    }));
    const boundedTest = session.brief.options.find(
      (o) => o.kind === 'bounded_test' && o.id !== recommended,
    );
    let support: ResolutionSupport | null = null;
    let ratificationStatus: RatificationStatus = 'not_required';
    if (session.spec.mode === 'quick' && ratification.length === 0) {
      ratificationStatus = 'not_run_by_quick_mode_policy';
    } else if (ratification.length > 0) {
      const weights = session.brief.relevance_weights;
      const counts = {
        resolution_sha256: draft.semantic_sha256,
        support: 0,
        conditional_support: 0,
        opposition: 0,
        abstention: 0,
      };
      for (const card of ratification) {
        const w = weights[card.seat_id] ?? 1;
        if (card.resolution_stance === 'support') counts.support += w;
        else if (card.resolution_stance === 'conditional_support') counts.conditional_support += w;
        else if (card.resolution_stance === 'oppose') counts.opposition += w;
        else counts.abstention += w;
      }
      support = counts;
      const materialProposed = ratification.some((c) =>
        c.amendments.some((a) => a.materiality === 'material' && a.disposition === 'proposed'),
      );
      ratificationStatus = materialProposed ? 'material_change_unratified' : 'ratified';
    }
    const acceptedAmendments = ratification.flatMap((c) =>
      c.amendments.filter((a) => a.disposition === 'accepted'),
    );
    const rejectedAmendments = ratification.flatMap((c) =>
      c.amendments.filter((a) => a.disposition === 'rejected'),
    );
    const strength = round2.every((c) => c.evidence_strength === 'high')
      ? 'high'
      : round2.some((c) => c.evidence_strength === 'low')
        ? 'low'
        : 'medium';
    const base = {
      schema_version: 'wise-elders.verdict/v1' as const,
      result_kind: 'scored' as const,
      session_id: session.spec.session_id,
      verdict_revision: 1,
      recommended_option_id: recommended,
      label,
      option_scores: summaries,
      active_weights: Object.fromEntries(
        session.spec.seat_ids.map((seatId) => [
          seatId,
          session.brief.relevance_weights[seatId] ?? 1,
        ]),
      ),
      evidence_strength: strength as 'low' | 'medium' | 'high',
      hard_constraint_findings: findings,
      main_reasons: reasons,
      strongest_dissent: dissent,
      accepted_amendments: acceptedAmendments,
      rejected_amendments: rejectedAmendments,
      critical_unknowns: unknowns,
      prerequisites,
      action_proposals: proposals,
      cheapest_informative_test: boundedTest
        ? `Run the bounded test in option ${boundedTest.id} (${boundedTest.label}) to gather the missing evidence.`
        : null,
      stop_criteria: session.brief.constraints
        .filter((c) => c.hard)
        .map((c) => `Stop if this hard constraint is violated: ${c.description}`),
      review_criteria: session.brief.unknowns.map(
        (u) => `Resolve the recorded unknown: ${u.statement}`,
      ),
      resolution_support: support,
      validation_status: 'valid' as const,
      ratification_status: ratificationStatus,
      brief_sha256: session.spec.brief_sha256,
    };
    const verdict = { ...base, content_sha256: canonicalHash(base) } as unknown as Verdict;
    const check = validateVerdict(verdict);
    if (!check.ok) {
      throw new CouncilError(
        'COUNCIL_INTERNAL',
        `Verdict failed final validation: ${check.issues.map((i) => `${i.path}: ${i.message}`).join('; ')}`,
        { retryable: false, exitCode: 1 },
      );
    }
    return verdict;
  }
}

const TERMINAL_LIKE: ReadonlySet<SessionState> = new Set([
  'COMPLETED',
  'CANCELLED',
  'FAILED',
]);
