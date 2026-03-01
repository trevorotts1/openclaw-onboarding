# Teach Yourself Protocol (TSP)

## What This Skill Is About

The Teach Yourself Protocol is the foundation of how every OpenClaw agent learns new
things. It is a structured, step-by-step process for taking in new knowledge - whether
it is an API reference, a business process, a client preference, or a tool guide - and
storing it in the right place so the agent can find it and use it in future sessions.

Without this protocol, agents either dump everything into their core workspace files
(which makes them bloated and slow) or forget what they learned entirely (because AI
agents start fresh every session with no built-in memory). TSP solves both problems.

## When This Skill Triggers

**Explicit triggers** - the user says things like:
- "Teach yourself this"
- "Learn this"
- "Train yourself on this"
- "Memorize this"
- "Save this for future reference"

**Implicit triggers** - the agent should auto-detect these:
- User shares a large document (50+ lines of structured reference material)
- User provides corrections or updated information about a tool or process
- User explains how something works in detail
- User shares credentials, account structures, or system architecture
- User shares a file saying "here you go" or "use this" without further instructions

**Important:** Every time TSP activates, the agent MUST announce it to the user before
doing any TSP work. Never run TSP silently.

## What It Covers

- **Three-Layer Knowledge Architecture** - lightweight summaries in core files (Layer 1),
  deep reference files in the master files folder (Layer 2), and organized folder
  structures for large topics like APIs (Layer 3)
- **The Decision Tree** - a step-by-step process: understand the knowledge, assess its
  size, check for conflicts with existing knowledge, create the right files, write
  lightweight summaries, and confirm to the user
- **Conflict Resolution** - what to do when new knowledge replaces, expands, or
  contradicts something the agent already knows
- **Priority Tagging** - CRITICAL, HIGH, STANDARD, or REFERENCE, so the agent knows
  what matters most
- **API Documentation** - special handling for APIs including folder structures,
  README indexes, and endpoint organization
- **Skills and Instruction Files** - every skill must have a matching instruction file
- **Versioning** - tracking when knowledge was learned and when it was last verified
- **Cross-Referencing** - linking related deep files to each other
- **Anti-Bloat Rules** - keeping core files lean and preventing duplicated content
- **Common Mistakes** - 10 real mistakes agents make and how to avoid them
- **Self-Installation** - how the protocol installs itself using its own rules

## Files in This Folder

Read them in this order:

1. **SKILL.md** (this file) - overview and orientation
2. **teach-yourself-protocol-full.md** - the complete protocol with all 19 sections,
   decision trees, examples, and checklists. This is the authoritative reference.
3. **INSTRUCTIONS.md** - step-by-step guide for executing TSP
4. **INSTALL.md** - how to install TSP into a new agent's workspace
5. **EXAMPLES.md** - worked examples showing TSP in action
6. **CORE_UPDATES.md** - the lightweight summaries to add to each core workspace file
7. **teach-yourself-protocol.skill** - the skill definition file

## Prerequisites

None. This is the very first skill installed for any OpenClaw agent. All other skills
depend on it. If TSP is not installed, the agent has no structured way to learn or
store anything.

## Key Things the Agent Needs to Know

1. **Core files stay lightweight.** Never dump full API docs or long SOPs into
   AGENTS.md, TOOLS.md, or MEMORY.md. Write a 10-25 line summary with a pointer
   to the deep file where the full content lives.

2. **The Five Question Test.** A good lightweight summary answers the 5 most common
   questions about the topic. If a new agent could handle basic tasks from just the
   summary, it is good enough. If they would be stuck guessing, it is too thin.

3. **Deep files go in ~/Downloads/openclaw-master-files/.** This folder (or whatever
   the user has named it) holds the complete, untruncated knowledge organized into
   subfolders: apis/, skills/, processes/, references/.

4. **Always check for conflicts first.** Before writing anything new, search all core
   files and the master files folder for existing knowledge on the same topic. Never
   create duplicates. Never leave contradictory instructions in different files.

5. **Update multiple core files.** Learning something usually affects more than one
   file. An API reference might need entries in TOOLS.md (how to use it), MEMORY.md
   (that it was learned), and AGENTS.md (rules about when to use it). Check every
   core file independently.

6. **Always confirm to the user.** After completing TSP, tell the user what you
   learned, where you stored it, which core files were updated, and demonstrate your
   working knowledge by summarizing the key points.

7. **User override always wins.** If the user says "put it all in TOOLS.md" even if
   it is 200 lines, do it. Note the tradeoff but follow their instruction.
