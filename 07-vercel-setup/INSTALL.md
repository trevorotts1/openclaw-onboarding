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
VERCEL SETUP - INSTALLATION GUIDE
══════════════════════════════════════════════════════════════════

This guide walks you through creating a Vercel account, generating an API
token, and connecting Vercel to your OpenClaw setup. Vercel is a website
hosting service. It is where your AI agent deploys (publishes) websites
so they are live on the internet.

Think of it like this: When your AI builds a website for you, Vercel is
the place where that website lives so anyone can visit it.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: CHECK IF YOU ALREADY HAVE VERCEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before creating a new account, the AI should ask:

"Do you already have a Vercel account? (yes/no)"

If YES:
  - Ask: "Are you currently logged into Vercel in your browser?"
  - If logged in: Skip to Step 3 (API Token Creation)
  - If not logged in: Tell them to log in at https://vercel.com, then
    go to Step 3

If NO:
  - Proceed to Step 2

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2: CREATE YOUR VERCEL ACCOUNT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Open your web browser (Chrome, Safari, Edge, or Firefox).

2. Go to: https://vercel.com

3. Click "Sign Up" in the top right corner of the page.

4. You will see options for how to create your account:
   - "Continue with GitHub" (RECOMMENDED if you have GitHub)
   - "Continue with GitLab"
   - "Continue with Bitbucket"
   - "Continue with Email"

5. If you have a GitHub account (recommended path):
   a. Click "Continue with GitHub"
   b. GitHub will ask you to authorize Vercel. Click "Authorize Vercel"
   c. Wait for the page to load. You should see the Vercel dashboard.

6. If you do NOT have a GitHub account:
   a. Click "Continue with Email"
   b. Enter your email address
   c. Check your inbox for a verification email from Vercel
   d. Click the verification link in the email
   e. You should now see the Vercel dashboard

7. The dashboard will either say "Welcome to Vercel" or show a list of
   projects (which will be empty if you are brand new).

   If you see the dashboard, your account is ready. Move on to Step 3.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3: CREATE AN API TOKEN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

An API token is like a password that lets your AI agent deploy websites
to Vercel on your behalf.

8. Go to: https://vercel.com/account/tokens
   (You can also get here by clicking your profile picture in the top
   right, then "Settings", then "Tokens" in the sidebar.)

9. You should see a page with a "Create" or "Create Token" button.
   Click it.

10. Fill in these settings:
    - Token Name: Type "OpenClaw Agent"
    - Scope: Select "Full Account"
    - Expiration: Select "No Expiration" (or choose a time limit if
      you prefer more security)

11. Click "Create Token".

12. IMPORTANT: The token will only be shown ONCE! It looks like a long
    string of random letters and numbers (about 24 characters), like:
    oEYwm7BpJVvtywdi6F6B5ymr

13. Copy the token immediately and paste it somewhere safe, or give it
    directly to your AI agent.

    If you accidentally close the page without copying the token, go back
    to the tokens page, delete that token, and create a new one.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4: STORE THE TOKEN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The AI agent should store the token in the following places:

14. Save to secrets.env file:
    Add this line:
    VERCEL_TOKEN=paste-your-token-here

15. Update AGENTS.md - add this section:
    ## Vercel
    - Token stored in secrets.env as VERCEL_TOKEN
    - Used for: Website deployments, hosting, serverless functions
    - Dashboard: https://vercel.com/dashboard

16. Update TOOLS.md - add this section:
    ## Vercel CLI and API
    - Token: $VERCEL_TOKEN (in secrets.env)
    - CLI: vercel (install with: npm i -g vercel)
    - API Base: https://api.vercel.com
    - Deploy: vercel --prod
    - List projects: vercel ls

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5: INSTALL THE VERCEL CLI (OPTIONAL BUT RECOMMENDED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The Vercel CLI (Command Line Interface) lets your AI agent deploy websites
from the terminal.

17. Open your terminal.

18. Type this command and press Enter:

    npm i -g vercel

    This installs the Vercel command line tool. You only need to do this
    once. If you see permission errors, try:

    sudo npm i -g vercel

19. After installation, verify it worked:

    vercel --version

    You should see a version number like "vercel 35.x.x" or similar.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 6: VERIFY EVERYTHING WORKS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Let's make sure your Vercel setup is working correctly.

20. In your terminal, type this command and press Enter:

    curl -s -H "Authorization: Bearer $VERCEL_TOKEN" \
      "https://api.vercel.com/v2/user" | jq '.user.username'

    You should see your Vercel username printed out (for example:
    "johndoe" or "mycompany").

    If you see an error, double check that:
    - Your token was saved correctly in secrets.env
    - You copied the full token (no missing characters)
    - The token has not been deleted from Vercel

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SETUP CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before telling the user that setup is complete, verify ALL of these:

[ ] Vercel account created (or confirmed existing)
[ ] API token created with Full Account scope
[ ] Token saved to secrets.env as VERCEL_TOKEN
[ ] AGENTS.md updated with Vercel section
[ ] TOOLS.md updated with Vercel section
[ ] Vercel CLI installed (optional but recommended)
[ ] Verification test passed - can see username via API

DO NOT tell the user setup is complete until the verification test passes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT THE USER CAN DO AFTER SETUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Once Vercel is set up, the AI agent can help with:
- Deploying websites to Vercel (making them live on the internet)
- Creating new projects
- Managing custom domains (like www.yourbusiness.com)
- Setting environment variables (configuration for websites)
- Preview deployments (testing a website before it goes live)

Tell the user:
"Your Vercel is all set up! I can now deploy websites for you anytime.
Just ask me to build or deploy something and I will handle it."
