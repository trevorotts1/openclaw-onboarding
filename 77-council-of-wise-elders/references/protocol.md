# Council Protocol Reference

The deliberation protocol the runtime implements. This reference states
the binding rules the shipped runtime follows.

## Modes

The council has three sizes, chosen by the four sizing checks in SKILL.md
step 2 (can it be undone, are other people affected, does it lock the
client in, do values pull against each other). No size depends on money,
and no money check exists anywhere in the sizing. Every mode seats the
full nine-advisor council; the mode changes the rounds and the
concurrency only, never how many seats are used.

- **Light.** All 9 seats, exactly 2 rounds, at most 3 provider calls in
  parallel (waves of 3), 50 provider requests.
  Round 1 openings and round 2 challenge always both run; light never
  stops early and never runs a separate ratification pass. The verdict is
  composed from the round-2 advisor cards and recorded as
  `ratification: not_required`.
- **Medium.** All 9 seats, 1 to 4 rounds, 50 provider requests. The stop
  rule below is evaluated after every completed round; medium may stop
  after round 1 only when the stop rule holds.
- **Heavy.** All 9 seats, 3 to 10 rounds, 100 provider requests. Rounds 1
  and 2 always run; the stop rule is evaluated from round 3 onward.

Concurrency is the lower of two limits: the provider's own ceiling (only
Ollama has one, the $20 plan 3 at a time and the $100 plan 10; every
other route adds none) and the mode's wave width (light 3, medium and
heavy the whole nine). A provider with no ceiling therefore never makes a
light sitting unlimited: light runs 3 at a time on OpenRouter and Agnes
too (`runtime/src/providers/parallel.ts`,
`runtime/src/contracts/modes.ts`).

Client overrides always win: "quick answer" means light, "full council"
means heavy. Medium is used when no size is named.

The four older modes keep working exactly as before:

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

## The stop rule

One round is one pass in which every panel seat answers once. Round 1 is
the isolated openings; every later round is a challenge pass on the open
cruxes carried from the previous round's cards.

After a round completes, light/medium/heavy decide as follows:

1. Fewer rounds done than the minimum: continue.
2. The maximum round count reached: stop.
3. Otherwise, when the size allows a stop at this round, evaluate the
   consensus: per seat take that seat's single highest-scored option (a
   tie for highest, an abstention, or an invalid card gives that seat no
   top). T is the most common top. The panel has converged when at least
   7 of the 9 seats share T and T's mean score leads the next-best
   option's mean score by at least 1.5 points. Stop when it has; run the
   next round when it has not.

Light evaluates nothing (its round count is fixed at 2). Medium
evaluates from round 1. Heavy evaluates from round 3. The measure is
unweighted, deterministic, and never inferred from a timestamp.

## Rounds

1. **Brief preparation.** One request. Retrieve permitted context,
   preserve unknowns, show the prepared brief.
2. **Round 1: isolated openings.** One request per seat. No seat sees
   another seat's opening before recording its own. Starting roster
   members can be hidden in the ceremony; capacity still reserves their
   positions.
3. **Round 1 synthesis.** One request. Organizes claims, support,
   conflict, and missing information; never forces consensus.
4. **Round 2: challenge.** One request per seat. Each seat challenges the
   strongest claims against its own owned question.
5. **Round 2 synthesis.** One request. Resolves differences into at most
   three open cruxes, typed fact, numbers, values, or execution.
6. **Later challenge rounds.** Medium may run up to round 4 and heavy up
   to round 10. Each later round re-derives the open cruxes from the
   previous round's cards and runs one request per seat, and is entered
   only when the stop rule has not fired. Light never runs a round after
   round 2. Round numbering is carried in the job descriptor and on each
   advisor card. No chair synthesis request is made between these rounds:
   the runtime derives the cruxes deterministically from the cards.
7. **Ratification.** One request, after the rounds, for the four older
   modes only. `informational_revote` for direction and thresholds,
   `final_decision` for the bounded ratification mode. Light, medium and
   heavy run no separate ratification pass: their verdict is composed
   from the last completed round's advisor cards and recorded as
   `ratification: not_required`.
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

## Request count arithmetic

The cap is per session and depends on the size: light 50, medium 50,
heavy 100. The four older modes keep 50.

For light, medium and heavy a provider request is one seat answering one
round. The runtime makes no chair, synthesis, verdict or quotation
provider request for these sizes: the brief, the cruxes, the draft and
the verdict are composed deterministically from the frozen brief and the
advisor cards. The planned counts are therefore exactly the seat
requests:

- **Light.** All 9 seats x 2 rounds = 18 planned, run 3 at a time in waves
  of 3, inside a cap of 50. Light runs no ratification and no later round.
- **Medium.** Up to 4 rounds x 9 seats = 36 planned, inside a cap of 50.
- **Heavy.** Up to 10 rounds x 9 seats = 90 planned, inside a cap of
  100. A heavy sitting that reaches the cap stops there and reports it
  rather than exceeding it.
- **Full council (unchanged).** 27 seat requests (9 openings, 9
  challenges, 9 responses) + 4 chair requests (brief, two syntheses,
  verdict) + 2 pipeline requests (ratification, quotation validation)
  = 33 planned, plus 9 repair and reconciliation requests and 8
  transport retries, a worst case of exactly 50.

The cap is hard, and a request whose completion is uncertain is recorded
as unknown and never replayed to make a display green.

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
