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
KIE AUDIO - INSTALLATION GUIDE
══════════════════════════════════════════════════════════════════

This skill is an API REFERENCE for KIE.ai audio generation (TTS + Suno music +
audio processing). "Installing" it means: confirm the KIE_API_KEY credential is
present, verify the endpoint responds, run the validator self-test, and wire the
lean core-file pointers. There is no account to create and no software to install.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: CONFIRM THE CREDENTIAL (SET / NOT-SET ONLY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KIE_API_KEY is the operator's KIE.ai API key (the SAME key Skill 07 uses for
image/video tasks). This skill REFERENCES that key for TTS/music. Do NOT mint a
new one, and do NOT print the value.

1. Check whether the key is set (name/presence only, never the value):

   openclaw config get env.vars.KIE_API_KEY >/dev/null 2>&1 && echo SET || echo NOT-SET

   You may also check the secrets file for the NAME only:

   grep -q '^KIE_API_KEY=' "$HOME/.openclaw/secrets/.env" && echo "SET (secrets file)" || echo "not in secrets file"

2. If SET, proceed to Step 2.

3. If NOT-SET, the box is missing the shared KIE credential. Do NOT invent a
   key. Ask the operator to provision KIE_API_KEY into
   ~/.openclaw/secrets/.env (chmod 600) exactly as Skill 07 expects, then:

   openclaw config set env.vars.KIE_API_KEY "$KIE_API_KEY"

   Never echo the value in that flow.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2: VERIFY THE ENDPOINT RESPONDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TEST 1: Reload the environment so the key is available (does NOT print it):

  source "$HOME/.openclaw/secrets/.env" 2>/dev/null || source "$HOME/clawd/secrets/.env" 2>/dev/null || true
  [ -n "$KIE_API_KEY" ] && echo "KIE_API_KEY is loaded" || echo "KIE_API_KEY is EMPTY"

TEST 2: Confirm the KIE API is reachable and the key is valid (account balance,
zero-cost, no generation):

  curl -sS -m 30 https://api.kie.ai/api/v1/account/balance \
    -H "Authorization: Bearer $KIE_API_KEY"

  Expected: a JSON body. HTTP 401 = key wrong/missing (return to Step 1).
  HTTP 402 = zero credits (top up before running any generation task).

Do NOT run a real TTS/Suno generation as the install check — that spends
credits. The validator self-test (Step 3) proves payload correctness offline.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3: RUN THE VALIDATOR SELF-TEST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  python3 scripts/validate_audio_request.py --self-test
  python3 scripts/normalize_alias.py --self-test

  Both must exit 0. The validator self-test covers: Gemini 10,000-char turn OK /
  10,001 rejected; ElevenLabs 5,000 combined OK / 5,001 rejected; Suno V4 custom
  3,000 OK / 3,001 rejected; V5_5 out-of-range duration = advisory warning only;
  sounds 500 OK / 501 rejected; mashup with 3 URLs rejected; STT dispatch attempt
  rejected (exit 2); bad accent and speed 1.5 rejected; Suno-via-createTask
  rejected.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4: WIRE CORE FILES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  bash wire.sh

  wire.sh writes each block behind its OWN version-free marker
  (<!-- BEGIN/END skill:68-kie-audio:<target> -->) REPLACE-IN-PLACE, resolves
  the master-files path to an absolute path on this box, and stamps
  <!-- skill:68-kie-audio:core-update-applied --> so the generic merger
  short-circuits and can never paste the recipe again. Run it twice: the second
  run must be byte-identical (idempotency proof) with no new backup.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SETUP CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[ ] KIE_API_KEY confirmed SET (value never printed)
[ ] Test 1 passed — key loads into the environment
[ ] Test 2 passed — account/balance endpoint returned JSON (401/402 diagnosed, not ignored)
[ ] Validator self-test exited 0 (both scripts)
[ ] wire.sh ran twice; second run byte-identical; sentinel stamped

DO NOT tell the user the skill is active until every box above is checked.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT TO ADD TO YOUR CORE FILES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Run `bash wire.sh` — it performs the adds (see CORE_UPDATES.md for the exact
text it writes). Do NOT paste the CORE_UPDATES.md payloads by hand.

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

If any step here appears to require an OpenClaw gateway restart, STOP. Do NOT run
`openclaw gateway restart` yourself. Notify the user and ask them to trigger it
(for example via `/restart` in Telegram). Wait for confirmation before
proceeding. This skill does not require a restart in the normal path.
