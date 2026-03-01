
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
🧠 CONTEXT7 SETUP - AI WALKTHROUGH INSTRUCTIONS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PURPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This document tells YOU (the AI) how to guide your human through setting up Context7.
Context7 gives you access to real-time API documentation so you don't hallucinate 
outdated code. You will ASK questions, TELL them what to do, and VERIFY each step.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHY THIS MATTERS (Explain to human if they ask)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Without Context7: You might give them outdated code that doesn't work anymore.
With Context7: You can fetch current documentation before writing code.

Example: If they ask you to build an n8n workflow, you can pull the latest n8n 
docs instead of relying on your training data (which might be outdated).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: CHECK IF THEY HAVE CONTEXT7
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ASK THE HUMAN:
"Do you already have a Context7 account? (yes/no)"

IF YES:
  → Ask: "Do you have your Context7 API key? It starts with 'ctx7sk-'"
  → If they have it: Skip to STEP 4 (Store the Key)
  → If they don't have it: Go to STEP 3 (Create API Key)

IF NO:
  → Proceed to STEP 2

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2: GUIDE ACCOUNT CREATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TELL THE HUMAN:
"Let's set up Context7 so I can look up current documentation for you. 
Go to https://context7.com"

ASK:
"Do you see a 'Get Started' or 'Sign Up' button?"

WHEN THEY CONFIRM:
TELL THEM:
"Click it and sign up. You can use GitHub (easiest) or email."

ASK:
"Which method would you like to use - GitHub or email?"

IF GITHUB:
  TELL THEM: "Click 'Continue with GitHub' and authorize the app. Let me know 
  when you're logged in and can see the dashboard."

IF EMAIL:
  TELL THEM: "Enter your email and create a password. Check your inbox for a 
  verification email. Let me know when you're logged in."

VERIFY COMPLETION:
  ASK: "Are you logged into Context7 and can see the dashboard?"
  → If yes: Proceed to STEP 3
  → If no: Troubleshoot

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3: CREATE THE API KEY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TELL THE HUMAN:
"Now let's create an API key. Look for 'API Keys' in the sidebar or settings menu."

ASK:
"Can you find the API Keys section?"

WHEN THEY FIND IT:
TELL THEM:
"Click 'Create API Key' or 'New Key'. 
Give it a name like 'OpenClaw Agent' so you know what it's for.
Then click Create."

CRITICAL - TELL THEM:
"Copy the API key and paste it here. It looks like: ctx7sk-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

WAIT FOR KEY:
  → When they provide the key, verify it starts with "ctx7sk-"
  → If valid: Proceed to STEP 4
  → If invalid: Ask them to try again or check what they copied

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4: STORE THE API KEY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WHEN YOU RECEIVE THE KEY:

1. Save to secrets.env:
   Add this line: CONTEXT7_API_KEY=<their_key>

2. Update AGENTS.md - add this section:
   ## Context7 - Real-Time Documentation
   - API Key stored in secrets.env as CONTEXT7_API_KEY
   - ALWAYS use before writing code for external APIs
   - Prevents outdated/hallucinated code
   - Key libraries: n8n, GHL, React, Node.js, Python packages

3. Update TOOLS.md - add this section:
   ## Context7 - Documentation Lookup
   - API Key: $CONTEXT7_API_KEY (in secrets.env)
   - Use BEFORE coding with any external library
   - Search: GET https://api.context7.com/v1/search?q=<library>
   - Get docs: GET https://api.context7.com/v1/libraries/<id>/context

4. Update MEMORY.md - add this reminder:
   ## Context7 Rule
   Before writing code for ANY external library or API, use Context7 first.
   Never rely on training data alone - documentation changes constantly.

TELL THE HUMAN:
"I've saved your Context7 key. This helps me give you accurate, up-to-date code. 
Whenever you ask me to build something with an external library (like n8n, 
GoHighLevel, React, etc.), I'll check the current docs first instead of guessing."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5: VERIFY IT WORKS (OPTIONAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ASK THE HUMAN:
"Want me to run a quick test to make sure Context7 is working?"

IF YES:
  Run a test search:
  curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY"     "https://api.context7.com/v1/search?q=react" | jq '.results[0].name'
  
  IF IT WORKS:
    TELL THEM: "Context7 is working! I can now look up real-time documentation."
  
  IF IT FAILS:
    Troubleshoot - check if the key is correct

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO USE CONTEXT7 (Reference for AI)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When the human asks you to write code for an external library:

1. FIRST: Search Context7 for that library
   curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY"      "https://api.context7.com/v1/search?q=<library_name>"

2. THEN: Get the documentation context
   curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY"      "https://api.context7.com/v1/libraries/<library_id>/context"

3. FINALLY: Write code based on the CURRENT documentation

Key libraries available:
  - n8n: n8n-io/n8n-docs
  - GoHighLevel: websites/marketplace_gohighlevel
  - React: facebook/react
  - Next.js: vercel/next.js
  - Many more...

REMEMBER: Always check Context7 BEFORE writing code for external APIs.
Your training data may be outdated - Context7 has the current docs.


