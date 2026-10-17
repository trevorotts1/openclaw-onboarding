# Evidence — fulfillment-map producer + ev1 entitlement_version

Room: S44 · Date: 2026-10-16 · Stream D (CR-S82-002 reply follow-through)
Basis: full reads this cycle of the CR-S82-002 reply package,
work/store/store.py + work/store/test_store.py,
work/processor/processor.py + work/processor/test_processor.py,
work/events/events.py, work/normalizer/normalizer.py,
work/DESIGN-S44-07-v1.md, work/acceptance/evidence-a21-and-item5.md,
and S82's contract file (see §1).

**Honesty label: this is module-level (L1/L2) work against the
durable store with the real processor pipeline. It is NOT native
(L4) proof, and nothing here is labeled live proof.**

---

## 1. S82 contract file — OBTAINED

Fetched via the GitHub read path (~/workspace/bin/gh_api.py, Git Data
API) and read in full before building:

- Repo: `trevorotts1/openclaw-onboarding`
- Path: `82-signature-thank-you/references/s44-fulfillment-continuity.md`
- Blob SHA: `db6efbbe8b5b47facd708b0e865d09e866dd9857`
- Size: 6676 bytes
- Verbatim copy with provenance header:
  `work/fulfillment_map/s82-contract-copy.md`

Consequences: the six `next_action` classifications are known
firsthand (contract §2): **access, download, manage_purchase,
support, schedule_included_service, noncommercial_next_step** — the
reply package's open ask ("S82 to restate the six names") is closed
by this fetch and S82 does not need to restate them. The map shape is
the contract's: keyed by entitlement ID, entries `{state,
delivery_url, next_action}`. The producer's vocabulary is BOUND to
these six; no fallback vocabulary was needed.

## 2. What was built

1. `Store.entitlement_version(tenant_id, launch_id, contact_ref)`
   (work/store/store.py) — the named implementing change from the CR
   reply package §5, implementing the committed ev1 specification
   exactly (row set = entitlements ⋈ buyer_lines for the buyer,
   revoked rows included, UTF-8-byte sort by (line_ref,
   entitlement), U+001F/U+001E canonical string, `"ev1:"` + lowercase
   SHA-256 hex). Plus three read-only helpers the producer uses:
   `buyer_entitlement_rows`, `line_action_states`, `stored_events`.
2. `work/fulfillment_map/fulfillment_map.py` —
   `build_fulfillment_map(store, tenant_id, launch_id, contact_ref)`
   returning `{tenant_id, launch_id, contact_ref,
   entitlement_version, entitlements: {<entitlement_id>: {state,
   delivery_url, next_action}}}`. The inner dict is exactly the
   contract §2 map shape. Pure read model: SELECTs only.
   `delivery_url` is always None — the durable store carries no
   delivery-URL source today; null is contract-valid. Named as an
   open item in §5.

## 3. Test results (exact counts, this session)

All runs with TMPDIR pointed at a workspace scratch dir (the box's
/tmp tmpfs is 100% full; see the A21 evidence note's environment
finding — the same precaution applied here).

New suites:

```
work/store:        Ran 14 tests — OK   (7 pre-existing test_store
                                        + 7 new test_entitlement_version)
work/fulfillment_map: Ran 16 tests — OK
```

Regression (after the store.py change):

```
work/processor:    Ran 7 tests  — OK
work/events:       Ran 17 tests — OK
work/acceptance:   Ran 13 tests — OK
work/normalizer:   Ran 12 tests — OK
work/receiver:     Ran 19 tests — OK
work/timing:       Ran 5 tests  — OK
work/provisioning: Ran 3 tests  — OK
```

Pre-existing total was 70 module tests + 13 acceptance = 83; now
93 module tests + 13 acceptance = 106, all green.

What the new tests pin:

- **entitlement_version**: zero-row buyer and a two-row worked
  example match SHA-256 values computed independently from the spec
  text (canonical strings built from literals in a separate process,
  hard-coded in the test); change on grant / revoke / re-grant
  (re-grant returns to the granted value, since the row set is again
  identical); stability across a duplicate grant and across duplicate
  event delivery at pipeline level; tenant / launch / contact
  isolation; rows on unregistered lines excluded; UTF-8 byte sort
  order (incl. a non-ASCII line ref).
- **fulfillment map**: granted (fulfillment done → `access`),
  pending-in-flight (claimed → `noncommercial_next_step`),
  pending-parked (fulfillment action `unknown` → `support`),
  revoked after full refund (→ `manage_purchase`), partial refund
  revoking only the extra line, per-buyer isolation, unknown buyer →
  empty map + zero-row version, map emission never writes (row
  counts of every table identical before/after two builds), the
  bound vocabulary is exactly the contract six, and the vocabulary
  check raises `VocabularyError` on out-of-vocabulary names (a
  new-charge-style action is the pinned example).

### States reached at read-model level only — named justification

`not_granted` and payment-`pending` were NOT produced through the
pipeline in these tests; they are constructed directly in the store
(a registered buyer line plus a recorded non-granting inbox event).
Justification: `DurableProcessor.process` registers buyer lines only
on the succeeded path, which also grants every entitlement on the
line — so within a registered buyer's scope every unit normally has
a book row, and a failed/pending FIRST purchase creates no buyer
registration at all, hence no buyer view for those states to attach
to. This is a real reachability property of the current pipeline,
not a test shortcut: the producer's branch-3 assembly (latest stored
event decides, book state always outranks event history) is
implemented for contract completeness and pinned here at the level
where it can honestly be exercised.

## 4. next_action decision table (as implemented)

Unit = one (line, entitlement). Per-entitlement aggregation takes
the strongest unit state (granted > pending > revoked > not_granted;
ties by smallest line_ref) and that unit's next_action.

| Unit outcome | next_action |
|---|---|
| granted (book active, fulfillment `done`) | `access` |
| pending, fulfillment action parked `unknown` | `support` |
| pending, fulfillment still `claimed` (in flight) | `noncommercial_next_step` |
| pending, payment not settled (no book row) | `manage_purchase` |
| pending, defensive succeeded-event-no-row | `noncommercial_next_step` |
| not_granted, payment `failed` | `manage_purchase` |
| not_granted, `requires_customer_action` | `manage_purchase` |
| not_granted, payment `unknown` | `support` |
| not_granted, defensive refund-no-row | `manage_purchase` |
| revoked | `manage_purchase` |

Rationale: granted produces an access block per the contract, so
`access`. A parked unknown outcome or an unverifiable payment leaves
no honest self-serve step, so `support`. In-flight fulfillment after
a settled payment asks nothing of the buyer, so
`noncommercial_next_step`. Payment-side problems and the post-refund
remainder are resolved on the purchase itself, so `manage_purchase`.

**Unemitted vocabulary slots:** `download` and
`schedule_included_service` are never selected. The durable store
carries no per-entitlement delivery-kind metadata (downloadable vs
access vs bookable service), so selecting either would be a guess.
They become selectable only when a launch-record binding supplies
the delivery kind per entitlement. Named, not papered over.

## 5. Defect found and fixed during this stream

First run of the new store tests failed one case:
`test_zero_row_buyer_matches_independent_pin`. The implementation's
`rs.join([header])` produced a canonical string WITHOUT the trailing
U+001E for a zero-row buyer, while the spec (§5 step 3: "With zero
rows the string ends at the first ␞") requires header + U+001E. The
produced hash matched SHA-256 of the header alone (verified
independently), confirming the implementation — not the independent
pin — was wrong. Fixed in `Store.entitlement_version` (canonical is
now header + RS + RS-joined rows, or header + RS when empty); all 14
store tests then pass, including the byte-exact worked example,
which had passed throughout because the join is correct whenever
rows exist. No test was weakened; the pin caught a real
canonicalization bug before the value ever reached S82.

## 6. Open items

1. `delivery_url` is always null: no delivery-URL source exists in
   the durable store. Whoever owns fulfillment delivery (the
   downstream executor) must supply URLs, or a launch-record binding
   must be added, before the map can carry them.
2. `download` / `schedule_included_service` await a per-entitlement
   delivery-kind binding (see §4).
3. Items 1–4 of CR-S82-002 still await the L4 input named in the
   reply package §6 (authorized test location) — unchanged by this
   stream. This stream closes the reply package's two named S44
   build items: the item-5 implementing change and the
   fulfillment-map producer (states, entitlement_version,
   classifications pinned by tests), at module level.
4. The map envelope wraps the contract's map under an
   `entitlements` key alongside `entitlement_version` and the buyer
   identity; if S82's resolver wants the bare map only, the producer
   can emit `map["entitlements"]` directly — a one-line change once
   S82 confirms which side of the seam serializes.
