# PD-108 — build report

**Unit:** PD-108 — The workbook procedure cites no operator folder
**Builder:** deepseek-chain (build and prove only; no verdict)
**Repo:** trevorotts1/openclaw-onboarding
**Branch:** `pd/fl24-role-procedures-c`
**Lane clone:** `<project-root>/pd-fix/worktrees/onboarding/FL24` (left clean — see §8)
**Build commit:** `871d96010f5224c4c1e2b0a395b78fd3b8fe8aa1`
**Remote head after the code push:** `871d96010f5224c4c1e2b0a395b78fd3b8fe8aa1`
**Remote head at the end:** the report commit you are reading, whose sha cannot appear inside itself.
The measured 40-character remote head is stated in the returned build report and in §8's read-back.
**Depends on:** PD-102 (passed) ✓

---

## 1. Spec quoted

From `<project-root>/fable-reviews-2026-11-11/03-presentation-department/FINAL/01-BUILD-SPEC.md`,
section `### PD-108`:

> **Read first — consolidation amendments (binding; they override the carried-over text below wherever the two differ):**
>
> The question for the manifest lane (should the workbook step wait for the speech) is already carried by PD-047; do not file it again.

> - **Build unit PD-108 (Moderate, Haiku: exact replacements in one file; lane FL24).** In `WORKBOOK-BUILDER-SOP.md` delete the two `~/Downloads/GAUNTLET-LOOP-WORK/` references (keep the sentence about what this procedure supersedes); replace `saved to ~/Downloads` with `saved to a scratch folder the operator names`; under the sources table add: `The engine starts this phase when the deck, the intake and the copy exist. The speech rows are used when present.` File to FL04: "should P8.25 consume the speech?" with the mapper's behavior once read. Acceptance: no path beginning `~/` remains in the file (read it).

| Field | Value |
|---|---|
| Acceptance rows the checker must run | **A1** |
| Live-action flag | none: files and stubbed tests only |
| Existing tests it breaks and must update | none known in advance |

Three instructions, plus the binding amendment:

1. Delete the two `~/Downloads/GAUNTLET-LOOP-WORK/` references, keeping the supersedes sentence.
2. `saved to ~/Downloads` → `saved to a scratch folder the operator names`.
3. Under the sources table, add the two-sentence engine/speech statement.
4. **Amendment:** do **not** file the "should the workbook step wait for the speech?" question — PD-047 already carries it. Honoured: no such question was filed, and no file to FL04 was written (see §7).

---

## 2. Files changed

One product file, one evidence file. Nothing else.

```
23-ai-workforce-blueprint/templates/role-library/presentations/sops/WORKBOOK-BUILDER-SOP.md   10 ++++---
evidence/PD-108/check_pd108.py                                                              65 +++++++
2 files changed, 71 insertions(+), 4 deletions(-)
```

Product file: **+6 / −4**, single file, exactly the four edits in §3.

---

## 3. A1 — proven

### 3.1 The command

`evidence/PD-108/check_pd108.py` — a runnable, assert-based check. Each row is a plain substring test on
line text; **no fnmatch / glob anywhere**, so no path separator can silently defeat a pattern (the
failure mode called out in the task).

It reports, and fails on:

| Row | Meaning |
|---|---|
| `A1 lines containing '~/'` | must be **0** — the acceptance row verbatim |
| `GAUNTLET-LOOP-WORK lines` | must be **0** — the two deleted references stay deleted |
| `R-scratch` | `saved to a scratch folder the operator names` present exactly **1** time |
| `R-sources` | the new engine/speech sentence present exactly **1** time |
| `R-supersede` | `the piece this SOP supersedes` still present exactly **1** time (guards the "keep the sentence" half of edit 1 — it fails if the whole research line is deleted) |

### 3.2 BEFORE — base `c358ea2ee51a75bf495213d3a7b12b861ddc5b10`, RED

```
SOP: 23-ai-workforce-blueprint/templates/role-library/presentations/sops/WORKBOOK-BUILDER-SOP.md
lines: 186
A1 lines containing '~/': 4
GAUNTLET-LOOP-WORK lines: 2
R-scratch: 0 (want 1)
R-sources: 0 (want 1)
R-supersede: 1 (want 1)

FAIL
  - A1 home path: 4 line(s) still contain '~/': L8; L9; L165; L173
  - GAUNTLET-LOOP-WORK: 2 line(s) still reference it: L8; L9
  - R-scratch: expected 1 occurrence(s) of 'saved to a scratch folder the operator names', found 0
  - R-sources: expected 1 occurrence(s) of 'The engine starts this phase when the deck, the intake and the copy exist. The speech rows are used when present.', found 0
EXIT=1
```

The four base `~/` lines, quoted from the base blob:

| Line | Base text |
|---|---|
| 8 | `**Research:** \`~/Downloads/GAUNTLET-LOOP-WORK/WORKBOOK-PDF-RESEARCH.md\` (its §4.2 "background only"` |
| 9 | `conclusion is the piece this SOP supersedes) + \`~/Downloads/GAUNTLET-LOOP-WORK/WORKBOOK-REDESIGN-PLAN.md\`.` |
| 165 | `  account and saved to \`~/Downloads\`. No client messaging.` |
| 173 | `    --out ~/Downloads/WORKBOOK-SAMPLE.pdf --no-upload` |

**Discrepancy named, not smoothed over:** the spec's change list names only three of these — the two
research references and the `saved to ~/Downloads` line. Line 173 (`--out ~/Downloads/WORKBOOK-SAMPLE.pdf`)
is a **fourth** home-anchored path the change list does not mention, and A1 ("no path beginning `~/`
remains in the file") cannot hold while it stays. It was therefore changed to
`--out <SCRATCH>/WORKBOOK-SAMPLE.pdf`, matching the `<SCRATCH>` convention PD-100 already uses for its
dry-run command. This is the only edit not literally named in the change list; it exists because the
acceptance row is binding and the change list alone could not satisfy it.

### 3.3 AFTER — head `871d96010f5224c4c1e2b0a395b78fd3b8fe8aa1`, GREEN

```
SOP: 23-ai-workforce-blueprint/templates/role-library/presentations/sops/WORKBOOK-BUILDER-SOP.md
lines: 188
A1 lines containing '~/': 0
GAUNTLET-LOOP-WORK lines: 0
R-scratch: 1 (want 1)
R-sources: 1 (want 1)
R-supersede: 1 (want 1)

PASS: all PD-108 rows hold
EXIT=0
```

Independent confirmation with a second instrument:

```
$ grep -c '~/' 23-ai-workforce-blueprint/templates/role-library/presentations/sops/WORKBOOK-BUILDER-SOP.md
0
grep rc=1
```

(`rc=1` is grep's "no lines selected" — the correct result for zero matches. The same command returned
`4` on the base blob, so the instrument is proven to discriminate; `rc=2` — a real error — never occurred.)

### 3.4 The four edits, head line numbers and final text

| # | Head line | Final text |
|---|---|---|
| 1 | 8–9 | `**Research:** the workbook research notes and the workbook redesign plan (the "background only"`<br>`conclusion is the piece this SOP supersedes).` |
| 2 | 51 | `The engine starts this phase when the deck, the intake and the copy exist. The speech rows are used when present.` |
| 3 | 167 | `  account and saved to a scratch folder the operator names. No client messaging.` |
| 4 | 175 | `    --out <SCRATCH>/WORKBOOK-SAMPLE.pdf --no-upload` |

Edit 1 keeps the supersedes sentence (spec: "keep the sentence about what this procedure supersedes") and
drops both `~/Downloads/GAUNTLET-LOOP-WORK/` paths — the paths were deleted, the conclusion was not.
Edit 2 sits **under the sources table**, immediately above `It produces:`.

### 3.5 Which commit makes each row hold

| Row | Commit |
|---|---|
| A1 (`~/` count 4 → 0) | `871d96010f5224c4c1e2b0a395b78fd3b8fe8aa1` — the only commit touching this file |
| GAUNTLET references 2 → 0 | `871d96010f5224c4c1e2b0a395b78fd3b8fe8aa1` |
| R-scratch 0 → 1 | `871d96010f5224c4c1e2b0a395b78fd3b8fe8aa1` |
| R-sources 0 → 1 | `871d96010f5224c4c1e2b0a395b78fd3b8fe8aa1` |
| R-supersede 1 → 1 (held) | `871d96010f5224c4c1e2b0a395b78fd3b8fe8aa1` |

Verified this file was **untouched on the branch** before my commit:

```
$ git diff --name-only 1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc c358ea2ee51a75bf495213d3a7b12b861ddc5b10 \
    -- '23-ai-workforce-blueprint/templates/role-library/presentations/sops/WORKBOOK-BUILDER-SOP.md'
(empty)
```

So no sibling unit contributed a string that could be mistaken for mine — the rows hold on my commit alone.

---

## 4. Failure proof — two mutations, each RED, each reverted

A row that cannot fail proves nothing, so each class of row was mutated and reverted.

### Mutation 1 — reintroduce a home-anchored path (tests the A1 and GAUNTLET rows)

Appended one line to the head file: `MUTATION-PROBE: see ~/Downloads/GAUNTLET-LOOP-WORK/probe.md`

```
A1 lines containing '~/': 1
GAUNTLET-LOOP-WORK lines: 1
R-scratch: 1 (want 1)
R-sources: 1 (want 1)
R-supersede: 1 (want 1)

FAIL
  - A1 home path: 1 line(s) still contain '~/': L190
  - GAUNTLET-LOOP-WORK: 1 line(s) still reference it: L190
EXIT=1
```

Reverted → `PASS: all PD-108 rows hold`, `EXIT=0`.

### Mutation 2 — remove the new sources-table sentence (tests the R-sources row)

Deleted the exact sentence plus its blank line, asserting the pre-state count was 1 before deleting:

```
FAIL
  - R-sources: expected 1 occurrence(s) of 'The engine starts this phase when the deck, the intake and the copy exist. The speech rows are used when present.', found 0
```

Reverted → `PASS: all PD-108 rows hold`, `EXIT=0`.

### Residue check after both reverts

```
$ shasum -a 256 <file> <pre-mutation backup>
7c6197843af488c4375784bdace77ba6c5ba95108fe4a38d1bd246ba8900943c  <file>
7c6197843af488c4375784bdace77ba6c5ba95108fe4a38d1bd246ba8900943c  <backup>

$ grep -c 'MUTATION-PROBE' <file>
0
```

Byte-identical to the pre-mutation head. No probe survives in the commit.

### Control-on-the-control

R-supersede read `1` on **both** base and head — it is a "must still hold" row, not a discriminator, and
is reported as such rather than dressed up as a before/after. It would fail if edit 1 deleted the whole
research line instead of just its paths, which is the mistake the spec's parenthetical guards against.

---

## 5. Tests by id — base and head

| Suite | Base `c358ea2ee` | Head `871d96010` |
|---|---|---|
| `…/presentations/scripts/tests/test_deliverables_gated_separately.py` (5) | 5 passed | 5 passed |
| `tests/unit/test_repair_placeholder_sops.py` (6) + `test_build_library_role_floor.py` (2) + `test_reconcile_role_floor.py` (4) | 12 passed, 68 subtests passed | 12 passed, 68 subtests passed |

Identical counts on both sides — no test was weakened, deleted, renamed, skipped or xfailed, and none
changed behaviour.

Test ids covered:

- `test_deliverables_gated_separately.py::test_bundle_spec_still_ten_and_excludes_gated_separately_keys`
- `…::test_gated_separately_constant_exists_and_covers_both_cases`
- `…::test_workbook_entry_cites_real_producing_phase_and_gate_codes` (this is the one that asserts `"WORKBOOK-BUILDER-SOP.md" in entry["sop"]` — the direct consumer of this file)
- `…::test_webinar_audio_entry_cites_real_producing_phase_and_gate_code`
- `…::test_citations_match_live_manifest_phase_records`
- `test_repair_placeholder_sops.py::TestRepairPlaceholderSops::` — `test_apply_repairs_and_protects`, `test_clean_box_exits_zero`, `test_dry_run_writes_nothing`, `test_idempotent`, `test_missing_departments_dir`, `test_symlinked_how_to_never_touched`
- `test_build_library_role_floor.py::TestBuildMeetsLibraryFloor::` — `test_folders_use_library_slugs_and_cover_the_library`, `test_second_build_adds_nothing`
- `test_reconcile_role_floor.py::TestReconcileRoleFloor::` — `test_apply_meets_floor_keeps_howtos_and_is_idempotent`, `test_dry_run_changes_nothing`, `test_floor_departments_never_include_other_clients_lanes`, `test_library_mode_reaches_prover_floor_with_declines_aliases_and_industry_gate`

### Census reading (rule 15) — what consumes this file

| Consumer | Relationship | Effect of this change |
|---|---|---|
| `23-ai-workforce-blueprint/templates/role-library/_index.json` (slug `WORKBOOK-BUILDER-SOP`) | carries `content_sha`, `content_version` | **Pre-existing drift, not mine.** Pinned sha is `sha256:fed7ceba…`; the file hashed `f5a5b285…` at base, before I touched it. My change moves it to `7c619784…`. `_index.json` is not in PD-108's owned paths and is not restamped — flagged in §7. |
| `…/presentations/DEPARTMENT-COUNTS-CANONICAL.md` line 130 | quotes §0 verbatim (`"TWO PDFs…"`) | §0 untouched — no effect |
| `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` line 1460 | lists the filename | name unchanged — no effect |
| `…/presentations/scripts/presentation_job/deliverables.py` | `sop` field names the file | name unchanged — no effect |
| Any test asserting this file's **body text** | none found | — |

No test in the repo asserts the body text of `WORKBOOK-BUILDER-SOP.md`; only its filename and its §0
quote. Both are untouched.

---

## 6. Hunk attribution — merge-base to HEAD

Merge base with `origin/main`: `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc` (`origin/main` head at read time:
`ebf5c769a2ad5b2582bf2256588095cbef20cfac`).

### Sibling units' hunks on this branch (before mine)

| Unit | Commits | Files (product hunks) |
|---|---|---|
| **PD-094** | `baf3f5dbb`, `bce9febf5`, `e649f7f57`, `579c937ae` | `slide-image-creator.md`, `sops/slide-image-creator-sops.md`, `typography-architect.md`, `sops/typography-architect-sops.md` |
| **PD-093** | `66bf69c97`, `7381bff56`, `e9fb04930`, `cd9a9f003`, `16988928f` | `pptx-assembly-specialist.md`, `sops/pptx-assembly-specialist-sops.md` |
| **PD-101** | `80e5bc392`, `054c77ef2`, `f6ad943c5`, `ac6c3a86a` | `audio-demonstration-specialist.md`, `sops/audio-demonstration-specialist-sops.md` |
| **PD-102** | `3236c7705`, `88dc5c45a`, `3538e19ca`, `c358ea2ee` | `media-librarian-ghl-updater.md`, `sops/media-librarian-ghl-updater-sops.md` |

Branch total before mine: 13 files, **+1212 / −223** (includes `evidence/PD-093/`, `evidence/PD-101/`,
`evidence/PD-102/` build reports).

**No sibling hunk is on my file.** `WORKBOOK-BUILDER-SOP.md` appears in zero of the 17 pre-existing
commits — proven by the empty `git diff --name-only` in §3.5.

### My hunk

| Commit | Files | Size |
|---|---|---|
| `871d96010f5224c4c1e2b0a395b78fd3b8fe8aa1` | `sops/WORKBOOK-BUILDER-SOP.md`, `evidence/PD-108/check_pd108.py` | +71 / −4 |

---

## 7. Unproved / out of scope — stated plainly

1. **`_index.json` `content_sha` is stale and remains stale.** The pinned `sha256:fed7ceba…` did not match
   the file at base (`f5a5b285…`) — that drift predates this unit. `_index.json` is not in PD-108's
   owned paths, so it was **not** touched. Whoever owns the restamp should note this entry needs it
   (it also needs it for the pre-existing drift, independent of me). **Not a VERIFIED NO-OP — an
   unperformed, out-of-scope action.**
2. **"File to FL04: 'should P8.25 consume the speech?'" was NOT filed.** Two reasons, both binding:
   the **consolidation amendment** states the question is already carried by PD-047 and says *"do not
   file it again"*; and FL04 is another lane's worktree, outside my owned paths. **Read the mapper anyway**,
   because the amendment asks for its behaviour once read:
   `scripts/workbook_mapper.py:404` — `speech = _read_json(speech_path) if speech_path.exists() else {}`,
   and `_speech_lines()` iterates `speech_spec.get("stages") or []` (line 269), returning `[]` when there
   is no speech. So **the mapper already consumes the speech only when present**, which is exactly what
   the sentence I added now states. The SOP and the code agree. The question for FL04 therefore reads:
   *not "should it?", but "the mapper is already tolerant — confirm the phase gate should not require
   speech"* — recorded here for PD-047's owner; not filed.
3. **Docs-only, so no runtime behaviour is claimed.** A1 is a file-content row and is proven by reading
   the file through a fail-able check. I claim nothing about the workbook builder executing differently.
4. **The `<SCRATCH>` substitution for line 173 is my judgement**, not literal spec text (§3.2 explains
   why it was unavoidable). A reviewer who wants different wording can change one line.

---

## 8. Remote-head proof and lane hygiene

```
$ git ls-remote --heads origin refs/heads/pd/fl24-role-procedures-c
871d96010f5224c4c1e2b0a395b78fd3b8fe8aa1	refs/heads/pd/fl24-role-procedures-c

$ git rev-parse HEAD
871d96010f5224c4c1e2b0a395b78fd3b8fe8aa1
```

That is the proof for the **code** commit. The final remote head is the report commit itself; its
40-character sha is measured after the push and stated in the returned build report, because a commit
cannot contain its own sha.

Push was a fast-forward: local parent `c358ea2ee51a75bf495213d3a7b12b861ddc5b10` equalled the remote head
read immediately before the push, and `--force-with-lease` was pinned to that sha.

**The artefact at the remote sha was then read back and checked** (not my local tree):

```
remote sha: 871d96010f5224c4c1e2b0a395b78fd3b8fe8aa1
remote file sha: 7c6197843af488c4375784bdace77ba6c5ba95108fe4a38d1bd246ba8900943c
A1 lines containing '~/': 0
GAUNTLET-LOOP-WORK lines: 0
R-scratch: 1 (want 1)
R-sources: 1 (want 1)
R-supersede: 1 (want 1)
PASS: all PD-108 rows hold
EXIT=0
```

Blob sha of the product file at the pushed commit:
`e4b88ad9a303a8ecccf83c55d95fef3335db680b`

**Lane clone untouched.** All work happened in a scratch worktree created under
`<project-root>/pd-fix/tmp/PD-108/wt.1794579788` at the remote head. The lane clone's
`FL24` worktree was read only; `git status --porcelain` on it was empty before and after. No file was
written under `/tmp`, `/private/tmp` or `/var/folders`; every scratch path was made with
`mktemp -p "$TMPDIR"`.

| Metric | Value |
|---|---|
| Files changed | 2 (1 product, 1 evidence) |
| Product-file diff | +6 / −4 |
| `~/` lines, base → head | 4 → **0** |
| GAUNTLET-LOOP-WORK lines, base → head | 2 → **0** |
| Mutations run / reverted | 2 / 2 |
| Tests, base → head | 17 passed (+68 subtests) → 17 passed (+68 subtests) |
| Build commit | `871d96010f5224c4c1e2b0a395b78fd3b8fe8aa1` |
| Remote head | `871d96010f5224c4c1e2b0a395b78fd3b8fe8aa1` |
