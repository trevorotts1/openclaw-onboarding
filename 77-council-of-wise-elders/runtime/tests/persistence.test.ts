/**
 * CWE-005 canonical persistence tests (directive Section 16).
 *
 * The canonical schema in src/persistence is exercised against a real
 * SQLite database (node:sqlite, the same driver family CWE-004's local
 * store uses). Command Center applies the identical statements through
 * its registry; its own suite proves the host lifecycle. Here we prove
 * the canonical definition itself: full inventory, idempotent apply,
 * composite scope enforcement, and the diagnostic bounds of Section
 * 16.6.
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

import {
  COUNCIL_SCHEMA_SQL,
  COUNCIL_SCHEMA_MIGRATION_ID,
  COUNCIL_TABLES_PROSE_BLOCK_EXTRA,
  COUNCIL_TABLES_SECTION_16_2,
} from '../src/persistence/index.js';

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
const { DatabaseSync } = requireFn('node:sqlite') as {
  DatabaseSync: new (path: string) => SqliteDatabase;
};

const NOW = '2026-10-14T12:00:00.000Z';
const ALL_TABLES = [...COUNCIL_TABLES_SECTION_16_2, ...COUNCIL_TABLES_PROSE_BLOCK_EXTRA];

function freshDb(): SqliteDatabase {
  const db = new DatabaseSync(':memory:');
  db.exec('PRAGMA foreign_keys = ON');
  return db;
}

function councilTables(db: SqliteDatabase): string[] {
  return (
    db
      .prepare(`SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'council%'`)
      .all() as { name: string }[]
  ).map((r) => r.name);
}

test('canonical schema applies fully and is idempotent', () => {
  assert.equal(COUNCIL_SCHEMA_MIGRATION_ID, 'council-0001');
  assert.equal(COUNCIL_TABLES_SECTION_16_2.length, 18);
  const db = freshDb();
  db.exec(COUNCIL_SCHEMA_SQL);
  assert.deepEqual(councilTables(db).sort(), [...ALL_TABLES].sort());
  db.exec(COUNCIL_SCHEMA_SQL);
  assert.deepEqual(councilTables(db).sort(), [...ALL_TABLES].sort());
  const triggers = (
    db.prepare(`SELECT name FROM sqlite_master WHERE type='trigger'`).all() as { name: string }[]
  ).map((r) => r.name);
  assert.deepEqual(triggers.sort(), [
    'trg_council_diag_payload_bounds',
    'trg_council_diag_payload_window',
  ]);
  db.close();
});

test('composite scope foreign keys reject cross-scope children', () => {
  const db = freshDb();
  db.exec(COUNCIL_SCHEMA_SQL);
  db.prepare(
    `INSERT INTO council_sessions
       (id, tenant_id, company_id, installation_id, owner_subject, created_by_subject,
        mode, visibility, state, created_at, updated_at)
     VALUES ('s1', 't1', 'co1', 'i1', 'owner-1', 'owner-1', 'full', 'private', 'DRAFT', ?, ?)`,
  ).run(NOW, NOW);
  assert.throws(
    () =>
      db
        .prepare(
          `INSERT INTO council_brief_revisions
             (tenant_id, company_id, session_id, revision, brief_json, canonical_hash, question,
              decision_type, stakes, reversibility, success_criteria_json, constraints_json,
              author_subject, created_at)
           VALUES ('t1', 'co-OTHER', 's1', 1, '{}', 'h', 'q', 'd', 's', 'rev', '[]', '[]', 'a', ?)`,
        )
        .run(NOW),
    /FOREIGN KEY/,
  );
  db.close();
});

test('diagnostic capture bounds hold in the canonical schema (Section 16.6)', () => {
  const db = freshDb();
  db.exec(COUNCIL_SCHEMA_SQL);
  db.prepare(
    `INSERT INTO council_sessions
       (id, tenant_id, company_id, installation_id, owner_subject, created_by_subject,
        mode, visibility, state, created_at, updated_at)
     VALUES ('s1', 't1', 'co1', 'i1', 'owner-1', 'owner-1', 'full', 'private', 'DRAFT', ?, ?)`,
  ).run(NOW, NOW);
  db.prepare(
    `INSERT INTO council_diagnostic_capture
       (tenant_id, company_id, session_id, id, record_kind, authorized_by_principal,
        authorization_kind, window_started_at, window_ends_at, capture_window_minutes,
        payload_ttl_hours, max_bytes_per_operation, max_bytes_per_session, created_at)
     VALUES ('t1', 'co1', 's1', 'g1', 'grant', 'owner-1', 'owner',
             '2026-10-14T12:00:00.000Z', '2026-10-14T13:00:00.000Z', 60, 24, 1000, 1500, ?)`,
  ).run(NOW);
  const payload = db.prepare(
    `INSERT INTO council_diagnostic_capture
       (tenant_id, company_id, session_id, id, record_kind, grant_id, operation_id, data_class,
        byte_count, redaction_status, payload_protected_ref, payload_deadline_at, captured_at, created_at)
     VALUES ('t1', 'co1', 's1', ?, 'payload', 'g1', 'op-1', 'provider_body', ?, 'redacted',
             'protected-store:ref', '2026-10-15T12:30:00.000Z', '2026-10-14T12:30:00.000Z', ?)`,
  );
  payload.run('p1', 900, NOW);
  assert.throws(() => payload.run('p2', 1001, NOW), /per-operation bound/);
  assert.throws(
    () =>
      db
        .prepare(
          `INSERT INTO council_diagnostic_capture
             (tenant_id, company_id, session_id, id, record_kind, grant_id, operation_id, data_class,
              byte_count, redaction_status, payload_protected_ref, payload_deadline_at, captured_at, created_at)
           VALUES ('t1', 'co1', 's1', 'p3', 'payload', 'g1', 'op-1', 'access_token', 10, 'redacted',
                   'protected-store:ref', '2026-10-15T12:30:00.000Z', '2026-10-14T12:30:00.000Z', ?)`,
        )
        .run(NOW),
    /CHECK constraint/,
  );
  db.close();
});
