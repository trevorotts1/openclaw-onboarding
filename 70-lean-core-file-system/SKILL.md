---
name: lean-core-file-system
version: 1.0.0
description: Keeps an OpenClaw agent's core files (AGENTS.md, TOOLS.md, MEMORY.md, and also USER.md, IDENTITY.md, SOUL.md) under 40,000 characters each by moving situational blocks into one-playbook-per-system documents in the master files folder and leaving a one-line pointer (WHAT, WHERE, WHEN) behind, while always-on rules stay inline. Ships an audit script (sizes, candidate blocks, broken pointers, orphans, duplicates, index consistency, content-preservation proof) and a quiet weekly OpenClaw cron job. Use when a core file is too long or truncated, before adding a long block to a core file, or when the user mentions core files, core.md files, bootstrap files, bloat, slimming down, playbooks, or pointers.
---

# Lean Core File System (skill 70)

## What this skill is about

Core files are sent to the model with every message. The bigger they are, the
slower and costlier every reply, the sooner the agent has to stop and compact
its memory, and the more likely OpenClaw silently cuts the middle out of the
last-loaded file (MEMORY.md). This skill keeps the core files lean: any block
longer than a short paragraph that is only needed for one topic moves into that
topic's playbook, and a one-line pointer stays behind that says WHAT it is,
WHERE it lives, and WHEN to open it. The Lean Core File System uses pointer
references: that one-line pointer is the technique, and this skill owns
core-file size and the weekly audit that keeps it that way.

This is a standalone skill. It is NOT part of skill 01 (Teach Yourself
Protocol): skill 01 is about learning new knowledge and where to store it;
skill 70 is about keeping the core files focused over time. Where the two
differ on what may sit in a core file, skill 70 is the newer rule (see section
2 of the playbook).

## When this skill triggers

- A core file is over 40,000 characters, or the agent notices a truncation
  notice ("some bootstrap files were truncated").
- The agent is about to add a block longer than about five sentences to a core
  file.
- The user says: core files, core.md files, bootstrap files, bloat, slim down,
  clean up AGENTS.md or MEMORY.md, playbook, pointer.
- Every Sunday at 05:30 box time, automatically, as a quiet OpenClaw cron job.

## What it covers

- Doctrine: why lean core files are faster (verified against the installed
  OpenClaw code) and the one trade-off (an extra file read).
- The pointer format with good and bad examples, and how to write trigger
  words that actually fire.
- The earn-your-place rule and the critical exception: always-on rules
  (safety, never-do, identity essentials, hard constraints) stay inline,
  shortened.
- One system = one playbook, the playbook template, storage paths on Mac and
  server, and the master index.
- Contradiction handling: newest rule wins, the old rule is marked superseded
  with a date, every playbook carries a "Last verified" date.
- Safety: backup first, never delete (only move), prove every moved paragraph,
  first run shows a dry-run diff, and a hard wall around the OpenClaw bootstrap
  limit settings.
- The test battery after every run and the weekly cron job.

## Files in this folder (read in this order)

1. **SKILL.md** (this file): overview.
2. **lean-core-file-system-full.md**: the complete playbook. The authoritative
   reference; everything else points into it.
3. **INSTRUCTIONS.md**: day-to-day use, the short version.
4. **INSTALL.md**: installation and verification.
5. **EXAMPLES.md**: worked examples with real commands and output.
6. **CORE_UPDATES.md**: the AGENTS.md pointer and the MEMORY.md "core files"
   definition (applied by `wire.sh`, never by hand).
7. **QC.md**: the quality-control checklist; `qc-70-lean-core-file-system.sh` runs
   it.
8. **wire.sh**: the installer that `update-skills.sh` runs on every update.
9. **scripts/**: `pointer-audit.sh` (audit, backup, proof),
   `install-weekly-cron.sh` (the weekly job), `lib-paths.sh` (shared paths),
   `weekly-cron-message.txt` (the job's instructions).
10. **tests/**: fixture batteries for the three scripts.
11. **lean-core-file-system.skill**: the packaged skill definition.
12. **CHANGELOG.md**, **skill-version.txt**.

## Prerequisites

- Skill 01 (Teach Yourself Protocol) installed: it creates the master files
  folder and the `playbooks/` convention this skill shares.
- `bash` (macOS bash 3.2 or Linux bash), `python3`, and the `openclaw` command
  line. No new service key, no new credential, no package install.
- For the weekly job: this box's configured model list must contain DeepSeek
  V4.1 Flash on Ollama Cloud and on OpenRouter. The installer proves both from
  the box's own list and refuses rather than guess.

## Key things the agent needs to know

1. A pointer is ONE line, at most two sentences: WHAT, WHERE (absolute path),
   WHEN (trigger words a user would say).
2. Only situational knowledge moves. Always-on rules stay inline, shortened.
3. One system, one playbook, listed once in `playbooks/README.md` and pointed
   to from a core file. Later updates go into the same playbook.
4. Newest rule wins; the old one is logged as superseded with a date.
5. Back up first, never delete, prove every move with
   `pointer-audit.sh --prove-moved` before removing text from a core file.
6. Never touch `agents.defaults.bootstrapMaxChars` or
   `agents.defaults.bootstrapTotalMaxChars` in any way.
