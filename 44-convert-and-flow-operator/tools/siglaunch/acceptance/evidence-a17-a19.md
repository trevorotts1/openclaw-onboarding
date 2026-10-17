# Evidence — A17 and A19 acceptance harness

Harness: `test_a17_a19_acceptance.py` (this directory). It drives the
REAL production pipeline — `normalizer.ingest` into the durable store,
then `DurableProcessor.process` — wired exactly as in
`work/processor/test_processor.py`. The only fake is at the native
boundary: the verified-purchase tag applier is a recording callable
(the engine-side seam of DESIGN-S44-06 section 1). All assertions read
durable state back from the store (public API plus row counts taken
directly from the store's SQLite file).

## Honesty label

**This is L1/L2 module-level proof against the implemented pipeline
with recording fakes at the native boundary; it is NOT native (L4)
proof.** No GoHighLevel / Convert and Flow system was touched, no live
order was read back, and nothing here evidences live behavior. It
proves the S44 pipeline's semantics (dedup, per-line grants, action
idempotency) as implemented in `work/{normalizer,store,processor}`.

## What each case proves

### A17 — "Original plus bump event does not drop the bump"
`A17OriginalPlusBump.test_original_plus_bump_event_does_not_drop_the_bump`

One order event (evt-1, order ord-1, txn txn-1) whose lines are
[main (li-m / ent-main), bump (li-b / ent-bump)] is ingested and
processed. Assertions:
- per-line state: `line_has_active_entitlement` is true for BOTH li-m
  and li-b; the tenant's active set is exactly
  `["ent-bump", "ent-main"]`, with an explicit named regression
  assertion that `ent-bump` is present;
- the buyer record links BOTH lines (`buyer_lines == ["li-b", "li-m"]`);
- the fulfillment action set includes both lines: one
  `initiate_fulfillment` action per line, each executed via
  `processor.fulfill` with a recording executor, receiving payloads
  `{"slot": "main"}` and `{"slot": "bump"}` respectively;
- both per-line `grant_access` actions are `done`; the purchase tag
  was applied exactly once, with the verbatim Phase-A string.

### A19 (duplicate) — same verified event delivered twice
`A19Duplicates.test_duplicate_redelivery_produces_zero_additional_effects`

After a first full processing (baseline: 1 inbox row, 5 action rows —
2 grants + 2 fulfillments + 1 tag — 2 entitlement rows, 1 buyer,
2 buyer_lines, 1 tag call), the identical read-back is delivered
again. Ingest returns `"duplicate"` (dedup by verified provider event
identity, before the processor can see it), and a full durable
snapshot (table row counts, active entitlements, buyer lines, every
action's state, tag-call list) is byte-identical to the baseline.

`A19Duplicates.test_reprocessing_an_accepted_event_is_effect_free`

A worker retry re-invokes `process()` on the already-accepted event.
Because every effect is a claimed ledger action, the second run
reports `actions_created == 0`, the durable snapshot is unchanged,
and the tag applier is not called again.

### A19 (out-of-order) — extras before the original, combined event last
`A19OutOfOrder.test_out_of_order_delivery_unions_lines_without_duplicates`

Three distinct provider event identities for the same order/transaction
(the implementation's model: dedup is by event identity, never by
order alone — one order can gain later extras; effects are keyed by
tenant + transaction + line + action type + version):
1. the bump line's event arrives FIRST (grants only ent-bump);
2. the main line's event arrives SECOND (active set becomes the union);
3. the ORIGINAL combined [main, bump] event arrives LAST — accepted
   by ingest (it is not a duplicate delivery), yet it changes nothing.

Final state is exactly the union: active entitlements
`["ent-bump", "ent-main"]`, 2 entitlement rows, 2 grant actions,
2 fulfillment actions, 1 tag action, 3 inbox rows, buyer linked to
both lines, and the tag applier called exactly once across all three
deliveries. No line is granted twice and no fulfillment is duplicated.

## Exact unittest output

Primary run — `python3 -m unittest -v` from this directory, at a
moment when it collected only this harness (4 tests):

```
test_original_plus_bump_event_does_not_drop_the_bump (test_a17_a19_acceptance.A17OriginalPlusBump.test_original_plus_bump_event_does_not_drop_the_bump) ... ok
test_duplicate_redelivery_produces_zero_additional_effects (test_a17_a19_acceptance.A19Duplicates.test_duplicate_redelivery_produces_zero_additional_effects) ... ok
test_reprocessing_an_accepted_event_is_effect_free (test_a17_a19_acceptance.A19Duplicates.test_reprocessing_an_accepted_event_is_effect_free) ... ok
test_out_of_order_delivery_unions_lines_without_duplicates (test_a17_a19_acceptance.A19OutOfOrder.test_out_of_order_delivery_unions_lines_without_duplicates) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.685s

OK
```

Confirmation runs — the same unmodified harness, run three
consecutive times scoped to this module
(`TMPDIR=<acceptance dir>/.scratch-tmp python3 -m unittest -v
test_a17_a19_acceptance`; see the environment note below for why
TMPDIR was redirected). All three runs: `Ran 4 tests … OK`
(3.381s / 3.432s / 3.158s), each test `ok` in each run.

## Environment note (not an implementation defect)

During this session the shared `/tmp` — a 512M tmpfs — was at 100%
(944K free; consumed by other processes' files, e.g. many `int06-*`
dirs) and at times filled completely mid-run. Under that condition,
ANY suite that creates its SQLite store under a default
`tempfile.TemporaryDirectory()` errors with
`sqlite3.OperationalError: database or disk is full`, raised inside
`Store.__init__` (WAL setup) or at a COMMIT — before pipeline logic
runs. This was observed in the pre-existing, unmodified
`work/processor/test_processor.py` (errors in `setUp`) as well as in
interim discovery runs of this directory. No assertion in any suite
failed for a behavioral reason. The confirmation runs above
therefore pointed TMPDIR at a scratch directory on the workspace
filesystem (created inside this directory, removed afterward); the
harness code itself is unchanged and follows the existing fixture
pattern. On any host with a non-full /tmp, plain
`python3 -m unittest` from this directory reproduces the primary
run (note: bare discovery in this directory now also collects the
sibling A18/A20 and A21 harnesses, which are separate deliverables).

## Defects found

None in the asserted behaviors. Every behavior A17 and A19 name is
supported by the implementation as written
(`work/normalizer/normalizer.py` ingest dedup;
`work/processor/processor.py` claimed-action processing;
`work/store/store.py` PRIMARY KEY enforcement). No test was weakened
and no result was faked; the only failure mode observed was the
environmental /tmp exhaustion documented above.

## Verdicts

- **A17: PASS** at L1/L2 (module-level). The bump line is granted,
  buyer-linked, and fulfilled alongside the main line from a single
  combined event. Native (L4) proof remains outstanding by definition
  of the levels.
- **A19: PASS** at L1/L2 (module-level). Duplicate redelivery is
  stopped at ingest with zero additional effects; re-processing is
  effect-free; out-of-order delivery (extra first, original last)
  converges to exactly the union of lines with each effect occurring
  once. Native (L4) proof remains outstanding by definition of the
  levels.
