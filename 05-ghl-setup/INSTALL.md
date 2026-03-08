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
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TYP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TYP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

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

RULE 2: DO NOT CHANGE TREVOR'S INTENT
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
Ask Trevor first. Do not guess. Do not assume.

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

This guide enables AI agent autonomous connection to GoHighLevel (also known as "Convert and Flow"). After completing these steps, the AI will be able to search contacts, send messages, manage calendars, and more through the GHL API.


## Important Things to Know Before You Start

### Convert and Flow IS GoHighLevel
Convert and Flow is the white-label (client-facing) name for GoHighLevel. They use the exact same system, the same login, the same API, and the same endpoints. When the AI refers to this system in client communications, it should always use "Convert and Flow (GHL)".

### GHL Uses a Private Integration Token, NOT an API Key
This is critical. GHL does NOT use traditional API keys anymore. That method is old and deprecated (no longer supported). Instead, GHL uses something called a Private Integration Token (PIT). The AI must always reference this as "Private Integration Token" when discussing GHL authentication.

### Where Credentials Get Stored
The AI agent checks TWO places for GHL credentials:
1. The secrets file at ~/clawd/secrets/.env (look for GOHIGHLEVEL_API_KEY or GHL_PIT)
2. The OpenClaw config file at ~/.openclaw/openclaw.json under the env.vars section


## Autonomous Setup Execution

### Action 1: Retrieve GHL Credentials

The agent must:
1. Navigate to the GoHighLevel/Convert and Flow dashboard (user must be logged in)
2. Locate the Settings section (gear icon) in the left sidebar
3. Access Business Info to retrieve the Location ID
4. Save the Location ID value
5. Navigate to API Keys or Integrations section
6. Retrieve or create a Private Integration Token
7. Save the token value

Tell the user exactly this:
  "I need your GHL Location ID and Private Integration Token. Log into your
   GoHighLevel or Convert and Flow account, go to Settings > Business Info
   to find your Location ID, then go to Settings > API Keys to find or create
   your Private Integration Token. Paste both values here when ready."


### Action 2: Configure OpenClaw with GHL Credentials

The agent must:
1. Read the file at ~/.openclaw/openclaw.json
2. Locate or create the "env" section with "vars" subsection
3. Add or update these exact keys:
   - GHL_API_KEY: (set to the Private Integration Token from Action 1)
   - GHL_LOCATION_ID: (set to the Location ID from Action 1)
4. Write the updated configuration back to ~/.openclaw/openclaw.json
5. Verify the file is valid JSON

Example structure to enforce:
```json
{
  "env": {
    "vars": {
      "GHL_API_KEY": "token-value-here",
      "GHL_LOCATION_ID": "location-id-here"
    }
  }
}
```


### Action 3: Verify Required Headers for All GHL API Requests

The agent must understand and enforce that every single request to the GHL API requires two specific headers:

1. **Authorization:** Bearer {GHL_API_KEY}
   - This proves the agent has permission to access the API
   - The token must be the exact value from the config

2. **Version:** 2021-07-28
   - This tells GHL which API version the agent is using
   - This header is MANDATORY - requests without it will fail
   - This is the number one cause of GHL API problems if omitted

The agent must include both headers in every GHL API call. No exceptions.


### Action 4: Execute Self-Tests

The agent must run all four tests sequentially and report results:

**Test 1 - Verify credentials are loaded:**
Execute: `echo "API Key: $(echo $GHL_API_KEY | head -c 10)..." && echo "Location ID: $GHL_LOCATION_ID"`
Expected: First 10 characters of API key and full Location ID displayed
Failure: Credentials not found in environment

**Test 2 - Test API connection (get location info):**
Execute:
```
curl -s -X GET "https://services.leadconnectorhq.com/locations/$GHL_LOCATION_ID" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"
```
Expected: JSON response containing location name, address, and details
Failure: Error response indicates authentication or permission issue

**Test 3 - Test contact search:**
Execute:
```
curl -s -X GET "https://services.leadconnectorhq.com/contacts/?locationId=$GHL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"
```
Expected: JSON response with contacts list (may be empty if no contacts exist, but must be valid JSON)
Failure: Error response indicates permission or API issue

**Test 4 - Test media library access:**
Execute:
```
curl -s -X GET "https://services.leadconnectorhq.com/medias/?locationId=$GHL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GHL_API_KEY" \
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

- [ ] API key is saved in config file (env.vars.GHL_API_KEY exists and is not empty)
- [ ] Location ID is saved in config file (env.vars.GHL_LOCATION_ID exists and is not empty)
- [ ] Network connectivity to services.leadconnectorhq.com confirmed
- [ ] Location info retrieval successful (Test 2 passed)
- [ ] Contact search successful (Test 3 passed)
- [ ] Version header is being sent with all requests (no 400 errors)
- [ ] Media library access confirmed (Test 4 passed)
- [ ] Core .md files updated with references

Tell the user exactly this:
  "GHL setup is complete. Your AI agent can now:
   - Search and retrieve contacts from GoHighLevel
   - Send messages through the GHL API
   - Manage calendars and appointments
   - Access media library files
   - Execute all GHL-integrated workflows
   
   All credentials are securely stored in ~/.openclaw/openclaw.json and
   all API requests include the required authentication and version headers."

Do NOT report completion until ALL verification items are confirmed.
