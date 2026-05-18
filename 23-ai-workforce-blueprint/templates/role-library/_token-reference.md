# Template Token Reference

Canonical tokens used in role-library how-to.md files. Tokens get replaced with company-specific values at build time via `post-build-role-workspaces.py`. The library docs themselves contain ONLY tokens, never literal client data.

## Format
All tokens use double-brace, uppercase, underscore-separated form: `{{TOKEN_NAME}}`.

## Required tokens (most roles)

| Token | Filled at build time with | Example value |
|---|---|---|
| `{{COMPANY_NAME}}` | Client's company name from interview | "BlackCEO" |
| `{{COMPANY_SLUG}}` | URL-safe company slug | "blackceo" |
| `{{COMPANY_INDUSTRY}}` | Detected industry vertical | "personal/professional development" |
| `{{INDUSTRY_VERTICAL}}` | Industry slug | "personal-pro-dev" |
| `{{COMPANY_MISSION_ONE_LINE}}` | From workspace SOUL.md | "Help solo founders build Fortune-500-scale AI workforces" |
| `{{OWNER_NAME}}` | Owner first name | "Trevor" |
| `{{OWNER_VOICE_SAMPLE}}` | From USER.md Behavioral B-4 answer | "We build AI teams for solo entrepreneurs" |
| `{{OWNER_COMMUNICATION_STYLE}}` | From behavioral profile | "direct, no jargon" |
| `{{YEARLY_GOAL}}` | Owner's stated yearly revenue goal | "$2,000,000" |
| `{{QUARTERLY_TARGET}}` | yearly ÷ 4 | "$500,000" |
| `{{MONTHLY_TARGET}}` | yearly ÷ 12 | "$166,667" |
| `{{WEEKLY_TARGET}}` | yearly ÷ 50 | "$40,000" |
| `{{DAILY_TARGET}}` | yearly ÷ 250 | "$8,000" |
| `{{ROLE_TITLE}}` | This role's name | "Email Deliverability & Optimization Specialist" |
| `{{DEPARTMENT_NAME}}` | This role's dept | "CRM" |
| `{{DIRECTOR_TITLE}}` | This dept's director title | "Director of CRM" |
| `{{ASSIGNED_PERSONA}}` | Selected at task dispatch by persona-selector-v2 | "hormozi-100m-offers" |
| `{{ASSIGNED_PERSONA_VERSION}}` | Persona version at dispatch | "1" |
| `{{GENERATION_DATE}}` | Library generation date | "2026-05-18" |
| `{{ROLE_REV_PERCENT}}` | Role's estimated % contribution to revenue cascade | "12" |

## Role-specific tokens (manifest declares which roles need which)

| Token | Roles that use it | Example |
|---|---|---|
| `{{SENDING_DOMAIN}}` | Email Deliverability roles | "mail.blackceo.com" |
| `{{PRIMARY_MAILBOX_PROVIDERS}}` | Email Deliverability | "Gmail, Outlook, Yahoo" |
| `{{CRM_PLATFORM_NAME}}` | CRM dept roles | "GoHighLevel" |
| `{{YEARLY_EMAIL_VOLUME}}` | Email roles | "240,000 emails/year" |
| `{{AD_PLATFORM_NAME}}` | Paid Ads platform-specific roles | "Google Ads" |
| `{{SOCIAL_PLATFORM_NAME}}` | Social Media platform-specific roles | "Instagram" |

## Canonical Deferral Clauses (verbatim — DO NOT MODIFY)

These are used in Section 2 of every how-to.md.

### Standard Deferral Clause (all roles except Master Orchestrator)

```
## Persona Governance Override

When you are assigned a persona for a task, that persona governs HOW you perform
the work. Your beliefs, voice, decision logic, quality bar, and judgment for that
task come from the persona — not from this file.

Act AS IF you ARE the persona for the duration of the task. Use their frameworks.
Use their phrasing. Hold their standards. Make the calls they would make.

This file is your fallback identity. It governs only when no persona is assigned.
When a persona is present, this file is subordinate to it.

**Order of operations when picking up a task:**
1. Check for an assigned persona. If present → act AS that persona.
2. If no persona is assigned → use this file (SOUL.md / IDENTITY.md / how-to.md).
3. In all cases: honor the company's mission (workspace SOUL.md) and the owner's
   stated values (workspace USER.md).
```

### CEO Deferral Clause (Master Orchestrator ONLY)

```
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
