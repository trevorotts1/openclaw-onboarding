
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
🚀 VERCEL SETUP - AI WALKTHROUGH INSTRUCTIONS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PURPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This document tells YOU (the AI) how to guide your human through setting up Vercel. 
You will ASK them questions, TELL them what to do, and VERIFY each step is complete 
before moving to the next one.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: CHECK IF THEY ALREADY HAVE VERCEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ASK THE HUMAN:
"Do you already have a Vercel account? (yes/no)"

IF YES:
  → Ask: "Are you currently logged into Vercel in your browser?"
  → If logged in: Skip to STEP 3 (API Key Creation)
  → If not logged in: Tell them to log in, then proceed to STEP 3

IF NO:
  → Proceed to STEP 2

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2: GUIDE ACCOUNT CREATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TELL THE HUMAN:
"Let's create your Vercel account. Go to https://vercel.com and click 'Sign Up' in the top right corner."

ASK THE HUMAN:
"Do you have a GitHub account? (yes/no)"

IF YES (RECOMMENDED PATH):
  TELL THEM:
  "Perfect! Click 'Continue with GitHub' - this is the easiest option because it lets 
  Vercel automatically deploy from your GitHub repositories later."
  
  THEN ASK:
  "Click 'Authorize Vercel' when GitHub asks for permission. Let me know when you see 
  the Vercel dashboard."

IF NO:
  TELL THEM:
  "No problem. Click 'Continue with Email' and enter your email address. You'll need 
  to verify it - check your inbox for a verification email from Vercel."
  
  THEN ASK:
  "Let me know when you've verified your email and can see the Vercel dashboard."

VERIFY COMPLETION:
  ASK: "Can you see the Vercel dashboard now? It should show 'Welcome to Vercel' or 
  a list of projects (which might be empty)."
  
  → If yes: Proceed to STEP 3
  → If no: Troubleshoot - ask what they see, help them through it

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3: CREATE THE API TOKEN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TELL THE HUMAN:
"Now let's create an API token so I can help you deploy websites. 
Go to: https://vercel.com/account/tokens"

ASK:
"Are you on the tokens page? You should see a button that says 'Create' or 'Create Token'."

WHEN THEY CONFIRM:
TELL THEM:
"Click 'Create' and fill in these settings:
  • Token Name: Type 'OpenClaw Agent'
  • Scope: Select 'Full Account'
  • Expiration: Select 'No Expiration' (or choose a time limit if you prefer)

Then click 'Create Token'."

CRITICAL - TELL THEM:
"⚠️ IMPORTANT: The token will only be shown ONCE! Copy it immediately and paste it 
here so I can save it for you. It looks like this: oEYwm7BpJVvtywdi6F6B5ymr"

WAIT FOR TOKEN:
  → When they provide the token, verify it looks correct (alphanumeric, ~24 characters)
  → If it looks like a token: Proceed to STEP 4
  → If they lost it: Tell them to delete that token and create a new one

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4: STORE THE TOKEN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WHEN YOU RECEIVE THE TOKEN:

1. Save to secrets.env:
   Add this line: VERCEL_TOKEN=<their_token>

2. Update AGENTS.md - add this section:
   ## Vercel
   - Token stored in secrets.env as VERCEL_TOKEN
   - Used for: Website deployments, hosting, serverless functions
   - Dashboard: https://vercel.com/dashboard

3. Update TOOLS.md - add this section:
   ## Vercel CLI & API
   - Token: $VERCEL_TOKEN (in secrets.env)
   - CLI: vercel (install with: npm i -g vercel)
   - API Base: https://api.vercel.com
   - Deploy: vercel --prod
   - List projects: vercel ls

TELL THE HUMAN:
"I've saved your Vercel token securely. You're all set up! I can now help you:
  • Deploy websites to Vercel
  • Create new projects
  • Manage domains
  • Set environment variables

Just ask me anytime you want to deploy something!"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5: VERIFY IT WORKS (OPTIONAL BUT RECOMMENDED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ASK THE HUMAN:
"Want me to run a quick test to make sure everything is working?"

IF YES:
  Run this command to verify the token:
  curl -s -H "Authorization: Bearer $VERCEL_TOKEN" "https://api.vercel.com/v2/user" | jq '.user.username'
  
  IF IT WORKS:
    TELL THEM: "Your Vercel is set up and working. I can see your account: [username]"
  
  IF IT FAILS:
    Troubleshoot - token might be wrong, ask them to double-check

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT YOU CAN DO WITH VERCEL (Reference for AI)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Once set up, use Vercel for:
• Deploying websites (HTML, React, Next.js, Vue, etc.)
• Hosting serverless API functions
• Managing custom domains
• Setting environment variables
• Preview deployments for testing

Common commands:
  vercel                    # Deploy (interactive)
  vercel --prod             # Deploy to production
  vercel ls                 # List projects
  vercel env add VAR_NAME   # Add environment variable

API endpoints:
  GET /v9/projects          # List projects
  POST /v13/deployments     # Create deployment
  GET /v2/user              # Get user info


