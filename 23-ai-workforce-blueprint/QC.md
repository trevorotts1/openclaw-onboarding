# QC Checklist — Skill 23: AI Workforce Blueprint
**Version:** 1.0 | Run this after installation to verify the skill installed correctly.

> You are the agent. Run every check yourself. Do not ask the user to run these checks.
> Mark each item [ ] → [x] as you confirm it. Report the final score at the end.

---

## SECTION 1 — File Structure Checks

Verify the skill folder is present and contains all required files.

### 1a. Skill Folder
- [ ] `~/.openclaw/skills/23-ai-workforce-blueprint/` exists
- [ ] `SKILL.md` is present in that folder
- [ ] `INSTALL.md` is present in that folder
- [ ] `INSTRUCTIONS.md` is present in that folder
- [ ] `EXAMPLES.md` is present in that folder
- [ ] `CORE_UPDATES.md` is present in that folder
- [ ] `CHANGELOG.md` is present in that folder
- [ ] `ai-workforce-blueprint-full.md` is present in that folder
- [ ] `scripts/build-workforce.py` is present in that folder
- [ ] `suggested-roles/` subfolder exists with at least 10 department `.md` files
- [ ] `suggested-roles/README.md` is present

**Check command:**
```bash
ls ~/.openclaw/skills/23-ai-workforce-blueprint/
ls ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/
ls ~/.openclaw/skills/23-ai-workforce-blueprint/suggested-roles/ | wc -l
```

### 1b. Blueprint File Integrity
- [ ] `ai-workforce-blueprint-full.md` is at least 60,000 characters (expected: 66,000+)

**Check command:**
```bash
wc -c ~/.openclaw/skills/23-ai-workforce-blueprint/ai-workforce-blueprint-full.md
```

**FAIL if:** File is under 50,000 characters — the copy was truncated. Re-copy the skill folder before using.

### 1c. Script Permissions
- [ ] `scripts/build-workforce.py` is executable

**Check command:**
```bash
ls -la ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/build-workforce.py
```

---

## SECTION 2 — Workforce Structure Checks

Verify the workforce folder was actually built (not just the skill installed).

Set `WORKFORCE_ROOT` to the workspace path reported at the end of installation before running these checks.

### 2a. Top-Level Folders
- [ ] `master-orchestrator-dept/` exists at `$WORKFORCE_ROOT`
- [ ] `universal-sops/` exists at `$WORKFORCE_ROOT`
- [ ] At least one other `-dept` folder exists (sales, marketing, ops, etc.)
- [ ] All department folder names end with `-dept` (no spaces, no uppercase)

**Check command:**
```bash
ls "$WORKFORCE_ROOT" | grep -E "\-dept$"
```

### 2b. Master Orchestrator
- [ ] `master-orchestrator-dept/00-00-Master-Orchestrator-Start-Here.md` exists
- [ ] `master-orchestrator-dept/01-How-to-Route-Work-to-Departments.md` exists
- [ ] `master-orchestrator-dept/02-How-to-Create-Missing-How-To-Files.md` exists

**Check command:**
```bash
ls "$WORKFORCE_ROOT/master-orchestrator-dept/"
```

### 2c. Universal SOPs
- [ ] `universal-sops/00-ROUTING.md` exists
- [ ] `00-ROUTING.md` contains at least 3 department routing entries (not a blank placeholder)

**Check command:**
```bash
ls "$WORKFORCE_ROOT/universal-sops/"
wc -l "$WORKFORCE_ROOT/universal-sops/00-ROUTING.md"
```

### 2d. Department Overviews
- [ ] Every `-dept` folder (except `master-orchestrator-dept`) contains a `00-Department-Overview-*.md` file

**Check command:**
```bash
for dept in "$WORKFORCE_ROOT"/*-dept; do
  name=$(basename "$dept")
  if [ "$name" != "master-orchestrator-dept" ]; then
    count=$(ls "$dept"/00-Department-Overview-*.md 2>/dev/null | wc -l)
    if [ "$count" -eq 0 ]; then
      echo "MISSING Department Overview: $name"
    else
      echo "OK: $name"
    fi
  fi
done
```

### 2e. Role Folder Required Files
Every role folder (depth 3 inside `$WORKFORCE_ROOT`) must have all 6 required files.

- [ ] Every role folder contains `00-Start-Here-*.md`
- [ ] Every role folder contains at least one numbered task file (`01-*.md`)
- [ ] Every role folder contains `good-examples.md` or `*Good-Examples*.md`
- [ ] Every role folder contains `bad-examples.md` or `*Bad-Examples*.md`
- [ ] Every role folder contains `intelligent-routing.md` or `tools.md`

**Check command:**
```bash
# Check for Start Here files
find "$WORKFORCE_ROOT" -mindepth 3 -maxdepth 3 -name "00-Start-Here-*.md" | sort

# Check for Good Examples
find "$WORKFORCE_ROOT" -mindepth 3 -maxdepth 3 -iname "*good-examples*" | sort

# Check for Bad Examples
find "$WORKFORCE_ROOT" -mindepth 3 -maxdepth 3 -iname "*bad-examples*" | sort
```

### 2f. Naming Convention Compliance
- [ ] No folder or file names contain spaces
- [ ] No folder or file names contain uppercase letters (except files that are all-caps like `00-ROUTING.md`)
- [ ] All department folders end with `-dept`
- [ ] All numbered task files use two-digit prefixes (`01-`, `02-`, `10-`, not `1-`)

**Check command:**
```bash
# Find files or folders with spaces
find "$WORKFORCE_ROOT" -name "* *" 2>/dev/null && echo "FAIL: spaces found" || echo "OK: no spaces"
```

---

## SECTION 3 — Core File Update Checks

Verify that AGENTS.md, TOOLS.md, and MEMORY.md were updated per CORE_UPDATES.md.

### 3a. AGENTS.md
- [ ] AGENTS.md contains a section titled `## AI Workforce Blueprint (Installed)`
- [ ] That section includes the skill path `~/.openclaw/skills/23-ai-workforce-blueprint/`
- [ ] That section includes department folder rules (`-dept` naming, required files)
- [ ] That section references the workspace location (not a placeholder `[fill in after build]`)
- [ ] AGENTS.md contains a `## Pending Skill Setup - Check and Remind` section

**Check command:**
```bash
grep -n "AI Workforce Blueprint" ~/clawd/AGENTS.md
grep -n "Pending Skill Setup" ~/clawd/AGENTS.md
```

### 3b. TOOLS.md
- [ ] TOOLS.md contains a section titled `## AI Workforce Blueprint - Scaffold Script`
- [ ] That section includes the script path `~/.openclaw/skills/23-ai-workforce-blueprint/scripts/build-workforce.py`
- [ ] That section mentions Options A, B, and C

**Check command:**
```bash
grep -n "AI Workforce Blueprint" ~/clawd/TOOLS.md
grep -n "build-workforce.py" ~/clawd/TOOLS.md
```

### 3c. MEMORY.md
- [ ] MEMORY.md contains a section titled `## AI Workforce Blueprint (Installed`
- [ ] That section includes the actual workspace path (not a placeholder)
- [ ] That section lists the departments that were created
- [ ] That section references the routing file path

**Check command:**
```bash
grep -n "AI Workforce Blueprint" ~/clawd/MEMORY.md
grep -n "universal-sops" ~/clawd/MEMORY.md
```

### 3d. Core Files Are Lean
- [ ] AGENTS.md does NOT contain the full text of `ai-workforce-blueprint-full.md`
- [ ] MEMORY.md does NOT contain full department SOPs pasted inline
- [ ] Core files contain summaries and file path references only

**Check command:**
```bash
wc -l ~/clawd/AGENTS.md
wc -l ~/clawd/MEMORY.md
```

**FAIL if:** Either file is over 1,000 lines — likely bloated with full docs that should live in the skill folder.

---

## SECTION 4 — Knowledge Verification Questions

Answer these questions from memory. If you cannot answer any of them, the skill was not fully absorbed.

**Q1:** What are the 3 setup options and when should each be used?

Expected answer:
- Option A = Full Automated Interview — AI asks questions, builds everything. Best for first-time setup.
- Option B = Manual Build — user reads the blueprint and builds themselves. Best for hands-on users.
- Option C = Audit/Resume Mode — scans existing folders, fills gaps, never overwrites. Best for returning users.

**Q2:** What 6 files are required in every role folder?

Expected answer: `00-Start-Here-*.md`, numbered task files (`01-`, `02-`...), `intelligent-routing.md`, `good-examples.md`, `bad-examples.md`, `tools.md`

**Q3:** What is the naming rule for all department folders?

Expected answer: lowercase, hyphens, must end with `-dept`. No spaces. No uppercase. (e.g., `sales-dept/`, `marketing-dept/`)

**Q4:** What is the first thing an agent should do when routing any task?

Expected answer: Read `universal-sops/00-ROUTING.md` first. Find the matching department and role. Go to that folder. Do not guess.

**Q5:** What does the Master Orchestrator department do?

Expected answer: Routes all incoming work to the correct department/role. Always created, regardless of which other departments are selected.

**Q6:** What is the relationship between Skill 23 and Skill 22?

Expected answer: Skill 23 requires Skill 22 (Book-to-Persona) as a prerequisite. If Skill 22 is installed, persona wiring runs automatically after the build. If not installed, the workforce builds clean with no persona references. Skill 22 governs HOW an agent thinks; Skill 23 governs WHERE it works and WHAT it does.

**Q7:** What must every `00-Start-Here` file include?

Expected answer: Role Overview, Purpose, Skill Sets to Embody, Experience to Embody, Role-Specific Tech Stack, Tone and Communication Style, KPIs, Boundaries and Constraints, Edge Case Protocol, Knowledge Base Roadmap (When-to Reference Map), Routing Logic.

**Q8:** What is the correct fallback when an agent receives a task that does not match any routing entry?

Expected answer: Ask "What is the end goal of this task?" → Route to the department whose purpose most closely matches → If still unsure, default to `ops-dept/` and let Operations route it further.

- [ ] All 8 questions answered correctly from context (no file lookups required)

---

## SECTION 5 — Live Behavior Test

These tests verify the agent behaves correctly after installation. Run each one and evaluate the response.

### Test 1 — Routing Test
**Prompt:** "Route this task: Write a follow-up email to a lead who went cold."

**Expected behavior:**
- Agent reads `universal-sops/00-ROUTING.md`
- Routes to `sales-dept/` (or `marketing-dept/` depending on structure)
- References the correct role folder and Start Here file
- Does NOT guess or answer from general knowledge without checking the routing file first

**PASS if:** Agent navigates to a specific department/role folder before producing output.
**FAIL if:** Agent answers directly without referencing the workforce structure.

- [ ] PASS / [ ] FAIL

### Test 2 — Department Awareness Test
**Prompt:** "What departments do I have?"

**Expected behavior:**
- Agent lists all `-dept` folders in the workforce root
- Identifies the Master Orchestrator as always present
- Does NOT hallucinate departments that were not built

**PASS if:** Agent lists actual folders from the filesystem.
**FAIL if:** Agent lists generic departments from general knowledge.

- [ ] PASS / [ ] FAIL

### Test 3 — Add Department Test
**Prompt:** "Add a web development department to my workforce."

**Expected behavior:**
- Agent creates `web-development-dept/` folder
- Asks about or proposes roles for that department
- Creates `00-Department-Overview-Web-Development.md` in the new dept folder
- Creates at least one role subfolder with all required files

**PASS if:** Agent builds the correct folder structure without being told the naming rules.
**FAIL if:** Agent creates a folder named `WebDev/` or `web development/` or skips required files.

- [ ] PASS / [ ] FAIL

### Test 4 — Audit Test
**Prompt:** "Audit my AI workforce."

**Expected behavior:**
- Agent scans all dept folders
- Reports what is present and what is missing
- Does NOT overwrite any existing files
- Fills in only genuine gaps

**PASS if:** Agent produces an audit report listing files found and files missing.
**FAIL if:** Agent overwrites existing content or skips the scan entirely.

- [ ] PASS / [ ] FAIL

### Test 5 — Persona Integration Awareness Test
**Prompt:** "Is Skill 22 wired to my workforce?"

**Expected behavior:**
- If Skill 22 IS installed: Agent confirms `governing-personas.md` files exist in dept and role folders
- If Skill 22 is NOT installed: Agent explains it was not detected and instructs user to install Skill 22 then re-run in Option C (audit mode) to wire personas retroactively

**PASS if:** Agent gives a correct, specific answer about the persona wiring status.
**FAIL if:** Agent gives a vague or incorrect answer.

- [ ] PASS / [ ] FAIL

---

## SECTION 6 — Anti-Pattern Checks

These are the most common ways this skill fails. Verify none of these are present.

### Anti-Pattern 1 — Bloated Core Files
- [ ] AGENTS.md does NOT contain the full blueprint document inline
- [ ] MEMORY.md does NOT contain full department SOPs inline
- [ ] Core files contain lean summaries + file paths only

### Anti-Pattern 2 — Wrong Naming
- [ ] No department folder uses a name that doesn't end in `-dept`
- [ ] No role folder has a space in its name
- [ ] No task files are unnumbered (e.g., `qualify-leads.md` instead of `01-qualify-leads.md`)

### Anti-Pattern 3 — Empty Placeholder Files
- [ ] No `00-Start-Here` file contains only a template with `[fill in]` placeholders and no real content
- [ ] No task files contain only a heading and nothing else
- [ ] `00-ROUTING.md` maps to actual departments, not just example entries

### Anti-Pattern 4 — Missing Master Orchestrator
- [ ] `master-orchestrator-dept/` was NOT skipped
- [ ] The Master Orchestrator has all 3 required files (not just the folder)

### Anti-Pattern 5 — Skipped Routing File
- [ ] `universal-sops/00-ROUTING.md` exists and has real routing entries
- [ ] The routing file was NOT skipped or left as a placeholder

### Anti-Pattern 6 — Gateway Restart Triggered Without Permission
- [ ] Agent did NOT run `openclaw gateway restart` autonomously during install
- [ ] If a restart was needed, agent stopped and notified user to type `/restart` in Telegram

### Anti-Pattern 7 — Persona Wiring Run Without Skill 22
- [ ] If Skill 22 is NOT installed, no `governing-personas.md` files were created
- [ ] Agent did NOT fabricate persona references in Start Here files when Skill 22 is absent

### Anti-Pattern 8 — TYP Skipped
- [ ] TYP was confirmed installed before proceeding with Skill 23
- [ ] All 6 required skill files were read before any building began

---

## SECTION 7 — Pass Criteria

### Scoring
Count your checkmarks from Sections 1–6.

| Score | Result |
|-------|--------|
| 95–100% of checks pass | **PASS** — Skill 23 is fully installed and operational |
| 80–94% of checks pass | **CONDITIONAL PASS** — Fix all failing items before using in production |
| Below 80% | **FAIL** — Re-run installation from Phase 1 |

### Minimum Hard Requirements (must ALL pass regardless of overall score)
These items are non-negotiable. If any single one fails, the result is FAIL regardless of total score:

- [ ] `ai-workforce-blueprint-full.md` is 60,000+ characters (not truncated)
- [ ] `master-orchestrator-dept/` exists with all 3 required files
- [ ] `universal-sops/00-ROUTING.md` exists with real routing entries (not blank)
- [ ] AGENTS.md contains the `## AI Workforce Blueprint (Installed)` section
- [ ] MEMORY.md contains the actual workspace path (not `[fill in after build]`)
- [ ] No department folder has spaces or uppercase in its name
- [ ] Every role folder has a `00-Start-Here-*.md` with real content

### Final Report Format

After running all checks, report to the user in this format:

```
AI Workforce Blueprint QC Complete.

Skill folder: [PASS/FAIL]
Workforce structure: [PASS/FAIL]
Core file updates: [PASS/FAIL]
Knowledge verification: [X/8 questions correct]
Live behavior tests: [X/5 passed]
Anti-patterns: [PASS/FAIL — list any found]

Overall: [PASS / CONDITIONAL PASS / FAIL]

Issues found:
- [list any failing items]

Recommended next steps:
- [what to fix, or "None — installation is complete"]
```
