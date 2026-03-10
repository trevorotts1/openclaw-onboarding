## 🔴 API-ONLY EXECUTION LOCK (SOVEREIGN)
- During onboarding, do NOT use the Vercel CLI for setup/auth.
- Treat any legacy CLI examples below as historical reference only, not the install path.
- Use browser-based token creation and API verification from INSTALL.md.


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
VERCEL - HOW TO USE IT (DAILY USAGE GUIDE)
══════════════════════════════════════════════════════════════════

This document explains how to use Vercel day to day. Vercel is where your
AI agent deploys (publishes) websites so they are live on the internet.
If you have not set up Vercel yet, go to INSTALL.md first.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEPLOYING A WEBSITE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The most common thing you will do with Vercel is deploy a website. This
means taking website files from your computer and putting them on the
internet where anyone can visit them.

Using the Vercel API / dashboard flow during onboarding:

1. Navigate to the folder containing your website files:
   cd /path/to/your/website/folder

2. Deploy to production (makes it live):
   vercel --prod

3. Deploy a preview (for testing before going live):
   vercel

   A preview deployment gives you a temporary URL to test the site
   before making it official.

Using the API:

The AI agent can also deploy using the Vercel API directly:
  POST https://api.vercel.com/v13/deployments

This is more advanced and is typically handled by the AI agent behind
the scenes. You do not need to worry about API calls - just tell your
agent "deploy my website" and it will handle the rest.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMON VERCEL CLI COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Here are the commands your AI agent uses most often:

  vercel                    Deploy a preview (for testing)
  vercel --prod             Deploy to production (make it live)
  vercel ls                 List all your projects
  vercel env add VAR_NAME   Add an environment variable to a project
  vercel domains ls         List all domains connected to your projects

Your AI agent runs these commands for you. You just need to tell it
what you want, like "deploy my website" or "show me my projects."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USEFUL API ENDPOINTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

These are the API endpoints the AI agent can use:

| What It Does          | Method | URL                               |
|-----------------------|--------|-----------------------------------|
| List your projects    | GET    | https://api.vercel.com/v9/projects|
| Create a deployment   | POST   | https://api.vercel.com/v13/deployments |
| Get your user info    | GET    | https://api.vercel.com/v2/user    |

All API requests need this header:
  Authorization: Bearer YOUR_VERCEL_TOKEN

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT VERCEL CAN HOST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Vercel can host many types of websites and web applications:

- Simple HTML websites (just HTML, CSS, and JavaScript files)
- React applications
- Next.js applications (Vercel's own framework - works best)
- Vue.js applications
- Any static website (files that do not change)
- Serverless functions (small pieces of code that run on demand)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANAGING CUSTOM DOMAINS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

By default, Vercel gives your website a URL like:
  your-project.vercel.app

If you want a custom domain (like www.yourbusiness.com), you can connect
it through Vercel. Your AI agent can help set this up.

The basic process:
1. Add the domain in Vercel project settings
2. Update your domain's DNS records to point to Vercel
3. Vercel automatically provides HTTPS (the secure padlock in the browser)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ENVIRONMENT VARIABLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Environment variables are settings that your website needs to run, like
API keys or database connections. Instead of putting these directly in
your code (which is not safe), you store them in Vercel.

To add one:
  vercel env add MY_VARIABLE_NAME

Or through the Vercel dashboard:
1. Go to https://vercel.com/dashboard
2. Click on your project
3. Go to Settings
4. Click "Environment Variables"
5. Add your variable name and value

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIPS FOR DAY-TO-DAY USE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Always deploy a preview first to test, then deploy to production when
  you are happy with it.
- If something goes wrong with a deployment, Vercel keeps all previous
  versions. You can roll back to an earlier version from the dashboard.
- Vercel's free tier is generous. For most personal and small business
  sites, you will not need to pay anything.
- If you connected GitHub, pushing code to your GitHub repository will
  automatically deploy to Vercel. This is very convenient.
