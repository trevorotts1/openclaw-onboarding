
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
GITHUB - REAL EXAMPLES
══════════════════════════════════════════════════════════════════

These examples show real interactions and commands for setting up and
using GitHub day to day.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 1: SETTING UP GITHUB FOR THE FIRST TIME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This is a sample conversation between a user and the AI agent:

USER: "I need to set up GitHub."

AI: "Do you already have a GitHub account? (yes/no)"

USER: "No."

AI: "Let's create your GitHub account. Go to https://github.com and click
'Sign up' in the top right corner. First, enter your email address."

USER: "I used trevor@example.com"

AI: "Now create a strong password. Done?"

USER: "Yes."

AI: "Choose a username. This will be visible publicly, so pick something
professional."

USER: "I chose blackceo-dev"

AI: "Complete the verification puzzle, then check your inbox for a
verification email from GitHub. Click the link to verify. Are you logged
in and can see the dashboard?"

USER: "Yes, I can see the dashboard."

AI: "Now we need to create a Personal Access Token. Go to:
https://github.com/settings/tokens
Click 'Generate new token' then 'Generate new token (classic)'.
For the Note, type 'OpenClaw Agent'. For Expiration, select 'No expiration'.
Then check ALL the scope boxes I am about to list..."

[AI walks through all the scope checkboxes]

AI: "Click 'Generate token' at the bottom. COPY THE TOKEN NOW - it will
only be shown once! It starts with 'ghp_' and is about 40 characters.
Paste it here."

USER: "ghp_1a2B3c4D5e6F7g8H9i0JkLmNoPqRsTuVwX"

AI: "I have saved your token. Let me configure Git and run a test..."

[AI runs git config commands and verification]

AI: "GitHub is all set up! I can see your account: blackceo-dev. I can now
back up your code, track changes, and deploy websites. Would you like me
to back up any projects right now?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 2: BACKING UP A PROJECT FOR THE FIRST TIME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USER: "Back up my website project."

What the AI agent does:

Step 1: Navigate to the project
  cd ~/projects/my-website

Step 2: Initialize Git
  git init

Expected output:
  Initialized empty Git repository in /Users/you/projects/my-website/.git/

Step 3: Add all files
  git add .

Step 4: Make the first commit
  git commit -m "Initial backup: my-website project"

Expected output:
  [main (root-commit) abc1234] Initial backup: my-website project
   15 files changed, 2340 insertions(+)

Step 5: Create a private repository on GitHub and push
  gh repo create my-website --private --source=. --push

Expected output:
  Created repository blackceo-dev/my-website on GitHub
  https://github.com/blackceo-dev/my-website
  Branch 'main' set up to track remote branch 'main'.

AI tells the user:
"Done! Your website is now backed up at:
https://github.com/blackceo-dev/my-website
It is private, so only you can see it. I will keep it updated whenever
we make changes."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 3: SAVING CHANGES AFTER EDITING A WEBSITE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

After the AI agent makes changes to a website, it automatically saves:

Step 1: Check what changed
  git status

Expected output:
  modified:   index.html
  modified:   styles.css
  new file:   contact.html

Step 2: Stage all changes
  git add .

Step 3: Commit with a descriptive message
  git commit -m "Feature: Added contact page and updated homepage styling"

Expected output:
  [main def5678] Feature: Added contact page and updated homepage styling
   3 files changed, 85 insertions(+), 12 deletions(-)

Step 4: Push to GitHub
  git push

Expected output:
  Enumerating objects: 7, done.
  To https://github.com/blackceo-dev/my-website.git
     abc1234..def5678  main -> main

The user does not see any of this - it happens automatically in the
background after the AI finishes making changes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 4: CHECKING YOUR GITHUB ACCOUNT VIA API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Command:
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/user" | jq '.login'

Expected output:
"blackceo-dev"

This confirms your token is working.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 5: LISTING YOUR REPOSITORIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Command:
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/user/repos" | jq '.[].name'

Expected output:
"my-website"
"client-portal"
"marketing-site"

This shows all the repositories (projects) in your GitHub account.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 6: ROLLING BACK A CHANGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USER: "The last change broke the website. Undo it."

What the AI agent does:

Step 1: See what the last commit was
  git log --oneline -5

Expected output:
  def5678 Feature: Added contact page
  abc1234 Fix: Updated navigation menu
  9876543 Initial backup

Step 2: Undo the last commit but keep the files
  git revert HEAD --no-edit

Step 3: Push the fix
  git push

AI tells the user:
"I have rolled back the last change. The website should be back to how
it was before. The change history is preserved so we can reference it
later if needed."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 7: SEEING RECENT CHANGES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USER: "What changes have been made to my website this week?"

What the AI agent does:

  git log --oneline --since="1 week ago"

Expected output:
  def5678 Feature: Added contact page and updated homepage styling
  abc1234 Fix: Contact form email validation was broken
  9876543 Docs: Updated footer with new business hours

AI tells the user:
"Here is what changed this week:
1. Added a contact page and updated the homepage styling
2. Fixed the contact form email validation
3. Updated the footer with new business hours"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMON TROUBLESHOOTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROBLEM: Token verification returns "Bad credentials"
SOLUTION: The token is wrong. Go to https://github.com/settings/tokens,
delete the old one, and create a new one. Make sure you copy the full
token (it starts with "ghp_").

PROBLEM: "Permission denied" when pushing
SOLUTION: Check that GITHUB_TOKEN is set in your environment. Also make
sure the token has the "repo" scope checked.

PROBLEM: "fatal: not a git repository"
SOLUTION: You need to run "git init" first in the project folder. This
is only needed once per project.

PROBLEM: "rejected - non-fast-forward"
SOLUTION: Someone else (or another computer) made changes. Run "git pull"
first to get those changes, then try "git push" again.
