#!/usr/bin/env python3
"""I8 sung hook: one catchy hook, sung a number of times set by video length.

Owner order 2026-10-08: every sung ad has ONE short hook built from the
client's own words, and the longer the video, the more times it is sung.
stdlib only; no network, no spend.

Formula (named constants, tunable):
    count = clamp(1 + floor(L / SECONDS_PER_HOOK), HOOK_MIN, HOOK_MAX)
    L = delivered seconds (the I4 rule already made that chosen length - 2).
    28 s -> 2, 58 s -> 3, 88 s -> 4, 118 s -> 5, 178 s -> 8, 298 s -> 12.

Placement (FU-HOOK-PLACEMENT, Trevor 2026-10-09): the hook is the payoff,
never the opener. The first hook comes after the build-up (a verse, plus a
pre-chorus where the style has one) and at the story beat where its words
become true; returns never go backwards (core/sung_hook/hook_placement.py).
hook_times is only the even spacing used when no plan gives the first
hook second: FIRST_HOOK_AT of runtime, last at LAST_HOOK_AT.

Measured: a hook counts only if its words sit inside a take segment the
singing detector measured as sung (never from labels). Band (Trevor):
count >= target accept; one short accept with a flag; two or more short
regenerate.
"""
from __future__ import annotations

import math
import re

TOOL_NAME = "sung_hook"
TOOL_VERSION = "1.0.0"

SECONDS_PER_HOOK = 25
HOOK_MIN, HOOK_MAX = 2, 12
FIRST_HOOK_AT = 0.15      # fraction of runtime (H6 first-sung target)
LAST_HOOK_AT = 0.90       # ponytail: fixed fraction; make it CTA-aware if the end card length varies
HOOK_WORDS_MIN, HOOK_WORDS_MAX = 4, 10
FLAG_SHORT = 1            # one short: accept with a flag; more: regenerate


def _words(text):
    """Word tokens; hyphen-held vowels (sma-a-all) and doubled letters fold so a
    held word matches its plain spelling on both sides of every comparison."""
    t = re.sub(r"(?<=[a-z])-(?=[a-z])", "", str(text).lower())
    return [re.sub(r"([a-z])\1+", r"\1", w)
            for w in re.findall(r"[a-z0-9]+(?:'[a-z]+)?", t)]


def hook_count(length_s):
    """How many times the hook is sung for a delivered length in seconds."""
    if not isinstance(length_s, (int, float)) or length_s <= 0:
        raise ValueError("length_s must be a positive number of seconds")
    return max(HOOK_MIN, min(HOOK_MAX, 1 + math.floor(length_s / SECONDS_PER_HOOK)))


def hook_times(length_s):
    """Target start second of each hook: first at 15%, last near the end."""
    n = hook_count(length_s)
    a, b = FIRST_HOOK_AT * length_s, LAST_HOOK_AT * length_s
    return [round(a + (b - a) * i / (n - 1), 2) for i in range(n)]


def check_hook_text(hook, client_text, protected_names=()):
    """4-10 words, only the client's own words, protected names exact."""
    text = " ".join(hook) if isinstance(hook, (list, tuple)) else str(hook)
    toks, errs = _words(text), []
    if not HOOK_WORDS_MIN <= len(toks) <= HOOK_WORDS_MAX:
        errs.append("hook is %d words, want %d-%d"
                    % (len(toks), HOOK_WORDS_MIN, HOOK_WORDS_MAX))
    extra = sorted(set(toks) - set(_words(client_text)))
    if extra:
        errs.append("hook uses words the client never said: %s" % extra)
    for name in protected_names:
        if name.lower() in text.lower() and name not in text:
            errs.append("protected name %r must be spelled exactly" % name)
    return errs


def build_lyric_sheet(verses, hook_lines, length_s, pre=None):
    """Interleave the hook into the verses the right number of times.

    verses: [{"tag","delivery","lines"}]. One verse opens (then ``pre``, the
    pre-chorus section, when the style has one), then the hook;
    remaining verses spread evenly between later hooks; last section is a
    hook. Returns a recipe-format sheet whose hook sections are tagged Hook.
    """
    n = hook_count(length_s)
    hook = {"tag": "Hook", "delivery": "sung", "lines": list(hook_lines)}
    gaps = [[] for _ in range(n)]            # verses placed before hook i
    rest = list(verses)
    if rest:
        gaps[0].append(rest.pop(0))
    if pre:
        gaps[0].append(dict(pre))
    for j, v in enumerate(rest):
        gaps[1 + j * (n - 1) // len(rest)].append(v)
    sheet = []
    for g in gaps:
        sheet += [dict(v) for v in g] + [dict(hook)]
    return sheet


def _hook_key(sheet, hook_lines):
    return tuple(_words(" ".join(hook_lines)))


def check_sheet_count(sheet, hook_lines, length_s, want=None):
    """The sheet must carry the hook exactly ``want`` times (default
    hook_count(length_s); hook_placement.hook_target when a hook_plan
    reduces it), sung, after a verse, and the last sung section a hook."""
    key, errs = _hook_key(sheet, hook_lines), []
    n = hook_count(length_s) if want is None else want
    idx = [i for i, s in enumerate(sheet) if s.get("delivery") == "sung"
           and tuple(_words(" ".join(s["lines"]))) == key]
    if len(idx) != n:
        errs.append("hook appears %d times, %d s needs %d" % (len(idx), length_s, n))
    if idx and not any("verse" in str(s.get("tag", "")).lower() for s in sheet[:idx[0]]):
        errs.append("first hook is section #%d with no verse before it: the hook is the "
                    "payoff, never the opener" % (idx[0] + 1))
    sung = [i for i, s in enumerate(sheet) if s.get("delivery") == "sung"]
    if idx and sung and idx[-1] != sung[-1]:
        errs.append("last sung section is not the hook")
    return errs


def measure(hook_text, words, segments, target):
    """Count hook occurrences that were actually sung.

    words: Suno aligned words [{"word","startS","endS"}] (lyric_timing tier 1).
    segments: the singing detector's [{"delivery","start","end","source"}].
    Returns the receipt: hook, target, measured, times, verdict, action.
    """
    segs = segments or []
    if not segs or any(s.get("source") != "measured" for s in segs):
        return judge(hook_text, target, [], reason="segments are not detector-measured")
    key = _words(hook_text)
    # Suno's aligned words carry section headers inline ("[Hook (sung): ...]\nGirl, "):
    # strip them so the section's first sung word is the word read
    seq = [(_words(re.sub(r"\[[^\]]*\]?|^[^\[]*\]", " ", w.get("word", ""))) or [""])[0]
           for w in words]
    hits, i = [], 0
    while key and i + len(key) <= len(seq):
        if seq[i:i + len(key)] == key:
            a, b = words[i]["startS"], words[i + len(key) - 1]["endS"]
            mid = (a + b) / 2
            if any(s["delivery"] == "sung" and s["start"] <= mid <= s["end"] for s in segs):
                hits.append(round(a, 2))
            i += len(key)
        else:
            i += 1
    return judge(hook_text, target, hits)


def judge(hook_text, target, times, reason=None):
    """Trevor band on the measured sung count."""
    short = max(0, target - len(times))
    if reason:
        verdict, action = "FAIL", "regenerate"
    elif short == 0:
        verdict, action = "PASS", "accept"
    elif short <= FLAG_SHORT:
        verdict, action = "FLAG", "accept-with-flag"
    else:
        verdict, action = "FAIL", "regenerate"
    return {"hook": hook_text, "target": target, "measured": len(times),
            "times_s": list(times), "verdict": verdict, "action": action,
            "reason": reason or ("%d short of target" % short if short else "")}
