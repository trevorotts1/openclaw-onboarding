# D-ESC-GATE (D-ESC-DRIFT / D-ESC-DEDUP / D-ESC-BACKOFF / D-ESC-NEWKEY / D-ESC-TICK)

The Rescue Rangers escalation path had **no dedup and no backoff** - while the operator
alert sitting directly beside it in `_handle_finding` had both. Measured 2026-08-26 on
ONE live box: a single `dedup_key` produced **992 escalations**, and the findings table
held **4,084 rows across 12 distinct `dedup_key`s**. The mechanism is not exotic:
`RR-SENDER-FIX-20260826` correctly leaves a finding OPEN when the intake never admits
its escalation, so the byte-identical escalation is rebuilt and re-posted on the next
15-minute tick, and the next, forever. The intake's rate limit is **GLOBAL** (12/60s)
for the whole fleet, so one box's runaway key sheds **other clients'** live escalations;
one box held 5 spill files carrying the same finding.

Five drills, run offline by `verify.sh` step 3, plus a compact whole-tick case in
`loop_watchdog.py --self-test` (step 1, and the one that runs on a box).

| Drill | Proves |
|---|---|
| **D-ESC-DRIFT** | The shipped `alert.escalation.dedup_window_hours` (12) equals the code fallback `DEFAULT_ESCALATION_DEDUP_WINDOW_HOURS`, and stays **distinct** from the 6h alert window. Both numbers are literals in the drill, never read from the module under test. |
| **D-ESC-DEDUP** | The gate HOLDS a repeat inside the window and **RELEASES** outside it (11h held / 13h released at the shipped 12h). A 3h override releases a 4h-old digest and a 5h override holds it - so a hardcoded 12, or a read of the alert's 6, fails the drill. An explicit `0` disables the dedup rather than falling back to the default. |
| **D-ESC-BACKOFF** | A refusal schedules the next attempt at ~2h then ~4h (jittered, bounds asserted) through the existing `loop_backoff` ladder and `backoff_state` table - never an immediate identical retry. It writes **no digest**, so the failed attempt cannot silence its own retry. It **RELEASES** once `next_at` passes. An admitted delivery resets the ladder to 0. |
| **D-ESC-NEWKEY** | A **new** `dedup_key` escalates immediately while another key is both deduped and pinned at the 24h backoff cap. Suppression is per key - never per class, per box, or global. |
| **D-ESC-TICK** | Reachability **by execution**, not by grep: three real `tick()` runs over real detectors and a real ledger. Tick 1 escalates; tick 2 is suppressed and **never reaches the injected transport**; tick 3 delivers the NEW key on the very tick the old key stays suppressed. The key that reached the transport is resolved from the ledger by `finding_id` (the escalation prose names no unit), and the suppressed finding is asserted still `open`, never `escalated`. |

## Failable in BOTH directions - and proven so

Every drill demonstrates the release as well as the hold. A suppression proven only in
the holding direction is exactly how a noisy system is quietly turned into a **silent**
one, and silent loss is the worse of the two failures by a wide margin.

Each drill was run against a deliberately broken copy of the skill and confirmed to go
RED. Baseline (unmutated) is green:

| Mutation | Drill that caught it |
|---|---|
| dedup gate short-circuited to `False` | D-ESC-DEDUP, D-ESC-TICK |
| backoff gate short-circuited to `False` | D-ESC-BACKOFF |
| `_escalation_key()` returns a constant (suppression made global) | D-ESC-NEWKEY, D-ESC-DEDUP, D-ESC-BACKOFF, D-ESC-TICK |
| a refusal also writes the dedup digest | D-ESC-BACKOFF |
| the gate reads `alert.dedup_window_hours` (6h) instead of the escalation window | D-ESC-DEDUP |
| escalation window "tidied" to equal the alert's 6h | D-ESC-DRIFT, D-ESC-DEDUP |

That last row is the **anti-vacuity guard**. In 0.6.2 a drill kept passing because a
default and the honoured value had become the same number - a dead test showing green.
If the escalation window is ever set equal to the alert window, D-ESC-DEDUP silently
loses its power to tell a config read from a hardcoded constant, so D-ESC-DRIFT fails
first and says why.

Offline: no network, no model call, no external API. `python3 -B` (no `__pycache__`).
