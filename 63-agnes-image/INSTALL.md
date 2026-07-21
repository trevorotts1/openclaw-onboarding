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
AGNES IMAGE 2.1 FLASH - INSTALLATION GUIDE
══════════════════════════════════════════════════════════════════

This skill is an API REFERENCE for an endpoint the fleet already has a key for.
"Installing" it means: confirm the existing AGNES_AI_API_KEY credential is
present, verify the endpoint responds, and wire the lean core-file pointers.
There is no account to create and no software to install.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: CONFIRM THE CREDENTIAL (SET / NOT-SET ONLY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AGNES_AI_API_KEY is an EXISTING fleet credential — the same key the registered
`agnes` / `agnes-2.0-flash` model already uses against apihub.agnes-ai.com/v1.
This skill REFERENCES that key. Do NOT mint a new one, and do NOT print the
value.

1. Check whether the key is set (name/presence only, never the value):

   openclaw config get env.vars.AGNES_AI_API_KEY >/dev/null 2>&1 && echo SET || echo NOT-SET

   You may also check the secrets file for the NAME only:

   grep -q '^AGNES_AI_API_KEY=' "$HOME/.openclaw/secrets/.env" && echo "SET (secrets file)" || echo "not in secrets file"

2. If SET, proceed to Step 2.

3. If NOT-SET, the box is missing the shared Agnes credential. Do NOT invent a
   key. Ask the operator to provision AGNES_AI_API_KEY into
   ~/.openclaw/secrets/.env (chmod 600) exactly as the existing `agnes` model
   expects, then:

   openclaw config set env.vars.AGNES_AI_API_KEY "$AGNES_AI_API_KEY"

   Never echo the value in that flow.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2: VERIFY THE ENDPOINT RESPONDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TEST 1: Reload the environment so the key is available (does NOT print it):

  source "$HOME/.openclaw/secrets/.env" 2>/dev/null || source "$HOME/clawd/secrets/.env" 2>/dev/null || true
  [ -n "$AGNES_AI_API_KEY" ] && echo "AGNES_AI_API_KEY is loaded" || echo "AGNES_AI_API_KEY is EMPTY"

TEST 2: Generate one small test image (1K, 1:1) and confirm a URL comes back in
the SAME response (the endpoint is synchronous):

  curl -sS -m 120 https://apihub.agnes-ai.com/v1/images/generations \
    -H "Authorization: Bearer $AGNES_AI_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "model": "agnes-image-2.1-flash",
      "prompt": "A simple red circle on a white background",
      "size": "1K",
      "ratio": "1:1",
      "extra_body": { "response_format": "url" }
    }'

  Expected: a JSON body with data[0].url set to an image URL. If you get HTTP
  401, the key is wrong/missing (return to Step 1). If HTTP 429, you hit a
  per-tier rate limit — wait and retry; that still proves the endpoint is
  reachable and the key is valid.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3: RUN THE BUNDLED QC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  bash qc-agnes-image.sh

  Exit 0 is required. The script confirms the skill files are present, that the
  reference doc carries the correct model name / endpoint / the extra_body
  response_format gotcha / the output-dimension table, and (as warnings, never
  hard fails) that AGNES_AI_API_KEY is set and TOOLS.md references Agnes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4: WIRE CORE FILES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Apply CORE_UPDATES.md surgically — only the labeled sections into the labeled
core files (AGENTS.md, TOOLS.md, MEMORY.md). Keep them lean (a summary + the
path to agnes-image-full.md). Do not touch SOUL.md / IDENTITY.md / USER.md /
HEARTBEAT.md.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SETUP CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[ ] AGNES_AI_API_KEY confirmed SET (value never printed)
[ ] Test 1 passed — key loads into the environment
[ ] Test 2 passed — endpoint returned a data[0].url in one synchronous response
[ ] qc-agnes-image.sh exited 0
[ ] CORE_UPDATES.md applied surgically to the labeled core files

DO NOT tell the user the skill is active until every box above is checked.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT TO ADD TO YOUR CORE FILES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[ADD TO AGENTS.md]
## Agnes Image 2.1 Flash
- Synchronous text-to-image and image-to-image. Key: AGNES_AI_API_KEY (existing).
- Model: agnes-image-2.1-flash. Endpoint: POST https://apihub.agnes-ai.com/v1/images/generations
- response_format goes in extra_body; image-to-image needs no tags.
- Full reference: 63-agnes-image/agnes-image-full.md

[ADD TO TOOLS.md]
## Agnes Image API
- Auth: Bearer $AGNES_AI_API_KEY
- POST https://apihub.agnes-ai.com/v1/images/generations (synchronous)
- Required: model, prompt, size (1K/2K/3K/4K); ratio optional (16:9, 9:16, 1:1, ...)
- Output: data[0].url or data[0].b64_json; response_format in extra_body
- Full reference: 63-agnes-image/agnes-image-full.md

[ADD TO MEMORY.md]
## Agnes Image 2.1 Flash - Installed [DATE]
- Existing AGNES_AI_API_KEY; synchronous image endpoint (no polling)
- Full reference: 63-agnes-image/agnes-image-full.md

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

If any step here appears to require an OpenClaw gateway restart, STOP. Do NOT run
`openclaw gateway restart` yourself. Notify the user and ask them to trigger it
(for example via `/restart` in Telegram). Wait for confirmation before
proceeding. This skill does not require a restart in the normal path.
