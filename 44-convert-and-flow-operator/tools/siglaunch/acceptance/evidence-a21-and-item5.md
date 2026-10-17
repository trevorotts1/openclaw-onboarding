# Evidence — A21 acceptance harness + CR-S82-002 item 5 determination

Room: S44 · Date: 2026-10-16 · Stream: CR-S82-002 evidence package / A21
Basis: full reads this cycle of work/processor/processor.py,
work/processor/test_processor.py, work/store/store.py,
work/events/events.py, work/events/test_events.py,
work/normalizer/normalizer.py, work/DESIGN-S44-04-v1.md,
work/DESIGN-S44-06-v1.md, work/DESIGN-S44-07-v1.md,
work/DESIGN-NOTES-v1.md.

Module-level proof only. This is NOT native proof and is never labeled
live proof.

---

## 1. A21 acceptance harness — results

Harness: `work/acceptance/test_a21_acceptance.py` — drives the real
pipeline (normalizer `ingest` → `DurableProcessor` on the durable
`Store` → `dispatch_marketing`), following the wiring of
`work/processor/test_processor.py`. A recording sender proves the
sender was or was not invoked, not merely that a return string looked
right.

Exact unittest output (`python3 -m unittest test_a21_acceptance -v`,
run from work/acceptance/):

```
test_a_nonbuyer_queued_send_dispatches (test_a21_acceptance.A21AcceptanceTests.test_a_nonbuyer_queued_send_dispatches) ... ok
test_b2_recheck_reads_live_state_at_each_dispatch (test_a21_acceptance.A21AcceptanceTests.test_b2_recheck_reads_live_state_at_each_dispatch) ... ok
test_b_same_queued_send_suppressed_after_purchase (test_a21_acceptance.A21AcceptanceTests.test_b_same_queued_send_suppressed_after_purchase) ... ok
test_c_full_refund_lifts_suppression (test_a21_acceptance.A21AcceptanceTests.test_c_full_refund_lifts_suppression) ... ok
test_d_partial_refund_keeps_suppression (test_a21_acceptance.A21AcceptanceTests.test_d_partial_refund_keeps_suppression) ... ok

----------------------------------------------------------------------
Ran 5 tests in 0.508s

OK
```

**5 tests ran, 5 passed, 0 failures.** Behaviors proven:

- (a) `test_a_nonbuyer_queued_send_dispatches`: a queued marketing
  send for a contact with no purchase dispatches; the sender is
  invoked exactly once.
- (b) `test_b_same_queued_send_suppressed_after_purchase`: the queued
  send object is created first, the purchase lands while it sits in
  the queue, and at dispatch the SAME send is suppressed; sender
  invoked zero times. `test_b2_recheck_reads_live_state_at_each_dispatch`
  sharpens it: the same queued object dispatched before the purchase
  fires (1 sender call); dispatched again after the purchase it is
  suppressed and the sender is NOT invoked a second time — the
  decision is computed from live entitlement state at each dispatch,
  never cached at enqueue.
- (c) `test_c_full_refund_lifts_suppression`: after a full refund
  event revoking both lines, `active_entitlements` is empty and the
  same queued send dispatches again — suppression follows ACTIVE
  entitlement state; no unsuppress job exists or is needed.
- (d) `test_d_partial_refund_keeps_suppression`: after a refund of
  the bump (extra) line only, `active_entitlements == ["ent-main"]`
  and the queued send remains suppressed, sender never invoked.

Existing suites re-run the same session and unaffected: events 17/17
OK, store 7/7 OK, normalizer 12/12 OK, processor 7/7 OK (see the
environment note below for the one transient failure observed and its
cause).

### Environment note (not a code defect)

Mid-session, one processor-suite run reported 5 errors, every one
`sqlite3.OperationalError: database or disk is full` raised while
creating the test database under the system temp dir. Cause verified:
the VM's `/tmp` is a 512M tmpfs at 100% (700K free at inspection),
filled by other work on the box. Re-running with TMPDIR pointed at a
directory on the home filesystem: processor suite 7/7 OK and the A21
harness 5/5 OK. No S44 code defect was found; no test was weakened.

---

## 2. Item 5 determination — entitlement_version source

**Determination in one paragraph:** No entitlement version, revision
counter, or state fingerprint exists in S44's code today — full reads
of store.py, processor.py, and events.py show the entitlement book
carries only per-(tenant, line_ref, entitlement) state
(`active`/`revoked`), and the only version-like values in the system
are the receiver's `request_version`, lease fencing tokens, and the
processor's action-key version constant `"v1"`, none of which is a
per-buyer entitlement revision. S44 therefore supplies item 5 as a
committed deterministic specification (below), precise enough that
S82's implementation and S44's produce byte-identical values from the
same entitlement-book state: `entitlement_version` is `"ev1:"` plus
the lowercase hex SHA-256 of a canonical serialization of exactly the
buyer's entitlement rows in the durable store. The implementing
change is named S44 build work: a `Store.entitlement_version(...)`
read method implementing this canonicalization, emitted on the
fulfillment map. Until that code lands, S82's derived-fingerprint
fallback remains in effect, and S44 does not claim the fallback and
this specification produce identical values today.

### The specification (normative)

Scope: one buyer, identified by (`tenant_id`, `launch_id`,
`contact_ref`) in the durable store (work/store/store.py).

1. Row set R: every row (`line_ref`, `entitlement`, `state`) of the
   `entitlements` table for `tenant_id` whose `line_ref` is in
   `buyer_lines(tenant_id, launch_id, contact_ref)`. Revoked rows are
   INCLUDED — the book preserves history and never deletes — so a
   revocation changes the version.
2. Sort R ascending by (`line_ref`, `entitlement`), comparing UTF-8
   byte sequences.
3. Canonical string (␟ = U+001F, ␞ = U+001E):
   `tenant_id` ␟ `launch_id` ␟ `contact_ref` ␞, followed by the rows
   in sorted order, each encoded `line_ref` ␟ `entitlement` ␟ `state`
   and separated by ␞. With zero rows the string ends at the first ␞.
   (`state` is exactly the stored value: `active` or `revoked` —
   the only two states the book writes.)
4. `entitlement_version = "ev1:" + sha256_hex(canonical as UTF-8)`,
   lowercase hex. The `ev1:` prefix versions the algorithm; any future
   canonicalization change mints a new prefix and never silently
   redefines `ev1:`.

Change semantics: the value changes exactly when R changes — a new
(line, entitlement) grant, a revocation, or a re-grant flipping a
revoked row back to `active`. It does NOT change on duplicate event
delivery, on non-granting payment states (pending / failed /
requires_customer_action / unknown), or for any other buyer, launch,
or tenant. It is a pure function of the book's contents for that
buyer, so two implementations applying this specification to the same
book state produce the identical string — which is what S82's dedupe
key `sha256(tenant|location|launch|order_ref|entitlement_version)`
requires of the `entitlement_version` component.

Implementation status: **SPEC ONLY as of 2026-10-16.** Named
implementing change (S44 build work): `Store.entitlement_version(
tenant_id, launch_id, contact_ref) -> str` in work/store/store.py,
with unit tests pinning stability across duplicate delivery, change
on grant / revoke / re-grant, and tenant/launch/contact isolation;
emitted by the fulfillment-map producer (see the CR reply package,
fulfillment-map status section).
