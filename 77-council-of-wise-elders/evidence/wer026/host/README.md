# WER-026 host acceptance — runnable supervisor driver (W13-U001)

Live acceptance on the operator host for the new supervisor entry point
`77-council-of-wise-elders/scripts/supervisor/runner.mjs`.

## Base

| Item | Value |
|---|---|
| Repository | `trevorotts1/openclaw-onboarding` |
| Live `origin/main` read with `git ls-remote` | `050da7fc8ab5e9886c18c6878dabcadb652edc9f` |
| Worktree base commit | `050da7fc8ab5e9886c18c6878dabcadb652edc9f` |
| Worktree | private lane `lanes/W13-U001-lane/wt` (path redacted) |
| Node | `v24.21.0` |
| Host | operator Mac Mini, Darwin 25.3.0 |

The worktree was created from the exact live `origin/main` commit. The real
checkout was not modified.

## What was built

* `scripts/supervisor/runner.mjs` (new, only source file added)
* `scripts/supervisor/runner.test.mjs` (new, only test file added)
* this evidence directory (new)

No existing supervisor module was edited. No file outside
`77-council-of-wise-elders/scripts/supervisor/{runner,runner.test}.mjs` and
`77-council-of-wise-elders/evidence/wer026/host/` was touched.

The driver wires the existing modules: `supervisor.mjs`, `policy.mjs`,
`leader-state.mjs`, `sweep-planner.mjs`, `sweep-executor.mjs`,
`sweep-runner.mjs`, `health-collector.mjs`, `health-observer.mjs`,
`incident-journal.mjs`, `restart-reconciler.mjs`, `singleton.mjs`,
`overdue-detector.mjs`. It adds no policy and no native binding:
`NATIVE_ADAPTER_BINDING` remains `UNKNOWN`.

## Acceptance command

```bash
bash 77-council-of-wise-elders/evidence/wer026/host/run-acceptance.sh
```

The script prints the raw evidence below and exits `0` on completion. Each run
uses a fresh temporary data directory under `/tmp/w13-u001-lane-wer026/`.

## Results (live, this host)

| Check | Evidence artifact | Exit code / value |
|---|---|---|
| Two real scheduled sweep ticks completed | `02-run-a-loop.log`, `03-pre-kill-state.json` | `completed_sweeps=2`, `scheduled_sweeps=2` |
| `kill -9` mid-tick | `04-run-a-exit.txt` | `137` |
| Restart reconciled the interrupted tick | `05-run-b-restart.log`, `08-restart-summary.txt` | exit `0` |
| Pending action consumed exactly once | `08-restart-summary.txt` | 1 reconciled record, 1 journal action, 1 incident |
| Restart ledger generation advanced | `08-restart-summary.txt` | `1 -> 2` (fencing `2 -> 3`) |
| Interrupted work resumed without consuming a scheduled slot | `08-restart-summary.txt` | `EXTRA`, `consumes_scheduled_slot=false` |
| Second concurrent instance refused | `10-run-c-second-instance.log`, `11-second-instance-exit.txt` | exit `3`, reason `LEASE_HELD`, `duplicate_start=true` |
| Graceful SIGTERM drains to STOPPED | `13-post-sigterm-state.json`, `14-singleton-and-stop-summary.txt`, `12-sigterm-exit.txt` | exit `0`, supervisor `STOPPED`, admission `STOPPED`, JSON valid |
| No writes outside the data dir | `01-temp-root-before.txt`, `15-temp-root-after.txt`, `16-temp-root-diff.txt`, `17-isolation-result.txt` | diff exit `0` (identical) |
| No process-spawning or network capability | `18-forbidden-api-grep.txt`, `19-forbidden-api-result.txt` | grep exit `1` (no matches) |
| No process left running | `20-ps-started-pids.txt`, `21-ps-runner-leftovers.txt`, `22-ps-result.txt` | `started_pids_still_alive=0`, leftovers grep exit `1` |
| Full supervisor test suite | `23-tests.log`, `24-tests-result.txt` | exit `0`, `112/112` pass (existing `99/99` preserved) |
| Existing supervisor tests only | `26-existing-tests-only.txt` | exit `0`, `99/99` pass |
| Working tree scope | `00-git-status-before.txt`, `25-git-status-after.txt` | only the three owned new paths |

## What the driver does

```text
runner.mjs --data-dir <dir> [--interval-seconds 600] [--lease-seconds N]
           [--tick-work-ms N] [--instance-id ID] [--once]
           | --ephemeral [same options]
```

* Durable JSON state in `--data-dir` only (`state.json`, atomic temp+rename).
  `--data-dir` is required; `--ephemeral` is the only way to default to a
  temporary directory.
* Fixed-cadence interval loop (default 600 s). Every tick goes through
  `executePlannedSweep` with an injected `execute` that records a receipt in
  the incident journal. It never spawns a process, never opens a socket and
  never reads a credential.
* The pending action is written to disk before the sweep side effect, so a
  `kill -9` leaves it for `reconcileAfterRestart()` on the next start. The
  reconciler consumes it exactly once and resumes it as an `EXTRA` sweep.
* Singleton lease: a second live instance is refused with `LEASE_HELD` and
  never advances the ledger generation. Every write is generation-fenced, so a
  stale instance is refused with `STALE_LEDGER_GENERATION`.
* SIGINT/SIGTERM drain the current tick, record `STOPPED`, and write the state
  atomically. `--once` runs exactly one tick and exits.

## Scope statement

No LaunchAgent was registered. `launchd`/`launchctl` were not run. No client
box, Command Center database or credential was touched. No network call or
provider call was made. `pm2` was not used.

Operator home paths in these artifacts are redacted as `<operator-home>`.
