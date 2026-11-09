#!/usr/bin/env python3
"""S75-T22 round-2 repair proof: the four recipes render AND dispatch.

Run from anywhere:

    python3 75-drama-song-ad-factory/scripts/core/music_styles/demonstrate_s75_t22_dispatch.py

Round 1's defect: the four records existed, but nothing registered them, so
``music_styles.style_prompt`` / ``spoken_target`` raised UNKNOWN_STYLE and the
only code that ever merged them was the unit's own test. Every check below
goes through the package the way production imports it -- no manual
``STYLES.update(...)`` anywhere in this file.

Exit 0 = every clause demonstrated. Exit 1 = the clause that broke is named.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

#: APPENDED, never prepended: HERE holds ``music_styles.py``, so putting it
#: first would shadow the ``music_styles`` PACKAGE with the leaf module.
if HERE not in sys.path:
    sys.path.append(HERE)

import music_styles as MS                      # noqa: E402
from music_styles import recipes_s75_t22 as R  # noqa: E402

FAILURES = []


def check(name, ok, detail=""):
    print("%-46s %s%s" % (name, "PASS" if ok else "FAIL",
                          (" " + detail) if detail else ""))
    if not ok:
        FAILURES.append(name)


def main():
    ids = R.style_ids()
    print("four ids: %s" % (", ".join(ids),))

    # C1 -- registered and resolvable by the shared table's own seam.
    check("C1-registered", all(sid in MS.extra_style_ids() for sid in ids),
          repr(MS.extra_style_ids()))

    # C2 -- render: style_prompt returns the compiled field plus the delivery
    # map, for each of the four, with no caller-side merge.
    prompts = {}
    for sid in ids:
        rendered = MS.style_prompt(sid)
        prompts[sid] = rendered
        verbs = ("SPEAKS", "SINGS") if sid != "urban-gospel" else (
            "SPEAKS", "RAPS", "SINGS")
        check("C2-render %s" % sid,
              rendered.startswith(R.compile_style_field(sid))
              and all(v in rendered for v in verbs)
              and len(rendered) > 200,
              "len=%d" % len(rendered))

    # C3 -- distinct full instructions: all six pairs differ.
    pairs = [(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]]
    check("C3-pairwise-distinct", all(prompts[a] != prompts[b]
                                      for a, b in pairs),
          "%d pairs" % len(pairs))

    # C4 -- dispatch: the spokes production calls, none of them doing a merge.
    for sid in ids:
        target = MS.spoken_target(sid, 180)
        hint = MS.section_hint(sid)
        record = MS.style(sid)
        check("C4-dispatch %s" % sid,
              target["style_id"] == sid and target["length_seconds"] == 180
              and bool(hint.strip()) and record["style_id"] == sid,
              "target=%s hint_len=%d" % (target["target"], len(hint)))

    from style_defaults import music as DEFAULT_MUSIC
    for sid in ids:
        ref = DEFAULT_MUSIC.music_style_ref(choice=sid)
        check("C5-style_defaults %s" % sid,
              ref["id"] == sid and ref["suno_prompt"] == prompts[sid]
              and ref["section_hint"] == MS.section_hint(sid))

    # C6 -- CONTROL on the same instrument: an id nobody registered still
    # fails closed. A negative only counts when the control passes.
    try:
        MS.style_prompt("not-a-style-at-all")
    except MS.MusicStyleError as exc:
        check("C6-control-unknown-still-refused", exc.code == "UNKNOWN_STYLE",
              exc.code)
    else:
        check("C6-control-unknown-still-refused", False, "no error raised")

    # C7 -- the three D18 records are untouched: the shared table still holds
    # exactly the three original ids, so the F13 record sweep and the owner's
    # byte rule read what they always read.
    check("C7-d18-table-unchanged",
          tuple(MS.STYLES) == ("soul-ballad", "rnb-flow", "soul-rise"),
          repr(tuple(MS.STYLES)))

    # C8 -- Kirk Franklin is a display reference only, and no approval loop.
    leaked = []
    for sid in ids:
        leaked += R.client_reference_hits(prompts[sid], sid)
    check("C8-kirk-absent-from-outbound", leaked == [], repr(leaked))
    source = open(os.path.join(HERE, "recipes_s75_t22.py"), encoding="utf-8")
    text = source.read()
    source.close()
    loops = [w for w in ("while not approved", "approval_loop",
                         "request_approval", "until_approved") if w in text]
    check("C9-no-approval-loop", loops == [], repr(loops))

    print()
    if FAILURES:
        print("FAILED: %s" % (", ".join(FAILURES),))
        return 1
    print("ALL DISPATCH CHECKS PASS (%d ids)" % len(ids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
