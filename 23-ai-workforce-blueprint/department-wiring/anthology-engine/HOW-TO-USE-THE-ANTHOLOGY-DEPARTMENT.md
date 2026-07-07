# How to Use the Anthology Department 📖

**Department:** Anthology
**Department head:** Anthology Producer Orchestrator
**Folder:** `departments/anthology/`
**Generated for:** {{COMPANY_NAME}}
**Last updated:** {{GENERATION_DATE}}

> This is the plain-language guide to the Anthology department. Most
> people never realize this department exists or know how to put it to work.
> This document fixes that. When you ask "how do I use the Anthology
> department?" or "how do I use the Anthology Producer Orchestrator?", this is
> the document your agent reads to answer you.

---

## 1. What This Department Does (in plain language)

You collect chapters from many contributors around one theme. For each
contributor, this department turns their intake answers into a finished
anthology chapter in their own voice, complete with a title, a blurb, an
outline, a cover, and both a Google Doc and a designed PDF. When your
collection is complete, it assembles the whole anthology into one manuscript
in your editorial voice.

In one sentence: **Turns one contributor's intake into a finished anthology
chapter, end to end, and assembles the finished anthology when every
contributor is ready.**

You do not need to know which specialist does what. You just tell the
department what you want in plain English, and the department head (Anthology
Producer Orchestrator) figures out who handles it and routes it for you.

---

## 1a. How This Department Runs Itself (Self-Invocation)

Every request this department acts on, whether it is a fresh intake, a gate
event, or the assembly trigger, is carried out through exactly one sanctioned
command: `anthology-engine-entry.sh`, inside `59-anthology-engine/`. The
department never runs a pipeline step by hand and never opens a second door.

- **Intake.** A new contributor's Convert and Flow submission, or your own
  plain-language request ("run the anthology engine", "start an anthology",
  "onboard an anthology producer"), invokes
  `anthology-engine-entry.sh --stage s0 --payload FILE`.
- **Gate events.** Every decision you or a contributor makes on a board card or
  the contributor's own token page (approve, request a rewrite, mark ready to
  assemble, sign off) reaches the SAME shared approval logic through
  `anthology-engine-entry.sh --stage sN`. The board and the token page are two
  doors onto one call; nothing is ever decided twice or in two places.
- **Assembly trigger.** Firing "assemble the anthology" invokes
  `anthology-engine-entry.sh --stage s9 --anthology-id ID`, which carries the
  ready-to-assemble check and, once every chapter is settled, your final
  sign-off.

No department event, board action, or plain-language request ever calls a
pipeline script directly. It always goes through this one entry point, which
runs its own safety checks first (a dependency check, a model-configuration
check, and a version check) before anything is dispatched.

---

## 2. When to Use It

Reach for this department when you want any of the following:

- Collect a chapter from a new anthology contributor.
- Start a brand-new anthology around a theme.
- Check on a contributor's progress or make a gate decision (approve or
  request a rewrite).
- Assemble the finished anthology once every contributor is settled.

If you are not sure whether a request belongs here, ask anyway. The department
head will either take it or hand it to the right department. You never have to
get the routing right yourself.

---

## 3. How to Ask It for Work

You have three ways to put this department to work. All of them are fine.

1. **Just say it in plain English.** Message your agent like you would a
   teammate: "I need help with a new anthology contributor." That is enough to
   start.
2. **Name the department if you want to be specific.** "Have the Anthology
   department handle a new contributor." This routes it straight to the
   Anthology Producer Orchestrator.
3. **Name a specialist if you know exactly who you want.** See the specialist
   list in Section 4 and ask for them by role: "Get the Anthology Approvals
   Steward to check on the readiness report."

A good request includes, where it applies: **what** you want, **who or what it
is for**, **when you need it**, and any **must-haves or limits**. You do not
have to provide all of that. If something important is missing, the department
first offers you a quick or an in-depth path, then asks one focused question at
a time (never a wall of questions) and waits for each answer. It gathers what
you tell it into a single brief before the work starts, rather than guessing.

---

## 4. The Specialists Inside This Department

Each specialist below is built for one job. You can ask the department as a
whole and it will pick the right one, or you can ask for a specialist by name.

| Specialist | What it is for |
| --- | --- |
| **Anthology Producer Orchestrator** | Owns your anthology end to end: intake and routing, delivery, and the final assembly of the whole manuscript. |
| **Anthology Approvals Steward** | Owns every gate: keeps nudges on schedule, prepares the readiness report, and runs the independent quality check before anything reaches you. |
| **Anthology Chapter Author** | Writes each contributor's chapter in that contributor's own voice, from avatar and tone through title, outline, and the finished chapter. |

### What each specialist is for, with an example request

**Anthology Producer Orchestrator**

- *What it is for:* Owns your anthology end to end, from the first intake to
  the final assembled manuscript.
- *Example request:* "Have the Anthology Producer Orchestrator start a new
  anthology for this collection."

**Anthology Approvals Steward**

- *What it is for:* Keeps every gate moving, prepares the readiness report, and
  runs the independent quality check.
- *Example request:* "Have the Anthology Approvals Steward tell me who is still
  outstanding before I can assemble."

**Anthology Chapter Author**

- *What it is for:* Writes each contributor's chapter in their own voice, from
  the avatar and tone work through the finished chapter.
- *Example request:* "Have the Anthology Chapter Author pick up this
  contributor's intake."

---

## 5. What to Expect Back

When you ask this department for something, here is the normal flow:

1. **Acknowledgment.** The Anthology Producer Orchestrator confirms the request
   landed and, if anything important is unclear, asks one focused question at a
   time (never a wall of questions).
2. **Routing.** The work is matched to the right specialist and the relevant
   procedure (its SOP). Nobody guesses; if there is no procedure for your
   request, one is written before the work starts.
3. **The work itself.** The specialist does the job and it is checked by the
   department's independent quality check before it reaches you.
4. **Delivery.** You get the finished result: a contributor's chapter as both a
   Google Doc and a designed PDF, or, once every contributor is settled, the
   assembled anthology manuscript. Anything that needs your sign-off before it
   goes live is flagged for your approval first, on the department's board.

Typical turnaround depends on the size of the request and how quickly your
contributors respond. There are no deadlines: a contributor who pauses for
months costs nothing, and their place is always saved.

---

## 6. How It Hands Off (to you and to other departments)

- **To you:** finished deliverables arrive on the Anthology department board
  and you are notified. Anything marked owner-approval-required (every gate
  decision) waits for your yes before it moves forward.
- **To other departments:** when your request needs another team, this
  department coordinates the handoff for you through the company's routing map
  (`universal-sops/00-ROUTING.md`). You do not have to manage the handoff.
  Marketing and Social Media get read-only access to your published anthology
  links so they can plan promotion; every other department has no access to
  this department or its work at all.
- **Escalation:** if something is blocked, needs a decision only you can make,
  or needs a credential or payment, it is escalated to you directly rather than
  stalling silently.

---

## 7. Quick Questions You Can Ask

You can ask your agent any of these at any time and it will answer from this
document:

- "How do I use the Anthology department?"
- "What can the Anthology department do for me?"
- "How do I use the Anthology Approvals Steward?"
- "Who handles a new anthology contributor?"
- "What do I get back if I ask Anthology for a new contributor?"
- "How does the Anthology department invoke itself?"

---

*This guide is generated for {{COMPANY_NAME}} by the AI Workforce Blueprint
(Skill 23). It is regenerated whenever the department's roster changes so it
always matches the specialists you actually have.*
