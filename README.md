# OpenClaw Onboarding

**The complete skill package for setting up a fully operational OpenClaw AI assistant.**

14 skills. Installed in order. Each one teaches your AI agent how to use a different tool or service - from backing up your files to generating images to managing a team through Telegram.

---

## What Is This?

This is a collection of 14 skill packages designed for [OpenClaw](https://openclaw.ai), the open-source AI assistant platform. When you share these skills with your AI agent, it learns how to:

- Protect your configuration files with automatic backups
- Think through problems systematically before acting
- Connect to GoHighLevel (Convert and Flow) for CRM and messaging
- Deploy websites and landing pages automatically
- Generate images and videos using KIE.ai
- Deploy projects to Vercel
- Look up documentation for any software library
- Manage code repositories on GitHub
- Design professional websites and interfaces
- Configure AI models through OpenRouter
- Connect to Google Workspace (Gmail, Calendar, Drive, Docs, Sheets)
- Manage a multi-person team through Telegram

---

## How to Install

### Option 1: Download the ZIP (No GitHub Account Needed)

This is the easiest way. You do not need a GitHub account.

1. Click the green **Code** button at the top of this page
2. Click **Download ZIP**
3. Unzip the file on your computer
4. Move the unzipped folder to your Downloads folder and rename it to **OpenClaw Onboarding**

Or use the terminal:

```bash
curl -L https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip -o ~/Downloads/openclaw-onboarding.zip
unzip ~/Downloads/openclaw-onboarding.zip -d ~/Downloads/
mv ~/Downloads/openclaw-onboarding-main ~/Downloads/"OpenClaw Onboarding"
```

### Option 2: Clone with Git

If you already have Git set up:

```bash
cd ~/Downloads
git clone https://github.com/trevorotts1/openclaw-onboarding.git "OpenClaw Onboarding"
```

---

## How to Use

### Step 1: Start with "Start Here.md"

Open **Start Here.md** first. This is the master instruction file. It tells your AI agent:
- What to check before starting (prerequisites)
- The exact order to install skills
- How to read and process each skill folder
- What to do if something goes wrong

**Share this file with your AI agent and say:**
> "Read this file and follow it exactly. Start the onboarding process."

### Step 2: The AI Does the Rest

Your AI agent will:
1. Verify your OpenClaw installation is running
2. Check that your workspace files exist (AGENTS.md, TOOLS.md, etc.)
3. Find or create your master files folder
4. Install each skill one at a time, in order
5. Ask you for API keys or account credentials when needed
6. Update your workspace files with what it learned
7. Confirm each skill is working before moving to the next one

### Step 3: You Just Answer Questions

For most skills, the AI will walk you through the setup by asking simple questions:
- "Do you have a KIE.ai account?"
- "What is your API key?"
- "Do you have a GoHighLevel account?"

You answer. The AI handles the rest.

---

## The 14 Skills (Install Order)

These must be installed in this exact order. Each skill builds on the ones before it.

| # | Skill | What It Does |
|---|-------|-------------|
| 01 | **Teach Yourself Protocol** | Teaches the AI how to learn new skills without cluttering your files. This is the foundation - every other skill depends on it. |
| 02 | **Back Yourself Up Protocol** | Teaches the AI to back up your configuration before every change. Prevents disasters. |
| 03 | **Superpowers** | A thinking framework with 4 Iron Laws and 14 sub-skills for systematic problem-solving. |
| 04 | **GHL Setup** | Connects the AI to GoHighLevel (Convert and Flow) for CRM, contacts, messaging, and calendars. |
| 05 | **GHL Install Pages** | Teaches the AI to deploy websites and landing pages into GoHighLevel using browser automation. |
| 06 | **KIE Setup** | Connects the AI to KIE.ai for generating images, videos, and audio using dozens of AI models. |
| 07 | **Vercel Setup** | Connects the AI to Vercel for deploying websites and web applications. |
| 08 | **Context7** | Gives the AI access to up-to-date documentation for any software library. No more outdated answers. |
| 09 | **GitHub Setup** | Connects the AI to GitHub for code backup, version control, and repository management. |
| 10 | **SuperDesign** | Teaches the AI to design professional websites and interfaces before building them. |
| 11 | **OpenRouter Setup** | Configures multiple AI models (Claude, GPT, Gemini, etc.) with intelligent routing and cost management. |
| 12 | **Google Workspace Setup** | Creates the Google Cloud project, service account, and API connections for Gmail, Calendar, and Drive. |
| 13 | **Google Workspace Integration** | The deep technical guide for Google Workspace - 70+ permission scopes, 26 APIs, troubleshooting. |
| 14 | **BlackCEO Team Management** | Sets up multi-person team management through Telegram with message routing and worker agents. |

---

## What Is Inside Each Skill Folder

Every skill folder contains 7 files:

| File | Purpose |
|------|---------|
| **SKILL.md** | The front door. Read this first. Explains what the skill is, when to use it, and what files to read next. |
| **INSTALL.md** | Step-by-step installation and setup instructions. |
| **INSTRUCTIONS.md** | How to use the skill day to day after it is installed. |
| **EXAMPLES.md** | Real examples showing the skill in action with sample commands and expected output. |
| **CORE_UPDATES.md** | Exact text snippets to add to your workspace files (AGENTS.md, TOOLS.md, MEMORY.md). |
| **[skill-name]-full.md** | The complete reference document. Every detail, every edge case. This is the bible. |
| **[skill-name].skill** | A compressed package file for automated installation (optional). |

**Reading order for each skill:** SKILL.md first, then INSTALL.md, then INSTRUCTIONS.md, then EXAMPLES.md, then CORE_UPDATES.md. The full.md is for reference when deeper detail is needed.

---

## Requirements

Before you start, make sure you have:

- **OpenClaw installed and running** - Follow the [OpenClaw installation guide](https://docs.openclaw.ai) if you have not done this yet
- **A Telegram account** - OpenClaw communicates through Telegram (or other messaging platforms)
- **A computer running macOS or Linux** - OpenClaw runs on Mac and Linux natively, and on Windows through WSL2

### Accounts You Will Need (the AI will walk you through creating these)

Not all accounts are required. The AI will ask you about each one during the relevant skill installation.

| Service | Required? | Free Tier? | What It Is For |
|---------|-----------|------------|----------------|
| GoHighLevel | Optional | No (paid) | CRM, contacts, messaging, website hosting |
| KIE.ai | Recommended | Credit-based | AI image, video, and audio generation |
| Vercel | Optional | Yes | Website and app deployment |
| Context7 | Recommended | Yes | Software documentation lookup |
| GitHub | Recommended | Yes | Code backup and version control |
| OpenRouter | Recommended | Credit-based | Access to multiple AI models |
| Google Cloud | Recommended | Yes | Gmail, Calendar, Drive, Docs integration |

---

## Frequently Asked Questions

**Do I need to install all 14 skills?**
No. Skills 01 (Teach Yourself Protocol) and 02 (Backup Protocol) are required - they are the foundation. After that, install the skills that match the services you use. If you do not use GoHighLevel, skip skills 04 and 05. If you do not need video generation, skip skill 06.

**Can I install them out of order?**
No. The skills build on each other. Skill 01 must be first because every other skill uses the Teach Yourself Protocol to store its documentation properly. Skill 02 must be second because every configuration change after that requires a backup first.

**How long does the full onboarding take?**
About 1 to 2 hours if you are installing all 14 skills. Each skill takes 5 to 15 minutes depending on whether you need to create new accounts.

**What if something goes wrong?**
The Start Here.md file includes troubleshooting guidance. Your AI agent is also trained to handle errors - it will try multiple approaches before asking you for help.

**Can I share this with other people?**
Yes. This package is designed to work with any OpenClaw installation. Share the ZIP file or send them to this repository.

**Do I need to know how to code?**
No. The AI agent does all the technical work. You just answer questions and provide API keys when asked.

---

## Support

- **OpenClaw Documentation:** [docs.openclaw.ai](https://docs.openclaw.ai)
- **OpenClaw Community:** [Discord](https://discord.com/invite/clawd)
- **Issues with this package:** Open an issue on this repository

---

## Credits

Built by Trevor Otts and the BlackCEO team.

Powered by [OpenClaw](https://openclaw.ai) - the open-source AI assistant platform.
