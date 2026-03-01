
╔══════════════════════════════════════════════════════════════╗
  MANDATORY TSP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

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

══════════════════════════════════════════════════════════════════
  TSP FILE STORAGE INSTRUCTIONS (only read this if TSP confirmed)
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
🐙 GITHUB SETUP - AI WALKTHROUGH INSTRUCTIONS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PURPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This document tells YOU (the AI) how to guide your human through setting up GitHub.
You will ASK them questions, TELL them what to do, and VERIFY each step is complete.
GitHub lets you back up their code, track changes, and deploy websites.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: CHECK IF THEY HAVE GITHUB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ASK THE HUMAN:
"Do you already have a GitHub account? (yes/no)"

IF YES:
  ASK: "What's your GitHub username?"
  THEN ASK: "Do you have a Personal Access Token (PAT) with full permissions?"
  
  → If they have a token: Ask them to share it, then skip to STEP 5
  → If no token: Skip to STEP 3 (Token Creation)

IF NO:
  → Proceed to STEP 2

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2: GUIDE ACCOUNT CREATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TELL THE HUMAN:
"Let's create your GitHub account. Go to https://github.com and click 'Sign up'."

GUIDE THEM THROUGH:
"I'll walk you through each step. First, enter your email address."

ASK: "What email did you enter?"
(Save this - you'll need it for git config later)

TELL THEM: "Now create a strong password."
ASK: "Done? (yes)"

TELL THEM: "Choose a username. This will be visible publicly and part of your 
repository URLs, so pick something professional."
ASK: "What username did you choose?"
(Save this - you'll need it later)

TELL THEM: "Complete the verification puzzle and verify your email. Check your 
inbox for a verification email from GitHub."

ASK: "Are you logged into GitHub now and can see the dashboard?"
  → If yes: Proceed to STEP 3
  → If no: Help them troubleshoot

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3: CREATE PERSONAL ACCESS TOKEN (PAT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TELL THE HUMAN:
"Now we need to create a Personal Access Token. This lets me help you manage 
your code repositories. Go to: https://github.com/settings/tokens"

ASK: "Are you on the tokens page?"

WHEN THEY CONFIRM:
TELL THEM:
"Click 'Generate new token' and then 'Generate new token (classic)'."

ASK: "Do you see a form asking for token settings?"

WHEN THEY CONFIRM:
TELL THEM:
"Fill in these settings:
  1. Note: Type 'OpenClaw Agent'
  2. Expiration: Select 'No expiration'
  3. Scopes: We need to select ALL scopes for full access. I'll guide you..."

GUIDE THROUGH SCOPES:
TELL THEM:
"Check ALL of these boxes. I'll list them - just confirm as you go:

  ☐ repo (Full control of private repositories)
  ☐ workflow (Update GitHub Action workflows)
  ☐ write:packages
  ☐ delete:packages
  ☐ admin:org
  ☐ admin:public_key
  ☐ admin:repo_hook
  ☐ admin:org_hook
  ☐ gist
  ☐ notifications
  ☐ user
  ☐ delete_repo
  ☐ write:discussion
  ☐ admin:enterprise
  ☐ audit_log
  ☐ codespace
  ☐ copilot
  ☐ project
  ☐ admin:gpg_key
  ☐ admin:ssh_signing_key

Did you check all of them?"

WHEN THEY CONFIRM:
TELL THEM:
"Scroll down and click 'Generate token' at the bottom."

CRITICAL - TELL THEM:
"⚠️ COPY THE TOKEN NOW! It will only be shown once. It starts with 'ghp_' 
and is about 40 characters. Paste it here so I can save it."

WAIT FOR TOKEN:
  → Verify it starts with "ghp_" and is ~40 characters
  → If valid: Proceed to STEP 4
  → If they lost it: Tell them to delete that token and create a new one

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4: CONFIGURE GIT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ASK THE HUMAN:
"What name should appear on your code commits? (Usually your full name)"

WHEN THEY RESPOND:
Run: git config --global user.name "<their_name>"

ASK:
"What email should be associated with your commits? (Use the same email as your 
GitHub account for best results)"

WHEN THEY RESPOND:
Run: git config --global user.email "<their_email>"

THEN RUN:
git config --global credential.helper store
git config --global init.defaultBranch main

TELL THE HUMAN:
"I've configured Git with your identity. Your commits will now show your name 
and email."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5: STORE THE TOKEN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WHEN YOU HAVE THE TOKEN AND USERNAME:

1. Save to secrets.env:
   GITHUB_TOKEN=<their_token>
   GITHUB_USERNAME=<their_username>

2. Update AGENTS.md - add this section:
   ## GitHub
   - Token stored in secrets.env as GITHUB_TOKEN
   - Username: <their_username>
   - All scopes enabled for full access
   - Used for: Version control, backups, deployments
   
   ### Git Rules
   - Commit after completing any logical unit of work
   - Commit before making risky changes
   - Push at the end of every work session
   - NEVER commit secrets or tokens
   - Use descriptive commit messages

3. Update TOOLS.md - add this section:
   ## Git & GitHub
   - Token: $GITHUB_TOKEN
   - Username: $GITHUB_USERNAME
   - API: https://api.github.com
   
   Common commands:
   - git status        # Check what's changed
   - git add .         # Stage all changes
   - git commit -m ""  # Commit with message
   - git push          # Push to GitHub
   - git pull          # Get latest changes

TELL THE HUMAN:
"GitHub is all set up! I can now help you:
  • Back up your code to the cloud
  • Track changes to your projects
  • Deploy websites automatically
  • Restore old versions if something breaks

Would you like me to back up any projects right now?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 6: VERIFY IT WORKS (OPTIONAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ASK THE HUMAN:
"Want me to run a quick test to make sure GitHub is working?"

IF YES:
  Run: curl -s -H "Authorization: Bearer $GITHUB_TOKEN"          "https://api.github.com/user" | jq '.login'
  
  IF IT WORKS:
    TELL THEM: "GitHub is working! I can see your account: <username>"
  
  IF IT FAILS:
    Troubleshoot - token might be wrong

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ONGOING GIT OPERATIONS (Reference for AI)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WHEN TO COMMIT (do this automatically):
  • After completing a feature or fix
  • Before making risky changes
  • Before switching to a different task
  • At the end of a work session
  • After updating configuration files

COMMIT MESSAGE FORMAT:
  Fix: <what was fixed>
  Feature: <what was added>
  Docs: <what documentation changed>
  Refactor: <what was restructured>
  Chore: <maintenance task>

BACKUP A WEBSITE:
  cd <project_folder>
  git init (if not already a repo)
  git add .
  git commit -m "Backup: $(date +%Y-%m-%d)"
  gh repo create <name> --private --source=. --push

KEEP IN SYNC:
  • Always pull before starting work: git pull
  • Always push after committing: git push
  • Check status regularly: git status

API ENDPOINTS:
  GET /user                     # User info
  GET /user/repos               # List repos
  POST /user/repos              # Create repo
  GET /repos/{owner}/{repo}     # Repo info
  GET /repos/{owner}/{repo}/commits  # Commit history

NEVER COMMIT:
  • .env files with real secrets
  • API tokens or passwords
  • node_modules/
  • Large binary files


