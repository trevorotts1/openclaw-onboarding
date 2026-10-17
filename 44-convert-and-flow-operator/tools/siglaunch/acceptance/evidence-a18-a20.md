# Evidence — A18 + A20 (S44 half) acceptance harness

Harness: `test_a18_a20_acceptance.py` (this directory). Pipeline under
test is the REAL production path — normalizer `ingest` ->
`DurableProcessor` on the S44-05 durable store (SQLite WAL) — with
recording fakes only at the native boundary (the verified-purchase
tag applier and the fulfillment executor). Source files read in full
before building: `processor/processor.py`, `processor/test_processor.py`,
`store/store.py`, `timing/timing.py`, `timing/test_timing.py`,
`events/events.py`, `events/test_events.py`,
`normalizer/normalizer.py`, `normalizer/test_normalizer.py`,
`DESIGN-S44-07-v1.md`.

**Level honesty: L1/L2 module-level proof with recording fakes at
the native boundary; NOT native (L4) proof.**

## A18 — Rapid extra purchases not blocked by long waits

Verdict: PROVEN at L1/L2.

- Five purchases fired back-to-back through ingest+process: base
  (main) then four distinct extras (upsell_1, upsell_2, downsell_1,
  bump), each its own verified event/transaction on the same order.
- After EVERY process() return, that line's `initiate_fulfillment`
  action was already in the ledger in state `claimed` — present
  immediately, gated by nothing.
- The fulfillment worker never ran during the sequence (all five
  fulfillment actions still `claimed` at the end), no timing/wait
  step executed anywhere, and still: all five entitlements active
  (`ent-bump, ent-d1, ent-main, ent-u1, ent-u2`), all five
  `grant_access` actions `done`, tag seam fired once per purchase
  (5 applier calls). Later purchases were not blocked by earlier
  purchases' downstream fulfillment or sequences.
- Grounding in the timing module: waits exist only as named steps of
  per-workflow timing contracts (S44-08 comparator). The harness
  asserts a representative contract's wait steps (`wait-3d`,
  `wait-cart`) are disjoint from every processor action type
  (`grant_access`, `initiate_fulfillment`,
  `apply_verified_purchase_tag`) — no wait binds the fulfillment
  action class.
- Wall time for the full five-purchase ingest+process sequence in
  the captured evidence run: **A18_WALL_SECONDS=1.4893**
  (asserted bound: < 5.0 s — the bound proves absence of waits, not
  machine speed; the figure is SQLite fsync time on a loaded box).
  Repeat runs measured 1.2190 s, 1.1012 s, 3.2075 s — all green.

## A20(a) — Tab close: base fulfillment survives with no page visit

Verdict: PROVEN at L1/L2.

- The flow contains NO page/thank-you observation at all — no page
  object, call, or input exists in the test. A single purchase event
  (buyer "closes the tab" right after checkout) is ingested and
  processed; from the event alone: `ent-main` active,
  `grant_access` action `done`, `initiate_fulfillment` action
  `claimed`, and `DurableProcessor.fulfill` then executes it to
  `done` with payload `{"slot": "main"}`; a second fulfill returns
  `already_done` and does not re-execute. Fulfillment is an
  event-driven claimed ledger action, never a thank-you-page
  behavior (DESIGN-S44-07 section 1).

## A20(b) — Extra failure: base grant intact

Verdict: PROVEN at L1/L2.

- Base purchase granted first. A later extra-offer event (upsell_1,
  its own transaction) arrives with verified payment status
  `failed`: ingest accepts it, process returns `no_grant:failed`.
- After it: `ent-main` still the only active entitlement, base line
  still carries an active entitlement, base `grant_access` still
  `done`, base `initiate_fulfillment` still `claimed` (and still
  executes to `done` afterwards); the failed extra has NO
  grant_access and NO initiate_fulfillment action; no extra tag
  application; no parked (unknown) actions; no quarantine rows.

## A20(c) — Single-send: page observation + event worker

Verdict: PROVEN at L1/L2.

- Convergence point, per the implementation: the order-completion
  effect is the claim-gated `apply_verified_purchase_tag` action
  (key `(tenant, txn, "*", action_type, version)`) — the handler
  workflow's entry seam (DESIGN-S44-06 section 1) whose application
  starts the onboarding/confirmation flow. S82's page emits no send;
  its `confirmation_shown` observation consumer is modeled here
  funnelling into the SAME `store.claim_action` key, which is the
  dedupe mechanism the implementation actually provides: the ledger
  admits exactly one claim winner, and only the winner fires the
  native-boundary applier.
- Both orders run as subTests on fresh stores (two-line purchase,
  main + bump):
  - worker-first: process -> page observation returns
    `already_claimed` -> full worker re-process of the same event;
  - page-first: observation fires -> process -> observation returns
    `already_claimed`.
- In both orders: the recording applier was called EXACTLY once
  (`[("contact-1", "siglaunch:purchased:main")]`), the durable
  ledger holds EXACTLY ONE row for the send action (counted by
  direct SQL read-back of the actions table), its state is `done`,
  `grant_access` rows are exactly 2 (one per line), and both
  entitlements are active.

## Exact unittest output (captured run, 2026-10-16)

```
test_a18_rapid_extra_purchases_not_blocked_by_long_waits (test_a18_a20_acceptance.A18A20Acceptance.test_a18_rapid_extra_purchases_not_blocked_by_long_waits) ... ok
test_a20a_tab_close_base_granted_without_any_page_visit (test_a18_a20_acceptance.A18A20Acceptance.test_a20a_tab_close_base_granted_without_any_page_visit) ... ok
test_a20b_extra_failure_leaves_base_grant_intact (test_a18_a20_acceptance.A18A20Acceptance.test_a20b_extra_failure_leaves_base_grant_intact) ... ok
test_a20c_single_send_page_and_worker_observe_same_completion (test_a18_a20_acceptance.A18A20Acceptance.test_a20c_single_send_page_and_worker_observe_same_completion) ... ok

----------------------------------------------------------------------
Ran 4 tests in 5.349s

OK
A18_WALL_SECONDS=1.4893
```

Run command: `python3 -m unittest test_a18_a20_acceptance -v`
from `rooms/S44/work/acceptance/`. Suite additionally run 3x before
the captured run: OK, OK, OK (4 tests each, A20c carrying 2 subTests).

## Environment note (not an implementation defect)

This box's `/tmp` tmpfs is 100% full (512M used, 812K free at
harness time; other projects' scratch). The first harness draft,
which used the default `/tmp` tempdirs like the existing suites,
intermittently failed Store setup with
`sqlite3.OperationalError: database or disk is full` at
`PRAGMA journal_mode=WAL` — an environment failure, not pipeline
evidence (A20c passed standalone at the same moment). The harness
therefore anchors its per-test scratch databases in a self-cleaning
`.scratch/` directory on the workspace filesystem. No implementation
file was changed. Note the pre-existing room suites share the same
`/tmp` exposure while that tmpfs stays full.

## Defects found

None in the implementation. Every behavior A18 and the S44 half of
A20 require was supported by the pipeline as written; no test was
weakened and no behavior was faked.
