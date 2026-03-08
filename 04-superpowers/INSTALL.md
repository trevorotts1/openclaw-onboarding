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

EXECUTION DISCIPLINE - MANDATORY BEFORE YOU START
╚══════════════════════════════════════════════════════════════╝

These rules apply every single time you execute instructions from this document.
No exceptions. No shortcuts. No improvising.

RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING
Read this entire document from top to bottom before executing a single step.
Do not start executing while still reading. Finish reading first. Then start.

RULE 2: DO NOT CHANGE THE OPERATOR'S INTENT
These instructions say exactly what to do. Execute them exactly as written.
- Do NOT reinterpret steps
- Do NOT "improve" the instructions
- Do NOT skip steps because they seem unnecessary
- Do NOT add steps that are not in the document
- Do NOT change the order of steps
If a step says do X, do X. Not Y. Not a better version of X. X.

RULE 3: NEVER MODIFY THESE WITHOUT PERMISSION
- API keys - copy them exactly, character for character
- Terminal commands - run them exactly as written, no edits
- Config values - use the exact values specified
- Model names - use the exact names specified, spelling matters
- File paths - use the exact paths specified
If you are unsure whether something should be changed, the answer is NO.
Ask the operator. Do not guess. Do not assume.

RULE 4: BUILD YOUR CHECKLIST BEFORE EXECUTING
Before you run a single command or make a single change, create a numbered
checklist of every action this document requires you to take. Write it out.
Show it to the user before starting. Get confirmation. Then execute.

RULE 5: CHECK YOURSELF AGAINST THE CHECKLIST WHEN DONE
When you believe you are finished, go back to your checklist.
Verify every single item was completed. Check it off explicitly.
If anything was missed, complete it before telling the user you are done.
Do NOT tell the user you are done until the checklist is 100% complete.

RULE 6: REPORT WHAT YOU DID
When finished, give the user a clear summary:
- What was completed
- What commands were run
- What files were changed
- Any errors encountered and how they were resolved
- Confirmation that the checklist was fully satisfied

══════════════════════════════════════════════════════════════════

# Superpowers - Installation Guide

This guide automates the installation of the Superpowers discipline framework on an AI agent. Superpowers is a set of 14 skill files that teach the agent how to think properly before coding, debug systematically, and never claim something is "done" without proof.

## Learning Sequence

The agent must verify these two prerequisites are already complete before proceeding:
1. Teach Yourself Protocol (TYP) - must be learned first
2. Backup Protocol - must be learned second
3. Superpowers - this is step 3 in the sequence

If either prerequisite is missing, the agent must stop and report this to the user.

**CONFLICT RULE - MANDATORY:** If this skill's files (SKILL.md, CORE_UPDATES.md, INSTALL.md, USAGE.md) conflict with TYP instructions on WHAT to add to core files or WHICH files to update, this skill wins. Always. TYP governs HOW to store (lean summaries + file paths). This skill governs WHAT content goes in and which files it touches. When in doubt: skill docs win.


## What Will Be Installed

Superpowers comes from this open-source project: https://github.com/obra/superpowers

It contains 14 skill files plus commands and agent files. Each skill is a short document (called SKILL.md) that teaches the agent a specific thinking pattern. Here is the complete list:

**Important version notes:**
- **v4.3.0 (Feb 12, 2026):** Brainstorming now has a HARD GATE - no code, no scaffolding, no implementation until design is presented and user has approved it. EnterPlanMode is intercepted to check brainstorming first.
- **v4.2.0 (Feb 5, 2026):** `using-git-worktrees` is now REQUIRED before `subagent-driven-development` and `executing-plans`. Never implement directly on main branch.

| Number | Skill Name | What It Teaches |
|--------|-----------|----------------|
| 1 | brainstorming | Ask questions one at a time, propose 2-3 approaches, present design in small chunks, validate each section |
| 2 | systematic-debugging | 4-phase debugging: root cause investigation, pattern analysis, hypothesis testing, implementation |
| 3 | test-driven-development | Write the failing test FIRST, then implement, then refactor. No exceptions. |
| 4 | verification-before-completion | Run actual verification commands, show output, never claim done without evidence |
| 5 | writing-plans | Create implementation plans clear enough for a junior engineer with no context |
| 6 | writing-skills | How to write new skills for the framework |
| 7 | executing-plans | How to follow plans step by step without deviation. **Requires using-git-worktrees first.** |
| 8 | subagent-driven-development | Spawn sub-agents per task, review their work, continue forward. **Requires using-git-worktrees first.** |
| 9 | dispatching-parallel-agents | Run multiple agents in parallel for speed |
| 10 | using-git-worktrees | Isolated workspaces on separate branches |
| 11 | finishing-a-development-branch | Clean up, squash, merge properly |
| 12 | receiving-code-review | How to handle feedback without performative agreement |
| 13 | requesting-code-review | How to review code and give actionable feedback |
| 14 | using-superpowers | Meta-skill: how to use the whole framework |


## Automated Installation Steps

### Step 1: Locate or Create the Master Files Folder

The agent must find the folder where OpenClaw master files are stored. This folder lives inside ~/Downloads/. Possible names:
- openclaw-master-files
- OpenClaw Master Files
- OpenClaw Master Documents
- OpenClaw Documents
- openclaw master files
- OpenClaw Files
- openclaw-documents

Execute this command to search:

```
find ~/Downloads/ -maxdepth 1 -type d -iname "*openclaw*" 2>/dev/null
```

If the search returns no results, create the folder:

```
mkdir -p ~/Downloads/openclaw-master-files
```

Store the path for use in subsequent steps.


### Step 2: Create the Superpowers Subfolder

Create a folder specifically for Superpowers inside the master files folder:

```
mkdir -p [MASTER_FILES_FOLDER]/superpowers
```

Replace [MASTER_FILES_FOLDER] with the actual path from Step 1. Example:

```
mkdir -p ~/Downloads/openclaw-master-files/superpowers
```


### Step 3: Download the Superpowers Files

Execute one of these three download methods. Choose based on system capabilities.

**Method A - Using git (PREFERRED - gets everything):**

```
cd [MASTER_FILES_FOLDER]/superpowers
git clone https://github.com/obra/superpowers.git .
```

The period at the end is critical. It places files directly into the superpowers folder.
Git clone downloads ALL folders: skills/, commands/, agents/, hooks/, lib/ - everything in the repo.
This is the preferred method. If git is available, always use Method A, not Method C.


**Method B - Using browser and manual extraction (if git unavailable):**

1. Open browser to: https://github.com/obra/superpowers/archive/refs/heads/main.zip
2. Wait for zip file to download to ~/Downloads/
3. Extract the zip file
4. Move contents into [MASTER_FILES_FOLDER]/superpowers/


**Method C - Using curl to download individual skill files:**

Execute each command in sequence:

```
curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/brainstorming/SKILL.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/brainstorming/SKILL.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/systematic-debugging/SKILL.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/systematic-debugging/SKILL.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/test-driven-development/SKILL.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/test-driven-development/SKILL.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/verification-before-completion/SKILL.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/verification-before-completion/SKILL.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/writing-plans/SKILL.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/writing-plans/SKILL.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/writing-skills/SKILL.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/writing-skills/SKILL.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/executing-plans/SKILL.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/executing-plans/SKILL.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/subagent-driven-development/SKILL.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/subagent-driven-development/SKILL.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/dispatching-parallel-agents/SKILL.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/dispatching-parallel-agents/SKILL.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/using-git-worktrees/SKILL.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/using-git-worktrees/SKILL.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/finishing-a-development-branch/SKILL.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/finishing-a-development-branch/SKILL.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/receiving-code-review/SKILL.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/receiving-code-review/SKILL.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/requesting-code-review/SKILL.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/requesting-code-review/SKILL.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/using-superpowers/SKILL.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/using-superpowers/SKILL.md
```

Also download the README:
```
curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/README.md" -o [MASTER_FILES_FOLDER]/superpowers/README.md
```

Download additional support files for specific skills:

```
curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/requesting-code-review/code-reviewer.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/requesting-code-review/code-reviewer.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/subagent-driven-development/code-quality-reviewer-prompt.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/subagent-driven-development/code-quality-reviewer-prompt.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/subagent-driven-development/implementer-prompt.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/subagent-driven-development/implementer-prompt.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/subagent-driven-development/spec-reviewer-prompt.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/subagent-driven-development/spec-reviewer-prompt.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/systematic-debugging/condition-based-waiting.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/systematic-debugging/condition-based-waiting.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/systematic-debugging/defense-in-depth.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/systematic-debugging/defense-in-depth.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/systematic-debugging/root-cause-tracing.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/systematic-debugging/root-cause-tracing.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/systematic-debugging/find-polluter.sh" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/systematic-debugging/find-polluter.sh

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/test-driven-development/testing-anti-patterns.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/test-driven-development/testing-anti-patterns.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/writing-skills/anthropic-best-practices.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/writing-skills/anthropic-best-practices.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/writing-skills/persuasion-principles.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/writing-skills/persuasion-principles.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/skills/writing-skills/testing-skills-with-subagents.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/skills/writing-skills/testing-skills-with-subagents.md
```

Download commands (slash commands for brainstorm, write-plan, execute-plan):

```
curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/commands/brainstorm.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/commands/brainstorm.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/commands/write-plan.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/commands/write-plan.md

curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/commands/execute-plan.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/commands/execute-plan.md
```

Download agents (code reviewer agent):

```
curl -sL "https://raw.githubusercontent.com/obra/superpowers/main/agents/code-reviewer.md" --create-dirs -o [MASTER_FILES_FOLDER]/superpowers/agents/code-reviewer.md
```


### Step 4: Verify All Downloads

Count the skill folders to confirm all 14 downloaded:

```
ls -d [MASTER_FILES_FOLDER]/superpowers/skills/*/ | wc -l
```

Expected output: 14

If output is less than 14, re-download missing skills.

Verify commands and agents downloaded:

```
ls [MASTER_FILES_FOLDER]/superpowers/commands/
```

Expected: brainstorm.md, write-plan.md, execute-plan.md

```
ls [MASTER_FILES_FOLDER]/superpowers/agents/
```

Expected: code-reviewer.md

Verify every skill has its SKILL.md file:

```
for skill in [MASTER_FILES_FOLDER]/superpowers/skills/*/; do
    if [ -f "$skill/SKILL.md" ]; then
        echo "OK: $(basename $skill)"
    else
        echo "MISSING: $(basename $skill)/SKILL.md"
    fi
done
```

Expected output: All skills marked "OK"

If any skills are marked "MISSING," re-download those specific skills.


### Step 5: Read and Internalize All Skills

The agent must read each downloaded skill file in this specific order to build foundational understanding:

1. using-superpowers/SKILL.md (meta-skill - explains the whole framework)
2. brainstorming/SKILL.md (foundational thinking pattern)
3. systematic-debugging/SKILL.md (problem-solving methodology)
4. test-driven-development/SKILL.md (code quality discipline)
5. verification-before-completion/SKILL.md (proof-based completion)
6. writing-plans/SKILL.md (planning methodology)
7. executing-plans/SKILL.md (execution discipline)
8. subagent-driven-development/SKILL.md (agent coordination)
9. dispatching-parallel-agents/SKILL.md (parallel execution)
10. writing-skills/SKILL.md (skill creation methodology)
11. using-git-worktrees/SKILL.md (isolated development)
12. finishing-a-development-branch/SKILL.md (merge discipline)
13. requesting-code-review/SKILL.md (code review methodology)
14. receiving-code-review/SKILL.md (feedback handling)

For each skill, the agent must understand:
- When does this skill activate? (trigger conditions)
- What steps does the agent follow? (process)
- What is the agent NOT allowed to do? (constraints)

After reading all 14, the agent must be able to explain each one in a single sentence.


### Step 6: Update Core .md Files

Follow TYP rules. Add only summaries and file path references. Never paste full skill content into core files.

**For AGENTS.md** - Add the content from the [ADD TO AGENTS.md] section. This includes the 4 Iron Laws, the Thinking Sequence, Anti-Patterns, and Workflow Map.

**For TOOLS.md** - Add the content from the [ADD TO TOOLS.md] section. This includes a brief reference with the skills list and trigger map.

**For MEMORY.md** - Add the content from the [ADD TO MEMORY.md] section. This includes a one-line note that Superpowers was installed and verified.


### Step 7: Verify Learning Comprehension

The agent must answer these five questions correctly to demonstrate understanding:

**Question 1:** "You found a bug in a function. What do you do FIRST?"
- Correct answer: Investigate root cause (systematic-debugging Phase 1). Do NOT guess at a fix.

**Question 2:** "You need to add a new feature. What do you do BEFORE writing any code?"
- Correct answer: Brainstorm with the user (ask questions one at a time), write a plan, get approval.

**Question 3:** "You wrote the fix and it seems to work. Can you tell the user it is done?"
- Correct answer: No. Run the verification command, show the output, THEN say done.

**Question 4:** "The user wants a new function. What is the first line of code you write?"
- Correct answer: A failing test for that function. Not the function itself.

**Question 5:** "You have 10 tasks to implement from a plan. How do you execute them?"
- Correct answer: Spawn sub-agents (subagent-driven-development), one per task, review their output.

If the agent answers any question incorrectly, re-read the relevant SKILL.md and retry.


## Installation for Other Platforms (Reference Only)

These commands are for other AI coding tools, not OpenClaw. Included for reference only.

- **Claude Code:** /plugin marketplace add obra/superpowers-marketplace then /plugin install superpowers@superpowers-marketplace
- **Cursor:** /plugin-add superpowers
- **Codex:** Fetch and follow instructions from https://raw.githubusercontent.com/obra/superpowers/refs/heads/main/.codex/INSTALL.md
- **OpenCode:** Fetch and follow instructions from https://raw.githubusercontent.com/obra/superpowers/refs/heads/main/.opencode/INSTALL.md
