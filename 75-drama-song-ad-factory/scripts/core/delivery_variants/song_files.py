"""H14: every delivery folder ships the finished SONG as its own audio files.

Trevor: "you're giving me the video, but you're not giving me the audio in
case they just want to use the song." Delivery folder must hold the full
mastered mix as MP3 320 kbps + WAV named after the ad, plus the instrumental
(same two formats) when one exists. The receipt (delivery-receipt.json) and
README.md list them; check_song_files() is the QC gate and fails closed.
Stdlib + ffmpeg/ffprobe only.

DEL-01 (complete client delivery package): the delivery folder also ships
THREE clearly-labelled audio versions -- the full song, the instrumental
and the voice-only stem -- each a numbered MP3, plus a short plain-English
note file that explains how the three differ. All three are EXISTING
pipeline output (the finished mix, the instrumental when the run made one,
the vocal stem saved for every take); nothing is re-synthesised here.
build_audio_versions() encodes them and writes the note; check_audio_versions()
is the QC gate and fails closed -- a missing source or file is a refusal,
never a two-version delivery dressed up as three.
"""
from __future__ import annotations

import json
import re
import subprocess

# Skill 75 load governor: every heavy local job goes through it (see load_governor/).
import os as _gos, sys as _gsys
_gcore = _gos.path.abspath(_gos.path.join(_gos.path.dirname(__file__), '..'))
if _gcore not in _gsys.path:
    _gsys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402
import sys
from pathlib import Path

from .manifests import sha256_file

CHECK_NAME = "song_files"
MP3_KBPS = 320
RECEIPT_NAME = "delivery-receipt.json"
README_NAME = "README.md"
_BEGIN, _END = "<!-- song-files:begin -->", "<!-- song-files:end -->"
PASS, FAIL, UNAVAILABLE = "PASS", "FAIL", "UNAVAILABLE"

# ── DEL-01: three clearly-labelled audio versions + a plain-English note ─────
# Every delivery folder ships the song three ways. The three are EXISTING
# pipeline output, never re-synthesised here: the finished mix, the
# instrumental the run already made, and the vocal stem saved for every take
# (song_dispatch saves stem + timestamps for every take; vocal separation
# hands back vocals AND instrumental together). One table drives the file
# labels, the note prose and the QC expectations, so they cannot drift.
DELIVERY_VERSIONS = (
    ("01", "Full Song",
     "the complete song, with the music and the singing together, exactly as "
     "it plays in your video"),
    ("02", "Instrumental",
     "the same music with no singing on it, for use as background music on "
     "its own"),
    ("03", "Voice Only",
     "just the singing, with no music behind it, for use on its own"),
)
VERSION_NOTE_NAME = "00 - About These Audio Files.txt"
VERSIONS_CHECK_NAME = "audio_versions"
_V_BEGIN, _V_END = "<!-- audio-versions:begin -->", "<!-- audio-versions:end -->"


def version_file_name(number, label, ext="mp3"):
    """The numbered name the client sees: ``01 - Full Song.mp3``."""
    n = re.sub(r"[^\w\- ]+", "", label).strip() or "Audio"
    return "%s - %s.%s" % (number, n, ext)


def expected_version_files():
    """[(number, label, filename)] for the three delivery versions."""
    return [(num, label, version_file_name(num, label))
            for num, label, _desc in DELIVERY_VERSIONS]


def version_note_text():
    """The plain-English note: what each version is, in client words.

    Built from DELIVERY_VERSIONS so the note, the file labels and the QC
    expectations always agree. No model names, no tool names, no prices, no
    income promises -- only what each file is and when to use it.
    """
    lines = ["About the three audio files in this folder", "=" * 44, "",
             "You are getting the same song three ways. Here is what each "
             "one is:", ""]
    for num, label, desc in DELIVERY_VERSIONS:
        lines.append("%s - %s" % (num, label))
        lines.append("This is %s." % desc)
        lines.append("")
    lines.append("All three are the same recording and the same length, just "
                 "with different parts of it kept in. They are high-quality "
                 "MP3 files you can use straight away.")
    return "\n".join(lines) + "\n"


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
        _LG.run_ffmpeg([ffmpeg, "-y", "-v", "error", "-i", str(srcs[kind]), "-vn",
                        *codec, str(dst)], "song-encode", check=True)
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


def build_audio_versions(mix_path, delivery_dir, instrumental_path,
                         vocal_stem_path, ffmpeg="ffmpeg", ffprobe="ffprobe"):
    """Encode the three labelled audio versions into delivery_dir (DEL-01).

    ``mix_path`` is the finished mix, ``instrumental_path`` the instrumental
    the run already made, ``vocal_stem_path`` the vocal stem saved for every
    take. All three are EXISTING pipeline output -- nothing is re-synthesised
    here. Every source is required: a delivery that ships two versions
    dressed up as three is a refusal, never a quiet pass. Returns the receipt
    rows (one per encoded file). Raises ValueError on a missing/empty source.
    """
    srcs = {"01": mix_path, "02": instrumental_path, "03": vocal_stem_path}
    for num, label, _d in DELIVERY_VERSIONS:
        src = srcs.get(num)
        if not src or not str(src).strip():
            raise ValueError("no %s source for audio version %s (%s); the "
                             "three versions are existing pipeline output, "
                             "never re-synthesised" % (label, num, label))
        if not Path(src).is_file() or Path(src).stat().st_size == 0:
            raise ValueError("audio version %s (%s) source missing or empty: "
                             "%s" % (num, label, src))
    out = Path(delivery_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for num, label, fname in expected_version_files():
        dst = out / fname
        _LG.run_ffmpeg([ffmpeg, "-y", "-v", "error", "-i", str(srcs[num]),
                        "-vn", "-c:a", "libmp3lame", "-b:a", "%dk" % MP3_KBPS,
                        str(dst)], "audio-version-encode", check=True)
        rows.append({"kind": "audio-version", "number": num, "label": label,
                     "file": fname, "format": "mp3",
                     "sha256": sha256_file(dst), **_probe(dst, ffprobe)})
    note = out / VERSION_NOTE_NAME
    note.write_text(version_note_text(), encoding="utf-8")
    rows.append({"kind": "audio-version-note", "number": "00",
                 "label": "About These Audio Files", "file": VERSION_NOTE_NAME,
                 "format": "txt", "sha256": sha256_file(note),
                 "bytes": note.stat().st_size})
    return rows


def write_version_docs(delivery_dir, rows):
    """List the three versions in delivery-receipt.json and README.md (merge,
    never clobber other receipt/README content)."""
    d = Path(delivery_dir)
    rp = d / RECEIPT_NAME
    receipt = json.loads(rp.read_text(encoding="utf-8")) if rp.is_file() else {}
    receipt["audio_versions"] = rows
    rp.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                  encoding="utf-8")
    lines = [_V_BEGIN, "## Three audio versions", "",
             "The same song, three ways -- see `%s` for what each one is:"
             % VERSION_NOTE_NAME, ""]
    for r in rows:
        if r.get("kind") != "audio-version":
            continue
        lines.append("- `%s` - %s (%s, %s)" % (
            r["file"], r["label"],
            "MP3 320 kbps" if r["format"] == "mp3" else r["format"],
            "%s s" % ("%.1f" % r["duration_s"]) if r.get("duration_s") else "n/a"))
    lines.append("- `%s` - the note explaining how they differ"
                 % VERSION_NOTE_NAME)
    lines.append(_V_END)
    block = "\n".join(lines) + "\n"
    rd = d / README_NAME
    text = rd.read_text(encoding="utf-8") if rd.is_file() else "# Delivery\n\n"
    if _V_BEGIN in text and _V_END in text:
        text = re.sub(re.escape(_V_BEGIN) + r".*?" + re.escape(_V_END) + r"\n?",
                      lambda _m: block, text, flags=re.S)
    else:
        text = text.rstrip("\n") + "\n\n" + block
    rd.write_text(text, encoding="utf-8")


def check_audio_versions(delivery_dir, ffprobe="ffprobe"):
    """QC (DEL-01): (PASS|FAIL|UNAVAILABLE, detail). All three MP3s and the
    note must exist, be listed in the receipt and README, and probe cleanly.
    Fail closed -- a two-version delivery is never a pass."""
    d = Path(delivery_dir)
    try:
        receipt = json.loads((d / RECEIPT_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (FAIL, "%s missing or unreadable; cannot list audio versions"
                % RECEIPT_NAME)
    listed = {r.get("file") for r in receipt.get("audio_versions") or []}
    readme = (d / README_NAME).read_text(encoding="utf-8") \
        if (d / README_NAME).is_file() else ""
    if not (d / VERSION_NOTE_NAME).is_file():
        return (FAIL, "delivery missing the note file %s" % VERSION_NOTE_NAME)
    if VERSION_NOTE_NAME not in listed:
        return (FAIL, "%s not listed in %s" % (VERSION_NOTE_NAME, RECEIPT_NAME))
    if VERSION_NOTE_NAME not in readme:
        return (FAIL, "%s not listed in %s" % (VERSION_NOTE_NAME, README_NAME))
    for num, label, fname in expected_version_files():
        p = d / fname
        if not p.is_file() or p.stat().st_size == 0:
            return (FAIL, "delivery missing audio version %s (%s): %s"
                    % (num, label, fname))
        if fname not in listed:
            return (FAIL, "%s not listed in %s" % (fname, RECEIPT_NAME))
        if fname not in readme:
            return (FAIL, "%s not listed in %s" % (fname, README_NAME))
        try:
            info = _probe(p, ffprobe)
        except (OSError, subprocess.CalledProcessError, ValueError):
            return (UNAVAILABLE, "ffprobe could not read %s" % fname)
        if info["duration_s"] <= 0:
            return (FAIL, "%s has no audio duration" % fname)
        if info["bit_rate"] < MP3_KBPS * 1000 * 0.98:
            return (FAIL, "%s is %d bps, below %d kbps"
                    % (fname, info["bit_rate"], MP3_KBPS))
    return (PASS, "three audio versions and the note present, listed in "
            "receipt and README")


def _cli(argv=None):
    a = argv if argv is not None else sys.argv[1:]
    if len(a) == 3 and a[0] == "check":
        verdict, detail = check_song_files(a[1], a[2])
        print(json.dumps({"check": CHECK_NAME, "verdict": verdict,
                          "detail": detail}))
        return 0 if verdict == PASS else 5
    if len(a) == 2 and a[0] == "check-versions":
        verdict, detail = check_audio_versions(a[1])
        print(json.dumps({"check": VERSIONS_CHECK_NAME, "verdict": verdict,
                          "detail": detail}))
        return 0 if verdict == PASS else 5
    print("usage: song_files.py check <delivery_dir> <ad_name> | "
          "check-versions <delivery_dir>")
    return 1



def produce_delivery(run_dir, item):
    """DEL-13 packaging adapter: stage this item's canonical files.

    The one naming scheme lives in delivery_package.contract (``NN - Label.ext``
    per item number). This adapter stages the item's files under those exact
    canonical names via contract.produce_item, so the packaging call copies
    them verbatim and the folder gate opens them unchanged. Signature is the
    packaging contract: produce_delivery(run_dir, item) -> list[Path].
    """
    from delivery_package.contract import produce_item
    staging = Path(run_dir) / "_package" / item.key
    return produce_item(item, staging)


if __name__ == "__main__":
    sys.exit(_cli())
