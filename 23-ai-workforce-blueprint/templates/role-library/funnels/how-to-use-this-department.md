# How to Use the Funnels Department 🔻

**Department:** Funnels
**Department head:** Director of Funnels
**Folder:** `departments/funnels/`
**Generated for:** {{COMPANY_NAME}}
**Last updated:** {{GENERATION_DATE}}

> This is the plain-language guide to the Funnels department. Most
> people never realize this department exists or know how to put it to work.
> This document fixes that. When you ask "how do I use the Funnels
> department?" or "how do I use the Funnel QA & Conversion Verification Specialist?", this is the
> document your agent reads to answer you.

---

## 1. What This Department Does (in plain language)

Owns the automated GHL sales-funnel BUILD queue that Skill 6 (`06-ghl-install-pages`, `tools/cc_board.py`) stamps every `job_type='funnel'` card into (`department_slug='funnels'`). Executes the cut -> import -> verify-imported -> provision-custom-values chain against the client's own GHL account, then QAs the delivered funnel end to end: page-by-page verification, checkout/order-bump/upsell path testing, and conversion-tracking (pixel) checks before a build is considered done. This is deliberately narrower than  -  and does not replace  -  the funnel-adjacent roles that already live in two other departments: - **Marketing** owns funnel STRATEGY and the copy/offer-ladder intake: Funnel Strategist (mapping the acquisition funnel, identifying leaks) and the Signature Funnel Specialist / Sales Page Assets Specialist "engine doors" onto Skill 49 / Skill 56, which frame the offer and hand the actual build to Skill 6. - **Web Development** owns the broader, multi-platform funnel-building toolset (ClickFunnels, Leadpages, custom builds outside the GHL/Skill-6 rail) and carries its own copies of the same two Skill 49 / Skill 56 engine-door roles for web-development-originated funnel requests. This THREE-department overlap (Marketing, Web Development, and now Funnels all carrying funnel-adjacent roles) is a known, deliberate, operator-ruled structure  -  not an oversight. It mirrors an already-existing pattern in this repo: Marketing and Web Development already both carry independent copies of the Signature Funnel Specialist and Sales Page Assets Specialist roles for their own intake paths. Funnels is the newest instance of that same pattern: the dedicated operational home for the ONE automated pipeline (Skill 6's `job_type='funnel'` card stamp) that previously had no registered department to land in at all, and silently misrouted to the general-task catch-all on any standard-floor box. Nothing in Marketing's or Web Development's existing role catalogs is moved, renamed, or deleted by this department's registration.

In one sentence: **Building, verifying, and shipping the GHL sales funnels Skill 6 creates for you**

You do not need to know which specialist does what. You just tell the department
what you want in plain English, and the department head (Director of Funnels)
figures out who handles it and routes it for you.

---

## 2. When to Use It

Reach for this department when you want any of the following:

- Post-build QA of every funnel the GHL Funnel Build Specialist ships.
- Drives the actual technical execution of every `department_slug='funnels'` card against the client's own GHL.

If you are not sure whether a request belongs here, ask anyway. The department
head will either take it or hand it to the right department. You never have to
get the routing right yourself.

---

## 3. How to Ask It for Work

You have three ways to put this department to work. All of them are fine.

1. **Just say it in plain English.** Message your agent like you would a
   teammate: "I need help with something from the funnels team." That is enough to start.
2. **Name the department if you want to be specific.** "Have the
   Funnels department handle something from the funnels team." This routes
   it straight to Director of Funnels.
3. **Name a specialist if you know exactly who you want.** See the specialist
   list in Section 4 and ask for them by role: "Get the Funnel QA & Conversion Verification Specialist
   to take on a funnels task for you."

A good request includes, where it applies: **what** you want, **who or what it
is for**, **when you need it**, and any **must-haves or limits**. You do not have
to provide all of that. If something important is missing, the department first offers you a quick or an
in-depth path, then asks one focused question at a time (never a wall of
questions) and waits for each answer. It gathers what you tell it into a single
brief before the work starts, rather than guessing.

---

## 4. The Specialists Inside This Department

Each specialist below is built for one job. You can ask the department as a whole
and it will pick the right one, or you can ask for a specialist by name.

| Specialist | What it is for |
| --- | --- |
| **Funnel QA & Conversion Verification Specialist** | Post-build QA of every funnel the GHL Funnel Build Specialist ships. |
| **GHL Funnel Build Specialist** | Drives the actual technical execution of every `department_slug='funnels'` card against the client's own GHL account. |

### What each specialist is for, with an example request

**Funnel QA & Conversion Verification Specialist**

- *What it is for:* Post-build QA of every funnel the GHL Funnel Build Specialist ships.
- *Example request:* "Have the Funnel QA & Conversion Verification Specialist take this on: Post-build QA of every funnel the GHL Funnel Build Specialist ships."

**GHL Funnel Build Specialist**

- *What it is for:* Drives the actual technical execution of every `department_slug='funnels'` card against the client's own GHL account.
- *Example request:* "Have the GHL Funnel Build Specialist take this on: Drives the actual technical execution of every `department_slug='funnels'` card against."


---

## 5. What to Expect Back

When you ask this department for something, here is the normal flow:

1. **Acknowledgment.** Director of Funnels confirms the request landed and, if
   anything important is unclear, asks one focused question at a time (never a wall of questions).
2. **Routing.** The work is matched to the right specialist and the relevant
   procedure (its SOP). Nobody guesses; if there is no procedure for your
   request, one is written before the work starts.
3. **The work itself.** The specialist does the job and it is checked by the
   department's quality-control review before it reaches you.
4. **Delivery.** You get the finished result: the finished funnels work you asked for.
   Anything that needs your sign-off before it goes live is flagged for your
   approval first.

Typical turnaround depends on the size of the request. Quick items come back the
same working session; larger projects come back with a clear estimate up front.

---

## 6. How It Hands Off (to you and to other departments)

- **To you:** finished deliverables arrive in your workspace and you are notified.
  Anything marked owner-approval-required waits for your yes before it ships.
- **To other departments:** when your request needs another team, this department
  coordinates the handoff for you through the company's routing map
  (`universal-sops/00-ROUTING.md`). You do not have to manage the handoff.
  
- **Escalation:** if something is blocked, needs a decision only you can make, or
  needs a credential or payment, it is escalated to you directly rather than
  stalling silently.

---

## 7. Quick Questions You Can Ask

You can ask your agent any of these at any time and it will answer from this
document:

- "How do I use the Funnels department?"
- "What can the Funnels department do for me?"
- "How do I use the Funnel QA & Conversion Verification Specialist?"
- "Who handles something from the funnels team?"
- "What do I get back if I ask Funnels for something from the funnels team?"

---

*This guide is generated for {{COMPANY_NAME}} by the AI Workforce Blueprint
(Skill 23). It is regenerated whenever the department's roster changes so it
always matches the specialists you actually have.*
