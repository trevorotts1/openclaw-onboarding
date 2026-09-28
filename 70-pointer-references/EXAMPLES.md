# Pointer References (70) - Examples

Real commands with the output they produced on a throwaway demo workspace
(paths shortened to `<demo>`). `S` is the skill folder:
`~/.openclaw/skills/70-pointer-references` on a Mac,
`/data/.openclaw/skills/70-pointer-references` on a server.

## Example 1: install on a box (core files only, no cron job)

```
$ bash $S/wire.sh --no-cron
[skill 70] installed playbook -> <demo>/mf/70-pointer-references/pointer-references-full.md
[skill 70] created master index <demo>/mf/playbooks/README.md
[skill 70] AGENTS.md: wrote block 'agents' (backup: <demo>/bk/pointer-references/wire-20260928T180414Z/AGENTS.md)
[skill 70] MEMORY.md: wrote block 'memory' (backup: <demo>/bk/pointer-references/wire-20260928T180414Z/MEMORY.md)
[skill 70] stamped <!-- skill:70-pointer-references:core-update-applied -->
[skill 70] wiring complete (workspace: <demo>/ws; playbook: <demo>/mf/70-pointer-references/pointer-references-full.md)
```

Running it again prints `block 'agents' already current, no change` for each
file and takes no backup.

## Example 2: the audit finds a candidate block

AGENTS.md had a six-sentence "QuickBooks notes" section.

```
$ bash $S/scripts/pointer-audit.sh --dry-run
...
| AGENTS.md | 1083 | ok |
...
## Candidate blocks (agent judgment: move situational knowledge, keep always-on rules inline)

| File | Line | Heading | Characters | Sentences | Hint |
| --- | --- | --- | --- | --- | --- |
| AGENTS.md | 6 | ## QuickBooks notes | 258 | 6 | situational? |

(dry run: no report file written)
PASS [pointer-audit.sh]: 0 finding(s), 1 candidate block(s), 0 playbook(s), 1581 total core characters
```

Exit 0: a candidate is a question for the agent, not a failure.

## Example 3: moving the block, step by step

1. Backup:
   ```
   $ bash $S/scripts/pointer-audit.sh --backup
   BACKUP [pointer-audit.sh]: 2 core file(s) and playbooks copied to <demo>/bk/pointer-references/20260928T180427Z
   <demo>/bk/pointer-references/20260928T180427Z
   ```
2. Create `<master-files>/playbooks/quickbooks-online.md` from the template:
   current rules on top, a "What changed" line, and the original block pasted
   VERBATIM under "Moved-text archive".
3. Add the index line to `playbooks/README.md`:
   `- [QuickBooks Online](quickbooks-online.md) - invoicing, late fees, refunds - last verified 2026-09-28`
4. Replace the block in AGENTS.md with the pointer:
   ```
   ## QuickBooks notes
   QuickBooks Online: invoicing, late-fee and refund rules live at <demo>/mf/playbooks/quickbooks-online.md. Read it whenever the user mentions QuickBooks, an invoice, bookkeeping, a late fee or a refund.
   ```
5. Prove nothing was lost:
   ```
   $ bash $S/scripts/pointer-audit.sh --prove-moved <backup>/core/AGENTS.md <workspace>/AGENTS.md
   SUMMARY: removed-or-changed paragraphs=1 unproven=0
   PASS [pointer-audit.sh]: every paragraph removed from AGENTS.md exists in <demo>/mf/playbooks
   ```
6. Final audit (writes the report):
   ```
   $ bash $S/scripts/pointer-audit.sh
   Report: <demo>/mf/70-pointer-references/reports/pointer-audit-20260928T180427Z.md
   PASS [pointer-audit.sh]: 0 finding(s), 0 candidate block(s), 1 playbook(s), 1539 total core characters
   ```

## Example 4: what a failed proof looks like

If a removed paragraph was never pasted into a playbook:

```
UNPROVEN: The courier account number rule was never copied anywhere.
SUMMARY: removed-or-changed paragraphs=1 unproven=1
FINDINGS [pointer-audit.sh]: restore the UNPROVEN paragraphs to the core file or copy them verbatim into the playbook's Moved-text archive, then re-run
```
Exit 1. Paste the paragraph into the right archive (or put it back) and prove
again before continuing.

## Example 5: findings the audit catches

```
- BROKEN POINTER: AGENTS.md line 9 -> <demo>/mf/playbooks/payroll.md (not found)
- ORPHAN (not indexed): zoom-webinars.md is not listed in README.md
- ORPHAN (no pointer): no core file points to zoom-webinars.md
- DUPLICATE PLAYBOOKS (same System: line): quickbooks-online.md, quickbooks-rules.md (one system = one playbook; merge them)
- POINTER WITHOUT WHEN: AGENTS.md line 7 points to a playbook but names no trigger (add 'Read it whenever the user mentions ...')
- UNRESOLVED: MEMORY.md line 4 names a master-files placeholder instead of a real path
- SIZE: AGENTS.md is 52803 characters, over the 40000 target by 12803
```

## Example 6: the weekly cron job

```
$ bash $S/scripts/install-weekly-cron.sh --dry-run
[install-weekly-cron.sh] job 'pointer-references-weekly' agent=main schedule='30 5 * * 0' session=isolated thinking=high delivery=none
[install-weekly-cron.sh] primary model:  ollama/deepseek-v4.1-flash:cloud
[install-weekly-cron.sh] fallback model: openrouter/deepseek/deepseek-v4.1-flash
[install-weekly-cron.sh] existing jobs with this name: 0
PLAN [install-weekly-cron.sh]: would ADD the job (dry run; pass --apply to create it)
```

On a box whose model list lacks the OpenRouter model:

```
REFUSED [install-weekly-cron.sh]: the model identifiers could not be proven on this box, so no job was created or changed:
  MISSING_FALLBACK=no id matching openrouter/deepseek/deepseek-v4\.1-flash
```
Exit 4. The operator decides whether to add the model; nobody substitutes one.

## Example 7: a contradiction, resolved

The Kie.ai images playbook said "prompt limit 25,000 characters". After a model
upgrade the owner says the limit is now 20,000. In the playbook:

- "Rules (current)": `Prompt limit: 20,000 characters.`
- "What changed": `- 2026-09-28: prompt limit changed from 25,000 to 20,000 characters after the model upgrade. The 25,000 rule is superseded.`
- `Last verified: 2026-09-28`

Any core file that still said 25,000 has that sentence moved into the archive,
so exactly one current statement exists.
