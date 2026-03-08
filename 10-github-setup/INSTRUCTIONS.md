
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
GITHUB - HOW TO USE IT (DAILY USAGE GUIDE)
══════════════════════════════════════════════════════════════════

This document explains how to use GitHub day to day. It covers the main
things your AI agent does with GitHub: saving your work, tracking changes,
backing up projects, and deploying websites. If you have not set up GitHub
yet, go to INSTALL.md first.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW GITHUB WORKS (THE BIG PICTURE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GitHub stores your projects in "repositories" (often called "repos" for
short). A repository is like a folder that lives in the cloud. Every time
your AI agent saves work, it goes through three steps:

1. STAGE the changes (tell Git which files to save)
2. COMMIT the changes (save them with a description of what changed)
3. PUSH the changes (upload them to GitHub in the cloud)

This three-step process means every change is tracked. You can always see
what was changed, when, and why. And if something breaks, you can go back
to any previous version.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHEN THE AI AGENT SHOULD COMMIT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The AI agent should save (commit and push) your work at these times:

- After completing a feature or fixing a bug
- Before making risky changes (so you can undo them if needed)
- Before switching to a different task
- At the end of every work session
- After updating configuration files

This should happen automatically. You should not have to ask your AI
to save your work.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMON GIT COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

These are the commands your AI agent uses. You do not need to run them
yourself, but it helps to know what they do:

  git status
  Shows what files have been changed since the last save.

  git add .
  Prepares all changed files to be saved. The dot (.) means "everything."

  git commit -m "Description of what changed"
  Saves the changes with a message explaining what was done. For example:
  git commit -m "Fix: Updated homepage layout"
  git commit -m "Feature: Added contact form"

  git push
  Uploads the saved changes to GitHub (the cloud).

  git pull
  Downloads the latest changes from GitHub. This is important when
  working from multiple computers or with other people.

  git log --oneline -10
  Shows the last 10 saves (commits) with their messages. Useful for
  seeing what has been done recently.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMIT MESSAGE FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The AI agent should use clear commit messages that describe what changed:

  Fix: what was fixed
  Feature: what was added
  Docs: what documentation changed
  Refactor: what was restructured
  Chore: maintenance task

Examples:
  "Fix: Contact form email validation was broken"
  "Feature: Added customer testimonials section to homepage"
  "Docs: Updated README with setup instructions"
  "Chore: Updated dependencies to latest versions"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BACKING UP A PROJECT TO GITHUB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

To back up a project that is not yet on GitHub, the AI agent does this:

1. Navigate to the project folder:
   cd /path/to/your/project

2. Initialize Git (only needed once per project):
   git init

3. Add all files:
   git add .

4. Make the first commit:
   git commit -m "Initial backup"

5. Create a repository on GitHub and push:
   gh repo create project-name --private --source=. --push

   This creates a PRIVATE repository (only you can see it) on GitHub
   and uploads all your files. The "gh" command is the GitHub CLI tool.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KEEPING THINGS IN SYNC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The AI agent should follow these habits:

- Always pull before starting work: git pull
  (This gets the latest version in case changes were made elsewhere.)

- Always push after committing: git push
  (This sends your changes to the cloud so they are backed up.)

- Check status regularly: git status
  (This shows if there are unsaved changes.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GITHUB API ENDPOINTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The AI agent can also interact with GitHub through its API:

| What It Does           | Method | URL                                    |
|------------------------|--------|----------------------------------------|
| Get user info          | GET    | https://api.github.com/user            |
| List your repositories | GET    | https://api.github.com/user/repos      |
| Create a repository    | POST   | https://api.github.com/user/repos      |
| Get repository info    | GET    | https://api.github.com/repos/OWNER/REPO|
| See commit history     | GET    | https://api.github.com/repos/OWNER/REPO/commits |

All API requests need this header:
  Authorization: Bearer YOUR_GITHUB_TOKEN

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECURITY RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NEVER commit these things to GitHub:

- .env files that contain real passwords or API keys
- API tokens or secret keys of any kind
- Database passwords
- Private certificates
- The node_modules/ folder (it is too large and not needed)
- Large binary files (videos, large images, etc.)

The AI agent should use a .gitignore file to automatically exclude these.
If secrets are accidentally committed, they must be rotated (changed)
immediately because GitHub keeps a history of everything.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONNECTING GITHUB TO VERCEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If you also set up Vercel (see the Vercel setup skill), you can connect
your GitHub repositories to Vercel for automatic deployments. This means:

1. Your AI agent pushes code changes to GitHub
2. Vercel automatically detects the change
3. Vercel deploys the updated website within a minute or two
4. Your live website is updated without any extra steps

This is the ideal workflow. Changes go from your AI to the live website
automatically.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIPS FOR DAY-TO-DAY USE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Your AI agent handles all of this automatically. You do not need to
  run Git commands yourself.

- If you want to see your projects, go to https://github.com and log in.
  You will see all your repositories listed there.

- Each repository has a "commits" section where you can see every change
  that was made, when it was made, and what the description says.

- If something breaks, tell your AI "roll back to the previous version"
  and it can use Git to undo the last changes.

- GitHub's free plan is very generous. You can have unlimited private
  repositories. You do not need to pay for a plan unless you have very
  specific needs.
