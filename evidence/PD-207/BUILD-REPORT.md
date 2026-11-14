# PD-207 — build report (deepseek-chain)

Repo: `trevorotts1/openclaw-onboarding` · branch `pd/fl17-phase-checks`
Branch head when I started: `b7d16fe6ba6709d65260086339ae97b6f095f1c1`
Branch head now: `bb54443f943cb045794caabdc15539516d880648` (code + tests), then the report commit.
All scratch work was done in worktrees under
`$LOOP_ROOT/tmp/PD-207` (`wt/` = after, `base/` = unchanged HEAD).
The lane clone was never edited and is clean.

## 1. Spec, quoted

`<EXTERNAL-VOLUME>/swarm-contract/fable-reviews-2026-11-11/03-presentation-department/FINAL/01-BUILD-SPEC.md`
lines 2911–2931, section `### PD-207 — The upload step needs an upload record`:

> | Lane and repository | FL17 · trevorotts1/openclaw-onboarding |
> | Acceptance rows the checker must run | A1 |
>
> - **Change:** in `_verify_ghl_upload` (keep one definition; delete the byte-identical second copy at lines 2595–2648): a missing, unreadable or non-object record returns `False` with "media_library.json is missing — the upload did not run". A missing `ghl_folder_id` is a failure, not a note.
> - **Acceptance:** the PD-207 probe as a test: empty run → fail; record with ids → pass (network part stubbed away).

Ledger row (`loop-control/pd-fix/ledger.json`): `"id": "PD-207"`, `"owned_paths"` =
`.../presentations/scripts/phase_verifiers.py`, `.../tests/test_pd_phase_checks_*.py`,
`test_pd061_verifier_paths.py`, `test_pd088_design_phase.py`, `test_fix112_missing_producers.py`;
`"acceptance_rows": ["A1"]`.

## 2. What I implemented

1. **One definition.** The two `_verify_ghl_upload` definitions were byte-identical. Proven before deleting:

```
copy1 2529 2582 copy2 2723 2776 identical= True
removed old lines 2723 to 2778
  (git show -U0: "@@ -2723,56 +2728,0 @@" — the 54-line body 2723-2776
   plus the two blank lines that followed it)
```

(Hashes of both function bodies: `41e35fc8242525e9`, computed with `ast` line spans.)
The **second** copy was deleted; Python binds module names to the *last* definition, so the
surviving first copy is the same code the module was already executing — behaviour-neutral on its own.

2. **The record is required.** `media_library.json` missing, unreadable (bad JSON), or a
non-object now returns `False` with the spec string, verbatim:
`media_library.json is missing — the upload did not run`.

3. **`ghl_folder_id` is a failure.** Was `NOTE: ghl_folder_id absent` (note only, still `True`).
Now `AF-BUNDLE-COMPLETE: media_library.json has no ghl_folder_id — the upload did not run.`
and the function cannot return `True`. That required fixing three fail-soft `return True` paths
(import/env skip, no LOCATION PIT, transport error) which would otherwise have converted the new
hard reason back into a pass — they now return `(len(reasons) == 0)` so a NOTE still does not fail
by itself but can no longer mask a hard reason.

The read-only list-back contract is unchanged (still fail-soft on transport/scope).

## 3. Files changed

| File | Change |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/phase_verifiers.py` | duplicate definition deleted (−55 lines); record required; `ghl_folder_id` hard-fails; fail-soft returns preserve the verdict. `+19 −69` |
| `.../scripts/tests/test_pd_phase_checks_upload_record.py` | **new**, 7 tests, row A1 |
| `.../scripts/tests/test_ghl_media_list.py` | `test_verify_ghl_upload_no_ledger` retargeted from "PASS with a NOTE" to the spec's FAIL. One assertion, strict equality. |
| `evidence/PD-207/BUILD-REPORT.md` | this report |

**Out-of-owned-path edit, declared:** `tests/test_ghl_media_list.py` is not in the unit's
`owned_paths`. It asserted the exact behaviour the spec reverses ("No ledger at all -> PASS with a
NOTE"). The spec's own field says *"Existing tests it breaks and must update: none known in advance;
the lane's reading units and the test census name the rest (rule 15)"* — this is that test. I changed
only that one function and strengthened it (`reasons == [<spec string>]` instead of a substring
match). Nothing was weakened, skipped, renamed or deleted.

## 4. Row A1, proven

Row A1 = *"the PD-207 probe as a test: empty run → fail; record with ids → pass (network part stubbed away)."*

New test file, run on the built tree (`$TMPDIR/wt/.../scripts`):

```
$ python3 -m pytest tests/test_pd_phase_checks_upload_record.py -q -p no:cacheprovider
.......                                                                  [100%]
7 passed in 0.49s
```

Each probe is its own test, so the verdict is per-case, not a summary:

- `test_missing_record_fails_with_the_spec_message` — empty run dir → `ok is False`, `reasons == ["media_library.json is missing — the upload did not run"]`
- `test_unreadable_record_fails` — invalid JSON on disk → `False`, same string
- `test_non_object_record_fails` — JSON list, not object → `False`, same string
- `test_record_with_ids_passes_with_stubbed_transport` — `ghl_folder_id` + `pptx_ghl_media_id` + `pptx_ghl_remote_name`, `ghl_media.resolve_location_pit/resolve_location_id/list_media` monkeypatched → `True`, zero hard reasons (**the network part is stubbed away**)
- `test_missing_folder_id_fails_even_when_listing_finds_the_deck` — the list-back *finds* the deck and it still fails: a folder id is a record field, not a note
- `test_missing_folder_id_fails_when_the_list_back_is_skipped` — pit empty → fail-soft path must not soften it
- `test_only_one_definition_of_the_verifier` — parses `phase_verifiers.py` and asserts exactly one `_verify_ghl_upload` at module level

## 5. The failure proof (BEFORE / AFTER)

Same test file, same command, against **unchanged HEAD code** (`b7d16fe6b`, worktree `base/`):

```
FFF.FFF                                                                  [100%]
...
assert ok is False
E       assert True is False            # missing record
assert ok is False
E       assert True is False            # unreadable
assert ok is False
E       assert True is False            # non-object
E       AssertionError: a missing folder id must be a failure, not a NOTE
assert ok is False
E       assert True is False            # folder id, list-back skipped
E       AssertionError: expected one _verify_ghl_upload, found 2
E       assert 2 == 1
6 failed, 1 passed in 0.22s
```

AFTER, same command: `7 passed`.  The single test that also passes on base is
`test_record_with_ids_passes_with_stubbed_transport` — that half of the contract already worked;
it is the control, and it must pass on both sides.

The retargeted existing test is also RED on base and GREEN on head:

```
# base, updated test_ghl_media_list.py copied in:
assert ok is False
E       assert True is False
1 failed in 0.14s
# head:
17 passed in 0.38s        (test_ghl_media_list.py + test_pd_phase_checks_upload_record.py)
```

No test was reverted afterwards on the branch — the "before" side is the untouched base commit,
which is a stronger proof than a hand-made mutation.

## 6. Test runs by id

| Run | base `b7d16fe6b` | head `bb54443f9` |
|---|---|---|
| `tests/test_pd_phase_checks_upload_record.py` (whole file) | 6 failed, 1 passed | **7 passed** |
| `tests/test_ghl_media_list.py` (whole file) | 10 passed | **10 passed** |
| `::test_verify_ghl_upload_no_ledger` (updated) | 1 failed | passes |
| `tests/test_pd061_verifier_paths.py` | passed | passed |
| `tests/test_pd088_design_phase.py` | passed | passed |
| `tests/test_fix112_missing_producers.py` | 1 failed, 5 passed | 1 failed, 5 passed (same test) |
| `tests/test_pd_phase_checks_{audio,human_review,prompt_reason,typography}.py` | passed | passed |
| owned set together (52 tests) | — | **51 passed, 1 pre-existing failure** |
| whole `scripts/tests/` suite | 226 failed, 3701 passed, 12 skipped (18:17) | **219 failed, 3708 passed, 12 skipped** (18:21) |

Failure-set diff, base vs head, by node id: **0 new failures**. 7 failures disappear: my 6
new tests (they were red on base by design) plus
`tests/test_pres026_media_resume.py::test_two_workers_same_run_single_operation`, which is a
two-worker locking test that failed on base and passed on head in these runs — I did not touch
`test_pres026_media_resume.py` or anything it exercises. Read it as order/timing, not as a fix
landing. The 219 remaining failures are the branch's pre-existing set.

Pre-existing failure named so it is not mistaken for mine:
`tests/test_fix112_missing_producers.py::test_infographic_checklist_phase_exists_with_role_file_and_verifier`
— `role file missing: .../presentations/infographic-checklist.md`, fails identically on base.

## 7. Hunk attribution (merge-base → head)

`git merge-base origin/main b7d16fe6b` = `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`.

Commits that touch `phase_verifiers.py` on this branch before my unit, with their hunk regions
(`git show --unified=0`):

| Commit | Unit | Regions in `phase_verifiers.py` |
|---|---|---|
| `da995d14e` | **PD-072** (accepted at `b7d16fe6b`) | `_verify_prompt` @@ −702/+703, −704/+720 — reason from measured/required/fix |
| `c6d702160` | **PD-075** | `_VERIFIER_SYMBOL_CONTRACT` −238/−240, `_verify_prompt` −733/−740, `_verify_qc_report` −765, `_verify_webinarized_speech` −2946..−2954 |
| `1e697fdda` | PD-088 | `_verify_motion_phase` +4029, `PHASE_VERIFIERS` −4059/+4126 |
| `cb8028e04` | PD-921 | `_intake_provenance_refusal` −165/−167 |
| `10cedc4ec` | PD-062v | `import sys` +55, `_fix16_apply` +1513, `_verify_assemble` −1515..−1566, `artifact_path` +4211/+4215 |
| `08a6cdcd7` | PD-910 | `_pu_check_receipt_identity` −4424, `_make_pu_verifier` −4725 |
| `200fa8630` | PD-064 | `_verify_notes_sync`/`_DELIVERY_PATTERN_BY_KEY` −1632..−1641, `_deliverable_content_check` −2068, `_verify_delivery` −2071..−2163, `_verify_bundle_gate` −3834 |
| `f63ef6b0c` | PD-061 | `_verify_json_artifact` −2165..−2167, `_verify_text_artifact` +2340, `_shadow_qc_verifier` +2906, `PHASE_VERIFIERS` −4020 |
| `471fdae82` | PD-206a | `_verify_render` −851, `anchors_iter` +997, `_verify_image_grounding` −1001..−1063, `_verify_representation_casting` −1110..−1171, `PHASE_VERIFIERS` −3978 |

**PD-924** is on this branch too (`a97fcc9ca`); it touches `test_runfacts.py` and
`tests/test_trust_boundary_observability.py`, **not** `phase_verifiers.py`.

My hunks are in the `_verify_fish_tag` / `_verify_ghl_upload` block: the edited body is current
lines **2529–2588**, and the deleted duplicate occupied old lines **2723–2776**. No sibling hunk on
this branch lands between lines 2340 and 2906, so those hunks are mine alone; the file's other hunks
above belong to the units in the table.

## 8. Remote head proof

```
$ git push origin HEAD:refs/heads/pd/fl17-phase-checks
   b7d16fe6b..bb54443f9  HEAD -> pd/fl17-phase-checks

$ git rev-parse HEAD
bb54443f943cb045794caabdc15539516d880648

$ git ls-remote --heads origin refs/heads/pd/fl17-phase-checks
bb54443f943cb045794caabdc15539516d880648	refs/heads/pd/fl17-phase-checks
```

40 characters, compared literally: match. (The report commit that follows is proven the same way in
the hand-off message that carries this file.)

## 9. Not proved / honest gaps

- The whole-suite numbers are from this machine, 18 minutes per side, and the suite has 219
  pre-existing failures on this branch. I proved *no new failure and the 6 targeted ones flipping*,
  not that the suite is green.
- `test_pres026_media_resume.py::test_two_workers_same_run_single_operation` changed state between
  the two runs. I did not touch that file or its subject; I am reporting the movement rather than
  claiming it.
- The `base/` full run started after I had copied the new test file into that worktree (the BEFORE
  proof), so those 6 tests legitimately appear in its failure list.
- The PD-207 spec's cited line range ("lines 2595–2648") does not match this tree; the second copy
  actually sat at lines **2723–2776** (`ast` spans). Byte-identity was proven, not line numbers.
- `_verify_fish_tag` is *also* duplicated byte-for-byte (2504–2526 / 2698–2720). That is not PD-207's
  subject and I left it alone.
- No network, no live GoHighLevel call, nothing deployed.
