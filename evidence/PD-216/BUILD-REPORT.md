# PD-216 — BUILD REPORT

**Unit:** PD-216 · Lane FL30 · repo `trevorotts1/openclaw-onboarding`
**Branch:** `pd/fl30-path-table--hold-d12` (D-12 HOLD — build and stage, never merge)
**Base:** `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`
**Dependencies:** PD-062 (`11ce373dffdea8b0ccd31df5317512047c9e9417`), PD-064
(`bc264097b` branch head). Both accepted (IN_BATCH), neither merged to main.

## Spec quoted

Section `### PD-216 — One path table that matches the producers, and a PDF exporter that finds the deck`,
`01-BUILD-SPEC.md` (presentation department FINAL):

> **Read first — consolidation amendments (binding; they override the carried-over text below wherever the two differ):**
> On the minimum path: without the finder change the PDF step cannot find the deck once PD-062 moves its declared path.
> The audit must pass on the manifest as edited by PD-062 and fail on the manifest as it is today (run both; that is the control).

> - **Change:** (1) `CANONICAL_PATHS`: `deck_pptx` → `working/deliverables/{deck_slug}-FINAL.pptx`, `deck_pdf` →
>   `working/deliverables/{deck_slug}-FINAL.pdf`; move the `working/delivery/` and run-top spellings into `ALIAS_PATHS`;
>   correct the comments at lines 72–88. (2) In `_audit_paths`, report every key whose manifest producer writes an alias
>   rather than the canonical path as a problem. (3) `pdf_export._find_pptx`: look in `working/deliverables/` first,
>   then the run top.
> - **Acceptance:** the PD-216 probes: deck only at `working/deliverables/` → found; audit on the corrected manifest → ok;
>   audit with one manifest path changed to an alias → fails naming it.

Acceptance rows: **A1** (ledger `acceptance_rows: ["A1"]`).

## Commits

- `1c6358215ede5691f6ab680fb9a8a0d5c131c941` — "PD-216: one path table that matches the producers, and a PDF exporter
  that finds the deck" — the code and the test. **Every row below is held by this commit.**
- a docs-only commit on top of it — this report. No code change; every row is held by `1c6358215`.

## Files changed

| File | Change |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/deliverable_paths.py` | canonical deck pair → `working/deliverables/`; old spellings into `ALIAS_PATHS`; comments corrected; `_audit_paths` reports alias-writing producers; `--manifest` seam |
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/pdf_export.py` | `_find_pptx` looks in `working/deliverables/` first, then the run top |
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_paths.py` | NEW — 10 tests covering both finder rows and the audit control pair |

No other file touched. `update-skills.sh`, `universal-sops/_content-manifest.json`, `install.sh` untouched.
`PIPELINE-MANIFEST.json` NOT edited (that is PD-062's owned path; this unit only reads it).

Diff size vs base: `deliverable_paths.py` +86/−39, `pdf_export.py` +8/−1, `test_pd_paths.py` new (10 tests).

## Row proofs (real output)

### R1 — deck only at `working/deliverables/` → found  (commit `1c6358215`)

Live run against real files in TMPDIR, `pdf_export._find_pptx` imported from the worktree:

```
empty -> None
only deliverables -> .../finder/run/working/deliverables/out-FINAL.pptx
both (deliverables wins) -> .../finder/run/working/deliverables/out-FINAL.pptx
```

Tests: `test_find_pptx_in_working_deliverables_only`, `test_find_pptx_prefers_producer_dir_over_run_top`,
`test_find_pptx_falls_back_to_run_top`, `test_find_pptx_none_when_absent`.

### R2 — audit on the corrected (PD-062) manifest → ok  (commit `1c6358215`)

PD-062's real manifest, read from its branch head `11ce373dffdea8b0ccd31df5317512047c9e9417`:

```
$ git show origin/pd/fl04-manifest--hold-d12:universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json > manifest-pd062.json
$ python3 presentation_job/deliverable_paths.py --audit --manifest manifest-pd062.json
...
all surfaces agree: manifest produces_artifact, phase_verifiers patterns, deliverables.DELIVERABLE_AUDIT_SPEC, build_deck.DELIVERABLES_REQUIRED
EXIT_PD062=0
```

### R3 — audit fails on the manifest as it is today, naming it (the control)  (commit `1c6358215`)

Same code, same tree, only the manifest differs:

```
$ python3 presentation_job/deliverable_paths.py --audit          # repo manifest at base
DISAGREEMENTS (1):
  - deck_pptx: manifest producer P8-ASSEMBLE writes the alias '{deck_slug}-FINAL.pptx', not the canonical path 'working/deliverables/{deck_slug}-FINAL.pptx'
EXIT_TODAY=1
```

### R4 — audit with one manifest path changed to an alias → fails naming it  (commit `1c6358215`)

Tests `test_audit_fails_naming_the_alias_a_producer_writes` (two cases, `P8-ASSEMBLE`/`deck_pptx` and
`P8.1-PDF-EXPORT`/`deck_pdf`) patch exactly one producer to the alias spelling and assert the problem names key + phase.
`test_audit_reports_todays_deck_pptx_spelling` is the shipped manifest's bare `*-FINAL.pptx` BEFORE row.
`test_audit_passes_on_the_pd062_manifest` is the AFTER row. Both manifest states are built from the repo manifest at
runtime, so the pair keeps its meaning after PD-062 merges.

### Integration with both dependencies present

Second worktree at PD-064's head `bc264097b` (its `_DELIVERY_PATTERN_BY_KEY` already declares
`working/deliverables/*-FINAL.pptx` / `.pdf`), my two files overlaid:

```
INTEG_TODAY_EXIT=1
  - deck_pptx: manifest producer P8-ASSEMBLE writes the alias '{deck_slug}-FINAL.pptx', not the canonical path 'working/deliverables/{deck_slug}-FINAL.pptx'
INTEG_PD062_EXIT=0
all surfaces agree: ...
10 passed
```

So the audit passes on PD-062's manifest with PD-064's verifier patterns in place, and still fails on today's manifest.

## Failure proof — mutations that turn the proof RED, then reverted

Each mutation applied to the worktree file, pytest run, file restored from a TMPDIR copy, restored state re-checked.

| # | Mutation | Result | Restored |
|---|---|---|---|
| M1 | `_find_pptx` reverted to the run-top-only one-liner | `2 failed, 8 passed` — `test_find_pptx_in_working_deliverables_only`, `test_find_pptx_prefers_producer_dir_over_run_top` | yes (`git diff --stat` back to +8/−1) |
| M2 | `CANONICAL_PATHS` deck pair reverted to `working/delivery/` | `3 failed, 7 passed` — `test_canonical_deck_paths_are_the_producers_paths`, `test_deliverable_path_expands_deck_slug`, `test_audit_passes_on_the_pd062_manifest` | yes (`RESTORED deck_pptx = working/deliverables/{deck_slug}-FINAL.pptx`) |
| M3 | alias-producer reporting loop removed from `_audit_paths` | `3 failed, 7 passed` — both `test_audit_fails_naming_the_alias_a_producer_writes` cases and `test_audit_reports_todays_deck_pptx_spelling` | yes |

The control can fail: M3 removes the new rule and the three audit rows go RED. The R2/R3 pair also differs only by the
manifest, and the same binary produced exit 0 and exit 1 in the same session.

Self-check on the control itself: the alias rule is guarded by `_same_artifact_alias` (slug-stripped basename
equality), so `PRESENTER-AUDIO-WEBINAR.mp3` under the `audio_mp3` key is not mistaken for the audio; without that guard
the pass row (R2) would fail on a correct manifest. That is why the guard exists — and R2 passing is the check on it.

## Tests by id

| | base `1a476d2cb` | head (this branch) |
|---|---|---|
| `test_deliverables_single_source.py` | collected | collected |
| `test_client_package.py` | collected | collected |
| `test_fix36_doc_code_reconcile.py` | collected | collected |
| `test_upload_gate.py` | collected | collected |
| `test_pd_paths.py` | absent on base | 10 new |
| **total** | **77 passed, 1 skipped** | **87 passed, 1 skipped** |

Command (same in both trees, only the file list differs by the new test):

```
python3 -m pytest -q <scripts>/tests/test_pd_paths.py <scripts>/tests/test_deliverables_single_source.py \
  <scripts>/tests/test_client_package.py <scripts>/tests/test_fix36_doc_code_reconcile.py <scripts>/tests/test_upload_gate.py
```

`test_upload_gate.py` and `test_deliverables_single_source.py` are the two existing suites that import
`delivery_gate` / `deliverable_paths`; no existing test was weakened, renamed, skipped or xfailed.

## Hunk attribution

`git diff 1a476d2cb..HEAD` on this branch contains only this unit's commit:
`presentation_job/deliverable_paths.py`, `pdf_export.py`, `tests/test_pd_paths.py`, `evidence/PD-216/BUILD-REPORT.md`.
No sibling-unit hunks on this branch (no other lane commits are on it).

## Remote head proof

Commit chain on `pd/fl30-path-table--hold-d12`, base `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`:

| commit | what |
|---|---|
| `1c6358215ede5691f6ab680fb9a8a0d5c131c941` | code + test — **every row is held by this commit** |
| `09d50d9543fb0900a2d2f0f680b87cde55f599ec` | this report |
| `5a60f54c9d4f902429e27dfe144f36d85b849666` | report wording (code commit named instead of the report's own sha) |
| `0f34aec35d5820f2f09660f4e71f51597f4764f6` | this remote-head section |

The remote head itself is the docs commit that carries this paragraph, so its literal sha is read at handback, not
written here (writing it would be a self-reference that changes on every commit):

```
$ git ls-remote --heads origin refs/heads/pd/fl30-path-table--hold-d12
<40-char sha>	refs/heads/pd/fl30-path-table--hold-d12
```

The pushed tree was re-checked from a clean checkout of the remote head (not the build tree): `10 passed`,
`AUDIT_TODAY_EXIT=1`, `AUDIT_PD062_EXIT=0`, and `git diff --stat base..HEAD` showing exactly the four files above.
The lane clone `/Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL30--hold-d12` was left clean and at
base (`git status --short` empty, `HEAD 1a476d2c`); all builds ran in worktrees under `$TMPDIR`.

## Unproved / observed, not fixed (not owned by this lane)

- `phase_verifiers.py:1615-1616`, `presentation_job/runfacts.py:1331-1332`, `verifier_registry.py:563-564` still
  hardcode `working/delivery/*-FINAL.pptx|pdf`. `phase_verifiers.py` is PD-064's file (its branch already fixes it,
  proven above in the integration tree); `runfacts.py` and `verifier_registry.py` are outside this unit's owned paths
  and were not edited. Reported here rather than touched.
- The audit still tolerates an alias on the `phase_verifiers` surface (`working/delivery/*-FINAL.pptx`) because the
  module-level comment documents that legacy glob; after PD-064 merges the pattern is canonical and the tolerance is
  unused for the deck pair. Removing the tolerance is a separate change and would break the pass row on a tree without
  PD-064.
