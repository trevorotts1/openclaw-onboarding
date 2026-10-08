#!/usr/bin/env python3
"""calibrate_controls.py: print the control table for the looser lip-sync check.

Known-good controls the cut-offs must satisfy:
  approved clips with their OWN audio  -> PASS
  the same clips with WRONG audio      -> FAIL
  one frame held still, real audio     -> FAIL
Usage (needs mediapipe + opencv + the face model, e.g. the fixer venv):
  python3 calibrate_controls.py CLIPS.json
CLIPS.json = {"label": {"clip": "a.mp4", "audio": "a.wav", "kind": "sung|spoken"}, ...}
Every clip's audio is also the wrong-audio / control audio for the others, so
give at least 3 entries. The client clips are NOT in this repo and the unit tests
never need them. Exit 1 when any control is wrong.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lip_gate as G  # noqa: E402

FF = "ffmpeg"


def table(spec):
    ids, rows, bad = list(spec), [], 0

    def row(case, want, clip, audio, others):
        nonlocal bad
        try:
            j = G.judge(G.measure_file(clip, audio, others))
        except Exception as e:
            j = G.unmeasured(e)
        ok = j["verdict"] in want
        bad += not ok
        rows.append("| %-26s | %-6s | %-16s | %5.2f | %3s | %6.2f | %s | %s |" % (
            case, "/".join(w[:6] for w in want), j["verdict"], j["corr"],
            j["lag_frames"], j["margin"], "OK " if ok else "BAD",
            ",".join(j.get("reasons", []) + j.get("flags", []))))

    for i in ids:
        others = [spec[k]["audio"] for k in ids if k != i]
        row("%s %s own audio" % (spec[i].get("kind", "?"), i), (G.PASS,),
            spec[i]["clip"], spec[i]["audio"], others)
    for i in ids:
        for j in ids:
            if i != j:
                others = [spec[k]["audio"] for k in ids if k != j]
                row("%s + WRONG audio %s" % (i, j), (G.FAIL,),
                    spec[i]["clip"], spec[j]["audio"], others)
    i = ids[0]
    d = tempfile.mkdtemp()
    png, still = os.path.join(d, "f.png"), os.path.join(d, "still.mp4")
    subprocess.run([FF, "-v", "error", "-y", "-i", spec[i]["clip"], "-frames:v",
                    "1", png], check=True)
    subprocess.run([FF, "-v", "error", "-y", "-loop", "1", "-framerate", "30",
                    "-i", png, "-i", spec[i]["audio"], "-t", "3.5", "-c:v",
                    "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                    still], check=True)
    row("still face + real audio", (G.FAIL,), still, spec[i]["audio"],
        [spec[k]["audio"] for k in ids if k != i])
    print("| case | want | got | onset corr | lag fr | margin | ok | why |")
    print("|---|---|---|---|---|---|---|---|")
    print("\n".join(rows))
    print("CONTROLS", "PASS" if not bad else "FAIL (%d wrong)" % bad)
    return bad


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(1 if table(json.load(open(sys.argv[1]))) else 0)
