---
name: signature-downsell
description: Build the Signature Downsell page (D1) - the reshaped alternative offer shown only after an explicit Upsell 1 decline. Derives an exact eight-section page from the 12-section landing format (keep sections 1-7, remove 8-11, replace section 12 with a renumbered section 8, "When Time Runs Out", listing 7 missed-out consequences), a CTA in every section, truthful scarcity only, a guarded native one-click action shared with the checkout system, and routes: D1 paid goes to the SAME Upsell 2 when enabled else the final thank-you; D1 declined goes to the final thank-you with the original order untouched.
version: 0.1.1
---

# Signature Downsell Page (Skill 81)

Status: BUILD CANDIDATE from the S81 room (Signature Launch packet v1.0, spec 11). Not merged, not installed, not live. Batch merge requires Trevor's explicit approval of an exact candidate.

## Route responsibility (packet 02 section 4, binding)

- D1 is reached ONLY when U1 is explicitly declined AND D1 is enabled. A failed or pending U1 payment is neither acceptance nor decline and never routes to D1 as a decline.
- D1 paid -> the SAME canonical Upsell 2 when enabled, else final thank-you. Never a D1-specific duplicate U2.
- D1 explicitly declined -> final thank-you. The original order (main plus any bump) remains valid on every branch.
- When U1 is disabled, D1 and U2 cannot remain enabled under this profile.
- U1 and D1 are mutually exclusive: an accepted U1 buyer never receives D1.

## What D1 is

An alternative to the declined U1 - changed scope or changed payment terms, recorded in a private difference table before any copy is written (see `references/offer-alternatives.md`). Never an additional charge for the identical promise. A lower installment is not a lower total price. Never auto-discount because a payment failed.

## Copy contract (see `references/downsell-copy-profile.md`)

Eight sections: 1 alternative clear immediately; 2-4 three distinct pains/objections; 5 the real reason this option exists; 6 who it fits; 7 exact inclusions and limitations; 8 "When Time Runs Out" with exactly 7 distinct foregone optional benefits. CTA in every section, all mapped to the same guarded native action, plus a visible non-purchasing decline action. Heading provenance: the owner corpus prose says "When Times Run Out", the owner sample says "When Time Runs Out"; the sample form is the proposed canonical display, recorded as a normalization - the corpus itself is never edited.

## Native action (see `references/native-action-states.md`)

Reuse the shared transactional action component owned by the shared page/checkout system (packet 16). Do not copy a second charge implementation into this folder. Exact terms adjacent to the action; pending state blocks repeat attempts; unknown outcomes reconcile from native records before retry; decline never charges and never removes existing access.

## Package contents

- `references/downsell-copy-profile.md` - derivation, eight-section contract, truth rules, heading normalization record.
- `references/offer-alternatives.md` - difference-table contract and hard checks.
- `references/native-action-states.md` - action states, entry guards, S44 event handoff note.
- `references/design-profile.md` - the eight-section design profile (S81-04): real scope-difference visibility, first-viewport original-buyer reassurance, body-size money disclosures, designed states including completed.
- `references/terms-entitlement-review.md` - the S81-07 terms, claims and entitlement review checklist that gates installed proof.
- `schemas/downsell-page.schema.json` - the D1 page document structure: exactly 8 sections in the derived role order, one purchase CTA per section bound to the single native D1 action, a separate non-purchasing decline action, the canonical section 8 heading, and exactly 7 missed-out items in section 8. Prose and truth rules over the same document are enforced by `validate_copy` in the validator and exercised by `tests/test_page_schema.py`.
- `schemas/downsell-request.schema.json` - D1 page request (role `downsell_1`, skill 81).
- `schemas/downsell-result-extension.schema.json` - the D1 extension carried alongside the packet page-result: refined offer description, UI states reference, difference matrix, disclosure audit, CTA map, source-profile mapping, heading normalization record, route result. Cross-field semantics are enforced by `validate_result_extension` in the validator and exercised by `tests/test_result_extension.py`.
- `validators/validate_downsell.py` - stdlib fail-closed validators: copy derivation, offer difference, trial disclosure, entry guard, result extension.
- `validators/validate_request.py` - stdlib fail-closed evaluator for `schemas/downsell-request.schema.json`: evaluates the packaged request schema with the standard library only, so the request contract is enforceable without the third-party jsonschema package, and fails closed on any unsupported schema keyword. Exercised by `tests/test_validate_request.py`.
- `fixtures/valid-downsell-page.json`, `fixtures/valid-downsell-result.json`, `fixtures/valid-downsell-request.json`, `fixtures/valid-downsell-result-trial-matched.json` - positive fixtures (test-only data, labeled). See the fixture pairing note under Package notes below and in `fixtures/README.md`: the page fixture and the result fixture are NOT a matched pair; the trial-matched fixture is a separate additional fixture, the matched result-extension companion to the page fixture's trial offer.
- `fixtures/README.md` - fixture inventory and the explicit not-a-matched-pair note for the page and result fixtures.
- `tests/` - validator, validator defect-fix, route, route-law pin, result-extension, request-schema, page-fixture disclosure and matched-pair trial-result suites (the matched-pair suite is `tests/test_matched_pair_trial_result.py`). Run: `python3 -m unittest discover -s tests -v`
- `adapters/README.md` - the two thin wrappers over the shared action component and the S06 native install rail, with their blocked status stated plainly. No payment client lives here.
- `adapters/provisional-binding-map.md` - PROVISIONAL room prep artifact, named here so the contents list accounts for every file in this directory: it maps D1 requirements against the S79/S06 extra-offer interface DRAFT, it is superseded the moment the confirmed S79/S06 contract lands, and it does NOT ship as part of the installed skill package. Nothing in it is a confirmed contract.

## Package notes

- Fixture pairing: `fixtures/valid-downsell-page.json` and `fixtures/valid-downsell-result.json` are NOT a matched pair. They are independent positive fixtures for two different contract objects. The page fixture describes a $1 trial offer ($1 due now for 30 days, then $27 per month) checked by the copy validator; the result fixture describes a $37 one-time offer (due_now_minor 3700, billing_type one_time) checked against the result-extension schema and the semantic validator. Do not derive one from the other, do not read the result fixture's disclosure audit as the disclosure for the page fixture's trial offer, and do not align their amounts: other tests depend on each fixture's current values. `fixtures/valid-downsell-request.json` is a third, separate positive fixture: a genuine instance of `schemas/downsell-request.schema.json`.

## Hard boundaries

No fabricated testimonials, proof, prices, or scarcity. Example prices from the owner sample are blocked from production use unless they match an approved native price mapping. No secret values anywhere in this package. Independent review is required: an artifact's reviewer is never its author. Incorrect money, entitlement, consent, source-method, or branch behavior is an automatic QC fail regardless of other scores (each applicable criterion at least 8/10, target average 8.5).
