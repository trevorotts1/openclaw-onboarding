# GK-17/A7 -- the S0->mc_board silent mirror drop: root cause + the converging-repair fix (U79)

**Status:** ONB-side repo/code fix, unit-tested and self-tested. The CC-side half
(wiring `checkAnthologyBoardProjection()` / `BoardDriftBanner.tsx`,
`src/lib/health/deep-checks.ts:937`, to actually consume the signal this unit adds
and to render the banner ONLY when it fires) is a SEPARATE build on
`blackceo-command-center` and is not touched by this change -- see "What is still
owed" below.

## The defect class (A7)

**What it looked like:** a participant is durably written to the Anthology
engine's ledger (`anthology_state.py`, the sole writer) but never gets a Command
Center board card -- invisible to the producer's Gate Panel -- with no error
anywhere. The v5.4.0 drift-detection machinery
(`checkAnthologyBoardProjection()` + `BoardDriftBanner.tsx`, both already shipped
in `blackceo-command-center`'s `src/components/anthology/`) could DETECT this
drift and render a banner, but detection was never linked to an actual repair
attempt -- "detection is not repair," the framing GK-17 names directly.

## Root cause (traced against the code, this build; UNVERIFIED against a live
## incident until an operator reproduces one -- see the honesty caveat in the unit
## spec)

The normal production path is: the gateway webhook (`/hooks/anthology-intake`)
calls `intake_router.py` directly with the raw payload. `intake_router.py`:

1. Verifies the route secret, validates the payload, resolves `contact_id` /
   `anthology_id`, and -- for a new participant -- calls
   `anthology_state.py upsert-participant` **synchronously**. This commit is
   durable before anything else happens (`scripts/intake_router.py:840-859`).
2. Marks the intake claim `"routed"` (`dedup.finalize(fp, "routed", ...)`,
   `intake_router.py:872`) -- "even if the box dies now the daily tick resumes."
3. Acknowledges the webhook caller (`< 2` seconds, per the acknowledge-budget
   doctrine) and spawns the REST of the pipeline via
   `spawn_stage_detached()` (`intake_router.py:572-608`):
   `subprocess.Popen(argv, ..., start_new_session=True, close_fds=True)` --
   **fully detached, fire-and-forget, never waited on, never retried by its
   parent.** stdout/stderr land in a per-run `stage-spawn.log` nobody watches.

The spawned continuation is `stage_s0_intake.py`, whose ordered WIRING
(`scripts/stage_s0_intake.py:48-53`) is: `intake_router.py` (skipped in this
replay path -- already routed) -> `anthology_state.py` (confirm cursor, idempotent
no-op) -> **`mc_board.py ensure`** (the card mirror, WIRING[2]) -> then the
holdable `drive-tree-provision.py` (WIRING[3]).

**The gap:** if the DETACHED process dies at ANY point before it reaches
WIRING[2] -- an `OSError` launching the interpreter, an uncaught exception in an
earlier step, an OOM kill, a box restart mid-run, a permissions error writing the
run directory -- the participant's ledger row already exists (step 1, above, was
synchronous and already committed) but the board card is **never created**, and
nothing surfaces the failure: the webhook caller already got `200 routed`, and the
only thing that would show the failure is a `stage-spawn.log` file under
`state/runs/s0/<key>/` that no automated process reads.

**The only pre-existing recovery** was the once-daily `mc_board.py reconcile` tick
(wired via `anthology-smoke-test.py`'s `reconcile_board()` step, "finding A2",
registered onto the box's ONE cron entry by `provision-anthology-client.sh` step
8). Two compounding gaps on the repair side, both fixed by this unit:

- **The daily tick's own wrapper reported success from the subprocess exit code
  alone.** `mc_board.py reconcile` is fail-soft BY DESIGN -- it always exits `0`,
  even when some subjects could not actually be repaired (a board outage, an auth
  rejection, a permanent refusal). `reconcile_board()`'s pre-fix shape
  (`rc == 0 -> {"status": "reconciled"}`) could not tell "every card genuinely
  landed" apart from "the sweep merely ran" -- the daily tick's own report could
  claim `"reconciled"` while participants remained invisible.
- **Detection (CC) and repair (ONB) were never linked by any machine-checkable
  signal.** The drift detector had no way to know whether a repair had already
  been attempted and failed, versus never attempted at all -- so there was no
  principled basis for "banner is the escalation of last resort."

## The fix shipped in this unit (ONB side only)

1. **`59-anthology-engine/scripts/mc_board.py`** -- `cmd_reconcile` is refactored
   into a pure `_reconcile_sweep(bcfg, state_dir, timeout, verbose)` function (the
   CLI is now a thin wrapper) that returns an explicit `"converged": bool` field
   alongside the pre-existing `counts` / `failsoft`: `converged` is `True` iff
   *zero* subjects ended the sweep in `deferred` or `error` -- i.e. every subject
   that needed a repair got one. This is the CONVERGING-REPAIR signal GK-17 asks
   for, and it is the single source of truth `cmd_reconcile`, the daily tick, and
   tests all share.
2. **`59-anthology-engine/scripts/anthology-smoke-test.py`** -- `reconcile_board()`
   now captures `mc_board.py reconcile --json`'s STDOUT (previously discarded) and
   reads its `converged` field back. On exit `0`, the daily tick's
   `board_reconcile` block now reports `status: "unconverged"` -- never
   `"reconciled"` -- when the sweep ran but did not fully converge. This is
   backward compatible: a caller supplying the legacy 2-tuple `(rc, err)` runner
   (no stdout) still gets the pre-existing `"reconciled"` on exit 0, with
   `converged: None` (unknown, never a false escalation).
3. **Tests** (all run FOREGROUND, all green):
   - `mc_board.py --self-test` -- extended to assert `converged is True` for a
     fully-successful sweep, `converged is False` when the board is down for the
     whole sweep, and `converged is True` (vacuously) for a zero-subject sweep.
   - `anthology-smoke-test.py self-test` -- extended with the legacy-2-tuple
     backward-compatibility assertion plus both new capture-runner scenarios
     (converged / unconverged).
   - **`tests/test_a7_selfheal_reconcile.py`** (new) -- the GK-17 BINARY
     acceptance scenario end to end, against a stateful `FakeBoard` that dedupes
     by `idempotency_key` exactly like the real Command Center route:
     - an induced drop (one participant whose `ensure` was suppressed) is fully
       repaired by ONE reconcile pass, with the already-mirrored participant's
       card left untouched;
     - a SECOND reconcile pass creates zero additional cards (idempotent dedupe
       across repeated sweeps);
     - a deliberately-broken repair path (permanent ingest refusal for one
       subject) converges to `False` while the healthy subject in the same sweep
       still lands -- proving the escalation signal fires ONLY when the repair
       path is genuinely broken, never on a merely-mid-flight sweep.

## What is still owed (explicitly out of scope for this ONB-only build)

- **CC side:** `checkAnthologyBoardProjection()` / `BoardDriftBanner.tsx`
  (`blackceo-command-center`, `src/lib/health/deep-checks.ts:937`) must be wired
  to consume this `converged` signal (via whatever channel the daily tick's
  report reaches CC through) and render the banner ONLY when `converged` is
  `False` -- i.e. the banner becomes the last-resort escalation the unit's title
  promises, rather than firing on drift alone. This is a separate builder's unit
  of work on the CC repo.
- **Sub-daily convergence:** `guard-cron-inventory.py` enforces exactly ONE
  recurring cron entry (the daily tick; "no heartbeat entry ever"). This fix makes
  the EXISTING daily cycle genuinely converging and its outcome honestly
  reported; it does NOT add a higher-frequency reconcile trigger. If GK-17's
  "one scheduled cycle" is later read as requiring sub-daily convergence, that
  would need either an on-demand reconcile trigger callable from CC's health
  check (a new, deliberately scoped surface) or a change to the cron-inventory
  guard's "exactly one" invariant -- both are operator/architecture decisions
  outside this unit's repo-side scope.
- **Live reproduction of a real A7 drop:** this unit's root-cause trace is
  derived from reading the shipped code's control flow (cited above with exact
  file:line references), not from an operator-witnessed live incident. The unit
  spec carries this caveat honestly ("the underlying cause is NOT identified
  anywhere yet (UNVERIFIED)"); this document narrows it to a specific, testable
  mechanism but does not claim a live-fleet reproduction.
