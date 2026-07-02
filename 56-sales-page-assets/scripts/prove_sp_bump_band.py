#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sp_bump_band.py — fail-closed prover for the Direct-Response BUMP-SALE copy
(Skill 56). Enforces the order-bump band: 40-80 body words, ENDING with the checkbox close
line ('[X] Yes, add this to my order' / '[ ] ...'). This is the one legacy asset the n8n
engine wrote WITHOUT a sanitizer pass (ANALYSIS §7.7); here it is machine-gated. The body
word count EXCLUDES the checkbox close line (the engine's examples count 72/68/76 body words
with the checkbox on a separate line). NO AI, stdlib only.

WHAT IT ENFORCES:
  * a BUMP asset exists (else fail-closed).                      -> AF-SP56-BUMP-EMPTY
  * the last non-empty line is a checkbox close line.            -> AF-SP56-BUMP-NO-CHECKBOX
  * body word count (checkbox line excluded) >= 40.              -> AF-SP56-BUMP-FLOOR
  * body word count (checkbox line excluded) <= 80.              -> AF-SP56-BUMP-CEILING

Word band bounds + checkbox pattern are read from
structure/sales_page_structure.json > bump so the SACRED band lives in one place.

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

AF_EMPTY = "AF-SP56-BUMP-EMPTY"
AF_CHECKBOX = "AF-SP56-BUMP-NO-CHECKBOX"
AF_FLOOR = "AF-SP56-BUMP-FLOOR"
AF_CEILING = "AF-SP56-BUMP-CEILING"

STAGE = "bump"

_SCRIPT_DIR = Path(__file__).resolve().parent
STRUCTURE = _SCRIPT_DIR.parent / "structure" / "sales_page_structure.json"

_DEFAULT_CHECKBOX_RX = re.compile(r"^\s*\[[ xX]\]\s+.+")


def _band_and_checkbox() -> Tuple[int, int, re.Pattern]:
    try:
        data = json.loads(STRUCTURE.read_text(encoding="utf-8"))
        b = data[STAGE]["word_band"]
        pat = data[STAGE].get("checkbox_pattern")
        rx = re.compile(pat) if pat else _DEFAULT_CHECKBOX_RX
        return int(b["min"]), int(b["max"]), rx
    except Exception:  # noqa: BLE001 — fail-closed to spec constants
        return 40, 80, _DEFAULT_CHECKBOX_RX


def _asset_text(asset: Dict[str, Any]) -> str:
    for k in ("text", "copy", "body", "markdown"):
        if asset.get(k):
            return str(asset[k])
    return ""


def _assets_for_stage(ledger: Any) -> List[Dict[str, Any]]:
    items = ledger.get("assets") if isinstance(ledger, dict) else None
    if items is None and isinstance(ledger, dict):
        items = ledger.get("pages")
    if not isinstance(items, list):
        return []
    return [a for a in items if isinstance(a, dict)
            and re.sub(r"\s+", "", str(a.get("stage") or "")).lower() == STAGE]


def _split_body_and_checkbox(text: str, rx: re.Pattern) -> Tuple[str, bool]:
    lines = text.splitlines()
    nonempty = [(i, ln) for i, ln in enumerate(lines) if ln.strip()]
    if not nonempty:
        return "", False
    last_i, last_ln = nonempty[-1]
    if rx.match(last_ln):
        body_lines = [ln for i, ln in enumerate(lines) if i != last_i]
        return "\n".join(body_lines), True
    return text, False


def _word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text.strip()) if w])


def evaluate(ledger: Any) -> List[Tuple[str, str]]:
    if not isinstance(ledger, dict):
        return [(AF_EMPTY, "ledger root is not a JSON object")]
    lo, hi, rx = _band_and_checkbox()
    assets = _assets_for_stage(ledger)
    if not assets:
        return [(AF_EMPTY, "no BUMP-stage asset in the ledger (cannot prove band; fail-closed)")]

    fails: List[Tuple[str, str]] = []
    for a in assets:
        key = a.get("asset_key", "<bump>")
        text = _asset_text(a)
        body, has_cb = _split_body_and_checkbox(text, rx)
        if not has_cb:
            fails.append((AF_CHECKBOX, f"{key}: last non-empty line is not a checkbox close ('[X] Yes, add this to my order')"))
        wc = _word_count(body)
        if wc < lo:
            fails.append((AF_FLOOR, f"{key}: {wc} body words < floor {lo}"))
        elif wc > hi:
            fails.append((AF_CEILING, f"{key}: {wc} body words > ceiling {hi}"))
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
    lo, hi, _ = _band_and_checkbox()
    if as_json:
        print(json.dumps({"gate": "sales-page-assets-bump-band", "band": [lo, hi],
                          "source": source, "pass": not failures,
                          "failures": [{"code": c, "message": m} for c, m in failures]}, indent=2))
        return
    print(f"== Sales Page Assets :: BUMP band [{lo}, {hi}] words + checkbox close ==")
    print(f"source: {source}")
    if not failures:
        print("RESULT: PASS — bump copy is in band and ends with the checkbox close line.")
        return
    print(f"RESULT: FAIL (fail-closed) — {len(failures)} violation(s):")
    for code, msg in failures:
        print(f"  [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test.
# ---------------------------------------------------------------------------
def _bump(nbody: int, checkbox: bool = True) -> Dict[str, Any]:
    body = " ".join(f"w{i}" for i in range(nbody))
    text = body + ("\n\n[X] Yes, add this to my order for $47" if checkbox else "")
    return {"stage": "bump", "type": "copy",
            "asset_key": "jane-doe__glow-method__bump__copy__v01", "text": text}


def _valid_ledger() -> Dict[str, Any]:
    return {"assets": [_bump(60)]}


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
        print(f"  [{'PASS' if good else 'MISS'}] VIOLATION {name:20s} -> codes={codes} (want {expect})")

    lo, hi, _ = _band_and_checkbox()
    print(f"== self-test: band [{lo},{hi}] — VALID fixtures (must PASS) ==")
    check_pass("mid-band-60", _valid_ledger())
    check_pass("floor-exact", {"assets": [_bump(lo)]})
    check_pass("ceiling-exact", {"assets": [_bump(hi)]})

    print("== self-test: VIOLATION fixtures (must FAIL) ==")
    check_fail("under-floor", {"assets": [_bump(lo - 1)]}, AF_FLOOR)
    check_fail("over-ceiling", {"assets": [_bump(hi + 1)]}, AF_CEILING)
    check_fail("no-checkbox", {"assets": [_bump(60, checkbox=False)]}, AF_CHECKBOX)
    check_fail("empty-ledger", {"assets": []}, AF_EMPTY)

    print("== self-test:", "ALL ASSERTIONS PASSED ==" if ok else "FAILED ==")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed prover for the BUMP-SALE band + checkbox close.")
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
