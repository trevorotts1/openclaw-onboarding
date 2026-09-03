# Changelog - ZHC Early Warning System (Skill 60)

All notable changes to this skill. Dates are UTC. This skill's version lives in
`skill-version.txt` and the SKILL.md frontmatter `version:` field, kept in lockstep.

## [0.1.7] - 2026-09-03

Fixed a self-amplifying alert-storm bug: `route_finding()`'s "no operator alert
target configured" branch (`ews_alert.py`) wrote a fresh, undeduped `S7`/`P2`
event on every finding, every tick, for as long as no operator target env var
was set - measured at 27,841 undeduped rows on one live box (49.9% of that
box's entire `events` table), because the branch never checked or recorded a
digest, so nothing could ever suppress a repeat.

- The branch now uses the same check-then-record `recent_digest()` /
  `record_digest()` idiom every other repeat condition in the function already
  uses, keyed on one fixed, condition-level key (`S7|no_operator_target`)
  instead of the per-finding key - the condition resurfaces once per
  `dedup_window_hours` (default 6h) while it stays broken, never silenced,
  never appended forever.
- Severity bumped P2 -> P1: this condition disables every alert the box's
  sentinel can raise, not just the one finding that triggered it - P1 also
  means an unacked one older than 30 minutes reaches Rescue Rangers via
  `escalate()`, the one path still able to reach a human when the operator
  target itself is what's missing.
- `ews_ledger.py`'s `record_event()` gained a write-layer guard: `dedup_key`
  is derived (`"<signal>|<key_path>"`) when a caller passes none, so the
  column is never NULL again. Hygiene/defense-in-depth, not a throttle -
  `record_event()` still does not itself enforce dedup; that stays the
  caller's job.
- Existing rows from the live flood are NOT cleaned up by this change
  (recommendation only, nothing destructive implemented).

## [0.1.0] - unreleased (build in progress)

Initial build of the fleet Early Warning System - a deterministic, zero-model-call
sentinel that runs on every OpenClaw box and alerts the OPERATOR (never the client)
when the machine breaks or drifts. Built to the locked operator decisions D1-D9.

- **Unit 1 - foundation** - the skill directory, SKILL.md doctrine (operator-only,
  zero model calls, config as the box user never root, never print a secret,
  no client names, canary-then-hold), `skill-version.txt` at 0.1.0, and the four
  configuration catalogs: `monitored-keys.json` (S1/S4/S10 key catalog),
  `signatures.json` (anthropic-family deny data, secret-class pin, known-writer
  allowlist), `thresholds.json` (15-min tick / hourly aggregator / 60-or-45 snapshot
  retention / weekly-pinned cadence / alert-only caps, all locked decisions), and
  `billing-models.json` (D9 billing-aware furnace framing: usage-allowance vs metered
  dollars). No secret values, no client names, no runtime Anthropic identifiers.

- **Unit 2 - S3 context-usage notifier fix** - closed four defects found in a
  read-only diagnostic pass: (1) the tick never computed live context usage, so
  `sig_s3()`'s 70%-note / 85%-handoff branches were dead code in production
  (exercised only by self-test fixtures) - fixed with a new `_context_usage()` in
  `ews_sentinel.py` (reads the newest session `*.trajectory.jsonl`'s latest event
  off an OPEN QUESTION-flagged candidate field list, verify-first against the
  canary box; an opt-in, OFF-by-default `openclaw session status --json` CLI
  fallback per the same OPEN QUESTION) and the `run_tick()` call-site fix that
  passes `usage_pct`/`context_window` into `sig_s3()`; (2) `box-agent-notices.jsonl`
  had no reader anywhere in the repo - fixed with `read_box_agent_notices()`
  (`ews_alert.py`) and `ews-entry.sh notices [--peek]`, tracked through the same
  single-writer ledger offset mechanism every other tailed stream in this skill
  uses; (3) the D5 running-low case never reached anyone but the box's own agent,
  even on the operator's own box - fixed with a NARROW, APPROVED exception (Lane 2,
  `context.operator_self_notify`, default true): on the operator's OWN box ONLY, an
  `S3|handoff` finding also sends one deduped, plain-language self-notice to the
  operator, gated structurally in code on that box's own ledger `role` meta (never
  a client box, regardless of the config flag); (4) added the failable
  `D-CONTEXT-USAGE` drill (`tests/drills/D-CONTEXT-USAGE.md`, fixture pair
  `context-window-clean.json` + `context-usage-86pct.trajectory.jsonl`, wired into
  `verify.sh`) proving the live computation, the reader, the Lane-2 operator-only
  boundary, and that the broken-config P1 path is untouched. `docs/SIGNAL-CATALOG.md`,
  `HOW-TO-USE.md`, and `SKILL.md` updated to match.

- **Unit 3 - context-token extractor nesting + field correction** (version 0.1.2) -
  closed the token-detection defect an independent QC found while verifying Skill 61:
  `ews_sentinel.py`'s `_extract_context_tokens()` was DOUBLY blind on every real
  trajectory row. (1) WRONG NESTING - it did a 2-level `obj["usage"][...]` lookup,
  but a `model.completed` row carries usage 3 levels deep at `row["data"]["usage"]`;
  the reader now digs into `data.usage`. (2) WRONG FIELD NAMES - it read the raw
  provider aliases `input_tokens`/`total_tokens`, which OpenClaw's trajectory writer
  CONSUMES but never EMITS (the emitted normalized shape is `{input, output,
  cacheRead, cacheWrite, total}`). Both facts are now CONFIRMED from the OpenClaw
  2026.6.11 trajectory-writer source, read-only, no live box touched
  (`selection-CVIPXpKT.js:14200-14216` writer, `:4310-4339` `getUsageTotals`;
  `usage-C67Kbb7n.js:44-64` `normalizeUsage`). The `OPEN QUESTION` labels in the
  script and `tests/fixtures/README.md` are replaced with the source-cited truth.
  METRIC: this detector measures CONTEXT-WINDOW OCCUPANCY, not spend, so it reads the
  PROMPT/INPUT side `input + cacheRead` (OpenClaw's own `prompt_tokens` definition,
  `usage-C67Kbb7n.js:68-70, :83`) - deliberately NOT `output` and NOT the billed
  `total` (Skill 61's spend metric). Reader HARDENED fail-soft via a shared
  `_coerce_nonneg_int`/`_prompt_side_tokens` posture mirroring Skill 61's
  `loop_watchdog._usage_total`, so a missing/bool/odd value yields `None`, never a
  crash or a guessed percentage. Documented CAVEAT: `data.usage` is run-accumulated,
  so the latest-completion prompt-side is an UPPER-BOUND (fail-early) proxy for
  single-turn occupancy - the safe direction for an early-warning detector; the tight
  per-turn `contextTokens` lives in the SESSION STORE, not the trajectory
  (`agent-runner.runtime-BriI2__w.js:2310-2377`). CLI-status fallback verdict: the
  hardcoded `openclaw session status --json` invocation targets a subcommand that
  does NOT exist on 2026.6.11 (the group is `sessions`, list-only; `sessions --json`
  carries the session store's `contextTokens`/`totalTokens`) - it stays opt-in and
  OFF by default (a separate, still-unverified shape, not the confirmed defect), with
  the extractor's flat-field reader aligned to the real session-store field names.
  The `context-usage-86pct.trajectory.jsonl` fixture is rebuilt into the real
  `data.usage` shape (and now discriminates occupancy 86% from a `total` read's 137%);
  new self-test cases prove pass-new (real `data.usage` -> 92880) and fail-old (the
  pre-fix 2-level/alias reader returns `None` on the same row), plus flat + fail-soft
  shapes. All script self-tests, four merge-gate scanners, and the fixture-drill
  battery (`verify.sh`) pass; `py_compile` clean. Skill stays DISARMED / alert-only;
  no rollout or HOLD state changed.

- **Unit 4 - law 8 doctrine scrub** (version 0.1.3) - X/U-X3 (U93), D20 Option B:
  `SKILL.md` law 8 reworded "CANARY, THEN HOLD" -> "PROVE ON THE OPERATOR BOX, THEN
  HOLD", matching the fleet-wide operator-box-is-the-proving-ground doctrine (this
  skill's own operator-box Mac mini, not a client box). No behavior change - doc-only
  correction. Companion rename in Skill 61 (`loop-protection-canary.sh` ->
  `loop-protection-first-proof.sh`, one-release shim retained at the old path) landed
  in the same unit; see `61-loop-protection-system/CHANGELOG.md`.

- **Unit 6 - cron-registration failure now fails the install loudly** (version
  0.1.5) - two defects fixed in `install.sh`, both reproduced before fixing. (1)
  The `--self-test` cron-flag guard added in 0.1.4 matched only the FIRST PHYSICAL
  LINE of each `openclaw cron add` invocation, so moving the (already-wrong)
  `--schedule` flag onto a `\` continuation line evaded detection entirely and the
  self-test still printed PASS - fixed by reconstructing each logical invocation
  (joining continuations) before inspecting it. (2) The root cause: `|| echo WARN`
  swallowed every cron-add failure and `do_install` returned `EX_OK` regardless, so
  a broken installer reported success while registering ZERO monitoring crons -
  fixed so a cron-registration failure now returns `EX_ERR` with an unmistakable
  "INSTALL FAILED" block (`--no-cron` and "no gateway present" remain successes:
  deliberately skipping is not failing). Self-test: 3 -> 5 cases, all pass.
  Mutation-proven: removing the non-zero return while keeping the diagnostic text
  turns the cron-failure self-test case red. `skill-version.txt` + SKILL.md
  frontmatter bumped 0.1.4 -> 0.1.5 in this same commit (the prior merge to main
  landed the `install.sh` fix without the version bump, tripping the repo's G3
  skill-content-change gate; this closes that gap).

- **Unit 7 - cron registration is now declaration-keyed, closing the
  N-duplicate-tick defect** (version 0.1.7) - `install.sh` registered its tick
  (and, on the operator box, the aggregator) via plain `openclaw cron add
  --name/--cron/--command`, with NO dedupe-by-name guard - the CLI itself has
  none. Every install/repair/fleet-skills-roll run therefore created ANOTHER
  identical registration under the same name, schedule, and command; a live box
  was found carrying NINE copies of the same tick, each firing every 15
  minutes (9x the intended wall time and load). FIX: both `cron add` calls now
  pass `--declaration-key` (verified against the installed OpenClaw CLI's own
  `cron add --help`, which documents it as an "Idempotent declaration identity
  key" and implements add-or-converge semantics in the gateway's `cron.add`
  handler - it updates the one existing job in place if anything differs,
  no-ops if nothing changed, and creates exactly one job the first time), so
  re-running the installer any number of times now always converges to ONE job
  per key. A new `dedupe_legacy_cron_dupes()` runs before each registration
  and separately cleans up registrations made BEFORE this fix existed (which
  the declaration key alone cannot retroactively adopt, since it only matches
  jobs that already carry it): it lists existing jobs, and only when 2+ share
  the exact name + command + schedule with no declaration key (proven
  duplication - a box with a single, ordinary, never-duplicated legacy
  registration is left untouched) does it DISABLE all of them (never delete -
  fully reversible via `openclaw cron list --all` / re-enable), logging every
  id + creation time; the declaration-keyed registration immediately following
  becomes the one enabled survivor. Self-test: 5 -> 10 cases. The two new
  cases beyond the direct dedupe checks are a static extension of the existing
  cron-flag guard (every `cron add` invocation must carry
  `--declaration-key`, reconstructed across `\` continuations exactly like the
  existing `--schedule`/`--cron` check) and a dynamic suite against a fake
  `openclaw` CLI (a tiny JSON-file cron store backing `cron add/list/disable`)
  proving: fresh install registers exactly one cron; running install.sh TWICE
  still leaves exactly one (the regression guard); an existing registration
  whose command/schedule drifted is converged back in place rather than
  duplicated; 3 seeded legacy duplicates are all disabled (never deleted) with
  exactly one declaration-keyed survivor left enabled; and a lone
  (non-duplicated) legacy registration is left completely untouched (no false
  positives). Mutation-proven twice: (1) deleting `--declaration-key` from a
  real invocation is caught by the static guard; (2) disabling the fake CLI's
  own declaration-key match logic (simulating a CLI that accepts the flag but
  never dedupes) passes "fresh install" but correctly fails "run install.sh
  TWICE" with 2 crons registered - proving that check is a real functional
  guard, not a restatement of the static one. `skill-version.txt` + SKILL.md
  frontmatter bumped 0.1.6 -> 0.1.7 in this same commit.

  Fleet-wide audit (same investigation): every other `openclaw cron add`
  registrar in this repo already guards against duplication via
  `shared-utils/cron-lib.sh`'s `oc_cron_present()` (an exact JSON name-match
  presence check called BEFORE registering - built after the documented "6x
  duplicate cron" incidents in Skill 38/39 and the FIX-XC-08a incident in
  Skill 37) or an equivalent local copy of that same check (the four
  `06-ghl-install-pages/scripts/install-*-cron.sh` installers,
  `35-social-media-planner/scripts/register-weekly-cron.sh`). Skill 60's
  `install.sh` was the one remaining registrar with no guard of any kind - not
  even the older list-then-check idiom. `59-anthology-engine/scripts/
  provision-anthology-client.sh` was also found still passing the
  non-existent `--schedule` flag (the exact defect class this skill fixed in
  itself back in 0.1.4/0.1.5) - a silent zero-registration bug, not a
  duplication bug, and out of scope for this unit; flagged for its own owner.
  No other repo file was changed - fixing those sites, or building a shared
  `--declaration-key` helper for them, is a separate, explicitly-scoped
  follow-up (touches more than a handful of skills).
