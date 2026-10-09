#!/usr/bin/env python3
"""calibrate_events.py: control table for the ADVISORY event_sync (read-only).

Same CLIPS.json and controls as calibrate_sync.py. Word stamps are not in the
file, so only voiced-run onset and offset events are scored (no p/b/m events).
event_sync may only ever gate if this table does as well as or better than
calibrate_sync.py's on the same controls. Usage (fixer venv: mediapipe + opencv):
  python3 calibrate_events.py CLIPS.json
Exit 1 when any control is wrong (own audio NOT_SYNCED, wrong audio / still face
SYNCED, cartoon not UNMEASURABLE).
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import event_sync as ES  # noqa: E402
import lip_gate as G  # noqa: E402
import mouth_landmarks as ML  # noqa: E402


def table(spec):
    series, rows, bad = {}, [], 0

    def run(clip, audio, others):
        if clip not in series:
            series[clip] = ML.mouth_series(clip)
        s = series[clip]
        fps = s["fps"]
        n = int(round(fps))
        op = [float("nan") if v is None else v for v in s["opening"]]
        ev = lambda a: ES.events(ES.voiced_runs(G.envelope(a, fps=n), n), (), None)
        base = ev(audio)
        base["dur"] = max(base["dur"], len(op) / float(fps))
        return ES.event_sync(op, base, [ev(o) for o in others], fps)

    def row(case, want, clip, audio, others):
        nonlocal bad
        r = run(clip, audio, others)
        ok = r["verdict"] in want
        bad += not ok
        rows.append("| %-34s | %-26s | %-12s | %5.2f | %5.2f | %6.3f | %3d | %s | %s |" % (
            case, "/".join(want), r["verdict"], r["hit"], r["control_hit"], r["margin"],
            r["n_events"], ",".join(r["hard_defects"]) or "-", "OK" if ok else "BAD"))

    ids = list(spec)
    for i in ids:
        s = spec[i]
        mates = [spec[k]["audio"] for k in ids if k != i and spec[k].get("set") == s.get("set")]
        want = (ES.UNMEASURABLE,) if s.get("kind") == "cartoon" else (ES.SYNCED, ES.WEAK)
        row("%s own audio" % i, want, s["clip"], s["audio"], mates)
    for i in ids:
        if spec[i].get("kind") == "cartoon":
            continue
        for j in ids:
            if i == j:
                continue
            own = [spec[k]["audio"] for k in ids if spec[k].get("set") == spec[i].get("set")]
            row("%s + WRONG audio %s" % (i, j), (ES.WEAK, ES.NOT_SYNCED, ES.UNMEASURABLE),
                spec[i]["clip"], spec[j]["audio"], [a for a in own if a != spec[j]["audio"]])
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
        mates = [spec[k]["audio"] for k in ids if k != i and spec[k].get("set") == spec[i].get("set")]
        row("STILL face (%s frame 0) + real audio" % i, (ES.NOT_SYNCED, ES.WEAK, ES.UNMEASURABLE),
            still, spec[i]["audio"], mates)
    print("| case | want | verdict | hit | control hit | margin | events | hard defects | ok |")
    print("|---|---|---|---|---|---|---|---|---|")
    print("\n".join(rows))
    print("EVENT_SYNC CONTROLS", "PASS" if not bad else "FAIL (%d wrong)" % bad)
    return bad


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(1 if table(json.load(open(sys.argv[1]))) else 0)
