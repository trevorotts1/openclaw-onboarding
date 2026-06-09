# Skill 01 — Teach Yourself Protocol — Changelog

## v6.5.9 — 2026-06-09

### Added: Enforced playbook-install pattern (3 mandatory rules)

**Gap filled:** TYP previously had no explicit instructions for the "use TYP on this
playbook/book/item" invocation — playbooks could land in any subfolder, the AGENTS/TOOLS
pointer block had no required structure, and VPS persistence was mentioned but not enforced
as a mandatory pre-write check.

**Changes made to INSTRUCTIONS.md:**
1. **Dedicated playbooks/ subfolder** — added explicit rule: when TYP is invoked on a
   playbook/SOP/process doc, content MUST go in `playbooks/` subfolder inside master-files
   root (Mac: `~/Downloads/openclaw-master-files/playbooks/`). If subfolder doesn't exist,
   CREATE it before saving.
2. **4-part hyper-concise pointer block** — Step 6 now enforces that every AGENTS.md/TOOLS.md
   block MUST contain all four: WHAT it is, WHEN to use it (trigger), WHY/what it does,
   POINTER REFERENCE (exact absolute path). Block fails to earn its place if any are missing.
3. **VPS persistence note** — added explicit MANDATORY CHECK: on Hostinger Docker VPS all
   files must live under `/data/.openclaw/` (bind-mounted). Files outside this path are
   wiped on container restart. Agent must verify path before writing.
- Added mistake #11 (wrong playbook subfolder), #12 (incomplete 4-part block), #13 (VPS path outside bind-mount)
- Added "Playbook/SOP/Process" row to "Which Core File Gets What" table
- Step 7 confirm now includes playbook subfolder confirmation + VPS path confirmation

**Changes made to CORE_UPDATES.md:**
- AGENTS.md block: added playbooks path, VPS persistence note, 4-part pointer block requirement
- TOOLS.md block: added "Use TYP on this playbook/book/item" trigger, playbook rule, VPS persistence, pointer block rule
- MEMORY.md block: added playbooks path for both Mac and VPS

**Not changed:** teach-yourself-protocol-full.md, SKILL.md trigger section (SKILL.md
description updated only in next full rewrite), INSTALL.md, EXAMPLES.md, MIGRATION-TYP.md
