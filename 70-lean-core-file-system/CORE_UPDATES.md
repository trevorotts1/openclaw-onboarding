# Lean Core File System (70) - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

These payloads are applied by this skill's own `wire.sh`, which
`update-skills.sh` runs automatically (and which INSTALL.md runs by hand). It
writes each block between `<!-- BEGIN/END skill:70-lean-core-file-system:<target> -->`
markers, REPLACE-IN-PLACE, so a re-run changes nothing and an older copy is
healed rather than duplicated. It resolves `[MASTER_FILES_FOLDER]` to this box's
absolute master files path, backs up each file before changing it, and stamps
`<!-- skill:70-lean-core-file-system:core-update-applied -->` into AGENTS.md so the
generic merger in `update-skills.sh` never pastes these blocks a second time.
Do NOT paste them by hand.

The AGENTS.md block is the pointer to this skill's playbook: one line, two
sentences, WHAT and WHERE in the first, WHEN in the second. The MEMORY.md block
is the definition of "core files". Both are deliberately short, because both
files are sent to the model with every message.

The sentinel comment on the first line under the AGENTS.md header is there on
purpose: the onboarding verification gate (`oc_core_sentinel_present` in
`lib-onboarding-state.sh`) takes the first line of each section body as the
text to look for in the workspace, and `wire.sh` stamps exactly that line into
AGENTS.md. Without it the gate would look for the word "Add:".

---

## AGENTS.md - UPDATE REQUIRED
<!-- skill:70-lean-core-file-system:core-update-applied -->

Add:

```
## Lean Core File System (70)
Core-file upkeep: the playbook at [MASTER_FILES_FOLDER]/70-lean-core-file-system/lean-core-file-system-full.md governs keeping AGENTS.md, TOOLS.md and MEMORY.md under 40,000 characters by moving situational blocks into playbooks behind one-line pointers, and its one-line pointer format replaces the older 10-to-25-line summary size from the Teach Yourself Protocol. Read it whenever a core file passes 40,000 characters, before adding a block longer than five sentences to a core file, or when the user mentions core files, bloat, slimming down, playbooks or pointers.
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## Core files (definition)
"Core files", "core.md files" and "bootstrap files" all mean the same six workspace files: AGENTS.md, TOOLS.md, MEMORY.md, USER.md, IDENTITY.md and SOUL.md. They are sent to the model with every message, so each stays under 40,000 characters, and long situational knowledge lives in playbooks in [MASTER_FILES_FOLDER]/playbooks/ (master index: README.md in that folder).
```

---

## TOOLS.md - NO UPDATE NEEDED
The pointer lives in AGENTS.md only. A second copy in TOOLS.md would be a
duplicate source of truth.

## IDENTITY.md - NO UPDATE NEEDED

## USER.md - NO UPDATE NEEDED

## SOUL.md - NO UPDATE NEEDED

## HEARTBEAT.md - NO UPDATE NEEDED
The weekly run is an OpenClaw cron job created by
`scripts/install-weekly-cron.sh`, not a heartbeat task.
