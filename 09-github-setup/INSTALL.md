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
GITHUB SETUP - INSTALLATION GUIDE
══════════════════════════════════════════════════════════════════

This guide walks you through creating a GitHub account, generating a
Personal Access Token (PAT), configuring Git on your computer, and
connecting GitHub to your OpenClaw setup.

What is GitHub? It is a website where your code and projects are stored
safely in the cloud. Think of it like Google Drive, but specifically
designed for code and website files. It keeps track of every change you
make, so if something breaks, you can always go back to a working version.

Why do you need it? Your AI agent uses GitHub to:
- Back up your code so it is never lost
- Track every change made to your projects
- Deploy websites automatically (when connected to Vercel)
- Collaborate if you work with others

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: CHECK IF YOU ALREADY HAVE GITHUB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before creating a new account, the AI should ask:

"Do you already have a GitHub account? (yes/no)"

If YES:
  - Ask: "What is your GitHub username?"
  - Ask: "Do you have a Personal Access Token (PAT) with full permissions?"
  - If they have a token: Skip to Step 5 (Store the Token)
  - If no token: Skip to Step 3 (Token Creation)

If NO:
  - Proceed to Step 2

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2: CREATE YOUR GITHUB ACCOUNT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Open your web browser (Chrome, Safari, Edge, or Firefox).

2. Go to: https://github.com

3. Click the "Sign up" button. It is usually in the top right corner.

4. Enter your email address when asked.
   (Remember this email - you will need it later for Git configuration.)

5. Create a strong password when asked.

6. Choose a username. This will be visible publicly and will be part of
   your project URLs. Pick something professional. For example, if your
   name is John Smith, you might use "johnsmith" or "jsmith-dev".

7. Complete the verification puzzle (GitHub will show you an image puzzle
   to prove you are a person, not a robot).

8. Check your email inbox for a verification email from GitHub. Click the
   link in that email to verify your account.

9. After verifying, you should be able to log into GitHub and see your
   dashboard. It will look mostly empty since you are brand new.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3: CREATE A PERSONAL ACCESS TOKEN (PAT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A Personal Access Token is like a special password that lets your AI agent
work with GitHub on your behalf. It is more secure than using your regular
password.

10. Go to: https://github.com/settings/tokens
    (You can also get here by clicking your profile picture in the top
    right corner, then "Settings", then "Developer settings" at the very
    bottom of the left sidebar, then "Personal access tokens", then
    "Tokens (classic)".)

11. Click "Generate new token" and then choose "Generate new token (classic)".

12. You will see a form. Fill it in like this:

    - Note: Type "OpenClaw Agent" (this is just a label so you remember
      what this token is for)
    - Expiration: Select "No expiration" (or choose a shorter time if
      you prefer more security, but you will need to create a new one
      when it expires)

13. Now you need to check the permission boxes. These tell GitHub what
    your AI agent is allowed to do. Check ALL of these boxes:

    Check the box next to "repo" (this automatically checks the sub-items)
    Check the box next to "workflow"
    Check the box next to "write:packages"
    Check the box next to "delete:packages"
    Check the box next to "admin:org"
    Check the box next to "admin:public_key"
    Check the box next to "admin:repo_hook"
    Check the box next to "admin:org_hook"
    Check the box next to "gist"
    Check the box next to "notifications"
    Check the box next to "user"
    Check the box next to "delete_repo"
    Check the box next to "write:discussion"
    Check the box next to "admin:enterprise"
    Check the box next to "audit_log"
    Check the box next to "codespace"
    Check the box next to "copilot"
    Check the box next to "project"
    Check the box next to "admin:gpg_key"
    Check the box next to "admin:ssh_signing_key"

    Yes, that is a lot of checkboxes. Check them all to give your AI
    agent full access to help you with everything.

14. Scroll down and click the green "Generate token" button at the bottom
    of the page.

15. IMPORTANT: The token will only be shown ONCE! It looks like a long
    string starting with "ghp_" followed by about 36 random letters and
    numbers. For example: ghp_1a2B3c4D5e6F7g8H9i0JkLmNoPqRsTuVwX

16. Copy this token immediately. Paste it somewhere safe, or give it
    directly to your AI agent.

    If you accidentally close the page without copying the token, go back
    to the tokens page, delete that token, and create a new one.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4: CONFIGURE GIT ON YOUR COMPUTER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Git is the software that runs on your computer and talks to GitHub. It is
probably already installed. The AI agent needs to set up your identity so
Git knows who is making changes.

17. The AI agent will ask: "What name should appear on your code commits?"
    (This is usually your full name, like "John Smith".)

18. The AI agent runs this command (you do not need to do this yourself):
    git config --global user.name "Your Name Here"

19. The AI agent will ask: "What email should be associated with your
    commits?" (Use the same email as your GitHub account.)

20. The AI agent runs this command:
    git config --global user.email "your-email@example.com"

21. The AI agent also runs these setup commands:
    git config --global credential.helper store
    git config --global init.defaultBranch main

    The first one saves your login so you do not have to enter it every
    time. The second one sets "main" as the default name for new projects.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5: STORE THE TOKEN AND USERNAME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The AI agent should store the token and username in these places:

22. Save to secrets.env file:
    GITHUB_TOKEN=paste-your-token-here
    GITHUB_USERNAME=your-github-username

23. Update AGENTS.md - add this section:
    ## GitHub
    - Token stored in secrets.env as GITHUB_TOKEN
    - Username: your-github-username
    - All scopes enabled for full access
    - Used for: Version control, backups, deployments

    ### Git Rules
    - Commit after completing any logical unit of work
    - Commit before making risky changes
    - Push at the end of every work session
    - NEVER commit secrets or tokens

24. Update TOOLS.md - add this section:
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
STEP 6: VERIFY EVERYTHING WORKS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

25. The AI agent runs this command to test:

    curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
      "https://api.github.com/user" | jq '.login'

    Expected output: Your GitHub username in quotes (for example:
    "johnsmith").

    If you see an error, check that:
    - The token was saved correctly
    - The token starts with "ghp_"
    - The token has not been revoked or deleted from GitHub

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
WHAT THE USER CAN DO AFTER SETUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Once GitHub is set up, the AI agent can help with:
- Backing up code to the cloud (so it is never lost)
- Tracking changes to projects (see what changed and when)
- Deploying websites automatically (especially with Vercel)
- Restoring old versions if something breaks
- Creating new repositories (project folders on GitHub)

Tell the user:
"GitHub is all set up! I can now back up your code, track changes, and
deploy websites for you. Would you like me to back up any projects
right now?"
