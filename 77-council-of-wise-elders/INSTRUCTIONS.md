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
the precise typed state and spends no provider requests. Convening is
the approval; there is no separate grant or approval step. A completed
live session is not yet established on any machine, so no instruction
below is a claim that live completion is proven; composition, admission,
and dispatch are the proven live legs.

## Starting a council

1. Recognize the front-door phrases in SKILL.md, or a department request
   that names the decision and carries its origin task. Do not start a
   full council for an ordinary "should I" question unless the client
   asks for the council.
2. Resolve existing sessions first. If a council is already open for the
   same decision, continue it; never create a duplicate.
3. Build the brief from permitted context only: the decision, the real
   options, constraints, known facts, and explicit unknowns. Keep the
   client's private preferences in their separate private store; they
   are not Round 1 inputs.
4. Show the prepared brief before spending. Unknowns stay unknown; a
   standard-company placeholder is never presented as a confirmed fact.
5. Ask the client which model to use. Run `blackceo-council routes`,
   list the options, and offer the harness default: the claude-nine
   configured default on claude-nine, Sonnet on Claude Code, or the
   latest DeepSeek Flash on DeepSeek (resolved from the provider's model
   list at run time, never pinned). Never pick silently. Pass the
   client's choice with `--route` and `--model`; when the client defers,
   pass nothing and the detected harness decides (`--harness` overrides).
6. For a question that depends on current facts, research the web first
   with your own tools and pass the findings with `--fresh-facts FILE`, a
   JSON array of `{claim, url, title, retrieved_at}`. Keep "From the
   elder's books" and "From the web today" separate in everything you
   tell the client, and never fabricate a finding, URL or date.
7. Convene with `blackceo-council convene --brief FILE` (or `--sample`
   for the built-in sample decision). Convening is the approval: no
   grant, no approval prompt. Report the session id, the exact model
   label, whether it was the client's choice or the harness default, and
   the links the command prints. Send the client the `chamber_url`
   exactly as printed, never a 127.0.0.1 link. If the output has no
   `chamber_url`, do not invent, guess, or build a link: tell the client
   the Council is running, the result will be shared, and their private
   Council link is still being set up. Use `blackceo-council`, or
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
emails. The operator publishes that address with
`scripts/provision-council-access.sh --all --apply`; wire.sh keeps it only
after the address answers with a Cloudflare Access sign-in, so a box whose
address is not live yet prints no `chamber_url`. Nobody hand-runs npm.

## Modes

- Full council: all rounds, bounded ratification, full report.
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
- The session ceiling is 50 provider requests, hard. When a request's
  completion is uncertain, it is recorded as unknown and never replayed
  just to make the display green.
- Pause, resume, and cancel act on the existing session. A cancelled
  session stays cancelled even if a late provider response arrives.

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
