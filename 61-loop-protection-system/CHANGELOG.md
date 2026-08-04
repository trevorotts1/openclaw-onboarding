# Changelog - Loop Protection System (Skill 61)

All notable changes to this skill. The skill versions independently of the repo
line (its own `skill-version.txt`), like Skill 60.

## [0.4.0] - 2026-08-04

New loop class **LP-A8: agent-to-agent cross-run resend loop**, closing a real
incident verified live on a client box the same day. Repo-only change (this
skill's rollout gate stays HELD, `config/rollout.json` unchanged); no box is
armed, activated, or touched by this release.

**The incident.** An orchestrator agent routed work to a department agent via
`sessions_send`, then waited. `sessions_send` falls back to a HARDCODED 30000ms
timeout when the caller omits `timeoutSeconds`. The target department was busy
and did not reply within 30s. The orchestrator misread the LOCAL TIMEOUT as a
DELIVERY FAILURE and re-sent the byte-identical message as a BRAND-NEW
top-level run - 6-8 times, ~34s apart (30s timeout + ~4s overhead is the resend
cadence fingerprint). The victim department churned past 154,000 input tokens
with no brake. Nothing caught it: OpenClaw's own `tools.loopDetection` counts
repeated tool calls WITHIN one run, and `session.agentToAgent.maxPingPongTurns`
bounds the INNER exchange of a single `sessions_send` call - every resend here
was a separate top-level run id, so both counters reset to a clean slate each
time. Zero firings across a 57MB gateway log while the loop was raging; tuning
either existing threshold is a structural no-op for this class.

**The detection signal (proven on the live box).** Every inbound cross-agent
message the gateway delivers is stamped in the RECEIVING agent's session
transcript as `message.provenance = {kind:"inter_session",
sourceTool:"sessions_send", sourceSessionKey:...}` - structural, and present
regardless of what the sending side logged (a resend is a fresh run at the
sender, so nothing the sender wrote survives the resend boundary; only the
receiver's transcript does).

Added:
- **D7 - cross-run resend (provenance-stamped)** (`loop_detectors.py
  :: d7_cross_run_resend`). Reads AGENT SESSION transcripts
  (`agents/*/sessions/*.jsonl` - a DIFFERENT stream from the
  `*.trajectory.jsonl` event log D1-D4 read; a bare `*.jsonl` glob is
  explicitly filtered to exclude the trajectory suffix), offset-tracked
  (`loop_watchdog.py :: collect_cross_run_sends` / `_read_new_session_rows`,
  its own `loop-sess:<path>` cursor namespace, never colliding with D3's
  `loop-traj:<path>`), bounded to recently-modified files - cheap enough for a
  60s cadence even though it currently rides the existing 15-minute tick (no
  new cron/pulse-lane is added by this release; see Known gaps below). Groups
  by (source, target, normalized-payload-hash) and slides a 300s window over
  each group's DISTINCT run ids; `>= 3` inside the window is loop-confirmed P1,
  `== 2` is WARN-only, and a genuine multi-message handoff (distinct payload
  hashes per send) never accumulates a group at all - conservative by default.
  D5 (completion-rate) and D6 (outbound-send-rate) remain the RESERVED,
  unbuilt names documented in `collect_evidence()`'s docstring (fix design
  SS4); D7 is unrelated and does not consume either reservation.
- **Never-log-raw-body boundary** (`loop_common.py ::
  normalize_inter_session_payload` / `cross_run_payload_hash`). The raw
  message body - which can carry a live client credential pasted
  mid-conversation - is normalized (leading bracketed preamble stripped,
  whitespace collapsed) and SHA-256 hashed (16-hex, matching
  `signature_hash`'s truncation) INSIDE the collector, one call, one stack
  frame; unlike D3 (whose structural fields carry no client content), the
  hash boundary sits at the collector here so the raw text never crosses into
  a detector, a finding, the ledger, or any log line anywhere in this skill.
- **LF-9 - abort + park** (`loop_killcards.py :: lf9_abort_cross_run_resend`,
  Tier 1, config-free like LF-6, so it applies for real in-tick on an armed
  box). Calls the native `sessions.abort` RPC on the resending SOURCE
  session's in-flight run (best-effort `openclaw sessions abort --session
  <key> --json`, `_sessions_abort_via_cli`; a documented safe no-op when
  nothing is active, `{ok:true, abortedRunId:null}`) then parks the source
  unit visible-red. NEVER pkill node, NEVER restarts the gateway. A 600s
  action cooldown (the incident's own proven-safe spacing) is enforced via the
  ledger's EXISTING digest/dedup primitive (the same one the alert path uses)
  - a second call inside the window is REFUSED, never re-applied.
  `run_fix()`'s `fix <finding-id>` operator path gained a matching `fc ==
  "LF-9"` branch (mirrors the LF-6 branch exactly).
- **`resend` breaker** (`config/breakers.json`, `loop_breaker.py ::
  resend_breaker_trips`) - the independent ceiling-copy predicate every other
  breaker carries (the S4 cap-raise-without-stamp pattern).
- **`config/thresholds.json :: d7_cross_run_resend`** - `window_seconds: 300`,
  `warn_repeat: 2`, `p1_repeat: 3`, `action_cooldown_seconds: 600` - the
  proven-safe values from the live incident.
- **`config/signatures.json` / `docs/LOOP-CLASS-CATALOG.md`**: `LP-A8`
  registered (family A, `F15` - the taxonomy's next LP-introduced extension
  after `F14`=LP-A1, per SKILL.md's "F14+" rule), detector `D7`, tier default 1.
- **Tests**: `tests/fixtures/cross-run-resend.sends.json` (3 groups: a 3-send
  true positive, a 2-send below-threshold pair, and a 3-message legitimate
  fan-out with distinct payloads) + `tests/drills/D-RESEND.md`, wired into
  `verify.sh` step 3 (now fifteen drills) and into `loop_detectors.py` /
  `loop_watchdog.py` / `loop_killcards.py` / `loop_breaker.py`'s own
  `--self-test`s.

Known gaps (stated plainly, not silently dropped):
- D7 rides the EXISTING 15-minute tick, not a dedicated 60s pulse-lane cron.
  It is built cheap enough to run at 60s (offset cursors, recent-mtime file
  filtering, no gateway-log tail) but no new cron/pulse-lane infrastructure
  ships in this repo-only PR - that is a separate, larger change or belongs to
  whatever eventually enables the D5/D6 pulse lane already reserved above.
- The exact envelope nesting of `message.provenance` and the message-body
  field name are read defensively (multi-candidate, fail-soft) per this
  skill's standing burn-in discipline; `message.provenance` itself (the
  `{kind, sourceTool, sourceSessionKey}` shape) IS the confirmed incident
  proof and is tried first. CONFIRM the exact envelope on the operator
  canary during burn-in, same as every other plausible-schema constant this
  skill ships with (`_CRON_LAST_RUN_FIELDS`, `_USAGE_TOTAL_FIELDS`).
- The `openclaw sessions abort --session <key> --json` CLI shape is a
  plausible candidate (mirrors the already-shipped `openclaw cron list
  --json` pattern), not yet confirmed against a live gateway - the mechanical
  action is written so an unreachable/wrong CLI shape degrades to
  `{ok: False}` and STILL parks the source (the park is what actually breaks
  the loop; the RPC is a best-effort courtesy).

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
