╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TYP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TYP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TYP"
- Look in your session context for prior TYP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TYP:
Proceed to the instructions below. Follow the TYP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TYP:
NOTE: TYP is recommended. If not yet installed, continue and revisit TYP
later if needed. You can still safely execute this skill without TYP - just
be mindful not to dump large blocks of content into core .md files. Add only
brief summaries and file path references to AGENTS.md, TOOLS.md, and MEMORY.md.

CONFLICT RULE (applies to all skill installs):
If this skill's SKILL.md, CORE_UPDATES.md, or any other file in this skill
folder conflicts with TYP regarding WHICH core .md files to update or WHAT
content to add, always follow this skill's files. The skill takes precedence
over TYP on core file update decisions. TYP governs the storage method (lean
summaries + file paths). The skill governs the content and which files it
touches. When in doubt: skill docs win.


TYP FILE STORAGE INSTRUCTIONS (only read this if TYP confirmed)

WHEN LEARNING THIS DOCUMENT, FOLLOW THIS STRUCTURE:

1. SAVE FULL DOCUMENTATION TO MASTER FILES FOLDER
   Find the OpenClaw master files folder in ~/Downloads/. It may be named:
   - OpenClaw Master Files
   - OpenClaw Master Documents
   - OpenClaw Documents
   - openclaw-master-files
   - openclaw master files
   - OpenClaw Files
   - openclaw-documents
   - Any variation of "openclaw" + "master" or "files" or "documents"
   Search case-insensitively. One word or two words. Plural or singular.
   If no folder is found, create: ~/Downloads/OpenClaw Master Files/

   Save this full document content as a .md file in that folder.

2. DO NOT DUMP FULL CONTENT INTO CORE .MD FILES
   AGENTS.md, TOOLS.md, and MEMORY.md must stay lean.
   Only add a brief summary and a file path reference to where the full
   documentation lives. Never paste thousands of lines into core files.

3. USE THE LABELED SECTIONS BELOW TO KNOW WHAT GOES WHERE
   Look for sections marked:
   [ADD TO AGENTS.md]
   [ADD TO TOOLS.md]
   [ADD TO MEMORY.md]
   Only add what is labeled. Nothing else goes into core files.

EXECUTION DISCIPLINE - MANDATORY BEFORE YOU START
╚══════════════════════════════════════════════════════════════╝

These rules apply every single time you execute instructions from this document.
No exceptions. No shortcuts. No improvising.

RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING
Read this entire document from top to bottom before executing a single step.
Do not start executing while still reading. Finish reading first. Then start.

RULE 2: DO NOT CHANGE THE OPERATOR'S INTENT
These instructions say exactly what to do. Execute them exactly as written.
- Do NOT reinterpret steps
- Do NOT "improve" the instructions
- Do NOT skip steps because they seem unnecessary
- Do NOT add steps that are not in the document
- Do NOT change the order of steps
If a step says do X, do X. Not Y. Not a better version of X. X.

RULE 3: NEVER MODIFY THESE WITHOUT PERMISSION
- API keys - copy them exactly, character for character
- Terminal commands - run them exactly as written, no edits
- Config values - use the exact values specified
- Model names - use the exact names specified, spelling matters
- File paths - use the exact paths specified
If you are unsure whether something should be changed, the answer is NO.
Ask the operator. Do not guess. Do not assume.

RULE 4: BUILD YOUR CHECKLIST BEFORE EXECUTING
Before you run a single command or make a single change, create a numbered
checklist of every action this document requires you to take. Write it out.
Show it to the user before starting. Get confirmation. Then execute.

RULE 5: CHECK YOURSELF AGAINST THE CHECKLIST WHEN DONE
When you believe you are finished, go back to your checklist.
Verify every single item was completed. Check it off explicitly.
If anything was missed, complete it before telling the user you are done.
Do NOT tell the user you are done until the checklist is 100% complete.

RULE 6: REPORT WHAT YOU DID
When finished, give the user a clear summary:
- What was completed
- What commands were run
- What files were changed
- Any errors encountered and how they were resolved
- Confirmation that the checklist was fully satisfied

══════════════════════════════════════════════════════════════════

# GHL (GoHighLevel) Setup - Installation Guide

> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.


This guide enables AI agent autonomous connection to GoHighLevel (also known as "Convert and Flow"). After completing these steps, the AI will be able to search contacts, send messages, manage calendars, and more through the GHL API.


## Important Things to Know Before You Start

### Convert and Flow IS GoHighLevel
Convert and Flow is the white-label (client-facing) name for GoHighLevel. They use the exact same system, the same login, the same API, and the same endpoints. When the AI refers to this system in client communications, it should always use "Convert and Flow (GHL)".

### GHL Uses a Private Integration Token, NOT an API Key
This is critical. GHL does NOT use traditional API keys anymore. That method is old and deprecated (no longer supported). Instead, GHL uses something called a Private Integration Token (PIT). The AI must always reference this as "Private Integration Token" when discussing GHL authentication.

### Where Credentials Get Stored
The AI agent checks TWO places for GHL credentials:
1. The secrets file at ~/.openclaw/secrets/.env (look for GOHIGHLEVEL_API_KEY or GHL_PIT)
2. The OpenClaw config file at ~/.openclaw/openclaw.json under the env.vars section


## Autonomous Setup Execution

### Pre-Action: Environment Credential Check

Before prompting the user for any credentials, the agent MUST check existing
env files first. Only ask the user if the values are not already stored.

**Step 1 - Check for existing GHL credentials:**
```bash
# Check secrets/.env (canonical names first, then legacy aliases)
grep -E "GOHIGHLEVEL_API_KEY|GHL_API_KEY|GHL_PIT|GHL_TOKEN|GHL_PRIVATE_INTEGRATION_TOKEN|PRIVATE_INTEGRATION_TOKEN|GHL_PRIVATE_TOKEN|PIT_TOKEN|GHL_PIT_TOKEN|GOHIGHLEVEL_LOCATION_PIT|GHL_LOCATION_PIT|GOHIGHLEVEL_LOCATION_ID|GHL_LOCATION_ID" ~/.openclaw/secrets/.env 2>/dev/null

# Check openclaw.json
cat ~/.openclaw/openclaw.json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('env',{}).get('vars',{}))" 2>/dev/null
```

**Decision tree:**
- If BOTH a token (any of: `GOHIGHLEVEL_API_KEY`, `GHL_API_KEY`, `GHL_PIT`, `GHL_TOKEN`, `GHL_PRIVATE_INTEGRATION_TOKEN`, `PRIVATE_INTEGRATION_TOKEN`, `GHL_PRIVATE_TOKEN`, `PIT_TOKEN`, `GHL_PIT_TOKEN`, `GOHIGHLEVEL_LOCATION_PIT`, `GHL_LOCATION_PIT` — see TERMINOLOGY.md) AND a location (`GOHIGHLEVEL_LOCATION_ID` or `GHL_LOCATION_ID`) are found: skip Action 1, proceed directly to Action 2.
- If one or both are missing: proceed to Action 1 to retrieve them.
- If the user cannot or does not want to provide credentials: offer a skip option.
  Tell the user: "You can skip credential setup now and add them later. GHL features
  will not work until credentials are added, but all other setup will complete."

**Skip option behavior:** If the user skips, note it in MEMORY.md and continue
installation. Never block the entire install on missing GHL credentials.


### Action 1: Retrieve GHL Credentials

The agent MUST first attempt to retrieve credentials automatically via API
before asking the user to do anything manually.

**Attempt 1 - Check if any credentials are partially configured and use them
to look up missing values:**

If a token exists but the location is missing, resolve the token from whichever
name is present and discover the location:
```bash
TOKEN="${GOHIGHLEVEL_API_KEY:-${GHL_API_KEY:-${GHL_PIT:-${GHL_TOKEN:-${GHL_PRIVATE_INTEGRATION_TOKEN:-${PRIVATE_INTEGRATION_TOKEN:-${GHL_PRIVATE_TOKEN:-${PIT_TOKEN:-${GHL_PIT_TOKEN:-${GOHIGHLEVEL_LOCATION_PIT:-${GHL_LOCATION_PIT:-}}}}}}}}}}}"
curl -s -X GET "https://services.leadconnectorhq.com/locations/search?limit=1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Version: 2021-07-28"
```
If this returns a valid location, extract the location ID automatically from
the response. Save it to ~/.openclaw/secrets/.env as BOTH
GOHIGHLEVEL_LOCATION_ID (canonical) and GHL_LOCATION_ID (legacy alias).

If the location exists but no token is present, you cannot recover the token
automatically. A Private Integration Token is a STATIC token (not an
OAuth session — there is nothing to refresh), so go to Attempt 2 and ask the
user for the PIT.

**Attempt 2 - If automatic retrieval fails or no credentials exist at all,
ask the user for manual input:**

Tell the user exactly this:
  "I checked your environment files and could not find your GHL credentials.
   I need your GHL Location ID and Private Integration Token.

   To get them:
   1. Log into your GoHighLevel or Convert and Flow account
   2. Go to Settings (gear icon in left sidebar) > Business Info
   3. Copy your Location ID
   4. Go to Settings > Integrations > Private Integrations
   5. Copy or create your Private Integration Token (GHL has no "API keys")

   Paste both values here when ready, or type 'skip' to continue without
   GHL credentials (you can add them later)."

**If the user types 'skip':** proceed to Action 5, noting credentials are
pending in MEMORY.md.


### Action 2: Configure OpenClaw with GHL Credentials

The PRIMARY credential storage location is ~/.openclaw/secrets/.env. This is
where the agent reads credentials at runtime. Always write here first.

The agent must:
1. Open ~/.openclaw/secrets/.env (create it if it does not exist)
2. Add or update these lines. Write the canonical names (read by QC, PREREQS,
   and skills 36/44) AND the legacy aliases (read by older skill 29), with the
   SAME values:
   ```
   GOHIGHLEVEL_API_KEY=<Private Integration Token from Action 1>
   GOHIGHLEVEL_LOCATION_ID=<Location ID from Action 1>
   GHL_API_KEY=<same Private Integration Token>
   GHL_LOCATION_ID=<same Location ID>
   ```
3. Save the file, then lock it down: `chmod 600 ~/.openclaw/secrets/.env`
4. Verify the canonical values are present:
   ```bash
   grep -E "GOHIGHLEVEL_API_KEY|GOHIGHLEVEL_LOCATION_ID" ~/.openclaw/secrets/.env
   ```

SECONDARY (optional sync): If ~/.openclaw/openclaw.json already has an
env.vars section, also add the canonical values there for convenience:
```json
{
  "env": {
    "vars": {
      "GOHIGHLEVEL_API_KEY": "token-value-here",
      "GOHIGHLEVEL_LOCATION_ID": "location-id-here"
    }
  }
}
```
On a VPS/Docker box, if you instead apply this with `openclaw config set`, run it
inside the container as user node (e.g. `docker exec -u node ...`) — config
writes as root can freeze the gateway.

NOTE: ~/.openclaw/secrets/.env is the authoritative source. openclaw.json is
a secondary mirror only. All runtime code should read from secrets/.env.


### Action 3: Verify Required Headers for All GHL API Requests

The agent must understand and enforce that every single request to the GHL API requires two specific headers:

1. **Authorization:** Bearer {GOHIGHLEVEL_API_KEY}
   - This proves the agent has permission to access the API
   - The value is the Private Integration Token (PIT) — the exact value from secrets/.env

2. **Version:** 2021-07-28
   - This tells GHL which API version the agent is using
   - This header is MANDATORY - requests without it will fail
   - This is the number one cause of GHL API problems if omitted

The agent must include both headers in every GHL API call. No exceptions.


### Action 4: Execute Self-Tests

The agent must run all four tests sequentially and report results:

**Test 1 - Verify credentials are loaded (presence only — never print a value):**
Execute:
```
[ -n "$GOHIGHLEVEL_API_KEY" ] && echo "GOHIGHLEVEL_API_KEY: SET" || echo "GOHIGHLEVEL_API_KEY: NOT-SET"
[ -n "$GOHIGHLEVEL_LOCATION_ID" ] && echo "GOHIGHLEVEL_LOCATION_ID: SET" || echo "GOHIGHLEVEL_LOCATION_ID: NOT-SET"
```
Expected: both lines report `SET`
Failure: either line reports `NOT-SET` — credentials not found in environment

Never echo, print, `head` or otherwise emit the PIT or the Location ID. A ten-character
prefix is still credential material, and terminal transcripts, agent logs and shell
history retain every character printed.

**Test 2 - Test API connection (get location info):**
Execute:
```
curl -s -X GET "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28"
```
Expected: JSON response containing location name, address, and details
Failure: Error response indicates authentication or permission issue

**Test 3 - Test contact search:**
Execute:
```
curl -s -X GET "https://services.leadconnectorhq.com/contacts/?locationId=$GOHIGHLEVEL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28"
```
Expected: JSON response with contacts list (may be empty if no contacts exist, but must be valid JSON)
Failure: Error response indicates permission or API issue

**Test 4 - Test media library access:**
Execute:
```
curl -s -X GET "https://services.leadconnectorhq.com/medias/?locationId=$GOHIGHLEVEL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28"
```
Expected: JSON response with media files list
Failure: Error response indicates media scope not enabled

If ANY test fails:
- Verify the API key is correct and has not expired
- Verify the Location ID matches the account
- Verify the Version header is exactly: 2021-07-28
- Verify the API key has correct permissions/scopes enabled in GHL
- Report the specific error message

Do NOT proceed to Action 5 until ALL tests pass.


### Action 5: Update Core .md Files

The agent must follow TYP rules - add only summaries and file path references to core files.

**Update TOOLS.md:**
Add reference to GHL API base URL, Version header requirement, and common endpoint paths.
Location: ~/clawd/TOOLS.md
Content to add: Brief summary + path reference to this document

**Update MEMORY.md:**
Add note that GHL credentials are configured and storage location.
Location: ~/clawd/MEMORY.md
Content to add: Brief summary + path reference to this document

**Update AGENTS.md:**
Add rule that all GHL API requests must include the Version header.
Location: ~/clawd/AGENTS.md
Content to add: Brief summary + path reference to this document


### Action 6: Completion Verification

The agent must verify all of these conditions are true:

- [ ] PIT is saved (GOHIGHLEVEL_API_KEY in secrets/.env is present and not empty)
- [ ] Location ID is saved (GOHIGHLEVEL_LOCATION_ID in secrets/.env is present and not empty)
- [ ] Legacy aliases also written (GHL_API_KEY / GHL_LOCATION_ID) for back-compat
- [ ] secrets/.env is chmod 600
- [ ] Network connectivity to services.leadconnectorhq.com confirmed
- [ ] Location info retrieval successful (Test 2 passed)
- [ ] Contact search successful (Test 3 passed)
- [ ] Version header is being sent with all requests (no 400 errors)
- [ ] Media library access confirmed (Test 4 passed)
- [ ] Core .md files updated with references

**Client-verifiable receipt:** After the tests pass, write a short receipt the
client can independently confirm in their own Convert and Flow (GHL) UI. Save it
to the workspace (NOT into chat, and never the full token). Include:
- masked PIT prefix only (e.g. first 8 chars + "...")
- the location's business name returned by Test 2
- the location ID
- a UTC timestamp
The client can match the business name against their GHL sub-account to confirm
the agent is wired to THEIR location and no one else's.

Tell the user exactly this:
  "GHL setup is complete. Your AI agent can now:
   - Search and retrieve contacts from GoHighLevel
   - Send messages through the GHL API
   - Manage calendars and appointments
   - Access media library files
   - Execute all GHL-integrated workflows
   
   All credentials are securely stored in ~/.openclaw/secrets/.env (chmod 600) and
   all API requests include the required authentication and version headers."

Do NOT report completion until ALL verification items are confirmed.

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

**During this installation, you may encounter instructions to restart the OpenClaw gateway.**

**YOU ARE FORBIDDEN from triggering gateway restarts yourself.**

### Correct Process
When a gateway restart is needed:
1. **STOP** - Do NOT execute the restart command
2. **NOTIFY** the user: "This installation requires an OpenClaw gateway restart to complete."
3. **INSTRUCT**: "Type `/restart` in Telegram to trigger it"
4. **WAIT** for user action - do NOT proceed until confirmed

### Forbidden Actions
- Do NOT run `openclaw gateway restart` without explicit user permission
- Do NOT say "I will restart the gateway now" without asking first
- Do NOT assume the user wants the restart

---
