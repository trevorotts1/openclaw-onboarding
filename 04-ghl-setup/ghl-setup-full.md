
╔══════════════════════════════════════════════════════════════╗
  MANDATORY TSP CHECK - READ THIS BEFORE ANYTHING ELSE
DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TSP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TSP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TSP"
- Look in your session context for prior TSP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TSP:
Proceed to the instructions below. Follow the TSP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TSP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TSP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TSP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TSP CONFIRMED.

TSP FILE STORAGE INSTRUCTIONS (only read this if TSP confirmed)

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
⚠️ PREREQUISITE: This tab follows the Teach Yourself Protocol. If you have not been taught the Teach Yourself Protocol yet, ask your owner to teach it before proceeding.

🔄 CONVERT AND FLOW = GOHIGHLEVEL (GHL)
Convert and Flow is the client-facing/white-label name for GoHighLevel (GHL). They use the SAME API, SAME endpoints, SAME authentication. When someone says "Convert and Flow" they mean GHL on the backend. Always refer to it as "Convert and Flow (GHL)" when talking to clients.

🔴🔴🔴 GHL DOES NOT USE API KEYS - THAT IS DEPRECATED 🔴🔴🔴
GHL uses a PRIVATE INTEGRATION TOKEN (PIT), NOT an API key. If your AI ever says "I need the API key" for GHL - IT IS WRONG. The correct term is Private Integration Token (PIT). Get it from: Settings > Integrations > Private Integration Token.

📋 WHERE TO CHECK FOR CREDENTIALS:
Your AI should check BOTH of these locations:
1. ~/clawd/secrets/.env (look for GOHIGHLEVEL_API_KEY or GHL_PIT)
2. ~/.openclaw/openclaw.json under env.vars (look for GOHIGHLEVEL_API_KEY)
New AI setups will NOT know to check both unless explicitly told.

🎯 PRIORITY SCOPES (Test These First):
1. Contacts - search, create, update contacts (used constantly)
2. Media Library - upload/list media files (used constantly)
3. Conversations - send SMS AND Email (used constantly)

🏢 GoHighLevel (GHL) / Converting Flow Setup

Complete guide to setting up GoHighLevel API integration.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 STEP 1: Get Your API Credentials

1. Log into your GHL account
2. Go to Settings > Business Info
3. Copy your Location ID
4. Go to Settings > API Keys
5. Create a new API key (or use existing)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 STEP 2: Add to OpenClaw Config

nano ~/.openclaw/openclaw.json

Add under "env" section:
{
  "env": {
    "vars": {
      "GHL_API_KEY": "your-api-key-here",
      "GHL_LOCATION_ID": "your-location-id-here"
    }
  }
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 CRITICAL: Required Headers

EVERY GHL API request needs these headers:
• Authorization: Bearer YOUR_API_KEY
• Version: 2021-07-28

Without the Version header, requests WILL FAIL!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 COMMON OPERATIONS

Base URL: https://services.leadconnectorhq.com

CONTACTS:
• Search: GET /contacts/search?query=email
• Get: GET /contacts/{contactId}
• Create: POST /contacts/
• Update: PUT /contacts/{contactId}

CONVERSATIONS:
• Send SMS: POST /conversations/messages
  Body: {"type": "SMS", "contactId": "xxx", "message": "text"}
• Send Email: POST /conversations/messages
  Body: {"type": "Email", "contactId": "xxx", "subject": "x", "html": "x"}

CALENDAR:
• Get slots: GET /calendars/{calendarId}/free-slots
• Book: POST /calendars/events/appointments

OPPORTUNITIES:
• List: GET /opportunities/search
• Create: POST /opportunities/
• Update: PUT /opportunities/{id}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 EXAMPLE: Search and Message a Contact

# Search for contact
curl -X GET "https://services.leadconnectorhq.com/contacts/search?query=john@email.com" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"

# Send SMS
curl -X POST "https://services.leadconnectorhq.com/conversations/messages" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "SMS",
    "contactId": "contact-id-here",
    "message": "Hello from your AI assistant!"
  }'

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 IMPORTANT RULES

• NEVER use the native GHL node in n8n - it's limited
• ALWAYS use HTTP Request nodes for GHL API calls
• Rate limits: 100 requests/minute for most endpoints
• Webhooks are your friend - set them up for real-time updates

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ ADD THIS TO YOUR AI'S FILES:

TOOLS.md - Add GHL endpoints and Version header rule
MEMORY.md - Note GHL credentials location
AGENTS.md - Add rule to always include Version header


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🧪 SELF-TEST: VERIFY GHL IS WORKING

After setup, the AI should run these tests automatically:

TEST 1: Verify Credentials Exist
echo "API Key: $(echo $GHL_API_KEY | head -c 10)..."
echo "Location ID: $GHL_LOCATION_ID"
# Should show first 10 chars of key and full location ID

TEST 2: Test API Connection (Get Location Info)
curl -s -X GET "https://services.leadconnectorhq.com/locations/$GHL_LOCATION_ID" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"

EXPECTED: JSON with location name, address, etc.

TEST 3: Test Contact Search
curl -s -X GET "https://services.leadconnectorhq.com/contacts/?locationId=$GHL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"

EXPECTED: JSON with contacts array (even if empty)

TEST 4: Verify Version Header Works
# If you get 400 errors, the Version header is missing!

TEST 5: Test Send SMS
curl -s -X POST "https://services.leadconnectorhq.com/conversations/messages" \
-H "Authorization: Bearer $GHL_API_KEY" \
-H "Version: 2021-07-28" \
-H "Content-Type: application/json" \
-d '{"type": "SMS", "contactId": "REPLACE_WITH_CONTACT_ID", "message": "Test SMS from AI assistant"}'
EXPECTED: JSON with messageId confirming delivery

TEST 6: Test Send Email
curl -s -X POST "https://services.leadconnectorhq.com/conversations/messages" \
-H "Authorization: Bearer $GHL_API_KEY" \
-H "Version: 2021-07-28" \
-H "Content-Type: application/json" \
-d '{"type": "Email", "contactId": "REPLACE_WITH_CONTACT_ID", "subject": "Test Email from AI", "html": "<p>This is a test email from your AI assistant.</p>"}'
EXPECTED: JSON with messageId confirming delivery

TEST 7: Test Media Library Access
curl -s -X GET "https://services.leadconnectorhq.com/medias/?locationId=$GHL_LOCATION_ID&limit=1" \
-H "Authorization: Bearer $GHL_API_KEY" \
-H "Version: 2021-07-28"
EXPECTED: JSON with media files array (proves media library scope works)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ SELF-TEST CHECKLIST FOR AI

After setting up GHL, automatically verify:

□ API key is in config (check env.vars.GHL_API_KEY)
□ Location ID is in config (check env.vars.GHL_LOCATION_ID)
□ Can reach services.leadconnectorhq.com
□ Can get location info (proves auth works)
□ Can search contacts (proves permissions work)
□ Version header is being sent (no 400 errors)

IF ANY TEST FAILS:
1. Check API key is correct and not expired
2. Check Location ID matches your account
3. Check Version header: 2021-07-28
4. Check API key has correct permissions/scopes
5. Report specific error to user

DO NOT tell user "it's set up" until all tests pass!

