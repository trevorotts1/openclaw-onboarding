# ADD-TO-REPO -- Handoff instructions for the Cowork agent (Skill 41)

This skill is self-contained. The generic install.sh and update-skills.sh loops pick up any numbered
skill folder with no script edits, so it will install and run as-is. A clean, blueprint-compliant
merge still needs the repo-level touches below, none of which are edits to install.sh or
update-skills.sh.

## Placement

1. Put the folder 41-build-with-ai-playbook in the SAME directory that currently holds skills 38, 39,
   and 40 (locate them first; do not assume the repo root). Add it to every repo you maintain, BYTE-IDENTICAL:
   - your Mac mini repo (your own Mac install repo, if you keep one separate),
   - your Mac mini onboarding repo,
   - your VPS onboarding repo.
   The only allowed differences anywhere are inside scripts behind the uname -s branch.
2. Collision check: confirm no 41 folder already exists. If it does, stop and report. Never renumber.

## Before committing

3. Run the Teach Yourself Protocol on the folder (read SKILL.md, then INSTALL.md, INSTRUCTIONS.md,
   CORE_UPDATES.md, EXAMPLES.md, CHANGELOG.md).
4. Run the QC suite: bash scripts/11-run-qc-checklist.sh must report all gates passing, and each
   scripts/qc-*.test.sh must report it bites. Do not commit if any fail.
5. Diff the skill folder across the repos to prove byte-identical parity.
6. Do NOT run the skill's own installer scripts (00 through 04) against the repo. Those run at client
   install time, not when adding the skill to the repo.

## Repo updates

7. Update the README Skill Inventory table and the headline counts in EVERY repo to include skill 41.
8. If you bump the repo version, run scripts/bump-version.sh vX.Y.Z, confirm --check shows all version
   locations agree, fix the prose Current Version line if touched, and cut the matching GitHub Release.
9. Recommended: register the QC gates and their .test.sh in .github/workflows/qc-static.yml, and
   optionally add a dedicated install_skill_41 function in the install sequence.

## Platform note

10. The skill behaves the same on Mac mini and VPS for the actual Build With AI work. The only
    operational difference is on a headless VPS: pre-set MASTER_FILES_DIR or ensure Skill 38's pointer
    exists before running 01-locate, since the interactive prompts need a terminal. See
    references/platform-differences.md.

## Leave untouched

11. Do not touch SOUL.md, IDENTITY.md, USER.md, or HEARTBEAT.md anywhere. The skill only appends to
    AGENTS.md, MEMORY.md, and TOOLS.md, and only at client install time via its own installer.
