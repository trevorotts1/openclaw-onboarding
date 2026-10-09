"""DEL-05: every delivery folder ships the video TWICE -- captioned and clean.

One delivery folder per client run holds two clearly numbered files:

    1 - <Ad> - Ad (captioned).mp4
    2 - <Ad> - Ad (clean, no captions).mp4

Both are produced at the END OF THE RUN through
``final_assembler/captions_burn`` -- the one caption site this skill has. The
captioned file burns the plan captions_burn drew; the clean file is the SAME
plan with ``style.enabled`` False, so neither variant can invent its own
words or its own look. Nothing leaves this module until
``delivery_audio.check_delivery_audio()`` has passed it (AAC-LC, 48 kHz,
faststart, not silent): a refused file is deleted and the step raises, fail
closed, all or nothing -- a half-delivered pair is never handed over.

``check_video_delivery()`` is the QC row (PASS / FAIL / UNAVAILABLE, same
contract as ``song_files``) and ``write_video_docs()`` lists both files in
``delivery-receipt.json`` and ``README.md`` the way the song files are listed.
The caption SRT is carried in the receipt, not shipped as a third file:
shipping the caption file itself is DEL-10's job, and this step writes a
video, never a file that is not one of the two.

The returned ``captioned`` / ``clean_master`` keys are exactly the two
``batch_zip.build_batch_zip`` consumes, and ``check_video_delivery`` is the
``video_delivery`` record the delivery QC gate can require.

Stdlib + ffmpeg/ffprobe only; no network, no paid call, no operator path.
Run: python3 core/delivery_variants/video_delivery.py check <delivery_dir> <ad_name>
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Skill 75 load governor: every heavy local job goes through it (see load_governor/).
import os as _gos
_gcore = _gos.path.abspath(_gos.path.join(_gos.path.dirname(__file__), '..'))
if _gcore not in sys.path:
    sys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402
import delivery_audio  # noqa: E402
from final_assembler import captions_burn  # noqa: E402

from .manifests import sha256_file  # noqa: E402

CHECK_NAME = "video_delivery"
RECEIPT_NAME = "delivery-receipt.json"
README_NAME = "README.md"
_BEGIN, _END = "<!-- video-delivery:begin -->", "<!-- video-delivery:end -->"
PASS, FAIL, UNAVAILABLE = "PASS", "FAIL", "UNAVAILABLE"

#: The two delivered files, in the order the client opens the folder.
CAPTIONED_N, CLEAN_N = 1, 2
KINDS = ("captioned", "clean_master")

RENDER_TIMEOUT_S = 900


class VideoDeliveryError(Exception):
    """A delivery video could not be produced or was refused by the gate."""

    def __init__(self, code, message, path=None):
        super().__init__("%s: %s" % (code, message))
        self.code, self.path = code, path


def safe_name(ad_name):
    name = re.sub(r"[^\w\-]+", "-", (ad_name or "").strip()).strip("-")
    if not name:
        raise ValueError("ad_name required")
    return name


def captioned_name(ad_name):
    """Numbered, unmistakable: the version with the captions on it."""
    return "%d - %s - Ad (captioned).mp4" % (CAPTIONED_N, safe_name(ad_name))


def clean_name(ad_name):
    """Numbered, unmistakable: the same cut with no captions at all."""
    return "%d - %s - Ad (clean, no captions).mp4" % (CLEAN_N, safe_name(ad_name))


def _argv(args, ffmpeg="ffmpeg"):
    """Governor-bounded argv; a renamed vendor binary still runs unblessed."""
    args = [str(a) for a in args]
    try:
        return _LG.ffmpeg_argv(args, ffmpeg=ffmpeg)
    except _LG.LoadGovernorError:
        return [ffmpeg] + args


def _ass_colour(hex_colour):
    """#RRGGBB -> ASS &HAABBGGRR (alpha 00 = opaque)."""
    h = (hex_colour or "").lstrip("#")
    if len(h) != 6:
        return "&H000000"
    return "&H00%s%s%s" % (h[4:6], h[2:4], h[0:2])


def force_style(style):
    """D16's look as an ffmpeg ``force_style`` string.

    Every value is READ from the plan captions_burn drew -- box colour, font
    colour, font size, the safe-area margins. This function only speaks the
    render filter's syntax; it decides no look of its own.

    ponytail: libass force_style draws a RECTANGLE, not a rounded box, so
    ``box="rounded"`` arrives square. Upgrade path: emit an ASS ``\\p`` draw
    path when the render pass grows one; the style record already carries the
    intent.
    """
    return ",".join((
        "FontSize=%d" % int(round(style.get("font_size_px") or 48)),
        "PrimaryColour=%s" % _ass_colour(style.get("font_colour")),
        "BackColour=%s" % _ass_colour(style.get("box_colour")),
        "BorderStyle=3",            # 3 = background box, the white rounded box
        "Outline=0", "Shadow=0",
        "Alignment=2",              # bottom centre
        "MarginV=%d" % int(round(style.get("bottom_margin_px") or 0)),
        "MarginL=%d" % int(round(style.get("edge_margin_px") or 0)),
        "MarginR=%d" % int(round(style.get("edge_margin_px") or 0)),
    ))


def burn_argv(master, out, srt_name, style, ffmpeg="ffmpeg"):
    """ffmpeg argv: master + captions_burn's SRT + captions_burn's look."""
    vf = "subtitles=%s:force_style='%s'" % (srt_name, force_style(style))
    return _argv(["-y", "-v", "error", "-i", str(master),
                  "-map", "0:v:0", "-map", "0:a:0", "-vf", vf,
                  "-c:v", "libx264", "-pix_fmt", "yuv420p",
                  *delivery_audio.AUDIO_OUT_ARGS,
                  *delivery_audio.FASTSTART_ARGS, str(out)], ffmpeg)


def clean_argv(master, out, ffmpeg="ffmpeg"):
    """ffmpeg argv: the master untouched -- picture copied, audio to AAC."""
    return _argv(["-y", "-v", "error", "-i", str(master),
                  "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy",
                  *delivery_audio.AUDIO_OUT_ARGS,
                  *delivery_audio.FASTSTART_ARGS, str(out)], ffmpeg)


def probe(path, ffprobe="ffprobe"):
    """{width, height, duration_s} of the master's picture. Raises on unreadable."""
    try:
        p = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60)
        doc = json.loads(p.stdout or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise VideoDeliveryError("MASTER_UNREADABLE", str(exc), str(path))
    if p.returncode != 0:
        raise VideoDeliveryError("MASTER_UNREADABLE",
                                 (p.stderr or "ffprobe failed")[-300:], str(path))
    streams = doc.get("streams") or []
    if not streams or not streams[0].get("width"):
        raise VideoDeliveryError("MASTER_NO_PICTURE", "no video stream", str(path))
    fmt = doc.get("format") or {}
    try:
        duration = float(fmt.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    return {"width": int(streams[0]["width"]),
            "height": int(streams[0]["height"]),
            "duration_s": duration}


def _plan(lines, cues, provenance, geo, enabled, srt_path=None):
    plan, why = captions_burn.build_plan(
        lines, provenance=provenance, cues=cues,
        width_px=geo["width"], height_px=geo["height"],
        enabled=enabled, srt_path=srt_path)
    if why:
        raise VideoDeliveryError("CAPTION_PLAN_REFUSED", why)
    return plan


def _render(argv, job, cwd=None):
    try:
        proc = _LG.run_ffmpeg(argv, job, cwd=cwd, capture_output=True,
                              text=True, timeout=RENDER_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VideoDeliveryError("RENDER_FAILED", "%s: %s" % (job, exc))
    if proc.returncode != 0:
        raise VideoDeliveryError(
            "RENDER_FAILED",
            "%s failed (exit %s): %s" % (job, proc.returncode,
                                         (proc.stderr or "")[-400:]))


def _gate(path, audio_gate):
    try:
        return delivery_audio.require_delivery_audio(path, audio_gate)
    except delivery_audio.DeliveryAudioRefused as exc:
        path.unlink(missing_ok=True)
        raise VideoDeliveryError("DELIVERY_AUDIO_REFUSED", str(exc),
                                 str(path)) from None


def build_video_delivery(master, delivery_dir, ad_name, lines, cues=None,
                         provenance=None, ffmpeg="ffmpeg", ffprobe="ffprobe",
                         audio_gate=None):
    """Write the numbered pair into ``delivery_dir``. All or nothing, fail closed.

    Returns ``{"captioned", "clean_master", "files", "srt", "rows",
    "duration_s", "resolution", "plans"}``; ``captioned`` / ``clean_master``
    are ready to hand straight to ``batch_zip.build_batch_zip``.
    """
    master = Path(master)
    if not master.is_file() or master.stat().st_size == 0:
        raise VideoDeliveryError("MASTER_MISSING",
                                 "no master video at %s" % master, str(master))
    out = Path(delivery_dir)
    out.mkdir(parents=True, exist_ok=True)
    geo = probe(master, ffprobe=ffprobe)

    # ONE caption site: both variants are captions_burn's plan, captions on
    # and captions off. This module renders them; it writes no caption text.
    plan_cap = _plan(lines, cues, provenance, geo, enabled=True)
    plan_clean = _plan(lines, cues, provenance, geo, enabled=False)
    if not plan_cap.get("srt"):
        raise VideoDeliveryError("CAPTION_TIMING_UNAVAILABLE",
                                 "measured cues are required to burn captions")

    cap_path = out / captioned_name(ad_name)
    clean_path = out / clean_name(ad_name)
    tmp = Path(tempfile.mkdtemp(prefix="dsaf-del05-"))
    try:
        srt_path = tmp / "captions.srt"
        srt_path.write_text(plan_cap["srt"], encoding="utf-8")
        _render(burn_argv(master, cap_path, srt_path.name,
                          plan_cap["style"], ffmpeg),
                "video-delivery-captioned", cwd=str(tmp))
        _render(clean_argv(master, clean_path, ffmpeg),
                "video-delivery-clean")
    finally:
        for junk in tmp.glob("*"):
            try:
                junk.unlink()
            except OSError:
                pass
        try:
            tmp.rmdir()
        except OSError:
            pass

    # Gate both before either is called delivered: a refused pair leaves NOTHING.
    try:
        gate_cap = _gate(cap_path, audio_gate)
        gate_clean = _gate(clean_path, audio_gate)
    except VideoDeliveryError:
        cap_path.unlink(missing_ok=True)
        clean_path.unlink(missing_ok=True)
        raise

    resolution = "%dx%d" % (geo["width"], geo["height"])
    rows = [{"kind": kind, "file": path.name, "sha256": sha256_file(path),
             "duration_s": geo["duration_s"], "resolution": resolution,
             "mean_db": g["mean_db"]}
            for kind, path, g in (("captioned", cap_path, gate_cap),
                                  ("clean_master", clean_path, gate_clean))]
    return {"captioned": str(cap_path), "clean_master": str(clean_path),
            "files": [r["file"] for r in rows], "rows": rows,
            "srt": plan_cap["srt"],
            "plans": {"captioned": plan_cap, "clean": plan_clean},
            "gates": {"captioned": gate_cap, "clean_master": gate_clean},
            "duration_s": geo["duration_s"], "resolution": resolution}


def write_video_docs(delivery_dir, rows):
    """List the pair in delivery-receipt.json and README.md (merge, never clobber)."""
    d = Path(delivery_dir)
    rp = d / RECEIPT_NAME
    receipt = json.loads(rp.read_text(encoding="utf-8")) if rp.is_file() else {}
    receipt["video_delivery"] = rows
    rp.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                  encoding="utf-8")
    lines = [_BEGIN, "## The video", "",
             "Two versions of the same cut -- post the captioned one, keep "
             "the clean one for anything that draws its own text:", ""]
    for r in rows:
        label = ("Captions on" if r["kind"] == "captioned"
                 else "No captions")
        lines.append("- `%s` - %s, %s" % (r["file"], label,
                                          r.get("resolution") or "UNMEASURED"))
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


def check_video_delivery(delivery_dir, ad_name, ffprobe="ffprobe",
                         ffmpeg="ffmpeg", audio_gate=None):
    """(PASS|FAIL|UNAVAILABLE, detail): both files present, listed and gated.

    Missing file, a file the receipt or README never names, or a file that
    fails ``check_delivery_audio`` is a FAIL. An unreadable probe is
    UNAVAILABLE, never a pass.
    """
    d = Path(delivery_dir)
    try:
        receipt = json.loads((d / RECEIPT_NAME).read_text(encoding="utf-8"))
        listed = {r.get("file") for r in receipt.get("video_delivery") or []}
    except (OSError, ValueError):
        return (FAIL, "%s missing or unreadable; cannot list the videos"
                % RECEIPT_NAME)
    readme = (d / README_NAME).read_text(encoding="utf-8") \
        if (d / README_NAME).is_file() else ""
    for kind, fname in (("captioned", captioned_name(ad_name)),
                        ("clean", clean_name(ad_name))):
        p = d / fname
        if not p.is_file() or p.stat().st_size == 0:
            return (FAIL, "delivery is missing the %s video %s" % (kind, fname))
        if fname not in listed:
            return (FAIL, "%s not listed in %s" % (fname, RECEIPT_NAME))
        if fname not in readme:
            return (FAIL, "%s not listed in %s" % (fname, README_NAME))
        try:
            if audio_gate is None:
                res = delivery_audio.check_delivery_audio(
                    p, ffprobe=ffprobe, ffmpeg=ffmpeg)
            else:                       # tests inject a stand-in gate
                res = audio_gate(p)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            return (UNAVAILABLE, "ffprobe/ffmpeg could not read %s: %s"
                    % (fname, exc))
        if isinstance(res, dict) and res.get("ok") is False \
                and str(res.get("reason_code", "")).startswith("DELIVERY_AUDIO_UNREADABLE"):
            return (UNAVAILABLE, "%s: %s" % (fname, res.get("reason")))
        if not (isinstance(res, dict) and res.get("ok")):
            return (FAIL, "%s: %s" % (fname,
                                      (res or {}).get("reason", "refused")))
    return (PASS, "captioned and clean both present, listed and AAC-gated")


def _cli(argv=None):
    a = list(argv) if argv is not None else sys.argv[1:]
    if len(a) != 3 or a[0] != "check":
        print("usage: video_delivery.py check <delivery_dir> <ad_name>")
        return 1
    verdict, detail = check_video_delivery(a[1], a[2])
    print(json.dumps({"check": CHECK_NAME, "verdict": verdict,
                      "detail": detail}))
    return 0 if verdict == PASS else 5


if __name__ == "__main__":
    raise SystemExit(_cli())
