---
name: ai-workforce-blueprint

description: The single skill that builds your entire AI company. Interviews you about your business, creates departments, hires department heads as permanent agents, determines which specialists are full-time team members vs on-call, assigns coaching personas using the Act As If Protocol, sets up workspaces with full core files, and generates your company org chart. This is where your AI stops being a chatbot and starts running like a real company.
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
  - "set up my departments"
  - "hire my AI team"
version: 2.0.0
---

## MANDATORY - Teach Yourself Protocol (TYP)

**Before using this skill, complete the Teach Yourself Protocol (Skill 01 - Teach Yourself Protocol) on this folder.**

Required read order:
1. SKILL.md (this file)
2. ai-workforce-blueprint-full.md - the complete blueprint document
3. INSTRUCTIONS.md - interview question framework and dynamic question logic
4. EXAMPLES.md - good and bad department/role structure examples
5. INSTALL.md - setup, workspace creation, and config management
6. CORE_UPDATES.md - what to add to your workspace files

Do NOT run the scaffold script or create any folders before completing all 6 reads.
Do NOT claim the skill is installed until CORE_UPDATES.md has been applied.

---

# AI Workforce Blueprint

## The Philosophy

"The whole point of this system is to BUILD them into running a real company. Not quiz them on shit they don't know. The AI should be the expert that guides them, not a survey that interrogates them."

This skill serves new entrepreneurs and business owners who have never successfully run a company. The AI is their business partner. It leads with knowledge. It suggests answers. It detects when they are stuck and helps them through it. It never uses jargon. It never makes them feel stupid.

**Forbidden terms in client-facing interactions:**
- SOPs (say "step-by-step instructions" or "how things get done")
- Handoffs (say "what this department sends to other departments")
- Tech stack (say "tools you use")
- Permanent agent (never mention)
- Sub-agent (never mention)
- Agent (say "team member" or "specialist" or "director")

## What This Skill Does

This is the SINGLE skill that builds a client's entire AI company. It replaces what used to be three separate skills (Skills 23, 33, and 34) with one unified flow:

1. **Interviews the client** about their business using dynamic, plain-English questions (3-7 per department based on complexity and what the AI already knows)
2. **Creates departments** based on interview answers (could be 5, 17, or 50 - never hardcoded)
3. **Hires department heads** as permanent agents with full workspaces and core files
4. **Determines specialists** - the AI silently decides which roles are full-time team members (permanent agents) vs on-call specialists (spawned when needed). The client never hears these technical terms.
5. **Assigns coaching personas** using the Act As If Protocol and 5-layer alignment check
6. **Sets up workspaces** with inherited files (TOOLS.md, AGENTS.md, USER.md from main) and unique files (SOUL.md, MEMORY.md, HEARTBEAT.md, memory/ folder)
7. **Generates the org chart** (ORG-CHART.md in the CEO workspace)
8. **Creates the Devil's Advocate** in every department automatically
9. **Generates the Command Center config** (departments.json for the dashboard)

## How It Connects to the System

### Skill Pipeline
Skill 22 (Book-to-Persona Coaching Leadership System) builds coaching personas
--> **Skill 23 (AI Workforce Blueprint)** interviews, creates departments, creates agents, assigns personas, generates org chart
--> BlackCEO Command Center displays and manages everything

### What Skill 22 Provides
Skill 22 converts books into persona blueprints. These personas are organized by category:

**12 Domain Tags:** Marketing, Sales, Leadership, Finance, Operations, Communication, Copywriting, Mindset, Productivity/Systems, Coaching, Strategy/Innovation, Personal Development

**6 Perspective Tags:** African American experience, Women's challenges, Men's challenges, Family/relationships, Faith/spirituality, Love/romantic relationships

When Skill 23 assigns personas to agents and tasks, it first filters by category (a marketing task pulls marketing-tagged personas, not finance personas), then runs the 5-layer alignment on those candidates. Tags are stored in persona-categories.json in the coaching-personas folder. This category filtering is how the system efficiently searches 40+ personas (and eventually 1000+) without reading every single blueprint.

### What the Command Center Consumes
The Command Center reads:
- departments.json (which departments exist, their names, emoji, head titles)
- company-config.json (company KPIs, industry, connected systems)
- department-config.json per department (department KPIs, specialist assignments)
- ORG-CHART.md (organizational structure)
- persona-matrix.md (which personas are available and pre-qualified)
- governing-personas.md per role folder (persona matching reference guide, NOT static assignment)
- persona-matching-protocol.md (5-layer runtime persona matching: mission, values, company goals, department goals, task fit)

## Model Requirements

**This skill MUST run on a high reasoning model.** The decisions it makes (department structure, specialist determination, persona alignment) shape the entire company. Wrong choices cascade into everything.

**Approved models:**
- anthropic/claude-opus-4-6
- anthropic/claude-sonnet-4-6
- openrouter/xiaomi/mimo-v2-pro (with thinking enabled)
- google/gemini-3.1-pro-preview
- openai-codex/gpt-5.4

**Forbidden for this skill:**
- moonshot/kimi-k2.5
- google/gemini-3-flash-preview
- google/gemini-3.1-flash-lite-preview

**If the client is on a low reasoning model:**
Say: "For setting up your company, I recommend switching to a model that thinks more deeply so we get the best results. Want me to switch?"

**Research model:** When the AI offers to research industry best practices, it uses openrouter/perplexity/sonar-pro-search.

## The Three Options

When this skill triggers, it ALWAYS presents three options. Never skip this. Never auto-select.

**Option A - Full Interview (recommended)**
The AI interviews you about your business. Asks 3-7 questions per department based on complexity and what it already knows. Builds everything from your answers. Most personalized.

**Option B - Quick Setup (fastest)**
No interview. The AI reads what it already knows from your workspace files plus industry best practices. Proposes a structure. You approve or adjust. Then it builds.

**Option C - Audit / Resume Mode**
For people who already have a workforce set up. Scans what exists, finds gaps, fills them without overwriting anything. Also resumes an interrupted interview.

## The Act As If Protocol

When a persona is selected for a task, the instruction is:

**"Act as if you are [persona name] executing this task."**

This means BECOME that person for the duration of the task. Their beliefs, standards, voice, approach, quirks. The agent asks itself: "How would this person do this?" and that's how it executes.

Personas are selected PER TASK, not per role. The same Marketing Director might use Seth Godin for content strategy, Gary Vee for social media, and Alex Hormozi for a lead magnet. The persona follows the work, not the worker.

## 5-Layer Persona Alignment

Before selecting a persona for any task:

1. **Company Mission** - Does this persona align with the company's mission?
2. **Owner Values** - Does this persona match the owner's personal beliefs and style?
3. **Company Goals/KPIs** - Does this persona support what the company is trying to achieve?
4. **Department Goals/KPIs** - Does this persona fit this department's objectives?
5. **Task Fit** - Is this persona the right guide for THIS specific task?

Layers 1-2 run once at setup (pre-qualified pool). Layers 3-5 run fresh every task.

## Workspace Architecture

### What Every Department Gets

**Unique files (created new):**
- SOUL.md - generated from interview answers, specific to this department
- MEMORY.md - empty, ready for use
- HEARTBEAT.md - department-specific starting priorities
- memory/ folder - for daily session logs

**Inherited files (copied from main CEO workspace):**
- TOOLS.md - same tools, same credentials
- AGENTS.md - same behavioral playbook
- USER.md - same human, same preferences

### What Gets Added to openclaw.json
Each department head gets an agents.list entry:
- id: "dept-[name]"
- name: "[Department] Director"
- workspace: full path to department folder
- model: assigned based on department complexity

## Interview Design

### Before Asking Any Question
Check USER.md, MEMORY.md, AGENTS.md, TOOLS.md, and workforce-interview-answers.md for information already known. Confirm instead of re-asking.

### Question Philosophy
- Plain English only. No jargon.
- Every question includes an example answer
- After every question, tell the client: "If you are not sure, just say 'I don't know' and I will research the best answer for you."
- Dynamic count: 3-7 per department based on complexity and what is already known
- Progress indicators at milestones

### "I Don't Know" Research Protocol

When the client says "I don't know", "not sure", "skip", "research it", or anything indicating they do not have an answer:

1. **Acknowledge warmly.** Say something like: "No problem. Let me look into the best practices for this."

2. **Research immediately.** Use web search to find best practices that are specific to:
   - The client's industry (from earlier interview answers)
   - The client's company goals (from earlier interview answers)
   - The specific department this question is about
   - The specific role this question is about
   Do NOT give generic advice. Research must be tailored to what you already know about this client's business.

3. **Come back with a recommendation.** Present it like:
   - "Based on what I found, here is what companies like yours typically do: [recommendation]."
   - "This aligns with your goal of [goal from earlier answer]."
   - "Do you want to go with this, adjust it, or skip it for now?"

4. **Wait for approval.** The client must say yes, adjust it, or skip. Do NOT auto-accept your own recommendation.

5. **Log the answer.** If they approve:
   - Write it to workforce-interview-answers.md with a note: "Researched recommendation — approved by client"
   - Follow the normal flush protocol (handoff update, MEMORY.md, etc.)
   If they skip:
   - Log it as skipped in interview-handoff.md
   - Circle back at the end of the interview

6. **Never make the client feel bad for not knowing.** This is a business partner helping them figure it out, not a test they are failing.

### Interview Persistence Protocol (Mandatory)

This interview may take hours, days, weeks, or months. The client may stop and come back at any time. Every answer must survive gateway restarts, session resets, context loss, and even agent replacement. Three files work together to guarantee this:

1. **workforce-interview-answers.md** — the permanent answer record
2. **interview-handoff.md** — the progress tracker and resume point
3. **MEMORY.md** — the boot-time progress line

#### After EVERY Answered Question (No Exceptions)

Do these 4 things IN THIS ORDER before asking the next question:

1. **Write the answer to disk first.** Append the question number, question text, client's answer, and timestamp to `workforce-interview-answers.md`. This is the safety net. If everything else fails, the answers are on disk.

2. **Update interview-handoff.md** with:
   - `last_question_number`: the number just answered
   - `last_question_text`: what was asked
   - `next_question_number`: the next one to ask
   - `total_questions_answered`: running count
   - `total_questions_estimated`: best estimate of remaining
   - `skipped_questions`: list of any questions the client said "I don't know" or "skip" (these get circled back to at the end)
   - `last_updated`: timestamp
   - `status`: "in_progress" or "complete"
   - `started_date`: when the interview first began
   - `interview_version`: the version of Skill 23 that started this interview

3. **Update MEMORY.md** with a single living progress line (update it, do not keep appending new lines):
   - Format: `Skill 23 Interview: IN PROGRESS | Question X/Y answered | Last: YYYY-MM-DD H:MM PM | Handoff: interview-handoff.md`
   - When complete: `Skill 23 Interview: COMPLETE | X/X answered | workforce-interview-answers.md`

4. **Only then ask the next question.**

#### Resume Logic (Boot-Time and Session-Start)

At the START of every session, before doing anything else related to Skill 23:

1. Check for `interview-handoff.md`. If it exists and `status` is "in_progress":
   - Read it. Find `next_question_number`.
   - Read `workforce-interview-answers.md` to confirm what has been answered.
   - Tell the client: "I found your previous progress. You answered X questions so far. Picking up where we left off."
   - Resume from the next unanswered question. Do NOT start over.

2. If `interview-handoff.md` is missing but `workforce-interview-answers.md` exists:
   - Reconstruct progress by counting answered questions in the file.
   - Rebuild `interview-handoff.md` from the answers file.
   - Resume from the next unanswered question.

3. If both files are missing but MEMORY.md says "Skill 23 Interview: IN PROGRESS":
   - Ask the client: "It looks like you started the interview before but I cannot find the saved answers. Would you like to start fresh or tell me where you left off?"

4. If everything says complete, do NOT re-interview. Proceed to Skill 32.

#### Edge Cases

- **Client says "I don't know" or "skip":** Log it as skipped in `interview-handoff.md`. Move to the next question. Circle back to all skipped questions at the end of the interview. Offer to research the answer for them.

- **Client wants to change a previous answer:** Update the answer in `workforce-interview-answers.md`. Add a note: "Updated on [date] — previous answer was [X]." Do not re-ask every question.

- **Stale handoff (started months ago):** If `started_date` is more than 90 days old, ask the client: "You started this interview on [date]. Some of your answers may be outdated. Would you like to review your previous answers before continuing, or pick up where you left off?"

- **Client says "continue" or "resume" or "pick up where I left off":** These are all resume triggers. Go straight to the resume logic.

- **Gateway crash mid-flush:** Because the answer is written to disk FIRST (step 1), the worst case is that the handoff file and MEMORY.md are slightly behind. On next session start, the agent reconstructs from the answers file.

## Devil's Advocate (Auto-Created)

After all departments are set up, the AI automatically creates a Devil's Advocate in every department. The client is NOT asked about this. The DA:
- Challenges department claims with evidence and data
- Compares current performance to historical peaks
- Has a 72-hour response window before escalating to the CEO feed
- Gets a unique set of challenge questions based on that department's KPIs

**The DA uses the Act As If Protocol.** Each challenge the DA makes, it selects a persona through the same 5-layer alignment. A DA reviewing marketing might operate as Jim Collins ("Is this good enough, or is it good to great?"). A DA reviewing finances might operate as Mike Michalowicz ("Where is the profit?"). Different challenges, different personas, different angles. This prevents the DA from becoming a one-trick mechanical critic.

The CEO gets a plain-English explanation: "Your AI workforce includes a quality checker in every department. Its job is to make sure your team is actually delivering results, not just saying they are."

## Example: Completed Department Workspace

After Skill 23 finishes, a Marketing department workspace looks like this:

~/clawd/departments/marketing/
- SOUL.md (unique - Marketing Director identity, generated from interview)
- MEMORY.md (unique - empty, ready for use)
- HEARTBEAT.md (unique - department priorities from interview)
- TOOLS.md (inherited from main workspace)
- AGENTS.md (inherited from main workspace)
- USER.md (inherited from main workspace)
- memory/ (folder for daily logs)
- governing-personas.md (pre-qualified persona pool for marketing tasks)
- devils-advocate/ (DA config and challenge questions)

If a specialist was determined to be full-time (e.g., Social Media Manager):
~/clawd/departments/marketing/specialists/social-media-manager/
- SOUL.md (unique - generated from interview, reflects what the client said about social media)
- MEMORY.md (unique - tracks campaigns run, engagement data, brand voice decisions)
- agents.list entry in openclaw.json (makes it a permanent team member that survives restarts)

If a specialist was determined to be on-call (e.g., one-time logo design):
~/clawd/subagents/templates/logo-designer/
- SOUL.md (task template only - no persistent memory, spawned by department head when needed)

## Config Safety

Before ANY edit to openclaw.json:
1. Backup to ~/Downloads/openclaw-backups/ with human-readable name
2. Make the edit
3. Validate JSON
4. Verify backup is in the right location (not a hidden folder)
5. If backup is in wrong place, re-backup to correct location

Reference: https://docs.openclaw.ai and https://github.com/openclaw/openclaw

## Files in This Skill

| File | Purpose |
|------|---------|
| SKILL.md | This file - philosophy, architecture, and overview |
| INSTALL.md | Step-by-step execution (workspace creation, config edits, agents.list) |
| INSTRUCTIONS.md | Interview question framework, dynamic question logic, fallback scripts |
| EXAMPLES.md | Real examples of good department/role structures |
| CORE_UPDATES.md | What to add to client core memory files after install |
| ai-workforce-blueprint-full.md | The complete blueprint reference document |
| scripts/build-workforce.py | Interview engine, workspace builder, persona aligner, org chart generator |

## What This Skill Replaced

This skill consolidates what were previously three separate skills:
- **Former Skill 33 (Department Heads)** - workspace creation, SOUL.md generation, agents.list entries
- **Former Skill 34 (Intelligent Staffing)** - specialist determination (permanent vs on-call)
- Both are now archived as 33-department-heads-ARCHIVED and 34-intelligent-staffing-ARCHIVED

## Connection to Skill 22 (Book-to-Persona Coaching Leadership System)

Skill 22 is recommended but not required. If installed, coaching personas are wired into department workspaces automatically. If not installed, the workforce structure builds clean and personas can be added later via Option C.

If Skill 22 is installed: personas are assigned during setup using the Act As If Protocol and 5-layer alignment.
If Skill 22 is NOT installed: structure builds clean. Install Skill 22 later and re-run in Option C to wire personas in.
