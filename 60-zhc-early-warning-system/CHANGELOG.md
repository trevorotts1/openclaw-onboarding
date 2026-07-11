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
