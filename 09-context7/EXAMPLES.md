
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

══════════════════════════════════════════════════════════════════
CONTEXT7 - REAL EXAMPLES
══════════════════════════════════════════════════════════════════

These examples show how Context7 works in practice - what the AI agent
does behind the scenes when you ask it to write code.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 1: SETTING UP CONTEXT7 FOR THE FIRST TIME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This is a sample conversation between a user and the AI agent:

USER: "Let's set up Context7."

AI: "Do you already have a Context7 account? (yes/no)"

USER: "No."

AI: "Let's set up Context7 so I can look up current documentation for you.
Go to https://context7.com and click 'Get Started' or 'Sign Up'. Do you
have a GitHub account?"

USER: "Yes."

AI: "Click 'Continue with GitHub' and authorize the app. Let me know when
you are logged in and can see the dashboard."

USER: "I'm in."

AI: "Now look for 'API Keys' in the sidebar or settings menu. Click
'Create API Key', name it 'OpenClaw Agent', and click Create. Copy the
key and paste it here. It starts with 'ctx7sk-'"

USER: "ctx7sk-abc12345-def6-7890-ghij-klmnopqrstuv"

AI: "I have saved your Context7 key. Let me test it..."
[AI runs test search]
AI: "Context7 is working! From now on, whenever you ask me to build
something with an external library, I will check the current docs first
instead of guessing from memory."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 2: AI LOOKING UP N8N DOCUMENTATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

What happens behind the scenes when the user asks:
"Build me an n8n workflow that sends emails from a spreadsheet."

Step 1: AI searches Context7 for n8n documentation

curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY" \
  "https://api.context7.com/v1/search?q=n8n"

Expected response (simplified):
{
  "results": [
    {
      "id": "n8n-io/n8n-docs",
      "name": "n8n Documentation",
      "description": "Workflow automation documentation"
    }
  ]
}

Step 2: AI fetches the actual documentation

curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY" \
  "https://api.context7.com/v1/libraries/n8n-io/n8n-docs/context"

Expected response: Current n8n documentation content that the AI can
read and use to write the correct workflow code.

Step 3: AI writes the workflow using current documentation

The AI now knows the exact current node types, parameter names, and
API formats for n8n, so the workflow code is correct.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 3: AI LOOKING UP REACT DOCUMENTATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

What happens when the user asks:
"Build me a React component that shows a filterable list."

Step 1: Search for React

curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY" \
  "https://api.context7.com/v1/search?q=react"

Expected response (simplified):
{
  "results": [
    {
      "id": "facebook/react",
      "name": "React",
      "description": "JavaScript library for building user interfaces"
    }
  ]
}

Step 2: Get React documentation

curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY" \
  "https://api.context7.com/v1/libraries/facebook/react/context"

Step 3: Write the component using current React best practices

Without Context7, the AI might use older patterns (like class components).
With Context7, it knows to use current hooks and patterns.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 4: AI LOOKING UP GOHIGHLEVEL DOCUMENTATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

What happens when the user asks:
"Write code to create a contact in GoHighLevel."

Step 1: Search

curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY" \
  "https://api.context7.com/v1/search?q=gohighlevel"

Step 2: Get documentation

curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY" \
  "https://api.context7.com/v1/libraries/websites/marketplace_gohighlevel/context"

Step 3: Write correct API calls

The AI now has the current GHL API endpoints, required headers, and
parameter formats, so the integration code works on the first try.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 5: TESTING CONTEXT7 AFTER SETUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

After setup, you can verify Context7 is working with this test:

curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY" \
  "https://api.context7.com/v1/search?q=react" | jq '.results[0].name'

Expected output:
"React"

If you see an error instead:
- 401 error: Your API key is wrong. Check that it starts with "ctx7sk-"
- Connection error: Check your internet connection
- Empty response: Try a different search term

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 6: BEFORE AND AFTER CONTEXT7
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BEFORE Context7 (AI guessing from old training data):

USER: "Create an n8n workflow node for sending Slack messages."

AI writes code using an old node type that was renamed 6 months ago.
The workflow fails. User has to debug and fix it manually.

AFTER Context7 (AI checking current documentation first):

USER: "Create an n8n workflow node for sending Slack messages."

AI checks Context7, sees the current node type and parameters.
AI writes code using the correct, current node configuration.
The workflow works the first time.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 7: WHAT THE USER SEES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

From the user's perspective, they do not see Context7 working at all.
They just ask their AI to build something, and the code works.

USER: "Build me a Next.js page with a contact form."

AI (internally): Checks Context7 for Next.js docs. Gets current routing
and form handling patterns. Writes the code.

AI (to user): "Here is your contact form page. It uses Next.js App Router
with server actions for form handling. I checked the current Next.js docs
to make sure everything is up to date."

The user gets working code. They do not need to know or care that
Context7 was involved. It is invisible infrastructure that makes the
AI's work better.
