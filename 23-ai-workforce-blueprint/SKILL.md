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
  - "start AI workforce blueprint"
  - "build my back office"
  - "build my company"
  - "create my AI company structure"
version: 1.1.0
---

## MANDATORY - Teach Yourself Protocol (TYP)

**Before using this skill, complete the Teach Yourself Protocol (Skill 01) on this folder.**

Required read order:
1. SKILL.md (this file)
2. ai-workforce-blueprint-full.md - the complete blueprint document
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
  marketing-dept/
    [role-folder]/
      00-START-HERE.md
      01-[how-to-file].md
      02-[how-to-file].md
      good-examples.md
      bad-examples.md
      tools.md
  sales-dept/
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
- User says "start AI workforce blueprint" or "build my back office"
- User says "build my company" or "create my AI company structure"

## The 3-Option Flow (New)

When triggered, the skill now presents 3 clear options:

**Option A - Full Automated Build** 🚀
- AI interviews you about your business
- AI builds everything automatically based on your answers
- Most personalized results
- Best for: First-time setup

**Option B - Manual Build** 🛠️
- You build everything yourself using the blueprint
- Read ai-workforce-blueprint-full.md for step-by-step guidance
- Best for: Hands-on users who want full control

**Option C - Audit / Resume Mode** 🔍
- Scans existing workforce folder
- Adds missing files, wires personas if available
- Never overwrites existing content
- Best for: Returning users, adding personas later

## Pre-Built Departments Available

The skill comes with 10 pre-configured departments:

• **marketing-dept** - Content, ads, social media, email campaigns
• **sales-dept** - Converting leads to customers
• **billing-dept** - Invoicing, payments, financial tracking
• **customer-support-dept** - Helping existing clients
• **operations-dept** - Day-to-day business running
• **creative-dept** - Graphics, video, content creation
• **hr-people-dept** - Team management, hiring
• **legal-compliance-dept** - Contracts, regulations
• **it-tech-dept** - Software, websites, infrastructure
• **master-orchestrator-dept** - Routes all work (always included)

You choose: Keep all / Keep some + remove others / Keep all + add custom / Start from scratch

## Files in This Skill

| File | Purpose |
|------|---------|
| SKILL.md | This file - the trigger and overview |
| INSTALL.md | How to install and run this skill |
| INSTRUCTIONS.md | Step-by-step walkthrough of the build process |
| EXAMPLES.md | Real examples of good department/role structures |
| CORE_UPDATES.md | What to add to your core memory files after install |
| ai-workforce-blueprint-full.md | The complete blueprint document |
| scripts/build-workforce.py | Automated scaffold script - creates all folders and starter files |

## How to Use

**Option A - Automated (recommended):**
When triggered, execute INSTALL.md beginning at Phase 5. Run `scripts/build-workforce.py` which walks the user through questions and creates everything.

**Option B - Manual:**
Read `ai-workforce-blueprint-full.md` and follow the step-by-step instructions to build the structure.

**Option C - Resume:**
If a workforce structure already exists, run the scaffold script in audit mode. It scans existing folders and fills gaps without overwriting.

---

## Connection to Book To Persona & Coaching & Leadership System (Skill 22)

**⚠️ PRE-FLIGHT CHECK: Skill 23 requires Skill 22 to be FULLY installed first.**

Before running Skill 23, the system checks for the `coaching-personas` Gemini Vector Database. If not found:
- STOP and display: "Install Skill 22 (Book-to-Persona) first"
- Do not proceed with workforce build

**Skill 23 works independently once Skill 22 is verified.** If Skill 22 is not installed, the workforce blueprint builds clean with no persona references. Personas are an enhancement, not a requirement.

**Pre-flight check in action:**
```bash
# This runs automatically at the start of Skill 23
if qmd status 2>/dev/null | grep -q "coaching-personas"; then
  echo "✅ Skill 22 verified - proceeding with workforce build"
else
  echo "❌ STOP: Install Skill 22 (Book-to-Persona) first"
  exit 1
fi
```

**Re-detection after questions:**
After all departments/roles are defined, Skill 23 re-checks for coaching-personas. If found during the build, persona wiring runs automatically.

**These two skills work together automatically when both are present:**

**If Skill 22 (book-to-persona) is installed:**
- The scaffold script detects the `coaching-personas` Gemini Vector Database
- Every department folder gets a `governing-personas.md` file
- Every role folder gets its own `governing-personas.md` for role-specific tasks
- Every `00-START-HERE.md` gets a Governing Personas section with Gemini Engine query instructions
- **Auto-runs Gemini Engine update after wiring:** `python3 ~/clawd/scripts/gemini-indexer.py`
- Agents know exactly which persona methodology to follow

**If Skill 22 is NOT installed:**
- Structure builds clean with no persona references
- Install Skill 22 later, then re-run the scaffold in Option C (audit mode)
- It will detect personas and wire them in retroactively without touching existing files

**Cross-reference path:** `~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/PERSONA-ROUTER.md`
