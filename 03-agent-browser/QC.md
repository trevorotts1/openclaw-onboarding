# QC Checklist: Agent Browser

## 1. Purpose
Enables precise ref-based browser automation through the `agent-browser` CLI as the preferred onboarding browser tool.

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md` and `INSTALL.md`.
- [ ] If the source-of-truth operational skill exists at `~/clawd/skills/agent-browser/SKILL.md`, it is readable and treated as authoritative.
- [ ] `agent-browser` is discoverable in PATH: `command -v agent-browser`.
- [ ] If installation was needed, global npm install completed without permission errors and `agent-browser install` finished successfully.
- [ ] The `agent-browser` executable is runnable; this is the required executable for this skill.

## 3. Dependency Checks
- [ ] Node.js and npm are installed and working.
- [ ] Global npm install permissions are available, or a documented escalation path exists.
- [ ] Browser dependencies required by `agent-browser install` are present.
- [ ] No external API key is required for the basic CLI smoke test.

## 4. Key Detection
- [ ] No API key is required by this onboarding wrapper.
- [ ] Smart detection checks for binary availability, npm global path issues, and whether the authoritative skill doc path exists.
- [ ] QC fails if the installer incorrectly asks for a token just to run the local smoke test.

## 5. Functional Checks
- [ ] Run `agent-browser --help | head -20` and confirm normal help output.
- [ ] Run the documented smoke test: open `https://example.com`, take a snapshot, then close the session.
- [ ] Confirm the snapshot includes stable element refs such as `@e1` or similar ref markers.
- [ ] Verify the agent describes `agent-browser` as the preferred browser automation path, with Playwright only as fallback.
- [ ] If install initially failed due to permissions, verify the failure mode was reported clearly rather than silently skipped.

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
