# PD-933 BUILD REPORT

Unit: PD-933 | lane FL03 | branch `pd/fl03-question-bank` | builder: deepseek-chain
Owned path: `23-ai-workforce-blueprint/templates/role-library/presentations/intake/interview-app/test/test_email_election_flow.py`
Base: merge-base `1a476d2cb` (Merge pull request #3163). Branch tip before this unit: `479411406` (PD-014, QC PASS).

## Answer chosen: A — retarget, assertion line byte-identical

PD-014 is not wrong. The PD-014 QC receipt (`qc/PD-014.a8bedc…json`, defect 1) already ruled:
"Flip correct: unit title + toggle default no + PD-901/909 retargets assert required false by name;
stale assertion is PD-933's job." So B (rule PD-014 wrong) is excluded by an accepted receipt.
I retargeted.

The test's own module docstring already states the correct owner: "the toggle itself is a required
canonical field ... the CONDITIONAL reason is not a flat-required field". Line 102 was pinned to the
follow-up, contradicting the docstring; PD-014's optional-follow-up rule exposed it.

### The change (one hunk, 14 insertions / 3 deletions, no test deleted or skipped)
- `reason = by_id["email_sequences_declined_reason"]` → `followup = …` for the storeOn/conditional_on pins.
- Added, so the follow-up's new optional shape is pinned, not dropped:
  - `self.assertFalse(followup["required"])`
  - `self.assertFalse(followup["block_gate"])`
  - `self.assertEqual(followup["ask_if"], {"question_id": "want_email_sequences", "equals": "yes"})`
- `reason = toggle` — the expected owner of `required` moves to the election toggle.
- Line `        self.assertTrue(reason["required"])` is BYTE-IDENTICAL (proved below).

### Assertion line byte-identical (measured, not asserted)
```
--- OLD line 102 (git show HEAD:<file> | sed -n '102p' | od -c)
0000000                                    s   e   l   f   .   a   s   s
0000020    e   r   t   T   r   u   e   (   r   e   a   s   o   n   [   "
0000040    r   e   q   u   i   r   e   d   "   ]   )  \n
--- NEW line 113 (sed -n '113p' | od -c)
0000000                                    s   e   l   f   .   a   s   s
0000020    e   r   t   T   r   u   e   (   r   e   a   s   o   n   [   "
0000040    r   e   q   u   i   r   e   d   "   ]   )  \n
IDENTICAL: [        self.assertTrue(reason["required"])]
```

## Acceptance row A1 — four trees (each command run, output captured)

Command per tree (test module path): `python3 -m unittest
23-ai-workforce-blueprint.templates.role-library.presentations.intake.interview-app.test.test_email_election_flow`
Scratch root: `<scratch root — host path never committed>`

| tree | head | patched? | result | git status --porcelain |
|---|---|---|---|---|
| mainonly (origin/main) | `ebf5c769a` | no (still asserts True) | `Ran 11 tests` `OK` | empty |
| main-fl03 (origin/main + PD-014) | `f3023ee2b` | yes | `Ran 11 tests` `OK` | empty (restored) |
| pair (+ pd/fl21 PD-901/909) | `cc1e4f3fe` | yes | `Ran 11 tests` `OK` | empty (restored) |
| control (origin/main + PD-909 only, no PD-014) | `9f0c3eae7` | no | `Ran 11 tests` `OK` | empty |

Before this unit, main-fl03 and pair were `FAILED (failures=1)` at
`test_pair_present_in_lockstep :102 AssertionError: False is not true`. After: `OK`.

## Load-bearing mutations (each turns the proof RED)

M1 — patched test against PD-014 ABSENT (mainonly, `ebf5c769a`):
```
FAIL: test_pair_present_in_lockstep
  File ".../test_email_election_flow.py", line 108, in test_pair_present_in_lockstep
    self.assertFalse(followup["required"])
AssertionError: True is not false
Ran 11 tests — FAILED (failures=1)
```
→ the new optional-shape pin discriminates on PD-014's flags.

M2 — toggle `want_email_sequences.required` true→false in deck-intake-questions.json (mutated copy of
main-fl03, patched test):
```
FAIL: test_pair_present_in_lockstep
  File ".../test_email_election_flow.py", line 113, in test_pair_present_in_lockstep
    self.assertTrue(reason["required"])
AssertionError: False is not true
Ran 11 tests — FAILED (failures=1)
```
→ the byte-identical line 102 still discriminates on the toggle it now names.

M3 — remove `ask_only_if_previously_wanted` from the email reason alias + subfield (mutated copy of main-fl03):
```
ERROR: test_pair_present_in_lockstep
  File ".../test_email_election_flow.py", line 110
KeyError: 'ask_if'
Ran 11 tests — FAILED (errors=1)
```
→ the prior-YES pin discriminates.

All three mutated trees restored; `git status --porcelain` empty afterwards.

## Regression check beyond the unit
- Pair, unmodified, three suites (test_payload.py + test_waiver_decline_flow.py + test_email_election_flow.py):
  `1 failed, 32 passed` (only the unpatched email test red).
- Pair, patched email test, same three suites: `33 passed in 0.39s`.
- Interview-app test dir: mainonly baseline `7 failed, 141 passed`; FL03 branch with this change
  `11 failed, 137 passed`. The +4 are PD-014 collateral in files owned by sibling lanes, not this unit:
  `test_payload.py::{test_curated_set_contract,test_email_election_pair_is_pinned,test_motion_election_pair_is_pinned}`
  and `test_waiver_decline_flow.py::test_both_reasons_minted_conditionally_with_canonical_storeon`.
  Those same four are green on the pair tree (33 passed), i.e. resolved by PD-901/PD-909 on FL21.
- `test_email_election_flow.py` is not among any failure list on main-fl03/pair after this change.

## Collateral observed, NOT owned, NOT fixed
1. `intake/interview-app/payload/build_questions_payload.py` selftest is RED at its own line 459 on PD-014's head:
   `AssertionError: {'id': 'vsl_page_declined_reason', … 'required': False …}` — the selftest asserts every
   `_declined_reason` follow-up `required is True`. PD-014's bank flip broke the producer's own invariant.
   Outside this unit's owned_paths.
2. `intake/upsell-questions.json` still declares `email_sequences_declined_reason` `required: true`,
   `block_gate: true` (outside PD-014's and this unit's owned paths) — the third bank shape now contradicts
   deck-intake-questions.json.
3. `intake/interview-app/pages/questions.json` (FL21 generated) still `required: true` for the four reasons,
   as PD-014's note already recorded.

## Hunk attribution (merge-base `1a476d2cb` → HEAD)
Branch commits since merge-base: `941a777cf` PD-024, `0678e4822`+`84f907214`+`479411406` PD-014, plus this unit.
- PD-024 (`941a777cf`): 12 prompt wordings in `deck-intake-questions.json`.
- PD-014 (`0678e4822`,`84f907214`): declined-reason required/block_gate/ask_only flags in
  `deck-intake-questions.json` + `ask_if` projection in `question_sequence.py`.
- PD-014 (`479411406`): new `scripts/tests/test_pd_bank_014_declined_reason_flags.py`.
- PD-933 (this commit): `interview-app/test/test_email_election_flow.py` only — the sole hunk in this commit.

## Commit / push
See the commit metadata and the `git ls-remote` proof in the final return text.
No merge, no rebase, no force-push. No verdict issued — QC owns that.
