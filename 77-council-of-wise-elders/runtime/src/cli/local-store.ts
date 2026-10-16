/**
 * Standalone local store (CWE-004 foundation): a SQLite implementation of
 * the CouncilStore port for the standalone adapter (directive Sections
 * 5.3 and 16.1). The database lives in the per-user data directory,
 * never inside the skill folder, so skill updates that replace the
 * folder wholesale cannot sweep client history away.
 *
 * This is the standalone adapter's local schema
 * (`wise-elders.local-store/v1`). The canonical migration set and the
 * full repository layer (event journal, outbox, archival reads) are
 * CWE-005 and CWE-006; nothing here pretends to be them. In managed
 * mode the Command Center adapter supplies its existing database
 * through the same port instead.
 *
 * Rules enforced here: validated cards are unique per logical operation
 * (session, round, seat, input hash); events receive a monotonically
 * increasing per-session sequence inside one short transaction; state
 * writes are compare-and-swap on state_version so a stale worker cannot
 * overwrite a newer record; no provider call ever happens inside these
 * transactions.
 */

import { createRequire } from 'node:module';
import { join } from 'node:path';
import type {
  CouncilCard,
  CouncilEvent,
  JobCheckpoint,
  SeatId,
  SessionStateRecord,
  Verdict,
} from '../contracts/index.js';
import { CouncilError } from './errors.js';
import type { CouncilStore, StoredSession } from './host-ports.js';
import { ensureDataDir } from './paths.js';

export const LOCAL_STORE_SCHEMA_VERSION = 'wise-elders.local-store/v1';

interface SqliteStatement {
  run(...params: unknown[]): { changes: number | bigint };
  get(...params: unknown[]): unknown;
  all(...params: unknown[]): unknown[];
}
interface SqliteDatabase {
  exec(sql: string): void;
  prepare(sql: string): SqliteStatement;
  close(): void;
}

const requireFn = createRequire(import.meta.url);

function loadDatabaseSync(): new (path: string) => SqliteDatabase {
  try {
    const mod = requireFn('node:sqlite') as {
      DatabaseSync: new (path: string) => SqliteDatabase;
    };
    return mod.DatabaseSync;
  } catch {
    throw new CouncilError(
      'COUNCIL_STORE_UNAVAILABLE',
      'The local council store needs the Node.js SQLite module (node:sqlite), which this Node runtime does not provide.',
      {
        retryable: false,
        action:
          'Run the council with a Node runtime that includes node:sqlite (Node 22.13+ or 24+), or use managed Command Center mode.',
        exitCode: 3,
      },
    );
  }
}

const SCHEMA_SQL = `
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  spec_json TEXT NOT NULL,
  brief_json TEXT NOT NULL,
  scope_json TEXT NOT NULL,
  sample INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS state_records (
  session_id TEXT PRIMARY KEY REFERENCES sessions(session_id),
  record_json TEXT NOT NULL,
  state_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cards (
  session_id TEXT NOT NULL,
  round INTEGER NOT NULL,
  seat_id TEXT NOT NULL,
  input_sha256 TEXT NOT NULL,
  card_json TEXT NOT NULL,
  PRIMARY KEY (session_id, round, seat_id, input_sha256)
);
CREATE TABLE IF NOT EXISTS events (
  session_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  event_json TEXT NOT NULL,
  PRIMARY KEY (session_id, sequence)
);
CREATE TABLE IF NOT EXISTS verdicts (
  session_id TEXT PRIMARY KEY,
  verdict_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkpoints (
  session_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  seat_key TEXT NOT NULL,
  input_sha256 TEXT NOT NULL,
  checkpoint_json TEXT NOT NULL,
  PRIMARY KEY (session_id, phase, seat_key, input_sha256)
);
`;

export class LocalSqliteStore implements CouncilStore {
  private readonly db: SqliteDatabase;

  constructor(dataDir: string) {
    ensureDataDir(dataDir);
    const DatabaseSync = loadDatabaseSync();
    this.db = new DatabaseSync(join(dataDir, 'council.db'));
    this.db.exec('PRAGMA journal_mode = WAL;');
    this.db.exec('PRAGMA foreign_keys = ON;');
    this.db.exec(SCHEMA_SQL);
    this.db
      .prepare('INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)')
      .run('schema_version', LOCAL_STORE_SCHEMA_VERSION);
  }

  close(): void {
    this.db.close();
  }

  private transaction<T>(fn: () => T): T {
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const out = fn();
      this.db.exec('COMMIT');
      return out;
    } catch (err) {
      this.db.exec('ROLLBACK');
      throw err;
    }
  }

  async createSession(session: StoredSession): Promise<void> {
    this.transaction(() => {
      this.db
        .prepare(
          'INSERT INTO sessions (session_id, spec_json, brief_json, scope_json, sample) VALUES (?, ?, ?, ?, ?)',
        )
        .run(
          session.spec.session_id,
          JSON.stringify(session.spec),
          JSON.stringify(session.brief),
          JSON.stringify(session.scope),
          session.sample ? 1 : 0,
        );
      this.db
        .prepare(
          'INSERT INTO state_records (session_id, record_json, state_version) VALUES (?, ?, ?)',
        )
        .run(
          session.spec.session_id,
          JSON.stringify(session.state),
          session.state.state_version,
        );
    });
  }

  async getSession(sessionId: string): Promise<StoredSession | null> {
    const row = this.db
      .prepare(
        'SELECT s.spec_json, s.brief_json, s.scope_json, s.sample, r.record_json FROM sessions s JOIN state_records r ON r.session_id = s.session_id WHERE s.session_id = ?',
      )
      .get(sessionId) as
      | {
          spec_json: string;
          brief_json: string;
          scope_json: string;
          sample: number;
          record_json: string;
        }
      | undefined;
    if (!row) return null;
    return {
      spec: JSON.parse(row.spec_json) as StoredSession['spec'],
      brief: JSON.parse(row.brief_json) as StoredSession['brief'],
      scope: JSON.parse(row.scope_json) as StoredSession['scope'],
      state: JSON.parse(row.record_json) as SessionStateRecord,
      sample: row.sample === 1,
    };
  }

  async updateState(
    record: SessionStateRecord,
    expectedVersion: number,
  ): Promise<void> {
    const result = this.db
      .prepare(
        'UPDATE state_records SET record_json = ?, state_version = ? WHERE session_id = ? AND state_version = ?',
      )
      .run(
        JSON.stringify(record),
        record.state_version,
        record.session_id,
        expectedVersion,
      );
    if (Number(result.changes) !== 1) {
      throw new CouncilError(
        'COUNCIL_STATE_CONFLICT',
        `Session ${record.session_id} changed underneath this writer (expected state version ${expectedVersion}).`,
        {
          retryable: true,
          action: 'Reload the session state and retry from the current version.',
          exitCode: 3,
        },
      );
    }
  }

  async saveCard(card: CouncilCard): Promise<void> {
    const round =
      card.card_kind === 'ratification' ? 3 : card.card_kind === 'consult' ? 0 : card.round;
    this.db
      .prepare(
        'INSERT INTO cards (session_id, round, seat_id, input_sha256, card_json) VALUES (?, ?, ?, ?, ?)',
      )
      .run(
        card.session_id,
        round,
        card.seat_id,
        card.input_manifest_sha256,
        JSON.stringify(card),
      );
  }

  async findCard(
    sessionId: string,
    round: number,
    seatId: SeatId,
    inputSha256: string,
  ): Promise<CouncilCard | null> {
    const row = this.db
      .prepare(
        'SELECT card_json FROM cards WHERE session_id = ? AND round = ? AND seat_id = ? AND input_sha256 = ?',
      )
      .get(sessionId, round, seatId, inputSha256) as { card_json: string } | undefined;
    return row ? (JSON.parse(row.card_json) as CouncilCard) : null;
  }

  async listCards(sessionId: string): Promise<CouncilCard[]> {
    const rows = this.db
      .prepare(
        'SELECT card_json FROM cards WHERE session_id = ? ORDER BY round, seat_id',
      )
      .all(sessionId) as Array<{ card_json: string }>;
    return rows.map((r) => JSON.parse(r.card_json) as CouncilCard);
  }

  async appendEvent(
    event: Omit<CouncilEvent, 'sequence'>,
  ): Promise<CouncilEvent> {
    return this.transaction(() => {
      const row = this.db
        .prepare(
          'SELECT COALESCE(MAX(sequence), 0) AS max_seq FROM events WHERE session_id = ?',
        )
        .get(event.session_id) as { max_seq: number };
      const sequence = row.max_seq + 1;
      const full: CouncilEvent = { ...event, sequence };
      this.db
        .prepare(
          'INSERT INTO events (session_id, sequence, event_json) VALUES (?, ?, ?)',
        )
        .run(event.session_id, sequence, JSON.stringify(full));
      return full;
    });
  }

  async listEvents(
    sessionId: string,
    afterSequence = 0,
  ): Promise<CouncilEvent[]> {
    const rows = this.db
      .prepare(
        'SELECT event_json FROM events WHERE session_id = ? AND sequence > ? ORDER BY sequence',
      )
      .all(sessionId, afterSequence) as Array<{ event_json: string }>;
    return rows.map((r) => JSON.parse(r.event_json) as CouncilEvent);
  }

  async saveVerdict(verdict: Verdict): Promise<void> {
    this.db
      .prepare(
        'INSERT OR REPLACE INTO verdicts (session_id, verdict_json) VALUES (?, ?)',
      )
      .run(verdict.session_id, JSON.stringify(verdict));
  }

  async getVerdict(sessionId: string): Promise<Verdict | null> {
    const row = this.db
      .prepare('SELECT verdict_json FROM verdicts WHERE session_id = ?')
      .get(sessionId) as { verdict_json: string } | undefined;
    return row ? (JSON.parse(row.verdict_json) as Verdict) : null;
  }

  async saveCheckpoint(checkpoint: JobCheckpoint): Promise<void> {
    this.db
      .prepare(
        'INSERT OR REPLACE INTO checkpoints (session_id, phase, seat_key, input_sha256, checkpoint_json) VALUES (?, ?, ?, ?, ?)',
      )
      .run(
        checkpoint.session_id,
        checkpoint.phase,
        checkpoint.seat_id ?? '',
        checkpoint.input_sha256,
        JSON.stringify(checkpoint),
      );
  }

  async getCheckpoint(
    sessionId: string,
    phase: string,
    seatId: SeatId | null,
    inputSha256: string,
  ): Promise<JobCheckpoint | null> {
    const row = this.db
      .prepare(
        'SELECT checkpoint_json FROM checkpoints WHERE session_id = ? AND phase = ? AND seat_key = ? AND input_sha256 = ?',
      )
      .get(sessionId, phase, seatId ?? '', inputSha256) as
      | { checkpoint_json: string }
      | undefined;
    return row ? (JSON.parse(row.checkpoint_json) as JobCheckpoint) : null;
  }
}
