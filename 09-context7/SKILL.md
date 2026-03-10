---
name: context7
description: >
  Setup for Context7 - a real-time documentation lookup tool that lets your AI
  agent pull current library and API docs instead of guessing from old training data.
metadata:
  
  version: "1.0"
  priority: HIGH
  install_method: "api"
---

## 🔴 API-ONLY EXECUTION LOCK (SOVEREIGN)
- For this onboarding package, do NOT use service CLIs for GitHub, Vercel, or Context7.
- Do NOT use `gh`, `vercel`, or any Context7 CLI command for setup/auth.
- Use API-driven setup and browser-based account/token creation flows only.
- The only onboarding skill allowed to rely on CLI-specific service commands is Superdesign.

# Context7 Setup

Context7 is a service that gives your AI agent access to up-to-date documentation
for programming libraries, frameworks, and APIs. Without it, the agent relies on
its training data, which may be months or years out of date. With Context7, the
agent can look up the current docs before writing code - so the code actually works.

## When to Use This Skill

- You are setting up a new OpenClaw installation and need the agent to write accurate code
- The agent keeps producing outdated code for libraries like n8n, React, or GoHighLevel
- You want the agent to check real documentation before building anything
- Someone says "set up Context7" or "install Context7"

## What This Skill Covers

1. Checking if the user already has a Context7 account
2. Executing account creation at context7.com (step by step)
3. Creating an API key (starts with "ctx7sk-")
4. Storing the key securely in secrets.env
5. Adding short references to AGENTS.md, TOOLS.md, and MEMORY.md
6. Testing that the key works with a quick API call
7. How the agent should use Context7 going forward (search first, then code)

## Files in This Folder

Read them in this order:

1. **SKILL.md** - You are here. Overview and trigger conditions.
2. **context7-full.md** - The complete walkthrough with every step, exact commands,
   and what to say to the user at each point. This is the file you execute from.
3. **INSTRUCTIONS.md** - Additional setup instructions if needed.
4. **INSTALL.md** - Installation-specific notes.
5. **EXAMPLES.md** - Example usage patterns.
6. **CORE_UPDATES.md** - What to add to your core .md files (AGENTS.md, TOOLS.md, MEMORY.md).
7. **context7.skill** - Skill definition file.

## Prerequisites

- The Teach Yourself Protocol (TYP) must be installed first. If you have not learned
  TYP yet, stop and Request from user teach it to you before proceeding.
- The Backup Protocol should also be in place.

## Key Things the AI Agent Needs to Know

- Context7 is an API service, not a local tool. It needs an internet connection.
- The API key format is: ctx7sk-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
- Two main API calls: search for a library, then fetch its documentation.
- The agent should use Context7 BEFORE writing code for any external library or API.
  This is the whole point - check the current docs, then write code based on what
  you find. Do not guess from training data.
- The full document follows TYP rules: save the deep file to the master files folder,
  only add short summaries to core .md files. Do not dump the full content into
  AGENTS.md or TOOLS.md.
- Popular libraries available include: n8n, GoHighLevel, React, Next.js, and many more.
- Free tier has usage limits. The key is tied to the user's Context7 account.

## How to Execute This Skill

1. Read context7-full.md completely before doing anything.
2. Follow the TYP file storage rules (deep file in master folder, summaries in core files).
3. Execute each step conversationally - ask, tell, verify.
4. Do not skip the verification step at the end.
