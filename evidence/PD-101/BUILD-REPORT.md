# PD-101 — BUILD REPORT

**Unit:** PD-101 · "The Audio procedure names the engine's files" · Moderate · mechanical
**Lane:** FL24 · **Branch:** `pd/fl24-role-procedures-c`
**Worktree:** `/Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL24`
**Base:** `16988928f` (PD-093's accepted head; branch confirmed on the right branch before any edit)
**Build commit:** `80e5bc39218b9078989813302eada7f09af896b9`
**Report commit:** the commit that carries this file (its parent is the build commit)
**Acceptance row built and proven:** A1

---

## 1. Which spec text this row came from

`/Volumes/mac mini m4/swarm-contract/fable-reviews-2026-11-11/03-presentation-department/FINAL/01-BUILD-SPEC.md`,
unit section **PD-101 — The Audio procedure names the engine's files** (lines 3897-3919), read in full:

> - **Build unit PD-101 (Moderate, Haiku: exact path replacements in one role file; lane FL24).**
>   Audio role file: `working/presenter-speech/presenters_speech.md` → `working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md`;
>   `working/audio-demo/<deck>_demo.mp3` → `working/delivery/PRESENTER-AUDIO.mp3` (all occurrences);
>   `Presentations/scripts/synthesize_full_speech.py` → `scripts/synthesize_full_speech.py`;
>   in step 4 replace "MAX 2 TAGS PER LINE" with "at most 2 emotion tags per line and at most 3 cues of any kind per sentence".
>   The QC paths are fixed in PD-098, the Media Librarian's in PD-102. **Acceptance: mirror regenerated; diff shown.**

The unit table row (line 383) gives severity Moderate, difficulty mechanical, wave 3, depends on PD-093, acceptance
row `A1`. **PD-101 has no "Read first — consolidation amendments" block.** The amendment block at line 3927 belongs to
PD-102 (it opens after PD-102's table); PD-101's section runs straight from its table into the carried-over text.

Rule 11 of the same spec binds the mirror: *"After editing a role file, regenerate its `sops/` mirror the way the
file's header says."* The mirror's own header (line 4) states `**Extract:** Section 9 (Standard Operating Procedures)
verbatim mirror.` and line 5 states *"If they diverge, the role file wins and this mirror must be regenerated."*

---

## 2. The engine's own names (measured, not inherited)

Read from `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` (parsed, not text-searched):

| Phase id | order | owning_role | produces_artifact | executor.cmd |
|---|---|---|---|---|
| `P9-SPEECH` | 8.5 | presenters-speech-writer | `working/deliverables/PRESENTERS-SPEECH.md` | `python3 scripts/speech_build_harness.py …` |
| `P8.4-FISH-TAG` | 8.52 | fish-audio-expression-specialist | `working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md` | `python3 scripts/speech_fish_tag.py --run-dir {run_dir}` |
| `P9-SPEECH-WEBINAR-INTRO` | 8.54 | audio-demonstration-specialist | `working/delivery/PRESENTER-AUDIO-WEBINAR.mp3` | `python3 scripts/synthesize_full_speech.py --speech … --tagged-speech … --out {run_dir}/working/delivery/PRESENTER-AUDIO-WEBINAR.mp3 --webinar-intro-outro` |
| `P-SPEECH-QC` | 8.6 | qc-specialist-speech-presentations | `working/qc/speech_qc_report.json` | consumes `working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md` |
| `P9-DELIVER` | 9 | delivery-concierge | `working/delivery/PRESENTER-AUDIO.mp3` | `python3 scripts/synthesize_full_speech.py --speech … --tagged-speech … --out {run_dir}/working/delivery/PRESENTER-AUDIO.mp3` |

Three consequences, each one the row's target: the engine runs `scripts/synthesize_full_speech.py` (never
`Presentations/scripts/…`); the plain client audio it writes is `working/delivery/PRESENTER-AUDIO.mp3` (never
`working/audio-demo/<deck>_demo.mp3`); and the script the audio role synthesizes from is
`working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md`, which is also what the speech QC consumes — so the mirror's
phrase "the QC-passed script" describes that file exactly.

---

## 3. Files changed (both inside the unit's owned paths)

| File | Δ |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/audio-demonstration-specialist.md` | +9 −9 |
| `23-ai-workforce-blueprint/templates/role-library/presentations/sops/audio-demonstration-specialist-sops.md` (mirror) | +7 −7 |

`git diff --numstat` on the build commit: `9  9  …/audio-demonstration-specialist.md` and
`7  7  …/sops/audio-demonstration-specialist-sops.md`. No other path was written.

### Row-by-row, before → after

Occurrence counts below are measured by the A1 checker (§4), on the pre-edit blobs and on HEAD.

| Row | Before (count) | After (count) |
|---|---|---|
| presenter-speech path — **mirror only** | `working/presenter-speech/presenters_speech.md` (1, mirror L19) | `working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md` (1). The role file never carried the old string; it is now named in the role's SOP 9.1 Inputs too so the pair agrees (coherence edit 1, below). |
| demo mp3 path | `working/audio-demo/<deck>_demo.mp3` (role 4, mirror 4 = 8) | `working/delivery/PRESENTER-AUDIO.mp3` (all 8 replaced; role now 7 total mentions incl. pre-existing ones, mirror 4) |
| engine script path | `Presentations/scripts/synthesize_full_speech.py` (role 1, mirror 1) | `scripts/synthesize_full_speech.py` (role 1 in that line, mirror 1 in that line) |
| SOP 9.1 step 4 tag rule | `MAX 2 TAGS PER LINE` (role 1, mirror 1) | `at most 2 emotion tags per line and at most 3 cues of any kind per sentence` (role 1, mirror 1) |

### Coherence edits forced by the rows (named, not implied)

PD-093 established this form; all four are consequences of the demo-path row, with no new rule added:

1. **SOP 9.1 Inputs, both files.** The row replaces the mirror's stale input with the Fish-tagged artifact. The role
   file named only the untagged `PRESENTERS-SPEECH.md` there, which would have left role and mirror naming different
   single inputs. Both now read:
   `` - `working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md` (the QC-passed script -- the P8.4-FISH-TAG artifact; the untagged speech it was tagged from is `working/deliverables/PRESENTERS-SPEECH.md`) ``.
   Both paths are real engine paths (manifest rows above); the role's identity paragraph ("your source script is the
   QC-passed Presenters Speech … at `working/deliverables/PRESENTERS-SPEECH.md`") stays true.
2. **Role line 23.** `Your SOP workdir is working/audio-demo/ (chunks, the scratch demo mp3, the tag-annotated script)`
   → `(chunks and the tag-annotated script)`. No rendered mp3 is written to that workdir any more.
3. **Role line 119 (Tools).** The same phantom name is removed from the workdir description: `(write: chunk mp3s and
   the tag-annotated script; the rendered mp3s are the phase's manifest artifacts: …)`.
4. **Role line 280.** The parenthetical that called the file "this SOP's workdir scratch" would have contradicted the
   manifest once the path became the manifest artifact; it now reads "(the executor `synthesize_full_speech.py --out`
   writes that manifest artifact directly)". Line 283's trailing clause changed the same way, to "— the P9-DELIVER
   manifest artifact".

Nothing was deleted that named a real file.

---

## 4. A1 proof — run, captured, and made failable

The checker is `…/pd-fix/scratchpads/PD-101/check_pd101.py` (outside the repo; the unit authorises no new test file).
It reads the two files and the manifest, asserts every row, and exits non-zero on any failure.

Command and result on HEAD:

```
$ cd /Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL24
$ python3 -I /Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-101/check_pd101.py .
PASS  old-string-absent :: 'working/presenter-speech/presenters_speech.md' role=0 mirror=0
PASS  old-string-absent :: 'working/audio-demo/<deck>_demo.mp3' role=0 mirror=0
PASS  old-string-absent :: 'Presentations/scripts/synthesize_full_speech.py' role=0 mirror=0
PASS  old-string-absent :: 'MAX 2 TAGS PER LINE' role=0 mirror=0
PASS  no-demo-mp3-name-role :: 0 occurrences of <deck>_demo.mp3
PASS  no-demo-mp3-name-mirror :: 0 occurrences of <deck>_demo.mp3
PASS  new-string-present :: 'working/delivery/PRESENTER-AUDIO.mp3' role=7(4) mirror=4(4)
PASS  new-string-present :: 'scripts/synthesize_full_speech.py' role=5(1) mirror=3(1)
PASS  new-string-present :: 'working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md' role=3(1) mirror=1(1)
PASS  tag-rule-rewritten :: role=1 mirror=1
PASS  tag-rule-in-step-4 :: role=1 mirror=1
PASS  engine-delivers-PRESENTER-AUDIO :: P9-DELIVER produces_artifact='working/delivery/PRESENTER-AUDIO.mp3'
PASS  engine-cmd-path :: P9-DELIVER cmd uses scripts/synthesize_full_speech.py
PASS  engine-produces-fish-tagged :: P8.4-FISH-TAG produces_artifact='working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md'
PASS  qc-consumes-tagged :: P-SPEECH-QC consumes=['working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md']
PASS  engine-webinar-cmd-path :: P9-SPEECH-WEBINAR-INTRO cmd uses scripts/synthesize_full_speech.py
PASS  mirror-lockstep :: 'working/delivery/PRESENTER-AUDIO.mp3' in role=True/ mirror=True
PASS  mirror-lockstep :: 'scripts/synthesize_full_speech.py' in role=True/ mirror=True
PASS  mirror-lockstep :: 'working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md' in role=True/ mirror=True

RESULT: GREEN (all A1 checks hold)
RC=0
```

### Negative control 1 — the pre-edit artifacts (a row that cannot fail proves nothing)

The two files as committed at the branch base were copied to `scratchpads/PD-101/mutant/` with the manifest; the
checker was pointed at that tree:

```
$ python3 -I .../check_pd101.py .../scratchpads/PD-101/mutant
RESULT: RED (12 failed: old-string-absent, old-string-absent, old-string-absent, old-string-absent,
no-demo-mp3-name-role, no-demo-mp3-name-mirror, new-string-present, new-string-present,
tag-rule-rewritten, tag-rule-in-step-4, mirror-lockstep, mirror-lockstep)
NC1_RC=1
```

### Negative control 2 — one row mutated back

The HEAD files, with exactly one row reverted (`at most 2 emotion tags …` → `MAX 2 TAGS PER LINE`) in the role only:

```
$ python3 -I .../check_pd101.py .../scratchpads/PD-101/mutant
RESULT: RED (3 failed: old-string-absent, tag-rule-rewritten, tag-rule-in-step-4)
NC2_RC=1
```

The failure set is exactly the checks that row owns. It is not a blanket failure and it is not a pass.

---

## 5. A1 — the mirror, and the drift that is NOT this unit's

The mirror was regenerated in lockstep with the role: every row this unit changed is present, verbatim, in both files
(§4 `mirror-lockstep`, all PASS).

The audio mirror carries **pre-existing** divergence from its role file that this unit did not create and did not
inherit into its rows. Measured on Section 9 of both files, at the base and at HEAD:

```
BASE  role_s9_lines 221  mirror_s9_lines 220  hunks 7  added 24  removed 25
HEAD  role_s9_lines 221  mirror_s9_lines 220  hunks 6  added 23  removed 24
```

One hunk disappeared — exactly the SOP 9.1 Inputs line the unit rewrote. The other six are identical at base and at
HEAD: the role's SOP 9.1 step 0 (pace authority), the role's duplicate first chunk step, the richer FULL-COVERAGE
paragraph, the Fish knob sentence, the duration-gate wording, and the failure-mode wording. Regenerating them is not
PD-101's row, and doing it here would DELETE content the mirror holds and the role does not (§7, F2).

Interpreting "mirror regenerated" as a wholesale overwrite was rejected for that measured reason, with PD-093's own
precedent (its mirror keeps a 60-line block the role does not have) as the lane's method.

---

## 6. Hunk attribution on this branch (merge-base `1a476d2c` → HEAD)

`git diff --numstat 1a476d2c..HEAD`:

| Hunks | File | Owning unit |
|---|---|---|
| `46 37` / `40 31` | `pptx-assembly-specialist.md` / `sops/pptx-assembly-specialist-sops.md` | **PD-093** ("An assembly procedure that can be followed") |
| `308 0` | `evidence/PD-093/BUILD-REPORT.md` | **PD-093** |
| `24 24` / `18 18` | `slide-image-creator.md` / `sops/slide-image-creator-sops.md` | **PD-094** ("The Slide Image Creator procedure stops contradicting itself"; commits `baf3f5dbb`, `bce9febf5`, `e649f7f57`, `579c937ae`) |
| `11 11` / `3 3` | `typography-architect.md` / `sops/typography-architect-sops.md` | **PD-094** (same commits) |
| `9 9` / `7 7` | `audio-demonstration-specialist.md` / `sops/audio-demonstration-specialist-sops.md` | **PD-101 (this unit)** |

PD-093 and PD-094 hunks are untouched by this build: neither audio file appears in `git diff
1a476d2c..HEAD` before the build commit, and this unit's diff touches no file of theirs.

---

## 7. Cross-unit findings (reported, not repaired)

- **F1 — role SOP 9.2 has two steps numbered "1."** (`audio-demonstration-specialist.md`, the two `1. CHUNK …` lines).
  A wholesale mirror regeneration would faithfully reproduce the duplication. Reported so the fix lands on the role,
  not on its mirror.
- **F2 — the mirror holds verified specifics the role has lost.** The mirror's SOP 9.2 says the executor sends
  `temperature: 0.9`, `top_p: 0.8`, `repetition_penalty: 1.2`, `prosody: {speed, volume, normalize_loudness}`
  "(fields verified against the Fish OpenAPI)" and splices silence at defaults "0.8 s / 1.2 s / 2.5 s"; the role now
  says only "the Fish expressiveness knobs (`temperature`, `top_p`, `repetition_penalty`, `prosody`)". A verbatim
  regeneration would delete the numbers. They were preserved, and this is flagged for whoever owns the role's content.
- **F3 — the engine scripts are not in this repository at this base.** `ls scripts/` (250 entries, listed in full) and
  `ls 51-signature-presentation/scripts/` (8 entries) hold no `synthesize_full_speech.py` and no `speech_fish_tag.py`,
  although both PIPELINE-MANIFEST cmds name `scripts/…`. The row corrects the path to the **engine's declared** path;
  shipping the file is not this unit and is not claimed here. I did not sweep the rest of the tree, so "absent
  everywhere" is not asserted.
- **F4 — three other tag-count phrasings remain in the role** (line 66 "max 2 tags per line", Gate 2 "max 2 tags per
  line", KPI row "Tags per line | <= 2", the Bad-Output bullet, and Common-Mistakes row 4). The row names step 4 only;
  the older phrasings are compatible but not identical wording. Left as-is for PD-101's scope.
- **F5 — the mirror's SOP 9.1 lacks the role's step 0** (pace authority). Pre-existing (present at base), untouched.

Guard B (`retired-doctrine-patterns.json`, 5 live patterns) was read in full: none of the text added by this unit
matches a retired pattern. `test_retired_roles.py` in the touched folder was read in full: it asserts on
`assembled-slide-legibility-qc` and on the registry shape, none of which this unit changes. No test was run by this
builder (spec rule 9) and no test was weakened, renamed or skipped.

---

## 8. Push proof

Branch `pd/fl24-role-procedures-c`, build commit `80e5bc39218b9078989813302eada7f09af896b9`.

Measured after the build commit and this report's first push (the head at that moment was `054c77ef2`, the commit that
first carried this file; the commit you are reading was pushed after it and is proven in the build's final message,
because a file cannot name the commit that introduces it):

```
$ git rev-parse HEAD
054c77ef206de3843504835d0fddf3e1e5e1ffe3
$ git ls-remote --heads origin refs/heads/pd/fl24-role-procedures-c | cut -f1
054c77ef206de3843504835d0fddf3e1e5e1ffe3
$ git status --porcelain
(empty)
```

The 40-character SHAs are compared literally, not inferred from the push command's own output. The lane clone
(`pd-fix/clones/onboarding`) and `pd-fix/worktrees/onboarding/_base` both report `git status --porcelain` with zero
lines, checked after this build.
