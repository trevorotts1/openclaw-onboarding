#!/usr/bin/env python3
"""Batch-8c proof 2: the C2 re-voicing presence line reaches the COMPOSED provider payload.

Re-runnable at the batch head. Stdlib only, no network, no provider call.

Builds the real requests through the shipped composer
`song_choices.song_choices.build_requests` (never a reimplementation of it) and
inspects `req["input"]["style"]` - the text the provider actually receives -
for every variant of every style in `variants.json`.

Expected, per style:
  * a variant marked `revoices_lead: true` carries the style's own presence
    rule (the text `_LEAD_PRESENCE_RE` extracts from `style_parts[0]`, e.g.
    "close dry upfront vocal") EXACTLY ONCE in the composed style;
  * a variant not so marked carries it ZERO times;
  * forcing the flag off on a flagged variant drops the line (causation control).

Correction history, kept because a receipt should show what was asserted first:
the first version of this probe counted `style_parts[0]` - the groove/palette
line - and failed 7 checks. The composer does not carry that whole line; it
inserts only the lead-presence clause matched by `_LEAD_PRESENCE_RE`. The probe
now uses the code's own regex; the failure was in the expectation, not the code.

Run from the repo root:
    python3 tests/w10-canary/evidence/B8C/proof_c2_presence.py
Exit 0 = every variant behaves; 1 = at least one assertion failed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[4]
CORE = REPO / "75-drama-song-ad-factory" / "scripts" / "core"
sys.path.insert(0, str(CORE))

import song_choices.song_choices as SC                       # noqa: E402
import song_choices.test_song_choices_fu_song as SHT         # noqa: E402  (sheet fixtures)
import suno_recipe.suno_recipe as SR                         # noqa: E402

VARIANTS = json.loads((CORE / "song_choices" / "variants.json").read_text("utf-8"))
FAILS = []

def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (" :: " + detail if detail else ""))
    if not cond:
        FAILS.append(name)

def main():
    styles = [k for k in VARIANTS if not k.startswith("_")]
    for style in styles:
        m = SR._LEAD_PRESENCE_RE.search(str(SR.music_block(style)["style_parts"][0]))
        presence = m.group(0) if m else None
        check("%s: the style data carries a lead-presence rule" % style,
              bool(presence), str(presence))
        reqs = SC.build_requests(
            style, SHT.sheet_for(style), SHT.CLIENT, "T",
            SHT.RNB_LEN if style == "rnb-flow" else 58, "f",
            hook_plan={"true_at_beat": "the_world"})
        print("  %-14s %-18s %-8s %s" % ("variant", "revoices_lead", "count", "chars"))
        for v, req in reqs:
            text = str(((req.get("input") or {}).get("style")) or "")
            n = len(SR._LEAD_PRESENCE_RE.findall(text))
            print("  %-14s %-18s %-8d %d"
                  % (v["id"], str(bool(v.get("revoices_lead"))), n, len(text)))
            if v.get("revoices_lead"):
                check("%s/%s: re-voicing payload carries the presence line exactly once"
                      % (style, v["id"]), n == 1, "count=%d" % n)
            else:
                check("%s/%s: non-re-voicing payload carries it zero times"
                      % (style, v["id"]), n == 0, "count=%d" % n)
            check("%s/%s: the style arrives nested under input.style" % (style, v["id"]),
                  bool(text), "empty")

    print("\n  causation control: same composer, flag forced off")
    for style in styles:
        flagged = [v for v in VARIANTS[style] if v.get("revoices_lead")]
        if not flagged:
            continue
        v = flagged[0]
        txt = SR.brief_style_text(style, SC._brief_text(v, "f"), None, "f", None,
                                  tail_clause=v["brief"]["arrangement"],
                                  revoices_lead=False)
        found = bool(SR._LEAD_PRESENCE_RE.search(txt))
        print("  %-14s %-18s found=%s" % (style, v["id"], found))
        check("%s/%s: with the flag off the presence line is absent"
              % (style, v["id"]), not found, "found=%r" % found)

    print("\nproof_c2_presence: %d check(s) failed" % len(FAILS))
    return 1 if FAILS else 0

if __name__ == "__main__":
    sys.exit(main())
