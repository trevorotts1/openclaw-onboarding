# Skill 34: Intelligent Workspace Staffing

## What It Does

Skill 34 adds intelligent specialist staffing to the OpenClaw onboarding process. After Skill 33 creates the 17 permanent department heads, Skill 34 interviews the client to determine which specialist roles inside each department should be **permanent agents** vs **temporary sub-agents**.

### The Core Question

Not every function in a department needs a permanent agent with persistent memory. Some tasks are recurring and need institutional knowledge. Others are one-off and do not.

**Skill 34 figures out which is which.**

## How It Works

### The Interview

Skill 34 asks 6 questions per department (102 total across 17 departments). Each question targets a specific specialist role:

- "Does your marketing team post on social media daily or weekly?" -> Social Media Manager
- "Do you send email campaigns on a recurring basis?" -> Email Marketing Specialist
- "Do you run paid ads continuously?" -> Paid Ads Specialist

### The Decision Matrix

Each question has a pre-assigned type based on the nature of the work:

| Answer | Question Type | Result |
|--------|--------------|--------|
| Yes | permanent | Creates permanent agent with SOUL.md, MEMORY.md, AGENTS.md |
| Yes | subagent | Creates sub-agent template (no persistent memory) |
| No | any | Skips that role entirely |

**The rule for permanent vs sub-agent:**
- Daily/weekly/monthly recurring task that needs to remember past work = **permanent**
- One-time, occasional, or batch task with no memory dependency = **sub-agent**
- Client-facing ongoing relationship = **permanent**

### What Gets Created

**For permanent specialists:**
- Workspace folder: `~/clawd/departments/[dept]/specialists/[specialist-name]/`
- `SOUL.md` - identity, purpose, operating rhythm, boundaries
- `MEMORY.md` - long-term memory scaffold
- `AGENTS.md` - behavior rules
- Entry in `~/.openclaw/openclaw.json` agents list

**For sub-agent roles:**
- Template folder: `~/clawd/subagents/templates/[role-name]/`
- `SOUL.md` - task template (no persistent memory)

## Department Coverage

All 17 departments are covered:

1. **Marketing** - Social Media, Email, Paid Ads, SEO, CRM, Creative Producer
2. **Sales** - Lead Nurturing, Account Development, Proposals, CRM, Prospect Research, Campaigns
3. **Billing/Finance** - Billing, Collections, Reporting, Subscriptions, Financial Analysis, Tax Prep
4. **Customer Support** - Tickets, Knowledge Base, Customer Success, Onboarding, Bug Reports, Surveys
5. **Operations** - Coordination, Vendors, Inventory, Project Management, Process Docs, Efficiency
6. **Creative** - Content Production, Calendar, Copywriting, Scripts, Creative Projects, One-Time Copy
7. **HR/People** - Recruitment, Onboarding, Employee Relations, Payroll, Policy, Compensation
8. **Legal/Compliance** - Contracts, Compliance, Regulatory, Agreements, Legal Research, IP
9. **IT/Tech** - Systems Monitoring, Access Management, Documentation, Infrastructure, Security, Integration
10. **Web Development** - Site Maintenance, Deployment, Performance, Funnels, Features, Audits
11. **App Development** - App Maintenance, Releases, Feedback, APIs, Prototyping, Code Audits
12. **Graphics** - Visual Content, Brand Assets, Ad Creative, AI Image Generation, Design, Infographics
13. **Video** - Video Production, Library, Video Ads, AI Video, Editing, Captions
14. **Audio** - Audio Production, Library, TTS, Voice Agents, Audio Editing, Transcription
15. **Research** - Market Research, Trend Analysis, Data Analytics, Customer Insights, Reports, Feasibility
16. **Communications** - Internal Comms, PR, Community, Stakeholders, Press Releases, Crisis
17. **CEO/Executive** - Strategic Planning, Board Liaison, KPI Tracking, Executive Assistant, Strategy, Competitive Intel

## Relationship to Other Skills

- **Skill 23 (AI Workforce Blueprint)** - Provides the interview framework and department structure that Skill 34 extends
- **Skill 33 (Department Heads)** - Creates the 17 permanent department directors that Skill 34 staffs under
- **Skill 34 (This skill)** - Adds the specialist layer below department heads

## Model Assignments

Specialists are assigned models based on their department's complexity:

| Department | Model |
|-----------|-------|
| Marketing, Creative, Graphics, Video, Audio, Research, Comms, CEO | moonshot/kimi-k2.5 |
| Sales, IT, WebDev, AppDev | openai-codex/gpt-5.4 |
| Operations, Legal | anthropic/claude-sonnet-4-6 |

## Installation

See [INSTALL.md](INSTALL.md) for step-by-step installation instructions.
