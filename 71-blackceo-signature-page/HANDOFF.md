# Next-Page Handoff Contract (Signature Launch S71-05)

**Owner:** S71 (Skill 71, BlackCEO Signature Page). **Governing packet
docs:** 02 (Shared Contracts and Architecture) section 6 and section 4,
07 (Skill 71 Landing Page Update Spec) sections 4, 5, 8 and 10,
16 section 1 and section 8, 18 rows A06/A07. **Status:** the contract
leg is implemented in this skill. The verified-submission leg is NOT
implemented here: it closes only when the S06 delivery adapter and
the S71-08 seam execute against a real native form (see "What S06
and S71-08 must still supply").

## The contract

A run invoked under a Signature Launch carries `page-request.json`
(doc 02 section 6) in its run directory. For such a run, the stage
gate's report pass (`scripts/stage_gate.py report`) also emits, in
the same pass:

- `page-result.json` — the doc 02 section 6 result. It returns the
  request ID and input hash, artifact paths with SHA-256 hashes
  (including the stage receipts and `page-handoff.json` itself), the
  actual author and reviewer identities from the run's records, the
  page status, known blockers, the native bindings reference when
  installation executed one, and the proof class. It conforms to
  `references/page-result.schema.json`, this skill's pinned copy of
  the packet schema (the packet's contract, owned by S49, is
  canonical; INTEGRATION reconciles distribution). The builder
  (`scripts/page_result.py`, standalone form
  `scripts/write_page_result.py`) validates every result against
  that schema file before writing and refuses to write an invalid
  one. Both artifacts are validated fully in memory before either
  is written, so a refused emission writes neither file and never
  leaves an orphaned `page-handoff.json` referencing a result that
  does not exist (files from an earlier successful emission are
  left untouched by a refused one). Legacy runs without a
  `page-request.json` emit nothing and behave exactly as before.
  A `page-request.json` that is present but corrupt (unparseable,
  or not a JSON object) is NOT a legacy run: it is an error state.
  The writer exits 2 naming the corruption and the report pass
  fails visibly, instead of silently skipping the run.
- `page-handoff.json` — the next-page handoff record: the approved
  next role and page, the route guard state, the interest popup's
  form mapping, the CTA action map, the popup states, the recorded
  submission evidence, the routing decision with its basis, and the
  S06 install request.

Status values are the doc 02 section 6 vocabulary and none implies
the next: `blocked` (a stage is recorded blocked), `live_verified`
(publish-verify receipt pass), `ready_for_activation` (install
verified, publication held `not_authorized`, per doc 07 section 8),
`installed_test_verified` (ghl-install-test receipt pass),
`locally_verified` (the local production chain through
responsive-html is closed), otherwise `authored`. The status derives
only from the gate's recorded stage receipts; a submission state
never advances it.

## The precondition rule

Routing is the route graph's landing edge: event `interest_submitted`,
guard `verified_native_contact_submit` (packet route-graph schema
and example). The landing page routes onward ONLY after a verified
successful native submission or approved API receipt (doc 07
section 4). A client-side "thanks" state is not contact creation.

The popup component (`interest-popup`, shared design package) emits
`sl:interest-capture` on submit and sits in pending verification; the
`sl:interest-verified` event exists only after the S06 delivery
adapter calls `markVerified()` with the verified receipt. The
run-side recorded equivalent this contract consumes is
`interest-submission.json` in the run directory, and the guard is
satisfied ONLY by a record with event `interest_verified`, state
`verified`, and the adapter's receipt attached. A capture-only or
pending record, a verified claim paired with the capture event, or a
verified event with no receipt NEVER authorizes routing; doc 16
section 8 names forged success an automatic failure. The handoff's
CTA action map records this attribution exactly: the visitor's CTA
click opens the popup (and emits nothing), and the popup form's
submit emits `sl:interest-capture` (the component dispatches that
event inside its submit handler, not on open).

The receipt must also belong to THIS run (receipt binding). When
the receipt is a dict carrying run-identity fields (`tenant_id`,
`location_id`, `launch_id`, `request_id`, `page_id`), every such
field it carries must equal the page-request's value; a receipt
naming a different tenant, launch, or request is another run's
receipt and never authorizes routing here, and the mismatch is
recorded as a blocker. A receipt carrying no identity fields at
all (a bare string receipt, or a dict without identity fields) is
accepted on presence alone. That presence-only acceptance is an
explicit, documented choice, not an accident: no approved adapter
receipt schema exists yet (the receipt is the S06 adapter's output
and its shape is not contracted), and the only receipt shape in
evidence carries no run identity, so refusing identifier-less
receipts would refuse the one known-good form. The handoff's
submission block records which case applied (`receipt_binding`:
`bound`, `contradicted`, or `no_identity_fields`), so a later
contracted receipt schema can tighten presence-only acceptance
without a silent behavior change.

### How "does not authorize routing" is represented

The page-result schema is closed (`additionalProperties: false`) and
carries no routing field, so routing authorization is NOT a
page-result field; inventing one would break the schema. The
contract's own representation is used instead:

- `page-handoff.json` carries `routing: {authorized: false, basis:
  "<the precise reason>"}` whenever the guard is unsatisfied, and
  `page-result.json` references the handoff, with its real SHA-256,
  in its `artifacts` list, so the decision travels with the result.
- When a submission is recorded but unverified (or failed), the
  page result's `blockers` names it: routing is not authorized.

The next role is read from the approved route graph the page-request
references, never invented: the target role of the landing node's
`interest_submitted` edge, restricted to `product_selection`,
`checkout`, or `free_entry` (the approved free-entry destination
when the launch record's `journey_mode` is `free_entry`; doc 07
section 5). `free_entry` is a journey designation, not a node role
(the route-graph schema's role enum has no such value): it is
recorded only when the edge target's own role is the graph's
terminal `thank_you` role under a `free_entry` journey. Any other
target under a free-entry journey keeps its own role and is never
relabeled; a purchase-progression target (`upsell_1`, `downsell_1`,
`upsell_2`) presupposes a purchase a free entry has not made, so
such a route refuses emission entirely, like any other
out-of-vocabulary target. A route target outside that vocabulary
refuses emission entirely (the writer exits 2 and writes no result). A route-graph
file whose SHA-256 no longer matches the page-request's recorded
`route_graph_hash` is the stale next-role hash of doc 07 section 10:
the handoff is emitted with routing unauthorized and the mismatch
recorded as a blocker.

## What S06 and S71-08 must still supply

This leg is producer-side only. To close the verified-submission leg
and the R71H seam (doc 07 section 5: after installation, return
verified form/page IDs and the automation handoff through the actual
delegated S06/S44 route; documentation-only handoff is insufficient):

- **S06 delivery adapter:** consume `sl:interest-capture`; perform the
  actual native submission binding the component's
  `native_field_map` (`first_name`, `last_name`, `email`, `phone`) to
  the native form; call `markVerified(prefix, receipt)` ONLY with a
  verified native submission result or approved API receipt (or
  `markFailed` on failure); write the run's `interest-submission.json`
  in the shape above, receipt attached; record the native bindings
  at install close in `handoff/automation-handoff.json` (IDs only),
  which the page result then references as `native_bindings_ref`.
- **S71-08 (with S44):** the actual delegated execution: S44
  provisions, S06 builds, S44 wires (doc 02 section 7's two-handoff
  model), returning `automation-receipt.json` with real workflow IDs
  and read-backs. An automation file with no executed consumer does
  not close integration (doc 07 section 10).

## Evidence this leg does and does not produce

Per doc 18 section 1 (levels) and section 3 (owners/evidence):

- **Produced:** L0 schema conformance for `page-result.json` against
  the schema file, and L1 deterministic test evidence
  (`tests/test_page_result.py`) for the routing rule, the
  receipt-binding rule, the next-role vocabulary and free-entry
  role check, the stale-hash failure, the corrupt-request error
  state, the no-orphan write ordering, and the status derivation.
  Accordingly, `proof_class` written by this emitter is at most `L1`
  (L1 only when the local production chain is fully closed).
- **NOT produced:** A07's required evidence. A07 (popup captures
  first/last/email/phone, native submit verified; owners S71/S06)
  has minimum evidence **L3**: an authorized test contact in an
  authorized installed test location. Nothing in this leg runs a
  browser, touches a native form, or verifies a real submission, so
  nothing here closes A07, and no page result from this leg may be
  read as doing so. A06's L1 half is served by S71-03's no-price gate;
  its full L2 visual/semantic review belongs to S71-10.

## Version note

Per the Signature Launch program's single-writer rule, the S71-09
branch owns edits to `SKILL.md` (entrypoint). This branch therefore
leaves `SKILL.md` and `skill-version.txt` untouched (both remain
1.2.9, consistent). The eventual merge-candidate assembly must bump
the version pair together (repo G3 rule) when this change lands with
the sibling S71 branches, and must add this handoff to the
entrypoint's reading surface at that time.
