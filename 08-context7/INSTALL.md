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
CONTEXT7 SETUP - INSTALLATION GUIDE
══════════════════════════════════════════════════════════════════

This guide walks you through creating a Context7 account, getting your API
key, and connecting Context7 to your OpenClaw setup.

What is Context7? It is a service that gives your AI agent access to
up-to-date documentation for software libraries and APIs. Without it,
your AI might write code based on old information that no longer works.
With Context7, the AI can check the latest documentation before writing
code, so the code is accurate and current.

Think of it like this: Instead of your AI guessing how a tool works based
on what it learned months ago, it can look up the current instructions
right before it writes code for you.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: CHECK IF YOU ALREADY HAVE CONTEXT7
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before creating a new account, the AI should ask:

"Do you already have a Context7 account? (yes/no)"

If YES:
  - Ask: "Do you have your Context7 API key? It starts with 'ctx7sk-'"
  - If they have it: Skip to Step 4 (Store the Key)
  - If they do not have it: Go to Step 3 (Create API Key)

If NO:
  - Proceed to Step 2

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2: CREATE YOUR CONTEXT7 ACCOUNT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Open your web browser (Chrome, Safari, Edge, or Firefox).

2. Go to: https://context7.com

3. Look for a "Get Started" or "Sign Up" button on the page.

4. Click it. You will see options to sign up:
   - "Continue with GitHub" (recommended if you have a GitHub account)
   - "Continue with Email"

5. If you use GitHub:
   a. Click "Continue with GitHub"
   b. Authorize the Context7 app when GitHub asks
   c. You should be logged in and see the Context7 dashboard

6. If you use email:
   a. Enter your email address and create a password
   b. Check your inbox for a verification email from Context7
   c. Click the verification link
   d. Log in to Context7

7. You should now see the Context7 dashboard. If so, move on to Step 3.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3: CREATE YOUR API KEY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

An API key lets your AI agent look up documentation from Context7.

8. From the Context7 dashboard, look for "API Keys" in the sidebar
   menu or in the settings area.

9. Click "Create API Key" or "New Key".

10. Give the key a name like "OpenClaw Agent" so you know what it is for.

11. Click "Create".

12. The API key will appear. It looks like:
    ctx7sk-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

    (It starts with "ctx7sk-" followed by a long string of letters,
    numbers, and hyphens.)

13. Copy this key immediately and paste it somewhere safe.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4: STORE THE API KEY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The AI agent should store the key in these places:

14. Save to secrets.env file:
    Add this line:
    CONTEXT7_API_KEY=paste-your-key-here

15. Update AGENTS.md - add this section:
    ## Context7 - Real-Time Documentation
    - API Key stored in secrets.env as CONTEXT7_API_KEY
    - ALWAYS use before writing code for external APIs
    - Prevents outdated or incorrect code
    - Key libraries: n8n, GHL, React, Node.js, Python packages

16. Update TOOLS.md - add this section:
    ## Context7 - Documentation Lookup
    - API Key: $CONTEXT7_API_KEY (in secrets.env)
    - Use BEFORE coding with any external library
    - Search: GET https://api.context7.com/v1/search?q=<library>
    - Get docs: GET https://api.context7.com/v1/libraries/<id>/context

17. Update MEMORY.md - add this reminder:
    ## Context7 Rule
    Before writing code for ANY external library or API, use Context7
    first. Never rely on training data alone.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5: VERIFY IT WORKS (OPTIONAL BUT RECOMMENDED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

18. In your terminal, type this command and press Enter:

    curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY" \
      "https://api.context7.com/v1/search?q=react" | jq '.results[0].name'

    You should see the name of a library (like "facebook/react") printed
    out. This means Context7 is working.

    If you see an error, check that:
    - The API key was saved correctly
    - The key starts with "ctx7sk-"
    - Your internet connection is working

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SETUP CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before telling the user that setup is complete, verify ALL of these:

[ ] Context7 account created (or confirmed existing)
[ ] API key generated (starts with ctx7sk-)
[ ] API key saved to secrets.env as CONTEXT7_API_KEY
[ ] AGENTS.md updated with Context7 section
[ ] TOOLS.md updated with Context7 section
[ ] MEMORY.md updated with Context7 reminder
[ ] Verification test passed (optional but recommended)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT THE USER CAN DO AFTER SETUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Once Context7 is set up, the AI agent will automatically use it when
writing code. The user does not need to do anything special.

Tell the user:
"I've saved your Context7 key. This helps me give you accurate, up-to-date
code. Whenever you ask me to build something with an external library
(like n8n, GoHighLevel, React, etc.), I will check the current docs first
instead of guessing from memory."
