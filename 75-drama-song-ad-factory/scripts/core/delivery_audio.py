"""delivery_audio.py: every delivered video carries real AAC audio.

FU-AAC-FINAL-MUX. QuickTime plays MP3-in-MP4 silent and social platforms /
iPhones expect AAC, so each ffmpeg argv that writes a delivered MP4 takes
AUDIO_OUT_ARGS + FASTSTART_ARGS (never `-c:a copy` of an mp3/wav source),
and check_delivery_audio() is the gate that refuses a delivered file whose
audio is not AAC or is silent. Stdlib only; shells to ffprobe/ffmpeg.
"""
import json
import re
import subprocess
import sys

AUDIO_OUT_ARGS = ["-c:a", "aac", "-profile:a", "aac_low", "-ar", "48000",
                  "-b:a", "256k"]
FASTSTART_ARGS = ["-movflags", "+faststart"]
SILENT_DB = -50.0
BAD_CODEC = "DELIVERY_AUDIO_NOT_AAC"
SILENT = "DELIVERY_AUDIO_SILENT"
NO_AUDIO = "DELIVERY_AUDIO_MISSING"
UNREADABLE = "DELIVERY_AUDIO_UNREADABLE"


def _res(ok, code, reason, **kw):
    return dict(ok=ok, reason_code=code, reason=reason, **kw)


def check_delivery_audio(path, ffprobe="ffprobe", ffmpeg="ffmpeg"):
    """{ok, reason_code, reason, codec, mean_db}; ok only for non-silent AAC."""
    try:
        p = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries",
             "stream=codec_name", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60)
        streams = json.loads(p.stdout or "{}").get("streams") or []
        if p.returncode != 0:
            return _res(False, UNREADABLE, "ffprobe failed: " + p.stderr[-200:])
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return _res(False, UNREADABLE, "ffprobe error: %s" % exc)
    if not streams:
        return _res(False, NO_AUDIO, "%s has no audio stream" % path)
    codec = streams[0].get("codec_name")
    if codec != "aac":
        return _res(False, BAD_CODEC, "audio codec is %r, must be aac "
                    "(QuickTime plays MP3-in-MP4 silent)" % codec, codec=codec)
    try:
        v = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-vn",
             "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _res(False, UNREADABLE, "ffmpeg error: %s" % exc, codec=codec)
    m = re.search(r"mean_volume:\s*(-?[\d.]+|-inf)\s*dB", v.stderr)
    if not m:
        return _res(False, UNREADABLE, "no volumedetect output", codec=codec)
    mean = float("-inf") if m.group(1) == "-inf" else float(m.group(1))
    if mean < SILENT_DB:
        return _res(False, SILENT, "decoded audio is silent (mean %s dB < %g "
                    "dB)" % (m.group(1), SILENT_DB), codec=codec, mean_db=mean)
    return _res(True, "DELIVERY_AUDIO_OK", "aac, mean %.1f dB" % mean,
                codec=codec, mean_db=mean)


if __name__ == "__main__":
    out = [check_delivery_audio(a) for a in sys.argv[1:]]
    print(json.dumps(out, indent=2))
    raise SystemExit(0 if out and all(r["ok"] for r in out) else 5)
