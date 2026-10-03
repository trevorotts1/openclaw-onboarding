#!/usr/bin/env bash
# Skill 72 automated QC.
#
# Checks, in order:
#   1. every scene segment exists and its frame count matches the manifest
#   2. no missing or zero-byte files in the work tree
#   3. blackdetect sweep clean (no unintended black runs over 0.5s)
#   4. freezedetect sweep clean (no unintended frozen runs over 1.0s)
#   5. audio duration equals video duration (within 0.2s)
#   6. contact sheet: 2-3 frames per scene tiled into one image for the
#      human 30-second review
#
# Usage:
#   bash scripts/qc.sh --manifest run/manifest.json --workdir work --final final.mp4
set -u
MANIFEST=""; WORKDIR=""; FINAL=""
while [ $# -gt 0 ]; do case "$1" in
  --manifest) MANIFEST="$2"; shift 2;;
  --workdir) WORKDIR="$2"; shift 2;;
  --final) FINAL="$2"; shift 2;;
  *) echo "unknown arg $1" >&2; exit 2;;
esac; done
[ -n "$MANIFEST" ] && [ -n "$WORKDIR" ] && [ -n "$FINAL" ] || { echo "usage: qc.sh --manifest M --workdir W --final F" >&2; exit 2; }
[ -f "$FINAL" ] || { echo "QC FAIL: final video missing: $FINAL" >&2; exit 1; }

fail=0
say() { printf '[QC %s] %s\n' "$1" "$2"; }

# 1. segment frame counts vs manifest
while read -r sid frames; do
  seg="$WORKDIR/scenes/$sid/$sid.mp4"
  if [ ! -f "$seg" ]; then say FAIL "missing segment $seg"; fail=1; continue; fi
  got=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$seg")
  if [ "$got" = "$frames" ]; then say PASS "segment $sid frames $got"; else say FAIL "segment $sid: manifest $frames frames, file has $got"; fail=1; fi
done < <(python3 -c "
import json
m = json.load(open('$MANIFEST'))
for s in m['scenes']:
    print(s['id'], round(s['duration_seconds'] * m['fps']))
")

# 2. zero-byte / missing files
if find "$WORKDIR" -type f -size 0 | grep -q .; then
  say FAIL "zero-byte files:"; find "$WORKDIR" -type f -size 0 | head; fail=1
else say PASS "no zero-byte files"; fi

# 3. blackdetect sweep on the final
black=$(ffmpeg -i "$FINAL" -vf "blackdetect=d=0.5:pix_th=0.10" -an -f null - 2>&1 | grep -c black_start || true)
if [ "$black" -eq 0 ]; then say PASS "blackdetect clean"; else say FAIL "blackdetect found $black black run(s)"; fail=1; fi

# 4. freezedetect sweep on the final
frz=$(ffmpeg -i "$FINAL" -vf "freezedetect=n=0.003:d=1.0" -an -f null - 2>&1 | grep -c freeze_start || true)
if [ "$frz" -eq 0 ]; then say PASS "freezedetect clean"; else say FAIL "freezedetect found $frz frozen run(s)"; fail=1; fi

# 5. audio duration equals video duration
vdur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$FINAL")
adur=$(ffprobe -v error -select_streams a:0 -show_entries stream=duration -of csv=p=0 "$FINAL")
diff=$(python3 -c "print(abs(float('$vdur')-float('$adur')))")
ok=$(python3 -c "print('yes' if float('$diff') <= 0.2 else 'no')")
if [ "$ok" = yes ]; then say PASS "audio==video duration (${vdur}s vs ${adur}s)"; else say FAIL "audio/video duration mismatch: video ${vdur}s audio ${adur}s"; fail=1; fi

# 6. contact sheet: 3 frames per scene, tiled
SHEET="$WORKDIR/contact-sheet.jpg"
python3 - "$MANIFEST" "$WORKDIR" "$SHEET" <<'PY'
import json, subprocess, sys, os
m = json.load(open(sys.argv[1])); work = sys.argv[2]; sheet = sys.argv[3]
tiles = []
for s in m["scenes"]:
    seg = "%s/scenes/%s/%s.mp4" % (work, s["id"], s["id"])
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "csv=p=0", seg],
        capture_output=True, text=True, check=True).stdout.strip())
    for frac, tag in ((0.15, "a"), (0.5, "b"), (0.85, "c")):
        t = d * frac
        out = "/tmp/mvplus_tile_%s_%s.jpg" % (s["id"], tag)
        subprocess.run(["ffmpeg", "-y", "-ss", str(t), "-i", seg,
                        "-frames:v", "1", "-q:v", "4", out],
                       check=True, capture_output=True)
        tiles.append(out)
cols = 3
rows = (len(tiles) + cols - 1) // cols
subprocess.run(["ffmpeg", "-y"] +
               sum([["-i", t] for t in tiles], []) +
               ["-filter_complex", "tile=%dx%d" % (cols, rows),
                "-q:v", "4", sheet], check=True, capture_output=True)
for t in tiles:
    os.unlink(t)
print("contact sheet: %s (%d tiles)" % (sheet, len(tiles)))
PY
say PASS "contact sheet written: $SHEET"

if [ "$fail" -eq 0 ]; then echo "SKILL 72 QC PASS"; exit 0; fi
echo "SKILL 72 QC FAIL" >&2; exit 1
