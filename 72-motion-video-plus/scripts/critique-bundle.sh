#!/usr/bin/env bash
# Skill 72 critique bundle assembler.
#
# Builds the review bundle the fresh critic scores in
# references/critique-protocol.md:
#   contact.jpg      2 fps contact strip of the preview/final video
#   phone.jpg        360 px wide strip (readability check)
#   beats.jpg        one frame per beat, when beats.json exists
#   safe.jpg         9:16 frame with the keep-out zones drawn on
#   metrics.json     durations, frame counts, loudness readings
#
# Usage:
#   bash scripts/critique-bundle.sh --video preview.mp4 --outdir review/r1 \
#       [--beats work/audio/beats.json]
set -u
VIDEO=""; OUTDIR=""; BEATS=""
while [ $# -gt 0 ]; do case "$1" in
  --video) VIDEO="$2"; shift 2;;
  --outdir) OUTDIR="$2"; shift 2;;
  --beats) BEATS="$2"; shift 2;;
  *) echo "unknown arg $1" >&2; exit 2;;
esac; done
[ -n "$VIDEO" ] && [ -n "$OUTDIR" ] || { echo "usage: critique-bundle.sh --video V --outdir D [--beats B]" >&2; exit 2; }
[ -f "$VIDEO" ] || { echo "video not found: $VIDEO" >&2; exit 2; }
command -v ffmpeg >/dev/null || { echo "ffmpeg not found" >&2; exit 2; }
command -v ffprobe >/dev/null || { echo "ffprobe not found" >&2; exit 2; }

mkdir -p "$OUTDIR"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# 2 fps contact strip of the whole video
ffmpeg -hide_banner -loglevel error -y -i "$VIDEO" -vf "fps=2,scale=320:-1,tile=8x8" \
  -frames:v 1 -q:v 4 "$OUTDIR/contact.jpg"

# phone-size strip: 360 px wide, 1 fps
ffmpeg -hide_banner -loglevel error -y -i "$VIDEO" -vf "fps=1,scale=360:-1,tile=6x6" \
  -frames:v 1 -q:v 4 "$OUTDIR/phone.jpg"

# per-beat frames, one per beat, when a beat grid exists
if [ -n "$BEATS" ] && [ -f "$BEATS" ]; then
  : > "$TMP/beatlist.txt"
  python3 - "$BEATS" "$TMP" <<'PY'
import json, sys
beats = json.load(open(sys.argv[1]))["beat_times"]
tmp = sys.argv[2]
with open(tmp + "/beatlist.txt", "w") as f:
    for i, t in enumerate(beats):
        f.write("%s %f\n" % (tmp + ("/beat_%04d.jpg" % i), t))
PY
  while read -r out t; do
    ffmpeg -hide_banner -loglevel error -y -ss "$t" -i "$VIDEO" \
      -frames:v 1 -q:v 4 "$out"
  done < "$TMP/beatlist.txt"
  ls "$TMP"/beat_*.jpg 2>/dev/null | head -64 > "$TMP/inputs.txt"
  if [ -s "$TMP/inputs.txt" ]; then
    n=$(wc -l < "$TMP/inputs.txt")
    cols=8; rows=$(( (n + cols - 1) / cols ))
    ffmpeg -hide_banner -loglevel error -y -pattern_type glob -i "$TMP/beat_*.jpg" \
      -filter_complex "tile=${cols}x${rows}" -q:v 4 "$OUTDIR/beats.jpg"
  fi
fi

# 9:16 safe-zone check: center crop with keep-out zones drawn
ffmpeg -hide_banner -loglevel error -y -ss 1 -i "$VIDEO" -frames:v 1 \
  -vf "crop=in_h*9/16:in_h,drawbox=x=0:y=0:w=iw:h=ih*0.14:c=red:t=4,drawbox=x=0:y=ih*0.8:w=iw:h=ih*0.2:c=red:t=4,drawbox=x=iw*0.88:y=0:w=iw*0.12:h=ih:c=red:t=4" \
  -q:v 4 "$OUTDIR/safe.jpg"

# metrics.json
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VIDEO")
frames=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$VIDEO")
loud=$(ffmpeg -hide_banner -i "$VIDEO" -af loudnorm=I=-14:TP=-1:LRA=11:print_format=json -f null - 2>&1 \
  | python3 -c "import json,sys; s=sys.stdin.read(); print(json.dumps(json.loads(s[s.index('{'):s.rindex('}')+1])))" 2>/dev/null || echo '{"integrated_loudness":"n/a"}')
python3 - "$OUTDIR" "$dur" "$frames" "$loud" <<'PY'
import json, sys
outdir, dur, frames, loud = sys.argv[1:5]
json.dump({
    "duration_seconds": float(dur),
    "video_frames": frames.strip(),
    "loudness": json.loads(loud),
}, open(outdir + "/metrics.json", "w"), indent=2)
PY

echo "critique bundle: $OUTDIR"
ls "$OUTDIR"
