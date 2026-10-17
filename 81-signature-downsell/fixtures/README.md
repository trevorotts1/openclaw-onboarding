# Fixtures - Skill 81 (D1)

All fixtures in this directory are TEST ONLY data. None of them are real client facts, real prices for a live launch, or production copy.

## Inventory

- `valid-downsell-page.json` - a valid D1 page object for the copy validator (`validate_copy` in `validators/validate_downsell.py`). It mirrors the owner sample structure with test-only facts. Its offer is a trial: $1 due now for 30 days, then $27 per month. Those amounts appear on its surfaces only because its `approved_amounts_minor` lists [100, 2700] as this fixture's approved test prices.
- `valid-downsell-result.json` - a valid D1 result extension for `schemas/downsell-result-extension.schema.json` and the semantic validator `validate_result_extension`. Its offer is a one-time payment: due_now_minor 3700 ($37), billing_type one_time, reduced scope.
- `valid-downsell-result-trial-matched.json` - a valid D1 result extension for `schemas/downsell-result-extension.schema.json` and the semantic validator `validate_result_extension`, built as the trial-matched companion to `valid-downsell-page.json`: it describes that page fixture's own trial offer ($1 due now for 30 days, then $27 per month), with a disclosure audit of billing_type trial, due_now_minor 100, renewal_amount_minor 2700, a first renewal charge on day 31 rule, and cancellation_terms_present true. TEST ONLY, like every fixture in this directory. Proven by `tests/test_matched_pair_trial_result.py`, which pins the derivation from the page fixture (amounts and action refs) and fails on a deliberately mismatched pair.
- `valid-downsell-request.json` - a valid D1 page request: a genuine instance of `schemas/downsell-request.schema.json` (role `downsell_1`, assigned_skill 81, success_route `upsell_2`, decline_route `thank_you`), proven by `tests/test_request_schema_fixture.py`.

## The page fixture and the result fixture are NOT a matched pair

Read this before pairing, deriving, or editing any fixture here:

- The page fixture and the result fixture are independent positive fixtures for two different contract objects. The result fixture was NOT produced from the page fixture, and no test derives one from the other.
- Their offers are different on purpose: a $1 trial with a $27 per month renewal (page) versus a $37 one-time payment (result). The result fixture's disclosure audit (billing_type one_time, due_now_minor 3700, renewal fields null) describes the result fixture's own one-time offer only. It is NOT the disclosure for the page fixture's trial offer, and read as a pair it would be wrong for that trial.
- Do not align their amounts and do not change one fixture to match the other. Other tests depend on each fixture's current values exactly as they are.
- A result extension built for the page fixture's trial offer would instead need a disclosure audit with billing_type trial, due_now_minor 100, renewal_amount_minor 2700, a renewal date or rule, and cancellation_terms_present true.

## Negative fixtures

Added 2026-10-16 by the negative-fixture lane, closing the gap recorded in `rooms/S81/lane-fixture-gap-2010.md` (the package previously carried no standalone negative fixtures; every defect sentence lived only as an inline string in a test method). Each fixture below is TEST ONLY, is validly structured, violates exactly one named rule, and carries its expected violation codes in its own `expected_violations` field. Each is proven by `tests/test_negative_fixtures.py`, which asserts the validator returns exactly those codes, and re-runs the three positive validator fixtures above as controls. The escaping examples from the review chain that are NOT in this set, and why, are mapped in `rooms/S81/negative-fixture-disposition.md`.

- `invalid-downsell-page-fake-scarcity.json` - a D1 page whose section 1 body carries a scarcity claim ("Only a couple of spots remain at this price.", recorded in review-validator-fix.md, D-3) with no `scarcity_evidence_ref` recorded. Expected rejection: `D1-COPY-FAKE-SCARCITY`.
- `invalid-downsell-page-private-label.json` - a D1 page whose section 1 body opens with a private framework label ("For internal review only, do not share.", recorded in review-validator-fix.md, D-8). Expected rejection: `D1-COPY-PRIVATE-LABEL-LEAK`.
- `invalid-downsell-page-loss-of-purchase.json` - a D1 page whose section 1 body carries a false loss-of-purchase threat ("Skip this and we will take away what you already bought.", recorded in review-validator-fix.md, finding N-2). Expected rejection: `D1-COPY-FALSE-LOSS-OF-PURCHASE`.
- `invalid-downsell-page-decline-is-purchase.json` - a D1 page whose `decline_action.action_ref` is the purchase action ref used by every section CTA (recorded in review-validator-fix.md, D-6 and finding N-1). Expected rejection: `D1-COPY-DECLINE-ACTION-IS-PURCHASE-ACTION`.
- `invalid-downsell-page-example-price-leak.json` - a D1 page in the scrubbed control construction (every example amount scrubbed from the surfaces, none approved) whose section 1 CTA label carries the D-9 regression format "Join for $27.00 now" (recorded in review-validator-fix.md, D-9). Expected rejection: `D1-COPY-EXAMPLE-PRICE-LEAK`.
- `invalid-downsell-result-decline-is-purchase.json` - a D1 result extension whose `decline_action_ref` is the purchase action ref used by every `cta_map` entry (lane 5 defect D-6). Expected rejection: `D1-RESULT-DECLINE-ACTION-IS-PURCHASE-ACTION`.
- `invalid-downsell-result-trial-disclosure.json` - a D1 result extension built on the trial-matched valid fixture with `cancellation_terms_present` set to false in its disclosure audit (lane 5 defect D-10). Expected rejection: `D1-RESULT-DISCLOSURE-CANCELLATION-MISSING`.
- `invalid-downsell-offer-identical-promise.json` - a U1/D1 offer pair whose D1 is the recorded synonym paraphrase of U1 (review-validator-fix.md, D-13): deliverables reworded, entitlement ids renamed to a disjoint set, lower total, claimed as `reduced_scope`. Expected rejection: `D1-OFFER-IDENTICAL-PROMISE`.
- `invalid-downsell-disclosure-missing-cancellation.json` - a D1 trial offer plus its adjacent disclosure, complete in every field except a whitespace-only `cancellation_terms` (recorded in review-validator-fix.md, D-5). Expected rejection: `D1-DISCLOSURE-MISSING-CANCELLATION_TERMS`.
