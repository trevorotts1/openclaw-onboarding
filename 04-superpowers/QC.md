# QC Checklist: Superpowers

## 1. Purpose
Enables disciplined software-development behavior by installing the Superpowers framework and its 14 thinking skills.

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md`, `INSTALL.md`, `USAGE.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, the full reference `.md`, and the `.skill` package.
- [ ] TYP and BYUP are already installed before this skill is installed.
- [ ] The Superpowers folder exists inside the master files folder, and the expected repository or downloaded skill files are present.
- [ ] At minimum, the 14 documented skill folders or equivalent downloaded `SKILL.md` files exist under the Superpowers install path.
- [ ] No extra executable script is required in this wrapper; if git/curl helper scripts were created during install, verify they are executable.

## 3. Dependency Checks
- [ ] Git is available for the preferred clone method, or curl/browser download fallback is available.
- [ ] The master files folder under ~/Downloads is writable.
- [ ] Network access exists to `https://github.com/obra/superpowers` or the raw GitHub URLs.
- [ ] Workspace core files are writable for the lean summary updates required by `CORE_UPDATES.md`.

## 4. Key Detection
- [ ] No API key is required for Superpowers installation itself.
- [ ] Smart detection should verify prerequisites instead: TYP present, BYUP present, master files folder present, and Superpowers files downloaded.
- [ ] QC fails if the installer blocks on a missing secret for this skill.

## 5. Functional Checks
- [ ] Ask the agent to name the 4 Iron Laws. Expected: investigate first, failing test first, proof before done, evidence before claims.
- [ ] Ask for the workflow for a new feature. Expected: brainstorm, plan, approval, then execution.
- [ ] Verify the installed Superpowers path contains all 14 skill names, especially `brainstorming`, `systematic-debugging`, `test-driven-development`, and `using-git-worktrees`.
- [ ] Ask the agent to start coding a vague feature request and verify it asks clarifying questions or plans first instead of immediately coding.
- [ ] Verify the agent understands that `using-git-worktrees` is required before `subagent-driven-development` and `executing-plans`.

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
