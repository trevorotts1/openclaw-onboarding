# S80-06 native binding integration CORE - build notes

Scope: the S80 side of the S79/S06 shared extra-offer interface, built at
interface level (L1) against the DRAFT fixture interface
(`rooms/S79/work/binding/extra_offer_interface.md`). Tree:
`rooms/S80/work/binding/`. Python stdlib only, deterministic, house style
matching the S80 adapters. Nothing outside `work/binding/` was edited;
the adapters/pages integration is a separate worker's job.

## Files

| File | SHA-256 |
|---|---|
| extra_offer_binding.py | 03814223a30cc06c783cdc2f8d7611d034edd8264e1231a8b644f65bcb3b50c1 |
| fixture_driver.py | cfbef715098f8d6d5f6a69d1c538fa907fe919c101eff2bcaaa76c7dad16be6b |
| test_binding.py | 36bb1c7aa4d80ca6db93d44f42740482953dbfe6ecfffcfdb6767075c248ccd9 |
| BUILD-NOTES-BINDING.md | (this file; hash reported with the delivery, not self-referential) |

## What was built

- `extra_offer_binding.py`
  - `PURCHASE_STATES` = the doc 09 section 8 vocabulary exactly (ready,
    validating, submitting, pending_confirmation, paid, failed,
    requires_customer_action, cancelled) with a legal-transition map;
    illegal transitions raise `BindingError`.
  - `BindingContext` (frozen dataclass): tenant/location/launch refs,
    parent order ref + parent verification source, offer id, native
    product/price refs, REQUIRED capability evidence ref, integer
    amount_minor, currency, success/decline/error route refs, billing
    type with recurring terms, and U2 entry context.
  - `NativeDriver` (typing.Protocol): `invoke` / `read_back`;
    `NativeResult` validated against the state vocabulary.
  - `ExtraOfferBinding`: presentation_decision, accept (single-flight,
    read-back-confirmed paid only), decline (routed, zero driver calls),
    reconcile (read-back first), binding_record() in the exact agreed
    shape.
  - `OPEN_QUESTIONS`: interface section 7 Q1..Q9 as data with ids
    S06-Q1..S06-Q6, S44-Q7, S44-Q8, S49-Q9, all status "unresolved".
- `fixture_driver.py`: TEST ONLY deterministic NativeDriver scripting
  paid-with-readback, paid-without-readback, failed, pending-then-paid,
  requires_customer_action, expired/cancelled, and invoke-raises-unknown.
  Never imported by production paths.
- `test_binding.py`: unittest suite, 33 tests, all passing.

## How each interface section is honored

- Section 3 (inputs): BindingContext refuses construction unless every
  input is present and well-formed. **[F2 repair correction,
  2026-10-16: that sentence is now scoped precisely. The binding
  carries and refuses-without: the tenant/location/launch refs, the
  distinct launch revision, the parent order ref and its verification
  source, the offer id, the native product/price refs, the capability
  evidence ref, amount/currency, the success/decline/error route refs,
  the billing-type/recurring-terms pair, the U2 entry context, the
  approved copy references (copy_refs, which must be stated, () only
  when explicitly so), and disclosure_terms_ref, a structured ref to
  the offer's full disclosure data. The disclosure DATA itself
  (discount/tax/shipping policy, trial, installments, beyond the
  amount/currency/recurring terms the binding validates directly) and
  the copy itself live in the adapters/pages layer; the binding
  records the references so the presented terms are the terms the
  binding was made against.]** The parent verification source must
  be one of the adapters' verified sources (imported from
  adapter_common.ADAPTER_VERIFICATION_SOURCES, asserted equal in tests);
  a client-side claim is rejected. capability_evidence_ref is required
  and must be a structured reference (scheme-prefixed or
  separator-structured); a bare assertion word is rejected. Amount is
  integer minor units; recurring bindings require recurring_terms and
  one-time bindings forbid them (mirrors adapter_common disclosure).
- Section 4 (outputs): results use the doc 09 section 8 vocabulary.
  Only a `paid` result CONFIRMED BY read_back settles as paid; a bare
  invoke `paid` without read-back confirmation settles as
  pending_confirmation with failure_kind
  "paid_not_confirmed_by_readback" and stays unresolved. Outcomes carry
  the native transaction ref and route to the context's success/error
  route refs. **[F3 repair correction, 2026-10-16: two outputs listed
  in interface section 4 are NOT emitted by this core, and the
  paragraph above must not be read as claiming them: (1) the
  normalized extra-purchase event for S44 - not emitted; its shape is
  blocked on open questions S44-Q7/Q8, and inventing it would have
  been worse than omitting it; (2) the billing display audit result -
  not emitted; it is owned by the pages/checker layer plus S06
  evidence at L3. binding_record()'s shape is unchanged by this
  correction.]**
- Section 5 (disclosure): presentation_decision(True) offers one-click;
  False or None (unknown) DISABLES the one-click route and records the
  approved-fallback requirement
  (approved_standard_checkout_fallback_with_clear_disclosure_and_user_choice),
  citing open question S06-Q5 - unknown capability is never silently
  treated as supported (same doctrine as S79 capability_matrix.py).
  accept() refuses to run after a disabled presentation decision.
  Decline is a normal routed outcome to decline_route_ref, never an
  error state, with zero driver calls.
- Section 6 (no-rollback): the parent purchase is a read-only
  observation. The binding snapshots it (deep copy) at construction and
  exposes no method that mutates it (the public API surface is pinned by
  test). Every AttemptOutcome carries parent_purchase_unaffected and
  the observed parent state; tests prove the parent object is
  byte-identical (canonical JSON) after accept-success, accept-failure,
  decline, pending, and requires-action outcomes. Unknown outcomes
  (invoke raises, unconfirmed paid, pending) mark the attempt
  unresolved: accept() retries are refused and decline() is refused
  until reconcile() resolves the attempt by read-back FIRST.
- Section 7 (open questions): Q1..Q9 are data, all "unresolved".
  binding_record() reports native_action_id=None and
  binding_status="interface_conformant_pending_s06". No native action
  ID, element name, or vendor fact is invented anywhere in the tree.
- Section 8 (proof boundary): see the honest scope statement below.

Composition with existing S80 code: verification-source vocabulary is
imported from adapter_common (not re-declared); the single-flight guard
is routing_state.PaymentAttemptGuard (accept goes through
begin_attempt/release_attempt, so a re-entrant accept during invoke
raises - proven by test).

## Design decisions where the interface left room

1. Read-back is mandatory proof for paid even though S06-Q1 (how a
   verified success is surfaced) is unresolved: the binding takes the
   stricter reading of interface section 4 ("only a verified native
   success result counts as paid"), so if S06 later confirms a purely
   synchronous verified result, only the driver's read_back
   implementation changes, not this core.
2. In `_settle`, a paid read-back arriving via reconcile() triggers one
   confirming read-back through the same settle path; harmless with a
   real read-back (idempotent read) and keeps one code path for "paid".
   **[F8 repair note, 2026-10-16: SUPERSEDED. reconcile() now passes
   its read-back result into _settle with confirmed=True, so a paid
   reconcile performs exactly ONE read-back. The invariant is
   unchanged - a paid settle still requires a result that came from
   read_back, never a bare invoke result; the read-back reconcile
   itself performed IS that confirmation. Proven by
   test_paid_reconcile_performs_exactly_one_readback.]**
3. Structured-ref rule for capability_evidence_ref: scheme-prefixed
   (e.g. `native:...`, `ledger:...`, `https://...`) or
   separator-structured ids are accepted; bare words are not. This
   mirrors the S80-01..03 validator's structured-evidence standard at
   the string level; authenticity of the ref remains S06's evidence
   (S06-Q2).
   **[F6 repair note, 2026-10-16: TIGHTENED. capability_evidence_ref
   now requires a recognized scheme prefix - native:, ledger:,
   provider-event:, s44:, catalog:, request:, graph:, or https://
   (EVIDENCE_REF_PREFIXES in the module). Merely separator-structured
   strings such as "a-b" or "some/path" are now REJECTED for this
   field. The check remains syntactic; authenticity of the ref is
   still S06's evidence (S06-Q2). Other structured-ref fields
   (disclosure_terms_ref, copy_refs entries) keep the general
   structured-ref rule above.]**
4. accept() may start from ready, failed (a KNOWN failure - a new
   attempt), or requires_customer_action (customer acted - resubmit).
   It can never start from pending_confirmation/submitting (in-flight
   or unresolved) or paid/cancelled (terminal).
5. Non-paid definitive outcomes route to error_route_ref;
   requires_customer_action also routes there as the recoverable
   continuation (its dedicated native destination configuration is
   S06-Q4).

## Tests

Run from `rooms/S80/work/binding/`:

    python3 -m unittest test_binding -v     (or: python3 test_binding.py)

Result at build time: **33 tests, all OK** (0 failures, 0 errors).
Coverage: state vocabulary + transition legality (incl. illegal
transition raising on the binding); unverified parent source rejected;
verification-source set equal to the adapters'; missing/unstructured
capability_evidence_ref rejected; recurring-terms rules; amount/currency
validation; capability True/False/None presentation decisions with
fallback recorded; accept refused after disabled presentation;
double-accept single-flight (re-entrant driver) and no accept after
paid; paid requires read-back; failed known-and-retryable;
requires_customer_action and cancelled outcomes; deterministic
idempotency keys; unknown outcome blocks retry until reconcile;
reconcile-then-paid; decline refused while unresolved; decline with
zero driver calls; no-rollback byte-identity across five outcome kinds;
public API surface pinned; U2 contexts from both entry paths; open
questions exact; binding_record() shape exact.

## Honest scope statement

This is interface-level (L1) integration only: the binding core conforms
to the DRAFT S79/S06 interface and is proven against a TEST-ONLY fixture
driver. It is NOT installed proof. Real native action IDs and installed
(L3/L4) proof remain S06 work, gated on answers to open questions
Q1..Q6 and an approved GHL test location. binding_record() says exactly
that: native_action_id=None,
binding_status="interface_conformant_pending_s06".

---

## Repair appendix - review-S80-06-binding-core findings F1-F8 (2026-10-16)

Scoped repair of the independent review's findings F1-F7, plus the
optional F8. The review file itself was not edited. No original test
was deleted or weakened; the suite was extended only. Where the F1/F2
repairs changed what a correct caller must do (record an offered
presentation decision before accept(); state the new section 3
fields), the existing flow tests were updated to do exactly that -
every original assertion stands unchanged. binding_record()'s output
shape is FROZEN and byte-identical (test_binding_record_shape_exact
passes unmodified). fixture_driver.py is untouched.

Post-repair file hashes (the Files table at the top of these notes
predates the repair; the two changed files' hashes there are
superseded by these):

| File | SHA-256 (post-repair) |
|---|---|
| extra_offer_binding.py | 4502b255670312d66b864c60eb7219b3dbbbc971d55c8ccda8f0f557b8b7a19d |
| fixture_driver.py | cfbef715098f8d6d5f6a69d1c538fa907fe919c101eff2bcaaa76c7dad16be6b (unchanged) |
| test_binding.py | 79a3ae99a3aa2ac91c233422ba5e844dc6d42159fb7f59aab73a1fc8708f615b |

Tests after repair: **50 tests, all OK** (33 original + 17 new),
run 2026-10-16: `python3 -m unittest test_binding` - Ran 50 tests, OK.

### Finding-by-finding closure

| Finding | Status | What changed |
|---|---|---|
| F1 (medium) | CLOSED | accept() now refuses with BindingError when NO presentation decision has been recorded, and (as before) when the recorded decision did not offer one-click. The capability gate is binding-enforced, not caller-discipline. New tests: test_accept_without_presentation_decision_raises (zero driver calls, state stays ready), test_accept_after_offered_decision_proceeds. The pre-existing test_accept_refused_after_disabled_presentation stands. |
| F2 (medium-low) | CLOSED | BindingContext gained three validated fields: launch_revision (non-empty, and rejected if it merely repeats launch_ref), copy_refs (tuple of structured refs; the field has NO default - callers must state it, () allowed only when explicitly passed), disclosure_terms_ref (required structured ref to the offer's full disclosure data; the data itself lives in the adapters/pages layer). The section 3 claim in these notes is corrected in place, marked as the F2 repair, scoping exactly what the binding carries vs where the rest lives. New tests: TestSection3Fields (4 tests). |
| F3 (low-medium) | CLOSED (notes) | A marked F3 correction is appended to the section 4 paragraph above, listing the two section 4 outputs this core does NOT emit: the normalized S44 extra-purchase event (blocked on S44-Q7/Q8) and the billing display audit result (owned by the pages/checker layer + S06 evidence at L3). binding_record()'s shape was NOT changed. |
| F4 (low) | CLOSED | ExtraOfferBinding accepts an optional guard=None constructor parameter (default composes its own PaymentAttemptGuard - composition unchanged). New test test_injected_held_guard_surfaces_route_error injects an already-held guard and proves accept() surfaces the guard's routing_state.RouteError before any state change or driver call; test_default_construction_composes_own_guard pins the default. INTEGRATOR NOTE: both BindingError (contract violations) and routing_state.RouteError (single-flight guard refusal) can surface from accept(); the pre-existing re-entrant test exercises the state gate, and this repair's injected-guard test exercises the guard itself - each mechanism is now proven by its own test. |
| F5 (low) | CLOSED | New TestU2Flows: for EACH entry path (from_upsell_1, from_downsell_1) an accept-through-read-back paid flow and a decline flow, all on offer TEST-OFFER-U2, asserting paid state, read-back confirmation, routes, txn ref, zero decline driver calls, and the entry context carried on the binding (4 tests). |
| F6 (low) | CLOSED | capability_evidence_ref now requires a recognized scheme prefix (native:, ledger:, provider-event:, s44:, catalog:, request:, graph:, https://) via EVIDENCE_REF_PREFIXES; a bare dashed string like "a-b" is REJECTED (previously accepted). Marked F6 note appended to design decision 3. Honesty statement stands: the check is syntactic only; authenticity remains S06's evidence under S06-Q2. New tests: TestCapabilityEvidenceScheme (2 tests). |
| F7 (low) | CLOSED | Decline is now terminal for the binding instance: after decline(), accept() raises BindingError and a second decline() raises BindingError (a declined presentation needs a fresh binding). decline() still records the normal routed outcome exactly as before, and the existing decline tests stand (state remains "ready" after a decline; terminality is enforced by the binding, not by a state change). New tests: test_accept_after_decline_raises, test_second_decline_raises. |
| F8 (info, optional) | CLOSED (cheap fix was clean) | reconcile() passes its read-back result into _settle with confirmed=True, so a paid reconcile performs exactly ONE read-back instead of two. The read-back-confirmed-paid invariant is NOT weakened: a paid settle still requires a result that came from read_back - reconcile's own read-back is that confirmation, and the accept path still performs its confirming read-back on every invoke-paid. Design decision 2 carries a marked F8 supersession note. New test: test_paid_reconcile_performs_exactly_one_readback (accept of pending performs 0 read-backs; the paid reconcile brings the total to exactly 1). |

### What did NOT change

- binding_record() output: byte-identical shape and values.
- PURCHASE_STATES vocabulary, TRANSITIONS, OPEN_QUESTIONS: untouched.
- The public API surface is unchanged in names (the constructor gained
  one optional keyword, guard=None); test_binding_exposes_no_parent_mutator
  still passes - constructor parameters are not part of the pinned
  instance-attribute surface it asserts.
- Proof boundary: still L1 only. S80-06 is NOT completed by this
  repair; L3 native install remains gated on S06 answers to Q1-Q6 and
  an approved GHL test location.
