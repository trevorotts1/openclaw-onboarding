# PD-208 — build report (deepseek-chain)

Repo: `trevorotts1/openclaw-onboarding` · branch `pd/fl17-phase-checks`
Remote branch head before this unit: `bc264097b300006c6fe53a58fb823c855c9dbfc0`
Code + tests commit: `993f6fb9ce917c5eaf0d48644304f82029e33bb1`
This report commit: the one that adds this file.

All scratch work was done in throwaway copies under
`<LOOP_ROOT>/tmp/PD-208` (`work.VLS8fP/onboarding` = my tree,
`work.VLS8fP/base` = untouched `bc264097b`, `work.VLS8fP/mut` = mutation copy). The lane clone
was never edited and is clean.

## 1. Spec, quoted

`<SWARM_ROOT>/fable-reviews-2026-11-11/03-presentation-department/FINAL/01-BUILD-SPEC.md`
lines 2933–2949, section `### PD-208 — PDF steps check for a PDF`:

> | Lane and repository | FL17 · trevorotts1/openclaw-onboarding |
> | Wave | 3 |
> | Depends on (must be ACCEPTED, that is QC-passed, first) | PD-207 |
> | Acceptance rows the checker must run | A1 |
>
> **Carried-over unit text (from `PASS5-GATES.md`, section PD-208; ids, decisions and lanes already converted to final):**
>
> - **Change:** add `_verify_binary_artifact(pattern, min_bytes, magic, scale_by_slides, floor_formula)` beside `_verify_text_artifact`: size from the file's byte length, and the first bytes must equal `magic`. Register the three PDF steps with `magic=b"%PDF"`.
> - **Acceptance:** the PD-208 probe as a test: text named `.pdf` → fail "not a PDF"; a file starting `%PDF` above the floor → pass.

Ledger row (`loop-control/pd-fix/ledger.json`): `"id": "PD-208"`, `"depends_on": ["PD-207"]`,
`"acceptance_rows": ["A1"]`, `owned_paths` =
`.../presentations/scripts/phase_verifiers.py`,
`.../tests/test_pd_phase_checks_*.py`,
`.../tests/test_pd061_verifier_paths.py`,
`.../tests/test_pd088_design_phase.py`,
`.../tests/test_fix112_missing_producers.py`.

Dependency PD-207 is ACCEPTED and is the branch head `bc264097b` (`PD-207: correct the deleted-range
line count in the build report`). I built on it.

## 2. What I implemented

1. **`_verify_binary_artifact`** added immediately beside `_verify_text_artifact` (inserted at old
   line 2452, right after `_verify_text_artifact`'s `return _v`). Signature is the spec's, verbatim
   and in order: `(pattern, min_bytes=50, magic=b"%PDF", scale_by_slides=False, floor_formula="pdf")`.
   - size = `p.stat().st_size` — the **byte length on disk**, never `len(text)`.
   - first `len(magic)` bytes read in `"rb"` and compared: `if head != magic` → `False` with
     `"...: not a PDF — expected b'%PDF' at offset 0, got b'...'"`.
   - floors scale by slide count exactly like `_verify_text_artifact`: the same one helper
     `presentation_job.deliverable_floors` (`slide_count`/`pdf_floor`/`guide_floor`), the same
     `floor_formula` select, the same raw-`min_bytes` fallback when the module is unavailable.
   - it stamps `.artifact_pattern`, the PD-061 contract `test_pd061_verifier_paths.py` A4 walks
     (that test is unchanged and still green — see §5).

2. **The three PDF steps are registered with the binary factory and `magic=b"%PDF"`:**

```
"P8.1-PDF-EXPORT":    _verify_binary_artifact("working/deliverables/*-FINAL.pdf",
                                              _MIN_BYTES["deck_pdf"], magic=b"%PDF",
                                              scale_by_slides=True, floor_formula="pdf"),
"P8.2-GUIDE":         _verify_binary_artifact("working/deliverables/PRESENTER-GUIDE.pdf",
                                              _MIN_BYTES["guide_pdf"], magic=b"%PDF",
                                              scale_by_slides=True, floor_formula="guide"),
"P9.1-SPEECH-PDF":    _verify_binary_artifact("working/deliverables/PRESENTERS-SPEECH.pdf",
                                              _MIN_BYTES["speech_pdf"], magic=b"%PDF"),
```

`_verify_text_artifact` is untouched and still serves `P9-SPEECH`, `P7-TELEPROMPTER` and the other
text steps.

## 3. Files changed

| File | Change |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/phase_verifiers.py` | `+48` new `_verify_binary_artifact`; three registry entries retargeted to it with `magic=b"%PDF"`; the FIX 103 comment above P8.1 updated to name the binary check. `+60 −8` |
| `.../scripts/tests/test_pd_phase_checks_pdf_magic.py` | **new**, 10 tests, row A1 (A1a–A1e) |
| `.../scripts/tests/test_deliverables_single_source.py` | behavioural PDF fixture seeds real `%PDF` bytes of the exact length under test instead of `"z" * n`. **Assertions unchanged.** `+7 −4` |
| `.../scripts/tests/test_fix17_verifier_import_failclosed.py` | docstring only: the `_mint_artifact` comment named `_verify_text_artifact("...", 51200)`; it now names `_verify_binary_artifact(..., magic=b"%PDF")`. No code, no assertion. |
| `evidence/PD-208/BUILD-REPORT.md` | this report |

### Out-of-owned-path edits, declared

- `tests/test_deliverables_single_source.py` and `tests/test_fix17_verifier_import_failclosed.py`
  are **not** in the unit's `owned_paths`. The spec's own field says *"Existing tests it breaks and
  must update: none known in advance; the lane's reading units and the test census name the rest
  (rule 15)"* — these two are what the census named.
  - `test_deliverables_single_source.py` **had** to change: its size-floor assertions seeded
    `"z" * floor` at a path named `PRESENTERS-SPEECH.pdf`. Under the new binary check that file is
    rejected for its magic, so the "one byte under the floor" case would have passed for the wrong
    reason and the "exactly at the floor" case would have failed spuriously. I proved the old
    fixture now fails, then made the fixture a real PDF (§6). **No assertion was weakened, deleted,
    renamed, skipped or xfailed** — same two assertions, same thresholds, same messages.
  - `test_fix17_verifier_import_failclosed.py`: one docstring line. Its fixture already wrote
    `b"%PDF-1.4 fixture " + b"x"*60000`, so no behaviour changed.
- The new test file is named into the owned glob `tests/test_pd_phase_checks_*.py` deliberately
  (it matches the lane's existing `test_pd_phase_checks_{audio,upload_record,typography,...}.py`
  convention), so the unit's own new test lands inside `owned_paths`.

`update-skills.sh`, `universal-sops/_content-manifest.json` and `install.sh` were not touched.

## 4. Row A1, proven

Row A1 = *"the PD-208 probe as a test: text named `.pdf` → fail 'not a PDF'; a file starting `%PDF`
above the floor → pass."*

```
$ cd .../work.VLS8fP/onboarding/23-ai-workforce-blueprint/templates/role-library/presentations/scripts
$ python3 -m pytest tests/test_pd_phase_checks_pdf_magic.py -q --tb=short -p no:cacheprovider
..........                                                               [100%]
10 passed in 1.59s
rc=0
```

The 10 = 3 × `test_a1a_text_named_pdf_fails_not_a_pdf` (one per registered PDF step) + 3 ×
`test_a1b_pdf_magic_above_floor_passes` + `a1c` (exactly at the floor passes) + `a1d` (one byte
under fails on size) + `a1e` (the control) + the registration/signature test.

Satisfying commit for every row: **`993f6fb9ce917c5eaf0d48644304f82029e33bb1`**.

### The pair at the artefact level (not a returned value)

Same probe, same fixture, run against the pristine base tree and against the built tree:

```
=== BASE (bc264097b) ===
factory   : code _v
verifier  : _v | closure: ['str', 'int', 'str', 'bool']
text .pdf -> PASS | []
real .pdf -> PASS | []

=== HEAD (993f6fb9c) ===
factory   : code _v
verifier  : _v | closure: ['str', 'bytes', 'int', 'str', 'bool']
text .pdf -> FAIL | ["working/deliverables/PRESENTERS-SPEECH.pdf: not a PDF — expected b'%PDF' at offset 0, got b'zzzz'"]
real .pdf -> PASS | []
```

The closure grew from 4 cells to 5 — `bytes` is the `magic` cell — which is the registration itself,
not a string in a test.

## 5. The failure proof (mutations, RED then reverted)

Both mutations were applied in `work.VLS8fP/mut` (a separate worktree at `bc264097b` carrying only
this unit's patch), so neither the base tree nor the built tree was disturbed.

**Mutation 1 — magic comparison neutralised** (`if head != magic:` → `if False:` inside
`_verify_binary_artifact`):

```
$ python3 -m pytest tests/test_pd_phase_checks_pdf_magic.py -q --tb=line
FAILED ...::test_a1a_text_named_pdf_fails_not_a_pdf[P8.1-PDF-EXPORT-working/deliverables/*-FINAL.pdf-deck_pdf]
    AssertionError: P8.1-PDF-EXPORT: a 200,000-byte text file named *.pdf must NOT pass — the step is checked for a PDF
FAILED ...::test_a1a_text_named_pdf_fails_not_a_pdf[P8.2-GUIDE-working/deliverables/PRESENTER-GUIDE.pdf-guide_pdf]
    AssertionError: P8.2-GUIDE: a 200,000-byte text file named *.pdf must NOT pass — the step is checked for a PDF
FAILED ...::test_a1a_text_named_pdf_fails_not_a_pdf[P9.1-SPEECH-PDF-working/deliverables/PRESENTERS-SPEECH.pdf-speech_pdf]
    AssertionError: P9.1-SPEECH-PDF: a 200,000-byte text file named *.pdf must NOT pass — the step is checked for a PDF
3 failed, 7 passed
```

Exactly three failures, and each names **its own** phase id — this is what proves the three registry
lines individually, not one string reused across them.

**Mutation 2 — size floor neutralised** (`if size < floor:` → `if False:`):

```
$ python3 -m pytest tests/test_pd_phase_checks_pdf_magic.py -q --tb=line
tests/.../test_pd_phase_checks_pdf_magic.py:104: AssertionError: a PDF one byte under the floor must fail
1 failed, 9 passed
```

**Reverted:** `diff -q` of the mutation tree's `phase_verifiers.py` against the built tree's →
`IDENTICAL`, then `10 passed in 0.15s`.

**The control cannot go vacuous.** `test_a1e` asserts that the *same* 200,000-byte text fixture still
**passes** the old `_verify_text_artifact`. If the fixture ever dropped below the text floor, A1e
would fail rather than A1a passing silently.

## 6. Proof that the single-source fixture had to change

With the built `phase_verifiers.py` and the **base** version of
`test_deliverables_single_source.py` restored (in the mutation worktree):

```
$ python3 -m pytest tests/test_deliverables_single_source.py -q --tb=line
FAILED tests/test_deliverables_single_source.py::test_no_min_bytes_drift_across_all_known_copies
E  phase_verifiers.PHASE_VERIFIERS['P9.1-SPEECH-PDF']: a 3,000-byte file (exactly the canonical
   3,000-byte speech_pdf floor) failed on size -- the verifier's real runtime floor is above
   doctrine: ["working/deliverables/PRESENTERS-SPEECH.pdf: not a PDF — expected b'%PDF' at offset 0,
   got b'zzzz'"]
1 failed, 13 passed
```

So the old text fixture is genuinely incompatible with the new check, and the update is required —
not cosmetic. The other 13 tests in that file pass untouched.

## 7. Tests by id — base vs head

Identical six-file set, run on the pristine base tree and the built tree:

```
$ python3 -m pytest tests/test_deliverables_single_source.py tests/test_pd061_verifier_paths.py \
    tests/test_fix17_verifier_import_failclosed.py tests/test_pd_phase_checks_audio.py \
    tests/test_presentation_job.py tests/test_slice3_gates.py -q --tb=no -p no:cacheprovider
```

| Tree | Result |
|---|---|
| base `bc264097b` | **6 failed, 71 passed** in 46.26s |
| head `993f6fb9c` | **6 failed, 71 passed** in 43.12s |

The two failure lists are identical, test for test:

```
FAILED tests/test_fix17_verifier_import_failclosed.py::TestVerifierImportFailureAborts::test_run_phase_raises_verifier_import_error
FAILED tests/test_fix17_verifier_import_failclosed.py::TestVerifierImportFailureAborts::test_no_done_attestation_minted
FAILED tests/test_fix17_verifier_import_failclosed.py::TestVerifierImportFailureAborts::test_persisted_state_has_no_attestation
FAILED tests/test_fix17_verifier_import_failclosed.py::TestVerifierImportFailureAborts::test_verifier_unavailable_event_recorded
FAILED tests/test_fix17_verifier_import_failclosed.py::TestVerifierImportFailureAborts::test_propagates_through_run_phase_timed
FAILED tests/test_presentation_job.py::TestQCAggregatePhaseEndToEnd::test_flawless_six_reports_reach_done
```

**These six fail on the pristine base tree with no working-tree changes, and fail identically on head.
They are pre-existing and unrelated to PD-208.** I did not fix or touch them. Their root causes:

- the five `test_fix17…` tests expect `VerifierImportError` out of `run_phase`; the phase instead
  reaches its post-executor artifact check and quarantines. I confirmed independently that the
  fixture's artifact **is** present and **does** resolve — a side script on the same `_Engine` +
  `_mint_artifact` reported `_artifacts_present -> (True, [])` — so the disappearance happens inside
  `run_phase`, not in the fixture. **Root cause not attributed further: out of this unit's scope.**
- `test_flawless_six_reports_reach_done` fails the same way on base; not investigated (out of scope).

`TESTING.md` is not needed here: no live action, no network, no model call — this unit is
"files and stubbed tests only", per its own spec row.

### Test census (rule 15)

I ran the census of every test file in the tree that mentions `phase_verifiers` — 57 files:

```
$ grep -rl "phase_verifiers" tests/*.py | wc -l   ->  57
```

One file in that set does not complete in this environment, **on the pristine base tree as well**:
`tests/test_fanout_prompt_phase.py` — still running after a 60 s bounded probe with no output; last
started test `test_workers_1_and_workers_n_produce_identical_file_sets`. It is a pre-existing
environmental hang, not PD-208: it hangs on a tree that does not contain this unit's change at all.
It is excluded from the census below and reported as unobserved.

With that file excluded (56 files, 803 collected tests), both trees run 237 tests and then **block**
(not compute: 4.5 s of CPU over 2 m 10 s of wall time) on a budget/timing test
(`test_f16_agent_phase_wait_race.py::test_complete_inherited_artifact_inside_budget_does_not_block`
in one run; the stall point moves between runs). Both trees stall the same way.

The two progress streams, verbatim:

```
$ sed 's|^|tests/|' census-files2.txt | xargs python3 -m pytest -q --tb=no -p no:cacheprovider
base: ............F.................................................F...F..F.F [ 26%]
      FFF..................
head: ...........FF.................................................F...F..F.F [ 26%]
      FFF..................
```

**One difference appeared in sample 1 and it was investigated, not waved away.** Character index 155
mapped (via `pytest --collect-only -q`, 803 ids in order) to
`tests/test_fault17_resume_false_block.py::test_resume_onto_finished_verifier_passing_work_does_not_false_block`
— base `.`, head `F`. Findings:

- it **passes on head in isolation** (`rc=0`);
- its **own file** fails on **both** trees, identically, and on a *different* test
  (`test_resume_onto_live_work_with_failing_verifier_still_blocks`: `1 failed, 1 passed` on base and
  on head);
- the test **cannot reach this unit's code**: it uses `P4-PROMPT` and does
  `monkeypatch.setattr(phase_verifiers, "verify", lambda *a, **k: (True, []))`;
- a **second census sample shows 0 differences** between base and head (`index155: . .` on both).

So it is an order/timing flake, not this unit. Full second-sample comparison:

```
len base 218 len head 217
differences: 0
index155: . . -> tests/test_fault17_resume_false_block.py::test_resume_onto_finished_verifier_passing_work_does_not_false_block
```

The census is therefore **partial**: 237 of 803 tests on both trees, identical except for the one
flake above. The six-file bisect in §7 is the complete, deterministic evidence for this unit's
blast radius.

## 8. Hunk attribution (merge-base → head)

`git merge-base origin/main HEAD` = `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`.

My hunks, `git diff -U0` against `bc264097b`:

```
phase_verifiers.py     @@ -2452,0 +2453,48 @@   (the _verify_binary_artifact factory)
                       @@ -4212,5 +4260,7 @@   (P8.1-PDF-EXPORT + the FIX 103 comment)
                       @@ -4219 +4269 @@       (P8.2-GUIDE)
                       @@ -4220,0 +4271 @@
                       @@ -4231,2 +4282,3 @@   (P9.1-SPEECH-PDF)
test_deliverables_single_source.py  @@ -272,0 +273,7 @@, @@ -276 +283 @@, @@ -287 +294 @@
test_fix17_verifier_import_failclosed.py  @@ -103,2 +103,3 @@  (docstring only)
test_pd_phase_checks_pdf_magic.py  new file
```

**Sibling units on this same branch, and the hunks they own in the same file** (all present at
`bc264097b`, none of them in my ranges):

| Unit | Commit | Region it owns in `phase_verifiers.py` |
|---|---|---|
| PD-061 | `f63ef6b0c` | P9-SPEECH path (the text factory's other registration) |
| PD-064 | `200fa8630` | `P9-DELIVER` audio scoping |
| PD-206a | `471fdae82` | human verdict readers |
| PD-910 | `08a6cdcd7` | unbound sentinel / note-vs-failure |
| PD-062v | `10cedc4ec` | deck path resolution |
| PD-921 | `cb8028e04` | provenance binding refusal |
| PD-088 | `1e697fdda` | typography step |
| PD-075 | `c6d702160` | typography report path |
| PD-072 | `da995d14e` | prompt failure reason |
| PD-207 | `bb54443f9` | `_verify_ghl_upload` (the dependency) |
| PD-924 | `a97fcc9ca` | test fixtures only, no `phase_verifiers.py` hunk |
| PD-060 | `0ac43ab3a` | bundle check out of the render (tests + build_deck) |
| PD-902 | `35c649df7` | closeout wrappers (tests) |
| PD-915 | `2d85e9d1b` | bundle gate assertion (tests) |
| PD-046 | `1372454c0`, `fea4d704e` | style pick / render (build_deck, tests) |

`git blame` at `bc264097b` attributes the three PDF registry lines and
`_verify_text_artifact`'s header to `4019cf9b09`, `2375720c80` and `9307ec8926` — all **ancestors of
the merge-base**, so no sibling unit on this branch had touched the lines I changed. My insertion
point sits immediately after `_verify_text_artifact`'s `return`, in a region no sibling touched.

## 9. Remote head proof

Before editing:

```
$ git ls-remote --heads origin refs/heads/pd/fl17-phase-checks
bc264097b300006c6fe53a58fb823c855c9dbfc0	refs/heads/pd/fl17-phase-checks
```

After the code+tests push:

```
$ git push origin HEAD:refs/heads/pd/fl17-phase-checks
   bc264097b..993f6fb9c  HEAD -> pd/fl17-phase-checks
```

and `git ls-remote` after it:

```
$ git ls-remote --heads origin refs/heads/pd/fl17-phase-checks
993f6fb9ce917c5eaf0d48644304f82029e33bb1	refs/heads/pd/fl17-phase-checks
```

This report is the commit immediately after `993f6fb9c` on the same branch; the branch head after
that push is given with this unit's return message (a report cannot contain its own commit SHA).

## 10. What is not proved

- The five `test_fix17_verifier_import_failclosed.py` failures and
  `test_flawless_six_reports_reach_done` were shown to predate this unit (they fail on the untouched
  base tree) and are unchanged by it. Their root causes were **not** investigated further.
- `tests/test_fanout_prompt_phase.py` hangs on the pristine base tree in this environment; its
  behaviour under PD-208 is therefore unknown. It does not import the changed behaviour path (it
  stubs `deepseek_complete`), but I did not observe it pass.
- The 56-file census is **partial**: both trees blocked at 237 of 803 collected tests (details in
  §7). Tests 238–803 were not observed on either tree.
- No live run of the presentation pipeline was performed (spec: "files and stubbed tests only").
- Design note, not a defect: the binary helper's failure text says `not a PDF`. `magic` is a
  parameter, so a future non-PDF registration would inherit that wording. All three registrations
  this unit makes are PDFs, and the acceptance row requires the literal string `not a PDF`, so I
  left the wording specific rather than invent a generic label for no current caller.
