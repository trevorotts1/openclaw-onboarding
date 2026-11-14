# PD-100 — BUILD REPORT

**Unit:** PD-100 · "The Speech Writer procedure reads files, hands off delivery and names the engine's paths" · Moderate
**Lane:** FL24 · **Repository:** trevorotts1/openclaw-onboarding · **Branch:** `pd/fl24-role-procedures-c`
**Worktree:** `<project-root>/pd-fix/tmp/PD-100/work.WU49CC/tree` (own scratch worktree; the lane clone was left clean)
**Base:** `f026a56d8857b61121f9fdae519c7309fa6f99ce` — confirmed on the remote (`git ls-remote --heads origin refs/heads/pd/fl24-role-procedures-c`) **before** any edit
**Build commit:** `976856b38123df9dcfac196af086d75ef6083c2a`
**Report commit:** the commit carrying this file; its parent is the build commit
**Acceptance row:** A1

---

## 1. The spec text this unit implements

`<project-root>/fable-reviews-2026-11-11/03-presentation-department/FINAL/01-BUILD-SPEC.md`,
section **PD-100** (lines 3968-3991), read in full.

Binding consolidation amendment (line 3987), quoted:

> The pace lines ("replace each 130") are not built here; they are PD-100b (held by decision D-3). Everything else in the text below is this unit.

Carried-over unit text (line 3991), quoted:

> **Build unit PD-100 (Moderate, Sonnet; lane FL24).** Speech Writer role file. Step 9.5-1 becomes `open slides.json and each prompt file and read them; compare each slide's copy with its spoken block`. Steps 9.5-2 and 9.5-3 become `Hand the five files to the Delivery Concierge. This role does not copy files to the client and does not message the client.` Notion lines become optional: `when the client's box has a Notion connection`, and the "= FAIL" line is deleted. SOP 9.4 is replaced by one paragraph pointing to the Audio procedure as the single owner of synthesis. Every output path becomes the manifest's (`working/deliverables/PRESENTERS-SPEECH.md`, `.pdf`, `presenter-teleprompter.html`; `working/delivery/PRESENTER-AUDIO.mp3`). Pace: replace each "130" with the value decided under D-3. The dry-run command uses `<SCRATCH>` paths. Acceptance: mirror regenerated; report lists each replaced path against the manifest row it now equals.

The acceptance row is defined by `TESTING.md:81`: *"the unit's acceptance rows are the rows A1, A2, … in `01-BUILD-SPEC.md` under that unit"*. PD-100 has one row, A1, whose two clauses are the last sentence above: **mirror regenerated**, and **the report lists each replaced path against the manifest row it now equals** (both answered in §2 and §5 below).

The "replace each 130" clause is **not** executed here — the amendment above assigns it to PD-100b. The pace count is unchanged by this unit: `130` appears 25 times in the role file before and after (`grep -c 130` = 25 on both blobs).

---

## 2. The manifest rows, measured (parsed JSON, not text-searched)

`universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json`, `manifest_version` = 75. Parsed with `json.load` and read from `produces_artifact` / `consumes`:

| Phase id | order | owning_role | produces_artifact |
|---|---|---|---|
| `P9-SPEECH` | 8.5 | presenters-speech-writer | `working/deliverables/PRESENTERS-SPEECH.md` |
| `P9.1-SPEECH-PDF` | 8.55 | presenters-speech-writer | `working/deliverables/PRESENTERS-SPEECH.pdf`, `working/deliverables/speech_spec.json` |
| `P8.4-FISH-TAG` | 8.52 | fish-audio-expression-specialist | `working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md` |
| `P7-TELEPROMPTER` | 8.95 | presenters-speech-writer | `working/deliverables/presenter-teleprompter.html` |
| `P9-DELIVER` | 9 | delivery-concierge | `working/delivery/PRESENTER-AUDIO.mp3` |

`P9-SPEECH`'s own executor writes `--out {run_dir}/working/deliverables/PRESENTERS-SPEECH.md --workdir {run_dir}/working/presenter-speech`, which is why `working/presenter-speech/` survives only as the harness **workdir**, never as a deliverable path.

---

## 3. Files changed

| File | numstat |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/presenters-speech-writer.md` | +168 −165 |
| `23-ai-workforce-blueprint/templates/role-library/presentations/sops/presenters-speech-writer-sops.md` (mirror) | +23 −58 |
| `evidence/PD-100/a1_check.py`, `evidence/PD-100/BUILD-REPORT.md` | evidence only |

`git diff --numstat` on the build commit: exactly the two role files. No other path was written.

**One structural consequence, disclosed up front.** The role file's Section 9 was three overlapping drafts (two `### SOP 9.1`, two `### SOP 9.2`, two `### SOP 9.3`, two `### SOP 9.4`) while its mirror carried the newer single-pass structure. A1's first clause — *mirror regenerated* — cannot be true while the two differ, so the role file's Section 9 was set to the mirror's Section 9 (which already contained this unit's new text). Proven byte-exact:

```
role-section9 == mirror-body: True | bytes: 25251 25251
```

That is also why PD-100b's A3 ("the mirror equals the role file's section 9") is true as a side effect; PD-100b is still needed for the pace number, which this unit leaves untouched.

---

## 4. Row by row — what changed, and the commit that satisfies it

Every row below is satisfied by **`976856b38123df9dcfac196af086d75ef6083c2a`** (the single build commit). Counts are the checker's own output (§5).

| Row | Before | After |
|---|---|---|
| **R1** step 9.5-1 | `1. Surface-boundary check: confirm no spoken-block text was copied onto the audience deck (grep slide copy and prompt files)…` | `1. open slides.json and each prompt file and read them; compare each slide's copy with its spoken block` — exact sentence, 1× in role, 1× in mirror |
| **R2** steps 9.5-2 and 9.5-3 | two steps: `Deliver per SOP-PITCH-05…` + `Notify the owner via openclaw message send, naming surfaces: "Your Presenter's Speech is ready…"` | merged into one: `2. Hand the five files to the Delivery Concierge. This role does not copy files to the client and does not message the client.` — exact sentence, 1× in role, 1× in mirror; `Notify the owner via openclaw message send` 0× in both |
| **R3** Notion optional + the `= FAIL` line deleted | `- notion_url.json missing or URL does not resolve = FAIL.` present in role and mirror; Notion steps unconditional | `when the client's box has a Notion connection` 8× role / 3× mirror; `notion_url.json missing or URL does not resolve = FAIL` 0× in both |
| **R4** SOP 9.4 → one paragraph naming the Audio procedure | two SOP 9.4 blocks in the role (`Audio Demonstration via the TTS Fallback Chain`, 48 lines, and a mis-headed duplicate) and a 34-line audio SOP in the mirror | one heading `### SOP 9.4 -- Audio synthesis is owned by the Audio procedure` + one paragraph containing `single owner of voice synthesis`; exactly one `### SOP 9.4` in each file |
| **R5** every output path = the manifest's | 8 distinct stale output paths (counts in §5) | the five manifest paths, each declared by a manifest `produces_artifact` row; all 8 old paths 0× in the role |
| **R6** dry-run uses `<SCRATCH>` | mirror: `--out /tmp/speech_test.md --workdir /tmp/speech_test_work` | mirror: `--out <SCRATCH>/speech_test.md --workdir <SCRATCH>/speech_test_work`; `/tmp/speech_test` 0×, `<SCRATCH>/speech_test` 2× |

The five files the handoff names are exactly the five this role's pipeline produces, and each is a manifest artifact: `working/deliverables/PRESENTERS-SPEECH.md`, `working/deliverables/PRESENTERS-SPEECH.pdf`, `working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md`, `working/deliverables/presenter-teleprompter.html`, `working/delivery/PRESENTER-AUDIO.mp3`.

**Coherence edits forced by the rows (named, not implied).** R2 says the role "does not message the client"; four surviving sentences said it did, so they went or changed:

1. SOP 9.5's delivery message paragraph (the `"Your Presenter's Speech is ready…"` text) — deleted in both files, directly required by R2.
2. SOP 9.5's enforcement bullet `- Delivery message does not name which artifact is which surface = FAIL.` — deleted; there is no message left to name surfaces.
3. SOP 9.5 failure mode `Owner unreachable: deliver to the default location (Downloads)…` — replaced by the Delivery-Concierge failure mode (R2: this role copies nothing).
4. Role §3 step 6 `Run SOP 9.4 (Audio Demonstration …)` → `Hand the Fish-tagged script to the Audio procedure…`; tools line for the TTS providers and the escalation row now name the Audio procedure as the synthesis owner (R4).

---

## 5. A1 proven — the checker and its real output

The checker is committed as `evidence/PD-100/a1_check.py`. It parses the manifest (not the prose), counts every row's strings in both files, and computes the mirror claim from `git diff -U0` line numbers. It exits nonzero on any FAIL.

**On the build (AFTER) — `python3 -I evidence/PD-100/a1_check.py <tree> --diff-base f026a56d8857b61121f9fdae519c7309fa6f99ce`, exit 0, 40 PASS:**

```
PASS  1a step 9.5-1 sentence in role  [count=1]
PASS  1b step 9.5-1 sentence in mirror  [count=1]
PASS  2a handoff sentence in role  [count=1]
PASS  2b handoff sentence in mirror  [count=1]
PASS  2c the role no longer runs a client message step  [count=0]
PASS  2d the mirror no longer runs a client message step  [count=0]
PASS  3a Notion conditional in role  [count=8]
PASS  3b Notion conditional in mirror  [count=3]
PASS  3c Notion '= FAIL' line gone (role)  [count=0]
PASS  3d Notion '= FAIL' line gone (mirror)  [count=0]
PASS  4a SOP 9.4 pointer heading in role  [count=1]
PASS  4b SOP 9.4 pointer heading in mirror  [count=1]
PASS  4c 'single owner of voice synthesis' in role  [count=1]
PASS  4d 'single owner of voice synthesis' in mirror  [count=1]
PASS  4e old SOP 9.4 synthesis block gone (role)  [count=0]
PASS  4f old SOP 9.4 synthesis block gone (mirror)  [count=0]
PASS  4g exactly one SOP 9.4 in role  [count=1]
PASS  4h exactly one SOP 9.4 in mirror  [count=1]
PASS  5a manifest row declares working/deliverables/PRESENTERS-SPEECH.md  [in manifest]
PASS  5b role names working/deliverables/PRESENTERS-SPEECH.md  [count=10]
PASS  5a manifest row declares working/deliverables/PRESENTERS-SPEECH.pdf  [in manifest]
PASS  5b role names working/deliverables/PRESENTERS-SPEECH.pdf  [count=3]
PASS  5a manifest row declares working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md  [in manifest]
PASS  5b role names working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md  [count=3]
PASS  5a manifest row declares working/deliverables/presenter-teleprompter.html  [in manifest]
PASS  5b role names working/deliverables/presenter-teleprompter.html  [count=2]
PASS  5a manifest row declares working/delivery/PRESENTER-AUDIO.mp3  [in manifest]
PASS  5b role names working/delivery/PRESENTER-AUDIO.mp3  [count=5]
PASS  5c old output path gone from role: working/presenter-speech/presenters_speech.md  [count=0]
PASS  5c old output path gone from role: working/presenter-speech/speech.md  [count=0]
PASS  5c old output path gone from role: working/presenter-speech/speech_tagged.md  [count=0]
PASS  5c old output path gone from role: working/presenter-speech/speech.md  [count=0]
PASS  5c old output path gone from role: working/presenter-speech/Presenters_Speech_<DeckTitle>.pdf  [count=0]
PASS  5c old output path gone from role: working/presenter-speech/audio/chunk-NN.mp3  [count=0]
PASS  5c old output path gone from role: working/presenter-speech/audio/Presenters_Speech_<DeckTitle>_demo.mp3  [count=0]
PASS  5c old output path gone from role: output/[DECK_SLUG]_presenters_speech.pdf  [count=0]
PASS  6a /tmp dry-run paths gone (mirror)  [count=0]
PASS  6b <SCRATCH> dry-run paths present (mirror)  [count=2]
PASS  A1-core mirror regenerated (every changed SOP 9.4-9.5 role line present in mirror)  [diff-base=f026a56d8857 checked=11 missing=0]
PASS  A1-full every changed Section 9 role line present in mirror  [diff-base=f026a56d8857 checked=132 missing=0]

RESULT: ALL PASS
```

With no `--diff-base` the checker defaults to `git merge-base HEAD origin/main` (`1a476d2cbbc5` on this branch) and still reports `checked=132 missing=0`. A diff base that yields **zero** lines is a FAIL, not a pass — verified by forcing it: `--diff-base HEAD` on the committed tree returns `rc=1` with `checked=0 missing=0` on both A1 rows and the printed line *"the diff base yielded no lines in SOP 9.4-9.5: pass --diff-base <unit base> (this is a FAIL, not a pass)"*. The A1 control cannot silently go vacuous.

### A1, second clause — every replaced path against the manifest row it now equals

| Old path (count in the base role file) | New path | Manifest row it now equals |
|---|---|---|
| `working/presenter-speech/presenters_speech.md` (8) | `working/deliverables/PRESENTERS-SPEECH.md` | `P9-SPEECH`, order 8.5, presenters-speech-writer, `produces_artifact` |
| `working/presenter-speech/speech.md` (2) | `working/deliverables/PRESENTERS-SPEECH.md` | `P9-SPEECH` |
| `working/presenter-speech/speech_tagged.md` (2) | `working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md` | `P8.4-FISH-TAG`, order 8.52, `produces_artifact`; also `P-SPEECH-QC` `consumes` |
| `working/presenter-speech/Presenters_Speech_<DeckTitle>.pdf` (2) | `working/deliverables/PRESENTERS-SPEECH.pdf` | `P9.1-SPEECH-PDF`, order 8.55, `produces_artifact` |
| `output/[DECK_SLUG]_presenters_speech.pdf` (3) | `working/deliverables/PRESENTERS-SPEECH.pdf` | `P9.1-SPEECH-PDF` |
| `working/presenter-speech/audio/chunk-NN.mp3` (1) | `working/delivery/PRESENTER-AUDIO.mp3` | `P9-DELIVER`, order 9, `produces_artifact` |
| `working/presenter-speech/audio/Presenters_Speech_<DeckTitle>_demo.mp3` (1) | `working/delivery/PRESENTER-AUDIO.mp3` | `P9-DELIVER` |
| `working/presenter-speech/audio_manifest.json` (1) | (removed — the Audio procedure's internal record; it has no manifest row) | — |
| `working/presenter-speech/audio/` (1) | (removed — chunk dir belongs to the Audio procedure, `working/audio-demo/chunks/`) | — |
| *(absent — added)* | `working/deliverables/presenter-teleprompter.html` | `P7-TELEPROMPTER`, order 8.95, presenters-speech-writer, `produces_artifact` |
| mirror only: `working/delivery/presenter-teleprompter.html` (1, wrong directory) | `working/deliverables/presenter-teleprompter.html` | `P7-TELEPROMPTER` |

Not a manifest row and deliberately left as-is: `working/presenter-speech/notion_url.json` (the optional Notion verification record — no phase produces it, and R3 makes the whole Notion path conditional) and `working/presenter-speech/lessons.md` (an internal lessons note inside the harness workdir `--workdir {run_dir}/working/presenter-speech`).

---

## 6. The failure proof

**BEFORE/AFTER pair — same checker, same files, base blob vs build.** `--base f026a56d8…` reads the three files with `git show <base>:<path>` and runs every row:

```
python3 -I a1_check.py <tree> --base f026a56d8857b61121f9fdae519c7309fa6f99ce
rc=1   32 FAIL

FAIL  1a step 9.5-1 sentence in role  [count=0]
FAIL  2c the role no longer runs a client message step  [count=1]
FAIL  3c Notion '= FAIL' line gone (role)  [count=1]
FAIL  4e old SOP 9.4 synthesis block gone (role)  [count=1]
FAIL  4g exactly one SOP 9.4 in role  [count=2]
FAIL  5b role names working/deliverables/PRESENTERS-SPEECH.md  [count=0]
FAIL  5c old output path gone from role: working/presenter-speech/presenters_speech.md  [count=8]
FAIL  5c old output path gone from role: output/[DECK_SLUG]_presenters_speech.pdf  [count=3]
FAIL  6a /tmp dry-run paths gone (mirror)  [count=2]
FAIL  6b <SCRATCH> dry-run paths present (mirror)  [count=0]
RESULT: 32 FAIL
```

(32 of the 38 rows evaluated on base are red; the two A1 line-diff rows are not evaluated against a bare blob, as the run prints. The six that pass are `4h exactly one SOP 9.4 in mirror` — the mirror was already single — plus the five `5a manifest row declares …` rows, which are facts about the manifest, not about either file.) A1's line-diff clauses are not evaluated against a bare blob and the checker says so in one printed note — they are evaluated on the build only.

**Mutation A — put the client-message step back in the mirror** (`2. Hand the five files…` → `3. Notify the owner via openclaw message send.`):

```
FAIL  2b handoff sentence in mirror  [count=0]
FAIL  2d the mirror no longer runs a client message step  [count=1]
FAIL  A1-core mirror regenerated (every changed SOP 9.4-9.5 role line present in mirror)  [diff-base=f026a56d8857 checked=11 missing=1]
FAIL  A1-full every changed Section 9 role line present in mirror  [diff-base=f026a56d8857 checked=132 missing=1]
RESULT: 4 FAIL
```

**Mutation B — put `/tmp` back in the dry-run command:**

```
FAIL  6a /tmp dry-run paths gone (mirror)  [count=2]
FAIL  6b <SCRATCH> dry-run paths present (mirror)  [count=0]
FAIL  A1-full every changed Section 9 role line present in mirror  [diff-base=f026a56d8857 checked=132 missing=1]
RESULT: 3 FAIL
```

Both reverted, each to `RESULT: ALL PASS`, and the mirror was confirmed byte-identical to its pre-mutation copy (`cmp -s` → equal). The controls can fail; neither is vacuous. A third control in §5 (`--diff-base HEAD` → `checked=0` → FAIL) covers the other way a checker can lie: passing because it measured nothing.

---

## 7. Tests, by id, on base and on the build

Test census over the repository for anything naming `presenters-speech-writer` / `presenters_speech_writer` in a runnable test file returns four suites. All four: same command, same interpreter, a private temp directory under the unit's own scratch, no system temp path.

```
python3 -m pytest -q test_preflight.py test_fix10_teleprompter.py \
    tests/test_qc_gate_teeth.py tests/test_deliverables_single_source.py
```

| Tree | Result |
|---|---|
| base `f026a56d8` (second worktree) | `110 passed, 66 warnings in 21.07s` (exit 0) |
| build `976856b38` | `110 passed, 66 warnings in 22.14s` (exit 0) |

Both runs are the identical 110 test ids; nothing was added, renamed, skipped or xfailed. These four suites reference the role and mirror names only in docstrings, comments and literals — they do not assert the file's prose — which is why no test breaks and none is a proof of this unit; the proof is §5.

---

## 8. Hunk attribution (merge-base → HEAD)

`git merge-base HEAD origin/main` = `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`. Commits on the branch at dispatch:

| Commit | Unit | Files |
|---|---|---|
| `baf3f5dbb`, `bce9febf5`, `e649f7f57`, `579c937ae` | **PD-094** (sibling) | `slide-image-creator.md` + mirror, `typography-architect.md` + mirror |
| `66bf69c97`, `7381bff56`, `e9fb04930`, `cd9a9f003`, `16988928f` | **PD-093** (sibling) | `pptx-assembly-specialist.md` + mirror, `evidence/PD-093/` |
| `80e5bc392`, `054c77ef2`, `f6ad943c5`, `ac6c3a86a` | **PD-101** (sibling, declared accepted) | `audio-demonstration-specialist.md` + mirror, `evidence/PD-101/` |
| `3236c7705`, `88dc5c45a`, `3538e19ca`, `c358ea2ee` | **PD-102** (sibling, declared accepted) | `media-librarian-ghl-updater.md` + mirror, `evidence/PD-102/` |
| `871d96010`, `96ab1e5f4`, `f026a56d8` | **PD-108** (sibling, declared accepted) | `sops/WORKBOOK-BUILDER-SOP.md`, `evidence/PD-108/` |
| `976856b38` | **PD-100 (this unit)** | `presenters-speech-writer.md`, `sops/presenters-speech-writer-sops.md` |

No sibling commit touches `presenters-speech-writer.md` or its mirror (`git log --oneline -- <path>` shows only this unit), and this unit touches no sibling's file. PD-101/PD-102/PD-108 hunks are untouched.

---

## 9. Remote-head proof

Before the edit, the branch existed and this was its head:

```
$ git ls-remote --heads origin refs/heads/pd/fl24-role-procedures-c
f026a56d8857b61121f9fdae519c7309fa6f99ce	refs/heads/pd/fl24-role-procedures-c
```

The lane clone at `<project-root>/pd-fix/worktrees/onboarding/FL24` was **behind** that head (it sat at `ac6c3a86a`, PD-101), so the build was made from a fresh scratch worktree at the fetched remote head — not from the lane clone. After pushing the build:

```
$ git push origin HEAD:refs/heads/pd/fl24-role-procedures-c
   f026a56d8..976856b38  HEAD -> pd/fl24-role-procedures-c

$ git ls-remote --heads origin refs/heads/pd/fl24-role-procedures-c
976856b38123df9dcfac196af086d75ef6083c2a	refs/heads/pd/fl24-role-procedures-c
```

A commit cannot name itself, so the head above is the **build** commit. Measured again after pushing the report commit:

```
$ git push origin HEAD:refs/heads/pd/fl24-role-procedures-c
   976856b38..4891897a0  HEAD -> pd/fl24-role-procedures-c

$ git ls-remote --heads origin refs/heads/pd/fl24-role-procedures-c
4891897a0b5673fd9d6b6b2018e6c5b4feecd5d0	refs/heads/pd/fl24-role-procedures-c
```

`4891897a0` is the report commit (parent `976856b38`). This paragraph's own commit is its child and cannot appear in its own bytes — PD-101 and PD-108 took the same step on this branch. The live head is re-measured in the hand-back, not claimed here.

The lane clone `<project-root>/pd-fix/worktrees/onboarding/FL24` was left clean (`git status --porcelain` empty after the push).

---

## 10. What is not proved, and what was deliberately not touched

1. **No repository test asserts that the mirror equals the role file.** The equality proof in §3 is this unit's checker plus a direct string compare, not a gate in CI. If that invariant is meant to be enforced, it needs a test in a later unit.
2. **PD-100b's pace change is not in this unit** (amendment at spec line 3987). `130` is present 25 times in the role file before and after; `140`/the D-3 value is untouched.
3. **The role file gained the mirror's SOP 9.0 (build harness) and 9.3 (Fish-tagged deliverable) sections** as part of making Section 9 equal its mirror. They were already the shipped SOP set; nothing new was invented, but they are additive relative to this unit's literal change list and are disclosed here rather than left implicit.
4. **`working/presenter-speech/notion_url.json` and `working/presenter-speech/lessons.md` keep non-manifest paths** (§5). Neither is a deliverable and neither has a manifest row; inventing one would have been worse than leaving them named honestly.
5. **Sections 10-14 of the role file were left alone** except the two Notion-conditionality lines (Gate 3, the Monday row) and Gate 4's audio line, which named a file this role no longer owns.
6. The mirror's `## 9A` preamble still says "See the role file Section 9A" — it now resolves, because the role file's Section 9 carries 9A. It did not before this unit.
