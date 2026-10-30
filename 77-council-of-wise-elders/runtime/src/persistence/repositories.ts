/**
 * Scoped council repositories (CWE-006, directive Sections 15, 16, 18;
 * unit CWE-006 build steps 1, 2, and 4).
 *
 * This is the repository layer over the canonical council_* schema
 * (CWE-005, persistence/migrations). Every method takes an
 * AuthorizationEnvelope and enforces tenant/company scope before
 * loading or writing content (Section 16.2: never rely on globally
 * unique UUIDs as authorization; composite scope is enforced here in
 * checked repository methods and structurally by the schema's
 * composite foreign keys).
 *
 * Commit discipline (Section 16.4): session state, validated cards,
 * ordered events, and projection outbox intents that belong together
 * are written in the SAME short transaction, with the caller's fence
 * (state version, cancellation generation, lease epoch) rechecked
 * inside the transaction immediately before commit. A crash or fault
 * between the operations rolls the whole unit back: no half-committed
 * accepted result. A duplicate commit of the same logical operation
 * returns the original outcome and duplicates nothing.
 *
 * Mapping notes (canonical contracts to the CWE-005 columnar schema):
 * - SessionSpec JSON and the full SessionStateRecord are carried in
 *   the journal (the session_created and state-change event payloads),
 *   which is the durable record Section 18 defines; the sessions row
 *   columns stay the authoritative index for state, state_version,
 *   brief_revision, and the archive flag, and reconstruction
 *   cross-checks the journal record against them.
 * - council_brief_revisions carries intake-owned columns
 *   (decision_type, stakes, reversibility, success criteria) that the
 *   CWE-003 brief contract does not define; the caller supplies them
 *   via BriefRevisionProfile (CWE-023 owns their semantics) and the
 *   defaults below record "not_recorded" honestly rather than
 *   inventing values.
 * - council_verdicts.label is NOT NULL in the CWE-005 schema while a
 *   consult result carries no label in the contract (Section 11.5:
 *   never invent scores or labels for consults). Consult verdict rows
 *   therefore store the contract JSON verbatim and the placeholder
 *   label INSUFFICIENT_EVIDENCE in the column only; consumers must
 *   read result_kind from the JSON. Flagged for the coordinator as a
 *   schema-mapping gap for CWE-005.
 */

import {
  assertTransition,
  canonicalHash,
  canonicalStringify,
  validateCard,
  validateDecisionBrief,
  validateSessionSpec,
  validateSessionStateRecord,
  validateVerdict,
  type Clock,
  type CouncilCard,
  type CouncilEventType,
  type DecisionBrief,
  type IdSource,
  type SessionMode,
  type SessionState,
  type SessionStateRecord,
  type Verdict,
} from '../contracts/index.js';
import type { StoredSession } from '../cli/host-ports.js';
import {
  assertEnvelopeMatchesScope,
  assertEnvelopePurpose,
  sessionVisibleToEnvelope,
  type AuthorizationEnvelope,
} from './envelope.js';
import {
  PersistenceError,
  sessionDeleted,
  sessionNotFound,
  scopeDenied,
} from './errors.js';
import { EventJournal, type JournalEvent } from './journal.js';
import { ProjectionOutbox, type OutboxIntent, type OutboxIntentInput } from './outbox.js';
import type { CouncilDatabase, SqliteDatabaseHandle } from './sqlite.js';
import type { CouncilPersistenceConfig } from './config.js';

/** One event a composed service appends through the repository journal. */
export interface RepositoryEventInput {
  event_id: string;
  type: CouncilEventType;
  payload: Record<string, unknown>;
  created_at: string;
  from_state?: string | null;
  to_state?: string | null;
  actor_subject?: string;
}

export const DELETION_TOMBSTONE_SOURCE = 'council-persistence';
export const DELETION_TOMBSTONE_OPERATION = 'session_deleted';

/**
 * ponytail: council_sessions.mode has a SQL CHECK (0001-council-schema.sql)
 * that lists only the four old modes, and the column is never read back —
 * the spec is rebuilt from the session_created journal event and the state
 * record carries the real mode. So the row column stores a CHECK-satisfying
 * alias only; spec, state and events keep the real mode. Upgrade: widen the
 * CHECK in a later migration and delete this map.
 */
export function sessionRowMode(mode: SessionMode): SessionMode {
  if (mode === 'light') return 'selected';
  if (mode === 'medium' || mode === 'heavy') return 'full';
  return mode;
}

const STATE_EVENT_TYPES: CouncilEventType[] = [
  'session_created',
  'session_state_changed',
  'session_paused',
  'session_cancelled',
  'session_blocked',
  'session_failed',
];

export interface SessionRow {
  id: string;
  tenant_id: string;
  company_id: string;
  installation_id: string;
  owner_subject: string | null;
  created_by_subject: string;
  archived: number;
  mode: string;
  visibility: string;
  state: string;
  state_version: number;
  brief_revision: number;
  brief_hash: string;
  cancellation_generation: number;
  selected_seats_json: string;
  created_at: string;
  updated_at: string;
}

/** Intake-owned brief columns the CWE-003 brief contract does not carry. */
export interface BriefRevisionProfile {
  decision_type?: string;
  stakes?: string;
  reversibility?: string;
  success_criteria?: unknown[];
}

export interface EvidenceRecordInput {
  id: string;
  source_kind:
    | 'owner_statement'
    | 'company_data'
    | 'customer_data'
    | 'external_reference'
    | 'generated_summary';
  attachment_ref: string | null;
  summary: unknown | null;
  content_hash: string;
  attribution: 'source_principle' | 'blackceo_adaptation';
  claim: string;
  strength: 'low' | 'medium' | 'high';
  verification: 'pending' | 'valid' | 'invalid';
}

export interface CommitFence {
  expected_state_version: number;
  cancel_generation: number;
  lease_epoch: number;
}

export interface AcceptCardResult {
  outcome: 'committed' | 'duplicate';
  event: JournalEvent | null;
  card: CouncilCard;
}

export interface SaveVerdictResult {
  outcome: 'committed' | 'duplicate';
  event: JournalEvent | null;
}

function validationFailed(what: string, issues: unknown): PersistenceError {
  return new PersistenceError(
    'PERSISTENCE_VALIDATION_FAILED',
    `${what} failed canonical contract validation and was not stored.`,
    {
      retryable: false,
      action: 'Fix the payload against the canonical contracts (CWE-003) and retry.',
      detail: { issues },
    },
  );
}

function stateConflict(message: string, detail?: Record<string, unknown>): PersistenceError {
  return new PersistenceError('PERSISTENCE_STATE_CONFLICT', message, {
    retryable: true,
    action: 'Reload the session state and retry from the current version. A stale worker never overwrites a newer record.',
    detail: detail ?? null,
  });
}

export class CouncilRepositories {
  readonly journal: EventJournal;
  readonly outbox: ProjectionOutbox;

  constructor(
    private readonly db: CouncilDatabase,
    private readonly deps: {
      clock: Clock;
      ids: IdSource;
      config: CouncilPersistenceConfig;
    },
  ) {
    this.journal = new EventJournal(db);
    this.outbox = new ProjectionOutbox(db, deps.config.outbox_max_attempts);
  }

  // ------------------------------------------------------------ tombstones

  /** True when an explicit deletion tombstone exists for this session. */
  isDeleted(tenantId: string, sessionId: string): boolean {
    const row = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT request_key FROM council_request_keys
            WHERE tenant_id = ? AND source = ? AND operation = ? AND request_key = ?`,
        )
        .get(tenantId, DELETION_TOMBSTONE_SOURCE, DELETION_TOMBSTONE_OPERATION, sessionId),
    ) as { request_key: string } | undefined;
    return row !== undefined;
  }

  private assertNotDeleted(envelope: AuthorizationEnvelope, sessionId: string): void {
    if (this.isDeleted(envelope.tenant_id, sessionId)) {
      throw sessionDeleted(sessionId);
    }
  }

  /**
   * Append one committed event through the canonical journal in its own
   * transaction. The composed services (report export journaling) use
   * this instead of reaching into the journal's transaction handle; the
   * vocabulary, sequence allocation and hash chain are the journal's.
   */
  appendEvent(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    input: RepositoryEventInput,
  ): JournalEvent {
    this.assertNotDeleted(envelope, sessionId);
    return this.db.write((handle) =>
      this.journal.append(handle, envelope, sessionId, {
        event_id: input.event_id,
        type: input.type,
        from_state: input.from_state ?? null,
        to_state: input.to_state ?? null,
        actor_subject: input.actor_subject ?? envelope.actor_subject,
        payload: input.payload,
        created_at: input.created_at,
      }),
    );
  }

  // -------------------------------------------------------------- sessions

  private sessionRow(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): SessionRow | null {
    const row = handle
      .prepare(
        `SELECT id, tenant_id, company_id, installation_id, owner_subject,
                created_by_subject, archived, mode, visibility, state,
                state_version, brief_revision, brief_hash, cancellation_generation,
                selected_seats_json, created_at, updated_at
           FROM council_sessions
          WHERE tenant_id = ? AND company_id = ? AND id = ?`,
      )
      .get(envelope.tenant_id, envelope.company_id, sessionId) as SessionRow | undefined;
    return row ?? null;
  }

  /**
   * Create a session, its first brief revision, and its session_created
   * journal event in one transaction. The envelope scope must match the
   * session scope exactly; a deleted session ID stays retired.
   */
  createSession(
    envelope: AuthorizationEnvelope,
    session: StoredSession,
    profile: BriefRevisionProfile = {},
  ): StoredSession {
    assertEnvelopeMatchesScope(envelope, session.scope);
    const specCheck = validateSessionSpec(session.spec);
    if (!specCheck.ok) throw validationFailed('SessionSpec', specCheck.issues);
    const briefCheck = validateDecisionBrief(session.brief);
    if (!briefCheck.ok) throw validationFailed('DecisionBrief', briefCheck.issues);
    const stateCheck = validateSessionStateRecord(session.state);
    if (!stateCheck.ok) throw validationFailed('SessionStateRecord', stateCheck.issues);
    this.assertNotDeleted(envelope, session.spec.session_id);
    this.db.write((handle) => {
      const existing = this.sessionRow(handle, envelope, session.spec.session_id);
      if (existing) {
        throw new PersistenceError(
          'PERSISTENCE_DUPLICATE_OPERATION',
          `Council session ${session.spec.session_id} already exists in this scope.`,
          { retryable: false, action: 'Load the existing session instead of recreating it.' },
        );
      }
      this.insertSessionRow(handle, envelope, session);
      this.insertBriefRevisionRow(handle, envelope, session.brief, envelope.actor_subject, profile);
      this.journal.append(handle, envelope, session.spec.session_id, {
        event_id: this.deps.ids.newId(),
        type: 'session_created',
        from_state: null,
        to_state: session.state.state,
        actor_subject: envelope.actor_subject,
        payload: {
          sample: session.sample,
          spec: session.spec,
          state_record: session.state,
        },
        created_at: session.state.updated_at,
      });
    });
    return session;
  }

  private insertSessionRow(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    session: StoredSession,
  ): void {
    handle
      .prepare(
        `INSERT INTO council_sessions
           (id, tenant_id, company_id, installation_id, owner_subject, created_by_subject,
            archived, mode, visibility, state, state_version, brief_revision, brief_hash,
            selected_seats_json, cancellation_generation, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .run(
        session.spec.session_id,
        session.scope.tenant_id,
        session.scope.company_id,
        session.scope.installation_id,
        session.scope.owner_subject,
        envelope.actor_subject,
        session.state.archived ? 1 : 0,
        sessionRowMode(session.spec.mode),
        session.spec.visibility,
        session.state.state,
        session.state.state_version,
        session.state.brief_revision,
        session.spec.brief_sha256,
        canonicalStringify(session.spec.seat_ids),
        session.state.cancel_generation,
        session.spec.created_at,
        session.state.updated_at,
      );
  }

  private insertBriefRevisionRow(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    brief: DecisionBrief,
    authorSubject: string,
    profile: BriefRevisionProfile,
  ): void {
    handle
      .prepare(
        `INSERT INTO council_brief_revisions
           (tenant_id, company_id, session_id, revision, brief_json, canonical_hash,
            question, decision_type, stakes, deadline, reversibility,
            success_criteria_json, constraints_json, author_subject, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .run(
        envelope.tenant_id,
        envelope.company_id,
        brief.session_id,
        brief.revision,
        canonicalStringify(brief),
        canonicalHash(brief),
        brief.question,
        profile.decision_type ?? 'general',
        profile.stakes ?? 'not_recorded',
        null,
        profile.reversibility ?? 'not_recorded',
        canonicalStringify(profile.success_criteria ?? []),
        canonicalStringify(brief.constraints),
        authorSubject,
        brief.created_at,
      );
  }

  /**
   * Load a session for the envelope. Returns null when the session does
   * not exist in this scope or is not visible to the envelope actor
   * (private sessions answer only to their owner); the two cases are
   * indistinguishable by design. Works for archived sessions (archival
   * reads) exactly as for live ones.
   */
  getSession(envelope: AuthorizationEnvelope, sessionId: string): StoredSession | null {
    const row = this.db.read((handle) => this.sessionRow(handle, envelope, sessionId));
    if (!row) return null;
    if (
      !sessionVisibleToEnvelope(envelope, {
        visibility: row.visibility as StoredSession['spec']['visibility'],
        owner_subject: row.owner_subject,
      })
    ) {
      return null;
    }
    return this.reconstruct(envelope, row);
  }

  private reconstruct(envelope: AuthorizationEnvelope, row: SessionRow): StoredSession {
    const created = this.journal.latestOfType(envelope, row.id, ['session_created']);
    if (!created) {
      throw new PersistenceError(
        'PERSISTENCE_INTERNAL',
        `Session ${row.id} has no session_created journal event; the store is inconsistent.`,
      );
    }
    const spec = created.payload.spec as StoredSession['spec'];
    const sample = created.payload.sample === true;
    const briefRow = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT brief_json FROM council_brief_revisions
            WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND revision = ?`,
        )
        .get(envelope.tenant_id, envelope.company_id, row.id, row.brief_revision),
    ) as { brief_json: string } | undefined;
    if (!briefRow) {
      throw new PersistenceError(
        'PERSISTENCE_INTERNAL',
        `Session ${row.id} is missing brief revision ${row.brief_revision}; the store is inconsistent.`,
      );
    }
    const stateEvent = this.journal.latestOfType(envelope, row.id, STATE_EVENT_TYPES);
    const journaled = stateEvent?.payload.state_record as SessionStateRecord | undefined;
    if (!journaled) {
      throw new PersistenceError(
        'PERSISTENCE_INTERNAL',
        `Session ${row.id} has no journaled state record; the store is inconsistent.`,
      );
    }
    if (journaled.state_version !== row.state_version || journaled.state !== row.state) {
      throw new PersistenceError(
        'PERSISTENCE_INTERNAL',
        `Session ${row.id} journal state (version ${journaled.state_version}) disagrees with the session row (version ${row.state_version}); refusing to serve a divergent record.`,
      );
    }
    const scope: StoredSession['scope'] = {
      tenant_id: row.tenant_id,
      company_id: row.company_id,
      installation_id: row.installation_id,
      owner_subject: row.owner_subject,
    };
    return {
      spec,
      brief: JSON.parse(briefRow.brief_json) as DecisionBrief,
      scope,
      state: {
        ...journaled,
        archived: row.archived === 1,
        cancel_generation: row.cancellation_generation,
      },
      sample,
    };
  }

  /** Sessions in scope for the envelope actor, newest first. */
  listSessions(
    envelope: AuthorizationEnvelope,
    options: { includeArchived?: boolean; state?: SessionState } = {},
  ): StoredSession[] {
    const rows = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT id, tenant_id, company_id, installation_id, owner_subject,
                  created_by_subject, archived, mode, visibility, state,
                  state_version, brief_revision, brief_hash, cancellation_generation,
                  selected_seats_json, created_at, updated_at
             FROM council_sessions
            WHERE tenant_id = ? AND company_id = ?
            ORDER BY created_at DESC`,
        )
        .all(envelope.tenant_id, envelope.company_id),
    ) as SessionRow[];
    const out: StoredSession[] = [];
    for (const row of rows) {
      if (!options.includeArchived && row.archived === 1) continue;
      if (options.state && row.state !== options.state) continue;
      if (
        !sessionVisibleToEnvelope(envelope, {
          visibility: row.visibility as StoredSession['spec']['visibility'],
          owner_subject: row.owner_subject,
        })
      ) {
        continue;
      }
      out.push(this.reconstruct(envelope, row));
    }
    return out;
  }

  /**
   * Save a new brief revision: insert the immutable revision row, move
   * the session's current-revision pointer, and journal the change in
   * one transaction. Revisions are strictly sequential; a skipped or
   * replayed revision number is a conflict, never an overwrite.
   */
  saveBriefRevision(
    envelope: AuthorizationEnvelope,
    brief: DecisionBrief,
    profile: BriefRevisionProfile = {},
  ): void {
    const briefCheck = validateDecisionBrief(brief);
    if (!briefCheck.ok) throw validationFailed('DecisionBrief', briefCheck.issues);
    this.assertNotDeleted(envelope, brief.session_id);
    this.db.write((handle) => {
      const row = this.sessionRow(handle, envelope, brief.session_id);
      if (!row) throw sessionNotFound(brief.session_id);
      if (brief.revision !== row.brief_revision + 1) {
        throw stateConflict(
          `Brief revision ${brief.revision} does not follow current revision ${row.brief_revision}.`,
          { current_revision: row.brief_revision, attempted_revision: brief.revision },
        );
      }
      this.insertBriefRevisionRow(handle, envelope, brief, envelope.actor_subject, profile);
      handle
        .prepare(
          `UPDATE council_sessions SET brief_revision = ?, brief_hash = ?, updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ?`,
        )
        .run(
          brief.revision,
          canonicalHash(brief),
          this.deps.clock.nowUtc(),
          envelope.tenant_id,
          envelope.company_id,
          brief.session_id,
        );
      this.journal.append(handle, envelope, brief.session_id, {
        event_id: this.deps.ids.newId(),
        type: 'brief_revised',
        from_state: null,
        to_state: null,
        actor_subject: envelope.actor_subject,
        payload: { revision: brief.revision, canonical_hash: canonicalHash(brief) },
        created_at: this.deps.clock.nowUtc(),
      });
    });
  }

  // ----------------------------------------------------------------- state

  /**
   * Write a state record with compare-and-swap on state_version. Used
   * directly by the CouncilStore port adapter (the engine validates
   * transition legality) and by transitionState below.
   */
  writeStateRecord(
    envelope: AuthorizationEnvelope,
    record: SessionStateRecord,
    expectedVersion: number,
    event: { type: CouncilEventType; payload: Record<string, unknown> },
  ): void {
    this.assertNotDeleted(envelope, record.session_id);
    this.db.write((handle) => {
      const row = this.sessionRow(handle, envelope, record.session_id);
      if (!row) throw sessionNotFound(record.session_id);
      const result = handle
        .prepare(
          `UPDATE council_sessions
              SET state = ?, state_version = ?, archived = ?,
                  cancellation_generation = ?, updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND state_version = ?`,
        )
        .run(
          record.state,
          record.state_version,
          record.archived ? 1 : 0,
          record.cancel_generation,
          record.updated_at,
          envelope.tenant_id,
          envelope.company_id,
          record.session_id,
          expectedVersion,
        );
      if (Number(result.changes) !== 1) {
        throw stateConflict(
          `Session ${record.session_id} changed underneath this writer (expected state version ${expectedVersion}, current ${row.state_version}).`,
          { expected_version: expectedVersion, current_version: row.state_version },
        );
      }
      this.journal.append(handle, envelope, record.session_id, {
        event_id: this.deps.ids.newId(),
        type: event.type,
        from_state: row.state,
        to_state: record.state,
        actor_subject: envelope.actor_subject,
        payload: { ...event.payload, state_record: record },
        created_at: record.updated_at,
      });
    });
  }

  /**
   * A legal, fenced state transition: legality comes from the canonical
   * transition table (CWE-003 assertTransition, including the
   * cancel-generation rule), persistence is compare-and-swap, and the
   * journal event commits in the same transaction.
   */
  transitionState(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    to: SessionState,
    expectedVersion: number,
    options: { resumePhase?: SessionState | null } = {},
  ): SessionStateRecord {
    const session = this.getSession(envelope, sessionId);
    if (!session) throw sessionNotFound(sessionId);
    const current = session.state;
    const enteringCancel = to === 'CANCEL_REQUESTED';
    const { stateVersion } = assertTransition({
      mode: current.mode,
      from: current.state,
      to,
      expectedVersion,
      currentVersion: current.state_version,
      actor: envelope.actor,
      resumePhase: options.resumePhase ?? current.resume_phase,
      cancelGeneration: enteringCancel ? current.cancel_generation + 1 : undefined,
      currentCancelGeneration: current.cancel_generation,
    });
    const now = this.deps.clock.nowUtc();
    const next: SessionStateRecord = {
      ...current,
      state: to,
      state_version: stateVersion,
      cancel_generation: enteringCancel
        ? current.cancel_generation + 1
        : current.cancel_generation,
      resume_phase:
        // CWE-050 reconciliation (CWE-027 carried item): the resume
        // target is recorded when the pause is REQUESTED, from the
        // pre-pause phase, and the PAUSED/BLOCKED landing keeps it.
        // Previously the landing overwrote resume_phase with
        // PAUSE_REQUESTED, a state the RESUMING legality rule can
        // never target. A pause requested while RESUMING keeps the
        // already-recorded resume target.
        to === 'PAUSE_REQUESTED'
          ? current.state === 'RESUMING'
            ? current.resume_phase
            : current.state
          : to === 'PAUSED' || to === 'BLOCKED'
            ? current.state === 'PAUSE_REQUESTED'
              ? current.resume_phase
              : current.state
            : current.resume_phase,
      updated_at: now,
    };
    const eventType: CouncilEventType =
      to === 'PAUSED'
        ? 'session_paused'
        : to === 'CANCELLED'
          ? 'session_cancelled'
          : to === 'BLOCKED'
            ? 'session_blocked'
            : to === 'FAILED'
              ? 'session_failed'
              : 'session_state_changed';
    this.writeStateRecord(envelope, next, expectedVersion, {
      type: eventType,
      payload: { from_state: current.state, to_state: to },
    });
    return next;
  }

  /** Set or clear the archive visibility flag (never a state change). */
  setArchived(envelope: AuthorizationEnvelope, sessionId: string, archived: boolean): void {
    this.assertNotDeleted(envelope, sessionId);
    const session = this.getSession(envelope, sessionId);
    if (!session) throw sessionNotFound(sessionId);
    this.writeStateRecord(
      envelope,
      { ...session.state, archived, updated_at: this.deps.clock.nowUtc() },
      session.state.state_version,
      { type: 'session_state_changed', payload: { archived } },
    );
  }

  // ----------------------------------------------------------------- cards

  /**
   * THE atomic accepted-work commit (Sections 15.2 and 16.4): fence
   * recheck, card insert, journal event, and projection outbox intent
   * in one short transaction. No network call, render, or notification
   * happens inside it. A duplicate commit of the same logical
   * operation returns the original card and writes nothing; the same
   * operation with different content is a conflict.
   */
  acceptCard(
    envelope: AuthorizationEnvelope,
    card: CouncilCard,
    fence: CommitFence,
  ): AcceptCardResult {
    const cardCheck = validateCard(card);
    if (!cardCheck.ok) throw validationFailed('CouncilCard', cardCheck.issues);
    if (
      card.host.scope.tenant_id !== envelope.tenant_id ||
      card.host.scope.company_id !== envelope.company_id
    ) {
      throw scopeDenied('The card host stamp scope does not match the authorization envelope.');
    }
    this.assertNotDeleted(envelope, card.session_id);
    return this.db.write((handle) => {
      const row = this.sessionRow(handle, envelope, card.session_id);
      if (!row) throw sessionNotFound(card.session_id);
      const session = this.reconstruct(envelope, row);
      // Fence recheck immediately before commit (Sections 15.2, 15.8):
      // a stale worker whose lease epoch, cancellation generation, or
      // state version has moved on cannot commit.
      if (
        row.state_version !== fence.expected_state_version ||
        row.cancellation_generation !== fence.cancel_generation ||
        session.state.lease_epoch !== fence.lease_epoch
      ) {
        throw stateConflict(
          `Commit fence failed for session ${card.session_id}: the session moved on (state version, cancellation generation, or lease epoch no longer matches). The card was not committed.`,
          {
            expected_state_version: fence.expected_state_version,
            current_state_version: row.state_version,
            fence_cancel_generation: fence.cancel_generation,
            current_cancel_generation: row.cancellation_generation,
            fence_lease_epoch: fence.lease_epoch,
            current_lease_epoch: session.state.lease_epoch,
          },
        );
      }
      const fingerprint = canonicalHash(card);
      const existing = handle
        .prepare(
          `SELECT card_json, payload_fingerprint FROM council_cards
            WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND operation_id = ?`,
        )
        .get(
          envelope.tenant_id,
          envelope.company_id,
          card.session_id,
          card.host.operation_id,
        ) as { card_json: string; payload_fingerprint: string } | undefined;
      if (existing) {
        if (existing.payload_fingerprint === fingerprint) {
          return {
            outcome: 'duplicate' as const,
            event: null,
            card: JSON.parse(existing.card_json) as CouncilCard,
          };
        }
        throw new PersistenceError(
          'PERSISTENCE_OPERATION_CONFLICT',
          `Operation ${card.host.operation_id} was already committed with different content. The conflicting card was not stored.`,
          { retryable: false, action: 'Treat the committed card as authoritative; a changed input is a new operation.' },
        );
      }
      const prev = handle
        .prepare(
          `SELECT canonical_hash FROM council_cards
            WHERE tenant_id = ? AND company_id = ? AND session_id = ?
            ORDER BY rowid DESC LIMIT 1`,
        )
        .get(envelope.tenant_id, envelope.company_id, card.session_id) as
        | { canonical_hash: string }
        | undefined;
      const round =
        card.card_kind === 'ratification' ? 3 : card.card_kind === 'consult' ? 0 : card.round;
      handle
        .prepare(
          `INSERT INTO council_cards
             (tenant_id, company_id, session_id, id, kind, seat_id, round, brief_revision,
              operation_id, payload_fingerprint, card_json, canonical_hash, prev_hash,
              validation, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'valid', ?)`,
        )
        .run(
          envelope.tenant_id,
          envelope.company_id,
          card.session_id,
          card.host.operation_id,
          card.card_kind,
          card.seat_id,
          round,
          card.brief_revision,
          card.host.operation_id,
          fingerprint,
          canonicalStringify(card),
          fingerprint,
          prev?.canonical_hash ?? '',
          this.deps.clock.nowUtc(),
        );
      const event = this.journal.append(handle, envelope, card.session_id, {
        event_id: this.deps.ids.newId(),
        type: 'card_accepted',
        from_state: null,
        to_state: null,
        actor_subject: envelope.actor_subject,
        payload: {
          operation_id: card.host.operation_id,
          seat_id: card.seat_id,
          round,
          card_hash: fingerprint,
        },
        created_at: this.deps.clock.nowUtc(),
      });
      this.outbox.enqueue(handle, envelope, {
        id: this.deps.ids.newId(),
        session_id: card.session_id,
        event_sequence: event.sequence,
        topic: 'card.accepted',
        idempotency_key: card.host.operation_id,
        payload: {
          session_id: card.session_id,
          operation_id: card.host.operation_id,
          event_sequence: event.sequence,
        },
        created_at: this.deps.clock.nowUtc(),
      });
      return { outcome: 'committed' as const, event, card };
    });
  }

  /** All validated cards for a session, in commit order. */
  listCards(envelope: AuthorizationEnvelope, sessionId: string): CouncilCard[] {
    const session = this.getSession(envelope, sessionId);
    if (!session) throw sessionNotFound(sessionId);
    const rows = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT card_json FROM council_cards
            WHERE tenant_id = ? AND company_id = ? AND session_id = ?
            ORDER BY rowid ASC`,
        )
        .all(envelope.tenant_id, envelope.company_id, sessionId),
    ) as Array<{ card_json: string }>;
    return rows.map((r) => JSON.parse(r.card_json) as CouncilCard);
  }

  findCard(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    round: number,
    seatId: string,
    inputSha256: string,
  ): CouncilCard | null {
    const cards = this.listCards(envelope, sessionId);
    return (
      cards.find((card) => {
        const cardRound =
          card.card_kind === 'ratification' ? 3 : card.card_kind === 'consult' ? 0 : card.round;
        return (
          cardRound === round &&
          card.seat_id === seatId &&
          card.input_manifest_sha256 === inputSha256
        );
      }) ?? null
    );
  }

  // --------------------------------------------------------------- verdicts

  /**
   * Persist a validated verdict revision with its journal event and
   * outbox intent in one transaction. Duplicate saves of the identical
   * revision return the original outcome; a different verdict under
   * the same revision is a conflict (verdicts are immutable,
   * Section 16.2).
   */
  saveVerdict(envelope: AuthorizationEnvelope, verdict: Verdict): SaveVerdictResult {
    const check = validateVerdict(verdict);
    if (!check.ok) throw validationFailed('Verdict', check.issues);
    this.assertNotDeleted(envelope, verdict.session_id);
    return this.db.write((handle) => {
      const row = this.sessionRow(handle, envelope, verdict.session_id);
      if (!row) throw sessionNotFound(verdict.session_id);
      const existing = handle
        .prepare(
          `SELECT canonical_hash FROM council_verdicts
            WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND brief_revision = ?`,
        )
        .get(
          envelope.tenant_id,
          envelope.company_id,
          verdict.session_id,
          verdict.verdict_revision,
        ) as { canonical_hash: string } | undefined;
      if (existing) {
        if (existing.canonical_hash === verdict.content_sha256) {
          return { outcome: 'duplicate' as const, event: null };
        }
        throw new PersistenceError(
          'PERSISTENCE_OPERATION_CONFLICT',
          `Verdict revision ${verdict.verdict_revision} for session ${verdict.session_id} was already committed with different content. Verdicts are immutable; a correction is a new revision.`,
          { retryable: false },
        );
      }
      const session = this.reconstruct(envelope, row);
      const lastCard = handle
        .prepare(
          `SELECT canonical_hash FROM council_cards
            WHERE tenant_id = ? AND company_id = ? AND session_id = ?
            ORDER BY rowid DESC LIMIT 1`,
        )
        .get(envelope.tenant_id, envelope.company_id, verdict.session_id) as
        | { canonical_hash: string }
        | undefined;
      const now = this.deps.clock.nowUtc();
      const isScored = verdict.result_kind === 'scored';
      handle
        .prepare(
          `INSERT INTO council_verdicts
             (tenant_id, company_id, session_id, id, brief_revision, verdict_json,
              canonical_hash, verdict_hash, cards_root_hash, brief_hash, policy_hash,
              validation_run_hash, label, validation, ratification, chosen_option_id,
              client_decision_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        )
        .run(
          envelope.tenant_id,
          envelope.company_id,
          verdict.session_id,
          `verdict-${verdict.verdict_revision}`,
          verdict.verdict_revision,
          canonicalStringify(verdict),
          verdict.content_sha256,
          verdict.content_sha256,
          lastCard?.canonical_hash ?? canonicalHash({ cards: [] }),
          verdict.brief_sha256,
          canonicalHash(session.spec.model_policy),
          canonicalHash({
            validation_status: verdict.validation_status,
            content_sha256: verdict.content_sha256,
            validated_at: now,
          }),
          // See the mapping note in the file header: consult results
          // carry no contract label; the column placeholder is never
          // read back as a recommendation.
          isScored ? verdict.label : 'INSUFFICIENT_EVIDENCE',
          verdict.validation_status,
          isScored ? verdict.ratification_status : 'not_required',
          isScored ? verdict.recommended_option_id : null,
          null,
          now,
        );
      const event = this.journal.append(handle, envelope, verdict.session_id, {
        event_id: this.deps.ids.newId(),
        type: 'verdict_validated',
        from_state: null,
        to_state: null,
        actor_subject: envelope.actor_subject,
        payload: {
          verdict_revision: verdict.verdict_revision,
          result_kind: verdict.result_kind,
          content_sha256: verdict.content_sha256,
        },
        created_at: now,
      });
      this.outbox.enqueue(handle, envelope, {
        id: this.deps.ids.newId(),
        session_id: verdict.session_id,
        event_sequence: event.sequence,
        topic: 'verdict.validated',
        idempotency_key: `verdict:${verdict.session_id}:${verdict.verdict_revision}`,
        payload: {
          session_id: verdict.session_id,
          verdict_revision: verdict.verdict_revision,
          event_sequence: event.sequence,
        },
        created_at: now,
      });
      return { outcome: 'committed' as const, event };
    });
  }

  /** The latest committed verdict for a session, or null. */
  getVerdict(envelope: AuthorizationEnvelope, sessionId: string): Verdict | null {
    const session = this.getSession(envelope, sessionId);
    if (!session) return null;
    const row = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT verdict_json FROM council_verdicts
            WHERE tenant_id = ? AND company_id = ? AND session_id = ?
            ORDER BY brief_revision DESC LIMIT 1`,
        )
        .get(envelope.tenant_id, envelope.company_id, sessionId),
    ) as { verdict_json: string } | undefined;
    return row ? (JSON.parse(row.verdict_json) as Verdict) : null;
  }

  // --------------------------------------------------------------- evidence

  /**
   * Record one authorized case-evidence item (Section 16.2: references
   * and hashes, never secrets). The frozen evidence manifest itself
   * lives in the brief; these rows are the scoped evidence records a
   * session accumulates.
   */
  addEvidenceRecord(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    record: EvidenceRecordInput,
  ): void {
    if (record.attachment_ref === null && record.summary === null) {
      throw new PersistenceError(
        'PERSISTENCE_VALIDATION_FAILED',
        'An evidence record needs an attachment reference or a summary; a content-free record was not stored.',
        { retryable: false },
      );
    }
    this.assertNotDeleted(envelope, sessionId);
    this.db.write((handle) => {
      const row = this.sessionRow(handle, envelope, sessionId);
      if (!row) throw sessionNotFound(sessionId);
      handle
        .prepare(
          `INSERT INTO council_evidence
             (tenant_id, company_id, session_id, id, source_kind, attachment_ref,
              summary_json, content_hash, attribution, claim, strength, verification,
              created_by_subject, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        )
        .run(
          envelope.tenant_id,
          envelope.company_id,
          sessionId,
          record.id,
          record.source_kind,
          record.attachment_ref,
          record.summary === null ? null : canonicalStringify(record.summary),
          record.content_hash,
          record.attribution,
          record.claim,
          record.strength,
          record.verification,
          envelope.actor_subject,
          this.deps.clock.nowUtc(),
        );
    });
  }

  listEvidenceRecords(
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): Array<Record<string, unknown>> {
    const session = this.getSession(envelope, sessionId);
    if (!session) throw sessionNotFound(sessionId);
    return this.db.read((handle) =>
      handle
        .prepare(
          `SELECT id, source_kind, attachment_ref, summary_json, content_hash,
                  attribution, claim, strength, verification, created_by_subject, created_at
             FROM council_evidence
            WHERE tenant_id = ? AND company_id = ? AND session_id = ?
            ORDER BY created_at ASC`,
        )
        .all(envelope.tenant_id, envelope.company_id, sessionId),
    ) as Array<Record<string, unknown>>;
  }

  // ------------------------------------------------------------ request keys

  /**
   * API idempotency (Section 17): the first claim records the payload
   * fingerprint and wins; a replay with the same fingerprint returns
   * the recorded claim; a replay with a DIFFERENT fingerprint is a
   * conflict and records nothing (the host maps it to HTTP 409).
   */
  /**
   * Commit one projection-outbox intent outside a caller transaction
   * (W74-A session-close marker). Idempotent per (scope, topic,
   * idempotency_key): a replay returns the existing intent and writes
   * nothing.
   */
  enqueueOutboxIntent(
    envelope: AuthorizationEnvelope,
    input: OutboxIntentInput,
  ): { intent: OutboxIntent; created: boolean } {
    return this.db.write((handle) => this.outbox.enqueue(handle, envelope, input));
  }

  claimRequestKey(input: {
    tenantId: string;
    source: string;
    operation: string;
    requestKey: string;
    payloadFingerprint: string;
    sessionId: string | null;
  }): { outcome: 'claimed' | 'replay' | 'conflict'; payloadFingerprint: string } {
    return this.db.write((handle) => {
      const existing = handle
        .prepare(
          `SELECT payload_fingerprint FROM council_request_keys
            WHERE tenant_id = ? AND source = ? AND operation = ? AND request_key = ?`,
        )
        .get(input.tenantId, input.source, input.operation, input.requestKey) as
        | { payload_fingerprint: string }
        | undefined;
      if (existing) {
        return existing.payload_fingerprint === input.payloadFingerprint
          ? { outcome: 'replay' as const, payloadFingerprint: existing.payload_fingerprint }
          : { outcome: 'conflict' as const, payloadFingerprint: existing.payload_fingerprint };
      }
      handle
        .prepare(
          `INSERT INTO council_request_keys
             (tenant_id, source, operation, request_key, payload_fingerprint, session_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)`,
        )
        .run(
          input.tenantId,
          input.source,
          input.operation,
          input.requestKey,
          input.payloadFingerprint,
          input.sessionId,
          this.deps.clock.nowUtc(),
        );
      return { outcome: 'claimed' as const, payloadFingerprint: input.payloadFingerprint };
    });
  }

  // --------------------------------------------------------------- deletion

  /**
   * Explicit authorized deletion (Section 16.5). In one transaction:
   * record the minimal non-content tombstone, collect the session's
   * diagnostic payload references, and delete the session row (the
   * schema's composite foreign keys cascade to every child table:
   * briefs, evidence, cards, verdicts, events, jobs, attempts,
   * reservations, proposals, approvals, previews, diagnostic rows,
   * task links, outcome reviews, and outbox intents). The caller
   * deletes the returned protected payload files after commit; reads
   * are blocked by the tombstone and the missing rows even if a file
   * sweep is delayed, and late writes fail with SESSION_DELETED, so a
   * deleted session is never reconstituted by a delayed event or a
   * stale worker. Backup copies follow the host's retention policy;
   * this method makes no claim of immediate physical erasure from
   * historical backups.
   */
  deleteSession(
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): { deleted: true; diagnosticProtectedRefs: string[] } {
    assertEnvelopePurpose(envelope, 'delete', 'Session deletion');
    return this.db.write((handle) => {
      const row = this.sessionRow(handle, envelope, sessionId);
      if (!row) {
        if (this.isDeleted(envelope.tenant_id, sessionId)) throw sessionDeleted(sessionId);
        throw sessionNotFound(sessionId);
      }
      const refs = handle
        .prepare(
          `SELECT payload_protected_ref FROM council_diagnostic_capture
            WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND record_kind = 'payload'`,
        )
        .all(envelope.tenant_id, envelope.company_id, sessionId) as Array<{
        payload_protected_ref: string;
      }>;
      handle
        .prepare(
          `INSERT INTO council_request_keys
             (tenant_id, source, operation, request_key, payload_fingerprint, session_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)`,
        )
        .run(
          envelope.tenant_id,
          DELETION_TOMBSTONE_SOURCE,
          DELETION_TOMBSTONE_OPERATION,
          sessionId,
          canonicalHash({
            deleted_session: sessionId,
            deleted_by: envelope.actor_subject,
            deleted_at: this.deps.clock.nowUtc(),
          }),
          sessionId,
          this.deps.clock.nowUtc(),
        );
      handle
        .prepare(
          `DELETE FROM council_sessions WHERE tenant_id = ? AND company_id = ? AND id = ?`,
        )
        .run(envelope.tenant_id, envelope.company_id, sessionId);
      return {
        deleted: true as const,
        diagnosticProtectedRefs: refs.map((r) => r.payload_protected_ref),
      };
    });
  }
}
