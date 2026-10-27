## [2.0.197] - 2026-10-25 - fix(integration): a proof id, a path, a state and a target position are observed or they are UNKNOWN (T-43 repair rounds 3-5, PBB-369 -> PBB-452)

- **Merge-time re-cut (PBB-867, 2026-10-26): `v2.0.128` -> `v2.0.197`.** The `v2.0.128` allocation below was measured when this branch's ladder topped out at `v2.0.123`; `origin/main` has since reached `v2.0.196` (`38-conversational-ai-system/skill-version.txt` at `bd2216185d11db8e9f4118d34d8babbd7b05c7b8`), so the number is re-cut one patch above it. Measured, not assumed: `2.0.197` is held by **0** remote refs as a marker and **0** as a heading, and both token forms are absent on `origin/main` (`scratch/lanes/PBB-867/version-measure.json`, 2192 refs enumerated, 0 missing in both roles, known-present control `origin/main` = `v2.0.196`, known-absent control absent). The BOOKKEEPING section below is the round-5 measurement as it stood and is kept verbatim; only the number this entry allocates is re-cut.

ROUND 5 (PBB-452) — verifier PBB-433 returned FAIL on `339bc542d` on one landability count and one live instance of the class this entry exists to close. All 24 acceptance probes passed and stay passing (24/24 re-driven after the merge). Three things are fixed here.

- **L-1 (decisive) — the candidate was 127 commits behind live `origin/main` and its three version-bookkeeping files would not merge.** PBB-433 measured `origin/main` as `006fc4260` / `v2.0.95` because it never fetched; live `origin/main` after `git fetch origin` is **`3c798db6659c576cc40e3ce8c81d2ede7acf3e0c`** at `v2.0.105`. Re-measured against the fetched ref: `git rev-list --count origin/main..339bc542d` = 5 ahead, `339bc542d..origin/main` = **127 behind** (PBB-433 measured 122 against the stale ref), merge-base `04fbdc240165345ab6a889d07595850b4315c708`, and `git merge-tree --write-tree origin/main 339bc542d` returns rc 1 with `CONFLICT (content)` in exactly three files and nothing else: `38-conversational-ai-system/CHANGELOG.md`, `38-conversational-ai-system/skill-version.txt`, root `CHANGELOG.md`. `origin/main` is merged **in** — a merge, not a rebase — so the reviewed commit `339bc542d` stays an ancestor of the landing (proved: `git merge-base --is-ancestor 339bc542d HEAD` rc 0, and `origin/main` rc 0 too). All three conflicts are bookkeeping text; each is resolved by keeping **both** sides and renumbering once.

- **V-2 (high) — the version pin was self-referential and could not see merge drift.** `test_the_skill_version_and_its_changelog_heading_are_one_number` compared the candidate marker against the candidate's OWN CHANGELOG heading, both read from the same stale tree, so it stayed green while `git merge-tree` proved conflicts in exactly those two files. It now also reads `skill-version.txt` at a **NAMED** `origin/main` SHA (`3c798db6659c576cc40e3ce8c81d2ede7acf3e0c`, never the moving ref) and requires the candidate marker to move strictly above it, scored NUMERICALLY (`major*1000000 + minor*1000 + patch`), never lexically. Absence is fail-closed: if the named SHA cannot be read the test FAILS naming the reason rather than passing on an unmeasured claim. **Proven, not asserted**: on a detached worktree at `339bc542d` with only the new test file dropped in, the pin fails with `AssertionError: 2000104 not greater than 2000105 : candidate marker v2.0.104 does not move above the number 38-conversational-ai-system/skill-version.txt declares at the NAMED main SHA 3c798db6659c576cc40e3ce8c81d2ede7acf3e0c (v2.0.105)` — legs 1-4 all passed there, so the old pin was green on exactly this state and the new one is red on it.

- **D-10 (high) — `schema.kind` still compared VALUES before it checked SHAPE.** `_schema_verdict` did `if kind == "none": return None` before any type test, so a non-`str` that merely *won* an equality test reached the "no schema clause" branch. PBB-433's two probes both rendered **ADMITTED, reasons=[]**: an object whose `__eq__` returned `other == "none"`, and a `str` subclass whose value was `"none"`. The observed type is now established BEFORE any equality test — `type(kind) is not str`, never `isinstance`, because a `str` subclass can override `__eq__` and lie about its own value — so a non-observed kind can never reach the "no schema clause" branch, including one that merely claims equality. Both probes now render **HELD / `schema_kind_malformed`** (ADMITTED -> REFUSED). Round 4's eleven rows stay pinned, and the inverses still admit: `schema` absent, `{}`, `"none"`, `"additive"` with tolerant-reader proof -> ADMITTED; `"breaking"` with the writer switch -> HELD. Pinned by `FifthRepairProofTests` (claiming-`__eq__` over all four kinds, `str` subclass over five values, round-4 rows re-driven under the new law, plus the inverse set).

- **R-1 (ruling + one enforcement) — the six residual raw `or` coercions at `integration.py` lines 1021, 1162, 1165, 1168, 1173, 1176.** Each probed; PBB-433 found all six in a refusal-or-reason-naming position and that holds for five of them, but one was a real leak:
  - **L1021 `owner.get("reason") or "owner_unobserved"` — acceptable as it stands.** The `or` only chooses the WORD printed inside a refusal reason. `build_receipt` with an owner that is not PROVEN renders `UNKNOWN` with `reasons=['owner:owner_unobserved', 'component_state_unobserved']`. There is no path from an unobserved owner to PROVEN.
  - **L1162 `cohort.get("hold") or cohort.get("unknown") or ...` — ENFORCED here.** "nothing is held" and "nothing is unknown" are FACTS a PROVEN receipt rests on, so an UNOBSERVED disposition is not the empty one. Probe before: `cohort.hold=None unknown=None` -> `valid=True` (absence became success). Probe after: `valid=False(proven receipt carries an unobserved cohort.hold)`. `hold='junk'` / `unknown='junk'` -> `malformed cohort.hold` / `malformed cohort.unknown`; `hold=[{}]` -> `non-admitted cohort`; `admit=None` -> `non-admitted cohort`. Observed empty lists still verify, so the pin is not a blanket refusal.
  - **L1165 `receipt.get("gates") or ()` — acceptable.** `if not receipt.get("gates")` already refuses absent and empty ("proven receipt has no gates"), and the top-of-function `_as_records` gate refuses every truthy non-list ("receipt gates must be a list of records"). The `or ()` can only skip a loop; it cannot mint PROVEN.
  - **L1168 `named_repairs or ()` and **L1173 `cleanup or ()` — acceptable.** The same two gates apply (`receipt named_repairs must be a list of records`, `receipt cleanup must be a list of records`), and an ABSENT optional collection is this module's own documented reading — `_as_names`' docstring: "`None` is the observed empty set (the caller passed nothing)" — and `verify_receipt`'s top-of-function loop encodes it (`if raw is not None and records is None` -> malformed). Enforcing "must be present" here would move the reason strings that four pinned `Receipts` tests assert and would contradict the module's stated contract. Probe shown: `named_repairs=None` and `cleanup=None` verify `valid=True`, `named_repairs='junk'` and `cleanup='junk'` refuse.
  - **L1176 `(receipt.get("proof") or {}).get("state")` — acceptable.** `proof=None`, `proof={}` and `proof={'state': UNKNOWN}` all refuse ("proven receipt lacks remote proof"); `proof='junk'` refuses at the top-of-function mapping gate ("receipt proof must be an object").

- **BASELINES CORRECTED (a verifier error inherited from PBB-433 and not repeated).** There are TWO suites and they were conflated. Measured here, on a detached `origin/main` at `3c798db6659c` and on this tree, each run twice, exit codes captured per command:
  - `38-conversational-ai-system/tools/tests/` — `test_interactive_owner.py` **IS** present (47,564 bytes, `class BookkeepingTests`). On `origin/main`: **410 collected, 7 failed** (3 `FAILED` + 4 `SUBFAILED`), all in `BookkeepingTests`. On this tree: **409 collected, 4 failed** (1 `FAILED` + 3 `SUBFAILED`), also all in `BookkeepingTests`. Collection is at or above the 406 floor; the failure count strictly improves but is **NOT zero**, and the reason is named below.
  - `tests/unit/` — 3,135 collected. On `origin/main`: **7 failed across 6 files**; on this tree: **7 failed, the identical 7 by name**. ZERO new failures. The seven are `hq/B18/test_mc_route_capture.py::McRouteCaptureTest::test_d_missing_or_broken_adapter_leaves_the_card_untouched`, `test_bundle_v25_1_70.py::test_full_install_makes_the_contract_check_fatal`, `test_execution_policy.py::GeneratorTemplateTests::test_managed_block_carries_four_categories`, `test_jev28_managed_instructions.py::D28PolicyClauseTests::test_canonical_policy_keeps_four_way_s5_4_distinction` (SUBFAIL, clause='Route new work'), `test_owner_sends_hold.py::TestGateFiresOnlyOnFullPass::test_passing_gate_fires_control`, and `test_skill23_build_nondestructive.py::TestMaterializeDeptAgents::{test_existing_agent_is_not_repointed_to_a_new_sparse_tree, test_no_duplicate_for_department_registered_under_another_key}`. **This corrects the baseline in the repair brief**, which named 5 failures across 4 files and omitted `hq/B18/test_mc_route_capture.py` and `test_bundle_v25_1_70.py`.
  - `bash scripts/bump-version.sh --check` -> **rc 0 on both trees**, each with the pre-existing `v21.4.25`-signature tag-containment advisory on both — that is parity.
  - Guard trap reproduced both ways on `scripts/ci/fast-guards.d/*.sh` (98 guards; line 4 is `cd "$GITHUB_WORKSPACE"`): **UNSET** -> `line 4: cd: null directory`, rc 1 (a FALSE failure, not a gate result); **SET** -> genuine results: `checker-false-fail-guards.sh` rc 0 (`syntax OK`), while `anthology-shared-run-dir-guard.sh` and `class-kit-gate.sh` fail on THIS box's environment (`error: externally-managed-environment`, `sudo: a terminal is required`), not on the gate. Onboarding main is red on `fast-guards (all folded guards)`; parity.

- **RESIDUAL, NOT PAPERED OVER — the `BookkeepingTests` `[:4]` pin is unsatisfiable after any merge of `origin/main`, and it is left alone deliberately.** `test_no_version_names_two_different_changes` and `test_no_version_this_branch_ships_appears_on_main` both slice `changelog_versions()[:4]` and treat those four as "the four T-19 entries this change owns". After a merge the file necessarily carries `main`'s own headings, so `[:4]` is `(2.0.128, 2.0.105, 2.0.97, 2.0.95)` and three of them already name an entry on `origin/main`. There are exactly two ways to make it green: invent three extra version numbers for one change (false bookkeeping), or change the pin's `[:4]` to the "owned" set its own sibling `test_the_changelog_is_strictly_monotonic_where_this_change_speaks` already computes. Both are a policy call on ANOTHER task's pin, and that call is already open as an owner decision, so it is not made here. The four residual failures are that pin and nothing else; `test_the_shipped_version_is_strictly_above_main_s` and `test_the_changelog_is_strictly_monotonic_where_this_change_speaks` both go green on this tree and were red on `origin/main`.

Independent QC of the T-43 round-2 bytes (`7a965c7f4`, PBB-309) returned FAIL: the five named defects were genuinely repaired, and the same defect shape was left live one field over in three untouched functions and two internal sites. This round closes the class, not the instances. Probes reproducing each case were run against a detached worktree at `7a965c7f4` and at this commit; the module is `shared-utils/decision_engine_train/integration.py`, the suite is `tests/unit/test_onboarding_integration.py`.

- **D-1 (critical) — `cleanup_disposition` handed out `eligible` from an unobserved `remote_merge_proof_ids`.** The field was tested for truthiness only, so `"junk"`, `[""]`, `[None]`, `[7]`, `1` and `{"p":1}` all returned `eligible / clean_merged_tree` — the T-46 deletion authorisation and the `verify_receipt` precondition — while the *same function* correctly returned `UNKNOWN / consumer_state_unobserved` for `consumers="nobody"`. The proof ids now pass `_as_names`, the same gate `combined_owner` and `depends_on_repos` use: a malformed shape is `UNKNOWN / remote_merge_proof_malformed`, an empty or absent collection is `UNKNOWN / remote_merge_proof_unobserved`, and a real id is unchanged. `id` is likewise an observed non-empty string, not `str()` of an int.
- **D-2 (high) — an unobserved `files` entry became a real path.** `_normalise_units` guarded the outer shape and then `str(f)`-coerced each entry, so `files=[None]`, `[5]`, `[{}]`, `[[]]`, `[False]`, `[b'x']` were all `ADMITTED`, and two such units produced `combined_candidates=[{'files': ['None'], 'unit_ids': ['A','B']}]` — an owner set built from an unobserved fact. Files and dependencies now pass `_as_names` entry by entry (`unit_files_malformed`, `unit_depends_on_malformed`), `repo` must be an observed non-empty string when supplied (`unit_repo_malformed`), and `unit_id`/`sha` are observed strings, the SHA exact 40-hex. The cohort-level `repository=` default is unchanged and still documented: it is the caller's declared cohort repository, not an unobserved per-unit fact.
- **D-3 (high) — an unobserved unit `state` was read as "not red".** Only `state is None` was refused; `""`, `5`, `True`, `[]`, `{}`, `"RED"`, `"red "` and `"greenish"` were all `ADMITTED` with an empty red subset, so BC-07 never ran. State is now one of `green`/`red` exactly (`unit_state_malformed` otherwise); `None` keeps `unit_state_unobserved`.
- **D-4 (high) — `verify_receipt` certified PROVEN with unobserved target positions.** `before`/`after` were truthiness-tested, so `"zz"`, `1` and `2` were a complete remote proof. They are now hex object ids through `_as_hex_ref` (an abbreviated hex prefix is allowed because existing receipts carry `"1"`/`"2"`; a non-hex string and any non-string are not), and `build_receipt` uses the same test, so a build can no longer emit a receipt its own verifier rejects.
- **D-5 (high) — `prove_named_repair` emitted PROVEN from unobserved identities and blob ids.** `repair_id` was `str()`-coerced (`5` -> `"5"`), `target_ref`/`observed_head` were truthiness-tested (`9`, `True`, `["r"]` passed), and `content_equivalence` compared `str()` of both sides, so `None == None` was a *content proof*. Repair id, target ref and observed head are observed now, and both content maps pass `_as_blob_map`: every path and every blob id must be a non-empty string, so two unobserved values can never compare equal.
- **D-6 (medium) — `build_receipt` emitted `UNKNOWN` with no reason.** The raw `cohort` mapping was folded as if it carried a component state, so it always contributed a `None` state; when every other clause was proven the receipt came out `UNKNOWN reasons=[]`, which `verify_receipt` rejects with "UNKNOWN receipt must name a reason". The cohort contributes its computed state only, and `_merge_component_states` now appends `component_state_unobserved` whenever an unrecognised state folds to `UNKNOWN`. A fully proven input set is now `PROVEN` and verifies.
- **D-7 (low) — `exact_independent_gate` `str()`-coerced the identity its proof carries.** `unit_id=5` produced `PROVEN` with `unit_id="5"`. The identity must be an observed non-empty string, and a check collection whose names or statuses are not observed strings is `required_check_results_malformed` instead of a silently dropped entry.

PROBE, verbatim. All 22 rows are in the lane (`probes.py`, kept in lane scratch, not in the repo), on a detached worktree at the reviewed commit and on this tree:
  BEFORE `python3 -I probes.py <wt-7a965c7f4>` -> `RESULT: FAIL (10/22)`, exit 1.
  AFTER  `python3 -I probes.py <wt>`            -> `RESULT: PASS (22/22)`, exit 0.
The malformed matrix is exact: `remote_merge_proof_ids` in `"junk"`, `[""]`, `[None]`, `[7]`, `1`, `{"p":1}`, `[]`, `None` all `eligible` before and all `UNKNOWN` after, with `["M-1"]` still `eligible` and `consumers="nobody"` still `UNKNOWN` in both trees (the contrast case that proves the sibling site was already right).

MUTATIONS, verbatim (`mutate.py`, one edit per throwaway copy, restore sha256-proven): 13 mutations, **13/13 caught**, restored byte-identical after every one and green at the end.

PRIOR DEFECTS. The five repaired defects were re-probed with the same script on the parent `d32103b2f` and here: C1 lease-with-no-expires `PROVEN stolen=True` -> `UNKNOWN / lease_expiry_unobserved stolen=False`; C1b `owner=None` `PROVEN` -> `UNKNOWN / lease_owner_unobserved`; C2 `combined_owner="AB"` `ADMITTED combined=[{...A,B}]` -> `UNKNOWN combined=[]`; C3 `required_checks=()` `PROVEN` -> `UNKNOWN / required_checks_unobserved`; C5 `busy_until="x"` `TypeError` -> `UNKNOWN / merge_state_unobserved`; C7 malformed receipt collections 7 raised -> 0 raised, 8/8 typed with a reason. No regression.

SUITES on these bytes, **twice each**, against a DETACHED `origin/main` worktree baseline (`wt-main` at `006fc4260`), all four runs serial — a parallel run produces a fifth flaky failure in the harness (`test_onboarding_qc_deadline.py::…test_normal_cli_and_qc_pass_with_private_diagnostics`, `AssertionError: 1 != 0`) which is concurrency flake and not a candidate defect:

```
python3 -B -m pytest tests/unit -q -p no:cacheprovider
  candidate  pass 1   4 failed, 3124 passed, 3 skipped, 1 warning, 608 subtests passed   exit 1
  candidate  pass 2   4 failed, 3124 passed, 3 skipped, 1 warning, 608 subtests passed   exit 1
  origin/main pass 1  4 failed, 3009 passed, 3 skipped, 1 warning, 488 subtests passed   exit 1
  origin/main pass 2  4 failed, 3009 passed, 3 skipped, 1 warning, 488 subtests passed   exit 1
```

Failure sets compared **by name**, not by count — 4 rows, byte-identical across all four runs:

```
FAILED tests/unit/hq/B18/test_mc_route_capture.py::McRouteCaptureTest::test_d_missing_or_broken_adapter_leaves_the_card_untouched
FAILED tests/unit/test_bundle_v25_1_70.py::test_full_install_makes_the_contract_check_fatal
FAILED tests/unit/test_execution_policy.py::GeneratorTemplateTests::test_managed_block_carries_four_categories
SUBFAILED(clause='Route new work') tests/unit/test_jev28_managed_instructions.py::D28PolicyClauseTests::test_canonical_policy_keeps_four_way_s5_4_distinction
```

**Attributed to `origin/main`, not to this commit**: the detached baseline carries exactly this set before any of this work exists, and this commit adds zero new names to it. Targeted file alone: `tests/unit/test_onboarding_integration.py` -> **115 passed, 120 subtests**, exit 0 (base `56f817dc`: 107 passed, 63 subtests; parent `7a965c7f4`: 98 passed, 27 subtests, exit 0).

TEST DIFF AGAINST THE PARENT `7a965c7f4`: `git diff --numstat 7a965c7f4 <this commit> -- tests/unit/test_onboarding_integration.py` -> `409 0`, exit 0, and the raw diff carries **0** `-` lines (the same command's `+` side reports 409, which is the positive control that the instrument is counting at all). 98 -> 115 test methods, 12 -> 14 classes, 228 -> 314 `self.assert*` calls. Round 3 contributed `200 0` of that (`ThirdRepairProofTests`, 98 -> 107); round 4 contributes `209 0` (`FourthRepairProofTests`, 107 -> 115, plus one added import line for the private `_sha_for` helper). Against the round-3 base `56f817dc` the same command reports `209 0`. No existing assertion was weakened, deleted or reordered — the test diff is additions only.

ROUND 4 (PBB-412) — independent QC of the round-3 bytes (`56f817dc`, PBB-390) returned FAIL on three counts. All three are closed here. The module and the suite are unchanged; probes are `probe_d8.py` / `attest.py` / `absence-proof.sh` in lane scratch, run on a detached worktree at `56f817dc`, on the parent `7a965c7f4` and on this tree.

- **V-1 (critical) — a false measured-absence attestation in this entry's own BOOKKEEPING paragraph.** The round-3 sentence claimed `v2.0.97` was "allocated above every number claimed by any branch on `origin`" and that "the bracketed token `[2.0.97]` returns 0 hits across those 49 refs". Both were false: the command it described covered 49 of 1974 heads, and `v2.0.97` was the live claim of `origin/batch/PBB-380/t05-merge`. Under the standard, a false claim that *absence was measured* is a FAIL regardless of the duplicate. The sentence is replaced below by one that names the population it actually measured, every command with its exit code, and a same-instrument positive control. The number is re-allocated to `v2.0.128`, which the harness below measured free. The habit is fixed with it: every zero this entry asserts now carries its command, its exit code and a control — see MEASURED ZEROS AND THEIR CONTROLS.
- **D-8 (high) — a falsy malformed `schema.kind` was read as "no schema clause".** `_schema_verdict` did `kind = str(schema.get("kind") or "none")`, so `""`, `0`, `False`, `[]`, `{}`, `0.0` and `None` all collapsed to the `"none"` sentinel and the unit was ADMITTED with BC-04/BC-05 never run, while the same malformation with a truthy value was HELD. The discriminator was falsy-vs-truthy — the exact trap D-3 killed at `unit.state`, one field over. The `unit.state` law is now applied to `schema.kind`: an undeclared `kind` (the key absent) is the documented "no clause" case and admits; `None` is `schema_kind_unobserved`; anything that is not a non-empty known string is `schema_kind_malformed`; `unknown_schema_kind:<name>` is kept for a non-empty string outside `none`/`additive`/`required`/`breaking`, so the type is never `str()`-coerced into the reason either. Before `56f817dc`: 7 of the 11 `schema.kind` probe rows rendered ADMITTED (the 7 falsy values) while the other 4 were HELD under the old `str()`-coerced reason; after: 11/11 render HELD with a typed reason, and the inverses (`schema` absent, `{}`, `"none"`, `"additive"` with reader proof) still ADMIT while a `"breaking"` clause still runs its own checks.
- **D-9 (medium) — six guards round 3 introduced were unpinned.** A one-line edit reopened each of them with `pytest tests/unit/test_onboarding_integration.py` still rc 0. Each is now pinned by a test that fails on its removal, and each pin carries its inverse so nothing is satisfied by refusing everything: `M13` `_as_hex_ref`'s 40-char ceiling (a 41-char string is not a target position), `M14` `_as_blob_map`'s path-is-a-string rule, `M15` `cleanup_disposition`'s consumer-id-is-a-string rule (which the removal turned into a `TypeError` out of a function whose docstring promises `UNKNOWN`), `M17` `_sha_for`'s unit-id-is-a-string rule, `M18` `_normalise_units`' exact-40-hex candidate sha (the strongest of the six: its removal produced a genuine false `ADMITTED`), and `M20` the 9-shape matrix's own `remote_merge_proof_malformed` vs `remote_merge_proof_unobserved` reason column, which round 3 asserted only as "UNKNOWN and not clean_merged_tree".

ROUND 4 MUTATIONS, verbatim (`mutate.py`, one edit per throwaway worktree copy, pristine bytes restored and sha256-verified after every one, green at the end: `115 passed, 120 subtests`, exit 0). **12 mutations, 12/12 caught, 0 survivors.** Each names the test that fails on its removal:

```
M-D8-revert-schema-kind-or-none   -> FourthRepairProofTests::test_a_falsy_schema_kind_is_never_a_silent_no_clause
M-D8-drop-kind-unobserved         -> same test
M-D8-drop-kind-malformed          -> same test
M13-hexref-maxlen-off             -> FourthRepairProofTests::test_a_target_position_is_at_most_forty_hex_characters
M14-blobmap-path-guard-off        -> FourthRepairProofTests::test_a_content_path_is_an_observed_string
M15-consumer-id-guard-off         -> FourthRepairProofTests::test_an_unobserved_consumer_id_never_raises_and_never_defers
M17-sha-for-guard-off             -> FourthRepairProofTests::test_a_frozen_sha_is_looked_up_by_an_observed_unit_id
M18-normalise-sha-40hex-off       -> FourthRepairProofTests::test_a_candidate_sha_is_exact_40_hex_or_the_unit_is_unknown
M20-proof-malformed-reason-swap   -> FourthRepairProofTests::test_the_malformed_and_unobserved_proof_shapes_name_their_own_reason
M20b-proof-unobserved-reason-swap-INVERSE -> the same test AND CleanupDispositions::test_merged_tree_without_remote_proof_is_unknown
M-V1-version-marker-alone         -> FourthRepairProofTests::test_the_skill_version_and_its_changelog_heading_are_one_number
SENTINEL-unit-states-shrink       -> RedSubset x2 and ThirdRepairProofTests::test_an_unrecognised_unit_state_is_unknown_never_not_red
```

`M20`/`M20b` are the inverse pair that shows the instrument is not stuck in one polarity: the malformed->unobserved swap and the unobserved->malformed swap each go red, on the new pin and on the round-3 test alike. `SENTINEL-unit-states-shrink` is the out-of-harness FAIL-CONTROL: it is unrelated to every pin above and still turns the suite red, so "everything green" was never a stuck instrument. Round 3's six survivors (QC D-9: `M13`, `M14`, `M15`, `M17`, `M18`, `M20`) are exactly the six now caught here — that is the point of this round's pin set.

BOOKKEEPING. `v2.0.128` is the number this repair allocates, and the allocation was verified rather than assumed. **Scope actually measured: every remote-tracking ref of `origin`, read with `git for-each-ref refs/remotes/origin` — BARE PREFIX, no `/*` glob, because the glob form returns only 113 of the 2003 names and hides 1890 namespaced refs — and the version each ref declares was read out of `38-conversational-ai-system/skill-version.txt` at that ref's own tree, in one `git cat-file --batch`.** Every command below was run in one harness (`ladder3.py`) and every exit code printed by the command itself:

```
git fetch origin                                                              -> rc 0
git rev-parse origin/main                                    -> 3c798db6659c576cc40e3ce8c81d2ede7acf3e0c
git show origin/main:38-conversational-ai-system/skill-version.txt             -> v2.0.105
git for-each-ref refs/remotes/origin                       | wc -l  -> 2003    rc 0
git for-each-ref 'refs/remotes/origin/*'                   | wc -l  -> 113     rc 0  (glob form; 1890 hidden)
git cat-file --batch over <ref>:38-conversational-ai-system/skill-version.txt
                                                             -> 2003 read, 0 missing, rc 0
git grep --fixed-strings -n '[2.0.128]' origin/main                           -> EMPTY   rc 1
git grep --fixed-strings -n 'v2.0.128'  origin/main                           -> EMPTY   rc 1
  POSITIVE CONTROL git grep --fixed-strings -n '[2.0.34]'  origin/main        -> 1 hit   rc 0
  POSITIVE CONTROL git grep --fixed-strings -n 'v2.0.105'  origin/main        -> 1 hit   rc 0
  NEGATIVE CONTROL git cat-file --batch on a bogus 40-zero object name        -> missing rc 0 (the missing path really fires)
  INSTRUMENT CONTROL  the same cat-file --batch with a REAL object name under a made-up refname
                                                             -> resolves anyway (v2.0.18): this
                                                                instrument reads the SHA and never the
                                                                name, so a name/SHA mismatch is invisible
                                                                to it. Recorded below as a residual
                                                                hazard rather than hidden.
```

Both token forms are required and both were measured, because a bare number false-matches the presentations skill's `v22.0.3x..v22.0.8x` as a SUBSTRING; the bracketed form is the exact one and the `v`-prefixed form is the one the marker file uses. The declared-claim ladder was read per ref, not inferred, and scored NUMERICALLY (`major*1000000 + minor*1000 + patch`), never lexically: the maximum any ref declares is **`v2.0.123`** (`pb/PBB-420/t-28-repair5`), then `v2.0.122` x1 (`pb/PBB-387/t-14-repair4`), `v2.0.121` x1 (`pb/PBB-386/t-21-repair5`), `v2.0.120` x1 (`pb/PBB-378/t-08-repair5`), `v2.0.105` x4 (including `origin/main`), `v2.0.104` x2 (`origin/HEAD`, `pb/PBB-412/t-43-repair3`), `v2.0.103` x1, `v2.0.102` x1, `v2.0.101` x2, `v2.0.100` x1, `v2.0.99` x1, `v2.0.98` x2, `v2.0.97` x2, `v2.0.96` x1, `v2.0.95` x6. Max + 5 patches = **`v2.0.128`**, PROVISIONAL — one merge-time writer renumbers every landing candidate. `v2.0.124`..`v2.0.128` are each absent on `origin/main` in BOTH token forms (rc 1 each) and each held by 0 refs. The over-subscribed band `v2.0.97`..`v2.0.105` is deliberately avoided: `v2.0.101` has two holders, `v2.0.104` has two and `v2.0.105` has four. This entry and `v2.0.128` ride in the same commit. NOTE ON THE PREVIOUS NUMBER: the round-4 entry shipped as `v2.0.104` on `pb/PBB-412/t-43-repair3`, and that number is now taken by that ref and by `origin/HEAD`, so it cannot be re-used here.

MEASURED ZEROS AND THEIR CONTROLS. The V-1 failure was a reasoning failure, so the sweep covers the habit and not only the one sentence. Every "0 / zero / none / never / no longer" this release asserts about a measurement was re-measured on this tree, each with its command, its exit code and a same-instrument positive control (`attest.py` prints them):

```
"7 raised -> 0 raised"  verify_receipt() over 9 malformed receipt shapes -> raises=0 typed=9, rc 0
     POSITIVE CONTROL  verify_receipt(<honest PROVEN-shaped receipt>)    -> (True, '')
"zero removed, zero changed"  git diff --numstat 7a965c7f4 <this commit> -- tests/unit/test_onboarding_integration.py -> 0 deletions, rc 0
     POSITIVE CONTROL  the same command returns a non-zero addition count; the raw diff has 0 '-' lines
"the same four failures"  pytest tests/unit on detached origin/main, on the parent and here -> identical failure SETS by name, each run rc 1
     POSITIVE CONTROL  all three runs are red, so "the same four" is a set comparison and not an empty instrument
"11 of 11 schema.kind rows HELD"  probe_d8.py -> RESULT: PASS (42/42), rc 0
     POSITIVE CONTROL  the same probe on a detached worktree at 56f817dc -> RESULT: FAIL (32/42), rc 1, with 10 rows red: the 7 falsy kinds and `None` rendered ADMITTED (the admission hole itself), and `5` / `True` / `b'none'` were HELD but under the old `str()`-coerced `unknown_schema_kind:<str(value)>` reason
"0 of 11 malformed proof-id shapes authorise a deletion"  probe_claim.py -> `0 / 11`, `['M-1']` still authorises, `control direction verdict: OK`, rc 0
     POSITIVE CONTROL  the same probe on the parent 7a965c7f4 -> `9 / 11`, `control direction verdict: BROKEN`, rc 1
```

SWEEP, stated explicitly with its own numbers so this is a claim and not an impression. The whole diff against `7a965c7f4` (`git diff 7a965c7f4`, 693 added lines in rounds 3+4) was searched for sentences asserting a measured absence, with two filters and both counts printed: a loose one (`0 hit|zero hit|no hit|returns 0|rc=0|0 matches|no match|empty|absent|never|next free|nothing|none|not found|not present|not claimed|is not in|unobserved|measured`) matched **130** added lines; a narrow one (`0 hit|returns 0|0 matches|no match|next free|looked for|not found|no such|EMPTY`) matched **15**. Of those 15, **4** are the measured-absence lines themselves — the two `-> EMPTY rc 1` grep results, their `NEGATIVE CONTROL` sibling, and the round-3 BOOKKEEPING sentence quoted inside the V-1 bullet — and all four now carry command, exit code and control. The other 11 are code docstrings ("every path and every blob id must already be a non-empty string"), test docstrings, a `assertNotIn` assertion, and the D-1..D-7 and D-8 bullets describing what the code does; none of them claims that an external search came back empty. Two sentences in this entry assert measured zeros in prose ("0 raised", "zero removed, zero changed") and are listed in the block above rather than matched by either filter. One further sentence **outside** this diff was found and left alone deliberately: the T-19 entry on `origin/main` says "Pinned by `BookkeepingTests`", and no such test exists in `tests/`. It is main's sentence, not this commit's, and changing it here would rewrite another task's record.
## [2.0.179] - 2026-10-26 - feat(fulfillment): the T-13 direct original fulfillment module gets a real production call site and its suite step (PBB-647)

T-13 (R-10/R-12; C-13, C-F04, C-F07, C-F09) shipped `tools/direct_fulfillment.py` and merged, but nothing outside its own tests called it: zero non-self, non-test, non-CHANGELOG, non-evidence production references at `origin/main` `de85ac2f0`. An artifact no production path calls is not a deliverable.

- **Production call site, in an existing production entry point.** `tools/pb_contracts.py` — the shared contract CLI that already fronts the outbound-action lifecycle — gains `fulfill-basis`, `fulfill-access`, `fulfill`, `fulfill-resume`, `fulfill-proof` and `fulfill-continue`, each driving the module through its public API only. The CLI still talks to no provider itself: the module sends through the caller's append-only journal and these commands hand it files and print its outcome. Before this commit the module had 0 production importers and 0 production call sites.
- **Exactly one added CI step.** `.github/workflows/qc-static.yml` gains one step naming `38-conversational-ai-system/tools/tests/test_direct_fulfillment.py` BY EXPLICIT PATH (the T-22/T-15 explicit-name pattern: resolve, DRY-list, absent-checkout SKIPs loudly, `python3 -I`), directly after the T-24 pb-contracts step. Measured against the live base `3d7135664`: 0 of 66 workflow files named this suite before, 1 of 66 after; qc-static steps 145 -> 146, the hit at index 146 one-based, no other step touched.
- **Suite evidence (targeted, stdlib only; MEMORY GREEN with permits).** `python3 -I 38-conversational-ai-system/tools/tests/test_direct_fulfillment.py` = 16 tests OK. `python3 -I 38-conversational-ai-system/tools/direct_fulfillment.py` self-check = `OK 8 PASS`. Regression controls: `tests/test_pb_contracts.py` 46 OK (skipped=1), `scripts/qc-pb-contracts.sh` 46 OK. CLI smoke end-to-end: basis recorded; `fulfill` sent once (`sent` / `accepted`, admission never claimed as delivered); a second `fulfill` returned `already_satisfied` / `already_sent` with the journal still at one row; a real receipt promoted `accepted -> delivered`; `fulfill-continue` returned `continuation_ready` with `continuation_allowed: true`; `fulfill-resume` returned `nothing_to_do`. The full repository suite stays PENDING — it was not run here.
- **Pre-existing red named, not inherited silently.** `tests/test_interactive_owner.py` fails on a clean `origin/main` checkout in a real git worktree too (control: this change's edits stashed); the failing cases are T-19's bookkeeping locks against numbers already published on main, not this unit's to rewrite.
- **Version number re-cut at merge time.** The first cut was `2.0.152`; the freshness merge brought main to `2.0.178`, so this change is `2.0.179` — above main's newest, and not a number another live branch already names.

## [2.0.178] - 2026-10-25 - ci(receipts): run the T-25 receipt tests in the workflow that gates this repo (PBB-496, T-25 reachability)

The T-25 module's own test file had no call site anywhere in `.github/`, so its pins were enforced by nothing: a pin could be deleted and the build would stay green. This wires it in. One step, one file, no product change.

- **Wiring, matched to a sibling entry.** A single step `shared-utils publication receipts unit tests (T-25)` is added to `.github/workflows/qc-static.yml`, in the same shape as the adjacent `Skill 38 canonical playbook engine unit tests (U-16)` step: `- name:`, `shell: bash`, `run: |`, `set -uo pipefail`, a comment naming what the gate protects, the command, then a `✓` line. The command is `python3 -I shared-utils/receipts/test_publication_receipts.py`, the same invocation the module's own suite is run with. The step carries no `${{ }}` expression, so there is no interpolation surface for untrusted input.
- **Measured, not assumed.** The workflow parses after the edit — `yaml.safe_load` gives 1 job and 141 steps, and the new step name is present. Before the edit, a whole-`.github/` fixed-string census found zero occurrences of `test_publication_receipts`, `shared-utils/receipts` or `publication_receipts`, so the zero-call-site finding is measured rather than inferred.
- **What this does NOT change.** The module's public functions still have no production caller outside `shared-utils/receipts/` and its own test — the same is true of every accepted peer module in that layer (`unit_status_core`, `social_bootstrap`, `discovery_aliases`, `winner_harvest`, `workflow_slots`, `tamper_guard`), so it is the layer's norm rather than a defect this task introduces. Wiring the module into a `qc-*.sh` runner remains outside this task's file ownership and is left for the T-25 follow-on.

## [2.0.177] - 2026-10-25 - chore(t-25): land T-25 on live main and re-cut the T-25 release numbers above the measured maximum (PBB-496, T-25 merge and renumber)

Release bookkeeping for the merge that brings the T-25 candidate onto live `origin/main` and re-cuts its release numbers. This entry replaces an earlier one that claimed a ladder measurement it did not take: that entry asserted `2003` remote refs, a numeric max of `(2,0,123)` and that `2.0.125`..`2.0.128` were "free across all 2003 refs in both roles". Every one of those figures was stale or false when written, and each is re-derived below from a measurement taken in this run. A number already claimed by another ref names two changes with one number, which is the defect class this entry exists to close. No product file and no test file changes in this commit; only this entry and `skill-version.txt`, as CONTRIBUTING.md (Release Ceremony Batching) requires.

- **The merge.** Merge-base `3c798db6659c576cc40e3ce8c81d2ede7acf3e0c`; measured `git rev-list --left-right --count origin/main...HEAD` = `40	5` before the merge (40 on main not on the branch, 5 on the branch not on main). Exactly two paths conflicted, both release-ceremony files: this `CHANGELOG.md` and `skill-version.txt` (`v2.0.128` against `v2.0.133`). No third path conflicted, and no product or test file was in conflict. The shared body from `## [2.0.28]` down is byte-identical on the merge-base, the branch and main — measured sha256 `05f90b21b50b8decfc842efd37199a76911225cb4d2413eb3bc538e7148c0d8d` on all three — and was not touched. Brought forward with `git merge origin/main`, never a rebase, so the reviewed commit `753a112918e53ba05c9d4f8c190b80bda1896f35` stays an ancestor of everything that lands.
- **Main, measured not remembered.** `origin/main` = `b011d2cc2c90e8ad13dab9a980fa4a0e05b23ced`, agreed by three independent reads (`git rev-parse origin/main`, `git ls-remote --heads origin main`, `git for-each-ref refs/remotes/origin/main`). It had moved 22 commits past `c883b35ce9f594b4450e5cffc654ec4945cef2d3`, the value an earlier verifier measured — `git merge-base --is-ancestor c883b35ce b011d2cc2` rc 0 and the reverse rc 1, so the move is forward only. Main's own marker is `v2.0.133`, so a branch at `v2.0.128` is now below main as well as duplicated.
- **Ladder, measured not remembered.** `git for-each-ref refs/remotes/origin` with a bare prefix and no `/*` glob enumerates **2040** remote refs; the glob shows only **113** and hides **1927** namespaced ones, which is why the prefix is bare. The unit's two version surfaces are `38-conversational-ai-system/skill-version.txt` and its `CHANGELOG.md` headings; every ref's pair is read through one `git cat-file --batch` stream — **172608** requests, **148492** records, **24116** missing paths, instrument complete. Unit marker numeric max and unit heading numeric max are both **`2.0.149`**, held by `refs/remotes/origin/pb/PBB-449/t-21-update`. A known-present control rides in the same harness — `refs/remotes/origin/main` must resolve to marker `2.0.133`, and does — so a zero result would have named a broken instrument instead of a free number; `refs/remotes/origin/zzz/definitely-absent` must be absent, and is. The lexical trap is live: string-sorting picks `2.0.99` over `2.0.149`. Every comparison in the harness is a tuple compare. (Other skills carry their own version series — the tree-wide marker maximum is `27.1.74` — and are deliberately not the gate for this entry.)
- **The renumber.** `2.0.128` is already claimed twice over: **6** refs carry it in the unit marker role and **10** carry it as a unit heading, including `refs/remotes/origin/main` itself. The three earlier T-25 entries sat at `2.0.125`/`2.0.126`/`2.0.127`. All four are re-cut together to `2.0.174` < `2.0.175` < `2.0.176` < `2.0.177`, a block strictly above the measured maximum `2.0.149` and free in both roles across all 2040 refs. The gap above `2.0.149` is deliberate margin: several sibling branches are landing release numbers in the same window and a `+1` block races them. Each entry's own prose citing its own number was renumbered with it.
- **Absence on `origin/main`, all three token forms, controls in the identical invocation shape.** A fixed-string census of every one of **13797** blobs of `b011d2cc2` finds **no** occurrence of `2.0.174`, `2.0.175`, `2.0.176` or `2.0.177` in bare, bracketed `[x.y.z]` or `v`-prefixed form — 12 tokens, all absent. The known-absent control `zzq_nonexistent_token_qq` is absent, and the known-present controls `[2.0.34]`, `v2.0.95` and `2.0.133` are all present, so the 12 absences are answers and not a dead instrument. Brackets stay mandatory for a heading claim — a bare `2.0.34` false-matches the presentations tree's `v22.0.34`, which is reproduced in the same run.
- **Provisional.** `2.0.177` is a merge-time allocation, not a permanent reservation. One merge-time writer renumbers every landing candidate in sequence, so if another candidate lands first this number is cut again before merge.

## [2.0.176] - 2026-10-24 - fix(receipts): a parent id is compared by identity, and malformed plan input is a ReceiptError (PBB-119 T-25 repair 3, PBB-273)

Repair round for the independent QC verdict `qc4-t-25`, which FAILED candidate `ead48c654ff16bcc9c5de1cb683cf9637662b38b` on three defects (its N1, N2, N3) plus carried non-gating notes N4/N5/N6. Scope unchanged: `shared-utils/receipts/` only, plus this entry and `skill-version.txt` in this one commit, as CONTRIBUTING.md (Release Ceremony Batching) requires. No live actions, no network code, no new storage, no new send path.

- **Defect N1 — the parent compare was by spelling, not identity (R-05/R-06).** Exactly the defect class the previous round closed on `provider_object_id`, one branch over. `validate_provider_receipt` compared `parent != expected_parent`, and `resume_plan` stored `post_object_id[placement_id] = receipt["provider_object_id"]` raw. So a post receipted with `provider_object_id=" fb-post-900 "` counted as received (the module already accepts a padded real provider id), while its comment's `parent_provider_object_id="fb-post-900"` was refused with `"$.parent_provider_object_id: 'fb-post-900' is not the receipted post ' fb-post-900 '"` — so the comment never counted as received and was never resumed. Reverse direction fails the same way. Fix: the parent compare runs through the same identity helper as the echo compare (`contracts.normalise_evidence_id` on both sides, factored out as `_same_id`), and `resume_plan` keeps the receipt's raw provider id for the plan while comparing by identity. Symmetric, both directions pinned.
- **Defect N2 — a local id echoed into the parent field counted as a receipt (R-05).** `parent_provider_object_id` was never checked against `LOCAL_ID_FIELDS`, so `validate_provider_receipt(comment, comment_receipt(parent=item["action_id"]))` returned `[]` and `true_receipt` handed that back as publication evidence — contradicting the module's own headline claim that "a local id echoed back ... never counts". Not reachable through `resume_plan` (which always passes `expected_parent` for a comment) but reachable through the public `validate_provider_receipt` / `true_receipt` default path. Fix: the echo check is now one helper, `_provider_id_errors`, run over `provider_object_id` and over `parent_provider_object_id`; the string-shape test moved into it, so a non-string id refuses on either field with the field named. Deliberately NOT extended to `expected_parent`, which is a caller-supplied comparison target rather than a receipted id.
- **Defect N3 — malformed plan input escaped as a built-in, not `ReceiptError` (hardening).** `ReceiptError` is documented "Malformed plan input. Fail closed: nothing is published", but `resume_plan(store, mf, [None], path)` raised `AttributeError: 'NoneType' object has no attribute 'get'`, and `item_key(None)`, `true_receipt(store, None)` the same. A caller catching only `ReceiptError` lost the error-type half of that contract (publication itself was already fail-closed). Fixed at the class, not the instance: `_plan_item` is the single shape guard and every entry point goes through it (`item_key`, `true_receipt`, `validate_provider_receipt`, `approved_order`); `approved_order` refuses a non-sequence plan; and the two dict lookups that crash on an unhashable field (`ORDER_RANK.get(purpose)`, `placement_index.get(placement_id)`) now take their default only from a string.
- **Proof — before/after, re-measured in this run against the named blobs.** The current 38-test file run against the unpatched module blob `dbfc72ccf1bfbd955435351fd1698c5232ef92b7` (the module at `ead48c654`, verified against `git ls-tree ead48c654`) reports `Ran 38 tests ... FAILED (failures=4, errors=2)`, and the six reds are exactly the three named proofs plus the two `MalformedInputTests` and the carried N4: `test_the_parent_compare_is_by_identity_not_spelling`, `test_a_padded_post_receipt_still_serves_its_missing_comment`, `test_a_local_id_echoed_as_the_parent_is_not_a_receipt`, `test_a_non_object_plan_item_is_a_receipt_error`, `test_a_non_list_plan_or_unhashable_field_is_a_receipt_error`, `test_a_bool_or_non_finite_timestamp_is_refused`. Against this tree the same file reports `Ran 38 tests ... OK`. Every new test carries its own control (a different post is still refused; a real provider parent id is still accepted; a well-formed plan still resumes, from a tuple too).
- **Proof — no assertion weakened.** `git diff --numstat ead48c654 -- shared-utils/receipts/test_publication_receipts.py` = **147 / 0**. Additions only. Suite count 31 -> 38.
- **Proof — suites, re-measured in this run.** `python3 -I shared-utils/receipts/test_publication_receipts.py` **38 tests OK**; `scripts/qc-pb-contracts.sh` **42 tests OK**; `scripts/qc-playbook-engine.sh` **44 tests OK `RESULT: PASS`**; `tools/tests/test_durable_processing.py` + `test_tenant_identity.py` + `test_collection_lock.py` + `test_pb_contracts.py` **116 passed, 1 skipped**. (An earlier revision of this entry read "117 tests OK" for that last suite; re-measuring shows 116 passed and 1 skipped, and the claim is corrected here.)
- **Carried forward, not gating.** N5 (this file's `2.0.174` entry reads "its comments in the approved content order", broader than the code, which ranks `REVEAL_COMMENT` before `BONUS_COMMENT`) and N6 (`true_receipt` returns the first valid receipt in `PERSISTED_RECEIPT_KINDS` order, so a valid dispatch receipt wins over a valid ack naming a different object) are both recorded rather than changed: N5 is a wording fix to an entry this task does not own, and N6 is the documented "strongest publication evidence first" order with no clause break. C-F10 and C-F17 remain UNPROVEN package-wide, as the QC recorded.

## [2.0.175] - 2026-10-24 - fix(receipts): a decorated local id is still a local id, and an in-flight attempt is never resumed (PBB-119 T-25 repair)

Two defects from the independent QC defect packet against candidate `d7ec43e34`, each pinned by a test that fails before the fix and passes after. Scope unchanged: `shared-utils/receipts/` only, plus this entry and `skill-version.txt` as CONTRIBUTING.md lines 76 and 116-117 require in the same commit. No live actions, no network code, no new storage, no new send path.

- **Defect D1 — a decorated local id passed the echo defence (requirement R-05).** `validate_provider_receipt` compared `provider_object_id` to the local fields with `==`, so an echo wrapped in decoration was not recognised as an echo: `post_receipt(object_id=" " + item["action_id"] + " ")` returned `[]` and would have counted through `true_receipt`. The module's own claim was "a local id echoed back ... never counts", and `" act-x "` is an echo that counted. The fix compares identities rather than spellings: both sides go through `contracts.normalise_evidence_id` (the T-08d normaliser, which already trims whitespace and category Cf from both ends) before the comparison. Symmetric, so decoration on the local field cannot hide an echo either. The message still names the raw value and the field it echoes. Pinned by `test_a_decorated_local_id_echo_is_not_a_provider_receipt`, which covers all three local fields (`action_id`, `logical_intent_key`, `idempotency_key`) under three decorations each (space padding, U+200B, U+FEFF) plus the reversed direction and a `true_receipt` end-to-end case.
- **Defect D2 — an action with an open attempt was returned in `resume` (requirements R-05/R-06).** After `queue` -> `claim_for_dispatch` -> `begin_attempt`, the row is `state='queued'` with an attempt whose outcome is still NULL: a send in flight that may or may not have reached the provider. `resume_plan` returned it in `resume`, contradicting the module's own claim that resume "never re-issues ... a possibly-sent effect", and the block reasons it does own (`STATE_UNKNOWN`, `EFFECT_WITHOUT_TRUE_RECEIPT`) exist for exactly that reason. The fix blocks on `store.unresolved_attempt(row["action_id"]) is not None` with reason `ATTEMPT_IN_FLIGHT`, consulted only after the existing state reasons so a stronger reason is never masked. Pinned by `test_an_in_flight_attempt_is_never_resumed`, which also keeps the two controls: an admitted item with no attempt still resumes, and once the attempt is reconciled with a true provider receipt the item lands in `already_received`. QC severity note carried forward: `claim_for_dispatch` already refuses while an unresolved attempt exists, so this was a wrong plan rather than a duplicate send.
- **Proof — before/after, re-measured in this run.** The current 38-test file run against the module at `d7ec43e34` reports `Ran 38 tests ... FAILED (failures=6, errors=2)`, and both new proofs are among the reds: `test_a_decorated_local_id_echo_is_not_a_provider_receipt` and `test_an_in_flight_attempt_is_never_resumed`. Against this tree the same file reports `Ran 38 tests ... OK`, so the fixes move nothing else.
- **Proof — suites, re-measured in this run.** `python3 -I shared-utils/receipts/test_publication_receipts.py` **38 tests OK**; `scripts/qc-pb-contracts.sh` 42 tests OK; `scripts/qc-playbook-engine.sh` 44 tests OK `RESULT: PASS`; the four `tools/tests` files above **116 passed, 1 skipped** (corrected from an earlier "117 tests OK").
- **Not changed, recorded rather than hidden.** The two QC "nuance" notes and the `float()` timestamp coercion are unchanged, because each is either not a gate or is pinned behaviour of a clause the QC marked PROVEN: the reveal/bonus comment rank is the taught sequence from SPEC.md line 15, and `numeric-string timestamps accepted` is an inverse control in clause 7 that tightening would break. The `C-F10` and `C-F17` focused traces remain UNPROVEN package-wide — every `C-F01`..`F-20` row in ACCEPTANCE-MATRIX.md is UNVERIFIED — and no trace artifact for them is inside this task's file ownership.

## [2.0.174] - 2026-10-24 - feat(publication): true post/comment receipts, approved order and partial resume (PBB-119 T-25)

New shared module `shared-utils/receipts/publication_receipts.py` with its pinned tests. It owns only what the accepted T-12 and T-23 modules do not: which provider object proves a publication, the order publications follow, and what a resume may re-issue. Placement binding is delegated to `pb_contracts.approval_errors` and receipt persistence to `durable_store`; no guard is copied.

- **True provider receipts.** A publication counts only when the provider's own object id was persisted through the fenced outbox: provider named, `provider_object_id` present, object kind matching the purpose (a `SCHEDULED_POST` is a post object, `REVEAL_COMMENT`/`BONUS_COMMENT` are comment objects), `supported_status` in `accepted`/`sent`/`delivered`, and a comment naming the post it was published under. A blank or format-mark-only id, an id that echoes the local `action_id`/`logical_intent_key`/`idempotency_key`, a comment-shaped receipt on a post, an `unknown`/`failed_not_sent` status, or a comment whose parent is not the receipted post all refuse. The blank test reuses `pb_contracts.normalise_evidence_id` (the T-08d normaliser), so one predicate owns "carries no identifier".
- **Approved order.** The canonical sequence is the manifest placement order, then inside each placement the post, then its comments in the approved content order. Input order across placements is ignored; two posts in one placement and comments with no post are structural errors that publish nothing. An invalidated placement is reported `unapproved` with the T-23 guard's own reason and is never resumed, while its approved siblings continue.
- **Partial resume.** `resume_plan` returns the missing approved pieces in order and never re-issues a receipted item. A comment with no receipted parent post is `blocked: PARENT_POST_NOT_RECEIPTED`, because its parent provider id does not exist until the post is published; the next pass resumes it. Items whose durable state is `unknown` (`STATE_UNKNOWN`), dispatched without a true receipt (`EFFECT_WITHOUT_TRUE_RECEIPT`), suppressed, quarantined, canceled, or never admitted (`NOT_ADMITTED`) are blocked rather than replayed.
- **No one-minute rule.** `reveal_timing_errors` refuses only a comment that precedes its post. There is no minimum gap anywhere in the module. Marked `ponytail:` beside the code, naming the ceiling (clock skew across two provider hosts) and the upgrade path (normalise to epoch at the adapter). Wiring the module into a `qc-*.sh` runner is outside this task's file ownership and is left for the T-25 follow-on.
- **Proof — suites, re-measured in this run.** `python3 -I shared-utils/receipts/test_publication_receipts.py` **38 tests OK** (the suite grew to 38 across the two repair rounds above). Upstream regression unchanged: `scripts/qc-pb-contracts.sh` 42 tests OK, `scripts/qc-playbook-engine.sh` 44 tests OK `RESULT: PASS`, and `tools/tests/test_durable_processing.py` + `test_tenant_identity.py` + `test_collection_lock.py` + `test_pb_contracts.py` **116 passed, 1 skipped** (corrected from an earlier "117 tests OK"). No existing assertion was weakened.
- **Ceiling named.** `reveal_timing_errors` takes numeric provider timestamps; a provider that reports local wall-clock strings must normalise at the adapter. Marked `ponytail:` beside the code.
## [2.0.180] - 2026-10-25 - feat(discovery): useful help and a relevant real recommendation after the gift, wired into the delivery path (T-27, PBB-461 build + PBB-627 repair)

New module `tools/post_delivery_discovery.py` satisfies R-17 / C-27, the clause that "Phone-only, email-only and declining people still get the original resource and help. Skill 38 continues needs discovery, knowledge-based answers and a relevant resource/community/offer/calendar recommendation. No universal three-question gate and no capture-as-completion." The module itself is additive, standard library only, and exports `Catalog`, `KnowledgeBase`, `Discovery`, `DiscoveryError`. The PBB-627 repair (this release number) additionally wires the module into production and CI, as recorded in the Wiring bullet below; nothing existing is removed.

- **Real.** A catalogue item must name one of the four contract kinds (`resource`, `community`, `offer`, `calendar`) and a usable destination — an existing path, or an http/https URL whose host is dotted and not a reserved special-use name. Placeholders, fragments, pseudo-schemes, reserved hosts, dotless hosts, missing paths and duplicate ids are refused. An item marked unavailable is never recommended. The self-check proves each refusal against an accepted control (an existing local file and a real dotted host) so the check cannot pass by refusing everything.
- **Adaptive, not a questionnaire.** The pending question set is a function of the catalogue and of what is already known: a field is only asked when some AVAILABLE item can be matched by it, a learned field drops its own question, and a refused field is suppressed without blocking help. `questions()` shrinks monotonically to zero in the tests and is asserted not to be a fixed set of three.
- **No capture-as-completion.** One known need is enough to recommend; nothing requires the discovery set to be finished first. Phone-only, email-only and marketing-declined callers produce byte-identical recommendations and answers. The module deliberately exposes no capture endpoint, and the tests pin that absence both on the module and on `Discovery`.
- **Grounded answers.** An answer is returned only with the stored entry's own source; an unmatched topic returns `unknown` with no invented text.
- **Truthful records.** Provider acceptance is labelled `accepted`/`sent`; `delivered` requires an actual receipt. An outcome needs authoritative evidence unless it is `unknown`. Keyword and multi-touch attribution are preserved with `exact_post_causality` false, so a single post is never claimed as the cause.
- **Tests.** `tools/tests/test_post_delivery_discovery.py` (29 tests) plus the module's own assert self-check (33 assertions). `python3 -I tools/post_delivery_discovery.py` rc 0 `OK 33 PASS`; `python3 -m unittest discover -s tools/tests -p 'test_post_delivery_discovery.py'` rc 0, `Ran 29 tests ... OK`.
- **Wiring (PBB-627 repair).** The module is no longer test-only: `tools/direct_fulfillment.py` (the module that owns "the gift is delivered") imports it and its production entry point `record_delivery_proof()` calls `post_gift_help()` on the delivery-verified path, returning the help with the outcome (`FulfillmentOutcome.post_gift_help`). Answers carry their stored source, recommendations name real `resource`/`community`/`offer`/`calendar` items, discovery stays adaptive, and no catalogue means the truthful `no_match`, never an invented item. `.github/workflows/qc-static.yml` gains exactly one step, "Skill 38 post-delivery discovery unit tests (T-27)", running the suite by explicit path (`python3 -m unittest discover -s 38-conversational-ai-system/tools/tests -p 'test_post_delivery_discovery.py'`). `python3 -I tools/direct_fulfillment.py` rc 0 `OK 13 PASS`; `test_direct_fulfillment.py` 16 tests rc 0 (existing suite still green).
- **Bookkeeping (PBB-627 repair; supersedes the false claim this entry carried).** Version `v2.0.180` in `skill-version.txt` and in this heading. The derivation is numeric, over `38-conversational-ai-system/skill-version.txt` read at every remote ref (2,106 refs swept 2026-10-25, including `origin/main` = `v2.0.143` and all 89 remote `pb/*` branches, every one of which touches this path; 0 refs unreadable): the value range is `2.0.0`-`2.0.179`, the true numeric maximum is `v2.0.179` (held by `origin/pb/PBB-454/t-06-update`), and `2.0.180` is the smallest integer strictly greater than every value and used by no ref, so it is both above all and unique. A second sweep after the PBB-627 fold of the next `origin/main` (`a16081620`, which carries `v2.0.150`) covered 2,107 refs: `2.0.180` is held only by this unit's own two branches (the claim itself) and `2.0.181` is unused, so the number stays unique and strictly above every other branch's value — the same "held by this branch alone" convention as the `2.0.143` entry below. An earlier cut of this entry claimed the maximum was `v2.0.178` and picked `2.0.179`; a later sweep refuted that — `origin/pb/PBB-454/t-06-update` holds `v2.0.179` — so the number is rederived here as `v2.0.180`, measured, not guessed. The earlier `v2.0.133` claim in this entry was FALSE and is corrected here: `2.0.133` is not absent from `origin/main` — it already names the T-46 repair 4 (PBB-455) entry there (measured: token `2.0.133` appears 12 times in `origin/main:38-conversational-ai-system/CHANGELOG.md`) — and `v2.0.133` was never bumped, which is what failed CI gate G3 on the reviewed head. With this renumber the duplicate `## [2.0.133]` heading is gone: `2.0.133` now names only the PBB-455 entry, and `2.0.180` names only this one. Absence of the new number on `origin/main` is measured in bracketed form (explicit-path read of `origin/main:38-conversational-ai-system/CHANGELOG.md`: `[2.0.180]` -> 0 hits; `[2.0.179]` -> 0 hits) against the known-present control `[2.0.133]` -> 3 bracketed hits (bare `2.0.133` -> 12) in the same run, so the instrument reads present and absent correctly. Brackets mandatory: a bare number false-matches neighbouring version text as a substring.

## [2.0.150] - 2026-10-25 - fix(reminders): a provider admission never claims the final landed, a narrow refusal covers only the final it names, and a declined collection has its own stop (T-17 repair 2 + repair 4, PBB-272 / PBB-404)

This entry covers the T-17 repair work this ref carries: the repair-2 defect fixes below, plus the repair-4 corrections recorded in the last three bullets. One change, one number.

Repair round for the qc2-t-17 FAIL verdict on `639557222` (defects D1, D2, D3). All three were independently reproduced on those exact bytes before any edit, each with its own control leg. The reproduction is reproducible from this repo alone - the tree is extracted with `git archive` of `639557222`, the reviewed module is written over the tree's copy of `shared-utils/reminders/reminder_state_machine.py`, and the suite is run - so no out-of-repo probe script is cited as evidence here. Files: `shared-utils/reminders/` plus this changelog and `skill-version.txt`, in this one commit. No live actions, no network code, no vendor call.

- **D1 (blocking) - one ACK contract for the whole module.** `dispatch_final` closed `stopped_final` and returned `status='sent'` on a bare dispatch receipt, while `expire_final` refused the identical evidence: `store.receipts(action_id) == ['dispatch']` (no `ack`) gave `sent`/`stopped_final` on one path and `canceled`/`stopped_ineligible` on the other, and the early close was uncorrectable because expiry then reported `already_terminal`. `outbound_gate` documents `ST_SENT` as "provider returned an admission receipt" and `durable_store.record_dispatch` as "Provider admission is NOT completion; ack is a separate receipt" (`RECEIPT_KINDS = dispatch|ack|completion`), so an admission was being promoted into an acceptance its own contract forbids. `_close_if_acknowledged` is now the ONLY writer of `stopped_final`, and dispatch, reconciliation and expiry all close through it. A provider admission records `final_admitted` and returns `status='admitted'` with the sequence still `closing_final`; nothing is claimed as sent until a persisted ACK receipt proves the landing. The ACK can arrive through `reconcile_final(applied=True, receipt=...)` (which persists it as the ack via `durable_store.reconcile_applied`), through `record_ack` with a later `dispatch_final` call (an already-acknowledged action closes instead of being dispatched again), or at expiry. A reserved window that expires without an ACK still closes `stopped_ineligible` without ever claiming sent. `reconcile_final(applied=True)` with no receipt proves nothing under the same rule, so it records the admission and claims nothing rather than inventing a receipt.
- **D2 (minor) - a narrow refusal refuses only what it covers.** A `REASON_FIELD` refusal on the closing envelope's topic refused the reservation AND closed the whole sequence `stopped_complete`, while the same reason in `send_reminder` suppressed only that ask. `reserve_final` now applies the same DATA-CONTRACTS section 7 scope rule as the reminder path (one predicate, `_consent_is_terminal`): a channel opt-out or a field refusal refuses that one final and the sequence stays live, so a final on another channel or topic still reserves; a global stop, a human fence or an unrecognised reason still closes the sequence. The half the verdict called defensible is now stated in the module's STOP contract and pinned by a test: once a final IS reserved the sequence has one final, so a refusal recorded before dispatch cancels it and closes `stopped_complete` (section 8 step 3).
- **D3 (minor) - `stopped_declined` is reachable.** The state is declared in `COLLECTION_STATES`/`TERMINAL_STATES` and in `schemas/collection-state.schema.json`, but no path produced it and a declined collection closed `stopped_complete` instead. `decline()` records the person declining the collection: the pending reminders are suppressed (never un-sent), a reserved final action is canceled without claiming a send, and the sequence closes `stopped_declined` - its own terminal state, which `open_sequence` then serves without restarting capture.

- **Proof - before/after, one test file, one extracted tree.** The suite run against the reviewed module (`git show 6395572224bceb90d2203b4fb46686a87fe15738:shared-utils/reminders/reminder_state_machine.py` written over an otherwise identical tree) fails **10 of 51** (8 failures, 2 errors) and passes **51 of 51** after this repair. Re-measured for this entry at `v2.0.150`, not copied forward. Failing before: `test_d1_dispatch_admission_never_claims_the_final_landed`, `test_d1_one_evidence_class_one_verdict_across_paths`, `test_d2_a_narrow_refusal_refuses_only_the_final_it_covers`, `test_d3_a_declined_collection_closes_stopped_declined`, `test_d3_a_decline_refuses_a_reserved_final_without_claiming_sent`, and the five assertions that had carried a bare admission into a claimed send - `T06` `test_terminal_state_refuses_every_further_effect` and `test_second_dispatch_of_the_same_final_is_not_a_second_send` (through `_stop_by_acceptance`), `T08` `test_a5_terminal_stop_refuses_a_fresh_budget`, `test_a6_pause_refuses_the_reservation_itself`, `test_a9_a_final_with_no_completion_still_sends`. The inverse legs are green on BOTH trees, so the repair refuses nothing that is genuinely valid: `test_d1_reconciled_acceptance_still_closes_the_final`, `test_d2_a_refusal_after_the_reservation_still_closes_the_sequence`, `test_d2_a_global_stop_still_stops_the_whole_sequence`, `test_d3_an_undeclined_sequence_still_sends_its_reminders`. The ACK control is unchanged before and after and is pinned in-repo by `test_a8_ack_receipt_still_proves_acceptance` (`expire_final` with a persisted ack -> `sent` / `stopped_final`), and the same-evidence legs now agree: a bare `['dispatch']` receipt is `admitted` / `closing_final` on the dispatch path and `canceled` / `stopped_ineligible` at expiry - neither claims the landing.
- **No assertion weakened or removed.** Assertion inventory 238 -> 317 across 41 -> 51 test methods; zero methods missing, zero carrying fewer assertions than before. Both figures are counted with an `ast` walk of `shared-utils/reminders/tests/test_reminder_state_machine.py`, where an assertion is a call whose callee name starts `assert`, and "test methods" means the `def`s named `test_`. The earlier draft of this line read "238 -> 304 across 51 -> 62 methods", which is corrected here (repair 4): the assertion half was right as of repair 2 (304), but the method half mixed two different units and was unverifiable as written. The same file carries 61 -> 74 `def` in total and 51 -> 63 class-level methods, so a bare "methods" number is meaningless without the unit. (304 across 50 test methods is what repair 2 alone stood at; repair 4 adds the terminal-set pin below.) The five assertions that asserted the defect were kept and strengthened onto the ACK acceptance leg rather than dropped. `python3 -m unittest discover -s shared-utils/reminders/tests` = **51 tests OK**; `python3 shared-utils/reminders/tests/test_reminder_state_machine.py` = **51 tests OK**; `python3 -I shared-utils/reminders/reminder_state_machine.py` self-check **21 assertions** (16 before).
- **Nothing re-implemented.** ACK evidence is read from the upstream `durable_store` receipts and written only by `record_ack` / `reconcile_applied`; dispatch is still `outbound_gate.dispatch`; the consent reasons stay the `consent_gate` objects pinned as the same objects by `T07UpstreamReuse`. `decline()` uses the module's own `_cancel_siblings`, so a decline never un-sends and never mints a slot.
- **Ceiling named, not hidden.** A decline recorded while a closing action is mid-flight cancels the outbox action where the store allows it and never claims it was unsent; a final that was already dispatched is left to reconciliation. `ponytail:` the shared-budget ceiling from 2.0.30 stands unchanged - a narrow refusal still spends the slot as `suppressed`, and the upgrade path remains a channel-capable scheduler.
- **Repair 4 (PBB-404) - the terminal set is now pinned, and the gap was a pin gap, not a clause failure.** `TERMINAL_STATES` is the one set every guard reads: `snapshot`'s `terminal` flag is literally `row["state"] in TERMINAL_STATES`, and each mutation entry point raises `SequenceTerminal` behind that same membership test. Before this repair, deleting `STATE_STOPPED_INELIGIBLE` from that set left the suite green (rc 0, 50 tests, 0 failing) while behaviour silently diverged - the mutant read `terminal: False` and accepted a fresh invitation ("INVITE ACCEPTED on s1"), the control read `terminal: True` and raised `SequenceTerminal(sequence is already stopped_ineligible)`. Sends stayed 2 in both runs, which is exactly why the six acceptance clauses still held: the other terminal tests all drive `stopped_final`, which is itself in the set. `test_stopped_ineligible_is_in_the_terminal_set` now drives the one path that lands in `stopped_ineligible` (a reserved final that expires with no ACK) and asserts the terminal flag and the by-name re-entry refusal. Re-running the exact mutation makes it RED at `self.assertTrue(snap["terminal"])` (`AssertionError: False is not true`), and it is the ONLY test that fails there - 51 tests, 1 failure. Unmutated it is green, 51 tests OK.
- **Repair 4 - version renumbered off a number that named two changes.** This entry was filed as `[2.0.34]`, which is at/below live main (`v2.0.95`) and is already LANDED on main naming a different change - `origin/main:38-conversational-ai-system/CHANGELOG.md` carries `## [2.0.34]` for the T-23 manifest repair. One number, two changes. It is now `v2.0.150`, reserved for T-17 and free under both token forms on `origin/main`.
- **Repair 4 - two shipped claims were corrected rather than left standing.** The count claim is fixed above. The before/after proof also cited `scratch/pb-skill38-20261024/lanes/PBB-272-repair/probe_d123.py`, a scratch path that is not in this repo and no longer exists on disk, so it proved nothing to anyone reading the changelog; it is replaced by a reproduction anyone can run from this repo alone (git archive the reviewed commit, swap the one module, run the suite), with the numbers re-measured rather than copied. The ACK control is likewise cited in-repo as a named test instead of as "the probe's" control.

## [2.0.179] - 2026-10-25 - feat(acquisition): approval, capacity, claims and one accountable owner bind the brief, and a tampered owner is refused on the read path (T-06 update, PBB-454)

Lands the reviewed T-06 repair pair that `origin/main` did not carry — `e5e3a8728` ("T-06: bind approval, capacity, claims and one accountable owner") and `579b161d` ("T-06 repair4: enforce owner binding on the read path") — brought forward by MERGE, never rebased, so `579b161d` stays an ancestor of the branch tip. The census had ranked T-06 landed on content because `38-conversational-ai-system/tools/acquisition_brief.py` exists on `origin/main` (added by `8fd9f517c`, ancestor rc 0). Measured by ancestry rather than by that content judgement, the file was on main while the reviewed bytes were not: at merge-base `2fb558ba4` the reviewed commit was ahead 2 / behind 20 / diverged, `origin/main`'s blob for that path was still the pre-binding `e52616b54e`, and `tools/tests/test_acquisition_brief_binding.py` and `tools/tests/fixtures/synthetic_client.json` did not exist there at all. So this task needed a merge and not a no-op.

The reviewed bytes land unchanged. All three files in the reviewed diff are byte-identical to `579b161d` before and after both merges — sha256 `912043aebe…`, `35071a11db…`, `40dc4019d9…`, blobs `07e4a00230`, `4cec8b2d98`, `2d2aa423f0`, each classified IDENTICAL. `acquisition_brief.py` gains `bind_owner`, `bind_approval`, `bind_capacity` and `bind_claims`, and read-path validation that raises `BriefCorruptError` when a persisted owner has an empty role, an empty or malformed email, or a foreign `tenant_id` — the PBB-333 finding, where a hand-edited brief reloaded as `is_bound=True` and campaign-ready through both read paths. The new fixture and the new binding suite close the gap that let that ship: no test had asserted read-path refusal.

- **Bookkeeping.** Version allocated `v2.0.179` at the fold. The branch carried `v2.0.138` PROVISIONAL; when the branch was folded into `origin/main` `dfe9303f7` that number was re-measured NUMERICALLY as `major*1000000+minor*1000+patch` over `git for-each-ref refs/remotes/origin` (bare prefix, no `/*` glob): 2098 remote refs, 0 unreadable, 81 distinct `38-conversational-ai-system/skill-version.txt` values, highest claim `v2.0.178` (`2000178`) held by exactly one ref, `pb/PBB-450/t-25-update`; the `38-conversational-ai-system/CHANGELOG.md` heading census over the 89 remote `pb/*` refs plus `origin/main` peaked at the same `2000178`. The smallest integer strictly above every claim that no ref holds is `2000179` = `v2.0.179`; `v2.0.179` is absent from all 2098 refs and from all 90 CHANGELOG heading sets. Absence on `origin/main` measured over every one of its 13808 blobs in three token forms, each with its own count: `'2.0.179'` 0, `'v2.0.179'` 0, `'[2.0.179]'` 0, against present-token controls in the same run `'2.0.143'` 7, `'v2.0.143'` 3, `'[2.0.143]'` 2. Brackets mandatory: a bare number false-matches the presentations skill's `v22.0.3x..v22.0.8x` as a substring.

## [2.0.143] - 2026-10-25 - fix(pb-contracts): a new approved cycle, account binding or content revision is a new placement, not a duplicate (T-24, PBB-459)

`pb_contracts.py dispatch` identified a logical intent as `tenant_id::logical_intent_key`, a string the caller supplies. Every other placement field — the campaign cycle, the account, the account-binding revision, the content revision — sat outside the identity. The consequence was measured on live `origin/main` (`7477816dc`), not reasoned about: a **newly approved campaign cycle for the same placement collapsed as `DUPLICATE_LOGICAL_INTENT` and was never dispatched**. The retry leg was already correct and had to stay correct.

- **The defect, measured before any edit.** Two dispatches against one ledger. The retry of an unchanged placement returned `COLLAPSED / DUPLICATE_LOGICAL_INTENT` at 1 attempt (correct). A second action carrying the same placement `P-1` but a *new approved* `campaign_cycle_id` of `cycle-2026-12`, its own matching manifest and a matching `ALLOW` gate, returned **`COLLAPSED` as well** — `rc 0`, `decision COLLAPSED`, no send. The instrument control is carried in the same run: a genuinely different placement `P-2` on a fresh ledger returned `DISPATCHED`, so the probe discriminates and is not always reporting `COLLAPSED`.
- **What changed.** `idempotency_key()` now builds a public-placement identity from `tenant_id` + `campaign_cycle_id` + `placement_id` + `account_id` + `account_binding_revision` + `content_revision` + `logical_intent_key`. Same placement retried → same key → collapses; any of those five differing → a different key → dispatches. `logical_intent_key` stays in the key so two different intents on one placement (a scheduled post and its reveal) do not collapse into each other. Other scopes keep `tenant_id::logical_intent_key` unchanged.
- **`approval_revision` is deliberately NOT in the identity.** Re-approving unchanged content is freshness, and the dispatch gate already refuses a gate checked against another approval revision (`GATE_CHECKED_OTHER_APPROVAL_REVISION`). Folding it into the identity would let one placement post twice by re-approving it.
- **One owner, one migration.** `pb_contracts.py` remains the only owner of the identity. A version 1 entry never recorded which placement it belonged to, so its key cannot be recomputed without guessing, and guessing would silently un-collapse an in-flight action and could send it twice. `load_ledger` therefore migrates version 1 to version 2 by moving those entries to `legacy_actions` untouched; `dispatch` consults that map as a fallback and writes the entry back where it lives, and `receipt` reads both maps. A retry against a version 1 ledger still collapses — proven, not asserted, for **both** scopes. The first cut of that fallback was guarded `and action["scope"] == "public_placement"`, so for a `person_directed` action the lookup found nothing and a v1 entry the ledger already records at `sent` was dispatched a second time: measured on that head as `DISPATCHED / GATE_ALLOWED`, attempts 1, against baseline `c883b35ce` giving `COLLAPSED / DUPLICATE_LOGICAL_INTENT`, and the same at status `dispatching`. The guard is gone. For a non-public scope the old key is still the live key, so a general fallback is exactly right and never over-collapses.
- **Tests — 4 added, none removed.** `test_a_new_approved_cycle_is_a_new_placement_not_a_duplicate` drives the real CLI: prime the placement in `cycle-2026-11`, then dispatch the same `P-1` approved in `cycle-2026-12`, and require `DISPATCHED` with both placements recorded. `test_a_version_one_ledger_still_dedupes_a_retry` writes a version 1 ledger by hand and requires `COLLAPSED` at 1 attempt, the retry reporting the legacy key it actually collapsed into, then a `receipt` against that legacy key and the migrated shape on disk. `test_a_version_one_person_directed_retry_collapses` is the regression test for the duplicate-send above: a version 1 ledger holding a `person_directed` action at `sent` **and** at `dispatching` must both return `COLLAPSED` with the recorded status untouched and nothing new written. `test_each_placement_identity_field_makes_a_new_placement` pins `campaign_cycle_id`, `placement_id`, `account_id`, `account_binding_revision` and `content_revision` one subtest each — the clause names cycle/account/revision, and pinning only `campaign_cycle_id` would let a future edit delete the other four and stay green. The class-level `PUBLIC_KEY` pin is **derived** from `idempotency_key()` instead of hand-written; that follows the implementation rather than guarding it, so the per-field test above is what actually holds the identity together.
- **Suites, twice each, real rc, against a detached `origin/main` baseline at `b011d2cc2` (the main this branch merged).** Contract suite `test_pb_contracts.py`: candidate `Ran 46 tests … OK` rc 0 twice; baseline `Ran 42 tests … OK` rc 0 twice. `scripts/qc-pb-contracts.sh`: rc 0 twice on both trees (46 / 42 tests). Skill-38 tools discovery: candidate `Ran 410 tests` **4 failures** rc 1 twice; baseline `Ran 406 tests` **7 failures** rc 1 twice. The candidate's four are a **strict subset** of the baseline's seven — nothing new, and three cleared (`2.0.130` leg, monotonicity, shipped-above-main). An earlier cut of this entry said the two failing-name sets were byte-identical; that was measured against a pre-merge base and is corrected here to what the detached baseline shows. Every red is `test_interactive_owner.BookkeepingTests`, red on `origin/main` itself: `test_no_version_names_two_different_changes` and `test_no_version_this_branch_ships_appears_on_main` for `2.0.131`, `2.0.132`, `2.0.133` (that test greps the top four CHANGELOG numbers as bare strings, and main itself carries three of them). That window is owner decision #237 and is reported as numbers only, not scored here. Repo-root `tests/unit`: `Ran 1302 tests` **5 failures, 1 skipped** rc 1 twice, and the same five names on both trees (`test_execution_policy…test_managed_block_carries_four_categories`, `test_jev28_managed_instructions…test_canonical_policy_keeps_four_way_s5_4_distinction`, `test_owner_sends_hold…test_passing_gate_fires_control`, `test_skill23_build_nondestructive…test_existing_agent_is_not_repointed_to_a_new_sparse_tree`, `…test_no_duplicate_for_department_registered_under_another_key`) — its own baseline, nothing added. All eight `35-social-media-planner/scripts` suites rc 0 on both trees, twice. `bash scripts/bump-version.sh --check` rc 0 on both trees, twice.
- **Mutation control.** With `idempotency_key()` reverted to the pre-fix `tenant_id::logical_intent_key`, the suite returned `rc 1` and exactly **1** failure — `test_a_new_approved_cycle_is_a_new_placement_not_a_duplicate` — with every retry and control case still passing. Restored from a copy, `sha256` of `pb_contracts.py` identical before and after (`2ff379022c3c889beeb8ead35a748186da8b210ec7a27d2603ee098fec6894e9`). A test that fails nothing when the fix is removed would have been decoration. The repair round (PBB-484) re-ran the matrix as 7 mutations against the suite: the `public_placement` guard put back, and `placement_id`, `account_id`, `account_binding_revision`, `content_revision`, `campaign_cycle_id` dropped from the identity one at a time — every one `rc 1`, each killed by the test naming that field, with `pb_contracts.py` restored byte-identical after every mutation.
- **Bookkeeping.** Version allocated `v2.0.143` — **PROVISIONAL**, strictly above `origin/main`'s marker `v2.0.133` and held by this branch alone, enumerated NUMERICALLY as `major*1000000+minor*1000+patch` over `git for-each-ref --format='%(objectname) %(refname)' refs/remotes/origin` — a **bare prefix, no `/*` glob**: 2040 refs, 1984 distinct commits, 2040 readable versions, 0 unreadable, 0 unparsable, with the known-present control `origin/main` reading `v2.0.133` (numeric `2000133`) in the same run and exactly one ref holding `2.0.143` (this branch). The highest claim on `origin` is **`v2.0.149` on `pb/PBB-449/t-21-update`**, above this one, so the number stays PROVISIONAL and the single serial renumber writer at merge owns the final number. Absence on `origin/main` measured over every blob of that tree (13797 blobs, 12755 read back) in all three token forms, each with its own result: `'[2.0.143]'` **absent, 0 matches**, `'v2.0.143'` **absent, 0 matches**, bare `'2.0.143'` **absent, 0 matches**; present-token controls in the same run `'[2.0.133]'` present (2 matches) and `'v2.0.133'` present (3 matches), known-absent control `'[9.9.999]'` absent. Brackets mandatory: a bare number false-matches a neighbouring version as a substring.

## [2.0.133] - 2026-10-25 - fix(cleanup): an absence proof is a measurement, and a claim of absence for a path still present never dispatches (T-46 repair 4, PBB-455)

PBB-434's review of `ec3933772` returned FAIL for one reason: a hollow pin on a load-bearing acceptance clause. Its mutation pass over the pins that commit adds ran green at baseline (59 tests OK), killed seven of eight mutations, and left **M2 "absence proof always absent" SURVIVING at rc 0, 59 tests OK**. The suite asserted only the absent polarity (`{'lexists': False, 'absent': True}`), never the present one, so a proof that always claims absence was indistinguishable from a real one. The acceptance clause says "immediate eligible dispatch with preserved content, exact external path and actual absence proof", so a pin that cannot tell those apart is hollow on the clause itself.

Two pins added in `shared-utils/cleanup/tests/test_disposal.py` (`ThirdRepairProofTests`) driving the clause both ways. A genuinely proven absence dispatches immediately and the proof reports both polarities at the exact recorded path: `{'lexists': True, 'absent': False}` before, `{'lexists': False, 'absent': True}` after. And a removal that leaves the tree on disk must never dispatch: the proof comes back `lexists: True, absent: False`, the record is `BLOCKED_REMOVAL_FAILED` with `disposed: False`, `deletions` is empty and status is `INCOMPLETE`. Mutation M2 before -> after: **SURVIVOR rc 0, 59 tests OK -> KILLED rc 1**. The force-flag guard pin (M1) is kept unchanged.

No contract rule, schema, input class or one-responder rule is removed; nothing in `disposal.py` changes in this entry.

- **Bookkeeping.** Version `v2.0.133`, numerically above the live `origin/main` marker `v2.0.105` and above the highest version held by any remote ref, `v2.0.128` (`pb/PBB-439/t-04-renumber`), measured over all 2006 refs of `git for-each-ref refs/remotes/origin` taken with the bare prefix and no `/*` glob. Absence on `origin/main` in BOTH bracketed forms: `git grep --fixed-strings -- '[2.0.133]' origin/main` rc 1 and `git grep --fixed-strings -- '[v2.0.133]' origin/main` rc 1, against the present-token controls `'[2.0.95]'` rc 0 and `'[2.0.105]'` rc 0. Brackets mandatory: a bare `2.0.33` probe returns hits in `evidence/t01-interface-inventory.md` as well as the skill's own file, and the presentations `v22.0.3x` range swallows bare numbers too. The four numbers below are allocated at landing time for this branch's four commits: the branch shipped its code with no per-commit release bookkeeping, so the numbers are assigned here in one place rather than invented retroactively in each commit.

## [2.0.132] - 2026-10-25 - fix(cleanup): a proof must be a receipt, and unreadable content types UNKNOWN (T-46 repair 3, PBB-354)

Commit `ec393377218691904f294378644ea7f08e19a6c9` on branch `pb/PBB-354/t-46-repair3`. Provenance correction: that commit's own subject names `PBB-312 T-46`, but the repairer for repair 3 is **PBB-354** -- the branch that carries the commit names PBB-354 and the task ledger names repairer PBB-354. The subject is not rewritten (published history is never amended); the correct name is recorded here. A remote merge proof that is no receipt is no longer taken as proof, while a real remote merge proof still disposes; a malformed disposal receipt id no longer proves prior disposal, while a real one still does. Record content the module cannot read types as `UNKNOWN_UNREADABLE_CONTENT` instead of raising, and `dispatch` deletes nothing for such a record. Files: `shared-utils/cleanup/` only.

- **Bookkeeping.** `v2.0.132` allocated at landing time (see the `2.0.133` entry). Absent on `origin/main` as `'[2.0.132]'` and `'[v2.0.132]'`, both rc 1.

## [2.0.131] - 2026-10-25 - fix(cleanup): contained preserved copies, a force-flag guard in every spelling, proven caller copies (T-46 repair 2, PBB-265)

Commit `a96a25e591b457d5d31cc915ea2a2bdb63d60a54`. A preserved copy can no longer be steered outside the preserved root: an identity is folded into one safe path segment and the destination is proven contained before and after the copy. The symlink-component guard finds its boundary by resolution instead of a lexical comparison, so it fires when the approved root and the resource are written in different forms. The no-force guard refuses force in every spelling (`-f`, clusters like `-af`, `--force`, `--force=1`). A caller copy is proof only when its content is proven byte-for-byte against the resource at an exact external path; a preserved directory merely existing is never proof, and every deletion record carries that exact external path and its digest. A batch container that cannot be read types as `UNKNOWN_MALFORMED_ITEM` instead of raising. Files: `shared-utils/cleanup/` only.

- **Bookkeeping.** `v2.0.131` allocated at landing time (see the `2.0.133` entry). Absent on `origin/main` as `'[2.0.131]'` and `'[v2.0.131]'`, both rc 1.

## [2.0.130] - 2026-10-25 - fix(cleanup): receipt pre-flight, missing facts typed UNKNOWN, one containment test (T-46, PBB-131)

Commit `bd832e5f058c80e4b38c53ecc28a0b05101f398d`. The first landing of `shared-utils/cleanup/`: typed cleanup eligibility for scratch, merged, dirty and shared-consumer resources, immediate eligible dispatch with preserved content, the exact external path recorded, and an actual absence proof; nothing is ever force-deleted. The receipt target is proven writable before the first removal, so a receipt that cannot be written blocks every deletion as `BLOCKED_RECEIPT_DESTINATION`, and a write that still fails after removal is typed with the real deletions recorded inline instead of raising. A missing `clean_state` or `consumers` key is UNKNOWN, never a clean default. One contained-or-equal test serves both the receipt location (a receipt directly in the approved root is accepted) and caller copies (a copy equal to or containing the resource is not preservation). Files: `shared-utils/cleanup/` only.

- **Bookkeeping.** `v2.0.130` allocated at landing time (see the `2.0.133` entry). Absent on `origin/main` as `'[2.0.130]'` and `'[v2.0.130]'`, both rc 1.

## [2.0.128] - 2026-10-25 - fix(T-20): the merge is landed, the never-substring pin can now fail, and the bookkeeping is re-measured against live `origin/main` (PBB-442 repair of PBB-432 on `b4d4e5a336bb7cc87818434d536de4c41c95e395`)

Repair of the PBB-432 FAIL on candidate `b4d4e5a336bb7cc87818434d536de4c41c95e395` (ref `pb/PBB-411/t-20-repair4`). All four acceptance clauses of that review PASSED and nothing here re-opens them: separate public/opener/inbound eligibility with no route vouching for another; author exclusion living only in `durable_store.admit_event`, with a bare-string or non-iterable `own_actor_ids` refused as `RouteError` and a rejected admission writing nothing; keyword fallback with a known ref winning over a contradictory keyword, ambiguous keys refused naming the KEYS, and no invented attribution on `IG_DM`; `capability_status()` reporting `ordinary_reader_proof=DEFERRED`, `public_monitoring=NOT_PROVEN`, `ref_attribution=NOT_PROVEN`. The FAIL was on landability and on one hollow pin. `shared-utils/routes/page/facebook_routes.py` is **byte-identical** to the reviewed candidate throughout - blob `b8be28cc4714cc3a4264f1fa994287106eccfcd5`, sha256 `68efdfd127a469132a4be4a2c5feb875c4a949d1c26aaba12ff06e556a62b0e2`, before and after every mutation copy - so no behaviour changed and the whole repair is landability, one added pin and re-measured bookkeeping. The only product-file edit is additive and lives in `test_facebook_routes.py`: 19 inserted lines, 0 deleted. Its git blob goes `31d68088fc308d812a85a96888bb20bef623ca2b` (candidate) -> `9c735356b6339c8c18dc23c298409282addc36a4` (here), and its sha256 goes `cece93350a7fbb15d1500b54fa6c72e4bf13283e25d1e665c43ee14f978cedef` -> `7e25053fed7b1f12cc69a365a7be380b9d7346a0727a0dd879468acd20f5ca7b`. **Corrected (PBB-442, follow-up commit):** the sentence that stood here printed the sha256 `7e25053f...` in a slot the sentence had opened with the word `blob`, so `git rev-parse` on it returned `9c735356...` and the claim did not re-run from the committed tree. Both units are now named and both are given.

- **D1 - it did not merge.** `git fetch origin` first, because the FAIL's own figures were taken against a stale remote-tracking ref and one of its claims (`006fc42601148b34c29d5335daed4480e0bc52fb` "still EXACTLY live origin/main") was false by the time this repair opened: live `origin/main` is **`3c798db6659c576cc40e3ce8c81d2ede7acf3e0c`** at Skill 38 **v2.0.105**, proved two ways, `git ls-remote --heads origin main` and the `gh api` repository ref endpoint, both returning that sha. Re-measured against that fetched ref this branch was **127 behind / 6 ahead** (`git rev-list --left-right --count origin/main...HEAD` -> `127\t6`, merge-base `04fbdc240165345ab6a889d07595850b4315c708`), not 122 behind. `git merge-tree --write-tree origin/main HEAD` returned rc 1 with `CONFLICT (content)` in exactly two files, `38-conversational-ai-system/CHANGELOG.md` and `38-conversational-ai-system/skill-version.txt`; the code files were conflict-free. `origin/main` is merged in here as **`537eda7f43409b3d9a6da987fb41007662a1b77c`**, resolving each conflict by keeping this branch's own release blocks above main's and leaving `skill-version.txt` at `v2.0.103` so the merge itself changes no bookkeeping. The merge-seam ordering is disclosed below rather than papered over.
- **D2 - the bookkeeping gate, before and after the merge.** `BookkeepingTests` (`38-conversational-ai-system/tools/tests/test_interactive_owner.py`, a file the candidate did not carry and the merge brings in) was run against the candidate tree at three points. **Before the merge:** `Ran 4 tests ... FAILED (failures=4)`, rc 1 - `(2, 0, 28) already names an entry on origin/main`, `test_no_version_this_branch_ships_appears_on_main (version='2.0.28')`, `(2, 0, 103) not greater than (2, 0, 105) : the newest entry must sit above main's newest`, and `(2, 0, 103) not greater than (2, 0, 105) : the shipped version must never be at or below main's`. The FAIL recorded two failures; there are four against the live ref, because main has moved to `v2.0.105` since that measurement. **After the merge, before this repair:** `Ran 4 tests ... FAILED (failures=4)`, rc 1, and the names have changed - the two `[2.0.28]` failures are GONE, replaced by `(2, 0, 105) already names an entry on origin/main` and `test_no_version_this_branch_ships_appears_on_main (version='2.0.105')`. **The `[2.0.28]` ruling:** no renumber is needed and none is made. The duplicate `[2.0.28]` block the candidate carried next to main's is not a duplicate any more - the merged file contains the heading exactly once, `grep -cE '^## \[2\.0\.28\]'` -> `1` - and `[2.0.28]` has fallen out of the gate's four-entry window (`changelog_versions()[:4]`) because main's newer blocks now sit above it, so no failure names it. **After this repair:** `Ran 4 tests ... OK`, rc 0. The only version this branch changes is the one it adds: its own marker and its own new heading. No release block of `origin/main`'s is renumbered or rewritten.
- **D3 - the never-substring pin could not fail.** The one pin, `test_keyword_matching_is_not_a_substring_match`, drove `text="GUIDED"` against approved `"GUIDE"` - a SUPERSTRING, which exact, prefix AND substring matching all reject - so a substring mutation survived it untouched. That is now reproduced exactly here: with the new pin removed and `keyword in words` replaced by `any(keyword in k for k in words)`, the suite reports **`Ran 75 tests ... OK`, rc 0** - PBB-432's survivor, byte for byte. The new pin `test_keyword_matching_is_not_a_substring_match_in_either_direction` drives the SUBSTRING direction, `text="GUI"` and `text="IDE"` against approved `"GUIDE"` (plus the lowercase forms), which only an exact match refuses, and carries its own positive control (`text="GUIDE"` still returns `route='item-guide', reason='keyword_fallback'`) so the assertions cannot pass by the lookup being dead. With it present the same mutation reports **`Ran 76 tests ... FAILED (failures=4)`, rc 1**, and the only killing test name in the run is the new one. Five substring-shaped mutations were run against the committed tree, each replacing exactly `if keyword and keyword in words:` / `return EntryResult(route=words[keyword],` with `if keyword and any(PRED for k in words):` / `return EntryResult(route=words[next(k for k in words if PRED)]:`: `PRED = keyword in k` (PBB-432's M16) **4 failures rc 1**; `PRED = keyword in str(list(words))` **5 failures rc 1**; `PRED = keyword in k` under the second spelling `any(keyword in k for k in words)` **4 failures rc 1**; `PRED = k.startswith(keyword)` **2 failures rc 1**; `PRED = k in keyword` (the inverse direction, the one the old pin did cover) **2 failures rc 1**. The no-change control in the same harness is **`Ran 76 tests ... OK`, rc 0**, and the module is restored to sha256 `68efdfd127a469132a4be4a2c5feb875c4a949d1c26aaba12ff06e556a62b0e2` after every copy. This is a pin, not a behaviour change: `"GUI"` -> `None`, `"IDE"` -> `None`, `"GUIDED"` -> `None`, `"guide!"` -> `item-guide` before and after. The false attestation that this mutation yields `1 error` is corrected in place in the `[2.0.99]` block above.
- **D4 - the stale ref count.** Re-measured with `git for-each-ref refs/remotes/origin` as a **bare prefix, no `/*` glob**: **2003 refs**. The `refs/remotes/origin/*` glob returns **113** and hides namespaced branches, so it is not the count. The figure is stated as of the fetch that resolved `origin/main` to `3c798db6659c576cc40e3ce8c81d2ede7acf3e0c`, not as a standing number. The `1979 refs scanned` sentence in the `[2.0.103]` block is corrected in place alongside this entry.
- **Version - v2.0.128, measured not asserted.** Enumerated **numerically** as `major*1000000+minor*1000+patch`, never lexically, by one harness that reads every ref's `38-conversational-ai-system/skill-version.txt` through a single `git cat-file --batch` and carries two known-present controls in the same run: `refs/remotes/origin/main` must be present in the bare-prefix ref list (it is, among 2003), and `origin/main`'s marker must read exactly `v2.0.105` (it does). Both controls PASS; if either returned zero the check would be broken, not the target. The ladder: **true numeric max `v2.0.123`**, held by `refs/remotes/origin/pb/PBB-420/t-28-repair5`, then `v2.0.122` (`pb/PBB-387/t-14-repair4`), `v2.0.121` (`pb/PBB-386/t-21-repair5`), `v2.0.120` (`pb/PBB-378/t-08-repair5`), then `v2.0.105` on `origin/main` itself. True numeric max plus headroom of 5 gives **v2.0.128**, and the number is **PROVISIONAL** because the band `2.0.97`-`2.0.105` is over-subscribed across unlanded branches - `v2.0.101` alone has two holders, `pb/PBB-405/t-25-renumber` and `pb/PBB-421/t-25-verify`, and `v2.0.103` has one, `pb/PBB-411/t-20-repair4` (this branch's own reviewed ref) - so a single merge-time writer renumbers all landing candidates in sequence. 2003 refs hold `v2.0.128` as their marker **0** times. Absence on `origin/main` is proved in BOTH bracketed token forms, each with its own rc: `git --no-pager grep --fixed-strings -n '[2.0.128]' origin/main` rc 1, 0 lines; `git --no-pager grep --fixed-strings -n 'v2.0.128' origin/main` rc 1, 0 lines. Brackets are mandatory, because the bare form false-matches `v22.0.34` in the presentations skill; the gate itself greps the bare form, so the bare form is measured too and is also empty here: `2.0.128`, `2.0.103`, `2.0.101` and `2.0.99` each return rc 1 with 0 lines on `origin/main`. The instrument is proven alive in the same run by a known-present control: `git --no-pager grep --fixed-strings -n '[2.0.34]' origin/main` returns rc 0 at `38-conversational-ai-system/CHANGELOG.md:78`. The marker file reads `v2.0.128`.
- **Residual hazard, named.** Because `origin/main`'s release blocks are never rewritten and this branch renumbers only the entry it adds, the merged `CHANGELOG.md` is not globally newest-first across the merge seam: this branch's three T-20 lineage blocks (`[2.0.103]`, `[2.0.101]`, `[2.0.99]`) sit above main's `[2.0.105]` block. The gate passes - `changelog_versions()[:4]` is `2.0.128 > 2.0.103 > 2.0.101 > 2.0.99`, strictly decreasing, `versions[0]` above main's newest `(2, 0, 105)`, and the only entry at or above main's newest is this one - but the seam is an ordering inversion and a later reader should know it. Closing it would mean renumbering three entries rather than one, which is exactly the scope this repair was told not to take.
- **Proof - suites, each run twice on this tree with its own exit code.** `shared-utils/routes/page` **76 tests OK, rc 0** and **76 tests OK, rc 0** (75 before the added pin). `38-conversational-ai-system/tools/tests` and `scripts/qc-pb-contracts.sh`, `bash scripts/bump-version.sh --check` and the `scripts/ci/fast-guards.d/*.sh` guard trap both ways are recorded in the repair receipt alongside this entry.
- **Files changed:** `shared-utils/routes/page/test_facebook_routes.py` (19 inserted, 0 deleted), `38-conversational-ai-system/CHANGELOG.md`, `38-conversational-ai-system/skill-version.txt`. Migration notes: none - no schema, no command and no workflow change; risk LOW.

## [2.0.105] - 2026-10-25 - chore(t05-hygiene): redact the operator home path from the T-05 registration evidence (T-05 hygiene, PBB-413)

The recorded `launchctl print` capture in `evidence/engineering-loop-registration.json` embedded the real operator home directory in its `raw` field — an `ALWAYS_ON_TOKEN` banned by `scripts/qc-assert-no-client-names.sh`, which failed PR #2555's `QC static invariants` check with exactly 1 hit at that file's line 96. One substitution and one disclosure, nothing else: the home-directory component of the plist path is rendered as the placeholder `{{operatorHome}}` (the `{{...}}` placeholder shape named in that script's remedy text; `{{operatorHome}}` is not in `ALWAYS_ON_TOKENS`), and a new sibling `raw_redaction` field discloses exactly that substitution. The launchd attributes that make the T-05 acceptance proof real are byte-identical in that `raw` field — user domain `gui/501`, the job label exactly as launchd reported it, `active count = 1`, `type = LaunchAgent`, `state = running`, and the arguments tail `tick --run-id pb-eng-loop-20261024T0807Z-g2` with its run id and generation suffix. No record is deleted or hollowed out. (The label literal itself is quoted only in `evidence/`, outside this skill tree: this tree's own `qc-no-personal-data.sh` bans the operating brand token that label carries, so restating it here would red-block a gate whose whole purpose is that no identifier ships in skill content.)

- **Bookkeeping.** Version allocated `v2.0.105` (reserved for this batch) and assigned in this same commit. Absence on `origin/main` measured with BOTH token forms, each printing its own rc: `git grep --fixed-strings -n '[2.0.105]' origin/main` rc 1 and `git grep --fixed-strings -n 'v2.0.105' origin/main` rc 1, against the known-present control `git grep --fixed-strings -n '[2.0.34]' origin/main` rc 0 at `38-conversational-ai-system/CHANGELOG.md:61`. Brackets mandatory: a bare number false-matches the presentations skill's v22.0.3x..v22.0.8x as a substring. The number is deliberately NOT inherited from `7105bab51` (v2.0.98), which is already held by `pb/PBB-376/t-28-repair4` and would create a duplicate.

## [2.0.97] - 2026-10-25 - fix(eng-loop): configuration is read at use time, and malformed stop/payload input is refused, never raised (T-05 repair 2, PBB-279)

Second repair round for the engineering-loop adapter (`CONTROL/eng_loop.py`, `CONTROL/owner_handler.py`). Every defect below was reproduced on the reviewed bytes (`e7f5d98a`) before any edit, with the verifier's own controls (PBB-279) re-run unchanged. Nothing else in Skill 38 changes; the version rolls because the task commit carries the release bookkeeping.

- **D1 (blocking) — the isolated selftest wrote the production store.** `PB_STATE_DIR`/`PB_LABEL`/`PB_PLIST`/`PB_TMP`/`PB_CACHE` were copied into a module-level `EXTERNAL_ENV` map at import, and `run_handler` applied that map after `os.environ`, so the import-time value beat the runtime one. `cmd_selftest` sets `PB_STATE_DIR` to a sandbox at runtime, so the owner-handler child opened the OUTER store while the parent asserted on the sandbox. Configuration is now resolved by `refresh_config()` / `external_env()` from the current environment at use time; `main()` re-resolves before any command, `plist_payload` and the child environment both call `external_env()`, and `cmd_selftest` restores the caller's `PB_STATE_DIR` instead of deleting it. Controls: `env -u PB_STATE_DIR -u PB_LABEL -u PB_PLIST python3 CONTROL/eng_loop.py selftest` rc 0 PASS before and after; `PB_STATE_DIR=<sandbox> python3 CONTROL/eng_loop.py selftest` **rc 1 `handler_rc: 5`, state `dispatched` -> rc 0 PASS**, and the outer store is no longer created at all (`engine.db` absent after the run where it was a 72 KiB store before).
- **D2 — the stop ownership guard crashed instead of refusing.** `pargs[pargs.index("--run-id") + 1]` raised `IndexError` when `ProgramArguments` ended with `--run-id`. The value is now read with a bounds check; a flag with no value is refused `rc 3 job_not_owned_by_action_run_id`. Before -> after on `["x","--run-id"]`: rc 1 `IndexError` -> rc 3 refusal. Inverses unchanged: absent / `""` / `"   "` still refuse rc 3 and a matching run id still passes rc 0.
- **D3 — a boundary generation raised `OverflowError` out of the driver.** `request-stop --generation 9223372036854775808` (and a 40-digit value) reached a SQLite INTEGER bind. The value is now range-checked before the store is opened and refused `rc 3 generation_out_of_range`. Inverses unchanged: `2^63-1`, `-1` and `0` are still accepted rc 0.
- **D4 — a malformed payload leaked `JSONDecodeError`.** `create --payload '  '` and `--payload '{'` were parsed inside the write path. One `_json_arg` helper now parses `--payload` and the `--body` of `record-ack` / `record-complete`, refusing `rc 2 invalid_payload` / `invalid_body`. Inverses unchanged: empty, `{}`, `[1,2]`, `null`, `5`, `"hi"` still create rc 0.
- **Tests — the module shipped with none.** `CONTROL/tests/test_eng_loop_guards.py` (8 tests) covers the runtime-over-import precedence, the three refusals above and their inverse controls, and pins the stop-path guard both ways. Mutation control: against the pre-fix bytes **4 failures and 1 error**, all in the new cases, with every inverse/control case passing on both versions; after the repair **8 tests OK**. `python3 -m unittest discover -s CONTROL/tests` rc 0.
- **Bookkeeping.** Version allocated `v2.0.97` at merge and assigned in this same commit: it is above the live `origin/main` marker `v2.0.95` and above the highest unlanded claim `v2.0.96` (`pb/PBB-370/t-28-repair3`). Absence on `origin/main` is measured with the bracketed token form only: `git grep --fixed-strings -- '[2.0.97]' origin/main` rc 1 and `git grep --fixed-strings -- 'v2.0.97' origin/main` rc 1, against the present-token control `'[2.0.95]'` rc 0. A bare `2.0.36` probe returns `[v22.0.36]` in the presentations CHANGELOG, which is why the tokens are bracketed.

## [2.0.95] - 2026-10-24 - fix(interactive): the declared refusals are the refusals, and a whitespace-only name is not an id (PBB-271, T-19 repair 3)

Four defects from the PBB-261 review of `3b840d436`, reproduced on those committed bytes before any edit, plus the same class found by the same probe. No contract rule, schema, input class or one-responder rule is removed; three verdicts now name what the contract document already promised.

- **D1/D2 — bookkeeping regression.** This branch shipped `skill-version.txt` at `v2.0.31` while `origin/main` was already at `v2.0.33`, so a deployed box compared remote against local and saw "not newer"; and the T-19 entries claimed `2.0.29` / `2.0.30` / `2.0.31`, all three already published on `main` for other tasks (T-13, T-42, T-39), so one number named three different changes and the CHANGELOG stopped being monotonic. **Fix:** `skill-version.txt` is `v2.0.95`, above `main`'s `v2.0.33` at review and above `main`'s `v2.0.35` at merge; the three T-19 entries are renumbered `2.0.90` (feature) / `2.0.91` (PBB-115 repair) / `2.0.92` (PBB-169 repair 2), so the four T-19 entries read `2.0.90` < `2.0.91` < `2.0.92` < `2.0.95`, none of which appears anywhere on `origin/main`, and no number names two changes. This entry, the version bump and the code ride in the same commit (`CONTRIBUTING.md` "Release Ceremony Batching"). Pinned by `BookkeepingTests`, which reads `origin/main`'s own marker and CHANGELOG.
- **D3 — two declared refusals were unreachable code.** `NO_RESPONDER` ("responders must be a list") and `INVALID_STEP` (`free_text` not `accept`/`reject`) sat after `validate_schema`, which returns as soon as a field fails its type, so a contract naming `responders` as a string was refused `INVALID_CONTRACT: $.responders: expected type array` and a step with `free_text: "maybe"` was refused `INVALID_CONTRACT: $.steps[0].free_text: ...` — never the codes `launch/interactive-owner-contract.md` §2 and §3 tell a caller to assert on. **Fix:** those guards run first, as `_shape_errors`, so the same documents are still refused and now refuse with the code the contract document promises. The class is the ordering, not the one case: the same reordering also makes a whitespace-only `step_id`, control id or `free_text` refuse as `INVALID_STEP` instead of sliding through the schema's `minLength: 1`.
- **D4 — whitespace-only identity was accepted as a real id.** `{"steps":[{"step_id":"   ","controls":["  "]}]}` and `{"responders":[{"id":"  ",...}]}` validated `accepted`, exit 0 — yet the event side uses `_nonempty`, so a step declared `step_id: "   "` could never be reached by any event and the contract was valid and unroutable at the same time. **Fix:** contract-side `step_id` and control ids are judged by the same `_nonempty` the event side uses, refused `INVALID_STEP`. A responder `id` is a label, not a routing key (`§2` binds on `kind`), so it keeps the schema's `minLength: 1`; the class fix is the identity fields an event can echo.
- **M1 — the generation rule applied to free text.** `resolve_event` checked the generation before branching, so `{kind: free_text, step_id: pick_time, generation: 2}` came back `STALE_TAP` and a `reject` step with a stale generation came back `STALE_TAP` rather than `FREE_TEXT_REJECTED`. §3 gives `generation` to the step re-render and §4 routes typed text on the step's policy alone. **Fix:** the generation is judged on a control or a callback after the control is known to exist; free text routes (or is refused `FREE_TEXT_REJECTED`) whatever it carries. A control that names a control the step never rendered now answers `UNKNOWN_CONTROL` whatever else it carries, which is what the class of "long inline event" already expected.
- **M2 — §7 claimed an exit the tool never had.** "input nested deeper than the checker can walk" was unfalsifiable: 3 000-deep and 100 000-deep JSON parsed and returned a verdict, never exit 2. **Fix:** `DEPTH_LIMIT` (64) is walked with an explicit stack, so an event or a contract nested past it is the documented `2 = usage or IO` with the usage text — and the refusal itself cannot exhaust the stack. Everything at the depth a real contract uses (four or five levels) is untouched.
- **Proof.** New `ContractCodeTests` (5), `WhitespaceIdentityTests` (5), `FreeTextGenerationTests` (7), `DepthLimitTests` (4) and `BookkeepingTests` (4) in `tools/tests/test_interactive_owner.py` -- 25 tests, plus 3 subtest groups. One file, run twice: once against the reviewed bytes and once against this commit.
  - before, `3b840d4364191ebbbe807ab6b8c56efa13410000` module + this test file: **`FAILED (failures=28, errors=1)`** -- `BookkeepingTests` 7 (marker `v2.0.31` not above main's `v2.0.33`; `2.0.31`/`2.0.30`/`2.0.29`/`2.0.33` all already name an entry on `origin/main`; `2.0.29` not greater than `2.0.33` at the top of the file), `ContractCodeTests` 5 (`INVALID_CONTRACT` where `NO_RESPONDER`/`INVALID_STEP` was promised), `WhitespaceIdentityTests` 5 (`step_id: "   "` and `controls: ["  "]` accepted), `FreeTextGenerationTests` 7 (free text answered `STALE_TAP`, and a 900-character unknown `control_id` answered `MALFORMED_EVENT`), `DepthLimitTests` 5 (3 000-deep event and contract returned a verdict instead of exit 2; `DEPTH_LIMIT` did not exist).
  - after, this commit: **`Ran 83 tests ... OK`**, exit 0.
  - Inverse cases pass on BOTH sides, so the fix is surgical: `test_a_short_step_id_still_validates`, `test_the_routed_identity_is_the_owner_kind_not_the_responder_label`, `test_a_tap_still_needs_the_current_generation`, `test_a_known_control_with_no_generation_is_still_malformed`, `test_a_contract_that_only_fails_the_schema_still_says_invalid_contract`, `test_the_default_derives_exactly_one_responder`, `test_a_control_the_step_does_not_offer_is_refused` and `test_a_missing_generation_is_malformed_not_stale`.
  - No existing assertion removed or weakened: `git diff aa3d43d7f..HEAD -- 38-conversational-ai-system/tools/tests/` adds lines only (zero `-...assert` lines).
- **Acceptance instrument.** The PBB-261 probe (`probe_t19.py`, 114 cases) was run against the reviewed bytes first (`total=114 pass=103 fail=11`, the 11 exactly the cases above) and against this commit: `total=114 pass=114 fail=0`, with both live-instrument controls still splitting (`CTRL-A valid tap routes` exit 0, `CTRL-B two-responder refused` exit 1).
- **Suite.** `python3 38-conversational-ai-system/tools/tests/test_interactive_owner.py` → 83 tests OK (was 55). `bash 38-conversational-ai-system/scripts/qc-interactive-owner.sh` exit 0. Skill 38 `pytest 38-conversational-ai-system/tools/tests/` and Skill 44 `pytest 44-convert-and-flow-operator` compared against a detached `origin/main` worktree: the FAIL sets are identical, so nothing here is new red.
- **Bookkeeping note.** `main`'s own CHANGELOG already carries one legacy non-contiguous repeat (`2.0.0` at lines 427 and 2755) and repeats each number once per entry for one task; this change does not rewrite it. The T-19 block is contiguous and monotonic, and no number it uses appears on `main`.

## [2.0.92] - 2026-10-24 - fix(interactive): a null event is refused and a non-object contract is a verdict, not a crash (PBB-169, T-19 repair 2)

Two defects from the PBB-157 review of `cc79b30db`, reproduced on those committed bytes before any edit, plus the rest of the same class found by the same probe. No contract rule, schema, input class or one-responder rule changes.

- **Defect 1 — fail-open.** `resolve --contract tools/tests/fixtures/interactive-owner/valid.json --event null` exited 0 with `{"status":"accepted","errors":[]}`; a file holding `null` did the same. Cause: `resolve_contract` used `event=None` as its "validate only" switch, so a parsed JSON `null` skipped `resolve_event` and came back as a contract validation. **Fix:** the switch is now a private sentinel (`_VALIDATE_ONLY`); `None` is judged like any event and refused `MALFORMED_EVENT`, exit 1, `route: null`. `validate` passes no event and is unchanged.
- **Defect 2 — crash.** A contract file holding `null`, `[]`, `"hello"`, `5` or `true` (and a contract whose `owner` is a string, number or list) crashed both `validate` and `resolve` with an uncaught `AttributeError` at `interactive_owner.py:265` (`doc.get("owner")` before schema validation): exit 1, traceback, no verdict. **Fix:** the launch-bundle pointer is read only when the document and its `owner` are objects; the schema then refuses the document. Schema errors now carry the stable `INVALID_CONTRACT` code (it was declared but unused, so a refused verdict carried `code: "$"`), so the result is `refused` / `INVALID_CONTRACT`, exit 1.
- **Same class, IO side.** A contract or bundle path that is a folder, a file that is not UTF-8, and input nested deeper than the parser or schema checker can walk each raised a traceback (exit 1). They are now the documented `2 = usage or IO` exit with the usage text. On Python 3.9 (`/usr/bin/python3`) any inline event longer than one path name crashed with `OSError: File name too long` from `Path.is_file`; the file-or-inline probe now uses `os.path.isfile`, which answers False instead of raising.
- **Proof.** New `HostileInputTests` (12 tests, 30 subtests) in `tools/tests/test_interactive_owner.py`. Every case asserts exit code, verdict code, `route: None` and no `Traceback`, so it passes only on the documented answer. On the old bytes: Python 3.14 `failures=7, errors=19`, Python 3.9 `failures=7, errors=20`; on the new bytes both `OK`. Inverse cases pinned: omitting the event still validates (canonical fixture accepted, two-responders still `TWO_RESPONDERS`), the canonical file still validates and routes, and a long valid inline event routes. No existing assertion removed or weakened; the existing 43 tests are unchanged.
- **Docs.** `launch/interactive-owner-contract.md` §7 gains a three-row table naming the hostile-input verdicts.
- **Suite.** `tools/tests/test_interactive_owner.py` **55 tests OK** (was 43) on Python 3.14 and 3.9. Whole Skill 38 test set `pytest 38-conversational-ai-system/tools/tests/` **302 passed** (was 290), exit 0. Skill 44 `pytest 44-convert-and-flow-operator` **727 passed, 9 skipped**, exit 0 (unchanged). `scripts/qc-interactive-owner.sh` exit 0.
- **No new red.** `scripts/11-run-qc-checklist.sh`: 51 PASS / 28 FAIL on this tree and on a pristine `git archive cc79b30db` tree, `diff` of the FAIL lines empty. The T-19 row is PASS on both.

## [2.0.91] - 2026-10-24 - fix(interactive): an unparseable inline `--event` is a usage exit, not a traceback (PBB-115 T-19 repair)

One named defect from the T-19 review, reproduced on the committed bytes before any edit. No contract rule, schema or verdict code changes; the four input classes and the one-responder rule are untouched.

- **The defect.** `interactive_owner.py resolve --event '{not json'` raised an uncaught `json.JSONDecodeError`: exit 1, zero bytes of verdict JSON, raw Python traceback on stderr. The same bad bytes supplied as a **file path** were already handled cleanly by `contracts.load_json` (`UsageError` → exit 2), so the gap was exactly the inline `json.loads(value)` branch of `_parse_event`. The contract document (§7) states "Exit 0 = accepted or valid, 1 = refused or invalid, 2 = usage or IO" and shows `resolve` printing a JSON verdict — a caller-controlled string that will not parse yielded neither a verdict nor the documented usage/IO exit.
- **Fix.** The inline branch now wraps `json.loads` in `try/except ValueError` and re-raises as `contracts.UsageError("invalid JSON event: %s" % exc)`, which `main` already maps to exit 2 with the usage text. Same bytes, same verdict, inline or in a file. 3 lines in `tools/interactive_owner.py`; no new code path, no second parser.
- **Proof.** `test_an_unparseable_inline_event_is_a_usage_exit_not_a_traceback` asserts exit 2, the `invalid JSON event` usage message, **no** `Traceback` on stderr and an empty stdout — so the test fails on a raise and also on a silent exit-1-without-a-verdict, rather than passing on any failure. It fails before the fix (unittest error, the exact `JSONDecodeError` the review named) and passes after. Inverse: `test_resolve_returns_zero_for_an_accepted_tap` (unchanged) and the new `test_resolve_still_reads_a_valid_event_from_a_file` both still route a valid event to `openclaw_inbound`, so the repair did not narrow what counts as a usable event. `test_the_same_bad_json_is_the_same_exit_inline_or_in_a_file` pins the symmetry that motivated the fix.
- **Test-strength repair (same review class).** `test_native_ghl_is_refused_when_the_bundle_names_openclaw` could not distinguish "the launch bundle was read and names OpenClaw" from "the launch bundle yielded no owner record": both refuse with `OWNER_NOT_VERIFIED`, so the old assertion set (`assertTrue(errors)` + code prefix) passed even if `load_launch_owner` stopped reading the file at all. It now first asserts the read landed (`launch_owner == {"kind": "openclaw_inbound"}`) and then that the refusal says `does not name native_ghl`. Fault injection proves the split: with the loader stubbed to return `None` the old assertions pass and the new one fails; on the real bytes the new one passes. No existing assertion weakened or removed.
- **Suite.** `tools/tests/test_interactive_owner.py` **43 tests OK** (was 40). Whole Skill 38 test set green, **290 tests, 0 failures** (1 pre-existing skip in `test_pb_contracts`): acquisition_brief 23, asset_registry 39, collection_lock 23, consent_gate 24, durable_processing 26, interactive_owner 43, pb_contracts 42, playbook_engine 44, tenant_identity 26. `scripts/qc-interactive-owner.sh` exit 0.
- **No new red.** `scripts/11-run-qc-checklist.sh` on this tree: 51 PASS / 28 FAIL — byte-identical FAIL set to a pristine `git archive HEAD` tree (same 51/28, `diff` of the FAIL lines empty). All 28 were already red before this commit and are not touched here, including the `docs/lattice-citations.json` drift already recorded in 2.0.90.

## [2.0.90] - 2026-10-24 - feat(ownership): one responder for interactive workflow steps (PBB-115 T-19 / C-19)

Closes the interactive half of D-15 ("44 native-GHL ownership conflicts with 38 full default"). One new contract record, one stdlib resolver, one focused suite, one QC gate; no live effects, no network code, no change to any existing module.

- **The contract.** `launch/interactive-owner-contract.md` + `schemas/interactive-owner.schema.json` bind every interactive workflow input to exactly one responder. `owner.kind` defaults to `openclaw_inbound` when `owner` is omitted, so the OpenClaw route is the default rather than a preference. `responders` is derived when omitted; declared, it must be exactly one record whose kind matches the owner.
- **The four inputs.** `tools/interactive_owner.py` resolves `control` (a rendered control press), `callback` (the provider's delivery of the same press), `free text` (routed when the step's policy is `accept`, refused `FREE_TEXT_REJECTED` when `reject`), and the stale tap. A stale tap is **derived, never self-declared**: it is any control or callback whose `generation` differs from the step's current generation, refused as `STALE_TAP` with `route: null` so a late tap can never re-open a step, book twice, or reach a second responder. A future generation is refused by the same rule because a generation the contract has not issued is not current.
- **No two responders.** `TWO_RESPONDERS` (two or more records), `NO_RESPONDER` (zero) and `RESPONDER_MISMATCH` (one record whose kind disagrees with the owner) are contract refusals. A refused contract has no route at all, so every event against it is refused with the same code.
- **Reuse, not a second guard.** The module never judges whether a native GHL translation is approved. A `native_ghl` owner needs `owner.launch_bundle`, and the contract reads only that bundle's `reply_owner.kind`. The approval decision stays with `launch/qc-launch-conversation-ai.sh` (`REPLY_OWNER_TRANSLATION`): a bundle that names `native_ghl` without `translation_approved` is admitted here and still refused there. Pinned by `test_this_module_never_judges_translation_approval`. Schema validation reuses `pb_contracts.validate_schema` from the T-08 contract layer; no new validation engine.
- **The 44 side.** `44-convert-and-flow-operator/SKILL.md` now states it builds and QC's the workflow that renders the controls and **never answers a conversation or an interactive step**; its native node output is a build artifact, not a responder. Pinned by `test_skill_44_declares_it_never_answers_an_interactive_step`, so the ownership claim is a content assertion, not prose trust.
- **Proof.** `scripts/qc-interactive-owner.sh` (new) → `tools/tests/test_interactive_owner.py`: **40 tests OK** (5 fixture/schema, 4 OpenClaw-default, 4 controls, 3 callbacks, 3 free text, 5 stale tap, 5 single responder, 4 native GHL, 3 ownership documents, 4 CLI). Registered in `scripts/11-run-qc-checklist.sh`. Existing suites unchanged and green: `qc-pb-contracts.sh` 42, `test_durable_processing` 26, `test_playbook_engine` 44, `test_tenant_identity` 26, `test_consent_gate` 24, `test_collection_lock` 23 — **225 skill-38 tests, 0 failures**. No existing assertion was weakened, changed or deleted.
- **Known pre-existing red, not caused by this change.** `scripts/qc-lattice-pointer.sh` fails on `origin/main` before this commit: `docs/lattice-citations.json` cites `SKILL.md:33/35/55` while the quoted text now sits at `:54/:56/:76` (+21 lines of earlier drift). Reproduced on a pristine `git archive HEAD` tree, identical 3 FAILs. Fixing it means editing `docs/lattice-citations.json` + `docs/CONTENT-CONVERSATION-LATTICE.md`, which are outside this task's Skill 38/44 ownership — left for a named repair instead of a silent rewrite of another unit's citation manifest.

## [2.0.35] - 2026-10-24 - fix(manifest): a wrong-shaped or unreadable campaign window is refused, never raised (T-23 repair, PBB-166)

One defect from the PBB-163 / qc2-t-23 verdict on the joined monthly approval manifest (`shared-utils/manifest/monthly_manifest.py`), reproduced on the committed bytes (`8f49e6d2b`) before any edit. Nothing inside `38-conversational-ai-system/` changes except this entry and the version marker: no schema, no guard, no dispatch behaviour. The module's own version is `shared-utils/manifest/VERSION`, now 1.0.2.

- **Defect — the documented return contract did not cover `campaign_window`.** `terms_errors` and `_window_errors` read the window as `doc.get("campaign_window") or {}` and called `.get` on it, so a string, integer, list, boolean or float window raised `AttributeError` from `approve`, `amend`, `reapprove`, `next_cycle` and `terms_errors`; `terms_errors` on a non-object document raised too. A right-typed but unreadable window day passed the schema and raised `UsageError` out of the contract's semantic check from every call and from `validate`. `next_cycle` skipped the no-overlap check when the previous window's last day was unreadable. One window reader now refuses each of these with the field named; `terms_errors` refuses a non-object document; `validate` returns the contract's `UsageError` as an error; an unreadable previous window refuses the next cycle instead of skipping the overlap check.
- **Proof — before -> after.** A sweep of 1,914 wrong shapes through every public call: **42 raised -> 0 raised**, valid-fixture control clean both times. Four tests added (`WindowShapeTests`): against the pre-fix module **3 failures and 36 errors**, all in the new class, every pre-existing case passing; after the fix `shared-utils/manifest/tests/test_monthly_manifest.py` **56 tests OK** (52 -> 56, no existing assertion changed). Each refusal is paired with the same call on the real window succeeding. `python3 -m pytest 38-conversational-ai-system/tools/tests/ -q` **247 passed, 90 subtests passed**.

## [2.0.34] - 2026-10-24 - fix(manifest): revision ordering reads the whole number run; a malformed manifest is refused, never raised (T-23 repair)

Three defects in the joined monthly approval manifest (`shared-utils/manifest/monthly_manifest.py`, added by the T-23 task), each reproduced on the committed T-23 bytes (`129bbf6b8`) before any edit and repaired under the task's own acceptance. Nothing inside `38-conversational-ai-system/` changes: no schema, no guard, no dispatch behaviour. The skill version rolls because this is the release bookkeeping every task commit carries; the module's own version is `shared-utils/manifest/VERSION`, now 1.0.1.

- **Defect 1 — a revision rollback leaked whenever a word trailed the counter, and a whole class of valid revisions could never advance.** The counter was read out of the trailing digits only (`(\d+)\s*$`), so a revision without a trailing digit was opaque and any differing value advanced: `check_revision("rev-3", "rev-2-final")` and `check_revision("rev-3", "rev-2-approval")` both returned `[]` — a rollback from 3 to 2 under any `rev-N-<tag>` scheme. The same heuristic refused forward moves it could not read, so `check_revision("2026-11-01", "2026-12-01")` and `check_revision("v1.0", "v2.0")` both came back "does not advance", with a reason diagnosing a rollback that had not happened. Ordering now compares the revision's whole number run position by position, numerically: `rev-2-final` is 2 whatever word trails it, `2026-12-01` advances `2026-11-01`, `v1.10.0` advances `v1.9.0`, and a repeat of the same number run is still refused. A revision with no digits stays opaque and advances by inequality; two revisions that cannot be ordered against each other (one numbered, one not) are refused rather than guessed at, because the function promises a revision never rolls back. The whole decision table is pinned literally in the tests.
- **Defect 2 — the module's documented return contract did not hold at the JSON trust boundary.** The header promises "on any error the original document comes back unchanged", but manifests are loaded from files, and a wrong-shaped document raised at the caller instead of returning errors: `approve` with `placements` set to `"P-1"`, `{"P-1": 1}`, `["P-1"]` or `[None]` raised `AttributeError`; `amend` with `changes=None` raised `TypeError` and with `changes=["keyword"]` raised `AttributeError`; a non-object document raised on every lifecycle call. Every call now refuses a non-object document and a `placements` value that is not a list of objects with the field named, `amend` requires a map of approved term to new value, and no loop iterates a shape it has not checked.
- **Defect 3 — a malformed campaign window leaked the interpreter's message.** `next_cycle(..., ends_on=None)` did refuse, but the error text was `unsupported operand type(s) for +: 'NoneType' and 'str'` instead of naming the field; it now reads `campaign_window.ends_on must be a non-empty ISO-8601 string, got None`.
- **Proof — before -> after, same probes both ways.** `check_revision("rev-3", "rev-2-final")` `[]` -> `rolls back 'rev-3'`; `check_revision("rev-3", "rev-2-approval")` `[]` -> `rolls back 'rev-3'`; `check_revision("2026-11-01", "2026-12-01")` `does not advance` -> `[]`; `check_revision("v1.0", "v2.0")` `does not advance` -> `[]`; `approve` with the four malformed `placements` shapes `AttributeError` -> `$.placements: must be a list of placement objects` with the document returned unchanged; `amend(changes=None)` / `amend(changes=["keyword"])` `TypeError` / `AttributeError` -> `an amendment is a map of approved term to its new value`, document unchanged; `next_cycle(ends_on=None)` `unsupported operand ...` -> the field named. Inverses unchanged on both versions: `check_revision("rev-2-final", "rev-3")` -> `[]`, `2026-12-01` -> `2026-11-01` and `v2.0` -> `v1.0` still refused as rollbacks, `alpha` -> `beta` and `rev-3` -> `rev-4` still advance, and `approve` / `amend` / `next_cycle` on the well-formed fixture still return no errors — the refusals above are not a blanket refusal.
- **Proof — suites.** `shared-utils/manifest/tests/test_monthly_manifest.py` 43 -> **52 tests OK**, the nine added cases only (`RevisionOrderingTests`, `MalformedDocumentTests`); no existing assertion was changed or weakened. Mutation control on the new tests: run against the pre-fix module they produce **13 failures and 12 errors**, all inside the two new classes, while every pre-existing case still passes — the new coverage bites exactly the new behaviour and cannot be satisfied by a blanket refusal or a broken import, since each refusal case is paired with the same call succeeding on a valid document. `python3 -m pytest 38-conversational-ai-system/tools/tests/ -q` **247 passed, 90 subtests passed** before and after. Skill 38 self-counts re-verified against disk for this bump: protocols 52, scripts 96, references 27, journey templates 8. A commit that adds no file under `38-conversational-ai-system/` except this entry and the version marker cannot move them; any drift between those numbers and the SKILL.md/INSTALL.md prose is pre-existing and is left to the Skill-38 doc self-count check, which is outside this task's ownership.

## [2.0.33] - 2026-10-24 - fix(capture): an outcome, a plan and an unknown id answer only for this ask (T-16 repair 2, PBB-168)

Repair round for QC PBB-157 (FAIL on `2f5c8cb16`). Three defects, all reproduced on the reviewed bytes before any edit with the reviewer's own probes (`probe_t16.py` 5/8, `probe_b.py` T-16 half 2/4), all closed here. Files: `shared-utils/capture/` plus this changelog and `skill-version.txt`, in this one commit. Nothing else changed.

- **Defect 1 - `state_after()` state-reported a foreign outcome as this ask.** It read `outcome.status` before asking whose outcome it was, so ask B returned `accepted` for ask A's sent outcome while `askB.state()` raised `the SMS email ask was never created`. That falsified 2.0.30's "no longer be sent, read or state-reported as this ask". Fix: `state_after` runs the same `_select` identity check on `outcome.action_id` before mapping any status; an outcome naming no action is refused too. Inverse kept: this ask's own outcome still maps to `accepted`.
- **Defect 2 - a suppressed ask was re-offered when the counter said zero.** `plan_capture(mobile known, access_ready=True, ask_state=suppressed, asks_used=0)` returned the SMS email ask (`email_missing`) while `asks_used=1` refused it. The ask's own state is the authority: any created ask that is not open (`suppressed`, `failed_not_sent`) now answers `ask_budget_exhausted` whatever the counter says. A `failed_not_sent` ask is retried as the SAME action by `retry_after_correction`, never re-planned as a new ask. Inverse kept: `not_created` with `asks_used=0` still plans exactly one ask.
- **Defect 3 (minor) - an unknown action_id leaked `DurableStoreError`.** `state`/`view`/`dispatch` raised the upstream store error for an unknown id, and an empty-string id was falsy so it silently fell back to this ask's own row. `_select` now treats only `None` as "this ask"; any other id the store cannot find (unknown or empty) is refused as `CaptureRefused("... is not this SMS email ask")` with the store error chained as `__cause__`, on `state_after` too. Still fail-closed: evaluator and sender are never called.
- **Proof - before -> after.** Reviewer probes on a `git archive` of `2f5c8cb16` -> this tree: `probe_t16.py` 5/8 -> **8/8**, `probe_b.py` T-16 half 2/4 -> **4/4**. Four new tests, run against the reviewed module bytes: **FAILED (failures=10, errors=3)**; against this tree: **OK**. Each new test carries its inverse case.
- **Proof - mutation controls** (lane copies, one fix reverted each): drop the `state_after` identity check -> 3 failures; drop the created-ask budget rule -> 3 failures; stop translating the store error -> 8 errors.
- **Proof - suites.** `shared-utils/capture/tests` 43 -> **47 tests OK** (pytest 47 passed, 30 subtests). Unchanged and green: `38-conversational-ai-system/tools/tests` **247 tests OK**, `38-conversational-ai-system/scripts/qc-pb-contracts.sh` **42 tests OK**. No existing assertion changed or removed; the diff to the test file is additions only.

## [2.0.33] - 2026-10-24 - fix(capture): the send boundary only ever touches this ask (T-16 repair, PBB-113)

Repair round for QC-T-16 (FAIL on clause 1). One hard defect, one proven input asymmetry, one test-strength gap - all three reproduced on the reviewed candidate (`edc20ea1d`) before any edit, all three closed here. Files: `shared-utils/capture/` plus this changelog and `skill-version.txt`, in this one commit - the two repo-mandated release-bookkeeping files every task commit in this repo carries. No source, schema, config or test outside `shared-utils/capture/` changed.

- **The hard defect (clause 1) - the send boundary did not check identity.** `SmsEmailAsk.dispatch(evaluator, sender, worker_id, action_id=X)` sent WHATEVER action `X` named. The QC repro (`attack_a8.py`, re-run here verbatim from its own script) dispatched another contact's `ACCESS_PASS` action **as** the one logical SMS email ask: `outcome.sent=True`, foreign row `state=dispatched`, `receipts ['dispatch']`, while the gate context still claimed `purpose=SMS_EMAIL_ASK` and this contact's id. The minting side was already enforced (`logical_intent_key == idempotency_key`); only the read/send side was open. The reviewer's own note that `view(action_id=)` and `state(action_id=)` carried the same unchecked selector is fixed with them.
- **Fix - `_select`, one guard beside `require_action`.** `state`, `view` and `dispatch` now resolve their row through a single selector that requires the row's `(tenant_id, canonical_contact_id, logical_intent_key, purpose)` to equal this ask's before the store is touched any further; anything else raises `CaptureRefused("action ... is not this SMS email ask")`. A foreign id can therefore no longer be sent, read or state-reported as this ask, and a cross-person or cross-sequence selector is refused at the boundary rather than trusted and corrected later.
- **Input asymmetry (clause 10 note, the reviewer's "one line of normalisation").** `channel_optouts` folded case (`"sms"` and `"SMS"` one opt-out) while `field_refusals` did not (`"Mobile"` raised where `"mobile"` was a refusal). Field names now fold case the same way, in `refuse()` and in `plan_capture`. Nothing becomes acceptable by being unrecognisable: `"address"` is still refused, a non-string refusal value still fails closed, and an unknown refusal scope still never becomes broader permission.
- **Test-strength (clause 5 M4 caveat, closed).** Deleting the `ASK_UNKNOWN` guard in `retry_after_correction` used to leave the suite green, because the later "retry requires known nonexecution" guard raises the same `CaptureRefused` for the same observable outcome - the behaviour was pinned, the guard was not. The test now pins the reason string as well as the class, so the mutation is visible; the message difference is the test's instrument, and no assertion was weakened (three `assertRaises` became `assertRaisesRegex` with the guard's own wording, plus one new test).
- **Proof - the QC's own repro, before -> after** (its script copied and run unchanged against a `git archive` extraction of `edc20ea1d` and against this tree): `outcome.sent=True` / foreign `dispatched` / `receipts ['dispatch']` -> `CaptureRefused: action '...' is not this SMS email ask`, sender never called. Inverse in the same tests: this ask's own `action_id` still dispatches to `sent=True` and still reports `state`/`view`, so the guard cannot be satisfied by blanket refusal. Foreign shapes covered: another contact's `ACCESS_PASS`, this contact's own `ACCESS_PASS`, another sequence's ask.
- **Proof - suites.** `shared-utils/capture/tests` **43 tests OK** (39 -> 43: three new boundary tests, one new refusal-folding test). Unchanged and green: `38-conversational-ai-system/tools/tests` **247 tests OK**, `scripts/qc-pb-contracts.sh` **42 tests OK**. New tests fail before the fix and pass after: boundary tests **6 subtest failures** on `edc20ea1d` (a foreign action dispatched, sent and receipted), refusal-folding test **1 error** (`CaptureRefused: field refusal must name one of ('mobile', 'email')` for `"Mobile"`).
- **Proof - mutation controls.** The repaired guard: deleting `_select` from `dispatch` returns the QC attack to `sent=True` (the boundary tests fail). The repaired test-strength gap: deleting the `ASK_UNKNOWN` guard against the OLD test file -> **OK** (the gap the reviewer named), against the NEW test file -> **FAILED (failures=1)**, message `"unknown ask must reconcile" does not match "retry requires known nonexecution, ask state is 'unknown'"`.
- **Ceiling named, not hidden.** `_select` pins identity at this module's boundary; it does not make a foreign action undispatchable through `durable_store`/`outbound_gate` themselves, which any other module with the store handle can still reach. Adding an owner check inside T-12's gate is a T-12 change and out of T-16's scope.

## [2.0.33] - 2026-10-24 - feat(capture): mobile-first capture and the one logical SMS email ask (T-16, PBB-113)

New module `shared-utils/capture/progressive_capture.py` plus its suite. No existing file's behaviour changes: the diff is additions only, and no assertion anywhere was weakened or removed. No live actions, no network code, no vendor call.

- **Nothing is re-implemented.** The ask IS a T-12 `durable_store` outbox action, so `logical_intent_key` and `idempotency_key` are the same derived string and no code path can mint a second identity. Every send and retry goes through T-12 `outbound_gate.dispatch`. Later-email binding is T-11 `tenant_identity`. When a collection lock is configured, `create_or_resume` and the suppression path require a live T-11 fence. The serialized `sms_email_ask` object is validated against T-08's `schemas/collection-state.schema.json` on every read, so this module cannot drift from the contract shape.
- **Policy added (DATA-CONTRACTS 6-7, R-14 / R-16).** `plan_capture` decides in contract order: global stop, human ownership, terminal sequence, delivery consent (separate from marketing), "email already known is pass-only", the missing field, then the single ask. Mobile is asked first over the original DM; the SMS email ask is planned only when mobile is known, access is actually ready, SMS is not opted out, and the budget of exactly one is unspent.
- **States.** `not_created -> queued -> dispatching -> accepted`, plus `failed_not_sent`, `unknown`, `suppressed`. `dispatching` is derived from an unresolved attempt row, so it cannot be claimed by a process that is not in flight. Accepted is provider admission, not completion: the store keeps dispatch, ack and completion as separate receipts and this module never records completion.
- **Known nonexecution vs unknown.** Known nonexecution requeues the SAME identity (`reconcile_not_applied`, `blocked_reason=reconciled_not_applied`) and reports `failed_not_sent`; only then may a corrected number retry, and the retry still passes a fresh gate. `unknown` refuses every retry until provider evidence resolves it: `applied` becomes accepted and is never resent, `not_applied` becomes retryable. A carrier failure reported AFTER acceptance is not treated as nonexecution.
- **Email arriving before dispatch.** The ask is cancelled and reported suppressed, and a separate `ACCESS_PASS` action is created under a different logical key - the pass is not an ask. Once dispatching or accepted, suppression is refused rather than claimed retroactively.
- **Refusals.** Field, sequence, channel and global scopes are separate; an unknown scope raises instead of granting broader permission. A mobile refusal ends mobile prompts while preserving an existing email; an email refusal preserves requested SMS access; an SMS opt-out blocks only that channel.
- **Email identity (C-F11).** A later email binds through the contact's existing verified identifiers, so it lands on the verified member instead of minting a second account. An email already verified for another contact in the same tenant is refused, never merged. The same email value in another tenant resolves to a different member.
- **Proof - suites.** `python3 -m unittest discover -s shared-utils/capture/tests` **39 tests OK** (new). Existing suites unchanged and green: `38-conversational-ai-system/tools/tests` **247 tests OK**, `scripts/qc-pb-contracts.sh` **42 tests OK**.
- **Proof - mutation controls** (throwaway copies, one change each). Deleting the pass-only branch -> **4 failures**; deleting the one-ask budget -> **2**; deleting the open-ask guard -> **1**; deriving a random ask identity per call -> **2 failures, 13 errors**; deleting the accepted/dispatching suppression refusal -> **1 error**. Two policy lines survive deletion because a second guard raises the same `CaptureRefused` for the same observable outcome; the behaviour, not the line, is what the suite pins.
- **Ceiling named, not hidden.** The contract has no quarantined ask state, so a quarantined binding reports `suppressed` while the durable row keeps the exact reason (`ponytail:` beside the mapping). A `failed` durable row is already terminal in T-12 and is reported as `failed_not_sent` without being resurrected.

## [2.0.33] - 2026-10-24 - fix(handoff): a lapsed offer reaches the backup, and one release never unpauses a sibling (T-29 repair, PBB-138)

Two defects in `shared-utils/handoff/handoff.py`, both reproduced on this tree's base before any edit (the T-29 build commit, byte-identical to the one the QC reviewed: 1180 added lines across `handoff.py` and `tests/test_handoff.py`). No schema change, no network, no provider, no new dependency.

- **Defect 1 — a handoff that lapsed unaccepted had no route out.** `escalate()` required `state == active`, `accept()` refused once `ts >= due_at`, and `release()` matches `actual_owner_id`, which is NULL before acceptance. So an offer whose owner never answered died at the due time with the bot paused for ever — while `accept()`'s own refusal text said "escalate to the backup", the one operation that was itself refused. Reproduced with the QC dead-handoff probe on the base: `escalate: illegal_transition: escalate requires state active, found offered`, `accept: refused: the due time already passed; escalate to the backup`, `release_by_backup` and `release_by_owner: refused: only the actual owner can release`, state `offered`, `bot_paused: True`. The read layer was blind to it as well: `escalation_due` reported `False` for that lapsed offer.
- **Fix.** `escalate()` now runs on `offered` as well as `active`, and still requires the due time to have passed. `backup_accept()` now also runs on an escalated `offered` handoff, and that acceptance is what makes the handoff owned at all: `state` becomes `active`, `actual_owner_id` becomes the backup, `backup_accepted_at` is recorded, and `accepted_at` stays NULL because the offered owner never accepted. The `accepted` read is now `accepted_at or backup_accepted_at`, so `accepted == (actual_owner_id is not None)` holds in every state. `get()` takes an optional `now` and reports `overdue` / `escalation_due` for a lapsed offer too. What is deliberately unchanged: the offered owner still cannot accept late, still cannot release, and ownership still changes only through an explicit acceptance by the actor who becomes the owner.
- **Defect 2 — releasing one handoff unpaused the bot while a sibling was still open.** `_finish_release()` called `fence.release()` whenever the fence was paused, with no sibling check, although `create()`'s own rollback path already guarded with `_other_open()` and stated the invariant in its comment: "A concurrent open handoff for the same contact keeps the fence: releasing it would unpause a live one." Consequence on the base: handoff B open and unaccepted, `gate_decision` `SUPPRESSED`, `bot_paused` `False` — the bot runs over a live handoff.
- **Fix.** `_finish_release()` returns before touching the fence when `_other_open()` is true: the same guard, the same invariant, one place. The last release alone resumes the bot.
- **Proof — before -> after on the base -> this commit.** QC attack suite `attack_handoff.py`, 21 cases including the inverse chain, the idempotent retry and the cross-tenant refusal: **3 failures (A1, A2, A3) -> 21 OK**. QC dead-handoff probe: `escalate` `illegal_transition` -> **ok**, and the bot still stays paused until the backup accepts and releases (the probe's own assertions stay green). The ten new proof tests run against the base module: **10 failed -> 0**; `python3 -m pytest shared-utils/handoff/tests/test_handoff.py -q` **39 passed, 19 subtests -> 50 passed, 22 subtests**; `python3 -I shared-utils/handoff/handoff.py` -> `handoff self-check OK` on both trees. New tests: `LapsedOfferTests` (7) and `ConcurrentHandoffFenceTests` (3) — escalation of a lapsed offer, the backup accepting and then releasing it, only the named backup taking it, the offered owner still refused, escalation refused before the due time and backup acceptance refused before escalation, `overdue` / `escalation_due` under a supplied clock, the fence kept while a sibling is open, the last release resuming the bot, and the fence surviving a release while a lapsed offer is open.
- **The QC probe `probe_dead_handoff.py::test_G2` flips from ok to fail, by design.** It asserts the contradicted rule ("escalate() is only reachable from ACTIVE ... the offer-only state has no escalation path"), which is precisely defect 1. Its corrected form is pinned in-repo by `test_an_overdue_unaccepted_offer_is_escalated_to_the_backup` and `test_the_due_reads_agree_that_a_lapsed_offer_is_escalatable`. The stuck-fence probes (the QC's noted, non-clause item) are green before and after and their fail-safe behaviour is untouched.
- **Two tests enshrined the contradiction and were repaired, not weakened.** `test_escalation_requires_an_accepted_handoff` asserted exactly the refusal the dead-handoff probe contradicts; it is replaced by `test_escalation_is_refused_once_the_handoff_is_released` (same `illegal_transition:` class, now on the released state). In `test_failed_operations_change_nothing` the escalate call moves from `t0 + 7200` to `t0 + 20`, because escalation of a lapsed offer is legal now and that list is about operations that are refused; the assertion itself — a refused operation changes nothing — is untouched and every other call in the list is unchanged. Assertion count 127 -> 177: fifty added, none deleted or rewritten, no `assertTrue(True)`, no skip, no xfail.
- **Ceiling named, not hidden.** The sibling check is the same check-then-act as `create()`'s rollback: a create landing inside the window between the check and `fence.release()` can still lose the fence. Closing it needs one transaction across the handoff and consent stores, or a re-pause after release; marked `ponytail:` at the guard. Noted and left alone, as the QC recorded it: a fence release that fails after the released state commits, with no `release_key`, leaves the bot paused (the fail-safe direction), and a same-release-key retry still finishes the job.

## [2.0.32] - 2026-10-24 - fix: write-ahead per-step receipts and a run lock, so a crash never leaves a created object unrecorded (T-36/PBB-081)

The independent QC verdict on v2.0.28 reproduced both shipped claims - the hash-identical second run and the interrupted-run resume - and still failed the unit on one durability defect and one concurrency defect. Both are fixed here; every other v2.0.28 guarantee is unchanged and re-proven.

- **A hard kill could leave a created object without its receipt.** v2.0.28 wrote the state file once, after the step loop, while this changelog and the module docstring claimed that every completed step was persisted as a receipt before the next step ran. The brief's own attack - interrupted after a resource is created but before it is recorded - therefore left the artifact on disk with no receipt, and the next run refused it forever as `owner_handoff_required`: resume worked only with `adopt_existing`. The receipt is now written and fsynced **before** its artifact (write-ahead) and made durable again after every step, so a crash at any write boundary leaves either the receipt and the artifact together, or the receipt alone, which the next run restores idempotently. A failed step still keeps no receipt: its write-ahead record is retracted before the failure is reported, so a resume retries that step instead of restoring it, and completed steps keep theirs.
- **Two concurrent runs could lose receipts and create a resource twice.** Nothing serialised the read-modify-write of the shared state file: with different specs the later run's write erased the earlier run's receipts (files on disk with no record at all), and with identical specs both runs reported creating the same resources. `run()` now holds an exclusive `flock` on `<state>.lock` for its whole duration and reads the state under that lock, so two setups never create the same resource twice and neither loses the other's receipts. A run that cannot take the lock within `lock_timeout` (default 30 seconds) fails with a named `BootstrapError` instead of hanging or losing data.

Proof, one instrument run before and after (scratch lane `pb-skill38-20261024/lanes/PBB-081-lane`): a hard kill at each of the eight write calls - unrecorded artifacts 4 -> 0, resources blocked on resume 4 -> 0, receipts complete after resume at every kill point, every pre-crash artifact byte- and mtime-identical; two concurrent identical runs - create actions 7 -> 4 for four resources (each created exactly once, four receipts); two concurrent different-specs runs - receipts recorded 4 -> 8 of 8 files. The hash after run 1 equals the hash after run 2 in both versions.

Tests: `tools/tests/test_bootstrap_engine.py` (35) - four new: a real child interpreter hard-killed at each write boundary, proving no created object is ever left unrecorded and that the resume needs no adoption; two real concurrent runs (identical and different specs), proving no duplicate create and no lost receipt; and a held-lock test, proving a second run refuses with a named reason instead of hanging. Whole tools suite: 240 tests. Assert-based self-check: `python3 -I tools/bootstrap_engine.py`.

## [2.0.32] - 2026-10-24 - feat: idempotent guided setup, permitted-only provisioning and resume (T-36)

Adds one stdlib-only module, `tools/bootstrap_engine.py` (the T-36 `client-bootstrap-engine`), which provisions the objects a guided setup asks for into one target root. `plan()` is a pure scoped diff and writes nothing, so nothing can be reported as provisioned when it was only planned; `run()` is the only writer. Receipts were written once per run in 2.0.28; the per-step write-ahead durability claimed at the time landed in 2.0.29.

Idempotency and permission are enforced rather than described. A second run over unchanged inputs writes no file at all: the state file and the provisioned tree are byte-identical before and after (proven by hash in the tests and by an independent lane driver). Provisioning is permitted-only - a resource that the operator did not name by resource id, by kind, or by `kind:<kind>` is skipped with reason `not_permitted` and the report names the permission it needed; there is no wildcard. Credentials, secrets and provider/model configuration are refused with `never_permitted` even when the operator explicitly permits them. An object that already exists and is not owned by this engine is never overwritten: matching bytes are adopted only when the spec sets `adopt_existing` and the operator permitted it, otherwise the step blocks with `owner_handoff_required`; differing unowned bytes block with `target_exists_unowned`, and a hand-edited or re-specified object this engine created blocks with `content_drift`. All writes are atomic and confined to the target root; a resolved path that escapes the root (including through a symlink) is refused with `path_escape`, and a corrupt or unknown-schema state file fails closed instead of starting over.

Resume is a continuation, not a restart. A step that fails is reported by name with `write_failed`, the receipts for the completed steps stay on disk, later steps are marked `not_attempted`, and the next run creates only what is missing - a resource created before the failure is unchanged (same bytes, same mtime) and recorded once. A recorded resource whose artifact was deleted is restored idempotently, replacing its receipt rather than adding one. The module contains no network or shell path (`TRAFFIC_AUTHORIZED = False`), so provisioning produces no traffic; sending stays the outbound gate's job.

Tests: `tools/tests/test_bootstrap_engine.py` (31) covering the byte-identical second run, permission and hard-refusal shapes, adoption and owner-handoff, content drift, duplicate ids/paths, path escape, corrupt state, discover, and a real partial failure (a read-only directory) resumed by a second run. Whole tools suite: 236 tests. Assert-based self-check: `python3 -I tools/bootstrap_engine.py`.

## [2.0.31] - 2026-10-24 - fix(T-39): the generation check and the write are one atomic step, and a migration can no longer regress the generation (PBB-078)

Two silent data-loss defects in `tools/compat_guard.py`, found by an independent review of the committed bytes and reproduced before the fix. The public API, the record shape, the error names already in use and the "no new dependency" rule are all unchanged.

- **`cas_update()` was compare-then-write, not an atomic swap.** The generation was checked at read time and the write was atomic (`os.replace`), but nothing held the two together and the module held no lock, so two writers both holding generation 7 both reported success and one payload vanished with no error in either process. The generation check and the write now run inside one critical section under a real `flock(2)` record lock (sidecar `<record>.lock`, released by the operating system even if the holder dies). Exactly one writer wins; the loser gets `StaleWriteError` and writes nothing.
- **`migrate()` bypassed the generation protocol and could regress it.** It copied `writer_generation` through from its own read, so a migration racing a CAS write overwrote the CAS write, dropped the generation back to 7 and made the already-consumed generation 7 acceptable again — record-bricking. `migrate()` now runs under the same record lock (so its read is against the generation that is actually current) and every write goes through one write-time guard that refuses to lower the on-disk generation with the named `GenerationRegressionError`. A migration that would lower it refuses rather than proceeds.

Proven by execution, not assertion, with the reviewer's two attacks run against the rejected tree and the repaired tree by the same harness: attack 1 before `['WROTE gen=8 payload=A', 'WROTE gen=8 payload=B']` (payload B lost), after `['WROTE gen=8 payload=A', 'REFUSED StaleWriteError: stale writer: expected generation 7, on-disk generation 8 is newer']` with the winning payload intact; attack 2 before the migration wrote its stale snapshot (`MIGRATED gen=7` after `WROTE gen=8`, CAS payload lost, generation back to 7) and the replay with the consumed generation 7 was **accepted**, after the generation never regresses (both serializations observed: migrate-then-CAS ends at 8, CAS-then-migrate ends at 8), the CAS payload survives and the replay with generation 7 is **refused** `StaleWriteError`. A write that would lower the generation is refused by name and leaves the bytes unchanged. Controls re-proven unchanged: the single-writer path still bumps the generation, `migrate()` still applies its pending steps, and a second migration run is a byte-identical no-op (sha256 compared). The two race tests fail against the pre-fix module (`2 != 1` writers won, `7 != 8` generation), so they discriminate rather than pass vacuously.

Suite: 25/25 in `tools/tests/test_compat_guard.py` (21 previous + 4 new), 230/230 across `tools/tests`, module self-check 7/7; the full suite run twice back to back with the same counts.

## [2.0.31] - 2026-10-24 - feat: compatibility, migration, CAS and forward-repair safeguards (T-39)

Adds one stdlib-only module, `tools/compat_guard.py`, and its suite `tools/tests/test_compat_guard.py` (21 tests). It guards a versioned JSON record of the shape `{"version", "writer_generation", "data"}` and implements DATA-CONTRACTS section 10 without a new dependency: `cas_update()` is a compare-and-swap on `writer_generation` that refuses a stale writer (`StaleWriteError` naming expected and actual generations) and writes through a temp file plus `os.replace`; `migrate()` applies only steps above the record's version and at or below the version this code knows, and a second run applies nothing and does not touch the file; `assert_compatible()` refuses a record newer than known (`NewerThanKnownError` naming both versions, no downgrade path); `forward_repair()` is the reporting entry point that returns `corrupt` / `newer_than_known` / `missing` / `protected_state` / `ok` and never writes in a refused case. A corrupt record is reported with its named problems and left byte-for-byte untouched. Migrations and CAS mutations that would drop or rewrite a protected data key (`sent_effects`, `contact_facts`, `consent`, `suppression`, `counters`, `unknown_sends`) are refused before any write (`ProtectedStateError`), and unknown top-level and data keys are preserved.

Proven by execution, not assertion: CAS refuses a stale writer with the on-disk bytes unchanged; a migration run twice reports `noop` on the second run with an identical sha256 (`3ab0ce0b…` before and after); a newer-than-known record is refused with both versions named; a corrupt record reports its problems and its bytes do not change. Suite: 21/21 in `tools/tests/test_compat_guard.py`, 226/226 across `tools/tests`, module self-check 5/5.

## [2.0.30] - 2026-10-24 - CI: required checks map to the behavior they name (PBB-069 / T-42)

New test-support module `scripts/ci/required_context_behaviors.py` enumerates the eight required status contexts the merge gate reads (`scripts/pr-rollup-required-contexts.fallback.json`), maps each to the workflow job that reports it, and states what that job actually verifies on a pull request. It fails when a context has no job, more than one job, a workflow that no longer triggers on `pull_request`, an undeclared job-level `if`, or a step body that no longer contains the behavior it claims.

Declared gap, not a green check: `G1 — version file change requires a matching annotated tag (push to main)` is skipped on every PR by `if: github.event_name == 'push'`; the merge gate counts SKIPPED as PASS (`pr-rollup-check.py` `TERMINAL_PASS`), so at PR time this required context proves nothing. The gap is registered with that exact condition, so closing or moving the condition fails the map instead of passing silently. The remaining seven contexts run on PRs and are mapped to their real verifiers.

The focused trace `tests/unit/required-context-behaviors.test.py` runs the map against the real tree (PASS) and against five deliberately broken copies — renamed job, undeclared PR skip, closed G1 gap, workflow removed from `pull_request`, gutted behavior assertion — each of which must be rejected. Wired into the `QC static invariants` job so the required context now proves its own mapping.

## [2.0.30] - 2026-10-24 - fix(reminders): a refusal stops only what it covers, and capture never restarts behind a stop (T-17 repair, PBB-134)

Eight defects in `shared-utils/reminders/reminder_state_machine.py`, each independently reproduced on the reviewed candidate (`5e8b38b9c`) before any edit, plus two tests that asserted contract-violating behaviour as correct. The only files touched are `shared-utils/reminders/` and the two repo-mandated bookkeeping files. No live actions, no network code, no vendor call.

- **Scope (A1, A2) - a narrow refusal no longer ends the shared budget.** `send_reminder` wrote `stopped_complete` on ANY consent refusal. An `sms` channel opt-out therefore closed the whole FB/IG/SMS shared sequence and a scoped `email_ask` field refusal stopped the sequence outright. DATA-CONTRACTS s7 reads "channel opt-out blocks that channel ... field refusal suppresses that ask ... Unknown refusal scope is not broader permission". The terminal stop is now scoped by reason through one predicate, `_consent_is_terminal`: only `REASON_CHANNEL` and `REASON_FIELD` are narrow, and everything else - a global stop, a human fence, a channel opt-out recorded without a channel, or a reason this module does not recognise - still stops the sequence. Fail closed: an unknown scope is never broadened into permission. Both refusal paths (the queue-time pre-check and the fresh gate inside `dispatch`) share the one rule.
- **Pause at dispatch (A3).** The docstring claimed pause was "resolved ... again by the fresh gate at dispatch", but `make_gate_evaluator(self.consent)` re-checks STOP and the fences and has no pause concept, so a `pause()` recorded after the slot was reserved and before dispatch did not stop the send and a message left the sender. `_block_reason` is now re-read immediately before `dispatch()` - pause, human ownership, `closing_final`, terminal, and a recorded reply - and the slot is left pending with the budget untouched, because nothing was sent. The overclaim is gone from the docstring.
- **Quiet window (A4).** `due_slot` fast-forwarded the later overdue slots BEFORE testing the quiet interval, so a merely DEFERRED send consumed a reminder slot (observed `['sent','pending','skipped']` at t=1030 under a 60s window). The quiet test now runs first: while the interval holds every overdue slot stays pending, and the "no catch-up burst" skip follows only a send that actually goes out.
- **Terminal stop (A5).** After `stopped_final`, `open_sequence(tenant, contact, "new-id")` minted a brand-new sequence carrying a new t0 and three new slots, and the reminder was actually sent. Capture restarted behind a terminal stop, contradicting DATA-CONTRACTS s8 ("A late explicit request can receive useful help/fulfillment without restarting capture") and s1 ("it cannot restart final or declined capture"), and the C-F19 trace step "late request may be served; capture remains stopped". `open_sequence` now reuses the stopped sequence and never mints a second one for a contact that has already stopped, so there is no fresh t0, no fresh slots and no fresh budget to send with.
- **Pause on the final path (A6).** `reserve_final` and `dispatch_final` ignored `paused_active` entirely, so the closing action could slip past a pause the reminder path honoured. Both now raise `FinalRefused` naming the state; a pause recorded between the reservation and the dispatch is caught by the same re-read as A3.
- **Field completion (A9).** DATA-CONTRACTS s8.3 and F-05 both say "STOP, field completion, refusal or handoff before dispatch cancels the reserved action", but a reply recorded between reservation and dispatch cancelled nothing and the closing message went out claiming `stopped_final`. The module had no field-completion hook at all. `dispatch_final` now consults the reply record: a `reply_recorded` event after `reserved_at` cancels the reserved action and closes `stopped_complete`. The handoff leg was already proven and is untouched.
- **Admission is not acceptance (A8).** `expire_final` treated any `dispatch` receipt as provider acceptance and reported `status='sent'` / `stopped_final`, though `durable_store.record_dispatch` documents that receipt as "Provider admission is NOT completion; ack is a separate receipt" (`RECEIPT_KINDS = dispatch|ack|completion`). Expiry now keys on the `ack` receipt: an expired slot holding nothing but an admission closes `stopped_ineligible` and never claims sent.
- **Two tests asserted the bug as correct.** `test_narrow_refusal_does_not_become_broader_permission` asserted the broad stop its own name forbids; `test_terminal_state_refuses_every_further_effect` asserted the new-sequence restart (`late["collection_sequence_id"] == "seq-late"`). Both are rewritten to assert the contract - the narrow refusal blocks only its own ask and the refused ask stays refused, and a late request is served from the stopped sequence with no row minted under the late id. Neither is weaker: each now asserts more legs than the one it replaces.
- **Proof - before/after.** The new `T08RepairProofs` suite plus the two rewritten tests, run against the pre-repair module (`git show 5e8b38b9c:shared-utils/reminders/reminder_state_machine.py` in an extracted tree), fail **12 of 41**: `test_a1_channel_opt_out_blocks_that_channel_only`, `test_a2_field_refusal_suppresses_that_ask_only`, `test_a3_pause_between_reservation_and_dispatch_stops_the_send`, `test_a4_quiet_window_defers_without_consuming_a_slot`, `test_a5_terminal_stop_refuses_a_fresh_budget`, `test_a6_pause_refuses_the_reservation_itself`, `test_a6_pause_after_the_reservation_still_refuses_the_dispatch`, `test_a8_admission_receipt_is_not_acceptance`, `test_a9_field_completion_cancels_the_reserved_final`, both rewritten tests, and `T07UpstreamReuse` (the pre-repair module carried no upstream reason constants to reuse). After the repair: **41 tests OK**. The inverse legs - `test_a8_ack_receipt_still_proves_acceptance` and `test_a9_a_final_with_no_completion_still_sends` - pass on BOTH trees, so the fix does not turn a genuinely valid input into a refusal. `python3 -I shared-utils/reminders/reminder_state_machine.py` self-check **16 assertions**.
- **Nothing re-implemented.** The consent reasons are imported from `consent_gate` and pinned as the same objects by `T07UpstreamReuse`; dispatch is still `outbound_gate.dispatch`; no second consent, gate or lock copy exists.
- **Ceiling named, not hidden.** A channel-scoped or field-scoped refusal records the ask as `suppressed` rather than returning the slot to the pool, so a caller that only ever uses the opted-out channel spends the budget on refusals instead of sends. Slot ordering and "at most three shared reminders" both still hold. The upgrade path is a channel-capable scheduler that tries another eligible channel for the same slot before suppressing it; marked `ponytail:` beside the code.

## [2.0.29] - 2026-10-24 - feat: original direct fulfillment, independent of bonus access (T-13, PBB-067)

Adds one stdlib-only module, `tools/direct_fulfillment.py`. The original promised item is `(item_id, version, content_sha256)`: an approved item is required, a hosting URL is optional metadata that never changes identity, and the same item id/version carrying a different content hash is refused as `immutable_violation`. There is no import of any bonus-access, membership or vendor module, so T-13 fulfills whether or not T-14/T-15 exist. A `FulfillmentLedger` (its own SQLite file, decisions only) holds the durable requested-delivery basis and the observed intended-reader accessibility; `fulfill()` refuses with `no_delivery_basis` BEFORE creating an outbox action, so a call can never mint its own permission. Every externally visible effect is one action sent through the accepted T-12 `outbound_gate.dispatch()` + `durable_store` fenced lease — the at-most-once guard is reused, not copied — with the T-18 `make_gate_evaluator()` optionally composed as a second, stricter gate. Provider admission is labelled `accepted`; `delivered` exists only after `record_delivery_proof()` receives an actual receipt whose content hash and destination match the pinned item and the recorded basis; completion is refused from anything but acknowledged. `resume()` reconciles a crash-between-acceptance-and-receipt through `reconciliation.resolve_unknown()` against an offline append-only `JournalTransport` journal keyed by idempotency key: applied becomes acknowledged with no second send, known nonexecution returns to queued under the SAME action identity, and an explicit `retry=True` re-passes a fresh gate instead of resending blind; unresolved stays unclaimable. `can_continue()` allows optional collection only when the item is approved and immutable, reader accessibility is recorded, the destination matches, transport status is supported and nothing is unknown or failed. No network calls anywhere. Tests: `tools/tests/test_direct_fulfillment.py` (16: happy path, real-receipt promotion, proof mismatch/premature proof refusal, double delivery refused before and after completion, crash-after-acceptance resume with one send, known-nonexecution retry on the same identity, no-basis refusal with zero actions, consent stop after queueing, host migration identity, version tamper refusal, unapproved item, continuation gating); 221 across the skill suite (was 205).

## [2.0.28] - 2026-10-24 - fix(contracts): a format-mark-only trusted contact mapping is absent (T-08d residual, PBB-055)

One residual from the T-08c review, reproduced on this tree's base (`aa1a27bcb`) before any edit. No runtime behaviour outside the contract layer changes; no live actions, no network code. Schema unchanged.

- **The residual — an allow path on a value that carries no information.** `normalise_evidence_id` trimmed with `str.strip()`, which removes Unicode category Zs but not category Cf. So a gate whose `trusted_contact_mapping_evidence_id` was a single zero width space (U+200B) or a byte order mark (U+FEFF), or a mix of those with spaces and tabs, still reached `DISPATCHED` / `GATE_ALLOWED`. Probes on the base tree: `"\u200b"` `DISPATCHED/GATE_ALLOWED`, `"\ufeff"` `DISPATCHED/GATE_ALLOWED`, `"\u200b \ufeff\u3000\t "` `DISPATCHED/GATE_ALLOWED`.
- **Fix.** The same one normaliser now trims a character when it is whitespace **or** `unicodedata.category(c) == "Cf"`, then requires non-empty. Whitespace behaviour is provably unchanged: `str.isspace()` and `str.strip()`'s whitespace set are identical over the whole code space (29 characters on both sides, verified), and category Cf holds 170 characters disjoint from them. Non-strings are still handed back untouched, so `123`, `{}`, `[]`, `true` stay `INVALID_GATE` naming the field and the schema layer keeps owning "malformed". No second copy of the rule exists: `_is_blank_mark` is the single predicate the trim calls.
- **Decision recorded — a mixed value is trimmed, not refused.** `"id\u200b"` dispatches as `"id"`: the id is a reference to the mapping evidence record, its meaning is the identifier it spells, and a format mark around it is invisible decoration carrying no information of its own — the same shape as the whitespace padding that already dispatched (`"  ev-tcm-1  "`), so it is trimmed the same way and the id goes through. What is refused is a value whose entire content is decoration, because then there is no identifier at all. Unit-level statement of that rule: `test_the_normaliser_trims_format_marks_but_never_rewrites_the_id`.
- **Ceiling named, not hidden.** The trim is end-only, as `str.strip()` always was: a format mark buried *inside* an id (`"ev\u200b-tcm-1"`) stays part of that literal id and dispatches. The normaliser removes decoration, it never rewrites an id's body, because rewriting would silently retarget the reference onto a different evidence record. If internal marks must refuse, add a byte-exact check where the id is resolved against the evidence store. Marked `ponytail:` beside the code.
- **Proof — dispatch shapes, base `aa1a27bcb` -> this commit** (probes run against trees extracted with `git archive`, never inside a worktree): `"\u200b"` `DISPATCHED/GATE_ALLOWED` -> `SUPPRESSED/NO_TRUSTED_CONTACT_MAPPING`; `"\ufeff"` same -> `SUPPRESSED/NO_TRUSTED_CONTACT_MAPPING`; `"\u200b \ufeff\u3000\t "` `DISPATCHED/GATE_ALLOWED` -> `SUPPRESSED/NO_TRUSTED_CONTACT_MAPPING`; every one of those refusals carries `errors == []`. `"id\u200b"`, `"\ufeffev-tcm-1"`, `"\u200bev-tcm-1\ufeff"` and `" ev-tcm-1 \u200b"` `DISPATCHED/GATE_ALLOWED` -> unchanged (control, decision above). `" "` and `"\u3000"` `SUPPRESSED/NO_TRUSTED_CONTACT_MAPPING` -> unchanged; `null`, `""` -> unchanged; `"ev-tcm-1"` and `"  ev-tcm-1  "` `DISPATCHED/GATE_ALLOWED` -> unchanged (control); `123`, `{}`, `[]`, `true` `INVALID_GATE` naming the field -> unchanged.
- **Proof — suites.** `scripts/qc-pb-contracts.sh` 38 tests OK on the base tree -> **42 tests OK** here (four added: `test_an_invisible_only_trusted_contact_mapping_is_absent`, `test_non_breaking_and_ideographic_spaces_are_still_absent`, `test_a_real_id_decorated_with_format_marks_still_dispatches`, `test_the_normaliser_trims_format_marks_but_never_rewrites_the_id`). No existing assertion was weakened or changed: the four are additive, and the two blank/real tables keep their original values. Mutation control, new tests against the base normaliser: **2 tests fail** (`test_an_invisible_only_trusted_contact_mapping_is_absent`, `test_the_normaliser_trims_format_marks_but_never_rewrites_the_id`), 5 assertion failures across their subtests — the new coverage is not hollow. `scripts/qc-playbook-engine.sh` 44 tests OK throughout.

## [2.0.27] - 2026-10-24 - fix(contracts): a whitespace-only trusted contact mapping is absent, and the lifecycle edge table is pinned (T-08c repair)

Two defects, both independently reproduced on this tree's base (`7c05a16aa`) before any edit. No runtime behaviour outside the contract layer changes; no live actions, no network code.

- **Defect 1 — a whitespace-only trusted contact mapping dispatched.** The 2.0.26 change made the schema admit `null` and left the gate's presence test falsy-only (`if not gate["trusted_contact_mapping_evidence_id"]`). `"   "` and `" \t\n"` are truthy strings, so a person-directed action dispatched as `DISPATCHED` / `GATE_ALLOWED` with no mapping evidence at all. The 2.0.26 claim "a falsy id still refuses" was therefore not true. Presence now runs through one normaliser, `normalise_evidence_id`, which strips and requires non-empty after the strip. `None`, `""`, `"   "` and `" \t\n"` all refuse as `SUPPRESSED` / `NO_TRUSTED_CONTACT_MAPPING` with `errors == []`; a real id dispatches with or without surrounding padding; non-string shapes still fail as `INVALID_GATE` naming the field, because the normaliser hands non-strings back untouched and the schema layer keeps owning "malformed". The schema is deliberately unchanged — a stricter schema would turn a blank into `INVALID_GATE`, which section 3's closed return set forbids.
- **Defect 2 — the 2.0.26 mutation claim was half wrong, and the edge table was genuinely under-covered.** The claim read "removing the nine-field comparison, the cross-tenant block and the lifecycle edge table still fails the suite (9, 1 and 1 failures) ... coverage is not hollow", and a reviewer recorded it `NOT REPRODUCED`. Both halves resolve from a re-run that mutates one thing per throwaway copy and refuses to run a mutation whose target text is not found exactly once. "Removing the lifecycle edge table" reproduces only for the guard: deleting the `if new not in LIFECYCLE_EDGES[old]` check fails exactly 1 test, and deleting the `LIFECYCLE_EDGES` constant itself produces 4 errors (an error count, not "1 failure"). The part that did not reproduce is the last clause. At base the table's terminal rows were untested: widening `CLOSED` from `set()` and widening `CANCELED` from `set()` each left the whole suite green, 0 failures. So the coverage was hollow in exactly the place the claim said it was not.
- **Fix to defect 2.** `LifecycleTests` now pins the whole edge table literally (`test_the_lifecycle_edge_table_is_pinned`), so any widening, narrowing or deletion fails instead of silently redefining the rule the behavioural cases read back, and adds `test_a_closed_loop_cannot_reopen`, which walks a `CLOSED` loop back to every other state. No new fixture files: the reopened record is derived from `lifecycle/loop-closed.json` in a temp directory.
- **Proof — dispatch shapes, before -> after.** `"   "` `DISPATCHED` -> `SUPPRESSED/NO_TRUSTED_CONTACT_MAPPING`; `" \t\n"` `DISPATCHED` -> `SUPPRESSED/NO_TRUSTED_CONTACT_MAPPING`; `""` and `null` `SUPPRESSED/NO_TRUSTED_CONTACT_MAPPING` -> unchanged; `"ev-tcm-1"` and `"  ev-tcm-1  "` `DISPATCHED` -> unchanged (control); `123`, `{}`, `[]`, `true` `INVALID_GATE` with the field named -> unchanged.
- **Proof — mutation counts, base `7c05a16aa` -> this commit** (`scripts/qc-pb-contracts.sh`, 33 -> 38 tests): widen every edge row 1 -> 7 failures; widen `RUNNING` with `CLOSED` 1 -> 2; widen `CLOSED` **0 -> 5**; widen `CANCELED` **0 -> 1**; drop the edge guard 1 -> 6; drop the `LIFECYCLE_EDGES` constant 4 -> 10 errors; drop the approved-placement comparison 9 -> 9; drop the cross-tenant block 1 -> 1; revert the gate to the falsy-only test (new) -> 2; drop the strip in the normaliser (new) -> 2. A no-change runner control stays green at 38 on both trees. `tools/tests/test_playbook_engine.py` 44 tests green throughout. Note the placement comparison is ten bound fields with nine mutated-manifest fixtures; the "nine-field" wording in 2.0.26 named the fixtures, not the loop.

## [2.0.27] - 2026-10-24 - integration: combined inbound-mapping candidate and asset evidence shape (PBB-053)

One combined hooks.mappings candidate, because the accepted repairs were parallel fixes off the same base and touching the same files: the PBB-017 reconciliation (`model` optional, one contract sourced by the writer, the self-test, the QC gate and the installer; `messageTemplate` required non-empty) and the claim-accuracy repair (a read-only config target is refused with exit 12 before any backup or temp is written, routing failures name the configured agent candidates, changed keys are reported one line at a time and a successful rewrite reports success instead of needing attention). Both were merged into one tree rather than layered as independent branches; T-10 predicate behaviour is carried by the reconciliation, whose contract and fixture matrix are a strict superset of the T-10 repair.

`ci(qc-static)`: the T-10 inbound-mapping step warns and continues when its test script is absent instead of failing a green PR at exit 127, and still fails on a genuinely failing script.

`fix(T-07)`: asset evidence must be a real path, a real http/https URL with a dotted, non-reserved host, or a named source; a fabricated pointer can no longer promote a missing asset or relabel it `client_provided`.

## [2.0.26] - 2026-10-24 - fix(contracts): a missing trusted contact mapping is a named gate refusal, not a malformed gate record (T-08b F5-11 adjudication)

One open disagreement between two instruments on the T-08b repair, adjudicated from `DATA-CONTRACTS.md` section 3 and closed. No runtime behaviour outside the contract layer changes; no live actions, no network code.

- **What the contract actually says.** Section 3 lists "trusted contact mapping" as a person-branch check and closes the gate's return at five values — "Return ALLOW, WAIT_UNTIL, SUPPRESSED, QUARANTINED or RECONCILE_UNKNOWN with checked time, binding/policy/fence and supporting evidence." The contract names neither a `reason` field nor an `errors` collection; both stand in as the supporting evidence. So the disagreement was never reason-versus-errs: the probe matches its expected token against `reason` and `errors` joined together (`probe.py`, `record()`), and would have accepted it in either field.
- **The real disagreement, and the ruling.** A person gate carrying no trusted contact mapping returned `decision=INVALID_GATE` with a JSON-pointer type error (`$gate.trusted_contact_mapping_evidence_id: expected type string, got null`) instead of a refusal naming the check. Section 3's return set is closed and `INVALID_GATE` is not in it; the record carried no checked time, binding, policy or fence. Ruled against the implementation: absence of the mapping is a refused check that must explain itself to a human, never a malformed document and never an allow.
- **Fix.** `trusted_contact_mapping_evidence_id` now admits `null`, exactly as `consent_evidence_id` already does in the same branch. The refusal that already existed — `SUPPRESSED` / `NO_TRUSTED_CONTACT_MAPPING` in `tools/pb_contracts.py` — becomes reachable instead of standing as dead code behind a schema that rejected every falsy value first. Nothing opens: a falsy id still refuses, and `INVALID_GATE` remains only for genuinely malformed documents (wrong type).
- **Proof.** The independent verifier's probe, re-run unchanged on this tree: 87 rows before and after, F5-11 FAIL -> PASS (82 -> 83 PASS, 1 -> 0 FAIL, 4 INFO). Author suite 32 -> 33 tests over 60 -> 61 fixtures, green; 12 of the 13 original tests are byte-identical to `053c4fee`, and `test_known_good_control_accepts_one_of_every_kind` is extended additively with three control cases (lifecycle, compatibility, reconciliation). The Draft 2020-12 cross-validation runs and passes on the QC script's interpreter (jsonschema 4.26.0) and is a named skip under `python3 -I`. Mutation control: removing the nine-field comparison, the cross-tenant block and the lifecycle edge table still fails the suite (9, 1 and 1 failures), restoration green — coverage is not hollow.

## [2.0.26] - 2026-10-24 - feat: scoped refusal, global opt-out, human precedence, partial consent capture (T-18)

Adds one stdlib-only module, `tools/consent_gate.py`, on top of the accepted T-11 identity/collection lock (4e5ffa7ca) and T-12 durable store/gate (a2d8b3720); neither dependency module is modified. `ConsentStore` keeps an append-only decision log and the human-ownership fence in the same SQLite file as identity, and implements DATA-CONTRACTS section 7 precedence at the section 3 gate: global stop, then channel opt-out, then human ownership, then field (topic/offer/campaign) refusal. A refusal is never broader than its recorded scope, the latest decision wins per exact scope, a narrow grant lifts only its own scope and never a global stop, and an unresolved channel with an existing channel opt-out blocks rather than assuming a different channel ("unknown refusal scope is not broader permission"). A global stop blocks every channel for that contact, immediately and after restart, and is also honoured when it appears in the identity module's `contacts.suppression` column. Human takeover fences every send until an explicit `human_release(actor=...)`, which is audited; a grant never releases the fence. `make_gate_evaluator()` is the `outbound_gate.dispatch()` evaluator, so consent is re-evaluated on every dispatch and retry and a suppression recorded after queueing still blocks the send. `ConsentCapture` wraps `collection_lock.CaptureStore`: the decision for a step is written once (unique per capture+step) before the cursor moves, so a crash between the two replays idempotently, a mid-capture failure resumes at its own cursor in a new process, and a rejected capture stays rejected and cannot be advanced. `fold()` carries consent onto the surviving contact of a merge, keeping the stricter human fence. Tests: `tools/tests/test_consent_gate.py` (24), including real second interpreters for a stop passed between processes, human takeover/dispatch/release, a capture crashed mid-way with `os._exit` and resumed by a second process after the lock handover, and a rejected capture re-checked from a third process; 143 across the skill suite.

## [2.0.26] - 2026-10-24 - fix(hooks): a read-only target is now refused, the routing-agent failure names its candidates, changed keys are reported one line at a time, and a successful rewrite reports success

Four claim defects in the v2.0.24 hooks.mappings work, found by an independent review of the committed bytes. The migration mechanics themselves were correct and are unchanged.

- **A read-only target was silently replaced.** `rename(2)` replaces the DIRECTORY entry, not the file's own bits, so `openclaw.json` at mode 444 in a *writable* directory was overwritten and reset to 0600 while the installer exited 0 — the "read-only target fails with no partial write" claim did not hold for that shape. `refuse_unwritable_config` now fires before any backup or temp is created (and again immediately before the rename), exits **12**, and leaves the config byte- and mode-identical with no `.bak` and no temp left behind. A read-only *directory* still fails as before.
- **The "no routing agent" failure named no candidates.** The installer exited 10 with a generic `set ROUTING_AGENT_ID to a configured agent id` while `repair-inbound-hooks.py` exited 2 naming them. `s38_resolve_routing_agent` (and the `s38_migrate_mapping` fallback) now name every configured agent id in the message — `set ROUTING_AGENT_ID to one of x, y` — so the operator can act on it. The installer still exits 10 and still leaves `agentId` untouched.
- **Changed keys were reported as one combined line.** Both writers now print **one line per changed key**, plus the `agentId` old -> new pair (folded into the `agentId` key line when `agentId` is one of them, printed as an unchanged pair otherwise). This is the accurate wording for what v2.0.24 described as "one line naming every changed key".
- **A successful rewrite reported `NEEDS ATTENTION` exit 2.** `repair-inbound-hooks.py` flagged every rewrite whose `agentId` was not rebound, even when the rewrite itself succeeded. Exit 2 is now reserved for work that genuinely needs attention; a successful rewrite reports success and exits 0.

Unchanged and re-proven: three-key migration on a pre-upgrade mapping with operator `name`, `wakeMode`, `timeoutSeconds`, `deliver` and an unknown key preserved; second run byte-identical with no second backup; an already-correct mapping makes zero backups; malformed JSON exit 10 with the config untouched; config changed under the run exit 11 with the operator's newer content preserved; repair rebind and second-run no-op; dry-run writes nothing.

Tests: `scripts/lib-docker-tenant.test.sh` unchanged and still passing; `tests/repair-inbound-hooks.test.sh` selftest gains a case for a successful rewrite that needs no `agentId` rebind (must exit 0, never `NEEDS ATTENTION`).

## [2.0.26] - 2026-10-24 - fix: asset evidence must be a real path, a real URL or a named source (T-07 repair)

The evidence check in `tools/asset_registry.py` was `if not os.path.exists(evidence) and "://" not in evidence`, so any string containing "://" counted as proof: `mark_ready("logo", evidence="totally://made.up")` was accepted, readiness became ready, and the source was recorded as `client_provided` - a missing asset silently promoted on a fabricated pointer and relabelled as client-supplied. `https://invented.invalid/nope.png` was accepted the same way, and `record_present` accepted any non-empty string at all. Both holes are closed. An evidence pointer must now clear a real shape check: an existing path on disk, or a URL that `urllib.parse.urlsplit` shows to be http/https with a non-empty netloc containing a dot and a host that is not a reserved special-use name (RFC 2606/6761 reserve test, example, invalid, localhost, local and example.com/net/org because they can never name a real asset), or - for a claim the client or a discovery source states - a genuinely named source. Bare "://", pseudo-schemes, a scheme with no host, a host with no dot, a path that names no file that exists, blank and non-string pointers are all refused with a message that names the offending value. Offline URL existence cannot be verified and is not claimed: the comment on the check states the achievable bar, and the reserved-name rule is what makes `invented.invalid` refusable at all. A prepared asset keeps source `prepared` instead of being relabelled `client_provided`, and `mark_ready` demands a real path or a usable URL rather than a name, because preparation produced something that must be pointed at. `record_present` applies the same shape discipline to path and URL-shaped evidence while still accepting a named source, so `sync_from_brief` inherits it. Tests: `tools/tests/test_asset_registry.py` (39) - every rejected shape with a known-good control for every accepted shape (an existing file, a genuine https URL with a dotted host, a named source), and a proof that a refused pointer never promotes the asset and the campaign stays blocked while it is missing. Whole tools suite: 106 tests.

## [2.0.25] - 2026-10-24 - fix(contracts): loop lifecycle, compatibility record and the approved-placement dispatch gate (T-08 repair)

Independent QC failed T-08 on seven defects. This release repairs each one and proves the repair with adversarial fixtures that mirror the reviewer's probes, each rejection paired with a known-good control so a blanket failure cannot pass. No runtime behaviour outside the contract layer changes; no live actions, no network code.

- **F1 — DATA-CONTRACTS section 9 was not modeled.** New `schemas/engineering-loop.schema.json` (`--kind lifecycle`): `NOT_INSTALLED → ADOPTING → RUNNING | PAUSED_RESUMABLE → CLOSING → CLOSED`, `CANCELED` distinct, and **no `CLOSED_VERIFIED` alias** — the alias is not in the enum, so it is rejected at schema level. The record carries `applied_event_revision` with `closed_event_revision` equal to it (the CLOSED update lands at exactly one applied event revision) and `controller_id` / `controller_generation`, which `transition --kind lifecycle` refuses to change — a crashed controller is never recreated. `CLIENT_RUNTIME` jobs stay protected (`client_runtime_jobs_protected`).
- **F2 — section 10 compatibility record was not modeled.** New `schemas/compatibility-record.schema.json` (`--kind compatibility`): schema/protocol/reader/writer versions, `migration_checkpoint`, `writer_generation` (required, minimum 1), `config_revision`, plus `rollback.mode/target_revision` and the five-item `never_rolled_back` set. A rollback target newer than the revision the upgrade wrote is rejected as a forward repair, and a client revision newer than the upgrade's rejects rollback mode outright.
- **F3 — the public branch was not checked at dispatch.** The public placement action now carries `scheduled_at`, `timezone`, `cta_text`, `keyword`, `promised_item_version`, `bonus_asset_versions`, `conversation_policy_version`, `allowed_spare_ids` alongside `channel`, and `approval_errors()` compares all ten against the approved placement. Any divergence blocks dispatch with a reason naming the field. Nine mutated-manifest fixtures prove it field by field; each subtest first re-dispatches the pristine pair as its control.
- **F4 — section 1 reconciliation/merge absent.** New `schemas/contact-reconciliation.schema.json` (`--kind reconciliation`): verified identifiers (each stamped with its own `tenant_id` and evidence), merge handling with an explicit basis, and preserved unknown sends / prior reminder totals / stricter suppression. `DISPLAY_NAME` and `CROSS_TENANT` bases are rejected by name. Dispatch additionally refuses a `canonical_contact_id` already dispatched under another tenant.
- **F5 — section 3 gate record incomplete.** Both gate branches now return `policy_revision`, `authority_revision`, `lifecycle_state`, `content_revision`, `asset_version_id`, `schedule_evidence_id` and `quiet_rule_status` (binding/policy/fence plus the common checks). Public adds `platform_publishing_permission` and `reveal_order_verified`; person adds `trusted_contact_mapping_evidence_id`, an `inbound_dm_window` marker and a purpose-scoped `eligibility_evidence` list with a `basis`. Dispatch enforces each: no platform permission blocks publishing, a reveal order that is not verified blocks the reveal, a comment opener never opens an inbound-DM window, a DM without a window is refused, and eligibility refreshed by an outbound or cross-channel message does not count for FB/IG.
- **F6 — "FB, IG and SMS references share this lock" unmodeled.** `collection-state.schema.json` gains `channel_references` (cardinality 1..n, the origin must be one of them) and a `capture_budget` distinct from `reminders_accepted` (3 reminders, 1 SMS email ask). Every timestamp in the collection record — `t0`, `requested_at`, `fulfilled_at`, `due_at` — is now parsed and must carry an explicit timezone.
- **F7 — cardinality.** `reminder_slots` rejects duplicate slot numbers and out-of-order slots, `due_at` must increase across slots, `pending_request_ids` is unique, an APPROVED manifest with zero placements is rejected, and manifest placements must sit in schedule order.

Suite: 32 tests over 60 fixtures (was 13 / 26), every original case still green, plus a Draft 2020-12 cross-validation over all eight schema kinds. `scripts/qc-pb-contracts.sh` exit 0; `tools/tests/test_playbook_engine.py` 44 tests exit 0. A mutation control — the nine-field comparison, the cross-tenant block and the lifecycle edge table removed in a throwaway copy — fails 11 tests, so the new coverage is not hollow.

## [2.0.25] - 2026-10-24 - fix(38/hooks): `model` is OPTIONAL on hooks.mappings — PBB-017 reconciliation

Two accepted repairs contradicted each other, and the contradiction made a fresh install fail its own readiness gate:

- **T-09** (`s38_canonical_mapping`) rewrites the inbound mapping and deliberately emits **no** `model` key.
- **T-10** put the authoritative predicate in `scripts/lib-hook-mapping-contract.sh`, which listed `model` as a REQUIRED key. Its own fixture row `fresh-installer-today` proved the consequence: `GATEVERDICT=ERR`, reason `missing-key:model`. So `24-self-test-hook.sh` and `qc-backend-ready.sh` agreed with each other and both disagreed with the writer.

**Ground truth (evidence, not preference): `model` is NOT required — `agentId` is sufficient.**

| Evidence | Shows |
|---|---|
| Installed OpenClaw 2026.10.5 (1b58cb9), `dist/zod-schema-BVpLKnmq.mjs` | `HookMappingSchema = strictObject({ ... model: string().optional() ... })` — every mapping field is `.optional()`; `.strict()` only rejects unknown keys |
| `openclaw config validate` (that same build) | mapping WITHOUT `model` -> "Config valid"; the same mapping with `fallbacks` -> "Unrecognized key: fallbacks" |
| `docs/gateway/config-hooks.md`, "Mapping details" | `model` | default "agent/model defaults" | contract "Templated model override." |
| `dist/hooks-STZ6dZJ5.mjs` | `renderOptional(mapping.model, ctx)` -> undefined when absent; `mergeAction` -> `override.model ?? baseAgent?.model`, i.e. the run falls back to the AGENT's configured model |
| live `~/.openclaw/openclaw.json` on the operator box | 5 of 7 mappings carry no `model` and the config validates clean |
| this skill's own `24-self-test-hook.sh` | resolves the self-test model from `agents.entries[].model` -> `agents.list[].model` -> `agents.defaults.model`, never from the mapping |
| `references/GHL-INBOUND-AND-PLAYBOOKS.md` §12 | lists `model` among *valid* mapping keys, never as required; the "23 keys (exact)" is the GHL RAW BODY, a different object |

Changes:

- `scripts/lib-hook-mapping-contract.sh`: `model` removed from the required key set and kept as a valid optional key. A `model` key that is PRESENT but BLANK is still refused (`blank-model-override`) — harmless on the mapping path, but OpenClaw's own `normalizeAgentPayload` rejects a present-but-blank model with "model required", so a blank override is always a wiring mistake. Named as a SKILL-level strictness, not an OpenClaw requirement. `messageTemplate` is now also required NON-EMPTY (`no-messageTemplate`), because OpenClaw's `validateAction` refuses an agent action with no message — that is the key the evidence genuinely makes load-bearing.
- The directive needles have ONE home. `HOOK_MAPPING_SEND_DIRECTIVE_NEEDLES` / `HOOK_MAPPING_CONVERSATION_MEMORY_NEEDLES` live in the contract; `scripts/lib-docker-tenant.sh` SOURCES it and its `s38_send_directive_needles` / `s38_conversation_memory_needles` / `s38_required_template_needles` are printers over it, failing closed when the contract file is absent. The test-side "needles asserted equal rather than sourced" ceiling is deleted.
- `scripts/qc-backend-ready.sh` and `scripts/24-self-test-hook.sh` stop demanding `model`; both report the optionality explicitly.
- `tests/hook-mapping-contract.test.sh`: 11 rows. `fresh-installer-today` now PASSes (it is a correctly-shaped fresh mapping); `missing-model` renamed `blank-model-override` (its body carries `"model":""`, a blank override, not a missing one); `decoy-model-elsewhere` now PASSes; two new rows — `missing-messageTemplate` (a genuinely-required key missing MUST fail in both gates with the reason naming the key) and `decoy-valid-elsewhere` (a complete decoy must not launder a broken target, the case the old whole-file grep passed). The writer checks now read the shape from `s38_canonical_mapping`, run that shape through the contract end to end, and assert the needles are SOURCED rather than compared.

The 23-key GHL RAW BODY is unchanged and still carries `model` — it is a different object from a `hooks.mappings` entry.

## [2.0.25] - 2026-10-24 - fix: five T-11 defects — identity-root allowlist, no channel fusion, generated owner identity, fenced captures (T-11 QC repair)

Independent QC FAILED the 2.0.24 T-11 modules on five reproduced defects. All five are repaired here, each with its own test, including real multi-process races; the original 70043d040 commit is left intact as evidence of what failed.

- **Provenance bypass (D1).** `tenant_identity.normalize_identifier` accepted any `[a-z0-9_]{1,32}` token as a person-unique identity root, so a contact could be bound through a public placement path and then drive the collection lock. Identity roots are now an explicit allowlist (`IDENTITY_ROOT_TYPES`: fb_psid, ig_psid, sms_number, email, phone, login_id). Anything placement-, ad-, campaign- or thread-scoped is classified a CHANNEL_REFERENCE and is structurally unable to carry or merge a canonical contact, whatever the provenance argument says; unknown kinds are refused outright rather than guessed.
- **Channel collision fusion (D2).** Two people carrying one conversation/thread id fused into a single canonical contact, leaking suppression and reminder totals across them and sharing one collection-lock key. Channel references now live in `contact_channel_refs` with no uniqueness on the reference value and never carry merge authority; merging still requires a person-unique identifier or the explicit client-confirmed `merge()`. A shared thread id writes no `contact_merges` row.
- **Shared owner_id double send (D3).** `owner_id` was the only process discriminator and was neither generated nor validated, so two real processes passing the same string were both granted and both sent. Every owner id is now normalized once and bound to the lock's own generated per-process instance id (`CollectionLock.instance_id`), so two distinct processes can never both be granted; `Lease.owner_id` is the canonical owner key and any method accepts either it or the caller's label. The same normalization runs in acquire, renew, release, reconcile, assert_fence, record_effect and every capture mutation, so a padded owner string no longer locks itself out with `StaleWriter`.
- **Capture not fenced by the lock (D4).** `CaptureStore.begin/advance/complete/reject` borrowed `lock._write()` as a transaction helper and never asserted the caller held the collection lock, so two workers could both read cursor 0 and both execute the collection step. Every capture mutation now takes `owner_id`/`fence` and asserts the fence inside its own write transaction BEFORE the caller runs a step.
- **Premature complete() (D5).** `_set_terminal` marked a capture terminal without checking `cursor == len(steps)`, so a premature `complete()` left steps permanently unreachable and silently dropped data. `complete()` now raises `CaptureIncomplete` with the cursor and step count and leaves the capture resumable; `reject()` is still allowed with steps remaining.

Tests: `tools/tests/test_tenant_identity.py` (26) and `tools/tests/test_collection_lock.py` (23) — 49 in these two files, 93 across the skill suite (73 before). Three capture tests that encoded the unfenced D4 behaviour (`test_rejected_capture_stays_rejected_and_cannot_advance`, `test_capture_cursor_never_rewinds`, `test_capture_rejects_a_foreign_contact`) now acquire the collection lock before mutating a capture, and the `_worker` harness behind `test_partial_capture_resumes_in_a_new_process_never_restarts` does the same; no existing assertion was weakened.

## [2.0.25] - 2026-10-24 - feat: durable inbox/outbox, fresh outbound gate and unknown-send reconciliation (T-12)

Adds four stdlib-only modules under `tools/`. `durable_store.py` holds a SQLite inbox keyed on (provider, tenant_id, provider_event_id): a redelivered provider event has exactly one effect across processes and restarts, and identical bodies with different event ids stay two events. Its outbox is keyed by `logical_intent_key`/`idempotency_key` with the states not_requested, queued, dispatched, acknowledged, completed, unknown, failed, canceled, suppressed and quarantined; ACK and completion are separate persisted receipts and a stop ACK never counts as completion. Dispatch takes a fenced lease and commits the attempt with one `INSERT ... SELECT` that a cancellation or a stolen lease makes fail before anything is sent. `outbound_gate.py` evaluates the gate fresh on every dispatch and every retry; a verdict row is keyed to its attempt number and can never be reused, and the only verdict that sends is the one computed immediately before the fenced commit. `reconciliation.py` resolves a dispatch with no verdict without ever double-sending: applied becomes acknowledged (not completed), not_applied returns to queued under the SAME action identity, and unresolved stays unclaimable. `sweep_inflight()` promotes a dead-mid-send action to explicit unknown on restart while leaving its attempt open. Tests: `tools/tests/test_durable_processing.py` (26), including a real SIGKILL between provider acceptance and receipt persistence, two real worker processes racing one action, and a two-process cancellation race; the provider in every case is a real append+fsync file on disk. Contract dependency: shared schemas are owned by T-08 and were absent at this base; the modules implement DATA-CONTRACTS sections 2, 3 and 4 directly.

The interrupted pre-restart session had also written the T-11 `tenant_identity.py`/`collection_lock.py` modules and their tests into this worktree. They are byte-identical to commit 70043d040 on `pb/T-11/tenant-collection-lock` and are committed here unchanged so that no partial work is lost; the T-11 release entry below is theirs.

## [2.0.25] - 2026-10-24 - fix: `model` is optional on a hooks.mappings entry — the predicate accepts what the installer writes

T-10's shared predicate fixed the two-gates-two-contracts defect but got the direction wrong: it made BOTH gates
demand `model`, so both refused the mapping the real installer emits (which has no `model` key) and a fresh install
was still rejected `missing-key:model`. Agreement is not correctness.

Ground truth (evidence `E-PBB017-MODEL-KEY`, PBB-017-operator lane): the installed OpenClaw `HookMappingSchema`
declares `model: string().optional()` (every mapping field is optional; `.strict()` only rejects unknown keys),
`openclaw config validate` accepts a mapping with no `model`, `buildActionFromMapping`/`mergeAction` do
`override.model ?? baseAgent?.model`, the live `~/.openclaw/openclaw.json` runs 5 of 7 mappings with no `model`, and
this skill's own self-test has always resolved its model from the AGENT (`agents.entries` -> `agents.list` ->
`agents.defaults`), never from the mapping key. `agentId` alone routes.

- `scripts/lib-hook-mapping-contract.sh`: `model` moves from the required key set to the optional one. Required is
  now `id, match, action, agentId, deliver, messageTemplate`; optional is `wakeMode, name, sessionKey,
  timeoutSeconds, model`. A `model` that is PRESENT but BLANK is still refused, reason `blank-model-override`
  (was `no-model`): harmless on the mapping path, but OpenClaw's `normalizeAgentPayload` rejects a
  present-but-blank model on the direct `/agent` path, so a blank override is always a wiring mistake. That refusal
  is SKILL-level strictness, named as such — not an OpenClaw requirement. Everything else is unchanged: the exact
  key set still fails unknown keys by name, `agentId` must still be listed in `hooks.allowedAgentIds`, `deliver`
  must still be exactly `false`, and all twelve send/memory directive needles are still required. Still evaluated
  per mapping id, never a whole-file grep, and still fail-closed when the evaluator itself errors.
- `scripts/qc-backend-ready.sh` no longer claims "a working model is set on the inbound mapping" — that claim was
  never what it checked (it grepped the whole config for any `model`). It now reports exactly what it knows: no
  blank model override on any parsed mapping, and the effective model is the routing agent's own, resolved by the
  self-test's section (b).
- `scripts/24-self-test-hook.sh` section (a) is aligned with section (b): readiness no longer demands a `model` on
  the mapping and no longer tells the operator to add one.
- `install.sh` is unchanged. Its `install_skill_38_conversational_ai_system` already fingerprints all four
  contract-carrying scripts (including `lib-hook-mapping-contract.sh`), so this predicate change is picked up as
  `refreshed-content-drift` on an existing box, and it makes no model claim of its own.

Proven (`lanes/PBB-041-lane/prove-predicate.sh`, hermetic fixture + a local stand-in for the tunnel probe, live box
untouched): the mapping written by the REAL `15-configure-hooks-mappings.sh` against a fixture config is accepted
by BOTH gates and by `openclaw config validate`; the known-good control passes both; four invalid mappings are
refused by both with a reason naming the key; all 9 fixture-matrix rows report byte-identical verdicts in both
gates, decoy-model-elsewhere included; and re-running the writer converges to a no-op.

Hand-off: `tests/hook-mapping-contract.test.sh` is owned by the T-09 lane and was NOT edited here. Three of its
MATRIX expectations encode the old contract and are updated by the apply-checked patch at
`lanes/PBB-041-lane/0001-tests-align-matrix-with-model-optional.patch` (see `HANDOFF.md`).

## [2.0.25] - 2026-10-24 - feat: asset registry and preparation worklist (T-07)

Adds `tools/asset_registry.py`, the per-tenant asset inventory a 30-day campaign plan needs. It classifies all seven kinds (logo, photos, testimonial text, offer documents, links, video, prior posts) by source (client-provided, discovered, must-prepare) and readiness (ready, missing, must-prepare, unassessed). A missing asset is stored as missing with the stated reason and no value, path or placeholder of any kind; an unassessed kind is never reported as missing. The preparation worklist names the exact deliverable per missing asset plus every input it needs, resolves inputs from trusted acquisition-brief facts, and marks the rest as explicitly blocked, so preparation can be handed off without inventing anything. The campaign readiness gate returns green only when every required kind is present with a trusted source and evidence pointer, and otherwise names each blocker in plain language. It builds on T-06 rather than duplicating it: the brief's kinds and required set are asserted as a subset at import, `sync_from_brief` imports the brief's present/absent assessments with their provenance (refusing an assessment that has no trusted source), and `link_defaults` joins each present asset to the brief fact that references it, refusing an assumption. State is one JSON document written by atomic replace under an exclusive cross-process lock; re-applying identical operations is a no-op, and two processes produce the same bytes as one. Tests: `tools/tests/test_asset_registry.py` (32), including a no-assets client blocked with an explicit list, a complete set passing, a missing-asset no-placeholder negative, provenance refusal on claims and links, round-trip equality, and idempotency across two separate processes plus two concurrent processes.

## [2.0.24] - 2026-10-24 - feat(contracts): shared collection, outbound, approval, readiness and action-lifecycle contracts (T-08)

Adds the typed contract layer the Purple Billboard build needs before any provider transport is written. No runtime behaviour changes, no live actions, no network code.

- `schemas/` (new): five JSON Schemas authored from Purple Billboard `DATA-CONTRACTS.md` sections 1, 2, 3, 9, 10. `collection-state.schema.json` keys the serialized lock on `(tenant_id, canonical_contact_id, collection_sequence_id)` and records each requested item separately so partial capture is preserved. `outbound-action.schema.json` is a strict `oneOf` — a public placement can never carry a canonical contact, a person-directed action always must — and carries a branch-specific dispatch gate. `approval-manifest.schema.json` binds one joined 30-day campaign, revisioned, with per-placement invalidation. `readiness-evidence.schema.json` separates installed, configured, running, replied and fulfilled with a per-key evidence time. `action-lifecycle.schema.json` keeps acknowledgement and completion as separate receipts.
- `tools/pb_contracts.py` (new): stdlib-only validator and dispatch gate. `validate`, `transition`, `dispatch` and `receipt` subcommands. Enforces the rules JSON Schema cannot: a stale gate cannot authorise a retry, a duplicate logical intent collapses instead of sending twice, an unknown effect is reconciled and never replayed, a changed account binding quarantines queued work, and a terminal collection state cannot be restarted by a new request.
- `tools/tests/test_pb_contracts.py` + `tools/tests/fixtures/pb-contracts/` (new): 26 fixtures exercised as 13 tests in both directions, with a known-good control per contract kind, a vacuity control on the engine, and a Draft 2020-12 cross-validation that reports a named skip when `jsonschema` is unavailable. A mutation control (schema rule removed in a throwaway copy) was run to prove the suite fails rather than passing vacuously.
- `scripts/qc-pb-contracts.sh` (new): thin QC entry point so the repo's existing QC scripts can run the suite.

Deliberately not implemented: provider transport, durable store, outbox worker, and the onboarding/999/CC write-side propagation of readiness invalidation. Those are separate tasks; this release binds the contracts only.

## [2.0.24] - 2026-10-24 - feat: tenant/contact identity and the shared collection lock (T-11)

Adds two stdlib-only modules under `tools/`. `tenant_identity.py` resolves one person across FB, IG and SMS to ONE canonical contact inside a tenant and refuses to resolve across tenants; isolation is enforced by the SQLite keys and `verify()`, not by path convention. It rejects an unknown or missing tenant, an empty contact, and any contact whose provenance is a public placement. `collection_lock.py` serializes at (tenant_id, canonical_contact_id, collection_sequence_id) with a fenced lease: one collector wins, losers defer, an expired lease freezes as `reconcile_required` until a successor records the handover at the exact fence, and a partial capture resumes from its own cursor while a rejected capture stays rejected. Tests: `tools/tests/test_tenant_identity.py` (15) and `tools/tests/test_collection_lock.py` (14), including three real-process concurrency races and a cross-tenant negative. Contract dependency: shared schemas are owned by T-08 and were absent at this base; the modules implement DATA-CONTRACTS sections 1 and 4 directly.

## [2.0.24] - 2026-10-24 - feat: guided business, audience and offer discovery (T-06)

Adds `tools/acquisition_brief.py`, a stdlib-only acquisition front door for the 30-day campaign: one persistent brief covering business, offers, audience, proof, constraints, channels, geography and seasonality, plus the client's real asset inventory. Every fact carries provenance (client-stated, discovered, assumed) and a UTC recording timestamp. The next-question set is the minimal ordered remainder of unanswered required facts; a recorded fact is never asked again, an assumed fact raises a confirmation question and blocks readiness until confirmed, and an explicitly missing fact is recorded as missing and blocks readiness rather than being defaulted to a plausible value. The interview persists by atomic replace after every answer, so an interrupted or killed process resumes on the same unanswered question with no data loss and no repeated questions; a corrupt brief fails loudly and is never overwritten. The asset registry records present and confirmed-absent assets only, never generates or fabricates one, and publishes `must_prepare` for T-07. Tests: `tools/tests/test_acquisition_brief.py` (23), including resume after an abrupt child-process exit, a six-known-fact no-repeat proof, a no-default negative, and an asset-registry no-generation negative.
## [2.0.24] - 2026-10-24 - fix: one inbound-mapping contract shared by the self-test, the QC gate and the installer

G-03 / G-04 / G-05. `24-self-test-hook.sh` evaluated one parsed hooks mapping and refused it without a `model`,
while `qc-backend-ready.sh` grepped the WHOLE `openclaw.json` for `"model": "..."` and `"deliver": false` — so a
model anywhere in the file made the QC gate PASS the exact mapping the self-test refused. Same fixture: self-test
says `no-model`, qc-backend-ready says PASS. On top of that the installer skipped a Skill 38 copy on a matching
`skill-version.txt` STRING ALONE, so a dest wearing the right version with wrong content was never refreshed.

- New `scripts/lib-hook-mapping-contract.sh`: the ONE predicate for a valid inbound mapping, evaluated per mapping
  id. Exact key set (required `id`, `match`, `action`, `agentId`, `model`, `deliver`, `messageTemplate`; optional
  `wakeMode`, `name`, `sessionKey`, `timeoutSeconds`; anything else fails by name — the OpenClaw schema is `.strict()`
  and rejects `fallbacks`), `action` exactly `agent`, a non-empty `match.path`, `agentId` listed in
  `hooks.allowedAgentIds`, a non-empty `model`, `deliver` exactly `false`, and all twelve send/memory directive
  needles in `messageTemplate`. Pure bash + POSIX awk: no jq, no python3, so it works on a fleet box and keeps
  qc-backend-ready's "no python" claim true. It emits `MAPCONTRACT` / `MAPENABLED` / `MAPSELECT` / `GATEVERDICT`
  lines and fails CLOSED when the evaluator itself errors.
- `scripts/qc-backend-ready.sh` and `scripts/24-self-test-hook.sh` both source it and print the same verdict lines,
  so the two gates cannot reach different verdicts on the same config. The whole-file greps are gone.
  `24-self-test-hook.sh` gains `--mapping-only` (evaluate the mapping contract and stop) for the fixture matrix.
  The private python predicate in the self-test is deleted.
- `install.sh` `install_skill_38_conversational_ai_system` now skips ONLY when the version string AND the content
  both match (cksum over the four contract-carrying scripts), reports `installed` / `already-current` /
  `refreshed-content-drift` / `refreshed-version`, and writes a secret-free `provisioning-receipt.json` next to the
  install recording what was actually installed.
- Tests: `tests/hook-mapping-contract.test.sh` — a 9-row fixture matrix (known-good control, fresh installer
  output, T-09-upgraded, stale agentId, missing model, missing directive, wrong shape, decoy model on a sibling
  mapping, hooks disabled) driven through BOTH gates with byte-identical verdicts and matching exit codes on every
  row, plus the known-good control so identical failure cannot masquerade as agreement. It also asserts the
  writer's fail-closed directive needles equal the contract's needles, and runs the extracted installer function
  to prove content drift is refreshed rather than skipped.

Open: `15-configure-hooks-mappings.sh` (T-09 lane) still does not emit `model`, so a fresh mapping is refused
`missing-key:model` — that is G-03 on the writer side and is the fix T-09 owns. The directive needles are asserted
equal to the writer's rather than sourced from it, because that file is not editable from this lane; once the
writer sources the contract too, the equality assertion can go.

## [2.0.24] - 2026-10-24 - fix(hooks): content-addressed hooks.mappings migration; repair rebinds a stale agentId

Two demonstrated defects left an upgraded box with a permanently broken GHL inbound hook body:

- **G-01 — "skipping merge" froze a pre-upgrade mapping forever.** `scripts/15-configure-hooks-mappings.sh` only merged a mapping when the id was absent, so an existing entry kept its nested `sessionKey` merge tokens (the GHL body sends a FLAT `{{session_key}}`), a `messageTemplate` with no send-directive (the agent drafts and never sends) and no conversation-log read-before/append-after (the agent has no memory mid-conversation) on every re-run.
- **G-02 — the repair reported a stale `agentId` and never rebound it.** `scripts/repair/repair-inbound-hooks.py` rewrote only `hooks.maxBodyBytes` and `gateway.trustedProxies` and printed a "not a configured agent" note.

Both are now one content-addressed migration:

- `scripts/lib-docker-tenant.sh` owns the canonical mapping shape (`s38_canonical_mapping`), the mandatory send-directive and conversation-memory needle lists (`s38_send_directive_needles`, `s38_conversation_memory_needles`) and the key-level merge (`s38_merge_mapping_body`, `s38_mapping_changed_keys`, `s38_migrate_mapping`). Only divergent keys are upgraded: `id`, `action`, `deliver`, `match.path` are forced; `agentId` is kept while it names a configured agent and rebound to the resolved routing agent when stale; `sessionKey` is kept unless it is empty or carries a nested `{{a.b}}` token; `messageTemplate` is kept unless it is missing a required directive element; operator values for `name`, `wakeMode`, `timeoutSeconds` and any unknown operator key are left alone. A second run reports no changes and writes nothing. The canonical messageTemplate stays in a `.sh` under `scripts/` so `qc-send-directive.sh` and `qc-conversation-memory.sh` keep linting it.
- `scripts/15-configure-hooks-mappings.sh` builds the mapping through that lib and, when the id already exists, migrates it instead of skipping: it reports exactly which keys changed and writes the upgraded body.
- `scripts/repair/repair-inbound-hooks.py` now rewrites the mapping body through the same lib (single source of the required shape), including rebinding a stale `agentId`, and prints one line naming every changed key plus the `agentId` old -> new pair. When no rebind target can be resolved and the box has more than one configured agent it stops and asks for `ROUTING_AGENT_ID` rather than guessing.

Safety on both paths: the pre-change mapping body is backed up next to the config (`openclaw.json.hooks-mapping-<id>.bak-<ts>.json`), the config is replaced by an atomic rename after `openclaw config validate`, and the installer refuses to commit (exit 11) when the file changed under the run.

**T-10 contract note:** this writer emits no model key. The mapping body carries `agentId` only, and that id is now always a configured agent, so nothing here needs to agree with 24-self-test-hook.sh, qc-backend-ready.sh or install.sh about a model.

Tests: `scripts/lib-docker-tenant.test.sh`, `tests/repair-inbound-hooks.test.sh` (selftest extended with the body-migration and stale-agentId-rebind cases).

## [2.0.19] - 2026-10-13 - refactor(models): client-choice model selection, no prescribed models

Model selection doctrine applied across the skill: no surface prescribes a specific model by name anymore. Selection resolves as (1) the client's explicit choice, (2) the client's configured default model, (3) a stop with a clear ask-the-client message. Where an old prescription carried a real rationale (reasoning depth, context size, speed, cost), it is kept as a recommendation with its reason, as guidance the client can override, never wired as a fallback value in code or config.

- Install scripts: `scripts/15-configure-hooks-mappings.sh` (the Step 3.5 wizard now asks the client, with recommendation profiles and no named defaults or option lists), `scripts/04-register-crons.sh` (batch model resolution), `scripts/28-configure-pixel-hook.sh` (pixel hook model resolution), `scripts/21-generate-client-reference-sheet.sh` with `templates/client-reference-sheet-template.md`, `templates/sms-workflow-ai-prompt-template.md`, and `templates/workflow-verification-checklist-template.md` (the model is resolved through the same hook and substituted as <CLIENT_MODEL>), `scripts/24-self-test-hook.sh` and `scripts/33-runtime-tool-gating-prover.sh` (self-test model resolution), `scripts/32-verify-model-failover-support.sh` (usage examples).
- Docs: INSTRUCTIONS.md, the weekly, monthly, and proactive review protocols, the web-scraper protocol, the conversation-workflows protocol, the model fallback chain reference, the subagent delegation pattern, the GHL inbound and raw-body references, the workflow AI instructions standard, the strategic roadmap, the agent-capabilities template, and the prescriptive sections of `references/v6.0-source-playbook.md` (the Step 3.5 wizard, the subagent model profile, the scraper sections, the review-protocol copies, the capabilities sections, and the copyable hook payload examples) now use the client-choice pattern. Historical release notes and the model-version freshness examples in the playbook are unchanged, as are the Class 3 registry and narrative surfaces (HOSTINGER-DOCKER-ENV.md, EXAMPLES.md, the freshness protocol).

## [2.0.18] - 2026-10-14 - feat: presentations conversational layer (FIX-PLAN Item 33b)

New `protocols/presentations-conversational-layer-protocol.md`: this skill's bounded doctrine for the three human-facing seams of the Presentations department: park and resume client communication (park-notice), post-delivery conversational follow-up including review-call booking through Skill 44 calendars (delivery-followup), and the intake front door that hands a qualified client into Skill 51's gated intake (intake-frontdoor). The contract is conversation-brief.json out of the run folder and conversation-receipt.json back into the run record; the department-side adapter and the message templates live in the presentations tree (`scripts/conversation_layer.py`, `scripts/conversation_templates.json`). Skill 51's gated intake is explicitly out of scope: the layer never asks the intake questions and never writes intake answers. Protocol count 51 to 52 (SKILL.md and INSTALL.md conformed). The scripts total stated at v1.9.2 (92) no longer matches disk (94 .sh files); that drift predates this change, is flagged in the Item 33b build manifest, and is deliberately not restated here.

## [2.0.12] - 2026-10-06 - fix: step O.6 accepts the Skill 76 local Ollama embedder

`scripts/19-configure-dreaming-embeddings.sh` failed with "no client-owned embedding provider key" on a
box whose memory search runs on the local Ollama embedder (Skill 76) and that has no OpenAI or Google key.
It now accepts that box first (provider `ollama` with `remote.baseUrl` on 127.0.0.1, localhost or ::1) and
changes nothing. The "already set" check also reads `memory.search.provider` (the current OpenClaw key)
before the legacy `agents.defaults.memorySearch.provider`.

## [2.0.10] - 2026-10-06 - fix: boxes that already installed Skill 38 get the inbound-hooks fix on their next update

The 2.0.9 fix lived in install-time scripts, which never re-run on an installed box. New
`scripts/repair/repair-inbound-hooks.py` is registered in the shared front door (`skill38-inbound-hooks`),
so every update route runs it. Only when `hooks.enabled` is already true: removes `hooks.maxBodyBytes`,
sets `gateway.trustedProxies` when unset (same detection as step 15, via `lib-docker-tenant.sh`), and reports
(never edits) a mapping `agentId` that is not a configured agent (exit 2). Backs up, validates, restores on
failure; idempotent; never enables hooks or touches tokens. Test: `tests/repair-inbound-hooks.test.sh`.

## [2.0.9] - 2026-10-06 - fix: inbound hooks work on docker tenants (operator-managed tunnel); no Cloudflare token demanded

A Contabo/VPS docker tenant could send through GHL but never receive. Four defects, one install path:

- **Wrong token demand.** `00-verify-prerequisites.sh` halted with the Rule 13 "CLOUDFLARE API KEY NOT FOUND"
  message on boxes whose public hostname is served by the operator's cloudflared on the HOST, which the
  container cannot see. The agent then asked the client for a token on the operator's own zone. New
  QC-PROTOCOL.md Rule 13a: inside a container, a set `PUBLIC_HOSTNAME` passes with no token and steps 13/14
  skip themselves; without it the agent asks the operator for the hostname. The operator zone's token is
  never given to a client box.
- **403 on every tunneled request.** Step 15 never set `gateway.trustedProxies`, so OpenClaw 2026.9.x answered
  `403 proxy_attribution_required`. New Step 3.1 merges the hop cloudflared connects from (docker tenant: the
  container's default-route gateway; host/Mac: loopback; `TRUSTED_PROXIES` overrides). Runs even when the
  mapping already exists.
- **Invalid config.** Step 15 wrote `hooks.maxBodyBytes`, which the 2026.9.x schema rejects
  (`hooks: Unrecognized key "maxBodyBytes"`); it is no longer written and is removed where an earlier run left
  it. Every config write is now validated as a candidate file BEFORE it replaces the live config.
- **Agent `main` that does not exist.** The hook mapping, `allowedAgentIds`, the model wizard and the crons
  (04 and the step-15 heartbeat) defaulted to `main`; 2026.9.x boxes keep agents in `agents.entries` and often
  have no `main`. New `scripts/lib-docker-tenant.sh` resolves the routing agent: `ROUTING_AGENT_ID` (must
  exist) > the agent an existing hook mapping uses > `dept-communications` > `main`; nothing else is guessed.
  21/24/33 put the same id in the 23-key body.

Also: the step-15 E2E no longer starts a real agent run at a fake contact; it probes (no token -> 401; real
token + a disallowed session key -> 400 before admission), retrying through the gateway's self-restart. The
full inbound->reply test stays `24-self-test-hook.sh`. The model wizard never blocks without a terminal and
never changes the routing agent's model unasked (an object model keeps its fallbacks). Secrets default to the
file 18 persisted, then the stores boxes actually use (`secrets/.env`). New hermetic test
`scripts/lib-docker-tenant.test.sh` (wired into qc-static).

## [2.0.8] - 2026-10-06 - docs: the hero visual's Kie transport is Skill 74 (one KIE path)

`scripts/31-generate-workflow-visual.sh` and `protocols/workflow-visual-protocol.md` now state that
any real hero job runs through Skill 74's CLI (`kie_live_adapter.py ... --mode active --json`, a
sibling skill folder) and that this skill never grows its own createTask, polling, upload or
download code; Skill 66 stays the model authority. The script is still a stub (no Kie call, no
model recorded), so no behavior changed. The earlier wording about a Skill 74 shadow-mode
catalog check is replaced.

## [2.0.7] - 2026-10-05 - fix: QC follow-ups to 2.0.6 (Skill 66 prereq, fixtures, comments)

`PREREQS.json` gains an optional `skill-66` entry (the image policy owner) and the Skill 07 entry
no longer claims to provide an image catalog. `workflow-visual-protocol.md` section 9 matches, and
its over-long line is wrapped. `qc-workflow-visual.test.sh` fixtures use `mock` instead of
`mock-gpt-image`. `09-install-conversation-workflows.sh` says hero generation is delegated to
Skill 66. Skill 74 is referenced as "once installed" because it is not on main yet.

## [2.0.6] - 2026-10-05 - fix: remove stale Kie model ids from the workflow visual; image policy is Skill 66's

`scripts/31-generate-workflow-visual.sh` recorded `${KIE_IMAGE_MODEL:-gpt-image}` as the hero
`model_id`; `gpt-image` is not a Kie model id, and the script makes no Kie call (it is a stub).
It now records no model (null) until a real job runs, and the dry-run mock id is `mock`.
`protocols/workflow-visual-protocol.md` no longer tells the agent to query the catalog itself,
no longer falls back to "Flux", and no longer claims Skill 07 documents "GPT Image 1.5". Image
generation is delegated to Skill 66 (kie-image), the image policy owner, which applies the fleet
image pin (AGENTS.md N43). The live catalog check is provided by Skill 74 (`74-kie-live-adapter`)
in shadow mode; Skill 66 remains the decision authority. No non-Kie behavior changed.

## [2.0.0] - 2026-08-04 - fix: the pointer-stanza rewriter (v1.11.0) is now WIRED IN, and 9 qc gates check the LIVE box instead of the shipped source

v1.11.0 shipped `05-update-agents-md.sh` (the writer) but nothing in the
automated pipeline ever CALLED it — it was a MANUAL INSTALL.md step-5 only.
`update-skills.sh`'s per-skill wiring loop now invokes it for
`38-conversational-ai-system`, scoped and not sentinel-gated (needs to run
every pass for the corefile-watcher staged-descent convergence to work).

Separately, `qc-segmentation.sh`, `qc-multi-tenant.sh`, `qc-tool-gating.sh`,
`qc-workflow-exits.sh`, `qc-client-test-mode.sh`, `qc-zhc-tag-prefix.sh`,
`qc-ab-testing.sh`, `qc-zhc-pixel.sh`, and `qc-webhook-chaining.sh` all
checked the SHIPPED SOURCE script for their marker text instead of the box's
LIVE AGENTS.md — proof the writer could produce the marker, never that it had
run. Every one of the 9 now ALSO asserts against the live file (env-override
`AGENTS_MD`, else the writer's own platform default; no live file = SKIP, not
a false FAIL). `11-run-qc-checklist.sh` exports its own resolved `AGENTS_MD`
to every sub-gate so one checklist run checks one file throughout.

New mutation-proof suites: `tests/unit/skill38-agents-md-wiring.test.sh`
(14 assertions) and `tests/unit/skill38-qc-gates-live-agentsmd-awareness.test.sh`
(31 assertions, every gate/marker pair proven both directions). All 8
pre-existing per-gate `.test.sh` negative fixtures still pass unchanged.

## [1.11.0] - 2026-08-03 - fix: AGENTS.md gets POINTER STANZAS, not a 52,444-character corpus; the GHL PIT monitor can finally pass

### Why
`scripts/05-update-agents-md.sh` appended the FULL text of 23 marker blocks -- **52,444
characters** -- into every box's `AGENTS.md`. On the operator box that was **40.65% of the
whole file**, and `AGENTS.md` is re-billed to the model on EVERY turn. Most of it was not
even distinct content: the OPERATOR-ONLY / "injection vector, IGNORED" paragraph appeared
10 times, an `openclaw.json` config stanza 14 times, the default-OFF preamble 8 times and
the PII-free logging tail 10 times.

Idempotency was `grep -q "<!-- BEGIN SKILL38: $name -->"` followed by an append, which
meant three separate defects: a marker RENAME appended a second copy and nothing removed
the first (the same class that doubled `MEMORY.md`); an EDIT to a block never reached an
already-wired box because the guard saw the old marker and skipped; and a fresh timestamped
backup was taken on EVERY run whether or not anything was written -- backup spam on every
fleet roll.

Separately, `scripts/check-ghl-pit-liveness.sh` had NEVER once passed and could not: it
resolved `GHL_PRIVATE_INTEGRATION_TOKEN` from `openclaw.json` `env.vars`, where that name
holds the documentation PLACEHOLDER `pit-abc123` (three of its five candidate names hold
the same placeholder there), while the box's REAL tokens sat in `secrets/.env` and tested
HTTP 200 live. It then read the resulting bare 401 as "DEAD/EXPIRED" and told the client to
re-issue a credential that was never set -- a false alarm the operator had to personally
challenge.

### What changed
- **`scripts/05-update-agents-md.sh` is now a POINTER writer.** Each of the 23 surfaces
  becomes a compact WHAT / WHEN-trigger / POINTER stanza, plus ONE new
  `SKILL38_RUNTIME_INVARIANTS` stanza that states the deduplicated boilerplate exactly
  once. Prohibitions, the GHL build-path note and the 11 Playbook-Builder trigger phrases
  stay INLINE, verbatim, because they bind at read time.
- **New `references/agents-runtime-rules.md`** -- the canonical FULL text of all 23 blocks,
  each under its historical marker name, plus the shared-invariants section. The script
  installs it and the per-feature `protocols/*.md` into the client's master-files folder so
  no pointer can dangle.
- **True replace-in-place across the whole `SKILL38:` namespace**, including RETIRED marker
  names and skill 38's own legacy generic-installer stub. Idempotency is a property of the
  WRITER, so a rename can never duplicate and a re-run is byte-identical.
- **Self-heal**: the next fleet roll CLEANS a bloated box instead of leaving it bloated. A
  hand-cleaned box takes the same code path with no special case.
- **Backups only when the content actually changes.** A no-op run writes nothing.
- **Watcher-floor aware.** On a box running an anti-tamper core-file watcher the heal is
  STAGED so each pass stays at or above the restore floor (`max(200 bytes, 40% of the
  vaulted size)`); convergence is geometric. The vault is never written.
- **The shared stamp bank is untouched.** ~44 other installers key idempotency on
  `<!-- skill:<NN-slug>:core-update-applied -->` in the same file; the writer matches only
  the `SKILL38:` namespace plus skill 38's own block, and removes no stamp.
- **`CORE_UPDATES.md`**: the AGENTS.md and MEMORY.md sections are re-headed
  `NO UPDATE NEEDED here`, so update-skills.sh's generic merger stops pasting this
  documentation prose into every box's core files as a `skill:38-...:agents` block.
- **`scripts/check-ghl-pit-liveness.sh` -- five verified defects fixed:**
  1. placeholder-shaped values (< 20 chars, `pit-abc*`, known dummy words) are SKIPPED, and
     a value from a secrets ENV-FILE outranks one from `openclaw.json` `env.vars`;
  2. the 401 BODY is inspected -- "Invalid Private Integration token" = a CREDENTIAL
     problem, a scope/not-authorized/not-accessible message = a CONFIGURATION problem
     reported as such and NEVER as "expired", anything else = unclassified operator triage;
  3. the probe endpoint matches the token CLASS -- an agency token goes to
     `GET /locations/search?companyId=...` with `Version: 2021-07-28`, a location endpoint
     is only probed with a location PIT;
  4. the operator alert names the variable that was ACTUALLY selected, and its source;
  5. "no usable credential configured" is its own honest status (exit 2, operator-only),
     never a client "your token expired" message.
  New exit contract: `0` valid/nothing to check, `1` credential failure, `2` configuration
  problem. The token value is never printed -- only the variable name, source and length.

### Evidence (scratch only, never against a live workspace)
- fresh install: 24 stanzas written, 362 -> 29,008 chars; run 2 byte-identical, no backup
- fat legacy (a real pre-clean 129,128-byte AGENTS.md): 24 blocks removed, 129,128 ->
  104,524 chars (-24,604, -19.1% of the whole file); all 44 `core-update-applied` stamps
  and all 8 other-skill blocks preserved; runs 2 and 3 byte-identical, one backup total
- skill-38 block bytes 52,444 -> 28,328 (-46%) with zero rule loss
- marker-rename duplication (69 skill-38 blocks across 3 marker generations): 235,041 ->
  104,524 in one pass, 46 retired markers swept
- watcher floor: 158,830 -> 63,711 (staged, floor 63,532) -> 28,745 (full) -> no-op; zero
  simulated restores across six passes
- PIT monitor: placeholder-only env -> "no usable credential" exit 2; live PIT in
  secrets/.env -> PASS exit 0; 401 scope body -> config problem exit 2; 401 "Invalid
  Private Integration token" -> credential failure; unclassified 401 -> exit 2, no client
  message; agency token -> `/locations/search` + `Version: 2021-07-28`; agency token with
  no company id -> config problem, never probed
- all 35 skill-38 QC gates: identical to the origin/main baseline (34 pass, 1 pre-existing
  environmental fail)

## [1.10.0] - 2026-08-03 - fix: MEMORY.md gets a POINTER, never the ~40,000-character rule corpus (and the idempotency guard actually works)

### Why
`scripts/06-append-memory-rules.sh` pasted the FULL text of design rules 6-44 (~40,000
characters, 24 fenced blocks) into every box's `MEMORY.md` on every install/update/fleet
roll. `MEMORY.md` is re-billed to the model on every single turn, so that corpus was a
permanent per-turn tax — and it was worse than a single paste, because the idempotency
guard was broken by construction: each block was fenced by a VERSION-STAMPED marker
(`<!-- BEGIN skill-38 memory-rules v1.5.0 -->`) and guarded by
`grep -qF "<that exact string>"`. The guard only ever protected against re-running THE SAME
VERSION. Every marker rename re-appended the whole corpus under the new name and nothing
removed the predecessor: `memory-rules v1.4.0` -> `builder-design-rules v1.5.0` and
`memory-rules v1.5.0` -> `round3-queueA-rules v1.5.0` each produced a verbatim second copy
of the same rules. Boxes carried the corpus two or more times and an earlier manual cleanup
was silently undone by the next roll.

### Changed
- **`scripts/06-append-memory-rules.sh` is now a POINTER writer.** It writes exactly ONE
  TYP-format block (WHAT / WHEN-trigger / WHY / POINTER / when-to-go-deeper) behind the
  VERSION-FREE marker `<!-- BEGIN skill-38 memory-rules-pointer -->`, naming the exact
  on-disk path to the full rules.
- **Idempotency is now a property of the writer, not of a string literal.** Before writing,
  every MATCHED `<!-- BEGIN skill-38 … -->` … `<!-- END skill-38 … -->` block (and the
  `skill:38-…:memory` legacy form) is removed — every legacy corpus block from every past
  version plus the script's own previous pointer. A rename can no longer create a duplicate.
  A second run is a byte-identical no-op and writes no new backup.
- **Self-heal.** Because the strip runs first, the next fleet roll CLEANS a bloated box
  instead of re-bloating it. Timestamped backup before any edit.
- **Staged descent past an anti-tamper core-file watcher.** Where a box keeps vaulted copies
  of its bootstrap files and restores any file that shrinks below max(200 bytes, 40% of the
  vaulted size), a one-shot 50 KB -> 1.5 KB replacement would be reverted minutes later. The
  script now computes that floor itself and removes only as many legacy blocks as keep the
  file at or above it, so the watcher accepts and re-vaults each pass; the next run works
  against the new baseline. Convergence is geometric (proved in test at 47,616 -> 19,309 ->
  8,621 -> 4,254 bytes with zero restores). The script never writes to the vault.
- **The pointer can never dangle:** the script copies `references/memory-design-rules.md`
  and all 51 `protocols/*.md` into the client's master-files folder, resolving the root via
  `SKILL38_MASTER_FILES_DIR` -> the folder `01-locate-master-files-folder.sh` persisted ->
  the platform default used by repo `scripts/typ-migrate.sh` (VPS `/data/.openclaw/master-files`,
  Mac `~/Downloads/openclaw-master-files`).
- **New overrides** `OPENCLAW_WORKSPACE`, `SKILL38_MASTER_FILES_DIR`, `SKILL38_COREFILE_VAULT`
  so the writer is testable without touching a real workspace.

### Added
- **`references/memory-design-rules.md`** — the canonical full text of design rules 6-44,
  lifted verbatim out of the script's heredocs (marker comments retained so each rule group
  is still addressable by its historical name). Reference count 25 -> 26.

### Fixed
- **Rule 17 3-PART -> 4-PART migration removed as obsolete.** The whole legacy block is now
  replaced wholesale, so the targeted rewrite has nothing left to migrate.
- **An unmatched `<!-- BEGIN skill-38 … -->` with no closing END no longer risks swallowing
  the rest of MEMORY.md** — it is restored verbatim.

### QC
- 13 gates that asserted the rule text lived inside the appender now assert it against
  `references/memory-design-rules.md` (`qc-ab-testing`, `qc-client-test-mode`,
  `qc-model-fallback`, `qc-multi-tenant`, `qc-opportunity-sync`, `qc-proactive-outreach`,
  `qc-segmentation`, `qc-tool-gating`, `qc-voice-phone`, `qc-webhook-chaining`,
  `qc-workflow-exits`, `qc-workflow-visual`, `qc-zhc-tag-prefix`). All 13 PASS.
- Full skill-38/39/40/41 gate sweep on this branch is identical to `origin/main`:
  96 pass / 3 fail, the 3 failures pre-existing and unrelated.

## [1.9.6] - 2026-07-31 - fix (SPEC Item 10): fleet approval gate — refuse when the box is not approved for conversational_ai

### Why
`fleet_standing.conversational_ai_approved` was a real column on every one of the 38 fleet
rows and nothing in Skill 38 ever read it — the operator ratified this system as gated
("we want to get that skill set also if they're not in good standing"), but a not-approved
box could still run the full install. Same class of defect Item 2 fixed for the anthology
engine.

### Added
- **STEP A2 in `scripts/00-verify-prerequisites.sh`** — immediately after the Cloudflare key
  check (Rule 10 requires that check stay first) and before every other prerequisite,
  asks the Item 1 fleet-wide standing endpoint (`POST /webhook/system-standing-check`,
  `{"system":"conversational_ai","box_slug":"<box>"}`) whether this box's `fleet_standing`
  row is approved (`good_standing===true && conversational_ai_approved===true`, computed
  read-time by the endpoint, never stored here). FAILS CLOSED on an unreachable endpoint,
  a non-200 reply, a missing credential, an unparseable body, or an unrecognised
  `reason_code` — all treated identically to an explicit refusal. On refusal it calls the
  shared rejection notifier (`POST /webhook/system-access-rejection-notify`,
  `system: "conversational_ai"`) so the client is told on whichever channel reaches them,
  then exits 1 (this file's own existing refusal idiom — no new exit code introduced).
- **Shell-native equivalent of `59-anthology-engine/scripts/standing_gate.py` (Item 2),
  not an import of it** — Skill 38 must not assume Skill 59 is installed on this box (this
  file's own STEP B already models cross-skill dependencies as an explicit presence check,
  not an assumed one). The contract matches `standing_gate.py` exactly: identical env var
  names/defaults (`FLEET_STANDING_GATE_HEADER` / `FLEET_STANDING_GATE_SECRET` /
  `FLEET_STANDING_BOX_SLUG`, the same already-fleet-propagated n8n httpHeaderAuth
  credential), identical curl-config-on-stdin secret hygiene (the header value never
  touches argv, a log line, or an error message), and the same never-guess-a-reason rule.
  No new credential provisioning needed on any box that already has the legacy
  fleet-standing propagation.

### Risk
Read-only network calls; the script never writes anything and every other prerequisite
check is unchanged. An unreachable standing-check endpoint now refuses the install where
it previously would have proceeded — this is the intended fail-closed behavior, not a
regression. No client names, emails, or channel ids.

## [1.9.2] - 2026-07-16 - GK-27/U89: relationship lattice pointer + citation tripwire

### Added
- **Relationship lattice pointer + citation tripwire.** SKILL.md gained a one-line pointer to the new `docs/CONTENT-CONVERSATION-LATTICE.md` (the canonical Skill 6/44/35/38/3 content↔conversation relationship map, which now canonicalizes and replaces the five partial cross-references this and other skills carried). A new `scripts/qc-lattice-pointer.sh`, wired into `scripts/11-run-qc-checklist.sh`, asserts the pointer is present AND that this skill's own owned edges — the inbound-ownership statement ("Skill 38 OWNS every inbound conversation those CTAs generate...") and the build-path-ladder statements (caf-direct PRIMARY route + "NOT a hard prereq") — still cite real, unchanged ground truth (`docs/tools/check_lattice_citation.py`, drift tripwire; fail-first proof in `docs/tools/test_check_lattice_citation.py`). No behavior change to the inbound pipeline itself.

## [1.9.1] - 2026-07-12 - P3-08 merge (renumbered [1.8.3]→[1.9.1] — branch cut at 1.8.2, [1.9.0] P3-07 landed on main first): Skill 35 named as an inbound SOURCE (DM-CTA + comment handoff)

### Added
- **Cross-reference to Skill 35 (`social-media-planner`) as an INBOUND SOURCE** (SKILL.md "What This Skill Is"). Skill 35's campaign CTAs feed conversations into this brain two ways: (1) the primary DM CTA (playbook §12) → FB/IG DM → GHL Conversations → this skill's existing inbound pipeline; (2) the comment-reader (playbook §12b) surfaces prospect comment replies as synthetic handoffs into this skill's `conversational-logs/`. Skill 38 OWNS every inbound conversation those CTAs generate; Skill 35 never answers a conversation itself. Reciprocal reference added in `35-social-media-planner/SKILL.md` (Phase 4). Closes the Skill 35 ↔ Skill 38 zero-cross-reference gap. No code/behavior change to the inbound pipeline itself.

## [1.9.0] - 2026-07-11 - fix+feat (P3-07): playbook_engine.py parser fixes + the RUNTIME U-1 tool-gating prover

Two live parser fixes in `tools/playbook_engine.py` (the SINGLE canonical parser every machine-enforced QC gate trusts) plus the missing RUNTIME proof for the tool-gating guarantee. Preserves every v1.8.x differentiator. OPERATOR-ONLY surfaces; no customer-invokable path. No client names.

### Fixed - parser (the file every QC gate trusts)
- **`###` heading closure (P3-07 root cause 1):** the phase-block-closing logic claimed a `#`/`##`/**`###`** non-Phase heading closes the current phase's key:value scan, but the check matched only `# `/`## `. A bare `### Some heading` mid-playbook silently absorbed its lines into the preceding phase, corrupting that phase's `tools`/`max-attempts` resolution — the exact data the U-1 tool-gating gates rely on. The closing tuple now includes `"### "` (the `#### edge` carve-out and the Phase-N exemption are preserved). Regression test added to `tools/tests/test_playbook_engine.py` (`TestPhaseHeadingClosure`): a `### Notes` block with `tools: everything` + `max-attempts: 99` must NOT leak into Phase 1 — proven to FAIL against the pre-fix engine (the 2.1 fail-first law).
- **exit-rule order-independence (P3-07 root cause 3):** `_parse_exit_rule` assumed `closing:` always precedes `target:`; a reversed order let `target` greedily swallow the trailing closing message with no validation error. Rewritten to parse `action`/`closing`/`target` as named segments in ANY order — neither can swallow the other. `TestExitRuleOrderIndependence` covers both orders + the malformed (no-action) case, which now surfaces as a LOUD validate defect, never a silent bad parse.

### Added - RUNTIME U-1 tool-gating prover (P3-07 root cause 2)
- **`scripts/33-runtime-tool-gating-prover.sh`:** the tool-gating twin of `scripts/24-self-test-hook.sh`. Layer A (static ground truth, CI-safe) resolves the fixture playbook's active phase via the canonical engine and asserts it grants `check_availability` (tool A) but NOT `book_appointment` (tool B). Layer B (live) seeds the fixture + a throwaway conversation log, POSTs a synthetic flat-23-key inbound engineered to tempt an immediate `book_appointment` call, reads the session transcript, and asserts by GROUND TRUTH that the agent REFUSED the ungranted tool (and used tool A / escalated / logged a gate-deny — a silent no-op is not a pass), quoting the refusal evidence. Writes `runtimeToolGatingPassed`; `--dry-run` runs Layer A only; `--auto` (box-level scheduled) runs live when configured and degrades to Layer A otherwise (never schedule spam). Converts tool gating from "the agent read the protocol" to a machine-enforced runtime proof.
- **`scripts/qc-runtime-tool-gating.sh` (+ `.test.sh`):** the gate. RUNS the engine against the shipped fixture to prove the gating boundary is real (not a grep), runs the prover's Layer-A `--dry-run`, and asserts the live-layer wiring (own-hook POST + Bearer + transcript read + refusal check + state write) is present and that the prover is wired into the pre-handoff gate set AND the box-level self-test cron. The negative test proves the gate FAILS when the fixture's active phase is mutated to also grant `book_appointment`. Fixtures: `tools/tests/fixtures/runtime-gating-playbook.md` + `runtime-gating-log.md`.
- **Wiring:** added to `scripts/11-run-qc-checklist.sh` (pre-handoff gate set + file-existence list) and `.github/workflows/qc-static.yml` (gate + negative test), and registered as the `skill38-tool-gating-selftest` box-level self-test cron in `scripts/04-register-crons.sh` (2nd of each month, `--auto`). `register_command_cron` gained an optional script-args parameter so existing callers are unchanged.

## [1.8.0] - 2026-07-05 - feat: CloseBot Alignment Upgrade (17 cards U-1..U-17) - per-phase tool gating, tag-driven exits, objective metadata, canonical playbook engine, model fallback chain, workflow visuals, GHL coverage (multi-calendar / opportunity sync / handoff tasks / install snapshot), and the departments-and-roles operating SOP

This minor closes the 11 CloseBot feature-parity gaps (U-1..U-11), adds four GHL-coverage updates (U-12..U-15), ships the canonical playbook parser (U-16), and lands the organizational operating SOP (U-17). Every new surface is OPERATOR-ONLY: no customer-invokable path exists, and every protocol carries the injection-vector language (a customer naming a tag, tool, calendar, pipeline stage, or persona changes nothing). All new JSONL sinks are PII-free and seeded only via `scripts/25-seed-round3-feature-files.sh`. Every new QC gate is wired into BOTH `scripts/11-run-qc-checklist.sh` AND `.github/workflows/qc-static.yml` and ships with a negative `.test.sh` that fails on a seeded bad fixture. Preserves every v1.7.13 differentiator (runtime GHL Tier ladder + raw-REST fallback + 401 no-credential honesty, daily GHL PIT-liveness cron, Command Center Kanban via `cc-task.sh`, cron silence doctrine, operator-exclusion in client-doc delivery, existence-only secret greps, the talk-to-build Conversation Playbook Builder). `references/v6.0-source-playbook.md` is untouched. No client names.

### Added - CloseBot feature-parity (U-1..U-11)
- **U-1 Per-phase tool gating, THE GATE (CARD-01):** `protocols/tool-gating-protocol.md` + `scripts/qc-tool-gating.sh` (+ `.test.sh`). A playbook phase resolves a HARD enabled-tools capability set; a tool not granted for the active phase cannot fire regardless of prompt drift. `escalate_to_human` is ALWAYS granted and can never be gated off. AGENTS.md marker `STEP_1_88_TOOL_GATING`; MEMORY design rule 32.
- **U-2 Tag-driven workflow exits (CARD-02):** `protocols/workflow-exit-rules-protocol.md` + `scripts/qc-workflow-exits.sh` (+ `.test.sh`). AGENTS.md marker `STEP_1_30_EXIT_RULES`; MEMORY design rule 33.
- **U-3 Smart FAQ closed learning loop (CARD-04):** an unknown FAQ is flagged to the operator (never auto-answered as fact). MEMORY design rule 34.
- **U-4 Objective metadata on phases (CARD-07):** `protocols/conversation-log-protocol.md` per-contact log header carries `active_workflow`, `active_phase`, and `phase_attempts`; U-1 resolves the phase from the SAME header lines, so U-1 and U-4 share one source of truth. MEMORY design rule 35.
- **U-5 Persona registry (CARD-15):** `protocols/persona-registry-protocol.md`; a persona is a named, reusable style object. MEMORY design rule 36.
- **U-6 Client test mode (CARD-14):** `protocols/client-test-mode-protocol.md` + `scripts/qc-client-test-mode.sh` (+ `.test.sh`). Three enforcement layers (state flag re-read at AGENTS.md marker `STEP_0_4_TEST_MODE_REREAD`, U-1 gate forcing every phase to the empty tool set, and WOULD-HAVE narration); auto-expires after 60 minutes or on `end test`. MEMORY design rule 37.
- **U-7 Standard lifecycle status tags (CARD-05):** `protocols/zhc-tag-prefix-protocol.md` lifecycle tags; `scripts/qc-zhc-tag-prefix.sh`.
- **U-8 Model fallback chain (CARD-12):** `references/model-fallback-chain.md` + `scripts/32-verify-model-failover-support.sh` + `scripts/qc-model-fallback.sh` (+ `.test.sh`). Mode A (per-session model override) vs Mode B (standing model + routing hint). MEMORY design rule 38. Client agents run on the client's OWN configured providers; never a hardcoded Anthropic or paid-cascade prescription.
- **U-9 Machine-readable playbook references / declares block (CARD-08):** `scripts/qc-playbook-declares.sh` (+ `.test.sh`) cross-validates tools-used against phase tool lines, exits-used against exit rules, and `ZHC_` fields against the CRM mappings.
- **U-10 Per-workflow model tier override (CARD-13):** the Layer 2 header may carry `model-tier`; live only in U-8 Mode A, a logged routing hint in Mode B. Documented in `references/model-fallback-chain.md`.
- **U-11 Workflow visual diagram on every build, Part 4 (CARD-03):** `protocols/workflow-visual-protocol.md` + `scripts/31-generate-workflow-visual.sh` + `scripts/qc-workflow-visual.sh` (+ `.test.sh`). Kie.ai plus Mermaid. MEMORY design rule 39; the 3-PART Build Rule (rule 17) becomes the 4-PART Build Rule.

### Added - GHL coverage (U-12..U-15)
- **U-12 Multi-calendar routing (CARD-09):** the declares block carries a `calendars` map; `scripts/qc-playbook-declares.sh` validates every calendar id against a cached caf calendars export. MEMORY design rule 40.
- **U-13 Opportunity and pipeline stage sync (CARD-10):** `protocols/opportunity-sync-protocol.md` + `scripts/qc-opportunity-sync.sh` (+ `.test.sh`). MEMORY design rule 41.
- **U-14 Human task creation on handoff (CARD-06):** when `ZHC-ai-handoff` fires, the brain creates a GHL Task on the contact (PII lives inside the client's own CRM, not the PII-free JSONL logs) with an SLA due time; documented in `protocols/notification-routing-protocol.md`. MEMORY design rule 42.
- **U-15 Convert and Flow install snapshot (CARD-11):** `references/convert-and-flow-snapshot-guide.md` + the raw fixture `references/snapshot-inbound-workflow-fixture.json` (no backtick fences; validated by `scripts/qc-23-key-bodies.sh` so snapshot drift from the FLAT 23-key raw-body standard fails CI). MEMORY design rule 43.

### Added - engine and organization (U-16, U-17)
- **U-16 playbook_engine.py, the canonical parser (CARD-16):** `tools/playbook_engine.py` with `validate`, `hash`, `mermaid`, and `resolve --log` subcommands + `tools/tests/test_playbook_engine.py`; driven by `scripts/qc-playbook-engine.sh`. MEMORY design rule 44. Runs FIRST since every later gate calls it.
- **U-17 Departments, roles, and the operating SOP (CARD-17):** `references/departments-and-roles.md` + the operating SOP `universal-sops/SOP-CONV-AI-01-OPERATING-THE-CONVERSATIONAL-AI-SYSTEM.md`.

### Changed
- SELF-COUNTS in SKILL.md recounted on disk: protocols/ 45 to 51, scripts/ 70 to 88, references/ 22 to 25 (journey templates unchanged at 8).
- `scripts/00-verify-prerequisites.sh` STEP G appended (kie-image-events prerequisites) without disturbing the PR #511 Command Center ACTIVE/INACTIVE additions.
- `PREREQS.json` lists Skill 07 as required and Skill 46 as recommended.

### Notes
- Bumped to 1.8.0 (one minor above the live 1.7.13). SKILL.md carries no top-level frontmatter `version:`, so the frontmatter-version guard skips this skill by design; `skill-version.txt` is the single source (one line, no v prefix, trailing newline). Ships in the repo unified train v17.0.32. There is no per-skill git tag; per-skill tags are not part of the repo's unified scheme.

## 1.7.15 — Wave-2 train W2-doc-38 (FIX-XC-13c — INSTALL.md doc/count drift)

### Fixed (FIX-XC-13c — INSTALL.md regenerated from SELF-COUNTS)
- `INSTALL.md`: reconciled the stale hard-coded counts in "What this installs" against
  disk and against SKILL.md's authoritative SELF-COUNTS (which were already current):
  protocols **32 → 45**; reference documents **15 → 22**; numbered install-script range
  **`00`–`29` → `00`–`30`** (adds `30-voice-phone-setup-wizard.sh`). Added the six shipped
  Round-2 feature QC gates (`qc-multi-tenant` / `qc-segmentation` / `qc-proactive-outreach`
  / `qc-ab-testing` / `qc-voice-phone` / `qc-webhook-chaining`, each + its `.test.sh`) and
  `qc-f45-f47-substance.sh` to the linter list, and `GHL_AI_LAYERS.md` to the references
  summary.
- `INSTALL.md`: corrected the FALSE "Does NOT implement pending roadmap features
  (F14…F21)" line — all six Round-2 backlog features SHIPPED in v1.5.7–v1.5.12 (matching
  SKILL.md "All six Round-2 backlog features have shipped"). The line now states they ship
  OFF-by-default (operator opt-in per feature; live voice telephony needs operator Twilio/
  STT/TTS creds via `30-voice-phone-setup-wizard.sh`). Added a positive "6 Round-2 backlog
  features (all SHIPPED, OFF by default)" bullet to "What this installs", and a truthful
  continuation note to the install-order code block (which had implied scripts stop at `08`).
- `scripts/bump-version.sh` (repo-root — the single version-bump tool): extended the
  "SKILL 38 SELF-COUNT RE-VERIFICATION" checklist to ALSO cover INSTALL.md, and added a
  non-fatal `skill38_doc_selfcount_advisory` that diffs the protocol/reference counts and the
  `00`-`NN` script range in BOTH SKILL.md and INSTALL.md against disk (plus a stale-"pending"
  guard on INSTALL.md), printing WARNs on every `--check`/bump. Advisory only — never mutates
  a file and never changes the exit code, so it is safe under `set -e` in the release path.

### Notes
- Scope: `38-conversational-ai-system/INSTALL.md` + `38-conversational-ai-system/CHANGELOG.md`
  + `skill-version.txt`, and the repo-root `scripts/bump-version.sh` (the skill's own bump
  tool — it lives at repo root, not under the skill dir, so no per-skill guard applies to it).
  This is the skill's own patch bump (1.7.14 → 1.7.15), NOT a repo-wide release. No client
  names, no secrets. SKILL.md carries no top-level frontmatter `version:`, so the
  frontmatter-version guard skips this skill by design (skill-version.txt is the single source).

## 1.7.14 — merge-train T-w1-board-and-54 (Wave-1)
- **FIX-XC-06** — `scripts/cc-task.sh` gained a `fail` subcommand that moves the
  install task to `blocked` (never `done`), with an optional reason as the card
  note; it is invoked from the FAIL branch of `scripts/11-run-qc-checklist.sh` so a
  failed mechanical QC is VISIBLE on the board instead of leaving the card stranded
  at in_progress. `cmd_start` now does GET-before-PATCH so a re-run never regresses a
  card the independent QC scorer already advanced to `review`/`done` back to
  in_progress. Both paths stay fail-soft (always exit 0, never message a client).

## [1.7.13] - 2026-07-05 — fix: cron silence-doctrine (--no-deliver + isolated session), Command Center env docs + ACTIVE/INACTIVE, safe operator-exclusion in client-doc discovery

### Fixed (FIX-XC-08b — cron delivery silencing / silence doctrine)
- `scripts/04-register-crons.sh`: replaced `--best-effort-deliver` on the agent-message cron path with `--no-deliver` **plus** `--session isolated`, so the 5 maintenance crons (conversation-log-summarizer, analytics-weekly-digest, weekly-tune-up, proactive-suggestions-scan, system-health-heartbeat) never fallback-deliver their output to the client chat and run off the client-facing main session. On CLI 2026.6.8+ `cron add` defaults to announcing the job's final text to the last chat, which would have spammed the client on every fire. Both flags are FEATURE-DETECTED against `cron add --help` with a no-flag retry (older CLIs register without them rather than fail). The `ghl-pit-liveness` command-cron gains `--no-deliver` too (silences the runner's stdout dump; the script's own deliberate client 401-notice still sends). Added a soft `cron list` delivery-mode assertion after each add (pure bash, stock-3.2 safe).
- `scripts/15-configure-hooks-mappings.sh`: same silencing (`--no-deliver` + `--session isolated`, feature-detected + no-flag retry) on the `system-health-heartbeat` cron it registers.

### Fixed (FIX-S36-07 — Command Center reporting config was undocumented)
- `INSTALL.md`: documented the three `cc-task.sh` env vars — `MC_API_TOKEN` (required for any board post), `MC_SKILL38_SOP_ID`, `MC_SKILL38_AGENT_ID` (the optional leave-backlog Triad) — plus `MISSION_CONTROL_URL`. Previously undocumented, so `cc-task.sh` silently no-op'd and the install task never landed on the board.
- `scripts/00-verify-prerequisites.sh`: prints an explicit `Command Center reporting: ACTIVE` / `INACTIVE` line (keyed on `MC_API_TOKEN`) right before the `cc-task.sh start` call, so the operator sees whether the install is being carded instead of guessing.

### Fixed (FIX-S36-08 — client doc could be sent to the operator when the operator id was unset)
- `scripts/22-notify-client-doc.sh`: transcript discovery excludes the OPERATOR chat id so the client doc is never sent to the operator — but the exclusion only worked when `OPERATOR_TELEGRAM_CHAT_ID` was set (`grep -vxF ""` excludes nothing). Now: (1) when the var is unset, cross-check the fleet resolver `shared-utils/operator-chat-id.sh` (config + env, incl. `OPERATOR_ESCALATION_CHAT_ID` / `ZHC_OPERATOR_CHAT_ID`); (2) if the operator id is STILL unresolved on the discovery path, FAIL LOUDLY with a banner and require an explicit `SKILL38_ACK_OPERATOR_CHAT_UNSET=1` ack to proceed (writes `clientDocDelivered=false` on refusal); (3) the exclusion filter now only runs when the operator id is non-empty, removing the empty-pattern footgun. A provided `CLIENT_TELEGRAM_CHAT_ID` bypasses the gate (no discovery needed).

### Notes
- Bumped to 1.7.13 (not 1.7.12): origin/main independently published 1.7.12 for this skill (the FIX-XC-07 / FIX-XC-09g secret-grep + Anthropic-operator-only release, retained below), so this merge-train advances to the next free patch to avoid a version collision. Wave-0 merge-train T-38-conversational-ai; changes are scoped to `38-conversational-ai-system/` only. SKILL.md carries no top-level frontmatter `version:`, so the frontmatter-version guard skips this skill by design (skill-version.txt is the single source).

## [1.7.12] - 2026-07-05 — fix: secret-printing greps → existence-only (FIX-XC-07); ANTHROPIC verify branch annotated operator-only (FIX-XC-09g)

### Security (FIX-XC-07 — no secret VALUES in transcripts/logs)
- `references/v6.0-source-playbook.md`: every credential-verification grep in the setup flow is now
  EXISTENCE-ONLY (`grep -qE '^(export )?KEY=' && echo SET || echo MISSING`) instead of printing the
  matched line — the GEMINI/GOOGLE embedding check, the OpenRouter/Ollama/direct-provider model-pick
  checks, and both Notion three-layer checks.
- `references/HOSTINGER-DOCKER-ENV.md`: the live-process env checks no longer print values — Step 3
  strips the value with `cut -d= -f1` (key NAMES only) and the post-recreate verify uses
  `grep -q '^NEW_API_KEY=' && echo "NEW_API_KEY loaded"`.

### Changed (FIX-XC-09g — Anthropic is operator-only, never a client model pick)
- `references/v6.0-source-playbook.md` model-provider preflight: split the combined
  `ANTHROPIC_API_KEY|OPENAI_API_KEY|GOOGLE_API_KEY` check so Anthropic is no longer verified/wired as a
  client provider, and annotated it OPERATOR-ONLY (cost-prohibitive; client agents run on the client's
  OWN configured providers only — never a hardcoded Anthropic or paid-cascade prescription).

### Notes
- Supersedes 1.7.11 (which shipped with no CHANGELOG entry, mirroring the earlier 1.7.9/1.7.7 gaps below).
- Repo-level: a new deterministic shipped gate `scripts/qc-assert-no-secret-printing-grep.sh`
  (wired into `qc-static.yml`) fails any secret-pattern grep in the 36/38 SOPs that lacks `-q`/`-l`/`-L`.

## [1.7.10] - 2026-07-01 — docs: caf-first banners on 7 automation-proposing protocols + caf-path verify mandate + qc-built-workflow.sh gate in monthly-review cron

### Added (caf-first banner — final-review Points 2/3/7-fix7)
- Added an identical caf-first banner (`BUILD path:** caf-direct...`) to the 7 protocol files that propose creating or altering a GHL automation: `protocols/business-logic-workflow-suggestions-protocol.md`, `protocols/intelligent-routing-protocol.md`, `protocols/smart-playbook-switching-protocol.md`, `protocols/proactive-suggestions-protocol.md`, `protocols/monthly-comprehensive-review-protocol.md`, `protocols/weekly-tune-up-protocol.md`, `protocols/prompt-injection-protection-protocol.md`. Read all 45 protocol files in full (not just grepped) to find this set; excluded operator-owned, third-party, and read/route/tag-only protocols after reading each.

### Changed (caf-path verify mandate)
- `protocols/conversation-workflows-protocol.md`: added a Section E caf-path verify mandate (cross-referencing the D.3 End-to-end test subsection) requiring `44-convert-and-flow-operator/qc-built-workflow.sh <workflow-id> --json` before asking the human to verify a caf-built workflow; added a "Verification completed" column to the Section F registry table (Yes-pass / No-not-yet-verified / FAILED) so monthly review can surface delivered-but-never-verified workflows.
- `templates/workflow-verification-checklist-template.md`: mirrored the caf-QC mandate + verification_completed recording instruction in its own End-to-end test section.
- `scripts/04-register-crons.sh`: extended cron 5 (system-health-heartbeat) prompt text so the GHL-workflow audit clause runs `qc-built-workflow.sh --json` per built workflow and folds the PASS/FAIL result into the audit, instead of relying on agent prose alone.

### Notes
- Bumped from 1.7.9 (which shipped with no CHANGELOG entry, mirroring the 1.7.7→1.7.8 gap below) → 1.7.10.

## [1.7.8] - 2026-06-30 — feat: runtime GHL tier ladder (caf-first) + runtime-PIT liveness + 401 credential fallback; caf build-path preflight; GHL cred canonicalization; Command Center Kanban lifecycle

### Added (runtime GHL fallback — deep-dive P0/P1)
- **Runtime GHL TIER LADDER in the agent brain** — new AGENTS.md marker block `SKILL38_RUNTIME_GHL_TIER_LADDER` (via `scripts/05-update-agents-md.sh`): Tier 0 caf (Skill 44, PRIMARY — `caf conversations`/`calendars`/`contacts`/`payments`/`locations`; exact flags via `caf --help`, never guessed) → Tier 1 official GHL MCP (orchestrator only) → Tier 2 community MCP (billing/products) → **Tier 3 raw REST (the existing curl, KEPT as the documented last-resort fallback)**. Media stays Tier 3. Inbound hook + FLAT 23-key body + `hooks.mappings` + `deliver:false` are UNCHANGED. Nothing removed — caf is added IN FRONT of raw REST.
- **No-credential / 401 honesty-floor clause** (same block): on a GHL send/read 401/non-2xx the agent NEVER reports the reply "sent" — it escalates to the operator AND sends the CLIENT a plain-English "refresh your GHL connection" message (which var, where it lives, re-issue steps).
- **Daily runtime-PIT liveness watcher** — new `scripts/check-ghl-pit-liveness.sh`: the RUNTIME-PIT twin of Skill 44's Firebase `ghl-token-liveness`. Probes the location PIT via the skill's own in-scope READ (`GET /conversations/search`, scope `conversations.readonly`, so a valid token never false-alarms); 2xx = day-stamp, clean 401 = notify the CLIENT's own Telegram once per day with PIT-refresh steps, any other non-2xx is operator-logged without client spam. PII-free target resolution (no hardcoded chat ids — `CLIENT_TELEGRAM_CHAT_ID` / `OPERATOR_TELEGRAM_CHAT_ID` env, mirrors `22-notify-client-doc.sh`). Registered as cron `ghl-pit-liveness` (daily) in `scripts/04-register-crons.sh` via the CLI-portable command-cron pattern (`--command` on 2026.6.x, agent-message fallback on 2026.5.x). Distinct name from Skill 44's cron — no collision.
- Compact **runtime tier-ladder pointer** added to the TOOLS.md cheat sheet (`references/ghl-api-quick-reference.md`); `scripts/qc-tools-md-ghl-ref.sh` char budget bumped 7000→7500 with rationale (one blockquote; 92/120 lines used — the line guard remains the real anti-bloat gate).

### Added (caf build-path preflight + Skill 29/44 reconcile — GHL-review P0)
- `scripts/00-verify-prerequisites.sh` **STEP F (non-fatal)**: preflights caf + Skill 44 + the Firebase refresh token and REPORTS the ACTIVE BUILD PATH (Option 1 caf-direct vs Option 2 manual Build-with-AI paste) so a client is never silently on Option 2. Skill 29 (runtime GHL connection) stays the HARD prereq; Skill 44 is documented as required-for-Option-1 (not hard).
- **SKILL.md** reconciled: Skill 29 = runtime GHL connection (hard prereq, STEP E); Skill 44 (`caf`, Tier 0) = the caf-direct build path (Option 1) + runtime Tier-0 preference. Added to the Prerequisites list.

### Added (Command Center Kanban lifecycle — GHL-review AI GOAL)
- New `scripts/cc-task.sh` (`start`/`review`) — graceful-degrading Command Center task lifecycle. `start` creates-or-reuses the Skill-38 install task and moves it to `in_progress`; `review` moves it to `review` (the independent CC auto-scorer promotes review → the done column — the builder NEVER self-grades). curl-only; never prints `$MC_API_TOKEN`; on missing token / unreachable host / any non-2xx it prints ONE operator-only stderr line and exits 0 (never fails the caller). Wired fail-soft: `00-verify-prerequisites.sh` → `cc-task.sh start || true`; `11-run-qc-checklist.sh` (only when FAIL==0) → `cc-task.sh review || true`. Task id persisted to `~/.openclaw/.skill-38-cc-task-id`. `11` also gained a non-blocking informational check for the `ghl-pit-liveness` cron.

### Changed (GoHighLevel credential canonicalization)
- `scripts/00-verify-prerequisites.sh` STEP E now accepts the CANONICAL cred names (`GOHIGHLEVEL_API_KEY` / `GOHIGHLEVEL_LOCATION_ID`) in ADDITION to the legacy/PIT aliases (`GHL_PRIVATE_INTEGRATION_TOKEN` / `GHL_API_KEY` / `GHL_LOCATION_ID`), and searches the `secrets/.env` subdir + VPS `/data` path — a box on either naming now passes (backward-compatible; nothing renamed out). `check-ghl-pit-liveness.sh` resolves creds in the same canonical-first order.
- `scripts/qc-send-directive.sh`: documented that caf-first templates already PASS unchanged (element 2 satisfied by the retained `conversations/messages` fallback reference) — the gate is NOT weakened and does not require caf (caf-less boxes still pass).

### Anti-Anthropic (verification only — no client model recommends Anthropic)
- Full re-scan: this skill recommends NO Anthropic/Claude runtime model. All remaining `anthropic`/`claude` strings are defensive provider-routing (`anthropic/*) → ANTHROPIC_API_KEY`), informational provider lists (model-freshness endpoints, "where keys live"), framework names ("Claude Code"), anti-Anthropic steering ("Anthropic models are NOT recommended for client install subagents"), or prompt-injection/identity-drift example strings ("are you Claude"). None changed. No Anthropic/Claude model id introduced anywhere. (Genuine client-model recommendations were already scrubbed to DeepSeek/Ollama in v1.7.6.)

### Notes / not-done (flagged for operator)
- Bumped from 1.7.7 (which shipped with no CHANGELOG entry) → 1.7.8.
- NOT done this pass (too large/risky or unverifiable — flagged): extending `24-self-test-hook.sh`/`qc-self-test.sh` to exercise the caf send path (needs a working `caf --help`; broken in this shell — anti-fabrication), a net-new QC gate that fails when the tier ladder / fallback clause is absent (+ negative fixture), the single canonical path/secrets-resolver refactor across 04/15/self-test, the `_wire_*.py` atomic-write hardening, the weekly PII-safe client recap, and a full SKILL.md self-count recompute.

## [1.7.6] - 2026-06-15 — fix: strip client-facing Anthropic options from model-picker lists

### Changed (anti-Anthropic strip, repo v12.14.6)
- Removed `anthropic/claude-opus-4-7` from the install-subagent model lists in `references/subagent-delegation-pattern.md` and the source-of-truth `references/v6.0-source-playbook.md` (both the priority list and the interactive picker); added a "not recommended for client install subagents (operator-only, cost-prohibitive)" note. Primary was already `deepseek/deepseek-v4-pro` via Ollama Cloud / OpenRouter — unchanged.
- `protocols/web-scraper-protocol.md` (+ playbook copy): scraper "higher quality" alternative `anthropic/claude-haiku-4.5` → `ollama/deepseek-v4-pro:cloud` (or `openrouter/deepseek/deepseek-v4-pro`).
- `scripts/15-configure-hooks-mappings.sh`: async-tier picker "premium quality" option `anthropic/claude-opus-4-7` → `ollama/deepseek-v4-pro:cloud`.
- No runtime behavior change; the default/primary models were already client-available. Clients are never pinned to Anthropic.

## [1.7.2] - 2026-06-11 — de-hoop: route workflow-creation through Skill 44 (Tier 0) first

### Changed (GHL skills integration review — CAF-first de-hoop)
- **Operator-facing handoff + templates now lead with Skill 44 (Tier 0), not the manual Build-with-AI hoop.** Per the fleet directive ("clients never jump through hoops to create a workflow — they just ask their Skill-44 agent"), the build-path instructions the agent reads to the owner are reordered to CAF-first:
  - `protocols/conversation-workflows-protocol.md` — operator handoff (~L370) now says: if the Firebase token is connected, **Skill 44 builds the workflow directly — the owner does nothing**; Build with AI is the explicit no-token fallback. The §D.2 CRITICAL note (~L286) reworded to the same Option-1 (CAF, PRIMARY) / Option-2 (Build-with-AI, no-token fallback) framing.
  - `templates/sms-workflow-ai-prompt-template.md` — added the CAF-first lead; the manual Build-with-AI steps are now labeled "fallback — only when the Firebase token is NOT connected."
  - `templates/workflow-verification-checklist-template.md` — corrected the factual error that Build-with-AI is "the only programmatic path"; Skill 44's internal-API path IS programmatic and is primary when the token is present.
  - `references/workflow-ai-instructions-standard.md` — "WHERE it goes" §1 reordered to Option 1 (Skill 44 / Tier 0, PRIMARY) then Option 2 (Build with AI, no-token fallback); intro paragraph aligned.
  - `CORE_UPDATES.md` Rule 16 (Convert-and-Flow Build-Path Rule) reworded to CAF-first.
- **3-layer separation preserved** (Layer 0 Build-with-AI prompt / Layer 1 Workflow-AI step prompt / Layer 2 OpenClaw playbook never conflated). The TRINITY rule + `scripts/qc-trinity-registry.sh` hard gate are untouched. Prompt-generation (§D.2) and the path-agnostic verification checklist remain documented manual artifacts (legitimate exceptions — caf consumes a prompt but does not author it).

### Fixed
- SKILL.md SELF-COUNTS: `references/` count reconciled 19 → 22 to match disk (the Addendum-C `GHL_AI_LAYERS.md` merge plus `GHL-INBOUND-AND-PLAYBOOKS.md` and `VPS-VS-MAC-INSTALL.md` were on disk but uncounted). Per the bump-version.sh Skill-38 self-count re-verification rule.

## [1.7.1] - 2026-06-11 — wire.sh stock-bash-3.2 compatibility (externalize python-in-$() heredocs)

### Fixed
- **`wire.sh` could not PARSE on stock macOS `/bin/bash` 3.2.57.** The M3 Rules-15/16
  migration runner embedded two `python3 - "$X" <<PYEOF ... PYEOF` heredocs INSIDE `$()`
  command substitutions. bash 3.2 mis-counts the double-quotes inside a heredoc nested in
  a `$()` and aborts the WHOLE script with `unexpected EOF while looking for matching "`
  at PARSE time — so on every client Mac WITHOUT Homebrew bash, `update-skills.sh`'s
  auto-invocation of `wire.sh` (it runs `$SKILL_DIR/wire.sh` first on each update) silently
  failed and the live MEMORY.md/AGENTS.md Rules 15/16 rewrite never applied. Same root-cause
  class as the qc-completeness.sh v11.18.4 fix.

### Changed
- Externalized the two heredoc bodies to sibling files `_wire_rules_15_16.py` (MEMORY.md
  Rules 15/16 rewrite) and `_wire_agents_ghl_note.py` (AGENTS.md GHL build-path note),
  invoked as `python3 "$SCRIPT_DIR/<file>" "$TARGET_MD"`. Logic byte-equivalent. `wire.sh`
  now resolves `SCRIPT_DIR` and is `bash -n` clean on both bash 3.2.57 and bash 5.x.
  Verified live: full M3 run + idempotent re-skip on stock `/bin/bash` 3.2 with fixtures.

## [1.7.0] - 2026-06-11 — CAF-first workflow build (Option 1 primary); Build-with-AI demoted to fallback; human=final verifier; +GHL_AI_LAYERS.md

### Why
Skill 44 v2.1.0 (engine CLI 2.1.0, merged `beb43e35`) resolved both critical build bugs —
`link_steps()` pre-save fix eliminating GHL 400 corrupted-order errors, and rejected-save
non-zero exit eliminating the silent Steps:0/Errors:0/exit-0 false-pass. With these fixes
verified in main, the CAF direct-build path is now the reliable Option 1 primary. The
Build-with-AI manual paste is demoted to Option 2 fallback (Firebase token absent/expired).
The 3-layer architecture (Layer 0 compile-time, Layer 1 runtime Workflow AI step, Layer 2
OpenClaw playbook) was undocumented; operators confused the three surfaces repeatedly. The
human-is-final-verifier rule was implicit; it is now explicit in every build-path touchpoint.

### Added
- `references/GHL_AI_LAYERS.md` (NEW) — the authoritative 3-layer GHL AI architecture
  reference. Layer 0 = compile-time Build-with-AI / CAF direct-build. Layer 1 = runtime
  GHL Workflow AI step prompt (inside a Conversation AI node). Layer 2 = OpenClaw
  Master-Files playbook (`conversation-workflows/<id>.md`). Explains CAF-first (Option 1)
  vs Build-with-AI (Option 2) routing, the CAF engine v2.1.0 fixes, the human-is-final-
  verifier rule, and a quick decision table. Cross-referenced by skills 36, 38, 41, 44.

### Changed
- `INSTRUCTIONS.md` — "Read first" block: added item 6 pointing to `GHL_AI_LAYERS.md`.
  Step 9.20 GHL build-path note rewritten: **CAF-first (Option 1 PRIMARY)** when Firebase
  token present; **Build-with-AI (Option 2 FALLBACK)** when absent. References Skill 44
  engine v2.1.0 fixes (engine fix SHA `beb43e35`). Adds explicit "human is always the
  final verifier" statement with the in-builder Test-button caveat.
- `references/GHL-INBOUND-AND-PLAYBOOKS.md` — Section 4 header renamed to clarify it is
  the Option 2 fallback template. Pre-amble updated with a routing callout box: Option 1
  (CAF direct, PRIMARY) vs Option 2 (this section, fallback). Cross-links `GHL_AI_LAYERS.md`.

## [1.6.0] - 2026-06-10 — Skill 44 era: nine-file sweep + Rules 15/16 rewrite + TRINITY/self-test wiring + alias-aware credentials

### Why
Skill 44 (convert-and-flow-operator) ships an internal-API workflow-build path. Without this rewrite, every onboarded agent carries a standing NEVER rule (Rule 16) that forbids skill 44's core capability. This is the critical blocker fix.

### Changes
- **Nine-file sweep:** all occurrences of the old "NO API and NO MCP / NEVER write or claim" wording replaced with the canonical sentence: "GHL Automations have no PUBLIC API or MCP. The Build with AI button is the public path. Skill 44 provides an internal-API build path when the client's Firebase token is present; when absent, Build with AI remains the only path." Files touched: scripts/06-append-memory-rules.sh, scripts/05-update-agents-md.sh, CORE_UPDATES.md, INSTRUCTIONS.md, protocols/conversation-workflows-protocol.md, references/workflow-ai-instructions-standard.md, references/GHL-INBOUND-AND-PLAYBOOKS.md, references/v6.0-source-playbook.md, this CHANGELOG. Historical CHANGELOG entries (pre-v1.6.0) intentionally quote old wording — they are immutable records.
- **Rules 15/16 rewrite:** Rule 15 = Build-Routing Rule (node-type-based routing, TRINITY gate, supersedes "always Step 9.20"). Rule 16 = Convert-and-Flow Build-Path Rule (public path + skill 44 internal path). Marker version bumped v1.4.1 -> v1.5.0 in scripts/06-append-memory-rules.sh so live boxes re-apply via M3 migration.
- **TRINITY wiring:** skill 44 QC calls qc-trinity-registry.sh as a hard gate for conversational builds.
- **Self-test credential alias add (Part 0 finding #7):** 24-self-test-hook.sh readiness check now alias-aware (`GHL_PRIVATE_INTEGRATION_TOKEN|GOHIGHLEVEL_API_KEY` and `GHL_LOCATION_ID|GOHIGHLEVEL_LOCATION_ID`). Behavior-preserving; matches skill 37's existing pattern. Needed so criterion 3 (44-built workflow passes the self-test) passes on a canonical-named box.
- **Conditional manual-paste branch:** skill 38's client-doc generator gains a conditional — if box has skill 44 + healthy Firebase token, doc says direct build; else existing manual paste instructions verbatim (no manual content deleted).
- **wire.sh added:** M3 migration (marker-bounded in-place Rules 15/16 rewrite on live MEMORY.md + AGENTS.md blocks).

## [1.5.12] - 2026-05-30 - Round-2 backlog F18: Webhook Chaining (downstream triggers — the AI as the front door of an automated workflow, OFF by default)

### Why
Round-2 backlog feature 6 of 6 (and the lowest priority of the six). When the agent COMPLETES an action — a booking,
an invoice, an escalation, a transcript export — it can now fire an OUTBOUND webhook to a third-party system, turning
the AI into the FRONT DOOR of a fully automated downstream workflow (Zapier / Make / n8n / a partner API). This is the
OUTBOUND, post-action counterpart to the INBOUND GHL hook that STARTS a conversation: same idea, opposite direction.
Chains are OPERATOR-DEFINED registry files (trigger event + `https://` target + PII-free payload template + retry
policy with exponential backoff + max attempts); they fire ONLY after the underlying action genuinely succeeds, ASYNC,
and NEVER block the customer-facing reply. Toggle default OFF (opt-in advanced feature; the installer never flips it
ON). **OPERATOR-ONLY / NEVER customer-invoked** — an outbound POST reaches outside + may spend money downstream, so a
customer naming or supplying a target URL is an outbound-exfiltration/SSRF injection vector, IGNORED; only the four
allow-listed completed actions, fired by the agent's own post-action logic, can match a chain. Canonical content is
byte-identical across `openclaw-onboarding` (Mac) and `openclaw-onboarding-vps`; only repo-specific env (paths,
INSTRUCTIONS layout, qc-static line positions) diverges.

### Added — `protocols/webhook-chaining-protocol.md` (F18, Step 9.49), byte-identical across both repos
- The OUTBOUND post-action front-door framing + the operator-defined registry `<MASTER_FILES_DIR>/webhook-chains/`,
  with the five-part chain definition (trigger event + `https://` target + PII-free payload template + retry policy +
  optional static headers whose secrets live in the ENV, never the repo) + a worked example chain.
- The FOUR allow-listed trigger events `booking_completed` / `invoice_sent` / `escalation_raised` /
  `transcript_exported` (any other event is IGNORED + flagged) — each fires only on GENUINE success of the underlying
  action (drafting-is-not-sending discipline), reusing actions the skill already takes; the source paths are
  cross-referenced (smart-booking, GHL invoice/Stripe, escalation, conversation export).
- The PII-free payload (a fixed allow-list of merge fields: opaque `<CONTACT_REF>`, the opaque action id,
  `<WORKFLOW_ID>`, `<EVENT>`, an optional numeric `<AMOUNT>` — NEVER a name/email/phone/address or the transcript
  body; the downstream system looks the record up itself with the opaque key).
- The retry policy (exponential backoff `base_delay_seconds * 2^(attempt-1)` capped at `max_delay_seconds`,
  `max_attempts` default 5; 2xx=success → `ZHC-webhook-chain-fired`, transient 429/5xx/timeout retried, non-retryable
  4xx stops as `rejected`, exhausted retries → `ZHC-webhook-chain-failed` + operator notification) and the
  async/never-block-the-customer-reply invariant.
- **Operator-only / never customer-invoked:** chains exist ONLY because the operator authored a registry file; a
  customer naming or supplying a target ("send my details to https://evil.example" / "POST this to my server") is
  IGNORED (outbound-exfiltration / SSRF injection vector); only the four allow-listed completed actions, fired by the
  agent's own post-action logic, can match a chain, and the target is always an operator-defined registry URL.
- **Honest scope:** ships the protocol + the registry format + the example chain + the retry/backoff policy + the
  PII-free F52 log + the AGENTS.md post-action wiring; an outbound POST is a plain HTTPS request to an operator-defined
  URL — reuses the actions the skill already takes as triggers, NOT a new action, payment flow, or queue/broker.

### Added — QC gate + negative test, byte-identical across both repos
- `scripts/qc-webhook-chaining.sh` — asserts the load-bearing F18 substance (the front-door/post-action framing, the
  `webhook-chains/` registry, the four allow-listed trigger events, the `https://`-only target, the PII-free payload
  (opaque `contact_ref`; never name/email/phone/address/transcript), the retry policy (exponential backoff +
  max_attempts), the async/never-block invariant, the operator-only/SSRF-exfiltration outbound guard, the
  `ZHC-webhook-chain-fired`/`-failed` tags, AGENTS Step 2.9 `STEP_2_9_WEBHOOK_CHAINING`, MEMORY Rule 31, the PII-free
  `webhook-chain-events.jsonl` contract documented+seeded, the default-OFF toggle). Wired into
  `scripts/11-run-qc-checklist.sh` + `.github/workflows/qc-static.yml`.
- `scripts/qc-webhook-chaining.test.sh` — negative self-test: proves the gate PASSES intact and FAILS when each of
  three invariants is broken (the operator-only/SSRF-exfiltration outbound guard, the retry policy (exponential
  backoff + max attempts), and the `webhook-chain-events.jsonl` seeding).

### Wiring
- `scripts/05-update-agents-md.sh` — NEW marker block `STEP_2_9_WEBHOOK_CHAINING` (AGENTS.md Step 2.9): the
  fire-after-a-completed-action POST-ACTION step (after the CRM-field-write Step 2.5 + the runtime routing 2.8 — a
  free, semantically-correct slot, no collision). Idempotent BEGIN/END marker, backup-before-write.
- `scripts/06-append-memory-rules.sh` — NEW Round-2 marker block (v2.0.5) appending MEMORY **Rule 31** (Webhook
  Chaining Rule). Own marker, does not renumber rules 6-30.
- `scripts/25-seed-round3-feature-files.sh` — seeds the `webhook-chains/` registry dir (README + the example chain
  `booking-to-zapier.md`) and the empty PII-free `webhook-chain-events.jsonl` sink. Idempotent (never overwrites an
  operator's real chain).
- `scripts/qc-feature-logs.sh` — adds the `webhook-chain-events.jsonl|webhook-chaining-protocol.md|webhook_chain` row
  to the F52 data-contract guard.
- `INSTRUCTIONS.md` — Step 9.49 row + the Phase-5 F52 data-contract table row for `webhook-chain-events.jsonl` + the
  supporting-data-files note now lists the `webhook-chains/` dir.
- `.github/workflows/qc-static.yml` — the `qc-webhook-chaining.sh` gate + its `qc-webhook-chaining.test.sh` negative
  test.

### Notes — honesty
- F18 ships the protocol + the registry + the retry/backoff design + the PII-free log + the post-action AGENTS wiring.
  An outbound POST is a plain HTTPS request to an operator-defined URL — it reuses the actions the skill already takes
  (booking / invoice / escalation / transcript export) as triggers; it does NOT build a new action, payment flow, or
  queue/broker, and the actual outbound delivery runtime (the POST + the backoff loop) executes inside the agent's
  own action path at run time. Default OFF; the operator authors at least one chain and confirms the target URL(s)
  before turning it on.

## [1.5.11] - 2026-05-30 - Round-2 backlog F14: Voice / Phone Integration (STT→brain→TTS over Twilio Media Streams, scaffold + setup wizard + honest live-telephony gap, OFF by default)

### Why
Round-2 backlog feature 5 of 6. The AI now takes and places VOICE CALLS with the SAME conversational brain it uses
for text — the cost-savings pitch vs Convert-and-Flow's paid Voice AI add-on, so clients keep the margin instead of
paying a per-minute platform markup. STT Whisper-large-v3 (via OpenRouter / Groq / local Ollama) → the existing
brain → TTS (ElevenLabs Flash 2.5 or an OSS alternative), bridged over Twilio Voice + Media Streams (SIP/PSTN);
first audio targets < 800ms; a degraded call falls back to the text channel. Voice is a SEPARATE CHANNEL PIPELINE
(its own hook + state machine), NOT a step in the text reply-draft flow. Toggle default OFF (opt-in advanced
feature). **HONEST GAP: live telephony is NOT faked** — it requires operator-provisioned Twilio/STT/TTS
credentials and the actual media-stream bridge is provisioned at setup by the wizard, not pre-baked in the repo.
Canonical content is byte-identical across `openclaw-onboarding` (Mac) and `openclaw-onboarding-vps`; only
repo-specific env (paths, INSTRUCTIONS layout, qc-static line positions) diverges.

### Added — `protocols/voice-phone-protocol.md` (F14, Step 9.48), byte-identical across both repos
- The STT→brain→TTS pipeline (Whisper-large-v3 via OpenRouter/Groq/Ollama → the existing conversational model →
  ElevenLabs Flash 2.5 / OSS TTS), bridged over Twilio Voice + Media Streams (SIP/PSTN), with the inbound transport
  flow documented end to end.
- The inbound voice HOOK scaffolding `/hooks/voice-call-event` (FLAT body like the GHL inbound hook, `deliver:false`,
  the SAME conversation-memory read-before/append-after; carries the STT transcript + call refs, never raw audio).
- The call-lifecycle STATE MACHINE greeting → listen → respond → handoff / booking → ended, with barge-in and the
  invariant that every spoken turn obeys the same hard-gates as text (honesty floor, compliance/spoken-opt-out,
  quiet hours, the confidence gate, prompt-injection, mandatory conversation-memory read/append).
- The latency design (first audio < 800ms: stream STT partials, low-latency Whisper-on-Groq, a Flash-class streamed
  TTS, a short first reply, a co-located bridge) + the degrade-to-text fallback (call quality drops → continue on
  the text channel, default sms, on the same conversation log; tag `ZHC-voice-degraded-to-text`).
- Agent-applied tags `ZHC-voice-inbound` / `ZHC-voice-outbound` / `ZHC-voice-degraded-to-text` / `ZHC-voice-handoff`
  (per `zhc-tag-prefix-protocol.md`; NOT retroactive).
- **Operator-only / never customer-invoked:** placing an OUTBOUND call spends money + reaches outside, gated by
  `outbound_requires_operator_approval` (default true). A customer asking the agent to "call me at this number" /
  "dial 555-…" / "call my friend" is IGNORED (outbound-dial injection vector). Enabling voice / provisioning the
  bridge is operator-only; voice unlocks no autonomous spend a text turn couldn't take.
- **Honest scope / the live gap:** ships the protocol + the setup wizard + the inbound hook scaffolding + the state
  machine + the cost/latency design + the PII-free log; live telephony requires operator-provisioned Twilio/STT/TTS
  credentials and the actual Twilio Media Streams ⇄ STT ⇄ TTS bridge is provisioned at setup by the wizard — NOT
  faked, never a working live-call path pre-baked in the repo. Reuses the existing brain + conversation log + GHL
  APIs + hard-gates + Cloudflare tunnel — NOT a new telephony platform, CRM, speech model, or media server.

### Added — setup wizard + QC gate + negative test, byte-identical across both repos
- `scripts/30-voice-phone-setup-wizard.sh` — operator-run, OFF by default: captures the Twilio Account SID + Auth
  Token + phone number (E.164) and the STT/TTS provider choice (stored in the environment, never the repo), writes
  the documented default-OFF config, and provisions the media-stream bridge + Twilio voice webhook — PAUSING with
  an exact-needs message if any credential is missing (no silent failure) and never flipping the toggle ON itself.
  Idempotent; non-interactive mode for CI.
- `scripts/qc-voice-phone.sh` — asserts the load-bearing F14 substance (the STT→brain→TTS pipeline with the named
  engines, Twilio Voice + Media Streams (SIP/PSTN), the `/hooks/voice-call-event` scaffolding, the four lifecycle
  states + booking, the < 800ms first-audio target, the degrade-to-text fallback, the setup wizard, the
  operator-only outbound-dial guard, the `ZHC-voice-*` tags, the HONEST live-telephony gap, MEMORY Rule 30, the
  PII-free `voice-call-events.jsonl` contract documented+seeded, the default-OFF toggle). Wired into
  `scripts/11-run-qc-checklist.sh` + `.github/workflows/qc-static.yml`.
- `scripts/qc-voice-phone.test.sh` — negative self-test: proves the gate PASSES intact and FAILS when each of three
  invariants is broken (the operator-only/outbound-dial-injection guard, the HONEST live-telephony gap, the
  `voice-call-events.jsonl` seeding).

### Wiring
- `scripts/05-update-agents-md.sh` — NEW marker block `VOICE_PHONE_PIPELINE` documenting the call lifecycle + the
  `/hooks/voice-call-event` hook (voice is a separate channel pipeline, so NO numbered Step 9.x reply-draft block —
  per the feature spec). Idempotent BEGIN/END marker, backup-before-write.
- `scripts/06-append-memory-rules.sh` — NEW Round-2 marker block (v2.0.4) appending MEMORY **Rule 30** (Voice/Phone
  Rule). Own marker, does not renumber rules 6-29.
- `scripts/25-seed-round3-feature-files.sh` — seeds the empty PII-free `voice-call-events.jsonl` sink (F14 has no
  operator-facing data dir; its credentials are captured to env by the setup wizard, never the repo).
- `scripts/qc-feature-logs.sh` — adds the `voice-call-events.jsonl|voice-phone-protocol.md|voice_call` row to the
  F52 data-contract guard.
- `INSTRUCTIONS.md` — Step 9.48 row + the Phase-5 F52 data-contract table row for `voice-call-events.jsonl`.
- `.github/workflows/qc-static.yml` — the `qc-voice-phone.sh` gate + its `qc-voice-phone.test.sh` negative test.

### Notes — honesty
- F14 is a SCAFFOLD + WIZARD + HONEST GAP, not a faked live call. The brain, the protocol, the hook contract, the
  state machine, the F52 log, the tags, and the toggle ship in the repo; the live Twilio Media Streams ⇄ STT ⇄ TTS
  bridge + the provider keys are provisioned by the operator at setup. Until provisioned, no live call is placed or
  answered. Streaming endpointing/voice-activity tuning, barge-in fine-tuning, call-forwarding transfer on handoff,
  and per-region bridge co-location are documented production follow-ups, not fully turnkey in v1.

## [1.5.10] - 2026-05-30 - Round-2 backlog F16: A/B Testing of Reply Variants (deterministic-by-contact split + two-proportion z-test, OFF by default)

### Why
Round-2 backlog feature 4 of 6. When the operator is unsure which reply STYLE converts, the system now runs TWO
Communication-Playbook VARIANTS (`a`/`b`) for a channel on different conversations, measures the OUTCOMES, and
locks in the winner — instead of guessing. The operator defines variant a + b per channel; each inbound
conversation is assigned ONE arm deterministically by contact (a contact stays in one arm); the arm shapes how
the reply is drafted; per-conversation outcomes (booked / converted / sentiment trajectory) are tracked; after a
documented number of conversations a two-proportion z-test declares a winner; the winner auto-promotes
(operator-notified). Toggle default OFF (opt-in advanced feature). Canonical content is byte-identical across
`openclaw-onboarding` (Mac) and `openclaw-onboarding-vps`; only repo-specific env (paths, INSTRUCTIONS layout,
qc-static line positions) diverges.

### Added — `protocols/ab-testing-protocol.md` (F16, Step 9.47), byte-identical across both repos
- The full experiment engine: per-channel experiment definitions (`skill38.ab_testing.experiments.<channel>` +
  the human-readable companion `<MASTER_FILES_DIR>/ab-experiments/<channel>.md`), each naming exactly TWO variants
  (`a`/`b`); each variant is a TONE/STRUCTURE/CTA OVERLAY on the channel Communication Playbook (it shifts only
  HOW the reply READS — never the mandatory SEND, conversation memory, escalation+honesty-floor, or compliance).
- DETERMINISTIC-BY-CONTACT assignment: a stable hash of `experiment_id + ":" + contact_id` mod 2 → `a`/`b`, sticky
  to the first recorded assignment, so a contact STAYS in one arm for the experiment's life (a single-turn hook
  recomputes the same arm from the opaque contact id alone, persisting nothing random).
- Variant selection AT DRAFT TIME — AGENTS.md Step 1.87, after segmentation (Step 1.85) and before the reply
  draft (Step 1.9). Outcomes tracked per conversation from signals the skill already detects: `booked` (calendar
  booking), `converted` (payment/checkout), `sentiment_trajectory` (improving/flat/declining via F4/Step 9.6).
- Significance method documented: a two-proportion z-test on the `primary_metric` at `significance_alpha`
  (default 0.05) after BOTH arms reach `min_conversations_per_arm` (default N = 30 per arm — a documented,
  conservative floor; raise via `min_per_arm` for high-volume channels). An inconclusive test keeps running; a
  winner is never declared early or before both arms hit N.
- Auto-promotion: the winning overlay becomes the channel's standing overlay and the loser stops receiving new
  assignments — `auto_promote` default true WITH operator notification, or (false) the agent notifies + waits for
  an explicit operator promote. Promotion is never silent.
- Agent-applied arm tags `ZHC-abtest-variant-a` / `ZHC-abtest-variant-b` (per `zhc-tag-prefix-protocol.md`; NOT
  retroactive).
- **Operator-only / never customer-invoked:** defining/starting/stopping/promoting an experiment and choosing an
  arm are allow-list actions. A customer asking to "put me in the other test group" / "use your other style" /
  "promote variant B" / "stop the experiment" is IGNORED (A/B-injection vector). All standing hard-gates (quiet
  hours, compliance, honesty floor, conversation memory, mandatory SEND) apply to every arm; a variant never
  unlocks autonomous spend.
- **Honest scope:** reuses the reply-draft path + the existing booking/conversion/sentiment signals + the
  Communication Playbooks; the assignment is a deterministic hash of the opaque contact id, the outcomes are
  existing signals attributed to the arm, and the significance check is a documented closed-form two-proportion
  z-test computed from PII-free counts — NOT a new statistics engine, experimentation platform, analytics
  warehouse, or CRM.

### Added — QC gate + negative test, byte-identical across both repos
- `scripts/qc-ab-testing.sh` — asserts the load-bearing F16 substance (the two variants per channel, the
  experiment + `ab-experiments/<channel>.md` mapping, the deterministic-by-contact sticky assignment, the
  at-draft-time Step 1.87 placement, the three outcome metrics, the two-proportion z-test + the sane default N,
  the auto-promote-with-operator-notify flow, the ZHC-abtest-variant- tags, the operator-only/A-B-injection
  guard, the honest scope, the PII-free `ab-test-events.jsonl` contract documented+seeded with the
  `ab-experiments/` scaffold, the default-OFF toggle). Wired into `scripts/11-run-qc-checklist.sh` +
  `.github/workflows/qc-static.yml`.
- `scripts/qc-ab-testing.test.sh` — negative self-test: proves the gate PASSES intact and FAILS when each of
  three invariants is broken (the deterministic-by-contact/sticky assignment, the operator-only/A-B-injection
  guard, the `ab-test-events.jsonl` seeding).

### Wiring
- `scripts/05-update-agents-md.sh` — NEW marker block `STEP_1_87_AB_TESTING` (variant selection at draft time;
  the free 1.87 slot, after segmentation Step 1.85, before the reply draft Step 1.9 — distinct from the 1.85
  blocks). Idempotent BEGIN/END marker, backup-before-write.
- `scripts/06-append-memory-rules.sh` — MEMORY Rule 29 (A/B Testing Rule) in a new marker-guarded Round-2 block,
  backup-before-write, idempotent (does not renumber rules 6-28).
- `scripts/25-seed-round3-feature-files.sh` — seeds the empty `ab-test-events.jsonl` sink + the `ab-experiments/`
  dir with a universal example experiment (`sms.md`) + the two variant overlays (`sms-variant-a.md` /
  `sms-variant-b.md`) + the dir README (existence-guarded, never overwrites operator files).
- `scripts/qc-feature-logs.sh` — F16 added to the F52 ROWS (the JSONL + PII guard now also covers
  `ab-test-events.jsonl` / `variant_assigned`).
- `INSTRUCTIONS.md` — Step 9.47 row + the Phase-5 F52 data-contract table row for `ab-test-events.jsonl`.

### Version
- skill38 1.5.9 → **1.5.10** (`skill-version.txt`, SKILL.md self-counts: protocols 42→43, scripts 61→63).
- Mac/VPS skill38 sequences are intentionally independent — this bump is the same number on both because both
  were at 1.5.9; the repo-level v10.x versions are untouched.

## [1.5.9] - 2026-05-30 - Round-2 backlog F15: Proactive Outreach Campaigns (scheduled/event-driven outbound, OFF by default)

### Why
Round-2 backlog feature 3 of 6. The agent can now run SCHEDULED OUTBOUND campaigns — re-engage cold leads,
appointment reminders, post-purchase follow-ups, win-back, birthday/anniversary touches — not just reactive
replies. This is the OUTBOUND counterpart to the inbound reply system: it reuses the existing Communication
Playbooks (tone/voice), the existing `openclaw cron` mechanism, the existing GHL tag/contact APIs, and the
existing quiet-hours + compliance hard-gates. Toggle default OFF (opt-in advanced feature — it is the only
part of the conversational system that reaches OUT to people who did not message first). Canonical content is
byte-identical across `openclaw-onboarding` (Mac) and `openclaw-onboarding-vps`; only repo-specific env
(paths, INSTRUCTIONS layout, qc-static line positions) diverges.

### Added — `protocols/proactive-outreach-protocol.md` (F15, Step 9.46), byte-identical across both repos
- The full campaign engine: campaign definitions under `<MASTER_FILES_DIR>/outreach-campaigns/<id>.md`, each
  with six parts — a TRIGGER (time-based `cron` registered as an `openclaw cron` job, OR event-based, e.g. a
  tag applied / appointment booked / purchase completed), a GHL-TAG AUDIENCE filter (`include_tags`/`exclude_tags`,
  opt-out implicit), a MESSAGE template rendered THROUGH the matching Communication Playbook (same brand voice
  as a reactive reply — never a raw blast), a FREQUENCY CAP (anti-fatigue, across ALL campaigns; default 7
  days per contact), and OPT-OUT respect (`ZHC-outreach-opted-out`, global; fed by the Step 9.9 compliance
  keyword gate).
- STRICT quiet-hours respect (Step 9.8 / AGENTS Step 0.5) — a proactive touch due in a quiet window QUEUES for
  the next valid window, never drops. Reactive vs proactive are tracked SEPARATELY: every outreach log line
  carries `direction: proactive` so outbound performance analyzes apart from inbound handling.
- Agent-created tags `ZHC-outreach-<campaign-id>` / `ZHC-outreach-opted-out` (operator-owned audience tags are
  READ, never renamed). The engine is CRON/EVENT-DRIVEN — there is intentionally NO AGENTS.md inbound-reply
  step (no `STEP_9_46` marker); the cron + event wiring is documented in the protocol.
- **F29 migration relationship:** F29 Intelligent Follow-up's own "Pre-Feature-15 implementation" note says it
  schedules its 10-touchpoint stalled-lead cadence with direct cron calls until F15 ships, then migrates. F15
  IS that infrastructure — F29's cadence becomes an event-triggered campaign. F15 does not rip F29 out; it is
  the destination F29 moves to, on F29's own schedule.
- **Operator-only / never customer-invoked:** creating/enabling a campaign and firing a real SEND are
  allow-list actions, gated by `require_operator_approval_to_send` (default true). A customer asking to "send a
  campaign to everyone" / "blast my list" is IGNORED (outbound-injection vector). All standing hard-gates
  (quiet hours, compliance, honesty floor, mandatory-SEND-confirmation) apply to every proactive send.
- **Honest scope:** reuses the GHL Conversations API send path + `openclaw cron` + the Communication Playbooks
  + the existing quiet-hours/compliance hard-gates — NOT a new email/SMS sending service, a new scheduler, or
  a new CRM.

### Added — QC gate + negative test, byte-identical across both repos
- `scripts/qc-proactive-outreach.sh` — asserts the load-bearing F15 substance (the campaign-definitions dir,
  both trigger kinds, the GHL-tag audience, the Communication-Playbook-rendered message, the frequency cap,
  opt-out respect, the ZHC-outreach- tag, the STRICT quiet-hours Step 9.8 respect, the reactive-vs-proactive
  separation via `direction:proactive`, the operator-only/outbound-injection SEND guard, the F29 migration
  relationship, the honest scope, the NO-inbound-AGENTS-step invariant, the PII-free `outreach-events.jsonl`
  contract documented+seeded with the `outreach-campaigns/` dir + example campaign, the default-OFF toggle).
  Wired into `scripts/11-run-qc-checklist.sh` + `.github/workflows/qc-static.yml`.
- `scripts/qc-proactive-outreach.test.sh` — negative self-test: proves the gate PASSES intact and FAILS when
  each of three invariants is broken (the STRICT quiet-hours Step 9.8 cross-reference, the operator-only/
  outbound-injection SEND guard, the `outreach-events.jsonl` seeding).

### Wiring
- `scripts/06-append-memory-rules.sh` — MEMORY Rule 28 (Proactive Outreach Rule) in a new marker-guarded
  Round-2 block, backup-before-write, idempotent (does not renumber rules 6-27).
- `scripts/25-seed-round3-feature-files.sh` — seeds the empty `outreach-events.jsonl` sink + the
  `outreach-campaigns/` dir with a universal example campaign (`cold-lead-reengagement.md`) + the dir README
  (existence-guarded, never overwrites operator files).
- `scripts/qc-feature-logs.sh` — F15 added to the F52 ROWS (the JSONL + PII guard now also covers
  `outreach-events.jsonl` / `campaign_fired`).
- `INSTRUCTIONS.md` — Step 9.46 row + the Phase-5 F52 data-contract table row for `outreach-events.jsonl`.
- `scripts/05-update-agents-md.sh` — intentionally UNCHANGED: F15 is cron/event-driven, not an inbound-reply
  step, so it adds no AGENTS.md marker block (the cron + event hooks are documented in the protocol instead).

### Version
- skill38 1.5.8 → **1.5.9** (`skill-version.txt`, SKILL.md self-counts: protocols 41→42, scripts 59→61).
- Mac/VPS skill38 sequences are intentionally independent — this bump is the same number on both because both
  were at 1.5.8; the repo-level v10.x versions are untouched.

## [1.5.8] - 2026-05-30 - Round-2 backlog F17: Customer Segmentation Awareness (segment-aware tone/priority/escalation, OFF by default)

### Why
Round-2 backlog feature 2 of 6. The agent now recognizes the customer's SEGMENT — `vip` / `prospect` /
`returning` / `at-risk` / `churned` — and adjusts its tone, response priority, and escalation thresholds
accordingly. A 5-year VIP must NOT be treated like a cold Google-ad stranger, and a churned customer trying
to come back must NOT be handled like a brand-new prospect. Segments are defined PER CLIENT from GHL tags the
operator maps; the feature READS that membership and OVERRIDES four existing behavior knobs. Toggle default
OFF (opt-in advanced feature). Canonical content is byte-identical across `openclaw-onboarding` (Mac) and
`openclaw-onboarding-vps`; only repo-specific env (paths, INSTRUCTIONS layout, qc-static line positions) diverges.

### Added — `protocols/customer-segmentation-protocol.md` (F17, Step 9.45), byte-identical across both repos
- The full segmentation protocol: the five canonical segments (vip/prospect/returning/at-risk/churned); the
  per-client GHL tag → segment mapping (`skill38.segmentation.tag_map` + the human-readable companion
  `segment-map.md`); the multi-tag precedence (at-risk > vip > churned > returning > prospect; un-tagged →
  `default_segment`, default `prospect`); the FOUR behavior overrides — response priority, the F4/Step 9.6
  sentiment-escalation threshold (lowered for vip + at-risk), the Communication Playbook tier (white-glove /
  retention / win-back / familiar / standard), and the Step 9.11 confidence threshold (raised for vip +
  at-risk); the BEFORE-reply-draft AGENTS Step 1.85 placement; the `ZHC-segment-` agent-tag prefix; the
  operator-only/never-customer-invoked guard (a customer can never self-promote into a segment); and the
  PII-free F52 log.
- **Honest scope:** the segmentation protocol + the per-client GHL-tag → segment mapping + the four behavior
  overrides + the before-reply-draft placement — a behavior-layer feature that READS segment membership from
  the operator's GHL tags, NOT a new CRM, scoring engine, or lifecycle-automation system. Overrides tune the
  dial but NEVER disable a hard-gate (compliance / quiet hours / honesty floor / mandatory SEND apply to every
  segment; a `vip` never unlocks autonomous spend).

### Added — QC gate + negative test, byte-identical across both repos
- `scripts/qc-segmentation.sh` — asserts the load-bearing F17 substance (the five segments, the tag_map +
  segment-map.md mapping, the multi-tag precedence, all four overrides, the before-reply-draft Step 1.85
  placement, the ZHC-segment- prefix, the operator-only guard, the honest scope, the PII-free
  `segmentation-events.jsonl` contract documented+seeded with the segment-map.md companion, the default-OFF
  toggle). Wired into `scripts/11-run-qc-checklist.sh` + `.github/workflows/qc-static.yml`.
- `scripts/qc-segmentation.test.sh` — negative self-test: proves the gate PASSES intact and FAILS when each of
  three invariants is broken (the multi-tag precedence, the operator-only/self-promotion guard, the
  `segmentation-events.jsonl` seeding).

### Wiring
- `scripts/05-update-agents-md.sh` — new marker block `STEP_1_85_SEGMENTATION_AWARENESS` (segment lookup BEFORE
  the reply draft; coexists with the operator-side Workflow-Builder triggers in the same 1.85 region — different
  marker, different concern).
- `scripts/06-append-memory-rules.sh` — MEMORY Rule 27 (Customer Segmentation Rule) in a new marker-guarded
  Round-2 block, backup-before-write, idempotent (does not renumber rules 6-26).
- `scripts/25-seed-round3-feature-files.sh` — seeds the empty `segmentation-events.jsonl` sink + the
  `segment-map.md` companion (existence-guarded, never overwrites operator files).
- `scripts/qc-feature-logs.sh` — F17 added to the F52 ROWS (the JSONL + PII guard now also covers
  `segmentation-events.jsonl` / `segment_detected`).
- `INSTRUCTIONS.md` — Step 9.45 row + the Phase-5 F52 data-contract table row for `segmentation-events.jsonl`.

### Version
- skill38 1.5.7 → **1.5.8** (`skill-version.txt`, SKILL.md self-counts: protocols 40→41, scripts 57→59).
- Mac/VPS skill38 sequences are intentionally independent — this bump is the same number on both because both
  were at 1.5.7; the repo-level v10.x versions are untouched.

## [1.5.7] - 2026-05-30 - Round-2 backlog F21: Multi-Tenant Agent Isolation (the AGENCY tier, OFF by default)

### Why
Round-2 backlog feature 1 of 6. For an AGENCY running ON TOP of Convert-and-Flow (a client who serves
their OWN end-clients), each end-client now gets an ISOLATED agent context — Client A's data,
conversations, Knowledge Sources, Communication Playbooks, and Conversation Workflows NEVER leak to
Client B's agent. Unlocks the agency-tier sale; an operator running their own multi-tenant agency benefits first.
Toggle default OFF — most clients are single-tenant. Canonical content is byte-identical across
`openclaw-onboarding` (Mac) and `openclaw-onboarding-vps`; only repo-specific env (paths, qc-static line
positions) diverges.

### Added — `protocols/multi-tenant-isolation-protocol.md` (F21, Step 9.44), byte-identical across both repos
- The full isolation protocol: the opaque `tenant_id`; the `hooks.mappings` `tenant_id` routing convention
  (the authoritative "which tenant" source per turn); the per-tenant root `<MASTER_FILES_DIR>/tenants/<tenant_id>/`
  scoping ALL FOUR surfaces (conversation logs, typed Knowledge Sources, Communication Playbooks, Conversation
  Workflows); the per-tenant `tenant.md` config directive (declares the active tenant so the agent loads only
  that tenant's context); tenant resolution order (mapping `tenant_id` → AGENTS.md binding → `tenant.md`, else
  ESCALATE — never guess); per-tenant tag namespacing `ZHC-<tenant_id>-…`; the operator-only/never-customer-invoked
  guard (a customer can never switch tenants — cross-tenant injection vector); and the PII-free F52 log.
- **Honest scope:** the isolation protocol + the scoping/namespacing scheme + the per-tenant config mechanism +
  the `hooks.mappings` `tenant_id` convention — an architecture/protocol feature, NOT a runtime DB migration.

### Added — QC gate + negative test, byte-identical across both repos
- `scripts/qc-multi-tenant.sh` — asserts the load-bearing F21 substance (protocol substance, AGENTS Step 0.8 block,
  MEMORY Rule 26, the PII-free `multi-tenant-events.jsonl` contract documented+seeded, the per-tenant root scaffold,
  the default-OFF toggle). Wired into `scripts/11-run-qc-checklist.sh` + `.github/workflows/qc-static.yml`.
- `scripts/qc-multi-tenant.test.sh` — negative self-test: proves the gate PASSES intact and FAILS when each of
  three invariants is broken (the `hooks.mappings` `tenant_id` convention, the operator-only guard, the
  `multi-tenant-events.jsonl` seeding).

### Changed — wiring (canonical additions byte-identical; host-script scaffolding repo-local)
- `scripts/05-update-agents-md.sh` — new marker block `STEP_0_8_MULTI_TENANT_ISOLATION` (AGENTS.md Step 0.8,
  early context-setup region: resolve the active tenant FIRST so the rest of the turn loads only that tenant's
  scope). Idempotent BEGIN/END marker.
- `scripts/06-append-memory-rules.sh` — appends MEMORY Rule 26 (Multi-Tenant Isolation Rule) in a new
  Round-2 marker block (does NOT renumber rules 6-25), marker-guarded + backup-before-write.
- `scripts/25-seed-round3-feature-files.sh` — seeds the empty `multi-tenant-events.jsonl` sink + scaffolds the
  per-tenant root `tenants/<TENANT_ID>/` (a `tenant.md` directive + the four scoped surfaces + a tenants README),
  existence-guarded (never overwrites operator files).
- `INSTRUCTIONS.md` — new Step 9.44 row + the Phase-5 F52 data-contract row for `multi-tenant-events.jsonl`
  (`event_type` `tenant_routing`, PII-free).

### openclaw.json toggle (documentation-only default — no destructive write)
- `skill38.multi_tenant.enabled` default **false** (OFF); `skill38.multi_tenant.tenants{}` optional per-tenant map.

## [1.5.6] - 2026-05-30 - ZHC Tag-Prefix Rule substance QC fix (byte-identical across both onboarding repos)

### Why
A QC re-score of the "ZHC Tag-Prefix Convention" system rule found four real substance gaps and a
doc-parity gap. This release closes all of them so the rule is self-consistent end-to-end and the gate
genuinely catches a regression. The shared docs/scripts are made **byte-identical** across
`openclaw-onboarding` (Mac) and `openclaw-onboarding-vps`. UNIVERSAL — zero personal/client data.

### Changed — `protocols/intelligent-followup-protocol.md` (F29), byte-identical across both repos
- The three agent-created follow-up tags are now `ZHC-` prefixed (per the rule's single test "did the AGENT
  create this tag?"): `cold-lead-released` → `ZHC-cold-lead-released`, `followup-opted-out` →
  `ZHC-followup-opted-out`, `stalled-sales` → `ZHC-stalled-sales`.
- Wired the 10-touchpoint sequence so each touch applies `ZHC-followup-cadence-1` … `ZHC-followup-cadence-10`
  (added to each T1…T10 heading + the cron pseudocode), so the operator can see exactly how far a contact got.
- Added a "Tags this protocol creates" table at the top documenting the full ZHC- tag set + CREATE-TAG-FIRST.

### Changed — `protocols/sales-best-practices-protocol.md`, byte-identical across both repos
- The same agent-created `stalled-sales` tag is now `ZHC-stalled-sales` (the F29 entry signal also surfaces here).

### Added — `references/tag-migration-notes.md` (the spec-required deliverable), byte-identical across both repos
- New optional, operator-driven migration reference: explains the not-retroactive posture and gives a
  legacy-bare-tag → `ZHC-` mapping table. Cross-linked from `zhc-tag-prefix-protocol.md`. Seeded idempotently
  into the operator's master-files dir (`KnowledgeBases/business/tag-migration-notes.md`) by
  `scripts/25-seed-round3-feature-files.sh` (existence-guarded, never overwrites).

### Changed — `scripts/qc-zhc-tag-prefix.sh` (close the enforcement hole), both repos
- Added `intelligent-followup-protocol.md` to the SCAN_FILES list.
- Added the F29 tags (`ZHC-stalled-sales`, `ZHC-followup-cadence-1`/`-10`, `ZHC-cold-lead-released`,
  `ZHC-followup-opted-out`) to the expected-tags list.
- Added a dedicated check (4b) that fails on a BARE prose-applied follow-up tag in that file (the prose
  "tag contact as `x`" form the create_tag literal parser cannot see). Proven with a negative test.
- CI (`.github/workflows/qc-static.yml`) now plants a bare F29 follow-up tag and asserts the gate fails closed
  (in addition to the existing bare-create_tag negative test).

### Changed — Skill 39 real-estate carve-out contradiction (Mac repo) + journey template (both repos)
- `39-real-estate-playbook/references/real-estate-tags.md` (Mac): the "Supporting (non-ZHC) status tags"
  carve-out is removed; those agent-created lifecycle tags are now `ZHC-` prefixed
  (`ZHC-listing-alert-engaged`, `ZHC-showing-confirmed`, `ZHC-offer-active`, `ZHC-under-contract`,
  `ZHC-closed`, `ZHC-post-close-nurture`, `ZHC-sphere-reactivation`) — no undocumented contradiction left.
- `38-conversational-ai-system/templates/journey-templates/real-estate/journey.md` (both repos): the lifecycle
  tags it applies are `ZHC-` prefixed to match (incl. `ZHC-buyer-lead`/`ZHC-seller-lead`).

### Changed — `protocols/zhc-tag-prefix-protocol.md` doc parity + self-consistency, byte-identical across both repos
- VPS now carries the "NOT retroactive — bot-detection continuity" section so both protocols match (gap 5).
- Added a canonical-name note: the rule's canonical name is the "ZHC Tag-Prefix Rule" (shipped as Rule 20;
  number may vary per client MEMORY.md) — refer to it by name, not number (gap 6; no renumber).
- Documented the F29 tags + the new migration-notes reference in Naming-form examples + Cross-references.

## [1.5.5] - 2026-05-30 - F46 (Conversational CRM Field Write + Create-If-Missing) QC deep-fix + Mac↔VPS reconciliation

### Why
F46 shipped at v1.5.0 but a QC re-score surfaced four gaps, all on or around the F46 logging contract:
a **PII leak** on the VPS side (the canonical JSONL example logged `value_written` — raw customer PII —
directly contradicting the same doc's PII note), a **cross-repo schema divergence** (VPS carried TWO
competing JSONL schemas — a per-event `field_key/field_type/value_written/workflow_id` form AND a combined
`crm_field_write` summary — while Mac shipped ONE clean PII-free schema), the **F35 weekly tune-up not
actually wired** (F46 + AGENTS Step 2.5 + MEMORY Rule 24 all claimed the tune-up reviews auto-created-field
usage, but `weekly-tune-up-protocol.md` had no such review item), and an **inaccurate cross-reference**
(F46 pointed at `references/ghl-api-quick-reference.md` for the discover/write shapes, but that file never
documented the `customFields` endpoints). The Mac `crm-field-write-protocol.md` was the correct, PII-safe
reference; the VPS doc was reconciled toward it. UNIVERSAL — zero personal/client data; `qc-no-personal-data.sh`
passes both repos.

### Fixed — PII leak + single JSONL schema (VPS `protocols/crm-field-write-protocol.md`, reconciled to Mac)
- **Removed the `value_written` raw-customer-value key** from the canonical JSONL example AND deleted the
  competing `crm_field_write` summary schema + its `field_key/field_type/workflow_id` per-event form. The VPS
  protocol now ships Mac's ONE PII-free contract: `event_type` `field_write` / `field_created` /
  `field_write_skipped` with keys `contact_id`, `workflow`, `field_name`, `field_id`, `data_type`,
  `created_now`, `validated`, `reason` (skip), `operator_notified` — collectively the `crm_field_write`
  event family, NEVER the raw value (PII stays in GHL + the conversation log).
- INSTRUCTIONS.md F46 data-contract row + the strategic-roadmap F46 entry on VPS updated to the same event
  family + key fields (dropped the "summary form" reference); the F46 event-type values + key data fields are
  now identical across both repos.

### Added — F46↔F35 wiring made bidirectional (`protocols/weekly-tune-up-protocol.md`, identical both repos)
- New "What it analyzes" item **5. CRM auto-created field usage (F46)**: reads `crm-field-mappings.md` +
  `crm-field-writes-log.jsonl` (field NAME/ID + metadata only, never the raw value) and reports, per
  `ZHC_`-prefixed auto-created field, written-vs-ignored counts (flag unused fields for operator review),
  operator-field collisions (consolidate candidates), and repeated `field_write_skipped` patterns (wrong
  dataType). Closes the loop the F46 protocol + AGENTS Step 2.5 + MEMORY Rule 24 already claimed.

### Added — accurate cross-reference (`references/ghl-api-quick-reference.md`, both repos)
- New **CUSTOM FIELDS (F46)** section documenting the real shapes: `GET /locations/<LOCATION_ID>/customFields`
  (returns `id`/`name`/`fieldKey`/`dataType`) and `POST /locations/<LOCATION_ID>/customFields` (create with
  `name`/`dataType`, `ZHC_` prefix, operator-approved never customer-invoked), Version `2021-07-28`. The F46
  protocol's pointer to this file is now accurate.

### Changed — QC gate tightened (`scripts/qc-feature-logs.sh`, identical both repos)
- Added a **PII guard**: any Round-3 protocol's JSONL example line carrying a raw-value key
  (`value_written` / `"value"` / `field_value` / `raw_value`) is now a hard FAIL. Negative-tested — it
  catches the exact `value_written` leak this release removed.
- `scripts/qc-tools-md-ghl-ref.sh` size budget bumped for the legitimate new CUSTOM FIELDS section (Mac
  CHAR_BUDGET 6500→7000; VPS MAX_LINES 185→195), documented as a deliberate bump (same rationale as prior
  bumps; the line guard remains the real anti-bloat gate).

### Verification
- `bash -n` clean on all changed scripts. `scripts/qc-feature-logs.sh` PASS both repos (incl. new PII guard).
  `scripts/qc-tools-md-ghl-ref.sh` + `qc-no-personal-data.sh` PASS both repos. Full `11-run-qc-checklist.sh`
  introduces ZERO new failures vs clean main (remaining FAILs are environmental — live-install paths absent
  in a bare clone). VPS↔Mac version sequences kept independent (not converged).

## [1.5.4] - 2026-05-30 - F47 (Smart FAQ) + F45 (Geo-Qualification) substance deep-fix (byte-identical across both onboarding repos)

### Why
F47 and F45 shipped at v1.5.0 and were reconciled to a canonical superset at v1.5.3, but several roadmap
(`references/conversational-ai-strategic-roadmap.md`, Features 45 + 47) SUBSTANCE points were thin or
missing in the protocol bodies — and the two protocol files had drifted apart between the Mac and VPS repos.
This release deep-fills every spec gap and makes the two protocol files (and the new QC gate) **byte-identical**
across `openclaw-onboarding` (Mac) and `openclaw-onboarding-vps`. UNIVERSAL — zero personal/client data;
`qc-no-personal-data.sh` passes.

### Changed — `protocols/smart-faq-tool-protocol.md` (F47), made byte-identical across both repos
- Crisp one-line **sentence-vs-sub-flow rule** at the top (one sentence + nothing changes → F47; needs a
  follow-up/calc/quote/mini-flow → F44 `ZHC-faq-detoured`).
- The parallel FAQ-match layer is stated to run **alongside the active workflow AND the F44 always-listening
  layer** (Step 1.42), as the two halves of one layer.
- Restored the explicit **"bigger than one sentence → hand to F44"** section with the `ZHC-faq-detoured` tag
  (this is F44's tag, distinct from F47's `ZHC-faq-answered`).
- `faq-scope.md` reframed as the task's **sales-relevant vs ops-relevant** split, with worked guidance.
- Expanded the **F44(sub-flow) vs F47(sentence)** table (added trigger + reply-shape rows) and the bidirectional
  hand-off (F44 hands simple questions DOWN to F47; F47 hands bigger ones UP to F44).
- Keeps: `KnowledgeBases/business/faqs.md` match, the "By the way, [answer]. Coming back to [topic]…" handoff,
  `ZHC-faq-answered`, `faq-detour-log.jsonl` schema.

### Changed — `protocols/geo-qualification-protocol.md` (F45), made byte-identical across both repos
- Added the **per-product toggle** `skill38.geo_qualification.per_product` (in ADDITION to the global default-OFF
  `enabled`), with the explicit resolution order (global OFF wins → per-product override → fall back to
  `service-areas.md` presence) and a mixed-catalog example (gate an in-person consult, never gate a digital course).
- Added the **exact confirmation question** ("…what ZIP code would the service be at? I don't want to turn you
  away if we actually can help.") and a complete **all-response-branches** table — **here** (in-area, qualify),
  **elsewhere** (confirmed out-of-area, apply mode), **vacation** (do-not-disqualify), **moving** (clarify
  timing, do-not-disqualify if pending/unclear), **no clear engagement** (do-NOT-disqualify; a non-answer is not
  a confirmed out-of-area location).
- The 4 out-of-area modes now name their tags (`decline_plus_referral`/`waitlist`/`full_decline` →
  `ZHC-out-of-service-area`; `limited_remote` → `ZHC-service-area-flexible`).
- Strengthened the JSONL invariant note: the vacation/moving/no-engagement branches never produce an
  `in_area:false` + `ZHC-out-of-service-area` line.
- Keeps: HINTS-only priority (pixel/IP → area code → form address → explicit ask), `service-areas.md`
  (ZIP/county/state/radius per product), the 3 ZHC tags, `geo-qualification-log.jsonl` schema.

### Changed — supporting touchpoints (so the new substance reaches the running agent), applied identically to both repos
- **`scripts/05-update-agents-md.sh`** (`STEP_2_0_GEO_QUALIFICATION` block) — added the per-product toggle,
  the exact confirmation question, and the here/elsewhere/vacation/moving/no-engagement branch summary.
- **`scripts/06-append-memory-rules.sh`** (Rule 23) — added the per-product opt-in and the
  do-not-disqualify-on-vacation/moving/no-answer rule.
- **`scripts/25-seed-round3-feature-files.sh`** (`service-areas.md` seed) — documents the per-product toggle
  and the do-not-disqualify branches.

### Added — QC gate (the "update QC gates to verify these" requirement)
- **`scripts/qc-f45-f47-substance.sh`** (NEW, byte-identical across both repos) — machine-verifies all 41
  F45/F47 substance points listed above from the protocol files alone; fails closed on a stripped point.
  Wired into `scripts/11-run-qc-checklist.sh` AND `.github/workflows/qc-static.yml` (with a per-product-toggle
  negative self-test). `SKILL.md` self-counts bumped (scripts 54→55).

---

## [1.5.3] - 2026-05-30 - Round-3 canonical reconciliation (Mac ↔ VPS): markers, MEMORY rules, QC superset, F52 seeding, roadmap traceability

Aligns this (Mac) onboarding repo's Round-3 artifacts with the sibling VPS onboarding repo so both
ship the SAME canonical Round-3 decisions (only intentional Mac-vs-VPS path/OS differences remain).
Universal — zero personal/client data (`qc-no-personal-data.sh --no-gen` passes). The repo-root
version/CHANGELOG are untouched — this is a per-skill bump (1.5.2 → 1.5.3); the repo-wide bump is the
Cap phase.

### Protocols — merged to the canonical (superset) bodies, all cross-references aligned
- `protocols/smart-faq-protocol.md` → **renamed** `protocols/smart-faq-tool-protocol.md` (the canonical
  filename every other protocol + the F52 gate already point at); all in-repo references rewritten.
- `zhc-tag-prefix-protocol.md` — canonical body (scope table, naming form, why, operator-facing note)
  with the H1 Step 9.42 anchor and the canonical AGENTS marker `SKILL38_ZHC_TAG_PREFIX`.
- `aggression-detection-protocol.md` (F50) — canonical body (turn-order diagram, sensitivity threshold
  table, JSONL schema table) + the dedicated MEMORY Rule 21 section; AGENTS marker corrected to
  `STEP_1_35_AGGRESSION_PRE_ROUTING`; JSONL event_type `aggression_detected`/`tension_detected`.
- `smart-playbook-switching-protocol.md` (F44) — canonical body (F33-vs-F44 table, JSONL schema table)
  + the `skill38.smart_playbook_switching.{enabled,max_interrupt_depth}` toggle block + the dedicated
  MEMORY Rule 22 section + the `interrupt-triggers.md` operator-config reference; AGENTS cross-ref
  corrected to Step 1.42 / `STEP_1_42_INTERRUPTS_AND_FAQ`; JSONL event_type `interrupt_detour`.
- `geo-qualification-protocol.md` (F45) — canonical body (service-areas template, out-of-area mode
  table, JSONL schema table, the `in_area:false ⇒ confirmed_with_customer:true` invariant) + the nested
  `skill38.geo_qualification.enabled` toggle + the MEMORY Rule 23 section + pre-fill-confirmation
  guidance; AGENTS cross-ref corrected to Step 2.0 / `STEP_2_0_GEO_QUALIFICATION`; JSONL event_type
  `geo_qualification`.
- `crm-field-write-protocol.md` (F46) — canonical body (dataType table incl. PHONE/E.164,
  MULTIPLE_OPTIONS, MONETARY; mapping-record example; F35 reads the write-log) + the three JSONL event
  types `field_write`/`field_created`/`field_write_skipped` (the `crm_field_write` family) + the full
  `skill38.crm_field_write.{enabled,create_if_missing,created_field_prefix}` toggle block + the MEMORY
  Rule 24 section; AGENTS cross-ref corrected to Step 2.5 / `STEP_2_5_CRM_FIELD_WRITE`.
- `smart-faq-tool-protocol.md` (F47) — canonical body (faqs.md + faq-scope.md templates, F44-vs-F47
  table, confidence-threshold cross-ref) + the `skill38.smart_faq.enabled` toggle + the MEMORY Rule 25
  section; JSONL event_type `faq_answered`.
- `conversational-safeguards.md` — Safeguard-4 (F50 extension) merged to be self-contained: the inline
  Tier-1/Tier-2/ALL-CAPS bullets + the nested `skill38.aggression_detection.{enabled,sensitivity}`
  toggle path + both log paths.
- `zhc-pixel-protocol.md` + `templates/zhc-pixel/zhc-pixel.template.js` — pixel script-number
  references renumbered 25→26, 26→27, 27→28, 28→29; both are now byte-identical to the sibling repo.

### Scripts — numbering + the F52 seeder
- **NEW `scripts/25-seed-round3-feature-files.sh`** (canonical, from the sibling repo): idempotently
  seeds `KnowledgeBases/sales/service-areas.md` (F45), `KnowledgeBases/business/faqs.md` (F47),
  `crm-field-mappings.md` (F46), the five JSONL sinks, and the F50 human-readable log — never
  overwriting operator content. Documented + wired in INSTRUCTIONS.md.
- Pixel scripts renumbered to the canonical scheme: `25→26-verify-pixel-prerequisites.sh`,
  `26→27-render-pixel-js.sh`, `27→28-configure-pixel-hook.sh`, `28→29-deploy-pixel-cloudflare.sh`;
  the self-test hook renumbered `12→24-self-test-hook.sh`. Every in-repo reference rewritten.

### QC gates — converged to the canonical SUPERSET (wired into 11-run-qc-checklist.sh + CI)
- **NEW `scripts/qc-feature-logs.sh`** — the F52 JSONL data-contract gate (5 logs documented in
  protocol + INSTRUCTIONS.md + seeded by script 25).
- **NEW `scripts/qc-backend-ready.sh`** — the "backend ready to RECEIVE" live gate (exits 3/SKIP with
  no install).
- `qc-config-keys.sh` → **renamed** `scripts/qc-config-schema-safety.sh` (the canonical name), VPS
  content + this repo's checks 4 (pointer-sourcing) and 5 (hardcoded legacy skill path) merged back IN
  so no check is lost.
- `qc-zhc-tag-prefix.sh` — now the UNION of both repos' checks (this repo's MEMORY/AGENTS/example-tag
  checks + the sibling's bare-create-tag-literal parser).
- `qc-no-personal-data.sh` — banned-identifier list expanded to the superset of both repos
  (six additional fleet client first-names) while keeping the `--no-gen`-aware structure.
- `qc-self-test.sh` retargeted to `24-self-test-hook.sh`. CI now wires `qc-feature-logs.sh`,
  `qc-backend-ready.sh`, `qc-self-test.sh`, and the renamed config gate.

### References
- `references/conversational-ai-strategic-roadmap.md` — adopted the v6.0 base and ADDED a Round-3
  section indexing the System Rule + F44/F45/F46/F47/F49/F50/F52 + Skill 39 + Skill 40 + the three
  QC-enforced standards (each expanded from its in-repo protocol/skill file), and a corrected
  Implementation-status footer (39 protocol files).

## [1.5.2] - 2026-05-30 - F49 ZHC Pixel (flagship): per-client private visitor-signal pixel + Pixel Concierge agent + scope-gated Cloudflare deploy

A new flagship capability. Every client gets THEIR OWN private pixel that POSTs anonymous-but-persistent
visitor signals to THEIR OpenClaw via THEIR existing Cloudflare tunnel — NOT a shared collector. Universal
(zero personal/client data — `qc-no-personal-data.sh` + `qc-zhc-pixel.sh` pass). The behavioral protocol goes
through `scripts/05-update-agents-md.sh` marker blocks (AGENTS.md Step 1.45, never inline); the new INSTRUCTIONS
step is 9.43. The repo-root version/CHANGELOG are untouched — this is a per-skill bump (1.5.1 → 1.5.2, rebased
above the concurrent #57 standards wave which had also taken 1.5.1).

### Added — the pixel (browser bundle + generator)
- `templates/zhc-pixel/zhc-pixel.template.js` (~250 lines) — first-party anonymous cookie + persistent
  random `visitor_id` (NOT derived from any personal attribute), a privacy-bounded soft fingerprint (cookie
  survival hint, skipped under DNT), watchers for pages/time/scroll/clicks/return-visits, a buffered batch
  flush every ~5s (sendBeacon on unload), and the public API `window.ZHCPixel.{grantConsent, denyConsent,
  optOut, flush}`. Placeholders `__ZHC_PIXEL_ENDPOINT__` / `__ZHC_PIXEL_SITE_ID__` / `__ZHC_PIXEL_AGENT_ID__`.
- `scripts/27-render-pixel-js.sh` — renders a per-client `<MASTER_FILES_DIR>/pixel/zhc-pixel.js` (their tunnel
  URL / `<SITE_ID>` / `<AGENT_ID>` baked in), guards against any unresolved placeholder leaking, records the
  site id/hostname/agent to the run-state, and prints the one-line `<script>` paste snippet.

### Added — the hook + Pixel Concierge agent
- `scripts/28-configure-pixel-hook.sh` — registers the `pixel-visitor-signal` hooks.mappings entry
  (`deliver:false`, a real model, a bot-gate-FIRST messageTemplate that drops bot traffic with ZERO reasoning,
  appends to the F52 JSONL, evaluates the trigger rules, and NEVER fabricates identity) and a SEPARATE scoped
  **Pixel Concierge** agent (`agents.list` + `hooks.allowedAgentIds` + `hooks.allowedSessionKeyPrefixes`
  `hook:pixel:`). jq-1.7-safe (`.x = (.x // {})`, never `//= ;`); reuses HOOKS_TOKEN (never the gateway token);
  runs `openclaw config validate`. Fail-closed guard on the messageTemplate.
- AGENTS.md `STEP_1_45_PIXEL_CONCIERGE` block (free slot 1.45 — after Step 1.42 interrupts, before Step 1.5/1.7
  routing; no collision) via `scripts/05-update-agents-md.sh` marker block (BLOCK_K).

### Added — behavioral trigger rules (operator-configurable)
- Bot-like → silently DROP with zero model spend (FIRST); pricing-page >3min → chat widget; 4th return to the
  same page → soft outreach; contact-click → preempt with widget; known customer on an account page → no
  engagement; cart abandonment → +1h email; comparison-shopping (3+ service pages) → consultation offer.
  Toggles under `openclaw.json` `skill38.zhc_pixel.{enabled, triggers.*}`.
- Tags (ZHC- prefix, per Step 9.42): `ZHC-pixel-visitor`, `ZHC-pixel-returning-visitor`,
  `ZHC-pixel-high-intent`, `ZHC-pixel-bot-suspected`.
- Custom fields (ZHC_ prefix, per Step 9.40 create-if-missing): `ZHC_first_visit_date` (date),
  `ZHC_total_visits` (number), `ZHC_pages_viewed` (text), `ZHC_high_intent_signal` (text).

### Added — identification (legally compliant; documented possible vs NOT)
- Possible: first-party form linkage (ever-filled-a-form → `visitor_id` tied to a GHL contact forever),
  cross-device (same email = same person), anonymous→known retroactive backfill.
- NOT possible (the agent NEVER fabricates): cold-anonymous name lookup, Gmail/Facebook/social direct lookup,
  IP→person.

### Added — scope-gated Cloudflare deploy + precheck
- `scripts/26-verify-pixel-prerequisites.sh` — inspects the CF token via the API and HALTS if Pages:Edit /
  Workers Scripts:Edit / Workers Routes:Edit are missing (the SAME scopes F52 needs), pointing the operator to
  the token-instructions Google Doc's "Cloudflare Pages/Workers permissions" section. Also confirms an existing
  tunnel + an identified domain. Records `ZHC_PIXEL_SCOPES_OK` in the run-state. Never echoes the token.
- `scripts/29-deploy-pixel-cloudflare.sh` — GATED on `ZHC_PIXEL_SCOPES_OK=1` (or `--force` + operator confirm):
  (a) adds `pixel.<CLIENT_DOMAIN>` to the EXISTING tunnel + proxied CNAME; (b) creates/reuses a CF Pages
  project; (c) deploys the rendered JS via the API; (d) optionally deploys a minimal edge Worker (batching/
  rate-limit, attaches the bearer token server-side) + a Workers Route. No silent failure — exits non-zero with
  the Google-Doc pointer on a missing scope. **Code ships; the live per-client deploy is GATED** (owner directive).

### Added — privacy compliance (non-negotiable, enforced in code)
- GDPR consent deferral (built-in banner or host CMP — no cookie/fingerprint/POST until `grantConsent()`),
  CCPA opt-out (`optOut()` clears state + POSTs `delete_request`), Do-Not-Track hard-stop (DNT=1 → no
  fingerprint, no cookie, nothing sent), data deletion path, privacy-policy reminder. The hooks bearer token is
  NEVER baked into the browser bundle (edge Worker attaches it server-side, or the gateway requires it at ingress).

### Added — F52 data contract
- `<MASTER_FILES_DIR>/pixel-events/YYYY-MM-DD.jsonl` — one JSON object/line; `timestamp` + `event_type`
  (`pageview`/`scroll`/`click`/`page_hidden`/`delete_request`) + the envelope identity + `data`. Schema +
  worked example in `protocols/zhc-pixel-protocol.md` §7 and the INSTRUCTIONS F52 table.

### Added — QC
- `scripts/qc-zhc-pixel.sh` — asserts the hook is registered, the Pixel Concierge protocol is present (AGENTS
  Step 1.45 + protocol doc), the ZHC-/ZHC_ prefixes are used, the privacy controls are documented AND enforced
  in the bundle, the scope precheck names the three scopes + the Google Doc and the deploy is gated, and there
  is no personal/client data. Wired into `scripts/11-run-qc-checklist.sh` + `.github/workflows/qc-static.yml`.
- `scripts/qc-zhc-pixel.test.sh` — negative test: proves the gate PASSES intact and FAILS when each of three
  invariants is broken (hook removed / required ZHC_ field dropped / a required scope name removed). Also in CI.

### Honest MVP/scaffold status
- The live per-client Cloudflare deploy is GATED, not auto-run (requires the CF Pages/Workers scopes).
- The edge Worker is a minimal MVP (production rate-limit/abuse/KV-dedup are follow-ups).
- Server-side identity resolution / cross-device email-collapse is specified for the agent; the nightly
  backfill + `delete_request` purge are light scaffolds (F52 territory), not a hardened DSAR pipeline.

## [1.5.1] - 2026-05-30 - Three QC-enforced standards (mirror the workflow-AI standard's rigor): Communication Playbook Standard (ELEVATED) + GHL Raw Body JSON Standard (NEW) + Notion Client-Doc Standard (NEW)

Three formal, machine-enforced standards, each leading with a hard "MUST INCLUDE ALL OF THE FOLLOWING"
mandatory checklist mirroring `references/workflow-ai-instructions-standard.md`. Skill 38 only. Universal
(zero personal/client data — `qc-no-personal-data.sh` passes). Each standard gets its own QC gate that
FAILS the build if the standard is violated; all three are wired into `scripts/11-run-qc-checklist.sh` +
CI `.github/workflows/qc-static.yml` and were negative-tested (removing a mandatory item FAILS).

### Added / Elevated — the three standards
- **Communication Playbook Standard (ELEVATED in place, NOT duplicated)** —
  `references/communications-playbook-standard.md` now LEADS with a new **Section 0 "EVERY COMMUNICATION
  PLAYBOOK MUST INCLUDE ALL OF THE FOLLOWING"** mandatory checklist (NON-NEGOTIABLE), covering the 8 channels
  (SMS, Email, FB Messenger, FB comments, IG DM, LinkedIn, Live Chat, All-in-One / Chat Widget) and items
  (a)-(i): (a) channel + persona/voice, (b) opening behavior + greeting, (c) conversation goal, (d) mandatory
  SEND rule (Conversations API + mirror inbound channel + thread by contactId + drafting-is-NOT-sending),
  (e) conversation-memory read-before/append-after, (f) escalation/handoff + honesty floor, (g) quiet-hours +
  compliance-keyword respect, (h) ZHC- tag-prefix for programmatic tags, (i) per-channel formatting. The
  existing Sections 1-9 are unchanged (the field-by-field expansion of Section 0).
- **GHL Raw Body JSON Standard (NEW)** — `references/ghl-raw-body-json-standard.md` codifies the FLAT 23-key
  body as THE single standard ("23 is the minimum AND the standard, never fewer, never nested"), with the
  exact 23 keys + a one-line purpose each, the canonical body once, the FLAT / placeholder-free-messageTemplate
  / deliver:false rules, and per-channel variants (only `channel` + `session_key` prefix change). References
  `references/GHL-INBOUND-AND-PLAYBOOKS.md` §0-§2 as source-of-truth + `qc-23-key-bodies.sh` as the enforcer.
- **Notion Client-Doc Standard (NEW)** — `references/notion-client-doc-standard.md` codifies the client
  Quick-Start Notion doc structure with a hard **"EVERY CLIENT NOTION SETUP DOC MUST INCLUDE ALL OF THE
  FOLLOWING, IN THIS ORDER"** list (items 1-12): Quick-Start FIRST → Webhook URL block → Authorization as TWO
  blocks (block1 "Authorization", block2 value-only "Bearer <token>", never combined) → Content-Type split →
  FLAT 23-key Raw Body → tags-first + manual Custom-Webhook fill + "Build-with-AI builds the SHAPE only" +
  post-build VERIFY → "Your Communication Playbooks" (CTA + trigger word + I-Do/You-Do + brainstorm) →
  VPS-vs-Mac → how-it-works LAST → every-value-its-own-block → Telegram delivery → UNIVERSAL.

### Added — three QC gates (each machine-checked, negative-tested, wired into 11-run-qc-checklist.sh + qc-static.yml)
- `scripts/qc-communications-playbook-standard.sh` — asserts the Section 0 mandatory-checklist headline + the
  8 channels + items (a)-(i) + the SKILL.md/INSTRUCTIONS.md pointer.
- `scripts/qc-ghl-raw-body-standard.sh` — asserts the 23-key list + FLAT/placeholder-free/deliver:false rules +
  canonical body; COMPOSES `qc-23-key-bodies.sh` so the standard's own canonical body is proven lint-clean.
- `scripts/qc-notion-doc-standard.sh` — asserts the ordered mandatory list (1-12); COMPOSES
  `qc-reference-sheet.sh --require-manual-fill` so the generator is proven to match the standard's order.

### Changed
- `SKILL.md` + `INSTRUCTIONS.md` (Step 9.20 **Standards:** clause) gain 1-line pointers to all three standards
  (pointer only — standard bodies are never inlined into AGENTS.md/SKILL.md). SKILL.md self-counts updated:
  scripts/ 42 → 45, references/ prose 15 → 17.

## [1.5.0] - 2026-05-30 - Round-3 Queue-A CORE feature wave: ZHC tag-prefix rule + F50 aggression (two-tier, extends safeguards) + F44 smart playbook switching (DETOUR-AND-RETURN interrupts) + F45 geo-qualification (off by default) + F46 CRM field write/create-if-missing + F47 smart FAQ tool + F52 JSONL data contract

A coherent feature wave that ships the Round-3 Queue-A CORE conversational-AI capabilities in one minor
bump. Universal (zero personal/client data — `qc-no-personal-data.sh` passes). Every behavioral feature is a
`protocols/<name>-protocol.md` + a new INSTRUCTIONS Step (9.37-9.42); every AGENTS.md change goes through
`scripts/05-update-agents-md.sh` marker blocks (never inline); MEMORY rules go through
`scripts/06-append-memory-rules.sh` in a NEW marker block (rules 6-19 untouched). All tags the agent creates
programmatically now carry the `ZHC-` prefix.

### Added — ZHC tag-prefix rule (universal)
- `protocols/zhc-tag-prefix-protocol.md` (Step 9.42) — every tag the agent creates PROGRAMMATICALLY (via the
  GHL skill `create_tag`, or the fallback `POST /locations/{id}/tags` — the existing Section D.1 /
  workflow-AI Section-6 mechanism, REUSED not replaced) carries the `ZHC-` prefix. **NOT retroactive**: the
  agent never renames existing or operator-owned tags. The bot-detection tag is created as `ZHC-bot-suspected`
  going forward. Companion: programmatically created CRM custom FIELDS use the `ZHC_` prefix (F46).
- MEMORY **Rule 20** appended in a new `round3-queueA-rules v1.5.0` marker block (rules 21-25 alongside).
- AGENTS.md `SKILL38_ZHC_TAG_PREFIX` behavioral note block.
- D.1 example tags + the workflow-AI Section-6 Add-Tag example audited to the `ZHC-` form
  (`ZHC-pricing-interest`, `ZHC-discovery-scheduled`, `ZHC-quoted`).
- New gate `scripts/qc-zhc-tag-prefix.sh` (wired into `11-run-qc-checklist.sh` + `qc-static.yml`) asserts the
  rule is documented and every programmatic-tag example uses the prefix.

### Added — F50 Aggression Detection (EXTENDS the safeguards family; does NOT rebuild bot-detection)
- `protocols/aggression-detection-protocol.md` (Step 9.37) — a two-tier hostility classifier that runs
  **PRE-routing** (AGENTS.md **Step 1.35** — before workflow match, before any LLM spend, so a hostile message
  doesn't burn a reasoning call). **Tier 1 TENSION** (multiple irritation words / sustained 3+ message streak /
  `!!!`|`???`) → tag `ZHC-tension-detected`, heighten attention, NO reroute. **Tier 2 AGGRESSION**
  (profanity-AT-agent / threats legal-physical-public / ALLCAPS+profanity+direct-address / 3+ signals in one
  message) → tag `ZHC-aggression-detected`, route to the `aggression-handler` workflow, notify the operator.
  **ALL CAPS ALONE does NOT fire.** Reuses existing bot-detection (`ZHC-bot-suspected` going forward) — it is
  EXTENDED via `conversational-safeguards.md` Safeguard 4 + the safeguard-ordering update, not rebuilt.
  Toggle `skill38.aggression_detection.{enabled (default true), sensitivity (lenient|standard|strict, default
  standard)}` with documented thresholds. Logs firings + reasoning to `aggression-detection-log.md` AND emits
  JSONL to `aggression-detection-log.jsonl`.

### Added — F44 Smart Playbook Switching / Always-Listening Interrupts (DETOUR-AND-RETURN, distinct from F33)
- `protocols/smart-playbook-switching-protocol.md` (Step 9.38) — a NEW protocol, **DISTINCT** from Step 9.33
  (`intelligent-routing-protocol.md`, route-and-stay). F44 is **DETOUR-AND-RETURN**: an always-listening layer
  parallel to the active workflow; on a trigger (operator-urgent keywords, FAQ types, compliance redirects,
  F50 aggression, F49 pixel-priority) it **SAVEs** workflow state (step + gathered data + context) → **EXECUTEs**
  the sub-flow → **RETURNs** to the saved step with a soft transition ("Coming back to where we were…"). Max
  **2 levels** deep then escalate. Multiple triggers: highest priority first, queue the rest. Tags
  `ZHC-interrupt-handled` / `ZHC-faq-detoured` / `ZHC-aggression-handled-and-resumed`. AGENTS.md **Step 1.42**.
  Toggle `skill38.smart_playbook_switching.{enabled (default true), max_interrupt_depth (default 2)}`. Logs to
  `interrupt-log.jsonl`.

### Added — F45 Geo-Qualification (OFF by default, signals-are-hints / always-ask)
- `protocols/geo-qualification-protocol.md` (Step 9.39) — per-client toggle
  `skill38.geo_qualification.enabled` (default **FALSE**). Detect location priority pixel/IP (if F49) → phone
  area code → form address → explicit ask. **CRITICAL: signals are HINTS; the agent ALWAYS ASKS to confirm
  before ANY disqualification or out-of-area handling — never disqualify on a guess.** Out-of-area handling is
  operator-configured (decline+referral / limited-remote / waitlist / full decline). Service areas per product
  in `KnowledgeBases/sales/service-areas.md` (ZIP/county/state/radius). Tags `ZHC-out-of-service-area` /
  `ZHC-service-area-confirmed` / `ZHC-service-area-flexible`. AGENTS.md **Step 2.0**. Logs to
  `geo-qualification-log.jsonl`.

### Added — F46 CRM Field Write + Create-If-Missing
- `protocols/crm-field-write-protocol.md` (Step 9.40) — the agent writes ANY GHL contact custom field
  mid-conversation, **type-aware** (text/number/date ISO/dropdown-must-match-option), discovering fields via
  `GET /locations/{locationId}/customFields` and validating before write. **CREATE-IF-MISSING**: if no matching
  field exists, create one via `POST /locations/{locationId}/customFields` with the `ZHC_` prefix (e.g.
  `ZHC_budget_range`), notify the operator, and record the per-workflow mapping in `crm-field-mappings.md`.
  Field creation is an **allow-list action — operator-approved, NEVER customer-invoked**. The weekly tune-up
  (F35) reviews field usage. AGENTS.md **Step 2.5**. Toggle `skill38.crm_field_write.{enabled (default true),
  create_if_missing (default true), created_field_prefix (default "ZHC_")}`. Logs to `crm-field-writes-log.jsonl`.

### Added — F47 Smart FAQ Tool (lightweight sibling of F44: a SENTENCE, not a sub-flow)
- `protocols/smart-faq-tool-protocol.md` (Step 9.41) — a parallel FAQ-match layer matching
  `KnowledgeBases/business/faqs.md`; a confident match yields a brief inline answer then RETURNs to the current
  step in the SAME reply ("By the way, [answer]. Coming back to [topic]…"). Per-workflow scope in
  `conversation-workflows/<id>/faq-scope.md`. Bigger FAQ questions hand off to F44. Tag `ZHC-faq-answered`.
  Wired into AGENTS.md Step 1.42. Toggle `skill38.smart_faq.enabled` (default true). Logs to
  `faq-detour-log.jsonl`.

### Added — F52 data contract (JSONL event logs)
- INSTRUCTIONS.md gains a Phase 5 **data-contract table**: each new feature emits JSONL (one object per line)
  with `timestamp` + `event_type` + event data at the documented `<MASTER_FILES_DIR>/` path
  (`aggression-detection-log.jsonl`, `interrupt-log.jsonl`, `geo-qualification-log.jsonl`,
  `crm-field-writes-log.jsonl`, `faq-detour-log.jsonl`). Each protocol file shows a worked example.

### Changed
- `protocols/conversational-safeguards.md` — EXTENDED with Safeguard 4 (aggression cross-reference) + the
  safeguard-ordering update (PRE-routing aggression scan as step 3a) + the `ZHC-bot-suspected` tag note.
- `scripts/05-update-agents-md.sh` — 5 new marker blocks (`SKILL38_ZHC_TAG_PREFIX`,
  `STEP_1_35_AGGRESSION_PRE_ROUTING`, `STEP_1_42_INTERRUPTS_AND_FAQ`, `STEP_2_0_GEO_QUALIFICATION`,
  `STEP_2_5_CRM_FIELD_WRITE`); idempotent (verified: second run skips all 12 blocks).
- `scripts/06-append-memory-rules.sh` — new `round3-queueA-rules v1.5.0` marker block (rules 20-25); rules
  6-19 untouched; idempotent (verified).
- `scripts/11-run-qc-checklist.sh` — runs `qc-zhc-tag-prefix.sh`; AGENTS.md marker check now includes the 5
  new markers.
- `.github/workflows/qc-static.yml` — adds the ZHC tag-prefix gate + an explicit no-personal-data step.
- `SKILL.md` self-counts updated (protocols 32→38, scripts 36→42 actual, references 16).

### Scope
- Skill 38 ONLY. No repo-root `CHANGELOG.md` / repo-wide version change (reserved for a later cap). No
  personal/client data anywhere (UNIVERSAL). F44 built as a NEW detour-and-return protocol (NOT skipped as
  "present" — it is distinct from F33). F50 EXTENDED the existing safeguards family (bot-detection NOT rebuilt).

## [1.4.21] - 2026-05-30 - Reply on the SAME channel the message arrived on: channel-mirroring + contactId-threaded send-directive (no hardcoded SMS, no conversationId-on-send) + conversation READ endpoints + extended QC gates

Surgical correction to how the conversational agent SENDS its reply, against the authoritative GoHighLevel
official OpenAPI `SendMessageBodyDto`. Universal, zero personal/client data. The send goes through ONE
endpoint (`POST /conversations/messages`), the reply `type` MIRRORS the inbound channel (NOT a hardcoded
SMS), and the send is threaded into the contact's conversation BY `contactId` — `conversationId` is the
READ key only, never a send-body field.

### Changed — the MANDATORY send-directive (channel-mirroring, contactId-threaded)
- `scripts/15-configure-hooks-mappings.sh` canonical SERVER-mapping `messageTemplate` (Layer 1) rewritten:
  "SEND on the SAME channel the message arrived on, do not just draft: read the inbound channel
  (`{{channel}}`) and SEND via the GHL Conversations API — `POST conversations/messages` — with `type` = the
  MIRRORED channel value (SMS→SMS, Email→Email, Facebook→FB, Instagram→IG, WhatsApp→WhatsApp,
  Live Chat→Live_Chat); do NOT hardcode SMS. Send body = `{type:<mirrored>, contactId:{{contact_id}},
  locationId:{{location_id}}, message:<reply>}` (Email also subject+html+emailFrom+emailTo). GHL threads it
  into the contact's conversation BY `contactId`." Adds the READ path for prior thread history
  (GET `conversations/search?locationId=&contactId=` → GET `conversations/{conversationId}/messages`).
  Preserves the existing drafting-is-NOT-sending clause, the do-not-end-turn-until-messageId clause, and the
  READ-before / APPEND-after conversation-log memory steps.
- The installer's FAIL-CLOSED guard now also refuses any hook whose `messageTemplate` lacks
  `SAME channel` / `do NOT hardcode SMS` / `conversations/search`.
- Same correction applied to the two reference SERVER-mapping examples
  (`references/GHL-INBOUND-AND-PLAYBOOKS.md` §4, `references/v6.0-source-playbook.md`).

### Changed — `references/ghl-api-quick-reference.md` (MESSAGING)
- MESSAGING section retitled "MIRROR the inbound channel's `type`"; adds the explicit mirror map and the
  complete `SendMessageBodyDto` enum note (`SMS`/`Email`/`FB`/`IG`/`WhatsApp`/`Live_Chat`; also valid but
  rare `RCS`/`Custom`/`TIKTOK`). GMB is **inbound-only** (not a send type — cannot reply via this endpoint);
  TikTok inbound is workflow-action-only. Send body shows `{type, contactId, locationId, message}` (NEVER
  `conversationId`). Adds a **MESSAGING (READ)** sub-table — GET `/conversations/search` (find the thread by
  contact) + GET `/conversations/<conversationId>/messages` (read history), scope `conversations.readonly`
  (added to the scopes summary). Enum already used the short codes `FB`/`IG`.
- `references/GHL-INBOUND-AND-PLAYBOOKS.md` §7-8 mirrored to the same enum + READ ops + threading note.

### Changed — `references/workflow-ai-instructions-standard.md`
- Adds a concise **Critical Design Pattern** subsection (one endpoint, mirror the inbound channel as the
  reply `type`, send by `contactId` — GHL threads automatically, `conversationId` is read-only for history)
  and a one-line threading note next to the canonical 23-key RAW BODY. **The 23-key body is UNCHANGED** (no
  key changes); the note just records that the thread is preserved by `contactId` on send and `conversationId`
  is looked up only to READ history.

### Changed — QC gates (extended + negative-tested)
- `scripts/qc-send-directive.sh` now also asserts each GHL inbound SERVER `messageTemplate` is
  channel-mirroring (references the mirrored `type` values / "same channel" / "do not hardcode" — not
  SMS-only), threads the send BY `contactId`, and references GET `conversations/search` for reads.
- `scripts/qc-tools-md-ghl-ref.sh` now also asserts the send enum uses the short codes `FB`/`IG` (and FAILS
  on a long-form `Facebook`/`Instagram`/`Webchat` presented as a valid send `type`), FAILS if
  `conversationId` appears as a send-body field, and requires the READ ops (`/conversations/search` +
  `/conversations/<conversationId>/messages`) and the `conversations.readonly` scope. CHAR_BUDGET 6000→6500
  for the legitimate new READ content (120-line guard unchanged).
- Negative-tested: each new assertion was proven to FAIL when its target is regressed (hardcoded SMS,
  dropped search read, long-form `Facebook` send type, `conversationId` in the send body, dropped
  `conversations.readonly` scope, dropped search op).

## [1.4.20] - 2026-05-30 - Preload the CLIENT TOOLS.md with a concise, verified GHL Convert-and-Flow API quick-reference (faster agent replies; core-context request shapes) + installer step + machine-enforced QC gate

The conversational agent now ships with the exact GHL request shapes in its CORE context, so it replies FAST
without digging through the dense full reference at runtime. The block goes into the client **TOOLS.md** (NOT
AGENTS.md) — AGENTS.md = WHAT-TO-DO (rules/behavior); TOOLS.md = WHERE-THINGS-LIVE (tools, endpoints, API
reference), which is where request shapes belong. Universal, zero personal/client data, machine-enforced.

### Added — `references/ghl-api-quick-reference.md` (the canonical, concise block)
- The single source of truth the installer injects verbatim. Grouped: **MESSAGING** (one
  `POST /conversations/messages` endpoint, one row per channel `type` — SMS, Email, FB, IG, Live Chat, Chat
  Widget→Live_Chat, WhatsApp — plus the explicit **All-in-One unified-inbox note** that EVERY channel flows
  through the same endpoint, and the VALID/INVALID `type` enum: GMB is NOT a send type) / **CALENDARS** (list,
  get, create, free-slots) / **APPOINTMENTS** (book, reschedule, cancel) / **INVOICES** (create + send). A
  one-line **Required PIT scopes** summary at the top: `conversations/message.write`, `calendars.readonly`,
  `calendars.write`, `calendars/events.readonly`, `calendars/events.write`, `invoices.write`. Every op carries
  method + full URL + the 3 headers + the JSON body shape (placeholder fields) + the required scope.
- **Verified, not invented.** Shapes confirmed against `references/GHL-INBOUND-AND-PLAYBOOKS.md` §7-9 and
  `29-ghl-convert-and-flow/references/{conversations,calendars,payments}.md`. Notable corrections vs. naive
  seeds: the `Version` header is **`2021-04-15`** (not `2021-07-28`); EVERY send requires **`locationId`**;
  the 6 valid send types are `SMS`/`Email`/`FB`/`IG`/`WhatsApp`/`Live_Chat` (**GMB is rejected** as a send
  type; the website Chat Widget routes through `Live_Chat` — there is no distinct widget type); Email requires
  `subject`/`html`/`emailFrom`/`emailTo`; reschedule = `PUT /calendars/events/appointments/<eventId>`, cancel
  = `DELETE /calendars/events/<eventId>`; free-slots takes epoch **milliseconds**.

### Added — `scripts/24-update-tools-md.sh` (installer step that injects the block into the client TOOLS.md)
- OS-aware target (Darwin `$HOME/clawd/TOOLS.md`, Linux `/data/clawd/TOOLS.md`; override via `$TOOLS_MD` /
  `$OPENCLAW_WORKSPACE`), mirroring `06-append-memory-rules.sh`. **Idempotent** (skips if the
  `SKILL38: GHL_API_QUICK_REFERENCE` marker is already present), **append-only** (never overwrites operator
  content), timestamped backup before any write, creates TOOLS.md if absent. Emits `$PUBLIC_HOSTNAME` ONLY as
  an orientation comment — never a token, never client data. Wired into `INSTRUCTIONS.md` as **Step 7.5**
  (Phase 4) and into the install QC checklist.

### Added — `scripts/qc-tools-md-ghl-ref.sh` (machine-enforced gate, negative-tested)
- FAILS if the block is missing any listed operation (each messaging channel type SMS/Email/FB/IG/Live_Chat —
  **row-anchored** so prose short codes can't mask a dropped channel row — plus calendars list/get/create,
  free-slots, appointment book/reschedule/cancel, send invoice) or any required scope; if it exceeds the
  concise size budget (120 lines / 6000 chars — guards against core-file bloat); or if any personal/client
  identifier appears (real email, real phone, a concrete `contactId`/`locationId`/etc. value, or a real
  client host). Wired into `scripts/11-run-qc-checklist.sh` (gate + a runtime assertion that the block is
  present in the installed client TOOLS.md) and into `.github/workflows/qc-static.yml`. Negative-tested:
  drop-operation, drop-scope, bloat, and three personal-data variants all FAIL; the shipped block PASSes
  (76 lines / 5308 chars; zero personal data).

## v1.4.19 — standardized workflow-AI output + AI backend self-test + UNIVERSAL (zero personal data)

Driven by operator feedback: the workflow-AI output was (a) not standardized (wildly different each run),
(b) too light on the GHL Build-with-AI Custom Webhook instructions, and (c) leaked personal/client data into
a UNIVERSAL skill. The GHL body stays EXACTLY 23 keys, flat (non-negotiable).

- **STANDARDIZATION (REQ 1).** `references/workflow-ai-instructions-standard.md` now opens with a hard
  "EVERY workflow-AI instruction set MUST INCLUDE ALL OF THE FOLLOWING" block (a numbered mandatory
  checklist): (1) workflow name + PUBLISH; (2) Trigger type + sub-option + filters in exact order;
  (3) Settings -> Allow Re-entry = ON (the workflow must re-fire per contact); (4) Custom Webhook — every
  field; (5) Save -> Publish toggle ON -> Save. `scripts/21-generate-client-reference-sheet.sh` and
  `templates/sms-workflow-ai-prompt-template.md` emit this EXACT structure every run, so every client gets
  the SAME experience.
- **EXHAUSTIVE BUILD-WITH-AI WEBHOOK (REQ 2).** The prompt + verification spell out every Custom Webhook
  field with the exact value: EVENT=CUSTOM; METHOD=POST; URL=the exact hook URL; AUTHORIZATION dropdown=None
  (token goes in headers); HEADERS via Add item (Authorization / Bearer <token>, then Content-Type /
  application/json) with the value box ONLY "Bearer <token>" (never the word Authorization); RAW BODY=full
  FLAT 23-key JSON; plus Settings -> Allow Re-entry = ON. Every copyable value is its own code block.
- **CONCISE 60-YEAR-OLD VERIFICATION (REQ 3).** The generator's post-build verification is now dead-simple
  and per-area: one short imperative line per check + the exact value in a COPY CODE BLOCK + a one-line
  "if you do not see it, paste this." Covers, in order: open workflow; Trigger; Allow Re-entry; URL; Headers;
  Raw Body; Save; Publish; Save.
- **CLIENT SELF-TEST SECTION (REQ 4).** The generated client doc now has a "How to test your system" section:
  Contacts -> search your name -> open your record -> text yourself -> reply on your phone -> Automations ->
  open the workflow -> Execution Logs -> every step green (especially the Custom Webhook); red = failure.
- **AI BACKEND SELF-TEST (REQ 5).** New `scripts/24-self-test-hook.sh`: after the agent configures the hook
  and BEFORE the client is told to test, the agent self-tests the full chain by ground truth — readiness
  (hooks.enabled, live mapping deliver:false + model, GHL creds + location in secrets/.env,
  conversational-logs writable, /healthz 200); POST a SYNTHETIC flat 23-key inbound (channel sms, throwaway
  test contact, real Bearer) to its OWN hook URL; verify 200/{ok:true} + configured model with no 401/429 +
  a conversation-log read + a GHL Conversations API 200/201 messageId (temp-contact create/delete + cleanup);
  fix-and-retest on failure; records `selfTestPassed=true`. Standard documented in
  `references/GHL-INBOUND-AND-PLAYBOOKS.md` §15. Statically enforced by new `scripts/qc-self-test.sh` and
  wired as a BLOCKING readiness gate (`selfTestPassed=true`) in `scripts/11-run-qc-checklist.sh`.
- **NOTION DOC HEAVILY ENFORCED (REQ 6).** The install cannot be marked COMPLETE unless the client doc was
  created (Quick Start + 23-key body + split Authorization + playbooks/trigger/I-Do-You-Do + VPS-vs-Mac +
  the How-to-test section) AND delivered via Telegram. The doc-delivery + readiness + self-test gates hard
  -block completion (non-zero exit).
- **UNIVERSAL — ALL PERSONAL/CLIENT DATA STRIPPED (REQ 7).** Every real personal/client identifier across
  the entire skill tree was genericized — real names (operator + live clients), real hostnames, the
  operator's chat id, operator email/domain, and worked-example business names -> generic placeholders
  (<CLIENT_BUSINESS_NAME>, <PUBLIC_HOSTNAME>, <HOOKS_TOKEN>, <LOCATION_ID>, <OPERATOR_TELEGRAM_CHAT_ID>,
  "the operator", "your setup admin", "a live client"). The hardcoded operator Telegram chat id default was
  removed from `scripts/21` + `scripts/22`. New gate `scripts/qc-no-personal-data.sh` FAILS if any banned
  identifier appears in the skill or in generated output (scans the tree + drives the generator offline).
- `38-conversational-ai-system/skill-version.txt`: 1.4.18 -> 1.4.19.

## [1.4.18] - 2026-05-30 - Audit + prune (phantom-file QC bug, stale counts/line-numbers, stale version pin) + new VPS-vs-Mac install-considerations section (client doc + reference doc + QC gate)

Full audit + prune of Skill 38, plus a new prominent "⚙️ Things to consider when installing: VPS (Hostinger
Docker) vs Mac mini" section in the generated client doc, mirrored to a reference doc and machine-enforced.
The 23-key FLAT GHL RAW BODY rule, the split Authorization (Key/Value) blocks, the Quick-Start-first ordering,
the "Your Communication Playbooks" section (trigger word + "I Do / You Do" + brainstorm), and the mandatory
Telegram doc-delivery are all preserved intact.

### Fixed — `scripts/11-run-qc-checklist.sh` referenced THREE files that do not ship (phantom-file FAILs)
- The install QC checklist hard-listed `protocols/qc-protocol.md`, `protocols/handoff-protocol.md`, and
  `templates/journey-template.md` as required files — **none of which exist in the skill** — so a clean
  install reported 3 spurious `[FAIL] MISSING:` lines every time. Replaced them with the files that actually
  ship: the skill's own `protocols/pre-handoff-qc-protocol.md` + the repo-root governing `../QC-PROTOCOL.md`
  (SKIP, not FAIL, when the skill is installed standalone outside the onboarding repo); and, for journey
  templates, `templates/journey-templates/registry.md` + a count assertion that all 8 per-vertical `journey.md`
  files are present (coach + 7 verticals). Also added `templates/client-reference-sheet-template.md` to the
  template existence check. The file-existence section now reports all PASS on a clean checkout.

### Fixed — stale counts + line-numbers + a stale version pin (audit/prune)
- **`SKILL.md`** — removed the stale **`(v5.14)`** version pin from the H1 title (the skill ships at 1.4.18 and
  the source playbook was long-since renamed to `v6.0-source-playbook.md`; the title pinned a number that
  contradicts both). The lineage references to the operator's v5.14 playbook work elsewhere are accurate history and
  are kept.
- **`INSTALL.md`** — corrected the install-script counts that contradicted `SKILL.md`: "24 numbered scripts …
  (27 `.sh` files total)" → **25 numbered install scripts** (`00`–`23`, noting the TWO `22-` scripts:
  `22-init-run-manifest.sh` + `22-notify-client-doc.sh`) and **36 `.sh` files total**, with the full list of
  the 10 QC linters/fixtures (the old text named only 2). Removed the stale **"8,797-line"** source-playbook
  line count (the file is now ~9,490 lines — replaced with a version-agnostic description).
- **`INSTRUCTIONS.md`** — removed the same stale **"8,797 lines"** source-playbook line count.

### Added — "⚙️ Things to consider when installing: VPS (Hostinger Docker) vs Mac mini" section
- **`scripts/21-generate-client-reference-sheet.sh`** — emits a new section into the generated client doc,
  placed AFTER the Quick Start + "Your Communication Playbooks" and BEFORE the deep Full Reference. It covers
  BOTH install targets — **VPS:** env vars in host `/docker/<project>/.env`; apply with
  `docker compose up -d --force-recreate` (plain `restart` ignores `env_file`); GHL/provider creds ALSO in
  container `/data/.openclaw/secrets/.env`; the `/hostinger/server.mjs` wrapper rewrites `hooks.token` to
  `hooks_${OPENCLAW_GATEWAY_TOKEN}` each boot UNLESS `OPENCLAW_HOOKS_TOKEN` is set in the host `.env`; the
  gateway port is often NOT 18789 (read `PORT` / `openclaw gateway status`); public hook via a `cloudflared`
  tunnel (PM2 + `pm2 save`) OR an existing Traefik `*.hstgr.cloud` route; `apt` is a brew shim (use
  `/data/linuxbrew/.linuxbrew/bin/brew`). **Mac mini:** PROVIDER keys MUST go in the `openclaw.json` TOP-LEVEL
  `env` block (the launchd service-env file does NOT carry them; `~/.openclaw/.env` alone is insufficient); GHL
  creds still in `~/.openclaw/secrets/.env`; restart via `launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway`;
  remote access via Cloudflare tunnel + Access service token (`zsh -lc` wrap); public hook via
  `sudo cloudflared service install <token>`. **Common to both:** FLAT 23-key body; conversational-logs
  node-owned; GHL creds in `secrets/.env`; `deliver:false`; Ollama Cloud `:cloud` models hard-cap `maxTokens`
  at 65536.
- **`references/vps-vs-mac-install-considerations.md` (NEW)** — the authoritative reference doc the generated
  section mirrors (references/=14 → **15**). Cross-linked from `references/communications-playbook-standard.md`
  §7 (a new MANDATORY, machine-enforced checklist item).

### Changed — QC enforces the VPS-vs-Mac section
- **`scripts/qc-reference-sheet.sh --require-manual-fill`** now ALSO FAILS the build when the generated doc is
  missing the VPS-vs-Mac section or any of its load-bearing points: the section heading; the VPS
  `/docker/<project>/.env` + `docker compose up -d --force-recreate` (plain-restart-ignores-env_file) +
  container `/data/.openclaw/secrets/.env` + `hooks.token` rewrite-on-boot + `OPENCLAW_HOOKS_TOKEN` points; the
  Mac `openclaw.json` TOP-LEVEL `env` block + `launchctl kickstart` points; the COMMON FLAT-23-key /
  node-owned-logs / `deliver:false` / 65536 points; and the AFTER-Quick-Start / BEFORE-Full-Reference ordering.
  **Negative-tested:** removing any one of these from the generated sheet FAILs the gate (six negative cases,
  all FAIL as expected); the positive (full) sheet PASSes.

### QC
- All Skill 38 CI gates pass locally: `qc-23-key-bodies.sh` (23 bodies, 0 failures), `qc-trinity-registry.test.sh`,
  `qc-send-directive.sh`, `qc-conversation-memory.sh`, `qc-playbook-doc.test.sh`, `qc-reference-sheet.sh`
  (default + `--require-manual-fill`), `qc-config-keys.sh`, `qc-notify-client-doc.sh`. `11-run-qc-checklist.sh`
  file-existence section reports all PASS on a clean checkout. Six negative tests confirm the new VPS-vs-Mac
  enforcement FAILs when its content is removed.

### Version
- **`skill-version.txt`** 1.4.17 → 1.4.18; **`SKILL.md`** SELF-COUNTS re-verified (protocols/=32, scripts/=36,
  references/=**15** — added `references/vps-vs-mac-install-considerations.md`, journeys=8). No repo-tracked
  (8-location) version file changed, so the repo version is unaffected and `scripts/bump-version.sh` is not run
  (matches the v1.4.15 / v1.4.16 / v1.4.17 precedent).

## [1.4.17] - 2026-05-29 - New-playbook creation experience: trigger word + "I Do / You Do" + brainstorm prep (agent behavior + client doc + QC)

Adds the AGENT BEHAVIOR and client-facing content for how a NEW communication playbook gets created.
Three pieces, in the agent-behavior files AND the generated client doc, and machine-enforced.

### Added — agent behavior in the playbook-CREATION flow (Step 9.20 Part 3)
- **`protocols/conversation-workflows-protocol.md`** — extended the Part 3 brainstorm flow (not duplicated):
  - **§I.1a (NEW) — personal TRIGGER WORD.** On the client's FIRST playbook build, the agent OFFERS to set a
    personal trigger word, explained like **"Alexa" / "Hey Siri"** (e.g. *"Playbook time!"*): asks for it,
    confirms it back, and **REMEMBERS it** — persists it to the client's `USER.md` AND the
    `conversation-workflows/registry.md` `trigger-word` header so future builds recognize it (never co-mingle
    clients). The standard *"Help me build a [purpose] playbook"* phrasing always still works.
  - **§I.1b (NEW) — the "I Do / You Do" process.** When a build starts the agent presents the 8-step
    YOU/AI-DO overview so the client knows responsibilities + that a good playbook takes **~15-30 minutes**
    (trigger → AI brainstorms a few Qs → YOU answer → AI drafts → YOU review → AI finalizes/stores/wires the
    Workflow AI prompt → AI wires actions → YOU approve, go live).
  - **§I.2 — brainstorm "what to think about".** The agent's JOB is to BRAINSTORM the PERFECT playbook; gives
    the client the things to think about — **goal** (book a call / recover a sale / get a review / FAQ),
    **who it's for**, the **channel(s)**, the **offer/hook**, the **tone/brand voice**, **timing & follow-up
    cadence**, and the **"win" action** (booked / replied / tagged / purchased) — with the reassurance
    *"if you're unsure, that's what I'm here to brainstorm."*
  - **§J + the 3-PART build table + Part 3 prose** — AGENTS.md Step 1.85 now also recognizes the stored
    trigger word; the table/prose reflect the trigger-word offer + "I Do / You Do".
- **`INSTRUCTIONS.md`** (Step 9.20 row) + **`references/communications-playbook-standard.md`** §6 (Build
  sequence) + **`references/workflow-ai-instructions-standard.md`** §7 — mirror the trigger-word offer, the
  "I Do / You Do" process, and the brainstorm "what to think about" so every entry point describes them the
  same way; they point at the canonical detail in §I.1a/§I.1b/§I.2.

### Added — client-facing explanation in the generated client doc
- **`scripts/21-generate-client-reference-sheet.sh`** — inside the "🗂️ Your Communication Playbooks" section
  (after Quick Start, before the deep reference), three new friendly sub-sections with emojis:
  **🔑 a personal trigger word** ("Alexa"/"Hey Siri" style, e.g. "Playbook time!"); **🤝 the "I Do / You Do"
  process ⏱️** (who does what + a good playbook takes ~15-30 minutes); and **🧠 what to think about** before
  you ask (goal/audience/channel/offer/tone/timing/win action + *"if you're unsure, that's exactly what your
  AI is here to brainstorm"*). FLAT 23-key body + Quick-Start-first ordering kept intact.

### Changed — QC enforces all three in the client doc
- **`scripts/qc-reference-sheet.sh --require-manual-fill`** now ALSO FAILS the build when the generated doc is
  missing: the **trigger-word concept** + its **"Alexa"/"Hey Siri" analogy**; the **"I Do / You Do" process**
  + the **~15-30 minute** expectation; and the brainstorm **"what to think about"** prep + its reassurance.
  Negative-tested: removing any one of these from the generated sheet FAILs the gate (six negative cases,
  all FAIL as expected); the positive (full) sheet PASSes.

### QC
- All Skill 38 CI gates pass locally: `qc-23-key-bodies.sh`, `qc-trinity-registry.test.sh`,
  `qc-send-directive.sh`, `qc-conversation-memory.sh`, `qc-playbook-doc.test.sh`, `qc-reference-sheet.sh`
  (default + `--require-manual-fill`), `qc-config-keys.sh`, `qc-notify-client-doc.sh`. Six negative tests
  confirm the new enforcement checks FAIL when their content is removed.

### Version
- **`skill-version.txt`** 1.4.16 → 1.4.17; **`SKILL.md`** SELF-COUNTS re-verified (protocols/=32, scripts/=36,
  references/=14, journeys=8 — unchanged; this release edited existing files only, added no new files) +
  the `qc-reference-sheet.sh` bullet updated. No repo-tracked (8-location) version file changed, so the repo
  version is unaffected and `scripts/bump-version.sh` is not run (matches the v1.4.15 / v1.4.16 precedent).

## [1.4.16] - 2026-05-29 - Authorization two-block bug fix + enriched "build another playbook" section + tightened QC

Two client-doc fixes driven by live pain, mirrored into the standards, and machine-enforced.

### Fixed — the Authorization header was emitted as ONE combined copy block (the second-block bug)
- **`templates/client-reference-sheet-template.md`** (rendered into the generated client doc by
  `scripts/21-generate-client-reference-sheet.sh` as the "Full Reference" body) emitted the Authorization
  header as a SINGLE combined copy block — `Authorization: Bearer <HOOKS_TOKEN>` — so a client copying that
  block pasted the whole string (including the repeated word `Authorization`) into the GHL header **Value**
  box. A GHL custom-webhook header has a separate **Key** box and **Value** box, so it is now TWO separate
  copy blocks: block 1 is exactly **`Authorization`** (paste into the **Key**/header-name box) and block 2 is
  exactly **`Bearer <HOOKS_TOKEN>`** (paste into the **Value** box) — the value block NO LONGER repeats
  `Authorization:`. Content-Type was verified already split correctly (block 1 `Content-Type`, block 2
  `application/json`). The click-by-click step (Row 1 / Row 2) was updated to match. The Quick-Start LEAD
  block in script 21 was already correct; this fix closes the gap in the template-rendered Full Reference.
  - **Before:** ` ```\nAuthorization: Bearer <HOOKS_TOKEN>\n``` `  →  **After:** ` ```\nAuthorization\n``` ` (Key) + ` ```\nBearer <HOOKS_TOKEN>\n``` ` (Value)

### Changed — enriched the "Your Communication Playbooks" section (teach the client to build MORE)
- **`scripts/21-generate-client-reference-sheet.sh`** — the "🗂️ Your Communication Playbooks" section
  (after the Quick Start, before the deep reference) now teaches the client how the AI helps them build
  ADDITIONAL communication playbooks (friendlier tone, more emojis 💬🚀🛠️📅🏷️✅): a **"Want another
  communication playbook? Just ask me!"** CTA with a concrete copyable example (*"Help me build a missed-call
  follow-up playbook"*) plus more examples (appointment-reminder, lead-nurture, review-request); a walkthrough
  of WHAT THE AI WILL DO — (1) brainstorm it with you using known business context (not a 50-question
  interrogation), (2) create the playbook, (3) store it (master-files `conversation-workflows/` folder,
  mirrored to Notion), (4) help create the matching **Workflow AI prompt** wired to **YOUR** Convert and Flow
  (GoHighLevel) account, (5) and that the AI can take real actions in Convert and Flow on the client's
  behalf — **create tags 🏷️, update the calendar 📅, create/book appointments 🗓️**; and the explicit
  *"You have an AI that is connected to your Convert and Flow account and can do these things for you — just
  ask."* Kept the FLAT 23-key body + Quick-Start-first ordering intact.

### Changed — tightened the QC gate to enforce both
- **`scripts/qc-reference-sheet.sh --require-manual-fill`** now ALSO FAILS the build when: (a) any copy line is
  a combined `Authorization: Bearer <token>` block (the second block must be ONLY `Bearer <token>` and must
  NOT repeat the word `Authorization`); and (b) the doc is missing the enriched playbook facts — the
  "just ask me / Help me build a [purpose] playbook" CTA, at least one of the additional examples
  (missed-call/appointment-reminder/lead-nurture/review-request), the where-stored fact (`conversation-workflows/`
  + mirrored to Notion), the matching Workflow AI prompt wired to the client's Convert and Flow account, the
  Convert-and-Flow abilities (create **tags**, update the **calendar**, create/book **appointments**), and the
  explicit "connected to your Convert and Flow account … just ask" statement. Both new checks are
  negative-tested (a doc with a combined Authorization block FAILs; a doc missing the playbook content FAILs).

### Standards mirrored
- **`references/communications-playbook-standard.md`** §7 now mandates the Authorization Key/Value two-block
  split (value = ONLY `Bearer <token>`, never combined) + the same split for Content-Type; §9 now spells out
  the enriched "Want another communication playbook? Just ask me!" section (CTA + examples + brainstorm/create/
  store/Workflow-AI-prompt walkthrough + Convert-and-Flow abilities + the explicit "connected … just ask"
  statement) and the gate that enforces it.
- **`references/workflow-ai-instructions-standard.md`** §3 reinforces that the Authorization **Value** box is
  ONLY `Bearer <HOOKS_TOKEN>` (not `Authorization: Bearer …`) and the Content-Type Value box is ONLY
  `application/json`; §7 mirrors the enriched playbook section.

### QC
- All Skill 38 CI gates pass locally: `qc-23-key-bodies.sh`, `qc-trinity-registry.test.sh`,
  `qc-send-directive.sh`, `qc-conversation-memory.sh`, `qc-playbook-doc.test.sh`, `qc-reference-sheet.sh`
  (default + `--require-manual-fill`), `qc-config-keys.sh`, `qc-notify-client-doc.sh`. Negative tests
  confirm the two new enforcement checks FAIL when their content is missing.

### Version
- **`skill-version.txt`** 1.4.15 → 1.4.16; **`SKILL.md`** SELF-COUNTS re-verified (protocols/=32, scripts/=36,
  references/=14, journeys=8 — unchanged; no new files added). No repo-tracked (8-location) version file
  changed, so the repo version is unaffected and `scripts/bump-version.sh` is not run (matches the v1.4.15
  precedent).

## [1.4.15] - 2026-05-29 - Mandatory Telegram doc-delivery + Communication Playbooks location section + readiness gates

Three belt-and-suspenders + machine-enforced hardenings driven by repeated live-client pain.

### Added — MANDATORY Telegram delivery of the client doc (un-skippable, state-gated)
- **`scripts/22-notify-client-doc.sh` (NEW).** Every client gets their setup-doc LINK via Telegram, NO
  MATTER WHAT — the install is not complete until the client has been SENT their Quick-Start / Notion doc
  link via `openclaw message send --channel telegram`. The script (a) resolves the client's chat id —
  `CLIENT_TELEGRAM_CHAT_ID` first, else DISCOVERS it by GREPPING THE TRANSCRIPTS `agents/*/sessions/*.jsonl`
  for the four shapes (`"chat":{"id":<n>`, `telegram:direct:<n>`, `"chatId":<n>`, `"from":{"id":<n>`) and
  taking the most-frequent NON-operator id (a hard-won live-client lesson — `sessions.json` keys alone miss paired
  chats); (b) sends the link via the gateway (never `api.telegram.org`); (c) on no chat FLAGS LOUDLY
  (stderr banner + `clientDocDelivered=false` in the run-state) and exits non-zero — NEVER silently skips.
  On success it records `clientDocDelivered=true` + chat id + link.
- **`scripts/qc-notify-client-doc.sh` (NEW QC gate).** Statically asserts 22-notify-client-doc.sh exists,
  parses, sends via the gateway (not curl to telegram), discovers from the transcripts (all four shapes,
  most-frequent non-operator), LOUD-fails on no chat, and is wired into INSTRUCTIONS.md + the v6.0 playbook
  + the comms standard. Wired into `scripts/11-run-qc-checklist.sh` AND CI `.github/workflows/qc-static.yml`.
- **Binding install step.** INSTRUCTIONS.md gains **Step 6.5**; `references/v6.0-source-playbook.md` gains a
  binding "Step 6.5 — deliver the doc LINK to the client via Telegram" section + Checkpoint D / Step 11 QC
  items; `references/communications-playbook-standard.md` gains §8. The pre-handoff checklist
  (`11-run-qc-checklist.sh`) asserts the run-state field `clientDocDelivered=true` at runtime.

### Added — DOC + BACKEND READINESS as completion gates (testing happens only after BOTH pass)
- **`scripts/11-run-qc-checklist.sh`** gains a backend-ready check: a live `hooks.mappings` entry (matched
  to `HOOK_NAME`, else any agent mapping) with `deliver:false` and a working `model`, AND `/healthz`
  returns 200 (public `PUBLIC_HOSTNAME` or localhost). The doc-structure side is already gated
  (`qc-reference-sheet.sh --require-manual-fill` + `qc-23-key-bodies.sh` assert the FLAT 23-key body +
  Quick-Start). v6.0 playbook Step 11 gains a "DOC + BACKEND READINESS" block: never test inbound before
  the doc is delivered AND the backend is confirmed receiving.

### Added — "YOUR COMMUNICATION PLAYBOOKS" section in the generated client doc
- **`scripts/21-generate-client-reference-sheet.sh`** now emits a prominent **"🗂️ Your Communication
  Playbooks"** section AFTER the Quick Start and BEFORE the deep Full Reference. It answers the client's
  first-test question — "where are my workflows / communication playbooks?" — with: WHERE they live (the
  `conversation-workflows/` master-files folder + human-facing copies in Notion → Google Docs → text), and
  in BIG BOLD **"⭐ Want a NEW communications playbook? Start here:"** the steps (just tell your AI
  "help me build a [purpose] playbook"; it brainstorms with you and builds all 3 parts — the workflow-AI
  prompt + the conversation playbook + the GHL automation — then documents + registers it).
- **`scripts/qc-reference-sheet.sh --require-manual-fill`** now also FAILS unless the generated doc carries
  the "Communication Playbooks" heading, the `conversation-workflows` + Notion location facts, the "Want a
  NEW communications playbook" CTA, the "help me build a [purpose] playbook" instruction, the brainstorm
  explanation, and the 3-part trinity note — and unless the section sits after Quick Start and before the
  deep reference. Negative-tested. Standardized in `communications-playbook-standard.md` §9 +
  `workflow-ai-instructions-standard.md` §7.

### Version
- **`skill-version.txt`** 1.4.14 → 1.4.15; **`SKILL.md`** SELF-COUNTS re-verified (protocols/=32,
  scripts/=34 → **36** (+`22-notify-client-doc.sh`, +`qc-notify-client-doc.sh`), references/=14, journeys=8)
  + the scripts bullet updated (eight QC linters now). No repo-tracked (8-location) version file changed, so
  the repo version is unaffected and `scripts/bump-version.sh` is not run.

## [1.4.14] - 2026-05-29 - Bulletproof Quick-Start + workflow-AI (where-to-paste, tag-first, post-build verify)

Belt-and-suspenders hardening of the client reference-sheet generator, the workflow-AI standard/templates,
and the QC gates — driven by live client pain (a live client + a live client). The reference sheet now leads with an
actionable Quick Start AND keeps a full explanation, splits every copyable value into its own copy block,
teaches create-the-tag-FIRST, and adds a post-build verification that catches the blank-tag trigger bug.

### Changed — `scripts/21-generate-client-reference-sheet.sh` (the generated reference sheet, now bulletproof)
- **Quick Start FIRST, then full explanation (BOTH).** The sheet now LEADS with a section literally named
  **"🚀 Quick Start"** (the actionable copy-paste items, in order) and then, AFTER it, a complete
  **"📖 Full Reference & Explanation"** section (how the inbound pipe works, what each piece is, and
  troubleshooting). Quick Start does NOT replace the explanation — both are present.
- **Every copyable value gets its OWN fenced code block (its own copy button).** The Authorization header is
  now TWO separate code blocks — one containing exactly `Authorization` (the key) and one containing exactly
  `Bearer <token>` (the value), NEVER combined. The Content-Type header is likewise split into `Content-Type`
  and `application/json`. (50+ clients copy each field individually.) The Webhook URL and the FLAT 23-key
  Raw Body JSON each keep their own block.
- **Create-tags-FIRST (new Section 0).** If the workflow uses any tag (a trigger/If-Else filter or an
  Add-Tag action), the sheet directs the client to CREATE the tag(s) FIRST (via the agent's GHL skill, or in
  GHL **Settings → Tags**) so the filter references a REAL existing tag — and tells them WHERE to check
  (Settings → Tags) and WHAT they should see.
- **Post-build VERIFICATION (new Section 5).** After Build-with-AI runs, the sheet walks the client through
  three checks, each stating WHERE to go, WHAT they should SEE, and WHAT to put if missing/wrong:
  TRIGGER (incl. the **blank/non-existent-tag-in-a-"does not contain"-filter** bug from a live client), CUSTOM
  WEBHOOK (Method=POST, URL, both headers, all 23 Raw-Body keys — Build-with-AI does NOT fill these), and
  PUBLISH (Published, not Draft).
- **Manual Custom-Webhook fill (Section 4)** now names each GHL UI box precisely (Method dropdown / URL box /
  HEADERS → Add item → Key box + Value box, twice / Content-Type field / RAW BODY box).

### Changed — workflow-AI standard + templates (explicit + bulletproof)
- **`references/workflow-ai-instructions-standard.md`** — Custom-Webhook field-by-field now names the exact
  GHL UI boxes (Method dropdown, URL box, Key/Value boxes via "Add item", RAW BODY box); Section 6 rewritten
  as **"create the tag FIRST, then use it"** with the agent path + the client path (where to check:
  Settings → Tags, what they should see); Section 4 verification gains the trigger tag-existence check
  (WHERE/SEE/PUT) calling out the blank-tag "does not contain" bug.
- **`templates/sms-workflow-ai-prompt-template.md`** — manual-fill steps name the precise GHL boxes.
- **`templates/workflow-verification-checklist-template.md`** — Trigger section gains a tag-EXISTS check
  (cross-check Settings → Tags; the blank-tag "does not contain" bug + the fix).

### Changed — QC enforcement (machine-enforced, BASH)
- **`scripts/qc-reference-sheet.sh --require-manual-fill`** now additionally FAILS unless the generated sheet
  contains: a literal **"🚀 Quick Start"** section, a complete explanation/reference section AFTER it, the
  SEPARATE `Authorization` key code block + `Bearer <token>` value code block (detected inside fences via
  awk), the create-tags-FIRST instruction + a `Settings → Tags` pointer, and the POST-BUILD verification
  section (trigger tag-existence + Published-not-Draft) — on top of the existing Bearer/```json/hook-URL/
  manual-fill/lead-order checks. Negative-tested: removing any marker fails the gate.
- **`.github/workflows/qc-static.yml`** — the manual-fill CI step is updated to describe + enforce the
  bulletproof set (it already invoked `--require-manual-fill`).

### Version
- **`skill-version.txt`** 1.4.13 → 1.4.14; **`SKILL.md`** SELF-COUNTS note re-verified (protocols/=32,
  scripts/=34, references/=14, journeys=8 — unchanged, no files added/removed) + qc-reference-sheet ship line
  updated. No repo-tracked version file changed, so the repo version (8-location) is unaffected and
  `scripts/bump-version.sh` is not run.

## [1.4.13] - 2026-05-29 - v1.4.11 install-script bug fixes (config-validity) + MANDATORY manual Custom-Webhook fill instructions

Two classes of fix, both verified against a live openclaw 2026.5.27 box.

### Fixed — install-script bugs that broke/degraded fresh installs (PART A)
- **`scripts/15-configure-hooks-mappings.sh` (Model Wizard + hooks merge):**
  - No longer writes `agents.defaults.async` / `agents.defaults.batch` — those keys are REJECTED by the
    2026.5.27 `.strict()` schema, so `openclaw config validate` FAILED on a fresh install. The real-time
    model is the only one written to `openclaw.json` (on the main agent's `agents.list[].model`); the
    async + batch tier CHOICES are persisted to `SECRETS_ENV_FILE` as `ASYNC_MODEL`/`BATCH_MODEL` (read by
    `04-register-crons.sh`).
  - The hooks merge `jq` no longer uses the top-level `.hooks //= {};` form, which jq 1.7+ REJECTS
    (`syntax error, unexpected ';'`). Rewritten to the valid `.hooks = (.hooks // {}) | …` form (same
    semantics). The corrected SERVER `messageTemplate` (read-before + append-after + mandatory SEND) is
    preserved and still validates clean.
  - The inline `system-health-heartbeat` cron is now registered via `openclaw cron add` (not the invalid
    `cron.jobs` JSON block).
- **`scripts/04-register-crons.sh`:** rewritten to register all 5 crons via `openclaw cron add` (gateway
  cron store), idempotent by name via `openclaw cron list`. The legacy `cron.jobs` JSON config block does
  NOT validate on 2026.5.27 — the script no longer touches `openclaw.json` at all. Reads `BATCH_MODEL` from
  `SECRETS_ENV_FILE` (set by the Model Wizard).
- **`scripts/02-create-knowledgebases.sh` + `scripts/03-create-journey-templates.sh`:** stop `source`-ing
  the master-files POINTER file. The pointer holds a bare PATH (a directory), so `. <pointer>` errored
  "Is a directory". Now READ it with `head -n1` into `MASTER_FILES_DIR`.
- **`scripts/12-scaffold-channel-playbooks.sh`:** resolves the skill root DYNAMICALLY from the script's own
  location instead of hardcoding the legacy `~/clawd/skills/38-openclaw-cloudflare-tunnel` path (which no
  longer exists). Same dynamic-resolution fix applied to `scripts/11-run-qc-checklist.sh`, whose expected
  cron-name list was also corrected to the names `04-register-crons.sh` actually registers.

### Added
- **`scripts/qc-config-keys.sh`** (pure BASH) — new machine-enforced QC gate that scans `scripts/*.sh` and
  FAILs (exit 1) if any install script would invalidate the 2026.5.27 config or trip the known install
  bugs: `agents.defaults.async/.batch` writes, a `cron.jobs` JSON config block, the jq-1.7-invalid
  `//= … ;` form, sourcing the master-files pointer, or a hardcoded legacy skill path. Wired into
  `scripts/11-run-qc-checklist.sh` and CI `.github/workflows/qc-static.yml`.
- **`scripts/qc-reference-sheet.sh --require-manual-fill`** — new flag that additionally enforces the
  manual Custom-Webhook fill instructions and the lead-with-values ordering on the generated reference
  sheet (CI runs both default + `--require-manual-fill`).

### Fixed — MANDATORY manual Custom-Webhook fill (PART B)
GHL's "Build with AI" only builds the workflow SHAPE (the trigger + an EMPTY Custom Webhook action); it
does NOT reliably populate the URL, the Authorization/Bearer header, the Content-Type header, or the Raw
Body JSON. The client MUST open the Custom Webhook action and paste those values by hand. Made explicit and
mandatory:
- **`scripts/21-generate-client-reference-sheet.sh`** — the generated reference sheet now LEADS with the
  copy-paste values in this exact order: (1) Webhook URL, (2) Authorization/Bearer token (revealed real
  value), (3) Raw Body JSON (fenced `json`, flat 23-key), (4) the manual Custom-Webhook fill steps
  ("Build with AI will not fill it — do it yourself"), (5) the Workflow-AI prompt. All explanation/
  reference now follows AFTER those values.
- **`references/workflow-ai-instructions-standard.md`**, **`templates/sms-workflow-ai-prompt-template.md`**,
  **`templates/workflow-verification-checklist-template.md`** — each gains a prominent "AFTER Build-with-AI
  runs, you MUST open the Custom Webhook action and MANUALLY enter Method/URL/Headers/Raw Body, then
  Save + Publish — Build with AI will NOT fill these for you; verify every field is non-empty before
  publishing" section.
- **`references/communications-playbook-standard.md`** — notes the manual-fill step is MANDATORY in every
  client doc, machine-enforced by `qc-reference-sheet.sh --require-manual-fill`.

### Changed
- **`.github/workflows/qc-static.yml`** — adds CI steps for `qc-config-keys.sh` and for
  `qc-reference-sheet.sh --require-manual-fill`.
- **`SKILL.md`** — self-counts updated (scripts 33 → 34; new `qc-config-keys.sh`); QC-linter description
  extended.

## [1.4.12] - 2026-05-29 - client reference sheet MUST include the bearer token + a copyable GHL Raw Body JSON (machine-enforced)

Root cause fixed: on a live client, the generated Client Reference Sheet
(`scripts/21-generate-client-reference-sheet.sh`) had NEITHER the hooks Bearer token NOR the GHL Custom
Webhook Raw Body as a copyable ` ```json ` fenced code block. The client opened their reference doc and
the token was simply missing, and there was no JSON to copy into GHL's Build-with-AI — which stranded the
client. The reference sheet's content came entirely from the template wrapper, where the bearer token
appeared only inside `[code block, copy button]` pseudo-markers (not a real fence) and the per-channel
Raw Body JSONs lived in a separate Part 3 documentation section, not in the reference sheet body. The
sheet MUST contain both, ALWAYS — now enforced, not left to the template.

### Fixed
- **`scripts/21-generate-client-reference-sheet.sh`** now APPENDS two authoritative, always-present
  sections to the rendered reference sheet (so they survive regardless of template wrapping):
  - **Authorization Header / Bearer Token** — resolves the real `hooks.token` in priority order
    `HOOKS_TOKEN` → `OPENCLAW_HOOKS_TOKEN` → `hooks.token` read from `openclaw.json`
    (`$OPENCLAW_CONFIG`, `~/.openclaw/openclaw.json`, `/data/.openclaw/openclaw.json`), and renders it as
    `Authorization: Bearer <token>` inside a real fenced code block. If the token cannot be resolved it
    emits a clearly-marked `REPLACE_ME__…` PLACEHOLDER and WARNs to stderr (never silently omits it).
  - **GHL Custom Webhook — Raw Body** — the canonical FLAT 23-key body as a copyable ` ```json ` fenced
    code block, plus the Method (POST), the hook URL (`https://<host>/hooks/<id>`), and Content-Type
    (`application/json`) as copyable code blocks. Body stays placeholder-free in `messageTemplate`, not
    nested, not stripped below 23 keys.

### Added
- **`scripts/qc-reference-sheet.sh`** (pure BASH, mirrors the other `qc-*.sh`) — new machine-enforced QC
  gate. Default mode drives `21-generate-client-reference-sheet.sh` in an offline sandbox (strips
  `openclaw` from PATH → Layer-3 markdown, no network/Telegram) and FAILs (exit 1) if the rendered sheet
  lacks the word `Bearer`, a line-anchored ` ```json ` fence, or a hook URL; `--sheet FILE` statically
  checks an existing sheet; exit 2 (never a blind PASS) if no sheet can be produced/located. BASH (not
  Python) so it respects qc-static's ban on claude-/anthropic strings in `.py` under 22/23.

### Changed
- **`scripts/11-run-qc-checklist.sh`** — wires `qc-reference-sheet.sh` in as a mechanical gate (and adds
  it to the script-existence list).
- **`.github/workflows/qc-static.yml`** — new CI step "Skill 38 client reference sheet copy-paste
  artifacts" runs `qc-reference-sheet.sh` on every push/PR so a template/script regression that drops the
  bearer token or the copyable Raw Body JSON fails the build.
- **`references/communications-playbook-standard.md`** — new section documenting that the bearer token +
  copyable Raw Body JSON are MANDATORY in every client reference sheet, machine-enforced by
  `qc-reference-sheet.sh`.

## [1.4.11] - 2026-05-29 - enforce the per-playbook human-facing doc deliverable (Notion → Google Docs → text) so a created playbook never ships without a client-facing reference

Root cause fixed: when a communications/conversation playbook is created (the base install creates the FIRST
one — appointment booking, F.7), the agent is ALSO supposed to create a human-facing copy of that playbook in
the CLIENT's OWN account, in the fallback order (1) the client's Notion, (2) if no Notion → Google Docs, (3) if
neither → a plain-text doc the client can access. On a recent client this step was SKIPPED — the agent
scaffolded the playbook files locally and reported the install "clean" but never created the client's Notion
doc, leaving the customer stranded with no human-facing reference of what was set up. The cause: the Notion-doc
deliverable was PROSE in the standard (`references/communications-playbook-standard.md` §4 + the protocol §I.3
step 4), not an ENFORCED gate, so the agent skipped it. "AUTOMATIC NEXT STEP" prose is NOT enforcement — it
needs a recorded state field + a verify/resume gate + a QC check, exactly like the send-directive
(`qc-send-directive.sh`) and conversation-memory (`qc-conversation-memory.sh`) gates. The per-playbook
human-facing doc is now enforced the same way, in four changes, not left optional.

### The canonical rule
Every conversation playbook registered in `<MASTER_FILES_DIR>/conversation-workflows/registry.md` MUST carry a
recorded human-facing doc — a Notion URL, a Google Docs URL, or a `.md`/`.txt` path the client can reach —
created in the client's OWN account in the fallback order Notion → Google Docs → plain-text. The reference is
recorded in the registry's new `Doc (Notion/Docs/text)` column (TABLE form) or a `[doc: …]` tail (legacy BULLET
form) and in the Run Manifest. Never co-mingle clients — always the client's own workspace.

### Added
- **CHANGE 3 — machine-enforced QC gate.** New `scripts/qc-playbook-doc.sh` (bash; mirrors
  `qc-trinity-registry.sh`) reads the client's installed `conversation-workflows/registry.md` and FAILs
  (exit 1) any registered playbook (table OR bullet form) whose doc reference is empty / `n/a` / a placeholder,
  PASSes (exit 0) when every playbook has a recorded Notion/Docs/text doc, exits 2 (NOT a blind PASS) when no
  playbooks exist, and exits 3 when no conversation-workflows folder is found. It rejects the Layer-2 playbook
  file itself and the reserved companion files (`--build-with-ai-prompt.md`, `--verification-checklist.md`,
  `--ghl-side.md`) as "the doc," and catches an on-disk-but-unregistered playbook (no doc can be recorded for
  it). New `scripts/qc-playbook-doc.test.sh` proves all of this with fixtures. Wired into BOTH
  `scripts/11-run-qc-checklist.sh` (pre-handoff QC; SKIP on exit 2/3 = nothing installed yet, FAIL on exit 1)
  AND `.github/workflows/qc-static.yml` (CI runs the fixture test on every push/PR). BASH (with an inline
  python core) so it does not trip the qc-static ban on claude-/anthropic strings in `.py` under Skills 22/23.

### Changed
- **CHANGE 1 — binding, state-gated install step.** `INSTRUCTIONS.md` (Step 9.20 + Phase 7),
  `references/v6.0-source-playbook.md` F.7 (the base SMS automation that creates the first playbook) + §H Run
  Manifest, and `protocols/conversation-workflows-protocol.md` §F/§H/§I.3/§J now state that the install is NOT
  complete until a created playbook's human-facing doc has been created in the client's account (Notion →
  Google Docs → plain-text) and its URL/path recorded in the registry + Run Manifest. An incomplete doc is
  retried (verify/resume), not silently skipped.
- **CHANGE 2 — installer action.** `scripts/09-install-conversation-workflows.sh` now adds the new
  `Doc (Notion/Docs/text)` column to the registry it scaffolds, and runs a verify/resume loop over every
  on-disk playbook: for any playbook with no recorded doc it creates one (Notion subpage under the client's
  designated parent page via `NOTION_API_KEY` + `NOTION_PARENT_PAGE_ID`/`NOTION_PARENT_SEARCH` → Google Docs
  via the Google Workspace helper → a plain-text `.md` in `<MASTER_FILES_DIR>/playbook-docs/`), records the
  resulting URL/path back into the registry, and emits a clear operator-facing line stating WHERE the doc was
  created (or which fallback was used). Idempotent — a playbook that already has a recorded doc is left as-is.
- **CHANGE 4 — standards.** `references/communications-playbook-standard.md` adds "human-facing doc created in
  client's account (Notion → Google Docs → text), URL recorded" to the §2 MUST-APPEAR checklist and strengthens
  §4 from prose to a MANDATORY, machine-enforced deliverable (naming `qc-playbook-doc.sh`).
  `protocols/conversation-workflows-protocol.md` §F adds the doc column to the registry table and marks it
  mandatory + gated; `references/GHL-INBOUND-AND-PLAYBOOKS.md` §10 (first appointment-booking playbook) marks
  the doc step mandatory + gated. SKILL.md self-counts updated (scripts 30 → 32, four QC linters → five).

## [1.4.10] - 2026-05-29 - enforce conversation-memory (read-before + append-after) so single-turn hook agents never lose context

Root cause fixed: GHL inbound hook sessions are SINGLE-TURN / stateless (confirmed: every hook run is a fresh
session, user-turns = 1). The agent has NO in-session memory of prior messages — its ONLY memory of a contact
across messages is that contact's per-contact conversation log file
(`<MASTER_FILES_DIR>/conversational-logs/<contact_id>__<name>.md`), which it must READ before replying and
APPEND to after sending. On a live client this broke because the canonical `messageTemplate` was
"simplified" during testing and lost the read/append steps, the `conversational-logs/` dir was never created
(and was root-owned, so even when present the `node` gateway could not write it), and AGENTS.md had no memory
protocol — so the agent had ZERO memory ("didn't remember anything" mid-booking). The send-directive gate
(`qc-send-directive.sh`) did NOT catch it because it only checks the SEND instruction. Conversation-memory is
now enforced exactly like the send-directive, in four layers, not left optional.

### The canonical conversation-memory steps
Every GHL inbound SERVER `messageTemplate` must contain all of: the **conversational-logs** path, a
**READ**-before-replying instruction (recover prior conversation + any in-progress booking/topic and CONTINUE
it; if missing, treat as new), and an **APPEND**-after-sending instruction (append inbound + reply to the log,
create if missing). The directive lives ONLY on the SERVER mapping — the in-GHL-body `messageTemplate` stays
placeholder-free per the 23-key rule.

### Added
- **LAYER 4 — machine-enforced QC gate.** New `scripts/qc-conversation-memory.sh` (bash; mirrors
  `qc-send-directive.sh`) scans every GHL INBOUND SERVER-mapping `messageTemplate` (installer canonical
  template + reference examples) and FAILS (exit non-zero) if any is missing the conversational-logs path, the
  READ-before instruction, or the APPEND-after instruction. It SKIPS the placeholder-free 23-key bodies and
  non-GHL (Stripe/Shopify/n8n) mappings, and exits 2 (FAIL) if zero GHL inbound server templates are found so
  it never goes silently blind. Wired into BOTH `scripts/11-run-qc-checklist.sh` (pre-handoff QC, plus a new
  conversational-logs dir presence+writability check) AND `.github/workflows/qc-static.yml` (CI on every push/PR).

### Changed
- **CHANGE 1 — installer canonical template (fail-closed).** `scripts/15-configure-hooks-mappings.sh` now
  writes the read-before + append-after conversation-log steps into the GHL inbound mapping's `messageTemplate`
  (alongside the send-directive), and a second fail-closed guard refuses to write the config (exit 9) if the
  built template is missing the conversational-logs path, the read element, or the append element — it is no
  longer possible to install a GHL hook whose server `messageTemplate` lacks the read/append steps.
- **CHANGE 2 — installer creates + chowns the conversational-logs dir.** `scripts/09-install-conversation-workflows.sh`
  (Step 9 "Set up conversation log system") now `mkdir -p`s `<MASTER_FILES_DIR>/conversational-logs/` and chowns
  it to the runtime/gateway user (`node` on VPS/Docker, the login user on Mac/Homebrew; override via
  `OPENCLAW_RUNTIME_USER`) so the agent can actually write logs — runs before the registry early-exit and warns
  loudly with the exact `sudo chown` command if it cannot.
- **CHANGE 3 — AGENTS.md Conversation Memory Protocol base rule.** `scripts/05-update-agents-md.sh` now emits a
  concise standing rule (new `CONVERSATION_MEMORY_PROTOCOL` marker block): GHL inbound is single-turn; memory =
  per-contact logs; READ before replying + CONTINUE in-progress topics + APPEND after sending; a reply that
  ignores or fails to update the log is a failure. Pointer-style, no bloat.
- **v6.0 playbook + authoritative spec.** `references/v6.0-source-playbook.md` (canonical server mapping, Step 3)
  and `references/GHL-INBOUND-AND-PLAYBOOKS.md` (canonical mapping §4 + new §4b) now carry the read-before +
  append-after steps in their canonical server `messageTemplate`, replacing the simplified template that lacked
  them. 23-key rule, FLAT bodies, no nesting, no `\n`, placeholder-free in-body templates all preserved.
- **Standards.** `references/communications-playbook-standard.md` (new conversation-memory must-appear item) and
  `references/workflow-ai-instructions-standard.md` (new machine-enforced conversation-memory callout) now state
  the read/append steps are mandatory on the SERVER mapping and how to verify them (`scripts/qc-conversation-memory.sh`).

### Version
- `skill-version.txt` → `1.4.10`; SKILL.md self-counts updated (scripts/ 29 → 30; four QC linters).

## [1.4.9] - 2026-05-29 - enforce the mandatory GHL send-directive (drafting != sending) for every client

Root cause fixed: if a GHL inbound hook's SERVER-mapping `messageTemplate` does not EXPLICITLY order the
agent to SEND its reply via the GHL Conversations API, the model drafts a reply and STOPS — drafting is NOT
sending — and the customer receives nothing. This is now enforced in three layers, not left optional.

### The canonical send-directive
The exact mandatory clause every GHL inbound SERVER `messageTemplate` must contain (all elements required:
the word SEND, the GHL Conversations API, the contact id, the channel, the drafting-is-NOT-sending clause,
and "do not end your turn until a messageId/conversationId is returned"):

> MANDATORY — SEND, do not just draft: You MUST send your reply by calling the GHL Conversations API (POST
> conversations/messages) for contact {{contact_id}} on the {{channel}} channel, per TOOLS.md. Composing or
> drafting a reply is NOT sending — the customer receives nothing unless you make the API call. Do NOT end
> your turn until the send call returns a messageId/conversationId.

### Added
- **LAYER 3 — machine-enforced QC gate.** New `scripts/qc-send-directive.sh` scans every GHL INBOUND
  SERVER-mapping `messageTemplate` (the installer's canonical template + the reference examples) and FAILS
  (exit non-zero) if any is missing the send-directive elements (SEND, GHL Conversations API /
  `conversations/messages`, drafting-is-not-sending, do-not-end-turn-until-messageId). It deliberately
  SKIPS the placeholder-free object-A 23-key bodies (those stay placeholder-free per the 23-key rule — the
  send-directive lives ONLY on the server mapping) and non-GHL server mappings (Stripe/Shopify/n8n). Exits
  2 (FAIL) if zero GHL inbound server templates are found so it never goes silently blind. Wired into BOTH
  `scripts/11-run-qc-checklist.sh` (pre-handoff QC) AND `.github/workflows/qc-static.yml` (CI on every push/PR).

### Changed
- **LAYER 1 — installer canonical template (fail-closed).** `scripts/15-configure-hooks-mappings.sh` now
  writes the strengthened send-directive into the GHL inbound mapping's `messageTemplate`, and a fail-closed
  guard refuses to write the config (exit 8) if the built template is missing any send-directive element —
  it is no longer possible to install a GHL hook whose server `messageTemplate` lacks the send-directive.
  The in-GHL-body messageTemplate (the Step-4 E2E FLAT body) stays placeholder-free per the 23-key rule.
- **LAYER 2 — AGENTS.md standing base rule (belt-and-suspenders).** `scripts/05-update-agents-md.sh` now
  emits a concise standing rule (new `GHL_SEND_MANDATORY` marker block) + strengthens Step 7C "Send the
  reply": for ANY GHL inbound hook, SENDING via the GHL Conversations API is MANDATORY; a drafted-but-unsent
  reply is a failure; always confirm a messageId/conversationId before ending the turn.
- **v6.0 playbook + authoritative spec.** `references/v6.0-source-playbook.md` (canonical server mapping,
  Step 3) and `references/GHL-INBOUND-AND-PLAYBOOKS.md` §4 (the doc that wins) now show the strengthened
  send-directive in their canonical server `messageTemplate`, replacing the softer "reply via the GHL
  Conversations API per TOOLS.md" phrasing. 23-key rule, FLAT bodies, no nesting, no `\n`, placeholder-free
  in-body templates all preserved.
- **Standards + checklist.** `references/communications-playbook-standard.md` (GHL reply mechanism item),
  `references/workflow-ai-instructions-standard.md` (new machine-enforced send-directive callout), and
  `templates/workflow-verification-checklist-template.md` (new Webhook-Action verification item) now state
  the send-directive is mandatory on the SERVER mapping and how to verify it (`scripts/qc-send-directive.sh`).

### Version
- `skill-version.txt` → `1.4.9`; SKILL.md self-counts updated (scripts/ 28 → 29; three QC linters).

## [1.4.8] - 2026-05-29 - add Skill 23 cross-reference (role/SOP gate + comms hand-off) to v6.0 playbook

### Added
- **Skill 23 cross-reference in the v6.0 playbook.** Added a "🔗 How this connects to the AI Workforce
  Blueprint (Skill 23)" section to `references/v6.0-source-playbook.md`, placed right after the TRINITY /
  standards area (Communications Playbook Standard + Workflow-AI Instructions Standard). It documents the two
  enforced connections between Skill 38 and Skill 23: the **Role Library + SOP Library auto-pull gate**
  (build-state field + verify/resume gate; multiple Six Sigma DMAIC SOPs per role under
  `departments/<dept>/sops/`, never empty/stub) and the **comms-automation hand-off** (Skill 23 → Skill 38
  via a `commsAutomationStatus` state field + resume self-ping when a Communications/Sales/Customer-Support
  department is built), and ties both back to THE TRINITY keeping every workflow, playbook, and prompt in
  lockstep.

### Version
- `skill-version.txt` → `1.4.8`.

## [1.4.7] - 2026-05-29 - Close the 2 QC gaps: TRINITY registry format match + 23-key linter now covers the v6.0 playbook

Two QC checks that *looked* like they were enforcing invariants were silently no-op'ing on real inputs.
Both are now genuinely enforced, with fixture coverage.

### Fixed
- **GAP 1 — TRINITY registry format mismatch.** `scripts/qc-trinity-registry.sh` parsed the
  conversation-workflows registry only as a markdown TABLE, but `scripts/09-install-conversation-workflows.sh`
  documents/emits the active-workflow list as BULLETS (`- <id>: <desc>`). On a real installed (bullet)
  registry the table-only parser saw ZERO rows, so registry-vs-disk reconciliation
  (registered-but-no-files / files-but-not-registered) never fired and registered slugs were even
  mis-flagged "not registered". The validator now parses BOTH shapes (table rows scoped anywhere; bullet
  rows scoped under "## Active workflows", ignoring `<placeholder>`/backtick doc lines and quoted trigger
  phrases). Bullet rows carry no Layer-1 column → disposition recorded as unknown (still counts as
  registered). `scripts/09-install-conversation-workflows.sh` now seeds the canonical TABLE shape (matching
  protocol §F + the validator) while the validator still tolerates the legacy bullet form for older installs.
- **GAP 2 — 23-key linter excluded the v6.0 playbook.** `scripts/qc-23-key-bodies.sh` skipped
  `references/v6.0-source-playbook.md` (~9,430 lines) by name — the file holding the LARGEST set of GHL RAW
  BODY examples (per-channel curl smoke tests, Build-with-AI prompt bodies, verification-checklist bodies).
  Exclusion removed; the playbook is now scanned. The single-DOTALL `FENCE_RE` was also mis-pairing fences
  across that large multi-language document (it found only 1 of the file's 12 bodies), so the fence scanner
  was rewritten as a line-state iterator that pairs `` ``` `` open/close correctly regardless of language
  tag — now catching object-A bodies in ```json, ```text, no-language Build-with-AI blocks, AND ```bash
  `curl -d '{…}'` smoke tests. Object-B server `hooks.mappings` blocks (camelCase `agentId`) are still
  skipped by the snake_case `agent_id` discriminator — not by file exclusion. Linter result on the playbook:
  **all 12 of its bodies PASS**; repo-wide **RESULT: PASS — 23 object-A bodies across 6 files** (was 10/5).

### Added
- `scripts/qc-trinity-registry.test.sh` — fixture tests proving reconciliation catches a
  registered-but-missing-files row AND a file-present-but-unregistered slug on BOTH the bullet and table
  registry forms (and that a clean bullet registry PASSes). Wired into CI (`.github/workflows/qc-static.yml`).

### Version
- `skill-version.txt` → `1.4.7`.

## [1.4.6] - 2026-05-29 - 8 rated improvements (port of VPS #47): machine-enforced 23-key + TRINITY, Build-with-AI label fix, real self-counts, fleshed journeys, Skill 23 chain

Part of repo `v10.15.9`. Six of the eight rated improvements land in this skill; the other two
(cross-skill chain enforcement + library-gate status surfacing) land in Skill 23 but reference this skill.
No stripped GHL bodies introduced — the 10 embedded object-A bodies all pass the new linter (23-key, flat,
placeholder-free).

### Added
- `scripts/qc-23-key-bodies.sh` — machine-enforces the 23-key GHL RAW BODY rule across references/ +
  templates/ + scripts/ (exactly 23 flat keys, placeholder-free `messageTemplate`, no nesting, no `\n`).
  Wired into `scripts/11-run-qc-checklist.sh` and into CI (`.github/workflows/qc-static.yml`). Excludes the
  verbatim `v6.0-source-playbook.md`; skips object-B server mappings.
- `scripts/qc-trinity-registry.sh` — machine-enforces THE TRINITY: a registry row with a communications
  playbook but no Build-with-AI prompt (or an orphan prompt) is flagged INCOMPLETE; honors the
  Layer-1-not-needed exemption. Wired into `11-run-qc-checklist.sh`; referenced from the verification
  checklist + standards.

### Changed
- **Mislabel fix (the failure this standard set out to kill):** `templates/sms-workflow-ai-prompt-template.md`,
  `templates/workflow-verification-checklist-template.md`, `scripts/21-generate-client-reference-sheet.sh`,
  `scripts/09-install-conversation-workflows.sh`, and `scripts/20-seed-design-principles.sh` now name the
  authoritative location — GHL **Automations → "Build with AI"** (top-right) on a NEW automation — instead
  of "Use Workflow AI" / "Create workflow → Workflow AI".
- **Real self-counts:** `SKILL.md` + `INSTALL.md` now state protocols=32, scripts=27, references=14,
  journeys=8 with a `SELF-COUNTS` re-verify comment; a re-verification note was added to the repo
  `scripts/bump-version.sh`.
- **7 stub journey templates fleshed out** to ≥ coach depth with vertical-specific triggers / conversation
  phases / success actions: consulting, course-creator, e-commerce, real-estate, saas, service-provider,
  wellness (107–121 lines each).
- **Distinction-map table** added at the top of `protocols/conversation-workflows-protocol.md` (channel
  communication playbook vs communications playbook vs workflow-AI prompt vs GHL automation).
- **Skill 23 upstream cross-reference** added to `SKILL.md` + the protocol's TRINITY note (Skill 23's
  comms/sales/support build now hands off here via the enforced `commsAutomationStatus` chain).

### Version
- `skill-version.txt` → `1.4.6`.

## [1.4.5] - 2026-05-29 - v6.0 clean comprehensive playbook; de-staled

### Why
The source playbook is replaced with the **clean, conflict-free v6.0** single-source-of-truth build. All GHL
hook guidance now matches the settled standard everywhere: **23-key FLAT** Raw Body, the body's own
`messageTemplate` value is **placeholder-free**, `deliver` is **`false`**, mapping-level `fallbacks` is
**never** a key (the `.strict()` schema rejects it; fallbacks live on the model-routing config only), and no
nested bodies / no stripped sub-23-key bodies anywhere. Every passage that disagreed with that standard was
removed or corrected upstream in the v6.0 content, so the repo carries **no stale or conflicting playbook
content**. The standards docs (`GHL-INBOUND-AND-PLAYBOOKS.md`, `communications-playbook-standard.md`,
`workflow-ai-instructions-standard.md`) remain their own reference docs; the playbook references them rather
than duplicating them. `skill-version.txt` bumped 1.4.4 → 1.4.5.

### Changed
- `references/v5.14-source-playbook.md` → **renamed** to `references/v6.0-source-playbook.md` (git mv) and its
  content replaced with the clean v6.0 comprehensive playbook (9,430 lines / ~452 KB). The header now stamps
  **Version 6.0 (CLEAN, CONFLICT-FREE)** and declares itself the single source of truth superseding v5.x.
- Updated every live pointer/cross-link from `v5.14-source-playbook.md` to `v6.0-source-playbook.md`:
  `scripts/01-locate-master-files-folder.sh` (both `PLAYBOOK_SRC` and the `DEST_PLAYBOOK` copy target),
  `INSTALL.md`, `INSTRUCTIONS.md`, and the reference cross-links in `GHL-INBOUND-AND-PLAYBOOKS.md`,
  `stripe-coupons-api.md`, `stripe-webhooks-reference.md`, `shopify-graphql-reference.md`,
  `sales-frameworks-deep-dive.md`, `ghl-coupons-api.md`, `cloudflare-tunnel-troubleshooting.md`,
  `fleet-onboarding-tunnel-provisioning-field-guide.md`.
- Conflict sweep across the Skill 38 folder (nested GHL body, sub-23-key body, `deliver:true`, mapping-level
  `fallbacks`, conflicting "DATA ONLY / no messageTemplate" phrasing): **no contradictions found**. The only
  remaining `deliver:true` / "no stripped bodies" mentions are corrective prose that debunks the old patterns,
  and the standards docs already match the corrected structure — no surgical edits were needed beyond the
  playbook content + filename pointers above.

## [1.4.4] - 2026-05-29 - THE TRINITY + Communications Playbook & Workflow-AI standards

### Why
Two recurring failure surfaces hardened, with full content kept in reference/protocol docs (CORE md files
get concise pointers only — no bloat): (1) operators were building a GHL workflow OR a playbook OR a
workflow-AI prompt in isolation, leaving the other two missing; (2) GHL's Build-with-AI repeatedly fails to
populate the Custom Webhook fields, and there was no single standard spelling them out field-by-field. All
new GHL RAW BODY examples honor the 23-key rule (flat, placeholder-free `messageTemplate`, no `\n`, no
nesting, no stripped bodies). `skill-version.txt` bumped 1.4.3 → 1.4.4.

### Added
- `references/communications-playbook-standard.md` — the COMMUNICATIONS PLAYBOOK STANDARD: standardized
  format + a "must appear in EVERY playbook" checklist (slug/id, owner agent id, channel, trigger
  phrases/intent, goal, step-by-step flow, GHL Conversations-API reply mechanism per TOOLS.md,
  cross-playbook transition rules, edge cases incl. frustration/refund/legal escalation, on-success/tagging,
  tone, honesty floor); STORAGE in `conversation-workflows/` + register in `registry.md`; and the client-side
  human-readable copy fallback order **Notion → Google Docs → plain text**.
- `references/workflow-ai-instructions-standard.md` — the WORKFLOW-AI INSTRUCTIONS STANDARD: must-appear
  checklist; WHERE it goes (GHL Automations **Build with AI** button when creating a NEW automation); the
  explicit field-by-field Custom Webhook steps (EVENT=CUSTOM, METHOD=POST, real URL not sample-url,
  AUTHORIZATION=None, HEADERS via Add item → Authorization Bearer token + Content-Type json, RAW BODY = full
  23-key flat JSON via the Custom Values picker); MULTI-ACTION teaching (if/else branches, Add-Tag, tag-check,
  multiple sequential actions, create-tag-via-GHL-skill-first); and the BUILD-WITH-AI VERIFICATION CHECKLIST.

### Changed
- `protocols/conversation-workflows-protocol.md` — added **THE TRINITY** connection rule (workflow ⇄
  communications playbook ⇄ workflow-AI prompt; one implies the other two) + pointers to the two new
  standards; D.2 Build-with-AI prompt block upgraded to the field-by-field Custom Webhook format
  (EVENT/METHOD/AUTHORIZATION=None/HEADERS via Add item/Content-Type); Section E now points at the
  communications-playbook standard's checklist + Notion→Google Docs→plain-text storage order.
- `templates/sms-workflow-ai-prompt-template.md` — Action 1 rewritten to the precise field-by-field format
  (EVENT=CUSTOM, METHOD via dropdown, real URL, HEADERS via Add item, Custom Values picker) + a MULTI-ACTION
  note (if/else, Add-Tag, tag-check, multiple actions; tags created via GHL skill first).
- `templates/workflow-verification-checklist-template.md` — extended with EVENT=CUSTOM, real-URL-not-sample,
  "exactly the intended action(s)" count check, Custom-Values-picker check, and a tags/multi-action item.
- `scripts/05-update-agents-md.sh` (AGENTS.md guidance, Step 1.85) — added concise 1-2 line pointers to THE
  TRINITY + the two new standard reference docs (full content stays in the references, not inline in CORE md).
- `INSTRUCTIONS.md` — Step 9.20 row notes THE TRINITY + the two standards.

## [1.4.3] - 2026-05-29 - Enforce 23-key GHL body everywhere (no stripped bodies)

### Why
Owner directive (non-negotiable): EVERY GHL Custom Webhook RAW BODY example in this skill must contain ALL 23
keys. 23 is the MINIMUM — no stripped/short bodies (8/11/13/16-key versions) are allowed anywhere. The prior
13/16-key bodies are replaced with the full 23-key canonical body. The body stays FLAT, the body's
`messageTemplate` value is kept placeholder-free (no `{{…}}`) so GHL never mangles the JSON, and there are no
`\n` escapes inside any JSON example. Per-channel variants keep all 23 keys; only `channel` + the `session_key`
prefix differ. `skill-version.txt` bumped 1.4.2 → 1.4.3.

### The 23 keys (exact)
`id`, `match`, `action`, `agent_id`, `model`, `wakeMode`, `name`, `session_key`, `messageTemplate`, `deliver`,
`timeoutSeconds`, `channel`, `to`, `thinking`, `contact_id`, `first_name`, `last_name`, `email`, `phone`,
`subject`, `message_body`, `location_id`, `location_name`.

### Added / Changed
- `references/GHL-INBOUND-AND-PLAYBOOKS.md` — new rule (0) mandating all 23 keys (23 = minimum); canonical body
  upgraded to 23 keys + per-channel variant list; Section 4 Build-with-AI body upgraded; Section 5 checklist now
  demands all 23 keys; cardinal-rule + corrected-structure prose rewritten (body now carries a placeholder-free
  `messageTemplate` instead of "no messageTemplate").
- `references/v5.14-source-playbook.md` — every GHL Raw Body upgraded to 23 keys (Step 3C smoke test, Step 4 E2E
  test, Step 9.20-D.2 + multi-channel Build-with-AI prompts, the D.3 verification stub, all six Part 3 channel
  blocks); stripped `tags`/`workflow_id` extra-keys removed; corrected-structure notes rewritten.
- `scripts/15-configure-hooks-mappings.sh` — Step 4 E2E test PAYLOAD upgraded to the full 23-key body.
- `protocols/conversation-workflows-protocol.md` — Build-with-AI Raw Body + D.3 verification stub upgraded to 23
  keys; corrected-structure note rewritten.
- `templates/sms-workflow-ai-prompt-template.md` — SMS Raw Body upgraded to 23 keys; mistakes list updated.
- `templates/client-reference-sheet-template.md` — all six channel Raw Body blocks upgraded to 23 keys.
- `templates/workflow-verification-checklist-template.md` — Raw Body stub upgraded to the full 23-key body.
- `skill-version.txt` — 1.4.2 → 1.4.3.

## [1.4.2] - 2026-05-29 - GHL inbound hook correction: FLAT body, no nesting, server-only messageTemplate

### Why
Verified LIVE on a live client (OpenClaw 2026.5.27): the GHL Custom Webhook RAW BODY must be FLAT
(data-only). A nested `contact:{…}` / `customer_message:{…}` body makes EVERY field arrive EMPTY at the hook
(even a hardcoded `"channel"`), and a `messageTemplate` placed in the GHL body gets mangled by GHL's own
merge-field parser → webhook Skipped ("Error while parsing the object to JSON"). The `messageTemplate` is
server-side only and MUST include the reply-via-GHL-Conversations-API instruction or the agent drafts but
never sends. Content + script correction; `skill-version.txt` bumped 1.4.1 → 1.4.2.

### Added / Changed
- `references/GHL-INBOUND-AND-PLAYBOOKS.md` — new top-of-doc **CORRECTED GHL HOOK STRUCTURE (2026-05-29)**
  section (the 12-point canonical spec); Section 4 Build-with-AI body flattened; Section 5 verification
  checklist updated to demand a FLAT, no-`messageTemplate`, Custom-Values-picker body.
- `references/v5.14-source-playbook.md` — every GHL Raw Body flattened (Step 3C smoke test, Step 4 E2E test,
  Step 9.20-D.2 + multi-channel Build-with-AI prompts, all six Part 3 channel blocks); mapping `messageTemplate`
  rewritten to reference FLAT body keys + reply-via-GHL-API instruction; `deliver:false`; `sessionKey:"{{session_key}}"`;
  removed invalid `fallbacks` key from the mapping (schema is `.strict()`); schema-fields list + Checkpoint C corrected.
- `scripts/15-configure-hooks-mappings.sh` — mapping `messageTemplate` now uses FLAT body keys + GHL-API reply
  instruction; `deliver:false`; `sessionKey` default is `{{session_key}}`; E2E test PAYLOAD flattened.
- `protocols/conversation-workflows-protocol.md` — Build-with-AI Raw Body flattened + corrected-structure note.
- `templates/sms-workflow-ai-prompt-template.md` — SMS Raw Body flattened; mistakes list + placeholders updated.
- `templates/client-reference-sheet-template.md` — all six channel Raw Body blocks flattened.
- `skill-version.txt` — 1.4.1 → 1.4.2.

## [1.4.1] - 2026-05-28 - Conversation Playbook Builder enhancement (the differentiator) (repo v10.15.7)

### Why
The recurring "build me a conversation playbook" flow is the system's USP — communication-driven funnels /
automations, built by talking and brainstorming instead of click-and-drag (this is what beats CloseBot).
Step 9.20 needed to be explicitly bulletproof every time, and the MEMORY.md rules + Mac env handling needed
to back it. Content-only addition; no version files touched (repo stays v10.15.7).

### Added / Changed
- `protocols/conversation-workflows-protocol.md` — Step 9.20 reframed as an explicit **3-PART build**:
  Part 1 (Workflow AI instruction set = Build-with-AI prompt + new **manual-build fallback** D.2b +
  verification checklist, with the SHAPE-first / operator-pastes-tokens guidance); Part 2 (the conversation
  playbook → registered in registry.md, with the hook-path "how the two halves connect" note); Part 3 (new
  Section I — the friendly **brainstorm trigger**: use Typed KBs + USER.md + MEMORY.md, ask ONLY smart gaps,
  NEVER 50 questions, concise "is this what you want?" confirmation → build → Notion doc → register). New
  Section J (AGENTS.md Step 1.85 runtime hook), Section K (builder ↔ router ↔ proactive cross-references),
  Section L (Mac env note). Removed ambiguous "Workflow AI" usage referring to the GHL feature (now
  "Build with AI") and the implication that GHL Automations have an API.
- `scripts/06-append-memory-rules.sh` — adds a second idempotent block: **builder design rules 15-19**
  (Terminology, No-GHL-API, 3-PART Build, Brainstorm-Not-50-Questions, Mac Env).
- `scripts/05-update-agents-md.sh` — Step 1.85 block expanded with the communication-driven USP, the
  brainstorm-not-50-questions rule, the 3-PART build, the no-GHL-API note, and the router/proactive cross-refs.
- `scripts/18-locate-secrets-env.sh` — Step O.5: Mac now searches BOTH `~/clawd/secrets/.env` and
  `~/.openclaw/.env`; added the Mac-vs-VPS env clarity note.
- `protocols/intelligent-routing-protocol.md` (Step 9.33) + `protocols/proactive-suggestions-protocol.md`
  (Step 9.34) — reciprocal triangle cross-references to the builder.
- `INSTRUCTIONS.md` — Step 9.20 row rewritten (3-PART build, USP, no-API note); 9.33/9.34 rows annotated;
  Phase 0 Step O.5 Mac env note added.
- `CORE_UPDATES.md` — documents builder design rules 15-19 so install writes them.

## [1.4.0] - 2026-05-28 - GHL Build-with-AI hardening + calendar-sync (repo v10.15.7)

### Why
A live Mac-mini build surfaced several traps that every future Mac client would otherwise hit:
token confusion (4 distinct secrets), `deliver: true` silently breaking GHL API replies, the
`cron.jobs` JSON block failing validation on openclaw 2026.5.27, GHL having no API/MCP for building
automations (Build-with-AI is the only path), and the Mac-specific `cloudflared` launchd install
needing interactive sudo. Baked all the fixes into the skill so no Mac client stalls on them.

### Added
- `references/GHL-INBOUND-AND-PLAYBOOKS.md` (NEW) — authoritative Mac reference: 4-token table,
  one-tunnel-many-hooks model, copy-paste **Build-with-AI prompt** template (placeholders
  PUBLIC_HOSTNAME / HOOK_PATH / HOOKS_TOKEN / CHANNEL), post-build verification checklist (incl.
  real-inbound-test caveat), Reusable Tunnel Values storage rule (AGENTS.md + TOOLS.md + client
  Notion), JSON one-value-per-key rule, verified channel→`type` enum (valid: SMS/Email/FB/IG/
  WhatsApp/Live_Chat; invalid: TikTok/Call/GMB + long-forms), Conversations reply recipe, Calendar
  recipe (free-slots epoch-MILLIS, book/reschedule/cancel), first playbook = appointment booking.
- `scripts/skill38-calendar-sync.sh` (NEW) — weekly GHL calendar refresh; rewrites the
  `<!-- GHL_CALENDARS_START/END -->` block in TOOLS.md. Auto-detects Mac vs VPS env/paths. Generic
  per-client. Registered via `openclaw cron add --name skill38-calendar-sync --cron "0 9 * * 0" ...`.

### Changed (surgical edits to references/v5.14-source-playbook.md)
- Step 3C + Step 3.5G: `deliver: true` → `deliver: false` on GHL reply hooks, with corrected
  rationale (true makes the gateway try to deliver to a non-existent default chatId → reply never sends).
- Step 3A: added the 4-token disambiguation table; Mac note (no Hostinger wrapper → hooks.token in
  openclaw.json is stable; no OPENCLAW_HOOKS_TOKEN env trick).
- All cron registrations → `openclaw cron add` CLI flag form, with a banner that `cron.jobs` JSON
  does not validate on openclaw 2026.5.27.
- Step 9.20 D.2: "Workflow AI prompt" → "Build-with-AI prompt"; Build-with-AI is PRIMARY, manual
  node-build demoted to FALLBACK; verification checklist required even on success; F.6 Reusable Tunnel
  Values; F.7 base SMS automation also creates the first appointment-booking playbook and wires the
  hook to it.
- Part 2 (Client Reference Sheet / Notion-doc spec) rewritten ordering: Reusable Tunnel Values →
  Build-with-AI prompt per channel → verification checklist; manual webhook build moved to fallback.
- Rules of Engagement: added Rule 7 (one value per key — proper JSON structure).
- Standardized `GHL_PRIVATE_INTEGRATION_TOKEN` + `Version: 2021-04-15` on the Conversations/Calendar
  path (was `<GHL_PIT_TOKEN>`). `GOHIGHLEVEL_AGENCY_PIT` is not present in this repo.
- Calendar action: verified endpoints (free-slots epoch-millis; appointments required fields; PUT/DELETE).
- Mac cloudflared step: kept launchd `sudo cloudflared service install` but flagged the
  interactive-sudo requirement prominently (cannot run over non-interactive rescue SSH).

# Skill 38 — Conversational AI System: Changelog

## [1.0.0] - 2026-05-28 - Initial release (packages v5.14 playbook)

### Why
the operator's v5.14 conversational AI playbook (~8,800 lines, 14 version iterations) packaged as
an installable skill. Builds the conversational AI BRAIN on top of skill 29 (GHL Convert and Flow).

### Added
- 27 protocol files (humanizer NOT included; skill 19 owns it)
- 8 customer journey templates (coach fully detailed; 7 stubbed)
- 9 idempotent + OS-aware install scripts (00 prerequisites → 08 Shopify wizard)
- 7 reference documents including the FULL v5.14 source playbook + strategic roadmap
- SKILL.md, INSTALL.md, INSTRUCTIONS.md, EXAMPLES.md, CORE_UPDATES.md
- AGENTS.md Steps 1.7, 1.8, 1.9, 2.8; upgraded Step 1.75
- MEMORY.md design rules 6-14
- 4 cron jobs (Sunday 2am tune-up, Saturday 11pm proactive + 11:30pm model freshness, 1st-of-month review)

### Source of truth
- `references/v5.14-source-playbook.md` — the canonical 8,797-line playbook
- `references/conversational-ai-strategic-roadmap.md` — strategic context (✅ shipped vs 📋 pending)

### Out of scope (DEFERRED, not in this skill)
- F14 Voice/Phone Integration
- F15 Proactive Outreach Campaigns
- F16 A/B Testing of Reply Variants
- F17 Customer Segmentation Awareness
- F18 Webhook Chaining
- F21 Multi-Tenant Agent Isolation

The skill's structure (numbered scripts, protocols/ folder, references/) leaves room for
these to be added later without restructuring.

## [v2.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
