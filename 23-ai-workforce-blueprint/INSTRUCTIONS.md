# AI Workforce Blueprint - Build Instructions

## Philosophy

This interview builds people into running a real company. It is NOT a survey. The AI is the expert. It leads with knowledge, suggests answers when the client is unsure, and adapts to each person's comfort level. No jargon. No overwhelm. Partnership, not interrogation.

**Forbidden client-facing language:**
- Never say: SOPs, handoffs, tech stack, permanent agent, sub-agent, agent
- Instead say: step-by-step instructions, what departments share, tools you use, team member, specialist, director

**Research model:** When the client is unsure, use openrouter/perplexity/sonar-pro-search to research industry best practices and suggest answers for their approval.

---

## The 3 Options

When you trigger this skill, ALWAYS present all 3 options. NEVER skip this. NEVER auto-select.

---

### Option A - Full Interview (Recommended)

**Best for:** First-time setup, new businesses, or reorganizing

**What happens:**
1. I check what I already know about you from your workspace files
2. I show you the recommended departments and you decide which ones fit
3. I interview you about your business with dynamic questions (3-7 per department based on your needs)
4. I build everything automatically: departments, team leaders, specialists, org chart, and your Command Center config
5. I assign coaching personas to guide how your AI team thinks and works

**Department Recommendations:**

Present the recommended departments with plain English descriptions. The client can keep all, remove some, add custom ones, or start from scratch.

The number of departments is DYNAMIC. A client might choose 5 or 25. Never force a fixed number.

Each department description should be one plain sentence:
- Marketing - Getting the word out about your business
- Sales - Turning interested people into paying customers
- Billing / Finance - Invoices, payments, tracking your money
- Customer Support - Helping your existing customers when they need it
- Operations - Making sure the day-to-day runs smoothly
- Creative - All the writing (blogs, emails, scripts, copy)
- HR / People - Managing your team, hiring, culture
- Legal / Compliance - Contracts, regulations, keeping you protected
- IT / Tech - Your technology, servers, software, security
- Web Development - Your website, landing pages, funnels
- App Development - Mobile apps, software applications
- Graphics - Visual content (logos, images, brand assets)
- Video - Video production, editing, AI video
- Audio - Podcasts, voiceovers, music, audio production
- Research - Market research, competitor analysis, data insights
- Communications - PR, announcements, internal and external messaging
- CEO / Executive - Strategy, vision, high-level decisions

Default to keeping all recommended departments if the client has no preference. But never pressure them. "You can always add more later."

**To choose this option:** Say "Build my AI workforce - Option A"

---

### Option B - Quick Setup (Fastest)

**Best for:** People who want it done fast without a long interview

**What happens:**
- I read what I already know about you from your workspace files (USER.md, MEMORY.md, AGENTS.md, TOOLS.md)
- I combine that with industry best practices for your type of business
- I propose a full company structure: which departments, who leads each one, which specialists are needed, and which coaching personas fit
- You review it and say "looks good" or tell me what to change
- I build everything: department workspaces with core files, team leader agents, specialist assignments, persona alignment, org chart, and Command Center config
- Same output as Option A, just without the interview

**To choose this option:** Say "Build my AI workforce - Option B"

---

### Option C - Audit / Resume Mode

**Best for:** Returning users, adding personas later, resuming an interrupted interview, checking for gaps

**What happens:**
1. I scan your existing workforce folder
2. If an interview-handoff.md exists, I resume exactly where you left off
3. I add any missing files without overwriting anything existing
4. If Coaching Personas (Skill 22) were installed after the initial build, I wire them in
5. I never overwrite or delete anything existing

**To choose this option:** Say "Audit my AI workforce" or "Build my AI workforce - Option C"

---

## Interview Design (Option A)

### Model Requirement
This interview MUST run on a high reasoning model (Opus 4.6, Sonnet 4.6, MiMo V2 Pro with thinking, Gemini 3.1 Pro, or GPT 5.4). If the client is on a low reasoning model, suggest switching: "For setting up your company, I recommend switching to a model that thinks more deeply. Want me to switch?"

### Before Asking Any Question
Check these files for information you already have:
- USER.md - personal preferences, name, timezone
- MEMORY.md - business decisions, prior conversations
- AGENTS.md - tool configurations, behavior rules
- TOOLS.md - connected systems
- workforce-interview-answers.md - previously answered questions (if resuming)

If you already know an answer, confirm instead of re-asking:
"Based on what I already know, your business is in the real estate industry and your main goal is lead generation. Is that still correct, or would you like to change anything?"

### Core Business Questions (asked once, not per department)

1. "What is the name of your business?"
2. "In one sentence, what does your business do?"
3. "What industry are you in?" (examples: coaching, e-commerce, agency, restaurant, law firm, SaaS)
4. "What tools do you currently use to run your business?" (examples: Stripe, Convert and Flow, Mailchimp)
5. "What is your biggest challenge right now?"

After every question: "If you are not sure, just tell me to research it. I will look up best practices for your industry and suggest something for you to approve."

After core questions: "You are 30% complete."

### Per-Department Questions (3-7, dynamic)

Questions are NOT a fixed list. The AI generates questions in real time based on the client's industry, business type, and what it already knows. A hair salon gets different questions than a SaaS company.

**Question categories (pick from these based on relevance):**
1. What the department does regularly
2. Who handles it now (you, someone else, or nobody yet)
3. What success looks like for this department
4. What tools are used (only if not already known from core questions)
5. What is most important about this department to the business
6. What is not working well right now
7. How this department connects to other parts of the business

**Examples of good industry-adapted questions:**

For a hair salon's marketing:
- "How do your clients usually find out about you? Word of mouth, social media, Google?"
- "Do you post on social media regularly or is that something you want to start doing?"

For a SaaS company's marketing:
- "What channels drive most of your signups right now?"
- "Do you run paid campaigns or is growth mostly organic?"

For a coaching business's sales:
- "When someone is interested in working with you, how does that process usually go?"
- "Do you have a follow-up system for people who showed interest but didn't sign up?"

For a restaurant's operations:
- "Walk me through a typical day at your restaurant from open to close."
- "What is the one thing that causes the most headaches in your day-to-day?"

For a law firm's billing:
- "How do you currently track your billable hours and send invoices?"
- "Is getting paid on time a problem for your firm?"

For an e-commerce store's customer support:
- "When a customer has an issue with an order, what happens right now?"
- "Do you get the same types of questions over and over?"

For a real estate agency's marketing:
- "Where are most of your leads coming from right now? Zillow, referrals, social media?"
- "Do you create content about your listings or your local market?"

For a fitness coach's sales:
- "What does your process look like from someone following you online to becoming a paying client?"
- "What usually stops people from signing up after they express interest?"

For a nonprofit's operations:
- "How do you currently track donations and communicate with your donors?"
- "What takes up the most time for your team on a weekly basis?"

For a construction company's billing:
- "How do you handle invoicing for your projects? Per milestone, upon completion, or something else?"
- "Do you have a system for tracking materials costs and change orders?"

The AI should generate questions like these for ANY industry. These examples show the STYLE and DEPTH expected. Plain language. Relevant to their world. Never generic.

**The AI decides how many questions based on:**
- How much it already knows from the core questions
- How complex this department is for this industry
- Whether the client is comfortable or getting fatigued (short answers = offer more support, fewer questions)
- Whether the AI can infer answers from what was already said

NEVER exceed 7 questions per department.

### KPI Capture (per department)

After each department's questions:
"What does success look like for this department? How would you know it is doing a great job?"

If the client hesitates: "That is completely fine. I can research what companies in your industry typically measure and suggest some options. Want me to do that?"

If yes, use Perplexity sonar-pro-search to research and present 3 options. Client picks whichever feels right.

After department creation: "You are 50% complete."
After KPI setup: "You are 70% complete."

### Flush After Every Question

After every answered question:
1. Update workforce-interview-answers.md (in company-discovery/ folder) with the question and answer
2. Update interview-handoff.md with current progress state
3. Trigger a memory flush

This ensures no progress is ever lost. If the session dies or the client walks away, they resume exactly where they left off via Option C.

### Detecting Hesitation

If the client gives short answers, says "I don't know" twice, or pauses:
- Shift to offering suggestions instead of asking more questions
- "Based on what I know about businesses like yours, most companies in [industry] focus on [X]. Want me to set that up for you?"
- Reduce question count for remaining departments
- The goal is completion, not interrogation

### If the Client Wants to Stop

If the client says they need a break, are overwhelmed, or want to stop:
- Save everything immediately (flush answers, update handoff file)
- Tell them: "No problem. Everything we have done so far is saved. When you are ready to continue, just say 'Resume my AI workforce setup' and I will pick up right where we left off."
- Do NOT make them feel bad for stopping. This is their company. Their pace.

### Custom Departments

If the client wants a department that is not in the recommended list:
- Ask them the same dynamic questions (3-7) for that department
- Create the workspace with the same structure as any other department
- Generate a SOUL.md specific to what they described
- The system handles any department name. There are no limits.
- Example: If a client says "I need a Partnerships department," create partnerships-dept/ with a Partnerships Director and treat it exactly like any other department.

---

## What Gets Built After the Interview

### Department Workspaces
The build-workforce.py script handles all workspace creation via `create_department_workspace()`.
For each department chosen, create a workspace at ~/clawd/departments/[dept-name]/ with:

**Unique files:**
- SOUL.md - generated from interview answers (NOT a generic template)
- MEMORY.md - empty, ready for use
- HEARTBEAT.md - department-specific priorities from interview
- memory/ folder - for daily session logs

**Inherited files (copied from main CEO workspace ~/clawd/):**
- TOOLS.md
- AGENTS.md
- USER.md

### Department Head Agents
Every department automatically gets a permanent director added to agents.list in openclaw.json via `add_agent_to_config()`. This is NOT a question asked to the client. Every department has a head. Period.

The SOUL.md for each director is generated from interview answers via `generate_soul_md()`, NOT from a generic template. If the client said their marketing focuses on social media and email, the Marketing Director's SOUL.md reflects that. If they said they do paid ads, the SOUL.md includes ad management responsibilities.

### Specialist Determination (Silent)
The AI reads the interview answers via `determine_specialists()` and determines which specialist roles are needed per department:

**Full-time team member** (permanent agent with memory):
- Work happens daily or weekly
- Needs to remember past work
- Maintains ongoing relationships

**On-call specialist** (spawned when needed):
- Work is occasional or one-time
- No memory dependency

The client NEVER hears these technical terms. They see their org chart showing directors and specialists.

### Persona Assignment (Act As If Protocol)
After workspaces are created, persona alignment runs using the 5-layer check:
1. Company Mission alignment
2. Owner Values alignment (from USER.md)
3. Company Goals/KPI alignment
4. Department Goals/KPI alignment
5. Task Fit

Results stored in:
- ~/clawd/persona-matrix.md (master pre-qualified pool)
- ~/clawd/departments/[dept]/governing-personas.md (department-specific pool)

Personas are selected PER TASK at runtime, not locked to roles.

### ORG-CHART.md
Generated at ~/clawd/ORG-CHART.md via `generate_org_chart()` showing the full company structure: CEO at top, each department director below, specialists under each director with their type (full-time or on-call). Summary reference added to MEMORY.md.

### Command Center Config
departments.json generated via `generate_departments_json()` for the BlackCEO Command Center. Exact schema per entry: id (slug), emoji, name (display), headTitle (director title). Only includes departments the client actually chose.

### Devil's Advocate
Auto-created in every department after all workspaces are built. Client is NOT asked about this. Each DA gets a unique set of challenge questions based on that department's KPIs from the interview. The CEO gets a plain-English explanation: "Your AI workforce includes a quality checker in every department whose job is to make sure your team is actually delivering results, not just saying they are."

After everything is built: "You are complete! Setting up your AI workforce now."

---

## Config Safety

Before ANY edit to openclaw.json:
1. Backup to ~/Downloads/openclaw-backups/ with human-readable name
2. Make the edit
3. Validate JSON after writing
4. Verify backup is in correct location (not a hidden folder)
5. If backup ended up wrong, re-backup to correct location

---

## Required Files in Every Role Folder

| File | What it is |
|------|-----------|
| 00-START-HERE.md | First file the AI reads. What this role does, who owns it, where to find files |
| 01-[task-name].md | Step-by-step instructions for task 1. Numbered, sequential |
| 02-[task-name].md | Step-by-step instructions for task 2 |
| (continue numbering) | One file per major task |
| good-examples.md | Examples of excellent output for this role |
| bad-examples.md | Examples of bad output and what to avoid |
| tools.md | List of every tool this role uses |

## The Routing File

Every workforce structure needs: universal-sops/00-ROUTING.md

This tells the AI which department owns each type of task, which role handles it, and which file to read first.

## Naming Convention (Non-Negotiable)

- Department folders: [name]-dept/ (lowercase, hyphens)
- Role folders: descriptive lowercase with hyphens
- Files: numbered with two digits (01-, 02-)
- No spaces in folder or file names. Ever.

## Context Awareness

Before asking questions, check:
- MEMORY.md for business info
- USER.md for preferences
- AGENTS.md for known tools
- IDENTITY.md for context

If you already know something, use that info and skip the question.

## Telegram-Friendly Output

All messages use Telegram-friendly formatting:
- No markdown tables
- No code blocks
- Short lines with bullets
- Emojis for visual breaks

---

## Quick Start Guide

**New user?** → Option A
**Want it fast?** → Option B
**Already built something?** → Option C

Tell me: "Start AI workforce blueprint"
