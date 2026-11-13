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
