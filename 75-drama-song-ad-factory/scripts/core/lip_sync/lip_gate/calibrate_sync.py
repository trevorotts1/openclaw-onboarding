#!/usr/bin/env python3
"""calibrate_sync.py: print the control table for the sync check (read-only).

Known-good controls the verdict map must reproduce:
  approved SPOKEN clips with their own audio  -> PASS
  approved SUNG clips with their own audio    -> ACCEPT_WITH_FLAG or UNDETERMINED (never FAIL)
  cartoon / non-human faces                   -> UNMEASURABLE
  any clip with WRONG audio                   -> never PASS
  one frame held still, real audio            -> never PASS
Usage (needs mediapipe + opencv + the face model, e.g. the fixer venv):
  python3 calibrate_sync.py CLIPS.json
CLIPS.json = {"label": {"clip": "a.mp4", "audio": "a.wav", "kind": "spoken|sung|cartoon",
                        "set": "group name"}, ...}
`set` groups the lines of one chapter: the other lines of the set are the control for
each clip. Give at least 3 entries per set. The client clips are NOT in this repo and
the unit tests never need them. Exit 1 when any control is wrong.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lip_gate as G  # noqa: E402
import mouth_landmarks as ML  # noqa: E402
import sync_check as SC  # noqa: E402


def table(spec):
    series, envs = {}, {}

    def env(path, fps):
        k = (path, fps)
        if k not in envs:
            envs[k] = G.envelope(path, fps=fps)
        return envs[k]

    def measure(clip, audio, others):
        if clip not in series:
            series[clip] = ML.mouth_series(clip)
        s = series[clip]
        filled, why = ML.usable(s)
        if why:
            return SC.unmeasurable(why)
        f = s["fps"]
        return SC.measure_sync(filled, env(audio, f), [env(o, f) for o in others],
                               f, s["face_found"], s["mouth_pos"])

    rows, bad = [], 0

    def row(case, kind, want, clip, audio, others, sung):
        nonlocal bad
        j = G.judge(measure(clip, audio, others), sung)
        ok = j["verdict"] in want
        bad += not ok
        rows.append("| %-34s | %-8s | %-26s | %-16s | %-10s | %5.2f | %3d | %5.2f | %6.3f | %s |" % (
            case, kind, "/".join(want), j["verdict"], j["grade"], j["corr"], j["lag_frames"],
            j["pct"], j["margin"], "OK" if ok else "BAD"))

    ids = list(spec)
    for i in ids:
        s = spec[i]
        mates = [spec[k]["audio"] for k in ids
                 if k != i and spec[k].get("set") == s.get("set")]
        kind = s.get("kind", "spoken")
        want = {"spoken": (G.PASS,), "sung": (G.FLAG, G.UNDETERMINED, G.PASS),
                "cartoon": (G.UNMEASURABLE,)}[kind]
        row("%s own audio" % i, kind, want, s["clip"], s["audio"], mates, kind == "sung")
    for i in ids:
        if spec[i].get("kind") == "cartoon":
            continue
        for j in ids:
            if i == j:
                continue
            own_set = [spec[k]["audio"] for k in ids if spec[k].get("set") == spec[i].get("set")]
            others = [a for a in own_set if a != spec[j]["audio"]]
            row("%s + WRONG audio %s" % (i, j), "wrong", (G.FAIL, G.FLAG, G.UNDETERMINED,
                                                           G.UNMEASURABLE),
                spec[i]["clip"], spec[j]["audio"], others, spec[i].get("kind") == "sung")
    # one frame held for the whole clip, real audio (ffmpeg through the load governor)
    for i in ids:
        if spec[i].get("kind") == "cartoon":
            continue
        d = tempfile.mkdtemp()
        png, still = os.path.join(d, "f.png"), os.path.join(d, "still.mp4")
        for argv in (["ffmpeg", "-v", "error", "-y", "-i", spec[i]["clip"], "-frames:v", "1", png],
                     ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", "30", "-i", png,
                      "-i", spec[i]["audio"], "-t", "3.5", "-c:v", "libx264", "-pix_fmt",
                      "yuv420p", "-c:a", "aac", "-shortest", still]):
            G._run_raw(argv)
        mates = [spec[k]["audio"] for k in ids
                 if k != i and spec[k].get("set") == spec[i].get("set")]
        row("STILL face (%s frame 0) + real audio" % i, "still", (G.FAIL, G.FLAG, G.UNDETERMINED,
                                                                    G.UNMEASURABLE),
            still, spec[i]["audio"], mates, spec[i].get("kind") == "sung")
    print("| case | kind | want | verdict | grade | corr | lag | chance pct | margin | ok |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    print("\n".join(rows))
    # hard rule: wrong audio and a still face are never PASS
    passed = [r for r in rows if ("WRONG" in r or "STILL" in r) and "| PASS " in r]
    for r in passed:
        print("BAD (never PASS):", r)
    bad += len(passed)
    print("CONTROLS", "PASS" if not bad else "FAIL (%d wrong)" % bad)
    return bad


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(1 if table(json.load(open(sys.argv[1]))) else 0)
