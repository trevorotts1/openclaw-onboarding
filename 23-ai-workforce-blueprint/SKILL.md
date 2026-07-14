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
version: 20.0.21
---

## MANDATORY - Teach Yourself Protocol (TYP)

**Before using this skill, complete the Teach Yourself Protocol (Skill 01 - Teach Yourself Protocol) on this folder.**

Required read order:
1. SKILL.md (this file)
2. INSTRUCTIONS.md - **AUTHORITATIVE** interview spec: question framework, dynamic question logic, the No-Work-During-Interview Gate, Phase 5.5 reconciliation. On any conflict, INSTRUCTIONS.md WINS.
3. ai-workforce-blueprint-full.md - HISTORICAL REFERENCE for folder/file structure and naming conventions only. Superseded by INSTRUCTIONS.md and the canonical department floor on any conflict. Do NOT copy its "7 Required Questions" or "17 departments" list; they are obsolete.
4. EXAMPLES.md - good and bad department/role structure examples
5. INSTALL.md - setup, workspace creation, and config management
6. CORE_UPDATES.md - what to add to your workspace files

**Branding questions - single source of truth:** `interview/branding-questions.json` defines the structured branding question set (ids, prompts, storage targets, drill requirements). The Command Center vendors a copy of this file. INSTRUCTIONS.md Phase 3 themes reference the question ids. Do NOT hardcode branding question prompts anywhere outside that file.

Do NOT run the scaffold script or create any folders before completing all 6 reads.
Do NOT claim the skill is installed until CORE_UPDATES.md has been applied.

---

## 🔴 NO CO-MINGLING (binding)

This skill builds **this client's** company and nothing else. Every department, workspace, role file, persona, and resource it creates belongs to **this one client** and is provisioned in **this client's own** workspace/Notion/GHL/Drive/Telegram/keys. NEVER reuse, borrow, or default to another client's resource. If a needed resource does not exist yet, **STOP and WAIT** - do not substitute another client's as a placeholder. See [`../NO-COMINGLING-RULE.md`](../NO-COMINGLING-RULE.md) and AGENTS.md N0. Co-mingling is a hard violation.

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

1. **Ingests existing client context first** (Phase 0.5: `scripts/context-ingest.py` reads all 6 core workspace files + prior answers + Phase 0 research → `interview-context-map.json`), then **interviews the client** with dynamic, plain-English questions (3-7 per department, skipping known facts, deepening partial ones, asking fresh only for unknowns)
2. **Creates departments** based on interview answers, on top of a CANONICAL FLOOR. The canonical floor (run `scripts/list-canonical-departments.py` to see the current list) of mandatory departments (from department-naming-map.json) is built for every company unless the client explicitly declined one in build-state (canonicalReconciliation.decisions), UNION any client custom departments. reconcile_canonical_floor() in build-workforce.py enforces this in code (standard-unless-declined) and writes an auditable canonicalReconciliation record. Client-named canonical depts keep their real description; the rest inherit the naming-map one-liner with the client's industry context. The reconciliation ENGINE (Phase 5.5) then: COMBINES a custom dept that semantically overlaps a canonical dept under a non-slug name into ONE department on an owner `merge` decision (apply_semantic_merges, never a duplicate); honors symmetric opt-in/opt-out for the mandatory floor AND the 6 universal-primary verticals (naming-map v2.6.1: listings reclassified to real-estate-only, so 6 not 7; floor = 28) AND custom depts (a `no` skips it); materializes the per-dept extra roles the owner asked for as a build decision (materialize_custom_roles, not the post-build add-role path); and captures per-dept owner procedures (capture_custom_sops) respecting the canonical/custom SOP boundary gate (canonical = overlay; custom = authoring source).
3. **Hires department heads** as permanent agents with full workspaces and core files
4. **Determines specialists** - the AI silently decides which roles are full-time team members (permanent agents) vs on-call specialists (spawned when needed). The client never hears these technical terms.
5. **Assigns coaching personas** using the Act As If Protocol and 5-layer alignment check
6. **Sets up workspaces** with inherited files (TOOLS.md, AGENTS.md, USER.md from main) and unique files (SOUL.md, MEMORY.md, HEARTBEAT.md, memory/ folder)
7. **Generates the org chart** (ORG-CHART.md in the CEO workspace)
8. **Creates the Devil's Advocate** in every department automatically
9. **Generates the Command Center config** (departments.json for the dashboard)
10. **Pulls the ROLE LIBRARY + authors the SOP LIBRARY for every role - ENFORCED (v10.15.8).** Filling each role's `how-to.md` from `templates/role-library/` and authoring its SOPs is a GATED build step, not optional cleanup. State fields `roleLibraryStatus` / `sopLibraryStatus` (+ per-dept `roleLibraryFilled` / `sopLibraryFilled`) plus the verify/resume gate `scripts/verify-library-gate.sh` mean a workforce is **NOT complete** (no `buildCompletedAt`, no closeout) until BOTH libraries are populated. The 15-min resume cron fires `[LIBRARY-RESUME]` until they are. See INSTRUCTIONS.md "Moment 3.6 - ROLE LIBRARY + SOP LIBRARY auto-pull gate".

## How It Connects to the System

### Skill Pipeline
Skill 22 (Book-to-Persona Coaching Leadership System) builds coaching personas
--> **Skill 23 (AI Workforce Blueprint)** interviews, creates departments, creates agents, assigns personas, generates org chart
--> **Skill 38 (Conversational AI System)** scaffolds the matching comms automations when a Communications / Sales / Customer-Support department was built
--> BlackCEO Command Center displays and manages everything

### Cross-skill chain → Skill 38 (Conversational AI System) - ENFORCED
When this skill builds a **Communications, Sales, or Customer-Support** department, the closeout MUST
hand off to **Skill 38** to scaffold the matching conversational automations (channel/communications
playbooks + their Build-with-AI prompts, starting with appointment booking). This is NOT optional prose:
it is enforced by the `commsAutomationStatus` state field in `build-state-schema.json` + the
`[COMMS-AUTOMATION-RESUME]` gate in `scripts/resume-workforce-build.sh` (same shape as the role/SOP
library gate). See **INSTRUCTIONS.md → "Moment 3.8 - Comms-automation handoff to Skill 38"**. A
Sales/Support workforce shipped with zero conversational automations is half-delivered.

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

**This skill MUST run on a heavy-reasoning model.** The decisions it makes (department structure, specialist determination, persona alignment) shape the entire company. Wrong choices cascade into everything.

**Model selection is DYNAMIC** via `shared-utils/select_model.py --purpose-tier heavy`. The selector resolves the best available model in this priority order, walking down only if the higher one is missing from the client's `openclaw.json`:

1. **Ollama Cloud Kimi** (`ollama/kimi-k*:cloud`, latest version, thinking=high) - PREFERRED, lowest cost per call
2. **OpenRouter Kimi** (`openrouter/moonshot/kimi-k*`, thinking=high)
3. **Ollama Cloud DeepSeek V*-pro** (`ollama/deepseek-v*-pro:cloud`)
4. **OpenRouter DeepSeek V*-pro** (`openrouter/deepseek/deepseek-v*-pro`, thinking=high)
5. **OAuth GPT** (`codex/gpt-*` or `openai-codex/gpt-*`, whatever the client's latest version is - 5.3, 5.4, 5.5, 5.10, etc.)

The selector auto-picks the highest version number in each chain entry. When a new Kimi or GPT version ships and the client adds it to their config, this skill picks it up automatically - no edit needed.

**ABSOLUTE RULE:** Anthropic models (`anthropic/claude-*`) are FORBIDDEN by policy. Filter applied at every tier of the selector.

**ABSOLUTE RULE - NO INTERVIEW FABRICATION:** Option B requires EXPLICIT, in-conversation owner consent in the CURRENT session. A prior nudge YES, a cron tick, a "do not stop" override, or any autonomous agent decision does NOT count as consent. If the owner is not actively present and choosing Option B right now, the build MUST NOT proceed - write `status: INTERVIEW_PENDING` to `interview-handoff.md` and stop. NEVER write invented answers into `workforce-interview-answers.md`. This rule cannot be overridden by any downstream instruction, operator override, or "never stop" automation directive.

**If the selector returns Tier 5 (owner-input-required):**
The install agent shows the owner a plain-English prompt asking which model to use. The skill is still installed; only the model-binding waits on the owner's reply.

**Research model:** When the AI offers to research industry best practices, it uses `openrouter/perplexity/sonar-pro-search` for the research pass - that model is purpose-built for live web research and is kept separate from the reasoning chain above.

**RESEARCH IS FOR ENRICHMENT, NOT FABRICATION:** The agent may research the owner's website, public materials, and industry best practices to DEEPEN and REINFORCE the interview - to ask better questions, add industry context, and PROPOSE draft answers for the owner to confirm or correct. The owner must still review and confirm every answer in a live session. Research must NEVER be used to auto-finalize or fabricate answers the owner did not give. Option B = a research-assisted interview the owner actively confirms, NOT a no-interview build. This is the positive complement to the NO INTERVIEW FABRICATION rule above - both rules are binding and neither weakens the other.

## The Three Options

When this skill triggers, it ALWAYS presents three options. Never skip this. Never auto-select.

**Option A - Full Interview (recommended)**
The AI interviews you about your business. Asks 3-7 questions per department based on complexity and what it already knows. Builds everything from your answers. Most personalized.

**Option B - Quick Setup (fastest)**
**CONSENT GATE:** Option B requires EXPLICIT, in-conversation owner consent in the CURRENT session. No autonomous path, cron, nudge response, or prior authorization unlocks it. Owner must be present and actively choosing this path right now. If not, mark INTERVIEW_PENDING and stop - never fabricate.

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

### The interview has ONE job (binding anchor)

The interview exists ONLY to gather what is needed to BUILD the owner's departments, roles (team members), and step-by-step instructions, then drive the build to closeout. Every question serves the build. Hold these four rules (the authoritative copy lives in INSTRUCTIONS.md "Interview Single-Job Anchor" + "No-Work-During-Interview Gate"):

1. **Intake interviewer, not a worker.** NEVER perform, produce, demo, or OFFER any client work during the interview: no presentations, decks, copy, funnels, names, logos, graphics, videos, or sample/showcase deliverables. Those are post-build deliverables, gated behind an explicit owner request AFTER closeout. (This is the direct fix for the signature-presentation drift.)
2. **No-Work-During-Interview Gate.** Until `interviewComplete: true` is written to `.workforce-build-state.json`, create NO departments / roles / step-by-step instructions / files / folders and produce NO deliverables. The ONLY permitted in-interview side-action is SILENT capability lookup (tool/API research, best-practice research) that yields NO owner-facing artifact.
3. **No chat-log analysis as a content source.** Context ingestion is a bounded ONE-SHOT pre-pass over the named core files; after it, BUILD. Never re-mine the owner's conversation history to decide content.
4. **Always proceeds to reconciliation.** When intake is gathered, ALWAYS run Phase 5.5 (Canonical Departments Reconciliation), then the build. Never drift into client work or open-ended analysis.

### Before Asking Any Question - Context Ingestion (v12.3.4)

Run `scripts/context-ingest.py` (Phase 0.5 in INSTRUCTIONS.md) BEFORE asking any question.
It reads all **6 core workspace files** (IDENTITY.md, MEMORY.md, AGENTS.md, TOOLS.md,
USER.md, SOUL.md) plus pre-interview-research.md, software-stack-capabilities.md,
prior workforce-interview-answers.md, and provided-context-manifest.md, then produces
`interview-context-map.json` classifying each interview theme:

- **KNOWN** → confirm with client: *"Based on [source], [X]. Still right, or did anything change?"*
  Log only after client confirms. Tag answer: `confirmed-from-context: <source>`.
- **PARTIAL** → deepen: skip the surface question, lead in with what you know, drill deeper.
- **UNKNOWN** → ask fresh (standard interview flow).

**Two non-negotiable definitions:**
- **KNOWN-CONTEXT** = a fact found in an ingested source. May inform questions only; NEVER
  silently recorded as a client answer.
- **RECORDED-ANSWER** = a value written to `workforce-interview-answers.md` by `log_answer()`.
  May ONLY originate from a client utterance in the live session.

If context-ingest.py cannot run or produces no map, treat all themes as UNKNOWN and run the
full interview as normal - purely additive.

### Question Philosophy
- Plain English only. No jargon.
- Every question includes an example answer
- After every question, tell the client: "If you are not sure, just say 'I don't know' and I will research the best answer for you."
- Dynamic count: 3-7 per department based on complexity and what is already known
  (the `interview-context-map.json` from Phase 0.5 is the source of "what is already known")
- Progress indicators at milestones
- For every department, ask the one Healer-dependency question so the embedded Healer knows what to watch: "Are there any unusual outside tools, APIs, or services this department depends on that I should keep an eye on for breakages or version changes?" (example answer: "We rely on a niche scheduling API and a custom Zapier webhook.") This seeds the department Healer's model and external-dependency census.

**DECK-INTAKE OVERRIDE (binding):** For the Presentations DECK-INTAKE interview specifically,
`deck-intake-driver.py` is the authoritative pacing mechanism and supersedes model-discretion.
Do NOT emit deck-intake questions (representation_mix, audience_composition_note,
grounded_content, visual_mix, dark_ok, hook_seed, plus scope fields) yourself. Run
`deck-intake-driver.py --next --run-dir <RUN_DIR>` for each question. The driver enforces
canonical ordering, one-question-per-turn, answer validation, budget enforcement, and the
block-gate precondition for `--complete`. The AI Workforce Blueprint workforce-build interview
(this skill's main interview) keeps its existing dynamic question logic described above —
these are separate interviews with separate signals and separate drivers.

**Downstream precondition (binding):** Command Center setup (Skill 32) and the build-resume /
materialize remediation scripts are GATED on `interviewComplete: true` in
`.workforce-build-state.json`. Until then they REPORT "interview not completed yet" and refuse to
scaffold — they never auto-create the default department floor under company `default`. This skill's
`build-workforce.py` already fail-closes the same way via `_enforce_consent_or_refuse` (exit code 87,
`status: INTERVIEW_PENDING`), corroborated by `_genuine_interview_complete_signal` (a bare flag is
never trusted). One rule, enforced at every layer.

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
   - Write it to workforce-interview-answers.md with a note: "Researched recommendation - approved by client"
   - Follow the normal flush protocol (handoff update, MEMORY.md, etc.)
   If they skip:
   - Log it as skipped in interview-handoff.md
   - Circle back at the end of the interview

6. **Never make the client feel bad for not knowing.** This is a business partner helping them figure it out, not a test they are failing.

### Interview Persistence Protocol (Mandatory)

This interview may take hours, days, weeks, or months. The client may stop and come back at any time. Every answer must survive gateway restarts, session resets, context loss, and even agent replacement. The Memory Wiki system ensures persistence across all layers:

**Active Persistence Files:**
1. **workforce-interview-answers.md** - the permanent answer record (Layer 1: Filesystem)
2. **interview-handoff.md** - the progress tracker and resume point (Layer 1: Filesystem)
3. **MEMORY.md** - the boot-time progress line (Layer 1: Filesystem)
4. **Memory Wiki** - structured interview pages with provenance (Layer 8: Wiki System)

**Persistence Guarantees:**
- Layer 1 (Markdown files): All answers written immediately to disk
- Layer 2 (Memory flush): Key decisions captured before context compaction
- Layer 7 (Obsidian Vault): Daily interview progress logged to `memory/YYYY-MM-DD.md`
- Layer 8 (Wiki System): Structured pages enable cross-referencing and search

#### After EVERY Answered Question (No Exceptions)

Do these 5 things IN THIS ORDER before asking the next question:

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

4. **Update build-state JSON (MANDATORY, added v10.15.1 / v10.14.1).** Run:

   ```bash
   # VPS:
   bash /data/.openclaw/skills/23-ai-workforce-blueprint/scripts/update-interview-state.sh \
     --phase "$CURRENT_PHASE" \
     --question-number "$QUESTION_NUMBER" \
     --asked-by "$AGENT_NAME"
   # Mac:
   bash ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/update-interview-state.sh \
     --phase "$CURRENT_PHASE" \
     --question-number "$QUESTION_NUMBER" \
     --asked-by "$AGENT_NAME"
   ```

   This writes `interviewProgress.lastQuestionNumber`, `lastQuestionPhase`, `lastQuestionAskedBy`, and `lastQuestionAt` into `.workforce-build-state.json`. The resume cron and dashboard read these fields. Skipping this step makes the build-state file lie about your progress, and the cron will repeatedly try to "resume" because it thinks the interview is stuck at Q1 forever. This was the v10.15.0 bug; v10.15.1 (VPS) / v10.14.1 (Mac) closes it.

5. **Only then ask the next question.**

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

- **Client wants to change a previous answer:** Update the answer in `workforce-interview-answers.md`. Add a note: "Updated on [date] - previous answer was [X]." Do not re-ask every question.

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

~/.openclaw/workspace/departments/marketing/
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
~/.openclaw/workspace/departments/marketing/specialists/social-media-manager/
- SOUL.md (unique - generated from interview, reflects what the client said about social media)
- MEMORY.md (unique - tracks campaigns run, engagement data, brand voice decisions)
- agents.list entry in openclaw.json (makes it a permanent team member that survives restarts)

If a specialist was determined to be on-call (e.g., one-time logo design):
~/.openclaw/workspace/subagents/templates/logo-designer/
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

## Memory Wiki Integration

The AI Workforce Blueprint integrates with the OpenClaw Memory Wiki system for structured knowledge management:

### Wiki Pages Created

| Page | Purpose | Location |
|------|---------|----------|
| Company Org Chart | Live organizational structure | `~/.openclaw/workspace/ORG-CHART.md` |
| Department Config | Per-department KPIs and assignments | `~/.openclaw/workspace/departments/[dept]/department-config.json` |
| Persona Matrix | Pre-qualified coaching persona pool | `~/.openclaw/workspace/persona-matrix.md` |
| Governing Personas | Per-department persona matching guide | `~/.openclaw/workspace/departments/[dept]/governing-personas.md` |
| Interview Answers | Permanent record of workforce interview | `~/Downloads/openclaw-master-files/company-discovery/workforce-interview-answers.md` |
| Interview Handoff | Progress tracker for resume capability | `~/Downloads/openclaw-master-files/company-discovery/interview-handoff.md` |

### How the Wiki Is Used

- **Department pages** are created with frontmatter for structured queries (id, emoji, head title, KPIs)
- **Persona pages** include provenance (book source, author, category tags) for 5-layer alignment scoring
- **Interview data** is stored in the wiki for durability and cross-referencing
- **Daily session logs** in `memory/` are wiki-compatible markdown for Obsidian integration

### Wiki Maintenance

The workforce structure auto-updates the wiki:
- Adding a department → creates department page + updates org chart
- Assigning a persona → updates persona-matrix.md with runtime usage
- Completing interview → writes to interview answers page
- Daily operations → logs to dated pages in `memory/` folder

For full wiki capabilities, see Skill 31 (Upgraded Memory System).

---
---

## Self-Service: Add a Role / Add an SOP After Build (§1.5)

**These operations are available AFTER the workforce is built. Every add MUST end with the converge call.**

> Authoring standard: any custom role or SOP the 420-template core library does NOT cover (custom department, or a custom role/SOP inside any department incl. a core one) must be authored to `CUSTOM-AUTHORING-AND-MERGE-STANDARD.md` (19-section role file, six-field SOP, QC gate), and any semantically overlapping custom content must be LAYERED INTO the one core department, never shipped as a duplicate. Canonical/floor content stays COPY + token-personalize (never LLM-authored) per `scripts/sop_boundary_gate.py`.

### Add a Role to an Existing Department

When the owner says "add a `<X>` specialist to `<dept>`":

```bash
# 1. Add the role (creates files + inserts agent row + updates _index.json)
bash add-role.sh --dept <slug> --role "<X Specialist>"

# 2. REQUIRED: Fill how-to.md from the role-library template (REMOVE the [PENDING] marker)
#    Template: 23-ai-workforce-blueprint/templates/role-library/<dept>/<role>/how-to.md
#    The role is BLOCKED from live status until this is filled.

# 3. Run converge (MANDATORY closing step - never skip)
bash 32-command-center-setup/scripts/sync-extensions.sh --converge
```

**Hard rule:** The role stays blocked (status=pending, not routable) until how-to.md no longer contains `[PENDING - FILL FROM LIBRARY]`. Do not skip step 2.

### Add an SOP

When the owner says "add this SOP / write a procedure for `<task>`":

```bash
# 1. Author the SOP markdown (you write it FIRST, then call add-sop.sh)
#    Must have: section headers (##) or numbered steps (1.) and at least 5 lines.
cat > /tmp/sop-draft.md << 'EOF'
# <SOP Title>

## Purpose
<one-line purpose>

## Steps
1. <Step 1>
2. <Step 2>
3. <Step 3>
EOF

# 2. Add the SOP (validates substance, places file, regenerates 00-INDEX.md)
bash 32-command-center-setup/scripts/add-sop.sh \
  --dept <dept-slug> \
  [--role <role-slug>] \
  --title "<SOP Title>" \
  --file /tmp/sop-draft.md \
  [--keywords "kw1,kw2"]

# 3. Run converge (MANDATORY closing step - never skip)
bash 32-command-center-setup/scripts/sync-extensions.sh --converge
```

### The Converge Command

The converge step is REQUIRED after EVERY add. It:
- Validates _index.json invariants
- Refreshes build-state + ORG-CHART.md
- Re-renders the org chart infographic
- Re-syncs the Command Center dashboard
- Updates last-sync.json

```bash
# Standard converge (full renders)
bash 32-command-center-setup/scripts/sync-extensions.sh --converge

# Fast mode (for Sunday cron - skips infographic/Notion if no delta)
bash 32-command-center-setup/scripts/sync-extensions.sh --converge --fast
```

<!-- BREADCRUMB: skill-23-mac | 2026-04-12 | Memory Surgery Phase 2 Wave A -->
<!-- SKILL.md updated: Added Memory Wiki Integration section, updated Interview Persistence Protocol with layer references -->
<!-- SKILL.md updated: Added Self-Service Add-and-Wire section (§1.5) -->
