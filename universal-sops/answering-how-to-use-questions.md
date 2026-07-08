# Answering "How Do I Use This Department / Specialist?" Questions
**Version:** 1.0 | 2026-06-15
**Applies to:** Master Orchestrator / CEO Agent AND every Department Director (all installs, Mac and VPS)
**Status:** CANONICAL, fleet standard

---

## Why this SOP exists

Most owners do not realize how many departments and specialists their AI workforce
has, or how to put them to work. So they ask things like:

- "How do I use the marketing department?"
- "What can the sales department do for me?"
- "How do I use the closer?" / "What does the appointment setter do?"
- "Who handles my landing page?"

These are INFORMATIONAL questions about the workforce. They are NOT requests to
produce a deliverable. Answering them well is the difference between an owner who
uses one department and an owner who uses the whole company.

Each department ships a plain-language guide at:

    departments/<dept>/how-to-use-this-department.md

It is generated from that department's REAL roster, so it always matches the
specialists the owner actually has. This SOP defines how the agent answers from it.

---

## The rule (binding)

When an owner message is an informational "how do I use ..." or "what can ... do
for me" question about a department or a specialist:

1. This is an ALLOWED read-and-answer. It is NOT production work, so it does NOT
   get routed to the task board and does NOT need owner permission to answer.
   (The Master Orchestrator may always read workspace files and reply; that is
   explicitly inside its permitted actions.)
2. Identify which department the question is about. If the owner named a
   specialist (for example "the closer"), find the department that specialist
   belongs to using `universal-sops/00-ROUTING.md` plus each
   `departments/<dept>/ROSTER.md`.
3. Read `departments/<dept>/how-to-use-this-department.md` and answer FROM it.
   Quote the relevant parts in plain language: what the department does, when to
   use it, how to ask, what the named specialist is for and an example request,
   and what the owner gets back.
4. If the question spans multiple departments ("how does my whole workforce
   work?"), read `universal-sops/00-ROUTING.md` for the department list, then
   summarize each, and offer to go deeper on any one.
5. Do NOT invent specialists, capabilities, or turnaround promises that are not
   in the guide. If the guide does not cover the question, say so plainly and
   offer to have the department clarify, rather than guessing.

## How to tell a "how do I use" question from a work request

| Owner says | Treat as | Action |
|------------|----------|--------|
| "How do I use the X department?" | Informational | Answer from the guide |
| "What can X do for me?" | Informational | Answer from the guide |
| "How do I use the <specialist>?" | Informational | Answer from the guide |
| "Who handles <thing>?" | Informational | Answer from the guide / routing map |
| "Do <thing> for me" / "Make me a <thing>" | Work request | Route per SOP-00 |
| "Have X handle <thing>" | Work request | Route per SOP-00 |

When a message mixes both ("how do I use the video team, and can you make me a
reel?"), answer the informational part from the guide AND route the work request
per SOP-00. Do both. Never drop one.

---

## Also surface skill-backed capabilities (not just the roster)

Departments **natively operate skills** (see `universal-sops/native-skill-invocation.md`).
When you answer "what can this department do for me?", surface the department's
**skill-backed capabilities** in plain language, not only the specialist roster —
because the biggest capabilities (make a video, write a nurture sequence, generate
ads, build a funnel, produce a keynote) are delivered by a skill the specialist
operates, and the owner benefits even without naming it.

- The binding of department → skill → plain-language intent is
  `~/.openclaw/skills/23-ai-workforce-blueprint/skill-department-map.json`; each
  owning role's `how-to.md` §8 also lists its "Skills You Operate."
- Frame it as an invitation: "Just tell me what you want in plain language — e.g.
  'make me a week of social posts' — and the department will reach for the right
  tool." The owner never has to know the skill's name.
- Still do NOT invent capabilities. Only surface skills the map/role actually binds
  to that department.

---

## Client-optional engine departments and self-invocation questions

Most departments are floor departments: they live in
`23-ai-workforce-blueprint/templates/role-library/`, their guide is rendered from
the specialist index, and at build time it is written to
`departments/<dept>/how-to-use-this-department.md`. A few client-facing
capabilities are instead delivered by a client-optional ENGINE department that is
seeded per client at provisioning (by Skill 32's `add-department.sh`). Such a
department is NOT one of the floor departments, is NOT declared in
`department-naming-map.json`, and its guide is hand-authored and shipped with the
engine's wiring bundle rather than rendered. Answer from that shipped guide the
same way, and never claim the department is on the standard floor.

The first such department is **Anthology** (the Anthology Engine, skill 59):

- Guide: `23-ai-workforce-blueprint/department-wiring/anthology-engine/HOW-TO-USE-THE-ANTHOLOGY-DEPARTMENT.md`.
  At a client install the same guide is seeded into that client's
  `departments/anthology/how-to-use-this-department.md` at provisioning, so the
  standard read-and-answer path in the rule above still works for the owner.
- Answer "how do I use the Anthology department?" and "what can the Anthology
  department do for me?" from that guide, exactly as for any other department.
- Self-invocation questions ("how does the Anthology department invoke itself?",
  "how does it run itself?", "what actually runs when I start an anthology?") are
  answered from the guide's Section 1a (Self-Invocation). The one-line answer:
  every Anthology request, whether a fresh intake, a gate event, or the assembly
  trigger, runs through exactly ONE sanctioned command,
  `anthology-engine-entry.sh`, and never a pipeline stage runner directly. The
  board card and the participant token page are two doors onto that one call, so
  nothing is ever decided twice or in two places.
- Do NOT tell the owner the Anthology department sits on the fleet floor, is
  mandatory, or is one of the 28 floor departments. It is client-optional and
  seeded only when the owner turns the engine on. The floor is unchanged either
  way (see the wiring bundle's `FLOOR-EXPECTATIONS.md`).

This is still an informational read-and-answer, not production work, and the
"do not invent capabilities" rule applies unchanged.

---

## Where this is wired

- Master Orchestrator: `master-orchestrator-dept/SOP-00-Owner-Task-Routing.md`
  Step 1.5 references this SOP as the carve-out to the pure-router rule.
- Department Directors: the director Operating Protocol (written into each
  director's IDENTITY.md / SOUL.md by the build) points here for questions about
  the director's own department and specialists.
- The per-department guides are generated by
  `23-ai-workforce-blueprint/scripts/build-workforce.py`
  (`write_department_how_to_use`) into `departments/<dept>/how-to-use-this-department.md`.

---

*This guide is regenerated whenever a department's roster changes, so the answers
always match the specialists the owner actually has.*
