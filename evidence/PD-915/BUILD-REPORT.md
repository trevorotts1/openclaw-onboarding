# PD-915 — BUILD REPORT

- Unit: PD-915 (added unit, not in the 164 lock), lane FL17
- Branch: `pd/fl17-phase-checks`
- Fix commit: `2d85e9d1bda5c9cb1202412af5e87033da0d6d6d`
- Pushed: **yes** — `git ls-remote origin refs/heads/pd/fl17-phase-checks`
  returned `2d85e9d1bda5c9cb1202412af5e87033da0d6d6d` after the push.

## Live head recorded BEFORE editing

`git log --oneline -8`:

```
021f74e24 PD-910: build report
08a6cdcd7 PD-910: the unbound sentinel is not a placeholder and a note is not a failure
200fa8630 PD-064: the audio step is checked for the audio
f63ef6b0c PD-061: the speech check reads the path the manifest declares
fea4d704e Merge remote-tracking branch 'origin/pd/fl15-renderer' into pd/fl17-phase-checks--qc-merge
0ac43ab3a PD-060: the bundle check comes out of the render
35c649df7 PD-902: closeout wrappers read the human-review verdict files
29108bfac Merge remote-tracking branch 'origin/pd/fl17-phase-checks' into pd/fl15-renderer
```

## Files changed

One file, one test:

`23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_slice3_gates.py`
(+17 / −9)

- `test_phase_level_report_only_keeps_legacy_result` — retargeted to the gate
  that now owns the ten-deliverable check. No test deleted, skipped, or
  weakened. Every other test in the file is untouched.

## Why

`tests/test_slice3_gates.py` is owned by no unit. PD-064 (`200fa8630`) moved
the ten-deliverable bundle check off `P9-DELIVER` (now the audio step,
`_verify_delivery_scoped(("audio_mp3",))`) onto `P-BUNDLE-GATE`
(`_verify_bundle_gate`). The old assertion still called `P9-DELIVER`, so the
fabricated deck PDF was never read and the step returned PASS. That is a real
regression in the suite even though every PD-064 row passes.

## Old assertion vs new assertion, side by side

```python
# OLD at head (falsified by 200fa8630)
    (rd / "working" / "delivery" / "demo-FINAL.pdf").write_bytes(b"0" * 60_000)
    ok, reasons = pv.verify("P9-DELIVER", rd)
    assert not ok
    assert any("not a valid" in r for r in reasons)

# NEW
    dl = rd / "working" / "delivery"
    dls = rd / "working" / "deliverables"
    for name in ("demo-FINAL.pptx", "demo-FINAL.pdf", "infographic.png"):
        (dl / name).rename(dls / name)          # PD-064 path move
    (dls / "demo-FINAL.pdf").write_bytes(b"0" * 60_000)
    ok, reasons = pv.verify("P-BUNDLE-GATE", rd)
    assert not ok
    assert any("not a valid" in r for r in reasons)
```

The decoy relocation is part of the retarget, not tidying: PD-064 also moved
the deck and infographic paths the gate reads from `working/delivery/` to
`working/deliverables/`. Without it `P-BUNDLE-GATE` would fail on absence,
which would be a weaker assertion than the original. The assertion still
requires the gate to READ the fabricated file and name it (`not a valid`), so
a report-only run keeps its legacy result instead of silently passing or
producing nothing.

## Exact commands and output

All runs: `TMPDIR=<LOOP_ROOT>/tmp`,
`PYTHONDONTWRITEBYTECODE=1`, from
`.../FL17/23-ai-workforce-blueprint/templates/role-library/presentations/scripts`.

1. **HEAD + ORIGINAL test** — reproduces the regression:

```
$ python3 -m pytest tests/test_slice3_gates.py::test_phase_level_report_only_keeps_legacy_result -q -p no:cacheprovider

    ok, reasons = pv.verify("P9-DELIVER", rd)
>   assert not ok
E   assert not True

tests/test_slice3_gates.py:483: AssertionError
1 failed in 1.81s
```

Reason: `P9-DELIVER` is scoped to `audio_mp3`; the deck decoy is never read.
Raw log: `evidence/PD-915/head-original.log`.

2. **HEAD + RETARGETED test** — green:

```
.                                                                        [100%]
1 passed in 1.54s
```

Raw log: `evidence/PD-915/head-retargeted-target.log`.

3. **HEAD full file** — green:

```
...............                                                          [100%]
15 passed in 4.47s
```

Raw log: `evidence/PD-915/head-retargeted-fullfile.log`.

4. **BASE `f63ef6b0c` + ORIGINAL test** — control, passes (the test was valid
   before the behaviour change):

```
.                                                                        [100%]
1 passed in 1.34s
```

Raw log: `evidence/PD-915/base-original.log`. Base tree extracted with
`git archive f63ef6b0c -- <scripts dir> | tar -x -C <throwaway base dir>`.

5. **BASE `f63ef6b0c` + RETARGETED test** — fails on the assertion that the
   gate reads the decoy:

```
>           assert any("not a valid" in r for r in reasons)
E           assert False

tests/test_slice3_gates.py:492: AssertionError
1 failed in 1.52s
```

At base, `P-BUNDLE-GATE` only checks presence plus the checkpoint record and
returns:

```
['working/checkpoints/bundle_gate.json: missing or not a JSON object — the '
 'bundle gate has not recorded its verdict']
```

i.e. no magic-byte check at that gate yet. This is what proves the retarget
follows the head behaviour change rather than papering over a break. Raw log:
`evidence/PD-915/base-retargeted.log`.

## Other units' hunks not disturbed

The commit contains exactly one file (`git show --stat` = 1 file changed). None
of these commits touch `tests/test_slice3_gates.py` — `git show --name-only
--format= <sha> | grep -c test_slice3_gates.py` returns `0` for each:

| Unit | Commit | Files |
|---|---|---|
| PD-064 | `200fa8630` | `phase_verifiers.py`, `tests/test_pd_phase_checks_audio.py` |
| PD-061 | `f63ef6b0c` | `phase_verifiers.py`, `tests/test_pd061_verifier_paths.py` |
| PD-206a | `471fdae82` | `phase_verifiers.py`, `tests/test_pd_phase_checks_human_review.py` |
| PD-910 (code) | `08a6cdcd7` | `phase_verifiers.py`, `tests/test_pres012_strict_pu_verifiers.py` |
| PD-910 (report) | `021f74e24` | `evidence/PD-910/BUILD-REPORT.md` |

No `phase_verifiers.py` line was touched by PD-915.

## Scope

No merge, no push to main, no rebase, no force-push, no client box, no live
system. Work stayed in the FL17 worktree and the pd-fix room; temp files under
`<LOOP_ROOT>/tmp`, scratch under
`<LOOP_ROOT>/tmp/PD-915`.
