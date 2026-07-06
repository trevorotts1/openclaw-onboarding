/**
 * Podcast Production Engine dashboard: database access.
 *
 * READ-ONLY BY CONSTRUCTION (design D3 / Section 5.5, acceptance criterion 1):
 * the engine's writer module (podcast_state.py) is the ONLY code that creates
 * the schema or writes episode data. This module opens podcast-engine.db with
 * better-sqlite3 { readonly: true, fileMustExist: true } for every episode
 * query. There is exactly ONE narrow read-write handle, used exclusively by
 * the token auth layer and the operator token screen (Section 11), and it is
 * wrapped so any statement that touches an episode table, or any DDL, throws
 * before reaching SQLite.
 *
 * No schema creation, no migrations, no PRAGMA writes happen here. If the DB
 * file does not exist yet (the client has never run the engine), readers get
 * null and the UI renders the empty state, never an error (Section 8.5).
 *
 * WAL note (fleet memory: WAL mtime lags): freshness is never derived from
 * file mtime; consumers poll SELECT MAX(updated_at) FROM podcast_jobs.
 */

import Database from 'better-sqlite3';
import path from 'path';
import os from 'os';
import fs from 'fs';

/** Resolution order per design Section 3. */
export function resolvePodcastDbPath(): string {
  const explicit = process.env.PODCAST_DB_PATH;
  if (explicit && explicit.trim().length > 0) return explicit.trim();
  return path.join(os.homedir(), '.openclaw', 'podcast-engine', 'podcast-engine.db');
}

let readDb: Database.Database | null = null;
let authDb: Database.Database | null = null;

/**
 * Read-only handle over the engine's database. Returns null when the DB file
 * does not exist yet so pages can render the empty state (Section 8.5).
 */
export function getPodcastReadDb(): Database.Database | null {
  const dbPath = resolvePodcastDbPath();
  if (readDb) {
    try {
      // The handle can outlive a deleted file (churn step 10.4); re-check.
      readDb.prepare('SELECT 1').get();
      return readDb;
    } catch {
      try { readDb.close(); } catch { /* already dead */ }
      readDb = null;
    }
  }
  if (!fs.existsSync(dbPath)) return null;
  try {
    readDb = new Database(dbPath, { readonly: true, fileMustExist: true });
    return readDb;
  } catch {
    return null;
  }
}

/** Tables the auth layer may touch, and the ONLY tables it may write. */
const AUTH_WRITABLE_TABLES = ['podcast_dashboard_tokens', 'podcast_client_state'];
const EPISODE_TABLES = ['podcast_jobs', 'podcast_job_events', 'podcast_job_payloads'];
const WRITE_VERBS = /^\s*(insert|update|delete|replace|create|drop|alter|vacuum|attach|pragma)\b/i;

export class PodcastDbWriteError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PodcastDbWriteError';
  }
}

function assertAuthStatementAllowed(sql: string): void {
  const lowered = sql.toLowerCase();
  const isWrite = WRITE_VERBS.test(lowered);
  if (!isWrite) return; // reads are fine on either handle
  for (const table of EPISODE_TABLES) {
    if (lowered.includes(table)) {
      throw new PodcastDbWriteError(
        `Refusing to write episode table via the dashboard (${table}). ` +
          'podcast_state.py is the sole writer of episode data.'
      );
    }
  }
  const touchesAllowed = AUTH_WRITABLE_TABLES.some((t) => lowered.includes(t));
  if (!touchesAllowed) {
    throw new PodcastDbWriteError(
      'Dashboard writes are restricted to podcast_dashboard_tokens and podcast_client_state.'
    );
  }
  if (/^\s*(create|drop|alter|vacuum|attach|pragma)\b/i.test(lowered)) {
    throw new PodcastDbWriteError('Schema statements are owned by podcast_state.py, not the dashboard.');
  }
}

/**
 * The ONE permitted read-write handle (design Section 5.5 exception): token
 * mint, revoke, and last_used_at touches only. Its prepare() is guarded so a
 * future edit cannot quietly widen the write surface. Returns null when the
 * DB file does not exist (the engine has never initialized this box).
 */
export function getPodcastAuthDb(): Database.Database | null {
  const dbPath = resolvePodcastDbPath();
  if (authDb) {
    try {
      authDb.prepare('SELECT 1').get();
      return authDb;
    } catch {
      try { authDb.close(); } catch { /* already dead */ }
      authDb = null;
    }
  }
  if (!fs.existsSync(dbPath)) return null;
  try {
    const raw = new Database(dbPath, { fileMustExist: true });
    raw.pragma('busy_timeout = 5000');
    const originalPrepare = raw.prepare.bind(raw);
    // Guard every statement compiled on this handle.
    (raw as unknown as { prepare: (sql: string) => unknown }).prepare = (sql: string) => {
      assertAuthStatementAllowed(sql);
      return originalPrepare(sql);
    };
    const originalExec = raw.exec.bind(raw);
    (raw as unknown as { exec: (sql: string) => unknown }).exec = (sql: string) => {
      assertAuthStatementAllowed(sql);
      return originalExec(sql);
    };
    authDb = raw;
    return authDb;
  } catch {
    return null;
  }
}

/**
 * The box's own client id. Physical isolation means one client per box, and
 * every dashboard query is still parameterized by this id (design 10.1.2)
 * so even a mis-copied database cannot leak another client's rows.
 *
 * Resolution: PODCAST_CLIENT_ID env override, else the engine-registered row
 * in podcast_client_state, else the sole distinct client_id in podcast_jobs.
 */
export function resolvePodcastClientId(db: Database.Database | null): string | null {
  const explicit = process.env.PODCAST_CLIENT_ID;
  if (explicit && explicit.trim().length > 0) return explicit.trim();
  if (!db) return null;
  try {
    const state = db
      .prepare('SELECT client_id FROM podcast_client_state ORDER BY client_id LIMIT 1')
      .get() as { client_id: string } | undefined;
    if (state?.client_id) return state.client_id;
    const job = db
      .prepare('SELECT client_id FROM podcast_jobs ORDER BY created_at ASC LIMIT 1')
      .get() as { client_id: string } | undefined;
    return job?.client_id ?? null;
  } catch {
    return null;
  }
}

/** Cheap freshness probe for polling clients; never uses file mtime. */
export function getLastUpdatedAt(db: Database.Database, clientId: string): string | null {
  const row = db
    .prepare('SELECT MAX(updated_at) AS last FROM podcast_jobs WHERE client_id = ?')
    .get(clientId) as { last: string | null } | undefined;
  return row?.last ?? null;
}

/** Is this client active (kill-switch application blade, Section 11.4)? */
export function isClientActive(db: Database.Database, clientId: string): boolean {
  try {
    const row = db
      .prepare('SELECT active FROM podcast_client_state WHERE client_id = ?')
      .get(clientId) as { active: number } | undefined;
    // No row means the engine never deactivated this client; treat as active
    // (the engine writes the row on provision or on deactivation).
    if (!row) return true;
    return row.active === 1;
  } catch {
    // Fail closed on any read error.
    return false;
  }
}
