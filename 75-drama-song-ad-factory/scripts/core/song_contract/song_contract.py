#!/usr/bin/env python3
"""song_contract: each music style's own definition, enforced (FU-RNBFLOW-SONG).

The failure this prevents (the One-Check Chanel 150 s R&B Flow ad, v1 and
v2, Trevor 4 out of 10): the lyric sheet had ZERO sung lyrics outside a
4-word hook ("Girl, I got you-u") repeated 6 times with "slow long held
notes"; all 66 storyboard dialogue lines (254 words) were tagged rap with
no rap delivery cue, so Suno talked them over the beat. Measured on the
vocal stem: 24.9% of voice sung against the 77.5% target. Skill 75's own
150 s plan calls for about 116 sung words (2 verses, 2 pre-choruses, 2
choruses, a bridge); the sheet kept only the hook. The sheet checks were
rap-blind and the share checks were waived for "all storyboard lines word
for word" (Option A). v2 doubled the hook line, still had no sung verse,
and Suno returned 9 hook blocks for the sheet's 6.

Two checks, one rule set, read from the styles' OWN records
(core/music_styles STYLES, the length plan core/length_formula, the rates
core/words_fit, the band core/spoken_share):

  check_sheet          the sheet, before any spend (suno_recipe.guard_request
                       and song_dispatch.validate_request call it);
  check_returned_song  the returned take, before any picture or video spend
                       (song_dispatch.judge_take runs it as gate
                       "song_contract"), from Suno's aligned words (which
                       carry the section headers) and the singing detector.

Hook COUNT and PLACEMENT belong to core/sung_hook/hook_placement
(FU-HOOK-PLACEMENT). This module only owns sung / rap / spoken content.
While hook_placement is not installed (it lands in its own PR), a thin
fallback here keeps the length's hook count (sung_hook.hook_count of the
delivered seconds) so the count is never unchecked.

Rules per style, derived from its definition:
  * every chorus (Hook/Chorus block) carries the hook AND at least one
    other line of real words: the hook itself may be one short line (I8,
    4-10 words), the chorus is never the hook repeated alone;
  * the sung sections the length plan calls for are present: pre-choruses
    and bridges for every style, plus the verses for a style whose verses
    are sung (Soul Ballad, Soul Rise). R&B Flow's verses are rap
    ("Rap verses with a smooth sung R&B hook");
  * planned sung share of voice on Trevor's band against the STYLE's own
    sung target, as a FLOOR (more singing is never a fault, so a Soul sheet
    may be almost all sung): Soul Ballad and Soul Rise 77.5%; R&B Flow the
    sung share its own length plan holds once its rap budget is carved out
    (length_formula.plan(style_id=...), at the style's words_fit rates);
  * rap blocks (only in a style whose deliveries include rap) carry a
    delivery cue that says rhythmic rap on (or over) the beat, and never
    spoken / talk / speech / conversational;
  * an upbeat style (its own tempo starts at 80 bpm or more) never asks for
    "slow" delivery in a sung tag or the style text;
  * a spoken Outro says "no melody", so the closing lines are never sung on
    the hook melody (Trevor: the hook has to be placed correctly).
The spoken voiceover version (velvet_voiceover, Google voices over the
song) is the one spoken-dialogue style: it is EXEMPT here.

Rap versus spoken on the AUDIO is UNMEASURED: the singing detector reads
sung versus not sung only, and no speech-to-text is used. stdlib only; no
network, no spend.
"""
from __future__ import annotations

import os
import re
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import length_formula as _LF   # noqa: E402
import music_styles as _MS     # noqa: E402
import spoken_share as _SS     # noqa: E402
import sung_hook as _SH        # noqa: E402
import words_fit as _WF        # noqa: E402
import suno_recipe as _RP     # noqa: E402
#: the module itself whether core/suno_recipe/ is a package or on sys.path
_R = getattr(_RP, "suno_recipe", _RP)
try:   # FU-HOOK-PLACEMENT owns hook count and placement once it is installed
    from sung_hook import hook_placement as _HP   # noqa: E402
except ImportError:
    _HP = None

TOOL_NAME = "song_contract"
TOOL_VERSION = "1.1.0"

MIN_CHORUS_LINES = 2          # the hook line plus at least one other real line
MIN_REAL_WORDS_PER_LINE = 2
UPBEAT_BPM_MIN = 80
RAP_AUDIO_UNMEASURED = ("UNMEASURED: rap versus spoken delivery on the audio -- the "
                        "singing detector reads sung versus not sung only, and no "
                        "speech-to-text is used")

_VOCABLE_RE = re.compile(r"^(?:o|oh|ah|aw|uh|huh|la|na|da|ba|m|hm|ye|yeah|yea|wo|woah|"
                         r"whoa|hey|ay|ey|sha)+$")
_SLOW_RE = re.compile(r"\bslow\b", re.I)
_RAP_NEED = (re.compile(r"\brhythmic\b", re.I), re.compile(r"\b(?:on|over) the beat\b", re.I))
#: a character may be "the narrator"; the delivery words below are what a cue may not ask for
_RAP_BAN = re.compile(r"\b(spoken|speak\w*|talk\w*|speech|conversational)\b", re.I)
_NO_MELODY_RE = re.compile(r"\bno melody\b", re.I)
_HEADER_RE = re.compile(r"\[[^\]]*\]")
_BPM_RE = re.compile(r"(\d+)(?:\s*-\s*\d+)?\s*bpm", re.I)
NON_HOOK_SUNG_KINDS = ("verse", "pre", "bridge", "product", "other")


def _sid(style_id):
    return _MS.style(style_id)["style_id"]


def _real_words(line):
    return [w for w in _SH.words(line) if not _VOCABLE_RE.match(w)]


def _kind(tag):
    """Section kind from a tag: pre / hook / vocalise / bridge / verse /
    intro / outro / product / other. Pre-chorus is read before chorus."""
    t = re.sub(r"[^a-z0-9]+", " ", str(tag).lower())
    if re.search(r"\bpre ?(chorus|hook)\b|\bprechorus\b|\bbuild\b", t):
        return "pre"
    for kind, pat in (("hook", r"\b(hook|chorus)\b"), ("vocalise", r"\bvocali[sz]e\b"),
                      ("bridge", r"\bbridge\b"), ("verse", r"\bverse\b"),
                      ("intro", r"\bintro\b"), ("outro", r"\boutro\b"),
                      ("product", r"\bproduct\b")):
        if re.search(pat, t):
            return kind
    return "other"


def parse_sections(text):
    """Raw sheet (or Suno's returned lyric text) -> sections WITH their cue.

    suno_recipe.parse_lyrics drops the cue after the colon; the cue is where
    "slow long held notes" and the rap delivery live, so this keeps it. The
    delivery is read by THE tag grammar (suno_recipe.parse_tag / the named
    dialect). [{"tag", "cue", "delivery" (sung|spoken|rap|None), "kind",
    "lines"}]; [Instrumental ...] and [End] carry delivery None.
    """
    out, cur = [], None
    for ln in str(text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        m = _R._BRACKET_RE.match(s)
        if m:
            inner = m.group(1).strip()
            named = _R._NAMED_TAG_RE.match(inner)
            if named:
                tag, d = named.group(1).strip(), named.group(2).lower()
                cue = inner.split(":", 1)[1].strip() if ":" in inner else ""
            else:
                tag, d, cue = inner, _R.parse_tag(inner), inner
            if d not in _R.DELIVERIES or tag.lower() == "end":
                d = None
            cur = {"tag": tag, "cue": cue, "delivery": d, "kind": _kind(tag), "lines": []}
            out.append(cur)
            continue
        if cur is not None:
            cur["lines"].append(s)
    return out


def _rates(sid):
    """The style's measured rates (words_fit). Keyed by id on one tree and by
    label on the other; both are read, the calm defaults otherwise."""
    rates = getattr(_WF, "STYLE_RATES", {})
    return dict(rates.get(sid) or rates.get(_MS.style(sid)["label"]) or _WF.DEFAULT_RATES)


def _is_rap_style(sid):
    return "rap" in _MS.style(sid)["deliveries"]


def _is_upbeat(sid):
    m = _BPM_RE.search(_MS.style(sid)["suno_style_prompt"])
    return bool(m) and int(m.group(1)) >= UPBEAT_BPM_MIN


def _hook_blocks(sections):
    """(hook blocks, hook line keys): sung sections tagged Hook/Chorus; with
    no such tag, the most repeated sung text (the recipe's own reading)."""
    sung = [s for s in sections if s["delivery"] == "sung" and s["kind"] != "vocalise"]
    blocks = [s for s in sung if s["kind"] == "hook"]
    if not blocks:
        keys = [tuple(_SH.words(" ".join(s["lines"]))) for s in sung]
        rep = [k for k in set(keys) if k and keys.count(k) >= 2]
        if rep:
            best = max(rep, key=keys.count)
            blocks = [s for s, k in zip(sung, keys) if k == best]
    lines = {tuple(_SH.words(ln)) for s in blocks for ln in s["lines"]}
    return blocks, {k for k in lines if k}


def required_sung_sections(style_id, delivered_s):
    """The sung non-hook sections the length plan calls for, per style."""
    sid = _sid(style_id)
    p = _LF.plan(delivered_s + _LF.END_EARLY_S)["sections"]
    need = {"pre_chorus": p["pre_chorus"], "bridge": p["bridge"]}
    if not _is_rap_style(sid):
        need["verses"] = p["verses"]
    return need


def _real_lines(block):
    """Distinct lines of real words (2+ non-vocable words) in one block."""
    return {tuple(_SH.words(ln)) for ln in block["lines"]
            if len(_real_words(ln)) >= MIN_REAL_WORDS_PER_LINE}


def _hook_count_owner():
    return ("sung_hook.hook_placement" if _HP is not None
            else "song_contract fallback: sung_hook.hook_count(delivered_s)")


def sung_target(style_id, delivered_s):
    """The style's own sung-of-voice target, judged as a FLOOR. A rap style
    (R&B Flow) takes the sung share its own length plan holds (the plan
    carves the rap budget out of the spoken allowance), at the style's
    rates; every other style keeps Trevor's 77.5%. ONE copy of the rule:
    words_fit.style_sung_target_pct, so the director's words-fit check and
    this contract judge every sheet the same way."""
    return _WF.style_sung_target_pct(_sid(style_id), delivered_s)


def _pct(part, whole):
    return round(100.0 * part / whole, 1) if whole else 0.0


def _non_hook_sung(sections, blocks):
    """Sung sections that are not the hook and not the wordless vocalise."""
    hook_ids = {id(b) for b in blocks}
    return [s for s in sections if s["delivery"] == "sung" and id(s) not in hook_ids
            and s["kind"] in NON_HOOK_SUNG_KINDS]


def check_sheet(sheet_text, style_id, delivered_s, style_text=None):
    """The style contract on one lyric sheet. Never raises on a bad sheet:
    returns {"verdict": PASS|FLAG|FAIL|EXEMPT, "reasons", "flags",
    "sections" (per-section words, seconds and word share by delivery),
    "totals", "hook", "sung_non_hook", "sung_of_voice"}."""
    missing = ["UNMEASURED: %s" % f for f, v in (("style_id", style_id), ("length_s", delivered_s))
               if v is None]
    if missing:   # no gate switches itself off: a missing input is a FAIL
        return {"verdict": "FAIL", "reasons": missing, "flags": [], "style_id": style_id}
    if _R.is_exempt(style_id):
        return {"verdict": "EXEMPT", "reasons": [], "flags": [], "style_id": style_id,
                "note": "spoken voiceover version: dialogue is spoken by design"}
    sid = _sid(style_id)
    label = _MS.style(sid)["label"]
    rates = _rates(sid)
    secs = parse_sections(sheet_text)
    reasons, flags = [], []
    rows, words, seconds = [], dict.fromkeys(_R.DELIVERIES, 0), dict.fromkeys(_R.DELIVERIES, 0.0)
    for s in secs:
        n = sum(len(ln.split()) for ln in s["lines"])
        d = s["delivery"]
        if d is None:
            if n:
                reasons.append("%r carries lyric lines under a tag that names no delivery" % s["tag"])
            continue
        t = n / float(rates[d])
        words[d] += n
        seconds[d] += t
        rows.append({"tag": s["tag"], "kind": s["kind"], "delivery": d, "words": n,
                     "seconds": round(t, 1)})
    total_w = sum(words.values())
    for r in rows:
        r["word_share_pct"] = _pct(r["words"], total_w)
    totals = {"%s_words" % d: words[d] for d in _R.DELIVERIES}
    totals.update({"%s_s" % d: round(seconds[d], 1) for d in _R.DELIVERIES})
    totals.update({"%s_word_share_pct" % d: _pct(words[d], total_w) for d in _R.DELIVERIES})
    totals["total_words"] = total_w
    out = {"verdict": "FAIL", "style_id": sid, "label": label, "delivered_s": delivered_s,
           "reasons": reasons, "flags": flags, "sections": rows, "totals": totals,
           "rap_vs_spoken": "planned from the sheet's tags; on the audio " + RAP_AUDIO_UNMEASURED}
    if not rows:
        reasons.append("no tagged sections: every block must name sung, spoken or rap")
        return out
    # deliveries the style's own definition carries
    allowed = set(_MS.style(sid)["deliveries"])
    for d in sorted(set(r["delivery"] for r in rows) - allowed):
        reasons.append("%s blocks in %s, whose definition (%s) has no %s"
                       % (d, label, _MS.style(sid)["sound"], d))
    # the chorus: the hook plus at least one other real line in EVERY chorus block
    blocks, hook_keys = _hook_blocks(secs)
    hook_text = " / ".join(blocks[0]["lines"]) if blocks else ""
    thin = [b for b in blocks if len(_real_lines(b)) < MIN_CHORUS_LINES]
    out["hook"] = {"text": hook_text, "blocks": len(blocks),
                   "blocks_with_only_the_hook": len(thin), "count_owner": _hook_count_owner()}
    if not blocks:
        reasons.append("no sung chorus: %s needs a sung chorus (the hook plus at least one "
                       "other line)" % label)
    elif thin:
        reasons.append("%d of %d chorus blocks are only the hook repeated (first: %r): every "
                       "chorus carries the hook plus at least one other line of real words"
                       % (len(thin), len(blocks), " / ".join(thin[0]["lines"])))
    if _HP is None:
        # thin fallback until FU-HOOK-PLACEMENT is installed: the length's count
        allowed_hooks = _SH.hook_count(delivered_s)
        out["hook"]["allowed"] = allowed_hooks
        if len(blocks) > allowed_hooks:
            reasons.append("%d hook blocks, a %g s song allows %d"
                           % (len(blocks), delivered_s, allowed_hooks))
    # the sung sections the plan calls for
    need = required_sung_sections(sid, delivered_s)
    non_hook = [s for s in _non_hook_sung(secs, blocks)
                if any(len(_real_words(ln)) >= MIN_REAL_WORDS_PER_LINE for ln in s["lines"])]
    nh_words = sum(len(ln.split()) for s in non_hook for ln in s["lines"])
    want = sum(need.values())
    out["sung_non_hook"] = {"sections": len(non_hook), "words": nh_words,
                            "required_sections": want, "plan": need}
    if len(non_hook) < want:
        reasons.append("%d sung non-hook sections (%d words), the %g s %s plan calls for %d (%s)"
                       % (len(non_hook), nh_words, delivered_s, label, want,
                          ", ".join("%s %d" % (k.replace("_", "-"), v)
                                    for k, v in sorted(need.items()) if v)))
    # planned sung share of voice, on the band, against the style's own target
    # as a floor: only a shortfall counts (a Soul sheet may be almost all sung)
    voice = seconds["sung"] + seconds["rap"] + seconds["spoken"]
    target = sung_target(sid, delivered_s)
    if voice <= 0:
        reasons.append("no voiced lines: sung share of voice UNMEASURED")
    else:
        pct = 100.0 * seconds["sung"] / voice
        short = max(0.0, target - pct)
        verdict = _SS.judge_gap(short)
        out["sung_of_voice"] = {"planned_pct": round(pct, 1), "target_pct": target,
                                "short_pts": round(short, 1), "verdict": verdict}
        text = ("planned sung share of voice %.1f%% (sung %.1f s, rap %.1f s, spoken %.1f s), "
                "%s target at least %g%%, %.1f points short"
                % (pct, seconds["sung"], seconds["rap"], seconds["spoken"], label, target, short))
        if verdict == _SS.VERDICT_FAIL:
            reasons.append(text)
        elif verdict == _SS.VERDICT_FLAG:
            flags.append(text)
    # delivery cues
    upbeat = _is_upbeat(sid)
    raps = [s for s in secs if s["delivery"] == "rap"]
    untagged = [s for s in raps
                if not all(p.search(s["cue"]) for p in _RAP_NEED) or _RAP_BAN.search(s["cue"])]
    if untagged:
        reasons.append("%d of %d rap blocks are not tagged as rhythmic rap on the beat (first: %r, "
                       "cue %r): Suno talks an untagged rap line instead of rapping it"
                       % (len(untagged), len(raps), untagged[0]["tag"], untagged[0]["cue"]))
    slow = [s for s in secs if upbeat and s["delivery"] == "sung" and _SLOW_RE.search(s["cue"])]
    if slow:
        reasons.append("%d sung blocks ask for slow delivery in upbeat %s (first: %r, cue %r)"
                       % (len(slow), label, slow[0]["tag"], slow[0]["cue"]))
    for s in secs:
        if s["kind"] == "outro" and s["delivery"] == "spoken" and not _NO_MELODY_RE.search(s["cue"]):
            reasons.append("spoken outro %r does not say \"no melody\" (cue %r): Suno sings the "
                           "closing lines on the hook melody" % (s["tag"], s["cue"]))
    if upbeat and style_text and _SLOW_RE.search(str(style_text)):
        reasons.append("style text asks for slow delivery in upbeat %s" % label)
    out["verdict"] = "FAIL" if reasons else ("FLAG" if flags else "PASS")
    return out


def _sung_hits(key, seq, words, segs):
    """How many times a word sequence sits in the aligned words inside a
    detector-measured sung segment."""
    hits = i = 0
    while key and i + len(key) <= len(seq):
        if seq[i:i + len(key)] == list(key):
            mid = (words[i]["startS"] + words[i + len(key) - 1]["endS"]) / 2.0
            if any(s["delivery"] == "sung" and s["start"] <= mid <= s["end"] for s in segs):
                hits += 1
            i += len(key)
        else:
            i += 1
    return hits


def _count(seq, key):
    """Non-overlapping occurrences of a word sequence."""
    n = i = 0
    while key and i + len(key) <= len(seq):
        if seq[i:i + len(key)] == list(key):
            n, i = n + 1, i + len(key)
        else:
            i += 1
    return n


def _hook_repeats(text, hook_keys):
    """Per hook line: how many times its words are sung, whatever section
    header (if any) they sit under. Headers are dropped, so Suno's returned
    words count the same way with or without them."""
    seq = _SH.words(_HEADER_RE.sub(" ", str(text or "")))
    return {k: _count(seq, k) for k in hook_keys}


def check_returned_song(sheet_text, aligned_words, segments, style_id, delivered_s):
    """Post-generation song gate, BEFORE any picture or video spend.

    aligned_words: Suno's aligned words [{"word", "startS", "endS"}], whose
    text carries the returned section headers; segments: the singing
    detector's measured segments (source="measured"). FAIL when Suno sang a
    hook line more times than the sheet does (tagged or untagged: the hook
    lyric sung under a verse or outro header counts), when the sung non-hook
    lyrics are absent for a style whose plan requires them, or when the
    measured sung share of voice is more than 10 points below the style's
    target. Any missing input is a FAIL marked UNMEASURED. Hook BLOCK count
    and placement on the take are hook_placement.check_returned's.
    """
    if _R.is_exempt(style_id):
        return {"verdict": "EXEMPT", "reasons": [], "numbers": {}}
    sid = _sid(style_id)
    reasons, nums = [], {"rap_vs_spoken": RAP_AUDIO_UNMEASURED}
    for field, val in (("sheet_text", sheet_text), ("delivered_s", delivered_s),
                       ("aligned_words", aligned_words)):
        if not val:
            reasons.append("UNMEASURED: %s" % field)
    if reasons:
        return {"verdict": "FAIL", "reasons": reasons, "numbers": nums, "style_id": sid}
    sheet = parse_sections(sheet_text)
    blocks, hook_keys = _hook_blocks(sheet)
    words = [w for w in aligned_words if isinstance(w, dict) and "startS" in w]
    returned = "".join(str(w.get("word", "")) for w in words)
    nums["sheet_hook_blocks"] = len(blocks)
    # Hook BLOCK count and placement on the take: hook_placement.check_returned.
    # Here: every time Suno sang a hook line, tagged or untagged.
    want, have = _hook_repeats(sheet_text, hook_keys), _hook_repeats(returned, hook_keys)
    nums["hook_line_repeats"] = {" ".join(k): [want[k], have[k]] for k in sorted(hook_keys)}
    extra = sorted((k for k in hook_keys if have[k] > want[k]), key=lambda k: -have[k])
    if extra:
        reasons.append("Suno sang the hook line %r %d times, the sheet has it %d times "
                       "(untagged repeats included)" % (" ".join(extra[0]), have[extra[0]],
                                                        want[extra[0]]))
    # detector-measured segments only: aligned segments (FU-U3, the rap read
    # from the sheet's own labels) are not the detector's, so they never count
    segs = [s for s in (segments or []) if isinstance(s, dict)
            and s.get("source") == _SS.MEASURED_SOURCE]
    measured = bool(segs)
    seq = [(_SH.words(w.get("word", "")) or [""])[-1] for w in words]
    need = sum(required_sung_sections(sid, delivered_s).values())
    nh_lines = [tuple(_SH.words(ln)) for s in _non_hook_sung(sheet, blocks) for ln in s["lines"]
                if len(_real_words(ln)) >= MIN_REAL_WORDS_PER_LINE]
    nums.update({"sung_non_hook_lines_on_sheet": len(nh_lines),
                 "sung_non_hook_sections_required": need})
    if not measured:
        reasons.append("UNMEASURED: detector-measured segments (sung lyrics and sung share)")
    else:
        sung_lines = sum(1 for k in nh_lines if _sung_hits(k, seq, words, segs))
        nums["sung_non_hook_lines_sung"] = sung_lines
        if need and sung_lines == 0:
            reasons.append("no sung lyrics outside the hook (sheet carries %d sung non-hook "
                           "lines, %d sung on the take); %s needs %d sung non-hook sections"
                           % (len(nh_lines), sung_lines, _MS.style(sid)["label"], need))
        v = _SS.check_sung_of_voice(segs)
        target = sung_target(sid, delivered_s)
        nums.update({"sung_of_voice_pct": round(v["sung_of_voice_pct"], 1),
                     "sung_s": round(v["sung_seconds"], 1),
                     "not_sung_voice_s": round(v["spoken_seconds"], 1),
                     "target_pct": target})
        if v["sung_of_voice_pct"] < target - _SS.FLAG_PTS:
            reasons.append("measured sung share of voice %.1f%% is %.1f points below the %g%% "
                           "target" % (v["sung_of_voice_pct"], target - v["sung_of_voice_pct"],
                                       target))
    return {"verdict": "FAIL" if reasons else "PASS", "reasons": reasons, "numbers": nums,
            "style_id": sid}
