#!/usr/bin/env python3
"""email_matcher_cli.py — CLI for the Email Engine library matcher (Skill 50).

Mirrors Skill 6's funnel_matcher_cli.py.

  --build-index [OUT]   normalise email-library/catalog-index.json into a built index
  --match "<text>"      classify + score a request; print the decision record (JSON)
  --type TYPE           optional type filter (framework|buyer-type|objective|persona-style|sequence)
  --selftest            route corpus examples to their correct entries (fail-closed)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import email_matcher as em  # noqa: E402

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CATALOG = os.path.join(_SKILL_DIR, "email-library", "catalog-index.json")
DEFAULT_BUILT = os.path.join(_SKILL_DIR, "email-library", "catalog-built-index.json")

# (request text, type filter, expected matched entry id) — corpus-faithful routes.
_SELFTEST_CASES = [
    ("problem agitate solution email for cart recovery", "framework", "framework-pas"),
    ("write a 10 email promo sequence for my landing page", "sequence", "sequence-landing-page-10-promo"),
    ("12 email high ticket appointment strategy session sequence", "sequence", "sequence-high-ticket-appointment"),
    ("features to benefit email tying each feature to a benefit", "framework", "framework-features-to-benefit"),
    ("before after bridge email showing the transformation", "framework", "framework-before-after-bridge"),
    ("spontaneous impulse buyer quick blunt email", "buyer-type", "buyer-type-spontaneous"),
    ("methodical analytical buyer who needs evidence and details", "buyer-type", "buyer-type-methodical"),
    ("abandoned cart recovery email within a few hours", "objective", "objective-abandoned-cart"),
    ("downsell email after they declined the offer", "objective", "objective-downsell"),
    ("tony robbins high energy upsell style", "persona-style", "persona-style-tony-robbins"),
    ("iyanla vanzant spiritual affirmation style email", "persona-style", "persona-style-iyanla-vanzant"),
]


def _load(catalog_path: str) -> em.Catalog:
    if not os.path.isfile(catalog_path):
        print("catalog not found: %s" % catalog_path, file=sys.stderr)
        sys.exit(3)
    return em.Catalog.load(catalog_path)


def cmd_build_index(catalog_path: str, out_path: str) -> int:
    cat = _load(catalog_path)
    p = cat.save_index(out_path)
    print("built index: %s (%d entries, types=%s)" % (p, len(cat.entries), ",".join(cat.types)))
    return 0


def cmd_match(catalog_path: str, text: str, type_filter: str | None) -> int:
    cat = _load(catalog_path)
    req = {"text": text}
    if type_filter:
        req["type"] = type_filter
    decision = em.match_email(req, cat)
    print(json.dumps(decision, indent=2))
    return 0


def cmd_selftest(catalog_path: str) -> int:
    cat = _load(catalog_path)
    ok = True
    print("== email_matcher selftest (route corpus examples to their entry) ==")
    for text, tf, expect in _SELFTEST_CASES:
        d = em.match_email({"text": text, "type": tf}, cat)
        got = d.get("matched_id")
        good = got == expect
        ok = ok and good
        print("  [%s] %-52s -> %s (conf=%.3f)%s"
              % ("PASS" if good else "MISS", text[:52], got, d.get("confidence", 0.0),
                 "" if good else (" WANT %s" % expect)))
    print("== selftest: %s ==" % ("ALL ROUTED CORRECTLY" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Email Engine library matcher CLI (Skill 50).")
    ap.add_argument("--catalog", default=DEFAULT_CATALOG, help="path to catalog-index.json")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--build-index", nargs="?", const=DEFAULT_BUILT, metavar="OUT",
                   help="normalise the catalog into a built index")
    g.add_argument("--match", metavar="TEXT", help="match a free-text request")
    g.add_argument("--selftest", action="store_true", help="route corpus examples (fail-closed)")
    ap.add_argument("--type", dest="type_filter", default=None, help="optional type filter for --match")
    args = ap.parse_args(argv)

    if args.selftest:
        return cmd_selftest(args.catalog)
    if args.build_index is not None:
        return cmd_build_index(args.catalog, args.build_index)
    if args.match:
        return cmd_match(args.catalog, args.match, args.type_filter)
    ap.error("no command")


if __name__ == "__main__":
    sys.exit(main())
