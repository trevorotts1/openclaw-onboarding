# QC Checklist: Vercel Setup

## 1. Purpose
Enables guided Vercel account and token setup with browser-based token creation and API verification, without relying on the Vercel CLI for auth.

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, the full reference `.md`, and the `.skill` package.
- [ ] The installer follows the API-only lock: browser-based account/token creation and API validation, not CLI auth.
- [ ] A secrets file exists and stores `VERCEL_TOKEN` after setup.
- [ ] Lean core file updates reference the Vercel setup docs without exposing the token.
- [ ] No executable helper script is required in the folder; `curl`, `jq`, `node`, and `npm` are the practical command dependencies.

## 3. Dependency Checks
- [ ] `jq` is installed or installable.
- [ ] Node.js and npm are installed for downstream Vercel workflows, even though setup/auth itself is API-driven.
- [ ] `curl` is installed for token verification.
- [ ] A web browser is available for the human-guided account and token creation flow.

## 4. Key Detection
- [ ] Search all standard secret locations in order: `~/clawd/secrets/.env`, `~/.openclaw/openclaw.json` `env.vars`, `~/.openclaw/.env`, `/data/.openclaw/openclaw.json` `env.vars`, `/data/.openclaw/.env`, live environment, and `~/.env`.
- [ ] Primary variable is `VERCEL_TOKEN`; also detect any already-exported `$VERCEL_TOKEN` in the current shell.
- [ ] When a token is found, verify it immediately via `https://api.vercel.com/v2/user` before asking the user to create a new one.
- [ ] QC fails if the installer jumps to CLI login or asks for a new token without validating an existing one first.

## 5. Functional Checks
- [ ] Verify the agent describes the process as a guided conversation and not silent automation of account creation.
- [ ] If `VERCEL_TOKEN` already exists, run the user endpoint and confirm a username is returned, then verify setup short-circuits correctly.
- [ ] If no token exists, verify the instructions send the user to `https://vercel.com/account/tokens` with token name `OpenClaw Agent`, Full Account scope, and no expiration.
- [ ] Verify the token is stored as `VERCEL_TOKEN` in the chosen secrets file and exported to the current shell for immediate verification.
- [ ] Run the final API verification and confirm the returned username is reported as proof of success.

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
