> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.

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
RULE 2: DO NOT CHANGE THE OPERATOR'S INTENT — execute steps exactly as written.
RULE 3: NEVER MODIFY API keys, commands, config values, model names, or file
        paths without permission. Model name spelling matters.
RULE 4: BUILD YOUR CHECKLIST BEFORE EXECUTING.
RULE 5: CHECK YOURSELF AGAINST THE CHECKLIST WHEN DONE.
RULE 6: REPORT WHAT YOU DID.

══════════════════════════════════════════════════════════════════
KIE VIDEO (SKILL 67) - INSTALLATION GUIDE
══════════════════════════════════════════════════════════════════

"Installing" this skill means: confirm the KIE_API_KEY credential is present,
verify connectivity without burning generation credits, and wire the lean
core-file pointers. There is no account to create and no software to install.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: CONFIRM THE CREDENTIAL (SET / NOT-SET ONLY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The auth env var NAME is `KIE_API_KEY` (repo convention). KIE's own
documentation shows only a literal placeholder `YOUR_API_KEY` in the
Authorization header — no fetched page documents an environment variable name;
the env var is convention, not vendor-documented (research: 01-kie-common.md,
section f, status UNDETERMINED).

1. Check whether the key is set (name/presence only, never the value):

   openclaw config get env.vars.KIE_API_KEY >/dev/null 2>&1 && echo SET || echo NOT-SET

   You may also check the secrets file for the NAME only:

   grep -q '^KIE_API_KEY=' "$HOME/.openclaw/secrets/.env" && echo "SET (secrets file)" || echo "not in secrets file"

2. If SET, proceed to Step 2.

3. If NOT-SET, the box is missing the KIE credential. Do NOT invent a key.
   Ask the operator to provision KIE_API_KEY into ~/.openclaw/secrets/.env
   (chmod 600), then:

   openclaw config set env.vars.KIE_API_KEY "$KIE_API_KEY"

   Never echo the value in that flow.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2: VERIFY CONNECTIVITY - WITHOUT BURNING GENERATION CREDITS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TEST 1: Reload the environment so the key is available (does NOT print it):

  source "$HOME/.openclaw/secrets/.env" 2>/dev/null || source "$HOME/clawd/secrets/.env" 2>/dev/null || true
  [ -n "$KIE_API_KEY" ] && echo "KIE_API_KEY is loaded" || echo "KIE_API_KEY is EMPTY"

TEST 2: Verify the API is reachable with the key WITHOUT creating a task.
Use the recordInfo endpoint with a deliberately empty/invalid taskId — a 401
means the key is wrong (return to Step 1), anything else (404/400/422)
proves the endpoint answers and the credential authenticates:

  curl -sS -m 30 https://api.kie.ai/api/v1/jobs/recordInfo?taskId=__connectivity_probe__ \
    -H "Authorization: Bearer $KIE_API_KEY"

  Expected: NOT 401. 404 ("Task not found") or 400 (taskId required semantics)
  both prove the key authenticates and the API responds. 401/403 means the key
  is wrong or missing — return to Step 1.

If the operator has ALREADY authorized a generation smoke test, one small
verification video may be created on the operator account (never a client
account): see EXAMPLES.md (e.g. short 5s clip) — but treat a real generation
as an authorized, deliberate act; do not "smoke test" on credits without
explicit permission for this box.

TEST 3: Confirm the three validators + selector pass deterministically:

  python3 scripts/normalize_alias.py --self-test
  python3 scripts/select_video_model.py --self-test
  python3 scripts/validate_prompt.py --self-test
  python3 scripts/validate_payload.py --self-test

  Each must print PASS and exit 0.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3: WIRE CORE FILES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Apply CORE_UPDATES.md surgically — ONLY the labeled sections into the labeled
core files (AGENTS.md, TOOLS.md, MEMORY.md). These updates are PERFORMED by
`bash wire.sh`, not pasted: it writes each block behind its
`<!-- BEGIN/END skill:67-kie-video:<target> -->` marker REPLACE-IN-PLACE, with
the master-files path resolved to an absolute path on this box, and stamps
`<!-- skill:67-kie-video:core-update-applied -->`. Earlier versions of other
skills had no installer, so the generic merger copied CORE_UPDATES.md VERBATIM
and boxes ended up with the literal word `Add:` and an unresolved relative
pointer. Never paste the instruction — run `bash wire.sh`. Do not touch
SOUL.md / IDENTITY.md / USER.md / HEARTBEAT.md.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SETUP CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[ ] KIE_API_KEY confirmed SET (value never printed)
[ ] Test 1 passed — key loads into the environment
[ ] Test 2 passed — recordInfo probe answered without 401 (connectivity proven,
    no credits burned)
[ ] normalize_alias.py --self-test PASS
[ ] select_video_model.py --self-test PASS
[ ] validate_prompt.py --self-test PASS
[ ] validate_payload.py --self-test PASS
[ ] wire.sh run — one block per core target, one sentinel, second run no-change
[ ] CORE_UPDATES.md applied via wire.sh to the labeled core files

DO NOT tell the user the skill is active until every box above is checked.

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

If any step here appears to require an OpenClaw gateway restart, STOP. Do NOT run
`openclaw gateway restart` yourself. Notify the user and ask them to trigger it
(for example via `/restart` in Telegram). Wait for confirmation before
proceeding. This skill does not require a restart in the normal path.
