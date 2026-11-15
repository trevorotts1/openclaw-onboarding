# PD-105 — build report (deepseek-chain)

Repo: `trevorotts1/openclaw-onboarding` · branch `pd/fl17-phase-checks`
Remote branch head before this unit: `1b24dacaf9138314e4e1350e360907788474e8d4`
Code + tests commit: `bdcd2667ec6721cd99638300846bc0b27722b78e`
This report commit: the one that adds this file.

All scratch work was done in an independent clone at
`/Volumes/mac mini m4/swarm-contract/loop-control/pd-fix/tmp/PD-105/work.y94gGY/repo`
(`work.y94gGY/base` = untouched `1b24dac`). The lane clone
`/Volumes/mac mini m4/swarm-contract/pd-fix/clones/onboarding` was only read and is clean; the
lane worktree `.../pd-fix/worktrees/onboarding/FL17` was not touched and is clean.

## 1. Spec, quoted

`01-BUILD-SPEC.md`, section `### PD-105 — The infographic check requires a real image`
(lines 2955-2978):

> | Lane and repository | FL17 · trevorotts1/openclaw-onboarding |
> | Wave | 3 |
> | Depends on (must be ACCEPTED, that is QC-passed, first) | PD-208 |
> | Acceptance rows the checker must run | A1 |
>
> **Read first — consolidation amendments (binding; they override the carried-over text below
> wherever the two differ):**
>
> (a) The Image Creator role-file sentence is built in PD-094 (lane FL24), not here. (b) From
> PD-215: the builder's status file will carry `render_verified` in place of `qc_passed`; this
> check accepts either key during the change-over. (c) "Who authors the infographic prompt for a
> deck built from existing content": pass 4 read the whole dispatcher and reported contracts for
> the copy, prompt and typography checks only. Confirm by reading the dispatcher's contract table
> and its fan-out phase list (read-only), then state the answer; if nobody authors it, file
> `BLOCKED-FOLLOWUP: infographic prompt has no producer for converter-origin decks`.
>
> **Carried-over unit text (from `PASS4-PROCEDURES.md`, section PD-105; ids, decisions and lanes
> already converted to final):**
>
> - **Build unit PD-105 (Moderate, Sonnet; lane FL17).** In `_verify_infographic_checklist`
>   require the PNG signature (first 8 bytes) before the size test. In the report, state from a
>   full read of the dispatcher who authors the infographic prompt for a `content_general` deck
>   […] **Acceptance:** a 102,400-byte file of letters fails; a real PNG of that size passes.

Ledger row (`loop-control/pd-fix/ledger.json`): `"id": "PD-105"`, `"depends_on": ["PD-208"]`,
`"acceptance_rows": ["A1"]`, `owned_paths` =
`.../presentations/scripts/phase_verifiers.py`, `.../tests/test_pd_phase_checks_*.py`,
`.../tests/test_pd061_verifier_paths.py`, `.../tests/test_pd088_design_phase.py`,
`.../tests/test_fix112_missing_producers.py`.

Dependency PD-208 is on the branch (commit `993f6fb9c`, "PD-208: the PDF steps are checked for a
PDF") and is the branch tip before this unit, so the change is built directly on it.

## 2. What I implemented

1. **PNG signature before the size test**, in `_verify_infographic_checklist`
   (`phase_verifiers.py`):

```python
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
...
        try:
            with open(png, "rb") as fh:
                head = fh.read(len(_PNG_SIGNATURE))
        except OSError as exc:  # noqa: BLE001
            head = None
            reasons.append(f"infographic.png: unreadable ({exc!r})")
        if head is not None and head != _PNG_SIGNATURE:
            reasons.append(f"infographic.png: not a PNG — expected "
                           f"{_PNG_SIGNATURE!r} at offset 0, got {head!r}")
        if png.stat().st_size < floor:
            ...   # unchanged 102_400-byte floor
```

   The signature is appended to `reasons` BEFORE the size reason, and a file that is not a PNG
   fails the phase whether or not it clears the floor. An unreadable file also fails.

2. **`render_verified` accepted in place of `qc_passed`** (amendment b), same function:

```python
        if status.get("qc_passed") is not True and status.get("render_verified") is not True:
            reasons.append("infographic_status.json: qc_passed is not true "
                           "(nor render_verified)")
```

3. **Rule 15 (tests my change makes false).** `tests/test_fix112_missing_producers.py` wrote
   `b"x" * 102_400` as the infographic PNG and expected a pass. Its fixture is now a real PNG
   (signature + filler) at the same 102,400 bytes. Nothing else in that file changed — the
   negative case (letters → fail) and the rest of its coverage are PD-099b's unit.

4. **Not done here, by spec:** the Image Creator role-file sentence (amendment a → PD-094,
   lane FL24). `_verify_binary_artifact` (PD-208) was left untouched — its wording is
   PDF-specific, and PD-105's spec names an inline signature test in this function.

## 3. Files changed (code commit `bdcd2667e`)

```
23-ai-workforce-blueprint/templates/role-library/presentations/scripts/phase_verifiers.py      +27 -8
.../presentations/scripts/tests/test_fix112_missing_producers.py                              +6 -1
.../presentations/scripts/tests/test_pd_phase_checks_png_signature.py                         +147 (new)
```

## 4. Proof — row A1, real output

New test file: `tests/test_pd_phase_checks_png_signature.py`. Every case builds a run dir that
satisfies every OTHER requirement of P8.3-INFOGRAPHIC, so only the PNG bytes (and, for A1d, the
status keys) vary.

```
$ python3 -I -m pytest tests/test_pd_phase_checks_png_signature.py -q
.....                                                                    [100%]
5 passed in 0.19s
```

Rows covered:

- **A1a** a 102,400-byte file of letters → FAIL, reason `infographic.png: not a PNG — …`
- **A1b** a real PNG (signature + filler) of 102,400 bytes → PASS
- **A1c** signature checked BEFORE size: a letters file under the floor reports "not a PNG"
  ahead of "bytes <"
- **A1d** `render_verified: true` with no `qc_passed` → PASS; neither key → FAIL
- **A1e** control: the A1a fixture is EXACTLY at the 102,400-byte floor, so the size test alone
  would pass it — only the signature can fail it

Direct verifier output (same fixtures, no pytest):

```
letters 102400 -> (False, ["infographic.png: not a PNG — expected b'\\x89PNG\\r\\n\\x1a\\n' at offset 0, got b'xxxxxxxx'"])
real png 102400 -> (True, [])
render_verified only -> (True, [])
neither key -> (False, ['infographic_status.json: qc_passed is not true (nor render_verified)'])
```

### Mutation RED then GREEN

Mutation: the three-line signature comparison removed from `_verify_infographic_checklist`, the
size test left in place.

```
RED   (product line removed):
  FAILED tests/test_pd_phase_checks_png_signature.py::test_a1a_102400_bytes_of_letters_fails_not_a_png
  FAILED tests/test_pd_phase_checks_png_signature.py::test_a1c_signature_is_checked_before_the_size_test
  2 failed, 3 passed in 0.14s

GREEN (product line restored):
  5 passed in 0.10s
```

### Wider suite, base vs head, with counts

Scope: every test file under `presentations/scripts/tests/` that imports `phase_verifiers` or
`pv.verify` — 57 files at base, 58 at head (mine is the 58th). Each file run separately with a
120 s bound, Python 3.14, `-p no:randomly`.

| tree | files | passed | failed | skipped |
|---|---|---|---|---|
| base `1b24dac` | 57 | 780 | 18 | 5 |
| head `bdcd2667e` | 58 | 785 | 18 | 5 |

Delta head−base = **+5 passed, 0 failed, 0 skipped** — exactly the new test file. Every one of the
18 failures exists identically at base (same file, same count) and is not from this unit; they are
pre-existing red on the lane branch (e.g. `test_fix17_verifier_import_failclosed` 5,
`test_upsell_verifiers` 3, `test_f16_agent_phase_wait_race` 2, `test_presentation_job` 1,
`test_fix112_missing_producers` 1 — the last being the missing flat
`presentations/infographic-checklist.md` role file, missing at base too).

Two files exceed the per-file bound at BOTH trees and behave identically:

```
test_fanout_prompt_phase.py   head: 4 failed in 270.39s   base: 4 failed in 266.39s  (same 4 tests)
test_pres002_ready_gate.py    head: "FF." then hung       base: "FF." then hung
```

Whole-directory aggregate runs were attempted first and abandoned after 20+ minutes because these
same two files dominate the wall clock; the per-file table above is the complete, reproducible
census.

Documentation sync (the repo's own gate):

```
$ python3 -I scripts/ci/phase_doc_sync.py --check
phase_doc_sync: manifest universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json -> manifest_version 75, 56 phases
PHASE_DOC_SYNC_PASS: every phase table and version marker matches manifest_version 75 (56 phases).
```

## 5. The producer question (amendment c) — answered, and filed

Question: who authors the infographic prompt for a `content_general` (converter-origin) deck?

Read, read-only, at head before this unit's commit:

- `presentation_job/dispatcher.py` — 11,058 lines. **`ARTIFACT_CONTRACTS` has 11 entries and none
  is P8.3-INFOGRAPHIC; the strings "infographic" and "P8.3" do not occur in the file at all.**
- `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` — 56 phases. P8.3-INFOGRAPHIC
  lists `working/prompts/infographic-prompt.txt` in `consumes`; **zero phases list it in
  `produces_artifact`.**
- Fan-out phase list: P4-COPY (by section), P4-PROMPT (by slide, width 12), P-PROMPT-QC (by slide),
  P-STYLE-SPEC (by slide, 3), P-IMAGE-QC (by slide), P9-SPEECH (by slide). P4-PROMPT produces only
  `working/prompts/slide-*.txt`; `fanout._slides_for_units` returns slides only, so no extra unit
  is invented.
- `CHANGELOG.md` 4244-4255: the prompt was REMOVED from `P4-PROMPT.produces_artifact` precisely
  because no unit could ever write it. The author is named as role `slide-image-creator`
  (`build_infographic.py`'s failure text, `sops/slide-image-creator-sops.md` step 5) but nothing
  schedules that role for a converter-origin deck.

**Answer: nobody authors it.** `evidence/PD-105/BLOCKED-FOLLOWUP.md` carries the exact line
`BLOCKED-FOLLOWUP: infographic prompt has no producer for converter-origin decks` plus this
evidence.

## 6. Discrepancies found while proving the branch

1. **Stale bare mirror.** `_repos/openclaw-onboarding.git` reports `pd/fl17-phase-checks` at
   `b7d16fe6ba6709d65260086339ae97b6f095f1c1`; GitHub (the real `origin`) reports
   `1b24dacaf9138314e4e1350e360907788474e8d4`. The branch is present in both, so the create-from-
   dependency path was not needed; I built on the GitHub head, which is the lane's pushed head and
   carries PD-208.
2. **Lane clone `main` behind remote.** `clones/onboarding` is on `main` at
   `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`, clean; remote `main` is `ebf5c769`. Read-only
   observation, nothing changed.
3. **Lane worktree behind.** `worktrees/onboarding/FL17` is clean, on `pd/fl17-phase-checks` at
   `04cf381a226cc148c324f0dcb6570bba991cf122` (PD-207's report commit) — three commits behind the
   GitHub head. Not touched.

## 7. File overlap with a sibling unit

`tests/test_fix112_missing_producers.py` belongs to PD-105's `owned_paths` but is ALSO named in
PD-099b's unit text (item 2: "use a real PNG header in the fixture and add a negative case").
I changed only the fixture bytes (rule 15 — my change makes its `b"x" * 102_400` pass assertion
false). PD-099b, which waits on PD-105, still owns the added negative case and the rest of that
file. No other file overlaps a sibling unit: `phase_verifiers.py` is the lane's, and
`test_pd_phase_checks_png_signature.py` is new.

## 8. Push

```
before: 1b24dacaf9138314e4e1350e360907788474e8d4  refs/heads/pd/fl17-phase-checks
push:   1b24dacaf..bdcd2667e  pd/fl17-phase-checks -> pd/fl17-phase-checks   (fast-forward)
remote: bdcd2667ec6721cd99638300846bc0b27722b78e
local:  bdcd2667ec6721cd99638300846bc0b27722b78e   EQUAL (40/40 chars)
```

No rebase, no force-push.
