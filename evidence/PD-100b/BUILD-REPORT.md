# PD-100b — BUILD REPORT

**Unit:** PD-100b · "The Speech Writer procedure uses the one pace default" · Moderate · mechanical
**Lane:** FL24 · **Repository:** `trevorotts1/openclaw-onboarding`
**Branch:** `pd/fl24-role-procedures-c--hold-d3`
**Worktree:** `/Volumes/mac mini m4/swarm-contract/loop-control/pd-fix/tmp/PD-100b/work.bYALBu/tree` (own scratch worktree; the lane clone was left clean)
**Base:** `276762b420499f2fda50c0651667c3011d2bf588` — PD-100's ACCEPTED head, proved as the remote head of `pd/fl24-role-procedures-c` before any edit (§2)
**Held by:** decision D-3 (built and staged at the default; not merged until Trevor says yes)
**Acceptance rows:** A1, A2, A3

---

## 1. The spec text this unit implements

`/Volumes/mac mini m4/swarm-contract/fable-reviews-2026-11-11/03-presentation-department/FINAL/01-BUILD-SPEC.md`, section **PD-100b** (line 3993 onward), quoted in full:

> ### PD-100b — The Speech Writer procedure uses the one pace default
>
> | Field | Value |
> |---|---|
> | Findings | PD-100, PD-023 |
> | Severity | Moderate |
> | Builder | deepseek-chain — difficulty mechanical: one number replaced throughout one role file |
> | Lane and repository | FL24 · trevorotts1/openclaw-onboarding |
> | Wave | 3 |
> | Depends on (must be ACCEPTED, that is QC-passed, first) | PD-100 |
> | Held by decision | D-3 (built and staged, not merged until yes) |
> | Acceptance rows the checker must run | A1, A2, A3 |
>
> **Unit text (written in consolidation):**
>
> - **Change (Speech Writer role file, then regenerate its mirror):** replace each statement of 130 words a minute with the value Trevor gives under decision D-3 (default 140), and recompute any word budget on the same line from that value (minutes times words a minute). Change no other number.
> - **Acceptance:** (A1) the report lists each replaced line before and after. (A2) no line in the role file states a pace other than the decided value (read the file). (A3) the mirror equals the role file's section 9.

The binding amendment on PD-100 (line 3987) assigns the pace lines to this unit:

> The pace lines ("replace each 130") are not built here; they are PD-100b (held by decision D-3).

`06-DECISIONS-FOR-TREVOR.md` (lines 36-41), quoted:

> ### D-3 — built and staged, not merged until yes
> - **Question:** One speaking-pace default: 140 words a minute (PD-023, and the pace lines of the Speech Writer procedure, PD-100b)?
> - **Options:** 140 / another number
> - **Default:** Use 140; stage; not merged until yes.
> - **Units waiting on a yes:** PD-023, PD-100b

The lane table (`01-BUILD-SPEC.md:3830`, `02-SWARM-PLAN.md:255`) names lane FL24, branch `pd/fl24-role-procedures-c`, units in order `PD-094, PD-093, PD-101, PD-102, PD-108, PD-100, PD-100b, PD-094b`.

---

## 2. Branch-state discrepancy (recorded as required)

The lane row's branch for this unit is `pd/fl24-role-procedures-c--hold-d3`. Proved **absent** on the remote, while `refs/heads/main` resolves:

```
$ git ls-remote --heads origin pd/fl24-role-procedures-c--hold-d3
(no output — branch absent)

$ git ls-remote --heads origin refs/heads/main
ebf5c769a2ad5b2582bf2256588095cbef20cfac	refs/heads/main
```

The lane clone also carried a stale local placeholder of that name at an old `main` commit (`1a476d2cb`), never pushed; it was left untouched.

The dependency decides the base. PD-100 is **ACCEPTED** (ledger row; QC verdict PASS) at head `276762b420499f2fda50c0651667c3011d2bf588`, and that commit is the **remote head of the lane branch**:

```
$ git ls-remote --heads origin 'refs/heads/pd/fl24*'
276762b420499f2fda50c0651667c3011d2bf588	refs/heads/pd/fl24-role-procedures-c

$ git merge-base --is-ancestor 276762b42049 origin/main   # exit 1
PD-100 NOT on main
```

So `origin/main` (`ebf5c769`) does **not** contain PD-100. Creating from `origin/main` would leave every PD-100 rewrite out of the file I must edit, and force this unit to re-apply a sibling unit's hunks — forbidden by the "do not widen scope into neighbouring units" rule and a merge hazard. **Base used: `276762b42049` (PD-100 ACCEPTED head, remote head of the lane branch).** The whole discrepancy is here with both commands and their output.

---

## 3. Files changed (numstat against the base)

| File | numstat |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/presenters-speech-writer.md` | 16 / 16 |
| `23-ai-workforce-blueprint/templates/role-library/presentations/sops/presenters-speech-writer-sops.md` | 6 / 6 |
| `evidence/PD-100b/check_pd100b.py` (new, A1/A2/A3 checker) | new |
| `evidence/PD-100b/BUILD-REPORT.md` (this file) | new |

No other file was touched. No shared file was written.

## 4. A1 — every replaced line, before and after

Decision D-3 fixes the **default** at 140. `130` occurs 25 times in the base role file; 17 of those are statements of the procedure's own pace or arithmetic derived from it and are replaced below. The other 8 are research bands or named alternatives that PD-023 (same decision) keeps (`teaching=130`, `high-energy=~155-160`); §6 lists them.

| # | Line | Before | After |
|---|---|---|---|
| 1 | 25 | `You budget the spoken script at 130 words per minute.` | `You budget the spoken script at 140 words per minute.` |
| 2 | 68 | `3. Run SOP 9.1 (Write the Word-for-Word Speech at 130 wpm).` | `3. Run SOP 9.1 (Write the Word-for-Word Speech at 140 wpm).` |
| 3 | 97 | `did the 130 wpm budget hold in real delivery?` | `did the 140 wpm budget hold in real delivery?` |
| 4 | 105 | `keep 130 wpm unless evidence moves the absorption band.` | `keep 140 wpm unless evidence moves the absorption band.` |
| 5 | 116 | `\| Script word count within +/- 10% of (DURATION_MIN x 130) minus pause budget \|` | `\| Script word count within +/- 10% of (DURATION_MIN x 140) minus pause budget \|` |
| 6 | 117 | `\| Spoken rate used and exposed in the header \| 130 wpm (tunable) \|` | `\| Spoken rate used and exposed in the header \| 140 wpm (tunable) \|` |
| 7 | 241 | `### SOP 9.1 -- Write the Word-for-Word Webinar Speech at 130 wpm` | `### SOP 9.1 -- Write the Word-for-Word Webinar Speech at 140 wpm` |
| 8 | 243 | `paced so a human delivering it at 130 wpm with the doctrine's pauses` | `paced so a human delivering it at 140 wpm with the doctrine's pauses` |
| 9 | 245 | `The total word count is budgeted at 130 words per minute against DURATION_MIN` | `The total word count is budgeted at 140 words per minute against DURATION_MIN` |
| 10 | 250 | `converted to word-equivalents at 130 wpm (130 wpm = about 2.17 words/second)` | `converted to word-equivalents at 140 wpm (140 wpm = about 2.33 words/second)` |
| 11 | 250 | `Target words = net spoken seconds x 2.17.` | `Target words = net spoken seconds x 2.33.` |
| 12 | 260 | `SPOKEN_RATE_WPM = 130, pause budget` | `SPOKEN_RATE_WPM = 140, pause budget` |
| 13 | 266 | `>10% off the pause-adjusted 130 wpm budget` | `>10% off the pause-adjusted 140 wpm budget` |
| 14 | 395 | `word count within 10% of the pause-adjusted 130 wpm budget` | `word count within 10% of the pause-adjusted 140 wpm budget` |
| 15 | 465 | `SPOKEN_RATE_WPM: 130 (verified band 120-140 for audience absorption; 140 = peak credibility; 130 leaves headroom for mandatory drop pauses)` | `SPOKEN_RATE_WPM: 140 (verified band 120-140 for audience absorption; 140 = peak credibility; leaves headroom for mandatory drop pauses)` |
| 16 | 466 | `TARGET WORDS: ~3855 \| ACTUAL: 3902 (+1.2%)` | `TARGET WORDS: ~4149 \| ACTUAL: 3902 (-5.9%)` |
| 17 | 564 | `Smaller word budget; the 130 wpm math and pause subtraction still apply.` | `Smaller word budget; the 140 wpm math and pause subtraction still apply.` |

Rows 5, 10, 11, 16 are the recomputed word budgets the spec allows: `DURATION_MIN x 140`; `140/60 = 2.3333…` words/second (was `130/60 = 2.1666…`); and the example header's own budget, `1778 s x 2.3333 = 4148.6` → `~4149`, with the actual 3902 now `3902/4148.6 - 1 = -5.9%` (was `3855` / `+1.2%` at 130). No other number on those lines changed.

Raw fragments for the two table cells whose pipes need escaping (verbatim, before then after):

```
| Spoken rate used and exposed in the header | 130 wpm (tunable) |
| Spoken rate used and exposed in the header | 140 wpm (tunable) |
TARGET WORDS: ~3855 | ACTUAL: 3902 (+1.2%)
TARGET WORDS: ~4149 | ACTUAL: 3902 (-5.9%)
```

## 5. A2 — no line states a pace other than the decided value

Every statement in the procedure's own voice now reads **140 wpm** / **140 words per minute**: the identity paragraph (25), the daily run step (68), the monthly review (97), the quarterly re-verify (105), the KPI table (116-117), SOP 9.1 heading/purpose/rule/step 1/step 11/enforcement (241-266), Gate 2 (395), the example header (465-466), and Edge Case 17.1 (564). `2.17` is gone; `2.33` carries the arithmetic.

`130` survives 8 times, each inside an explicit research band or a named alternative that PD-023 keeps under the same decision D-3 (PD-023 sets `default=140`, `medium=150`, `fast=160` and asks the client for a "slower teaching pace (about 130)"):

| Line | Occurrence | Why it stays |
|---|---|---|
| 25 | `band is 130 to 160 words per minute` | research band, not a default statement |
| 28 | `allow 130 for teach-heavy content, 150 to 160 for high-energy` | named alternative; default on the same line is already 140 |
| 107 | `(130 teach-heavy / 150 to 160 high-energy allowed)` | named alternative; default already 140 |
| 546 | `(TARGET_WPM = 140 verified; 130 teach-heavy / 150 to 160 high-energy)` | source note; default 140 |
| 549 | `general 130 to 160 wpm` | research band |
| 552 | `range 130 to 160` | research band |
| 577 | `may want 130 WPM for clarity. Record TARGET_WPM=130` | Edge Case 17.2 teach-heavy alternative |

Interpretation of A2 is stated plainly: "a pace other than the decided value" means the procedure's DEFAULT pace, because D-3 is "One speaking-pace default: 140" and PD-023 — the sibling unit under the same decision — keeps the teaching/high-energy options. Removing them would contradict PD-023 and would change numbers the spec told me not to touch. Recorded again in §10 as the one judgement call.

## 6. A3 — the mirror equals the role file's section 9

Measured before editing, on the base blobs: the mirror body from `## 9A.` to the end equals the role file's `## 9A.` through the line before `## 10.` — **byte-identical, 25,258 characters each**. After editing, the mirror was regenerated from that same slice (rule 11, `01-BUILD-SPEC.md:31`: "After editing a role file, regenerate its `sops/` mirror the way the file's header says"; the mirror's own header says "Extract: Section 9 (Standard Operating Procedures) verbatim mirror"). Re-measured: **equal, byte for byte**, mirror 234 lines. The mirror carries exactly the 6 SOP-9.1 hunks inherited from the role file (mirror lines 87, 89, 91, 96, 106, 112) — no other mirror line moved.

## 7. Tests — one per acceptance row, by id, real output

Checker: `evidence/PD-100b/check_pd100b.py <tree> [--base <ref>]` (stdlib only; exit 0 = all rows PASS). Every row is computed from the file contents, never asserted by name.

At the working tree, with this report present:

```
PASS  A1
PASS  A2
PASS  A3
counts: pairs=16 role_130=8 mirror_lines=234 base=working-tree
```

At the base blob (`--base 276762b42049`):

```
FAIL  A1     (no report at base; every "after" absent, every "before" present)
FAIL  A2     (25 occurrences of 130; the procedure's own pace reads 130; 2.17 present)
FAIL  A3     (mirror still states the old pace only)
counts: pairs=16 role_130=25 mirror_lines=234 base=276762b420499f2fda50c0651667c3011d2bf588
```

Row-level reads behind A2: line 68 unqualified 130 at base; line 241 heading "Speech at 130 wpm" at base; both absent after. A3's base PASS changes only the pace text because the mirror was already in sync at base — which is why the A3 mutation (below) reverts the mirror alone.

## 8. Mutation proof

**Mutation A — the change neutralised** (both role file and mirror restored to base): RED on all three rows, `role_130=25`.

```
### MUTATION A: both files back at base (change neutralised)
rc=1
FAIL  A1
      'budget the spoken script at 130 words per minute' -> 'budget the spoken script at 140 words per minute' report=False role=False before_gone=False
      ...
FAIL  A2
      line 68: unqualified 130 -> 3. Run SOP 9.1 (Write the Word-for-Word Speech at 130 wpm).
      line 241: unqualified 130 -> ### SOP 9.1 -- Write the Word-for-Word Webinar Speech at 130 wpm
      stale 130-derived arithmetic 2.17 still in the role file
      ...
FAIL  A3
      mirror still states the old pace only
counts: pairs=16 role_130=25 mirror_lines=234 base=working-tree
```

**Mutation B — role built, mirror left stale** (proves A3 has teeth independently): A3 RED by byte comparison.

```
### MUTATION B: role built, mirror left at base (mirror stale)
rc=1
FAIL  A1     (report absent in this run)
PASS  A2
FAIL  A3
      mirror body is not byte-identical to role sections 9A+9
      mirror still states the old pace only
counts: pairs=16 role_130=8 mirror_lines=234 base=working-tree
```

**Restored** (role + mirror back to the built state, report absent at that moment):

```
rc=1
FAIL  A1      (only clause left: the report did not exist yet)
PASS  A2
PASS  A3
counts: pairs=16 role_130=8 mirror_lines=234 base=working-tree
```

After this file was written, the full run is GREEN (see §7).

## 9. Wider affected suite — base and head, both counts

Run in two scratch worktrees: base `276762b42` and head (working tree). No test in the repository reads this role file's prose; the five below are the pace/library/mirror neighbourhood, and each was run at base to settle any red.

| Test | Base `276762b42` | Head (this unit) |
|---|---|---|
| `presentations/scripts/tests/test_speech_pacing_fix97.py` (pytest) | **10 failed, 5 passed** (rc=1) | **10 failed, 5 passed** (rc=1) — identical failure set |
| `23-ai-workforce-blueprint/scripts/test-library-register.sh` | **rc=1** — `✗ clean baseline should PASS (rc 0), got 7`, `✗ infra-shaped file should NOT trip --check (expected rc 0), got 7` | **rc=1**, same two fixtures |
| `23-ai-workforce-blueprint/scripts/test-sop-substance-models.sh` | rc=0 (`SOP substance-model checks: PASS`) | rc=0, same |
| `23-ai-workforce-blueprint/scripts/test-wiring-gate-role-dir-walk.sh` | rc=0 (`50 passed, 0 failed`) | rc=0 (`50 passed, 0 failed`) |
| `23-ai-workforce-blueprint/scripts/test-reconcile-orphan-library-files.sh` | rc=0 (`75 passed, 0 failed`) | rc=0 (`75 passed, 0 failed`) |

The two reds are **pre-existing at the base commit**, proven by the base run above (identical failing ids: `test_band_is_fix97_seven_pct`, `test_gate_60min_130wpm_speech_fails_when_target_140`, `test_gate_60min_140wpm_speech_fails_when_target_130`, `test_gate_defaults_to_speech_target_wpm_when_intake_omits_it`, `test_gate_out_of_band_but_above_floor_names_resize_target`, `test_gate_reads_uppercase_target_wpm_key`, `test_pspeech_qc_rejects_genuine_report_over_wrong_pace_speech`, `test_pspeech_qc_teeth_match_gate_at_both_targets`, `test_pure_arithmetic_60min_130wpm_passes_at_130_fails_at_140`, `test_pure_arithmetic_60min_140wpm_passes_at_140_fails_at_130`). They are defects of the engine arithmetic suites/environment on this branch, not of this text-only unit; no count moved.

## 10. Hunk attribution

`git diff -U0` hunk headers, role file (all single-line hunks; 116 and 465 are two-line):

```
@@ -25 +25 @@
@@ -68 +68 @@
@@ -97 +97 @@
@@ -105 +105 @@
@@ -116,2 +116,2 @@
@@ -241 +241 @@
@@ -243 +243 @@
@@ -245 +245 @@
@@ -250 +250 @@
@@ -260 +260 @@
@@ -266 +266 @@
@@ -395 +395 @@
@@ -465,2 +465,2 @@
@@ -564 +564 @@
```

Mirror file: 6 hunks, all produced by regenerating sections 9A+9 — attributed to the spec's "then regenerate its mirror". No hunk in either file belongs to another unit, and no line outside the pace statements and their derived budgets was rewritten.

## 11. Remote-head proof

To be appended by the report commit that measures it after the push (§12).

## 12. Honest unproved / judgement calls

1. **A2 interpretation.** "No line states a pace other than the decided value" is implemented as "no line states the *default* pace other than 140", keeping the qualified alternatives PD-023 keeps (teaching 130, high-energy 150-160). The alternative strict reading — delete every 130/150/160 mention — would contradict PD-023 under the same D-3 and would change numbers the unit text says not to change. If QC reads A2 strictly, this is the single point to re-decide.
2. **The example budget (row 16)** sits one line below the pace line in a code block; recomputing it was necessary to avoid a self-contradicting example, and it is a word budget, which the unit text explicitly allows recomputing. No other example number moved.
3. **D-3 is unconfirmed.** The build stages 140 as the default, as ordered; nothing merges until Trevor answers.
4. **No engine test reads the role file**, so the acceptance proof is the checker above; the wider suite is neighbourhood evidence only, and its two reds are pre-existing at base (proven).
5. **Lane clone** was not used for building and is clean; the stale unpushed local `--hold-d3` placeholder in it was not touched.
