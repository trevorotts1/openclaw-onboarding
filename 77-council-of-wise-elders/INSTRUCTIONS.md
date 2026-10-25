# Council of Wise Elders: Instructions

Day-to-day operating instructions for the council capability. Read
SKILL.md first; it is the entry point. This file expands the parts a
front-door agent needs most often.

## Build status

The deliberation runtime and the nine advisor packs are built and ship
in this package (see SKILL.md, Build status). Every council request
resolves the capability and runs through the council service: a service
that reports not ready, no usable model route, or no compatible
Command Center release for managed mode means the request refuses with
the precise typed state and uses no provider requests. Convening is
the approval; there is no separate grant or approval step. A completed
live session is not yet established on any machine, so no instruction
below is a claim that live completion is proven; composition, admission,
and dispatch are the proven live legs.

## Starting a council

1. Recognize the front-door phrases in SKILL.md, or a department request
   that names the decision and carries its origin task. Do not start a
   full council for an ordinary "should I" question unless the client
   asks for the council. Size a new decision with the four checks in
   SKILL.md step 2 (can it be undone, other people affected, lock-in,
   values pulling against each other; there is no money check), announce
   the size in one line, and honor the client's override: "quick answer"
   is light, "full council" is heavy.
2. Resolve existing sessions first. If a council is already open for the
   same decision, continue it; never create a duplicate.
3. Build the brief from permitted context only, with the one shared
   brief-builder (`runtime/src/brief/permitted-brief.ts`) running FIRST
   in the convene flow. It reads the door's own memory files through
   the door's adapter (the OpenClaw door: memory.md, agents.md,
   soul.md, user.md; the claude-nine / Claude Code (999) door:
   CLAUDE.md, AGENTS.md, memory/MEMORY.md), plus at most one hop of the
   pointer links inside them (recursion never, and a link can never
   escape the context root or touch a private path). It selects the
   facts that bear on THIS decision (never a file dump), records the
   decision, the real options, and the constraints, marks everything
   the context does not state as an explicit unknown, keeps the
   client's private preferences in their separate private store (the
   brief carries only `private_preference_ref`, an opaque handle), and
   never exceeds its 2000-word cap. The brief shape is identical
   whichever door the client came through.
4. Show the prepared brief before convening. Unknowns stay unknown; a
   standard-company placeholder is never presented as a confirmed fact.
5. Ask the client which model to use, and offer the council's providers in
   this fixed order. Run `blackceo-council routes` and list what it
   returns: those are the council runtime's own configured providers on
   this box, never the calling agent's models.
   - OpenRouter first, and recommended: it runs every advisor at once with
     no parallel limit, so the sitting is the fastest.
   - The client's own Ollama, if they prefer it. When their plan is not
     already known, ask once: the $20 a month plan runs at most three
     advisors at a time, the $100 a month plan runs up to ten. When Ollama
     fails and the client has named an OpenRouter fallback model
     (`--fallback-model ID`), the failed seats re-run on OpenRouter; with
     no fallback model the sitting blocks on the failed seats instead.
   - Agnes 3.0 Flash, when the client selects it: no parallel limit.
   The default follows the same rule as SKILL.md: read the calling agent's
   own configured provider (in OpenClaw, `openclaw agents list`; on
   claude-nine or Claude Code, the harness default) and, if one of those
   routes is that provider family, that route is the default; otherwise
   OpenRouter is the default and the recommendation. Never pick silently.
   Pass the client's choice with `--route` and `--model`; when the client
   defers, pass nothing and the detected harness decides (`--harness`
   overrides).
6. For a question that depends on current facts, research the web first
   with your own tools and pass the findings with `--fresh-facts FILE`, a
   JSON array of `{claim, url, title, retrieved_at}`. Keep "From the
   elder's books" and "From the web today" separate in everything you
   tell the client, and never fabricate a finding, URL or date.
7. Convene with
   `blackceo-council convene --brief FILE --mode light|medium|heavy` (or
   `--sample` for the built-in sample decision). For a light question pass
   the three chosen seats with `--seat-ids id,id,id`; when it is omitted
   the driver picks the three best-fit seats. On the client's own Ollama
   pass `--ollama-plan 20` or `--ollama-plan 100`, and `--fallback-model
   ID` to name the OpenRouter model used when Ollama fails. Convening is
   the approval: no grant, no approval prompt. Report the session id, the
   exact model
   label, whether it was the client's choice or the harness default, and
   the links the command prints. Send the client the `chamber_url`
   exactly as printed, never a 127.0.0.1 link. If the output has no
   `chamber_url`, do not invent, guess, or build a link: tell the client
   the Council is running, the result will be shared here, and their
   private Council link is still being set up (it is set up automatically:
   ask the client for nothing, and never mention scripts, servers, fleet or
   Cloudflare). Use `blackceo-council`, or
   `$OPENCLAW_ROOT/council-runtime/bin/blackceo-council` when it is not on
   PATH. If the box cannot convene, run `bash scripts/verify-council-box.sh`
   and report its `COUNCIL_BOX:` line and the matching fix from
   references/install-matrix.md.

## Where the service runs

`wire.sh` (run by the fleet roll) keeps the service up: LaunchAgent
`ai.blackceo.council-service` on a Mac, pm2 app `council-of-wise-elders` in
the container on a VPS, release and receipts in
`$OPENCLAW_ROOT/council-runtime`, durable data in
`$OPENCLAW_ROOT/council-data`. The client signs in at their own Council
address (the `chamber_url` the command prints) with their Command Center
emails. That address is published automatically for every client, with no
operator or client step and no dependence on the AI Workforce Interview
(every client has a Command Center from install, locked to the interview
until closeout): an operator-side job publishes it within about 30 minutes
of the Command Center existing, and the box looks for it each time a
council is convened, so the first council after the address exists carries
the link. Until then no `chamber_url` is printed. Nobody hand-runs npm.

## The two doors

A client triggers either door the same way: by asking for the council
in their own words (SKILL.md, Front doors) or by naming a seat. The
OpenClaw door is the client's OpenClaw agent on their box. The
claude-nine / Claude Code (999) door is this same skill inside
claude-nine or Claude Code. The 999 tree vendors it under
`.claude/skills/council-of-wise-elders`, with the runtime entry at
`runtime/dist/council-entry.mjs` (built by that tree's
`scripts/council-runtime-install.sh`), while the OpenClaw door runs the
same runtime's `blackceo-council` CLI. Each door feeds the flow its own
adapter's permitted context (`runtime/src/flow/convene-flow.ts`
selects the adapter from the harness markers), so one flow and one
brief shape serve both.

## Modes

Three council sizes, sized from the question and never from money:

- **Light.** 3 best-fit seats, exactly 2 rounds, cap 50 provider requests.
  No separate vote pass: the verdict is composed from the round-2 advisor
  cards and recorded as `ratification: not_required`. A light question may
  never stop early, and it never skips a round.
- **Medium.** All 9 seats, 1 to 4 rounds, cap 50 provider requests. After
  every completed round the chair checks the stop rule in
  references/protocol.md and stops when the panel has converged.
- **Heavy.** All 9 seats, 3 to 10 rounds, cap 100 provider requests. The
  stop rule is evaluated from round 3 onward; rounds 1 and 2 always run.

Client overrides always win: "quick answer" means light, "full council"
means heavy. The medium size is used when no size is named.

The four older modes keep working exactly as before:

- Full council: all three rounds, bounded ratification, full report.
- Quick council: may end after the early rounds only under the strict
  conditions in references/protocol.md; a quick council never pretends
  ratification happened.
- Named-seat consult: one seat's perspective on a focused question,
  clearly labeled as a single perspective, not a council verdict.
- Rerun: same decision with changed facts; the brief is revised and the
  rerun is linked to the original session.

## During a session

- Seats open independently; no seat sees another seat's opening before
  recording its own.
- Challenges must name a factual, numerical, value, or execution crux.
  Agreement after distinct, well-supported tests is valid; manufactured
  disagreement is a defect.
- New factual input during a round is queued as a brief amendment and
  applied at the next defined boundary, never injected mid-round.
- The session ceiling is 50 provider requests for light and medium, and
  100 for heavy, hard. When a request's
  completion is uncertain, it is recorded as unknown and never replayed
  just to make the display green.
- Pause, resume, and cancel act on the existing session. A cancelled
  session stays cancelled even if a late provider response arrives.

## Closing a session

A council sitting is one session, and every sitting gets closed; a
sitting never hangs open.

- Five minutes after the client's last interaction in an open session,
  ask exactly ONE soft-close question: "Is that all, or are we still
  working?" One per quiet spell: never repeat it while the question
  is standing.
- An explicit close phrase ("that's all", "we're done", "finalize",
  and the other phrases in runtime/src/protocol/session-close.ts)
  finalizes the sitting immediately; ask nothing more.
- Any other answer is a new interaction: the sitting continues and the
  five-minute quiet clock restarts from it. Never auto-finalize over
  an answer.
- No answer within ten minutes of the soft-close question: finalize
  automatically. The session is never left open.
- Finalize means: mark the session closed in the store, render the
  counsel artifact (the renderer's `renderArtifact(sessionRecord)`
  returns its path and link), and deliver it: the reply carries the
  artifact link beside the chamber link, so the client can read the
  counsel and step back into the Roast Room from the same message.
- Close state is derived from the store's own timestamps (the last
  event on the session and the recorded soft-close), never from
  in-memory timers: a service restart continues the same quiet spell,
  loses nothing, and never sends a second soft-close question.
- One active session per client: resolve the existing session first
  (see Starting a council); never open a second sitting while one is
  still open.

## Reading a result

The verdict page order is fixed (references/report-template.md):
recommendation, conditions, three main reasons, strongest concern,
immediate next actions, full scorecard, then detailed rounds and
sources. Scores are interpreted by references/scoring.md. A GO-style
label requires at least 80 percent weighted score coverage and no
unresolved critical-domain abstention; anything else is presented with
its conditions, not rounded up into a GO.

## Follow-through

A council result is advice. Turning it into work is a separate chain,
and each link is its own authorization:

1. Preview the action plan (no tasks created).
2. Approve the plan (nothing created or executed by approving).
3. Create tasks: exactly one parent task per company session, created
   through the existing task core with the deterministic operation
   identity, so a retry never duplicates it.
4. Authorize execution separately. "Create these tasks" and "Authorize
   execution" are different buttons and different decisions.

## Privacy and records

- Every seat output carries its exact profile label (see SKILL.md).
- Private sessions are visible only to their owner; a company-scoped
  event stream never carries private session content.
- Reports exported for a team are separate redacted artifacts; redaction
  removes private details from the body, metadata, source appendix,
  embedded assets, and filenames.
- Samples and replays are always labeled as samples and replays, and a
  replay can never create production actions.
- Outcome reviews are recorded against the session so the council's
  advice can be judged later by what actually happened.
