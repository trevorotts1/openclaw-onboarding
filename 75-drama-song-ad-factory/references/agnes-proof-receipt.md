# Agnes live proof — operator Mac, Agnes only, no KIE spend (W4-proof-U1)

Receipt for SPEC acceptance 1 and BUILD-PLAN `W4-proof-U1`. One live window on
Trevor's own operator Mac Mini, 2026-10-15 10:13:01Z → 10:41:23Z, using
Trevor's own Agnes key. **No call to `api.kie.ai` was made — zero KIE spend.**

Everything below is a command and its output from that window. The key is never
in this document: it is read only by `agnes_access.key_value()` and printed only
as `key_present: true`.

**Where the run lived** (scratchpad lane, removed with the run; every artifact
named below is quoted here so the receipt stands alone):

```
L = ".../Agnes Drama Ad Factory/run/lanes/W4-proof-U1-lane"
L/run/control/agnes-http.log     every HTTP call, wall-clock stamped
L/run/control/spend.sqlite3      spend_ledger rows (all cost 0)
L/run/control/agnes-quota.sqlite3  quota ledger (DSAF_AGNES_QUOTA_DB)
L/run/control/agnes-progress.json  progress file (SPEC A11)
L/run/work/agnes/                the stills, the clips, the prompt receipts
L/run/conform/                   the conformed 30 fps clips
L/evidence/                      one JSON per step, quoted below
```

## What code was run

`origin/main` does not carry the Agnes modules yet (they are the open
`unit/AGN-W1-agnes-core-*` branches), so the proof ran the product exactly as
the program ships it: a scratch checkout of `origin/main` with each owning
branch's own files applied on top. Nothing was committed from that checkout;
this PR's diff is this one file.

| Source | SHA |
|---|---|
| `origin/main` (base of this PR) | `1e1c12dcc0ad336d24c13986973e885e58d95954` |
| `unit/AGN-W1-agnes-core-U1` (the Agnes door) | `11210bca83c58467ee2fb250152eb47d961e5846` |
| `unit/AGN-W1-agnes-core-U2` (quota) | `fa65da4f8f952f0affbd30f83b753c7ef31a5e70` |
| `unit/AGN-W1-agnes-core-U3` (access / key) | `428043e155fb1172af93dc3b6daf85bd6b466518` |
| `unit/AGN-W1-agnes-core-U4` (plan) | `03ada0129fd36a85240ada2abaf6b49a07e74d75` |
| `unit/AGN-W1-agnes-core-U5` (on-screen text) | `1ffc1b05dd0c270db2c0c48fa9c1189a4d5af415` |
| `unit/AGN-W1-agnes-core-U6` (frame gate + conform) | `0279fe219e2b393d8c65012a78b24d807760c7c5` |
| `unit/AGN-W1-card-questions-U1` (the AGNES question) | `72841f2b93117900ec946d55dd4fb714e84cecc6` |
| `unit/AGN-W1-method-lipsync-U2` (face-crop ladder) | `f67112ab29d6992ed53573dcf99fe25a130a7c1e` |

---

## 1. The AGNES question shows and hides by the remembered answer (SPEC A2)

```
$ python3 proof.py remembered
```

```json
{
  "card_rows": [
    {"remembered": "unknown", "agnes_question_in_card": true},
    {"remembered": "yes",     "agnes_question_in_card": true},
    {"remembered": "no",      "agnes_question_in_card": false}
  ],
  "studio_shows_when": {"agnes_remembered": ["unknown", "yes"],
                        "purpose": [1, 2, 3, 4], "length_s_max": 300},
  "agnes_access_status_stdout": "{\"remembered\": \"no\", \"key_present\": true}",
  "agnes_access_status_stderr_present": false,
  "key_present_via_key_value": true
}
```

Card ids prove the show/hide, not just the count:

```
remembered=unknown -> [... "music", "look", "agnes", "model" ...]
remembered=yes     -> [... "music", "look", "agnes", "model" ...]
remembered=no      -> [... "music", "look", "model", "spend" ...]   (no "agnes")
```

The studio screen carries the same rule as `shows_when`, so the page hides it
too. The status CLI printed `key_present: true` and **nothing else** — no key on
stdout, nothing on stderr.

Before any network call, the whole gate chain was opened and its refusal was
exercised as a control:

```
$ python3 proof.py gate
{"gate_chain": [{"kind": "image", "gate_chain": "OPEN"},
                {"kind": "video", "gate_chain": "OPEN"}],
 "each_gate_open": {"placeholder": ["/prompt", "{{"], "onscreen_text": null,
                    "storyboard": null, "song_pick": null,
                    "script_approval": null, "card": null,
                    "agnes_answer": "yes"},
 "negative_control_agnes_no": "AGNES_NOT_CHOSEN"}
```

The negative control is the same request with `agnes.answer = "no"`: the door
refuses `AGNES_NOT_CHOSEN` and sends nothing.

---

## 2. Three stills at 2K 9:16 (SPEC acceptance 1)

```
$ python3 proof.py image --logical-key still-a --prompt "$(cat still-closeup.txt)" \
      --size 2K --ratio 9:16 --out evidence/image-still-a.json
```

| still | envelope | size | ratio | ffprobe | bytes | sha256 |
|---|---|---|---|---|---|---|
| `still-a.png` (cartoon close-up) | `ok` / `AGNES_IMAGE_OK` | `2K` | `9:16` | **1472x2624** png | 3316373 | `ab19f52e0f3aa9a5a4eb86bc9da32aa59c09e212d3bf5ffe84b38057def0630e` |
| `still-b.png` (wide, no face) | `ok` / `AGNES_IMAGE_OK` | `2K` | `9:16` | **1472x2624** png | 3506103 | `23e774a9e5b7f42679f69ceb688c5570632d8a8bd3b3543b3120965a70412459` |
| `still-c.png` (three-quarter) | `ok` / `AGNES_IMAGE_OK` | `2K` | `9:16` | **1472x2624** png | 3798487 | `a5d3cd56e4ed7e2f2ef758f4a95c5f78a9d0723efff188d5039688d5a93e1f98` |
| `still-d.png` (hands close-up, 0 faces) | `ok` / `AGNES_IMAGE_OK` | `2K` | `9:16` | **1472x2624** png | 3602182 | `94244cae9998dd7432578bd9cde7a171aabd0eaf90a7053ea5fffcd55d3c008e` |

1472x2624 is RESEARCH's measured 2K 9:16 pixel size. Each still took 12-18 s
(`elapsed_s` in the evidence JSON), each carried `actual_cost: 0`, and each wrote
its own `<key>.a1.prompt-receipt.json`.

`still-d` is a 4th still, generated because a face-free close-up is the only
input on which the face-crop ladder can run (section 9): the ladder is keyed off
`face_count == 0`. Six image generations in total, inside the ≤ 15 budget.

---

## 3. Two 10-second `keyframe` clips, two in flight (SPEC A4.4)

Launched as two separate processes one second apart:

```
$ date -u +%Y-%m-%dT%H:%M:%SZ > logs/videos-started-utc.txt   -> 2026-10-15T10:22:49Z
$ python3 proof.py video --logical-key seg-1 --prompt-file seg1.txt \
      --first-frame <still-a.png CDN url> --out evidence/video-seg-1.json &
$ python3 proof.py video --logical-key seg-2 --prompt-file seg2.txt \
      --first-frame <still-a.png CDN url> --out evidence/video-seg-2.json &
```

**Both in flight at once** — the two slot files the door uses for the 2-job
cap, both held, both holder processes alive:

```
$ cat run/control/agnes-video-slot-0.json ; cat run/control/agnes-video-slot-1.json
{"pid": 18215, "at": 1792059769}
{"pid": 18212, "at": 1792059769}
$ ps -p 18212,18215   -> both alive
```

The HTTP log shows the two creates landing within 3 ms of each other, before
either had finished:

```
seg-1 2026-10-15T10:22:49.626Z POST https://apihub.agnes-ai.com/v1/videos -> 200
seg-2 2026-10-15T10:22:49.623Z POST https://apihub.agnes-ai.com/v1/videos -> 200
```

**What was actually sent** (captured with an injected transport that answers 401
locally — zero sockets, zero spend):

```
$ python3 capture_body.py
video POST https://apihub.agnes-ai.com/v1/videos
{"model": "agnes-video-2.5-flash", "prompt": "<5323 chars ...>",
 "mode": "keyframe", "seconds": "10", "size": "720P",
 "aspect_ratio": "9:16", "first_frame": "<url of still-a.png>"}
image POST https://apihub.agnes-ai.com/v1/images/generations
{"model": "agnes-image-2.5-flash", "prompt": "<18 chars ...>",
 "size": "2K", "ratio": "9:16"}
video_body_keys = [aspect_ratio, first_frame, mode, model, prompt, seconds, size]
video_has_no_n = true   image_has_no_n = true   video_mode = keyframe
video_seconds = "10"    video_first_frame_set = true
```

Both capture runs returned `rejected / AGNES_KEY_REFUSED` with
`"submitted": false` — the fake 401 proves nothing was sent.

Both clips came back `ok`:

```
seg-1  outcome=ok reason=AGNES_VIDEO_OK  prompt_chars=5323 prompt_verdict=PASS
       seconds=10 aspect=9:16 actual_cost=0 retries=0 queue_full_wait_s=0
seg-2  outcome=ok reason=AGNES_VIDEO_OK  prompt_chars=5320 prompt_verdict=PASS
       seconds=10 aspect=9:16 actual_cost=0 retries=0 queue_full_wait_s=0
```

---

## 4. Generation time per clip (SPEC acceptance 1)

From `evidence/video-seg-*.json`:

| clip | task id | submitted (UTC) | completed (UTC) | generation time | polls | file |
|---|---|---|---|---|---|---|
| `seg-1` | `task_nGD2ZLDGLRqT3tu2SdzJazzKIlIGiwTN` | 10:22:49.594 | 10:37:12.665 | **863.1 s (14.4 min)** | 57 | `seg-1.mp4`, 1681897 B, sha `7d04fc571b0694e8db490817db5d3d8325497fd03ab9c25623085773ed071243` |
| `seg-2` | `task_oZChjf6DoZXAVb6aeqXSKwjtkJaW8E71` | 10:22:49.594 | 10:36:44.046 | **834.5 s (13.9 min)** | 55 | `seg-2.mp4`, 1308748 B, sha `5894f64a4120194e4595edf6f3ab5b6f78cb5a107ae3a7dacc6a44badc71f5df` |

RESEARCH's trial A measured 11-13 min for a 10 s clip; this window measured
13.9 and 14.4 min.

---

## 5. Measured 704x1280, 24 fps, audio present (SPEC A8, trial A)

```
$ ffprobe -v error -print_format json -show_streams run/work/agnes/seg-1.mp4
```

```
seg-1: VIDEO 704x1280 fps=24/1 frames=243 codec=h264   duration 10.125000
       STREAM audio codec=aac
seg-2: VIDEO 704x1280 fps=24/1 frames=243 codec=h264   duration 10.125000
       STREAM audio codec=aac
```

Every field matches the RESEARCH measurement for Agnes 2.5 Flash output
(704x1280, 24 fps, 243 frames, 10.125 s, AAC present and not silent).

---

## 6. Conform: 24 fps + audio → 1080x1920 30 fps, no audio (SPEC A8)

```
$ python3 proof.py conform
```

The argv is `fps_conform.agnes_conform_argv(src, dst, 1080, 1920)` verbatim:

```
nice -n 10 ffmpeg -threads 4 -y -i run/work/agnes/seg-1.mp4 -an
  -vf minterpolate=fps=30:mi_mode=mci,scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=w=1080:h=1920:x=0:y=0,setsar=1
  -c:v libx264 -pix_fmt yuv420p run/conform/seg-1-30fps.mp4
```

- `-an` strips the clip's own AAC track (the song is the only audio in the master);
- `minterpolate=fps=30:mi_mode=mci` is the 24 → 30 motion interpolation, not a
  plain frame-doubling `fps` filter;
- `lanczos` + `crop` is the cover-scale, so the clip fills the frame with no
  blur fill and no letterbox pad;
- no blur filter and no pad filter anywhere in the argv;
- `NATIVE_FPS["agnes"] == 24.0`.

Result (returncode 0, 14.7 s and 15.3 s of ffmpeg):

```
src: 704x1280, 24/1 fps, 243 frames, audio aac, duration 10.125000
dst: 1080x1920, 30/1 fps, 302 frames, NO audio stream, duration 10.066016
     seg-1-30fps.mp4 4044282 B   seg-2-30fps.mp4 3259461 B
```

---

## 7. Poll interval ≥ 15 s in the log (SPEC A4.4)

Every HTTP call was timestamped with wall clock and epoch in
`run/control/agnes-http.log`, then summarised:

```
$ python3 - <<'PY'  (parse run/control/agnes-http.log)
status counts: {200: 126, 401: 1, 502: 8}
method counts: {POST: 8, DOWNLOAD: 8, GET-RETRY-FOR-DOWNLOAD: 7, GET: 112}

--- key seg-1
  requests=60 POST=1 GET=57 DOWNLOAD=1
  poll gaps: n=56 min=15.315 max=15.489 under15=0
--- key seg-2
  requests=58 POST=1 GET=55 DOWNLOAD=1
  poll gaps: n=54 min=15.317 max=16.119 under15=0
```

**Minimum gap between two consecutive polls of the same job: 15.315 s (seg-1)
and 15.317 s (seg-2). Zero gaps under 15 s out of 110 measured gaps.** Five
consecutive raw lines for `seg-1`, with the epoch deltas that give the gaps:

```
seg-1 2026-10-15T10:32:49.577Z epoch=1792060369.209 GET .../agnesapi -> 200
seg-1 2026-10-15T10:33:04.910Z epoch=1792060384.582 GET .../agnesapi -> 200   gap 15.373 s
seg-1 2026-10-15T10:33:20.267Z epoch=1792060399.920 GET .../agnesapi -> 200   gap 15.338 s
seg-1 2026-10-15T10:33:35.642Z epoch=1792060415.276 GET .../agnesapi -> 200   gap 15.356 s
seg-1 2026-10-15T10:33:51.003Z epoch=1792060430.644 GET .../agnesapi -> 200   gap 15.359 s
```

---

## 8. Any 503 retried and counted (SPEC A4.4)

**No 503 arrived in this window, so there was nothing to retry.** The claim is
carried by the status histogram above, which is the whole window:

```
status counts: {200: 126, 401: 1, 502: 8}
```

- `502 × 8` are all `DOWNLOAD` calls (section 12, FOUND-ELSEWHERE), not queue-full;
- `401 × 1` is the instrumented download retry in the very first attempt;
- the door's own counters agree: both clip envelopes report `retries: 0` and
  `queue_full_wait_s: 0`, i.e. zero platform refusals were seen and zero were
  swallowed.

This is an honest zero, not an untested path: the door's 503/429 back-off and
resubmit behaviour is proven by `test_agnes_dispatch.py` (`503 ×2 then 200 →
one submitted row`, `429 then 200 → one row`) on the branch named in the table
above. What this window adds is the live half: 112 polls and 8 posts with no
503 to hide.

---

## 9. Quota and progress files, matching what was used (SPEC A5.3, A11)

```
$ python3 proof.py quota
state_path: .../lanes/W4-proof-U1-lane/run/control/agnes-quota.sqlite3
limits: {'video': 500, 'image': 4000}
utc_day: 2026-10-15   next_reset: 2026-10-16T00:00:00+00:00
remaining video: 480   remaining image: 3994
used today (reserved+succeeded): {'image': 6, 'video': 20}
```

Every row, in insertion order:

```
1  image  units=1  reserved  still-1
2  image  units=1  reserved  still-closeup
3  image  units=1  reserved  still-a
4  image  units=1  reserved  still-b
5  image  units=1  reserved  still-c
6  video  units=10 failed    seg-2      <- pool refusal, never sent, released
7  video  units=10 failed    seg-1      <- pool refusal, never sent, released
8  video  units=10 reserved  seg-2      <- the clip that was made
9  video  units=10 reserved  seg-1      <- the clip that was made
10 image  units=1  reserved  still-d
```

The numbers match what was actually used:

- **video: 500 − 480 = 20 seconds = exactly the two 10-second clips.** The two
  `failed` rows are the first attempt that never reached the network (section
  12b); they were released through `agnes_quota.settle(id, ok=False)` — the
  "failed job releases its seconds" path — and therefore do not count.
- **image: 4000 − 3994 = 6**, one row per still generation, including the two
  that generated on the vendor side but could not be downloaded (section 12a).
- Nothing was reserved for the body capture: that used a fake quota seam, and
  no capture row exists in the table.

Progress file, written atomically by `agnes_quota.progress()`:

```
$ python3 proof.py progress --done 2 --in-flight 0
run/control/agnes-progress.json:
{"clips_total": 2, "clips_done": 2, "in_flight": 0, "waiting_reason": null,
 "next_continue_utc": null, "eta_minutes_low": 0, "eta_minutes_high": 0,
 "updated_utc": "2026-10-15T10:41:23Z"}
```

The ETA maths is exercised too, on its own run folder so the live file is never
lied to — 1 of 2 done and 1 in flight is one remaining round at the measured
11-13 minutes:

```
Q.progress(run-partial, clips_total=2, clips_done=1, in_flight=1)
{"clips_total": 2, "clips_done": 1, "in_flight": 1, ..., "eta_minutes_low": 11,
 "eta_minutes_high": 13}
```

---

## 10. Dry-run assembly at 30 fps

```
$ python3 proof.py assemble          # assembler.main([timeline, out.mp4, --dry-run])
timeline: fps=30 width=1080 height=1920
  seg 1  run/conform/seg-1-30fps.mp4  10.066 s
  seg 2  run/conform/seg-2-30fps.mp4  10.066 s
return_code=1   output_rendered=False
outcome=error   reason=LIPSYNC_COVERAGE_SHORT+LIPSYNC_LINES_TOO_FEW
```

The dry run executed and produced its full receipt:

```
plan fps=30.0 w=1080 h=1920 total_dur=19.733333333333334
argv: nice -n 10 ffmpeg -threads 3 -y -i seg-1-30fps.mp4 -i seg-2-30fps.mp4
      -filter_complex [0:v]trim=...,scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,
      crop=w=1080:h=1920:x=0:y=0,setsar=1[v0]; ... xfade ... [vout]
      -map [vout] -an -c:v libx264 -pix_fmt yuv420p -r 30 -movflags +faststart run/out.mp4
qc_no_blur ok: True
motion: outcome=ok reason=CLIPS_MOTION_PASS
frame_text rows: 0
output_rendered: false            (a dry run renders nothing, by design)
```

`-r 30`, `-an`, lanczos cover-scale and the two conformed 30 fps inputs are all
in the argv, and **no `out.mp4` was written**.

The envelope carries `outcome=error` for exactly one reason, and it is not an
Agnes one: E6 lip-sync coverage. This proof is forbidden a KIE call, so the
timeline has no lip-sync clips at all — `0 line(s) of 0.00 s in a 19.7 s ad;
the rule needs at least 3 line(s) and 9.87 s`. `assembler.py` says what that
means ("blocked before spend, but evidence stays"): the dry-run receipt is
returned in full with `gate_evidence` attached, and no render happens. The gate
is satisfied only by a run that actually carries its lip-sync clips, which is
W1-method-lipsync's and `lipsync_clips`' territory, not this receipt's.

---

## 11. Picture gate and face-crop ladder on an Agnes cartoon close-up (SPEC A7)

Real mediapipe measurement (lane venv, mediapipe 1.1.1), the pinned face model,
`regenerate=None` so **no paid regeneration is reachable**:

```
$ ./venv/bin/python3 picture_probe.py
model: .../lip_gate/assets/face_landmarker.task
crop ladder widths: [0.7, 0.6, 0.8]   target face height: 38.0
```

**The close-up that passes the gate** — `still-a.png`, the Agnes cartoon
close-up, measured directly:

```
still-a.png  verdict=ACCEPT_WITH_FLAG  face_count=1  face_h_pct=28.7
             yaw_proxy=0.347 roll_deg=2.5 smile=0.07 jaw_open=0.0
             inner_gap_pct=1.12 sharp_face_256=2466.4
             reasons=[]   flags=['TEETH']
   attempt still-a.png -> ACCEPT_WITH_FLAG
```

**The ladder, on the Agnes close-up that shows no face** — `still-d.png` is a
9:16 close-up of the same character's hands; the ladder is keyed off
`face_count == 0`, so it runs there and only there:

```
still-d.png  verdict=FAIL  face_count=0  reasons=['FACE_COUNT']
    attempt still-d.png      -> FAIL ['FACE_COUNT']
    attempt still-d-ladder1.png -> FAIL ['FACE_COUNT']   rung width 0.70
    attempt still-d-ladder2.png -> FAIL ['FACE_COUNT']   rung width 0.60
    attempt still-d-ladder3.png -> FAIL ['FACE_COUNT']   rung width 0.80
```

All three rungs ran, each wrote its own receipt in `evidence/picture-receipts/`,
and the gate stayed fail-closed instead of inventing a pass. `still-b.png` (a
frame with no person in it) behaves identically, and `still-c.png` is refused on
`HEAD_YAW` with no ladder (a face is present). Every one of those outcomes is a
gate result on a real Agnes cartoon still, measured by the real model.

---

## 12. FOUND-ELSEWHERE (proven here, not fixed here — QC-AND-FIXER §2.2)

**a. `agnes_dispatch`'s media download always fails: the transport sends the
HTTP method `DOWNLOAD`, and the origin answers 502.**

```
agnes_dispatch.py:496-503  _download() -> transport("DOWNLOAD", url, key, None)
agnes_dispatch.py:105-131  default_transport() -> urllib.request.Request(url, method="DOWNLOAD")
```

Same URL, same host, one control, no auth difference:

```
method "DOWNLOAD" -> HTTPError 502
GET               -> 200 bytes=3277709
```

Seen **8 times out of 8 downloads** in this window (4 stills, 2 clips, plus the
2 first attempts): every `DOWNLOAD` returned 502, and every one was recovered by
the instrumented `GET` retry in this proof's transport wrapper
(`GET-RETRY-FOR-DOWNLOAD ... -> 200`). Without that wrapper the door returns
`agnes-result-missing` ("Agnes answered 200 but carried no image bytes") even
though the bytes exist — that is the `still-1` and `still-closeup` evidence JSON
above.

**b. A video dispatch without an explicit `pool_dir` never starts.**

```
agnes_dispatch.py:656-659
    refused = quota_admission(quota, "video", 10, ...)   # quota is None here
    pool = quota_pool_dir(quota, pool_dir)               # still None -> returns None
agnes_dispatch.py:379-390  quota_pool_dir(None, None) -> None
```

`quota_admission` imports `agnes_quota` into its *own* local name, so the
caller's `quota` stays `None`. First attempt, verbatim:

```
outcome=error reason_code=agnes-quota-unavailable
next_action=the quota folder that holds the two in-flight video slots could not
            be resolved (agnes_quota.state_path); nothing was sent.
```

Nothing was sent, so the door's own documented `--pool-dir` flag was passed on
the retry and both clips then went through. The CLI at
`agnes_dispatch.py:933-935` exposes `--pool-dir` with a `None` default, so the
documented command line has the same hole.

**c. The quota row reserved just above that failure is never released.**

The reservation happens at `agnes_dispatch.py:656`, the pool refusal returns at
`agnes_dispatch.py:660-664`, and no `agnes_quota.settle()` runs in between —
the two `failed` rows in section 9 had to be released by hand with
`agnes_quota.settle(id, ok=False)`. SPEC A5.3 says a failed job releases its
seconds.

**d. Pre-existing regression failure on this base, untouched by this diff.**

```
$ python3 -m pytest -q 75-drama-song-ad-factory/tests
1 failed, 193 passed
FAILED 75-drama-song-ad-factory/tests/test_model_choice.py::ModelChoice::test_no_model_pin_in_skill_docs
  AssertionError: <re.Match ... match='<model name redacted>'> is not None :
  75-drama-song-ad-factory/references/studio-e2e-receipt.md
```

The matched text is redacted here on purpose: this test scans every
`references/*.md` for that model name, so quoting it verbatim would make this
file a second match and turn a pre-existing failure into a new one. The regex is
`tests/test_model_choice.py:7` (`PIN`).

Control: the worktree was `git status --porcelain`-empty (exactly base
`1e1c12dcc`) when that run happened, so the failure is the base's own, on a file
this diff does not touch. Re-run with this file present (section 14) still names
`studio-e2e-receipt.md` as the only failing file.

---

## 13. Budget and spend

| Budget (BUILD-PLAN W4-proof-U1) | Used |
|---|---|
| ≤ 20 Agnes video-seconds | **20** — two 10-second clips, quota shows `500 − 480 = 20` |
| ≤ 15 images | **6** — `still-1`, `still-closeup`, `still-a`, `still-b`, `still-c`, `still-d`; quota shows `4000 − 3994 = 6` |
| KIE spend | **0** — see below |

No KIE spend, proved two ways:

```
$ python3 proof.py control
control OK -> REFUSED-KIE-HOST: api.kie.ai
```

(the guard raises before a socket is opened, so no request can reach KIE), and
the host histogram of every request in the window:

```
hosts: ['apihub.agnes-ai.com', 'platform-outputs.agnes-ai.space']
```

Every dollar figure on every Agnes row is `0` (`actual_cost=0` in each
envelope, `estimated_cost=0` in each `spend_ledger` row).

---

## 14. Area regression (top of BUILD-PLAN.md)

Run in this unit's worktree at base `1e1c12dcc` plus this one file:

```
$ bash run_regressions.sh        # 16 commands, full log in evidence/regression.txt
15 commands exit=0
1 command  exit=1   <- the pre-existing test_model_choice failure in section 12d
```

The commands are the BUILD-PLAN list, with `S75` resolved to
`75-drama-song-ad-factory/` as the BUILD-PLAN header defines it. Two
substitutions, stated rather than skipped, per BUILD-PLAN's own instruction:

1. `S75/tests/test_cli_smoke.py` **does not exist on O `origin/main`** —
   `git ls-files | grep smoke` returns nothing under `75-drama-song-ad-factory/`.
   Nearest equivalent run: `python3 -m pytest -q 75-drama-song-ad-factory/tests`
   (193 passed, the 1 pre-existing failure above).
2. `node --test S75/mini-app/service/test/*.test.mjs` run with the glob expanded.

Green: intake card, dispatch + lock, catalog calculator, final assembler, song,
length, story/board, clips, lip-sync, checklist, factory (intake preflight),
ready post kit, shared bridge, service, page (`run-all.sh`: 14 + 32 + 3 + 5 + 49
+ drift rules all OK), and skill 75's own test directory.

---

## 15. What this receipt does not claim

- The two 503-retry and 429-retry behaviours were **not** triggered live in this
  window (section 8) — no platform refusal arrived. Their live proof remains
  parked behind the door's own test suite, not asserted here as measured.
- The dry-run assembly did **not** return `outcome=ok` (section 10): E6
  lip-sync coverage cannot pass without lip-sync clips, and this proof buys no
  KIE. The dry run itself executed and its argv, plan and gates are quoted.
- The face-crop ladder did **not** accept any picture: on both face-free Agnes
  stills all three rungs ran and the gate stayed `FAIL` (section 11). It is
  recorded as run, not as accepted.
- Nothing in this document was produced by a second run: every number comes from
  the single window named at the top.
