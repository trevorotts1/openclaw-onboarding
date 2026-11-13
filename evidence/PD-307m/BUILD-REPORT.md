# PD-307m — build report

**Unit:** PD-307m — The webinar video step declares the audio it needs
**Lane:** FL04 · branch `pd/fl04-manifest` · worktree `/Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL04`
**Commit:** `4243522a599e5e921dd154949068efdf226c6624`
**Base at start:** `fe19a5d25` (PD-021, accepted-in-progress) on top of `98a3ff093` (PD-038, ACCEPTED)
**Rows:** A1, A2, A3, A4 — all delivered.

## Change

`P9.6-WEBINAR-VIDEO` now declares `working/delivery/PRESENTER-AUDIO.mp3` in its
`consumes` list, because `build_webinar_video.resolve_required_inputs`
(lines 269-302, `raise WebinarBuildError(f"presenter audio not found: ...")`)
refuses to run without it while the artifact DAG never made it wait for the
producer (`P9-DELIVER`). One line added at
`universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json:1900`.
Nothing else in the phase changed (name, order, executor, gates, produces_artifact
untouched).

## Files changed

| File | Change |
|---|---|
| `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` | +1 line: audio entry in `P9.6-WEBINAR-VIDEO.consumes` |
| `universal-sops/presentation-slide-craft/MANIFEST-SOURCE.txt` | restamp (`content_sha256`, `generated`) |
| `universal-sops/_content-manifest.json` | regenerated (`generated_at`, 2 sha/bytes rows) |

`git diff --stat` for the build commit: 3 files changed, 6 insertions(+), 5 deletions(-).

## Commands run and results

Manifest edited in place with the repo's own serializer so the diff is exactly one
line (verified first that `json.dumps(obj, indent=2, ensure_ascii=False) + "\n"`
reproduces the checked-in bytes exactly):

```
python3 -I -  # json.load -> insert consumes[2] -> json.dumps(indent=2, ensure_ascii=False)+"\n"
consumes now: ['renders/slide-*.png', 'working/deliverables/PRESENTERS-SPEECH.md',
               'working/delivery/PRESENTER-AUDIO.mp3', 'working/checkpoints/slide_media_manifest.json']
```

Derived docs regenerated with the repository's own tool (never hand-edited):

```
$ python3 -I scripts/ci/phase_doc_sync.py --write
phase_doc_sync: manifest universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json -> manifest_version 75, 56 phases
  unchanged 23-ai-workforce-blueprint/templates/role-library/presentations/00-START-HERE.md
  unchanged universal-sops/presentation-slide-craft/SOP-SLIDE-05-PROCESS-MANIFEST.md
  unchanged 23-ai-workforce-blueprint/templates/role-library/presentations/DEPARTMENT-COUNTS-CANONICAL.md
  unchanged 23-ai-workforce-blueprint/templates/role-library/presentations/qc-specialist-prompt-presentations.md
  unchanged 23-ai-workforce-blueprint/templates/role-library/presentations/director-of-presentations.md
  unchanged 23-ai-workforce-blueprint/templates/role-library/presentations/pptx-assembly-specialist.md
  unchanged 23-ai-workforce-blueprint/templates/role-library/presentations/slide-image-creator.md
rc=0
```

(The generated regions restate names, order, version and count only; a `consumes`
edit changes none of them, so the tools correctly wrote nothing.)

```
$ python3 -I scripts/hash-universal-sops-manifest.py
OK wrote universal-sops/_content-manifest.json (116 files)
rc=0
```

`MANIFEST-SOURCE.txt` restamped from the manifest bytes:

```
content_sha256=6b6610bd7e4085b5df9248be8afdb73093a9f1f451e54d774600bad1f16664d2
generated=2026-11-13T00:11:55Z
```

## Acceptance rows

Script: `/Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-307m/check_rows.py`
(control manifest materialized at
`/Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-307m/MANIFEST-head-control.json`
= `git show HEAD:...PIPELINE-MANIFEST.json`, sha `9e0bfc79…8b65c`).

```
$ python3 -I .../scratchpads/PD-307m/check_rows.py
A1 parsed_manifest_has_entry=True consumes=['renders/slide-*.png',
   'working/deliverables/PRESENTERS-SPEECH.md', 'working/delivery/PRESENTER-AUDIO.mp3',
   'working/checkpoints/slide_media_manifest.json']
A2 edited_edge P9-DELIVER->P9.6-WEBINAR-VIDEO=True
A2 control_edge(HEAD manifest)=False (must be False)
A4 order_checker_rc=0 no_producer_rows_for_audio=0
ROWS: PASS
rc=0
```

- **A1** — parsed manifest shows the new entry. PASS.
- **A2** — `presentation_job.execution_plan.build_edges` on the edited manifest has
  the edge `P9-DELIVER -> P9.6-WEBINAR-VIDEO`; on the unedited HEAD manifest it has
  none (control). PASS.
- **A3** — `python3 -I .../presentations/scripts/sync_check.py` → `IN SYNC`,
  `rc=0` (manifest_version 75, 56 phases, 196 autofails, 36 roles). PASS.
- **A4** — `python3 -I scripts/ci/pd_manifest_order_check.py --manifest …` → `PASS:
  no DEFER_TRAP or NO_PRODUCER row in any election set.`, `rc=0`; zero
  `NO_PRODUCER` rows naming `PRESENTER-AUDIO.mp3`. PASS.

Lockstep side-checks (both rc=0):
`python3 -I scripts/ci/phase_doc_sync.py --check` and
`python3 -I scripts/hash-universal-sops-manifest.py --check`.
GATE 2a sha comparison: recorded `6b6610bd…664d2` == computed `6b6610bd…664d2`.

Narrow tests in the folders touched (rule 15 census):

```
$ python3 -I -m pytest -q .../tests/test_pd_manifest_defer_trap.py \
      .../tests/test_manifest_assert.py .../tests/test_manifest_workers_field.py
16 passed
$ python3 -I -m pytest -q .../tests/test_fix32_manifest_copy_drift.py \
      .../tests/test_l11_webinar_executor_no_recursion.py
20 passed
```

No existing assertion was made false; nothing was updated, weakened or deleted.

## Hunk attribution

Every hunk in `4243522a5` belongs to PD-307m. The branch also carries the two
preceding units' hunks, untouched by this commit:

- `98a3ff093` — PD-038 (ACCEPTED): manifest defer-trap checker and CI wiring,
  `defers_unless` on the sales/checkout and VSL build phases.
- `fe19a5d25` — PD-021 (building at dispatch time): `P-SP-INTAKE` name and
  `preflight.label` rename, plus its START-HERE / MANIFEST-SOURCE /
  `_content-manifest.json` restamps.

This commit's `MANIFEST-SOURCE.txt` + `_content-manifest.json` rows rewrite the
sha and timestamp values those two units last wrote; the surrounding values are
recomputed from the current file, not from theirs. No PD-038 or PD-021 hunk was
reverted or edited.

## Deviation from SOP-SLIDE-06 §4, reported not hidden

`manifest_version` was **not** bumped (stays 75). A bump requires editing the two
mirror constants, both outside this unit's owned paths:

- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/manifest.py:1018`
  (`MIN_MANIFEST_VERSION = 75  # MUST EQUAL PIPELINE-MANIFEST.json's manifest_version`)
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/manifest_assert.py:63`
  (same value, same comment)

`tests/test_client_package.py:319,361` and `tests/test_manifest_assert.py:27` assert
that equality, so bumping the manifest alone would fail the suite. The lane's
predecessor units did the same: PD-021 (`fe19a5d25`) and PD-038 (`76afd8c11`) both
changed manifest content at version 75 without a bump. If the orchestrator wants the
version bumped, that is a three-file change (`PIPELINE-MANIFEST.json`, `manifest.py`,
`manifest_assert.py`) plus one `MANIFEST-SOURCE.txt` restamp and it needs a unit that
owns the two script paths.

## Acceptance-row status

| Row | Status |
|---|---|
| A1 | delivered |
| A2 | delivered (edited edge present, control absent) |
| A3 | delivered |
| A4 | delivered |

Unit delivered in full against the four rows the spec names.
