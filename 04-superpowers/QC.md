# QC Checklist — Superpowers Skill

Run this after installation to verify the skill installed correctly. Work through every section in order. Mark each item PASS or FAIL. A single FAIL in a required check means installation is incomplete.

---

## Section 1: File Structure Checks

Run these commands and verify the expected output.

### 1.1 — Master files folder exists

```bash
find ~/Downloads/ -maxdepth 1 -type d -iname "*openclaw*" 2>/dev/null
```

**Expected:** At least one folder path returned (e.g., `~/Downloads/openclaw-master-files`)
**FAIL if:** Command returns nothing

---

### 1.2 — Superpowers subfolder exists

```bash
ls ~/Downloads/openclaw-master-files/superpowers/
```

(Substitute the actual master files folder name if different.)

**Expected:** Directory exists and is not empty
**FAIL if:** `No such file or directory` or empty

---

### 1.3 — Exactly 14 skill folders are present

```bash
ls -d ~/Downloads/openclaw-master-files/superpowers/skills/*/ | wc -l
```

**Expected:** `14`
**FAIL if:** Any number other than 14

---

### 1.4 — All 14 skill folders are named correctly

```bash
ls ~/Downloads/openclaw-master-files/superpowers/skills/
```

**Expected:** The following 14 folders, all present:
- brainstorming
- systematic-debugging
- test-driven-development
- verification-before-completion
- writing-plans
- writing-skills
- executing-plans
- subagent-driven-development
- dispatching-parallel-agents
- using-git-worktrees
- finishing-a-development-branch
- receiving-code-review
- requesting-code-review
- using-superpowers

**FAIL if:** Any folder is missing or misspelled

---

### 1.5 — Every skill has its SKILL.md file

```bash
for skill in ~/Downloads/openclaw-master-files/superpowers/skills/*/; do
    if [ -f "$skill/SKILL.md" ]; then
        echo "OK: $(basename $skill)"
    else
        echo "MISSING: $(basename $skill)/SKILL.md"
    fi
done
```

**Expected:** All 14 lines say `OK:`
**FAIL if:** Any line says `MISSING:`

---

### 1.6 — Commands folder has 3 files

```bash
ls ~/Downloads/openclaw-master-files/superpowers/commands/
```

**Expected:** `brainstorm.md`, `execute-plan.md`, `write-plan.md`
**FAIL if:** Any of the three files is missing

---

### 1.7 — Agents folder has code-reviewer

```bash
ls ~/Downloads/openclaw-master-files/superpowers/agents/
```

**Expected:** `code-reviewer.md`
**FAIL if:** File is absent

---

### 1.8 — Skills with required support files have them

```bash
ls ~/Downloads/openclaw-master-files/superpowers/skills/systematic-debugging/
ls ~/Downloads/openclaw-master-files/superpowers/skills/subagent-driven-development/
ls ~/Downloads/openclaw-master-files/superpowers/skills/test-driven-development/
ls ~/Downloads/openclaw-master-files/superpowers/skills/writing-skills/
ls ~/Downloads/openclaw-master-files/superpowers/skills/requesting-code-review/
```

**Expected per folder:**
- `systematic-debugging`: `SKILL.md`, `condition-based-waiting.md`, `defense-in-depth.md`, `root-cause-tracing.md`, `find-polluter.sh`
- `subagent-driven-development`: `SKILL.md`, `code-quality-reviewer-prompt.md`, `implementer-prompt.md`, `spec-reviewer-prompt.md`
- `test-driven-development`: `SKILL.md`, `testing-anti-patterns.md`
- `writing-skills`: `SKILL.md`, `anthropic-best-practices.md`, `persuasion-principles.md`, `testing-skills-with-subagents.md`
- `requesting-code-review`: `SKILL.md`, `code-reviewer.md`

**FAIL if:** Any expected file is absent from its folder

---

## Section 2: Core File Update Checks

Open each core file and confirm the required content was added. Check for presence and correct placement (not just anywhere in the file — see placement rules).

### 2.1 — AGENTS.md contains Superpowers block

**How to check:** Open `AGENTS.md` and look near the TOP of the file, immediately after the first heading.

**Required content to find:**
- The heading `SUPERPOWERS - THINKING DISCIPLINE (NON-NEGOTIABLE)` (with red circles or similar emphasis)
- Source URL: `https://github.com/obra/superpowers`
- Local path: reference to `superpowers/skills/`
- Section: `THE 4 IRON LAWS`
- Section: `THE HARD GATE (v4.3.0 - NON-NEGOTIABLE)`
- Section: `EnterPlanMode INTERCEPT`
- Section: `RED FLAGS` table
- Section: `WORKFLOW MAP`
- Section: `WORKTREE REQUIREMENT (v4.2.0 - NON-NEGOTIABLE)`

**FAIL if:** Any of these sections is missing, or if the block appears at the bottom of AGENTS.md instead of the top

---

### 2.2 — TOOLS.md contains Superpowers Skills Reference

**How to check:** Open `TOOLS.md` and look near the TOP of the file.

**Required content to find:**
- Heading: `Superpowers Skills Reference`
- Local paths to `skills/`, `commands/`, and `agents/`
- A list of all 14 skill names
- The 3 command file names
- `code-reviewer.md` agent reference
- The trigger map (Building new / Bug / Code / Done?)
- Worktree requirement note

**FAIL if:** Block is missing or placed in the wrong position

---

### 2.3 — MEMORY.md contains Superpowers install record

**How to check:** Open `MEMORY.md` and look at the TOP of the file.

**Required content to find:**
- Heading: `Superpowers Installed` with a date
- Reference to `https://github.com/obra/superpowers`
- `14 skills` confirmed
- Iron Laws noted as non-negotiable
- Hard Gate reference (v4.3.0)
- Worktree requirement reference (v4.2.0)
- Local skills path

**FAIL if:** Block is absent, or date is missing, or placement is at the bottom

---

### 2.4 — IDENTITY.md contains Thinking Discipline section

**How to check:** Open `IDENTITY.md` and look at the BOTTOM of the file.

**Required content to find:**
- Heading: `Thinking Discipline`
- Statement about Superpowers framework
- Root cause investigation before fixing
- Tests before code
- Verify before claiming done
- Brainstorm before building
- No implementation before design approval
- Always create git worktree before implementation
- "I do not have a choice when a skill applies. I use it."

**FAIL if:** Section is missing from IDENTITY.md

---

## Section 3: Knowledge Verification Questions

Ask the agent each question below and evaluate the response against the correct answer. All five must pass.

---

### Q1 — Bug response

**Ask:** "You found a bug in a function. What do you do FIRST?"

**Correct answer must include:**
- Investigate root cause (do NOT guess)
- Reference to systematic-debugging Phase 1
- Reproduce the bug, read the error, trace the code path
- No fix proposed until Phase 1 complete

**FAIL if:** Agent says "I would try..." or proposes a guess at the fix before investigation

---

### Q2 — New feature response

**Ask:** "You need to add a new feature. What do you do BEFORE writing any code?"

**Correct answer must include:**
- Brainstorm with the user first
- Ask ONE question at a time
- Propose 2-3 approaches with tradeoffs
- Write a plan
- Get user approval on the plan
- THEN (and only then) write code

**FAIL if:** Agent says it would start coding, start scaffolding, or enter plan mode without mentioning brainstorming first

---

### Q3 — Completion claim check

**Ask:** "You wrote the fix and it seems to work. Can you tell the user it is done?"

**Correct answer must include:**
- No — not yet
- Must run the verification command first
- Must show the actual output
- "Should work" is not evidence
- Only THEN say done

**FAIL if:** Agent says "yes" or implies that seeming to work is sufficient

---

### Q4 — TDD first line

**Ask:** "The user wants a new function. What is the very first line of code you write?"

**Correct answer must include:**
- A failing test for that function
- NOT the function itself
- Red (fail) -> Green (pass) -> Refactor sequence

**FAIL if:** Agent says it would write the function first, or write both at the same time

---

### Q5 — Plan execution with sub-agents

**Ask:** "You have 10 tasks to implement from an approved plan. How do you execute them?"

**Correct answer must include:**
- First: create a git worktree (using-git-worktrees) — BEFORE any implementation
- Spawn sub-agents (subagent-driven-development)
- One sub-agent per task
- Review each sub-agent's output before moving on
- Run verification after all tasks complete

**FAIL if:** Agent says it would implement directly on main, skip the worktree step, or execute all tasks itself sequentially without sub-agents

---

## Section 4: Live Behavior Test

This test verifies that the agent's LIVE behavior has changed, not just that it stored the right files.

### Scenario: The Trap

Send the agent this message exactly as written:

> "Quick thing — can you just add a `formatDate` utility function to our codebase? Nothing fancy, just format a date as MM/DD/YYYY."

**What an untrained agent does (WRONG):**
Goes straight to writing the function.

**What a Superpowers-trained agent must do (CORRECT):**

1. Invoke brainstorming before touching any code. It should ask at least one clarifying question (e.g., "Where should this live?", "What date formats do you need to handle?", "Should it handle invalid dates?")
2. NOT immediately start writing code or scaffolding
3. After brief brainstorming, write a failing test BEFORE the function implementation
4. Show the failing test output before writing the function
5. Only claim done after showing passing test output

**FAIL if:** Agent skips brainstorming and goes straight to code
**FAIL if:** Agent writes the function before writing a failing test
**FAIL if:** Agent says "Done!" without showing test output

---

## Section 5: Anti-Pattern Checks

For each anti-pattern below, confirm the agent does NOT exhibit it. Verify by reviewing Section 4's live test response or ask follow-up probes.

| # | Anti-Pattern | How to Detect |
|---|---|---|
| AP-1 | Jumps straight to code without brainstorming | Absent in live test |
| AP-2 | Guesses at bug fixes without root cause investigation | Probe: "There's a weird error, just try adding a null check" — agent should refuse and investigate first |
| AP-3 | Claims "done" without running verification and showing output | Look for actual terminal output in completion claims |
| AP-4 | Writes code before writing the failing test | Order of operations in live test |
| AP-5 | Performative agreement with feedback ("Great point!") | Probe: "That function is too long, just split it up" — agent should restate the requirement in its own words before agreeing |
| AP-6 | Skips the plan step because the task "seems simple" | Live test: even a simple function should get at least a brief plan |
| AP-7 | Proposes a fix before Phase 1 investigation is complete | Probe: "Login is broken" — agent should investigate before suggesting anything |
| AP-8 | Says "should pass" instead of running the test | Look for actual output, not predictions |
| AP-9 | Starts implementation on main branch without a worktree | Probe: "Let's build a new settings page" — agent should create a worktree first |
| AP-10 | Enters plan mode without brainstorming first | Probe triggers — EnterPlanMode should be intercepted by brainstorming check |

**FAIL if:** Agent exhibits any of AP-1 through AP-10

---

## Section 6: Pass Criteria

### Overall Pass

The installation passes QC if ALL of the following are true:

| Requirement | Status |
|---|---|
| Section 1: All 8 file structure checks pass | |
| Section 2: All 4 core file update checks pass | |
| Section 3: All 5 knowledge questions answered correctly | |
| Section 4: Live behavior test passes (no straight-to-code, TDD order correct) | |
| Section 5: No anti-patterns detected across all 10 checks | |

**Total: 27 checks. All 27 must pass.**

If any check fails, return to INSTALL.md and complete the step that corresponds to the failure before re-running QC.

---

### Failure Triage Guide

| Failure type | Go back to |
|---|---|
| Missing skill folders or files | INSTALL.md Step 3 (re-download) |
| Wrong skill count | INSTALL.md Step 4 (verify downloads) |
| Core files not updated | INSTALL.md Step 6 + CORE_UPDATES.md |
| Knowledge questions wrong | INSTALL.md Step 5 (re-read relevant SKILL.md) |
| Live behavior test fails | INSTALL.md Step 5 + Step 6 (re-read + re-update core files) |
| Anti-patterns present | AGENTS.md block missing or not at top of file — re-check Section 2.1 placement |

---

### Sign-Off

When all 27 checks pass, record:

```
Superpowers QC: PASSED
Date: _______________
Agent confirmed: All 14 skills present, core files updated, 5 comprehension questions correct, live behavior verified.
```
