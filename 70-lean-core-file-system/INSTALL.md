> **N24 - Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.

╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TYP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TYP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TYP"
- Look in your session context for prior TYP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TYP:
Proceed to the instructions below.

IF YOU HAVE NOT BEEN TAUGHT TYP:
STOP IMMEDIATELY. Do not read further. Tell the user you must be taught the
Teach Yourself Protocol first.

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

CONFLICT RULE (applies to all skill installs):
If this skill's SKILL.md, CORE_UPDATES.md, or any other file in this skill
folder conflicts with TYP regarding WHICH core .md files to update or WHAT
content to add, always follow this skill's files. The skill takes precedence
over TYP on core file update decisions. TYP governs the storage method (lean
summaries + file paths). The skill governs the content and which files it
touches. When in doubt: skill docs win.

EXECUTION DISCIPLINE - MANDATORY BEFORE YOU START
╚══════════════════════════════════════════════════════════════╝

RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING.
RULE 2: DO NOT CHANGE THE OPERATOR'S INTENT - execute steps exactly as written.
RULE 3: NEVER MODIFY API keys, commands, config values, model names, or file
        paths without permission. Model name spelling matters.
RULE 4: BUILD YOUR CHECKLIST BEFORE EXECUTING.
RULE 5: CHECK YOURSELF AGAINST THE CHECKLIST WHEN DONE.
RULE 6: REPORT WHAT YOU DID.

══════════════════════════════════════════════════════════════════
LEAN CORE FILE SYSTEM (70) - INSTALLATION GUIDE
══════════════════════════════════════════════════════════════════

"Installing" this skill means exactly four things, all done by ONE command:

  1. the playbook is copied to where the AGENTS.md pointer says it lives,
  2. the playbooks folder and its README.md master index exist,
  3. AGENTS.md gets a one-line pointer to the playbook and MEMORY.md gets the
     definition of "core files" (backed up first, idempotent),
  4. the weekly OpenClaw cron job `lean-core-file-system-weekly` exists with the
     right model order.

It does NOT move anything out of your core files. Moving is agent judgment,
done by the weekly job or when someone asks (see INSTRUCTIONS.md), and the
first run on every box only shows a dry-run diff.

## Paths

| | Mac | Server (virtual private server, Docker) |
| --- | --- | --- |
| Skill folder | `~/.openclaw/skills/70-lean-core-file-system/` | `/data/.openclaw/skills/70-lean-core-file-system/` |
| Master files | `~/Downloads/openclaw-master-files/` | `/data/.openclaw/master-files/` |
| Backups | `~/Downloads/openclaw-backups/lean-core-file-system/` | `/data/.openclaw/backups/lean-core-file-system/` |

On a server, run every command INSIDE the OpenClaw container (for example
`docker exec -it <container> bash`), as the same user the gateway runs as.

## Step 1: Pre-flight (read-only)

```bash
S=~/.openclaw/skills/70-lean-core-file-system        # server: /data/.openclaw/skills/70-lean-core-file-system
bash "$S/qc-70-lean-core-file-system.sh"             # must end with "PASS"
bash "$S/scripts/install-weekly-cron.sh" --dry-run
```

The dry run prints the two model identifiers it found on this box, for example:

```
[install-weekly-cron.sh] primary model:  ollama/deepseek-v4.1-flash:cloud
[install-weekly-cron.sh] fallback model: openrouter/deepseek/deepseek-v4.1-flash
PLAN [install-weekly-cron.sh]: would ADD the job (dry run; pass --apply to create it)
```

If it exits **4**, one of the two models is not on this box's configured model
list. Do NOT substitute another model and do NOT edit the model configuration:
report it to the operator, who decides. If it exits **5**, this OpenClaw is too
old for a flag the job needs; report it. If it exits **2**, the gateway did not
answer; check `openclaw gateway status` and retry later.

## Step 2: Install

```bash
bash "$S/wire.sh"
```

It prints each file it changed and where the backup went, then the cron job
read-back:

```
PASS [install-weekly-cron.sh]: read-back confirms exactly one 'lean-core-file-system-weekly' job with the intended model order, schedule, session, thinking and quiet delivery
[skill 70] wiring complete (...)
```

Fleet updates run this same `wire.sh` automatically (`update-skills.sh` calls
it with `--idempotent`), so a box that could not create the job today retries
on the next update. Running it again changes nothing.

## Step 3: Verify

```bash
bash "$S/scripts/install-weekly-cron.sh" --check     # exit 0
bash "$S/scripts/pointer-audit.sh" --dry-run         # read the size table
grep -c 'BEGIN skill:70-lean-core-file-system' ~/.openclaw/workspace/AGENTS.md   # 1 (use your workspace path)
```

The audit may report findings on an existing box (large files, older pointers
without a WHEN, playbooks not yet indexed). That is expected: it is the work
the weekly job does. Installation is complete when the three checks above
behave as shown.

## Step 4: Report

Tell the operator, in plain English: the skill is installed, the weekly job
runs Sundays at 05:30 box time on DeepSeek V4.1 Flash (Ollama Cloud first,
OpenRouter if that is full), the current size of each core file, and that the
first weekly run only prepares a proposal (a dry-run diff) and changes nothing.

## Undo

- Core files: copy the files back from the backup folder `wire.sh` printed.
- Cron job: `openclaw cron list --json` to find the id, then
  `openclaw cron remove <id>` (only when the operator asks).

## Never

- Never touch `agents.defaults.bootstrapMaxChars` or
  `agents.defaults.bootstrapTotalMaxChars`.
- Never pick a model identifier by hand to get past exit 4.
- Never run `openclaw cron run` to "test" the job on a client box: it starts a
  real agent turn that can message the client.
