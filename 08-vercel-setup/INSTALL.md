## 🔴 API-ONLY EXECUTION LOCK (SOVEREIGN)
- For this onboarding package, do NOT use service CLIs for GitHub, Vercel, or Context7.
- Do NOT use `gh`, `vercel`, or any Context7 CLI command for setup/auth.
- Use API-driven setup and browser-based account/token creation flows only.
- The only onboarding skill allowed to rely on CLI-specific service commands is Superdesign.

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

══════════════════════════════════════════════════════════════════
VERCEL SETUP - AGENT EXECUTION GUIDE
══════════════════════════════════════════════════════════════════

This guide enables an AI agent to autonomously set up Vercel account access,
generate API tokens, and configure OpenClaw for website deployment.

Vercel is a website hosting service where the agent deploys (publishes)
websites so they are live on the internet.

══════════════════════════════════════════════════════════════════
AGENT EXECUTION FLOW
══════════════════════════════════════════════════════════════════

STEP 1: CHECK FOR EXISTING VERCEL ACCOUNT AND TOKEN

Agent action:
1. Check environment variables for existing VERCEL_TOKEN:
   - Read ~/.openclaw/openclaw.json for VERCEL_TOKEN
   - Read ~/clawd/secrets/.env for VERCEL_TOKEN
   - Read $VERCEL_TOKEN environment variable

2. If VERCEL_TOKEN found and valid:
   - Verify token via API call:
     curl -s -H "Authorization: Bearer $VERCEL_TOKEN" \
       "https://api.vercel.com/v2/user" | jq '.user.username'
   - If successful, report: "Vercel token found and verified. Skipping setup."
   - HALT execution. Setup complete.

3. If VERCEL_TOKEN not found or invalid:
   - Proceed to Step 2

STEP 2: REQUEST VERCEL ACCOUNT STATUS FROM USER

Agent action:
1. Query user: "Do you already have a Vercel account?"
   - If YES: Proceed to Step 3A (Existing Account)
   - If NO: Proceed to Step 3B (New Account)

STEP 3A: EXISTING VERCEL ACCOUNT FLOW

Agent action:
1. Query user: "Are you currently logged into Vercel in your browser?"

2. If NO:
   - Instruct user: "Please open https://vercel.com in your browser and log in"
   - Wait for user confirmation: "I have logged in"

3. If YES or after user confirms login:
   - Proceed to Step 4 (API Token Creation)

STEP 3B: NEW VERCEL ACCOUNT FLOW

Agent action:
1. Open browser to https://vercel.com/signup

2. Instruct user:
   "I am opening Vercel signup. You will see options to sign up with GitHub,
    GitLab, Bitbucket, or Email. Choose the option that works best for you.
    If you have a GitHub account, use 'Continue with GitHub' (recommended).
    Otherwise, use 'Continue with Email'. Complete the signup process and
    confirm when you reach the Vercel dashboard."

3. Wait for user confirmation: "I have completed signup and see the dashboard"

4. Proceed to Step 4 (API Token Creation)

STEP 4: CREATE VERCEL API TOKEN

Agent action:
1. Instruct user:
   "I will now guide you to create an API token. Open this URL in your browser:
    https://vercel.com/account/tokens
    
    You should see a 'Create' or 'Create Token' button. Click it.
    
    Fill in these settings:
    - Token Name: OpenClaw Agent
    - Scope: Full Account
    - Expiration: No Expiration
    
    Click 'Create Token'. The token will appear once - copy it immediately."

2. Query user: "Please paste the API token you just created"

3. Receive token from user input

4. Validate token format (should be ~24 character alphanumeric string):
   - If invalid format: "Token format appears incorrect. Please verify and try again."
   - Return to Step 4, query 2

5. Verify token via API call:
   curl -s -H "Authorization: Bearer <TOKEN>" \
     "https://api.vercel.com/v2/user" | jq '.user.username'

6. If verification fails:
   - Report: "Token verification failed. Please check the token and try again."
   - Return to Step 4, query 2

7. If verification succeeds:
   - Capture username from API response
   - Proceed to Step 5 (Token Storage)

STEP 5: STORE TOKEN IN ENVIRONMENT

Agent action:
1. Check if secrets.env exists at ~/clawd/secrets/.env
   - If not found: Create file at ~/clawd/secrets/.env

2. Add or update line in secrets.env:
   VERCEL_TOKEN=<TOKEN>

3. Verify file was written correctly:
   - Read file and confirm VERCEL_TOKEN line present

4. Export token to current shell session:
   export VERCEL_TOKEN=<TOKEN>

5. Proceed to Step 6 (Core File Updates)

STEP 6: UPDATE CORE DOCUMENTATION FILES

Agent action:
1. Update AGENTS.md:
   - Add section:
     ## Vercel
     - Token stored in secrets.env as VERCEL_TOKEN
     - Used for: Website deployments, hosting, serverless functions
     - Dashboard: https://vercel.com/dashboard

2. Update TOOLS.md:
   - Add section:
     ## Vercel CLI and API
     - Token: $VERCEL_TOKEN (in secrets.env)
     - CLI: vercel (install with: npm i -g vercel)
     - API Base: https://api.vercel.com
     - Deploy: vercel --prod
     - List projects: vercel ls

3. Verify both files were updated correctly

4. Proceed to Step 7 (Optional CLI Installation)

STEP 7: OPTIONAL - INSTALL VERCEL CLI

Agent action:
1. Query user: "Would you like me to install the Vercel CLI? (yes/no)"
   - If NO: Skip to Step 8 (Verification)
   - If YES: Proceed with installation

2. Execute terminal command:
   npm i -g vercel

3. If permission error occurs:
   - Execute with sudo:
     sudo npm i -g vercel

4. Verify installation:
   vercel --version

5. If version output received:
   - Report: "Vercel CLI installed successfully: <version>"
   - Proceed to Step 8

6. If installation fails:
   - Report error to user
   - Proceed to Step 8 (Verification will still work via API)

STEP 8: FINAL VERIFICATION

Agent action:
1. Execute verification API call:
   curl -s -H "Authorization: Bearer $VERCEL_TOKEN" \
     "https://api.vercel.com/v2/user" | jq '.user.username'

2. If successful:
   - Capture username from response
   - Report: "✅ Vercel setup complete! Username: <username>"
   - Proceed to Step 9 (Completion Report)

3. If verification fails:
   - Report: "❌ Verification failed. Token may be invalid or expired."
   - Query user: "Would you like to create a new token and try again? (yes/no)"
   - If YES: Return to Step 4
   - If NO: Report setup incomplete and halt

STEP 9: COMPLETION REPORT

Agent action:
1. Generate completion checklist:
   ✅ Vercel account verified (or created)
   ✅ API token created with Full Account scope
   ✅ Token saved to secrets.env as VERCEL_TOKEN
   ✅ AGENTS.md updated with Vercel section
   ✅ TOOLS.md updated with Vercel section
   ✅ Vercel CLI installed (if requested)
   ✅ Verification test passed - username: <username>

2. Report to user:
   "Vercel setup is complete! I can now deploy websites for you anytime.
    Just ask me to build or deploy something and I will handle it."

3. HALT execution. Setup complete.

══════════════════════════════════════════════════════════════════
AGENT EXECUTION CHECKLIST
══════════════════════════════════════════════════════════════════

Before reporting completion, agent must verify ALL items:

[ ] Environment checked for existing VERCEL_TOKEN
[ ] User account status confirmed (existing or new)
[ ] Vercel account access verified (logged in or created)
[ ] API token created with Full Account scope
[ ] Token validated via API call
[ ] Token saved to secrets.env as VERCEL_TOKEN
[ ] AGENTS.md updated with Vercel section
[ ] TOOLS.md updated with Vercel section
[ ] Vercel CLI installed (if user requested)
[ ] Final verification test passed - username retrieved successfully

DO NOT report setup complete until verification test passes and all checklist items are confirmed.

══════════════════════════════════════════════════════════════════
AGENT CAPABILITIES AFTER SETUP
══════════════════════════════════════════════════════════════════

Once Vercel setup is complete, agent can autonomously:
- Deploy websites to Vercel (make them live on the internet)
- Create new projects via API
- Manage custom domains (like www.yourbusiness.com)
- Set environment variables (configuration for websites)
- Create preview deployments (test websites before going live)
- Query project status and deployment history
- Manage team members and permissions (if Full Account scope)
