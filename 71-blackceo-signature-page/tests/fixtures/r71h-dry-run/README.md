# R71H joint dry-run fixture

THIS IS A FIXTURE. It was built from fictional fixture records for
the Skill 71 to Skill 44 joint dry-run (R71H seam, S71-08 P3). It is
not live proof of anything: no real Convert and Flow location,
funnel, page, form, product, or launch exists behind these records,
nothing was dispatched to Skill 44 or anywhere else, and the
publish-verify fetch was served on loopback (127.0.0.1) by the
fixture builder only while the build ran; the URL in the run's
records resolves nowhere.

## What is here

- `build_fixture.py`: the builder. It writes only INPUT records
  (intake, brand fixture, launch wiring inputs in page-request.json,
  funnel-completion, click-through, the install receipt, evidence
  PNGs, the fixture page), registers and closes the fixture's
  browser sessions through `scripts/browser_sessions.py`, and then
  drives the real stage gate (`scripts/stage_gate.py`, shipped
  contract) through `ghl-install-test` close and `publish-verify`
  close. Every output artifact (the hand-off, the dispatch envelope,
  the emission record, the state hash-lock, the browser-hygiene
  receipts, the publish fetch record) is produced by the shipped
  code from those records; none of it is hand-written.
- `run/`: the built fixture run. In its state, `ghl-install-test`
  and `publish-verify` are closed and `automation-wiring` is open,
  which is exactly where a real run waits for Skill 44's receipt.
  The hand-off's SHA-256, locked in state at install close, is
  `5ea1502da48cf5c46317c865cfa06ef4f772cede6bba2026852a28809afb2325`.

## The fixture install

A fictional signature-page install into location
`fixture-location-001` (the value reaches the emitter through the
`GHL_LOCATION_ID` environment variable, the way a real install's
does), funnel `F-100`, page `P-200`, with three forms: FORM-1
(opt-in; the envelope builds it with the `contact_tag` mechanism),
FORM-2 (order; the envelope builds it with the `native` Tier 4
mechanism), and FORM-3 (booking; the envelope carries a
`no_workflow_reason` exception entry for it). The funnel record
derives all three conversational trigger classes (opt-in, purchase,
booking).

## Rebuilding

    python3 tests/fixtures/r71h-dry-run/build_fixture.py <empty-dir>

The hand-off is a deterministic derivation of the input records, so
a rebuild produces byte-identical hand-off bytes and the same
SHA-256; the envelope differs only in its minted `request_id` (and
the records' timestamps). `tests/test_r71h_fixture.py` rebuilds the
fixture into a temporary directory and asserts exactly that, plus
both gate closes passing on the rebuild.
