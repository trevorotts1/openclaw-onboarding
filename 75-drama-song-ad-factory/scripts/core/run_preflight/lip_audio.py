#!/usr/bin/env python3
"""lip_audio.py - N-84: lip audio cut at set-up, one whole sentence per piece.

Section 3.3a is the binding rule and this file is its code. Given the song's
whole sung lines with times, it returns the pieces to cut at set-up:
  * a piece is one or more WHOLE sentences, first word's start to last word's
    end (a line boundary is never crossed);
  * same-singer lines whose gap is 1.0 second or less are joined;
  * a piece is 5 to 30 seconds; nothing is padded with silence or cut;
  * a sentence under 5 seconds joins its same-singer neighbour, or is taken
    with the song's own real audio around it up to 5 seconds;
  * only a passage over 30 seconds is split, and only at a breath or a line
    boundary, into a stitch group whose pieces are each 5 seconds or longer.

Refusals (fixed codes): LIPSYNC_CUTS_SENTENCE, LIPSYNC_AUDIO_TOO_SHORT,
LIPSYNC_AUDIO_TOO_LONG. Stdlib only.
"""
import argparse
import hashlib
import json
import sys

MIN_S = 5.0
MAX_S = 30.0
JOIN_GAP_S = 1.0
EPS = 1e-6


def _lines(lines):
    out = []
    for i, ln in enumerate(lines or []):
        try:
            start, end = float(ln["start"]), float(ln["end"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("line %d has no numeric start/end" % i)
        if end - start <= 0:
            raise ValueError("line %d ends before it starts" % i)
        out.append({"start": start, "end": end,
                    "singer": ln.get("singer") or "lead"})
    out.sort(key=lambda r: r["start"])
    return out


def _merge_small_gaps(lines):
    """Join same-singer consecutive lines whose gap is 1.0 s or less."""
    groups = []
    for ln in lines:
        if groups:
            cur = groups[-1]
            gap = ln["start"] - cur["end"]
            same = ln["singer"] == cur["singers"][-1]
            if same and gap <= JOIN_GAP_S + EPS:
                cur["end"] = ln["end"]
                cur["singers"].append(ln["singer"])
                cur["lines"].append(ln)
                continue
        groups.append({"start": ln["start"], "end": ln["end"],
                       "singers": [ln["singer"]], "lines": [ln],
                       "joined_for_floor": False, "real_audio_pad": False})
    return groups


def _floor_fix(groups):
    """Bring any group under 5 s up to the floor with its own singer's neighbour,
    then with the song's real audio around it; refuse only if that is impossible."""
    refusals = []
    i = 0
    while i < len(groups):
        g = groups[i]
        while g["end"] - g["start"] < MIN_S - EPS:
            prev = groups[i - 1] if i > 0 else None
            nxt = groups[i + 1] if i + 1 < len(groups) else None
            candidates = []
            if prev and prev["singers"][-1] == g["singers"][0]:
                candidates.append((g["start"] - prev["end"], "prev"))
            if nxt and nxt["singers"][0] == g["singers"][-1]:
                candidates.append((nxt["start"] - g["end"], "next"))
            if not candidates:
                break
            candidates.sort()
            _, which = candidates[0]
            if which == "prev":
                g["start"] = groups[i - 1]["start"]
                g["singers"] = groups[i - 1]["singers"] + g["singers"]
                g["lines"] = groups[i - 1]["lines"] + g["lines"]
                g["joined_for_floor"] = True
                del groups[i - 1]
                i -= 1
            else:
                g["end"] = groups[i + 1]["end"]
                g["singers"] = g["singers"] + groups[i + 1]["singers"]
                g["lines"] = g["lines"] + groups[i + 1]["lines"]
                g["joined_for_floor"] = True
                del groups[i + 1]
        if g["end"] - g["start"] < MIN_S - EPS:
            need = MIN_S - (g["end"] - g["start"])
            # take the song's own real audio around it, up to 5 s in all
            half = need / 2.0
            g["start"] = max(0.0, g["start"] - half)
            g["end"] = g["end"] + (MIN_S - (g["end"] - g["start"]))
            g["real_audio_pad"] = True
            if g["end"] - g["start"] < MIN_S - EPS:
                refusals.append({"code": "LIPSYNC_AUDIO_TOO_SHORT",
                                 "start": g["start"], "end": g["end"],
                                 "detail": "the song has under 5 seconds of real audio here"})
        i += 1
    return groups, refusals


def _split_long(group, breaths):
    """Split a group over 30 s at a line boundary or a breath; each piece >= 5 s."""
    pieces, cur_start, cur_end = [], group["start"], group["start"]
    part = 0
    for ln in group["lines"]:
        line_len = ln["end"] - ln["start"]
        if line_len > MAX_S + EPS:
            # one line longer than 30 s: only a breath inside it may split it
            inside = sorted(b for b in (breaths or [])
                            if ln["start"] + EPS < b < ln["end"] - EPS)
            if not inside:
                return None, {"code": "LIPSYNC_AUDIO_TOO_LONG",
                              "start": ln["start"], "end": ln["end"],
                              "detail": "a single line over 30 s with no breath to split at"}
            cuts = [ln["start"]] + inside + [ln["end"]]
            for a, b in zip(cuts, cuts[1:]):
                if b - a < MIN_S - EPS:
                    return None, {"code": "LIPSYNC_AUDIO_TOO_SHORT",
                                  "start": a, "end": b,
                                  "detail": "a breath splits off under 5 seconds"}
                pieces.append({"start": a, "end": b})
            part += 1
            continue
        if cur_end - cur_start + line_len > MAX_S + EPS and cur_end > cur_start:
            pieces.append({"start": cur_start, "end": cur_end})
            cur_start = ln["start"]
            part += 1
        cur_end = ln["end"]
    if cur_end > cur_start:
        pieces.append({"start": cur_start, "end": cur_end})
    for p in pieces:
        if p["end"] - p["start"] < MIN_S - EPS:
            return None, {"code": "LIPSYNC_AUDIO_TOO_SHORT",
                          "start": p["start"], "end": p["end"],
                          "detail": "a split piece is under 5 seconds"}
    return pieces, None


def cut_pieces(lines, breaths=None):
    """Return {'pieces': [...], 'refusals': [...]} for the song's sung lines."""
    try:
        rows = _lines(lines)
    except ValueError as exc:
        return {"pieces": [], "refusals": [{"code": "LIPSYNC_CUTS_SENTENCE",
                                             "detail": str(exc)}]}
    groups = _merge_small_gaps(rows)
    groups, refusals = _floor_fix(groups)
    pieces = []
    for group in groups:
        if group["end"] - group["start"] <= MAX_S + EPS:
            pieces.append({"start": group["start"], "end": group["end"],
                           "singers": sorted(set(group["singers"])),
                           "stitch_group": False,
                           "joined_for_floor": group["joined_for_floor"],
                           "real_audio_pad": group["real_audio_pad"]})
            continue
        parts, refusal = _split_long(group, breaths)
        if refusal:
            refusals.append(refusal)
            continue
        for i, p in enumerate(parts):
            pieces.append({"start": p["start"], "end": p["end"],
                           "singers": sorted(set(group["singers"])),
                           "stitch_group": True, "stitch_part": i,
                           "joined_for_floor": False, "real_audio_pad": False})
    for p in pieces:
        p["seconds"] = round(p["end"] - p["start"], 3)
        p["fingerprint"] = piece_fingerprint(p)
    return {"pieces": pieces, "refusals": refusals}


def piece_fingerprint(piece):
    """Identity fingerprint of a piece (its exact audio window). The cutter then
    records the cut file's content hash through run_lock.match_audio."""
    body = json.dumps({"start": round(piece["start"], 6),
                       "end": round(piece["end"], 6)},
                      sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


def selftest():
    proofs = []
    # Two same-singer lines with a one-second gap join into one piece.
    r = cut_pieces([{"start": 0.0, "end": 2.5, "singer": "lead"},
                    {"start": 3.5, "end": 6.0, "singer": "lead"}])
    proofs.append(("a 1.0 s same-singer gap joins one piece",
                   len(r["pieces"]) == 1 and abs(r["pieces"][0]["seconds"] - 6.0) < 1e-6))
    # A 2-second lone sentence is lifted to the 5-second floor with real audio.
    r = cut_pieces([{"start": 10.0, "end": 12.0, "singer": "lead"}])
    proofs.append(("a lone 2 s sentence is taken with its real audio to 5 s",
                   r["pieces"] and r["pieces"][0]["seconds"] >= 5.0 - 1e-6
                   and r["pieces"][0]["real_audio_pad"]))
    # A 40-second passage splits into a stitch group of whole lines >= 5 s each.
    lines = [{"start": 0, "end": 10, "singer": "lead"},
             {"start": 10, "end": 20, "singer": "lead"},
             {"start": 20, "end": 30, "singer": "lead"},
             {"start": 30, "end": 40, "singer": "lead"}]
    r = cut_pieces(lines)
    proofs.append(("a 40 s passage is stitched, no piece over 30 s",
                   len(r["pieces"]) >= 2
                   and all(p["seconds"] <= 30.0 + 1e-6 for p in r["pieces"])
                   and all(p["stitch_group"] for p in r["pieces"])))
    # A single 35-second line with no breath cannot be split: refuse, never cut.
    r = cut_pieces([{"start": 0, "end": 35, "singer": "lead"}])
    proofs.append(("a single 35 s line with no breath is refused, not cut",
                   [x["code"] for x in r["refusals"]] == ["LIPSYNC_AUDIO_TOO_LONG"]))
    for name, ok in proofs:
        print(("ok   " if ok else "FAIL ") + name)
    return 0 if all(ok for _, ok in proofs) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lines", required=True, help="JSON file of [{start,end,singer}]")
    ap.add_argument("--breaths", default=None, help="JSON file of breath times in seconds")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    with open(args.lines, encoding="utf-8") as fh:
        lines = json.load(fh)
    breaths = None
    if args.breaths:
        with open(args.breaths, encoding="utf-8") as fh:
            breaths = json.load(fh)
    out = cut_pieces(lines, breaths)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if not out["refusals"] else 4


if __name__ == "__main__":
    sys.exit(main())
