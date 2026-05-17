# AI Workforce Blueprint — Build Instructions

**Version:** v10.4.0 (PRD v2.1 — Zero-Human Company Spec)
**Target interview length:** ~30 questions, ~35 minutes
**Persona governance:** Persona overrides identity files. CEO has special clause (mission/owner override persona on conflict).

---

## Philosophy

This interview builds people into running a Fortune 500-scale company with $0 in human payroll. It is NOT a survey. The AI is the expert. It leads with knowledge, suggests answers when the client is unsure, and adapts to each person's comfort level.

**No jargon. No overwhelm. Partnership, not interrogation.**

**Forbidden client-facing language:**
- Never say: SOPs, handoffs, tech stack, permanent agent, sub-agent, agent, Lean Six Sigma, DMAIC
- Instead say: step-by-step instructions, what departments share, tools you use, team member, specialist, director

The system uses Lean Six Sigma methodology INTERNALLY (standard work templates, quality gates, value-stream handoffs, continuous improvement) — but the owner never hears those words.

**Research model:** When the client is unsure, use `openrouter/perplexity/sonar-pro-search` to research industry best practices and suggest answers for their approval.

---

## The 3 Options

When you trigger this skill, ALWAYS present all 3 options. NEVER skip. NEVER auto-select.

### Option A — Full Interview (Recommended)
Best for: First-time setup. ~30 questions, ~35 minutes. AI generates 130-200 role-level how-to documents in the background after the interview completes.

### Option B — Quick Setup (Fastest)
Best for: Owners who want it done fast. AI reads existing workspace files + pre-interview research + industry best practices, proposes everything, owner approves.

### Option C — Audit / Resume Mode
Best for: Returning users, adding personas later, resuming an interrupted interview. Picks up from `interview-handoff.md`. Never overwrites custom edits.

---

## v2.1 Interview Structure (Option A)

### Phase 0 — Pre-Interview Asset Drop (0 questions, ~5 min)

Before any question, ask the owner:

> "Before we start, drop in anything that tells the story of your business. The more I have, the fewer questions I'll ask. For every document or link, I'll skip 3-5 questions later.
>
> What helps most:
> - Your website URL
> - Your About Me / founder bio page or PDF
> - LinkedIn (personal AND company)
> - YouTube channel or video links
> - Podcast (if you have one)
> - Brand documents — color scheme, brand voice guide
> - Logo files
> - Pitch deck or sales deck
> - Customer testimonials
> - Any SOPs or processes you've written
> - Social media handles (Instagram, TikTok, Facebook, Twitter/X, Pinterest, LinkedIn, Threads, Bluesky, YouTube)
> - Calendly or booking link
> - Past business plans
> - **Anything else that helps me understand your business**
>
> If you have nothing, no problem — we'll build it together."

**AI actions during Phase 0:**
1. Fetch every URL (Perplexity Sonar Pro for website crawl, LinkedIn parsing, YouTube transcript extraction)
2. Parse uploaded files (heavy model — DeepSeek/Kimi/Minimax)
3. Write findings to `[ZHC]/[slug]/pre-interview-research.md` with sections:
   - Mission & Vision
   - Industry vertical (auto-detected)
   - Stage (idea/MVP/growth/scale)
   - Geographic scope
   - Tools Used
   - Brand Voice
   - Target Audience
   - Customers
   - Open Questions
   - Source URLs
4. Pre-fill answers to later phases. Frame as confirmation, not question: *"Based on your LinkedIn, you're in real estate — still right, or did anything change?"*

**Industry auto-detection** via `shared-utils/industry-detector.py`:
- Personal/Professional Development (coaches, thought leaders) — ~60% of clients
- Real Estate
- Service Industry (spas, plumbers, maids, lawn care, restaurants)
- E-commerce
- SaaS / Tech
- Agency
- Content Creator

If detection confidence < 0.7, ask the C-4 confirmation question in Phase 3.

---

### Phase 1 — Behavioral Identity (5 questions, ~12 min)

These come BEFORE business questions. Behavior reveals identity; words conceal it.

**B-1: Hard Conversation Behavior**
"Tell me about the last time you had to have a really hard conversation with someone on your team. Walk me through what you said and how you said it. Give me the actual words you used."

**B-2: Failure Response**
"Think about the last big mistake you or your team made — something that cost real money or real trust. What did you do in the first hour after you found out?"

**B-3: Money Pressure**
"You have $10,000 to invest in growing your business this month. Walk me through how you'd decide where to put it. What do you look at? What do you trust? What do you ignore?"

**B-4: Style Sample**
"In ONE sentence, describe what your business does, as if you're talking to a friend at a barbeque. Not a pitch — just how you'd actually say it."

**B-5: Anti-Mentors**
"Name 2-3 people whose business thinking has shaped you most. Then name 1-2 people whose business thinking you actively disagree with."

After B-5: Run `extract-behavioral-patterns.py` and write `## Behavioral Identity Profile` to USER.md.

---

### Phase 2 — Vision and Goals (4 questions, ~6 min)

**V-1:** "What do you want this business to give you and your family in the next 5 years? Money is fine — but go beyond money if you can."
**V-2:** "What does winning look like for you in 12 months? Be specific — numbers, milestones, feeling."
**V-3:** "What's your revenue goal for the next 12 months? If you're not sure, give me a range — I'll do the math from there."
**V-4:** "What's the thing you secretly want this business to become but don't talk about often?"

**AI auto-derives Revenue Cascade from V-3** (becomes the KPI spine for every role):

| Cadence | Formula |
|---|---|
| Quarterly | yearly ÷ 4 |
| Monthly | yearly ÷ 12 |
| Weekly | yearly ÷ 50 |
| Daily | yearly ÷ 250 |

**Edge case:** If owner has no revenue yet → use "first paying customer" cascade (first customer in 60 days, 5 customers in 90 days, 20 in 6 months).

---

### Phase 3 — Customer & Business Context (5 questions, ~7 min)

**C-1:** "Describe your ideal customer like you're describing a friend. Who are they, what do they do, what keeps them up at night?"
**C-2:** "Where do they spend their time — online or in person? What platforms, communities, events?"
**C-3:** "In their words (not yours), what problem do they pay you to solve?"
**C-4** (only if auto-detection confidence < 0.7): "From your materials it looks like you're in [auto-detected industry]. Is that right?"
**C-5:** "What's the biggest thing holding you back from growing right now?"

---

### Phase 4 — Department Customization (~13 bundled questions, ~10 min)

Do NOT ask one question per department. Bundle related departments. Each question captures ONE customization signal.

**Q-D1:** "How do most people hear about your business right now? And where do you want them hearing about you 12 months from now?"
*(Captures: Marketing + Communications + Social Media + Paid Advertisement signal)*

**Q-D2:** "What makes your business different from the 3 closest competitors? If you're not sure, I'll research it and propose something."
*(Marketing positioning + Research signal)*

**Q-D3:** "When someone is interested in working with you, walk me through what currently happens, step by step."
*(Sales)*

**Q-D4:** "How do you currently get paid — invoices, subscriptions, one-time, retainers? What payment systems do you use?"
*(Billing & Finance)*

**Q-D5:** "When a customer has an issue, what happens right now? What's the most common issue they raise?"
*(Customer Support)*

**Q-D6:** "Do you have a website now? Are you building or planning to build an app? If yes to either — what's the role those play in your business?"
*(Web Development + App Development)*

**Q-D7:** "What does your business produce visually and in video / audio? Examples: social posts, YouTube videos, podcast episodes, sales VSLs, courses, presentations."
*(Graphics + Video + Audio)*

**Q-D8:** "What do you need to know more about — your competitors, your industry, your customers, or all three?"
*(Research)*

**Q-D9:** "Which CRM or contact-management system do you use (or want to use)? Examples: GoHighLevel, HubSpot, Salesforce, ActiveCampaign, or 'I don't have one yet'."
*(CRM)*

**Q-D10:** "Do you currently use written contracts with clients or vendors? Are there any compliance or regulatory requirements in your industry?"
*(Legal — and triggers regulated-industry overlay if applicable)*

**Q-D11 [CRITICAL]:** "On a scale of 1-10, how confident are you that your business emails actually land in inboxes (not spam)? Have you set up SPF, DKIM, or DMARC? It's fine if those terms don't mean anything to you."
*(Email Deliverability — flagship CRM role)*

**Q-D12:** "How comfortable are you with technical setup, troubleshooting, and updating systems? I'll calibrate how much hand-holding the maintenance team gives you."
*(OpenClaw Maintenance)*

**Q-D13:** "Of everything we just talked about, which area is MOST important for you to nail in the next 90 days?"
*(Highest-weight signal — used by Learning Loop and persona_assignment table)*

---

### Phase 5 — Industry Vertical Pack Confirmation (1 question, ~1 min)

"Based on what you told me, you're in [DETECTED_INDUSTRY]. Businesses like yours always need a few extra departments: [vertical pack list]. Sound right, or want me to skip some?"

---

### Phase 6 — Final Review (~1-2 min)

AI shows a plain-English summary of EVERYTHING captured. Owner confirms or edits any line. Then: "Build my company."

**Total: ~28-30 questions, ~35 minutes** (with asset drop happening in parallel).

---

## The 16 Mandatory Departments

Auto-built for EVERY zero-human company, no exceptions:

1. **Marketing** — brand, awareness, demand generation
2. **Sales** — outreach, conversion, deals
3. **Billing & Finance** — invoices, payments, cash flow, forecasting
4. **Customer Support** — onboarding, retention, service, refunds
5. **Web Development** — website, funnels, landing pages, SEO (with SEO Specialist + Funnel Builder)
6. **App Development** — desktop, mobile, PWA
7. **Graphics** — brand identity, social graphics, slides, ad creative
8. **Video** — long-form, short-form, editing, motion graphics, Video SEO Specialist
9. **Audio** — podcast, AI voice (11 Labs), sound design, speech writing, music
10. **Research** — McKinsey-style industry analysis, competitive intel, market trends
11. **Communications** — PR, internal comms, crisis comms, speech writing
12. **CRM** — platform admin, **Email Deliverability & Optimization Specialist (flagship)**, segmentation, automation
13. **OpenClaw Maintenance** — system health, skill updates, memory hygiene, backups, security
14. **Legal** — contracts, compliance, terms, privacy, IP
15. **Social Media (organic only)** — Facebook, Instagram, TikTok, LinkedIn, Twitter/X, Pinterest, YouTube channel, Threads, Bluesky, Community Manager
16. **Paid Advertisement** — Google Ads, Bing, Meta Ads, TikTok, LinkedIn, Twitter, Pinterest, YouTube Ads, Spotify, Snapchat, Native (Taboola/Outbrain)

**Plus: Master Orchestrator (CEO Agent)** — sits above all departments at `[ZHC]/[slug]/master-orchestrator/`. Special CEO persona deferral clause (mission/owner override persona on conflict).

See `suggested-roles/*.md` for the full role roster per department.

---

## Industry Vertical Packs (Auto-Added Based on Phase 0 Detection)

### Personal / Professional Development Pack (~60% of clients)
- Presentations (slides, decks, keynote prep)
- Client Coaches (for coaching agency clients — distinct from Customer Support)
- Course Creator (curriculum, ops, student success)
- Podcast
- Community Management (Facebook Groups, Skool, Circle, Discord, Slack)

### Real Estate Pack
- Listings Management
- MLS Operations
- Lead Generation (Zillow, Realtor.com, FB lead ads)
- Showings Coordinator
- Open House Specialist
- Closing Coordinator
- Local Market Intelligence

### Service Industry Pack (spas, plumbers, maids, lawn care)
- Scheduling / Dispatch
- Field Operations / Service Quality
- Local SEO (added to Web Development)
- Reviews Management (Google, Yelp)
- Recurring Service / Membership Coordinator

---

## Universal How-To Template (Sub-Agent Output Standard)

Every role's `how-to.md` follows the 18-section template at `templates/universal-how-to-template.md`. Sub-agents generating role docs use the prompt at `prompts/role-doc-generation-prompt.md`.

The 18 sections (every one must be present and filled):
1. Role Identity (Who You Are / What This Role Is NOT)
2. Persona Governance Override (verbatim from Chapter 19)
3. Daily Operations
4. Weekly Operations
5. Monthly Operations
6. Quarterly Operations
7. KPIs (tied to revenue cascade)
8. Tools You Use
9. Standard Operating Procedures (numbered, atomic)
10. Quality Gates
11. Handoffs (Value Stream Map)
12. Escalation Paths
13. Good Output Examples
14. Bad Output Examples (Anti-Patterns)
15. Common Mistakes
16. Research Sources (tiered: role-specific, McKinsey/HBR, Perplexity, Deep Research dept)
17. Edge Cases for This Role
18. Update Triggers

QC sub-agent verifies all 18 sections present, no TODOs, KPIs link to revenue cascade, Section 13 has concrete examples, Section 16 has actual URLs, word count 2500-5500.

---

## Role-Level Workspace Architecture

Per role within each department:

```
[ZHC]/[slug]/departments/[dept]-dept/[role-slug]/
├── IDENTITY.md         (unique to role)
├── SOUL.md             (unique to role, with deferral clause)
├── MEMORY.md           (unique to role, starts empty)
├── HEARTBEAT.md        (unique to role)
├── how-to.md           (universal 18-section template)
├── AGENTS.md → [ZHC]/[slug]/AGENTS.md    (symlink)
├── TOOLS.md  → [ZHC]/[slug]/TOOLS.md     (symlink)
└── USER.md   → [ZHC]/[slug]/USER.md      (symlink)
```

Symlink pattern extends the existing v9.6.1 department-level pattern down to the role level.

---

## Generation Orchestration (After Interview)

**Stage 1 (1 min):** `build-workforce.py` writes `sop-research-manifest.json`
**Stage 2 (5-10 min):** 1 sub-agent runs industry + competitor research → `[ZHC]/research/industry-research.md` + `competitor-intel.md`
**Stage 3 (10-30 min):** Up to 10 dept sub-agents in parallel — each generates dept SOUL/MEMORY/HEARTBEAT/governing-personas.md, DA SOUL+SOP, then spawns 5-13 role sub-agents
**Stage 4 (parallel with Stage 3):** Up to 50 role sub-agents concurrently — each generates IDENTITY/SOUL/MEMORY/HEARTBEAT/how-to.md per the universal template
**Stage 5 (5 min):** 1 QC sub-agent scans every how-to.md against the 9-item checklist
**Stage 6 (2 min):** Assembly — ORG-CHART.md, departments.json, persona-matrix.md, company-config.json

**Total: ~25-45 min for a full 130-200 document build.**

Owner sees real-time progress at `/onboarding/building` in the Command Center. Telegram notification when complete.

---

## Assisting Language (PRESERVED FROM v9.6.0 — DO NOT REMOVE)

### After every ASKED question (not confirmed):
> "If you're not sure, just let me do a little bit of research, and I can come back and help you with the answer."

### "I Don't Know" Flow (6 steps — USE THIS EXACT PROCESS)
1. **Acknowledge:** "That is completely fine. Let me help you figure this out."
2. **Research:** Use Perplexity Sonar Pro for industry best practices.
3. **Provide 2-3 Options:** "Based on what works for businesses like yours, here are 3 common approaches..."
4. **Recommend One:** "My recommendation is [X] because [specific reasoning]. But you know your business best."
5. **Let Client Choose:** "Which one feels right for you? Or want me to suggest something else?"
6. **Document the Choice:** Record in `workforce-interview-answers.md` as "researched recommendation."

### Hesitation Detection
If client gives short answers, says "I don't know" twice, or pauses:
- Shift to offering suggestions instead of asking more questions
- "Based on what I know about businesses like yours, most companies in [industry] focus on [X]. Want me to set that up for you?"
- Reduce question count for remaining areas
- **Goal is completion, not interrogation**

### If the Client Wants to Stop
- Save everything immediately (flush answers, update handoff file)
- "No problem. Everything we have done so far is saved. When you're ready, say 'Resume my AI workforce setup' and I'll pick up exactly where we left off."
- DO NOT make them feel bad. Their company. Their pace.

### Telegram Nudge Cadence (multi-day persistence)
- +24h idle: "You're {progress}% done. Want to keep going? {link}"
- +3d idle: "Still want to finish your AI workforce setup? You stopped at: {last_question}. {link}"
- +7d idle: "Last check-in. Want me to finish your setup with best-guess defaults? Reply YES and I'll handle it."

If owner replies YES at the 7-day nudge → auto-run Option B (Quick Setup) → ~25-45 min later, completed company is ready.

---

## Pull-Forward Rule (Binding)

Before asking ANY question, check (in this order):
1. `[ZHC]/[slug]/pre-interview-research.md` — Phase 0 findings
2. `[OPENCLAW_ROOT]/workspace/MEMORY.md` — facts already saved
3. `[OPENCLAW_ROOT]/workspace/USER.md` — owner preferences + behavioral profile
4. `[OPENCLAW_ROOT]/workspace/AGENTS.md` — tools/behavior already configured

If the answer exists in any of those files, **DO NOT re-ask**. Frame as confirmation:
> "Based on what I already know, your marketing focuses on social media and email. Still right, or did anything change?"

---

## Flush After Every Question

After every answered question:
1. Update `workforce-interview-answers.md` with question + answer
2. Update `interview-handoff.md` with progress state
3. Trigger memory flush

This ensures no progress is ever lost. If session dies, resume via Option C.

---

## What Gets Built After the Interview

### Department Workspaces
For each of the 16 mandatory departments + vertical pack departments, `create_department_workspace()` creates:
- SOUL.md (generated from interview, NOT a template — includes the deferral clause)
- MEMORY.md (empty)
- HEARTBEAT.md (department priorities)
- memory/ folder
- governing-personas.md (pre-qualified persona pool from 5-layer scoring)
- devils-advocate/SOUL.md + SOP.md
- AGENTS.md, TOOLS.md, USER.md as SYMLINKS to workspace root

### Role-Level Folders (NEW in v2.1)
Inside each department, one folder per role (Director, specialists, QC, Deep Research). Each role folder contains:
- IDENTITY.md (unique, with deferral clause)
- SOUL.md (unique, with deferral clause)
- MEMORY.md (empty)
- HEARTBEAT.md (role-specific cadence)
- how-to.md (universal 18-section template, generated by sub-agent)
- AGENTS.md, TOOLS.md, USER.md as SYMLINKS to workspace root

### Master Orchestrator (CEO Agent)
Created at `[ZHC]/[slug]/master-orchestrator/`. Same file structure as a role folder, BUT:
- SOUL.md and IDENTITY.md contain the **CEO Deferral Clause** (mission/owner override persona on conflict)
- how-to.md Section 2 contains the CEO Deferral Clause instead of the standard one

### Company-Level Files
- ORG-CHART.md (full structure with persona pills)
- departments.json (for Command Center)
- company-config.json (revenue cascade, mission, KPI targets)
- persona-matrix.md (full persona-to-dept mapping)

---

## Persona Governance — Two Deferral Clauses

### Standard Clause (every agent except Master Orchestrator)

```markdown
## Persona Governance Override

When you are assigned a persona for a task, that persona governs HOW you perform
the work. Your beliefs, voice, decision logic, quality bar, and judgment for that
task come from the persona — not from this file.

Act AS IF you ARE the persona for the duration of the task. Use their frameworks.
Use their phrasing. Hold their standards. Make the calls they would make.

This file is your fallback identity. It governs only when no persona is assigned.
When a persona is present, this file is subordinate to it.

**Order of operations:**
1. Check for an assigned persona. If present → act AS that persona.
2. If no persona is assigned → use this file (SOUL.md / IDENTITY.md / how-to.md).
3. In all cases: honor the company's mission (workspace SOUL.md) and the owner's
   stated values (workspace USER.md).
```

### CEO Clause (Master Orchestrator only)

```markdown
## Persona Governance — CEO Mode

As the CEO / Master Orchestrator, you do NOT fully defer to assigned personas.
You use them as INPUT, but you remain accountable to the company's mission and
the owner's values at all times — those override the persona when there is conflict.

When a persona is assigned to a CEO-level task:
1. Read the persona's frameworks, voice, and decision logic. Consider them.
2. Compare to mission (workspace SOUL.md) and owner profile (workspace USER.md).
3. Where the persona ALIGNS → embody it for the task.
4. Where the persona CONFLICTS → mission and owner WIN. Log conflict in MEMORY.md.
5. Your own identity governs when no persona is assigned.

You are the protector of the mission. Personas are tools you use, not authorities
you serve.
```

Apply via `STANDARD_DEFERRAL_CLAUSE` and `CEO_DEFERRAL_CLAUSE` constants in `build-workforce.py`. Append to every generated SOUL.md and IDENTITY.md. To migrate existing workspaces: run `shared-utils/migrate-deferral-clauses.py`.

---

## Telegram-Friendly Output

All client-facing messages use Telegram-friendly formatting:
- No markdown tables in chat (use them in markdown files only)
- No code blocks in chat
- Short lines with bullets
- Emojis for visual breaks

---

## Quick Start Guide

- **New user?** → Option A
- **Want it fast?** → Option B
- **Already built something?** → Option C

Tell me: "Start AI workforce blueprint"
