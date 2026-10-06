# Operator recovery — park/resume, unknown reconcile, escalation

Implemented behavior only. Modules: `core/spend_ledger.py` (spend authority),
`core/job_recovery.py` (verified recovery), `core/state_store.py` (stage
authority), `core/cc_sync.py` (board contract). Spend-ledger exit codes: ok 0,
waiting 3, parked 4, rejected 5, error 1.

## Where run state lives

- Build ledger: `<build-root>/run/` holds
  `state.json` (schema `blackceo.drama-song-factory.state/v1`,
  `build_started_unix` = T0). This is build-orchestration state, not campaign
  spend authority.
- Campaign spend authority: one per-run SQLite ledger DB (`spend_ledger.py`;
  path passed via `--db`, no fixed path committed). Tables: `runs` (`run_id`,
  ceiling, currency, qc_allowance, repair_cap, status `active`|`parked`,
  version); `jobs` (states `planned`→`reserved`→`submitted`→`succeeded`|`failed`→
  `reconciled`, plus `unknown` retaining the reservation; request digest,
  logical key, attempt id, remote task id, estimated/actual cost, owner lease,
  version); `receipts` (written before reconcile, same transaction); `events`
  (`UNIQUE` on provider event id = dedupe); `results` (artifact path/sha/bytes).
  Money is integer minor units. JSON manifests are projections, never authorities.
- Stage authority: `state_store.py` SQLite (caller-chosen path). States
  `NOT_STARTED READY RUNNING WAITING_PROVIDER WAITING_APPROVAL QC
  FAILED_RETRYABLE FAILED_BLOCKED PARKED COMPLETE STALE`; version-predicated
  compare-and-set writes; worker leases (default 300 s); `PARKED` and
  `FAILED_BLOCKED` require a reason; `PARKED`→`READY` only; owner/lease cleared
  on `PARKED`.
- `PARKED.json`: NOT IMPLEMENTED — no writer or reader anywhere in this tree
  (only the directive §18 names it, alongside `run-state.json`, `receipts/`,
  `checkpoints/`). The parked record is `runs.status='parked'` (+version,
  updated_at) and/or stage rows in `PARKED` with reason. Query the ledgers; do
  not invent a `PARKED.json` reader.

## Park/resume procedure

1. Park: `spend_ledger.py --db DB park_run --run R --reason REASON` → outcome
   `parked` (rc 4), `next_action` "resume from last incomplete stage". Automatic
   parks: `reserve` on `BUDGET_EXCEEDED` / `UNKNOWN_PRICE`; `reconcile` when
   settled charges push remaining budget negative. Budget violation parks the
   run instead of continuing.
2. While parked: every mutation except `unpark` is rejected `RUN_PARKED`
   ("reconcile or operator unpark"); `can_spend` rejects `RUN_PARKED`.
   Verified live: `park_run` → parked rc 4; `can_spend` while parked →
   rejected/`RUN_PARKED` rc 5; `unpark` → ok rc 0.
3. Diagnose: `summary` (estimated / committed / actual / unknown_or_reserved /
   qc_and_repair_allowance / provider_cost_by_stage / generation calls /
   retry_cost / remaining_budget / run_status). Then `job_recovery.py --db DB
   recover --run R` — read-only plan, provably writes nothing (opens `mode=ro`):
   job with no remote task id → `BLOCKED` / `NO_REMOTE_ID` (crash-before-dispatch
   vs crash-after-accept are indistinguishable locally → never auto-resubmit);
   `unknown` with remote id → `RECONCILE`; remote-tracked → `POLL`.
   Verified live: unknown job, no remote id → `BLOCKED`/`NO_REMOTE_ID`,
   "never auto-resubmit", rc 0.
4. Reconcile unknown submissions: `ingest_event` applies one verified provider
   event — callbacks never create jobs (unknown run/request/task/attempt →
   `NO_SUCH_JOB`); idempotent on `provider_event_id` (`DUPLICATE_EVENT`);
   older `provider_seq` recorded-not-applied (`STALE_SEQ`); task-id mismatch
   rejected (`TASK_MISMATCH`); terminal events only from
   `planned/reserved/submitted/unknown`. `record_result` persists a downloaded
   artifact against an existing job. `mark_terminal` then `reconcile` (receipt
   written first, same transaction). Acceptance undeterminable → park.
   `cancel` moves active jobs to `unknown` and preserves receipts; remote work
   reconciles later.
5. Resume: `unpark --db DB --run R` → `active`; resume from the last incomplete
   stage per the recover plan. Never resubmit an accepted, successful, or
   uncertain submission — poll the existing remote task id. Corrupt or
   incompatible DB stops spending (`CORRUPT_STATE` / `INCOMPATIBLE_STATE`,
   "verified recovery required") and never becomes a fresh empty run.

## Unknown-submission reconcile (rule)

Polling an existing job is distinct from resubmitting it. Before remote task
ids exist, recovery only BLOCKS. Retry only known failed artifacts within the
approved repair cap (`RETRY_NOT_FAILED`, `REPAIR_CAP`); a timeout during paid
submission is not proof the provider rejected it. Reconcile via supported
provider records or operator evidence; if acceptance cannot be determined, park.

## Escalation path

- Unknown price → operator decision before dispatch (`UNKNOWN_PRICE` blocks).
- Approval-affecting brief change → intake returns `parked` /
  `resume-approval-invalidated` → re-approve scope before paid work.
- Board: `cc_sync.py` stage route; `blocked` cards require `blocked_reason` plus
  a non-empty `ask` (server mirror), reserved to human-only / Master
  Orchestrator authority; media `PARKED` reasons stay in execution metadata and
  are never mapped to task `blocked`. The `return-to-orchestrator` handback has
  no local client (explicitly out of scope) — escalate through the Command
  Center contract, not around it.
- Corrupt state → spending stopped, verified recovery; cancellation preserves
  receipts and reconciles remote work afterwards.
