/**
 * SQLite handle and transaction discipline for the council persistence
 * layer (CWE-006, directive Sections 16.3 and 16.4).
 *
 * The portable runtime uses the Node.js built-in SQLite module
 * (node:sqlite), the same access pattern as the CWE-004 local store; no
 * new native dependency is introduced. Command Center supplies its own
 * better-sqlite3 handle through getDb() instead (managed mode); this
 * module serves the standalone store and the repository tests.
 *
 * Transaction law (Section 16.4):
 * - State, card, event, and outbox writes that belong together commit in
 *   ONE short transaction. A failure anywhere rolls back everywhere: a
 *   crash between operations cannot produce a half-committed result.
 * - No provider call, process spawn, render, or notification ever runs
 *   inside these transactions; the transaction callback is synchronous
 *   database work only, and the fence (lease, cancellation generation,
 *   state version) is rechecked inside the transaction immediately
 *   before commit.
 * - Locking uses a BOUNDED busy policy: SQLite's own busy timeout per
 *   attempt plus a bounded number of attempts with backoff. Exhausting
 *   the budget raises PersistenceDeferredError (test T056): the write is
 *   visibly deferred, never silently dropped and never half-applied.
 */

import { createRequire } from 'node:module';
import { PersistenceDeferredError, PersistenceError } from './errors.js';

export interface SqliteStatement {
  run(...params: unknown[]): { changes: number | bigint; lastInsertRowid: number | bigint };
  get(...params: unknown[]): unknown;
  all(...params: unknown[]): unknown[];
}

export interface SqliteDatabaseHandle {
  exec(sql: string): void;
  prepare(sql: string): SqliteStatement;
  close(): void;
}

const requireFn = createRequire(import.meta.url);

function loadDatabaseSync(): new (path: string) => SqliteDatabaseHandle {
  try {
    const mod = requireFn('node:sqlite') as {
      DatabaseSync: new (path: string) => SqliteDatabaseHandle;
    };
    return mod.DatabaseSync;
  } catch {
    throw new PersistenceError(
      'PERSISTENCE_SCHEMA_UNAVAILABLE',
      'The council store needs the Node.js SQLite module (node:sqlite), which this Node runtime does not provide.',
      {
        retryable: false,
        action:
          'Run the council with a Node runtime that includes node:sqlite (Node 22.13+ or 24+), or use managed Command Center mode.',
      },
    );
  }
}

/** True when an error is SQLite reporting a locked database. */
export function isBusyError(err: unknown): boolean {
  if (typeof err !== 'object' || err === null) return false;
  const e = err as { code?: unknown; errcode?: unknown; message?: unknown };
  if (e.errcode === 5 || e.errcode === 6) return true; // SQLITE_BUSY / SQLITE_LOCKED
  if (typeof e.message === 'string') {
    return /database is locked|database table is locked|SQLITE_BUSY/i.test(e.message);
  }
  return false;
}

function sleepSync(ms: number): void {
  if (ms <= 0) return;
  const buffer = new SharedArrayBuffer(4);
  Atomics.wait(new Int32Array(buffer), 0, 0, ms);
}

export interface BusyPolicy {
  /** Per-attempt SQLite busy timeout in milliseconds (PRAGMA busy_timeout). */
  busyTimeoutMs: number;
  /** Maximum total attempts for one logical write, including the first. */
  busyMaxAttempts: number;
  /** Base backoff between attempts; doubles each retry, capped at 500 ms. */
  busyBaseDelayMs: number;
}

/**
 * A council database: one handle plus the transaction and busy-policy
 * discipline every repository write goes through. Repositories never
 * touch the raw handle's exec for writes outside `write()`/`read()`.
 */
export class CouncilDatabase {
  readonly handle: SqliteDatabaseHandle;
  private readonly busy: BusyPolicy;
  private txDepth = 0;

  constructor(handle: SqliteDatabaseHandle, busy: BusyPolicy) {
    this.handle = handle;
    this.busy = busy;
    this.handle.exec(`PRAGMA busy_timeout = ${Math.trunc(busy.busyTimeoutMs)};`);
    this.handle.exec('PRAGMA foreign_keys = ON;');
  }

  static open(path: string, busy: BusyPolicy): CouncilDatabase {
    const DatabaseSync = loadDatabaseSync();
    const handle = new DatabaseSync(path);
    handle.exec('PRAGMA journal_mode = WAL;');
    return new CouncilDatabase(handle, busy);
  }

  /** In-memory database for tests and ephemeral compositions. */
  static openMemory(busy: BusyPolicy): CouncilDatabase {
    const DatabaseSync = loadDatabaseSync();
    return new CouncilDatabase(new DatabaseSync(':memory:'), busy);
  }

  close(): void {
    this.handle.close();
  }

  /**
   * Run synchronous read work. Reads still respect the busy policy when
   * the database is momentarily locked by another writer.
   */
  read<T>(fn: (db: SqliteDatabaseHandle) => T): T {
    return this.runBounded(() => fn(this.handle));
  }

  /**
   * Run one logical write as a single transaction under the bounded busy
   * policy. Nested calls participate in the outer transaction (the
   * journal and outbox join the caller's commit unit); only the outer
   * call opens and closes the transaction. On a busy failure the WHOLE
   * unit is rolled back and retried within the budget, so a retried
   * commit can never duplicate a card, event sequence, or outbox intent
   * that a previous attempt half-applied.
   */
  write<T>(fn: (db: SqliteDatabaseHandle) => T): T {
    if (this.txDepth > 0) {
      return fn(this.handle);
    }
    return this.runBounded(() => {
      this.handle.exec('BEGIN IMMEDIATE');
      this.txDepth = 1;
      try {
        const out = fn(this.handle);
        this.handle.exec('COMMIT');
        return out;
      } catch (err) {
        try {
          this.handle.exec('ROLLBACK');
        } catch {
          // The connection already rolled back (for example on a fatal
          // I/O error); the original error is the one that matters.
        }
        throw err;
      } finally {
        this.txDepth = 0;
      }
    });
  }

  private runBounded<T>(fn: () => T): T {
    const maxAttempts = Math.max(1, this.busy.busyMaxAttempts);
    let waitedMs = 0;
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        return fn();
      } catch (err) {
        if (!isBusyError(err) || attempt === maxAttempts) {
          if (isBusyError(err)) {
            throw new PersistenceDeferredError(attempt, waitedMs);
          }
          throw err;
        }
        const delay = Math.min(500, this.busy.busyBaseDelayMs * 2 ** (attempt - 1));
        sleepSync(delay);
        waitedMs += delay;
      }
    }
    // Unreachable: the loop always returns or throws.
    throw new PersistenceDeferredError(maxAttempts, waitedMs);
  }
}
