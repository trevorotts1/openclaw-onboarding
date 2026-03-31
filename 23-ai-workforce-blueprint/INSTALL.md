╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TYP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TYP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TYP"
- Look in your session context for prior TYP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TYP:
Proceed to the instructions below. Follow the TYP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TYP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TYP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TYP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

CONFLICT RULE (applies to all skill installs):
If this skill's SKILL.md, CORE_UPDATES.md, or any other file in this skill
folder conflicts with TYP regarding WHICH core .md files to update or WHAT
content to add, always follow this skill's files. The skill takes precedence
over TYP on core file update decisions. TYP governs the storage method (lean
summaries + file paths). The skill governs the content and which files it
touches. When in doubt: skill docs win.

TYP FILE STORAGE INSTRUCTIONS (only read this if TYP confirmed)

WHEN LEARNING THIS DOCUMENT, FOLLOW THIS STRUCTURE:

1. SAVE FULL DOCUMENTATION TO MASTER FILES FOLDER
   Find the OpenClaw master files folder in ~/Downloads/. It may be named:
   - OpenClaw Master Files
   - OpenClaw Master Documents
   - OpenClaw Documents
   - openclaw-master-files
   - openclaw master files
   - OpenClaw Files
   - openclaw-documents
   - Any variation of "openclaw" + "master" or "files" or "documents"
   Search case-insensitively. One word or two words. Plural or singular.
   If no folder is found, create: ~/Downloads/OpenClaw Master Files/

   Save this full document content as a .md file in that folder.

2. DO NOT DUMP FULL CONTENT INTO CORE .MD FILES
   AGENTS.md, TOOLS.md, and MEMORY.md must stay lean.
   Only add a brief summary and a file path reference to where the full
   documentation lives. Never paste thousands of lines into core files.

3. USE THE LABELED SECTIONS BELOW TO KNOW WHAT GOES WHERE
   Look for sections marked:
   [ADD TO AGENTS.md]
   [ADD TO TOOLS.md]
   [ADD TO MEMORY.md]
   Only add what is labeled. Nothing else goes into core files.

╚══════════════════════════════════════════════════════════════╝

---

## 🔴 PHASE 0a - SKILL 22 PRE-FLIGHT CHECK (GRACEFUL DEGRADATION)

**Skill 22 (Book-to-Persona) is recommended but not required.** If installed, coaching personas are wired into department workspaces automatically. If not installed, the workforce structure builds clean and personas can be added later via Option C.

**Pre-flight check - verify and proceed either way:**

```bash
# Check if coaching-personas Gemini Vector Database exists
if python3 ~/clawd/scripts/gemini-indexer.py --status 2>/dev/null | grep -q "indexed"; then
  echo "✅ Skill 22 verified: coaching-personas collection found"
  SKILL22_INSTALLED=true
else
  echo "⚠️  Skill 22 NOT installed: coaching-personas collection not found"
  echo ""
  echo "Skill 23 will build your AI workforce WITHOUT coaching personas."
  echo "Your departments, team leaders, and workspaces will be fully functional."
  echo "The only difference: tasks will not have persona-guided methodology."
  echo ""
  echo "When you are ready to add coaching personas:"
  echo "  1. Install Skill 22 (Book-to-Persona)"
  echo "  2. Re-run Skill 23 in Option C (Audit/Resume) to wire them in"
  echo ""
  SKILL22_INSTALLED=false
  # Continue — do NOT exit. Graceful degradation.
fi
```

**If this check fails:** Skill 23 proceeds with generic AI personas. You can add custom coaching personas later by installing Skill 22 and re-running in Option C (audit mode).

---

# Installing the AI Workforce Blueprint Skill

> **You are the agent. You read this file. You execute every step yourself.**
> You do NOT tell anyone to do anything. You do NOT "say to yourself" to do something.
> You read the instructions and you do the work. That is the entire protocol.

---

## PHASE 0 - TYP PREREQUISITE CHECK

Before installing this skill, TYP must already be installed.

**Check now:**
```
Search AGENTS.md and MEMORY.md for: "Teach Yourself Protocol" or "TYP"
```

**If TYP IS found:** Proceed to Phase 1.

**If TYP is NOT found:** STOP. The agent will check if the package is present at `~/.openclaw/skills/01-teach-yourself-protocol/`. If missing, notify the operator to complete Skill 01 first before returning to this skill.

Do NOT proceed until TYP is confirmed installed.

---

## PHASE 1 - READ ALL SKILL FILES (TYP Activation)

Read every .md file in this skill folder in this exact order:

1. `SKILL.md`
2. `ai-workforce-blueprint-full.md` (the complete 66,819-character blueprint - read ALL of it, do not skip or summarize)
3. `INSTRUCTIONS.md`
4. `EXAMPLES.md`
5. `CORE_UPDATES.md`
6. `INSTALL.md` (this file - you are reading it now)

**After each file, announce to the user:** "Read [filename]. Moving to next."

**Do not proceed to Phase 2 until all 6 files are confirmed read.**

After all reads, announce: "TYP complete for AI Workforce Blueprint skill. Proceeding with installation."

---

## PHASE 2 - DEPENDENCY CHECKS

Run these checks before building anything:

### 2a. Python 3 Check
```bash
python3 --version
```
If Python 3.8+ is available, note it. If not, note it - the build can still proceed manually without the scaffold script.

### 2b. OpenClaw Running Check
Confirm you are running inside an OpenClaw agent environment. If you are reading this file, you are. Proceed.

### 2c. Workspace Access Check
Confirm you have write access to the user's filesystem:
```bash
touch /tmp/.workforce-install-test && rm /tmp/.workforce-install-test
```

---

## PHASE 3 - MASTER FILES FOLDER DETECTION

Locate or create the master files folder. Search `~/Downloads/` for any existing folder matching these names (case-insensitive):

- openclaw-master-files
- OpenClaw Master Files
- OpenClaw Master Documents
- OpenClaw Documents
- openclaw master files
- OpenClaw Files
- openclaw-documents
- master-docs
- master-files
- Any variation of "openclaw" + "master" or "files" or "documents"

```bash
# Search for existing master folder
find ~/Downloads/ -maxdepth 1 -type d -iname "*openclaw*" -o -type d -iname "*master*file*" -o -type d -iname "*master*doc*" 2>/dev/null
```

**If a master folder exists:** Use it. Do NOT create a new one. Note its path as `$MASTER_FOLDER`.

**If no master folder exists:** Create it:
```bash
mkdir -p ~/Downloads/openclaw-master-files
```
Set `$MASTER_FOLDER` to `~/Downloads/openclaw-master-files`.

**Announce to user:** "Master files folder located at: [path]" or "Created master files folder at: [path]"

---

## PHASE 4 - COPY SKILL TO SKILLS FOLDER

```bash
# Copy skill to OpenClaw skills directory if not already there
if [ ! -d ~/.openclaw/skills/23-ai-workforce-blueprint ]; then
  cp -r "$(dirname "$0")/../23-ai-workforce-blueprint" ~/.openclaw/skills/ 2>/dev/null || \
  cp -r /tmp/openclaw-onboarding/23-ai-workforce-blueprint ~/.openclaw/skills/ 2>/dev/null || \
  echo "Skill folder already in place or copy from current location"
fi
```

```bash
chmod +x ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/build-workforce.py
```

**Verify the critical blueprint file was not truncated during copy:**
```bash
wc -c ~/.openclaw/skills/23-ai-workforce-blueprint/ai-workforce-blueprint-full.md
```
Expected: 66,000+ characters. If the file is under 50,000 characters, the copy was truncated - re-copy the skill folder before proceeding. A truncated blueprint will produce an incomplete workforce structure.

If the skill files are already at `~/.openclaw/skills/23-ai-workforce-blueprint/`, skip the copy but still run the chmod and file size check.

---

## PHASE 5 - BLUEPRINT EXECUTION (The Core Build)

This is where you build the actual workforce structure. You do all of this yourself.

### 5-PRE. Model Check (MANDATORY)

Before starting any interview or build work, verify you are running on an approved high reasoning model:
- anthropic/claude-opus-4-6
- anthropic/claude-sonnet-4-6
- openrouter/xiaomi/mimo-v2-pro (with thinking enabled)
- google/gemini-3.1-pro-preview
- openai-codex/gpt-5.4

If you are on Kimi 2.5, Gemini Flash, Gemini Flash Lite, or any other low reasoning model:
Say: "For setting up your company, I recommend switching to a model that thinks more deeply so we get the best results. Want me to switch?"

Do NOT proceed on a low reasoning model. The decisions made here shape the entire company.

### 🔴 5-PRE. COMPLETION SAFETY CHECK (MANDATORY — RUN BEFORE ANYTHING ELSE IN PHASE 5)

Before presenting options, before asking a single question, check if this client has ALREADY completed the AI Workforce Blueprint. Run these checks in order:

**Check 1:** Look for department folders in the workspace:
```bash
ls -d ~/clawd/departments/*/ 2>/dev/null | head -5
```
If department folders exist (e.g., marketing/, sales/), the build was already completed.

**Check 2:** Look for the completed interview answers:
```bash
cat ~/Downloads/openclaw-master-files/company-discovery/workforce-interview-answers.md 2>/dev/null | head -5
```
If this file exists and has real content (not empty, not a template), the interview was already done.

**Check 3:** Look in master files:
```bash
ls ~/Downloads/openclaw-master-files/*/SOUL.md 2>/dev/null | head -5
```

**Check 4:** Search MEMORY.md for completion markers:
```bash
grep -i "workforce complete\|AI WORKFORCE COMPLETE\|skill 23.*complete\|blueprint.*complete" ~/.openclaw/workspace/MEMORY.md 2>/dev/null
```

**Check 5:** Look for interview-handoff.md (partial completion):
```bash
cat ~/Downloads/openclaw-master-files/company-discovery/interview-handoff.md 2>/dev/null | head -10
```

**DECISION LOGIC:**

- **If Check 1 AND Check 2 pass (department folders + completed answers exist):** The client is DONE. Do NOT present options. Do NOT ask questions. Say: "I found your completed AI Workforce — [X] departments, [list them]. Your questions are already answered. Proceeding to set up your Command Center." Then go directly to the AUTOMATIC NEXT STEP section (Skill 32).

- **If Check 5 finds a handoff file but Check 1 fails (partial answers, no build):** The client started but did not finish. Say: "I found your previous progress — you answered [X] questions so far. Let me pick up where we left off." Then resume at the last unanswered question. Do NOT start from question 1.

- **If none of the checks find anything:** Ask the client: "Have you already answered the AI Workforce Blueprint questions before? If yes, I'll search for your answers. If not, we'll start fresh." Then proceed to present options.

This check is MANDATORY. It prevents re-asking 70 questions that the client already answered.

---

### 5a. Read the Full Blueprint

If you have not already absorbed `ai-workforce-blueprint-full.md` during Phase 1, re-read it now.

### 5b. Check Existing Context

Before asking ANY question, read these files for information you already have:
- USER.md - personal preferences, name, timezone
- MEMORY.md - business decisions, prior conversations
- AGENTS.md - tool configurations, behavior rules
- TOOLS.md - connected systems
- workforce-interview-answers.md (in company-discovery/) - previously answered questions if resuming

If you already know an answer, confirm instead of re-asking:
"Based on what I already know, your business is in the real estate industry. Is that still correct?"

### 5c. Present Options (MANDATORY - NEVER SKIP)

**🔴 You MUST present all 3 options and WAIT for the user to choose. NEVER skip. NEVER auto-select.**

**Option A - Full Interview (Recommended)**
"I will ask you about your business and each department. Based on your answers, I will build your entire AI company - departments, team leaders, specialists, and your command center. This is the most personalized option."

**Option B - Quick Setup (Fastest)**
"I will use what I already know about you plus industry best practices. I will propose a structure, you approve or adjust, then I build everything. Same result, just faster."

**Option C - Audit / Resume**
"If we started this before and did not finish, or if you already have departments set up, I will scan what exists and fill in any gaps without changing anything that is already there."

### 5d. Core Business Questions (asked once, not per department)

1. "What is the name of your business?"
2. "In one sentence, what does your business do?"
3. "What industry are you in?" (examples: coaching, e-commerce, agency, restaurant, law firm, SaaS)
4. "What tools do you currently use to run your business?" (examples: Stripe, Convert and Flow, Mailchimp)
5. "What is your biggest challenge right now?"

After every question: "If you are not sure, just tell me to research it. I will look up best practices for your industry and suggest something for you to approve."

**After each answered question:**
1. Update company-discovery/workforce-interview-answers.md with the Q&A
2. Update company-discovery/interview-handoff.md with progress
3. Trigger a memory flush

After core questions: "You are 30% complete."

### 5e. Department Selection

Present recommended departments with plain English descriptions. The client can keep all, remove some, add custom ones, or start from scratch. The number of departments is DYNAMIC - could be 5, 17, or 50.

Default to keeping all recommended if the client has no preference. "You can always add more later."

### 5f. Per-Department Questions (3-7, dynamic)

Questions are NOT a fixed list. Generate questions dynamically based on the client's industry and what you already know. See INSTRUCTIONS.md for the full question framework and 10 industry examples.

**Question categories (pick from these based on relevance):**
1. What the department does regularly
2. Who handles it now
3. What success looks like
4. What tools are used (only if not already known)
5. What is most important about this department
6. What is not working well right now
7. How this department connects to other parts of the business

NEVER exceed 7 questions per department. Fewer is better when you can infer answers.

**After each answered question:** flush answers and update handoff file.

**KPI capture after each department:** "What does success look like for this department?"
If client hesitates, use Perplexity sonar-pro-search to research and suggest 3 options.

**Detect hesitation:** If client gives short answers or says "I don't know" twice, shift to offering suggestions. The goal is completion, not interrogation.

**If client wants to stop:** Save everything immediately. "No problem. Everything is saved. Say 'Resume my AI workforce setup' when you are ready to continue."

After department creation: "You are 50% complete."
After KPIs: "You are 70% complete."

### 5g. Option B (Quick Setup)
Read USER.md, MEMORY.md, SOUL.md, TOOLS.md, and workspace context. Determine departments and roles based on business type and industry best practices. Propose the full structure. Wait for approval. Then build.

### 5h. Option C (Audit / Resume)
Check for company-discovery/interview-handoff.md. If it exists, resume exactly where the client left off. If not, scan existing workforce folder, find gaps, fill them without overwriting anything.

---

## PHASE 5-BUILD - CREATE WORKSPACES AND AGENTS

After the interview (or Option B proposal approval), build the company.

### 5-BUILD-A. Config Safety (MANDATORY BEFORE ANY CONFIG EDIT)

Before touching openclaw.json:
1. Backup to ~/Downloads/openclaw-backups/ with human-readable name
2. Verify backup exists in that location (NOT in a hidden dot-folder)
3. If backup ended up in wrong place, re-backup to correct location
4. Only then proceed with edits
5. After every edit, validate JSON is parseable

### 5-BUILD-B. Create Department Workspaces

For EACH department the client chose, use build-workforce.py create_department_workspace():

Create folder: ~/clawd/departments/[dept-name]/

**Unique files (created new):**
- SOUL.md - generated from interview answers via generate_soul_md(), NOT a generic template
- MEMORY.md - empty, ready for use
- HEARTBEAT.md - department-specific priorities from interview
- memory/ folder - for daily session logs

**Inherited files (copied from main CEO workspace ~/clawd/):**
- TOOLS.md - same tools, same credentials
- AGENTS.md - same behavioral playbook
- USER.md - same human, same preferences

**agents.list entry added to openclaw.json via add_agent_to_config():**
- id: "dept-[name]"
- name: "[Department] Director"
- workspace: full path to department folder
- model: assigned based on department complexity

Every department gets a permanent director. This is NOT a question. Every department has a head.

### 5-BUILD-C. Specialist Determination (Silent)

Using determine_specialists() from build-workforce.py, read the interview answers and determine:

**Full-time team member (permanent):**
- Work is daily/weekly, needs memory of past work, maintains relationships
- Gets: SOUL.md + MEMORY.md in ~/clawd/departments/[dept]/specialists/[name]/
- Gets: agents.list entry in openclaw.json

**On-call specialist:**
- Work is occasional/one-time, no memory needed
- Gets: SOUL.md template in ~/clawd/subagents/templates/[name]/
- No agents.list entry

The client NEVER hears "permanent agent" or "sub-agent."

### 5-BUILD-D. Knowledge Base Folder Structure (Pass 1 - Skeleton)

In addition to core workspace files, create the knowledge base file structure inside each department:

Create the complete folder tree inside `$MASTER_FOLDER`:

```bash
# Example structure - adapt based on user's approved departments and roles
WORKFORCE_ROOT="$MASTER_FOLDER"

# Master Orchestrator (always created)
mkdir -p "$WORKFORCE_ROOT/master-orchestrator"

# Universal SOPs (always created)
mkdir -p "$WORKFORCE_ROOT/universal-sops"

# Department folders (based on user's selections)
# Example: mkdir -p "$WORKFORCE_ROOT/sales/appointment-setter"
# Example: mkdir -p "$WORKFORCE_ROOT/sales/closer"
# Example: mkdir -p "$WORKFORCE_ROOT/marketing/content-creator"
```

**Naming rules (non-negotiable):**
- All department folders: lowercase, hyphens, NO suffix (e.g., marketing, sales, operations)
- All role folders: lowercase, hyphens, descriptive names
- All files: two-digit numbered prefix (00, 01, 02...), `.md` format
- No spaces in folder or file names. Ever.

**Create these files in every department:**
- `00-Department-Overview-[Department-Name].md`

**Create these files in every role folder:**
- `00-Start-Here-[Role-Name].md` (with all required sections: Purpose, Experience, Tone, KPIs, Boundaries, Handoffs, Tech Stack, When-to Reference Map, Routing Logic)
- `01-How-to-[First-Task].md` through `NN-How-to-[Last-Task].md` (one file per major task)
- `intelligent-routing.md`
- `[N]-Good-Examples-[Role-Name].md` (always second to last)
- `[N+1]-Bad-Examples-[Role-Name].md` (always last)

**Create Master Orchestrator files:**
- `00-00-Master-Orchestrator-Start-Here.md`
- `01-How-to-Route-Work-to-Departments.md`
- `02-How-to-Create-Missing-How-To-Files.md`

**Create Universal SOPs:**
- `00-ROUTING.md` (the master routing file mapping task types to departments/roles)

After creating the skeleton, show the user the full folder tree:
```bash
find "$WORKFORCE_ROOT" -type f -name "*.md" | sort
```
Ask: "Does this structure look correct before I write the content for each file?"

### 5-BUILD-E. Fill Every File with Real Content (Pass 2 - Content)

After user approves the skeleton, go file by file and write real content.

**Intelligence hierarchy for content:**
1. **SOURCE 1 (Best):** Interview answers from Option A
2. **SOURCE 2 (Good):** What you know from USER.md, MEMORY.md, SOUL.md, prior conversations
3. **SOURCE 3 (Fallback):** Industry best practices for this business type, department, and role

Use Source 1 if available. Fall back to Source 2, then Source 3. Combine sources where appropriate.

**Every knowledge base file (01, 02, 03...) must contain:**
- What this file covers (one sentence)
- Step-by-step process (numbered, specific, actionable)
- Common mistakes to avoid
- What "done" looks like (success criteria)

**Every Start Here file (00) must contain:**
- Role Overview (name, department, reports to, collaborates with)
- Purpose
- Skill Sets to Embody
- Experience to Embody
- Role-Specific Tech Stack
- Tone and Communication Style
- KPIs
- Boundaries and Constraints
- Edge Case Protocol
- Knowledge Base Roadmap (When-to Reference Map) - maps EVERY knowledge base file to its trigger
- Routing Logic

**Good Examples files:** 3-5 realistic examples of the role doing its job correctly
**Bad Examples files:** 3-5 realistic examples of common failures with explanations of WHY they fail

**Do NOT overwrite files that already have real content.** If resuming a previous build, skip completed files.

---

## PHASE 5-PERSONA - PERSONA ALIGNMENT (Act As If Protocol)

After workspaces are created, run persona alignment using build-workforce.py functions:

1. Load persona-categories.json via load_persona_categories()
2. For each department, identify relevant domain tags (marketing dept → marketing, copywriting, communication)
3. Pull pre-qualified personas from those categories via get_personas_for_category()
4. Create governing-personas.md per department via create_governing_personas_md()
5. Create ~/clawd/persona-matrix.md with the full company persona pool

### Governing-Personas.md Content Requirements (MANDATORY - NOT OPTIONAL)

**For EACH department, the agent MUST write a governing-personas.md with REAL content.** Empty stubs are not acceptable. The file MUST contain at minimum:

```markdown
# Governing Personas — [Department Name]

## Primary Persona
- **Name:** [Persona name from book]
- **Book Title:** [Book title]
- **Why This Fits:** [1-2 sentences explaining why this persona aligns with this department's mission and the owner's values]
- **3 Task Types:**
  1. [Task type] — [brief description of how this persona guides this task]
  2. [Task type] — [brief description]
  3. [Task type] — [brief description]

## Secondary Personas
- [Persona name] — [book] — [when to use this persona instead]
- [Persona name] — [book] — [when to use this persona instead]

## Runtime Selection
Personas are selected PER TASK using the 5-layer alignment:
1. Company Mission alignment
2. Owner Values alignment (from USER.md)
3. Company Goals/KPI alignment
4. Department Goals/KPI alignment
5. Task Fit
```

### Gate Check — DO NOT Proceed Until Verified

After creating all governing-personas.md files, run this check:

```bash
# Count departments with real governing-personas.md content
ACTUAL=$(grep -rl 'Primary Persona' ~/clawd/departments/*/governing-personas.md 2>/dev/null | wc -l | tr -d ' ')
EXPECTED=$(ls -d ~/clawd/departments/*/ 2>/dev/null | wc -l | tr -d ' ')
echo "Departments with governing-personas.md content: $ACTUAL / $EXPECTED"
```

**DO NOT proceed to Phase 5-ORG until `$ACTUAL` equals `$EXPECTED`.** Every department must have a governing-personas.md with the "Primary Persona" heading and all required fields filled in. Empty stubs, placeholder text, or missing files must be fixed before continuing.

### Persona Runtime Behavior

Personas are selected PER TASK at runtime via the 5-layer alignment:
1. Company Mission alignment
2. Owner Values alignment (from USER.md)
3. Company Goals/KPI alignment
4. Department Goals/KPI alignment
5. Task Fit

Layers 1-2 were determined at this setup step (pre-qualified pool).
Layers 3-5 run fresh every time an agent picks up a task.

The instruction to the agent is: "Act as if you are [persona name] executing this task."

## PHASE 5-ORG - GENERATE ORG CHART AND COMMAND CENTER CONFIG

### ORG-CHART.md
Generate ~/clawd/ORG-CHART.md via generate_org_chart() showing:
- CEO / Master Orchestrator at top
- Each department director with their model
- Specialists under each director (full-time or on-call)
- Add summary reference to MEMORY.md

### Command Center departments.json
Generate config/departments.json for the BlackCEO Command Center via generate_departments_json().
Exact format per entry: { "id": slug, "emoji": emoji, "name": display, "headTitle": director title }
Only include departments the client chose.

### Devil's Advocate
Auto-create devils-advocate/ folder in every department. Client is NOT asked.
Each DA gets challenge questions specific to that department's KPIs.

After everything is built: "You are complete! Setting up your AI workforce now."

---

## PHASE 5f - RE-DETECT SKILL 22 AFTER QUESTIONS

**This checks whether Skill 22 (Book-to-Persona) was installed during the interview. If detected, Phase 5-PERSONA (above) handles the actual persona wiring.**

**After all departments/roles are created, re-check for coaching-personas:**

```bash
# Re-run detection after questions complete
if python3 ~/clawd/scripts/gemini-indexer.py --status 2>/dev/null | grep -q "indexed"; then
  echo "✅ Skill 22 detected post-build - running persona wiring..."
  RUN_PERSONA_WIRING=true
else
  echo "ℹ️ Skill 22 not detected - building clean structure (personas can be added later via Option C)"
  RUN_PERSONA_WIRING=false
fi
```

If `RUN_PERSONA_WIRING=true`, proceed to Phase 6.

---

## PHASE 6 - COACHING PERSONAS INTEGRATION CHECK & WIRING

Check if Skill 22 (Book To Persona & Coaching & Leadership System) is installed.

**How detection works - step by step:**

1. Run this command to check for the Gemini Engine coaching-personas collection:
```bash
python3 ~/clawd/scripts/gemini-indexer.py --status 2>/dev/null | grep -q "indexed"
```
2. If that returns exit code 0 (match found), personas are installed.
3. As a fallback, also check for the persona skill folder:
```bash
ls ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/ 2>/dev/null
```
4. If EITHER check succeeds, treat personas as installed.

**If coaching personas ARE detected (either check succeeds):**
- Add a `governing-personas.md` file to EVERY role folder (persona matching reference guide)
- Add a "Persona Matching" section to every `00-START-HERE.md` with query instructions
- Copy `persona-matching-protocol.md` to the workspace root for runtime reference

### Specialist Folder Creation (MANDATORY)

**For each department, create a `specialists/` subfolder with at least 2 role files.**

Each department must have:
```
~/clawd/departments/[dept-name]/specialists/
  ├── [role-name-1].md
  └── [role-name-2].md
```

**Each role file (`[role-name].md`) MUST contain:**

```markdown
# [Role Title]

## Reports To
[Department Director name]

## Responsibilities
1. [Responsibility 1]
2. [Responsibility 2]
3. [Responsibility 3]
4. [Responsibility 4]
5. [Responsibility 5]

## Key Metrics
- [Metric 1]: [target/baseline]
- [Metric 2]: [target/baseline]
- [Metric 3]: [target/baseline]
```

Determine role names from the interview answers. Minimum 2 specialist roles per department. If the interview did not specify enough roles, infer from industry best practices for that department type.

### ORG-CHART.md Creation (MANDATORY)

**Create `~/clawd/ORG-CHART.md` showing the full reporting structure.**

Format:
```markdown
# ORG-CHART — [Company Name]

## CEO / Master Orchestrator
[Owner name]

### [Department 1 Name]
- **Director:** [Director title] ([model])
  - [Specialist 1 title]
  - [Specialist 2 title]

### [Department 2 Name]
- **Director:** [Director title] ([model])
  - [Specialist 1 title]
  - [Specialist 2 title]

[... repeat for all departments ...]
```

**Gate check:**
```bash
if [ -s ~/clawd/ORG-CHART.md ]; then
  echo "✅ ORG-CHART.md exists and is non-empty"
else
  echo "❌ ORG-CHART.md missing or empty — FIX BEFORE PROCEEDING"
  # DO NOT proceed
fi
```

**Gate check for specialist folders:**
```bash
for dept_dir in ~/clawd/departments/*/; do
  dept=$(basename "$dept_dir")
  count=$(ls "$dept_dir/specialists/"*.md 2>/dev/null | wc -l | tr -d ' ')
  if [ "$count" -lt 2 ]; then
    echo "❌ $dept has only $count specialist files (need at least 2) — FIX BEFORE PROCEEDING"
  else
    echo "✅ $dept has $count specialist files"
  fi
done
```

DO NOT proceed past Phase 6 until ALL specialist folders have at least 2 role files AND ORG-CHART.md exists and is non-empty.

**CRITICAL: Personas are NOT assigned to departments. Personas are attached to an agent or sub-agent at the TASK level.** The `governing-personas.md` in each role folder is a REFERENCE GUIDE, not a static assignment. It lists suggested starting-point personas for common tasks in that role, but the actual persona selection happens at runtime using the 5-layer alignment check:
1. Company Mission -- does this persona align with the company's mission?
2. Owner Values -- does this persona match the owner's beliefs and style?
3. Company Goals/KPIs -- does this persona support current company goals?
4. Department Goals/KPIs -- does this persona fit this department's objectives?
5. Task Fit -- is this persona the right guide for THIS specific task?
Layers 1-2 run once at setup (pre-qualified pool). Layers 3-5 run fresh every task. See `persona-matching-protocol.md` for the full protocol.

**Role-Level Governing Personas (Reference Guide):**
Each role gets a `governing-personas.md` that helps agents make faster matches:
```
[role-folder]/
  ├── 00-START-HERE.md
  ├── governing-personas.md    ← Persona matching reference (NOT static assignment)
  ├── 01-[task].md
  └── ...
```

The `governing-personas.md` should contain:
1. Available persona pool (full list installed in this system)
2. Suggested starting points for common task types in this role
3. Pointer to persona-matching-protocol.md for the runtime matching process
4. Task-type examples ("For negotiation tasks, consider Voss")

**If coaching personas are NOT detected (both checks fail):**
- This is NOT an error condition. Both paths are valid.
- Build proceeds clean with no persona references. No errors, no warnings.
- Note in the completion report: "Coaching personas not detected. If you install Skill 22 later, re-run this skill in Option C (audit mode) to wire personas in."

### Phase 6b - Gemini Engine Indexing (ALWAYS RUN)

Regardless of whether coaching personas were detected, ALWAYS run Gemini Engine indexing after the build:

```bash
# Add/update all collections
python3 ~/clawd/scripts/gemini-indexer.py

# Generate embeddings (covers master-files + coaching-personas + workforce files)
# Handled by gemini-indexer.py

# Verify completion
python3 ~/clawd/scripts/gemini-indexer.py --status
```

**Why this happens here:**
- Skill 22 no longer runs Gemini Engine embed (to avoid double-embedding)
- Skill 23 indexes everything at once: master-files + coaching-personas + workforce structure
- One embed covers all collections, saving time and compute

---

## PHASE 7 - VERIFICATION

After the build is complete, run a full audit:

### 7a. Structure Verification
```bash
# Check every department has a Department Overview
for dept in "$WORKFORCE_ROOT"/*; do
  if [ -d "$dept" ] && [ "$(basename "$dept")" != "master-orchestrator" ]; then
    ls "$dept"/00-Department-Overview-*.md 2>/dev/null || echo "MISSING: Department Overview in $(basename "$dept")"
  fi
done

# Check every role folder has a Start Here
find "$WORKFORCE_ROOT" -mindepth 3 -maxdepth 3 -name "00-Start-Here-*.md" -type f | sort

# Check every role folder has Good and Bad examples
find "$WORKFORCE_ROOT" -name "*Good-Examples*" -type f | sort
find "$WORKFORCE_ROOT" -name "*Bad-Examples*" -type f | sort

# Check for routing file
ls "$WORKFORCE_ROOT/universal-sops/00-ROUTING.md" 2>/dev/null || echo "MISSING: Master routing file"

# Check Master Orchestrator
ls "$WORKFORCE_ROOT/master-orchestrator/00-00-Master-Orchestrator-Start-Here.md" 2>/dev/null || echo "MISSING: Master Orchestrator Start Here"
```

### 7b. Content Verification
- Open and spot-check at least 3 Start Here files to confirm they contain all required sections (Purpose, Experience, Tone, KPIs, Boundaries, Handoffs, Tech Stack, When-to Reference Map)
- Confirm knowledge base files have step-by-step processes, not just placeholders
- Confirm the routing file maps task types to correct departments and roles

### 7c. Self-Score
Rate the build on a scale of 1 to 10:
- 10 = every file exists, every file has real content, every Start Here has a complete When-to Reference Map, routing file is complete, Master Orchestrator is wired
- Below 10 = list exactly what is missing and fix it before proceeding

**Announce to user:** "Build verification complete. Score: [X]/10. [Details of any gaps or confirmation that everything is solid.]"

**Progress Indicator:** After KPI setup is complete, tell the client: "You are 70% complete."

---

## PHASE 8 - APPLY CORE_UPDATES.md

Read `CORE_UPDATES.md` from this skill folder and apply every update it specifies:

### 8a. AGENTS.md Update
Add the `## AI Workforce Blueprint (Installed)` section to the bottom of AGENTS.md with:
- Skill path reference
- Department folder rules
- Routing instructions
- Note that this is separate from coaching personas
- Fill in the actual workspace location

### 8b. TOOLS.md Update
Add the `## AI Workforce Blueprint - Scaffold Script` section with:
- Script location
- How to run it
- Options A/B/C descriptions
- Full reference path

### 8c. MEMORY.md Update
Add the `## AI Workforce Blueprint (Installed [DATE])` section with:
- Skill path
- Actual workspace path (filled in from the build)
- List of departments created
- GitHub reference
- Routing file path

### 8d. Pending Setup Rule
Add the `## Pending Skill Setup - Check and Remind` block to AGENTS.md per CORE_UPDATES.md.

**Remember:** Only add lean summaries and file path references to core files. Never paste full documentation.

---

## PHASE 9 - WEEKLY AUTO-UPDATE SETUP

Set up automatic skill updates. The setup script is included in the onboarding package:

```bash
mkdir -p ~/.openclaw/skills/scripts

# Use the setup script from the onboarding package if available
SETUP_SCRIPT=""
for candidate in \
  "/tmp/openclaw-onboarding/scripts/setup-weekly-update.sh" \
  "$HOME/.openclaw/skills/scripts/setup-weekly-update.sh"; do
  if [ -f "$candidate" ]; then
    SETUP_SCRIPT="$candidate"
    break
  fi
done

if [ -n "$SETUP_SCRIPT" ]; then
  cp "$SETUP_SCRIPT" ~/.openclaw/skills/scripts/setup-weekly-update.sh
  chmod +x ~/.openclaw/skills/scripts/setup-weekly-update.sh
  bash ~/.openclaw/skills/scripts/setup-weekly-update.sh
else
  echo "Setup script not found in onboarding package. Skipping weekly auto-update setup."
  echo "Note this in the completion report and set up manually when the script is available."
fi
```

**Verify:**
```bash
crontab -l | grep update-skills
```

This installs a cron that runs every Sunday at 2:00 AM - checks for skill updates, applies them to installed skills, sends a notification with the changelog. Runs automatically. User never has to touch it.

If the script is not found, skip this step and note it in the completion report.

---

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

**During this installation, you may encounter instructions to restart the OpenClaw gateway.**

**YOU ARE FORBIDDEN from triggering gateway restarts yourself.**

### Correct Process
When a gateway restart is needed:
1. **STOP** - Do NOT execute the restart command
2. **NOTIFY** the user: "This installation requires an OpenClaw gateway restart to complete."
3. **INSTRUCT**: "Type `/restart` in Telegram to trigger it"
4. **WAIT** for user action - do NOT proceed until confirmed

### Forbidden Actions
- Do NOT run `openclaw gateway restart` without explicit user permission
- Do NOT say "I'll restart the gateway now" without asking first
- Do NOT assume the user wants the restart

---

## PHASE 10 - COMPLETION CHECKLIST

Before reporting done, verify every item:

- [ ] Model check passed (high reasoning model confirmed)
- [ ] TYP was confirmed installed before starting
- [ ] All 6 skill files were read completely
- [ ] Master files folder located or created
- [ ] Skill copied to ~/.openclaw/skills/23-ai-workforce-blueprint/
- [ ] User was asked about business name, industry, departments
- [ ] User chose Option A, B, or C and that option was fully executed
- [ ] Existing context checked before every question (no redundant asks)
- [ ] workforce-interview-answers.md created and updated after every answer
- [ ] interview-handoff.md created and updated after every answer
- [ ] Config backed up before ANY openclaw.json edit
- [ ] Backup verified in ~/Downloads/openclaw-backups/ (not hidden folder)
- [ ] All department workspaces created with FULL core files:
  - [ ] SOUL.md (unique, generated from interview)
  - [ ] MEMORY.md (empty)
  - [ ] HEARTBEAT.md (department priorities)
  - [ ] memory/ folder
  - [ ] TOOLS.md (inherited from main workspace)
  - [ ] AGENTS.md (inherited from main workspace)
  - [ ] USER.md (inherited from main workspace)
- [ ] agents.list entries added for all department heads
- [ ] Specialists determined (permanent vs on-call) silently from interview answers
- [ ] Permanent specialists have SOUL.md + MEMORY.md + agents.list entry
- [ ] On-call specialists have template SOUL.md in subagents/templates/
- [ ] governing-personas.md created per department with REAL content (Primary Persona name, book title, why it fits, 3 task types — NOT empty stubs)
- [ ] Gate check passed: grep -l 'Primary Persona' ~/clawd/departments/*/governing-personas.md | wc -l equals department count
- [ ] Specialist folders created: each department has specialists/ with at least 2 role files
- [ ] Each specialist role file contains: Title, Reports to, Responsibilities (5 bullets), Key metrics
- [ ] persona-matrix.md created in CEO workspace
- [ ] ORG-CHART.md generated in CEO workspace (exists and non-empty)
- [ ] departments.json generated for Command Center
- [ ] Devil's Advocate created per department
- [ ] All department folders use correct naming (lowercase, hyphens, NO -dept suffix)
- [ ] Universal SOPs folder created with 00-ROUTING.md
- [ ] Coaching personas integration checked (wired if available, noted if not)
- [ ] Build verified with self-score of 8.5+ out of 10
- [ ] AGENTS.md updated per CORE_UPDATES.md
- [ ] TOOLS.md updated per CORE_UPDATES.md
- [ ] MEMORY.md updated per CORE_UPDATES.md
- [ ] Weekly auto-update cron attempted
- [ ] JSON validated after all config edits

**Final announcement to user:**

> "You are complete! Setting up your AI workforce now.
>
> AI Workforce Blueprint installation complete.
>
> **Business:** [name]
> **Workforce location:** [path]
> **Departments created:** [list]
> **Total files created:** [count]
> **Self-score:** [X]/10
> **Coaching personas:** [integrated / not installed - install Skill 22 and re-run in audit mode]
>
> You can now route any task and I will check the routing file, go to the right department, find the right role, and follow the right SOP.
>
> To add a new department later, just say: 'Add a [department name] department to my workforce.'
> To audit the structure, say: 'Audit my AI workforce.'"

---

## 🔴 AUTOMATIC NEXT STEP — SKILL 32 (COMMAND CENTER SETUP)

After the final announcement above, IMMEDIATELY proceed to install Skill 32 (Command Center Setup). Do NOT wait for the user to ask. Do NOT stop and report. The Command Center is the next required step after the AI Workforce Blueprint.

**What to do:**
1. Read `~/.openclaw/skills/32-command-center-setup/INSTALL.md` (or `~/.openclaw/onboarding/32-command-center-setup/INSTALL.md` if skills folder does not have it)
2. Follow Phase 1 prerequisites — all should pass since Skill 23 just completed
3. Continue through all phases of Skill 32

**What to say to the user:**
> "Your AI Workforce is built. Now I am setting up your BlackCEO Command Center — this is the dashboard where you will see everything your AI workforce is doing. I will walk you through each step."

This handoff is MANDATORY. Skill 23 is not truly complete until the Command Center is live.

---

## POST-INSTALL CAPABILITIES

After installation is complete, these commands work:

| User Says | What You Do |
|-----------|-------------|
| "Add a [name] department" | Create the department folder, ask about roles, build all required files |
| "Audit my AI workforce" | Run Option C - scan all folders, find gaps, fill them without overwriting |
| "Add a role to [department]" | Create role subfolder with all required files inside the specified department |
| "Route this task: [description]" | Read 00-ROUTING.md, find the right department/role/file, execute the task |
| "What departments do I have?" | List all department folders and their roles |
| "Rate my workforce structure" | Run the self-score audit from Phase 7 |
