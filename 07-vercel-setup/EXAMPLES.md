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

══════════════════════════════════════════════════════════════════
VERCEL - REAL EXAMPLES
══════════════════════════════════════════════════════════════════

These examples show real interactions between a user and their AI agent,
plus actual commands and expected output.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 1: SETTING UP VERCEL FOR THE FIRST TIME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This is a sample conversation between a user and the AI agent:

USER: "I need to set up Vercel."

AI: "Do you already have a Vercel account? (yes/no)"

USER: "No."

AI: "Let's create your Vercel account. Go to https://vercel.com and click
'Sign Up' in the top right corner. Do you have a GitHub account?"

USER: "Yes."

AI: "Perfect! Click 'Continue with GitHub' - this is the easiest option
because it lets Vercel automatically deploy from your GitHub repositories
later. Click 'Authorize Vercel' when GitHub asks for permission. Let me
know when you see the Vercel dashboard."

USER: "I can see the dashboard."

AI: "Now let's create an API token so I can help you deploy websites.
Go to: https://vercel.com/account/tokens"

USER: "I'm there."

AI: "Click 'Create' and fill in these settings:
  - Token Name: Type 'OpenClaw Agent'
  - Scope: Select 'Full Account'
  - Expiration: Select 'No Expiration'
Then click 'Create Token'. IMPORTANT: The token will only be shown ONCE!
Copy it immediately and paste it here."

USER: "oEYwm7BpJVvtywdi6F6B5ymr"

AI: "I've saved your Vercel token securely. Let me run a quick test..."
[AI runs verification command]
AI: "Your Vercel is set up and working. I can see your account. I can now
help you deploy websites, create projects, and manage domains anytime!"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 2: DEPLOYING A WEBSITE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USER: "Deploy this website I just built."

What the AI agent does behind the scenes:

Step 1: Navigate to the project folder
  cd ~/projects/my-website

Step 2: Deploy a preview first
  vercel

Expected output:
  Vercel CLI 35.0.0
  ? Set up and deploy "~/projects/my-website"? [Y/n] y
  ...
  Preview: https://my-website-abc123.vercel.app

Step 3: Tell the user
  AI: "I deployed a preview version. You can see it at:
  https://my-website-abc123.vercel.app
  Take a look and let me know if everything looks good. If so, I'll
  push it to production."

USER: "Looks great, make it live."

Step 4: Deploy to production
  vercel --prod

Expected output:
  Production: https://my-website.vercel.app

AI: "Done! Your website is now live at https://my-website.vercel.app"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 3: CHECKING YOUR VERCEL ACCOUNT INFO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Command:
curl -s -H "Authorization: Bearer $VERCEL_TOKEN" \
  "https://api.vercel.com/v2/user" | jq '.user.username'

Expected output:
"your-username"

This confirms your token is working and shows your Vercel username.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 4: LISTING YOUR PROJECTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Using the CLI:
  vercel ls

Expected output:
  > 3 projects found
  my-portfolio          Production  https://my-portfolio.vercel.app
  client-website        Production  https://client-website.vercel.app
  test-project          Preview     https://test-project-abc123.vercel.app

Using the API:
  curl -s -H "Authorization: Bearer $VERCEL_TOKEN" \
    "https://api.vercel.com/v9/projects" | jq '.projects[].name'

Expected output:
  "my-portfolio"
  "client-website"
  "test-project"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 5: ADDING AN ENVIRONMENT VARIABLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USER: "Add my API key to the website project."

What the AI agent does:

  vercel env add MY_API_KEY

The CLI will ask:
  ? What's the value of MY_API_KEY? [input is hidden]

Type or paste the value and press Enter.

  ? Add MY_API_KEY to which Environments? (select with space)
  ◉ Production
  ◉ Preview
  ◉ Development

Select all three and press Enter.

The environment variable is now available to your website.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 6: BACKING UP A WEBSITE TO GITHUB AND AUTO-DEPLOYING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If Vercel was connected to GitHub during setup, this is automatic:

1. AI agent pushes code to GitHub:
   git add .
   git commit -m "Update homepage design"
   git push

2. Vercel detects the push and automatically deploys.

3. The user's live website is updated within a minute or two.

This is the ideal workflow - the user never has to think about deploying.
They just tell the AI to make changes, and the changes go live automatically.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMON TROUBLESHOOTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROBLEM: "vercel: command not found"
SOLUTION: Install the CLI with: npm i -g vercel

PROBLEM: Token verification returns an error
SOLUTION: Make sure $VERCEL_TOKEN is set in your environment. Try:
  echo $VERCEL_TOKEN
If it is blank, the token was not saved correctly. Re-add it to secrets.env.

PROBLEM: Deployment fails with "404"
SOLUTION: Make sure you are in the correct project folder before running
vercel. The folder should contain your website files (index.html, or a
package.json for React/Next.js projects).
