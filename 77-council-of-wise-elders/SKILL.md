---
name: council-of-wise-elders
description: Convene a source-grounded Council of Wise Elders for business or
  personal decisions, test alternatives, explain disagreements, produce one
  actionable recommendation, and prepare approved follow-through. Use when
  the client asks to convene the council, consult a named elder perspective,
  review a consequential decision, revisit a prior council, or compare a
  changed-facts rerun. Use the client's explicitly selected model route.
version: 1.0.0
---

# Council of Wise Elders (Skill 77)

Nine fixed advisory seats review a consequential decision from distinct,
source-grounded perspectives. The council produces one recommendation with
its conditions, the strongest objection, and the next useful step. A council
result is advice. It is never, by itself, permission to act.

## Build status (read first)

This package is the canonical onboarding scaffold for the council. The
deliberation runtime, the standalone CLI, and the nine advisor knowledge
packs are built by their own units and are NOT yet built. Until they land,
this skill's front door must report the council as not ready (a typed
not-ready result), never simulate a council session, never invent a verdict,
and never fabricate advisor output. Structure, registration, installation,
and update safety are complete at this stage; deliberation is not.

## The nine seats

Fixed roster, fixed order. Every seat is an AI perspective, labeled exactly:

| Seat ID | Seat | Profile label |
|---|---|---|
| simon-sinek | Simon Sinek | AI perspective inspired by the published work of Simon Sinek. Not the individual and not an endorsement. |
| td-jakes | T. D. Jakes | AI perspective inspired by the published work of T. D. Jakes. Not the individual and not an endorsement. |
| oprah-winfrey | Oprah Winfrey | AI perspective inspired by the published work of Oprah Winfrey. Not the individual and not an endorsement. |
| tiffany-aliche | Tiffany Aliche | AI perspective inspired by the published work of Tiffany Aliche. Not the individual and not an endorsement. |
| russell-brunson | Russell Brunson | AI perspective inspired by the published work of Russell Brunson. Not the individual and not an endorsement. |
| michelle-obama | Michelle Obama | AI perspective inspired by the published work of Michelle Obama. Not the individual and not an endorsement. |
| brene-brown | Brené Brown | AI perspective inspired by the published work of Brené Brown. Not the individual and not an endorsement. |
| dennis-kimbro | Dr. Dennis Kimbro | AI perspective inspired by the published work of Dr. Dennis Kimbro. Not the individual and not an endorsement. |
| les-brown | Les Brown | AI perspective inspired by the published work of Les Brown. Not the individual and not an endorsement. |

The T. D. Jakes seat runs three named lenses inside ONE seat (Instinct,
Disruptive Thinking, Don't Drop the Mic). Three lens findings are never
three votes. No seat is the individual, no output may present invented
quotations or biography as fact, and the chair is process governance, not a
tenth advisor.

## Front doors

Recognize these explicit phrases through the existing intent router:

- "Ask my Council of Wise Elders"
- "Take this decision to the council"
- "Ask the Tiffany Aliche seat" (any named seat works the same way)
- "Review this plan with the council"

Do not intercept every ordinary "should I" conversation and spend on a full
council. Recognize existing-session controls before creating new work:
"Stop that council" resolves the existing session and never creates a task
titled Stop that council. "What did they decide?" reads the verdict.
"Explain Russell's objection" retrieves an existing objection as a read, and
creates a linked consult only when new inference is requested.

## How a council runs

Read references/protocol.md before starting a new council; load the relevant
operational reference for a follow-up or an existing-session control.

1. Resolve the authenticated client and the authoritative managed or
   standalone session store. Do not silently change modes or create a
   duplicate session.
2. Identify whether this is a new decision, a follow-up, a rerun, a pause,
   a cancel, a resume, or an ordinary explanation. Resolve existing-session
   controls first.
3. Retrieve permitted context before asking for facts. Ask only the next
   material missing question. Preserve unknowns and show the prepared brief.
4. Confirm the explicitly selected route and existing applicable run
   authority. Resolve a real purpose-bound run grant through the installed
   tested runtime; do not self-approve or improvise a parallel council. The
   client selects their model, or their configured default applies. This
   skill never prescribes a specific model; it may recommend with reasons.
5. Use the exact approved roster and the requested mode. Keep openings
   isolated, challenges evidence-based, ratification bounded, and all
   source claims honest. A session never exceeds 50 provider requests.
6. Present one recommendation, the strongest objection, critical
   conditions, and the next useful step. Link to the durable validated
   result.
7. Treat the result as advice. Preview action conversion and use the
   existing approval and execution controls; a favorable vote is not
   permission. Preview does not approve, approve does not create or
   execute, and execution needs its own authorization.
8. Preserve source, model, usage, cancellation, history, and privacy
   guarantees. Label samples and replay. Report exact blockers rather
   than inventing output.

Read references/scoring.md for score interpretation,
references/source-policy.md for evidence and quotations,
references/model-routing.md for route and identity rules, and
references/report-template.md for the fixed verdict page order.

## State lives outside this folder

Update sync replaces skill folders wholesale. No council state is ever
stored inside this skill folder: no sessions, no briefs, no verdicts, no
client knowledge, no credentials, no databases. In managed mode the
Command Center database is authoritative. In standalone mode the per-user
council database lives outside the skills tree. The authority mode is
chosen and persisted at installation or session creation and is never
silently switched during a network failure.
