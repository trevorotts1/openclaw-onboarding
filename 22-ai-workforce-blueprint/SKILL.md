---
name: ai-workforce-blueprint

description: Build the folder and file system that turns your AI agent into a trained workforce. Creates department folders, role folders, SOPs, Start Here files, routing logic, and all knowledge architecture files your AI needs to operate without babysitting.
triggers:
  - "build my AI workforce"
  - "create department folders"
  - "set up my AI company structure"
  - "AI workforce blueprint"
  - "build department structure"
  - "create my AI org chart"
  - "scaffold my AI workspace"
version: 1.0.0
author: trevorotts1
---

## MANDATORY - Teach Yourself Protocol (TSP)

**Before using this skill, complete the Teach Yourself Protocol (Skill 01) on this folder.**

Required read order:
1. SKILL.md (this file)
2. ai-workforce-blueprint-full.md - the complete 66,819-character blueprint document
3. INSTRUCTIONS.md - build options A, B, and C explained
4. EXAMPLES.md - good and bad department/role structure examples
5. INSTALL.md - setup and dependencies
6. CORE_UPDATES.md - what to add to your workspace files

Do NOT run the scaffold script or create any folders before completing all 6 reads.
Do NOT claim the skill is installed until CORE_UPDATES.md has been applied.

---

# AI Workforce Blueprint Skill

## What This Is

This skill builds the folder and file system that turns your AI agent into a trained workforce.

Without this system, your AI forgets between sessions, gives inconsistent results, and you spend all day repeating yourself. With this system, your AI knows which department owns every task, which role handles it, and exactly which file tells it how to do the work.

**This is completely separate from the Coaching Personas Matrix.** Personas govern HOW an agent thinks and communicates. This blueprint governs WHERE the agent works and WHAT it does. They work together but neither requires the other.

## What It Creates

When you run this skill, your AI builds:

```
[your-workspace]/
  sales-dept/
    [role-folder]/
      00-START-HERE.md
      01-[how-to-file].md
      02-[how-to-file].md
      good-examples.md
      bad-examples.md
      tools.md
  marketing-dept/
    [role-folder]/
      ...
  ops-dept/
  finance-dept/
  coaching-dept/
  leadership-dept/
  universal-sops/
    00-ROUTING.md
    tools.md
```

## When to Trigger This Skill

- User wants to set up their AI company structure
- User says "build my departments" or "scaffold my workspace"
- User is starting a new business or reorganizing an existing one
- User wants their AI to stop forgetting and start operating consistently

## Files in This Skill

| File | Purpose |
|------|---------|
| SKILL.md | This file - the trigger and overview |
| INSTALL.md | How to install and run this skill |
| INSTRUCTIONS.md | Step-by-step walkthrough of the build process |
| EXAMPLES.md | Real examples of good department/role structures |
| CORE_UPDATES.md | What to add to your core memory files after install |
| ai-workforce-blueprint-full.md | The complete 66,819-character blueprint document |
| scripts/build-workforce.py | Automated scaffold script - creates all folders and starter files |

## How to Use

**Option A - Automated (recommended):**
Tell your AI: "Build my AI workforce structure. Use the blueprint."
The AI runs `scripts/build-workforce.py` which walks you through questions and creates everything.

**Option B - Manual:**
Read `ai-workforce-blueprint-full.md` and follow the step-by-step instructions to build your own structure.

**Option C - Resume:**
If you already started a structure, tell your AI: "Resume my AI workforce build."
The AI audits your existing folders and fills gaps.

---

## Connection to Coaching Personas Matrix (Skill 21)

These two skills are separate but work together automatically.

**If skill 21 (book-to-persona) is installed:**
- The scaffold script detects the `coaching-personas` QMD collection
- Every department folder automatically gets a `governing-personas.md` file listing which personas govern that department
- Every `00-START-HERE.md` gets a Governing Personas section with QMD query instructions
- Agents in each department know exactly which persona methodology to follow

**If skill 21 is NOT installed:**
- Structure builds clean with no persona references
- Install skill 21 later, then re-run the scaffold in Option C (audit mode)
- It will detect personas and wire them in retroactively without touching existing files

**Cross-reference path:** `~/.openclaw/skills/21-book-to-persona/PERSONA-ROUTER.md`
