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
