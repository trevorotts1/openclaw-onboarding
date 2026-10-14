# Council of Wise Elders: Instructions

Day-to-day operating instructions for the council capability. Read
SKILL.md first; it is the entry point. This file expands the parts a
front-door agent needs most often.

## Build status

The deliberation runtime and advisor packs are not yet built (see
SKILL.md, Build status). Until they land, every council request resolves
the capability, explains plainly that the council cannot deliberate yet,
and spends no provider requests. The instructions below describe the
behavior the finished capability implements, so installers and reviewers
can verify wiring against them; they are not a claim that deliberation
works today.

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
5. Confirm the route: the client's explicitly selected model, or their
   configured default. Recommendations may be offered with reasons; the
   selection is always the client's. Confirm the run grant for the
   session's purpose and budget before the first provider request.

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
