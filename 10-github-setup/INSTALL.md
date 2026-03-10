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


══════════════════════════════════════════════════════════════════
  TYP FILE STORAGE INSTRUCTIONS (only read this if TYP confirmed)
══════════════════════════════════════════════════════════════════

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

══════════════════════════════════════════════════════════════════
GITHUB SETUP - INSTALLATION GUIDE
══════════════════════════════════════════════════════════════════

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 0: LOCATE SECRETS FILE (MULTI-ENV CHECK)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before doing anything else, identify where secrets are stored on this machine.
Run this check and store the result in $SECRETS_FILE for use in later steps:

  SECRETS_FILE=""
  for f in ~/clawd/secrets/.env ~/.openclaw/.env ~/.env ~/secrets/.env; do
    if [ -f "$f" ]; then SECRETS_FILE="$f"; break; fi
  done
  if [ -z "$SECRETS_FILE" ]; then
    SECRETS_FILE=~/clawd/secrets/.env
    mkdir -p ~/clawd/secrets
  fi
  echo "Secrets file: $SECRETS_FILE"

Use $SECRETS_FILE for all read/write operations in subsequent steps.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: CHECK FOR EXISTING GITHUB TOKEN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Check $SECRETS_FILE for GITHUB_TOKEN or GH_TOKEN. Also check for
   GITHUB_USERNAME.

2. If both token and username exist, skip to Step 5 (Verify Everything Works).

3. If token exists but no username, extract via:
   curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
     "https://api.github.com/user" | jq -r '.login'
   If successful, skip to Step 4 (Store Credentials).

4. If no token found:
   - Request the token from the user once (see Step 3).
   - While waiting for the token, proceed immediately with all non-token
     setup tasks: git config, credential helper, jq/git dependency checks.
   - Mark token-dependent steps as PENDING and complete them when the
     token is received.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2: CREATE GITHUB ACCOUNT (if the user has none)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If user does not have a GitHub account:

1. Direct them to https://github.com and instruct them to click "Sign up".

2. Ask for their intended email address and store it for git config (Step 3).

3. Instruct them to complete the signup form (email, password, username,
   verification puzzle).

4. Instruct them to check their inbox and click the GitHub verification email.

5. Confirm they can see the GitHub dashboard before proceeding.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3: CREATE A PERSONAL ACCESS TOKEN (PAT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Instruct the user to:

1. Go to: https://github.com/settings/tokens

2. Click "Generate new token" then "Generate new token (classic)".

3. Fill in:
   - Note: OpenClaw Agent
   - Expiration: 90 days (recommended - rotate when expired)

4. Check these permission scopes (minimum required):
   - repo            (full repository access)
   - read:org        (read org and team membership)
   - workflow        (update GitHub Actions workflows)

   Only add additional scopes if a specific feature requires them.
   Over-permissioned tokens are a security risk.

5. Click "Generate token" at the bottom.

6. IMPORTANT: Copy the token immediately. It starts with "ghp_" and is
   shown only once. If the page is closed before copying, that token must
   be deleted and a new one created.

7. Paste the token here.

NON-BLOCKING: While waiting for the user to create the token, proceed with
Step 4 (git config, credential helper). Mark token storage as PENDING.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4: CONFIGURE GIT AND CREDENTIAL HELPER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

These steps do NOT require the token. Execute them immediately.

1. Ask the user: "What name should appear on your code commits?"
   (Typically their full name.)

   Run:
   git config --global user.name "USER_PROVIDED_NAME"

2. Ask the user: "What email should be associated with your commits?"
   (Use the same email as their GitHub account.)

   Run:
   git config --global user.email "USER_PROVIDED_EMAIL"

3. Configure credential helper and default branch:
   git config --global credential.helper store
   git config --global init.defaultBranch main

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5: STORE TOKEN AND USERNAME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Once the token is received:

1. Retrieve the GitHub username via API:
   curl -s -H "Authorization: Bearer <TOKEN>" \
     "https://api.github.com/user" | jq -r '.login'

2. Write to $SECRETS_FILE:
   GITHUB_TOKEN=<retrieved-token>
   GITHUB_USERNAME=<github-username>

3. Verify both lines are present:
   grep "GITHUB_TOKEN\|GITHUB_USERNAME" "$SECRETS_FILE"

4. Export to current shell:
   export GITHUB_TOKEN=<retrieved-token>
   export GITHUB_USERNAME=<github-username>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 6: UPDATE CORE DOCUMENTATION FILES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Follow CORE_UPDATES.md for exact text to add. Update:
- AGENTS.md - lean GitHub section + file path reference
- TOOLS.md - lean Git/GitHub commands + file path reference
- MEMORY.md - setup timestamp + file path reference

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 7: DETERMINISTIC VERIFICATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Run each check and confirm the expected output exactly.

CHECK 1: Git configuration
  git config --list | grep -E "user\.|credential\.|init\."

  Expected output (all four lines must be present):
  user.name=<the name provided by user>
  user.email=<the email provided by user>
  credential.helper=store
  init.defaultbranch=main

CHECK 2: Credential helper
  git config --global credential.helper

  Expected output:
  store

CHECK 3: GitHub API test
  curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
    "https://api.github.com/user" | jq -r '.login'

  Expected output:
  <the user's GitHub username as a plain string, no quotes, no null>

  If output is "null" or an error message: the token is invalid.
  Delete it from GitHub, create a new one, and repeat Step 3.

There is no GitHub CLI requirement in this onboarding flow.
GitHub setup is complete when git config is correct and the PAT verifies through the GitHub API.

ALL THREE CHECKS MUST PASS before declaring setup complete.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SETUP CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before telling the user that setup is complete, verify ALL of these:

[ ] Secrets file location determined ($SECRETS_FILE)
[ ] GitHub account confirmed (existing or created)
[ ] PAT created with at minimum: repo, read:org, workflow scopes
[ ] PAT expiration set to 90 days
[ ] Token saved to $SECRETS_FILE as GITHUB_TOKEN
[ ] Username saved to $SECRETS_FILE as GITHUB_USERNAME
[ ] git config user.name set
[ ] git config user.email set
[ ] git config credential.helper set to store
[ ] git config init.defaultBranch set to main
[ ] AGENTS.md updated
[ ] TOOLS.md updated
[ ] MEMORY.md updated
[ ] CHECK 1: git config --list shows all four expected values
[ ] CHECK 2: credential.helper returns "store"
[ ] CHECK 3: API call returns the correct username (not null)

DO NOT tell the user setup is complete until the verification checks pass.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POST-SETUP CAPABILITIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tell the user:
"GitHub is all set up! I can now back up your code, track changes, and
deploy websites for you. Would you like me to back up any projects now?"
