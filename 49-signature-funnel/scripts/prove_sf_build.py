#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sf_build.py — fail-closed P7-BUILD gate for the Signature Funnel.

FIX-XC-03a: P7-BUILD was an unconditional no-op (`_delegation_seam(..., None, ...)`) —
a certificate could mint with no build receipt and no proof the GHL funnel/page build
ever cleared QC. This prover requires a real `build_receipt.json` produced by the Skill 6
build rail and enforces the two documented invariants (FUNNEL-MANIFEST P7):
  * funnel-build QC score >= 8.5 (the OpenClaw QC threshold), MEASURED from the receipt
    and NEVER assumed — a missing/non-numeric/below-floor score FAILS.   -> AF-FUN-BUILD-QC
  * a non-empty http(s) preview URL for every built page (preview-only
    delivery still needs a real preview to hand to human approval).      -> AF-FUN-BUILD-PREVIEW

Fail-closed: an absent/unreadable/empty receipt is a FAIL, never a pass.  -> AF-FUN-BUILD-MALFORMED
funnel_type mismatch (when declared) also FAILS.                          -> AF-FUN-BUILD-TYPE

stdlib only. Exit 0 = pass, exit 2 = violation, exit 3 = usage / fail-closed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

FUNNEL_TYPE = "signature_funnel"
QC_FLOOR = 8.5  # OpenClaw QC Protocol threshold (>= 8.5 auto-approves)


def _preview_ok(url: Any) -> bool:
    return isinstance(url, str) and url.strip().lower().startswith(("http://", "https://"))


def verify(receipt: Dict[str, Any]) -> Tuple[List[Tuple[str, str]], List[str]]:
    fails: List[Tuple[str, str]] = []
    notes: List[str] = []

    def fail(code: str, msg: str) -> None:
        fails.append((code, msg))

    if not isinstance(receipt, dict):
        return [("AF-FUN-BUILD-MALFORMED", "build receipt is not a JSON object")], notes

    ftype = receipt.get("funnel_type")
    if ftype is not None and ftype != FUNNEL_TYPE:
        fail("AF-FUN-BUILD-TYPE", f"funnel_type is {ftype!r}, expected {FUNNEL_TYPE!r}")

    # QC score — measured, never assumed. bool is rejected (isinstance(True,int) guard).
    score = receipt.get("qc_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        fail("AF-FUN-BUILD-QC", f"qc_score is {score!r} — must be a number (fail-closed)")
    elif float(score) < QC_FLOOR:
        fail("AF-FUN-BUILD-QC", f"qc_score {float(score)} is below the {QC_FLOOR} funnel-build floor")

    pages = receipt.get("pages")
    if not isinstance(pages, list) or not pages:
        return [("AF-FUN-BUILD-MALFORMED",
                 "build receipt carries no non-empty 'pages' array (cannot prove a build)")] + fails, notes

    for i, pg in enumerate(pages):
        if not isinstance(pg, dict):
            fail("AF-FUN-BUILD-MALFORMED", f"page entry #{i} is not an object")
            continue
        who = str(pg.get("page_type") or pg.get("id") or f"#{i}")
        if not _preview_ok(pg.get("preview_url")):
            fail("AF-FUN-BUILD-PREVIEW",
                 f"page '{who}': preview_url {pg.get('preview_url')!r} is not a non-empty http(s) URL")

    notes.append(f"checked build receipt: qc_score={receipt.get('qc_score')!r} (floor {QC_FLOOR}), "
                 f"{len(pages)} page(s) with preview URLs")
    return fails, notes


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------
def _load_json(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def _report(violations, notes) -> None:
    for note in notes:
        print(f"NOTE: {note}")
    if not violations:
        print(f"PASS: funnel build receipt clears QC >= {QC_FLOOR} with a preview URL per page.")
        return
    print(f"FAIL: {len(violations)} build-receipt violation(s) — P7-BUILD does not clear.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test fixtures.
# ---------------------------------------------------------------------------
def _valid_receipt(size: int = 5) -> Dict[str, Any]:
    # a minimal, realistic receipt: main + one derived + thank-you, all built + previewed.
    stages = ["main", "upsell", "thank-you"]
    return {
        "funnel_type": FUNNEL_TYPE,
        "funnel_size": size,
        "qc_score": 9.1,
        "pages": [
            {"page_type": s, "status": "built",
             "preview_url": f"https://app.example-ghl.com/funnels/preview/{s}"}
            for s in stages
        ],
    }


def _violation_cases():
    def low_qc(r):
        r["qc_score"] = 7.9

    def missing_qc(r):
        r.pop("qc_score", None)

    def bool_qc(r):
        r["qc_score"] = True

    def empty_preview(r):
        r["pages"][1]["preview_url"] = ""

    def bad_preview(r):
        r["pages"][0]["preview_url"] = "ftp://nope"

    def no_pages(r):
        r["pages"] = []

    def wrong_type(r):
        r["funnel_type"] = "sales_page"

    def _mk(fn):
        r = _valid_receipt()
        fn(r)
        return r

    return [
        ("low_qc", "AF-FUN-BUILD-QC", lambda: _mk(low_qc)),
        ("missing_qc", "AF-FUN-BUILD-QC", lambda: _mk(missing_qc)),
        ("bool_qc", "AF-FUN-BUILD-QC", lambda: _mk(bool_qc)),
        ("empty_preview", "AF-FUN-BUILD-PREVIEW", lambda: _mk(empty_preview)),
        ("bad_preview_scheme", "AF-FUN-BUILD-PREVIEW", lambda: _mk(bad_preview)),
        ("no_pages", "AF-FUN-BUILD-MALFORMED", lambda: _mk(no_pages)),
        ("wrong_type", "AF-FUN-BUILD-TYPE", lambda: _mk(wrong_type)),
    ]


def run_self_test() -> int:
    ok = True
    v, _ = verify(_valid_receipt())
    if v:
        ok = False
        print(f"SELF-TEST FAIL: valid receipt produced {len(v)} violation(s): {v}")
    else:
        print("SELF-TEST ok: valid receipt PASSES (0 violations).")
    cases = _violation_cases()
    caught = 0
    for name, expected, build in cases:
        vio, _ = verify(build())
        codes = {c for c, _ in vio}
        if not vio:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' produced NO violations (expected {expected}).")
        elif expected not in codes:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' -> {sorted(codes)} (expected {expected}).")
        else:
            caught += 1
            print(f"SELF-TEST ok: '{name}' -> nonzero, carries {expected}.")
    print(f"SELF-TEST FIXTURES: 1 valid-pass, {caught}/{len(cases)} violation-catch")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description=f"Fail-closed P7-BUILD gate: validate build_receipt.json (QC >= {QC_FLOOR} + "
                    "preview URL per page). Exit 0 pass, 2 violation, 3 usage.")
    ap.add_argument("--receipt", help="path to build_receipt.json ('-' reads stdin)")
    ap.add_argument("receipt_pos", nargs="?", help="optional positional receipt path (equivalent to --receipt)")
    ap.add_argument("--self-test", action="store_true",
                    help="construct a VALID receipt (must PASS) + each VIOLATION fixture (must FAIL)")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()

    receipt_path = args.receipt or args.receipt_pos
    if not receipt_path:
        print("USAGE ERROR: pass --receipt <build_receipt.json> (or a positional path, or --self-test).")
        return EXIT_FAILCLOSED
    try:
        receipt = _load_json(receipt_path)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load build receipt {receipt_path!r}: {exc}")
        return EXIT_FAILCLOSED

    violations, notes = verify(receipt)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
