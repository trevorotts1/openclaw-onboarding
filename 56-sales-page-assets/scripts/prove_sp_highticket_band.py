#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sp_highticket_band.py — fail-closed prover for the Direct-Response HIGH-TICKET
long-form page (Skill 56). Enforces the "Sovereign Architect" word band: the STRIPPED word
count must land in [6,500, 7,100] words (the engine's spec for $1k-$25k+ ascension pages).
NO AI, stdlib only. The prover measures STRIPPED text and IGNORES any self-reported count.

WHAT IT ENFORCES:
  * a HIGH-TICKET asset exists (else fail-closed).               -> AF-SP56-HIGHTICKET-EMPTY
  * stripped word count >= 6,500.                                -> AF-SP56-HIGHTICKET-FLOOR
  * stripped word count <= 7,100.                                -> AF-SP56-HIGHTICKET-CEILING

Word band bounds are read from structure/sales_page_structure.json > high-ticket.word_band
so the SACRED band lives in one place.

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

AF_EMPTY = "AF-SP56-HIGHTICKET-EMPTY"
AF_FLOOR = "AF-SP56-HIGHTICKET-FLOOR"
AF_CEILING = "AF-SP56-HIGHTICKET-CEILING"

STAGE = "high-ticket"

_SCRIPT_DIR = Path(__file__).resolve().parent
STRUCTURE = _SCRIPT_DIR.parent / "structure" / "sales_page_structure.json"

_SCRIPT_RX = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_TAG_RX = re.compile(r"<[^>]+>")
_HTML_ENTITY_RX = re.compile(r"&[#a-zA-Z0-9]+;")


def _band() -> Tuple[int, int]:
    try:
        data = json.loads(STRUCTURE.read_text(encoding="utf-8"))
        b = data[STAGE]["word_band"]
        return int(b["min"]), int(b["max"])
    except Exception:  # noqa: BLE001 — fail-closed to the spec constants
        return 6500, 7100


def strip_text(blob: Any) -> str:
    s = str(blob or "")
    s = _SCRIPT_RX.sub(" ", s)
    s = _TAG_RX.sub(" ", s)
    s = _HTML_ENTITY_RX.sub(" ", s)
    return s


def word_count(blob: Any) -> int:
    return len([w for w in re.split(r"\s+", strip_text(blob)) if w])


def _asset_text(asset: Dict[str, Any]) -> str:
    for k in ("text", "copy", "html", "fragment", "body"):
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
            and re.sub(r"[\s-]+", "", str(a.get("stage") or "")).lower() == STAGE.replace("-", "")]


def evaluate(ledger: Any) -> List[Tuple[str, str]]:
    if not isinstance(ledger, dict):
        return [(AF_EMPTY, "ledger root is not a JSON object")]
    lo, hi = _band()
    assets = _assets_for_stage(ledger)
    if not assets:
        return [(AF_EMPTY, "no HIGH-TICKET-stage asset in the ledger (cannot prove band; fail-closed)")]

    fails: List[Tuple[str, str]] = []
    for a in assets:
        wc = word_count(_asset_text(a))
        key = a.get("asset_key", "<high-ticket>")
        if wc < lo:
            fails.append((AF_FLOOR, f"{key}: {wc} stripped words < floor {lo}"))
        elif wc > hi:
            fails.append((AF_CEILING, f"{key}: {wc} stripped words > ceiling {hi}"))
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
    lo, hi = _band()
    if as_json:
        print(json.dumps({"gate": "sales-page-assets-highticket-band", "band": [lo, hi],
                          "source": source, "pass": not failures,
                          "failures": [{"code": c, "message": m} for c, m in failures]}, indent=2))
        return
    print(f"== Sales Page Assets :: HIGH-TICKET word band [{lo}, {hi}] ==")
    print(f"source: {source}")
    if not failures:
        print("RESULT: PASS — high-ticket long-form page is within the Sovereign Architect band.")
        return
    print(f"RESULT: FAIL (fail-closed) — {len(failures)} violation(s):")
    for code, msg in failures:
        print(f"  [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test.
# ---------------------------------------------------------------------------
def _asset_with_words(n: int) -> Dict[str, Any]:
    # deterministic distinct-ish body of n words wrapped in HTML (proves stripping).
    body = " ".join(f"word{i}" for i in range(n))
    # style/script blocks + tags are stripped and MUST NOT contribute words, so the
    # measured count equals exactly n (proves the stripper).
    return {"stage": "high-ticket", "type": "page",
            "asset_key": "jane-doe__glow-method__high-ticket__page__v01",
            "html": f"<html><head><style>.x{{color:red}}</style></head><body><p>{body}</p>"
                    f"<script>var t=setInterval(function(){{}},1000);</script></body></html>"}


def _valid_ledger() -> Dict[str, Any]:
    return {"assets": [_asset_with_words(6800)]}


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

    lo, hi = _band()
    print(f"== self-test: band [{lo},{hi}] — VALID fixtures (must PASS) ==")
    check_pass("mid-band-6800", _valid_ledger())
    check_pass("floor-exact", {"assets": [_asset_with_words(lo)]})
    check_pass("ceiling-exact", {"assets": [_asset_with_words(hi)]})

    print("== self-test: VIOLATION fixtures (must FAIL) ==")
    check_fail("under-floor", {"assets": [_asset_with_words(lo - 1)]}, AF_FLOOR)
    check_fail("over-ceiling", {"assets": [_asset_with_words(hi + 1)]}, AF_CEILING)
    check_fail("padded-1000", {"assets": [_asset_with_words(1000)]}, AF_FLOOR)
    check_fail("empty-ledger", {"assets": []}, AF_EMPTY)

    print("== self-test:", "ALL ASSERTIONS PASSED ==" if ok else "FAILED ==")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed prover for the HIGH-TICKET word band.")
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
