
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
CONTEXT7 - HOW TO USE IT (DAILY USAGE GUIDE)
══════════════════════════════════════════════════════════════════

This document explains how your AI agent uses Context7 day to day.
If you have not set up Context7 yet, go to INSTALL.md first.

The good news: Once Context7 is set up, you (the human) do not need to do
anything special. Your AI agent uses it automatically behind the scenes
when writing code. This guide is mainly for the AI agent to understand
how to use Context7 properly.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHEN TO USE CONTEXT7
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The AI agent should use Context7 BEFORE writing code for any external
library or API. This includes:

- Building an n8n workflow
- Writing code that uses GoHighLevel APIs
- Creating a React or Next.js application
- Working with Python libraries
- Integrating with any third-party service
- Any time the AI is not 100% sure about the current API format

The rule is simple: If you are about to write code that calls someone
else's software, look up the current documentation first.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE TWO-STEP WORKFLOW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Using Context7 is a simple two-step process:

Step 1: SEARCH for the library you need documentation for

  curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY" \
    "https://api.context7.com/v1/search?q=LIBRARY_NAME"

  This returns a list of matching libraries with their IDs.

Step 2: GET the documentation for that specific library

  curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY" \
    "https://api.context7.com/v1/libraries/LIBRARY_ID/context"

  This returns the actual current documentation that the AI can read
  and use when writing code.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API ENDPOINTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| What It Does               | Method | URL                                          |
|----------------------------|--------|----------------------------------------------|
| Search for a library       | GET    | https://api.context7.com/v1/search?q=NAME    |
| Get library documentation  | GET    | https://api.context7.com/v1/libraries/ID/context |

All requests need this header:
  Authorization: Bearer YOUR_CONTEXT7_API_KEY

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POPULAR LIBRARIES AVAILABLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Context7 has documentation for thousands of libraries. Some common ones:

- n8n: n8n-io/n8n-docs (workflow automation)
- GoHighLevel: websites/marketplace_gohighlevel (CRM/marketing)
- React: facebook/react (web UI framework)
- Next.js: vercel/next.js (React framework for websites)
- Node.js: nodejs/node (JavaScript runtime)
- Python packages: Various
- And many, many more

To find a library, just search for it. If Context7 has it, the search
will return results.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BEST PRACTICES FOR AI AGENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ALWAYS check Context7 before writing code for external APIs.
   Your training data might be months old. APIs change frequently.

2. Do NOT skip this step because you "think you know" how the API works.
   Check anyway. It takes a few seconds and prevents bugs.

3. If Context7 does not have documentation for a specific library,
   fall back to your training data but tell the user:
   "I could not find current documentation for this library in Context7.
   I am using my best knowledge, but you may want to double-check the
   code against the official docs."

4. Cache documentation within a single session. If you already looked up
   React docs 5 minutes ago in the same conversation, you do not need
   to look them up again.

5. When the user asks "why did my code break," the first thing to check
   is whether the API has changed since the code was written. Context7
   can help with this.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHY THIS MATTERS TO THE USER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Without Context7, your AI might:
- Use an old API endpoint that no longer exists
- Write code with deprecated (outdated) functions
- Use the wrong parameter names for an API call
- Miss new features that have been added to a library

With Context7, your AI:
- Checks the CURRENT documentation before writing code
- Uses the correct, up-to-date API endpoints and parameters
- Takes advantage of new features in libraries
- Produces code that works the first time more often

The user does not need to know or care about Context7 in their daily
workflow. It just works in the background, making the AI's code better.
