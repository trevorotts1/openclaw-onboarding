# PD-072 — Put the fix text in the prompt failure reason

- Unit: PD-072 (Moderate, mechanical), lane FL17, position 7
- Branch: `pd/fl17-phase-checks`
- Spec used: `PASS4-ENGINE.md`, section "PD-072 — Put the fix text in the reason"
  (finding evidence at section "PD-072 — When a prompt fails at step level, the
  reason text is empty"), plus its acceptance row in `_scratch-pd-docs/acc.txt`
  line 171 — A1: "a too-short prompt → the reason contains the measured
  character count and the words to add."
- Fix commit: `da995d14e0a865fd68cbe1b1dc21b6c3fa728725`
- Parent (pre-fix branch head): `a97fcc9ca640f5131d6c9504a228f19de91c09cf`

## The defect

`phase_verifiers.py`, `_verify_prompt`, when the deterministic measurer returns
`pass: false`:

    reasons.append(
        f"AF-PROMPT-FLOOR slide-{sid}: {d.get('code', '?')} — {d.get('detail', '')}"
    )

The deficiency record built by `build_deck._pdef` (build_deck.py:9644-9647) has
no `detail` key. Its keys are `code`, `severity`, `measured`, `required`,
`intelligence`, `fix`. `d.get('detail', '')` therefore resolves to `""` and the
reason reaches the engine's regenerate order and the client's pause message as
`AF-PROMPT-FLOOR slide-3: AF-P1 — ` with nothing after the dash.

## The change

`phase_verifiers.py` — the reason detail is now built from the record's own
fields: `measured` (with `required` when present) then `fix`. `detail` is kept
as a first preference so a caller that ever does supply one is not discarded;
the record's `intelligence` is the last fallback, so the reason can never end in
an empty dash for any shape the measurer emits today.

No other file changed. `build_deck.py`, `dispatcher.py` and every sibling-owned
path were left untouched.

`tests/test_pd_phase_checks_prompt_reason.py` (new, matches the lane's
`test_pd_phase_checks_*.py` naming):

- `test_a1a…` hermetic: stubs `_bd_fn` with the real `_pdef` record shape and
  asserts the reason names the measured count and the ADD text.
- `test_a1b…` end to end: writes `working/copy/slides.json` and a real 38-char
  `working/prompts/slide-01.txt`, then runs `_verify_prompt` through
  `build_deck.check_prompt_qc_deterministic`. This is the acceptance row as the
  client would hit it.

## Proof

Probe: a throwaway probe script kept outside the tree (not committed; ephemeral run dirs).
It loads one `phase_verifiers.py` by path inside the real scripts dir, so HEAD
bytes and fixed bytes are exercised in the same import context.

### 1. Too-short prompt, BEFORE (HEAD `a97fcc9ca`)

    ok=False
    REASON: AF-PROMPT-FLOOR slide-1: AF-P1 —
    REASON: AF-PROMPT-FLOOR slide-1: AF-P-STRUCT —
    ...
    HAS_CHAR_COUNT=False
    HAS_ADD_TEXT=False

Every reason ends at the empty dash: no count, no instruction. This is the
reported defect reproduced on the live parent.

### 2. Too-short prompt, AFTER (`da995d14e`)

    ok=False
    REASON: AF-PROMPT-FLOOR slide-1: AF-P1 — measured 38 chars (required inside the rule 12 band); prompt is 38 chars (0.2% of max 20000), below the 80 percent floor: ADD at least 15962 chars of genuine specification to reach 16000, and ADD at least 18962 chars to reach the 19000 target (reject and rewrite, never pad). Re-author with real specificity; do NOT pad.
    ...
    HAS_CHAR_COUNT=True
    HAS_ADD_TEXT=True

The reason now carries the measured character count (38 chars) and the words
to add (ADD at least 15962 chars … to 16000, ADD at least 18962 to 19000).
`ok=False` is unchanged: this unit fixes the message, not the verdict.

### 3. Negative control — the new test fails on the parent

Same test file copied into a worktree at `a97fcc9ca`, then run:

    2 failed in 1.26s
    E AssertionError: the reason must not end at the empty dash,
      got ['AF-PROMPT-FLOOR slide-3: AF-P1 — ']
    E AssertionError: ... got ['AF-PROMPT-FLOOR slide-1: AF-P1 — ',
      'AF-PROMPT-FLOOR slide-1: AF-P-STRUCT — ', ...]

On the fixed tree the same file:

    2 passed in 2.85s

The row cannot pass on the old behaviour, so it proves something.

### 4. Owned suite, both trees

Seven files: `test_pd_phase_checks_audio.py`,
`test_pd_phase_checks_human_review.py`, `test_pd_phase_checks_typography.py`,
`test_pd061_verifier_paths.py`, `test_pd088_design_phase.py`,
`test_fix112_missing_producers.py`, `test_pd_phase_checks_prompt_reason.py`.

| tree | pass | fail |
|---|---|---|
| HEAD `a97fcc9ca` | 32 | 3 |
| fixed `da995d14e` | 34 | 1 |

The three HEAD failures are the two new assertions plus the pre-existing
`test_fix112_missing_producers.py::test_infographic_checklist_phase_exists_with_role_file_and_verifier`.
On the fixed tree the only remaining failure is that same pre-existing one —
identical name, already failing before this unit and outside its scope. No test
was weakened, deleted, renamed, skipped or marked xfail.

### 5. PD-924 retargeted assertions untouched

`test_runfacts.py` + `tests/test_trust_boundary_observability.py`, identical on
both trees:

    HEAD  : 1 failed, 33 passed — TestPreflightFamily::test_clean_run_summary_line_is_parsed
    FIXED : 1 failed, 33 passed — same test

PD-924's assertions still hold; this unit edits neither file.

## Hunk attribution (merge-base `1a476d2cb` to HEAD)

Sibling units on this branch, and their hunks:

| unit | commits | files |
|---|---|---|
| PD-060 | `0ac43ab3a` | bundle gate out of the render |
| PD-206a | `471fdae82` | human verdict files |
| PD-902 | `35c649df7` | closeout wrappers |
| PD-046 | `1372454c0` | recorded style pick |
| PD-061 | `f63ef6b0c` | speech check path |
| PD-064 | `200fa8630` | audio step |
| PD-910 | `08a6cdcd7`, `021f74e24` | unbound sentinel |
| PD-915 | `2d85e9d1b`, `76703417c` | phase-level bundle check |
| PD-062v | `10cedc4ec` | deck resolved where render writes it |
| PD-921 | `cb8028e04`, `13d00426b` | intake provenance refusal |
| PD-088 | `1e697fdda`, `5288f07a9` | typography step |
| PD-075 | `c6d702160`, `9255a8a2a` | typography report at its own step |
| PD-924 | `a97fcc9ca` | divergence fixtures |

This unit is exactly two paths and one commit (`da995d14e`):

- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/phase_verifiers.py`
  (+17 / −1, only inside `_verify_prompt`'s deficiency loop)
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_phase_checks_prompt_reason.py`
  (new)

The other `phase_verifiers.py` hunks on this branch belong to PD-061, PD-064,
PD-075 and PD-921 and were read, not touched.

## Recomputing the digests

    git rev-parse da995d14e
      → da995d14e0a865fd68cbe1b1dc21b6c3fa728725
    git show da995d14e --format='' | shasum -a 256
      → 99733f75ebdd5a0e03d1f82e1bc08a2884d087a028130c80d6243353e118d4ac
    git show da995d14e:23-ai-workforce-blueprint/templates/role-library/presentations/scripts/phase_verifiers.py | shasum -a 256
      → 81a1057462c18b6547d24afd354a4a4c29c87d38ffc356373c15053194f78124
    git show da995d14e:23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_phase_checks_prompt_reason.py | shasum -a 256
      → bbbdff3dd70e2c147251ed92807b437b2875ea0113069e117fc74fad5cc1feb7

## Remote

    git push origin HEAD:refs/heads/pd/fl17-phase-checks
      a97fcc9ca..da995d14e  HEAD -> pd/fl17-phase-checks
    git ls-remote --heads origin refs/heads/pd/fl17-phase-checks
      da995d14e0a865fd68cbe1b1dc21b6c3fa728725	refs/heads/pd/fl17-phase-checks

Local `da995d14e` and the remote's 40-char ref match literally.

## Receipt

- Model that built this unit: `deepseek-chain`. This report is BUILDER-side
  proof, not a verdict: the checker is the orchestration-assigned opus-chain
  judge, a different model and not a repairer of this work. No
  self-certification is offered or implied.
- Head: `da995d14e0a865fd68cbe1b1dc21b6c3fa728725` on
  `pd/fl17-phase-checks`, parent `a97fcc9ca640f5131d6c9504a228f19de91c09cf`.
- Lane worktree `git status --porcelain` is empty after the commit; the build
  and all proofs were run in throwaway copies outside the lane checkout.
