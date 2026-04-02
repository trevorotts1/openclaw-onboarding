# QC Checklist: GHL Install Pages

## 1. Purpose
Enables browser-based deployment of finished HTML pages into Convert and Flow / GHL funnels or websites using Playwright.

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, the full reference `.md`, and the `.skill` package.
- [ ] Playwright is installed and Chromium has been downloaded successfully.
- [ ] The credential store or persistent-session path exists at the documented location for this repo.
- [ ] The Playwright configuration uses persistent context with the documented session directory and minimum viewport requirements.
- [ ] No standalone script in the skill folder is required; if a local deployment helper was created, confirm it is executable.

## 3. Dependency Checks
- [ ] TYP, BYUP, and GHL setup (skill 05) are already complete.
- [ ] Python 3 and Playwright are installed: `python3 -c "from playwright.sync_api import sync_playwright"` succeeds.
- [ ] Chromium is installed for Playwright: `playwright install chromium` completed successfully.
- [ ] Stored GHL login credentials exist in `~/clawd/secrets/.env` or a persistent browser session exists at `~/.openclaw/playwright-data/ghl-install-pages`.
- [ ] Finished HTML is available, self-contained, and ready to paste.

## 4. Key Detection
- [ ] Search all standard locations for `GHL_EMAIL` and `GHL_PASSWORD`, while also allowing the documented skip path if SSO or manual login is used.
- [ ] Also search for existing persistent session data at `~/.openclaw/playwright-data/ghl-install-pages` before declaring credentials missing.
- [ ] Recognize broader GHL credential aliases from setup skill if needed for account context: `GHL_API_KEY`, `GHL_PIT`, `GOHIGHLEVEL_API_KEY`, and `GHL_LOCATION_ID`.
- [ ] QC fails if the agent hardcodes credentials into a script or ignores an existing reusable session.

## 5. Functional Checks
- [ ] Run the Playwright import verification command and confirm success output.
- [ ] Verify the launch configuration uses `launch_persistent_context()` and **not** `launch()`.
- [ ] Open the GHL dashboard and confirm the agent checks the current sub-account before editing any page.
- [ ] Verify the agent can describe the nested iframe requirement and that code insertion happens inside the correct builder context.
- [ ] Confirm the agent ends with preview/report behavior and does **not** publish without explicit user approval.

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
