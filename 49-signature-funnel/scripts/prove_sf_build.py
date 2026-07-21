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
  * that preview URL is not a placeholder/example/loopback host — a
    caller-authored stand-in is not a preview.                  -> AF-FUN-BUILD-PREVIEW-PLACEHOLDER

A10 / T0-11 — COMPLETENESS. The gate above verified every page the receipt SUPPLIED
and never checked that all required pages were supplied, so a 7-step funnel whose
receipt carried 3 pages returned zero violations and reached a Complete verdict. The
required page-type set is now DERIVED from the locked funnel size (the 3/5/7 matrix in
structure/funnel_structure.json — the same source of truth P6 and P8 use) and any
missing page type FAILS.                                                 -> AF-FUN-BUILD-PAGESET
The size is resolved from --funnel-size (the orchestrator passes the LOCKED brief size)
or from the receipt's own funnel_size; an unresolvable size is fail-closed, and a
receipt whose declared size contradicts the brief FAILS. -> AF-FUN-BUILD-SIZE / -SIZE-MISMATCH

Fail-closed: an absent/unreadable/empty receipt is a FAIL, never a pass.  -> AF-FUN-BUILD-MALFORMED
funnel_type mismatch (when declared) also FAILS.                          -> AF-FUN-BUILD-TYPE

stdlib only. Exit 0 = pass, exit 2 = violation, exit 3 = usage / fail-closed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

FUNNEL_TYPE = "signature_funnel"
QC_FLOOR = 8.5  # OpenClaw QC Protocol threshold (>= 8.5 auto-approves)

# Hosts that are never a real preview. Matched as an exact host or a dotted suffix,
# so a genuine vendor host that merely CONTAINS one of these words (for example
# app.example-ghl.com) is not false-failed.
PLACEHOLDER_HOSTS = (
    "example.com", "example.org", "example.net", "example.edu", "invalid",
    "localhost", "127.0.0.1", "0.0.0.0", "test.com", "changeme.com", "todo.com",
)


def _host_of(url: str) -> str:
    try:
        return (urlparse(url.strip()).hostname or "").lower()
    except (ValueError, TypeError):
        return ""


def _placeholder_host(url: Any) -> bool:
    """True when the URL's host IS a placeholder host or a subdomain of one."""
    if not isinstance(url, str):
        return False
    host = _host_of(url)
    if not host:
        return False
    return any(host == ph or host.endswith("." + ph) for ph in PLACEHOLDER_HOSTS)


def _preview_ok(url: Any) -> bool:
    return isinstance(url, str) and url.strip().lower().startswith(("http://", "https://"))


def required_page_types(size: int) -> List[str]:
    """The page-type set a build receipt MUST carry for a locked funnel size, read
    from the SAME 3/5/7 matrix P6-COMPOSE and P8-DERIVE use. Raises on an unknown
    size or an unreadable matrix so the caller fails closed rather than guessing."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import prove_sf_graph  # noqa: E402  (sibling prover; single source of truth)
    return list(prove_sf_graph.funnel_pages(int(size)))


def _resolve_size(receipt: Dict[str, Any],
                  funnel_size: Optional[int]) -> Tuple[Optional[int], List[Tuple[str, str]]]:
    """(size, fails). Explicit --funnel-size (the LOCKED brief size) wins; the
    receipt's own declaration is cross-checked against it, never trusted over it."""
    fails: List[Tuple[str, str]] = []
    declared = receipt.get("funnel_size")
    declared = declared if isinstance(declared, int) and not isinstance(declared, bool) else None
    if funnel_size is not None and declared is not None and int(funnel_size) != declared:
        fails.append(("AF-FUN-BUILD-SIZE-MISMATCH",
                      f"build receipt declares funnel_size {declared} but the locked brief "
                      f"size is {int(funnel_size)} — the receipt does not describe this funnel"))
        return None, fails
    size = int(funnel_size) if funnel_size is not None else declared
    if size is None:
        fails.append(("AF-FUN-BUILD-SIZE",
                      "funnel size is unresolved (no --funnel-size and no receipt funnel_size) "
                      "— the required page set cannot be computed, so completeness cannot be "
                      "proven (fail-closed)"))
    return size, fails


def verify(receipt: Dict[str, Any],
           funnel_size: Optional[int] = None) -> Tuple[List[Tuple[str, str]], List[str]]:
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

    supplied: List[str] = []
    for i, pg in enumerate(pages):
        if not isinstance(pg, dict):
            fail("AF-FUN-BUILD-MALFORMED", f"page entry #{i} is not an object")
            continue
        who = str(pg.get("page_type") or pg.get("id") or f"#{i}")
        pt = str(pg.get("page_type") or "").strip().lower()
        if pt:
            supplied.append(pt)
        url = pg.get("preview_url")
        if not _preview_ok(url):
            fail("AF-FUN-BUILD-PREVIEW",
                 f"page '{who}': preview_url {url!r} is not a non-empty http(s) URL")
        elif _placeholder_host(url):
            fail("AF-FUN-BUILD-PREVIEW-PLACEHOLDER",
                 f"page '{who}': preview_url {url!r} resolves to placeholder host "
                 f"{_host_of(url)!r} — a caller-authored stand-in is not a built preview")

    # A10 / T0-11 — COMPLETENESS against the locked size.
    size, size_fails = _resolve_size(receipt, funnel_size)
    fails.extend(size_fails)
    if size is not None:
        try:
            required = required_page_types(size)
        except (ValueError, OSError, ImportError) as exc:
            fail("AF-FUN-BUILD-SIZE",
                 f"cannot resolve the {size}-step page matrix ({exc}) — completeness cannot "
                 "be proven (fail-closed)")
        else:
            missing = [p for p in required if p.strip().lower() not in supplied]
            if missing:
                fail("AF-FUN-BUILD-PAGESET",
                     f"build receipt supplies {sorted(set(supplied))} but the {size}-step "
                     f"funnel requires {required} — missing {missing}. Every required page "
                     "must be built and previewed before the funnel can be Complete.")
            extra = sorted(set(supplied) - {p.strip().lower() for p in required})
            if extra:
                notes.append(f"receipt carries {len(extra)} page type(s) outside the "
                             f"{size}-step matrix: {extra} (not a violation)")
            notes.append(f"page-set completeness checked against the {size}-step matrix "
                         f"({len(required)} required page type(s))")

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
    """A COMPLETE receipt for `size`: every page type the locked matrix requires,
    built and previewed on a real (non-placeholder) vendor host.

    A10 / T0-11 — this fixture used to hardcode a 3-page list (main/upsell/
    thank-you) while declaring funnel_size 5, and the gate passed it. It now
    derives its page list from the SAME matrix the gate checks against, so the
    fixture cannot silently disagree with the contract it is meant to exercise."""
    stages = required_page_types(size)
    return {
        "funnel_type": FUNNEL_TYPE,
        "funnel_size": size,
        "qc_score": 9.1,
        "pages": [
            {"page_type": s, "status": "built",
             "preview_url": f"https://app.gohighlevel.com/funnels/preview/{s}"}
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

    def placeholder_preview(r):
        r["pages"][0]["preview_url"] = "https://preview.example.com/main"

    def no_pages(r):
        r["pages"] = []

    def wrong_type(r):
        r["funnel_type"] = "sales_page"

    def drop_a_page(r):
        # T0-11 in one line: hand back fewer pages than the locked size requires.
        r["pages"] = r["pages"][:-1]

    def undersized_receipt(r):
        # the exact shape the finding describes: a 7-step funnel, 3 pages supplied.
        r["funnel_size"] = 7
        r["pages"] = [p for p in r["pages"]
                      if p["page_type"] in ("main", "upsell", "thank-you")]

    def size_lies(r):
        r["funnel_size"] = 3  # contradicts the locked brief size passed in below

    def _mk(fn, size=5):
        r = _valid_receipt(size)
        fn(r)
        return r

    return [
        ("low_qc", "AF-FUN-BUILD-QC", lambda: (_mk(low_qc), None)),
        ("missing_qc", "AF-FUN-BUILD-QC", lambda: (_mk(missing_qc), None)),
        ("bool_qc", "AF-FUN-BUILD-QC", lambda: (_mk(bool_qc), None)),
        ("empty_preview", "AF-FUN-BUILD-PREVIEW", lambda: (_mk(empty_preview), None)),
        ("bad_preview_scheme", "AF-FUN-BUILD-PREVIEW", lambda: (_mk(bad_preview), None)),
        ("placeholder_preview_host", "AF-FUN-BUILD-PREVIEW-PLACEHOLDER",
         lambda: (_mk(placeholder_preview), None)),
        ("no_pages", "AF-FUN-BUILD-MALFORMED", lambda: (_mk(no_pages), None)),
        ("wrong_type", "AF-FUN-BUILD-TYPE", lambda: (_mk(wrong_type), None)),
        # --- A10 / T0-11 completeness ---
        ("missing_one_required_page", "AF-FUN-BUILD-PAGESET", lambda: (_mk(drop_a_page), None)),
        ("seven_step_funnel_three_pages", "AF-FUN-BUILD-PAGESET",
         lambda: (_mk(undersized_receipt, 7), None)),
        # An undeclared receipt cannot dodge completeness by simply not naming a
        # size: the LOCKED brief size the orchestrator passes decides the set.
        ("three_pages_against_locked_size_7", "AF-FUN-BUILD-PAGESET",
         lambda: (_mk(lambda r: r.pop("funnel_size", None), 3), 7)),
        ("receipt_size_contradicts_brief", "AF-FUN-BUILD-SIZE-MISMATCH",
         lambda: (_mk(size_lies), 5)),
        ("unresolvable_size", "AF-FUN-BUILD-SIZE",
         lambda: ({"funnel_type": FUNNEL_TYPE, "qc_score": 9.1,
                   "pages": [{"page_type": "main", "status": "built",
                              "preview_url": "https://app.gohighlevel.com/p/main"}]}, None)),
    ]


def run_self_test() -> int:
    ok = True
    for size in (3, 5, 7):
        v, _ = verify(_valid_receipt(size), funnel_size=size)
        if v:
            ok = False
            print(f"SELF-TEST FAIL: complete {size}-step receipt produced "
                  f"{len(v)} violation(s): {v}")
        else:
            print(f"SELF-TEST ok: COMPLETE {size}-step receipt PASSES (0 violations, "
                  f"{len(required_page_types(size))} required page types present).")
    cases = _violation_cases()
    caught = 0
    for name, expected, build in cases:
        receipt, size = build()
        vio, _ = verify(receipt, funnel_size=size)
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
    print(f"SELF-TEST FIXTURES: 3 complete-pass (3/5/7), {caught}/{len(cases)} violation-catch")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description=f"Fail-closed P7-BUILD gate: validate build_receipt.json (QC >= {QC_FLOOR} + "
                    "preview URL per page). Exit 0 pass, 2 violation, 3 usage.")
    ap.add_argument("--receipt", help="path to build_receipt.json ('-' reads stdin)")
    ap.add_argument("receipt_pos", nargs="?", help="optional positional receipt path (equivalent to --receipt)")
    ap.add_argument("--funnel-size", type=int, default=None,
                    help="the LOCKED brief funnel size (3/5/7). Required page-type "
                         "completeness is computed from it; without it the receipt's own "
                         "funnel_size is used and an unresolvable size is fail-closed.")
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

    violations, notes = verify(receipt, funnel_size=args.funnel_size)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
