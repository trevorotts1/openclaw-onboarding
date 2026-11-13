# PD-017 — BUILD REPORT

**Unit:** PD-017 — One interview system (Severe, logic)
**Lane:** FL08 · repo `trevorotts1/openclaw-onboarding`
**Branch:** `pd/fl08-buddy-procedure--hold-d2`
**Code commit (this unit's change):** `4e59828d6175834dda06a32413536a25b33e5981`
**Approved builder model:** deepseek-chain

**Decision D-2: BUILT AND STAGED, NOT MERGEABLE UNTIL TREVOR ANSWERS D-2.**
The unit is staged on its branch and pushed. It must not be merged, and no PR should be
merged, until Trevor answers D-2 in `CONTROL/DECISIONS.md`. PD-013 and PD-023 ride the same
yes; their branches and files were not touched by this unit.

---

## Files changed (both are this lane's owned paths)

| File | Change |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/brainstorming-buddy-presentations.md` | +12 lines: HOW TO ASK paragraph at the top of SOP 9.0, plus one driver-question-id line per SOP 9.0 field |
| `23-ai-workforce-blueprint/templates/role-library/presentations/sops/brainstorming-buddy-presentations-sops.md` | Regenerated from the role file's section 9 (never hand-edited): +34 −21 |

`git show --numstat` for the code commit:

```
12	0	23-ai-workforce-blueprint/templates/role-library/presentations/brainstorming-buddy-presentations.md
34	21	23-ai-workforce-blueprint/templates/role-library/presentations/sops/brainstorming-buddy-presentations-sops.md
```

## What was added to SOP 9.0

Paragraph (present exactly once in the role file and once in the mirror, as the mirror's
section 9 copy):

> HOW TO ASK. Every question in this procedure is asked through the intake driver, one at a
> time: run deck-intake-driver.py --run-dir <RUN_DIR> --next, say the question it returns to
> the owner in your own warm voice (you may add the example given in this procedure for that
> field), wait for the owner's reply, then record it with --answer <id> "<the owner's exact
> words>" --owner-msg-id <the id of the owner's message>. Never keep answers only in
> brief.json. Never answer a question for the owner. When the driver reports "complete", run
> --complete. The driver is the record the build door checks.

Driver question ids, one line per field (role-file lines 199, 208, 217, 225, 232, 239, 249,
262, 276, 283):

| SOP 9.0 field | Line as written |
|---|---|
| REPRESENTATION_MIX | `Driver question id: representation_mix.` |
| AUDIENCE-COMPOSITION NOTE | `Driver question id: audience_composition_note.` |
| GROUNDED-CONTENT | `Driver question id: grounded_content.` |
| VISUAL_MIX | `Driver question id: visual_mix.` |
| DARK_OK | `Driver question id: dark_ok.` |
| HOOK SEED | `Driver question id: hook_seed.` |
| DELIVERABLE_SET | `Driver question ids: want_teleprompter, want_speech_script, want_audio_deliverable.` |
| WANT_AUDIO_DEMO | `Driver question id: want_audio_demo.` |
| TARGET_WPM | `Driver question id: speech_speed_preference.` |
| STYLE BRANCH | `Driver question id: style_source.` |

(The specification says "nine fields" and then lists ten mappings; all ten listed mappings
were written, verbatim as given.)

---

## Acceptance row A1 — evidence

### 1. The mirror equals the role file's section 9

There is no repository checker that compares a presentations role file's section 9 against
its `sops/` mirror. Named sources checked, all negative for that comparison:

- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/sync_check.py` —
  scans roles and `sops/*.md` for registration/phantom-symbol/stale-repo-path findings and
  checks every `sop_refs` file exists (step A7); it never compares section 9 to a mirror.
- `scripts/check-duplicate-sop-drift.py` (GATE 6 of `scripts/ci/presentations-drift-gates.sh`) —
  compares duplicated basenames between `role-library/<dept>/sops/` and `universal-sops/<pack>/`.
  This mirror has no `universal-sops` twin (`find universal-sops -name "*brainstorming*"` → no
  match), so it is not in that gate's scope.
- `23-ai-workforce-blueprint/scripts/verify-library-gate.sh` — substantive-SOP floor and
  authoring gate only.
- `23-ai-workforce-blueprint/scripts/verify-role-library.sh` — no `sops` mirror compare.

So the mirror check used is the direct extraction-and-diff (the mirror's own header states the
rule it enforces: "If they diverge, the role file wins and this mirror must be regenerated").

Command run (extract section 9 from the role file, then diff against the mirror body, which
begins at its own `## 9.` line 10):

```
python3 -I - ROLE section9.md   # extract "## 9. ..." up to the line before "## 10. "
diff /Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-017/role-section9.md \
     <(sed -n '/^## 9\. Standard Operating Procedures (Numbered)$/,$p' MIRROR)
```

Output:

```
=== MIRROR CHECK: diff role-section9 vs mirror body (from its '## 9.' line) ===
10:## 9. Standard Operating Procedures (Numbered)
diff rc=0
```

Exit 0, empty diff: the mirror body is byte-identical to the role file's section 9.

### 2. The inserted paragraph is present once

```
grep -c "HOW TO ASK\. Every question in this procedure is asked through the intake driver" ROLE
1
grep -c "HOW TO ASK\. Every question in this procedure is asked through the intake driver" MIRROR
1
```

### 3. No existing question text was deleted

Every line containing `Ask` was captured before the edit and after it, line numbers stripped:

```
diff q-before.txt q-after.txt
IDENTICAL: 16 Ask lines, no question text changed
```

`Ask:` occurrences specifically: 8 before, 8 after.

---

## Other places in the procedure (line 151 to end, read in full) that tell the agent to record answers somewhere other than the driver

Read the whole file (718 lines before this change) and listed every recording venue. These
remain, unchanged by this unit; each is a place the procedure still names brief.json or the
message channel as a record:

| Line (post-edit) | Text |
|---|---|
| 174 | HOW TO ASK (this unit's paragraph) — names the driver as the record |
| 291 | SOP 9.0 step 3 — "write the pre-presentation block to brief.json" |
| 302–326 | SOP 9.0 step 3 JSON block written to brief.json |
| 327 | SOP 9.0 Outputs — "`brief.json` with `pre_presentation_capture` block" |
| 348 | SOP 9.1 step 1 — "Record `interview_mode: \"simple\"`" |
| 353 | SOP 9.1 step 3 — "Capture into brief.json under its field key" |
| 362 | SOP 9.1 Output — `brief.json` draft |
| 385 | SOP 9.2 step 5 — "Capture every answer into brief.json under its field key, including verbatim quotes … (`owner_verbatim` array)" |
| 389 | SOP 9.2 Output — `brief.json` draft |
| 425 | SOP 9.3 step 4 — "Send via openclaw message send. WAIT for explicit confirmation" (channel, not a record) |
| 428–434 | SOP 9.3 steps 5–6 — set `interview_confirmed`, `confirmed_by`, `confirmed_at`, `confirmation_message`; "Write the final brief.json" |
| 460 | SOP 9.4 step 5 — "Record `handoff_at`, `handoff_to`, `dispatch_id` in brief.json" |

No other place names a second answer store.

---

## Divergence resolved while regenerating the mirror (recorded, not hidden)

The mirror on `main` had been hand-edited and carried five passages the role file does not
have. Regenerating the mirror from the role file (as this unit's spec directs — "regenerate
the mirror from the role file; never edit the mirror by hand") therefore removed them from
THIS mirror. They were not carried into the role file, because that is outside this unit's
named change:

1. SOP 9.1 step 3a — Decision 1C ASSET BRANCH (`asset_intake_question_asked`, AF-ASSET-QUESTION-MISSING)
2. SOP 9.1 step 3b — Decision 2A PITCH BRANCH (`pitch_included`, AF-PITCH-FLAG-UNSET)
3. SOP 9.1 step 3c — PRICE-SEPARATION BRANCH (`EVENT_PRICE` / `ACCESS_FREE` vs `FINAL_PRICE`, `free_only_close`)
4. SOP 9.2 steps 2a/2b — the same ASSET and PITCH branches for the extensive path
5. Smaller wording gaps the role file already carried the newer form of: TARGET_WPM
   "ruling 9.3" wording, the `target_wpm_defaulted` key in the JSON block, and SOP 9.4's
   full speech-chain specialist list.

The same doctrine still ships in the sibling dept mirrors
(`offer-price-strategist-sops.md`, `director-of-presentations-sops.md`,
`devils-advocate-presentations-sops.md`) and in the intake bank and autofail ruleset. If
Trevor wants that doctrine to survive on the Brainstorming Buddy specifically, it must be
added to the ROLE file (the authoritative side) by its own unit, and the mirror regenerated
again — not hand-patched.

---

## Every command run, with its result

| # | Command | Result |
|---|---|---|
| 1 | `git branch --show-current` (FL08 worktree) | `pd/fl08-buddy-procedure--hold-d2` — matches ledger row |
| 2 | `git rev-parse HEAD` before work | `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc` |
| 3 | `python3 -c` print PD-017 ledger row | branch/worktree/note read as above |
| 4 | `grep -n "D-2" CONTROL/DECISIONS.md` | `D-2 \| HOLD \| PD-013, PD-017, PD-023 built, staged` |
| 5 | `sed -n '1800,1900p' 01-BUILD-SPEC.md` | unit text read; change, acceptance A1 confirmed |
| 6 | `grep -n "Ask:" ROLE > ask-before.txt` | 16 matching lines, 8 of them `Ask:` |
| 7 | Edit ×11 on the role file | 1 paragraph + 10 driver-id lines inserted, 0 deletions |
| 8 | `python3 -I regen_mirror.py > $TMPDIR/PD017.*` | 307-line mirror generated from section 9 |
| 9 | `cp` generated file → mirror path | mirror replaced |
| 10 | `diff role-section9.md <(sed -n '/^## 9\./,$p' MIRROR)` | rc=0, no output — mirror equals section 9 |
| 11 | `grep -c "HOW TO ASK…"` ROLE / MIRROR | `1` / `1` |
| 12 | `grep -n "Driver question id"` ROLE | 10 lines, listed above |
| 13 | `diff q-before.txt q-after.txt` | identical, 16 Ask lines, 8 `Ask:` — no question text deleted |
| 14 | `git status --short` | 2 modified files, both this lane's owned paths |
| 15 | `git diff --stat` | 46 insertions, 21 deletions |
| 16 | `git add <both files> && git commit` | `4e59828d6` |
| 17 | `git push origin HEAD:refs/heads/pd/fl08-buddy-procedure--hold-d2` | new branch created on origin |
| 18 | `git ls-remote --heads origin pd/fl08-buddy-procedure--hold-d2` | `4e59828d6175834dda06a32413536a25b33e5981` = local HEAD (`REMOTE_PROOF=PASS`) |

Note: the branch's upstream was `origin/main`, so the push was made with an explicit refspec
(`HEAD:refs/heads/pd/fl08-buddy-procedure--hold-d2`). Nothing was pushed to `main`.

## Storage

Temp files: `/Volumes/mac mini m4/swarm-contract/pd-fix/tmp/PD017.FoaSOn` (via `mktemp -p "$TMPDIR"`).
Scratch: `/Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-017/`. No `/tmp` path used.

---

# PD-017 — REPAIR PASS (QC fail `50326dc9f4ac…`, five dropped passages)

**Repair code commit:** `330f12fc5440e77d98323f3a2c05d6101e37fd9b` — the two SOP files, on `pd/fl08-buddy-procedure--hold-d2`
**Base for the repair:** `50326dc9f4ac0fa7cddeba232bb99d9c145d8fdb` (the tree the reviewer failed)
**Isolation:** own worktree at
`/Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-017/worktree`
(branch `pd017-fix` from the tip). The lane clone was read only and left clean.

## Decision: which file each passage belongs in

**The ROLE file is the correct home for all five.** Reasons, all from the repo itself:

- The mirror's own header says: *"This file mirrors the role file. The role file is
  authoritative. If they diverge, the role file wins and this mirror must be regenerated."*
- The mirror is generated by extracting the role file's `## 9.` section. A passage that lives
  only in the mirror is deleted by the next regeneration — the exact bug under repair.
- `brainstorming-buddy-presentations/00-START-HERE.md:214` registers this mirror as covering
  `9.1 Simple Interview, 9.2 Extensive Interview, 9.3 Confirm-and-Lock, 9.4 Kickoff/Handoff`,
  so all five passages are in-scope section-9 content.
- The original build report's own closing note (above) said the durable fix is "added to the
  ROLE file (the authoritative side) by its own unit, and the mirror regenerated again — not
  hand-patched." This pass does exactly that.

No mirror-only section and no generator change is needed: the generator is a plain section-9
extract, so once the text is in the role file every regeneration carries it.

## 1. BEFORE — proof the passages were gone at the failed tip

Occurrence counts (`grep -o … | wc -l`) on `50326dc9f` (the tree the reviewer failed):

```
asset_intake_question_asked = role 0 | mirror 0
AF-ASSET-QUESTION-MISSING  = role 0 | mirror 0
pitch_included             = role 0 | mirror 0
AF-PITCH-FLAG-UNSET        = role 0 | mirror 0
PRICE-SEPARATION           = role 0 | mirror 0
EVENT_PRICE                = role 0 | mirror 0
```

The reviewer's PRE-MIRROR numbers **verified exactly** on `4e59828d6^` (the mirror before
PD-017 regenerated it), counting occurrences, not lines:

```
asset_intake_question_asked = 2
AF-ASSET-QUESTION-MISSING  = 2
pitch_included             = 7
AF-PITCH-FLAG-UNSET        = 2
PRICE-SEPARATION           = 2
EVENT_PRICE                = 3
```

So the reviewer's `2/2/7/2/2/3` is correct (line counts were `2/2/4/2/2/2`; occurrences are
`2/2/7/2/2/3`). Loss confirmed, not reconciliation.

## 2. AFTER — the same six counts, in the authoritative file and the mirror

Role file (`brainstorming-buddy-presentations.md`) and mirror
(`sops/brainstorming-buddy-presentations-sops.md`) after the repair:

```
asset_intake_question_asked = role 2 | mirror 2
AF-ASSET-QUESTION-MISSING  = role 2 | mirror 2
pitch_included             = role 7 | mirror 7
AF-PITCH-FLAG-UNSET        = role 2 | mirror 2
PRICE-SEPARATION           = role 1 | mirror 2   (mirror's extra hit is the version header)
EVENT_PRICE                = role 3 | mirror 3
target_wpm_defaulted       = role 3 | mirror 3
TARGET_WPM                 = role 10 | mirror 9
```

The five passages are present verbatim — each inserted block is a `grep -Fxc` match of
exactly `1` in both role and mirror (`grep -F`, whole line, no regex):

```
9.1 step 3a ASSET BRANCH            role 1 | mirror 1
9.1 step 3b PITCH BRANCH            role 1 | mirror 1
9.1 step 3c PRICE-SEPARATION BRANCH role 1 | mirror 1
9.2 step 2a ASSET BRANCH            role 1 | mirror 1
9.2 step 2b PITCH BRANCH            role 1 | mirror 1
```

Also restored: the price-assumption read-back in 9.1 step 5 (`EVENT_PRICE`, `FINAL_PRICE`,
`pitch_included` must be marked `assumed: true`, read back at lock, never denied).
TARGET_WPM "ruling 9.3" wording, the `target_wpm_defaulted` key, and the full SOP 9.4
speech-chain specialist list were already carried by the role file and are present in both.

## 3. SURVIVAL — regenerate again and the passages are still there

This is the test that matters. Re-ran the mirror generator from the role file into a fresh
file and compared it to the committed mirror:

```
python3 -I regen_mirror_240.py > /tmp/regen2.md     # rc=0
diff -q /tmp/regen2.md <mirror>                     # rc=0 (identical — no output)
```

Counts in the freshly regenerated file:

```
asset_intake_question_asked = 2
AF-ASSET-QUESTION-MISSING  = 2
pitch_included             = 7
AF-PITCH-FLAG-UNSET        = 2
PRICE-SEPARATION           = 2
EVENT_PRICE                = 3
target_wpm_defaulted       = 3
TARGET_WPM                 = 9
```

All five blocks also `grep -Fxc` = `1` in the regenerated file. The regeneration reproduces
the committed mirror byte-for-byte, so the next regen cannot delete them again.

Section-9 equality (the mirror's own rule) is `rc=0` on both trees:

```
base 50326dc9f: role section 9, 298 lines = mirror body, 298 lines   diff rc=0
head (repair):  role section 9, 305 lines = mirror body, 305 lines   diff rc=0
```

## 4. The two gates still have teeth

Fixtures under
`/Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-017/gate-fixture/`.
Driver imports the real `build_deck.py` and calls the real gate functions
(`_chk_asset_question`, `_chk_pitch_flag`) — no reimplementation.

Negative deck (`intake.json` lacks both flags): exit **3**. Exact stderr:

```
FATAL: PROCESS PREFLIGHT FAILED — refusing to render or assemble.
Missing or incomplete required artifacts:

  - (run-dir scoped gate)  asset-intake question asked
      reason:  AF-ASSET-QUESTION-MISSING: intake.json does not record asset_intake_question_asked:true. Every signature run MUST ask the client the one asset-intake question (photos / a logo / brand colors / a rough or old deck / slides / concepts) and record that it was asked. See Brainstorming Buddy SOP 9.1/9.2 + Director intake.
      produced by: Intake — Brainstorming Buddy SOP 9.1/9.2 + Director
  - (run-dir scoped gate)  pitch_included captured
      reason:  AF-PITCH-FLAG-UNSET: intake.json.pitch_included must be an explicit boolean captured at intake (true = the presentation ends with an offer/pitch; false = a teaching/content-only presentation). It was None. Never default it — ask the client and record yes/no.
      produced by: Intake — Brainstorming Buddy + Director
```

Positive control (same deck with `asset_intake_question_asked: true`, `pitch_included: false`):
exit **0**, `PASS: both intake-flag gates returned no problem (deck not refused)`. The gate
discriminates; the failure is not a blanket refusal.

Note the gate's own message points at the SOP the Buddy reads: *"See Brainstorming Buddy
SOP 9.1/9.2 + Director intake."* That instruction now exists again in both role and mirror.

## 5. Regression — SOP/mirror equality and the presentation in-sync check, by test id

There is **no repository test id** that compares a presentations role file's section 9 to its
`sops/` mirror; the original build report reached the same conclusion after naming the four
candidate checkers. The equality check is the direct extract-and-diff the mirror's own header
defines, run above (base rc=0, head rc=0).

The real, runnable in-sync tests, by name/id, on base and head:

| Test (id) | Base `50326dc9f` | Head (repair) |
|---|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/sync_check.py` (full lockstep) | exit 0 — IN SYNC | exit 0 — IN SYNC |
| `…/sync_check.py --sops-only` (SOP AUDIT: phantom-symbol, stale-repo-path, unresolved-registration) | exit 0 — Zero findings | exit 0 — Zero findings |
| `tests/unit/test_build_library_role_floor.py` | exit 0 | exit 0 |
| `scripts/ci/presentations-drift-gates.sh` GATE 6 (duplicate-SOP authority) | out of scope: `find universal-sops -name '*brainstorming*'` = 0, no twin to disagree with | same |

Base and head are identical on every runnable check. No test changed from pass to fail.

## Repair diff

```
12  5  23-ai-workforce-blueprint/templates/role-library/presentations/brainstorming-buddy-presentations.md
13  6  23-ai-workforce-blueprint/templates/role-library/presentations/sops/brainstorming-buddy-presentations-sops.md
```

The role-file hunk is the section-9 restore, and it also repairs a corruption left by the
bad regen: 9.1 carried two steps numbered `3` and a step 4 whose sentence was split by the
displaced "already captured in SOP 9.0" clause. The restore returns the pre-change numbering
(`3`, `3a`, `3b`, `3c`, `4`, `5`, `6`) with the PD-017 STYLE BRANCH step kept intact. The
mirror hunk is the regeneration output (header version 2.4 plus the restored section 9).

## Push proof

```
local  330f12fc5440e77d98323f3a2c05d6101e37fd9b
remote 330f12fc5440e77d98323f3a2c05d6101e37fd9b
```

`git push origin HEAD:refs/heads/pd/fl08-buddy-procedure--hold-d2` reported
`50326dc9f..330f12fc5  HEAD -> pd/fl08-buddy-procedure--hold-d2`. `git ls-remote` returns the
same full 40-character hash as `git rev-parse HEAD`, compared literally. Nothing was pushed to
`main`; the D-2 hold is intact and this branch was not merged.

## Files this repair changed

- `23-ai-workforce-blueprint/templates/role-library/presentations/brainstorming-buddy-presentations.md`
  — the authoritative role file: five passages restored in section 9 (9.1 steps 3a/3b/3c and
  the step-5 price read-back; 9.2 steps 2a/2b), malformed 9.1 numbering repaired.
- `23-ai-workforce-blueprint/templates/role-library/presentations/sops/brainstorming-buddy-presentations-sops.md`
  — regenerated from the role file's section 9 (header version 2.4); not hand-edited.
- `evidence/PD-017/BUILD-REPORT.md` — this report.
