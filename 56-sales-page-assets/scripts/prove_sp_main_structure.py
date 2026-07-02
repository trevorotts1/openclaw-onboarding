#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sp_main_structure.py — fail-closed prover for the Direct-Response MAIN sales page
(Skill 56). Enforces the "Advanced Sales Page Creation Instructions" 8-SECTION structure,
in order, for BOTH A/B variants, with the mandated countdown timer. NO AI, stdlib only.

Canonical 8 sections (verbatim from the engine, structure/sales_page_structure.json > main):
  1 header (attention-grabbing / notification banner)  2 hero  3 problem-solution
  4 benefits  5 product-details  6 credibility  7 final-cta  8 footer

WHAT IT ENFORCES (measuring the declared section ledger, ignoring any self-report):
  * a MAIN asset exists for BOTH variants a and b.               -> AF-SP56-MAIN-VARIANT-MISSING
  * each variant declares exactly 8 sections.                    -> AF-SP56-MAIN-SECTION-COUNT
  * every canonical section is present.                          -> AF-SP56-MAIN-SECTION-MISSING
  * no section outside the canonical set.                        -> AF-SP56-MAIN-SECTION-UNKNOWN
  * sections are in canonical ascending order.                   -> AF-SP56-MAIN-SECTION-ORDER
  * a countdown timer is present (has_countdown_timer OR the
    fragment carries countdown JS).                              -> AF-SP56-MAIN-NO-COUNTDOWN
  * at least one MAIN asset exists (else fail-closed).           -> AF-SP56-MAIN-EMPTY

stdlib only. Exit 0 = pass, exit 2 = autofail, exit 3 = usage/IO (still fail-closed).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_VARIANT = "AF-SP56-MAIN-VARIANT-MISSING"
AF_COUNT = "AF-SP56-MAIN-SECTION-COUNT"
AF_MISSING = "AF-SP56-MAIN-SECTION-MISSING"
AF_UNKNOWN = "AF-SP56-MAIN-SECTION-UNKNOWN"
AF_ORDER = "AF-SP56-MAIN-SECTION-ORDER"
AF_COUNTDOWN = "AF-SP56-MAIN-NO-COUNTDOWN"
AF_EMPTY = "AF-SP56-MAIN-EMPTY"

STAGE = "main"
REQUIRED_VARIANTS = ("a", "b")

_SCRIPT_DIR = Path(__file__).resolve().parent
STRUCTURE = _SCRIPT_DIR.parent / "structure" / "sales_page_structure.json"

# Countdown-timer signatures used when an asset ships an HTML fragment instead of a flag.
_COUNTDOWN_RX = re.compile(r"countdown|setinterval|data-countdown|gettime\(\)|timer", re.I)


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _load_canonical() -> List[Dict[str, Any]]:
    data = json.loads(STRUCTURE.read_text(encoding="utf-8"))
    return data[STAGE]["sections"]


def _match_section(name: str, canon: List[Dict[str, Any]]) -> Optional[str]:
    """Resolve a declared section name to a canonical id, or None if unknown."""
    n = _norm(name)
    if not n:
        return None
    for sec in canon:
        cid = sec["id"]
        if n == cid or n == _norm(sec.get("id")):
            return cid
        for alias in sec.get("aliases", []):
            a = _norm(alias)
            if n == a or a in n or n in a:
                return cid
    return None


def _assets_for_stage(ledger: Any) -> List[Dict[str, Any]]:
    items = ledger.get("assets") if isinstance(ledger, dict) else None
    if items is None and isinstance(ledger, dict):
        items = ledger.get("pages")
    if not isinstance(items, list):
        return []
    return [a for a in items if isinstance(a, dict) and _norm(a.get("stage")) == STAGE]


def _has_countdown(asset: Dict[str, Any]) -> bool:
    if asset.get("has_countdown_timer") is True:
        return True
    blob = asset.get("html") or asset.get("fragment") or ""
    return bool(_COUNTDOWN_RX.search(str(blob)))


def _verify_variant(asset: Dict[str, Any], canon: List[Dict[str, Any]], vlabel: str) -> List[Tuple[str, str]]:
    fails: List[Tuple[str, str]] = []
    secs = asset.get("sections")
    if not isinstance(secs, list) or not secs:
        return [(AF_MISSING, f"variant {vlabel}: no sections declared")]

    resolved: List[str] = []
    for s in secs:
        name = s.get("name") if isinstance(s, dict) else s
        cid = _match_section(name, canon)
        if cid is None:
            fails.append((AF_UNKNOWN, f"variant {vlabel}: section {name!r} matches no canonical main section"))
        else:
            resolved.append(cid)

    canon_ids = [c["id"] for c in canon]
    if len(secs) != len(canon_ids):
        fails.append((AF_COUNT, f"variant {vlabel}: {len(secs)} sections, expected {len(canon_ids)}"))

    seen = set(resolved)
    for cid in canon_ids:
        if cid not in seen:
            fails.append((AF_MISSING, f"variant {vlabel}: canonical section {cid!r} absent"))

    # order: the resolved canonical ids (dedup, first-seen) must equal canonical order
    firstseen: List[str] = []
    for cid in resolved:
        if cid not in firstseen:
            firstseen.append(cid)
    if firstseen != [c for c in canon_ids if c in seen]:
        fails.append((AF_ORDER, f"variant {vlabel}: sections not in canonical order (got {firstseen})"))

    if not _has_countdown(asset):
        fails.append((AF_COUNTDOWN, f"variant {vlabel}: mandated countdown timer absent"))
    return fails


def evaluate(ledger: Any) -> List[Tuple[str, str]]:
    if not isinstance(ledger, dict):
        return [(AF_EMPTY, "ledger root is not a JSON object")]
    canon = _load_canonical()
    assets = _assets_for_stage(ledger)
    if not assets:
        return [(AF_EMPTY, "no MAIN-stage assets in the ledger (cannot prove structure; fail-closed)")]

    fails: List[Tuple[str, str]] = []
    by_variant: Dict[str, Dict[str, Any]] = {}
    for a in assets:
        by_variant[_norm(a.get("variant"))] = a

    for v in REQUIRED_VARIANTS:
        if v not in by_variant:
            fails.append((AF_VARIANT, f"MAIN variant {v!r} missing (both a and b are required)"))
            continue
        fails.extend(_verify_variant(by_variant[v], canon, v))
    return fails


def decide_exit(failures) -> int:
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


def prove(path: str, as_json: bool = False) -> int:
    p = Path(path)
    if not p.is_file():
        _emit(str(p), [("USAGE", f"ledger not found: {p}")], as_json)
        return EXIT_USAGE
    try:
        ledger = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        _emit(str(p), [("USAGE", f"cannot read/parse ledger JSON: {exc}")], as_json)
        return EXIT_USAGE
    failures = evaluate(ledger)
    _emit(str(p), failures, as_json)
    return decide_exit(failures)


def _emit(source: str, failures, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"gate": "sales-page-assets-main-structure", "source": source,
                          "pass": not failures,
                          "failures": [{"code": c, "message": m} for c, m in failures]}, indent=2))
        return
    print("== Sales Page Assets :: MAIN 8-section structure ==")
    print(f"source: {source}")
    if not failures:
        print("RESULT: PASS — both variants carry the 8 canonical sections in order + countdown timer.")
        return
    print(f"RESULT: FAIL (fail-closed) — {len(failures)} violation(s):")
    for code, msg in failures:
        print(f"  [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test.
# ---------------------------------------------------------------------------
_CANON_ORDER = ["Attention-Grabbing Header", "Hero Section", "Problem & Solution",
                "Benefits Section", "Product Details", "Credibility Section",
                "Final Call to Action", "Footer"]


def _valid_main_asset(variant: str) -> Dict[str, Any]:
    return {
        "stage": "main", "variant": variant, "type": "page",
        "asset_key": f"jane-doe__glow-method__main__page__v01{variant}",
        "has_countdown_timer": True,
        "sections": [{"order": i + 1, "name": nm} for i, nm in enumerate(_CANON_ORDER)],
    }


def _valid_ledger() -> Dict[str, Any]:
    return {"assets": [_valid_main_asset("a"), _valid_main_asset("b")]}


def self_test() -> int:
    ok = True

    def check_pass(name, fixture):
        nonlocal ok
        fails = evaluate(fixture)
        good = not fails
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VALID {name:16s} -> exit {decide_exit(fails)}"
              + ("" if good else f" (unexpected: {fails})"))

    def check_fail(name, fixture, expect):
        nonlocal ok
        fails = evaluate(fixture)
        codes = [c for c, _ in fails]
        good = bool(fails) and expect in codes
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VIOLATION {name:22s} -> codes={codes} (want {expect})")

    print("== self-test: VALID fixtures (must PASS) ==")
    check_pass("both-variants", _valid_ledger())

    print("== self-test: VIOLATION fixtures (must FAIL) ==")
    f = _valid_ledger(); f["assets"] = [f["assets"][0]]
    check_fail("only-variant-a", f, AF_VARIANT)

    f = _valid_ledger(); f["assets"][0]["sections"] = f["assets"][0]["sections"][:7]
    check_fail("seven-sections", f, AF_COUNT)

    f = _valid_ledger()
    f["assets"][1]["sections"] = [{"order": i + 1, "name": nm} for i, nm in enumerate(
        ["Attention-Grabbing Header", "Hero Section", "Benefits Section", "Problem & Solution",
         "Product Details", "Credibility Section", "Final Call to Action", "Footer"])]
    check_fail("swapped-order", f, AF_ORDER)

    f = _valid_ledger(); f["assets"][0]["sections"][5] = {"order": 6, "name": "Bonus Stack"}
    check_fail("unknown-section", f, AF_UNKNOWN)

    f = _valid_ledger(); f["assets"][1]["has_countdown_timer"] = False
    check_fail("no-countdown", f, AF_COUNTDOWN)

    f = {"assets": []}
    check_fail("empty-ledger", f, AF_EMPTY)

    print("== self-test:", "ALL ASSERTIONS PASSED ==" if ok else "FAILED ==")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed prover for the MAIN 8-section structure.")
    ap.add_argument("--ledger", help="path to copy_ledger.json")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON output")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in VALID + VIOLATION fixtures and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.ledger:
        print("USAGE ERROR: pass --ledger <copy_ledger.json> (or --self-test).")
        return EXIT_USAGE
    return prove(args.ledger, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
