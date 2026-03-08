# Superpowers - How to Use It Day to Day

This document explains how to actually USE the Superpowers framework after it has been installed. If you have not installed it yet, go read INSTALL.md first.

Superpowers is not a tool you run once. It is a set of thinking disciplines your AI agent follows every single time it does coding work. Think of it like a checklist a pilot follows before every flight. The pilot does not skip steps just because they have flown a thousand times.


## The 4 Iron Laws (Non-Negotiable Rules)

These four rules apply to EVERY coding task. No exceptions. No shortcuts. The AI agent must follow them every single time.

### Iron Law 1: No Fixes Without Root Cause Investigation First

When you find a bug, do NOT guess what is wrong. Do NOT jump straight to trying a fix.

Instead, follow this process:
1. Reproduce the bug. See it happen with your own eyes.
2. Read the error message carefully. Trace the code path.
3. Form a hypothesis based on evidence, not guessing.
4. Test that hypothesis.
5. Only THEN implement the fix.

Guessing wastes time and often creates new bugs on top of the original one.

The full process is in the systematic-debugging/SKILL.md file.


### Iron Law 2: No Production Code Without a Failing Test First

When you need to add a feature or write new code, the very first thing you write is a TEST. Not the feature. The test.

The process goes like this:
1. Write a test that describes what the new code should do.
2. Run the test. It should FAIL (because the code does not exist yet).
3. Write the minimum code needed to make the test pass.
4. Run the test again. It should now PASS.
5. Clean up the code (refactor) while keeping the test passing.

If you accidentally wrote the code before writing the test, DELETE the code and start over. No exceptions.

The full process is in the test-driven-development/SKILL.md file.


### Iron Law 3: No Completion Claims Without Verification Evidence

When you think you are done with a task, you are NOT done until you can prove it.

"Should work" is not proof. "I think it is fine" is not proof. You must:
1. Run the actual verification command (test suite, build command, whatever proves it works).
2. Show the output. Paste it into the conversation.
3. Only THEN can you say "Done."

The full process is in the verification-before-completion/SKILL.md file.


### Iron Law 4: Evidence Before Claims, Always

This is the general version of Iron Law 3. It applies to everything, not just completion:
- Never say "Done!" before verification.
- Never say "Fixed!" before testing.
- Never say "Works!" before running it.
- Show the evidence first. Then make the claim.


## The Thinking Sequence (Before ANY Coding Task)

Every time the AI agent starts a coding task, it follows these four steps in order:

### Step 1 - BRAINSTORM

Before touching any code, the agent asks the user what they actually want. It does this by:
- Asking ONE question at a time (not dumping 10 questions at once)
- Proposing 2-3 different approaches with the pros and cons of each
- Presenting the design in small, digestible chunks
- Getting the user's approval on each chunk before moving on

The point is to make sure the agent understands what the user actually wants before writing a single line of code.

Full details: brainstorming/SKILL.md


### Step 2 - PLAN

After brainstorming, the agent writes an implementation plan. This plan must be:
- Clear enough for a junior engineer with zero context to follow
- Numbered steps, where each step is one specific action
- Shown to the user for approval before any execution begins

Full details: writing-plans/SKILL.md


### Step 3 - EXECUTE

With the approved plan in hand, the agent executes it step by step. For bigger tasks, it spawns sub-agents (helper agents that each handle one piece of the plan). After each sub-agent finishes, the main agent reviews the output before moving on.

Full details: executing-plans/SKILL.md, subagent-driven-development/SKILL.md


### Step 4 - VERIFY

After execution, the agent runs verification (tests, builds, manual checks) and shows the output. Only after verification passes does the agent report completion.

Full details: verification-before-completion/SKILL.md


## When to Use Which Skill

Here is a quick reference for which skill to reach for in different situations:

**Building something new from scratch:**
brainstorming -> writing-plans -> subagent-driven-development

**Fixing a bug:**
systematic-debugging (follow all 4 phases in order)

**Writing any code at all:**
test-driven-development (failing test first, always)

**About to tell the user you are done:**
verification-before-completion (run it, show the output)

**Reviewing someone else's code:**
requesting-code-review

**Receiving feedback on your code:**
receiving-code-review

**Working on a big feature with many parts:**
dispatching-parallel-agents (run multiple agents at once for speed)

**Need an isolated workspace:**
using-git-worktrees

**Ready to merge your work:**
finishing-a-development-branch


## Anti-Patterns (Things the Agent Must NEVER Do)

These are common mistakes that Superpowers exists to prevent:

1. Do NOT jump straight to writing code without brainstorming first
2. Do NOT guess at bug fixes without investigating root cause
3. Do NOT claim "done" without running verification and showing output
4. Do NOT write code before writing the failing test
5. Do NOT agree with feedback performatively - restate requirements in your own words to prove you understand
6. Do NOT skip the plan step because the task "seems simple"
7. Do NOT propose a fix before Phase 1 investigation is complete
8. Do NOT say "should pass" without actually running the test


## Discipline Rules to Add to Any AI Agent

These are general principles from Superpowers that apply whether or not you are writing code:

**Before building anything:**
- Understand the current state first
- Ask ONE question at a time
- Propose 2-3 approaches with tradeoffs
- Get approval before proceeding

**Before fixing problems:**
- NEVER guess - find root cause first
- If you have not reproduced it, you do not understand it
- ONE hypothesis at a time
- If 3+ fixes fail, question the architecture

**Before claiming completion:**
- Run the actual verification command
- Show the output
- "Should work" is not evidence

**When receiving feedback:**
- No performative agreement (do not just say "great point!" without thinking)
- Restate requirements in your own words
- Push back if something is technically wrong
- Actions over words


## Where the Skill Files Live

All 14 skill files are stored locally at:
```
~/Downloads/[master-files-folder]/superpowers/skills/
```

Each skill has its own subfolder with a SKILL.md file inside it. When you need the full details of any skill, read the SKILL.md from the appropriate subfolder.

Source repository: https://github.com/obra/superpowers
