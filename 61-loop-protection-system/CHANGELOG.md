# Changelog - Loop Protection System (Skill 61)

All notable changes to this skill. The skill versions independently of the repo
line (its own `skill-version.txt`), like Skill 60.

## [0.3.0] - 2026-07-13

The collect layer is REAL. `loop_watchdog.py :: collect_evidence()` was a stub
that returned `{"windows": [], "runs": [], "crons": [], "wedge": {}}` - so even a
fully armed watchdog handed D2, D3, and D4 EMPTY evidence on a real box; only D1
(pm2) had a live feed. This is why the 2026-07-13 token-furnace / correction-wave
incident produced zero findings (fix design SS4, finding 2: "the single most
important repo finding"). No box behavior changes until the operator's batched
roll; DRY_RUN/armed/rollout gates all stay intact.

Added:
- **`collect_windows()` (D2 feed)**: hourly paid/local token windows for the
  trailing 24h from the trajectory stream's `model.completed` events - field
  names verified against a live box. Usage totals are CUMULATIVE PER RUN, so each
  completion contributes its DELTA, making a burn visible MID-RUN while the
  looping run is still alive (a run-end-only source sees a furnace only after it
  stops). `trace.artifacts` totals back-fill runs whose completions carried no
  usage - never double-counted. `initiated_sessions` counts only HUMAN-triggered
  `session.started` rows (`data.trigger == "user"`; cron/heartbeat stay
  idle-classified). Windows also carry per-hour `completions` as the future D5
  completion-rate feed.
- **`collect_runs()` (D3 feed)**: offset-tracked NEW-bytes trajectory slice
  (ledger offsets `loop-traj:<path>`, line-boundary safe, rotation-safe) ->
  one signature per finished run from `trace.artifacts`: outcome class + ordered
  tool NAMES (`data.toolMetas[].toolName`) + target. BOTH outcomes collected:
  SUCCESSFUL runs hash as outcome `OK` - the correction wave was "successful"
  turns end to end, invisible to failure-only hashing. Erroring `session.ended`
  rows without an artifacts row are synthesized. Tool names only; arguments and
  message content are never collected.
- **`collect_crons()` + `collect_wedge()` (D4 feeds)**: `openclaw cron list
  --json` (read-only, fail-soft) with OBSERVED fire counting - last-run marker
  transitions persisted in ledger meta over a trailing 24h window; a strict
  lower bound, `None` (silent) until a fire is actually observed. Wedge probe:
  demand-without-progress tick counter (increments only when the slice shows
  prompts/starts with zero completions while the gateway process is up; resets
  on progress; HOLDS on an idle box - idleness is never a wedge) + orphan
  :18789 listener vs the declared supervisor pid in a STALE (expired or >=1h
  old) restart-handoff file; a fresh handoff mid-restart never reports.
- **D3 success ceiling**: `d3_identical_signature` accepts outcome `OK` runs at
  the new `config/thresholds.json` `p1_repeat_success: 10` (failures keep WARN 3
  / P1 5; successes never WARN) - so a heartbeat succeeding once per slice stays
  silent while 10+ back-to-back identical successful turns confirm a loop.
- **`LOOP_NO_PROBES=1` env seam**: disables every subprocess probe
  (pm2/openclaw/pgrep/lsof) so self-tests and drills are hermetic.
- **D-COLLECT drill** in `verify.sh` + collect cases in the watchdog self-test:
  a synthetic loop trajectory (real v20 schema) in a scratch openclaw root must
  yield non-empty windows/runs, D2 must flag the idle paid burn, D3 must flag
  the repeated identical successful turn, and the slice must be offset-consumed.

Changed:
- `collect_evidence(led=None)` now takes the tick's Ledger (offsets + persisted
  counters); with `led=None` (the read-only `audit` path) it PEEKS at bounded
  tails and advances nothing. The D5/D6 attach points (gateway-log model-fetch
  counts; sendguard ledger) are documented in its docstring per the fix design -
  deliberately NOT built here.

## [0.2.0] - 2026-07-10

Repo-side path to live: the machinery is WIRED into onboarding + the updater, but
still HELD by a fleet gate (canary-then-hold, law 8, stays intact). No box is armed
by this change; no client box is activated until the operator flips the gate.

Added:
- **Fleet rollout gate** `config/rollout.json` (`fleet_rollout_enabled: false` by
  default; env override `OPENCLAW_LOOP_PROTECTION_ROLLOUT`). Mechanically enforces
  the HOLD instead of relying on the absence of wiring.
- **Shared activation helper** `scripts/activate-loop-protection.sh` (repo root),
  called by BOTH `install.sh` (onboarding) and `update-skills.sh` (updater) — one
  definition, no copy-paste drift. Installs Skill 60 FIRST, then Skill 61 only if 60
  installed cleanly (60 is a hard prerequisite; 61 consumes 60's ledger read-only).
  Client role is GATED (HELD by default); operator role is UNGATED (the canary).
  NEVER arms; asserts `armed=false` afterward. `--self-test` (offline, sandboxed).
- **Operator canary** `scripts/loop-protection-canary.sh` — `install | verify |
  status | arm | disarm | runbook`. Idempotent; stamps a 7-day burn-in clock on
  first install; `arm` is refused before 7 days (unless `--force`) and requires
  `--yes`; refuses to arm a non-operator ledger. `--self-test` (offline, sandboxed).
- **Wiring proof** `scripts/test-loop-protection-wiring.sh` — 9 offline checks that
  install.sh + update-skills.sh call the helper, persist both scripts, keep the gate
  HELD by default, and that the helper, canary, and both skill installers self-test.

Wiring (repo change only; execution deferred to the operator):
- `install.sh` (end-of-run, before the final gateway restart) runs the activation
  helper with `--role client`; persists both loop-protection scripts to
  `~/.openclaw/scripts` (or `/data/.openclaw/scripts`).
- `update-skills.sh` apply-phase post-sync hook runs the same helper `--role client`;
  both scripts are added to the persistent-copy loop (survive temp-clone cleanup).

Deferred (operator-timed, NOT run here): the operator-box canary install + arm, and
the fleet rollout (flip `fleet_rollout_enabled=true` in ONE batch on Trevor's word).

## [0.1.0] - 2026-07-10

Initial build (repo-only; HELD pending the operator-box canary + 7-day burn-in per
spec 9.2). Implements the greenlit scope of `LOOP-PROTECTION-SYSTEM-SPEC-v1.md`.

Added:
- **Watchdog + detectors.** `loop_watchdog.py` (the host-level 15-minute tick,
  outside every OpenClaw session, zero model calls) driving the four loop-specific
  detectors `loop_detectors.py`: D1 restart velocity, D2 idle token-burn rate, D3
  repeated-identical-signature, D4 timer re-fire / wedge / orphan-port.
- **Protection.** `loop_breaker.py` - five circuit breakers (process / turn / retry
  / cron / healer) with S4-cap-raise-without-stamp detection; `loop_backoff.py` -
  persisted exponential backoff with jitter (2h base, doubling, 24h cap) reconciling
  the never-stop doctrine (spec 5.4).
- **Response.** `loop_killcards.py` - Tier-1 reversible kill cards (LF-1 stale-lock,
  LF-2 offset rewind, LF-4 cron park, LF-6 process park) with the DRY_RUN quarantine
  ladder and the healer self-breaker; `loop_escalate.py` - Rescue Rangers escalation
  via the n8n webhook with an injectable transport and the UNSENT fallback.
- **State.** `loop_ledger.py` - the single SQLite-WAL writer (findings, fix_actions,
  breaker_state, backoff_state, offsets, digests, meta); `armed=false` DRY_RUN
  observe-only default.
- **Surface.** `loop-companion.sh` (sole entry) + `scripts/loop_companion.sh`
  (audit/status/troubleshoot), `install.sh`, `preflight.sh`, `verify.sh` (nine
  offline drills).
- **Config as data.** `config/thresholds.json`, `breakers.json`, `fix-classes.json`,
  `signatures.json` (the loop taxonomy + LP<->F14+ mapping).
- **Gates.** The four merge-gate scanners (guard-no-anthropic-runtime,
  scan-no-secrets, scan-no-client-identifiers, scan-no-json-exports), same
  0/1/2/3/4 exit contract as Skill 59/60.
- **Tests.** `tests/fixtures/` (restart storm, identical-signature runs, corrupted
  offset, orphan-port, subtractive misconfig, idle-burn trajectory) + `tests/drills/`
  (D-RESTART, D-SIG, D-OFFSET, D-ORPHAN, D-BURN, D-BACKOFF, D-HEALERLOOP, D-ESCALATE,
  D-DRYRUN).

Interlock:
- Consumes Skill 60's ledger read-only; contributes D1-D4 (proposed as Skill 60
  signals S11-S14, Open Decision T2). Operated by openclaw-maintenance + Healer +
  Bugs (spec Section 8); the maintenance role SOPs now invoke
  `loop-companion.sh audit --local` and the kill cards, and carry the F14+ extension.
