---
version: 1.0.74
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
source-grounded perspectives. Every mode seats the full nine-advisor
council; the mode changes how many rounds the elders run and how many may
work at once, never how many seats are used: light (exactly 2 rounds, at
most 3 provider calls in parallel, in waves of 3), medium (up to 4 rounds)
and heavy (up to 10 rounds). A light session still shows all nine seats.
The council produces one recommendation with
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
from the standalone runtime renders the same print document through the
PDF renderer the box already carries (headless Chrome/Chromium, the
Playwright browser cache, or the CUPS filter); a completed sitting is
downloadable from the chamber as a real `application/pdf` attachment and
again from the past-session read, at
`/council/<session-id>/report.pdf`, inside the same owner boundary as
the session. A box with no renderer says so with a typed not-ready error
that names the missing piece; HTML is never renamed `.pdf`. Wherever a named
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
nobody (client or operator) does anything. The helper's `Chamber link:`
line (see "The chamber visual on every call") is the single source of
truth for the client's link: the client receives that exact line and
nothing else. The command's `chamber_url` field is the same link as
data - it feeds the helper's line and is never sent to the client on its
own. If no link is ready yet, the first council after it is ready
carries it: do not invent, guess, or build a link, and never send a
127.0.0.1 link (it only works on the box itself). Tell the client the
Council is running, the result will be shared here, and their private
Council link is still being set up. Never mention scripts, servers,
fleet or Cloudflare to the client.

Operator side only (never on a client box): the operator Mac's job
`scripts/council-access-autoprovision.sh` first runs
`scripts/ensure-cc-access.sh`, which keeps every client's Command Center
login page letting in the operator emails and every verified client email.
It creates a missing login page, adds missing emails to an existing one
without removing anything (RECONCILED), and finds client emails itself: the
emails file `~/.claude/state/council-elders/cc-access-emails.json`
(`{"operator","clients","ghl":{"location_id"}}`), the client's own login and
rescue pages, and a read-only, strict GoHighLevel lookup. The Council login
page then follows the Command Center login page's email list, additions and
removals alike (SYNCED). Details in INSTALL.md, "Client access" and "Command
Center login pages".

To learn whether this box is usable right now, run
`bash scripts/verify-council-box.sh` (read-only). Its last line,
`COUNCIL_BOX: READY|DEGRADED|NOT_READY <codes>`, is the truth. Report a
DEGRADED or NOT_READY code in plain words, with its fix from
references/install-matrix.md, instead of improvising.

## The chamber visual on every call

However the client calls the council - claude-nine terminal or chat - the
Roast Room visual they see at the link must show up for them too. On every
convene, right after `blackceo-council convene` returns:

1. Run `bash scripts/chamber-visual.sh --session <session_id>`. It prints
   exactly one line, `Chamber link: <url>`, resolved from the box's own
   runtime configuration (env, then the box's service.json), never
   hardcoded.
2. ALWAYS copy that exact `Chamber link:` line into your reply to the
   client - terminal and chat alike - so phone and chat callers tap it
   straight into the same visual. Never rewrite, guess, or build the URL.
3. The helper also opens that same visual in the box's default browser
   when a desktop session exists. It is fire-and-forget: it never blocks
   the reply, and on a headless box (CI, cron, server) it opens nothing
   and still prints the link.
4. If the line is a 127.0.0.1 address (local-only): the box's own screen
   shows the visual, and a remote client cannot open it. Never send a
   127.0.0.1 link to a client - tell them the Council is running, the
   result will be shared here, and their private Council link is still
   being set up. It arrives by itself with a later council.

The same applies to existing-session reads that surface the chamber ("What
did they decide?" and the like): include the `Chamber link:` line so the
visual is always one tap away.

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

The council has two doors and the client triggers both the same way:
by asking for the council in their own words (the phrases below). The
OpenClaw door is the client's OpenClaw agent on their box; the
claude-nine / Claude Code (999) door is the same skill running inside
claude-nine or Claude Code (the 999 tree vendors it under
`.claude/skills/council-of-wise-elders`, entry
`runtime/dist/council-entry.mjs`). Each door reads its own permitted
context through its own adapter and feeds the same assembler, so the
brief and the flow look identical either way.

Recognize these explicit phrases through the existing intent router:

- "Ask my Council of Wise Elders"
- "Ask the council" ("ask the council ...", "take this to the council")
- "Take this decision to the council"
- "Ask the Tiffany Aliche seat" (any named seat works the same way)
- "Review this plan with the council"

Do not intercept every ordinary "should I" conversation and run a full
council. Recognize existing-session controls before creating new work:
"Stop that council" resolves the existing session and never creates a task
titled Stop that council. "What did they decide?" reads the verdict.
"Explain Russell's objection" retrieves an existing objection as a read, and
creates a linked consult only when new inference is requested.

## The front door: one command

`council-ask` (installed beside `blackceo-council` by `wire.sh`) is the
supported entry point for every council call. It does the whole front door in
one step, so no part of it is a second, optional agent action:

```
council-ask ask --brief FILE [--mode light|medium|heavy] [--route R] [--model M] [--json]
council-ask session <session-id> [--json]
council-ask sessions [--json]
council-ask authority [--json]
```

`--json` prints exactly one JSON document on stdout (a refusal is one JSON
document on stderr). Every subcommand honours it; never advertise a flag the
command ignores.

The installed shim execs
`$OPENCLAW_ROOT/council-runtime/frontdoor/<release-id>/scripts/council-entry.mjs`,
a durable copy made by `scripts/install-front-door.sh` during `wire.sh`. It
never points into the skill checkout that ran the wiring, because that
checkout can be a lane worktree or a temporary clone that is deleted after
merge. The source copy in this skill (`node scripts/council-entry.mjs`) never
expires, so the command works from a checkout too.

Four rules it enforces, and the agent must not re-implement them by hand:

1. **An explicit ask always opens a NEW session.** A `COMPLETED` sitting on
   the same question is context, not the answer: the command says so in one
   line and still convenes. Only an OPEN session (in progress) is continued,
   and a `BLOCKED` one is resolved, never reused as the answer. Answering
   "ask the council" with a four-day-old verdict is a failure, not a
   shortcut (recorded on the operator box, 2026-10-28).
2. **The service is the authority.** `council-ask ask` proves the service
   answers `/healthz` before it convenes. If it does not, the command
   refuses with `COUNCIL_SERVICE_DOWN` and the exact recovery. Report that
   refusal plainly; never start a parallel council and never simulate one.
3. **Session reads go through the service.** `council-ask session <id>` and
   `council-ask sessions` read the service store. `blackceo-council status`,
   `pause`, `cancel` and `verdict` read the CLI's LOCAL store instead, so on
   a box whose sessions live in the service they report
   `COUNCIL_SESSION_NOT_FOUND` for sessions that exist. Never use them as
   the authority for "did the council run?".
4. **The chamber link is part of the call; the desktop pop is best effort.**
   The command runs `scripts/chamber-visual.sh` itself and always prints the
   one `Chamber link:` line. Copy that exact line; do not run a separate "now
   get the link" step, because it gets skipped. The pop is delivered to the
   box's own desktop when a GUI session can be reached (an Aqua process, or a
   root bridge through `launchctl asuser`); otherwise the helper reports
   `pop: skipped` or `pop: failed` on stderr and the link is still printed.
   A headless box, a VPS, or an ssh session never claims a pop it did not
   deliver. Nothing here sends to Telegram or any other channel: the agent's
   own reply is the delivery path, and the link line must be pasted into it.

`council-ask authority` prints the box's real state (service origin and
health, the actual LaunchAgent name from `service.json`, release id, public
origin, CLI path, and the front door path that is actually executing). An
adopted box keeps its own LaunchAgent name, so read it from there rather than
assuming the default.

## How a council runs

Read references/protocol.md before starting a new council; load the relevant
operational reference for a follow-up or an existing-session control.
One flow runs the sitting end to end
(`runtime/src/flow/convene-flow.ts`): the brief-builder runs first
(permitted context), then deliberation, then the verdict, the
session-close protocol manages the sitting, and finalize renders the
counsel artifact.

1. Resolve the authenticated client and the authoritative managed or
   standalone session store. Do not silently change modes or create a
   duplicate session.
2. Identify whether this is a new decision, a follow-up, a rerun, a pause,
   a cancel, a resume, or an ordinary explanation. Resolve existing-session
   controls first. For a new decision, size the question with exactly these
   four checks and nothing else:
   - Can it be undone? A reversible step is a light question.
   - Are other people affected? More people means more rounds.
   - Does it lock the client in? A lock-in is never a light question.
   - Do values pull against each other? Competing values need the debate.
   There is no money, cost or spending check, and none is ever applied.
   Then announce the size in ONE line and carry on: "Light question: all
   nine advisors, 2 rounds, 3 at a time. Say 'full council' for the full
   debate." (or "Medium question: 9 advisors, up to 4 rounds." / "Heavy
   question: 9 advisors, up to 10 rounds."). Every size seats all nine
   advisors; the size changes the rounds and the parallelism only. A
   client override always wins: "quick answer" means
   light, "full council" means heavy.
3. Retrieve permitted context before asking for facts: the brief the
   elders read is assembled FIRST by the one shared permitted-context
   builder (`runtime/src/brief/permitted-brief.ts`), through the door's
   own adapter: the OpenClaw door reads memory.md, agents.md, soul.md,
   user.md; the claude-nine / Claude Code (999) door reads CLAUDE.md,
   AGENTS.md, memory/MEMORY.md. It follows a pointer link at most one
   hop (recursion never), selects only the facts that bear on THIS
   decision (never a file dump), keeps private detail in the private
   store (only an opaque `private_preference_ref` handle), marks what
   the context does not state as an explicit unknown, and never runs
   past its 2000-word cap. Ask only the next material missing question.
   Preserve unknowns; do not stop to show a draft unless the client asks.
4. Resolve the model route from the CALLING agent, never from a guessed
   global default. The supported front door does this: run it from the
   calling agent's own workspace and pass the calling agent's configured
   route/model through the accepted caller-route path. The routes
   `blackceo-council routes` returns are the council runtime's own
   configured providers on this box - they are NOT the calling agent's
   models, and they must never be presented as if they were.
   Never ask the client to choose a provider and never stop to confirm a
   route. If the front door refuses with ROUTE_CHOICE_REQUIRED,
   ROUTE_NOT_CONFIGURED, ROUTE_NOT_COMPOSABLE, or ROUTE_MODEL_NOT_OFFERED,
   report that typed refusal and its recovery exactly; do not invent,
   force, or silently substitute a provider.
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
4b. Convene with
   `blackceo-council convene --brief FILE --mode light|medium|heavy` (or
   `--sample` for the harmless built-in sample decision). Convening with no
   `--mode` runs medium; that default is deliberate, so name the mode you
   announced. Every mode seats all nine advisors; light simply runs them in
   waves of 3, so no mode and no flag reduces the roster. On the
   client's own Ollama pass `--ollama-plan 20` or `--ollama-plan 100`, and
   `--fallback-model ID` to name the OpenRouter model used when Ollama
   fails. Convening is the approval: the client chose the model, so there
   is no grant to resolve and no approval step to run or wait for. Do not
   improvise a parallel council. The command prints the session id, the
   route, the exact model label, whether the model was the client's
   choice or the harness default, and the session and live events links.
   Tell the client which model is running, then run
   `bash scripts/chamber-visual.sh --session <session_id>` and follow
   "The chamber visual on every call" for the reply link. If the
   helper's line is a 127.0.0.1 address (COUNCIL_BOX code
   PUBLIC_ORIGIN_UNSET):
   do not invent or guess a link and never substitute a 127.0.0.1
   link. Tell the client the Council is running and the result will be
   shared here, give the session id, and say their private Council link is
   still being set up. It arrives by itself with a later council; ask the
   client for nothing.
   A fresh install convenes immediately on any usable route; there is
   no setup or approval step. If convening is refused for any other
   reason, read the refusal to the client in plain words and never
   simulate a session.
5. Use the exact approved roster and the mode you announced. Keep openings
   isolated, challenges evidence-based, ratification bounded, and all
   source claims honest. Every mode seats all nine advisors, so a light
   session shows all nine seats. The provider-request cap is light 50,
   medium 50, heavy 100 per session; light also runs at most 3 provider
   calls at a time, in waves of 3; the four older modes keep 50. Nothing
   else is capped.
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

## Closing a session

A council sitting is one session, and every sitting gets closed; a
sitting never hangs open. Five minutes after the client's last
interaction in an open session, ask exactly ONE soft-close question:
"Is that all, or are we still working?" An explicit close phrase
("that's all", "we're done", "finalize", ...) finalizes immediately;
any other answer continues the sitting and restarts the five-minute
quiet clock; no answer within ten minutes of the question finalizes
automatically. Finalize marks the session closed in the store, renders
the counsel artifact through the renderer's
`renderArtifact(sessionRecord)` (it returns the artifact path and
link), and delivers it: the reply carries the artifact link beside the
chamber link, so the client can read the counsel and return to the
Roast Room from the same message. The close state derives from
the store's own timestamps, never from in-memory timers, so a restart
loses nothing and never repeats the question. One active session per
client: resolve the existing session first, never create a duplicate.
Full detail in INSTRUCTIONS.md, Closing a session.

## State lives outside this folder

Update sync replaces skill folders wholesale. No council state is ever
stored inside this skill folder: no sessions, no briefs, no verdicts, no
client knowledge, no credentials, no databases. In managed mode the
Command Center database is authoritative. In standalone mode the per-user
council database lives outside the skills tree. The authority mode is
chosen and persisted at installation or session creation and is never
silently switched during a network failure.
