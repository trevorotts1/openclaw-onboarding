# AI Workforce Blueprint - Build Instructions

## The 3 Options

When you trigger this skill, you will see 3 options. Choose the one that fits your situation:

---

### Option A - Full Automated Build 🚀 (Recommended)

**Best for:** First-time setup, new businesses, or reorganizing

**What happens:**
1. I show you 17 pre-built departments you can choose from
2. You decide: Keep all / Keep some / Add custom / Start from scratch
3. I interview you about your business (with examples for each question)
4. I build all folders and files automatically based on your answers

**The 17 Recommended Departments:**

• marketing-dept - Content, ads, social media, email campaigns
• sales-dept - Converting leads to customers
• billing-dept - Invoicing, payments, financial tracking
• customer-support-dept - Helping existing clients
• operations-dept - Day-to-day business running
• creative-dept - Graphics, video, content creation
• graphics-dept - Static images, brand assets, AI image generation
• video-dept - AI video generation, editing, captions
• audio-dept - Full audio lifecycle: TTS, transcription, music, voice
• web-development-dept - Websites, funnels, landing pages
• app-development-dept - Software, mobile apps, APIs
• hr-people-dept - Team management, hiring
• legal-compliance-dept - Contracts, regulations
• it-tech-dept - Software, websites, infrastructure
• research-dept - Market research, competitive analysis
• comms-dept - Internal communications, announcements
• ceo-dept - Executive strategy, vision, high-level decisions
• master-orchestrator-dept - Routes all work (always included)

**Department Flexibility:**
"Here are the 17 departments we recommend for a complete AI workforce. You can keep all of them, remove any you do not need right now, or add new ones specific to your business. What would you like to adjust?"
- Default to keeping all 17 if the client has no preference

**Interview questions include:**
- What is your business name?
  - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."
- In one sentence, what does your business do?
  - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."
- What is your current team size?
  - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."
- What are the main tools your business uses?
  - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."
- What is your biggest challenge right now?
  - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."
- Do you have existing SOPs or training materials?
  - Fallback: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."

**System Discovery Question:**
- "What tools do you currently use to run your business? Examples: Stripe for payments, HubSpot or Convert and Flow for your CRM, Mailchimp for email."
- Store this answer in the workspace config

**KPI Capture per department:**
- After each department is created: "What does success look like for this department? How would you know it is doing a great job?"
- If client hesitates: "That is completely fine. I can research what companies in your industry typically measure and suggest some options. Want me to do that?"
- Present 3 KPI options as choices, not mandates

**Progress Indicators:**
- After basic business info: "You are 30% complete."
- After department creation: "You are 50% complete."
- After KPI setup: "You are 70% complete."
- At the end: "You are complete! Setting up your AI workforce now."

Each question includes examples so you know what kind of answer to give. After every question, the AI adds: "If you are not sure, just ask me to research best practices for your industry. We will figure it out together."

**To choose this option:** Say "Build my AI workforce - Option A"

---

### Option B - Manual Build 🛠️

**Best for:** Hands-on users who want full control

**What happens:**
- You read ai-workforce-blueprint-full.md
- You build everything yourself following the blueprint
- You have complete control over every detail

**To choose this option:** Say "Build my AI workforce - Option B"

---

### Option C - Audit / Resume Mode 🔍

**Best for:** Returning users, adding personas later, checking for gaps

**What happens:**
1. I scan your existing workforce folder
2. I add any missing files (good-examples.md, bad-examples.md, tools.md)
3. If Coaching Personas are installed, I wire them to all departments
4. I never overwrite or delete anything existing

**Use this when:**
- You installed Skill 22 (personas) after building your workforce
- You added new departments and need them audited
- You want to make sure nothing is missing
- Any time you re-run the script

**To choose this option:** Say "Audit my AI workforce" or "Build my AI workforce - Option C"

---

## The Required Files in Every Role Folder

Every role folder MUST have these files. No exceptions.

| File | What it is |
|------|-----------|
| `00-START-HERE.md` | First file the AI reads. What this role does, who owns it, what tools it uses, where to find files |
| `01-[task-name].md` | How-to file for task 1. Numbered, sequential |
| `02-[task-name].md` | How-to file for task 2 |
| (continue numbering) | One file per major task |
| `good-examples.md` | Examples of excellent output for this role |
| `bad-examples.md` | Examples of bad output - what to avoid |
| `tools.md` | List of every tool this role uses with login locations and instructions |

## The Routing File (Universal SOPs)

Every workforce structure needs one routing file at the top level:
`universal-sops/00-ROUTING.md`

This file tells the AI:
- Which department owns each type of task
- Which role inside that department handles it
- Which specific file in that role folder to read first

Without a routing file, the AI guesses. With a routing file, the AI always goes to the right place.

## Naming Convention (Non-Negotiable)

- Department folders: `[name]-dept/` (e.g., `sales-dept/`, `marketing-dept/`)
- Role folders: descriptive lowercase with hyphens (e.g., `lead-generation/`, `content-writer/`)
- Files: numbered with two digits (e.g., `01-`, `02-`) so they sort correctly
- No spaces in folder or file names. Ever.

## Signs Your Structure Is Working

- Your AI routes tasks to the right department without being told
- Output is consistent - same quality every time
- You can walk away and the AI keeps working
- Adding a new task means adding one .md file, not re-explaining everything
- New team members (human or AI) can onboard themselves by reading the folders

## Interview-Style Questions (Option A)

When you choose Option A, I will ask questions interview-style. This means:

✓ Each question includes an example answer
✓ I check what I already know about you before asking
✓ Questions are conversational, not robotic

**Example question format:**

Q: What is your business name?  
Example: Acme Coaching, BlackCEO, Otts Consulting  
[Your answer]: _____

Q: What are the main tools your business uses?  
Example: GoHighLevel, Slack, Google Workspace, QuickBooks  
[Your answer]: _____

This makes it easy to answer - you see exactly what kind of information I am looking for.

## Context Awareness

Before asking questions, I check:
- Your MEMORY.md for business info
- Your USER.md for preferences
- Your AGENTS.md for known tools
- Your IDENTITY.md for context

If I already know something (like your business name), I will use that info and skip the question.

## Telegram-Friendly Output

All messages from this skill use Telegram-friendly formatting:

✓ No markdown tables  
✓ No code blocks  
✓ Short lines with bullets (• or -)  
✓ Emojis for visual breaks  

This makes it easy to read on mobile devices.

---

## Quick Start Guide

**New user?** → Option A  
**Want full control?** → Option B  
**Already built something?** → Option C  

Run the script:  
```bash
python3 scripts/build-workforce.py
```

Or tell me: "Start AI workforce blueprint"
