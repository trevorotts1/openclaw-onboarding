/**
 * Canonical council persistence migrations (CWE-005, directive Section 16).
 *
 * This module is the single canonical definition of the council_* schema.
 * Hosts apply these statements through their own migration machinery:
 * - Command Center: the registry entry in src/lib/db/migrations.ts whose
 *   statements live in src/lib/council/persistence/council-schema.ts (a
 *   generated copy of the SQL below; a unit test asserts the two copies
 *   agree statement for statement).
 * - Portable runtime hosts: apply `COUNCIL_SCHEMA_SQL` with one exec
 *   call inside one transaction, recording the migration id in the
 *   host's own applied-migrations ledger.
 *
 * The migration id used here ('council-0001') is the canonical SCHEMA
 * version, not a host registry number. Command Center allocates its
 * numeric registry id only at integration time (see the CWE-005 build
 * report); no host registry number is ever allocated inside a unit branch.
 *
 * Everything is additive (IF NOT EXISTS throughout): applying twice is a
 * no-op, the DATA-01 additive self-heal path may apply it, and rollback is
 * "keep the tables, run the previous build" (Section 16.3: the previous
 * schema remains readable; nothing here alters or drops existing tables).
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export const COUNCIL_SCHEMA_MIGRATION_ID = 'council-0001';
export const COUNCIL_SCHEMA_MIGRATION_NAME = 'council_scoped_storage_schema';

/** The 18 tables of directive Section 16.2, in creation order. */
export const COUNCIL_TABLES_SECTION_16_2 = [
  'council_sessions',
  'council_brief_revisions',
  'council_evidence',
  'council_cards',
  'council_challenges',
  'council_verdicts',
  'council_events',
  'council_jobs',
  'council_provider_attempts',
  'council_budget_reservations',
  'council_action_proposals',
  'council_approvals',
  'council_run_previews',
  'council_diagnostic_capture',
  'council_task_links',
  'council_outcome_reviews',
  'council_request_keys',
  'council_projection_outbox',
] as const;

/**
 * One extra table from the CWE-005 prose block's owned-paths list
 * (council_kanban_links). It is additive and unused until CWE-021/CWE-042
 * wire the board projection; it is not part of the Section 16.2 inventory.
 */
export const COUNCIL_TABLES_PROSE_BLOCK_EXTRA = ['council_kanban_links'] as const;

function loadSchemaSql(): string {
  const sqlPath = fileURLToPath(new URL('./migrations/0001-council-schema.sql', import.meta.url));
  return readFileSync(sqlPath, 'utf8');
}

/**
 * The canonical schema script, comments included. Hosts apply it with a
 * single exec call inside one transaction; it is never split naively,
 * because trigger bodies contain semicolons.
 */
export const COUNCIL_SCHEMA_SQL: string = loadSchemaSql();
