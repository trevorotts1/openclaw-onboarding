╔══════════════════════════════════════════════════════════════╗
  MANDATORY TSP CHECK - READ THIS BEFORE ANYTHING ELSE
DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TSP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TSP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TSP"
- Look in your session context for prior TSP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TSP:
Proceed to the instructions below. Follow the TSP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TSP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TSP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TSP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TSP CONFIRMED.

TSP FILE STORAGE INSTRUCTIONS (only read this if TSP confirmed)

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

RULE 2: DO NOT CHANGE TREVOR'S INTENT
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
Ask Trevor first. Do not guess. Do not assume.

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

This guide walks you through installing the Superpowers discipline framework on your AI agent. Superpowers is a set of 14 skill files that teach your AI agent how to think properly before coding, debug systematically, and never claim something is "done" without proof.

## Learning Sequence

Before you install Superpowers, make sure these two prerequisites are already complete:
1. Teach Yourself Protocol (TSP) - must be learned first
2. Backup Protocol - must be learned second
3. Superpowers - this is step 3 in the sequence

If either prerequisite is missing, stop and go learn those first.


## What You Are Installing

Superpowers comes from this open-source project: https://github.com/obra/superpowers

It contains 14 skill files. Each skill is a short document (called SKILL.md) that teaches your AI agent a specific thinking pattern. Here is the complete list:

| Number | Skill Name | What It Teaches |
|--------|-----------|----------------|
| 1 | brainstorming | Ask questions one at a time, propose 2-3 approaches, present design in small chunks, validate each section |
| 2 | systematic-debugging | 4-phase debugging: root cause investigation, pattern analysis, hypothesis testing, implementation |
| 3 | test-driven-development | Write the failing test FIRST, then implement, then refactor. No exceptions. |
| 4 | verification-before-completion | Run actual verification commands, show output, never claim done without evidence |
| 5 | writing-plans | Create implementation plans clear enough for a junior engineer with no context |
| 6 | writing-skills | How to write new skills for the framework |
| 7 | executing-plans | How to follow plans step by step without deviation |
| 8 | subagent-driven-development | Spawn sub-agents per task, review their work, continue forward |
| 9 | dispatching-parallel-agents | Run multiple agents in parallel for speed |
| 10 | using-git-worktrees | Isolated workspaces on separate branches |
| 11 | finishing-a-development-branch | Clean up, squash, merge properly |
| 12 | receiving-code-review | How to handle feedback without performative agreement |
| 13 | requesting-code-review | How to review code and give actionable feedback |
| 14 | using-superpowers | Meta-skill: how to use the whole framework |


## Step-by-Step Installation

### Step 1: Find or Create the Master Files Folder

Your AI agent needs to find the folder where OpenClaw master files are stored. This folder lives inside your Downloads folder. It might be named any of these:
- openclaw-master-files
- OpenClaw Master Files
- OpenClaw Master Documents
- OpenClaw Documents
- openclaw master files
- OpenClaw Files
- openclaw-documents

To search for it, run this command in your terminal (the black window where you type commands):

```
find ~/Downloads/ -maxdepth 1 -type d -iname "*openclaw*" 2>/dev/null
```

If nothing comes back (meaning the folder does not exist yet), create one by running:

```
mkdir -p ~/Downloads/openclaw-master-files
```


### Step 2: Create the Superpowers Subfolder

Inside that master files folder, create a folder specifically for Superpowers:

```
mkdir -p [MASTER_FILES_FOLDER]/superpowers
```

Replace [MASTER_FILES_FOLDER] with the actual path you found or created in Step 1. For example, if your folder is at ~/Downloads/openclaw-master-files, you would run:

```
mkdir -p ~/Downloads/openclaw-master-files/superpowers
```


### Step 3: Download the Superpowers Files

You have three options. Pick whichever one works for your setup.

**Option A - If git is installed (most common):**

```
cd [MASTER_FILES_FOLDER]/superpowers
git clone https://github.com/obra/superpowers.git .
```

The period at the end is important. It tells git to put the files directly into the superpowers folder instead of creating another folder inside it.


**Option B - If git is NOT installed:**

1. Open your web browser
2. Go to https://github.com/obra/superpowers/archive/refs/heads/main.zip
3. A zip file will download automatically
4. Find the zip file in your Downloads folder
5. Double-click it to unzip it
6. Move the contents into your superpowers folder


**Option C - Download just the skill files one at a time using curl:**

Run each of these commands. They download each individual skill file:

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

Some skills have extra files you should also download:

- requesting-code-review: code-reviewer.md
- subagent-driven-development: code-quality-reviewer-prompt.md, implementer-prompt.md, spec-reviewer-prompt.md
- systematic-debugging: condition-based-waiting.md, defense-in-depth.md, root-cause-tracing.md, find-polluter.sh
- test-driven-development: testing-anti-patterns.md
- writing-skills: anthropic-best-practices.md, persuasion-principles.md, testing-skills-with-subagents.md


### Step 4: Verify the Download

Count the skill folders to make sure all 14 downloaded correctly:

```
ls -d [MASTER_FILES_FOLDER]/superpowers/skills/*/ | wc -l
```

You should see the number 14. If you see less than 14, go back and download the missing ones.

Then check that every skill has its SKILL.md file:

```
for skill in [MASTER_FILES_FOLDER]/superpowers/skills/*/; do
    if [ -f "$skill/SKILL.md" ]; then
        echo "OK: $(basename $skill)"
    else
        echo "MISSING: $(basename $skill)/SKILL.md"
    fi
done
```

Every single one should say "OK." If any say "MISSING," go back and re-download that specific skill.


### Step 5: Read and Internalize the Skills

Now the AI agent must actually READ each downloaded skill file to learn the thinking patterns. Read them in this specific order (it builds from foundational concepts to advanced ones):

1. using-superpowers/SKILL.md (the meta-skill - explains how the whole framework works)
2. brainstorming/SKILL.md (how to think before any creative work)
3. systematic-debugging/SKILL.md (how to fix problems without guessing)
4. test-driven-development/SKILL.md (how to write code properly)
5. verification-before-completion/SKILL.md (how to prove you are actually done)
6. writing-plans/SKILL.md (how to plan before implementing)
7. executing-plans/SKILL.md (how to follow the plan)
8. subagent-driven-development/SKILL.md (how to use sub-agents)
9. dispatching-parallel-agents/SKILL.md (how to run agents in parallel)
10. writing-skills/SKILL.md (how to create new skills)
11. using-git-worktrees/SKILL.md (isolated development)
12. finishing-a-development-branch/SKILL.md (clean merge)
13. requesting-code-review/SKILL.md (reviewing others)
14. receiving-code-review/SKILL.md (handling feedback)

For each skill, understand three things:
- When does this skill activate? (what triggers it?)
- What steps does the agent follow? (the process)
- What is the agent NOT allowed to do? (the constraints)

After reading all 14, the agent should be able to explain each one in a single sentence.


### Step 6: Update Your Core .md Files

Follow the TSP rules here. Only add summaries and file path references. Never paste the full skill content into your core files.

**What to add to AGENTS.md** - see the [ADD TO AGENTS.md] section in the superpowers-full.md file. It contains the 4 Iron Laws, the Thinking Sequence, Anti-Patterns, and Workflow Map.

**What to add to TOOLS.md** - see the [ADD TO TOOLS.md] section in the superpowers-full.md file. It contains a brief reference with the skills list and trigger map.

**What to add to MEMORY.md** - see the [ADD TO MEMORY.md] section in the superpowers-full.md file. It contains a one-line note that Superpowers was installed and verified.


### Step 7: Verify You Learned It

The AI agent must demonstrate it understood the skills by answering these five questions correctly:

1. "You found a bug in a function. What do you do FIRST?"
   - Correct answer: Investigate root cause (systematic-debugging Phase 1). Do NOT guess at a fix.

2. "You need to add a new feature. What do you do BEFORE writing any code?"
   - Correct answer: Brainstorm with the user (ask questions one at a time), write a plan, get approval.

3. "You wrote the fix and it seems to work. Can you tell the user it is done?"
   - Correct answer: No. Run the verification command, show the output, THEN say done.

4. "The user wants a new function. What is the first line of code you write?"
   - Correct answer: A failing test for that function. Not the function itself.

5. "You have 10 tasks to implement from a plan. How do you execute them?"
   - Correct answer: Spawn sub-agents (subagent-driven-development), one per task, review their output.

If the agent gets any wrong, re-read the relevant SKILL.md and try again.


## Installation for Other Platforms (Reference Only)

These commands are for other AI coding tools, not OpenClaw. Included here just for reference.

- **Claude Code:** /plugin marketplace add obra/superpowers-marketplace then /plugin install superpowers@superpowers-marketplace
- **Cursor:** /plugin-add superpowers
- **Codex:** Tell it to fetch and follow instructions from https://raw.githubusercontent.com/obra/superpowers/refs/heads/main/.codex/INSTALL.md
- **OpenCode:** Tell it to fetch and follow instructions from https://raw.githubusercontent.com/obra/superpowers/refs/heads/main/.opencode/INSTALL.md
