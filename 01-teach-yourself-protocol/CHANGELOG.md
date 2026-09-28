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

## [7.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.

## [7.0.1] - 2026-09-28 - Pointer standard: remove contradictions with Skill 70

Skill 01 stays the skill for LEARNING new knowledge. This patch only removes the places
where it contradicted Skill 70 (Lean Core File System, folder 70-lean-core-file-system).

- Core-file entries are now one-line pointers of at most two sentences (WHAT it is, WHERE
  it lives, WHEN to read it) instead of 10 to 25 line summaries. Always-on rules (safety
  rules, never-do rules, identity essentials, hard constraints) stay inline, shortened.
- The Five Question Test is replaced by the pointer test (what, where, when). The size
  threshold for moving a block into a deep file is now "longer than a short paragraph
  (about five sentences)" instead of 25 lines.
- Skill 70 owns core-file size and the weekly core-file audit (SKILL.md, full protocol
  anti-bloat rules and periodic review). The install check for AGENTS.md size now warns
  above 40,000 characters (Skill 70 target) instead of 50KB.
- Files changed: SKILL.md, INSTRUCTIONS.md, CORE_UPDATES.md, EXAMPLES.md, INSTALL.md,
  QC.md, MIGRATION-TYP.md, teach-yourself-protocol-full.md, qc-teach-yourself-protocol.sh.
- CORE_UPDATES.md changed: existing installs should replace their old Teach Yourself
  Protocol blocks in AGENTS.md, TOOLS.md, MEMORY.md, and IDENTITY.md with the new shorter
  blocks (do not add them a second time).
- Not changed: teach-yourself-protocol.skill (a stale packaged archive from March 2026 that
  agents copy but do not read) and scripts/typ-migrate.sh (outside this folder; its
  BLOAT_THRESHOLD=25 and its "10 to 25 line summary" notice text need a follow-up).
