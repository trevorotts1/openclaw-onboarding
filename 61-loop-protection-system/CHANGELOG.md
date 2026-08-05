# Changelog - Loop Protection System (Skill 61)

All notable changes to this skill. The skill versions independently of the repo
line (its own `skill-version.txt`), like Skill 60.

## [0.4.0] - 2026-08-05

**D5 - the first detector in this skill that measures a STOCK instead of a flow.**
D1-D4 all count events per tick: they answer "is a loop running right now?" and go
quiet the moment it pauses. That leaves a real gap, and an operator-box incident
walked straight through it - a run wedged against the runtime's own identical-call
guard filled a session transcript with ~1,100 of its own refusals, and because the
model reads that transcript back as its own history, every later turn on it stayed
degraded after the run was long dead. Three fixes aimed at the ENVIRONMENT were
deployed during that incident and none ended it, because the fault was in the
CONTEXT. D3 hashes the new-bytes-since-last-tick slice, so once the loop paused D3
reported all-clear on a transcript that was still ~72% wreckage.

**ARMED on the operator box; fleet rollout still HELD** (`config/rollout.json`
`fleet_rollout_enabled` stays `false`, awaiting a separate explicit operator GO).

### A correction to this entry's own premise, recorded on purpose

D5 was first specified against the theory that accumulated transcript poison was
the PRIMARY cause of that incident. **That theory was refuted before this shipped**
and the detector was redesigned rather than quietly re-labelled. The counterexamples
were decisive: the first burst ignited from a context measured at 0% loop text, and
the fully-poisoned session still answered a normal question correctly in seconds.
Poison was neither necessary nor sufficient. The apparent "clean experiment" behind
the original theory was confounded - the fast reply came from a brand-new session
created seconds after the old one died, so the variable that actually moved was
conversation-lane occupancy, not transcript cleanliness.

So D5 ships with IGNITION (a blocked-call burst) as the primary, early, high-
precision face, and poison ratio DEMOTED to a secondary aftermath signal. The
aftermath face is still worth having - it is what persists and what a roll must
clear - but a detector built on it alone fires late, after the damage.

### Added

- **`d5_transcript_poison()`** in `loop_detectors.py` + **`collect_sessions()`** in
  `loop_watchdog.py`, wired into `run_detectors`/`collect_evidence` exactly like
  D1-D4. New loop class **LP-A8** (F15), new **session** circuit breaker, new fix
  classes **LF-9/LF-10/LF-11**.
- The block signature is **STRUCTURAL, never prose**: `details.status == "blocked"`
  and `details.deniedReason == "tool-loop"` on a `toolResult` record. It is
  therefore language- and wording-drift-independent, and no message content enters
  a finding (counts, enum values and tool NAMES only). The blocked tool name is
  recorded but never assumed - both `read` and `tool_call` appeared in the measured
  incident, so nothing hard-codes a single tool.
- **Second carrier detection.** Compaction checkpoint summaries can capture the
  loop verbatim; those are re-injected on resume and **survive a transcript roll**,
  which is why rolling the file alone is not a complete fix. D5 counts them and
  says so in the finding (`SECOND CARRIER`). Measured: 7 of 16 checkpoint summaries
  poisoned in the incident file, 0 of 14 in a healthy control archive.
- **LF-10 auto-roll**: archives a confirmed-poisoned transcript to a timestamped
  name beside it so the next turn starts clean. **MOVE, never delete**; the
  one-line revert moves it back. Guarded by a **live-transcript refusal** - the
  unattended tick can clear yesterday's wreckage but can never roll a conversation
  in progress.
- **Four failable drills** (`D-POISON`, `D-POISON-CLEAN`, `D-POISON-ROLL`,
  `D-POISON-LIVE`) over two new synthetic fixtures, plus `tests/drills/D-POISON.md`.

### Fixed

- **`collect_units()` reported a unit's LIFETIME restart count as its per-tick
  delta.** pm2's `restart_time` is cumulative, so the first tick on any real box
  read a long-lived unit's entire history as one storm - a false D1 P1 for every
  unit that had ever restarted, and on an armed box a false park. Restart counts
  are now baselined per unit in ledger meta: first sight is always delta 0, and a
  counter that goes backwards re-baselines instead of spiking. Found while
  assessing whether arming this box was safe; it was not, and this is why. Covered
  by a new self-test case.

### Proven

- **Offline (drills, in `verify.sh`, exit 0):** 18 drills, all four merge-gate
  scanners clean.
- **Failability, mutation-tested rather than assumed:** raising the D5 thresholds
  out of reach fails all four D5 drills; removing BOTH the silence rule and the
  size guard fails `D-POISON-CLEAN`. Honestly noted in `D-POISON.md`: removing
  either guard *alone* is masked by the other, so no single mutation catches it -
  the two are redundant by design.
- **Live, read-only, on the operator box** (detector only - `tick()` was never
  called, so LF-10 could not run and no real file was moved):
  - TRUE POSITIVE - the archived incident transcript (4,607,807 bytes) yields
    exactly one P1 `LP-A8`: 275-block ignition burst, 50% trailing-200 share,
    7 poisoned checkpoints.
  - TRUE NEGATIVE (hard control) - a **larger** healthy archive from the same box
    and same agent (17,160,766 bytes, 3.7x the poisoned one, 8x past the flush
    re-arm floor): **0 findings**.
  - TRUE NEGATIVE (breadth) - all 69 live session transcripts for that agent:
    **0 findings**. One carried a single block, correctly below the WARN floor of
    3 and correctly silent.

### NOT verified (stated plainly)

- **LF-9 (abort the run) has never been executed and cannot be.** No supported
  run-abort CLI was found in OpenClaw 2026.7.1-2 (`openclaw sessions` offers
  `cleanup`/`compact`/`export-trajectory`/`list` only). It ships **Tier 2,
  prepare-only**. Aborting is believed to be the highest-value remediation - it is
  what frees the conversation lane, and the runtime rather than the model ended
  most observed bursts - but this skill does not do it today.
- **LF-11 (prune poisoned checkpoints) is prepare-only and was never executed.**
  The live gateway rewrites the session store, so an in-place edit without a
  restart is clobbered.
- **LF-10 has never fired on a real poisoned transcript in production.** It is
  proven on fixtures and by the armed-tick drill; the archived incident transcript
  was rolled by hand before this work began.
- The thresholds are derived from **ONE** incident on **ONE** box against that
  box's own healthy corpus. They are measured, not invented, and the derivation is
  recorded in `config/thresholds.json`, but a second incident could move them.
- **No claim is made about which config change prevents recurrence.** Config
  remediation was owned by other work and is not part of this skill.

## [0.3.2] - 2026-07-16

X/U-X3 (U93), D20 Option B: `scripts/loop-protection-canary.sh` renamed to
`scripts/loop-protection-first-proof.sh` (doctrine scrub, "CANARY, THEN HOLD" ->
"PROVE ON THE OPERATOR BOX, THEN HOLD" — this skill's law 8 in `SKILL.md` reworded
to match). A one-release shim is retained at the old path (`exec bash`'s the new
script with `"$@"`, no reimplemented behavior) so a live-box cron still calling
`loop-protection-canary.sh` keeps resolving unchanged; verified byte-identical
output between the old-path shim and the new path. `install.sh`/`update-skills.sh`
persist BOTH files for the one-release window. `HOW-TO-USE.md` and
`config/rollout.json` updated to match. No box behavior change; still DISARMED
(DRY_RUN default, rollout HELD).

## [0.3.1] - 2026-07-13

Field-hardening + doc-honesty correction for the D2 token reader (QC follow-up to
0.3.0). No box behavior changes; still DISARMED (DRY_RUN default, rollout HELD).

Fixed:
- **`_usage_total()` is now a multi-candidate, fail-soft extractor** instead of a
  single hard-coded `usage.total` read. It tries `usage.total` (the CONFIRMED
  emitted aggregate) -> `usage.totalTokens` / `usage.total_tokens` (defensive raw-
  schema aliases) -> the summed component buckets `input+output+cacheRead+cacheWrite`
  (== the writer's own `derivedTotal`). If a future schema drops `total` but keeps
  the buckets, D2 still charges non-zero rather than going silently blind - the exact
  Star-furnace failure mode. Mirrors Skill 60's `_extract_context_tokens` posture so
  the two skills share ONE defensive reader convention. The verified within-run
  cumulative-DELTA charging is preserved unchanged.
- **Doc-honesty**: replaced every "verified against a live box" / "verified live
  values" overclaim in `loop_watchdog.py` and this changelog with the truth. The D2
  token field is **confirmed from the OpenClaw 2026.6.11 trajectory-writer source**
  (`getUsageTotals()` emits `usage.total`; writer `dist/selection-CVIPXpKT.js:14200`
  / `:14217`, shape `:4328-4339`, normalizer `dist/usage-C67Kbb7n.js:44-64`, codex
  `dist/run-attempt-CJMFmJj8.js:5276`). The remaining field names (session triggers,
  cron last-run markers, handoff keys) are honestly labeled plausible OpenClaw-schema
  candidates, read defensively, **to be confirmed on the operator canary during
  burn-in**. This also resolves Skill 60's `_CONTEXT_TOKEN_FIELDS` OPEN QUESTION for
  the token field: the raw `total_tokens` / `input_tokens` guesses are aliases the
  writer consumes but never emits into the trajectory - the emitted field is `total`.

Added:
- **BURN-IN EXIT GATE** documented on `collect_windows()` and in `SKILL.md` doctrine
  7: *before any `arm`, confirm `collect_windows` yields non-zero `paid_tokens` on the
  operator canary's real trajectory* - a live non-zero reading is the arming
  precondition, so a silently-zero feed can never reach an armed box.
- **Two new failable drills** in `verify.sh` + the watchdog self-test:
  `D-COLLECT-DELTA` (a SINGLE runId whose cumulative usage rises 100k->800k, charged
  as the 800k DELTA and NOT the 3.6M naive sum - and carried under component buckets
  only, so it also exercises the derivedTotal fallback) and `D-COLLECT-FALLBACK` (a
  `total_tokens`-only row with no `usage.total`, asserting D2 still charges non-zero).
  Both FAIL against the old single-field reader and PASS after the fix.

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
  trailing 24h from the trajectory stream's `model.completed` events. Usage
  totals are CUMULATIVE PER RUN, so each
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
