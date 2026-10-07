# tests/resume-repair-evidence — W4-03-U1

Selective repair + resume + cost proof. Stdlib only; every check runs against
the live core modules in this tree (`core/intake_preflight/`,
`core/spend_ledger.py`, `core/state_store.py`, `core/job_recovery.py`,
`core/retake_manager/`, `core/music_director/`). No network, no paid
dispatch, no provider calls, no writes outside this folder (plus per-test
scratch under `/tmp/lane-W4-03-U1-*`, removed by each test).

## Run

```sh
bash run_resume_repair.sh        # table + non-zero exit on any failure
python3 test_resume_digest.py    # family A alone
python3 test_repair_budget.py    # family B alone
python3 test_unknown_reconcile.py  # family C alone
```

## Families and acceptance coverage

| Test | Acceptance clause it proves |
|---|---|
| `test_resume_digest.py` | **Resume produces identical digest** — park mid-run (ledger `runs.status=parked` rc 4 + state stage `PARKED`), spend blocked `RUN_PARKED` rc 5, write `evidence/PARKED.json`, unpark, `intake --resume-file` returns `resume-no-changes` with the pre-park digest three ways (file `digest` == `state_version.expected` == `state_version.current`). Negative control: approval-affecting brief change parks resume (`resume-approval-invalidated`, digest differs), so the identity check is not vacuous. |
| `test_repair_budget.py` | **repair <= repair_cap** — run with `--repair-cap 1` grants exactly one retry then rejects attempt 3 (`REPAIR_CAP` rc 5) and refuses retrying a non-failed attempt (`RETRY_NOT_FAILED` rc 5); default cap 2 run grants two and rejects the third (cap is read from the run row, not hardcoded); `retake_manager` parks the next retake past the profile/default cap (`REPAIR_CAP_EXHAUSTED` rc 4) with counters from durable history; `music_director.plan_repair(cap=1)` extends one section and parks the rest. |
| `test_unknown_reconcile.py` | **unknown reconcile evidence** — `recover()` plan: no remote id `BLOCKED`/`NO_REMOTE_ID` ("never auto-resubmit"), unknown + remote id `RECONCILE`/`UNCERTAIN_ACCEPTANCE`, remote-tracked `POLL`/`REMOTE_TRACKED`; read-only proof (main DB sha/size/mtime unchanged, WAL empty, no job row changed); re-plan of the active unknown key rejected `DUPLICATE_LOGICAL_JOB`; callbacks never create jobs (`NO_SUCH_JOB`); provider event applies once (`DUPLICATE_EVENT`, `STALE_SEQ`, `TASK_MISMATCH`); receipts written before reconcile and sum to summary `actual_cost`; unknown price parks before dispatch (`UNKNOWN_PRICE` rc 4) and stays blocked until unpark. |

Cost proof runs in every family: `summary` totals (actual + committed +
unknown_or_reserved + qc allowance) never exceed the ceiling (5000
USD-cents), `remaining_budget >= 0`.

## PARKED.json is a projection, not an authority

This tree has no `PARKED.json` writer or reader (see
`docs/operating-and-recovery/OPERATOR-RECOVERY.md`): the parked record is
`runs.status='parked'` and the stage row in `PARKED` with a reason. The
`evidence/PARKED.json` written by family A is an explicit projection of those
ledgers that also carries the intake resume contract fields (`digest`,
`summary`, `outstanding`, `next_stage`) so `factory.py intake --resume-file`
can consume it. It says so on its own face (`"projection": true`).

## Evidence and verdict ownership

Each test writes `evidence/<family>.json` (schema
`blackceo.resume-repair-evidence/v1`) with every named check, its result, and
the recorded digests/costs. These are test results, **not** a unit verdict:
`evidence/W4-03/W4-03-U1.verdict.json` belongs to the independent judge; this
unit never writes it (no self-approval).

The build root is not a git repository, so there is no commit to attach here;
the folder itself is the artifact.

## Hygiene

- Scratch: `/tmp/lane-W4-03-U1-*` only, created and removed per test.
- Lane logs: `swarm-plans/lanes/W4-03-U1-lane/`.
- Reads nothing outside this folder and `core/`.
