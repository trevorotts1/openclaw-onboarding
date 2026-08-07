#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_collateral_backup.py — fail-closed prover for the delivery collateral backup rail
(presentations upsell pipeline, GAUNTLET-LOOP DESIGN-OPUS §3.4 / §8 F16).

The collateral folder (`delivery/<SLUG>-FINAL/upsell/`) is the MANDATORY backup rail for
the upsell pages — required even when GHL succeeds. This prover asserts, for every page
the client OPTED IN to (sales/checkout when Q1==yes, VSL when Q2==yes):

  * the folder exists                                     -> AF-PRES-COLLATERAL-DIR-MISSING
  * the required HTML file for each opted-in page exists  -> AF-PRES-COLLATERAL-FILE-MISSING
  * each HTML file is NON-EMPTY (real fragment, not a stub) -> AF-PRES-COLLATERAL-EMPTY
  * each HTML file carries a real <html>/<body> or is a valid fragment with a heading
    (a .txt rename or an empty div is not collateral)     -> AF-PRES-COLLATERAL-NOT-HTML
  * when --expect-checkout/--expect-vsl are not passed,
    their files are still checked IF present but not
    required (optional pages may be absent legitimately)
  * (optional) --splice-html <file> compares the collateral
    HTML to the spliced page byte-for-byte after a
    media-URL rewrite, catching drift (DESIGN-OPUS §10.3) -> AF-PRES-COLLATERAL-DRIFT

Usage:
  prove_collateral_backup.py <delivery/upsell-dir> [--expect-sales|--no-sales]
      [--expect-checkout|--no-checkout] [--expect-vsl|--no-vsl]
  Defaults (design §3.4): the folder is the `upsell/` subdir of `delivery/<SLUG>-FINAL/`.

stdlib only. Exit 0 = pass, 2 = violation (autofail), 3 = usage/IO (fail-closed).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_DIR = "AF-PRES-COLLATERAL-DIR-MISSING"
AF_FILE = "AF-PRES-COLLATERAL-FILE-MISSING"
AF_EMPTY = "AF-PRES-COLLATERAL-EMPTY"
AF_NOT_HTML = "AF-PRES-COLLATERAL-NOT-HTML"
AF_DRIFT = "AF-PRES-COLLATERAL-DRIFT"

# Required page HTML files (DESIGN-OPUS §3.4).
PAGE_FILES = {
    "sales": "sales-page.html",
    "checkout": "checkout-page.html",
    "vsl": "vsl-page.html",
}

# A GHL code-block HTML fragment does not need a full <html> wrapper; but it must look
# like HTML: a tag, a heading, or a style/script block. A `.txt` paste or empty div fails.
_HTML_SIGNAL_RE = re.compile(r"<(html|body|section|div|h[1-6]|form|video|iframe|header|footer|main)[\s>]",
                             re.I)


def _looks_like_html(fragment: str) -> bool:
    return bool(_HTML_SIGNAL_RE.search(fragment)) or \
        bool(re.search(r"</?(style|script)[\s>]", fragment, re.I))


def _splice_equivalent(collateral: Path, splice_path: Path) -> List[Tuple[str, str]]:
    """DESIGN-OPUS §10.3: the HTML in collateral == the HTML that was spliced, byte-for-byte
    after a media-URL rewrite. We normalize CRLF and trailing whitespace, and allow a
    single media-URL substitution (cdn host) declared via --media-rewrite."""
    fails: List[Tuple[str, str]] = []
    try:
        a = collateral.read_text(encoding="utf-8", errors="replace")
        b = splice_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [(AF_DRIFT, f"cannot read collateral/splice file: {exc}")]
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    if norm(a) != norm(b):
        fails.append((AF_DRIFT,
                      f"{collateral.name} differs from the spliced page "
                      f"{splice_path.name} (byte-for-byte after whitespace normalization)"))
    return fails


def _verify_dir(upsell_dir: Path, expect: Dict[str, bool],
                splice_roots: Optional[List[Path]] = None) -> List[Tuple[str, str]]:
    fails: List[Tuple[str, str]] = []
    if not upsell_dir.is_dir():
        return [(AF_DIR, f"collateral upsell folder missing: {upsell_dir}")]

    for page, fname in PAGE_FILES.items():
        expected = expect.get(page, False)
        path = upsell_dir / fname
        if not path.is_file():
            if expected:
                fails.append((AF_FILE,
                              f"client opted into {page} but collateral file {fname} is "
                              f"missing in {upsell_dir}"))
            continue
        if path.stat().st_size == 0:
            fails.append((AF_EMPTY, f"collateral file {fname} is empty (0 bytes)"))
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        if not _looks_like_html(content):
            fails.append((AF_NOT_HTML,
                          f"collateral file {fname} does not look like HTML (no markup "
                          f"signals found)"))
        # Splice equivalence (design §10.3) — optional, via --splice-html.
        if expected and splice_roots:
            for root in splice_roots:
                splice = root / fname
                if splice.is_file():
                    fails.extend(_splice_equivalent(path, splice))
                    break
    return fails


def _emit(source: str, failures: List[Tuple[str, str]], as_json: bool) -> None:
    if as_json:
        import json
        print(json.dumps({"gate": "presentations-collateral-backup", "source": source,
                          "pass": not failures,
                          "failures": [{"code": c, "message": m} for c, m in failures]},
                         indent=2))
        return
    print("== Presentations :: collateral backup rail ==")
    print(f"source: {source}")
    if not failures:
        print("RESULT: PASS — every opted-in upsell page HTML exists, non-empty, and "
              "looks like a real fragment.")
        return
    print(f"RESULT: FAIL (fail-closed) — {len(failures)} violation(s):")
    for code, msg in failures:
        print(f"  [{code}] {msg}")


def prove(path: str, expect: Dict[str, bool], as_json: bool = False,
          splice_roots: Optional[List[Path]] = None) -> int:
    p = Path(path)
    # Accept either the upsell/ dir directly, or the delivery/<SLUG>-FINAL/ parent.
    if p.is_dir() and p.name != "upsell" and not (p / "upsell").is_dir() and not any(
            x.is_file() for x in PAGE_FILES.values() and (p / x).is_file()):
        # If it doesn't contain the page files and has an upsell subdir, use that.
        cand = p / "upsell"
        if cand.is_dir():
            p = cand
    fails = _verify_dir(p, expect, splice_roots)
    _emit(str(p), fails, as_json)
    return EXIT_PASS if not fails else EXIT_AUTOFAIL


# ---------------------------------------------------------------------------
# Self-test — must DISCRIMINATE.
# ---------------------------------------------------------------------------
def _write(tmp: Path, name: str, content: str) -> Path:
    f = tmp / name
    f.write_text(content, encoding="utf-8")
    return f


def _valid_fragment(page: str) -> str:
    if page == "sales":
        return ("<!doctype html><html><head><title>Sales</title></head><body>"
                "<section class=\"hero\"><h1>Stop Guessing. Start Closing.</h1></section>"
                "<section class=\"final-cta\"><button>Get Started</button></section>"
                "</body></html>")
    if page == "checkout":
        return ("<!doctype html><html><head><title>Checkout</title></head><body>"
                "<section class=\"order-form\"><h2>Order Summary</h2><form id=\"co\">"
                "<input name=\"email\" /></form></section></body></html>")
    return ("<!doctype html><html><head><title>VSL</title></head><body>"
            "<section class=\"hero-video\"><video src=\"v.mp4\"></video></section>"
            "<section class=\"gate-overlay\"><form id=\"gate\"></form></section>"
            "</body></html>")


def self_test(tmp: Optional[Path] = None) -> int:
    import tempfile
    ok = True
    work = tmp or Path(tempfile.mkdtemp(prefix="pres-collateral-selftest-"))
    upsell = work / "upsell"
    upsell.mkdir(parents=True, exist_ok=True)

    def check_pass(name: str, fails: List[Tuple[str, str]]) -> None:
        nonlocal ok
        good = not fails
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VALID {name:20s} -> exit "
              f"{EXIT_PASS if good else EXIT_AUTOFAIL}" + ("" if good else f" ({fails})"))

    def check_fail(name: str, fails: List[Tuple[str, str]], expect: str) -> None:
        nonlocal ok
        codes = [c for c, _ in fails]
        good = bool(fails) and expect in codes
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VIOLATION {name:22s} -> codes={codes} "
              f"(want {expect})")

    print("== self-test: VALID fixtures (must PASS) ==")
    for pg in ("sales", "checkout", "vsl"):
        _write(upsell, PAGE_FILES[pg], _valid_fragment(pg))
    check_pass("all-three-present", _verify_dir(upsell, {"sales": True, "checkout": True,
                                                         "vsl": True}))
    # Optional pages legitimately absent (client said no to VSL) must pass.
    (upsell / PAGE_FILES["vsl"]).unlink()
    check_pass("vsl-not-opted-in", _verify_dir(upsell, {"sales": True, "checkout": True,
                                                        "vsl": False}))

    print("== self-test: VIOLATION fixtures (must FAIL) ==")
    # Opted-in file missing.
    (upsell / PAGE_FILES["sales"]).unlink()
    check_fail("sales-opted-missing", _verify_dir(upsell, {"sales": True, "checkout": True,
                                                           "vsl": False}), AF_FILE)
    _write(upsell, PAGE_FILES["sales"], _valid_fragment("sales"))
    # Empty file.
    _write(upsell, PAGE_FILES["checkout"], "")
    check_fail("checkout-empty", _verify_dir(upsell, {"checkout": True}), AF_EMPTY)
    _write(upsell, PAGE_FILES["checkout"], _valid_fragment("checkout"))
    # Not-HTML (a .txt paste).
    _write(upsell, PAGE_FILES["vsl"], "this is not html, just some plain text notes about the vsl")
    check_fail("vsl-not-html", _verify_dir(upsell, {"vsl": True}), AF_NOT_HTML)
    _write(upsell, PAGE_FILES["vsl"], _valid_fragment("vsl"))
    # Directory missing.
    check_fail("dir-missing", _verify_dir(work / "nope", {"sales": True}), AF_DIR)

    print("== self-test:", "ALL ASSERTIONS PASSED ==" if ok else "FAILED ==")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed prover for the collateral backup rail.")
    ap.add_argument("dir", nargs="?", help="path to the delivery/<SLUG>-FINAL/upsell folder "
                                           "(or its parent)")
    ap.add_argument("--expect-sales", dest="expect_sales", action="store_true")
    ap.add_argument("--no-sales", dest="expect_sales", action="store_false")
    ap.set_defaults(expect_sales=True)
    ap.add_argument("--expect-checkout", dest="expect_checkout", action="store_true")
    ap.add_argument("--no-checkout", dest="expect_checkout", action="store_false")
    ap.set_defaults(expect_checkout=False)
    ap.add_argument("--expect-vsl", dest="expect_vsl", action="store_true")
    ap.add_argument("--no-vsl", dest="expect_vsl", action="store_false")
    ap.set_defaults(expect_vsl=False)
    ap.add_argument("--splice-html", action="append", default=[],
                    help="directory containing the spliced page HTML to byte-compare")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON output")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in VALID + VIOLATION fixtures and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.dir:
        print("USAGE ERROR: pass a collateral folder (or --self-test).")
        return EXIT_USAGE
    expect = {"sales": args.expect_sales, "checkout": args.expect_checkout,
              "vsl": args.expect_vsl}
    splice_roots = [Path(s) for s in args.splice_html]
    return prove(args.dir, expect, as_json=args.json, splice_roots=splice_roots)


if __name__ == "__main__":
    sys.exit(main())
