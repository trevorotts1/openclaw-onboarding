#!/usr/bin/env python3
"""DEL-06: the 60- and 90-second clips land in the delivery folder, measured.

Owner order (delivery package, item 6): every ad that comes with clips ships
TWO clip files in the client's delivery folder, with clear numbered file
names, and EVERY delivered video -- the clips included -- passes
``delivery_audio.check_delivery_audio()`` before it is listed as delivered.

Reuse only (nothing new is invented here):
  * ``clip_cutdown.plan_clips`` picks the windows (whole lines, hook in the
    first 15%, never into the end card, L-2 budget) and
    ``clip_cutdown.run_clips`` cuts them -- that path already runs the
    delivery audio gate and deletes a refused clip, fail closed;
  * ``delivery_audio.check_delivery_audio`` / ``require_delivery_audio`` is
    the gate every file below must pass;
  * ``delivery_variants.song_files`` is the model for how a delivery folder
    writer merges ``delivery-receipt.json`` and ``README.md`` -- this module
    does the same merge, never a clobber.

File names (clear, numbered, one folder per client run)::

    6 - 60-second clip.mp4
    6 - 90-second clip.mp4

Both files carry ``CLIP_ITEM`` (6): item 6 of the delivery package IS the
clips, and two files share the item's slot the way song_choices' three
versions each keep their own label inside one folder. ``DEL-13`` owns the
full numbered list; this module only states its own slot so two lanes never
guess at each other's numbers (slot 7 belongs to the ready-to-post kit).

Gate contract:
  * a delivered clip file that fails the audio gate FAILS the delivery
    (``CLIPS_AUDIO_REFUSED``) and is never listed as delivered;
  * a clip the ad never got (``clips_for(length) == ()``) is fine -- there
    is nothing to gate;
  * a clip the card promised (3, 5 or 10 minutes) but the folder does not
    hold fails closed (``CLIPS_MISSING``), naming the exact file.

stdlib only; shells to ffmpeg/ffprobe through the gate.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import delivery_audio  # noqa: E402
from clip_cutdown import clips_for, plan_clips, run_clips  # noqa: E402

TOOL_NAME = "delivery_clips"

#: the delivery folder slot these two files share (DEL-13 owns the full list)
CLIP_ITEM = 6

#: receipt key + README markers, mirroring delivery_variants.song_files
RECEIPT_NAME = "delivery-receipt.json"
README_NAME = "README.md"
_BEGIN = "<!-- delivery-clips:begin -->"
_END = "<!-- delivery-clips:end -->"

PASS, FAIL, UNAVAILABLE = "PASS", "FAIL", "UNAVAILABLE"


class DeliveryClipsError(ValueError):
    pass


def clip_file_name(seconds):
    """One clear numbered delivery file name: ``6 - 60-second clip.mp4``."""
    if seconds not in (60, 90):
        raise DeliveryClipsError("CLIP_UNKNOWN_LENGTH: %r" % (seconds,))
    return "%d - %d-second clip.mp4" % (CLIP_ITEM, seconds)


def deliver_clips(timeline, chosen_length_s, master, delivery_dir,
                  runner=None, audio_gate=None):
    """Cut the two clips into ``delivery_dir`` and list them in receipt + README.

    Returns the receipt rows (one per cut file). Fail closed: no window, an
    ffmpeg failure or a refused clip raises ``clip_cutdown.ClipCutdownError``
    with the folder left empty of partial clips; an unknown length or a
    delivered file that does not pass ``delivery_audio.check_delivery_audio()``
    after the rename raises ``DeliveryClipsError``.
    """
    out = Path(delivery_dir)
    out.mkdir(parents=True, exist_ok=True)
    plans = plan_clips(timeline, chosen_length_s)
    if not plans:
        return []                      # 60/90 s ads carry no clips: nothing owed

    kwargs = {"audio_gate": audio_gate}
    if runner is not None:             # tests inject a fake ffmpeg runner
        kwargs["runner"] = runner
    rows = []
    try:
        cut = run_clips(master, plans, str(out), **kwargs)
        if len(cut) != len(plans):
            raise DeliveryClipsError(
                "CLIPS_INCOMPLETE: planned %d clip(s), cut %d"
                % (len(plans), len(cut)))
        for plan, path in zip(plans, cut):
            seconds = int(plan["clip_length_s"])
            target = out / clip_file_name(seconds)
            if Path(path) != target:
                if target.exists():
                    target.unlink()
                os.replace(path, target)   # plan name -> clear numbered name
                path = str(target)
            # every delivered video is gated here, before it is ever listed
            try:
                delivery_audio.require_delivery_audio(path, audio_gate)
            except delivery_audio.DeliveryAudioRefused as exc:
                raise DeliveryClipsError("CLIPS_AUDIO_REFUSED: %s" % exc)
            rows.append({
                "kind": "clip",
                "clip_length_s": seconds,
                "file": target.name,
                "start_s": plan["start_s"],
                "end_s": plan["end_s"],
                "duration_s": plan["duration_s"],
                "hooks": plan["hooks"],
                "beats": plan["beats"],
                "delivery_audio": "DELIVERY_AUDIO_OK",
            })
    except Exception:
        # fail closed: any failure leaves NO clip file in the folder
        for plan in plans:
            for name in (plan["name"] + ".mp4",
                         clip_file_name(plan["clip_length_s"])):
                stale = out / name
                if stale.exists():
                    stale.unlink()
        raise

    rows.sort(key=lambda r: r["clip_length_s"])
    _write_docs(out, rows)
    return rows


def check_clips(delivery_dir, chosen_length_s, ffprobe="ffprobe",
                ffmpeg="ffmpeg"):
    """QC: (PASS|FAIL|UNAVAILABLE, detail). Fail closed on anything missing."""
    promised = clips_for(chosen_length_s)
    if not promised:
        return (PASS, "%ss ad owes no clips" % chosen_length_s)
    d = Path(delivery_dir)
    try:
        receipt = json.loads((d / RECEIPT_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (FAIL, "%s missing or unreadable; cannot list the clips"
                % RECEIPT_NAME)
    listed = {r.get("file") for r in receipt.get("delivery_clips") or []}
    readme = (d / README_NAME).read_text(encoding="utf-8") \
        if (d / README_NAME).is_file() else ""
    for seconds in promised:
        name = clip_file_name(seconds)
        p = d / name
        if not p.is_file() or p.stat().st_size == 0:
            return (FAIL, "delivery missing the %d-second clip (%s)"
                    % (seconds, name))
        if name not in listed:
            return (FAIL, "%s not listed in %s" % (name, RECEIPT_NAME))
        if name not in readme:
            return (FAIL, "%s not listed in %s" % (name, README_NAME))
        try:
            g = delivery_audio.check_delivery_audio(p, ffprobe, ffmpeg)
        except Exception as exc:      # noqa: BLE001 - a broken gate is UNAVAILABLE
            return (UNAVAILABLE, "audio gate could not read %s: %s"
                    % (name, exc))
        if not g["ok"]:
            if g["reason_code"] in (delivery_audio.UNREADABLE,):
                return (UNAVAILABLE, "UNAVAILABLE: %s: %s"
                        % (name, g["reason"]))
            return (FAIL, "%s failed the delivery audio gate (%s): %s"
                    % (name, g["reason_code"], g["reason"]))
    return (PASS, "both clips present, listed and AAC-LC 48 kHz faststart")


def _write_docs(delivery_dir, rows):
    """Merge the clip rows into delivery-receipt.json and README.md."""
    d = Path(delivery_dir)
    rp = d / RECEIPT_NAME
    receipt = json.loads(rp.read_text(encoding="utf-8")) if rp.is_file() else {}
    receipt["delivery_clips"] = rows
    rp.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                  encoding="utf-8")

    lines = [_BEGIN, "## Short clips for social", "",
             "Re-cut from your finished video on whole lines, so no clip "
             "starts or ends mid-sentence:", ""]
    for r in rows:
        lines.append("- `%s` - %d seconds (%.1f s cut, %d hook line(s))"
                     % (r["file"], r["clip_length_s"], r["duration_s"],
                        r["hooks"]))
    lines.append(_END)
    block = "\n".join(lines) + "\n"

    rd = d / README_NAME
    text = rd.read_text(encoding="utf-8") if rd.is_file() else "# Delivery\n\n"
    if _BEGIN in text and _END in text:
        import re
        text = re.sub(re.escape(_BEGIN) + r".*?" + re.escape(_END) + r"\n?",
                      lambda _m: block, text, flags=re.S)
    else:
        text = text.rstrip("\n") + "\n\n" + block
    rd.write_text(text, encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="DEL-06: cut the 60/90 s clips into the delivery folder "
                    "(numbered names, every file through the delivery audio "
                    "gate) and list them in the receipt and README")
    ap.add_argument("timeline", help="the run's edit/timeline.json")
    ap.add_argument("--length", type=int, required=True,
                    help="chosen ad length in seconds")
    ap.add_argument("--master", required=True, help="rendered master mp4")
    ap.add_argument("--delivery", required=True, help="the delivery folder")
    ap.add_argument("--check", action="store_true",
                    help="check only; do not cut (exit 5 on a FAIL)")
    ns = ap.parse_args(argv)
    if ns.check:
        verdict, detail = check_clips(ns.delivery, ns.length)
        print(json.dumps({"check": TOOL_NAME, "verdict": verdict,
                          "detail": detail}, indent=2))
        return 0 if verdict == PASS else 5
    with open(ns.timeline, encoding="utf-8") as fh:
        timeline = json.load(fh)
    rows = deliver_clips(timeline, ns.length, ns.master, ns.delivery)
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
