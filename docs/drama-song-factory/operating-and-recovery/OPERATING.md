# Operating guide — drama-song factory (implemented behavior only)

Scope: what the code does today. Every claim below names its module.
Items under NOT IMPLEMENTED have no writer/reader in this tree (verified 2026-10-06).

## 1. Control CLI — `core/intake_preflight/factory.py`

One entrypoint, two subcommands (`intake`, `preflight`). Stdlib only.
Envelope on every command: `schema_version` (`blackceo.intake-preflight/envelope/v1`),
`tool_version` (`0.1.0`), `command`, `run_id`, `outcome`, `reason_code`,
`next_action`, `evidence`, `data`, `state_version`.
Exit codes: ok 0, waiting 2, parked 3, rejected 4, error 1.
(Note: the spend-ledger CLI uses a different map — ok 0, waiting 3, parked 4,
rejected 5, error 1. See OPERATOR-RECOVERY.md.)

### `intake` — normalize brief, batch at most 3 missing essentials

Args: `--brief` / `--brief-file`, `--settings-file`, `--resume-file`, `--run-id`.

- Essentials asked (one message, max 3): offer / audience+action / spending authority.
  Placement substitutes into leftover slots only. Verified live: thin brief
  `{"offer":"demo offer"}` → `waiting` / `missing-essentials`, rc 2, exactly the
  3 questions above.
- Spending never defaulted: `budget_minor` must be int > 0 plus currency, else the
  spending question is asked. No invented ceiling, no currency conversion.
- Brief text is source material, never auth/policy: instruction-override patterns
  → `rejected` / `untrusted-injection-blocked`, auth untouched.
- Summary carries a sha256 digest (first 16 hex); `auth_status` is one of
  `missing` / `expired` / `out-of-scope` / `bound` (brief maximum alone is never
  an approval receipt — needs an explicit auth object with scope `campaign` or
  the summary digest).
- Resume: no changes → `ok` / `resume-no-changes`; approval-affecting change
  (offer/audience/action/budget) → `parked` / `resume-approval-invalidated`
  (re-approve scope); outstanding decisions → `waiting`, questionnaire not rerun.

### `preflight` — NAMES-only dependency/auth checks, never generates

Args: `--root` (approved storage root), `--storage-dir`, `--ref` (repeat),
`--require-tool` / `--require-module` (repeat), `--profile` (default
`short-9x16-30s`), `--allowed-profiles` / `--allowed-schemas` (JSON),
`--credential` (repeat, presence-only), `--auth-file`, `--summary-digest`,
`--min-free-bytes`.

Check order and reason codes (`preflight.py:check`): `schema-untrusted` (error) →
`delivery-profile-unknown` (rejected) → `reference-outside-approved-storage`
(rejected) → `reference-missing-or-truncated` (error) → `tool-unavailable` /
`module-unavailable` (error) → `storage-not-writable` / `disk-limit` (error) →
`credential-missing` (rejected) → `approval-missing` / `approval-expired` /
`approval-out-of-scope` (rejected) → `ok` / `preflight-pass`.
Resolves tools via `shutil.which`, modules via import, disk via `disk_usage`;
never executes tools, never submits generation, never logs credential values.
Verified live: no auth file → `rejected` / `approval-missing`, rc 4.

## 2. Ledger refresh — `build-control/project-bindings/refresh.sh`, 300 s

Watcher calls every 300 s. Atomically renders `LIVE-LEDGER.md` plus
the swarm-packet ledger copy (`LIVE-LEDGER.md`; temp file + `mv`, then `cp`) from
canonical `run/state.json` only — no second state authority.
Two distinct stamps: Last refresh (render time) vs Last progress (workflow-set
signature changed, kept in `.refresh-state.json`). Status `STALE` when the source
mtime is older than 600 s.
Unfinished = status in `reserved/starting/running/waiting/unknown` (same ACTIVE
set as the admission gate). Table shows unfinished count vs
`policy.max_active_workflows`, live agents vs `max_working_agents`, per-workflow
ceiling, ledger/merge intervals, repair cycles, status mix, per-workflow rows.
Live policy (`run/state.json`, schema `blackceo.drama-song-factory.state/v1`):
`max_active_workflows` 50, `max_agents_per_workflow` 10, `max_working_agents`
500, `heartbeat_seconds` 300, `merge_seconds` 1800, `repair_cycles` 2.

## 3. Admission gate — `admission_check.py`, ceiling 50

Refuses admission at >= 50 unfinished workflows (same ACTIVE set as refresh).
Exit 0 = ADMIT, 3 = REFUSE, 2 = state unreadable. Ceiling reads
`policy.max_active_workflows` (default 50). `--synthetic N` builds an in-memory
census for tests only, never writes state.
Verified live: `--synthetic 49` → `ADMIT: 49 unfinished < ceiling 50`, rc 0;
`--synthetic 50` → `REFUSE: 50 unfinished >= ceiling 50`, rc 3.

## 4. Batch windows — 1800 s, first eligibility T0+30 min

Merge cadence is `merge_seconds` = 1800 from policy: accepted work integrates in
batch-only windows every thirty minutes. First eligibility is recorded build
start T0 + 30 minutes. T0 = 1791300227 (`T0` file and `run/state.json`
`build_started_unix`), i.e. 2026-10-06T11:23:47-0400; first window 11:53:47 EDT.
Merge executor, dispatch gate, and watch tick live outside this tree
(`bindings.json` owners; 999-setup skill tooling) — cadence is pinned here, the
executors are not modified here.

## NOT IMPLEMENTED (no code in this tree as of 2026-10-06)

- `PARKED.json`, `run-state.json`, `receipts/`, `checkpoints/` as files; fixed
  `control/state.sqlite3` path (ledger/state-store DB paths are caller-chosen
  `--db` / constructor args).
- `release_check.py` (release verifier named in DEPENDENCY-MANIFEST, not built).
- A local `return-to-orchestrator` handback client (`core/cc_sync.py` marks it
  explicitly out of scope).
- Park/resume, unknown-submission reconcile, and escalation live in
  OPERATOR-RECOVERY.md — implemented in `spend_ledger.py`, `job_recovery.py`,
  `state_store.py`, not in the files named above.
