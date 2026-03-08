---
name: vercel-setup
description: >
  How to set up Vercel for deploying websites. This is an AI-guided walkthrough
  where the agent asks the human questions and Executes creating an
  account, getting an API token, and verifying everything works.
metadata:
  author: Trevor Otts, BlackCEO
  version: "1.0"
  priority: STANDARD
---

## 🔴 API-ONLY EXECUTION LOCK (SOVEREIGN)
- For this onboarding package, do NOT use service CLIs for GitHub, Vercel, or Context7.
- Do NOT use `gh`, `vercel`, or any Context7 CLI command for setup/auth.
- Use API-driven setup and browser-based account/token creation flows only.
- The only onboarding skill allowed to rely on CLI-specific service commands is Superdesign.

# Vercel Setup

Vercel is a platform for putting websites on the internet. When you build a
website (HTML, React, Next.js, or anything else), Vercel hosts it for you and
gives it a real web address that anyone can visit. It handles all the technical
server stuff so you do not have to.

This skill is different from most others. Instead of the AI doing everything
automatically, this one is a guided conversation. The AI walks the human through
each step, asks them questions, waits for their answers, and only moves forward
when each step is confirmed complete.

## When to Use This Skill

- The user asks you to set up Vercel
- The user wants to deploy a website or web app to the internet
- The user needs a hosting platform for a project
- You need a Vercel API token to deploy something and one has not been set up
- The user mentions Vercel, website deployment, or hosting

## Prerequisites

- Teach Yourself Protocol (TYP) must be learned first (skill 01)
- Backup Protocol must be learned first (skill 02)
- Node.js must be installed on the machine (for the Vercel CLI)
- The human needs a web browser to create their Vercel account
- A GitHub account is recommended (makes setup easier) but not required

## What This Skill Covers

1. **Checking for existing account** - Ask if they already have Vercel. If yes,
   skip account creation and go straight to the API token step.
2. **Account creation** - Execute signing up at vercel.com. The
   recommended path is "Continue with GitHub" because it connects their code
   repositories automatically. Email signup is also supported.
3. **API token creation** - Guide them to vercel.com/account/tokens, have them
   create a token named "OpenClaw Agent" with Full Account scope and no
   expiration. The token only shows once, so they must copy it right away.
4. **Storing the token** - Save the token to the secrets file as VERCEL_TOKEN
   and add references to AGENTS.md and TOOLS.md.
5. **Verification test** - Run a quick API call to confirm the token works and
   show the user their Vercel username as proof.
6. **What Vercel can do** - After setup, the AI can deploy websites, create
   projects, manage custom domains, set environment variables, and create
   preview deployments for testing.

## Files in This Folder (Reading Order)

1. **SKILL.md** - You are here. Start with this file.
2. **vercel-setup-full.md** - The complete walkthrough script with exact
   wording for every question and instruction to give the human, plus the
   commands and API calls to use after setup is complete.
3. **INSTRUCTIONS.md** - Additional operational instructions.
4. **INSTALL.md** - Steps for installing the Vercel CLI (npm i -g vercel).
5. **EXAMPLES.md** - Example deployments and common use cases.
6. **CORE_UPDATES.md** - What to add to AGENTS.md, TOOLS.md, and MEMORY.md.

## Critical Things to Know

- **This is a conversation, not automation.** You ask the human questions and
  wait for their answers. Do not try to automate account creation or skip
  steps. Execute it one step at a time.
- **The API token only shows once.** If they close the page before copying it,
  they need to delete that token and create a new one. Warn them clearly
  before they click Create Token.
- **Token goes in secrets.** Store as VERCEL_TOKEN in the secrets env file.
  Never put it in AGENTS.md or any file that is not meant for secrets.
- **Verify before declaring done.** Run the curl test to confirm the token
  actually works. Do not tell the user setup is complete until you have proof.
- **Common Vercel commands after setup:**
  - `vercel` - Deploy interactively (asks questions about the project)
  - `vercel --prod` - Deploy to production
  - `vercel ls` - List all projects
  - `vercel env add VAR_NAME` - Add an environment variable
- **API base URL:** https://api.vercel.com
- **Vercel is free for personal projects.** The free tier includes plenty of
  bandwidth and deployments for most use cases. Paid plans exist for teams
  and higher traffic, but most users will not need them right away.
