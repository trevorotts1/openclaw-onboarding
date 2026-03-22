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

## 🔴 PHASE 0a - SKILL 22 PRE-FLIGHT CHECK (MANDATORY)

**Skill 23 requires Skill 22 (Book-to-Persona) to be fully installed first.**

**Pre-flight check - verify before proceeding:**

```bash
# Check if coaching-personas Gemini Vector Database exists
if python3 ~/clawd/scripts/gemini-indexer.py --status 2>/dev/null | grep -q "indexed"; then
  echo "✅ Skill 22 verified: coaching-personas collection found"
  SKILL22_INSTALLED=true
else
  echo "❌ Skill 22 NOT installed: coaching-personas collection missing"
  echo ""
  echo "STOP: Install Skill 22 (Book-to-Persona) first."
  echo "Skill 23 cannot run without the coaching-personas collection."
  echo ""
  echo "To install Skill 22:"
  echo "  1. Navigate to 22-book-to-persona-coaching-leadership-system/"
  echo "  2. Complete all installation steps"
  echo "  3. Return here and re-run Skill 23"
  exit 1
fi
```

**If this check fails: STOP. Do not proceed.** Install Skill 22 first.

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

### 5a. Read the Full Blueprint

If you have not already absorbed `ai-workforce-blueprint-full.md` during Phase 1, re-read it now. You need the complete content - all naming conventions, folder structures, file templates, routing logic, and the Master Orchestrator concept.

### 5b. Gather Business Information from the User

**🔴 MANDATORY OPTION PRESENTATION:** You MUST present all 3 options (A, B, C) to the user and WAIT for them to choose BEFORE doing anything else. Do NOT skip this step. Do NOT auto-select an option. Do NOT proceed to questions until the user has explicitly chosen A, B, or C. If the user says "start" or "begin" without specifying an option, present the 3 options and ask them to choose. NEVER default to any option silently.

Ask the user these questions. Wait for answers before building anything. After each question, add this fallback line: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."

**Required questions:**
1. "What is the name of your business?"
   - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."
2. "What industry are you in?" (coaching, e-commerce, agency, restaurant, law firm, SaaS, etc.)
   - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."
3. "What tools do you currently use to run your business? Examples: Stripe for payments, HubSpot or Convert and Flow for your CRM, Mailchimp for email."
   - Store this answer in the workspace config as `connectedSystems`
   - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."
4. "Here are the 17 departments we recommend for a complete AI workforce. You can keep all of them, remove any you do not need right now, or add new ones specific to your business. What would you like to adjust?"
   - Default to keeping all 17 if the client has no preference
   - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."
5. "Which setup option do you want?"
   - **Option A - Full Interview** (recommended): "I will interview you about each department - at least 7 questions per department - so I deeply understand your operations, tools, KPIs, and processes. Then I build everything with real content based on your answers."
   - **Option B - Quick Setup** (fastest): "I skip the interview and build everything now using what I already know about you from your workspace files (USER.md, MEMORY.md, etc.) plus industry best practices. You can refine later."
   - **Option C - Review First** (middle ground): "I review everything I know, come back with recommendations for departments and roles, you approve or change them, then I build."

**Progress Indicator:** After completing basic business info, tell the client: "You are 30% complete."

### 5c. Execute the Chosen Option

#### If Option A (Full Interview):
For EACH department the user selected, ask at minimum these 7 questions. After each question, add this fallback line: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."

1. What is the purpose of this department?
   - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."
2. What roles exist inside this department?
   - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."
3. What does each role do day to day?
   - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."
4. What does this department receive from other departments and hand off to other departments?
   - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."
5. What is the tech stack for this department?
   - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."
6. What are the KPIs for this department?
   - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."
7. What are the top 10 most common tasks that need SOPs?
   - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."

**After each department is created, capture KPIs with this question:**
"What does success look like for this department? How would you know it is doing a great job?"
- If the client hesitates or says "I don't know", offer: "That is completely fine. I can research what companies in your industry typically measure and suggest some options. Want me to do that?"
- If yes, research industry best practices and present 3 KPI options as choices, not mandates
- After each department's KPI is captured, show progress: "You are 50% complete."

After all interviews complete, propose the full structure to the user. Wait for approval before building.

#### If Option B (Quick Setup):
Read USER.md, MEMORY.md, SOUL.md, and any existing workspace context. Determine departments and roles based on the user's business type and industry best practices. Propose the structure. Wait for brief approval ("looks good" or changes). Then build.

#### If Option C (Review First):
Analyze all available information. Present a detailed recommendation document with:
- Recommended departments and why
- Recommended roles per department and why
- Suggested tech stack per department
- Ask: "Want to add, remove, or change anything?"
After approval, optionally do the full interview (Option A) or proceed to build (Option B style).

### 5d. Build the Folder Structure (Pass 1 - Skeleton)

Create the complete folder tree inside `$MASTER_FOLDER`:

```bash
# Example structure - adapt based on user's approved departments and roles
WORKFORCE_ROOT="$MASTER_FOLDER"

# Master Orchestrator (always created)
mkdir -p "$WORKFORCE_ROOT/master-orchestrator-dept"

# Universal SOPs (always created)
mkdir -p "$WORKFORCE_ROOT/universal-sops"

# Department folders (based on user's selections)
# Example: mkdir -p "$WORKFORCE_ROOT/sales-dept/appointment-setter"
# Example: mkdir -p "$WORKFORCE_ROOT/sales-dept/closer"
# Example: mkdir -p "$WORKFORCE_ROOT/marketing-dept/content-creator"
```

**Naming rules (non-negotiable):**
- All department folders: lowercase, hyphens, end with `-dept`
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

### 5e. Fill Every File with Real Content (Pass 2 - Content)

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

## PHASE 5f - RE-DETECT SKILL 22 AFTER QUESTIONS

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
- Add a `governing-personas.md` file to every department folder
- Add a `governing-personas.md` file to EVERY role folder (role-specific persona mapping)
- Add a "Governing Personas" section to every `00-START-HERE.md` with Gemini Engine query instructions
- Wire persona methodologies to department AND role operations

**Role-Level Governing Personas:**
Each role gets its own `governing-personas.md` mapping personas to role-specific tasks:
```
[role-folder]/
  ├── 00-START-HERE.md
  ├── governing-personas.md    ← NEW: Role-specific persona mapping
  ├── 01-[task].md
  └── ...
```

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
for dept in "$WORKFORCE_ROOT"/*-dept; do
  if [ -d "$dept" ] && [ "$(basename "$dept")" != "master-orchestrator-dept" ]; then
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
ls "$WORKFORCE_ROOT/master-orchestrator-dept/00-00-Master-Orchestrator-Start-Here.md" 2>/dev/null || echo "MISSING: Master Orchestrator Start Here"
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

- [ ] TYP was confirmed installed before starting
- [ ] All 6 skill files were read completely (SKILL.md, ai-workforce-blueprint-full.md, INSTRUCTIONS.md, EXAMPLES.md, CORE_UPDATES.md, INSTALL.md)
- [ ] Master files folder located or created
- [ ] Skill copied to ~/.openclaw/skills/23-ai-workforce-blueprint/
- [ ] User was asked about business name, industry, departments
- [ ] User chose Option A, B, or C and that option was fully executed
- [ ] All department folders created with correct naming (lowercase, hyphens, -dept suffix)
- [ ] Master Orchestrator department created with all 3 required files
- [ ] Universal SOPs folder created with 00-ROUTING.md
- [ ] Every department has a Department Overview file
- [ ] Every role folder has: Start Here, numbered knowledge base files, intelligent-routing.md, Good Examples, Bad Examples
- [ ] Every Start Here file has a complete When-to Reference Map
- [ ] Coaching personas integration checked (wired in if available, noted if not)
- [ ] Build verified with self-score of 8+ out of 10
- [ ] AGENTS.md updated per CORE_UPDATES.md
- [ ] TOOLS.md updated per CORE_UPDATES.md
- [ ] MEMORY.md updated per CORE_UPDATES.md
- [ ] Weekly auto-update cron attempted

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

## POST-INSTALL CAPABILITIES

After installation is complete, these commands work:

| User Says | What You Do |
|-----------|-------------|
| "Add a [name] department" | Create the -dept folder, ask about roles, build all required files |
| "Audit my AI workforce" | Run Option C - scan all folders, find gaps, fill them without overwriting |
| "Add a role to [department]" | Create role subfolder with all required files inside the specified department |
| "Route this task: [description]" | Read 00-ROUTING.md, find the right department/role/file, execute the task |
| "What departments do I have?" | List all -dept folders and their roles |
| "Rate my workforce structure" | Run the self-score audit from Phase 7 |
