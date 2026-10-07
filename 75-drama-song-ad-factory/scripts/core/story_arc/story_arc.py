"""story_arc.py: twelve-beat arc validator (directive 11.1). stdlib only.

Contract: exactly the twelve canonical beat IDs, each once, in canonical
order (subsequence check so a single missing beat still fails on identity,
not on order noise), and the product reveal never lands before stage 8 —
beat 8 is Gift / Mechanism / Product Introduction.

QC fixtures: valid, one file per beat missing, duplicate, reordered,
early reveal.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "blackceo.story-arc/v1"
TOOL_VERSION = "0.1.0"

# Directive 11.1 (L1138-1149), canonical order is the contract.
BEATS = (
    "ordinary_world",        # 1  Ordinary World
    "humiliation",           # 2  Humiliation / Emotional Wound
    "wound_deepens",         # 3  Wound Deepens
    "frozen",                # 4  Frozen
    "seeing_it_too",         # 5  Seeing It Too
    "failed_solutions",      # 6  Failed Solutions
    "mentor",                # 7  Mentor / Trusted Guide
    "product_intro",         # 8  Gift / Mechanism / Product Introduction
    "doubt",                 # 9  Doubt
    "climb",                 # 10 Climb / Transformation
    "vindication",           # 11 Vindication
    "return_cta",            # 12 Return / Pitch / CTA
)

PRODUCT_REVEAL_MIN = 8   # reveal stage >= 8: product intro is beat 8
PRODUCT_REVEAL_MAX = len(BEATS)
STORY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
EXIT = {"ok": 0, "rejected": 4, "error": 1}
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _res(outcome, reason_code, errors, story, ids, reveal):
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "outcome": outcome,
        "reason_code": reason_code,
        "errors": errors,
        "beat_count": len(ids),
        "beats": ids,
        "product_reveal": reveal,
        "next_action": (
            "Proceed to storyboard." if outcome == "ok"
            else "Fix the listed beat errors and re-run validate_story."
        ),
        "story_id": story.get("story_id") if isinstance(story, dict) else None,
    }


def validate_story(story):
    """Validate a twelve-beat story record.

    Story record: {"story_id": ..., "beats": [beat_id x12], "product_reveal": int}
    Returns outcome/reason_code/errors/beat_count/beats/product_reveal/next_action.
    """
    if not isinstance(story, dict):
        return _res("error", "story-not-an-object",
                    [{"error": "story-not-an-object", "detail": "story must be a JSON object"}],
                    {}, [], None)

    errors = []
    beats = story.get("beats")
    if not isinstance(beats, list) or not beats:
        errors.append({"error": "beats-missing",
                       "detail": "beats must be a non-empty list"})
        return _res("rejected", "beats-missing", errors, story, [], None)

    ids = []
    for i, b in enumerate(beats):
        if not isinstance(b, str) or not b.strip():
            errors.append({"error": "beat-not-a-string",
                           "detail": "index %d: %r" % (i, b)})
        else:
            ids.append(b.strip())

    known = set(BEATS)
    unknown = sorted({b for b in ids if b not in known})
    if unknown:
        errors.append({"error": "beat-unknown", "detail": unknown})

    seen, dups = set(), []
    for b in ids:
        if b in seen and b not in dups:
            dups.append(b)
        seen.add(b)
    if dups:
        errors.append({"error": "beat-duplicate", "detail": sorted(dups)})

    missing = [b for b in BEATS if b not in seen]
    if missing:
        errors.append({"error": "beat-missing", "detail": missing})

    if len(ids) != len(BEATS):
        errors.append({"error": "beat-count",
                       "detail": "got %d, want %d" % (len(ids), len(BEATS))})

    if not unknown:  # order: every known beat must advance in canonical order
        order = [BEATS.index(b) for b in ids if b in known]
        if any(order[i] > order[i + 1] for i in range(len(order) - 1)):
            errors.append({"error": "beat-order", "detail": list(ids)})

    reveal = story.get("product_reveal")
    if "product_reveal" not in story:
        errors.append({"error": "reveal-missing",
                       "detail": "product_reveal (beat index of product first appearance) is required"})
    elif not isinstance(reveal, int) or isinstance(reveal, bool):
        errors.append({"error": "reveal-invalid",
                       "detail": "product_reveal must be an int, got %r" % (reveal,)})
    elif reveal < PRODUCT_REVEAL_MIN:
        errors.append({"error": "reveal-early",
                       "detail": "product_reveal=%d, must be >= %d (product intro is beat 8)"
                                 % (reveal, PRODUCT_REVEAL_MIN)})
    elif reveal > PRODUCT_REVEAL_MAX:
        errors.append({"error": "reveal-out-of-range",
                       "detail": "product_reveal=%d, must be <= %d" % (reveal, PRODUCT_REVEAL_MAX)})

    if "story_id" in story and not (
            isinstance(story["story_id"], str) and STORY_ID_RE.match(story["story_id"])):
        errors.append({"error": "story-id-invalid", "detail": repr(story.get("story_id"))})

    if errors:
        return _res("rejected", errors[0]["error"], errors, story, ids, reveal)
    return _res("ok", "story-valid", [], story, ids, reveal)


def load_fixture(name):
    with open(FIXTURE_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def selftest():
    """Run every QC fixture: valid passes, each defect rejects with its code."""
    checks, fails = [], []

    def expect(name, want_outcome, want_reason):
        try:
            story = load_fixture(name)
        except (OSError, json.JSONDecodeError) as e:
            checks.append(name)
            fails.append("%s: unreadable (%s)" % (name, e))
            return
        r = validate_story(story)
        ok = r["outcome"] == want_outcome and (
            want_reason is None or r["reason_code"] == want_reason)
        checks.append(name)
        if not ok:
            fails.append("%s: outcome=%s reason=%s, want %s/%s"
                         % (name, r["outcome"], r["reason_code"],
                            want_outcome, want_reason))

    expect("valid.json", "ok", "story-valid")
    for beat in BEATS:                       # each-beat-missing cases
        expect("missing-%s.json" % beat, "rejected", "beat-missing")
    expect("duplicate.json", "rejected", "beat-duplicate")
    expect("reordered.json", "rejected", "beat-order")
    expect("reveal-early.json", "rejected", "reveal-early")
    expect("reveal-missing.json", "rejected", "reveal-missing")

    for bad in (None, [], "x", {"beats": [], "product_reveal": 8},
                {"beats": list(BEATS), "product_reveal": 13},
                {"beats": list(BEATS), "product_reveal": "8"}):
        r = validate_story(bad)
        checks.append("inline:%r" % (bad if not isinstance(bad, list) else bad[:2],))
        if r["outcome"] == "ok":
            fails.append("inline %r accepted, want reject" % (bad,))

    # canonical identity: BEATS order matches directive 11.1 word for word
    want = ["ordinary_world", "humiliation", "wound_deepens", "frozen",
            "seeing_it_too", "failed_solutions", "mentor", "product_intro",
            "doubt", "climb", "vindication", "return_cta"]
    checks.append("beats-identity")
    if list(BEATS) != want or len(BEATS) != 12:
        fails.append("BEATS drifted from directive 11.1: %r" % (list(BEATS),))

    print("story_arc selftest: %s (%d checks, %d failures)"
          % ("PASS" if not fails else "FAIL", len(checks), len(fails)))
    for f in fails:
        print(" -", f)
    return 0 if not fails else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="story_arc.py",
                                 description="Twelve-beat story arc validator (directive 11.1).")
    ap.add_argument("--selftest", action="store_true", help="Run QC fixtures.")
    ap.add_argument("--story", default=None, help="Story record as a JSON file.")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.story:
        ap.error("one of --selftest or --story is required")
    try:
        with open(a.story, encoding="utf-8") as f:
            story = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        r = {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION,
             "outcome": "error", "reason_code": "story-unreadable",
             "errors": [{"error": "story-unreadable", "detail": str(e)[:200]}],
             "beat_count": 0, "beats": [], "product_reveal": None,
             "next_action": "Supply a readable JSON story record."}
    else:
        r = validate_story(story)
    json.dump(r, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return EXIT[r["outcome"]]


if __name__ == "__main__":
    sys.exit(main())
