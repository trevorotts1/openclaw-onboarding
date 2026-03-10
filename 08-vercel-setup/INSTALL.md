╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: VERIFY TEACH YOURSELF PROTOCOL (TYP) TRAINING

Agent must verify TYP training before proceeding:
- Check AGENTS.md, TOOLS.md, MEMORY.md for "Teach Yourself Protocol" or "TYP"
- Check session context for prior TYP training
- Check for "Teach Yourself Protocol" tab in this document

IF TYP CONFIRMED:
Execute instructions below following TYP file storage structure.

IF TYP NOT CONFIRMED:
HALT. Report to user:
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


══════════════════════════════════════════════════════════════════
  TYP FILE STORAGE INSTRUCTIONS (only read this if TYP confirmed)
══════════════════════════════════════════════════════════════════

WHEN LEARNING THIS DOCUMENT, FOLLOW THIS STRUCTURE:

1. SAVE FULL DOCUMENTATION TO MASTER FILES FOLDER
   Locate OpenClaw master files folder in ~/Downloads/. Possible names:
   - OpenClaw Master Files
   - OpenClaw Master Documents
   - OpenClaw Documents
   - openclaw-master-files
   - openclaw master files
   - OpenClaw Files
   - openclaw-documents
   - Any variation of "openclaw" + "master" or "files" or "documents"
   Search case-insensitively. One word or two words. Plural or singular.
   If no folder found, create: ~/Downloads/OpenClaw Master Files/

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

══════════════════════════════════════════════════════════════════
VERCEL SETUP - AGENT EXECUTION GUIDE
══════════════════════════════════════════════════════════════════

This guide enables an AI agent to autonomously set up Vercel account access,
generate API tokens, and configure OpenClaw for website deployment.
During onboarding, Vercel setup is API/token-driven and must not depend on the Vercel CLI.

Vercel is a website hosting service where the agent deploys (publishes)
websites so they are live on the internet.

══════════════════════════════════════════════════════════════════
AGENT EXECUTION FLOW
══════════════════════════════════════════════════════════════════

STEP 0: DEPENDENCY CHECK

Agent action - run before anything else:

1. Check that jq is available:
   if ! command -v jq &>/dev/null; then
     echo "Installing jq..."
     brew install jq 2>/dev/null || sudo apt-get install -y jq 2>/dev/null
   fi

2. Check that Node.js and npm are available:
   node --version && npm --version
   - If not found: instruct user to install Node.js from https://nodejs.org
     and halt until confirmed.

3. Check that curl is available:
   curl --version
   - If not found: install via system package manager.

STEP 1: CHECK FOR EXISTING VERCEL ACCOUNT AND TOKEN

Agent action:
1. Check environment variables for existing VERCEL_TOKEN across all known
   secrets locations:

   SECRETS_FILE=""
   for f in ~/clawd/secrets/.env ~/.openclaw/.env ~/.env ~/secrets/.env; do
     if [ -f "$f" ]; then SECRETS_FILE="$f"; break; fi
   done

   Also check: ~/.openclaw/openclaw.json and the $VERCEL_TOKEN env var.

2. If VERCEL_TOKEN found:
   - Verify token via API call:
     curl -s -H "Authorization: Bearer $VERCEL_TOKEN" \
       "https://api.vercel.com/v2/user" | jq -r '.user.username'
   - If the username is returned (not null/error), report:
     "Vercel token found and verified. Username: <username>. Skipping setup."
   - HALT execution. Setup complete.

3. If VERCEL_TOKEN not found or API call fails:
   - Proceed to Step 2.

STEP 2: GUIDE USER TO CREATE VERCEL ACCOUNT (if needed)

Agent action:
1. Instruct the user:
   "To continue, you need a Vercel account. If you do not have one yet,
    please go to https://vercel.com/signup and create one now.
    Recommended: click 'Continue with GitHub' to link your repositories.
    Once you see the Vercel dashboard, you are ready for the next step."

2. Do not wait for a conversational reply. Proceed directly to Step 4
   (token creation). The user will complete account creation in parallel.

STEP 3: CREATE VERCEL API TOKEN

Agent action:
1. Instruct user:
   "Go to: https://vercel.com/account/tokens

    Click 'Create' or 'Create Token' and fill in:
    - Token Name: OpenClaw Agent
    - Scope: Full Account
    - Expiration: No Expiration

    Click 'Create Token'. The token will appear once only - copy it
    immediately and paste it here."

2. Receive token from user input.

3. Validate the token by calling the API (do NOT rely on character count
   or format guessing):
   curl -s -H "Authorization: Bearer <TOKEN>" \
     "https://api.vercel.com/v2/user" | jq -r '.user.username'

4. If the API returns a username (non-null, no error):
   - Token is valid. Proceed to Step 5.

5. If the API returns an error or null:
   - Report: "Token validation failed. The token may have been copied
     incorrectly. Please return to https://vercel.com/account/tokens,
     delete that token, create a new one, and paste it here."
   - Return to Step 4, query 2.

STEP 4: STORE TOKEN IN ENVIRONMENT

Agent action:
1. Locate or create secrets file using multi-env check:
   SECRETS_FILE=""
   for f in ~/clawd/secrets/.env ~/.openclaw/.env ~/.env ~/secrets/.env; do
     if [ -f "$f" ]; then SECRETS_FILE="$f"; break; fi
   done
   if [ -z "$SECRETS_FILE" ]; then
     SECRETS_FILE=~/clawd/secrets/.env
     mkdir -p ~/clawd/secrets
   fi

2. Add or update the token line:
   VERCEL_TOKEN=<TOKEN>

3. Verify the line was written:
   grep "VERCEL_TOKEN" "$SECRETS_FILE"

4. Export to current shell session:
   export VERCEL_TOKEN=<TOKEN>

STEP 5: UPDATE CORE DOCUMENTATION FILES

Agent action - follow CORE_UPDATES.md for exact text:
1. Update AGENTS.md with Vercel section (lean summary + path reference).
2. Update TOOLS.md with Vercel API section.
3. Update MEMORY.md with setup timestamp.

STEP 6: FINAL VERIFICATION

Agent action:
1. Run the verification API call:
   curl -s -H "Authorization: Bearer $VERCEL_TOKEN" \
     "https://api.vercel.com/v2/user" | jq -r '.user.username'

2. Expected output: the user's Vercel username as a plain string.
   Example: "your-vercel-username"

3. If the API verification passes:
   - Report: "Vercel setup complete! Username: <username>"
   - Proceed to Step 8.

4. If the API check fails:
   - Report the specific error and retry from Step 4.

STEP 7: COMPLETION REPORT

Agent action:
1. Generate completion checklist:
   [x] jq dependency verified
   [x] Vercel API token created with Full Account scope
   [x] Token validated via API (not format-guessing)
   [x] Token saved to secrets file
   [x] AGENTS.md updated
   [x] TOOLS.md updated
   [x] MEMORY.md updated
   [x] Final verification passed - username: <username>

2. Report to user:
   "Vercel setup is complete! I can now deploy websites for you anytime.
    Just ask me to build or deploy something and I will handle it."

3. HALT execution. Setup complete.

══════════════════════════════════════════════════════════════════
AGENT EXECUTION CHECKLIST
══════════════════════════════════════════════════════════════════

Before reporting completion, agent must verify ALL items:

[ ] jq installed and available
[ ] Existing VERCEL_TOKEN checked across all secrets locations
[ ] User directed to account creation page (if needed)
[ ] API token created with Full Account scope
[ ] Token validated via API call (not character count)
[ ] Token saved to secrets file
[ ] AGENTS.md updated with Vercel section
[ ] TOOLS.md updated with Vercel section
[ ] MEMORY.md updated
[ ] Final API verification passed - username retrieved

DO NOT report setup complete until the API verification check passes and
all checklist items are confirmed.

══════════════════════════════════════════════════════════════════
AGENT CAPABILITIES AFTER SETUP
══════════════════════════════════════════════════════════════════

Once Vercel setup is complete, agent can autonomously:
- Create and manage projects via Vercel API
- Manage custom domains via Vercel API
- Set environment variables via Vercel API
- Create preview and production deployments via API or authenticated git push
- Query project status and deployment history via API
