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

6. **scripts/update-skills.sh** - Update:
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

Every Sunday at 2 AM, the client's machine runs `scripts/update-skills.sh`. It:
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

## Rules for AI Agents Working on This Repo

1. **Always work in isolated /tmp clones.** Never modify ~/clawd directly for repo work.
2. **Never break the other skills.** Test that unmodified skills still have valid file structures.
3. **Preserve the TYP check block** at the top of every INSTALL.md.
4. **No em dashes** in any file. Use commas, periods, or colons instead.
5. **Write for a 60+ audience.** Numbered steps, plain English, patient tone.
6. **Verify Python syntax** if you modify any .py file: `python3 -c "import ast; ast.parse(open('file.py').read())"`
7. **Verify JSON syntax** if you modify openclaw.json: `python3 -c "import json; json.load(open('file.json'))"`
8. **Update BOTH repos** (openclaw-onboarding and openclaw-onboarding-vps) unless the change is platform-specific.
9. **Never trigger a gateway restart.** Always instruct the user to type /restart in Telegram.
10. **Commit messages must be descriptive.** Not "update files" but "Add Skill 31 (Upgraded Memory System), fix Skill 23 options skip"

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

## Two Repos, Same Content (Mostly)

| Repo | Platform | Differences |
|------|----------|-------------|
| trevorotts1/openclaw-onboarding | Mac Mini | Paths use ~/Downloads/..., ~/clawd/ |
| trevorotts1/openclaw-onboarding-vps | VPS/Docker | Paths use /data/..., may have Docker-specific steps |

Both repos must stay in sync. When you push to one, push to the other.
