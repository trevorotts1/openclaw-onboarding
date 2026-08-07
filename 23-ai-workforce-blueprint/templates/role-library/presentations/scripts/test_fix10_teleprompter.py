#!/usr/bin/env python3
"""
test_fix10_teleprompter.py — FIX-10 (Part 10 M9): the teleprompter web app is
produced from the finished PRESENTERS-SPEECH.md and carries the FULL speech text.

FIX-10 gate (Gauntlet Loop per-task QC row):
    Generate `teleprompter_html` from `speech_md`.
    -> teleprompter_html exists AND contains the FULL speech text
       (python substring assertions on 5+ spaced sentences).

The `presenters-speech-writer` role existed but never ran (Error: role exists,
never fired; Part-10 M9 missing). build_teleprompter.py is a NO-AI deterministic
markdown->HTML transform: it parses the PRESENTERS-SPEECH.md contract
(`## Slide N -- Headline (STAGE)` + `> STAGE: ... SECONDS: Ns`) and emits a
single self-contained `presenter-teleprompter.html` (inline CSS + JS + the
speech as inline JSON at __SPEECH_JSON__).

This test proves the QC gate end-to-end, with no AI and no network:
  1. GENERATE — run build_teleprompter.py against a real PRESENTERS-SPEECH.md
     (the built-in SAMPLE_SPEECH_MD in the exact contract) and write the file.
  2. EXISTS — the teleprompter_html file exists, is non-empty, and clears the
     AF-BUNDLE-COMPLETE floor (TELEPROMPTER_MIN_BYTES = 20,000).
  3. FULL SPEECH TEXT — 8+ spaced sentences from the speech appear VERBATIM as
     substrings of the rendered HTML (the speech is embedded as inline JSON).
  4. SELF-CONTAINED — no external asset loads / @import (build_teleprompter's
     own verify_teleprompter_html must report zero issues).
  5. PARSES EVERY SLIDE — every slide of the source speech.md is present in the
     generated HTML's slide count.

Run:  python3 test_fix10_teleprompter.py
      python3 -m pytest test_fix10_teleprompter.py -q
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_teleprompter as bt  # noqa: E402

# 8+ spaced sentences taken verbatim from SAMPLE_SPEECH_MD. The QC gate demands
# substring assertions on 5+ spaced sentences; we assert 8 to prove the FULL
# speech text survives, not just a headline.
FULL_SPEECH_SENTENCES = [
    "Hello and welcome, everybody.",
    "Congratulations on taking the first step just by being here.",
    "You could be doing a hundred other things right now, and instead you showed up for your future.",
    "Drop in the chat where you are watching from today.",
    "Stay to the very end, because what I save for the last ten minutes is the part nobody else will give you for free.",
    "Let me tell you exactly who this is for.",
    "This is for the person who is genuinely good at what they do, and is quietly furious that the world has not noticed yet.",
    "Five years ago I was the best-kept secret in my whole industry.",
    "Here is the one thing I need you to believe before you leave today.",
    "You are not behind. You are one decision away.",
    "Make it today. I will see you on the inside.",
]

# A sentence that is NOT in the speech — the negative control. A containment
# check that also passes on this text would be matching nothing (broken check).
NOT_IN_SPEECH = "The teleprompter contains this sentence which is never spoken."

# Two sentences that span the whole deck (first slide open + last slide close)
# to prove end-to-end full-speech presence, not just the opening.
FIRST_SLIDE_OPEN = "Hello and welcome, everybody."
LAST_SLIDE_CLOSE = "Make it today. I will see you on the inside."


def test_generate_teleprompter_from_speech_md():
    """FIX-10 core: generate teleprompter_html from speech_md; the file exists,
    is non-empty, clears the AF-BUNDLE-COMPLETE floor, parses every slide, is
    self-contained, and contains the FULL speech text."""
    fails = []

    # ---- 1. Build the source PRESENTERS-SPEECH.md (exact contract) ----
    work = Path(tempfile.mkdtemp(prefix="fix10_speech_"))
    speech_md = work / "PRESENTERS-SPEECH.md"
    speech_md.write_text(bt.SAMPLE_SPEECH_MD, encoding="utf-8")

    # ---- 2. Generate the teleprompter_html (the role's SOP 9.2 step 3).
    # The ROLE runs the CLI exactly as documented:
    #   python3 build_teleprompter.py --speech PRESENTERS-SPEECH.md \
    #       --out working/delivery/presenter-teleprompter.html --intake intake.json
    # This exercises the real subprocess entry point (argparse, verify gates,
    # file write) — not just the in-process build_html call.
    out_html = work / "presenter-teleprompter.html"
    cli = subprocess.run(
        [sys.executable, str(HERE / "build_teleprompter.py"),
         "--speech", str(speech_md),
         "--out", str(out_html),
         "--intake", "/dev/null"],
        capture_output=True, text=True, timeout=120,
    )
    if cli.returncode != 0:
        fails.append(f"build_teleprompter.py CLI exited {cli.returncode}: "
                     f"{cli.stderr.strip()[:300]}")
        return fails
    # The CLI refuses to write a degenerate file; a non-zero exit above already
    # covers the floor. Re-read the bytes the CLI actually wrote.
    if not out_html.exists():
        fails.append("teleprompter_html was not produced by the CLI")
        return fails
    html = out_html.read_text(encoding="utf-8")
    data = bt.parse_speech(bt.SAMPLE_SPEECH_MD)
    if not data["slides"]:
        fails.append("parse_speech returned no slides for the sample contract")
        return fails

    # ---- 3. EXISTS — file exists, non-empty, above the AF-BUNDLE-COMPLETE floor
    if not out_html.exists():
        fails.append("teleprompter_html was not produced")
        return fails
    nbytes = out_html.stat().st_size
    if nbytes == 0:
        fails.append("teleprompter_html is empty (0 bytes)")
    if nbytes < bt.TELEPROMPTER_MIN_BYTES:
        fails.append(
            f"teleprompter_html is {nbytes} bytes, below the "
            f"{bt.TELEPROMPTER_MIN_BYTES}-byte AF-BUNDLE-COMPLETE floor")

    # ---- 4. SELF-CONTAINED — verify_teleprompter_html reports zero issues
    issues = bt.verify_teleprompter_html(html)
    if issues:
        fails.append(f"verify_teleprompter_html reported issues: {issues}")

    # ---- 5. FULL SPEECH TEXT — every asserted sentence appears verbatim
    missing = [s for s in FULL_SPEECH_SENTENCES if s not in html]
    if missing:
        fails.append(f"{len(missing)}/{len(FULL_SPEECH_SENTENCES)} speech "
                     f"sentences MISSING from the HTML: {missing!r}")

    # ---- 6. NEGATIVE CONTROL — the not-in-speech sentence must NOT appear
    if NOT_IN_SPEECH in html:
        fails.append("negative control matched — the containment check is "
                     "over-matching (broken check)")

    # ---- 7. FULL-DECK PRESENCE — first-slide open AND last-slide close
    if FIRST_SLIDE_OPEN not in html:
        fails.append("the speech's opening sentence is missing from the HTML")
    if LAST_SLIDE_CLOSE not in html:
        fails.append("the speech's closing sentence is missing from the HTML")

    # ---- 8. PARSES EVERY SLIDE — the HTML carries every slide of the source
    src_slides = data["slides"]
    # The slide count is embedded in the inline speech JSON; assert parity.
    parsed_back = json.loads(re.search(r'<script id="speech-data" type="application/json">(.*?)</script>',
                                       html, re.S).group(1))
    back_slides = parsed_back.get("slides") or []
    if len(back_slides) != len(src_slides):
        fails.append(f"HTML embeds {len(back_slides)} slides but the source "
                     f"speech has {len(src_slides)}")

    if fails:
        print(f"FIX10 GENERATE+CONTAINMENT   -> FAIL")
        for f in fails:
            print("  - " + f)
    else:
        print(f"FIX10 GENERATE+CONTAINMENT   -> PASS "
              f"({len(data['slides'])} slides, {nbytes:,} bytes, "
              f"{len(FULL_SPEECH_SENTENCES)} sentences contained)")
    return fails


def main():
    fails = []
    for fn in [test_generate_teleprompter_from_speech_md]:
        try:
            fails += fn()
        except Exception as exc:  # noqa: BLE001
            fails.append(f"{fn.__name__} raised {exc!r}")
    print("=" * 60)
    if fails:
        print(f"FIX-10 QC TEST: FAIL ({len(fails)} failing assertion(s))")
        for f in fails:
            print("  - " + f)
        raise SystemExit(1)
    print("FIX-10 QC TEST: PASS — teleprompter_html produced from speech_md "
          "containing the full speech text")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
