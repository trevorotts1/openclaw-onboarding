# Lean Core File System (70) - Instructions

The full procedure is in `lean-core-file-system-full.md` (the playbook). This page
is the short version for day-to-day use.

## When to act

- A core file (AGENTS.md, TOOLS.md, MEMORY.md, USER.md, IDENTITY.md, SOUL.md)
  is over 40,000 characters, or a truncation notice appeared.
- You are about to add a block longer than about five sentences to a core file:
  put it in the system's playbook instead and add a pointer.
- The user asks to slim down, clean up or audit the core files.
- The weekly cron job runs this automatically on Sundays at 05:30 box time.

## The five rules

1. **Pointer = one line, at most two sentences:** WHAT, WHERE (absolute path),
   WHEN (trigger words). Example:
   `QuickBooks Online: rules and playbook live at ~/Downloads/openclaw-master-files/playbooks/quickbooks-online.md. Read it whenever the user mentions QuickBooks, invoices, or bookkeeping.`
2. **Only situational knowledge moves.** Safety rules, never-do rules, identity
   essentials and hard constraints stay inline, shortened.
3. **One system, one playbook**, in the master files `playbooks/` folder,
   listed once in `playbooks/README.md`, pointed to from a core file. Updates
   go into the existing playbook.
4. **Newest rule wins.** Log the old rule as superseded, with a date, in the
   playbook's "What changed" section; update "Last verified".
5. **Back up, never delete, prove.** Back up first; paste moved text verbatim
   into the playbook's archive; run the proof before removing it from the core
   file. The first run on a box only shows a dry-run diff.

## Commands

```bash
S=~/.openclaw/skills/70-lean-core-file-system    # server: /data/.openclaw/skills/70-lean-core-file-system
bash $S/scripts/pointer-audit.sh --backup                 # 1. backup; prints the folder
bash $S/scripts/pointer-audit.sh --dry-run                # 2. sizes, findings, candidate blocks
#    ... move blocks per the playbook, section 8 ...
bash $S/scripts/pointer-audit.sh --prove-moved <backup>/core/AGENTS.md <workspace>/AGENTS.md   # 3. proof
bash $S/scripts/pointer-audit.sh                          # 4. final audit, writes the report
bash $S/scripts/install-weekly-cron.sh --check            # the weekly job is present and correct
```

Audit exit codes: **0** PASS, **1** FINDINGS, **2** tooling error (the check
itself failed; conclude nothing about the box).

## Message the owner only when a human decision is needed

Tooling error; a core file still above 40,000 with only always-on rules left;
two rules conflict and you cannot tell which is newer; unsure whether a block
is always-on; another skill's managed block is too long; a failed proof you
could not repair; two playbooks for one system you cannot merge safely. One
short plain-English message. Everything else goes in the report file only.

## Never

- Never touch `agents.defaults.bootstrapMaxChars` or
  `agents.defaults.bootstrapTotalMaxChars`.
- Never move or hand-edit a block between another skill's
  `<!-- BEGIN skill:... -->` / `<!-- END skill:... -->` markers.
- Never create a second playbook for a system that already has one.
