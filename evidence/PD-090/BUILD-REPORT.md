# BUILD REPORT — PD-090

**Unit:** PD-090 — Price rules that can both be passed (Severe, logic)
**Lane:** FL23 · repository `trevorotts1/openclaw-onboarding`
**Branch:** `pd/fl23-role-procedures-b--hold-d17` (held behind owner decision D-17; staged, never merged)
**Built:** November 12, 2026, 8:35 PM Eastern
**Builder:** deepseek-chain

## What the fault was

AF-PRICE-FACE carried two exceptions — (a) a price-ladder DROP slide, (b) the re-pitch value-stack where price is the running total — and, in the same row, an "always an auto-fail regardless of slide type" list whose item (a) banned a per-component dollar value and whose item (b) banned a `"Total Value So Far: $X"` tally on the audience face of a non-tally slide. A DROP, value-stack, tally or component-card slide was therefore required by the exceptions and banned by the always-fail list at the same time. No copy could pass both halves of one rule.

## Files changed

1. `23-ai-workforce-blueprint/templates/role-library/presentations/sops/qc-specialist-presentations-sops.md`
   The AF-PRICE-FACE row is the only full definition of the rule on this branch (the role file's Vision-Gate section is a summary and points at this mirror for full definitions).
   - Replaced the two exceptions with the one clause the unit specifies: `unless the slide is tagged in arc_allocation.json as ANCHOR, DROP1, DROP2, DROP3, FINAL, VALUE_STACK, TALLY, RE_PITCH, the value-gap slide, the callback slide, or is a component card listed in offer_stack.json components[]. On those slides every dollar figure must equal a figure in price_ladder.json or offer_stack.json.`
   - Deleted always-fail clauses (a) per-component dollar value and (b) the `"Total Value So Far: $X"` tally.
   - Kept clause (c) verbatim: `any dollar value on the face not declared in price_ladder.json or the value-stack table in the brief.`
   - Nothing else in the file changed.

2. `23-ai-workforce-blueprint/templates/role-library/presentations/qc-specialist-presentations.md`
   The mirror header rules that the role file is authoritative and that divergence means the mirror must be regenerated; the mirror is the Section 9 extract. The role file's Vision-Gate summary row for AF-PRICE-FACE still said `Unauthorized per-item dollar values or multiple prices on the offer face`, which after the fix would ban whole classes the mirror now authorizes, so the two sections would disagree in the opposite direction. The summary row now reads: `Unauthorized dollar figures on a slide face outside the price-belt, value-stack, tally, re-pitch, value-gap, callback and component-card classes the rule authorizes`.
   That is the only line changed in the role file.

3. `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd090_price_face.py` (new)
   The acceptance checker. It reads both procedure sections and fails if any slide class is authorized by one and banned by the other, if either retired exception survives, if always-fail (a) or (b) survives, if (c) is missing, or if the two sections stop describing the same class set. Built, not run — rule 9: acceptance rows are run by QC.

## Which two sections the checker reads

Both sections that state this rule inside the lane's owned files:

- the QC role file's Vision-Gate summary row, and
- the QC SOP mirror's full definition.

It does not read the Slide Image Creator's `sops/slide-image-creator-sops.md` Part F: that file is lane FL24, not FL23, and its matching edit is unit PD-094. PD-094's acceptance row (A3) is the cross-file agreement check ("the rule now agrees with PD-090's rewritten AF-PRICE-FACE").

## Slide-class agreement table

`allowed` = the class may carry a dollar figure that reconciles to `price_ladder.json` or `offer_stack.json`. `banned` = a rule forbids the class.

| Slide class | PD-090 rule (mirror) | Role-file summary | Any other rule in the two owned files bans it | Image Creator Part F (lane FL24) |
|---|---|---|---|---|
| ANCHOR | allowed | allowed | no | not covered |
| DROP1 | allowed | allowed | no | not covered |
| DROP2 | allowed | allowed | no | not covered |
| DROP3 | allowed | allowed | no | not covered |
| FINAL | allowed | allowed | no | allowed (the single sanctioned callout) |
| VALUE_STACK | allowed | allowed | no | still says the value-stack math lives in the presenter notes — PD-094 |
| TALLY | allowed | allowed | no | still says the running tally stays off the audience face — PD-094 |
| RE_PITCH | allowed | allowed | no | not covered |
| value-gap slide | allowed | allowed | no | not covered |
| callback slide | allowed | allowed | no | not covered |
| component card in `offer_stack.json components[]` | allowed | allowed | no | still bans a per-component dollar value — PD-094 |

**Result inside this unit: no slide class is required by one section and banned by the other.** The two remaining disagreements are with the FL24 file, which this unit may not edit; they are PD-094's, and PD-094 A3 quotes both rules.

Two adjacent rules that name the same subject and were checked, and are not class bans:

- `AF-TELEGRAPH` (b) bans the literal ledger phrasing `"Total Value So Far:"` as copy. It bans a string, not a slide class, and the tally class is authorized to carry reconciling figures without that phrasing.
- `AF-C8` / the copy character band bound every slide's copy length. They do not name a price class.

## Reading done before the change (rule 3 — no text-search tools used as proof)

Files opened and read for this unit: the role file's Section 9 copy, slide-craft, density, image-QC, deck-wide representation, final-deck, design-craft and Vision-Gate sections; the mirror's copy auto-fail table and Vision-Gate block; the Slide Image Creator's Part F; the full text of `scripts/tests/test_af_c8_copy_contract.py`, `scripts/tests/test_fix32_manifest_copy_drift.py`, `scripts/tests/test_contract_completeness.py`, `scripts/tests/test_pres001_unit_contracts.py`, `scripts/tests/test_qc_gate_teeth.py`.

## Tests that could break (rule 15)

The tests in the folders touched were read for assertions over the two edited files. None asserts the old AF-PRICE-FACE wording: `test_contract_completeness.py` and `test_pres001_unit_contracts.py` derive contracts from `presentation_job/`, `test_fix32_manifest_copy_drift.py` compares manifest JSON copies, `test_qc_gate_teeth.py` re-measures run artifacts, `test_af_c8_copy_contract.py` asserts `ARTIFACT_CONTRACTS` prose. No assertion was made false by this change, so none was edited and none was deleted.

## Not done, on purpose

- No merge, no push to `main`, no rebase, no force-push (lane rules; and D-17 holds this unit).
- No test, suite or acceptance command was run (rule 9). `test_pd090_price_face.py` is left for QC.
- No client box, no live service, no browser, no model call.
- No file outside the FL23 owned list was touched.
