#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sp_upsell_structure.py — fail-closed prover for the Direct-Response UPSELL page
(Skill 56). Enforces the Trevor Otts 9-SECTION Upsell Framework, in order, for BOTH A/B
variants (variant a = conversion copywriter persona; variant b = "Emotional Hijacking
Expert" persona). NO AI, stdlib only.

Canonical 9 sections (verbatim from the engine, structure/sales_page_structure.json > upsell-1):
  1 hook (acknowledge purchase + upgrade opportunity)  2 pain-1  3 pain-2  4 pain-3
  5 hope  6 solution  7 value-stack  8 logical-justification (founder credibility)
  9 identity-challenge (close)

WHAT IT ENFORCES (measuring the declared section ledger, ignoring any self-report):
  * an UPSELL asset exists for BOTH variants a and b.            -> AF-SP56-UPSELL-VARIANT-MISSING
  * each variant declares exactly 9 sections.                   -> AF-SP56-UPSELL-SECTION-COUNT
  * every canonical section is present.                         -> AF-SP56-UPSELL-SECTION-MISSING
  * no section outside the canonical set.                       -> AF-SP56-UPSELL-SECTION-UNKNOWN
  * sections are in the exact Trevor Otts order.               -> AF-SP56-UPSELL-SECTION-ORDER
  * at least one UPSELL asset exists (else fail-closed).        -> AF-SP56-UPSELL-EMPTY

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

AF_VARIANT = "AF-SP56-UPSELL-VARIANT-MISSING"
AF_COUNT = "AF-SP56-UPSELL-SECTION-COUNT"
AF_MISSING = "AF-SP56-UPSELL-SECTION-MISSING"
AF_UNKNOWN = "AF-SP56-UPSELL-SECTION-UNKNOWN"
AF_ORDER = "AF-SP56-UPSELL-SECTION-ORDER"
AF_EMPTY = "AF-SP56-UPSELL-EMPTY"

STAGE = "upsell-1"
REQUIRED_VARIANTS = ("a", "b")

_SCRIPT_DIR = Path(__file__).resolve().parent
STRUCTURE = _SCRIPT_DIR.parent / "structure" / "sales_page_structure.json"


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _load_canonical() -> List[Dict[str, Any]]:
    data = json.loads(STRUCTURE.read_text(encoding="utf-8"))
    return data[STAGE]["sections"]


def _match_section(name: str, canon: List[Dict[str, Any]]) -> Optional[str]:
    n = _norm(name)
    if not n:
        return None
    # exact id / alias first (prevents 'pain 1' vs 'pain 2' collisions before substring)
    for sec in canon:
        if n == sec["id"] or any(n == _norm(a) for a in sec.get("aliases", [])):
            return sec["id"]
    for sec in canon:
        for alias in sec.get("aliases", []):
            a = _norm(alias)
            if a and (a in n or n in a):
                return sec["id"]
    return None


def _assets_for_stage(ledger: Any) -> List[Dict[str, Any]]:
    items = ledger.get("assets") if isinstance(ledger, dict) else None
    if items is None and isinstance(ledger, dict):
        items = ledger.get("pages")
    if not isinstance(items, list):
        return []
    return [a for a in items if isinstance(a, dict) and _norm(a.get("stage")) == STAGE]


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
            fails.append((AF_UNKNOWN, f"variant {vlabel}: section {name!r} matches no canonical upsell section"))
        else:
            resolved.append(cid)

    canon_ids = [c["id"] for c in canon]
    if len(secs) != len(canon_ids):
        fails.append((AF_COUNT, f"variant {vlabel}: {len(secs)} sections, expected {len(canon_ids)}"))

    seen = set(resolved)
    for cid in canon_ids:
        if cid not in seen:
            fails.append((AF_MISSING, f"variant {vlabel}: canonical section {cid!r} absent"))

    firstseen: List[str] = []
    for cid in resolved:
        if cid not in firstseen:
            firstseen.append(cid)
    if firstseen != [c for c in canon_ids if c in seen]:
        fails.append((AF_ORDER, f"variant {vlabel}: sections not in Trevor Otts order (got {firstseen})"))
    return fails


def evaluate(ledger: Any) -> List[Tuple[str, str]]:
    if not isinstance(ledger, dict):
        return [(AF_EMPTY, "ledger root is not a JSON object")]
    canon = _load_canonical()
    assets = _assets_for_stage(ledger)
    if not assets:
        return [(AF_EMPTY, "no UPSELL-stage assets in the ledger (cannot prove structure; fail-closed)")]

    fails: List[Tuple[str, str]] = []
    by_variant: Dict[str, Dict[str, Any]] = {}
    for a in assets:
        by_variant[_norm(a.get("variant"))] = a

    for v in REQUIRED_VARIANTS:
        if v not in by_variant:
            fails.append((AF_VARIANT, f"UPSELL variant {v!r} missing (both a and b are required)"))
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
        print(json.dumps({"gate": "sales-page-assets-upsell-structure", "source": source,
                          "pass": not failures,
                          "failures": [{"code": c, "message": m} for c, m in failures]}, indent=2))
        return
    print("== Sales Page Assets :: UPSELL 9-section (Trevor Otts) structure ==")
    print(f"source: {source}")
    if not failures:
        print("RESULT: PASS — both variants carry the 9 Trevor Otts sections in order.")
        return
    print(f"RESULT: FAIL (fail-closed) — {len(failures)} violation(s):")
    for code, msg in failures:
        print(f"  [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test.
# ---------------------------------------------------------------------------
_CANON_ORDER = ["Hook acknowledging purchase", "First pain point", "Second pain point amplification",
                "Third pain point with urgency", "Hope introduction", "Solution positioning",
                "Value stacking presentation", "Logical justification with founder credibility",
                "Identity challenge close"]


def _valid_upsell_asset(variant: str) -> Dict[str, Any]:
    return {
        "stage": "upsell-1", "variant": variant, "type": "page",
        "asset_key": f"jane-doe__glow-method__upsell-1__page__v01{variant}",
        "sections": [{"order": i + 1, "name": nm} for i, nm in enumerate(_CANON_ORDER)],
    }


def _valid_ledger() -> Dict[str, Any]:
    return {"assets": [_valid_upsell_asset("a"), _valid_upsell_asset("b")]}


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
    f = _valid_ledger(); f["assets"] = [f["assets"][1]]
    check_fail("only-variant-b", f, AF_VARIANT)

    f = _valid_ledger(); f["assets"][0]["sections"] = f["assets"][0]["sections"][:8]
    check_fail("eight-sections", f, AF_COUNT)

    f = _valid_ledger()
    swap = list(_CANON_ORDER)
    swap[4], swap[5] = swap[5], swap[4]  # hope <-> solution
    f["assets"][1]["sections"] = [{"order": i + 1, "name": nm} for i, nm in enumerate(swap)]
    check_fail("hope-solution-swapped", f, AF_ORDER)

    f = _valid_ledger(); f["assets"][0]["sections"][6] = {"order": 7, "name": "Bonus Vault"}
    check_fail("unknown-section", f, AF_UNKNOWN)

    f = {"assets": []}
    check_fail("empty-ledger", f, AF_EMPTY)

    print("== self-test:", "ALL ASSERTIONS PASSED ==" if ok else "FAILED ==")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed prover for the UPSELL 9-section structure.")
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
