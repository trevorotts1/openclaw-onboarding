# START HERE - OpenClaw Onboarding
**READ THIS ENTIRE FILE BEFORE TOUCHING ANYTHING ELSE.**

---

## 🔴 TRIGGER DETECTED - YOU ARE NOW EXECUTING ONBOARDING

If you are reading this file, the user has triggered onboarding by saying something like:
- "Begin onboarding installation"
- "Start onboarding"
- "Install the 33 skills"

**Your task:** Install all 33 skills using the 5-Wave Parallel Orchestration below.

### STEP 0: VERIFY TRIGGER AND CHECK CAPABILITY

**0.1: Confirm AGENTS.md has ONBOARDING PENDING flag**

Search ALL possible AGENTS.md locations. The path differs between Mac and VPS:
```bash
# Try all possible locations
grep -r "ONBOARDING PENDING" ~/clawd/AGENTS.md 2>/dev/null || \
grep -r "ONBOARDING PENDING" ~/.openclaw/workspace/AGENTS.md 2>/dev/null || \
grep -r "ONBOARDING PENDING" /data/.openclaw/workspace/AGENTS.md 2>/dev/null || \
find / -name "AGENTS.md" -exec grep -l "ONBOARDING PENDING" {} \; 2>/dev/null | head -3
```

**Mac path:** `~/clawd/AGENTS.md`
**VPS/container path:** `/data/.openclaw/workspace/AGENTS.md`

If found in ANY location: Proceed with installation.  
If NOT found anywhere: Stop and tell user: "I don't see an ONBOARDING PENDING flag. Please run the install script first."

**0.2: Check for partial/resume state**
```bash
cat ~/.openclaw/onboarding/.onboarding-status 2>/dev/null
cat ~/Downloads/openclaw-master-files/OpenClaw\ Onboarding/.onboarding-status.json 2>/dev/null
```
If status files exist with skill markings (INSTALLED, ALREADY_INSTALLED, SKIPPED):  
→ Resume from first skill NOT marked complete. Do not reinstall completed skills.

**0.3: Test sub-agent spawn capability**
Before starting Wave 2, verify you can spawn sub-agents:
```bash
# Try to spawn a test sub-agent (this is a capability check, not actual install)
```
If `sessions_spawn` works: Use 5-Wave Parallel Orchestration (Waves 2 and 4 use parallel sub-agents).  
If `sessions_spawn` fails: Use Sequential Mode (install 01→30 one at a time).

**0.4: Announce your strategy**
Tell user: "Onboarding triggered. I will install 33 skills using [5-Wave Parallel / Sequential] strategy. Checking for existing installations..."

---

## Core.md Files - PROTECT AT ALL COSTS

These 7 files are your AI's memory and identity. Keep them LEAN.

**The Core.md Files:**
1. USER.md - Information about the human (you)
2. IDENTITY.md - Who the AI is (Stefanie, etc.)
3. SOUL.md - Core principles and philosophy
4. HEARTBEAT.md - Active projects and current status
5. AGENTS.md - Workflows, rules, multi-agent patterns
6. MEMORY.md - Long-term memory, lessons learned
7. TOOLS.md - Tool capabilities and how-to guides

**THE RULE:**
- Core.md files: 10-25 lines maximum
- Full documentation: Goes to ~/Downloads/openclaw-master-files/
- Never dump thousands of lines into core files
- Always use pointers: "See full guide at: [path]"

**Why This Matters:**
If core files get bloated, the AI's context window fills with outdated info. The AI becomes slow and confused. Lean core files = fast, focused AI.

---

## QC Agent - What It Checks

The QC agent verifies each skill installation by checking:

### 1. TYP Compliance
- Did it read ALL .md files before acting?
- Did it follow Teach Yourself Protocol exactly?
- Did it NOT take shortcuts?

### 2. Core.md Files Protection
Core.md files must stay LEAN (10-25 lines max):
- USER.md - About the human
- IDENTITY.md - Who the AI is
- SOUL.md - Core principles
- HEARTBEAT.md - Active projects/status
- AGENTS.md - Workflows and rules
- MEMORY.md - Long-term memory
- TOOLS.md - Tool capabilities

VERIFICATION: Check each core.md file has only lightweight summaries with pointers to master-files. NEVER full documentation.

### 3. Master Files Creation
- Did it create proper subfolder in openclaw-master-files/?
- Did it save full documentation there?
- Is folder structure correct?

### 4. Skill Instructions Followed
- Did it complete ALL steps in INSTALL.md?
- Did it verify success criteria from SKILL.md?
- Did it run any verification commands?

### 5. No Shortcuts Taken
- Did it NOT skip "similar looking" files?
- Did it NOT say "I'll read that later"?
- Did it NOT assume it knew what to do?

### QC Report Format
"Skill X - [PASS/FAIL] - [Details]"

### QC Agent Runs Continuously
- QC agent checks skills as install agents complete them
- Reports in real-time to master agent
- Does not wait for wave to finish

---

## Step Completion Verification and Proactive Remediation

The QC agent must verify that the install agent did NOT skip any steps. For each skill:

### 1. Check Against SKILL.md Checklist
- Did it read ALL .md files listed in the skill?
- Did it complete EVERY step in INSTALL.md?
- Did it verify ALL success criteria?

### 2. If Steps Were Skipped
- Create a REMEDIATION PLAN listing exactly what was missed
- Identify which steps need to be re-done
- Report: "Skill X - FAIL - Steps skipped: [list]. Remediation required."

### 3. Proactive Remediation Execution
- The QC agent should NOT just report the failure
- The QC agent should spawn a FIXER agent or take corrective action
- The QC agent should ensure the skipped steps get completed
- Report: "Skill X - Remediation complete. All steps now verified."

### 4. Remediation Report Format
```
Skill X - QC Check
Status: [PASS/FAIL/REPAIRED]
Steps Verified: [N/N complete]
Issues Found: [list or "none"]
Remediation: [what was fixed or "not needed"]
Final Status: [PASS after remediation]
```

---

## INSTALL ORDER - FOLLOW THIS EXACTLY

The install script handles dependencies automatically. Your AI agent installs skills in this order:

---

### 🔴 STEP 1 (MANDATORY FIRST): Teach Yourself Protocol (TYP)
**Folder:** `01-teach-yourself-protocol/`
Teaches the AI how to store knowledge correctly - lean summaries and file path references only.
Without this, every skill install will bloat your core files and waste tokens every session.
**Nothing else installs until TYP is confirmed.**

### 🔴 STEP 2 (MANDATORY SECOND): Back Yourself Up Protocol
**Folder:** `02-back-yourself-up-protocol/`
Teaches the AI how to back up config files before touching anything.
Without this, one bad edit can corrupt your system with no way to recover.
**Nothing else installs until this is confirmed.**

### ✅ STEP 3: Gemini Engine (Semantic Search Engine)
**Handled automatically by the install script - no skill folder needed.**
Gemini Engine is installed as a system dependency during Step 3 of install.sh.
It powers the persona search in Skill 22 and the persona detection in Skill 23.

**Gemini Engine is automatically installed and indexed at:**
- Install time: Gemini Engine installed, collections (clawd, master-files) created, initial indexing run
- After Skill 22: coaching-personas collection added and indexed
- After Skill 23: workforce files indexed
- After all 33 skills: final complete index

**Gemini Engine INDEXING happens at strategic points - see Gemini Engine INDEXING PROTOCOL below.**

### STEPS 4-30: All Remaining Skills (in numbered order)
Skills install sequentially. For each skill:
- The agent checks if API keys are already present in your env files
- If a key is found → proceeds automatically
- If a key is not found → asks you to enter it, or offers to skip and remind you later
- You can skip any skill and the agent moves to the next one automatically

**Every skill from 04 through 30 requires both TYP (Step 1) and Back Yourself Up (Step 2) to be installed first.**
No exceptions. If you skip those two, stop and go back.

---


---

---

---

## 🔴 SKILL INSTALLATION PROTOCOL (MANDATORY FOR EACH SKILL)

**For EVERY skill folder (01 through 30), you MUST follow this exact sequence. NO EXCEPTIONS. NO SHORTCUTS.**

### ZERO TOLERANCE SHORTCUTS
The following are FORBIDDEN and will cause installation failures:
- "I'll read that later" = **WRONG.** Read it NOW.
- "This looks similar to..." = **WRONG.** Read every file completely.
- "I can skip this step" = **WRONG.** Follow every step exactly.
- "Close enough" = **WRONG.** Verify every requirement is met.
- "The user probably wants..." = **WRONG.** Do not change intent. Follow instructions exactly.

### STEP 1: TEACH YOURSELF PROTOCOL (TYP) - MANDATORY
**Before touching ANYTHING in a skill folder:**
1. Announce: "Installing [skill-name]. Activating Teach Yourself Protocol."
2. Find ALL .md files in the skill folder (including subfolders)
3. Read SKILL.md completely
4. Read CORE_UPDATES.md completely
5. Read INSTALL.md completely
6. Read INSTRUCTIONS.md if present
7. Read any other .md files found
8. **VERIFICATION:** List every .md file you found and confirm you read it

### STEP 2: NO ACTION BEFORE COMPREHENSION
**Forbidden actions (DO NOT DO THESE):**
- Do NOT run install commands before reading ALL docs
- Do NOT assume you know what the skill does based on folder name
- Do NOT skip reading files because they "look similar" to other skills
- Do NOT execute shell commands from SKILL.md until you've read ALL files
- Do NOT create files or modify config before understanding the full scope
- Do NOT say "I understand" without listing what you learned

### STEP 3: FOLLOW THE CHECKLIST
Every skill has a specific install sequence. Follow it exactly:
- If INSTALL.md says "Step 1, Step 2, Step 3" → do them in that order
- If SKILL.md has prerequisites → verify they're met before proceeding
- If CORE_UPDATES.md lists files to update → update ALL of them
- If the skill requires API keys → prompt for them or skip with reminder
- **VERIFICATION:** After each step, explicitly state "Step X complete"

### STEP 4: VERIFY BEFORE CONFIRMING DONE
**Before saying a skill is "installed" or "complete":**
- [ ] Re-read the skill's success criteria from SKILL.md
- [ ] Verify all files were created/modified as specified
- [ ] Verify all API keys/credentials are properly stored
- [ ] Run any verification commands specified in the skill docs
- [ ] Confirm TYP was applied (core files updated with lightweight summary)
- [ ] Explicitly state: "[Skill-name] installation verified complete"

### STEP 5: NO GLOBAL "DONE" UNTIL ALL 30 ARE DONE
- Do NOT say "onboarding complete" after finishing one skill
- Do NOT skip skills because they "seem optional"
- Install skills 01-30 in order, confirm each one individually
- Only after skill 33 (Department Heads) is verified complete → remove ONBOARDING PENDING flag
- Only after skill 33 (Department Heads) is verified complete → write ONBOARDING COMPLETE to MEMORY.md

---

---

## 🔴 CORE .MD FILE PROTECTION - DO NOT BLOAT (PERMANENT RULE)

**Definition: "Core .md files" means these 7 files and ONLY these 7 files:**

| File | Purpose |
|------|---------|
| MEMORY.md | Long-term persistent state and lessons learned |
| AGENTS.md | Agent behavior rules and operating procedures |
| TOOLS.md | Tool setup, API credentials, environment-specific notes |
| USER.md | Who the human is (name, preferences, contacts) |
| IDENTITY.md | Who the agent is |
| SOUL.md | Agent personality and boundaries |
| HEARTBEAT.md | Periodic check tasks and current project status |

### Protection Rules

1. **NEVER dump large content into core files.** Each skill's CORE_UPDATES.md contains the EXACT text to add. Add ONLY what CORE_UPDATES.md specifies. Nothing more.

2. **NEVER copy full documentation into core files.** Core files are INDEX POINTERS, not storage. They say "Full guide at ~/path/to/file.md" instead of pasting the guide contents.

3. **NEVER overwrite core files.** Always APPEND the specific CORE_UPDATES.md entries. Never replace existing content.

4. **NEVER add the same entry twice.** Before adding a CORE_UPDATES.md entry, check if it already exists in the target core file. If it does, skip it.

5. **Maximum addition per skill:** No more than 20 lines per core file per skill. If a skill's CORE_UPDATES.md exceeds 20 lines for any single core file, something is wrong. Stop and ask the user.

6. **If a core file exceeds these sizes, it is bloated and needs cleanup:**
   - MEMORY.md: over 2000 lines
   - AGENTS.md: over 500 lines
   - TOOLS.md: over 500 lines
   - USER.md: over 200 lines
   - IDENTITY.md: over 100 lines
   - SOUL.md: over 100 lines
   - HEARTBEAT.md: over 200 lines

### Why This Matters

The Teach Yourself Protocol (TYP) exists specifically to prevent this. Without TYP, agents dump entire skill documentation into AGENTS.md, ballooning it from 500 lines to 5000+ lines. This wastes tokens on every session start, slows the agent down, and pushes important information out of the context window.

**The core files are the agent's brain. Keep them lean. Keep them fast. Keep them relevant.**

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY (PERMANENT RULE)

**Discipline Rule:** During any skill installation, you may encounter instructions to restart the OpenClaw gateway.

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
- Do NOT restart as part of an autonomous workflow"autonomous" workflow

### Why This Matters
Gateway restarts interrupt active sessions and can kill running processes. The user must control when this happens.

---

## 🔴 ONBOARDING WATCHDOG - HEARTBEAT AUTO-RESUME (PERMANENT RULE)

### Phase 0 Setup: Enable the Onboarding Heartbeat

Before starting Skill 01, the agent MUST set up a temporary 5-minute heartbeat that keeps the onboarding alive. This prevents the agent from stalling mid-install.

**Step 1: Set the heartbeat interval to 5 minutes**

The agent must update the heartbeat configuration in openclaw.json:
```json
"heartbeat": {
  "every": "5m"
}
```

**Step 2: Write the watchdog task to HEARTBEAT.md**

Add this EXACT content to the TOP of HEARTBEAT.md (above any existing content):

```markdown
## 🔴 ONBOARDING IN PROGRESS - DO NOT REMOVE UNTIL COMPLETE

Check onboarding status:
1. Read ~/.openclaw/onboarding/status.json
2. Count how many skills are INSTALLED vs remaining
3. If skills remain and you are not currently installing one, resume from the next unfinished skill
4. If you are stuck on a skill for more than 10 minutes, skip it, mark it FAILED, and move to the next
5. Report progress: "[X] of 33 skills installed. Currently on: [skill name]."

DO NOT REMOVE this block until all 33 skills are installed or attempted.
```

**Step 3: After onboarding completes, clean up**

When all 33 skills are installed (or attempted), the agent MUST:
1. Remove the "ONBOARDING IN PROGRESS" block from HEARTBEAT.md
2. Reset the heartbeat interval back to the default:
```json
"heartbeat": {
  "every": "1h"
}
```
3. Tell the user: "Onboarding complete. I have reset the heartbeat back to hourly checks. Type /restart in Telegram to apply the change."

### How This Works

OpenClaw sends a heartbeat message to the agent every 5 minutes. The agent reads HEARTBEAT.md and sees the onboarding watchdog task. If it was idle or stalled, it immediately checks the status file and resumes installation. This is external enforcement. The agent cannot "forget" to keep going because OpenClaw keeps poking it.

After onboarding finishes, the heartbeat goes back to hourly and the watchdog task is removed. The client's HEARTBEAT.md returns to normal.

---

## 🔴 ONBOARDING CONTINUITY - NEVER STOP UNTIL ALL 33 SKILLS ARE INSTALLED

**The onboarding process must run continuously until all 33 skills are installed.** Some models will stall, pause, or silently stop mid-installation. This protocol prevents that.

### Self-Check Rules

1. **After completing each skill**, immediately check the status file and count how many skills are done vs remaining. If skills remain, start the next one without waiting.

2. **After every 5 minutes of work**, verify you are still making progress:
   - Check which skill you are currently on
   - Check the status file for completed skills
   - If you have been idle or stuck on the same step for more than 10 minutes, re-read the current skill's INSTALL.md and resume from where you left off. Some skills legitimately take 10+ minutes to complete. Do NOT interrupt a skill that is actively working just because it is taking a while. Only re-engage if you have genuinely stalled with no progress

3. **If context is getting full** (above 70%), trigger the memory flush, then continue installation. Do NOT stop and wait for user input unless a skill explicitly requires it (like Skill 15 which needs Telegram IDs).

4. **If a skill fails**, log the failure, mark it as FAILED in the status file, and move to the next skill. Do NOT stop the entire onboarding because one skill failed. Come back to failed skills after all others are complete.

5. **If you lose your place**, check the status file:
   ```bash
   cat ~/.openclaw/onboarding/status.json 2>/dev/null
   ```
   Resume from the first skill not marked INSTALLED.

### Progress Reporting

After every 5 skills completed, send the user a brief progress update:
"Onboarding progress: [X] of 33 skills installed. Currently on: [skill name]. [Y] skills remaining."

### Completion

When all 33 skills are installed:
1. Count and verify: all 33 skill folders should exist in ~/.openclaw/skills/
2. Check the status file for any FAILED skills
3. If any failed, attempt to re-install them one more time
4. Send the user the final report with pass/fail for each skill
5. If a gateway restart is needed for any changes to take effect, tell the user:
   "All 33 skills are installed. To activate the changes, please type /restart in Telegram."

### 🔴 MANDATORY FILE READING BEFORE INSTALLATION

**Before installing ANY skill, you MUST read ALL .md files in that skill folder in the order specified in SKILL.md.**

This is not optional. This is not a suggestion. The Teach Yourself Protocol (TYP) requires it.

For every skill, the reading order is:
1. SKILL.md (overview, prerequisites, file reading order)
2. Every file listed in the "Files in This Folder and Reading Order" section of SKILL.md
3. Only AFTER reading all files do you begin executing INSTALL.md

**If you skip reading files and jump straight to installation:**
- You will miss prerequisites
- You will miss conflict rules
- You will configure things wrong
- You will waste the client's time fixing your mistakes

**How to verify you read all files:**
Before starting INSTALL.md, list every .md file you read and confirm:
"I have read [X] files for Skill [N]: [list filenames]. Proceeding with installation."

If you cannot list the files you read, you did not read them. Go back and read them.

---

### What This Protocol Prevents
- Agent stopping after 3-4 skills because the model ran out of steam
- Agent waiting for user input when none is needed
- Agent silently dying mid-installation with no error message
- Agent forgetting where it was after compaction
- Agent triggering restarts on its own (NEVER do this)

**ZERO TOLERANCE: The onboarding does not end until all 33 skills have been attempted. If you stop early, you failed.**

---

---

## 🔴 COMPLETE ALL DEPENDENCIES - NO PARTIAL INSTALLS

**Every skill may have multiple dependencies, sub-installs, and configuration steps.**

### You MUST Complete Everything Listed
When reading a skill's .md files:
- If INSTALL.md lists 5 steps → do ALL 5 steps
- If SKILL.md mentions 3 dependencies → install ALL 3
- If CORE_UPDATES.md says update 4 files → update ALL 4
- If there are sub-tasks (A, B, C) → complete ALL sub-tasks

### The Only Way to Know: Read ALL .md Files
Dependencies are often scattered across multiple files:
- SKILL.md might mention prerequisites
- INSTALL.md might list command sequences
- INSTRUCTIONS.md might detail configuration steps
- README.md might have additional setup notes

**VERIFICATION:** Before declaring a skill complete, scan back through ALL .md files and verify you did everything mentioned.

### Forbidden Actions
- Do NOT stop after the "main" install if there are additional steps
- Do NOT skip "optional" components that are actually required
- Do NOT assume "that part probably isn't important"
- Do NOT say "the core functionality works" when configuration is incomplete

---

---

## 🔴 OPENROUTER RULE - NEVER CHANGE PRIMARY MODEL

**When installing OpenRouter (Skill 12) or any skill that mentions OpenRouter:**

### YOU ARE FORBIDDEN from changing the user's primary model.

**Correct Process:**
1. Install OpenRouter CLI/tooling as specified
2. Configure API keys
3. **STOP** - Do NOT change any model settings
4. **INFORM** the user: "OpenRouter is installed. Your primary model remains unchanged."
5. **OFFER** (if they ask): "If you'd like to switch to an OpenRouter model, I can help you do that."

### Forbidden Actions
- Do NOT change the user's default model to an OpenRouter model
- Do NOT modify model configuration files
- Do NOT assume "they probably want OpenRouter now"
- Do NOT switch models "just to test"

### Why This Matters
Changing someone's primary model without permission breaks their workflow. Model selection is a user decision, not an installation side effect.

---

---

## 🔴 MAIN ORCHESTRATOR ONLY - SPECIFIC SKILLS

**The following skills MUST be installed by the main orchestrator agent, NEVER by sub-agents:**

| Skill | Folder | Reason |
|-------|--------|--------|
| AI Workforce Blueprint | `23-ai-workforce-blueprint/` | Complex multi-step setup requiring user interaction |
| Book-to-Persona Coaching System | `22-book-to-persona-coaching-leadership-system/` | High-stakes configuration, user must be present |

### Process for These Skills
1. Main orchestrator reads ALL .md files
2. Main orchestrator pauses and notifies: "This skill requires user interaction. I'll handle this directly."
3. Main orchestrator proceeds with install steps
4. Sub-agents are NEVER spawned for these skills

### Forbidden Actions
- Do NOT spawn sub-agents to install these skills
- Do NOT delegate these skills to background processes
- Do NOT skip user interaction steps

---

---

## 🔴 GOOGLE WORKSPACE - SAVE FOR LAST

**Skill 13/14 (Google Workspace Setup/Integration) MUST be installed LAST.**

### Why Last?
- Most complex skill with multiple auth flows
- Requires user presence for OAuth consent screens
- May require browser interaction
- Can have extended configuration steps
- Other skills should be stable before tackling this

### Install Order
Skills 01-12 → Skills 15-22 → Skill 23 (AI Workforce) → Skill 24-30 → **THEN Google Workspace**

If user wants to skip Google Workspace initially, that's acceptable. Log a reminder and continue.

---

---

## 🔴 ONBOARDING FLOW PROTECTION - NOTIFY BEFORE QUESTIONS

**For skills that require user configuration (especially AI Workforce Blueprint):**

### Correct Process
1. Install the skill files/read the skill
2. **NOTIFY** (do NOT ask questions yet):
   > "The AI Workforce Blueprint has been installed. Let me know when you're ready for me to set up your company's back office, right?"
3. **WAIT** for user to explicitly respond
4. **THEN** begin asking configuration questions

### Forbidden Actions
- Do NOT start asking configuration questions immediately after install
- Do NOT assume user wants to configure right now
- Do NOT skip the notification step
- Do NOT barrage user with questions without permission

### Why This Matters
Users need control over when configuration happens. They may want to review documentation first or finish something else.

---

---

## 🔴 MASTER FILES FOLDER DISCIPLINE

**Before creating ANY folders for skill storage:**

### Step 1: Check for Existing Folders
Search for existing master file folders:
- `~/Downloads/openclaw-master-files/`
- `~/Downloads/OpenClaw Master Files/`
- `~/Downloads/master-documents/`
- `~/Documents/openclaw-master-files/`
- Any folder containing both "openclaw" AND "master" in the name

### Step 2: Use Existing or Create
- **If found:** Use that folder. Create skill subfolders inside it.
- **If not found:** Create `~/Downloads/openclaw-master-files/`

### Step 3: Create Skill Subfolders Inside
All skill content goes inside the master files folder:
```
~/Downloads/openclaw-master-files/
├── 03-agent-browser/
├── 04-superpowers/
├── 05-ghl-setup/
└── [skill-content-here]
```

### Forbidden Actions
- Do NOT create skill folders at random locations
- Do NOT create duplicate master file folders
- Do NOT scatter skill content across different parent directories
- Do NOT ignore existing folder structure

---

---

## 🔴 CORE.MD FILES - PROTECT AT ALL COSTS

**The following are the ONLY core.md files. All other files are deep files.**

| Core File | Purpose | Location |
|-----------|---------|----------|
| AGENTS.md | Behavior rules, operating doctrine | `~/clawd/AGENTS.md` |
| MEMORY.md | Persistent state, project status | `~/clawd/MEMORY.md` |
| TOOLS.md | Tool setup, API credentials | `~/clawd/TOOLS.md` |
| USER.md | User preferences, context | `~/clawd/USER.md` |
| IDENTITY.md | Agent identity, persona | `~/clawd/IDENTITY.md` |
| SOUL.md | Core values, philosophy | `~/clawd/SOUL.md` |
| HEARTBEAT.md | Current priorities, active tasks | `~/clawd/HEARTBEAT.md` |

### TYP Storage Rules
- **Core files:** 10-25 line summaries ONLY, with pointers to deep files
- **Deep files:** Complete, unabridged content in `~/Downloads/openclaw-master-files/`

### TYP Conflict Resolution
| Scenario | Rule |
|----------|------|
| Skill asks for core file update → **matches TYP** | Follow TYP (lean summary + deep file) |
| Skill asks for core file update → **conflicts with TYP** | **Skill wins** - follow skill's specific instructions |
| Skill is silent on storage method | Default to TYP |

### Forbidden Actions
- Do NOT dump full content into core files (causes bloat)
- Do NOT create orphan deep files with no core file reference
- Do NOT duplicate content between core and deep files
- Do NOT add new "core files" to the list above

### Verification
After every skill install, verify:
- [ ] Core files have lightweight summaries only (10-25 lines)
- [ ] Deep files have complete content
- [ ] Core files reference deep files with correct paths
- [ ] No bloat added to AGENTS.md, MEMORY.md, TOOLS.md, USER.md, IDENTITY.md, SOUL.md, or HEARTBEAT.md

---

---

## 🔴 Gemini Engine INDEXING PROTOCOL - STRATEGIC EMBEDDING SCHEDULE

**Gemini Engine (semantic search) must be indexed at specific milestones, not after every skill.**

### Indexing Schedule

| Milestone | When to Index | Why |
|-----------|---------------|-----|
| **Initial** | After Gemini Engine install (step 3) | Base index of workspace |
| **Personas** | After Skill 22 (Book-to-Persona) complete | 32+ persona blueprints now searchable |
| **AI Workforce** | After Skill 23 (AI Workforce Blueprint) complete | Workforce definitions indexed |
| **Final** | After ALL 33 skills complete | Complete system index |
| **Ongoing** | After any NEW skill installed post-onboarding | Keep index current |

### What to Index at Each Milestone

```bash
# Standard indexing command sequence:
python3 ~/clawd/scripts/gemini-indexer.py          # Update file index
# Handled by gemini-indexer.py           # Generate embeddings
python3 ~/clawd/scripts/gemini-indexer.py --status   # Verify completion
```

### Collections to Index

| Collection | Contents | When Indexed |
|------------|----------|--------------|
| `clawd` | Workspace AGENTS.md, MEMORY.md, TOOLS.md, etc. | Every milestone |
| `master-files` | `~/Downloads/openclaw-master-files/` | Every milestone |
| `coaching-personas` | `~/Downloads/openclaw-master-files/coaching-personas/personas/` | After Skill 22 |

### Process for Each Indexing

1. **Announce:** "Running Gemini Engine indexing for [milestone] milestone..."
2. **Update:** `python3 ~/clawd/scripts/gemini-indexer.py` - scans all collections
3. **Embed:** `# Handled by gemini-indexer.py` - generates vectors
4. **Verify:** Check status shows all files indexed
5. **Report:** "Gemini Engine indexing complete: X files, Y collections"

### Forbidden Actions
- Do NOT index after every single skill (wasteful)
- Do NOT skip indexing at milestones (breaks search)
- Do NOT assume "it's probably fine" - verify with `python3 ~/clawd/scripts/gemini-indexer.py --status`
- Do NOT index before TYP and Back Yourself Up are complete

### Why This Schedule

- **Too frequent:** Wastes time, redundant embeddings
- **Too rare:** Search returns stale results, new skills invisible
- **Milestone-based:** Balances freshness with efficiency
- **Personas/AI Workforce:** These add the most content, need immediate indexing

---

---

## WEEKLY SKILL UPDATE CHECK

Once the onboarding package is installed, your agent should check for updates **every Sunday**.

**GitHub repo:** `https://github.com/trevorotts1/openclaw-onboarding`

### What to check

```bash
# From wherever the onboarding package is installed:
cd ~/.openclaw/onboarding   # or wherever the package lives
git fetch origin
git log HEAD..origin/main --oneline --name-only 2>/dev/null || \
  echo "No git history - check GitHub directly"
```

### Weekly check workflow

1. Pull the latest from `main`:
   ```bash
   git pull origin main
   ```
2. Compare CHANGELOGs for any skill folder that changed.
3. For each updated skill:
   - Re-run TYP on the updated SKILL.md
   - Re-apply CORE_UPDATES.md if it changed
   - Rebuild the `.skill` archive if scripts changed
4. Notify via your configured messaging channel: "3 skills updated this week: [list]. Re-learned. No action needed."

### If git is not available

Check `https://github.com/trevorotts1/openclaw-onboarding/commits/main` directly and compare the install date against recent commit dates.

---

## TYP CONFLICT RULE - UNIVERSAL (applies to every skill)

Every skill in this package uses the Teach Yourself Protocol. But skills have their
own SKILL.md, CORE_UPDATES.md, and supporting files that specify exactly what to
update and how.

**When a skill's files conflict with TYP about which core .md files to update
or what content to add - always follow the skill's files.**

- TYP governs the storage METHOD: lean summaries and file path references in core files
- The skill governs the CONTENT and which files it touches
- Skill docs always take precedence over TYP when there is a conflict
- This applies to every skill from 03 through 30

---

---

## RESUMING A PARTIAL ONBOARDING

Before starting fresh, check if a previous onboarding attempt was partially completed:

```bash
cat "$MASTER_FILES_FOLDER/OpenClaw Onboarding/.onboarding-status.json" 2>/dev/null
```

If this file exists and contains skill statuses, resume from the first skill that is not marked INSTALLED or ALREADY_INSTALLED. Do not re-run skills already marked complete.

After each skill completes, write or update this status file:

```json
{
  "started": "[ISO timestamp]",
  "master_files_folder": "[actual path used]",
  "skills": {
    "01-teach-yourself-protocol": "INSTALLED",
    "02-back-yourself-up-protocol": "INSTALLED"
  }
}
```

---

## BEFORE YOU DO ANYTHING - MANDATORY FIRST STEP

You are about to autonomously set up a new OpenClaw installation. This process is sequential.
You do the work. The human does not install skills, configure files, or execute steps.
Your job is to read each skill folder and execute the setup yourself.
Complete each step fully before moving to the next. Do not skip. Do not reorder. Do not improvise.
Only pause and request human input when you need something only they can provide:
an API key they have not yet entered, a 2FA code, or a first-time browser login.

---

## PREREQUISITES - VERIFY BEFORE STARTING

Before you begin onboarding, verify all of the following. If any check fails, stop
and tell the user what is missing. Do not start onboarding until every check passes.

### 0. Operating system
This onboarding package supports macOS and Linux. Run this check first:

```bash
uname -s
```

- **Darwin** (macOS): Proceed normally. Full support.
- **Linux**: Proceed, but note the following:
  ```
  Note: You are running on Linux. All core functionality is supported.
  Some install steps reference macOS-specific tools (brew, open, etc.).
  For those steps, use the Linux equivalent (apt/snap for package installs,
  xdg-open for open commands). Flag any brew commands to the user as
  "macOS only - use your package manager instead."
  ```
- **Anything else** (including Windows/MINGW/CYGWIN): Stop and tell the user:
  ```
  This onboarding package requires macOS or Linux. Windows is not supported.
  Please run this on a Mac or a Linux machine (including cloud VPS).
  ```

### CLOUD / LINUX INSTALL NOTES

**Only applies if `uname -s` returned `Linux`. Skip this section entirely on macOS.**

If you are running on a Linux-based cloud server (VPS, EC2, DigitalOcean, etc.), apply
these adjustments throughout the entire onboarding. These are not extra steps - they are
replacements for macOS-specific behavior.

#### 1. Package manager - replace `brew` with `apt-get`
Any install command in any skill that uses `brew install <package>` should be replaced with:
```bash
sudo apt-get update && sudo apt-get install -y <package>
```
If `apt-get` is not available, try `snap install <package>`.

#### 2. Playwright runs headless - no visible browser window
On a cloud server there is no display. Playwright must run in headless mode.
Any skill that requires a first-time browser login (Google Workspace setup, agent-browser, etc.)
will need the user to complete that login from a local machine first, then copy the session
data to the server, OR use a headless-compatible auth flow.

For Playwright persistent context on Linux:
```javascript
const browser = await chromium.launchPersistentContext(userDataDir, {
  headless: true,   // always true on cloud/Linux
  args: ['--no-sandbox', '--disable-dev-shm-usage']
});
```

Install Playwright's Linux dependencies before any skill that uses it:
```bash
npx playwright install chromium
npx playwright install-deps chromium
```

#### 3. Master files folder - use home directory, not Downloads
`~/Downloads` may not exist on a Linux server. Use this location instead:
```bash
mkdir -p ~/openclaw-master-files
```
When Start Here.md refers to `~/Downloads/openclaw-master-files`, use `~/openclaw-master-files` on Linux.

#### 4. Replace `open` command with `xdg-open`
Any skill that uses `open <file-or-url>` to open something should use `xdg-open` on Linux.
On a headless server, `xdg-open` will likely fail silently - that is expected. Skip those steps.

#### 5. Date command format
The date formatting command differs between macOS and Linux:

macOS (BSD date):
```bash
date +'%B %-d at %-I-%M %p'
```

Linux (GNU date):
```bash
date +'%B %-d at %-I-%M %p'
```
GNU date supports `%-d` and `%-I` the same way. No change needed.

#### 6. Shell defaults
Linux servers often default to `bash` instead of `zsh`. All shell commands in this
onboarding package work in both. No changes needed.

#### 7. Summary - Linux substitution table

| macOS | Linux replacement |
|-------|-------------------|
| `brew install X` | `sudo apt-get install -y X` |
| `~/Downloads/` | `~/` (home directory) |
| `open <file>` | `xdg-open <file>` (skip if headless) |
| Playwright headless: false | Playwright headless: true + --no-sandbox |
| `uname -s` → Darwin | `uname -s` → Linux |

---

**After reading this section, continue with the rest of the prerequisites normally.**
**All other onboarding steps are identical on macOS and Linux.**

### 1. OpenClaw is installed and running

```bash
openclaw status
```

If this command fails or OpenClaw is not running, stop. The user needs to install
OpenClaw first before any skills can be added.

### 2. Workspace files exist

Check that these files exist in the workspace root:
- AGENTS.md
- TOOLS.md
- MEMORY.md
- IDENTITY.md
- USER.md
- SOUL.md
- HEARTBEAT.md

If any are missing, create them as empty files with a single header line.
These are the files that skills will update during installation.

### 3. Find or create the master files folder

This is where full skill documentation and reference files are stored. The Teach
Yourself Protocol requires that full documentation lives here, not inside your
core workspace files.

**Search first. Do not create a duplicate.**

Check if the user already has a master files folder. It may not be named exactly
the same on every machine. Look for any of these patterns:

```bash
ls -d ~/Downloads/openclaw-master-files 2>/dev/null
ls -d ~/Downloads/openclaw-master-docs 2>/dev/null
ls -d ~/Downloads/OpenClaw\ Master\ Files 2>/dev/null
ls -d ~/Downloads/master-files 2>/dev/null
ls -d ~/Documents/openclaw-master-files 2>/dev/null
```

If exactly one match is found: use it and continue. If multiple matches are found: ask the user which to use. If no match is found: create ~/Downloads/openclaw-master-files/ and continue.

**If a folder exists:** Use it. Store that path. All skills will be extracted there.
Do not create a second folder.

**If no folder exists:** Create one:
```bash
mkdir -p ~/Downloads/openclaw-master-files/
```

**Store the path.** Every reference to the master files folder in this onboarding
uses the path you found or created here. If the user's folder is called
`~/Downloads/OpenClaw Master Docs` instead of `~/Downloads/openclaw-master-files`,
use their path everywhere. Do not rename their folder.

### 4. Write permission check
Verify the workspace root and master files folder are writable:

```bash
touch [WORKSPACE_ROOT]/.write-test && rm [WORKSPACE_ROOT]/.write-test
```

If this fails, tell the user the folder is not writable and stop. Do not proceed.

### 5. Disk space check

```bash
df -h ~ | awk 'NR==2 {print $4}'
```

Ensure at least 2 GB of free space before starting. Playwright alone uses 500 MB+.
If less than 2 GB available, warn the user and ask if they want to proceed anyway.

### 6. Workspace root detection
The workspace root is the directory containing AGENTS.md, TOOLS.md, and other core files.
Detect it:

```bash
grep -o '"workspace"[[:space:]]*:[[:space:]]*"[^"]*"' ~/.openclaw/openclaw.json 2>/dev/null
```

If not found in the config, check these common locations in order: ~/clawd, ~/openclaw, current directory.
Store the workspace root path - every reference to "workspace root" in this document uses this path.

### 7. Messaging channel detection
Detect the user's primary messaging channel:

```bash
grep -o '"channel"[[:space:]]*:[[:space:]]*"[^"]*"' ~/.openclaw/openclaw.json 2>/dev/null
```

Store the channel name (telegram, slack, discord, etc.). Use this channel for all status
messages and the weekly update notification. If no channel is found, deliver messages
in the current conversation only.

### 8. Existing skills scan
Before starting, scan what OpenClaw skills are already installed:

```bash
openclaw skills list 2>/dev/null || ls ~/.openclaw/skills/ 2>/dev/null
```

Record the list. During each skill's pre-check, cross-reference this list to detect
already-installed skills without repeating setup steps.

### 9. Download and extract the onboarding package

Download the onboarding ZIP and extract it into the master files folder, inside a subfolder called `OpenClaw Onboarding`:

> **Install command:** See your instructor or onboarding package README for the latest install URL.

```bash
unzip /tmp/onboarding.zip -d /tmp/onboarding-temp/
mv /tmp/onboarding-temp/*/  [MASTER_FILES_FOLDER]/OpenClaw\ Onboarding/
rm -rf /tmp/onboarding-temp /tmp/onboarding.zip
```

Replace `[MASTER_FILES_FOLDER]` with the actual path from step 3.

**After extraction, verify the folder structure looks like this:**

```
[MASTER_FILES_FOLDER]/OpenClaw Onboarding/
    Start Here.md                          (this file)
    01-teach-yourself-protocol/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        teach-yourself-protocol.skill
    02-back-yourself-up-protocol/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        back-yourself-up-protocol.skill
    03-agent-browser/
        SKILL.md
        INSTALL.md
        CORE_UPDATES.md
    04-superpowers/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        superpowers.skill
    05-ghl-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        ghl-setup.skill
    06-ghl-install-pages/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        ghl-install-pages.skill
    07-kie-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        kie-setup.skill
    08-vercel-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        vercel-setup.skill
    09-context7/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        context7.skill
    10-github-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        github-setup.skill
    11-superdesign/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        superdesign.skill
    12-openrouter-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        openrouter-setup.skill
    13-google-workspace-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        google-workspace-setup.skill
    14-google-workspace-integration/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        google-workspace-integration.skill
    15-blackceo-team-management/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        blackceo-team-management.skill
    16-summarize-youtube/
        SKILL.md
        INSTALL.md
        CORE_UPDATES.md
        summarize-youtube.skill
    17-self-improving-agent/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        self-improving-agent-full.md
        self-improving-agent.skill
        upstream-original/
    18-proactive-agent/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        proactive-agent-full.md
        proactive-agent.skill
        upstream-original/
    19-humanizer/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        humanizer-full.md
        humanizer.skill
        upstream-original/
    20-youtube-watcher/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        youtube-watcher-full.md
        youtube-watcher.skill
        upstream-original/
    21-tavily-search/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        tavily-search-full.md
        tavily-search.skill
        upstream-original/
    22-book-to-persona-coaching-leadership-system/
        SKILL.md
        INSTALL.md
        CORE_UPDATES.md
        PIPELINE.md
        GEMINI-RETRIEVAL-GUIDE.md
        PERSONA-ROUTER.md
        personas/
        pipeline/
    23-ai-workforce-blueprint/
        SKILL.md
        INSTALL.md
        CORE_UPDATES.md
        ai-workforce-blueprint.skill
    24-storyboard-writer/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        storyboard-writer.skill
    25-video-creator/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        video-creator.skill
    26-caption-creator/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        caption-creator.skill
    27-video-editor/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        video-editor.skill
    28-cinematic-forge/
        SKILL.md
        INSTALL.md
        README.md
```

**Each skill folder contains some combination of SKILL.md, INSTALL.md, INSTRUCTIONS.md, EXAMPLES.md, CORE_UPDATES.md.** Some skills also include a `[skill-name]-full.md`, a `.skill` package file, an `upstream-original/` subfolder, or additional reference documents. File count varies by skill. If SKILL.md or INSTALL.md is missing from a folder, stop and tell the user before proceeding.

**Naming rules:**
- Folder names are lowercase with hyphens, prefixed with their install number (01 through 30)
- The .skill file (when present) matches the folder name without the number prefix
- Do NOT rename any folder or file. Use the names exactly as listed above.


---

## STEP 1: LEARN THE TEACH YOURSELF PROTOCOL FIRST

Before installing any skill, before reading any other file in this folder,
you must learn the Teach Yourself Protocol.

**Why:** Without this protocol, you will learn things the wrong way. You will dump full
documentation into AGENTS.md, TOOLS.md, and MEMORY.md and bloat those files.
Bloated files burn tokens every session because they load every time you start.
This protocol teaches you HOW to store knowledge correctly - full docs go to the master
files folder, only summaries and file path references go into the core files.

**Where to find it:**
```
[MASTER_FILES_FOLDER]/OpenClaw Onboarding/01-teach-yourself-protocol/
```

**DO NOT PROCEED TO STEP 2 UNTIL THIS PROTOCOL IS FULLY LEARNED AND CONFIRMED.**

If you have not yet read the TYP files, go read them now from the folder listed above.
Do not announce this to the user - just do it and proceed.

---

## STEP 2: INSTALL THE BACKUP PROTOCOL SECOND

Before installing any tools, models, or integrations, you must learn and install
the Back Yourself Up Protocol. This protects the user's system from the moment
you start making changes.

**Why:** Every time you edit a model config file or any system config, you must
back it up first. If you have not learned the backup protocol, you will make
changes without backups and corrupt the user's system.

**Where to find it:**
```
[MASTER_FILES_FOLDER]/OpenClaw Onboarding/02-back-yourself-up-protocol/
```

**After installing backup protocol:**
- Confirm the backup folder exists or create it
- Confirm you know the correct date naming format: date +'%B %-d at %-I-%M %p'
  Example: models-backup-February 28 at 3-00 PM.txt
- Add the backup rules to AGENTS.md, TOOLS.md, MEMORY.md, and IDENTITY.md
- Set up the biweekly automated full backup cron job

**DO NOT PROCEED TO STEP 3 UNTIL BACKUP PROTOCOL IS INSTALLED AND VERIFIED.**

---

## STEP 3: INSTALL SKILLS IN THIS EXACT ORDER

Install one skill at a time. Complete each skill fully before starting the next.

### Files Inside Each Skill Folder

Every skill folder contains these files. Read them in this exact order:

| Order | File | Purpose |
|-------|------|---------|
| 1st | **SKILL.md** | Read this FIRST. Understand what this skill is, what it does, and when it triggers. Do not proceed until you understand the skill's purpose. |
| 2nd | **INSTALL.md** | Read this SECOND. Step-by-step installation and configuration. Follow every step exactly. Do not skip verification steps. |
| 3rd | **Full guide doc(s)** (if present) | Read any additional guide documents that exist in the folder: INSTRUCTIONS.md, EXAMPLES.md, [skill-name]-full.md, PIPELINE.md, upstream-original/ files, etc. Not every skill has all of these - read whatever is present. |
| 4th | **CORE_UPDATES.md** | Read this LAST before installing. This file tells you exactly which workspace files (AGENTS.md, TOOLS.md, MEMORY.md, IDENTITY.md, USER.md, SOUL.md, HEARTBEAT.md) need updating and gives you the exact text to add. Only update the files listed. Do not update files that are not listed. Do not add more than what is written. |
| Final | **[skill-name].skill** | Install this after reading all docs. This is the skill package. Install it with: openclaw skill install [skill-name].skill (only if a .skill file exists in this folder) |

### For Each Skill, Follow This Process

1. Open the skill folder
2. Read SKILL.md completely - understand what the skill is
3. Read INSTALL.md completely - build a mental checklist of everything it requires
4. Execute the INSTALL.md steps one by one - do not skip any step
5. Read all full guide docs that exist in this folder (INSTRUCTIONS.md, EXAMPLES.md, [skill-name]-full.md, PIPELINE.md, upstream-original/ files, etc.) - read whatever is present
6. Read CORE_UPDATES.md - update ONLY the workspace files it specifies, with ONLY the text it provides
7. Install the .skill package file (if one exists in this folder)
8. Verify the skill is working
9. **Report to the user:** "Skill [number] of 30 installed. [Skill name] is complete." Then proceed to the next skill immediately. Do not wait for acknowledgment.
10. Start the next skill.

### What CORE_UPDATES.md Does

Each skill affects different workspace files. A video editing skill does not need to update
IDENTITY.md or SOUL.md. A team management skill does need to update USER.md with team member
information. CORE_UPDATES.md removes the guesswork.

It tells you:
- Which workspace files to update (AGENTS.md, TOOLS.md, MEMORY.md, IDENTITY.md, USER.md, SOUL.md, HEARTBEAT.md)
- The exact text to add to each file
- Which files to NOT touch for this skill
- Where in each file to add the new content

**Rules for CORE_UPDATES.md:**
- Only update the files it lists. If a file is not listed, do not touch it.
- Use the exact text provided. Do not rewrite it, expand it, or summarize it.
- Add summaries and file path references only. Full documentation stays in the skill folder.
- This follows the Teach Yourself Protocol. If you have not learned TYP, go back to Step 1.

### If a Skill Fails to Install

If any step in a skill's installation fails:
1. Tell the user exactly what failed, which step failed, and the exact error.
2. Try at least one alternative fix before deciding final status.
3. Classify the skill:
   - CORE skills: 01 Teach Yourself Protocol, 02 Back Yourself Up Protocol, 03 Agent Browser
   - OPTIONAL skills: all platform/API-dependent skills (Superpowers, GHL, Vercel, Context7, GitHub, Google, KIE, etc.)
4. If a CORE skill fails, STOP onboarding and request what is needed.
5. If an OPTIONAL skill fails due to missing API key, missing account, or user says they do not use that system:
   - mark skill status as SKIPPED
   - record exact reason
   - continue to next skill
6. Never silently skip. Always report INSTALLED or SKIPPED with reason.
7. If failure appears network-related (timeout, DNS error, connection refused, download failure):
   retry the failing step up to 3 times with 10-second delays before classifying as FAILED.

---

### EXECUTION STRATEGY (MANDATORY)

**DEFAULT: Use the 5-Wave Parallel Orchestration documented above.**

1. **Wave 1** (Foundation): Run skills 01-03 sequentially in the main agent
2. **Wave 2** (Pre-Persona): Spawn 4 parallel agents for skills 04-21
3. **Wave 3** (Core System): Main agent installs skills 22-23 sequentially (NO sub-agents)
4. **Wave 4** (Post-Workforce): Spawn 2 parallel agents for skills 24-30
5. **Wave 5** (Final): Verify skill 15, install skills 31-33, and finalize

**Sequential Dependencies (Never Parallelize These):**
- Skill 05 (GHL Setup) must complete before Skill 06 (GHL Install Pages)
- Skill 13 (Google Workspace Setup) must complete before Skill 14 (Google Workspace Integration)
- Skill 22 (Book to Persona) must complete before Skill 23 (AI Workforce Blueprint)

**Agent Limits:**
- Maximum 4 sub-agents at any time
- Main orchestrator handles skills 22-23 personally (no delegation)

**The agent executes all installs.** The human is not asked to run steps. The agent runs them.

Keep OpenRouter setup for last after model config backup is verified.
Superdesign is the only skill allowed to rely on service CLI commands.
Vercel, Context7, and GitHub setup must use browser + token/API flows during onboarding, not service CLIs.

### API KEY DISCOVERY (MANDATORY BEFORE ASKING USER)

Before asking for any API key, scan these locations first:
- `.env` in the workspace root
- `secrets/.env` in the workspace root
- `~/.openclaw/secrets/` (any .env files in this directory)
- `~/.openclaw/openclaw.json` (check provider configs for existing keys)
- Shell environment: `printenv | grep -i <KEY_NAME>`

Use flexible matching for key names. Treat these as possible equivalents:
- OPENROUTER_API_KEY, OPEN_ROUTER_API_KEY, OPEN ROUTER API KEY
- CONTEXT7_API_KEY, CONTEXT_7_API_KEY, CONTEXT 7 API KEY
- VERCEL_TOKEN, VERCEL_API_TOKEN
- GITHUB_TOKEN, GH_TOKEN, GITHUB_PAT

If a usable key is found, use it and continue without asking the user.
If no key is found, ask once. If still missing and skill is optional, mark SKIPPED and continue.

### WHERE TO STORE NEW KEYS
When a user provides an API key during onboarding:
1. Check if the skill's INSTALL.md specifies a storage location - use that.
2. If INSTALL.md does not specify, write the key to `[WORKSPACE_ROOT]/secrets/.env`
   (create the file if it does not exist).
3. Never store API keys inside AGENTS.md, TOOLS.md, MEMORY.md, or any workspace .md file.

### DEFERRED KEYS - PENDING LIST
If a user says they will add a key later or wants to skip:
1. Mark the skill as SKIPPED with reason: "Missing [KEY_NAME] - user deferred"
2. Append an entry to `[MASTER_FILES_FOLDER]/OpenClaw Onboarding/.pending-keys.md`:
   ```
   ## [Skill Name] - PENDING
   - Key needed: [KEY_NAME]
   - Where to add it: [location from INSTALL.md or workspace secrets/.env]
   - To complete setup later: re-run this skill's INSTALL.md after adding the key
   ```
3. Include all pending keys in the final onboarding summary.

### GOOGLE ACCOUNT BRANCHING (MANDATORY)

At the start of Google setup, ask:
- "Do you use Google Workspace (custom domain) or regular Gmail?"

Routing:
- If Workspace domain account: use Workspace path (service account + delegated setup where required)
- If regular Gmail only: use Gmail path (OAuth/user-based setup)

### BROWSER SESSION PERSISTENCE (MANDATORY - ALL SKILLS)

Any skill that uses browser automation MUST use persistent session mode.
The user logs in once. The session is saved. Every subsequent run reuses the saved session.
This applies to ALL browser tools - no exceptions.

**agent-browser (Priority 1 - preferred):**
Use `--session-name <skill-name>` on every command:
```bash
agent-browser --session-name <skill-name> open <url>
agent-browser --session-name <skill-name> find ...
```
Sessions saved to: `~/.agent-browser/sessions/`
To check sessions: `agent-browser state list`
To reset a session: `agent-browser state clear <skill-name>`

**Playwright (Priority 2 - fallback):**
ALWAYS use `launchPersistentContext` - NEVER use regular `launch()`:
```javascript
const browser = await chromium.launchPersistentContext(
  path.join(os.homedir(), '.openclaw', 'playwright-data', '<skill-name>'),
  { headless: false }
);
```
Or in Python (sync):
```python
browser = p.chromium.launch_persistent_context(
    user_data_dir=os.path.expanduser("~/.openclaw/playwright-data/<skill-name>"),
    headless=False,
)
```
Sessions saved to: `~/.openclaw/playwright-data/<skill-name>/`
To reset: `rm -rf ~/.openclaw/playwright-data/<skill-name>/`

**OpenClaw browser (Priority 3 - last resort):**
Uses named Chrome profiles - persistent by default. Use the same profile name every time:
```bash
openclaw browser --browser-profile openclaw open <url>
```
Session (cookies, logins) is saved automatically to the openclaw profile.
To use a skill-specific profile: `--browser-profile google-setup`
To reset: delete or clear the profile via OpenClaw gateway settings.

**On Linux/cloud servers:**
Add `headless=True` and `args=['--no-sandbox', '--disable-dev-shm-usage']` to Playwright.
agent-browser also works headlessly on Linux.

**Why this matters:**
Without persistent sessions, every automation run requires a manual login.
With persistent sessions, the user logs in once during initial setup - never again.


### ALREADY-INSTALLED DETECTION (MANDATORY)

Before starting each skill, run a quick pre-check to detect whether the skill is already configured.

Rule:
1. If pre-check shows the skill is already installed and verified, mark it as ALREADY_INSTALLED.
2. Record short proof (what check passed).
3. Skip re-installation and continue to the next skill.
4. Never re-run setup steps blindly when the system is already configured.

Examples of pre-checks:
- Tool exists (`command --version` succeeds)
- Required env key exists and is non-empty in discovered env files
- Required config block already exists in target file
- Required account/token already validated by API test

Status values allowed per skill:
- INSTALLED
- ALREADY_INSTALLED
- SKIPPED (optional only, with reason)
- FAILED (core skill failure stops onboarding)

### INSTALL ORDER

All skill folders are located inside:
```
[MASTER_FILES_FOLDER]/OpenClaw Onboarding/
```

| # | Skill | Folder Name | Notes |
|---|-------|-------------|-------|
| 1 | Teach Yourself Protocol | 01-teach-yourself-protocol | 🔴 MANDATORY FIRST |
| 2 | Back Yourself Up Protocol | 02-back-yourself-up-protocol | 🔴 MANDATORY SECOND |
| - | **Gemini Engine** | *(installed by install script)* | ✅ Auto-installed before skills 3-33 |
| 3 | Agent Browser (Vercel) - preferred browser automation | 03-agent-browser |
| 4 | Superpowers | 04-superpowers |
| 5 | GHL / Convert and Flow Setup | 05-ghl-setup |
| 6 | GHL / Convert and Flow - Install Pages | 06-ghl-install-pages |
| 7 | KIE Setup and HTTP Structure | 07-kie-setup |
| 8 | Vercel Setup (API/browser) | 08-vercel-setup |
| 9 | Context7 Setup (API/browser) | 09-context7 |
| 10 | GitHub / Git Setup (API + git config) | 10-github-setup |
| 11 | SuperDesign Instructions Setup | 11-superdesign |
| 12 | Google Workspace Setup (branch: Workspace vs Gmail) | 13-google-workspace-setup |
| 13 | Google Workspace Integration | 14-google-workspace-integration |
| 14 | BlackCEO Team Management Setup | 15-blackceo-team-management |
| 15 | Summarize YouTube Setup | 16-summarize-youtube |
| 16 | Self-Improving Agent | 17-self-improving-agent |
| 17 | Proactive Agent | 18-proactive-agent |
| 18 | Humanizer | 19-humanizer |
| 19 | YouTube Watcher | 20-youtube-watcher |
| 20 | Tavily Search | 21-tavily-search |
| 21 | Book To Persona & Coaching & Leadership System | 22-book-to-persona-coaching-leadership-system |
| 22 | AI Workforce Blueprint | 23-ai-workforce-blueprint |
| 23 | Storyboard Writer | 24-storyboard-writer |
| 24 | Video Creator | 25-video-creator |
| 25 | Caption Creator | 26-caption-creator |
| 26 | Video Editor | 27-video-editor |
| 27 | Cinematic Forge | 28-cinematic-forge |
| 28 | OpenRouter Setup (MUST BE LAST, after model backup) | 12-openrouter-setup |
| 29 | GHL / Convert and Flow API v2 | 29-ghl-convert-and-flow |


---

## PACKAGE FILE LISTING

> **See README.md for the complete list of files included in this onboarding package.**

---

## RULES THAT APPLY TO THIS ENTIRE ONBOARDING

- Install TYP (01) FIRST. Install Back Yourself Up Protocol (02) SECOND. No exceptions.
- Every skill from 03 onward requires TYP to be confirmed before its install begins
- When a skill's files conflict with TYP about which core files to update - the skill wins
- TYP governs storage method. The skill governs content and which files it touches.
- Do NOT change any API keys, terminal commands, or config values from what is written
- Do NOT add steps that are not in the instructions
- GitHub setup uses browser + token/API setup and local git config only
- Vercel setup uses browser + token/API setup only
- Context7 setup uses browser + token/API setup only
- Superdesign is the only onboarding skill allowed to rely on service CLI commands
- Do NOT skip verification steps
- Do NOT tell the user a skill is installed until you have verified it works
- Do NOT bloat AGENTS.md, TOOLS.md, or MEMORY.md with full documentation
- Do NOT update workspace files that CORE_UPDATES.md does not list for that skill
- Do NOT rewrite the text provided in CORE_UPDATES.md - use it exactly as written
- Do NOT silently skip any skill
- Optional skills with missing account/API may be marked SKIPPED with reason and onboarding should continue
- Core skills (01, 02, 03) cannot be skipped
- Do NOT create a duplicate master files folder if one already exists
- ALWAYS back up config files before editing them
- ALWAYS use human-readable dates on all backup filenames: date +'%B %-d at %-I-%M %p'
- ALWAYS read .md files in this order: SKILL.md → INSTALL.md → all full guide docs present (INSTRUCTIONS.md, EXAMPLES.md, [skill-name]-full.md, upstream-original/ files, etc.) → CORE_UPDATES.md
- ALWAYS report skill completion to the user, then continue immediately without waiting
- If anything fails, report exact failure and classify as CORE stop or OPTIONAL skip

---

## IMPORTED SKILLS (16-30) - AUTHORITATIVE INSTALL RULES

Skills 16 through 30 are imported or recreated skills. Many preserve upstream source files under an `upstream-original/` subfolder. Some have additional reference documents (PIPELINE.md, GEMINI-RETRIEVAL-GUIDE.md, GOOD-AND-BAD-EXAMPLES.md, etc.).

**The file-read order for ALL imported skills is the same as for all skills:**
1. Read `SKILL.md` first
2. Read `INSTALL.md` second
3. Read all full guide docs present in the folder (INSTRUCTIONS.md, EXAMPLES.md, [skill-name]-full.md, PIPELINE.md, upstream-original/ files, etc.)
4. Read `CORE_UPDATES.md` last before installing

**Conflict rule:** If TYP wrapper instructions conflict with a skill's own `SKILL.md` or `CORE_UPDATES.md`, follow the skill's files. TYP governs storage method; the skill governs content.

**Mandatory TYP file-read rule:**
1. Discover every `.md` file in the skill folder (including all subfolders).
2. Read every `.md` file with no exceptions.
3. Report discovered count and read count.
4. If counts do not match, stop and mark install as failed.

**Core file update rule:**
- Apply only the updates listed in that skill's `CORE_UPDATES.md`.
- Do not edit workspace files that CORE_UPDATES.md does not list for that skill.

---

## HOW TO EXECUTE PARALLEL ORCHESTRATION (For AI Agent)

This section tells YOU (the AI agent) exactly how to run the 5-wave installation using `sessions_spawn`.

### Before Starting: Check What Exists

**Check for already installed skills:**
```bash
ls -la ~/.openclaw/skills/ 2>/dev/null | grep -E "^d" | wc -l
python3 ~/clawd/scripts/gemini-indexer.py --status 2>/dev/null
```

**Check onboarding status file:**
```bash
cat ~/.openclaw/onboarding/.onboarding-status 2>/dev/null
```

If skills are already installed, mark them as ALREADY_INSTALLED and skip.

### Sequential Mode vs Parallel Mode

**Use PARALLEL mode if:**
- `sessions_spawn` works (you can spawn sub-agents)
- User hasn't requested sequential

**Use SEQUENTIAL mode if:**
- `sessions_spawn` fails or is unavailable
- User explicitly requests sequential

---

### PARALLEL MODE: Wave-by-Wave Execution

#### WAVE 1: Foundation (Sequential - You Do These Directly)

Install these 4 items yourself, one at a time:

1. **Skill 01: Teach Yourself Protocol**
   - Read ALL .md files in `~/.openclaw/onboarding/01-teach-yourself-protocol/`
   - Execute installation steps
   - Mark: `SKILL-01: INSTALLED` in `~/.openclaw/onboarding/.onboarding-status`
   - Report: "Skill 01 complete"

2. **Skill 02: Back Yourself Up Protocol**
   - Read ALL .md files in `~/.openclaw/onboarding/02-back-yourself-up-protocol/`
   - Execute installation steps
   - Mark: `SKILL-02: INSTALLED`
   - Report: "Skill 02 complete"

3. **Gemini Engine Setup**
   - Verify Gemini Engine is installed: `python3 ~/clawd/scripts/gemini-indexer.py --status`
   - If not installed, install it
   - Run initial indexing: `python3 ~/clawd/scripts/gemini-indexer.py`
   - Report: "Gemini Engine setup complete"

4. **Skill 03: Agent Browser**
   - Read ALL .md files in `~/.openclaw/onboarding/03-agent-browser/`
   - Execute installation steps
   - Mark: `SKILL-03: INSTALLED`
   - Report: "Wave 1 complete: Foundation installed"

**Dependencies:** Wave 1 must complete before Wave 2 starts.

---

#### WAVE 2: Pre-Persona Tools (Parallel - Spawn 3 Install + 1 QC Sub-Agents)

Spawn these sub-agents SIMULTANEOUSLY using `sessions_spawn`:

**Agent A (Skills 04-07):**
```
sessions_spawn with task:
"Install skills 04, 05, 06, 07 from ~/.openclaw/onboarding/. 
For each skill: Read ALL .md files first, then execute installation steps exactly.
Skills: 04-superpowers, 05-ghl-setup, 06-ghl-install-pages, 07-kie-setup.
Report after each skill: 'Skill XX complete - QC passed' or 'Skill XX failed - [reason]'.
Write status to ~/.openclaw/onboarding/.onboarding-status after each skill."
label: "wave2-agent-a"
```

**Agent B (Skills 08-11):**
```
sessions_spawn with task:
"Install skills 08, 09, 10, 11 from ~/.openclaw/onboarding/.
For each skill: Read ALL .md files first, then execute installation steps exactly.
Skills: 08-vercel-setup, 09-context7, 10-github-setup, 11-superdesign.
Report after each skill: 'Skill XX complete - QC passed' or 'Skill XX failed - [reason]'.
Write status to ~/.openclaw/onboarding/.onboarding-status after each skill."
label: "wave2-agent-b"
```

**Agent C (Skills 12, 14-21):**
```
sessions_spawn with task:
"Install skills 12, 14, 15, 16, 17, 18, 19, 20, 21 from ~/.openclaw/onboarding/.
For each skill: Read ALL .md files first, then execute installation steps exactly.
Skills: 12-openrouter-setup, 14-google-workspace-integration, 15-blackceo-team-management, 
16-summarize-youtube, 17-self-improving-agent, 18-proactive-agent, 19-humanizer, 
20-youtube-watcher, 21-tavily-search.
NOTE: Skip skill 13 (Google Workspace Setup) - it is ARCHIVED.
Report after each skill: 'Skill XX complete - QC passed' or 'Skill XX failed - [reason]'.
Write status to ~/.openclaw/onboarding/.onboarding-status after each skill."
label: "wave2-agent-c"
```

**Agent D (QC Monitor):**
```
sessions_spawn with task:
"Monitor Wave 2 installation progress. Check ~/.openclaw/onboarding/.onboarding-status every 2 minutes.
Verify each skill was installed correctly by checking:
1. Status file shows INSTALLED for skill
2. Skill folder has required files
3. No FAILED statuses without remediation
If you find FAILED skills, spawn a FIXER agent to remediate.
Report: 'Wave 2 QC: X of Y skills complete, Z issues found [list]'"
label: "wave2-qc-agent"
```

**After spawning all 4 agents:**
- Use `subagents(action="list")` to monitor
- Poll every 30 seconds for completion
- Wait until all Wave 2 skills show INSTALLED in status file
- Report: "Wave 2 complete: Pre-Persona tools installed"

**Dependencies:** Wave 2 must complete before Wave 3 starts.

---

#### WAVE 3: Core System (Sequential - YOU Install These, No Sub-Agents)

**⚠️ CRITICAL: These skills MUST be installed by YOU (main orchestrator), NEVER by sub-agents.**

1. **Skill 22: Book-to-Persona Coaching Leadership System**
   - Read ALL .md files in `~/.openclaw/onboarding/22-book-to-persona-coaching-leadership-system/`
   - Execute installation steps (this includes downloading and processing persona blueprints)
   - Run Gemini Engine indexing for coaching-personas collection
   - Mark: `SKILL-22: INSTALLED`
   - Report: "Skill 22 complete"

2. **Skill 23: AI Workforce Blueprint**
   - **FIRST:** Notify user: "The AI Workforce Blueprint is installed. Let me know when you're ready for me to set up your company's back office."
   - **WAIT** for user response
   - **THEN:** Read ALL .md files in `~/.openclaw/onboarding/23-ai-workforce-blueprint/`
   - Execute installation steps
   - Mark: `SKILL-23: INSTALLED`
   - Report: "Wave 3 complete: Core system ready"

**Why no sub-agents?** These skills require complex configuration, user interaction, and high-stakes decisions that only the main orchestrator should handle.

---

#### WAVE 4: Post-Workforce (Parallel - Spawn 2 Sub-Agents)

Spawn these sub-agents SIMULTANEOUSLY:

**Agent E (Skills 24-26):**
```
sessions_spawn with task:
"Install skills 24, 25, 26 from ~/.openclaw/onboarding/.
For each skill: Read ALL .md files first, then execute installation steps exactly.
Skills: 24-storyboard-writer, 25-video-creator, 26-caption-creator.
Report after each skill: 'Skill XX complete - QC passed' or 'Skill XX failed - [reason]'.
Write status to ~/.openclaw/onboarding/.onboarding-status after each skill."
label: "wave4-agent-e"
```

**Agent F (Skills 27-30):**
```
sessions_spawn with task:
"Install skills 27, 28, 29, 30 from ~/.openclaw/onboarding/.
For each skill: Read ALL .md files first, then execute installation steps exactly.
Skills: 27-video-editor, 28-cinematic-forge, 29-ghl-convert-and-flow, 30-fish-audio-api-reference.
Report after each skill: 'Skill XX complete - QC passed' or 'Skill XX failed - [reason]'.
Write status to ~/.openclaw/onboarding/.onboarding-status after each skill."
label: "wave4-agent-f"
```

**After spawning both agents:**
- Monitor via `subagents(action="list")`
- Wait until all show INSTALLED
- Report: "Wave 4 complete: All skills installed"

---

#### WAVE 5: Final (Sequential - You Do These)

1. **Verify Skill 15 is complete**
   - Check status file shows `SKILL-15: INSTALLED`
   - If not, install it now

2. **Final Gemini Engine Indexing**
   ```bash
   python3 ~/clawd/scripts/gemini-indexer.py
   # Handled by gemini-indexer.py
   python3 ~/clawd/scripts/gemini-indexer.py --status
   ```

3. **Remove ONBOARDING PENDING flag from AGENTS.md**
   - Open `~/clawd/AGENTS.md`
   - Delete the ONBOARDING PENDING block

4. **Write ONBOARDING COMPLETE to MEMORY.md**
   - Add entry: "OpenClaw onboarding completed on [date]. All 33 skills installed."

5. **Report completion**
   - Install Skill 31 (Upgraded Memory System): Read SKILL.md, check prerequisites, follow INSTALL.md
   - "Wave 5 complete: Onboarding finished. All 33 skills installed."

---

### SEQUENTIAL MODE (Fallback)

If `sessions_spawn` doesn't work, install all 33 skills one at a time:

```
For skill in 01 02 03 04 05 06 07 08 09 10 11 12 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30:
  Read ALL .md files in ~/.openclaw/onboarding/[skill-folder]/
  Execute installation steps
  Mark: SKILL-XX: INSTALLED
  Report: "Skill XX complete"
```

Skip skill 13 (archived).

---

### Status File Format

Write to `~/.openclaw/onboarding/.onboarding-status` after EACH skill:

```
SKILL-01: INSTALLED
SKILL-02: INSTALLED
SKILL-03: INSTALLED
SKILL-04: FAILED - missing API key
SKILL-05: SKIPPED - user requested skip
```

Valid statuses: INSTALLED, ALREADY_INSTALLED, FAILED, SKIPPED

---

## PARALLEL INSTALLATION ORCHESTRATION

The OpenClaw onboarding uses a **5-WAVE PARALLEL STRATEGY** to install 33 skills efficiently.

### Conflict Prevention (IMPORTANT)

Before starting orchestration, check if install.sh is already running:

```bash
INSTALL_FLAG="$HOME/.openclaw/onboarding/.install-in-progress"

if [ -f "$INSTALL_FLAG" ]; then
  echo "Onboarding already in progress via install.sh. Start Here.md orchestration skipped."
  return
fi

# Create flag file - Start Here.md now owns the orchestration
touch "$INSTALL_FLAG"

# Ensure flag is removed on exit
trap 'rm -f "$INSTALL_FLAG"' EXIT
```

**First one to run (install.sh OR Start Here.md) creates the flag and takes control. The second one sees the flag and skips to avoid conflicts.**

---

### 5-WAVE PARALLEL STRATEGY

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         5-WAVE PARALLEL INSTALLATION                        │
├─────────┬─────────────────┬─────────────────────────────────────────────────┤
│  WAVE   │    AGENTS       │              SKILLS                             │
├─────────┼─────────────────┼─────────────────────────────────────────────────┤
│ Wave 1  │ 1 (Sequential)  │ 01 TYP, 02 Backup, Gemini Engine, 03 Agent Browser        │
│         │                 │ Foundation - must complete before Wave 2        │
├─────────┼─────────────────┼─────────────────────────────────────────────────┤
│ Wave 2  │ 4 (Parallel)    │ Agent A: 04, 05, 06, 07 (install)               │
│         │ 3 install + 1 QC│ Agent B: 08, 09, 10, 11 (install)               │
│         │                 │ Agent C: 12, 13, 14, 15, 16, 17, 18, 19, 20, 21 │
│         │                 │         (install)                               │
│         │                 │ Agent D: QC Agent (verification)                │
│         │                 │ Pre-Persona tools - all 4 run simultaneously    │
├─────────┼─────────────────┼─────────────────────────────────────────────────┤
│ Wave 3  │ 1 (Sequential)  │ 22 Book-to-Persona, 23 AI Workforce Blueprint   │
│         │                 │ CORE SYSTEM - Main orchestrator ONLY            │
├─────────┼─────────────────┼─────────────────────────────────────────────────┤
│ Wave 4  │ 2 (Parallel)    │ Agent E: 24, 25, 26                             │
│         │                 │ Agent F: 27, 28, 29, 30                             │
│         │                 │ Post-Workforce tools                            │
├─────────┼─────────────────┼─────────────────────────────────────────────────┤
│ Wave 5  │ 2 (Sequential)  │ 15 BlackCEO Team Management, 31 Upgraded Memory  │
│         │                 │ Final verification and Gemini Engine indexing             │
└─────────┴─────────────────┴─────────────────────────────────────────────────┘
```

---

### Agent Spawning Commands

Use these commands to spawn sub-agents for parallel installation:

#### Spawn a Single Skill Agent
```bash
openclaw agent spawn \
  --task "Install skill 04 from ~/.openclaw/onboarding/04-superpowers. Read ALL .md files first, then execute. Report: 'Skill 04 complete - QC passed' or 'Skill 04 failed - [reason]'." \
  --label "skill-04"
```

#### Spawn Wave 2 - Agent A (Skills 04-07)
```bash
for skill in "04-superpowers" "05-ghl-setup" "06-ghl-install-pages" "07-kie-setup"; do
  num=${skill%%-*}
  openclaw agent spawn \
    --task "Install skill $num from ~/.openclaw/onboarding/$skill. Follow Teach Yourself Protocol. Report completion status." \
    --label "skill-$num" &
done
wait
```

#### Spawn Wave 2 - Agent B (Skills 08-11)
```bash
for skill in "08-vercel-setup" "09-context7" "10-github-setup" "11-superdesign"; do
  num=${skill%%-*}
  openclaw agent spawn \
    --task "Install skill $num from ~/.openclaw/onboarding/$skill. Follow Teach Yourself Protocol. Report completion status." \
    --label "skill-$num" &
done
wait
```

#### Spawn Wave 2 - Agent C (Skills 12-21)
```bash
for skill in "12-openrouter-setup" "13-google-workspace-setup" "14-google-workspace-integration" "15-blackceo-team-management" "16-summarize-youtube" "17-self-improving-agent" "18-proactive-agent" "19-humanizer" "20-youtube-watcher" "21-tavily-search"; do
  num=${skill%%-*}
  openclaw agent spawn \
    --task "Install skill $num from ~/.openclaw/onboarding/$skill. Follow Teach Yourself Protocol. Report completion status." \
    --label "skill-$num" &
done
wait
```

#### Spawn Wave 2 - Agent D (Skills 18-21)
```bash
for skill in "18-proactive-agent" "19-humanizer" "20-youtube-watcher" "21-tavily-search"; do
  num=${skill%%-*}
  openclaw agent spawn \
    --task "Install skill $num from ~/.openclaw/onboarding/$skill. Follow Teach Yourself Protocol. Report completion status." \
    --label "skill-$num" &
done
wait
```

#### Spawn Wave 4 - Agent E (Skills 24-26)
```bash
for skill in "24-storyboard-writer" "25-video-creator" "26-caption-creator"; do
  num=${skill%%-*}
  openclaw agent spawn \
    --task "Install skill $num from ~/.openclaw/onboarding/$skill. Follow Teach Yourself Protocol. Report completion status." \
    --label "skill-$num" &
done
wait
```

#### Spawn Wave 4 - Agent F (Skills 27-30)
```bash
for skill in "27-video-editor" "28-cinematic-forge" "29-ghl-convert-and-flow"; do
  num=${skill%%-*}
  openclaw agent spawn \
    --task "Install skill $num from ~/.openclaw/onboarding/$skill. Follow Teach Yourself Protocol. Report completion status." \
    --label "skill-$num" &
done
wait
```

---

### Real-Time Progress Tracking

Progress is tracked in a JSON file:

```bash
PROGRESS_FILE="$HOME/.openclaw/onboarding/.install-progress"

# Read current progress
cat "$PROGRESS_FILE" | jq .
```

**Progress File Format:**
```json
{
  "wave": 2,
  "total_waves": 5,
  "skills_completed": 15,
  "total_skills": 30,
  "status": "Wave 2 in progress - Agent C completing",
  "last_update": "2026-03-13 09:15:32"
}
```

**Update progress after each skill:**
```bash
# After skill completes, update the count
current_completed=$(cat "$PROGRESS_FILE" | jq -r '.skills_completed')
new_completed=$((current_completed + 1))

echo "{\"wave\":2,\"total_waves\":5,\"skills_completed\":$new_completed,\"total_skills\":30,\"status\":\"Skill 15 complete\"}" > "$PROGRESS_FILE"
```

**Report progress to user:**
```bash
report_progress() {
  local wave="$1"
  local message="$2"
  echo "[Wave $wave/5] $message"
  
  # Also send to messaging channel if available
  openclaw agent --message "Onboarding progress: Wave $wave/5 - $message" --deliver 2>/dev/null || true
}
```

---

### QC Checklist for Each Skill

Every sub-agent MUST run this QC checklist after installation:

```bash
qc_skill() {
  local skill_num="$1"
  local skill_folder="$2"
  local ONBOARDING_DIR="$HOME/.openclaw/onboarding"
  
  echo "Running QC for Skill $skill_num..."
  
  # 1. Check skill folder exists
  if [ ! -d "$ONBOARDING_DIR/$skill_folder" ]; then
    echo "FAIL: Skill folder not found"
    return 1
  fi
  
  # 2. Check SKILL.md exists
  if [ ! -f "$ONBOARDING_DIR/$skill_folder/SKILL.md" ]; then
    echo "FAIL: SKILL.md missing"
    return 1
  fi
  
  # 3. Check all .md files were read (verification)
  md_count=$(find "$ONBOARDING_DIR/$skill_folder" -name "*.md" | wc -l)
  if [ "$md_count" -eq 0 ]; then
    echo "FAIL: No .md files found"
    return 1
  fi
  
  # 4. Verify success criteria from SKILL.md
  # (Read SKILL.md and check each criterion)
  
  # 5. Check for .skill file (if applicable)
  local skill_file="$ONBOARDING_DIR/$skill_folder/${skill_folder#*-}.skill"
  if [ -f "$skill_file" ]; then
    echo "  ✓ Skill package present"
  fi
  
  echo "✓ Skill $skill_num QC PASSED"
  return 0
}
```

**Required QC Reporting Format:**
- **PASS:** `"Skill X complete - QC passed"`
- **FAIL:** `"Skill X failed - [specific reason]"`

---

### Wave Completion Waiting

Wait for all agents in a wave to complete:

```bash
wait_for_wave() {
  local wave="$1"
  local expected_skills="$2"
  local timeout_minutes="${3:-30}"
  local PROGRESS_FILE="$HOME/.openclaw/onboarding/.install-progress"
  
  echo "Waiting for Wave $wave completion..."
  
  local start_time=$(date +%s)
  local timeout_seconds=$((timeout_minutes * 60))
  
  while true; do
    local current_time=$(date +%s)
    local elapsed=$((current_time - start_time))
    
    if [ $elapsed -gt $timeout_seconds ]; then
      echo "WARNING: Wave $wave timeout"
      return 1
    fi
    
    # Check progress
    local completed=$(cat "$PROGRESS_FILE" 2>/dev/null | jq -r '.skills_completed' || echo "0")
    
    if [ "$completed" -ge "$expected_skills" ]; then
      echo "Wave $wave complete: $completed/$expected_skills skills"
      return 0
    fi
    
    sleep 10
  done
}
```

---

### Critical Rules for Parallel Installation

1. **MAXIMUM 4 SUB-AGENTS AT ONCE** - Never spawn more than 4 parallel agents
2. **SEQUENTIAL WAVES** - Wave N must signal completion before Wave N+1 starts
3. **MAIN ORCHESTRATOR ONLY** - Skills 22 and 23 MUST be installed by main agent, NEVER sub-agents
4. **QC AFTER EACH SKILL** - Not just at wave end - every skill gets QC'd
5. **REAL-TIME REPORTING** - Update progress file and notify after EACH skill
6. **FAILURE HANDLING** - If a skill fails, log it but continue (optional skills) or stop (critical skills)

### Critical Skills (Cannot Skip)
- Skill 01: Teach Yourself Protocol
- Skill 02: Back Yourself Up Protocol  
- Skill 03: Agent Browser
- Skill 22: Book-to-Persona
- Skill 23: AI Workforce Blueprint

### Optional Skills (Can Skip on Failure)
- All platform-specific skills (GHL, Google Workspace, Vercel, etc.) if missing API keys

---

## AUTO-START RULE - READ THIS BEFORE INSTALLING ANYTHING

**When you receive this file, begin immediately. Do not ask the user if you should start. Do not say "Ready to begin?" Do not wait for confirmation. Just start.**

The install script has already downloaded all skills to disk. Your job is to install them in order, one by one, automatically.

- Install Skill 01 → confirm it worked → install Skill 02 → confirm → continue through all 30
- Only pause when you need something the user must provide (API key not in any env file, 2FA code, first-time browser login)
- When you need a key: ask clearly, wait for answer, then continue
- When a skill is optional and the user wants to skip: mark SKIPPED, move to next - do not stop the whole install
- Do not announce "I will now install skill X" - just do it and report when done

---

## RESUME DETECTION - CHECK BEFORE STARTING

Before installing skill 01, check if a previous onboarding attempt is partially complete:

```bash
cat ~/.openclaw/onboarding/.onboarding-status 2>/dev/null
```

If this file exists with skill statuses, resume from the first skill not marked INSTALLED, ALREADY_INSTALLED, or SKIPPED. Do not reinstall skills that are already complete.

After each skill completes, append to ~/.openclaw/onboarding/.onboarding-status:
```
SKILL-01: INSTALLED
SKILL-02: INSTALLED
```
(Use INSTALLED, ALREADY_INSTALLED, SKIPPED, or FAILED)

---

## PROGRESS UPDATES

Every 5 skills completed, send a brief status update via the user's configured messaging channel:
"Onboarding in progress: [X] of 33 skills complete. Currently on: [skill name]."

---

## FINAL STEP - SET UP WEEKLY AUTO-UPDATE (Agent Runs This)

After all 33 skills are installed, run this as the final step.
The agent executes these commands - the human does nothing.

```bash
bash ~/Downloads/openclaw-master-files/OpenClaw\ Onboarding/scripts/setup-weekly-update.sh
```

Verify the cron job installed:
```bash
crontab -l | grep update-skills
```

**How the weekly update works (v2.0 - Surgical Logic):**
1. Runs every Sunday at 2:00 AM
2. Reads CHANGELOG.md from GitHub FIRST. It understands what's new before downloading anything
3. Compares against locally installed versions
4. Rates each change: LOW risk (auto-apply), MEDIUM risk (recommend + confirm), HIGH risk (recommend SKIP)
5. Surfaces recommendations to the user BEFORE making any changes
6. Waits for user approval on MEDIUM/HIGH items. It never acts autonomously
7. NEVER overwrites: core .md files (AGENTS, MEMORY, SOUL, USER, IDENTITY, HEARTBEAT, TOOLS), company department folders, or custom SOPs
8. NEVER triggers a gateway restart. Always gives client restart instructions instead

**IMPORTANT:** The update script will NEVER overwrite anything inside `my AI company departments/`. That folder contains client-built content and is always protected.

To force a manual check: `bash ~/Downloads/openclaw-master-files/OpenClaw\ Onboarding/scripts/update-skills.sh`
To check update logs: `cat ~/.openclaw/skills/.update-log`

---

## WHEN ONBOARDING IS COMPLETE

### Remove the ONBOARDING PENDING flag
Before sending the completion summary, remove the flag that install.sh wrote to AGENTS.md:

Open [WORKSPACE_ROOT]/AGENTS.md and delete the block that reads:
```
## ONBOARDING PENDING - EXECUTE NOW
...
```
If the block is not present, continue without error.

### Final Gemini Engine Indexing (MANDATORY)

After all 33 skills are installed, run the final Gemini Engine indexing:

```bash
# Final index update
python3 ~/clawd/scripts/gemini-indexer.py

# Final embeddings generation
# Handled by gemini-indexer.py

# Verify all collections are indexed
python3 ~/clawd/scripts/gemini-indexer.py --status
```

**Why this is needed:**
- Skill 23 indexed personas + workforce + master-files at that milestone
- Skills 24-30 may have added additional content
- This final embed ensures everything is searchable
- Report the final file count and collection status to the user

### How to deliver the completion summary
- If running in an active chat session: post the summary in that chat.
- If running as a background or sub-agent task: send the summary via the configured
  messaging channel (detected in prerequisites).
- Format the 30-skill status report as a table: Skill | Name | Status | Notes

Then write to MEMORY.md: "ONBOARDING COMPLETE - [date] - All 33 skills processed"

When every skill on the list above is installed and verified, tell the user:
1. Everything that was installed (all 33 skills with status: INSTALLED / ALREADY_INSTALLED / SKIPPED / FAILED)
2. Everything that was added to each workspace file (AGENTS.md, TOOLS.md, MEMORY.md, etc.)
3. Which workspace files were updated and which were not touched
4. Where the full documentation for each skill is saved (the master files folder path)
5. That the backup protocol is active and the first backup has been created

---

This file is part of the OpenClaw Onboarding system.
oarding system.
not touched
4. Where the full documentation for each skill is saved (the master files folder path)
5. That the backup protocol is active and the first backup has been created

---

This file is part of the OpenClaw Onboarding system.
oarding system.
