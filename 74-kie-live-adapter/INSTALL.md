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


RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING.
RULE 2: DO NOT CHANGE THE OPERATOR'S INTENT. Execute steps exactly as written.
RULE 3: NEVER MODIFY API keys, commands, config values, model names, or file
        paths without permission. Model name spelling matters.
RULE 4: BUILD YOUR CHECKLIST BEFORE EXECUTING.
RULE 5: CHECK YOURSELF AGAINST THE CHECKLIST WHEN DONE.
RULE 6: REPORT WHAT YOU DID.

==================================================================
KIE LIVE ADAPTER (SKILL 74) - INSTALLATION GUIDE
==================================================================

"Installing" this skill means: confirm the prerequisites, run the offline
tests, and wire two short pointers into the core files. There is no account to
create and no software to install. The adapter starts in SHADOW mode: it
observes and records, and it never dispatches a paid job until an operator
sets active mode on purpose.

STEP 1: CONFIRM PREREQUISITES (SET / NOT-SET ONLY)

1. Skill 07 (KIE Setup) is installed.
2. python3 is on the PATH: python3 --version
3. KIE_API_KEY presence only. Never print the value:

   [ -n "${KIE_API_KEY:-}" ] && echo SET || echo NOT-SET

   If NOT-SET, the key may still resolve through the shared resolver in
   shared-utils. If the box has no key at all, ask the operator to provision
   it into the secrets file (chmod 600). Do NOT invent a key.

STEP 2: RUN THE OFFLINE QC (no network, no key needed)

   bash qc-74-kie-live-adapter.sh

   It must exit 0. It runs the unit tests with a fake transport and leaves no
   files inside the skill folder.

STEP 3: WIRE CORE FILES

   bash wire.sh

Writes one short block into AGENTS.md and one into TOOLS.md behind its own
markers (replace in place, backup only when a file changes) and stamps
`<!-- skill:74-kie-live-adapter:core-update-applied -->`. A second run changes
nothing. Do not touch SOUL.md, IDENTITY.md, USER.md, HEARTBEAT.md or MEMORY.md.

STEP 4 (OPTIONAL, OPERATOR ONLY): LIVE CHECK

   bash scripts/live_smoke.sh

Free calls only (health, credits, catalog, one schema, one validation, one
tiny upload). A single paid image needs the explicit --paid flag and an
operator account. Never run it on a client account.

Mode stays shadow unless the operator sets KIE_LIVE_ADAPTER_MODE=active or
writes the word active into $OC_CONFIG/kie-live-adapter-mode.conf.

SETUP CHECKLIST

[ ] Skill 07 present
[ ] python3 present
[ ] KIE_API_KEY SET or resolvable (value never printed)
[ ] qc-74-kie-live-adapter.sh exits 0
[ ] wire.sh run; second run reports no change
[ ] Mode confirmed shadow (default)

DO NOT tell the user the skill is active until every box above is checked.

---

## GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

If any step here appears to require an OpenClaw gateway restart, STOP. Do NOT run
`openclaw gateway restart` yourself. Notify the user and ask them to trigger it.
This skill does not require a restart.
