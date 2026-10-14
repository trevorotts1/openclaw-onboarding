/**
 * CWE-023 intake persistence: ports and store implementations.
 *
 * Two persistence concerns, kept separate on purpose:
 *
 * 1. Brief revisions (the canonical product record) persist through
 *    the CWE-006 scoped store. RepositoryIntakeBriefStore adapts
 *    CouncilRepositories: session creation, immutable revision rows,
 *    and the repository's own strictly-sequential revision discipline,
 *    with its state conflicts mapped to the intake conflict error.
 *    The frozen brief revision lives there, under the session's
 *    composite scope, with its canonical hash.
 *
 * 2. Intake working records (the resumable draft, draft brief
 *    revisions composed before freeze, the private preference value,
 *    the freeze record, and queued amendments) persist through the
 *    IntakeWorkingStore port. Two implementations ship here: an
 *    in-memory store (deterministic tests) and a durable file store
 *    for the standalone composition (one canonical-JSON document per
 *    record under a caller-supplied data directory, written by
 *    temp-file rename so a crash never leaves a torn record). The
 *    managed Command Center draft service binds the same port at
 *    CWE-050 composition; the port is the contract either way.
 *
 * Draft brief revisions are composed during intake and held as
 * working records because the canonical store creates a session only
 * with its complete frozen spec (CWE-006 createSession). At freeze,
 * the service writes the session and the frozen brief revision into
 * the canonical store in one step, preserving the revision number;
 * earlier draft revisions remain in the working record chain.
 */
import { mkdirSync, readFileSync, renameSync, writeFileSync, existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import {
  canonicalHash,
  canonicalStringify,
  type DecisionBrief,
} from '../contracts/index.js';
import type { StoredSession } from '../cli/host-ports.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import { PersistenceError } from '../persistence/errors.js';
import type { CouncilRepositories } from '../persistence/repositories.js';
import type { FreezeRecord } from './service-types.js';
import {
  IntakeError,
  type ClientPreferencePrivate,
  type IntakeDraft,
  type ProposedAmendment,
} from './types.js';

/** The canonical brief-revision store port (CWE-006 backed). */
export interface IntakeBriefStore {
  getSession(sessionId: string): Promise<StoredSession | null>;
  createSession(session: StoredSession): Promise<void>;
  saveBriefRevision(brief: DecisionBrief): Promise<void>;
}

/** Intake working records port. See the module header for the split. */
export interface IntakeWorkingStore {
  saveDraft(draft: IntakeDraft): Promise<void>;
  loadDraft(intakeId: string): Promise<IntakeDraft | null>;
  loadDraftBySession(sessionId: string): Promise<IntakeDraft | null>;
  /** Immutable: an existing revision with different content conflicts. */
  saveDraftBriefRevision(brief: DecisionBrief): Promise<void>;
  loadDraftBriefRevision(
    sessionId: string,
    revision: number,
  ): Promise<DecisionBrief | null>;
  listDraftBriefRevisions(sessionId: string): Promise<DecisionBrief[]>;
  savePreference(record: ClientPreferencePrivate): Promise<void>;
  loadPreference(preferenceId: string): Promise<ClientPreferencePrivate | null>;
  deletePreference(preferenceId: string): Promise<void>;
  saveFreezeRecord(record: FreezeRecord): Promise<void>;
  loadFreezeRecord(sessionId: string): Promise<FreezeRecord | null>;
  saveAmendment(record: ProposedAmendment): Promise<void>;
  listAmendments(sessionId: string): Promise<ProposedAmendment[]>;
}

// ---------------------------------------------------------------------------
// CWE-006 repository adapter
// ---------------------------------------------------------------------------

function mapStoreError(error: unknown): never {
  if (error instanceof PersistenceError && error.code === 'PERSISTENCE_STATE_CONFLICT') {
    throw new IntakeError(
      'INTAKE_REVISION_CONFLICT',
      'The brief changed underneath this writer. Reload the current revision and retry; nothing was overwritten.',
      { store_code: error.code },
    );
  }
  throw error;
}

export class RepositoryIntakeBriefStore implements IntakeBriefStore {
  constructor(
    private readonly repositories: CouncilRepositories,
    private readonly envelope: AuthorizationEnvelope,
  ) {}

  async getSession(sessionId: string): Promise<StoredSession | null> {
    return this.repositories.getSession(this.envelope, sessionId);
  }

  async createSession(session: StoredSession): Promise<void> {
    try {
      this.repositories.createSession(this.envelope, session);
    } catch (error) {
      mapStoreError(error);
    }
  }

  async saveBriefRevision(brief: DecisionBrief): Promise<void> {
    try {
      this.repositories.saveBriefRevision(this.envelope, brief);
    } catch (error) {
      mapStoreError(error);
    }
  }
}

// ---------------------------------------------------------------------------
// In-memory working store (deterministic tests)
// ---------------------------------------------------------------------------

export class MemoryIntakeWorkingStore implements IntakeWorkingStore {
  private readonly drafts = new Map<string, IntakeDraft>();
  private readonly draftBySession = new Map<string, string>();
  private readonly briefRevisions = new Map<string, DecisionBrief>();
  private readonly preferences = new Map<string, ClientPreferencePrivate>();
  private readonly freezeRecords = new Map<string, FreezeRecord>();
  private readonly amendments = new Map<string, ProposedAmendment[]>();

  async saveDraft(draft: IntakeDraft): Promise<void> {
    this.drafts.set(draft.intake_id, draft);
    this.draftBySession.set(draft.session_id, draft.intake_id);
  }

  async loadDraft(intakeId: string): Promise<IntakeDraft | null> {
    return this.drafts.get(intakeId) ?? null;
  }

  async loadDraftBySession(sessionId: string): Promise<IntakeDraft | null> {
    const intakeId = this.draftBySession.get(sessionId);
    return intakeId ? (this.drafts.get(intakeId) ?? null) : null;
  }

  async saveDraftBriefRevision(brief: DecisionBrief): Promise<void> {
    const key = `${brief.session_id}:${brief.revision}`;
    const existing = this.briefRevisions.get(key);
    if (existing) {
      if (canonicalHash(existing) !== canonicalHash(brief)) {
        throw new IntakeError(
          'INTAKE_STORE_CONFLICT',
          `Draft brief revision ${brief.revision} already exists with different content. Revisions are immutable.`,
        );
      }
      return;
    }
    this.briefRevisions.set(key, brief);
  }

  async loadDraftBriefRevision(
    sessionId: string,
    revision: number,
  ): Promise<DecisionBrief | null> {
    return this.briefRevisions.get(`${sessionId}:${revision}`) ?? null;
  }

  async listDraftBriefRevisions(sessionId: string): Promise<DecisionBrief[]> {
    return [...this.briefRevisions.values()]
      .filter((b) => b.session_id === sessionId)
      .sort((a, b) => a.revision - b.revision);
  }

  async savePreference(record: ClientPreferencePrivate): Promise<void> {
    this.preferences.set(record.preference_id, record);
  }

  async loadPreference(preferenceId: string): Promise<ClientPreferencePrivate | null> {
    return this.preferences.get(preferenceId) ?? null;
  }

  async deletePreference(preferenceId: string): Promise<void> {
    this.preferences.delete(preferenceId);
  }

  async saveFreezeRecord(record: FreezeRecord): Promise<void> {
    this.freezeRecords.set(record.session_id, record);
  }

  async loadFreezeRecord(sessionId: string): Promise<FreezeRecord | null> {
    return this.freezeRecords.get(sessionId) ?? null;
  }

  async saveAmendment(record: ProposedAmendment): Promise<void> {
    const list = this.amendments.get(record.session_id) ?? [];
    list.push(record);
    this.amendments.set(record.session_id, list);
  }

  async listAmendments(sessionId: string): Promise<ProposedAmendment[]> {
    return [...(this.amendments.get(sessionId) ?? [])];
  }
}

// ---------------------------------------------------------------------------
// Durable file working store (standalone composition)
// ---------------------------------------------------------------------------

/**
 * One canonical-JSON document per record under `directory`, in
 * kind-prefixed files. Writes go to a temp file renamed over the
 * target, so an interrupted write never leaves a torn record; loads
 * parse the exact canonical bytes. Record IDs are validated opaque
 * IDs by the contracts layer, so file names carry no client text.
 */
export class FileIntakeWorkingStore implements IntakeWorkingStore {
  constructor(private readonly directory: string) {
    mkdirSync(directory, { recursive: true });
  }

  private pathFor(kind: string, id: string): string {
    return join(this.directory, `${kind}-${id}.json`);
  }

  private write(kind: string, id: string, value: unknown): void {
    const target = this.pathFor(kind, id);
    const temp = `${target}.tmp`;
    writeFileSync(temp, canonicalStringify(value), 'utf8');
    renameSync(temp, target);
  }

  private read<T>(kind: string, id: string): T | null {
    const target = this.pathFor(kind, id);
    if (!existsSync(target)) return null;
    return JSON.parse(readFileSync(target, 'utf8')) as T;
  }

  private listByPrefix<T>(kind: string): T[] {
    const out: T[] = [];
    for (const name of readdirSync(this.directory)) {
      if (!name.startsWith(`${kind}-`) || !name.endsWith('.json')) continue;
      out.push(JSON.parse(readFileSync(join(this.directory, name), 'utf8')) as T);
    }
    return out;
  }

  async saveDraft(draft: IntakeDraft): Promise<void> {
    this.write('draft', draft.intake_id, draft);
    this.write('draft-session', draft.session_id, { intake_id: draft.intake_id });
  }

  async loadDraft(intakeId: string): Promise<IntakeDraft | null> {
    return this.read<IntakeDraft>('draft', intakeId);
  }

  async loadDraftBySession(sessionId: string): Promise<IntakeDraft | null> {
    const pointer = this.read<{ intake_id: string }>('draft-session', sessionId);
    return pointer ? this.loadDraft(pointer.intake_id) : null;
  }

  async saveDraftBriefRevision(brief: DecisionBrief): Promise<void> {
    const id = `${brief.session_id}-r${brief.revision}`;
    const existing = this.read<DecisionBrief>('brief', id);
    if (existing) {
      if (canonicalHash(existing) !== canonicalHash(brief)) {
        throw new IntakeError(
          'INTAKE_STORE_CONFLICT',
          `Draft brief revision ${brief.revision} already exists with different content. Revisions are immutable.`,
        );
      }
      return;
    }
    this.write('brief', id, brief);
  }

  async loadDraftBriefRevision(
    sessionId: string,
    revision: number,
  ): Promise<DecisionBrief | null> {
    return this.read<DecisionBrief>('brief', `${sessionId}-r${revision}`);
  }

  async listDraftBriefRevisions(sessionId: string): Promise<DecisionBrief[]> {
    return this.listByPrefix<DecisionBrief>('brief')
      .filter((b) => b.session_id === sessionId)
      .sort((a, b) => a.revision - b.revision);
  }

  async savePreference(record: ClientPreferencePrivate): Promise<void> {
    this.write('preference', record.preference_id, record);
  }

  async loadPreference(preferenceId: string): Promise<ClientPreferencePrivate | null> {
    return this.read<ClientPreferencePrivate>('preference', preferenceId);
  }

  async deletePreference(preferenceId: string): Promise<void> {
    const target = this.pathFor('preference', preferenceId);
    if (existsSync(target)) renameSync(target, `${target}.deleted`);
  }

  async saveFreezeRecord(record: FreezeRecord): Promise<void> {
    this.write('freeze', record.session_id, record);
  }

  async loadFreezeRecord(sessionId: string): Promise<FreezeRecord | null> {
    return this.read<FreezeRecord>('freeze', sessionId);
  }

  async saveAmendment(record: ProposedAmendment): Promise<void> {
    this.write('amendment', record.amendment_id, record);
  }

  async listAmendments(sessionId: string): Promise<ProposedAmendment[]> {
    return this.listByPrefix<ProposedAmendment>('amendment')
      .filter((a) => a.session_id === sessionId)
      .sort((a, b) => a.recorded_at.localeCompare(b.recorded_at) || a.amendment_id.localeCompare(b.amendment_id));
  }
}
