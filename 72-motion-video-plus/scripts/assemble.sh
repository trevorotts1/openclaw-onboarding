#!/usr/bin/env bash
# Skill 72 assembly.
#
# Joins scene segments with crossfaded joins, lays ONE continuous music bed
# over the final assembly (never per-segment music, to avoid seams), ducks
# the bed under the voiceover with FFmpeg sidechain compression, and mixes
# in beat-synced UI sounds from the manifest sfx_events.
#
# Cleanup: each scene's PNGs were already deleted by render.js after its
# segment encoded. This script deletes nothing but its temp dir (trap).
#
# Usage:
#   bash scripts/assemble.sh --manifest run/manifest.json --workdir work \
#     --voiceover work/audio/voiceover.mp3 --out final.mp4
set -euo pipefail

MANIFEST=""; WORKDIR=""; VOICEOVER=""; OUT=""
while [ $# -gt 0 ]; do case "$1" in
  --manifest) MANIFEST="$2"; shift 2;;
  --workdir) WORKDIR="$2"; shift 2;;
  --voiceover) VOICEOVER="$2"; shift 2;;
  --out) OUT="$2"; shift 2;;
  *) echo "unknown arg $1" >&2; exit 2;;
esac; done
[ -n "$MANIFEST" ] && [ -n "$WORKDIR" ] && [ -n "$OUT" ] || { echo "usage: assemble.sh --manifest M --workdir W --voiceover V --out O" >&2; exit 2; }

command -v ffmpeg >/dev/null || { echo "ffmpeg not found" >&2; exit 2; }
command -v ffprobe >/dev/null || { echo "ffprobe not found" >&2; exit 2; }
command -v python3 >/dev/null || { echo "python3 not found" >&2; exit 2; }
[ -f "$VOICEOVER" ] || { echo "voiceover not found: $VOICEOVER (run scripts/tts.py first)" >&2; exit 3; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# One python pass builds: ordered segment files, absolute sfx event times,
# the xfade video chain, and the audio graph. Shell just runs ffmpeg.
python3 - "$MANIFEST" "$WORKDIR" "$VOICEOVER" "$OUT" "$TMP" <<'PY'
import json, subprocess, shlex, sys

manifest_p, work, voiceover, out, tmp = sys.argv[1:6]
m = json.load(open(manifest_p))
FADE = 0.5

def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "csv=p=0", p],
        capture_output=True, text=True, check=True).stdout.strip())

# 1. segments, in order, with durations
segs = []
for s in m["scenes"]:
    p = "%s/scenes/%s/%s.mp4" % (work, s["id"], s["id"])
    try:
        open(p, "rb").close()
    except OSError:
        sys.exit("missing segment %s (render it first)" % p)
    segs.append((s["id"], p, dur(p)))

# 2. video: xfade chain across segments
vfilt = ""
off = 0.0
prev = "[0:v]"
for i in range(1, len(segs)):
    off = off + segs[i-1][2] - FADE
    lab = "[xv%d]" % i
    vfilt += "%s[%d:v]xfade=transition=fade:duration=%.2f:offset=%.3f%s;" % (prev, i, FADE, off, lab)
    prev = lab
vfilt += prev + "[vout];"

# 3. audio inputs: voiceover, then one input per sfx event
sfxmap = m.get("sfx", {})
inputs = [voiceover]
events = []  # (absolute_seconds, soundfile)
t = 0.0
for s, (_, _, d) in zip(m["scenes"], segs):
    for e in s.get("sfx_events", []):
        sf = sfxmap.get(e["sound"])
        if not sf:
            sys.exit("sfx '%s' not in manifest sfx map" % e["sound"])
        inputs.append(sf)
        events.append((t + e["at_seconds"], len(inputs) - 1))
    t += d

afilt = ""
mix_terms = ["[0:a]"]
for k, (at, inp_idx) in enumerate(events):
    ms = int(at * 1000)
    afilt += "[%d:a]adelay=%d|%d[sd%d];" % (inp_idx, ms, ms, k)
    mix_terms.append("[sd%d]" % k)
afilt += "".join(mix_terms) + "amix=inputs=%d:normalize=0[vo];" % len(mix_terms)

music = m.get("music_bed", "")
if music:
    inputs.append(music)
    mi = len(inputs) - 1
    afilt += ("[%d:a]volume=0.35,apad[bg];" % mi
              + "[bg][vo]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400[duck];"
              + "[duck][vo]amix=inputs=2:normalize=0[aout]")
else:
    afilt += "[vo]anull[aout]"

filter_complex = vfilt + afilt

cmd = ["ffmpeg", "-y"]
for i, p in enumerate(segs):
    cmd += ["-i", p]
for p in inputs:
    cmd += ["-i", p]
cmd += ["-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k", "-shortest", out]

with open(tmp + "/run-ffmpeg.sh", "w") as f:
    f.write("#!/usr/bin/env bash\nset -euo pipefail\n")
    f.write(" ".join(shlex.quote(c) for c in cmd) + "\n")
print("assembling %d segments, %d sfx events, music bed %s"
      % (len(segs), len(events), "on" if music else "off"))
PY

bash "$TMP/run-ffmpeg.sh"
echo "assembled: $OUT"
