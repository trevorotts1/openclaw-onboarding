#!/usr/bin/env python3
"""Method trailers (TRAILER_CLIP, SPEC C5) and the offer ad cuts (F19).

This module is inert for every run that has not carried ``method``:
``clip_cutdown.plan_clips`` only reaches in when the timeline carries one, so
a non-method timeline still gets today's hook-first window, byte for byte.

What it cuts (method 8.3, worked 60-second trailer in 9.2): a miniature
opening -> the ERM range with its first sung line -> pain -> Hero Shift ->
a partial breakthrough -> a hook excerpt only when a local breakthrough
precedes it -> an end card that says show, episode and where to watch.
The offer itself never rides the cut (``COMMERCIAL_CONTINUATION`` is not a
source range): a trailer sells the episode, an ad clip sells the offer.

Data read (nothing invented, nothing network)::

  timeline (blackceo.timeline/v1)          += "method"    the control/method.json block
                                                "blueprint" creative/blueprint.json (dict or path)
                                                "show"      {"name","episode","channel","destination"}
                                                "offer"     {"link","cta","name"}
                                                lines[] may carry "beat" (story_beat_id),
                                                  "state" and "flashback"/"setback"+"reason"
  blueprint (SPEC C1)                        story_beats[] / music_cues[]

Every source range is whole lines of the timeline (never mid-word, never
into the master's own end card), capped per role at the sizes method 9.2's
worked 60-second trailer uses. Records per §10.5: ``source_in/out`` and
``trailer_in/out`` for each piece, plus ``viewing_reason``,
``spoiler_boundary`` and ``destination``.

Fail closed by name: ``TRAILER_NO_VIEWING_REASON``, ``TRAILER_HOOK_UNEARNED``,
``TRAILER_NO_DESTINATION``, ``TRAILER_NO_WINDOW``,
``TRAILER_LENGTHS_IDENTICAL``, ``AD_NO_OFFER_DESTINATION``,
``AD_ARC_INCOMPLETE``, ``TRANSFORMATION_LOCK_BROKEN``.

stdlib only; the one ffmpeg render goes through ``load_governor`` (bounded,
heavy-slot gated); no network, no spend, no provider call.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import load_governor as _LG                                            # noqa: E402
import delivery_audio                                                  # noqa: E402
from master_length import master_max_s                                 # noqa: E402
from clip_cutdown import FADE_S, ClipCutdownError, clips_for           # noqa: E402
from delivery_variants.checks import CTA_HOLD_MIN_SECONDS              # noqa: E402
from delivery_variants.cover_image import (  # noqa: E402
    TITLE_SHRINK, has_filter, resolve_font,
)

TOOL_NAME = "trailer"
END_CARD = "end_card"

#: how long two source ranges overlap at a join (video and audio together).
CROSSFADE_S = 0.3
#: the ERM range opens shortly before the first sung line, so the drop lands in it.
ERM_LEAD_S = 4.0
#: longest source range each structural role keeps: method 9.2's worked
#: 60-second trailer (6 s setup, 12 s pain, 7 s hero, 10 s turn, 7 s hook).
ROLE_CAP_S = {"opening": 6.0, "erm": 10.0, "pain": 10.0, "hero": 7.0,
              "breakthrough": 10.0, "hook": 7.0}
EXTRA_CAP_S = 10.0          # a trailer-value-only range (context / complication)

#: cue id -> the structural range it opens (SPEC C1's cue list).
CUE_ROLE = {
    "BASELINE": "opening",
    "PAIN_BUILD": "pain",
    "PAIN_DEEPEN": "pain",
    "ERM_DROP": "erm",
    "HERO_SHIFT": "hero",
    "BREAKTHROUGH": "breakthrough",
    "SOLUTION_HOOK": "hook",
    "MEMORY_HOOK": "hook",
    "COMMERCIAL_CONTINUATION": "commercial",
    "RECAP": "commercial",
}
#: the offer/commercial range is never a source range of a derivative.
COMMERCIAL = "commercial"


class TrailerError(ClipCutdownError):
    """Every refusal here is a ClipCutdownError, so one except clause still holds."""


def _fail(code, detail=""):
    raise TrailerError(("%s: %s" % (code, detail)).rstrip(": "))


def _str(v):
    return v.strip() if isinstance(v, str) and v.strip() else ""


# ---------------------------------------------------------------- inputs ---
def blueprint_of(timeline, blueprint=None):
    """The Story Beat Blueprint: a dict, a path to one, or {} (never guessed)."""
    bp = blueprint if blueprint is not None else timeline.get("blueprint")
    if isinstance(bp, str):
        with open(bp, encoding="utf-8") as fh:
            bp = json.load(fh)
    return bp if isinstance(bp, dict) else {}


def purpose(timeline, blueprint=None):
    """The run's purpose; a method run that never recorded one reads campaign.

    ponytail: the card always writes ``purpose``, so the default only covers a
    hand-built fixture; a second purpose set (or a missing ``method`` block)
    never reaches here -- without ``method`` the caller does not call at all.
    """
    if not timeline.get("method"):
        return None
    for src in (blueprint_of(timeline, blueprint), timeline, timeline.get("method")):
        if isinstance(src, dict) and _str(src.get("purpose")):
            return _str(src["purpose"])
    return "campaign"


def _lines(timeline):
    """Whole source lines, never into the master's own end card (today's rule)."""
    ls = timeline.get("lines")
    if not isinstance(ls, list) or not ls:
        _fail("TRAILER_NO_LINES", "the timeline needs lines[] with start_s/end_s")
    cap = timeline.get("endcard_start_s")
    out = [l for l in ls if cap is None or l["end_s"] <= cap + 1e-6]
    if not out:
        _fail("TRAILER_NO_LINES", "every line sits after endcard_start_s")
    return sorted(out, key=lambda l: l["start_s"])


def _master_end(timeline, lines):
    """Where the master's music can still be taken from for the end card."""
    for key in ("duration_s", "total_s", "master_duration_s", "endcard_start_s"):
        v = timeline.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            return float(v)
    return max(l["end_s"] for l in lines)


def _show_fields(show, blueprint):
    """Show, episode, channel and the one watch destination (never the offer)."""
    d = show if isinstance(show, dict) else ({"channel": show} if _str(show) else {})
    bp = blueprint if isinstance(blueprint, dict) else {}

    def pick(*keys):
        for src in (d, bp):
            for k in keys:
                if _str(src.get(k)):
                    return _str(src[k])
        return ""

    return {"name": pick("name", "show", "series_name", "series"),
            "episode": pick("episode", "episode_title", "episode_id"),
            "channel": pick("channel", "channel_home"),
            "destination": (pick("destination", "watch_url", "url") or
                            pick("channel", "channel_home"))}


def _offer_fields(offer, blueprint):
    """The offer's own destination and call to action for an ad clip."""
    d = offer if isinstance(offer, dict) else ({"link": offer} if _str(offer) else {})
    bp = blueprint if isinstance(blueprint, dict) else {}
    ci = bp.get("commercial_intent") if isinstance(bp.get("commercial_intent"), dict) else {}

    def pick(*keys):
        for src in (d, ci):
            for k in keys:
                if _str(src.get(k)):
                    return _str(src[k])
        return ""

    link = pick("link", "url", "destination")
    if not link:
        _fail("AD_NO_OFFER_DESTINATION",
              "the ad clip sells the offer, so it needs the offer destination "
              "(timeline offer.link or blueprint commercial_intent.destination)")
    # ponytail: CTA copy comes from the offer record; "Learn more" is the one
    # neutral fallback, upgrade to the brief's own action wording when the card
    # starts writing offer.cta.
    return {"link": link, "cta": pick("cta", "action", "verb") or "Learn more",
            "name": pick("name", "label", "title") or pick("solution")}


def end_card_s():
    """The end-card hold: at least the acceptance profile's CTA hold, never under 3 s."""
    try:
        import timing_guard
        hold = float(timing_guard.load_profile()["cta"]["hold_seconds_min"])
    except Exception:                                   # profile unreadable -> shipped floor
        hold = CTA_HOLD_MIN_SECONDS
    return max(hold, 3.0, CTA_HOLD_MIN_SECONDS)


# ------------------------------------------------------------ candidates ---
def _roles(beat):
    out = []
    for cue in beat.get("music_cue_ids") or []:
        role = CUE_ROLE.get(str(cue).strip().upper())
        if role and role not in out:
            out.append(role)
    return out


def _beat_lines(lines, beat):
    """The beat's own lines (by id), else the lines inside its window."""
    hit = [l for l in lines if l.get("beat") == beat.get("story_beat_id")]
    if hit:
        return hit
    s, e = beat.get("start_s"), beat.get("end_s")
    if isinstance(s, (int, float)) and isinstance(e, (int, float)):
        return [l for l in lines if l["start_s"] < e and l["end_s"] > s]
    return []


def _state_of(beat, hit):
    """before / after / neutral, or None when the records say nothing."""
    for line in hit:
        v = _str(line.get("state")).lower()
        if v:
            return v.split()[0]
    v = _str(beat.get("character_state_before_after")).lower()
    if v and not v.startswith("{"):
        return v.split()[0]
    return None


def _continuity_tag(beat, hit):
    """A flashback/setback range may legitimately show the before-state (SPEC C4)."""
    for src in list(hit) + [beat]:
        for key in ("flashback", "setback"):
            if src.get(key) and _str(src.get("reason")):
                return {"tag": key, "reason": _str(src.get("reason"))}
    return None


def _cap(hit, cap):
    """Whole lines from the range start, as many as fit in ``cap`` seconds."""
    out = [hit[0]]
    for line in hit[1:]:
        if line["end_s"] - hit[0]["start_s"] > cap:
            break
        out.append(line)
    return out


def _first_sung_line(lines, blueprint):
    """Where the singing starts: a line flag, else the ERM cue's own start."""
    for line in lines:
        if line.get("first_sung") or line.get("sung"):
            return line
        if str(line.get("vocal_status") or "").lower() == "sung":
            return line
    for cue in blueprint.get("music_cues") or []:
        cid = str(cue.get("music_cue_id") or "").strip().upper()
        start = cue.get("start_s")
        if cid == "ERM_DROP" or str(cue.get("vocal_status") or "").lower() == "sung":
            if isinstance(start, (int, float)) and not isinstance(start, bool):
                for line in lines:
                    if line["start_s"] <= start < line["end_s"]:
                        return line
    return None


def _erm_window(lines, hit, anchor, cap):
    """The ERM range: whole lines carrying the first sung line, capped."""
    k = lines.index(anchor)
    j = k
    while j > 0 and lines[j - 1]["start_s"] >= anchor["start_s"] - ERM_LEAD_S:
        j -= 1
    win = [lines[j]]
    for line in lines[j + 1:]:
        if line["end_s"] - win[0]["start_s"] > cap:
            break
        win.append(line)
    # when the anchor is inside this beat's own lines, never open the range before it
    if hit[0]["start_s"] - 1e-6 <= anchor["start_s"] and anchor["end_s"] <= hit[-1]["end_s"] + 1e-6:
        clipped = [l for l in win if l["end_s"] > hit[0]["start_s"] + 1e-6]
        if any(l is anchor or l.get("line_id") == anchor.get("line_id") for l in clipped):
            win = clipped
    return win


def _candidates(lines, blueprint):
    """Every promotional range, story order; the excerpt is cut per length later."""
    out = []
    beats = blueprint.get("story_beats") or []
    ordered = sorted(beats, key=lambda b: b.get("start_s")
                     if isinstance(b.get("start_s"), (int, float)) else 0)
    anchor = _first_sung_line(lines, blueprint)
    for beat in ordered:
        raw = _roles(beat)
        roles = [r for r in raw if r != COMMERCIAL]
        tv = beat.get("trailer_value")
        if COMMERCIAL in raw and not roles:
            continue                      # the offer never rides a derivative cut
        if not roles and not _str(tv) and tv is not True:
            continue                      # nothing about this beat sells the edit
        hit = _beat_lines(lines, beat)
        if not hit:
            continue
        out.append({"beat": beat.get("story_beat_id"), "roles": roles or ["extra"],
                    "hit": hit, "anchor": anchor if "erm" in roles else None,
                    "state": _state_of(beat, hit), "continuity": _continuity_tag(beat, hit),
                    "reason": _str(tv) or _str(beat.get("viewer_understanding"))
                              or _str(beat.get("why_it_belongs"))})
    return out


def _pick(cand, budget, lines):
    """The whole-line excerpt of one range that this length can afford.

    The role caps come from method 9.2's worked 60-second trailer and grow
    with the budget, so the 90 s cut spends its extra time on more of the
    story (method 9.2: context, never repeated setup).
    """
    caps = [ROLE_CAP_S[r] for r in cand["roles"] if r in ROLE_CAP_S]
    cap = (min(caps) if caps else EXTRA_CAP_S) * budget / float(master_max_s(60))
    if "erm" in cand["roles"] and cand["anchor"] is not None:
        win = _erm_window(lines, cand["hit"], cand["anchor"], cap)
    else:
        win = _cap(cand["hit"], cap)
    return dict(cand, source_in=win[0]["start_s"], source_out=win[-1]["end_s"])


def _viewing_reason(candidates):
    for c in candidates:
        if c["reason"]:
            return c["reason"]
    _fail("TRAILER_NO_VIEWING_REASON",
          "no story beat says why this episode is worth watching "
          "(story_beats[].trailer_value / viewer_understanding)")


# ------------------------------------------------------------- assembling ---
def _dur(c):
    return c["source_out"] - c["source_in"]


def _total(chosen, ec_s):
    if not chosen:
        return ec_s
    seg = [_dur(c) for c in chosen]
    seg[-1] += ec_s
    return sum(seg) - CROSSFADE_S * (len(seg) - 1)


def _by_role(candidates):
    by = {}
    for c in candidates:
        for r in c["roles"]:
            by.setdefault(r, []).append(c)
    return by


def _assemble(candidates, budget, kind, ec_s, lines):
    """One derivative's source ranges in story order; raises when the arc is broken."""
    by = _by_role(candidates)

    def first(role):
        return _pick(by[role][0], budget, lines) if by.get(role) else None

    omitted, excluded = [], set()
    opening, erm = first("opening"), first("erm")
    for role, c in (("opening", opening), ("erm", erm)):
        if c is None:
            _fail("TRAILER_NO_WINDOW", "the blueprint has no %s range to open the cut with" % role)
    breakthrough = first("breakthrough")
    if kind == "ad" and breakthrough is None:
        _fail("AD_ARC_INCOMPLETE",
              "an ad clip is a complete sales arc; the blueprint has no breakthrough range")
    picked = [opening, erm]
    for role in ("hero", "breakthrough"):
        c = first(role)
        if c is not None:
            picked.append(c)
        else:
            omitted.append({"piece": role, "reason":
                            "the blueprint shows no help arriving" if role == "hero"
                            else "the blueprint shows no visible breakthrough"})
    hook = first("hook")
    if hook is None:
        excluded.add(id(by["hook"][0])) if by.get("hook") else None
        omitted.append({"piece": "hook", "reason": "the blueprint carries no solution hook"})
    elif breakthrough is None:
        excluded.add(id(by["hook"][0]))
        omitted.append({"piece": "hook", "reason":
                        "no breakthrough range precedes it (pain-led teaser)"})
    elif hook["source_in"] + 1e-6 < breakthrough["source_in"]:
        _fail("TRAILER_HOOK_UNEARNED",
              "the hook range opens at %.1fs, before its breakthrough at %.1fs"
              % (hook["source_in"], breakthrough["source_in"]))
    else:
        picked.append(hook)

    chosen = sorted({id(c): c for c in picked}.values(), key=lambda c: c["source_in"])
    core = _total(chosen, ec_s)
    if core > budget + 1e-6:
        _fail("TRAILER_NO_WINDOW",
              "the %s sequence needs %.1fs and a %gs cut allows %.1fs"
              % (kind, core, budget + 2, budget))
    # then the rest: pain refrains and trailer-worthy context, story order,
    # only what still fits -- the 90 s cut simply has more room than the 60 s one.
    held = {id(c) for c in chosen}
    for cand in candidates:
        if id(cand) in held or id(cand) in excluded:
            continue
        c = _pick(cand, budget, lines)
        trial = sorted(chosen + [c], key=lambda x: x["source_in"])
        if _total(trial, ec_s) <= budget + 1e-6:
            chosen = trial
            held.add(id(cand))
    return chosen, omitted


def transformation_lock(pieces):
    """SPEC C4: no present-time before-state after the breakthrough range.

    Returns ``OK`` when the records carry states, ``UNAVAILABLE`` when they
    carry none (a plan never claims a check it could not make), and raises
    ``TRANSFORMATION_LOCK_BROKEN`` for a real break a flashback/setback tag
    with a reason does not cover.
    """
    src = [p for p in pieces if p["piece"] != END_CARD]
    states = [p for p in src if p.get("state")]
    if not states:
        return "UNAVAILABLE"
    at = next((i for i, p in enumerate(src) if "breakthrough" in p["roles"]), None)
    if at is None:
        return "OK"
    for p in src[at + 1:]:
        if p.get("state") != "before":
            continue
        if p.get("continuity"):
            continue
        _fail("TRANSFORMATION_LOCK_BROKEN",
              "the %s range after the breakthrough (source %.1fs) still shows the "
              "before-state; tag it flashback/setback with a reason or re-cut it"
              % (p["piece"], p["source_in"]))
    return "OK"


def _inside_ranges(line, chosen):
    return any(c["source_in"] - 1e-6 <= line["start_s"] and line["end_s"] <= c["source_out"] + 1e-6
               for c in chosen)


def _record(kind, chosen, omitted, length_s, chosen_length_s, destination, ec_s,
            lines, view_reason, offer=None):
    """One plan dict: §10.5 records plus the keys delivery and ffmpeg both read."""
    pieces, t = [], 0.0
    for i, c in enumerate(chosen):
        d = _dur(c)
        pieces.append({"piece": c["roles"][0], "roles": list(c["roles"]), "beat": c["beat"],
                       "source_in": round(c["source_in"], 3), "source_out": round(c["source_out"], 3),
                       "trailer_in": round(t, 3), "trailer_out": round(t + d, 3),
                       "duration_s": round(d, 3), "state": c["state"],
                       **({"continuity": c["continuity"]} if c["continuity"] else {})})
        t = t + d if i == len(chosen) - 1 else t + d - CROSSFADE_S
    pieces.append({"piece": END_CARD, "roles": [END_CARD], "beat": None,
                   "source_in": None, "source_out": None,
                   "trailer_in": round(t, 3), "trailer_out": round(t + ec_s, 3),
                   "duration_s": round(ec_s, 3), "state": None})
    total = t + ec_s
    plan = {"kind": kind, "name": "%s-%ds" % (kind, length_s), "clip_length_s": length_s,
            "master_chosen_length_s": chosen_length_s,
            "duration_s": round(total, 3),
            "start_s": chosen[0]["source_in"], "end_s": chosen[-1]["source_out"],
            "hooks": sum(1 for l in lines if l.get("hook") and _inside_ranges(l, chosen)),
            "beats": len({c["beat"] for c in chosen}),
            "pieces": pieces, "omitted": omitted,
            "viewing_reason": view_reason,
            "spoiler_boundary": {
                "master_s": round(max(c["source_out"] for c in chosen), 3),
                "note": "the resolution and everything after this point in the "
                        "master are withheld from the cut"},
            "destination": destination,
            "end_card": {"kind": kind, "duration_s": round(ec_s, 3), "lines": []}}
    if offer:
        plan["offer"] = offer
    return plan


def end_card_lines(kind, fields):
    """What the end card says: watch the episode (trailer), take the action (ad)."""
    if kind == "ad":
        lines = [fields["cta"], fields["name"], fields["link"]]
    else:
        lines = [fields["name"], fields["episode"],
                 "Watch the full episode on %s" % (fields["channel"] or fields["destination"])]
    return [l for l in lines if _str(l)]


# ------------------------------------------------------------------ plan ---
def plan(kind, timeline, blueprint, chosen_length_s, show=None, offer=None):
    """Two derivative plans (60 s and 90 s) for one method campaign run.

    Returns [] when the chosen length owes no derivative at all (today's
    ``clips_for`` rule), so a 60/90 s master never gains a trailer.
    """
    if not clips_for(chosen_length_s):
        return []
    bp = blueprint_of(timeline, blueprint)
    lines = _lines(timeline)
    cands = _candidates(lines, bp)
    if not cands:
        _fail("TRAILER_NO_WINDOW", "the blueprint offers no promotional range to cut from")
    ec_s = end_card_s()
    fields, destination = None, ""
    if kind == "ad":
        fields = _offer_fields(offer if offer is not None else timeline.get("offer"), bp)
        destination = fields["link"]
    else:
        fields = _show_fields(show if show is not None else timeline.get("show"), bp)
        if not fields["destination"]:
            _fail("TRAILER_NO_DESTINATION",
                  "the trailer's destination is the episode/channel, never the "
                  "checkout: pass timeline.show with channel or destination")
        destination = fields["destination"]
    view_reason = _viewing_reason(cands) if kind == "trailer" else ""

    built = {}
    for length_s in clips_for(chosen_length_s):
        built[length_s] = _assemble(cands, master_max_s(length_s), kind, ec_s, lines)
    lengths = list(built)
    if len(lengths) > 1 and _same_ranges(*(built[l][0] for l in lengths)):
        # method 8.2: the 90 adds context or a complication, never repeated setup
        long_s = lengths[-1]
        for c in cands:
            if id(c) in {id(x) for x in built[long_s][0]}:
                continue
            trial = sorted(built[long_s][0] + [_pick(c, master_max_s(long_s), lines)],
                           key=lambda x: x["source_in"])
            if _total(trial, ec_s) <= master_max_s(long_s) + 1e-6:
                built[long_s] = (trial, built[long_s][1])
                break
        if _same_ranges(*(built[l][0] for l in lengths)):
            _fail("TRAILER_LENGTHS_IDENTICAL",
                  "the 60 s and 90 s %ss chose the same source ranges; the longer "
                  "cut must add a range, not repeat the short one" % kind)

    plans = []
    for length_s in lengths:
        chosen, omitted = built[length_s]
        plan_dict = _record(kind, chosen, omitted, length_s, chosen_length_s,
                            destination, ec_s, lines, view_reason,
                            offer=fields if kind == "ad" else None)
        plan_dict["transformation_lock"] = transformation_lock(plan_dict["pieces"])
        plan_dict["end_card"]["lines"] = end_card_lines(kind, fields)
        plan_dict["end_card"]["source_in"] = _card_source_in(
            plan_dict["pieces"][-2]["source_out"], ec_s, _master_end(timeline, lines))
        plans.append(plan_dict)
    return plans


def _card_source_in(last_source_out, ec_s, master_end):
    """The master's own music under the end card: right after the last range."""
    return round(max(0.0, min(last_source_out, master_end - ec_s)), 3)


def _same_ranges(a, b):
    return ({(c["source_in"], c["source_out"]) for c in a} ==
            {(c["source_in"], c["source_out"]) for c in b})


def plan_trailers(timeline, blueprint, chosen_length_s, show):
    """The 60 s and 90 s TRAILER_CLIP plans (method 8.3, SPEC C5)."""
    return plan("trailer", timeline, blueprint, chosen_length_s, show=show)


# ----------------------------------------------------------- ffmpeg argv ---
def _endcard_filters(text_file, font, hold_from, chars):
    """The end card: a dark band + the card text as DATA (textfile, no expansion).

    The cover-image pattern (delivery_variants/cover_image.py): the card's
    words travel as ``textfile=`` + ``expansion=none``, so a title containing
    ``:``, ``,`` or ``%{}`` is never parsed as filter syntax, and the font
    shrinks to the widest line (TITLE_SHRINK) so nothing runs off the frame.
    """
    box = ("drawbox=x=0:y=ih*0.55:w=iw:h=ih*0.45:color=black@0.60:t=fill"
           ":enable='gte(t,%.3f)'" % hold_from)
    # the comma inside min() must be escaped: this graph is one -filter_complex
    # string where a bare comma starts the next filter.
    size = "min(main_h*0.055\\,main_w*%.2f/%d)" % (TITLE_SHRINK, max(chars, 1))
    text = ("drawtext=fontfile=%s:textfile=%s:expansion=none:fontcolor=#ffffff"
            ":fontsize=%s:x=(main_w-text_w)/2:y=main_h*0.60:line_spacing=8"
            ":text_align=center:enable='gte(t,%.3f)'"
            % (font, text_file, size, hold_from))
    return ",".join([box, text])


def build_argv(master, plan_dict, out, text_file, ffmpeg="ffmpeg", fontfile=None):
    """One ffmpeg argv: whole-line ranges joined with 0.3 s crossfades + end card.

    DATA ONLY -- nothing is spawned here. The end card rides the last range
    (held frame) and the master's own music just after it, so the ending stays
    coherent (method 8.3 step 6) instead of cutting to silence.
    """
    src = [p for p in plan_dict["pieces"] if p["piece"] != END_CARD]
    card = plan_dict["end_card"]
    n = len(src)
    if n < 2:
        _fail("TRAILER_NO_WINDOW", "a derivative needs at least two source ranges")
    seg = [p["duration_s"] for p in src]
    seg[-1] = seg[-1] + card["duration_s"]
    font = resolve_font(fontfile)
    fc = ["[0:v]split=%d%s" % (n, "".join("[sv%d]" % i for i in range(n))),
          "[0:a]asplit=%d%s" % (n + 1, "".join("[sa%d]" % i for i in range(n + 1)))]
    for i, p in enumerate(src):
        vf = ("[sv%d]trim=start=%.3f:end=%.3f,setpts=PTS-STARTPTS"
              % (i, p["source_in"], p["source_out"]))
        af = ("[sa%d]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS"
              % (i, p["source_in"], p["source_out"]))
        if i == n - 1:
            vf += ",tpad=stop_mode=clone:stop_duration=%.3f" % card["duration_s"]
            vf += "," + _endcard_filters(text_file, font, p["duration_s"],
                                         max(len(x) for x in card["lines"]))
        fc.append(vf + "[vs%d]" % i)
        fc.append(af + "[as%d]" % i)
        if i == n - 1:
            ec_in = card.get("source_in", p["source_out"])
            fc.append("[sa%d]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS[sec]"
                      % (n, ec_in, ec_in + card["duration_s"]))
            fc.append("[as%d][sec]concat=n=2:v=0:a=1[ao%d]" % (i, i))
    v_prev, a_prev = "vs0", "as0"
    for k in range(1, n):
        offset = sum(seg[:k]) - CROSSFADE_S * k
        fc.append("[%s][vs%d]xfade=transition=fade:duration=%.3f:offset=%.3f[vx%d]"
                  % (v_prev, k, CROSSFADE_S, offset, k))
        a_k = "ao%d" % k if k == n - 1 else "as%d" % k
        fc.append("[%s][%s]acrossfade=d=%.3f[ax%d]" % (a_prev, a_k, CROSSFADE_S, k))
        v_prev, a_prev = "vx%d" % k, "ax%d" % k
    total = sum(seg) - CROSSFADE_S * (n - 1)
    fo = max(total - FADE_S, 0.0)
    fc.append("[%s]fade=t=out:st=%.3f:d=%.3f[vout]" % (v_prev, fo, FADE_S))
    fc.append("[%s]afade=t=out:st=%.3f:d=%.3f[aout]" % (a_prev, fo, FADE_S))
    return [ffmpeg, "-y", "-i", master, "-filter_complex", ";".join(fc),
            "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264",
            # xfade negotiates yuv444p, which no platform decodes; every other
            # delivered video in this skill is yuv420p (assembler, video_delivery).
            "-pix_fmt", "yuv420p",
            *delivery_audio.AUDIO_OUT_ARGS, *delivery_audio.FASTSTART_ARGS, out]


def _endcard_text(plan_dict):
    return "\n".join(plan_dict["end_card"]["lines"]) + "\n"


def render(master, plans, out_dir, runner=None, audio_gate=None, ffmpeg="ffmpeg",
           fontfile=None):
    """Cut every plan into ``out_dir`` through load_governor; returns the paths.

    runner is injectable (tests spend no frame); the end-card text file lives
    in a temp folder that is removed either way, so a delivery folder never
    holds anything but the delivered video (SPEC B3b).
    """
    os.makedirs(out_dir, exist_ok=True)
    if runner is None and not has_filter("drawtext", ffmpeg):
        _fail("TRAILER_DRAWTEXT_UNAVAILABLE",
              "this ffmpeg build has no drawtext, so the end card cannot carry "
              "its text; point --ffmpeg at a build with libfreetype")
    run = runner or (lambda argv, **kw: _LG.run_ffmpeg(argv, job="clip-cutdown", **kw))
    paths, tmp = [], tempfile.mkdtemp(prefix="dsaf-endcard-")
    try:
        for plan_dict in plans:
            text_file = os.path.join(tmp, plan_dict["name"] + ".txt")
            with open(text_file, "w", encoding="utf-8") as fh:
                fh.write(_endcard_text(plan_dict))
            path = os.path.join(out_dir, plan_dict["name"] + ".mp4")
            argv = build_argv(master, plan_dict, path, text_file, ffmpeg, fontfile)
            r = run(argv, capture_output=True, text=True)
            if getattr(r, "returncode", 0) != 0:
                why = (getattr(r, "stderr", "") or "").strip()[-300:]
                _fail("TRAILER_FFMPEG_FAILED: %s%s"
                      % (plan_dict["name"], ": " + why if why else ""))
            try:
                delivery_audio.require_delivery_audio(path, audio_gate)
            except delivery_audio.DeliveryAudioRefused as exc:
                if os.path.exists(path):
                    os.remove(path)
                _fail("CLIP_AUDIO_REFUSED: %s" % exc)
            paths.append(path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return paths
