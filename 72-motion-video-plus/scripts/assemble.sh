#!/usr/bin/env bash
# Skill 72 assembly.
#
# Joins scene segments with crossfaded joins, lays ONE continuous music bed
# over the final assembly (never per-segment music, to avoid seams), ducks
# the bed under the voiceover with FFmpeg sidechain compression, mixes in
# beat-synced UI sounds, and finishes at -14 LUFS integrated loudness.
#
# Sound is SYNTHESIZED by default: unless the manifest names a supplied
# music_bed track, scripts/synth-score.py writes an original royalty-free
# score (no licensing to clear) and scripts/synth-sfx.py writes the UI
# sounds. The beat grid is derived from the synthesis parameters.
# Set "synth_sfx": false in the manifest to use the legacy "sfx" file map.
#
# Cleanup: each scene's PNGs were already deleted by render.js after its
# segment encoded. This script deletes nothing but its temp dir (trap).
#
# Usage:
#   bash scripts/assemble.sh --manifest run/manifest.json --workdir work \
#     --voiceover work/audio/voiceover.mp3 --out final.mp4
#   Optional: --score/--beats/--sfx-dir reuse pre-synthesized inputs (e.g.
#   synthesized in parallel with the frame render). When absent, assemble.sh
#   synthesizes the same deterministic outputs itself.
set -euo pipefail

MANIFEST=""; WORKDIR=""; VOICEOVER=""; OUT=""; SCORE=""; BEATS=""; SFXDIR=""
while [ $# -gt 0 ]; do case "$1" in
  --manifest) MANIFEST="$2"; shift 2;;
  --workdir) WORKDIR="$2"; shift 2;;
  --voiceover) VOICEOVER="$2"; shift 2;;
  --out) OUT="$2"; shift 2;;
  --score) SCORE="$2"; shift 2;;
  --beats) BEATS="$2"; shift 2;;
  --sfx-dir) SFXDIR="$2"; shift 2;;
  *) echo "unknown arg $1" >&2; exit 2;;
esac; done
[ -n "$MANIFEST" ] && [ -n "$WORKDIR" ] && [ -n "$OUT" ] || { echo "usage: assemble.sh --manifest M --workdir W --voiceover V --out O [--score S --beats B --sfx-dir D]" >&2; exit 2; }

command -v ffmpeg >/dev/null || { echo "ffmpeg not found" >&2; exit 2; }
command -v ffprobe >/dev/null || { echo "ffprobe not found" >&2; exit 2; }
command -v python3 >/dev/null || { echo "python3 not found" >&2; exit 2; }
[ -f "$VOICEOVER" ] || { echo "voiceover not found: $VOICEOVER (run scripts/tts.py first)" >&2; exit 3; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
SDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MVPLUS_SCRIPTS="$SDIR"

# One python pass builds: the (possibly synthesized) music bed and beat
# grid, the sfx file map, ordered segment files, absolute sfx event times,
# the xfade video chain, and the audio graph. Shell just runs ffmpeg.
python3 - "$MANIFEST" "$WORKDIR" "$VOICEOVER" "$OUT" "$TMP" "$SCORE" "$BEATS" "$SFXDIR" <<'PY'
import json, os, subprocess, shlex, sys

manifest_p, work, voiceover, out, tmp = sys.argv[1:6]
pre_score = sys.argv[6] if len(sys.argv) > 6 else ""
pre_beats = sys.argv[7] if len(sys.argv) > 7 else ""
pre_sfxdir = sys.argv[8] if len(sys.argv) > 8 else ""
sdir = os.environ["MVPLUS_SCRIPTS"]
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

# 1b. music bed: a supplied track wins; otherwise synthesize an original
# score (royalty-free by construction) and derive its beat grid.
# Pre-synthesized --score/--beats are reused when passed (they must have
# been built with the same music_bpm/music_seed; synthesis is deterministic).
music = m.get("music_bed", "")
beats_json = ""
if not music:
    if pre_score:
        for label, p in (("score", pre_score), ("beats", pre_beats)):
            try:
                open(p, "rb").close()
            except OSError:
                sys.exit("pre-synthesized %s not found: %s" % (label, p))
        music = pre_score
        beats_json = pre_beats
    else:
        total_dur = sum(d for _, _, d in segs)
        bpm = float(m.get("music_bpm", 120))
        seed = int(m.get("music_seed", 7))
        adir = work + "/audio"
        os.makedirs(adir, exist_ok=True)
        subprocess.run(["python3", sdir + "/synth-score.py",
                        "--bpm", str(bpm), "--duration", str(total_dur),
                        "--seed", str(seed), "--outdir", adir], check=True)
        subprocess.run(["python3", sdir + "/beat-grid.py",
                        "--params", adir + "/score-params.json",
                        "--out", adir + "/beats.json"], check=True)
        music = adir + "/score.wav"
        beats_json = adir + "/beats.json"

# 1c. sfx map: synthesized UI sounds by default; manifest "sfx" map only
# when the manifest explicitly sets "synth_sfx": false.
# A pre-synthesized --sfx-dir is reused when passed.
sfxmap = m.get("sfx", {})
if m.get("synth_sfx", True):
    if pre_sfxdir:
        for name in ("pop", "click", "whoosh", "thump"):
            try:
                open(pre_sfxdir + "/" + name + ".wav", "rb").close()
            except OSError:
                sys.exit("pre-synthesized sfx not found: %s/%s.wav" % (pre_sfxdir, name))
        sfxmap = {"pop": pre_sfxdir + "/pop.wav", "click": pre_sfxdir + "/click.wav",
                  "whoosh": pre_sfxdir + "/whoosh.wav", "thump": pre_sfxdir + "/thump.wav"}
    else:
        sfxdir = tmp + "/sfx"
        subprocess.run(["python3", sdir + "/synth-sfx.py",
                        "--outdir", sfxdir], check=True)
        sfxmap = {"pop": sfxdir + "/pop.wav", "click": sfxdir + "/click.wav",
                  "whoosh": sfxdir + "/whoosh.wav", "thump": sfxdir + "/thump.wav"}

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
        "-c:a", "aac", "-b:a", "192k", "-shortest", tmp + "/assembled.mp4"]

with open(tmp + "/run-ffmpeg.sh", "w") as f:
    f.write("#!/usr/bin/env bash\nset -euo pipefail\n")
    f.write(" ".join(shlex.quote(c) for c in cmd) + "\n")
print("assembling %d segments, %d sfx events, music %s"
      % (len(segs), len(events),
         "supplied track" if m.get("music_bed") else "synthesized"))
if beats_json:
    print("beat grid: %s" % beats_json)
PY

bash "$TMP/run-ffmpeg.sh"
# Finish at -14 LUFS integrated, true peak -1 dBTP (single loudnorm pass).
ffmpeg -hide_banner -loglevel error -y -i "$TMP/assembled.mp4" \
  -af "loudnorm=I=-14:TP=-1:LRA=11" -c:v copy -c:a aac -b:a 192k "$OUT"
echo "assembled: $OUT (-14 LUFS)"
