# Council persistence (CWE-005)

Canonical, host-neutral persistence definitions for the Council of Wise
Elders, per directive Sections 16 and 34 (unit CWE-005).

## Layout

- `migrations/0001-council-schema.sql` is the canonical schema: the 18
  `council_*` tables of Section 16.2 plus `council_kanban_links` (named in
  the CWE-005 prose block's owned paths; additive, wired later by
  CWE-021/CWE-042), their indexes, composite scope foreign keys, canonical
  enum CHECK constraints, and the two diagnostic-capture bound triggers of
  Section 16.6.
- `index.ts` loads those statements for portable-runtime hosts and exports
  the schema version id (`council-0001`), which is a schema version, not a
  host registry number.

## Host application

- Command Center applies the same statements through its migration
  registry (`src/lib/db/migrations.ts`). The registry id is allocated by
  the single integrator at integration time only; this branch carries a
  clearly marked pending-allocation placeholder. The Command Center copy
  of the statements lives in `src/lib/council/persistence/` and must stay
  statement-identical to the SQL here.
- Any host applies the statements in order, in one transaction, and
  records the application in its own ledger. Re-applying is a no-op
  (IF NOT EXISTS throughout).

## Safety properties

- Additive only: no existing table is altered or dropped, so the DATA-01
  additive self-heal mode may apply this migration, and rollback is to
  keep the tables and run the previous build (no destructive downgrade).
- Scope is structural: every session-dependent table carries tenant,
  company, and session columns with composite foreign keys to
  `council_sessions (tenant_id, company_id, id)`. A globally unique UUID
  is never authorization (Section 16.2).
- Diagnostic capture (Section 16.6): grant rows record the CWE-003
  `DiagnosticRetentionPolicy` authorization for one named session; payload
  rows are redacted, protected-store references only, bounded by CHECK
  constraints and triggers (window at most 4 hours, TTL at most 72 hours,
  at most 5 MiB per operation, at most 25 MiB per session); metadata rows
  are the fallback when redaction or the protected store is unavailable
  and can never carry a payload reference. Never-captured data classes
  (hidden reasoning, tokens, cookies, auth headers, private keys) are
  rejected by a CHECK constraint in every mode.
