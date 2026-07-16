# Changelog - ZHC Early Warning System (Skill 60)

All notable changes to this skill. Dates are UTC. This skill's version lives in
`skill-version.txt` and the SKILL.md frontmatter `version:` field, kept in lockstep.

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
