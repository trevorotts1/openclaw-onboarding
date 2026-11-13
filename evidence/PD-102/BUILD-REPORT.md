# PD-102 — BUILD REPORT

**Unit:** PD-102 · "The Media Librarian procedure agrees with itself" · Moderate · logic
**Lane:** FL24 · `trevorotts1/openclaw-onboarding` · branch `pd/fl24-role-procedures-c`
**Base:** `ac6c3a86a0e61b154b0c1cd05fc08376c521b6b1` (PD-101's accepted head — re-measured with `git ls-remote` before any edit, see §8)
**Build commits:** `3236c7705b73dee1ad59fdb1924b739763f7677d`, `88dc5c45ae7f916e4c6718eff510c4320fbcfe04`
**Report commit:** the commit that carries this file (its parent is `88dc5c45a`)
**Acceptance row built and proven:** A1
**Machine paths are written as `<PROJECT ROOT>` per spec rule 8 (no operator paths in committed files).**

---

## 1. The spec text this unit implements (quoted)

`01-BUILD-SPEC.md`, section `### PD-102`, carried-over unit text, quoted verbatim:

> - **Build unit PD-102 (Moderate, Sonnet; lane FL24).** Media Librarian role file: SOP 9.3 status
>   sentence becomes `Skipping is permitted only with the logged owner_skip_approval token described in
>   the box above.` Rename the folder step to `Resolve the media destination (software never creates a
>   folder)` and delete "CREATE"; delete "PPTX assembly can begin" in both places and say the upload runs
>   after assembly (manifest phase P9.2-GHL-UPLOAD); SOP 9.9's pointer becomes `WEBINAR-BUILDER-SOP.md`;
>   replace the `ls | wc` count with a Python listing; fix the landing-zone tree to the run folder the
>   engine uses (read `presentation_job` path helpers first). Also file to FL04 a one-line request: add
>   `WEBINAR-BUILDER-SOP.md` to P9.6's `sop_refs`. Acceptance: mirror regenerated; no sentence in the
>   file contradicts the header box (reviewer reads both).

The binding consolidation amendment above it:

> **Read first — consolidation amendments (binding; they override the carried-over text below wherever the
> two differ):** The request to add `WEBINAR-BUILDER-SOP.md` to the webinar video phase is already built
> into PD-047 (lane FL04); do not file it again.

**Amendment honoured:** the FL04 one-line request was **not** filed. `P9.6-WEBINAR-VIDEO`'s `sop_refs`
was not touched (it still reads `["media-librarian-ghl-updater-sops.md"]`; PD-047 owns that edit).

Unit table facts used: severity Moderate, wave 3, depends on PD-101, acceptance rows **A1**,
existing tests it breaks "none known in advance", live-action flag "none".

---

## 2. Files changed (both inside FL24's owned paths)

| File | +/− |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/media-librarian-ghl-updater.md` | +61 −48 |
| `23-ai-workforce-blueprint/templates/role-library/presentations/sops/media-librarian-ghl-updater-sops.md` (mirror) | +46 −35 |

`git diff --numstat ac6c3a86a..HEAD`: exactly those two paths, those two rows (`61 48 …`, `46 35 …`).
No other file was written.

---

## 3. What the engine actually says (measured before editing)

Read, not guessed — these are the facts the tree and the ordering were fixed against.

| Fact | Where it was read | Value |
|---|---|---|
| run directory is what `--run-dir` names, and it contains `working/` | `scripts/presentation-canonical-entry.sh` usage block | `--run-dir DIR  the deck run directory (contains working/)` |
| the engine's runs root | `presentation_job/launcher.py` `resolve_runs_root()` (line 536-539) | `scripts.parent / "runs"` |
| the shipped default runs root | `scripts/presentation-intake-poll.sh` line 327 | `${HOME}/.openclaw/workspace/departments/Presentations/runs` |
| workspace root on a VPS | `presentation_job/oc_paths.py` line 20 + `workspace()` | `VPS_ROOT = /data/.openclaw` → `/data/.openclaw/workspace` |
| extra roots are configuration, never a hardcoded path | `presentation_job/scan_roots.py` (module docstring, `SCAN_ROOTS_ENV`) | `PRESENTATION_SCAN_ROOTS`, default config `config/scan-roots.conf` |
| renders live at the run root, not under `working/` | `scripts/run_signature_deck.py` 372-374, `slide_craft.py` 555-560, `delivery_gate.py` 179 | `run_dir / "renders"` / `renders_dir.glob("slide-*.png")` |
| prompt files are `slide-NN.txt` | `presentation_job/dispatcher.py` 3425, `gates.py` 131,167 | `run_dir / "working" / "prompts" / f"slide-{ordinal:02d}.txt"` |
| the ledger is `working/checkpoints/media_library.json` | `ghl_media_push.py` `_LEDGER_REL` = `("working","checkpoints","media_library.json")` | as stated |
| the assembled deck is an engine deliverable, not `output/` | `presentation_job/deliverable_paths.py` `CANONICAL_PATHS` | `working/deliverables/{deck_slug}-FINAL.pptx`, `working/delivery/PRESENTER-AUDIO.mp3`, `working/delivery/{deck_slug}-WEBINAR.mp4` |
| `run_ledger.json` and `qc/finalrender/` do not exist in code | scanned all 795 `.py/.sh/.json` files under `presentations/scripts`, `intake`, `scripts/tests` | **0** files name `run_ledger.json`; **0** name `finalrender` |
| `local_workdir` / `local_media_library` are doctrine-only keys | same scan | **0** code readers (safe to correct the example values) |
| phase order | `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` (parsed, manifest_version 75) | `P8-ASSEMBLE` order **8.0** → `P9.2-GHL-UPLOAD` order **8.9**, `owning_role: media-librarian-ghl-updater`, `produces_artifact: working/checkpoints/media_library.json` |
| the mirror is a load-bearing resource | `presentation_job/required_resources.py` 188-189 | `"media-librarian-ghl-updater": [ResourceSpec("sops/media-librarian-ghl-updater-sops.md", "sop")]` — presence-checked, content not asserted |

---

## 4. Row by row, before → after (counts measured, not asserted)

Counts come from the A1 checker (§5), run on the **base blob** (`git show ac6c3a86a:<path>`) and on
**HEAD**. "role" = `media-librarian-ghl-updater.md`; "mirror" = `sops/media-librarian-ghl-updater-sops.md`.

| Spec row | Before | After |
|---|---|---|
| SOP 9.3 status sentence | mirror: `Skipping this step is only permitted under the `has_ghl: false` carve-out (write `ghl_delivery_skipped: true`).` (1). Role file: no skip rule at all (`owner_skip_approval` count 0). | mirror carries the exact spec sentence once; role carries the same rule with a resolvable referent (`owner_skip_approval` count 2). Stale carve-out-skip claim: 0. |
| Rename the folder step + delete CREATE | role `**Steps (Resolve the GHL media destination -- run once per deck run):**` (1); mirror the same plus `; the folder is NEVER created by software` (1); `CREATE` labels 2, both in the mirror | New exact phrase `Resolve the media destination (software never creates a folder)` 1× in each file; old heading 0× in both; `CREATE` 0× in both |
| Delete "PPTX assembly can begin" in both places | role 1, mirror 1 | 0 and 0 |
| …and say the upload runs after assembly (P9.2-GHL-UPLOAD) | neither file named `P9.2-GHL-UPLOAD` (0) and neither said `runs after `P8-ASSEMBLE`` (0) | role 11 mentions of `P9.2-GHL-UPLOAD`, 4 of `runs after `P8-ASSEMBLE``; mirror 3 and 2 |
| SOP 9.9's pointer → `WEBINAR-BUILDER-SOP.md` | mirror: ``(`P9.6-WEBINAR-VIDEO`, SOP 9.6 above)`` (1) — SOP 9.6 is "Final Deck Delivery (MIGRATED to ROLE-13)", the wrong section | ``(`P9.6-WEBINAR-VIDEO`, `WEBINAR-BUILDER-SOP.md`)`` (1); `SOP 9.6 above` 0 |
| Replace the `ls \| wc` count with a Python listing | role 1, mirror 1 (`ls working/media-library/*.png \| wc -l`) | `\| wc -l` 0 in both; Python listing 1× in each file |
| Landing-zone tree → the engine's run folder | rooted at `<workdir>/`, with `media-library/` and `output/` at the run root, `renders/` and `prompts/` under `working/`, prompt files named `slide-NN-prompt.txt`, and two phantom entries (`run_ledger.json`, `qc/finalrender/`) | rooted at `<run_dir>/`; `renders/` at the run root with the `slide-NN.ocr.json` sidecars; `working/{copy,prompts,checkpoints,qc,deliverables,delivery,brand,media-library}`; prompts `slide-NN.txt`; `output/`, `run_ledger.json`, `finalrender/` gone; `~/webinar-decks/` named only in the sentence that forbids it (`<workdir>` 0, `     output/` 0 in both files) |

### Coherence edits forced by the rows (named, not implied)

Every one of these carried the same false claim; leaving them would have contradicted the row I wrote.
No new rule was added.

1. **Role §2 identity paragraph** — said the role "creates … the GHL media library folders" and uploads
   "immediately after [QC]" to finish "before the PPTX Assembly Specialist begins work". All three are
   false against the header box and against `P8-ASSEMBLE` 8.0 / `P9.2-GHL-UPLOAD` 8.9.
2. **Role §3 "Phase 5 to 6 Handoff Task"** — retitled to `Phase 5 Intake Task … and the Post-Assembly
   Upload (P9.2-GHL-UPLOAD)`; steps 2-4 now state that the upload runs in the phase after assembly.
3. **SOP 9.2 step 4** — "trigger SOP 9.3 … immediately. Do not batch -- upload as images pass" became the
   phase-ordered sentence. Same edit in the mirror.
4. **SOP 9.3 "When to run"** — names the phase and its order (both files).
5. **SOP 9.3 failure mode** — "The PPTX Assembly Specialist can still work from the local media-library/
   folder" became "A failed upload never blocks assembly … retried with `scripts/ghl_media_push.py
   --repair --run-dir <run_dir>`" (both files; `--repair` is a real flag: `ghl_media_push.py` 1440-1447).
6. **SOP 9.4 Outputs / Hand to / failure mode** — the hand-off is the Director (and the Delivery Concierge
   reads the ledger), not the PPTX Assembly Specialist; "PPTX assembly can proceed from local copies"
   deleted (both files).
7. **§6 Monthly/Quarterly** — the `~/webinar-decks/<client>/<deck>/<date>/` dir replaced by the runs root
   plus `PRESENTATION_SCAN_ROOTS`.
8. **§11 handoffs and §19 collaborators** — the PPTX Assembly Specialist no longer "depends on
   delivery_verified before assembly begins"; it assembles first and reads `working/media-library/`.
9. **§13 Example B** — "PPTX assembly green-lit" became "The P9.2-GHL-UPLOAD records are complete and the
   closeout gate can pass."
10. **§15 mistake 4** — the "upload incrementally instead of in batch" advice was the reverse of the
    engine's order; it now says intake as images pass and let `P9.2-GHL-UPLOAD` do the upload.
11. **§17 Edge Case 17.1** — `has_ghl: false` alone no longer writes `ghl_delivery_skipped: true`; the
    logged `owner_skip_approval` token is required, exactly as the header box says.
12. **§17 Edge Case 17.2** — "Create a new GHL folder named `<Client> <Deck> v2`" became "Have the owner
    pre-create … this pipeline never creates a folder."
13. **§12 escalation row** — "GHL folder creation fails" became "GHL media destination cannot be resolved".
14. **SOP 9.1 Outputs and §13 Example A** — the ledger example paths follow the run directory
    (`<run_dir>/`, `<run_dir>/working/media-library/`), and Example A's `/Users/…` paths are gone (spec
    rule 8). This is the whole of build commit `88dc5c45a`.

### Deliberate asymmetry, stated not hidden

The role file's §9 has SOPs 9.1-9.6; the mirror additionally carries 9.0, 9.7, 9.8, 9.9 and the gated
header box. That asymmetry pre-dates this unit, the header box must survive A1 ("reviewer reads both"),
and other files point at the mirror's 9.8 and 9.9. It was therefore preserved, not flattened. The
status sentence therefore appears verbatim in the mirror (where "the box above" resolves) and in
equivalent, self-contained words in the role file (where no box exists). Both state the same rule.

---

## 5. A1 proof — the checker, and its BEFORE/AFTER pair

The checker is a 30-row, stdlib-only script (`a1_check.py`, kept in the unit's scratch folder; it is not
committed because a test file would sit outside FL24's owned paths — spec rule 4). It reads the role file
and the mirror and asserts every sentence-level claim of the unit. Run:

```
python3 -I <SCRATCH>/a1_check.py <role.md> <mirror.md>
```

### BEFORE — the base blobs `git show ac6c3a86a:<path>`

```
TOTAL 30 rows: 3 pass, 27 fail          (exit 1)
FAIL  1a status sentence present in mirror  [count=0]
FAIL  1b old has_ghl carve-out SKIP claim gone  [count=1]
FAIL  1c owner_skip_approval named in role  [count=0]
FAIL  2a new folder-step name in role  [count=0]
FAIL  2b new folder-step name in mirror  [count=0]
FAIL  2c old folder-step name gone (role)  [count=1]
FAIL  2d old folder-step name gone (mirror)  [count=1]
FAIL  2e CREATE label gone (role+mirror)  [role=0 mirror=2]
FAIL  3a forbidden sentence gone (role)  [count=1]
FAIL  3b forbidden sentence gone (mirror)  [count=1]
FAIL  3c upload-after-assembly stated (role)  [P9.2=0 P8=0]
FAIL  3d upload-after-assembly stated (mirror)  [P9.2=0 P8=0]
FAIL  3e no reverse-ordering claim left (role)  [before-assembly/green-lit strings absent]
FAIL  4a wrong pointer gone  [count=1]
FAIL  4b WEBINAR-BUILDER-SOP.md named at P9.6  [count=0]
FAIL  5a ls|wc gone (role)  [count=1]
FAIL  5b ls|wc gone (mirror)  [count=1]
FAIL  5c python listing in role  [count=0]
FAIL  5d python listing in mirror  [count=0]
FAIL  6a tree rooted at run_dir (role)  [count=0]
FAIL  6b tree rooted at run_dir (mirror)  [count=0]
FAIL  6c no workdir/o utput placeholders left  [workdir=4 output=2]
FAIL  6e prompts use slide-NN.txt  [stale prompt filename absent, engine filename present]
FAIL  6f phantom entries gone (run_ledger/finalrender)  [run_ledger.json and finalrender absent]
FAIL  6g no ~/webinar-decks tree (role)  [count=2 (only the 'never build' sentence may name it)]
FAIL  6h runs root is the engine's  [departments/Presentations/runs/ named in both]
FAIL  6i ledger example paths follow the run directory  [role=0 mirror=0]
```

The three rows that pass on the base are the two vacuous ones (6d sees a `renders/` entry in the old tree
too; A1's "every changed line is in the mirror" is vacuously true when the role has none of them yet) and
1b2, which is the **positive control** — the real `owner-skip carve-out (the ONLY skip)` sentence must
survive, and it did.

### AFTER — HEAD `88dc5c45a`

```
TOTAL 30 rows: 30 pass, 0 fail          (exit 0)
PASS  1a status sentence present in mirror  [count=1]
PASS  1b old has_ghl carve-out SKIP claim gone  [count=0]
PASS  1b2 the real owner-skip carve-out survives (control)  [count=1]
PASS  1c owner_skip_approval named in role  [count=2]
PASS  2a new folder-step name in role  [count=1]
PASS  2b new folder-step name in mirror  [count=1]
PASS  2c old folder-step name gone (role)  [count=0]
PASS  2d old folder-step name gone (mirror)  [count=0]
PASS  2e CREATE label gone (role+mirror)  [role=0 mirror=0]
PASS  3a forbidden sentence gone (role)  [count=0]
PASS  3b forbidden sentence gone (mirror)  [count=0]
PASS  3c upload-after-assembly stated (role)  [P9.2=11 P8=4]
PASS  3d upload-after-assembly stated (mirror)  [P9.2=3 P8=2]
PASS  3e no reverse-ordering claim left (role)  [before-assembly/green-lit strings absent]
PASS  4a wrong pointer gone  [count=0]
PASS  4b WEBINAR-BUILDER-SOP.md named at P9.6  [count=1]
PASS  5a ls|wc gone (role)  [count=0]
PASS  5b ls|wc gone (mirror)  [count=0]
PASS  5c python listing in role  [count=1]
PASS  5d python listing in mirror  [count=1]
PASS  6a tree rooted at run_dir (role)  [count=6]
PASS  6b tree rooted at run_dir (mirror)  [count=4]
PASS  6c no workdir/output placeholders left  [workdir=0 output=0]
PASS  6d renders at run root (role)  [renders/ is a run-root entry]
PASS  6e prompts use slide-NN.txt  [stale prompt filename absent, engine filename present]
PASS  6f phantom entries gone (run_ledger/finalrender)  [run_ledger.json and finalrender absent]
PASS  6g no ~/webinar-decks tree (role)  [count=1 (only the 'never build' sentence may name it)]
PASS  6h runs root is the engine's  [departments/Presentations/runs/ named in both]
PASS  6i ledger example paths follow the run directory  [role=2 (SOP 9.1 step 5 + Example A) mirror=1]
PASS  A1 mirror regenerated (every changed role line present in mirror)  [missing=[]]
```

### The Python listing, executed (not just asserted present)

The listing the file now prescribes, run against a folder with two PNGs and against an empty folder —
this is the behaviour `ls … | wc -l` could not give (it errors and prints nothing count-able when empty):

```
$ mkdir -p <SCRATCH>/ml-test && : > <SCRATCH>/ml-test/slide-01.png && : > <SCRATCH>/ml-test/slide-02.png
$ python3 -c 'import pathlib,sys; p=sorted(pathlib.Path(sys.argv[1]).glob("*.png")); print(len(p)); print(*[q.name for q in p], sep="\n")' <SCRATCH>/ml-test
2
slide-01.png
slide-02.png
$ mkdir -p <SCRATCH>/ml-empty
$ python3 -c 'import pathlib,sys; p=sorted(pathlib.Path(sys.argv[1]).glob("*.png")); print(len(p)); print(*[q.name for q in p], sep="\n")' <SCRATCH>/ml-empty
0

# control -- the old form on the same empty folder (this is what it was replaced for):
$ ls <SCRATCH>/ml-empty/*.png | wc -l
(eval):1: no matches found: <SCRATCH>/ml-empty/*.png
       0
```
The old form's `0` is the output of `wc -l` counting an error message, not of a listing; with a stricter
shell it aborts instead. The Python form prints a real count in both cases.

---

## 6. Failure proof — two mutations that turn the proof RED, each reverted

Run against the **final HEAD artefact**, then reverted with `git checkout --`, leaving the tree clean
(`git status --porcelain` → 0 lines both times).

**Mutation A — put the old folder-step wording back in the role file:**

```
MUTATED role heading back to the old wording
MUTATION A rc=1
FAIL  2a new folder-step name in role  [count=0]
TOTAL 30 rows: 29 pass, 1 fail
REVERTED   (after revert rc=0)
```

**Mutation B — put the old `has_ghl: false` skip claim back in the mirror:**

```
MUTATED mirror status sentence back to the has_ghl carve-out
MUTATION B rc=1
FAIL  1a status sentence present in mirror  [count=0]
FAIL  1b old has_ghl carve-out SKIP claim gone  [count=1]
TOTAL 30 rows: 28 pass, 2 fail
REVERTED   (after revert rc=0; 0 files dirty)
```

Both mutations were applied to the committed artefact and reverted in the same command, so nothing was
left behind. The BEFORE run in §5 is a second, independent failure proof: the same checker on the real
pre-edit blobs.

The checker itself was corrected twice while building, and both corrections are named here rather than
being silent:
- `1b` originally banned the bare word "carve-out" and failed on the **legitimate** `Owner-skip carve-out
  (the ONLY skip)` line. Narrowed to the defective phrase, and a positive control (`1b2`) was added so the
  legitimate sentence cannot be deleted with it.
- `6i` originally demanded exactly one occurrence in the role; the role correctly has two (SOP 9.1 step 5
  and Example A). Relaxed to `>= 1` with the reason recorded in the row's own output.

Neither was a repo test, so spec rule 6 (never weaken a test to pass) is untouched.

---

## 7. Tests by id, base and head

No test file in the tree asserts on the content of either file. Named sources: the **263** files in
`presentations/scripts/tests/` were enumerated — **22** mention `role-library`, **0** mention
`media-librarian`. The wider scan (`scripts/tests`, `scripts`, `intake`: **795** `.py/.sh/.mjs/.js/.json`
files) finds **3** files naming the slug, and all three use it as an owning-role id, not as prose:
`presentation_job/persona_service/policy.py` 108-130, `presentation_job/required_resources.py` 188-189,
`presentation_job/manifest.py` 1005 comment. `presentations-drift-gates.sh` hash-enforces `.md` files
**inside the `scripts/` dir**; both files edited here live outside it.

The plausible neighbours were run on both revisions, empty home, real exit codes:

| Test id | base `ac6c3a86a` | head `88dc5c45a` |
|---|---|---|
| `tests/test_pres028_required_resources.py` | rc=0, 0 bytes output | rc=0, 0 bytes output |
| `tests/test_fix36_doc_code_reconcile.py` | rc=0, `27 passed in 0.88s` | rc=0, `27 passed in 0.75s` |
| `tests/test_fix77_roster_uniqueness.py` | rc=0, 0 bytes output | rc=0, 0 bytes output |

Invocation: `env -i HOME=<empty> PATH="$PATH" TMPDIR=<scratch> python3 <file>`. Identical on both
revisions; nothing to update. **I did not run the full 263-file suite** (rule 12 puts a suite through the
test queue; it is the QC model's job) — that is the honest limit of this row.

---

## 8. Hunk attribution, merge-base to HEAD

`merge-base(HEAD, origin/main)` = `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`.
`git diff --name-status 1a476d2c..HEAD` — 10 modified files, 2 added reports:

| File | Owner unit | Commits |
|---|---|---|
| `presentations/media-librarian-ghl-updater.md` | **PD-102 (this unit)** | `3236c7705`, `88dc5c45a` |
| `presentations/sops/media-librarian-ghl-updater-sops.md` | **PD-102 (this unit)** | `3236c7705`, `88dc5c45a` |
| `presentations/slide-image-creator.md` | PD-094 (sibling, already accepted) | `baf3f5dbb`, `e649f7f57`, `579c937ae` |
| `presentations/sops/slide-image-creator-sops.md` | PD-094 | `baf3f5dbb` |
| `presentations/typography-architect.md` | PD-094 | `baf3f5dbb`, `bce9febf5` |
| `presentations/sops/typography-architect-sops.md` | PD-094 | `baf3f5dbb` |
| `presentations/pptx-assembly-specialist.md` | PD-093 (`ac6c3a86a`'s accepted sibling) | `66bf69c97`, `e9fb04930` |
| `presentations/sops/pptx-assembly-specialist-sops.md` | PD-093 | `66bf69c97`, `e9fb04930` |
| `presentations/audio-demonstration-specialist.md` | PD-101 (accepted at `ac6c3a86a`) | `80e5bc392` |
| `presentations/sops/audio-demonstration-specialist-sops.md` | PD-101 | `80e5bc392` |
| `evidence/PD-093/BUILD-REPORT.md` | PD-093 | `7381bff56`, `e9fb04930`, `cd9a9f003`, `16988928f` |
| `evidence/PD-101/BUILD-REPORT.md` | PD-101 | `054c77ef2`, `f6ad943c5`, `ac6c3a86a` |

**This unit's own hunks:** `git diff -U3 ac6c3a86a..HEAD` over its two files gives **19 hunks** in the
role file and **11 hunks** in the mirror — **30 hunks, 0 shared with any sibling**. No sibling hunk is on
a file this unit touched, and no sibling commit after `ac6c3a86a` exists.

---

## 9. Remote-head proof

Branch confirmed before the first edit, and proven again after the push — full 40-character string
compared literally:

```
$ git ls-remote --heads origin refs/heads/pd/fl24-role-procedures-c     # before any edit
ac6c3a86a0e61b154b0c1cd05fc08376c521b6b1	refs/heads/pd/fl24-role-procedures-c

$ git push origin HEAD:refs/heads/pd/fl24-role-procedures-c
   ac6c3a86a..88dc5c45a  HEAD -> pd/fl24-role-procedures-c

$ git rev-parse HEAD
88dc5c45ae7f916e4c6718eff510c4320fbcfe04
$ git ls-remote --heads origin refs/heads/pd/fl24-role-procedures-c
88dc5c45ae7f916e4c6718eff510c4320fbcfe04	refs/heads/pd/fl24-role-procedures-c
MATCH: remote head == local HEAD, 40/40 characters
```

The commit that carries **this report** is pushed after it, so the branch head at report time is that
report commit; its parent is `88dc5c45a`, the last build commit whose artefact the rows above were proven
on.

---

## 10. What is NOT proved / honest gaps

1. **The report commit's own sha is not inside the report** — it cannot be. The measured push proof above
   is for the build head `88dc5c45a`.
2. **The full 263-file test suite was not run.** Three plausible neighbours were (identical base/head), and
   no test was found that reads either file; a suite run is QC's row, not mine.
3. **No live GHL action.** Nothing was uploaded; the `--repair` flag and the `P9.2-GHL-UPLOAD` phase were
   read, never executed. Live-action flag for this unit is "none".
4. **"No sentence contradicts the header box" is proven against my own 30-row reading of both files, not
   against a machine grammar.** A 500-line role file and a 450-line mirror were read end to end; §3 and §4
   list every claim that was checked. A reviewer reading both may still find a sentence I judged
   consistent and they judge otherwise — that is the reviewer's row.
5. **The mirror is hand-regenerated, not generated.** The mirror's header describes a "verbatim mirror of
   Section 9" but also carries material the role file lacks (SOP 9.0, 9.7, 9.8, 9.9 and the gated box).
   I applied each row to both files and proved, per changed line, that the role's version is present in the
   mirror (`A1` row, `missing=[]`). I could not prove byte-equality of the two §9 sections, because they
   were already unequal before this unit and flattening them would delete the gate.
6. **`~/webinar-decks/` still appears once in the role file** — deliberately, in the sentence that forbids
   building one. Any naive string search for that path will hit it; row `6g` allows exactly one.
