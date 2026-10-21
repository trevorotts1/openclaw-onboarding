---
version: 1.0.34
name: council-of-wise-elders
description: Convene a source-grounded Council of Wise Elders for business or
  personal decisions, test alternatives, explain disagreements, produce one
  actionable recommendation, and prepare approved follow-through. Use when
  the client asks to convene the council, consult a named elder perspective,
  review a consequential decision, revisit a prior council, or compare a
  changed-facts rerun. Use the client's explicitly selected model route.
---

# Council of Wise Elders (Skill 77)

Nine fixed advisory seats review a consequential decision from distinct,
source-grounded perspectives. The council produces one recommendation with
its conditions, the strongest objection, and the next useful step. A council
result is advice. It is never, by itself, permission to act.

## Build status (read first)

This package is the canonical onboarding package for the council. The
deliberation runtime, the standalone CLI, and the nine advisor knowledge
packs are built and ship in this package; their exact tree identity is
recorded in manifest.json. Composition, admission, and dispatch of a
live session are proven on the canary machine configuration; a
completed live session is not yet established, so live completion is
reported as unverified, never as proven. Every advisor pack stands at
bibliographic_only coverage: no seat is quality_qualified, and seats
abstain on claims their coverage does not support. Portable PDF export
from the standalone runtime is not ready by design and refuses with a
typed error; the Command Center side renders PDFs. Wherever a named
prerequisite is genuinely missing (no usable model route, a council
service that reports not ready, no compatible Command Center release for
managed mode), this skill's front door must report that precise state
(a typed not-ready result), never simulate a council session, never invent a verdict, and
never fabricate advisor output.

## Where it runs and how the client opens it

On every box the fleet roll's `wire.sh` builds the runtime into an
immutable release under `$OPENCLAW_ROOT/council-runtime` (`$OPENCLAW_ROOT`
is the environment value, else `/data/.openclaw`, else `~/.openclaw`),
keeps the durable data in `$OPENCLAW_ROOT/council-data`, and keeps the
Council service running on loopback port 8787: the LaunchAgent
`ai.blackceo.council-service` on a Mac, the pm2 app `council-of-wise-elders`
inside the container on a VPS. Nobody hand-runs npm. The result is the
`COUNCIL_WIRE:` line in the roll log (codes in references/install-matrix.md).

The agent convenes with `blackceo-council` (or
`$OPENCLAW_ROOT/council-runtime/bin/blackceo-council` when it is not on
PATH). The client opens the Roast Room chamber at their own Council
address and signs in with their Command Center emails. That address is
set up automatically for every client, finished AI Workforce Interview or
not, and the command looks for it every time a council is convened, so
the client does nothing and nobody re-runs anything on the box. If the command prints a
`chamber_url`, send the client exactly that link. If it prints no
`chamber_url`, the address is not ready yet and the first council after it
is ready carries the link: do not invent, guess, or build a link, and never
send a 127.0.0.1 link (it only works on the box itself). Tell the client
the Council is running, the result will be shared here, and their private
Council link is still being set up. Never mention scripts, servers, fleet
or Cloudflare to the client.

To learn whether this box is usable right now, run
`bash scripts/verify-council-box.sh` (read-only). Its last line,
`COUNCIL_BOX: READY|DEGRADED|NOT_READY <codes>`, is the truth. Report a
DEGRADED or NOT_READY code in plain words, with its fix from
references/install-matrix.md, instead of improvising.

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
4. Ask the client which model the council should use. Run
   `blackceo-council routes` and list the options it returns, then offer
   the default for the harness you are running in, and say which it is:
   the claude-nine configured default on claude-nine, Sonnet on Claude
   Code, or the latest DeepSeek Flash on DeepSeek (the exact id is
   resolved from the provider's model list at the moment of the run, so
   it is never an older pinned Flash). Never pick a model silently. If
   the client names a route or model, pass it with `--route` and
   `--model`. If the client says to use the default, pass nothing and the
   detected harness decides (`--harness` overrides detection).
4a. When the question depends on current facts (prices, laws, markets,
   news, a competitor, anything that changes), research the web before
   convening. Use your own web tools, keep each finding as a short claim
   with its URL, title and retrieved time, and save them as a JSON array
   of `{claim, url, title, retrieved_at}` passed with `--fresh-facts
   FILE`. The council stores them apart from the elders' books. In your
   own answer to the client keep the two kinds of material separate under
   the headings "From the elder's books" and "From the web today", and
   never present a web fact as something the elder taught. Never
   fabricate a finding, a URL or a date: if the research finds nothing,
   convene without fresh facts and say so.
4b. Convene with `blackceo-council convene --brief FILE` (or `--sample`
   for the harmless built-in sample decision). Convening is the
   approval: the client chose the model and pays for it, so there is no
   grant to resolve and no approval step to run or wait for. Do not
   improvise a parallel council. The command prints the session id, the
   route, the exact model label, whether the model was the client's
   choice or the harness default, and the session and live events links.
   Tell the client which model is running, and send them the
   `chamber_url` from the output so they can watch the Roast Room. If the
   output has no `chamber_url` (COUNCIL_BOX code PUBLIC_ORIGIN_UNSET):
   do not invent or guess a link and never substitute a 127.0.0.1
   link. Tell the client the Council is running and the result will be
   shared here, give the session id, and say their private Council link is
   still being set up. It arrives by itself with a later council; ask the
   client for nothing.
   A fresh install convenes immediately on any usable route; there is
   no setup or approval step. If convening is refused for any other
   reason, read the refusal to the client in plain words and never
   simulate a session.
5. Use the exact approved roster and the requested mode. Keep openings
   isolated, challenges evidence-based, ratification bounded, and all
   source claims honest. A session never exceeds 50 provider requests.
6. Present one recommendation, the strongest objection, critical
   conditions, and the next useful step. Link to the durable validated
   result. When fresh facts were used, keep "From the elder's books" and
   "From the web today" as separate sections of your answer.
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
