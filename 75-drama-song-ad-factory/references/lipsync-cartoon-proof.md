# Cartoon lip-sync recalibration — proof on the October 13 trial files (AGN W4-proof-U4)

I am a unit agent, not the conductor: I did not run the tick, act as conductor, or edit
`LEDGER.md`, `TODO.md` or any `SWARM-PLAN` file. This unit owns one file, this receipt.

Unit **AGN-W4-proof-U4** · plan row `W4-proof-U4` · proves **SPEC acceptance 4** line by line.
Receipt only: no code change, no version bump, no CHANGELOG edit, no provider call.

| | |
|---|---|
| Date | 2026-10-15 (operator Mac Mini; times local) |
| Repo / branch | `trevorotts1/openclaw-onboarding`, worktree `/Users/<operator>/agnes-wt/W4-proof-U4`, branch `unit/AGN-W4-proof-U4`, base `origin/main` = `1e1c12dcc` |
| Gate under test | the two open **O-method lipsync** candidate branches (see §3), because the recalibration is not on `main` yet |
| Spend | **$0.** No Agnes call, no KIE call, no image or video job. The only network was the Google face-model download (sha-pinned) and the pip wheels for mediapipe/OpenCV/numpy |
| Trial files | `trial-oct13/test-c-lipsync-same-character/` and `trial-oct13/test-b-cartoon-lipsync/` — **read only**, nothing written into them (proof in §7) |
| Lane (drivers, media, raw output) | `run/lanes/W4-proof-U4-lane/` — `out/sync_probe.json`, `out/picture_probe.json`, `media/`, `receipts/` |

**Result: all four SPEC acceptance-4 lines hold.** Test C's real line PASSES on the cartoon
look, each of three mismatched lines FAILS, test B still FAILS, and the crop ladder turns
test C's 0-face `cartoon.png` into an accepted crop — with no paid regeneration and no
remake. The two deviations that could have changed the numbers are named in §6.

---

## 1. What was re-run

SPEC acceptance 4 asks for the cartoon rule re-run on the files the trial already paid for:

> on the existing trial files, the cartoon rule passes test C's clip with its real audio,
> fails it with each mismatched line, still fails test B; the crop ladder turns test C's
> 0-face `cartoon.png` into an accepted crop.

Two factory gates, both free, both re-run on the original media:

* the **sync gate** (`lip_gate.measure_file` + `lip_gate.judge(look=…)`) on test C's
  `clip.mp4` against its real line and against three mismatched lines, and on test B's
  `clip.mp4` against its real line;
* the **picture gate** (`picture_gate.gate_picture`, which now carries the free face-crop
  ladder) on test C's `cartoon.png`.

## 2. The environment had to be rebuilt (the trial scaffolding is gone)

The 2026-10-13 trial left only the deliverable media and the `RESULTS.md` files. Everything
the gate needs was deleted with the rest of the scaffolding: `venv/`,
`face_landmarker.task`, `ctl1-3.mp3`, `bctl1-2.mp3`, `run_sync_gate.py`,
`run_picture_gate.py`, `.lipgate/`. Rebuilt in the lane, never in the trial folder:

```
$ python3 -m venv <lane>/venv
$ <lane>/venv/bin/pip install 'mediapipe>=0.10.14' opencv-python-headless numpy
$ <lane>/venv/bin/python -c "import mediapipe, cv2, numpy, sys; print(mediapipe.__version__, cv2.__version__, numpy.__version__, sys.version.split()[0])"
1.1.1 5.0.0 2.5.4 3.14.7
```

The face model was fetched with the skill's own installer (never a bare URL) and verified
against the sha256 pinned in `install_face_model.py`, then handed to both gates through
`LIPSYNC_FACE_MODEL` so nothing is written into the repo or the trial folder:

```
$ <python> -c "import sys; sys.path.insert(0,'<U2 worktree>/…/lip_gate'); import install_face_model as M; print(M.install('<lane>/assets/face_landmarker.task'), M.is_good(...))"
<lane>/assets/face_landmarker.task True
sha256 64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff   (MODEL_SHA256, match)
```

**Control lines had to be regenerated.** Test C's three mismatched lines were deleted and
their sentences were never written down (test C `RESULTS.md` §2 records only the voice,
the rate and the durations). Same macOS voice, same rate, new sentences, lengths matched to
the recorded durations as closely as the voice allows:

| file | `say` rate | duration now | duration on 2026-10-13 (RESULTS.md §2) | sha256 (first 16) |
|---|---|---|---|---|
| `ctl1.mp3` | `-r 165` | 7.477 s | 6.42 s | `6b29df1e0c8f5129` |
| `ctl2.mp3` | `-r 165` | 5.382 s | 5.51 s | `e7bad9a2d3ee1302` |
| `ctl3.mp3` | `-r 165` | 7.301 s | 7.24 s | `fd81a53ff849742f` |
| `bctl1.mp3` | `-r 105` | 4.235 s | not recorded | `e6fd123acef98ba8` |
| `bctl2.mp3` | `-r 105` | 4.181 s | not recorded | `78b3ae825422f2ec` |

Sentences: ctl1 "The morning train was late again and the platform felt colder than usual,
so she stood under the broken clock with her hands in her coat pockets." · ctl2 "She kept
the old photograph in the drawer beneath the silver spoon and the little blue box nobody
ever opened." · ctl3 "Nobody expected the garden to bloom so early after such a long winter,
least of all the neighbour who had planted nothing at all." · bctl1 "Nothing about that
quiet room had changed since the summer before." · bctl2 "He folded the letter twice and
set it down beside the cooling cup."

The trial's own real lines were **not** regenerated — the originals
(`test-c-…/line.mp3` 6.907 s, `test-b-…/line.mp3` 3.563 s) are still in the folders.

## 3. The gate under test is on two open candidate branches, not on `main`

At the base of this branch (`1e1c12dcc`) the recalibration is **not** present:
`git show 1e1c12dcc:…/lip_gate/sync_check.py | grep -c CARTOON_CORR_FLOOR` → `0`. The
look-aware floor is unit **AGN-W1-method-lipsync-U1** (`8e7e55c88`), the crop ladder and the
smile hook are unit **AGN-W1-method-lipsync-U2** (`f67112ab2`), both still open. Wave 4 is
pinned to candidate heads for exactly this reason (BUILD-PLAN, *Wave release and hygiene*).
So the drivers import the modules from those two worktrees, and every imported file was
hash-checked against the committed blob of its own SHA before and after the run:

```
U1 @ 8e7e55c88  lip_gate.py 11041db0…  sync_check.py 5f144112…  mouth_landmarks.py 11661f06…  picture_measure.py 8503e188…  __init__.py b7c7a065…   all MATCH
U2 @ f67112ab2  picture_gate.py 3d7eb121…  picture_measure.py 8503e188…  __init__.py b7c7a065…   all MATCH
U1 / U2 worktrees: `git status --porcelain` → 0 dirty lines each
```

Both `CARTOON_CORR_FLOOR = 0.35` and `CROP_LADDER_WIDTHS = (0.70, 0.60, 0.80)` came from
those files, not from a copy. When the batch merges `O-method`, the identical commands
below run unchanged against `main` and produce the same verdicts.

## 4. Picture gate — the crop ladder on test C's `cartoon.png` (SPEC 4, clause 4)

Input is a byte-identical copy of the trial picture taken into the lane, because the ladder
writes its rungs and the gate writes its receipts **next to the picture** — running it in
place would have written into the trial folder:

```
source  trial-oct13/test-c-lipsync-same-character/cartoon.png   2c14d7283ae6abfea7ad4228980282f7300a525821bf06dd803ecec1d7937c23
gated   <lane>/media/test-c-cartoon.png                         2c14d7283ae6abfea7ad4228980282f7300a525821bf06dd803ecec1d7937c23   (identical)

$ LIPSYNC_FACE_MODEL=<lane>/assets/face_landmarker.task <lane>/venv/bin/python picture_probe.py
```

`regenerate=None` on purpose: nothing here may buy a regeneration.

| rung | picture | width | verdict | face_count | face height | jaw_open | smile | reasons | flags |
|---|---|---|---|---|---|---|---|---|---|
| input | `test-c-cartoon.png` | 1472 px (full) | **FAIL** | 0 | — | — | — | `FACE_COUNT` | — |
| 1 | `test-c-cartoon-ladder1.png` | 1030 px, 9:16, top edge in the upper third | **ACCEPT_WITH_FLAG** | 1 | 36.6 % | 0.054 | 0.0 | — | `TEETH` (lip gap 5.84 % of face height, over the 1.0 flag line) |

Final gate result: `verdict ACCEPT_WITH_FLAG`, `accepted: true`, final image
`test-c-cartoon-ladder1.png` sha256 `875be4d49b9a424fe9c06156e96e116e84cf87499c76840153770f0574f202a4`.
Ladder rungs 2 and 3 were never needed, and no paid regeneration was bought (`MAX_PAID_REGENS = 2`,
untouched). The 1030 px rung is the same crop the 2026-10-13 trial picked by hand at 1040 px
(test C `RESULTS.md` §1) — the ladder finds it on its own, free.

**Crop accepted.**

## 5. Sync gate — the cartoon rule on test C and test B (SPEC 4, clauses 1-3)

```
$ LIPSYNC_FACE_MODEL=<lane>/assets/face_landmarker.task <lane>/venv/bin/python sync_probe.py
```

Every row is `lip_gate.measure_file(clip, audio=…, others=[…])` then
`lip_gate.judge(m, sung=False, look=…)`; floors are `CARTOON_CORR_FLOOR = 0.35` (cartoon
look) and `CORR_FLOOR = 0.40` (every other look). All clips 30 fps, face found in 100 % of
frames, `pct` = share of chance rolls that beat the real correlation (fails over 0.20).

### Test C, the real line — the clip the trial was made from

| field | value |
|---|---|
| clip / audio | `test-c-…/clip.mp4` / `line.mp3` (6.907 s), controls `ctl1 ctl2 ctl3` |
| frames (video / used) | 216 / 209 · face_found 1.0 · mouth_pos 0.704 · mouth_range 0.0797 |
| corr / control_corr / margin | **0.3911** / 0.2179 / **+0.1732** |
| lag / offset / chance `pct` | 0 frames / 0.000 s / **0.0** (no roll beat it) |

| look | verdict | grade | reasons |
|---|---|---|---|
| `2d-hand-painted` (cartoon) | **PASS** | SYNCED | — |
| `lifelike-3d` | FAIL | NOT_SYNCED | `LIP_CORR` |
| no look (plain 0.40 floor) | FAIL | NOT_SYNCED | `LIP_CORR` |

The corr of **0.3911 is bit-identical to the 2026-10-13 measurement** in test C's
`RESULTS.md` §4, which is the reproducibility check: same clip, same real audio, same
landmark measure, re-derived from scratch. Only the control lines changed, so
`control_corr` moved 0.2342 → 0.2179 and the margin moved +0.157 → +0.173. **PASS on the
cartoon look, and still FAIL on a non-cartoon look** — the floor moved for cartoons only,
exactly as unit U1 designed it.

### Test C, the three mismatched lines — each must still FAIL

| audio | corr | control_corr | margin | lag | chance `pct` | verdict (cartoon look) | reasons |
|---|---|---|---|---|---|---|---|
| `ctl1.mp3` (7.477 s) | 0.1991 | 0.4824 | −0.2833 | +10 | 0.419 | **FAIL** | `LIP_CORR`, `LIP_CHANCE`, `LIP_MARGIN` |
| `ctl2.mp3` (5.382 s) | 0.2126 | 0.3505 | −0.1379 | −7 | 0.422 | **FAIL** | `LIP_CORR`, `LIP_CHANCE`, `LIP_MARGIN` |
| `ctl3.mp3` (7.301 s) | 0.0991 | 0.4824 | −0.3832 | −10 | 0.661 | **FAIL** | `LIP_CORR`, `LIP_CHANCE`, `LIP_MARGIN` |

All three fail all three tests on the cartoon look, and the best wrong-line correlation
(0.2126) sits 0.18 under the 0.35 cartoon floor while the real line sits 0.041 over it.
The recalibration did not buy a pass for wrong audio.

### Test B — the closed-mouth cartoon, still FAIL

| field | value |
|---|---|
| clip / audio | `test-b-…/clip.mp4` / `line.mp3` (3.563 s), controls `bctl1 bctl2` |
| frames (video / used) | 112 / 108 · face_found 1.0 · mouth_pos 0.753 · mouth_range 0.0424 |
| corr / control_corr / margin | 0.3124 / 0.3443 / −0.0319 |
| lag / offset / chance `pct` | 0 frames / 0.000 s / 0.308 |

| look | verdict | grade | reasons |
|---|---|---|---|
| `2d-hand-painted` (cartoon) | **FAIL** | NOT_SYNCED | `LIP_CORR`, `LIP_CHANCE`, `LIP_MARGIN` |
| `lifelike-3d` | **FAIL** | NOT_SYNCED | `LIP_CORR`, `LIP_CHANCE`, `LIP_MARGIN` |

Corr 0.3124 is the number test B's `RESULTS.md` §5 recorded, again bit-identical. Test B's
mouth barely travels (`mouth_range` 0.0424 against test C's 0.0797), so it stays under the
cartoon floor and fails the chance and margin tests too. **The cartoon floor does not rescue
a closed-mouth cartoon.** This is the pair that makes the recalibration defensible: the gate
still separates test C from test B.

## 6. SPEC acceptance 4, line by line

| SPEC acceptance-4 line | Evidence here |
|---|---|
| the cartoon rule passes test C's clip with its real audio | §5 — corr 0.3911 ≥ 0.35, margin +0.1732, chance 0.0 → **PASS / SYNCED** on `2d-hand-painted` |
| fails it with each mismatched line | §5 — ctl1 / ctl2 / ctl3 all **FAIL** on all three tests |
| still fails test B | §5 — corr 0.3124, margin −0.0319, chance 0.308 → **FAIL** on both looks |
| the crop ladder turns test C's 0-face `cartoon.png` into an accepted crop | §4 — 0 faces on the full frame → rung 1 **ACCEPT_WITH_FLAG**, 1 face, 36.6 %, no paid regeneration |
| "no spend" (unit line) | $0, no Agnes call, no KIE call; only the sha-pinned face model and pip wheels touched the network |

**Area regression on this PR head stays green** (main's own lip_sync, the recalibration not
being merged yet):

```
$ cd <worktree> && python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/lip_sync
103 passed in 3.28s
```

Every other area regression command at the top of BUILD-PLAN.md was run on this head and is
green: intake card 114, dispatch+lock 45, calculator 3, assembler 163, song 226, length 50,
story/board 15, clips 28, lip-sync 103, checklist 66, factory 26, kit 22 (OK), skill 64
self-test 28/28, skill 63 self-test "ALL FIXTURES BEHAVED AS EXPECTED".

Two commands cannot be run as written, and neither is this unit's doing:

* `python3 75-drama-song-ad-factory/tests/test_cli_smoke.py` — **that file does not exist on
  this base** (`git ls-tree -r --name-only 1e1c12dcc | grep test_cli_smoke` → 0 lines). The
  nearest suite is `python3 -m pytest -q 75-drama-song-ad-factory/tests`, which here reports
  `1 failed, 193 passed`: the one failure is `test_model_choice.py::test_no_model_pin_in_skill_docs`,
  failing on **`references/studio-e2e-receipt.md`**, which is on the base and mentions
  `sonnet-chain` (`git show 1e1c12dcc:…/studio-e2e-receipt.md | grep -c sonnet-chain` → 1).
  It is pre-existing, unrelated to lip-sync, and owned elsewhere. This receipt carries no
  model-pin word (`grep -ciE 'fable|opus-chain|sonnet-chain|haiku-chain|ANTHROPIC_DEFAULT_'`
  on it → 0), so it adds no second failure.

## 7. Nothing was written into the trial folders

```
$ find trial-oct13 -type f | wc -l
47        (46 media/document files plus one pre-existing .DS_Store)
$ find trial-oct13 -type d -name .lipgate | wc -l
0
$ find trial-oct13 -type f -newermt '2026-10-15 05:00'
(none)
```

Every write this unit made is inside `run/lanes/W4-proof-U4-lane/`: the venv, the face
model, the five control lines, the copied `cartoon.png`, the two ladder rungs, the
`.lipgate` receipts, the two driver scripts and the raw JSON output.

## 8. What this receipt does NOT prove (named, not hidden)

1. **One clip, one voice, three controls.** As in the 2026-10-13 trial, this is a spot
   check, not a statistical calibration. The floor of 0.35 is justified by a single clip
   with 0.041 of headroom; a second cartoon clip could sit under it.
2. **Control sentences are new.** The originals were deleted before this unit ran (§2), so
   the wrong-line rows re-derive the same conclusion from different sentences. The verdicts
   agree with the 2026-10-13 table; the individual `control_corr` values do not match and
   are not expected to.
3. **The `TEETH` flag stays on the accepted crop.** The crop ladder fixes framing, not
   expression. Under unit U2's `no_smile=True` hook a smiling close-up is refused for
   lip-sync; this cartoon's smile measurement is 0.0, so the flag here is the lip-gap
   flag only, and the picture is accepted as it was on 2026-10-13.
4. **The recalibration is not on `main` yet** (§3). These verdicts are the candidate's;
   the batch merge must land `O-method` for a run on `main` to reproduce them.
5. Not re-tested, as the unit does not ask for it: a sung line (the gate grades a sung
   FAIL as UNDETERMINED), a real-person clip to check the 0.40 floor itself, the
   source-image vision gate (no analyzer in the repo), or any paid lip-sync job.

## 9. Reproduction recipe (self-contained)

```
LANE=/tmp/<you>-W4-proof-U4            # any scratch folder
O=~/openclaw-onboarding
U1=8e7e55c88                            # unit/AGN-W1-method-lipsync-U1
U2=f67112ab2                            # unit/AGN-W1-method-lipsync-U2
T=$HOME/Downloads/Agnes Drama Ad Factory/trial-oct13

python3 -m venv $LANE/venv
$LANE/venv/bin/pip install 'mediapipe>=0.10.14' opencv-python-headless numpy pytest
git -C $O worktree add --detach $LANE/u1 $U1
git -C $O worktree add --detach $LANE/u2 $U2
mkdir -p $LANE/media $LANE/receipts $LANE/out
$LIP=$LANE/u2/75-drama-song-ad-factory/scripts/core/lip_sync/lip_gate
python3 -c "import sys; sys.path.insert(0,'$LANE/u2/.../lip_gate'); import install_face_model as M; M.install('$LANE/assets/face_landmarker.task')"
cp "$T/test-c-lipsync-same-character/cartoon.png" $LANE/media/test-c-cartoon.png
say -r 165 -o $LANE/media/ctl1.aiff "<the ctl1 sentence in §2>"      # then ctl2, ctl3; say -r 105 for bctl1, bctl2
for f in ctl1 ctl2 ctl3 bctl1 bctl2; do ffmpeg -v error -y -i $LANE/media/$f.aiff -ar 44100 -ac 1 $LANE/media/$f.mp3; done
```

Then run the two drivers below, whose full text is what ran in this lane (the lane folder is
removed with the run; the drivers are inlined here so the receipt stays reproducible).

`picture_probe.py`:

```python
import hashlib, json, os, sys
sys.path.insert(0, os.environ["LANE"] + "/u2/75-drama-song-ad-factory/scripts/core/lip_sync/lip_gate")
import picture_gate as PG
LANE = os.environ["LANE"]
copy = os.path.join(LANE, "media", "test-c-cartoon.png")
rec = PG.gate_picture(copy, receipt_dir=os.path.join(LANE, "receipts"))   # regenerate=None
print(json.dumps({"verdict": rec["verdict"], "accepted": rec["verdict"] in PG.ACCEPTED,
                  "final_image": rec["image"], "final_sha256": rec["sha256"],
                  "reasons": rec.get("reasons"), "flags": rec.get("flags"),
                  "attempts": [{"image": a["image"], "verdict": a["verdict"],
                                "face_count": a["numbers"].get("face_count"),
                                "face_h_pct": a["numbers"].get("face_h_pct"),
                                "jaw_open": a["numbers"].get("jaw_open"),
                                "smile": a["numbers"].get("smile"),
                                "reasons": [r[0] for r in a["reasons"]],
                                "flags": [f[0] for f in a["flags"]]}
                               for a in rec.get("attempts", [])]}, indent=2))
```

`sync_probe.py`:

```python
import json, os, sys
sys.path.insert(0, os.environ["LANE"] + "/u1/75-drama-song-ad-factory/scripts/core/lip_sync/lip_gate")
import lip_gate as L, sync_check as SC
LANE, T = os.environ["LANE"], os.environ["T"]
C, B, MEDIA = T + "/test-c-lipsync-same-character", T + "/test-b-cartoon-lipsync", LANE + "/media"
CARTOON, KEEP = "2d-hand-painted", ("fps", "frames_video", "frames_used", "face_found",
    "mouth_pos", "mouth_range", "corr", "control_corr", "margin", "lag_frames", "offset_s",
    "pct", "others_used", "others_dropped", "unmeasurable")

def probe(case, clip, audio, others, looks):
    m = L.measure_file(clip, audio=audio, others=others)
    return {"case": case, "audio": os.path.basename(audio), "controls": [os.path.basename(o) for o in others],
            "measurement": {k: m.get(k) for k in KEEP}, "cartoon_floor": SC.CARTOON_CORR_FLOOR,
            "plain_floor": SC.CORR_FLOOR,
            "judged": [{"look": lk, "verdict": L.judge(dict(m), sung=False, look=lk)["verdict"],
                        "grade": L.judge(dict(m), sung=False, look=lk)["grade"],
                        "reasons": L.judge(dict(m), sung=False, look=lk)["reasons"]}
                       for lk in looks]}

ctls = [MEDIA + "/ctl%d.mp3" % i for i in (1, 2, 3)]
cases = [probe("C real line", C + "/clip.mp4", C + "/line.mp3", ctls, [CARTOON, "lifelike-3d", None])]
for i, ctl in enumerate(ctls, 1):
    cases.append(probe("C wrong line ctl%d" % i, C + "/clip.mp4", ctl,
                       [C + "/line.mp3"] + [c for c in ctls if c != ctl], [CARTOON]))
cases.append(probe("B real line", B + "/clip.mp4", B + "/line.mp3",
                   [MEDIA + "/bctl1.mp3", MEDIA + "/bctl2.mp3"], [CARTOON, "lifelike-3d"]))
print(json.dumps({"cases": cases}, indent=2))
```

Both drivers run with `LIPSYNC_FACE_MODEL=$LANE/assets/face_landmarker.task` and
`PYTHONDONTWRITEBYTECODE=1`.
