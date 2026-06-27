#!/usr/bin/env python3
"""funnel_matcher_cli.py — build the catalog index, run a match, or selftest the matcher.

Usage (from 06-ghl-install-pages/tools/):
  python3 funnel_matcher_cli.py --build-index
  python3 funnel_matcher_cli.py --match "grow my email list"
  python3 funnel_matcher_cli.py --match "..." --json
  python3 funnel_matcher_cli.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# The catalog lives in 06-ghl-install-pages/funnel-templates/ (sibling of tools/)
_SKILL6_ROOT = os.path.dirname(_HERE)
_ROOT = os.path.join(_SKILL6_ROOT, "funnel-templates")
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import funnel_matcher as fm  # noqa: E402

INDEX_PATH = os.path.join(_HERE, "catalog-index.json")


def build_index() -> int:
    cat = fm.Catalog.load(_ROOT)
    cat.save_index(INDEX_PATH)
    print(f"indexed {len(cat.templates)} templates, {len(cat.personas)} personas")
    print(f"groups: {sorted({t['group'] for t in cat.templates})}")
    print(f"-> {INDEX_PATH}")
    return 0


def run_match(text: str, as_json: bool, threshold: float) -> int:
    cat = (fm.Catalog.from_index(INDEX_PATH) if os.path.isfile(INDEX_PATH)
           else fm.Catalog.load(_ROOT))
    dec = fm.match_funnel(text, cat, threshold=threshold)
    if as_json:
        print(json.dumps(dec, indent=2, ensure_ascii=False))
        return 0
    print(f"decision   : {dec['decision']}")
    print(f"matched    : {dec['matched_template']} ({dec['matched_name']})")
    print(f"confidence : {dec['confidence']}  (threshold {dec['threshold']})")
    print(f"persona    : {(dec['copy_persona'] or {}).get('label')}")
    print(f"rationale  : {dec['rationale']}")
    print("top:")
    for r in dec["ranked"][:5]:
        print(f"   {r['confidence']:.3f}  {r['id']:<34} {r['parts']}")
    return 0


# (request, expected) — expected is a template id, a set of acceptable ids
# (genuinely ambiguous requests), or None for CREATE_NEW.
_CASES = [
    ("I want to grow my email list with a free guide", {"squeeze-page", "lead-magnet"}),
    ("give away a free training video before asking for the opt-in", "reverse-squeeze-page"),
    ("offer a downloadable ebook checklist in exchange for an email", "lead-magnet"),
    ("register people for my live perfect webinar masterclass", "webinar-funnel"),
    ("evergreen automated webinar that runs 24/7", "autowebinar-funnel"),
    ("free plus shipping book, customer just pays 7.95 shipping", "book-funnel"),
    ("high ticket coaching application funnel with a qualification phone call", "application"),
    ("reduce membership churn and save the sale when people try to cancel", "cancellation-funnel"),
    ("build a brand hub to organize all my funnels and look legit to the press", "funnel-hub"),
    ("a quiz that segments my audience and routes them to different offers", "survey-quiz"),
    ("two step tripwire free plus shipping order form with an order bump and OTOs", "2-step-tripwire-free-plus-shipping"),
    ("a sourdough bread recipe blog about hydration ratios", None),
    ("my favorite hiking trails in the pacific northwest", None),
]


def selftest(threshold: float) -> int:
    cat = fm.Catalog.load(_ROOT)
    ok = 0
    print(f"catalog: {len(cat.templates)} templates  threshold={threshold}\n")
    for text, expected in _CASES:
        dec = fm.match_funnel(text, cat, threshold=threshold)
        # Accept USE_TEMPLATE and HONORED_EXPLICIT as positive decisions
        # (HONORED_EXPLICIT fires when the request text unambiguously names a template —
        #  this is correct behavior from the flexibility retrofit, not a regression)
        positive_decision = dec["decision"] in ("USE_TEMPLATE", "HONORED_EXPLICIT")
        got = dec["matched_template"] if positive_decision else None
        if isinstance(expected, set):
            passed = got in expected
        else:
            passed = (got == expected)
        ok += passed
        flag = "ok " if passed else "FAIL"
        want = "|".join(sorted(expected)) if isinstance(expected, set) else str(expected)
        print(f"[{flag}] {dec['decision']:<12} conf={dec['confidence']:.3f} "
              f"got={got!s:<34} want={want:<34} :: {text[:46]}")
    n = len(_CASES)
    print(f"\n{ok}/{n} cases passed")
    print("SELFTEST PASS" if ok == n else "SELFTEST FAIL")
    return 0 if ok == n else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="funnel-matcher")
    ap.add_argument("--build-index", action="store_true")
    ap.add_argument("--match", metavar="TEXT")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--threshold", type=float, default=fm.DEFAULT_THRESHOLD)
    a = ap.parse_args(argv)
    if a.build_index:
        return build_index()
    if a.match:
        return run_match(a.match, a.json, a.threshold)
    if a.selftest:
        return selftest(a.threshold)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
