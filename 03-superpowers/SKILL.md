# Superpowers - Thinking Discipline for AI Agents

## What This Is

Superpowers is a set of rules and habits that stop your AI agent from making common coding mistakes. Think of it like a checklist a pilot uses before takeoff - it forces the agent to think before it acts, plan before it builds, and prove its work before claiming it is done.

It comes from an open-source project (github.com/obra/superpowers) and includes 14 separate skills that cover everything from brainstorming to debugging to code review.

## When to Use This Skill

Use this skill when:
- You are setting up a new OpenClaw agent and want it to write better code
- Your agent keeps guessing at bug fixes instead of finding the real problem
- Your agent claims "done!" but the code does not actually work
- You want your agent to plan before building, not just start typing code
- Someone says "use superpowers," "brainstorm this," or "debug this"
- Any time the agent is about to do software development work

## Prerequisites

You MUST have these two skills installed first, in this order:
1. Teach Yourself Protocol (TSP) - Skill 01
2. Back Yourself Up Protocol - Skill 02

Without TSP, the agent will dump too much content into your core files and waste tokens.

## The 4 Iron Laws (Non-Negotiable Rules)

These are the heart of Superpowers. The agent must follow these every time, no exceptions:

1. **No fixes without finding the real problem first.** Do not guess. Investigate.
2. **No code without a failing test first.** Write the test, watch it fail, then write the code.
3. **No claiming "done" without proof.** Run it. Show the output. "Should work" is not proof.
4. **Evidence before claims, always.** Never say "fixed" before testing it.

## The 14 Skills (What Gets Installed)

| Skill | What It Teaches |
|-------|----------------|
| brainstorming | Ask questions first, propose options, get approval before building |
| systematic-debugging | Find the real cause of bugs in 4 phases |
| test-driven-development | Write the test before the code, every time |
| verification-before-completion | Prove your work with actual output |
| writing-plans | Create step-by-step plans anyone can follow |
| writing-skills | How to create new skills for the framework |
| executing-plans | Follow plans without skipping or changing steps |
| subagent-driven-development | Use sub-agents for tasks, review their work |
| dispatching-parallel-agents | Run multiple agents at the same time for speed |
| using-git-worktrees | Work on separate branches without conflicts |
| finishing-a-development-branch | Clean up and merge code properly |
| receiving-code-review | Handle feedback without just agreeing to be polite |
| requesting-code-review | Review code and give useful feedback |
| using-superpowers | How to use the whole framework together |

## Files in This Folder and Reading Order

1. **SKILL.md** - You are here. Start here to understand what this skill is about.
2. **superpowers-full.md** - The complete guide. Covers installation steps, what to add to your core files (AGENTS.md, TOOLS.md, MEMORY.md), verification questions, and the full details of all 14 skills.
3. **INSTALL.md** - Quick install reference.
4. **INSTRUCTIONS.md** - Step-by-step execution instructions.
5. **EXAMPLES.md** - Real examples of how to use the skills.
6. **CORE_UPDATES.md** - Exactly what to add to your core .md files.
7. **superpowers.skill** - Machine-readable skill definition.

## What the Agent Needs to Know

- Superpowers downloads 14 skill folders from GitHub into your master files folder
- Each skill folder has a SKILL.md the agent reads before doing that type of work
- The workflow for building something new is: brainstorm with the user, write a plan, get approval, then execute using sub-agents
- The workflow for fixing a bug is: investigate root cause (4 phases), then fix, then verify
- The agent must NEVER skip the planning step, even for "simple" tasks
- The agent must NEVER claim work is done without running verification and showing output
- After installation, only summaries and file paths go into AGENTS.md and TOOLS.md - never the full skill content
- The full.md includes a 5-question comprehension test the agent must pass after learning
