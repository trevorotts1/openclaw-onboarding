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

    06 - Clip 60s.mp4
    06 - Clip 90s.mp4

Both files carry ``CLIP_ITEM`` (6): item 6 of the delivery package IS the
clips, and two files share the item's slot the way song_choices' three
versions each keep their own label inside one folder. ``DEL-13`` owns the
full numbered list; this module only states its own slot so two lanes never
guess at each other's numbers (slot 7 belongs to the ready-to-post kit).

Method runs (SPEC C5 / C5+ F19, method ``8.4``, inert until
``control/method.json`` exists -- ``clip_cutdown.plan_clips`` returns
trailer and ad plans only then) name their files as what they are, so a
client never opens "Clip" and finds a trailer::

    06 - Trailer 60s.mp4      episode / channel destination
    06 - Trailer 90s.mp4      episode / channel destination
    13 - Ad 60s.mp4           offer destination
    13 - Ad 90s.mp4           offer destination

The trailers keep the clip slot (06 -- they are the clipped promotion of
the same package); the ad clip takes slot **13**, because slot 07 is the
Ready-to-Post Kit and slots 08-12 belong to the rest of the contract. Each
trailer/ad row also writes its own ``destination`` and ``source_map`` into
``delivery-receipt.json`` (merged, never clobbered) so the trailer's "watch
the episode" link never turns out to be the checkout link. A plan reaches
this module as ``kind`` ``trailer``/``ad`` or a ``trailer-``/``ad-`` plan
name; a trailer or ad plan without a destination or without a source map
fails closed before anything is listed.

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

#: the delivery folder slot these two files share. The DELIVERY NAMES are the
#: ONE naming scheme, taken verbatim from the DEL-13 contract (``NN -
#: Label.ext``) -- both clips share item number 06, told apart by label.
from delivery_package.contract import ITEMS_BY_KEY as _ITEMS  # noqa: E402

_CLIPS = _ITEMS["clips"]
CLIP_ITEM = _CLIPS.number
#: seconds -> the contract's canonical file name for that clip.
_CLIP_FILES = {60: _CLIPS.files[0], 90: _CLIPS.files[1]}

#: receipt key + README markers, mirroring delivery_variants.song_files
RECEIPT_NAME = "delivery-receipt.json"
README_NAME = "README.md"
_BEGIN = "<!-- delivery-clips:begin -->"
_END = "<!-- delivery-clips:end -->"

PASS, FAIL, UNAVAILABLE = "PASS", "FAIL", "UNAVAILABLE"

#: method run: the slot and label of every plan kind (F11 / F19). Trailers
#: share the clip slot; the ad clip takes 13 because slot 7 is the
#: Ready-to-Post Kit and 8-12 are the rest of the DEL-13 contract.
AD_ITEM = 13
_KINDS = {"clip": (CLIP_ITEM, "Clip"),
          "trailer": (CLIP_ITEM, "Trailer"),
          "ad": (AD_ITEM, "Ad")}
#: the plan keys every trailer/ad receipt row must carry, fail closed.
_PIECE_KEYS = ("source_in", "source_out", "trailer_in", "trailer_out")


class DeliveryClipsError(ValueError):
    pass


def plan_kind(plan):
    """What this plan is: ``clip`` (today), ``trailer`` or ``ad`` (method).

    ``clip_cutdown.plan_clips`` marks a method plan with ``kind``; the plan
    name (``trailer-60s`` / ``ad-90s``) is the fallback so a plan that only
    carries its render name still lands in the right slot.
    """
    kind = plan.get("kind")
    if kind in _KINDS:
        return kind
    name = str(plan.get("name") or "")
    if name.startswith("trailer"):
        return "trailer"
    if name.startswith("ad"):
        return "ad"
    return "clip"


def clip_file_name(seconds, kind="clip"):
    """One clear numbered delivery file name: ``06 - Clip 60s.mp4``.

    ``kind`` picks the slot and the label -- ``06 - Trailer 60s.mp4`` and
    ``13 - Ad 90s.mp4`` on a method run; every other run is the contract's
    canonical file name unchanged. An unknown kind or an unknown length is a
    refusal, never a freshly invented name.
    """
    if kind not in _KINDS:
        raise DeliveryClipsError("CLIP_UNKNOWN_KIND: %r" % (kind,))
    if kind != "clip":
        if seconds not in (60, 90):
            raise DeliveryClipsError("CLIP_UNKNOWN_LENGTH: %r" % (seconds,))
        slot, label = _KINDS[kind]
        return "%02d - %s %ds.mp4" % (slot, label, seconds)
    if seconds not in _CLIP_FILES:
        raise DeliveryClipsError("CLIP_UNKNOWN_LENGTH: %r" % (seconds,))
    return _CLIP_FILES[seconds]


def source_map(plan):
    """The receipt's ``source_map`` for a trailer/ad plan, fail closed.

    Method ``10.5`` records ``{source_in, source_out, trailer_in,
    trailer_out}`` per piece: the pieces the plan joined, or -- when the plan
    carries one whole window instead -- that window as one piece.
    """
    pieces = plan.get("pieces")
    if isinstance(pieces, list) and pieces:
        out = [{k: p[k] for k in _PIECE_KEYS if k in p} for p in pieces]
        return [p for p in out if p]
    if plan.get("start_s") is not None and plan.get("end_s") is not None:
        return [{"source_in": plan["start_s"], "source_out": plan["end_s"],
                 "trailer_in": plan.get("trailer_in", 0.0),
                 "trailer_out": plan.get(
                     "trailer_out", plan.get("duration_s"))}]
    raise DeliveryClipsError(
        "TRAILER_NO_SOURCE_MAP: %r carries neither pieces[] nor "
        "start_s/end_s, so no source map can be recorded"
        % (plan.get("name"),))


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

    # method plans fail closed BEFORE any ffmpeg work: a trailer that cannot
    # say which episode it points at, or an ad with no offer link, is never
    # cut, gated or listed (SPEC C5; method 8.4 "distinct destination
    # records"). Ordinary clip plans are untouched by this loop.
    source_maps = [_method_record(p) for p in plans]

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
        for i, (plan, path) in enumerate(zip(plans, cut)):
            kind = plan_kind(plan)
            seconds = int(plan["clip_length_s"])
            target = out / clip_file_name(seconds, kind)
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
            row = {
                "kind": kind,
                "clip_length_s": seconds,
                "file": target.name,
                "duration_s": plan["duration_s"],
                "delivery_audio": "DELIVERY_AUDIO_OK",
            }
            if kind == "clip":
                row.update({"start_s": plan["start_s"],
                            "end_s": plan["end_s"],
                            "hooks": plan["hooks"],
                            "beats": plan["beats"]})
            else:
                # where this file sends the viewer, and the source map the
                # method records per piece (10.5): trailers -> episode/channel,
                # ads -> the offer.
                row["destination"] = plan["destination"]
                row["source_map"] = source_maps[i]
            rows.append(row)
    except Exception:
        # fail closed: any failure leaves NO clip file in the folder
        for plan in plans:
            for name in (plan["name"] + ".mp4",
                         clip_file_name(plan["clip_length_s"],
                                        plan_kind(plan))):
                stale = out / name
                if stale.exists():
                    stale.unlink()
        raise

    rows.sort(key=lambda r: (_KINDS[r["kind"]][0], r["clip_length_s"]))
    _write_docs(out, rows)
    return rows


def _method_record(plan):
    """Fail-closed pre-cut check of a trailer/ad plan; ``None`` for a clip."""
    kind = plan_kind(plan)
    if kind == "clip":
        return None
    if not plan.get("destination"):
        code = ("AD_NO_OFFER_DESTINATION" if kind == "ad"
                else "TRAILER_NO_DESTINATION")
        raise DeliveryClipsError("%s: plan %r carries no destination"
                                 % (code, plan.get("name")))
    return source_map(plan)


def _destination_text(destination):
    """A destination as the README prints it: a plain string, or JSON."""
    if isinstance(destination, str):
        return destination
    return json.dumps(destination, sort_keys=True)


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
    # a method run owes its trailer/ad files (named by this module and written
    # only once every cut passed); every other run owes the contract's two
    # clips. ponytail: the receipt rows ARE the promise -- deliver_clips writes
    # them as one merge after all cuts, so a partial set never reaches here.
    method_rows = [r for r in receipt.get("delivery_clips") or []
                   if r.get("kind") in ("trailer", "ad")]
    if method_rows:
        wanted = [(r["file"], r["kind"], r.get("clip_length_s"))
                  for r in method_rows]
        done = ("%d trailer/ad file(s) present, listed and AAC-LC 48 kHz "
                "faststart" % len(wanted))
    else:
        wanted = [(clip_file_name(s), "clip", s) for s in promised]
        done = "both clips present, listed and AAC-LC 48 kHz faststart"
    for name, kind, seconds in wanted:
        p = d / name
        if not p.is_file() or p.stat().st_size == 0:
            if kind != "clip":
                return (FAIL, "delivery missing the %d-second %s (%s)"
                        % (seconds, kind, name))
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
    return (PASS, done)


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
        if r["kind"] != "clip":
            # a trailer sends the viewer to the episode/channel, an ad to the
            # offer (method 8.4): the README says which, per file.
            lines.append("- `%s` - %d seconds - destination: %s"
                         % (r["file"], r["clip_length_s"],
                            _destination_text(r["destination"])))
            continue
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



def produce_delivery(run_dir, item):
    """DEL-13 packaging adapter: the REAL DEL-06 deliver path (60/90 clips).

    Reads the run's ``edit/timeline.json``, the rendered master
    (``edit/ad.mp4``) and the chosen ad length (card answer, else the brief),
    then calls ``deliver_clips`` -- the same entry the CLI runs: whole-line
    windows from ``clip_cutdown.plan_clips``, cut through
    ``clip_cutdown.run_clips``, every clip through the delivery audio gate
    and listed in the receipt and README. Fixture bytes are never written:
    ``contract.produce_item`` is test-only and no deliver path imports it.
    Signature: produce_delivery(run_dir, item) -> list[Path].
    """
    from delivery_package import run_inputs as RI
    out = RI.delivery_dir(run_dir)
    timeline = RI.load_json(run_dir, os.path.join("edit", "timeline.json"))
    length = RI.chosen_length_s(run_dir)
    master = RI.as_run(run_dir) / "edit" / "ad.mp4"
    deliver_clips(timeline, length, str(master), str(out))
    return RI.stage(item, out)


if __name__ == "__main__":
    sys.exit(main())
