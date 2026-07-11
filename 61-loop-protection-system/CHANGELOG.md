# Changelog - Loop Protection System (Skill 61)

All notable changes to this skill. The skill versions independently of the repo
line (its own `skill-version.txt`), like Skill 60.

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
