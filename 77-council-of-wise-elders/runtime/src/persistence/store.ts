/**
 * The composed council store (CWE-006, directive Sections 15, 16, 18).
 *
 * CouncilStoreService is the standalone composition of the CWE-006
 * persistence layer: it opens the council database in the data
 * directory, applies the canonical CWE-005 schema (additive, IF NOT
 * EXISTS, safe to re-apply on every open), enforces the recorded
 * state-authority profile, and wires the scoped repositories, the
 * event journal, the projection outbox, the job/checkpoint
 * repository, and the single diagnostic sink behind one object. It
 * also implements the CWE-004 CouncilStore host port, so the portable
 * engine can run on the full canonical schema instead of the
 * foundation's minimal local store.
 *
 * Authority law (Sections 4.5 and 16.1): the mode recorded in the
 * installation profile governs. This composition IS the standalone
 * authority; when the recorded or requested mode is 'managed', the
 * Command Center adapter owns the store and this composition refuses
 * to open rather than silently becoming a second, divergent
 * authority.
 *
 * Restart behavior (Section 16.5): opening an existing database
 * re-reads the profile, re-applies the additive schema, and serves
 * sessions, journal chains, byte counters, and outbox intents exactly
 * as they were committed; nothing is rebuilt from volatile state.
 */

import { join } from 'node:path';
import {
  SCHEMA_VERSIONS,
  type Clock,
  type CouncilCard,
  type CouncilEvent,
  type IdSource,
  type JobCheckpoint,
  type SeatId,
  type SessionStateRecord,
  type Verdict,
} from '../contracts/index.js';
import type { CouncilStore, StoredSession } from '../cli/host-ports.js';
import { ensureDataDir, resolveDataDir } from '../cli/paths.js';
import {
  parsePersistenceConfig,
  type CouncilPersistenceConfig,
} from './config.js';
import { DiagnosticSink, type DiagnosticRedactor } from './diagnostics.js';
import {
  envelopeFromScope,
  type AuthorizationEnvelope,
} from './envelope.js';
import { PersistenceError, sessionNotFound } from './errors.js';
import { CouncilJobs } from './jobs.js';
import { COUNCIL_SCHEMA_SQL } from './index.js';
import { ensureInstallationProfile, type CouncilInstallationProfile } from './profile.js';
import { CouncilRepositories } from './repositories.js';
import { CouncilDatabase } from './sqlite.js';

export interface OpenCouncilStoreOptions {
  /** Council data directory; resolved via cli/paths when omitted. */
  dataDir?: string;
  /** Database file path; defaults to <dataDir>/council.db. */
  databasePath?: string;
  /** Persistence configuration input; parsed against the locked surface. */
  config?: unknown;
  clock: Clock;
  ids: IdSource;
  /**
   * The host-resolved service envelope (CWE-007 owns principal
   * resolution). Port calls act under this envelope's scope and actor.
   */
  envelope: AuthorizationEnvelope;
  /** Managed-mode authority locator (reference only, never a credential). */
  authorityRef?: string | null;
  /** Optional stronger diagnostic redactor; defaults to the built-in one. */
  redact?: DiagnosticRedactor;
}

export class CouncilStoreService implements CouncilStore {
  readonly config: CouncilPersistenceConfig;
  readonly profile: CouncilInstallationProfile;
  readonly dataDir: string;
  readonly repositories: CouncilRepositories;
  readonly jobs: CouncilJobs;
  readonly diagnostics: DiagnosticSink;
  private readonly db: CouncilDatabase;
  private readonly envelope: AuthorizationEnvelope;
  private readonly clock: Clock;

  private constructor(args: {
    db: CouncilDatabase;
    config: CouncilPersistenceConfig;
    profile: CouncilInstallationProfile;
    dataDir: string;
    envelope: AuthorizationEnvelope;
    clock: Clock;
    ids: IdSource;
    redact?: DiagnosticRedactor;
  }) {
    this.db = args.db;
    this.config = args.config;
    this.profile = args.profile;
    this.dataDir = args.dataDir;
    this.envelope = args.envelope;
    this.clock = args.clock;
    this.repositories = new CouncilRepositories(args.db, {
      clock: args.clock,
      ids: args.ids,
      config: args.config,
    });
    this.jobs = new CouncilJobs(args.db, { clock: args.clock, ids: args.ids });
    this.diagnostics = new DiagnosticSink(args.db, {
      clock: args.clock,
      ids: args.ids,
      dataDir: args.dataDir,
      journal: this.repositories.journal,
      redact: args.redact,
    });
  }

  static open(options: OpenCouncilStoreOptions): CouncilStoreService {
    const config = parsePersistenceConfig(options.config);
    const dataDir = ensureDataDir(options.dataDir ?? resolveDataDir({}));
    const profile = ensureInstallationProfile(dataDir, {
      authority_mode: config.authority_mode,
      authority_ref: options.authorityRef ?? null,
      installation_id: options.envelope.installation_id,
      recorded_at: options.clock.nowUtc(),
    });
    if (profile.authority_mode !== 'standalone') {
      throw new PersistenceError(
        'PERSISTENCE_AUTHORITY_MODE_MISMATCH',
        'This installation is recorded as managed by the Command Center authority. The standalone composition refuses to open a second, divergent store; use the Command Center adapter.',
        { retryable: false },
      );
    }
    const db = CouncilDatabase.open(options.databasePath ?? join(dataDir, 'council.db'), {
      busyTimeoutMs: config.busy_timeout_ms,
      busyMaxAttempts: config.busy_max_attempts,
      busyBaseDelayMs: config.busy_base_delay_ms,
    });
    try {
      // The canonical schema is additive (IF NOT EXISTS throughout):
      // applying it on open is the restart and self-heal path, and a
      // no-op when the schema is already current.
      db.write((handle) => handle.exec(COUNCIL_SCHEMA_SQL));
      const probe = db.read((handle) =>
        handle
          .prepare(
            `SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'council_sessions'`,
          )
          .get(),
      ) as { name: string } | undefined;
      if (!probe) {
        throw new PersistenceError(
          'PERSISTENCE_SCHEMA_UNAVAILABLE',
          'The canonical council schema is not present after migration. The store was not opened.',
          { retryable: false },
        );
      }
    } catch (error) {
      db.close();
      throw error;
    }
    return new CouncilStoreService({
      db,
      config,
      profile,
      dataDir,
      envelope: options.envelope,
      clock: options.clock,
      ids: options.ids,
      redact: options.redact,
    });
  }

  close(): void {
    this.db.close();
  }

  /** Verify every session journal chain in the service scope (restart audit). */
  verifyAllChains(): Array<{ session_id: string; ok: boolean; checked: number }> {
    const sessions = this.repositories.listSessions(this.envelope, { includeArchived: true });
    return sessions.map((session) => {
      const result = this.repositories.journal.verifyChain(
        this.envelope,
        session.spec.session_id,
      );
      return { session_id: session.spec.session_id, ok: result.ok, checked: result.checked };
    });
  }

  // ------------------------------------------------- CouncilStore port

  async createSession(session: StoredSession): Promise<void> {
    const envelope = envelopeFromScope(
      session.scope,
      this.envelope.actor_subject,
      this.envelope.actor,
      'write',
    );
    this.repositories.createSession(envelope, session);
  }

  async getSession(sessionId: string): Promise<StoredSession | null> {
    return this.repositories.getSession(this.envelope, sessionId);
  }

  async updateState(record: SessionStateRecord, expectedVersion: number): Promise<void> {
    this.repositories.writeStateRecord(this.envelope, record, expectedVersion, {
      type: 'session_state_changed',
      payload: {},
    });
  }

  async saveCard(card: CouncilCard): Promise<void> {
    const session = this.repositories.getSession(this.envelope, card.session_id);
    if (!session) throw sessionNotFound(card.session_id);
    const result = this.repositories.acceptCard(this.envelope, card, {
      expected_state_version: session.state.state_version,
      cancel_generation: session.state.cancel_generation,
      lease_epoch: session.state.lease_epoch,
    });
    if (result.outcome === 'duplicate') {
      throw new PersistenceError(
        'PERSISTENCE_DUPLICATE_OPERATION',
        `Operation ${card.host.operation_id} already has a committed card. The port contract rejects duplicate logical operations; callers check findCard first when resuming.`,
        { retryable: false },
      );
    }
  }

  async findCard(
    sessionId: string,
    round: number,
    seatId: SeatId,
    inputSha256: string,
  ): Promise<CouncilCard | null> {
    const session = this.repositories.getSession(this.envelope, sessionId);
    if (!session) return null;
    return this.repositories.findCard(this.envelope, sessionId, round, seatId, inputSha256);
  }

  async listCards(sessionId: string): Promise<CouncilCard[]> {
    const session = this.repositories.getSession(this.envelope, sessionId);
    if (!session) return [];
    return this.repositories.listCards(this.envelope, sessionId);
  }

  async appendEvent(event: Omit<CouncilEvent, 'sequence'>): Promise<CouncilEvent> {
    const stored = this.db.write((handle) =>
      this.repositories.journal.append(handle, this.envelope, event.session_id, {
        event_id: event.event_id,
        type: event.event_type,
        from_state:
          typeof event.payload.from_state === 'string' ? event.payload.from_state : null,
        to_state: typeof event.payload.to_state === 'string' ? event.payload.to_state : null,
        actor_subject: event.owner_subject ?? this.envelope.actor_subject,
        payload: { ...event.payload, actor: event.actor },
        created_at: event.created_at,
      }),
    );
    return {
      schema_version: SCHEMA_VERSIONS.event,
      event_id: stored.event_id,
      session_id: event.session_id,
      sequence: stored.sequence,
      event_type: stored.type,
      tenant_id: this.envelope.tenant_id,
      company_id: this.envelope.company_id,
      owner_subject: event.owner_subject,
      actor: event.actor,
      payload: event.payload,
      created_at: stored.created_at,
    };
  }

  async listEvents(sessionId: string, afterSequence = 0): Promise<CouncilEvent[]> {
    const session = this.repositories.getSession(this.envelope, sessionId);
    if (!session) return [];
    return this.repositories.journal.list(this.envelope, sessionId, afterSequence).map((event) => {
      const { actor, ...payload } = event.payload;
      return {
        schema_version: SCHEMA_VERSIONS.event,
        event_id: event.event_id,
        session_id: sessionId,
        sequence: event.sequence,
        event_type: event.type,
        tenant_id: this.envelope.tenant_id,
        company_id: this.envelope.company_id,
        owner_subject: session.scope.owner_subject,
        actor:
          actor === 'owner' || actor === 'system' || actor === 'worker' || actor === 'chair'
            ? actor
            : this.envelope.actor,
        payload,
        created_at: event.created_at,
      };
    });
  }

  async saveVerdict(verdict: Verdict): Promise<void> {
    this.repositories.saveVerdict(this.envelope, verdict);
  }

  async getVerdict(sessionId: string): Promise<Verdict | null> {
    return this.repositories.getVerdict(this.envelope, sessionId);
  }

  async saveCheckpoint(checkpoint: JobCheckpoint): Promise<void> {
    const session = this.repositories.getSession(this.envelope, checkpoint.session_id);
    if (!session) throw sessionNotFound(checkpoint.session_id);
    this.jobs.saveCheckpoint(this.envelope, checkpoint, session.state.cancel_generation);
  }

  async getCheckpoint(
    sessionId: string,
    phase: string,
    seatId: SeatId | null,
    inputSha256: string,
  ): Promise<JobCheckpoint | null> {
    const session = this.repositories.getSession(this.envelope, sessionId);
    if (!session) return null;
    return this.jobs.getCheckpoint(this.envelope, {
      sessionId,
      attempt: session.state.attempt,
      briefRevision: session.state.brief_revision,
      phaseJobKey: phase,
      seatId,
      inputSha256,
      currentCancelGeneration: session.state.cancel_generation,
    });
  }
}
