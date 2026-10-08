"""H14: every delivery folder ships the finished SONG as its own audio files.

Trevor: "you're giving me the video, but you're not giving me the audio in
case they just want to use the song." Delivery folder must hold the full
mastered mix as MP3 320 kbps + WAV named after the ad, plus the instrumental
(same two formats) when one exists. The receipt (delivery-receipt.json) and
README.md list them; check_song_files() is the QC gate and fails closed.
Stdlib + ffmpeg/ffprobe only.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from .manifests import sha256_file

CHECK_NAME = "song_files"
MP3_KBPS = 320
RECEIPT_NAME = "delivery-receipt.json"
README_NAME = "README.md"
_BEGIN, _END = "<!-- song-files:begin -->", "<!-- song-files:end -->"
PASS, FAIL, UNAVAILABLE = "PASS", "FAIL", "UNAVAILABLE"


def safe_name(ad_name):
    name = re.sub(r"[^\w\-]+", "-", (ad_name or "").strip()).strip("-")
    if not name:
        raise ValueError("ad_name required")
    return name


def expected_files(ad_name, instrumental=False):
    n = safe_name(ad_name)
    kinds = [("song", "")] + ([("instrumental", "-instrumental")] if instrumental else [])
    return [(kind, "%s%s.%s" % (n, suf, ext), ext)
            for kind, suf in kinds for ext in ("mp3", "wav")]


def _probe(path, ffprobe="ffprobe"):
    out = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=codec_name,bit_rate,duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    s = (json.loads(out).get("streams") or [{}])[0]
    return {"codec": s.get("codec_name"), "bit_rate": int(s.get("bit_rate") or 0),
            "duration_s": float(s.get("duration") or 0)}


def build_song_files(mix_path, delivery_dir, ad_name, instrumental_path=None,
                     ffmpeg="ffmpeg", ffprobe="ffprobe"):
    """Encode the mastered mix (and instrumental, if any) into delivery_dir.
    mix_path may also be the final video: -vn drops the picture."""
    out = Path(delivery_dir)
    out.mkdir(parents=True, exist_ok=True)
    srcs = {"song": mix_path, "instrumental": instrumental_path}
    rows = []
    for kind, fname, ext in expected_files(ad_name, bool(instrumental_path)):
        codec = ["-c:a", "libmp3lame", "-b:a", "%dk" % MP3_KBPS] if ext == "mp3" \
            else ["-c:a", "pcm_s16le"]
        dst = out / fname
        subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(srcs[kind]), "-vn",
                        *codec, str(dst)], check=True)
        rows.append({"kind": kind, "file": fname, "format": ext,
                     "sha256": sha256_file(dst), **_probe(dst, ffprobe)})
    return rows


def write_song_docs(delivery_dir, rows):
    """List the song files in delivery-receipt.json and README.md (merge,
    never clobber other receipt/README content)."""
    d = Path(delivery_dir)
    rp = d / RECEIPT_NAME
    receipt = json.loads(rp.read_text(encoding="utf-8")) if rp.is_file() else {}
    receipt["song_files"] = rows
    rp.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [_BEGIN, "## The song (audio only)", "",
             "Use these if you only want the song, not the video:", ""]
    for r in rows:
        label = "Full song" if r["kind"] == "song" else "Instrumental (no vocals)"
        lines.append("- `%s` - %s, %s" % (r["file"], label,
                     "MP3 320 kbps" if r["format"] == "mp3" else "WAV, lossless"))
    lines.append(_END)
    block = "\n".join(lines) + "\n"
    rd = d / README_NAME
    text = rd.read_text(encoding="utf-8") if rd.is_file() else "# Delivery\n\n"
    if _BEGIN in text and _END in text:
        text = re.sub(re.escape(_BEGIN) + r".*?" + re.escape(_END) + r"\n?",
                      lambda _m: block, text, flags=re.S)
    else:
        text = text.rstrip("\n") + "\n\n" + block
    rd.write_text(text, encoding="utf-8")


def check_song_files(delivery_dir, ad_name, ffprobe="ffprobe"):
    """QC: (PASS|FAIL|UNAVAILABLE, detail). Missing song file = FAIL."""
    d = Path(delivery_dir)
    try:
        receipt = json.loads((d / RECEIPT_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (FAIL, "%s missing or unreadable; cannot list song files" % RECEIPT_NAME)
    listed = {r.get("file") for r in receipt.get("song_files") or []}
    has_instr = any(r.get("kind") == "instrumental" for r in receipt.get("song_files") or [])
    readme = (d / README_NAME).read_text(encoding="utf-8") if (d / README_NAME).is_file() else ""
    for kind, fname, ext in expected_files(ad_name, has_instr):
        p = d / fname
        if not p.is_file() or p.stat().st_size == 0:
            return (FAIL, "delivery missing %s file %s" % (kind, fname))
        if fname not in listed:
            return (FAIL, "%s not listed in %s" % (fname, RECEIPT_NAME))
        if fname not in readme:
            return (FAIL, "%s not listed in %s" % (fname, README_NAME))
        try:
            info = _probe(p, ffprobe)
        except (OSError, subprocess.CalledProcessError, ValueError):
            return (UNAVAILABLE, "ffprobe could not read %s" % fname)
        if info["duration_s"] <= 0 and ext == "wav":
            return (FAIL, "%s has no audio duration" % fname)
        if ext == "mp3" and info["bit_rate"] < MP3_KBPS * 1000 * 0.98:
            return (FAIL, "%s is %d bps, below %d kbps" % (fname, info["bit_rate"], MP3_KBPS))
    return (PASS, "song files present, listed in receipt and README")


def _cli(argv=None):
    a = argv if argv is not None else sys.argv[1:]
    if len(a) != 3 or a[0] != "check":
        print("usage: song_files.py check <delivery_dir> <ad_name>")
        return 1
    verdict, detail = check_song_files(a[1], a[2])
    print(json.dumps({"check": CHECK_NAME, "verdict": verdict, "detail": detail}))
    return 0 if verdict == PASS else 5


if __name__ == "__main__":
    sys.exit(_cli())
