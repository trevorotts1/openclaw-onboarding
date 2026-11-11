## WP-10a verify-then-fix round (2026-11-10, head 049e88876)

Method: scratch exports (git archive) of branch head 049e88876 and origin/main b05dcf3730 under the lane folder, pin
recomputed inside each scratch copy only (SF-PROVER-PIN.sha256 in the repository untouched). Same interpreter, same
env -i form, fresh HOME, lane TMPDIR; "with" = PYTHONPATH is a symlink farm to the user's jsonschema, "without" = unset.

### Claim 1: test_an_empty_root_reports_everything_missing fails the same way on main (environment artifact)
| tree | jsonschema on PYTHONPATH | result |
|---|---|---|
| branch head 049e88876 | with (symlink farm) | 1 failed: [] != ['runtime-jsonschema'] |
| branch head 049e88876 | without | 1 passed |
| origin/main b05dcf3730 | with (symlink farm) | 1 failed: [] != ['runtime-jsonschema'] |
| origin/main b05dcf3730 | without | 1 passed |

Branch and main are identical in both environments, and launcher_core/dependencies.py plus the test file have no diff
between them. Cause shown: dependencies.check imports jsonschema, then reads importlib.metadata.version(); the symlink
farm has no .dist-info, so the version read raises PackageNotFoundError and the package counts as missing. With the real
site-packages directory on PYTHONPATH the test passes on both trees (head 1 passed, main 1 passed). Claim holds; no fix.

### Claim 2: test_page_designs_real.py aborts 5 tests at head on [HASH-PIN]
Whole file at head, pin recomputed in scratch only, jsonschema available: 25 passed (the 22 that main has, plus the 3
tests this branch added for issue 16 provider-unknown). Main, same form: 22 passed. Without jsonschema both trees fail the
same 5 tests with ModuleNotFoundError in validate_checkout.py (head 5 failed 20 passed; main 5 failed 17 passed), so the
stale pin is the only reason the 5 abort in the repository state; no branch-caused failure. No fix.

### Package suites at the branch head (same form, jsonschema via symlink farm)
Skill 49 scripts: head 7 failed 657 passed; main 6 failed 630 passed. The 6 are identical on both
(test_checkout_wrapper adapter_command_with_staged_design_prose, test_dispatch_launch_entry budget approval, two in
test_front_door, test_page_image_inputs one_file_replaces_the_brand_owner_cap, test_thankyou_translator).
The seventh, test_collect_launch_receipts::MinimumProof::test_full_proof_accepted, fails at head only: the branch never
touched collect_launch_receipts.py or its test (no diff against the merge base 842c262760d5); the same file fails 3 tests
at the merge base itself and main commit 760f737d4 (self-test fixes for free entry and launch receipts) repairs it. So the
branch is behind main, not the cause. Fixed by the batch merge, not by this branch.

Code changed this round: none (both claims hold, nothing branch-caused). Full command log: lane tmp wp10a-fix-r8.log
and r8-*.log.

## WP-10a round 9 fix (2026-11-10, after judge round 8 FAIL 7.8 at bae7a5670): tests only, no production change

Cure at the cause: the enforcement lines named by the judge had no test that fails without them. Production files are
byte-identical to bae7a5670.

New tests: test_upsell_wrapper.py UpsellStageVocabularyTests, UpsellEntrySlotOnlyForDesignU2Tests;
test_downsell_wrapper.py DownsellStageVocabularyAndSchemaOnlyTests, DownsellReadbackJourneyMessageTests,
DownsellSchemaEvaluatorAllOfTests; 80 test_design_marker_stage.py (five tests added); 81 test_validator_pin_lockstep.py
(enforced_at test).

### The five named survivors, red with the line removed, green restored (log: lane tmp r9-red-green.log)
| enforcement line removed | test | red |
|---|---|---|
| upsell_wrapper CLI `choices=list(STAGES)` | test_the_cli_refuses_an_unknown_stage_at_argument_parsing | yes |
| upsell_wrapper enrich `if stage not in STAGES` | test_enrich_refuses_an_unknown_stage_without_the_cli | yes |
| both upsell layers together | both tests above | 2 failed |
| downsell_wrapper CLI `choices=list(STAGES)` | test_the_cli_refuses_an_unknown_stage_at_argument_parsing | yes |
| downsell_wrapper enrich `if stage not in STAGES` | test_enrich_refuses_an_unknown_stage_without_the_cli | yes |
| 80 adapter_common validate_request stage vocabulary check | test_an_unknown_stage_is_refused_by_the_vocabulary_check_itself (the old test passed because the marker rule also refused) | yes |
| downsell `violations = _schema_violations(ext, extension_schema)` -> `violations = []` | test_a_schema_only_result_extension_violation_is_refused | yes |
| downsell `_validate_result` `problems = _schema_violations(result, schema)` -> `problems = []` | test_a_schema_only_page_result_violation_is_refused | yes |

### Own sub-clause mutation sweep over every enforcement line this branch added or touched in 49, 80, 81
Scratch copies under the lane tmp (sw/), 4 workers, jsonschema on PYTHONPATH, env -i form; logs r9-sweep.log (80 adapter
mutants valid), r9-sweep2.log (49 mutants), r9-sweep3.log (re-run of every survivor with the new tests). 82 mutants.
Survivors of the first pass and the test added for each, all re-run and killed:
- 80: qualifying-purchase marker half of the stage rule, is_design_marker stage half and status half, the marker branch's
  `verified` result, U2 qualifying status check, qualifying slot membership, original-purchase problem pass-through.
- 49 upsell: `_design_slot` computed for upsell_1 or at install (refusal leaked outside design/upsell_2); the
  `design_slot is None` early return.
- 49 downsell: guard file `blocker` at install; read-back checks for non-object document, non-object binding, non-object
  journey, unknown key, boolean flags and event type (each now refused for its own stated reason); allOf recursion in the
  wrapper evaluator.
- 81: `enforced_at` names a function that exists in the consumer.
Equivalent mutants: none claimed. Two sweep patterns hit two sites and were rewritten with context; sweep3 shows them killed.

### Package results (pin recomputed in scratch only; SF-PROVER-PIN.sha256 in the repository untouched)
49 test_upsell_wrapper + test_downsell_wrapper + test_page_types_legend: 122 OK. 80 adapters (all) + 81 tests: 623 passed,
1 skipped (image plan file 13 passed in the clone). 83 tests.test_produce_stage: 96 OK. The round-8 Skill 83 group-2 run
(r8-g2.log) had already ended (rc=124, timeout); no process of this lane was running, none was killed.
