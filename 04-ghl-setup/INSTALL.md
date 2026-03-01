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

# GHL (GoHighLevel) Setup - Installation Guide

This guide walks you through connecting your AI agent to GoHighLevel (also known as "Convert and Flow"). After completing these steps, your AI will be able to search contacts, send messages, manage calendars, and more through the GHL API.


## Important Things to Know Before You Start

### Convert and Flow IS GoHighLevel
Convert and Flow is the white-label (client-facing) name for GoHighLevel. They use the exact same system, the same login, the same API, and the same endpoints. When someone says "Convert and Flow" they mean GoHighLevel on the backend. Your AI should always refer to it as "Convert and Flow (GHL)" when talking to clients.

### GHL Uses a Private Integration Token, NOT an API Key
This is critical. GHL does NOT use traditional API keys anymore. That method is old and deprecated (no longer supported). Instead, GHL uses something called a Private Integration Token (PIT). If your AI ever says "I need the API key" for GHL, that is WRONG. The correct term is Private Integration Token.

### Where Credentials Get Stored
Your AI agent checks TWO places for GHL credentials:
1. The secrets file at ~/clawd/secrets/.env (look for GOHIGHLEVEL_API_KEY or GHL_PIT)
2. The OpenClaw config file at ~/.openclaw/openclaw.json under the env.vars section

New AI setups will not know to check both locations unless you tell them.


## Step-by-Step Setup

### Step 1: Get Your API Credentials from GHL

1. Open your web browser and log into your GoHighLevel account (or Convert and Flow account - same thing)
2. Once you are on the dashboard, look at the bottom of the left sidebar
3. Click on "Settings" (it looks like a gear icon)
4. In the Settings area, click on "Business Info"
5. You will see a field labeled "Location ID" - copy this value and save it somewhere safe (like a text file on your desktop). You will need it in the next step.
6. Now go back to Settings and click on "API Keys" (or "Integrations" depending on your account version)
7. If you already have an API key/token listed, copy it. If not, click "Create New" to generate one.
8. Copy the token value and save it alongside your Location ID.


### Step 2: Add Your Credentials to OpenClaw Config

Open the OpenClaw configuration file by running this command:

```
nano ~/.openclaw/openclaw.json
```

This opens a text editor. Find the section that says "env" and add your GHL credentials inside it like this:

```json
{
  "env": {
    "vars": {
      "GHL_API_KEY": "your-api-key-here",
      "GHL_LOCATION_ID": "your-location-id-here"
    }
  }
}
```

Replace "your-api-key-here" with the actual token you copied in Step 1. Replace "your-location-id-here" with the actual Location ID you copied in Step 1.

To save and close the file:
- Press Ctrl+O (that is the letter O, not zero) to save
- Press Enter to confirm
- Press Ctrl+X to exit the editor


### Step 3: Understand the Required Headers

Every single request your AI makes to the GHL API must include two special headers. If either one is missing, the request will fail.

The two required headers are:
1. **Authorization:** Bearer YOUR_API_KEY (this proves you have permission)
2. **Version:** 2021-07-28 (this tells GHL which version of the API you are using)

Without the Version header, your requests WILL fail with confusing error messages. This is the number one cause of GHL API problems.


### Step 4: Run the Self-Tests

After setup, your AI agent should automatically run these tests to make sure everything is working:

**Test 1 - Verify the credentials exist:**
```
echo "API Key: $(echo $GHL_API_KEY | head -c 10)..."
echo "Location ID: $GHL_LOCATION_ID"
```
You should see the first 10 characters of your API key and your full Location ID.

**Test 2 - Test the API connection (get location info):**
```
curl -s -X GET "https://services.leadconnectorhq.com/locations/$GHL_LOCATION_ID" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"
```
You should see a response with your location name, address, and other details. If you see an error, check that your API key and Location ID are correct.

**Test 3 - Test contact search:**
```
curl -s -X GET "https://services.leadconnectorhq.com/contacts/?locationId=$GHL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"
```
You should see a response with a contacts list (it might be empty if you have no contacts yet, but you should still get a valid response, not an error).

**Test 4 - Test media library access:**
```
curl -s -X GET "https://services.leadconnectorhq.com/medias/?locationId=$GHL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"
```
You should see a response with a media files list. This proves the media library permissions are working.


### Step 5: Update Your Core .md Files

Follow the TSP rules - only add summaries and file path references.

**What to add to TOOLS.md:** Add the GHL API base URL, the Version header requirement, and the common endpoint paths. See the [ADD TO TOOLS.md] section in ghl-setup-full.md.

**What to add to MEMORY.md:** Add a note that GHL credentials are configured and where they are stored. See the [ADD TO MEMORY.md] section in ghl-setup-full.md.

**What to add to AGENTS.md:** Add the rule to always include the Version header. See the [ADD TO AGENTS.md] section in ghl-setup-full.md.


### Self-Test Checklist

After completing all steps, verify each of these is true:

- [ ] API key is saved in the config file (check env.vars.GHL_API_KEY)
- [ ] Location ID is saved in the config file (check env.vars.GHL_LOCATION_ID)
- [ ] Can reach services.leadconnectorhq.com (no network errors)
- [ ] Can get location info (proves authentication works)
- [ ] Can search contacts (proves permissions work)
- [ ] Version header is being sent (no 400 errors)
- [ ] Media library access works (proves media scope is enabled)

If ANY test fails:
1. Check that the API key is correct and has not expired
2. Check that the Location ID matches your account
3. Check that the Version header is exactly: 2021-07-28
4. Check that the API key has the correct permissions/scopes enabled in GHL
5. Report the specific error message to the user

Do NOT tell the user "it is set up" until ALL tests pass.
