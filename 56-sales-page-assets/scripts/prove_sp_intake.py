#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sp_intake.py — fail-closed deterministic prover for the Sales Page Assets intake
gate (Skill 56). NO AI, NO network, stdlib only.

WHAT IT ENFORCES (the locked, provenance-gated brief that unlocks generation):
  * funnel_type == "sales_page_assets".                          -> AF-SP56-INTAKE-TYPE
  * every REQUIRED intake answer is present + non-empty (the 12-field contract,
    sane keys — legacy embedded-space keys repaired).            -> AF-SP56-INTAKE-MISSING
  * image_prompt_count is an int in [1,20].                      -> AF-SP56-INTAKE-IMGCOUNT
  * offer_token_ledger is non-empty — the declared offer name(s) the bundle +
    delivery gates depend on.                                    -> AF-SP56-INTAKE-OFFER
  * client_slug + funnel_slug are present kebab slugs (labeling grammar seed).
                                                                 -> AF-SP56-INTAKE-SLUG
  * the brief is LOCKED (provenance-gated) before generation.    -> AF-SP56-INTAKE-UNLOCKED

The prover reads either the runtime brief (an `answers` object) or the schema spec
(intake/spa-intake.schema.json, a `fields` list). Both resolve through one model.

stdlib only. Exit 0 = pass, exit 2 = autofail, exit 3 = usage/IO (still fail-closed).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_TYPE = "AF-SP56-INTAKE-TYPE"
AF_MISSING = "AF-SP56-INTAKE-MISSING"
AF_IMGCOUNT = "AF-SP56-INTAKE-IMGCOUNT"
AF_OFFER = "AF-SP56-INTAKE-OFFER"
AF_SLUG = "AF-SP56-INTAKE-SLUG"
AF_UNLOCKED = "AF-SP56-INTAKE-UNLOCKED"

FUNNEL_TYPE = "sales_page_assets"

# The 12-field contract (sane keys — the legacy 'Sales_Page_Writer_Product _Info' and
# 'upsellOneProductDescription ' embedded-space keys are repaired to product_info / upsell_desc).
REQUIRED_ANSWERS = (
    "brand_info", "product_info", "primary_brand_color", "brand_logo",
    "image_prompt_count", "upsell_desc", "downsell_desc", "bump_desc",
    "high_ticket_desc", "first_name", "last_name", "email",
)

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

_SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INTAKE = _SCRIPT_DIR.parent / "intake" / "spa-intake.schema.json"


def _nonempty_str(v: Any) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _answered(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, tuple, dict)):
        return len(v) > 0
    if isinstance(v, bool):
        return True
    return True  # ints (e.g. image_prompt_count) count as answered


def evaluate(intake: Any) -> List[Tuple[str, str]]:
    failures: List[Tuple[str, str]] = []
    if not isinstance(intake, dict):
        return [(AF_TYPE, "intake root is not a JSON object")]

    ftype = intake.get("funnel_type")
    if ftype is not None and ftype != FUNNEL_TYPE:
        failures.append((AF_TYPE, f"funnel_type is {ftype!r}, expected {FUNNEL_TYPE!r}"))

    answers = intake.get("answers")
    if isinstance(answers, dict):
        # runtime brief shape — the full locked-brief gate applies.
        missing = [q for q in REQUIRED_ANSWERS if not _answered(answers.get(q))]
        if missing:
            failures.append((AF_MISSING, "missing/empty required answers: " + ", ".join(missing)))

        ic = answers.get("image_prompt_count")
        if isinstance(ic, bool) or not isinstance(ic, int) or not (1 <= ic <= 20):
            failures.append((AF_IMGCOUNT, f"image_prompt_count must be an int in [1,20], got {ic!r}"))

        ledger = intake.get("offer_token_ledger")
        if not (isinstance(ledger, list) and any(_nonempty_str(x) for x in ledger)):
            failures.append((AF_OFFER, "offer_token_ledger missing/empty — offer name(s) not declared"))

        cs, fs = intake.get("client_slug"), intake.get("funnel_slug")
        if not (_nonempty_str(cs) and SLUG_RE.match(cs.strip())):
            failures.append((AF_SLUG, f"client_slug missing/not a kebab slug: {cs!r}"))
        if not (_nonempty_str(fs) and SLUG_RE.match(fs.strip())):
            failures.append((AF_SLUG, f"funnel_slug missing/not a kebab slug: {fs!r}"))

        if intake.get("locked") is not True:
            failures.append((AF_UNLOCKED, "brief is not locked (provenance-gated) — generation must not start"))
    else:
        # spec-contract shape: every required field must be defined with an 'asks'.
        defined = {}
        fields = intake.get("fields")
        if isinstance(fields, list):
            for item in fields:
                if isinstance(item, dict):
                    defined[item.get("key")] = item.get("asks")
        missing = [q for q in REQUIRED_ANSWERS if not _nonempty_str(defined.get(q))]
        if missing:
            failures.append((AF_MISSING, "spec is missing field definitions: " + ", ".join(missing)))

    return failures


def decide_exit(failures) -> int:
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


def prove(path: str, as_json: bool = False) -> int:
    p = Path(path)
    if not p.is_file():
        _emit(str(p), [("USAGE", f"intake file not found: {p}")], as_json)
        return EXIT_USAGE
    try:
        intake = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        _emit(str(p), [("USAGE", f"cannot read/parse intake JSON: {exc}")], as_json)
        return EXIT_USAGE
    failures = evaluate(intake)
    _emit(str(p), failures, as_json)
    return decide_exit(failures)


def _emit(source: str, failures, as_json: bool) -> None:
    if as_json:
        print(json.dumps({
            "gate": "sales-page-assets-intake",
            "source": source,
            "pass": not failures,
            "failures": [{"code": c, "message": m} for c, m in failures],
        }, indent=2))
        return
    print("== Sales Page Assets :: intake gate ==")
    print(f"source: {source}")
    if not failures:
        print("RESULT: PASS — locked brief satisfies the intake gate; generation may unlock.")
        return
    print(f"RESULT: FAIL (fail-closed) — {len(failures)} violation(s):")
    for code, msg in failures:
        print(f"  [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test.
# ---------------------------------------------------------------------------
def _valid_runtime() -> Dict[str, Any]:
    return {
        "funnel_type": "sales_page_assets",
        "locked": True,
        "client_slug": "jane-doe",
        "funnel_slug": "glow-method",
        "offer_token_ledger": ["The Glow Method", "Glow Accelerator"],
        "answers": {
            "brand_info": "Glow Method — skincare rituals for busy founders; calm, premium voice.",
            "product_info": "The Glow Method course, $97, CTA https://example.com/checkout",
            "primary_brand_color": "#0B6E4F",
            "brand_logo": "https://example.com/logo.png",
            "image_prompt_count": 12,
            "upsell_desc": "Glow Accelerator done-with-you sprint, $197",
            "downsell_desc": "Glow recordings-only tier, $47",
            "bump_desc": "The 5-minute glow audio, $27",
            "high_ticket_desc": "Glow Sovereign 1:1 mentorship, $5,000",
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
        },
    }


def self_test() -> int:
    ok = True

    def check_pass(name, fixture):
        nonlocal ok
        fails = evaluate(fixture)
        good = not fails and decide_exit(fails) == EXIT_PASS
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VALID {name:16s} -> exit {decide_exit(fails)}"
              + ("" if good else f" (unexpected: {fails})"))

    def check_fail(name, fixture, expect):
        nonlocal ok
        fails = evaluate(fixture)
        codes = [c for c, _ in fails]
        good = bool(fails) and expect in codes
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VIOLATION {name:20s} -> codes={codes} (want {expect})")

    print("== self-test: VALID fixtures (must PASS) ==")
    check_pass("runtime-brief", _valid_runtime())

    print("== self-test: VIOLATION fixtures (must FAIL) ==")
    f = _valid_runtime(); f["funnel_type"] = "signature_funnel"
    check_fail("type-mismatch", f, AF_TYPE)

    f = _valid_runtime(); del f["answers"]["bump_desc"]
    check_fail("missing-answer", f, AF_MISSING)

    f = _valid_runtime(); f["answers"]["image_prompt_count"] = 0
    check_fail("img-count-zero", f, AF_IMGCOUNT)

    f = _valid_runtime(); f["answers"]["image_prompt_count"] = 21
    check_fail("img-count-over", f, AF_IMGCOUNT)

    f = _valid_runtime(); f["offer_token_ledger"] = []
    check_fail("empty-offer", f, AF_OFFER)

    f = _valid_runtime(); f["client_slug"] = "Jane Doe"
    check_fail("bad-client-slug", f, AF_SLUG)

    f = _valid_runtime(); f["locked"] = False
    check_fail("brief-unlocked", f, AF_UNLOCKED)

    print("== self-test:", "ALL ASSERTIONS PASSED ==" if ok else "FAILED ==")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Fail-closed prover for the Sales Page Assets intake gate.")
    ap.add_argument("intake", nargs="?", default=str(DEFAULT_INTAKE),
                    help="path to the intake/brief JSON (default: intake/spa-intake.schema.json)")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON output")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in VALID + VIOLATION fixtures and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    return prove(args.intake, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
