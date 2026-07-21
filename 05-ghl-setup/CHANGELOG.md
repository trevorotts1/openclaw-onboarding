# Changelog - ghl-setup

All notable changes to this skill wrapper are documented here.

---

## [v6.5.10] - July 21, 2026 — fix: the automatic self-test sent live SMS and email from the client's account

### Removed
- **Tests 5 and 6 (live SMS send, live email send) deleted from the automatic
  self-test in `ghl-setup-full.md`.** The guide said "After setup, the AI should
  run these tests automatically" and then listed seven tests, two of which
  `POST`ed a real message through `/conversations/messages` from the client's own
  account to a contact identifier the agent was instructed to substitute, with
  the expected result stated as "JSON with messageId confirming delivery".
  `SKILL.md` completed the instruction by withholding the setup-complete
  confirmation until all seven passed. An agent following the skill literally
  therefore sent two unsolicited messages out of a client account, to a real
  contact, as a side effect of being asked to set up an integration. There was no
  approval step, no dry-run mode and no sandbox scoping. (Finding T1-01.)

### Changed
- The media-library check renumbered from TEST 7 to TEST 5. All five remaining
  self-tests are read-only.
- `SKILL.md` self-test count corrected from 7 to 5 in both places that stated it
  (the "What This Skill Covers" bullet and the "Important Rules" gate), plus a new
  rule forbidding a test send from a client account outright.

### Added
- A **SEND VERIFICATION** section in `ghl-setup-full.md`. Send capability is still
  documented, but it is not part of setup and is not required to call setup
  complete. Proving it requires all four of: explicit operator approval for that
  specific send in that session; a designated operator test contact, never a
  client contact; an identifier supplied by the operator rather than discovered
  by searching the client's contacts; and a report afterwards. The section
  deliberately carries no ready-to-run command.
- A caution on the "Search and Message a Contact" example marking it
  reference-only, since it sits next to the self-test and carries a runnable send.
- `tests/unit/ghl-setup-selftest-no-live-send.test.py` (repo root) — fails if any
  numbered self-test is a send, if the checklist references one, if the numbering
  is not contiguous, or if a self-test count claimed in `SKILL.md` disagrees with
  the number of tests that actually exist. Wired into CI.

## [v6.5.9] - July 1, 2026 — docs: unified 11-alias GHL LOCATION-PIT resolver

### Changed
- Credential resolver chains in `INSTRUCTIONS.md` (`ghl_preflight`) and `INSTALL.md` (Step 1
  discovery + the location-lookup fallback) expanded from a 3-alias chain
  (`GOHIGHLEVEL_API_KEY` → `GHL_API_KEY` → `GHL_PIT`) to the full canonical 11-alias LOCATION-PIT
  set documented in `TERMINOLOGY.md` (adds `GHL_TOKEN`, `GHL_PRIVATE_INTEGRATION_TOKEN`,
  `PRIVATE_INTEGRATION_TOKEN`, `GHL_PRIVATE_TOKEN`, `PIT_TOKEN`, `GHL_PIT_TOKEN`,
  `GOHIGHLEVEL_LOCATION_PIT`, `GHL_LOCATION_PIT`).
- `SKILL.md` gains a unified-resolver callout (all 11 names + the Agency-PIT separation warning)
  and a cross-reference to `TERMINOLOGY.md`.

### Fixed
- Corrected the alias names quoted in `SKILL.md`'s resolver callout — a prior draft listed
  `GOHIGHLEVEL_CONVERTANDFLOW_API_KEY` / `GHL_CONVERTANDFLOW_API_KEY` /
  `GOHIGHLEVEL_CAF_API_KEY` / `GHL_CAF_API_KEY` / `CAF_API_KEY` / `GOHIGHLEVEL_PIT`, none of which
  are part of the canonical set in `TERMINOLOGY.md` or implemented by any resolver. Replaced with
  the actual 10-alias set that matches every shipped resolver.

---

## [v6.5.8] - June 30, 2026

### Fixed
- P0: Canonicalized GoHighLevel credential variable names. The installer now writes (and every doc reads) canonical `GOHIGHLEVEL_API_KEY` / `GOHIGHLEVEL_LOCATION_ID` (what QC, PREREQS, and skills 36/44 already require), plus legacy `GHL_API_KEY` / `GHL_LOCATION_ID` aliases for skill-29 back-compat. Resolves the fresh-box non-convergence where the installer wrote `GHL_*` but QC read `GOHIGHLEVEL_*`.
- P0: `qc-ghl-setup.sh` now resolves the VPS layout — uses `/data/.openclaw/secrets/.env` and `/data/.openclaw/skills` when `/data/.openclaw` exists, else the Mac `$HOME/.openclaw` paths. Stops the VPS false-FAIL.
- P1: Removed the dead `~/clawd/secrets/.env` path (SKILL.md, ghl-setup-full.md, INSTRUCTIONS.md) → `~/.openclaw/secrets/.env`.
- P1: Removed the self-contradiction telling users to create an "API key" — STEP 1 and the manual-input prompt now point to Settings > Integrations > Private Integrations (PIT).
- P1: `qc-ghl-setup.sh` pit-prefix check is now a WARN, not a hard FAIL (valid non-prefixed PITs no longer false-fail).
- P2: Removed dead OAuth-refresh advice (a PIT is static). Completion message now says creds live in `~/.openclaw/secrets/.env` (chmod 600), not openclaw.json. QC rubric VPS path corrected to `/data/.openclaw/secrets/.env`. PREREQS satisfy steps note `-u node` config writes on VPS.

### Added
- Runtime preflight + fallback chain (`ghl_preflight` / `ghl_request`) in INSTRUCTIONS.md: resolves token (GOHIGHLEVEL_API_KEY → GHL_API_KEY → GHL_PIT) + location, BLOCKS with the exact missing-var fix instead of a silent 401, auto-discovers location, and adds 429 exponential backoff + one 5xx/timeout retry.
- Real Location-PIT media upload example (`POST /medias/upload-file`, multipart/form-data) in INSTRUCTIONS.md and EXAMPLES.md; removed the "AI handles encoding automatically" hand-wave.
- MCP-first tiering banner echoed at the top of INSTRUCTIONS.md and EXAMPLES.md (defer day-to-day ops to skill 36 MCP / skill 44 caf; raw REST is the foundation/fallback tier).
- Read-only media-library reachability probe and a client-verifiable receipt step (masked PIT prefix + location business name + location id + timestamp).

---

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.

