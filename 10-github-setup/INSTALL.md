## 🔴 API-ONLY EXECUTION LOCK (SOVEREIGN)
- For this onboarding package, do NOT use service CLIs for GitHub, Vercel, or Context7.
- Do NOT use `gh`, `vercel`, or any Context7 CLI command for setup/auth.
- Use API-driven setup and browser-based account/token creation flows only.
- The only onboarding skill allowed to rely on CLI-specific service commands is Superdesign.

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
GITHUB SETUP - INSTALLATION GUIDE
══════════════════════════════════════════════════════════════════

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: CHECK FOR EXISTING GITHUB ACCOUNT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Check ~/clawd/secrets/.env for GITHUB_TOKEN or GH_TOKEN. If found, also
   check for GITHUB_USERNAME.

2. If both token and username exist, skip to Step 5 (Verify Everything Works).

3. If token exists but no username, extract username via:
   curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
     "https://api.github.com/user" | jq -r '.login'
   If successful, skip to Step 4 (Store the Token and Username).

4. If no token found, ask the user:
   "Do you already have a GitHub account? If yes, what is your username?
    Do you have a Personal Access Token (PAT) with full permissions?"

5. If user has an account and token: skip to Step 4.
   If user has an account but no token: skip to Step 3.
   If user has no account: proceed to Step 2.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2: CREATE GITHUB ACCOUNT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Navigate to https://github.com using browser automation.

2. Click "Sign up".

3. Enter user's email address when prompted. Request email from user if
   not already known. Store it for git config in Step 3.

4. Create a strong password when prompted. Request from user or generate one.

5. Enter a professional username when prompted. Request from user if no
   preference.

6. Complete the verification puzzle.

7. Instruct user to check their email inbox for GitHub verification email
   and click the verification link.

8. Verify the dashboard loads after email verification.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3: CREATE A PERSONAL ACCESS TOKEN (PAT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Navigate to https://github.com/settings/tokens using browser automation.

2. Click "Generate new token", then click "Generate new token (classic)".

3. Enter "OpenClaw Agent" in the Note field.

4. Select "No expiration" for Expiration.

5. Check ALL of these permission boxes:
   - repo
   - workflow
   - write:packages
   - delete:packages
   - admin:org
   - admin:public_key
   - admin:repo_hook
   - admin:org_hook
   - gist
   - notifications
   - user
   - delete_repo
   - write:discussion
   - admin:enterprise
   - audit_log
   - codespace
   - copilot
   - project
   - admin:gpg_key
   - admin:ssh_signing_key

6. Click "Generate token".

7. Retrieve the generated token from the page (starts with "ghp_"). Store
   it immediately - it is only displayed once.

8. If the page is closed before copying, navigate back to the tokens page,
   delete that token, and repeat this step.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4: CONFIGURE GIT AND STORE CREDENTIALS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Ask the user: "What name should appear on your code commits?" (usually
   their full name).

2. Run:
   git config --global user.name "USER_PROVIDED_NAME"

3. Ask the user: "What email should be associated with your commits?" (use
   the same email as their GitHub account).

4. Run:
   git config --global user.email "USER_PROVIDED_EMAIL"

5. Run:
   git config --global credential.helper store
   git config --global init.defaultBranch main

6. Save to secrets.env file (or ~/clawd/secrets/.env):
   GITHUB_TOKEN=<retrieved-token>
   GITHUB_USERNAME=<github-username>

7. Update AGENTS.md - add this section:
   ## GitHub
   - Token stored in secrets.env as GITHUB_TOKEN
   - Username: <github-username>
   - All scopes enabled for full access
   - Used for: Version control, backups, deployments

   ### Git Rules
   - Commit after completing any logical unit of work
   - Commit before making risky changes
   - Push at the end of every work session
   - NEVER commit secrets or tokens

8. Update TOOLS.md - add this section:
   ## Git and GitHub
   - Token: $GITHUB_TOKEN
   - Username: $GITHUB_USERNAME
   - API: https://api.github.com

   Common commands:
   - git status        (check what has changed)
   - git add .         (prepare all changes for saving)
   - git commit -m ""  (save changes with a message)
   - git push          (upload changes to GitHub)
   - git pull          (download latest changes from GitHub)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5: VERIFY EVERYTHING WORKS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Run:
   curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
     "https://api.github.com/user" | jq '.login'

2. Verify output matches the expected GitHub username.

3. If error occurs, check:
   - Token saved correctly in secrets.env
   - Token starts with "ghp_"
   - Token has not been revoked or deleted from GitHub

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SETUP CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before telling the user that setup is complete, verify ALL of these:

[ ] GitHub account created (or confirmed existing)
[ ] Personal Access Token created with all scopes
[ ] Token saved to secrets.env as GITHUB_TOKEN
[ ] Username saved to secrets.env as GITHUB_USERNAME
[ ] Git user.name configured
[ ] Git user.email configured
[ ] Git credential.helper set to store
[ ] Git default branch set to main
[ ] AGENTS.md updated with GitHub section
[ ] TOOLS.md updated with Git/GitHub section
[ ] Verification test passed - can see username via API

DO NOT tell the user setup is complete until the verification test passes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POST-SETUP CAPABILITIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tell the user:
"GitHub is all set up! I can now back up your code, track changes, and
deploy websites for you. Would you like me to back up any projects
right now?"
