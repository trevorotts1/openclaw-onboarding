---
name: github-setup
description: >
  Setup for GitHub and Git version control. Walks the user through creating a
  GitHub account, generating a Personal Access Token, configuring Git on their
  machine, and storing credentials securely.
metadata:
  author: Trevor Otts, BlackCEO
  version: "1.0"
  priority: HIGH
---

# GitHub and Git Setup

GitHub is where your code lives in the cloud. It keeps a backup of everything,
tracks every change you make, and lets you go back to any previous version if
something breaks. Git is the tool on your computer that talks to GitHub.

This skill walks the user through setting up both from scratch - even if they
have never used GitHub before.

## When to Use This Skill

- Setting up a new OpenClaw installation (GitHub is needed for backups and deployments)
- The user does not have a GitHub account yet
- The user has an account but no Personal Access Token (PAT) configured
- Git is not configured on the user's machine (no user.name or user.email set)
- Someone says "set up GitHub," "configure Git," or "I need version control"

## What This Skill Covers

1. Checking if the user already has a GitHub account
2. Walking them through account creation at github.com (step by step)
3. Creating a Personal Access Token (PAT) with full permissions
   - The token starts with "ghp_" and is about 40 characters long
   - It is only shown once, so the user must copy it immediately
4. Configuring Git on their machine (user.name, user.email, credential helper)
5. Storing the token and username securely in secrets.env
6. Adding short references to AGENTS.md and TOOLS.md
7. Verifying the setup works with a quick API test
8. Ongoing Git best practices (when to commit, what never to commit)

## Files in This Folder

Read them in this order:

1. **SKILL.md** - You are here. Overview and trigger conditions.
2. **github-setup-full.md** - The complete walkthrough with every step, exact
   commands, what to say to the user, and what to verify. This is the file
   you execute from.
3. **INSTRUCTIONS.md** - Additional setup instructions if needed.
4. **INSTALL.md** - Installation-specific notes.
5. **EXAMPLES.md** - Example usage patterns and common Git commands.
6. **CORE_UPDATES.md** - What to add to your core .md files.
7. **github-setup.skill** - Skill definition file.

## Prerequisites

- The Teach Yourself Protocol (TSP) must be installed first. If you have not
  learned TSP yet, stop and ask the user to teach it to you before proceeding.
- The Backup Protocol should be in place.

## Key Things the AI Agent Needs to Know

- The Personal Access Token (PAT) is the most important piece. Without it, the
  agent cannot interact with GitHub on the user's behalf.
- When creating the PAT, select ALL scopes (full permissions). This avoids
  having to create a new token later when you need a permission you skipped.
- Set expiration to "No expiration" so it does not suddenly stop working.
- The token is only shown ONCE after creation. If the user loses it, they must
  delete that token and create a new one. There is no way to see it again.
- Git config commands (user.name, user.email, credential.helper) only need to
  be run once per machine. They persist across sessions.
- NEVER commit secrets, API keys, .env files, or tokens to GitHub. These go
  in secrets.env which should be in .gitignore.
- The full document follows TSP rules: save the deep file to the master files
  folder, only add short summaries to core .md files.
- After setup, the agent should commit code regularly - after completing features,
  before risky changes, and at the end of every work session.

## How to Execute This Skill

1. Read github-setup-full.md completely before doing anything.
2. Follow the TSP file storage rules (deep file in master folder, summaries in core files).
3. Walk the user through each step conversationally - ask, tell, verify.
4. Do not skip the verification step at the end.
5. Make sure the user understands the token is shown only once and must be copied immediately.
