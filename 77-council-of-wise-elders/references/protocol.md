# Council Protocol Reference

The deliberation protocol the runtime implements. This reference states
the binding rules; the runtime itself is built by its own unit and is
not yet built.

## Modes

- **Full council.** All rounds below, bounded ratification, full report.
- **Quick council.** May end after Round 2 synthesis only when ALL of
  these hold: all nine valid openings exist, no critical factual or
  numerical crux is unresolved, no unresolved affordability, legal,
  safety, or delivery risk remains, and at least eight seats share the
  same direction with a meaningful confidence lead. A quick council
  records its ratification outcome exactly as
  `ratification: not_run_by_quick_mode_policy`. It never simulates
  challenges that did not happen.
- **Named-seat consult.** One seat, one focused question, clearly not a
  council verdict.
- **Rerun.** Same decision, changed facts. The brief is revised, the
  rerun links to the original session, and prior recommendations are
  never silently overwritten.

## Rounds

1. **Brief preparation.** One request. Retrieve permitted context,
   preserve unknowns, show the prepared brief.
2. **Round 1: isolated openings.** Nine requests. No seat sees another
   seat's opening before recording its own. Starting roster members can
   be hidden in the ceremony; capacity still reserves their positions.
3. **Round 1 synthesis.** One request. Organizes claims, support,
   conflict, and missing information; never forces consensus.
4. **Round 2: challenge.** Nine requests. Each seat challenges the
   strongest claims against its own owned question.
5. **Round 2 synthesis.** One request. Resolves differences into at most
   three open cruxes, typed fact, numbers, values, or execution.
6. **Round 3: bounded response.** Nine requests, only for open cruxes.
   There is no fourth challenge round.
7. **Ratification.** One request, after the rounds.
   `informational_revote` for direction and thresholds,
   `final_decision` for the bounded ratification mode.
8. **Verdict composition.** One request, producing the fixed report
   order (references/report-template.md).
9. **Quotation validation.** Runs after final verdict composition and
   before result release. If validation blocks a claim, the system
   repairs the report or withholds the blocked content before anyone
   sees the result.

## Challenge rules

- A challenge names a crux type and the evidence or missing evidence
  behind it. Agreement after distinct, well-supported tests is valid;
  never fabricate disagreement to look rigorous.
- New factual input arriving during a round becomes a brief amendment
  applied at the next defined boundary, never injected mid-round.
- The CEO's private preferences and prior leaning are not Round 1
  inputs; they may informedly shape ratification only.
- A seat that cannot answer honestly abstains with a reason. A timeout
  is recorded as a timeout, never dressed up as an abstention.

## Budget arithmetic

Planned full council: 27 seat requests (9 openings, 9 challenges, 9
responses) + 4 chair requests (brief, two syntheses, verdict) + 2
pipeline requests (ratification, quotation validation) = 33 planned.
Plus 9 repair and reconciliation requests and 8 transport retries gives
a worst case of exactly 50. The session ceiling is 50 provider
requests, hard. A request whose completion is uncertain is recorded as
unknown and never replayed to make a display green.

## Session controls

Pause, resume, and cancel act on the existing session through the
operation lease (60-second TTL, 15-second heartbeat). Action controls
are disabled during an active transition, and an unconfirmed cancel
shows a specific cleanup-pending state rather than success. A provider
response arriving after cancellation cannot resurrect the session.

## Follow-through separation

The council recommends; it does not execute. Preview, approval, task
creation, and execution authorization are four separate steps governed
by INSTRUCTIONS.md. One company parent task per session, created
through the existing task core with the deterministic operation
identity `council_task_parent:<session_id>`, so retries never duplicate
it. No council code creates its own task table.
