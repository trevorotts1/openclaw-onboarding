# QC Checklist: GHL / Convert and Flow Setup

## 1. Purpose
Enables the agent to connect to Convert and Flow (GoHighLevel) using the correct Private Integration Token and location configuration.

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, the full reference `.md`, and the `.skill` package.
- [ ] The secrets file exists at the documented workspace location and contains non-empty credential values for GHL token and location ID.
- [ ] If mirroring to OpenClaw config is used, the relevant env vars are also present under `env.vars` in the JSON config.
- [ ] Core file updates remain lean and point to the full GHL reference instead of dumping it inline.
- [ ] No executable helper script is required in the folder; curl must be available for API verification.

## 3. Dependency Checks
- [ ] TYP and BYUP are installed first.
- [ ] An active Convert and Flow / GHL account exists.
- [ ] curl and python3 or jq are available to inspect config and test endpoints.
- [ ] The agent understands and uses the mandatory `Version: 2021-07-28` header on every GHL API request.

## 4. Key Detection
- [ ] Search all standard secret locations in order: `~/.openclaw/secrets/.env`, `~/.openclaw/openclaw.json` `env.vars`, `~/.openclaw/.env`, `~/.openclaw/openclaw.json` `env.vars`, `~/.openclaw/.env`, live environment via `printenv`, and `~/.env`.
- [ ] Recognize all practical token variable variations: `GHL_API_KEY`, `GHL_PIT`, `GOHIGHLEVEL_API_KEY`, and where relevant `GOHIGHLEVEL_AGENCY_PIT` for agency-level work.
- [ ] Recognize location variables: `GHL_LOCATION_ID` and any existing mirrored location value in JSON config.
- [ ] QC fails if the installer asks for an “API key” without first checking for a Private Integration Token or if it ignores an already-present token.

## 5. Functional Checks
- [ ] Echo a masked token prefix and the location ID from the environment to confirm values load correctly.
- [ ] Run a lightweight contacts or locations request against `https://services.leadconnectorhq.com` with Authorization and Version headers and confirm a structured JSON response.
- [ ] If only token is present and location is missing, test the documented location lookup flow and verify the location can be discovered automatically.
- [ ] Ask the agent what GHL auth uses. Expected answer: Private Integration Token, not legacy API key terminology.
- [ ] Verify the agent names the three priority test domains after setup: contacts, media library, and conversations.

## 6. QC Score
- Score this skill from **0 to 10** after running the checks above.
- Suggested rubric:
  - **10/10**: All installation, dependency, key-detection, and functional checks pass with no ambiguity.
  - **8-9/10**: Core behavior works, but one or two non-critical items need cleanup or documentation fixes.
  - **6-7/10**: Basic install exists, but the skill is missing a meaningful validation, dependency, or behavior requirement.
  - **0-5/10**: Missing prerequisite pieces, broken verification path, wrong secrets handling, or failed functional tests.
- Record final result here:
  - **QC Score:** ____ / 10
  - **Status:** Pass / Needs Fix / Blocked
  - **Notes:** ____________________________________________

## 7. QC Loop Rule
- Run at most **5 total QC/fix rounds** for this skill.
- After each failed round:
  1. Record exactly which checklist items failed.
  2. Apply the smallest targeted fix.
  3. Re-run only the failed checks plus any directly affected dependencies.
- If the skill still fails after the **5th round**, stop and escalate instead of continuing to loop.

---

## 🔴 INSTALL-TIME QC RUBRIC (v9.3.0+ standard — added automatically)

After install, score yourself honestly against this rubric. **Pass gate: 8.5/10 minimum.** Below 8.5 = loop back and fix until passing (max 5 loops, then escalate to owner).

### Score breakdown (10 points)

| Section | Points | What it tests |
|---|---|---|
| Prerequisites + INSTALL-CONTRACT.md acknowledged | 1.0 | INSTALL-CONTRACT.md was read this session AND acknowledged in your work log for this specific skill. All prerequisite skills installed. |
| All skill .md files read before any execution | 1.0 | SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md (this file), any referenced `references/*.md`. Reading happened BEFORE any command was run. |
| INSTALL.md steps executed in order | 1.5 | No skipping, no reordering, no improvising. If a step was skipped, owner consent is documented. |
| Credentials at canonical paths with canonical names | 1.5 | `~/.openclaw/secrets/.env` (Mac) / `~/.openclaw/secrets/.env` (VPS), chmod 600. Canonical env-var names used (not deprecated ones). For GHL: `GOHIGHLEVEL_API_KEY` (a PIT, not an API key) + `GOHIGHLEVEL_LOCATION_ID`. |
| Functional checks pass | 1.5 | The skill's specific smoke tests (API reachability, software present, etc.) all return expected results. No 4xx/5xx unhandled. |
| CORE_UPDATES.md applied surgically | 1.0 | Only labeled sections added to labeled core files. No SOUL.md / IDENTITY.md / USER.md / HEARTBEAT.md touched unless this skill's CORE_UPDATES.md explicitly labels them. |
| Skill-specific QC items above all checked | 1.5 | Every checkbox in the skill-specific sections of THIS QC.md is ticked. |
| Security | 0.5 | No PIT or other secret leaked into chat / logs / commits / .md files. Secrets file chmod 600. |
| Owner-facing confirmation message sent | 0.5 | The final summary was sent in plain English with structure: "Skill NN active. Anything pending your attention: [list]." |

### Loop-until-passing rule

If score < 8.5:
1. Identify the lowest-scoring section
2. Apply the smallest fix possible
3. Re-run only the failed checks
4. Re-score
5. After 5 loops, STOP and escalate to owner via Telegram with: which sections failed, what you tried, what's blocking

### Bundled `qc-skill-NN.sh`

If a `qc-skill-NN.sh` script exists in this skill folder, run it. Exit 0 is required in addition to the rubric score. The script catches mechanical items the rubric assumes (file modes, env-var format, network reachability).

### Self-audit before declaring done

Recite in your work log:
1. INSTALL-CONTRACT.md acknowledged for this skill: ✓ / ✗
2. All .md files read before execution: ✓ / ✗
3. INSTALL.md step order followed verbatim: ✓ / ✗
4. QC rubric score: __/10 (≥ 8.5 to pass)
5. Bundled qc-*.sh exited 0: ✓ / ✗ / N/A
6. No shortcuts taken (no `--force`, etc.): ✓ / ✗
7. Owner confirmation message sent: ✓ / ✗

If any answer is ✗, this skill is NOT done. Loop back.
