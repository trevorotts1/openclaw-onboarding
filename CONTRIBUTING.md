# Contributing to OpenClaw Onboarding

Rules for anyone (human or AI) making changes to this repository.

---

## When Adding a New Skill

Every time a new skill folder is added, ALL of these files must be updated:

### Required Updates

1. **Create the skill folder** with the standard 7-file structure:
   - SKILL.md (overview, prerequisites, reading order)
   - INSTALL.md (step-by-step installation with TYP check block at top)
   - INSTRUCTIONS.md (day-to-day usage after install)
   - EXAMPLES.md (real command examples with expected output)
   - CORE_UPDATES.md (exact text to add to AGENTS.md, TOOLS.md, MEMORY.md)
   - [skill-name].skill (metadata/compressed package)
   - QC.md (verification checklist) - optional but recommended

2. **Start Here.md** - Update these sections:
   - Total skill count (e.g., "Install all 31 skills" becomes "Install all 32 skills")
   - Wave assignment table (which wave does this skill belong to?)
   - Install order list
   - Final completion message skill count
   - Sequential fallback skill count

3. **install.sh** - Update:
   - All "X skills" count references
   - Skill download count in progress messages

4. **README.md** - Update:
   - Skill count in description
   - "What's New" section with the new skill

5. **CHANGELOG.md** - Add entry:
   - Version bump
   - What skill was added and what it does
   - Any dependencies on other skills

6. **update-skills.sh** (repo root — NOT `scripts/update-skills.sh`, which is a
   retired, loud-failing shim) - Update:
   - Skill number range in the `seq` command (e.g., `seq -w 1 31` becomes `seq -w 1 32`)

### Verification After Adding

```bash
# Count skill folders (excluding archived)
ls -d [0-9]* | grep -v ARCHIVED | wc -l

# Verify Start Here.md matches
grep -c "XX skills" "Start Here.md"

# Verify install.sh matches
grep -c "XX skills" install.sh
```

---

## When Modifying an Existing Skill

1. **CHANGELOG.md** - Add entry describing what changed
2. **If skill count changed** (skill removed/added) - follow "Adding a New Skill" checklist above
3. **If INSTALL.md changed** - verify the TYP check block is still at the top
4. **If CORE_UPDATES.md changed** - note in CHANGELOG that existing users should re-run core updates
5. **Never modify protected client files**: AGENTS.md, MEMORY.md, TOOLS.md, USER.md, SOUL.md, IDENTITY.md, HEARTBEAT.md in the client workspace. Only add to them via CORE_UPDATES.md instructions.

---

## When Pushing Updates

### CHANGELOG.md Format

Every push that changes skill behavior must have a CHANGELOG entry:

```markdown
## [vX.Y.Z] - Month Day, Year

### What Changed
- Brief description of what changed and why

### Migration Notes (if applicable)
- What existing users need to do
- Whether the weekly update script handles it automatically
- Risk level: LOW / MEDIUM / HIGH

### Files Changed
- List of files modified
```

### How the Weekly Update Script Works

Every Sunday at 3 AM, the client's machine runs the REPO-ROOT `update-skills.sh`
(never `scripts/update-skills.sh` — that path is a retired, loud-failing shim). It:
1. Fetches CHANGELOG.md from GitHub
2. Compares the remote version against the local installed version
3. Generates a gap report and impact analysis
4. Surfaces recommendations to the user
5. Does NOT auto-apply changes. Waits for user approval.

**The CHANGELOG.md is the source of truth for what changed.** If you push changes without a CHANGELOG entry, the update script will not know what changed and cannot generate proper impact reports.

### Version Numbering

- **PATCH** (v4.0.1 to v4.0.2): Bug fixes, typo corrections, no new skills
- **MINOR** (v4.0.x to v4.1.0): New skill added, significant skill rewrite
- **MAJOR** (v4.x.x to v5.0.0): Breaking changes, architecture shifts, migration required

---

## Release Ceremony Batching (added 2026-08-20 — Recommendation R3, delay audit)

**Never open a PR whose ONLY changes are CHANGELOG.md and/or a version marker.** The
CHANGELOG entry and the version bump ride in the SAME PR as the fix they document —
never a follow-up, standalone release PR.

Why: on 2026-08-19/20, six version tags were cut in ~21 hours (v22.0.51 → v22.0.56),
each demanding a CHANGELOG-entry-then-annotated-tag two-step done as its own PR. That
produced three pure-CHANGELOG PRs (#942, #944, #951), each changing exactly one file,
CHANGELOG.md, and nothing else. PR #944 alone sat 14.4 hours open→merged and blocked
TWO real fixes (#945, #946) behind it in this repo's single-merge-writer serialization
— for a one-line CHANGELOG entry. Separately, main sitting untagged blocked CI guard
G1b on every open PR seven separate times in the same window, because G1b walks main's
whole release history, not any one PR's diff — so the fix has to be structural, not a
rule an agent has to remember. See `CONTROL/DELAY-DIAGNOSIS-FABLE.md` Section 2 D3,
Section 4(b), Section 7 item 3 for the full measurement.

**The mechanism (both halves are load-bearing — use both, do not improvise a third
way):**

1. **Bundle the bump into your fix branch.** Inside the branch that already carries
   your fix, run:
   ```
   scripts/bundle-release-in-branch.sh vX.Y.Z "Short description for CHANGELOG"
   ```
   This rolls all 10 version markers (`scripts/bump-version.sh`) and prepends the
   CHANGELOG entry, but does **not** commit, tag, or push — review with `git diff`,
   fold it into your fix commit (or a second commit in the same PR — either is fine,
   the constraint is "same PR"), then push as usual.
2. **The tag is cut automatically on merge — do nothing further.**
   `.github/workflows/auto-tag-on-merge.yml` runs on every push to `main` and, the
   instant it sees `/version` differ from the previous commit, cuts and pushes the
   annotated tag itself via `scripts/push-version-tag.sh`. No agent has to run it by
   hand, so "someone forgot to tag it" can no longer happen.
3. **CI enforces #1.** `.github/workflows/release-ceremony-batching-guard.yml`
   (`scripts/check-no-standalone-release-pr.py`) fails any PR whose entire diff sits
   inside {CHANGELOG.md} ∪ {the files in `scripts/version-markers.json`} — i.e. a PR
   that carries zero code. If you hit this red, you opened exactly the kind of PR this
   rule exists to stop; fold your CHANGELOG entry into the PR that carries the fix
   instead of arguing with the gate.

`scripts/release.sh` (bump + CHANGELOG + commit + tag + push in one shot) remains the
right tool for a deliberate, no-PR release cut directly on `main` — it is unaffected by
this rule, which only concerns fix PRs.

---

## Rules for AI Agents Working on This Repo

1. **Always work in isolated /tmp clones.** Never modify ~/clawd directly for repo work.
2. **Never break the other skills.** Test that unmodified skills still have valid file structures.
3. **Preserve the TYP check block** at the top of every INSTALL.md.
4. **No em dashes** in any file. Use commas, periods, or colons instead.
5. **Write for a 60+ audience.** Numbered steps, plain English, patient tone.
6. **Verify Python syntax** if you modify any .py file: `python3 -c "import ast; ast.parse(open('file.py').read())"`
7. **Verify JSON syntax** if you modify openclaw.json: `python3 -c "import json; json.load(open('file.json'))"`
8. **Use the unified repo** (openclaw-onboarding) for all changes — platform-specific files live in platform/mac/ and platform/vps/ overlays within this single repo.
9. **Master agent CAN trigger `openclaw gateway restart` autonomously when a config edit requires it.** Sub-agents CANNOT — they must return "restart needed" and let the master orchestrator decide. (Rule updated 2026-05-23 — was previously "never restart", lifted after restart safety improvements.)
10. **Commit messages must be descriptive.** Not "update files" but "Add Skill 31 (Upgraded Memory System), fix Skill 23 options skip"
11. **Never open a standalone CHANGELOG-only or version-bump-only PR.** See "Release
    Ceremony Batching" above — bundle the bump into your fix PR with
    `scripts/bundle-release-in-branch.sh`; the annotated tag is cut for you
    automatically on merge. CI (`release-ceremony-batching-guard.yml`) will reject a
    PR that violates this. (Rule added 2026-08-20 — Recommendation R3, delay audit.)

---

## Repo Structure

```
/
  01-teach-yourself-protocol/
  02-back-yourself-up-protocol/
  ...
  31-upgraded-memory-system/
  scripts/
    install.sh (not here, at root)
    setup-weekly-update.sh
    update-skills.sh
  Start Here.md
  install.sh
  README.md
  CHANGELOG.md
  CONTRIBUTING.md (this file)
  MIGRATION.md
```

---

## Unified Repo — One Codebase, Two Platforms

| Directory | Platform | Notes |
|-----------|----------|-------|
| trevorotts1/openclaw-onboarding (root) | Mac + VPS | Unified install.sh + update-skills.sh auto-detect platform |
| platform/mac/ | Mac Mini | Mac-specific docs and overrides (paths use ~/...) |
| platform/vps/ | VPS/Docker | VPS-specific docs and overrides (paths use /data/...) |

The openclaw-onboarding-vps repo is archived. All work goes here.
