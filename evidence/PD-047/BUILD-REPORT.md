# PD-047 — BUILD REPORT

**Unit:** PD-047 · **Lane:** FL04 · **Branch:** `pd/fl04-manifest`
**Commit:** `f83cefb75fefde7c7f396981256808f2a32505b3`
**Base:** `584cd958382dc8d1baadb7aaa6325897eaf066e8` (PD-034, ACCEPTED)
**Built:** 2026-11-12, US Eastern

---

## What changed

Eleven sales-package phases carried **no `sop_refs` at all**, so an agent dispatched into any of
them had nothing to read. Each is now wired to the procedure that actually governs it, after
reading all three procedures in full.

### `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json`

`sop_refs` added (inserted directly after `owning_role`, so the diff is 3 lines per phase):

| Phase | `sop_refs` set to |
|---|---|
| `P-U-SALES-COPY` | `["SALES-CHECKOUT-BUILDER-SOP.md"]` |
| `P-U-CHECKOUT-COPY` | `["SALES-CHECKOUT-BUILDER-SOP.md"]` |
| `P-U-BRIEF-SALES` | `["SALES-CHECKOUT-BUILDER-SOP.md"]` |
| `P-U-QC` | `["SALES-CHECKOUT-BUILDER-SOP.md", "VSL-BUILDER-SOP.md"]` |
| `P-U-COLLATERAL` | `["SALES-CHECKOUT-BUILDER-SOP.md", "VSL-BUILDER-SOP.md"]` |
| `P-U-VSL-RESEARCH` | `["VSL-BUILDER-SOP.md"]` |
| `P-U-VSL-COPY` | `["VSL-BUILDER-SOP.md"]` |
| `P-U-BRIEF-VSL` | `["VSL-BUILDER-SOP.md"]` |
| `P-U-FORM-GATE` | `["GHL-EXTERNAL-INSTALLER-SOP.md"]` |
| `P-U-GHL-SALES` | `["GHL-EXTERNAL-INSTALLER-SOP.md"]` |
| `P-U-GHL-VSL` | `["GHL-EXTERNAL-INSTALLER-SOP.md"]` |

**Amendment (b), finding PD-102:** `WEBINAR-BUILDER-SOP.md` appended to `P9.6-WEBINAR-VIDEO`'s
`sop_refs` (was `["media-librarian-ghl-updater-sops.md"]`, which carries no webinar procedure).

**Amendment (c):** `ecosystem/gate-form.json` and `workflows/gate-workflow.json` removed from
`P-U-GHL-SALES` `consumes`. Condition verified at
`23-ai-workforce-blueprint/templates/role-library/presentations/scripts/ghl_external_installer.py:693-697`:

```python
def _input_files(run_dir: Path, phase_id: str) -> List[Path]:
    if phase_id == PHASE_GHL_SALES:
        return [run_dir / "working" / "sales-checkout" / "html" / "sales.html",
                run_dir / "working" / "sales-checkout" / "html" / "checkout.html"]
```

Still just the two page files — so the two gate-form entries were stale and were removed.
`P-U-GHL-VSL` keeps both: its gate form is a real input (installer SOP §4, `SKILL44_WIDGET`).

### `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_manifest_sop_refs.py` (new)

Four checks: (1) no phase has empty `sop_refs`, allow-list none; (2) every named file exists in
the department `sops/` dir or the slide-craft folder; (3) the eleven-phase mapping is pinned, so an
existing-but-wrong file cannot pass (1) and (2); (4) `P9.6-WEBINAR-VIDEO` names its webinar
procedure. `PD_MANIFEST_PATH` reroutes every check against another manifest, which is how the
control below runs.

### `MANIFEST-SOURCE.txt` + `universal-sops/_content-manifest.json`

Restamped for the content change, per their own generators.

---

## Commands and results

### Lockstep gates, after the change

```
$ python3 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/sync_check.py
manifest_version: 75
phases: 56  autofails: 196  roles: 36
IN SYNC — the Python renderer, the MASTER ruleset Section-5 table, the role roster, and the SOP set all match PIPELINE-MANIFEST.json.
rc=0

$ python3 scripts/ci/phase_doc_sync.py --check
phase_doc_sync: manifest universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json -> manifest_version 75, 56 phases
PHASE_DOC_SYNC_PASS: every phase table and version marker matches manifest_version 75 (56 phases).
rc=0

$ python3 scripts/hash-universal-sops-manifest.py --check
PASS: universal-sops content manifest clean (116 files, all sha256 match)
rc=0

$ python3 scripts/ci/pd_manifest_order_check.py --manifest universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json
manifest_version=75 phases=56
rc=0
```

`sync_check.py` also enforces **A7** (every `sop_refs` file must exist in the sops dir) — it is
the mechanical version of the new test's check (2), and it passes.

### Acceptance pair (A1)

```
$ cd .../presentations/scripts
$ python3 -m pytest tests/test_pd_manifest_sop_refs.py -q
....                                                                     [100%]
4 passed in 0.03s
rc=0
```

Control — the same test against the **parent** manifest (`git show HEAD^:...PIPELINE-MANIFEST.json`,
saved to scratch):

```
$ PD_MANIFEST_PATH=<scratch>/unedited-manifest.json python3 -m pytest tests/test_pd_manifest_sop_refs.py -q
FAILED tests/test_pd_manifest_sop_refs.py::test_every_phase_names_at_least_one_procedure
FAILED tests/test_pd_manifest_sop_refs.py::test_the_sales_package_phases_name_the_procedure_that_governs_them
FAILED tests/test_pd_manifest_sop_refs.py::test_the_webinar_video_names_its_webinar_procedure
3 failed, 1 passed in 0.04s
rc=1
```

The one that passes on the parent is check (2): every ref the parent *did* have resolved fine — the
defect was absence, not dangling names. That is the control proving the right thing.

### Regression, manifest-adjacent tests

```
$ python3 -m pytest tests/test_pd_manifest_defer_trap.py tests/test_manifest_assert.py \
    tests/test_fix32_manifest_copy_drift.py tests/test_manifest_workers_field.py \
    tests/test_client_package.py tests/test_engine_client_report.py -q
73 passed, 1 skipped in 1.27s
rc=0
```

---

## Amendment (d) — the `P8.25-WORKBOOK` speech question (report, do not change)

**Answer: the workbook degrades; it does not fail when the speech is absent.**

`workbook_mapper.py:403-404`:

```python
speech_path = del_dir / "speech_spec.json"
speech = _read_json(speech_path) if speech_path.exists() else {}
```

Absent file → `{}`, no raise. `_speech_lines()` (`workbook_mapper.py:259-281`) iterates
`speech_spec.get("stages") or []` and, on an empty spec, returns `[]` — the call site at line 669
(`speech_quotes = _speech_lines(...)`) simply contributes no quote lines.

**So `P8.25-WORKBOOK` does not need to consume the speech to avoid a crash.** Whether it *should*
consume it is a content decision, not a correctness one: without the speech the workbook loses its
verbatim spoken one-liners and its `?`-bearing spoken questions (`_questions_from_ledgers`, line
715), so a workbook built before the speech exists is thinner, not broken. Reported only — the
manifest's `P8.25-WORKBOOK` `consumes` was left untouched, per the amendment.

---

## Decisions and deviations

**No `manifest_version` bump.** SOP-SLIDE-06 §4 says a manifest change must bump the version, but
**spec rule 7 is binding and wins**: "No version bumps, no `CHANGELOG.md`, no version markers. The
batch engine bumps once per batch." Branch precedent agrees — PD-021 (`fe19a5d25`), PD-307m
(`4243522a5`) and PD-018a (`b78085f9e`) each changed this manifest and left it at v75, restamping
`MANIFEST-SOURCE.txt` only.

A bump was tried and reverted; it forces edits outside this unit's owned paths and files that would
have been red for a reason PD-047 does not own:

- `presentation_job/manifest.py:1018` and `manifest_assert.py:63` — `MIN_MANIFEST_VERSION = 75`
  "MUST EQUAL PIPELINE-MANIFEST.json's manifest_version"; a bump to 76 makes
  `test_client_package.py::test_min_manifest_version_matches_repo_manifest_file` and
  `::test_assert_manifest_current_accepts_bumped_and_rejects_one_version_below` fail.
- `phase_doc_sync.py --write` then rewrites 7 docs (the generated region of `00-START-HERE.md`,
  `SOP-SLIDE-05`, `DEPARTMENT-COUNTS-CANONICAL`, and the version markers in
  `director-of-presentations.md`, `pptx-assembly-specialist.md`, `slide-image-creator.md`,
  `qc-specialist-prompt-presentations.md`). Measured: with the bump, `phase_doc_sync --check`
  exited 1 listing all seven; without it, exit 0 and zero doc edits.

Both were reverted. The batch engine bumps; this unit does not.

**Hooks.** This clone has no `core.hooksPath` and only `.sample` files under
`clones/onboarding/.git/hooks/`, so no repository hook was in play on the commit. The three
pre-commit-equivalent gates (`sync_check.py`, `hash-universal-sops-manifest.py --check`,
`phase_doc_sync.py --check`) were run by hand and all exit 0 — see the results above.

**Owned-path note.** Amendment says "report each file before editing it." Files edited:
`PIPELINE-MANIFEST.json`, `MANIFEST-SOURCE.txt` (both listed in `owned_paths`),
`tests/test_pd_manifest_sop_refs.py` (matches `test_pd_manifest_*.py`), and
`universal-sops/_content-manifest.json` (not in `owned_paths`; it is the hash registry every
`universal-sops/` change must restamp, and `phase_doc_sync.py --write` itself prints that
instruction). Reported, not silent.

---

## Pre-existing commits on this branch (not mine, left untouched)

| Commit | Unit | What |
|---|---|---|
| `584cd9583` | PD-034 | the generated block in `00-START-HERE.md`, ACCEPTED |
| `4ecf384c8` | PD-050 | two test renames |
| `b64fb8cd5` | PD-018a | build report with sha, files and check output |
| `b78085f9e` | PD-018a | plain client labels and visibility on every manifest phase |
| `4243522a5` / `fe19a5d25` | PD-307m | presenter audio as an input of the webinar video step |
| `98a3ff093` | PD-038 | qc fix A3 control to gate level |

---

## Files changed by this unit

- `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` (+38 −4)
- `universal-sops/presentation-slide-craft/MANIFEST-SOURCE.txt` (restamp)
- `universal-sops/_content-manifest.json` (restamp)
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_manifest_sop_refs.py` (new, 173 lines)
