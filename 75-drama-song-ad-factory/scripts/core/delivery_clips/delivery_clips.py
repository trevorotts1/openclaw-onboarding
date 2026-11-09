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

What the run OWES is derived once, by ``run_inputs.delivery_context`` from the
run's own saved answers (never from the folder, the brief or the receipt):
the packaging adapter plans against it and ``check_clips(run_dir=...)`` looks
for exactly that set. The planned (kind, seconds, file name) set must equal it
(``CLIPS_OBLIGATION_MISMATCH``) -- a method run that is not a campaign still
ships the contract's Clip names, and a campaign can never satisfy its trailers
with clip names. A 60/90 second ad owes nothing and stages nothing.

stdlib only; shells to ffmpeg/ffprobe through the gate.
"""
from __future__ import annotations

import argparse
import json
import math
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


def _finite_coordinate(value):
    """True for a real, finite coordinate: no bool, no NaN, no +/-infinity.

    ``bool`` is an ``int`` subclass, so it is refused before the numeric test;
    ``math.isfinite`` is what keeps NaN and both infinities out of every
    boundary the checker compares. A value too large to convert is refused
    rather than raised.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (TypeError, OverflowError):
        return False


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


def _coordinate_problem(piece):
    """Why this piece's four coordinates are unusable, or ``None``.

    Every coordinate is a real finite number -- a bool, a string, NaN or
    either infinity is a malformed record, not a window. Coordinates are
    nonnegative, and a range opens only when its end is strictly after its
    start: a reversed or zero-width range names nothing to cut. The end card
    is the one piece with no source range: both source keys are explicitly
    null while its trailer window stays measured.

    ponytail: no upper bound is claimed -- the authoritative clip length is
    not available at this boundary, so the window only has to be finite,
    nonnegative and increasing.
    """
    for key in ("trailer_in", "trailer_out"):
        if not _finite_coordinate(piece.get(key)):
            return "%s is not a finite number (%r)" % (key, piece.get(key))
    for key in ("trailer_in", "trailer_out"):
        if piece[key] < 0:
            return "%s is negative (%r)" % (key, piece[key])
    if piece["trailer_out"] <= piece["trailer_in"]:
        return ("the trailer window is empty or reversed (%r -> %r)"
                % (piece["trailer_in"], piece["trailer_out"]))
    start, end = piece.get("source_in"), piece.get("source_out")
    if start is None and end is None:
        return None                     # the end card holds no source range
    if start is None or end is None:
        return "the source window is half-empty"
    if not (_finite_coordinate(start) and _finite_coordinate(end)):
        return "the source window is not finite (%r -> %r)" % (start, end)
    for key, value in (("source_in", start), ("source_out", end)):
        if value < 0:
            return "%s is negative (%r)" % (key, value)
    if end <= start:
        return ("the source window is empty or reversed (%r -> %r)"
                % (start, end))
    return None


def _require_valid_piece(piece, name):
    """Fail closed before a malformed window is recorded, cut or listed."""
    why = _coordinate_problem(piece)
    if why:
        raise DeliveryClipsError(
            "TRAILER_SOURCE_MAP_INVALID: %r piece %r %s"
            % (name, piece.get("piece"), why))


def source_map(plan):
    """The receipt's ``source_map`` for a trailer/ad plan, fail closed.

    Method ``10.5`` records ``{source_in, source_out, trailer_in,
    trailer_out}`` per piece: the pieces the plan joined, or -- when the plan
    carries one whole window instead -- that window as one piece. Every piece
    must carry all four keys, and at least one piece must name a real source
    window; an explicit null source range is allowed only for the end card,
    never for the whole map.
    """
    pieces = plan.get("pieces")
    if isinstance(pieces, list) and pieces:
        out = []
        for piece in pieces:
            missing = [key for key in _PIECE_KEYS if key not in piece]
            if missing:
                raise DeliveryClipsError(
                    "TRAILER_SOURCE_MAP_INCOMPLETE: %r piece %r lacks %s"
                    % (plan.get("name"), piece.get("piece"),
                       ", ".join(missing)))
            _require_valid_piece(piece, plan.get("name"))
            out.append({key: piece[key] for key in _PIECE_KEYS})
        _require_source_window(out, plan.get("name"))
        return out
    if plan.get("start_s") is not None and plan.get("end_s") is not None:
        piece = {"source_in": plan["start_s"], "source_out": plan["end_s"],
                 "trailer_in": plan.get("trailer_in", 0.0),
                 "trailer_out": plan.get(
                     "trailer_out", plan.get("duration_s"))}
        _require_valid_piece(piece, plan.get("name"))
        _require_source_window([piece], plan.get("name"))
        return [piece]
    raise DeliveryClipsError(
        "TRAILER_NO_SOURCE_MAP: %r carries neither pieces[] nor "
        "start_s/end_s, so no source map can be recorded"
        % (plan.get("name"),))


def _real_source_window(piece):
    """True when this piece names a real finite, nonnegative source range."""
    start, end = piece.get("source_in"), piece.get("source_out")
    if not (_finite_coordinate(start) and _finite_coordinate(end)):
        return False
    return start >= 0 and end > start


def _require_source_window(pieces, name):
    """A source map needs source provenance; an end card alone is not one."""
    if not any(_real_source_window(piece) for piece in pieces):
        raise DeliveryClipsError(
            "TRAILER_NO_SOURCE_WINDOW: %r records no piece with a real source "
            "window (an all-null end card is not a source map)" % (name,))


def deliver_clips(timeline, chosen_length_s, master, delivery_dir,
                  runner=None, audio_gate=None, expected=None):
    """Cut the two clips into ``delivery_dir`` and list them in receipt + README.

    Returns the receipt rows (one per cut file). Fail closed: no window, an
    ffmpeg failure or a refused clip raises ``clip_cutdown.ClipCutdownError``
    with the folder left empty of partial clips; an unknown length or a
    delivered file that does not pass ``delivery_audio.check_delivery_audio()``
    after the rename raises ``DeliveryClipsError``.

    expected: the run's resolved derivative obligations, ``(file name, kind,
    seconds)`` from ``run_inputs.delivery_context``. When it is given the
    planned set must equal it exactly, before anything is cut.
    """
    out = Path(delivery_dir)
    out.mkdir(parents=True, exist_ok=True)
    plans = plan_clips(timeline, chosen_length_s)
    if expected is not None:
        _require_planned_obligations(plans, expected)
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


def _planned_derivatives(plans):
    """(delivery file name, kind, seconds) for every plan, in plan order."""
    out = []
    for plan in plans:
        kind = plan_kind(plan)
        seconds = int(plan["clip_length_s"])
        out.append((clip_file_name(seconds, kind), kind, seconds))
    return out


def _require_planned_obligations(plans, expected):
    """The planner must plan exactly the files the run owes -- no more, less."""
    planned = _planned_derivatives(plans)
    if sorted(planned) != sorted(expected):
        raise DeliveryClipsError(
            "CLIPS_OBLIGATION_MISMATCH: the run owes %s, the planner produced %s"
            % (sorted(expected), sorted(planned)))


def _owed_derivatives(ctx):
    """The derivative files this run's own resolved context owes (items 6/13)."""
    out = []
    for item in ctx["items"]:
        if item.key == "clips":
            kind = "trailer" if ctx["campaign"] else "clip"
        elif item.key == "ad_clips":
            kind = "ad"
        else:
            continue
        for seconds, name in zip((60, 90), item.files):
            out.append((name, kind, seconds))
    return out


def _timeline_campaign(timeline):
    """Whether ``clip_cutdown``'s planner will plan campaign derivatives here."""
    if not timeline.get("method"):
        return False
    from clip_cutdown import trailer as _trailer       # noqa: PLC0415
    return _trailer.purpose(timeline) == "campaign"


def _structural_wanted(rows, promised):
    """Structural fallback when the caller named no run.

    ponytail: without the run, the receipt's own naming family is the only
    evidence of which names to look for; a method family is still required in
    full (both trailers and/or both ad clips), so a partial receipt can never
    shrink the obligation. Pass ``run_dir`` for the authoritative set.
    """
    kinds = {r.get("kind") for r in rows}
    wanted = []
    if "trailer" in kinds:
        wanted += [(clip_file_name(s, "trailer"), "trailer", s) for s in promised]
    if "ad" in kinds:
        wanted += [(clip_file_name(s, "ad"), "ad", s) for s in promised]
    if wanted:
        return wanted
    return [(clip_file_name(s), "clip", s) for s in promised]


def _destination_problem(destination):
    """Where the trailer/ad sends the viewer must be recorded, not blank."""
    if isinstance(destination, str) and destination.strip():
        return None
    if isinstance(destination, dict) and destination:
        return None
    return "records no destination"


def _source_map_problem(source_map):
    """A method row's source map must carry usable windows, not a truthy blob.

    Every piece must carry BOTH source keys (an absent key is not an end
    card), sits somewhere on the finished cut (``trailer_in``/
    ``trailer_out``), and every piece that comes from the master names a real
    source window. The end card is the one piece with no source range: it holds
    the master's own music, so its ``source_in``/``source_out`` are explicitly
    null while its trailer window stays measured. A map whose every piece is
    such a null end card has no source provenance and is refused.
    """
    if not isinstance(source_map, list) or not source_map:
        return "records no source map"
    has_source = False
    for piece in source_map:
        if not isinstance(piece, dict):
            return "records a source map piece that is not an object"
        for key in ("source_in", "source_out"):
            if key not in piece:
                return "records a source map piece with no %s key" % key
        # every boundary is checked finite BEFORE any comparison: NaN and
        # both infinities compare false against themselves, so a bare
        # ``end <= start`` would wave them through.
        for key in ("trailer_in", "trailer_out"):
            value = piece.get(key)
            if not _finite_coordinate(value):
                return "records a source map piece with no numeric %s" % key
        for key in ("trailer_in", "trailer_out"):
            if piece[key] < 0:
                return "records a source map piece with a negative %s" % key
        if piece["trailer_out"] <= piece["trailer_in"]:
            return "records a source map piece with an empty trailer window"
        start, end = piece["source_in"], piece["source_out"]
        if start is None and end is None:
            continue                    # the end card holds no source range
        if start is None or end is None:
            return "records a source map piece with a half-empty source window"
        for key, value in (("source_in", start), ("source_out", end)):
            if not _finite_coordinate(value):
                return ("records a source map piece with no numeric %s" % key)
        for key, value in (("source_in", start), ("source_out", end)):
            if value < 0:
                return "records a source map piece with a negative %s" % key
        if end <= start:
            return "records a source map piece with an empty source window"
        has_source = True
    if not has_source:
        return "records no source window (every piece is an end card)"
    return None


def _method_row_problem(row):
    """A trailer/ad receipt row must say where it points and where it came from."""
    return (_destination_problem(row.get("destination")) or
            _source_map_problem(row.get("source_map")))


def _delivered_problem(d, name, kind, seconds, rows, readme, ffprobe, ffmpeg):
    """None when this owed file is present, listed, mapped and passes the gate."""
    path = d / name
    if not path.is_file() or path.stat().st_size == 0:
        return (FAIL, "delivery missing the %d-second %s (%s)"
                % (seconds, kind, name))
    row = next((r for r in rows if r.get("file") == name), None)
    if row is None:
        return (FAIL, "%s not listed in %s" % (name, RECEIPT_NAME))
    if row.get("kind") != kind or row.get("clip_length_s") != seconds:
        return (FAIL, "%s is listed as %r/%rs; the run owes %s/%ds"
                % (name, row.get("kind"), row.get("clip_length_s"),
                   kind, seconds))
    if kind != "clip":
        why = _method_row_problem(row)
        if why:
            return (FAIL, "%s %s" % (name, why))
    if name not in readme:
        return (FAIL, "%s not listed in %s" % (name, README_NAME))
    try:
        g = delivery_audio.check_delivery_audio(path, ffprobe, ffmpeg)
    except Exception as exc:      # noqa: BLE001 - a broken gate is UNAVAILABLE
        return (UNAVAILABLE, "audio gate could not read %s: %s" % (name, exc))
    if not g["ok"]:
        if g["reason_code"] in (delivery_audio.UNREADABLE,):
            return (UNAVAILABLE, "UNAVAILABLE: %s: %s" % (name, g["reason"]))
        return (FAIL, "%s failed the delivery audio gate (%s): %s"
                % (name, g["reason_code"], g["reason"]))
    return None


def check_clips(delivery_dir, chosen_length_s=None, ffprobe="ffprobe",
                ffmpeg="ffmpeg", *, run_dir=None, require_authority=False):
    """QC: (PASS|FAIL|UNAVAILABLE, detail). Fail closed on anything missing.

    With ``run_dir`` the expected set comes from that run's own saved context
    (``run_inputs.delivery_context``); the receipt row is evidence of each
    expected file, never the source of the expected set. Without it the check
    is structural (see ``_structural_wanted``) and a method family is still
    required in full -- but structural inspection is never authoritative: a
    caller that needs a production verdict sets ``require_authority`` and is
    refused outright when it supplies no run.
    """
    d = Path(delivery_dir)
    if run_dir is None and require_authority:
        return (FAIL, "CLIPS_NO_RUN_AUTHORITY: no run context supplied; a "
                      "folder inspection alone cannot grant a production PASS")
    wanted = None
    if run_dir is not None:
        from delivery_package import run_inputs as RI       # noqa: PLC0415
        try:
            ctx = RI.delivery_context(run_dir)
        except RI.RunInputError as exc:
            return (FAIL, "CLIPS_RUN_AUTHORITY_UNVERIFIED: %s" % exc)
        chosen_length_s = ctx["chosen_length_s"]
        wanted = _owed_derivatives(ctx)
        if not wanted:
            return (PASS, "%ss ad owes no clips" % chosen_length_s)
    else:
        promised = clips_for(chosen_length_s)
        if not promised:
            return (PASS, "%ss ad owes no clips" % chosen_length_s)
    try:
        receipt = json.loads((d / RECEIPT_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (FAIL, "%s missing or unreadable; cannot list the clips"
                % RECEIPT_NAME)
    rows = [r for r in receipt.get("delivery_clips") or []
            if isinstance(r, dict)]
    readme = (d / README_NAME).read_text(encoding="utf-8") \
        if (d / README_NAME).is_file() else ""
    structural = wanted is None
    if wanted is None:
        wanted = _structural_wanted(rows, promised)
    method = any(kind != "clip" for _name, kind, _seconds in wanted)
    done = ("%d trailer/ad file(s) present, listed and AAC-LC 48 kHz faststart"
            % len(wanted) if method
            else "both clips present, listed and AAC-LC 48 kHz faststart")
    if structural and method:
        done = "structural inspection only (no run authority): " + done
    for name, kind, seconds in wanted:
        problem = _delivered_problem(d, name, kind, seconds, rows, readme,
                                     ffprobe, ffmpeg)
        if problem is not None:
            return problem
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
    ap.add_argument("timeline", nargs="?",
                    help="the run's edit/timeline.json (required to cut)")
    ap.add_argument("--length", type=int,
                    help="chosen ad length in seconds (required to cut)")
    ap.add_argument("--master",
                    help="rendered master mp4 (required to cut)")
    ap.add_argument("--delivery", required=True, help="the delivery folder")
    ap.add_argument("--run",
                    help="the run folder whose own saved answers own the "
                         "obligations (required with --check)")
    ap.add_argument("--check", action="store_true",
                    help="check only; requires --run (exit 5 on a FAIL)")
    ns = ap.parse_args(argv)
    if ns.check:
        if not ns.run:
            ap.error("--check requires --run RUN: a context-free folder "
                     "inspection cannot grant a production PASS")
        verdict, detail = check_clips(ns.delivery, run_dir=ns.run,
                                      require_authority=True)
        print(json.dumps({"check": TOOL_NAME, "verdict": verdict,
                          "detail": detail}, indent=2))
        return 0 if verdict == PASS else 5
    if ns.length is None or not ns.timeline or not ns.master:
        ap.error("cutting clips needs TIMELINE, --length and --master")
    with open(ns.timeline, encoding="utf-8") as fh:
        timeline = json.load(fh)
    expected = None
    if ns.run:
        from delivery_package import run_inputs as RI       # noqa: PLC0415
        ctx = RI.delivery_context(ns.run)
        if ctx["chosen_length_s"] != ns.length:
            ap.error("--length %d disagrees with the run's own saved %d"
                     % (ns.length, ctx["chosen_length_s"]))
        expected = _owed_derivatives(ctx)
    rows = deliver_clips(timeline, ns.length, ns.master, ns.delivery,
                         expected=expected)
    print(json.dumps(rows, indent=2))
    return 0



def produce_delivery(run_dir, item):
    """DEL-13 packaging adapter: the REAL DEL-06 deliver path (60/90 clips).

    Reads the run's ``edit/timeline.json``, the rendered master
    (``edit/ad.mp4``) and the length/purpose the client's own confirmed
    answers recorded (``run_inputs.delivery_context``, never the brief), then
    calls ``deliver_clips`` -- the same entry the CLI runs: whole-line windows
    from ``clip_cutdown.plan_clips``, cut through ``clip_cutdown.run_clips``,
    every clip through the delivery audio gate and listed in the receipt and
    README. The timeline must plan the same purpose the saved context records,
    and the planned set must equal the owed files exactly. Fixture bytes are
    never written: ``contract.produce_item`` is test-only and no deliver path
    imports it. Signature: produce_delivery(run_dir, item) -> list[Path].
    """
    from delivery_package import run_inputs as RI
    ctx = RI.delivery_context(run_dir)
    timeline = RI.load_json(run_dir, os.path.join("edit", "timeline.json"))
    planned_campaign = _timeline_campaign(timeline)
    if planned_campaign != ctx["campaign"]:
        raise DeliveryClipsError(
            "CLIPS_PURPOSE_MISMATCH: the saved run is %s, the timeline plans %s"
            % ("a campaign" if ctx["campaign"] else "not a campaign",
               "campaign derivatives" if planned_campaign else "ordinary clips"))
    out = RI.delivery_dir(run_dir)
    master = RI.as_run(run_dir) / "edit" / "ad.mp4"
    deliver_clips(timeline, ctx["chosen_length_s"], str(master), str(out),
                  expected=_owed_derivatives(ctx))
    return RI.stage(item, out)


if __name__ == "__main__":
    sys.exit(main())
