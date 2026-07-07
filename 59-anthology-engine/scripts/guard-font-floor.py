#!/usr/bin/env python3
"""guard-font-floor.py -- proves the RENDERED PDF, never the template.

Unit W1.12. SPEC 3.4 row 24 / SPEC 10.2 / MASTERDOC floor law #7. AF-AE-FONT-FLOOR.

Parses EVERY visible text span of one or more rendered PDFs with PyMuPDF (fitz) and
fails if any glyph renders below the 14-point floor. This is the authoritative,
output-side font-floor gate: it inspects what WeasyPrint actually produced, so it
catches a sub-floor glyph no matter how it got there (a template regression, an inline
style, a font-family substitution that changed metrics, a pasted HTML fragment). The
template-side tripwire lives in pdf_render.py (exit 2); this gate lives over the output.

fitz reports span['size'] in PDF text-space points, which map 1:1 to CSS points through
WeasyPrint (verified in Wave 0, .build-state/W0.6.json: 14pt -> 14.0, 18 -> 18.0,
24 -> 24.0). The recommended epsilon 0.5 absorbs float noise around a legitimate 14.0
without masking a real violation (a 12pt injection was still caught in the Wave-0 probe).

DOCTRINE: this guard NEVER prints the prose it inspects (participant content is PII).
By default it reports only size, page, and counts. Pass --show-text ONLY for local
debugging; it is never used in an automated gate run.

Exit codes (SPEC 3.4 row 24; house convention for the edge cases):
  0  clean (no glyph below the floor)
  4  violation (at least one span below the floor)
  2  bad invocation (no PDF given, or a path is missing / unreadable)
  3  dependency unavailable (PyMuPDF/fitz not importable)
  1  unexpected error
"""
import argparse
import json
import sys
from pathlib import Path

EX_OK, EX_ERR, EX_BAD, EX_DEP, EX_VIOLATION = 0, 1, 2, 3, 4

DEFAULT_FLOOR_PT = 14.0
DEFAULT_EPSILON = 0.5  # .build-state/W0.6.json recommended_epsilon


def _iter_spans(doc):
    """Yield (page_number_1based, size_pt, char_count, text) for every visible span."""
    for pno, page in enumerate(doc, 1):
        info = page.get_text("dict")
        for block in info.get("blocks", []):
            for line in block.get("lines", []):  # image blocks have no 'lines'
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if text.strip():  # skip whitespace-only spans (no visible glyph)
                        yield pno, float(span.get("size", 0.0)), len(text.strip()), text


def check_pdf(path, floor, epsilon, want_text=False):
    """Return a report dict for one PDF. Raises on open/parse failure."""
    import fitz
    doc = fitz.open(path)
    try:
        threshold = floor - epsilon
        violations = []
        min_size = None
        spans = 0
        sizes_seen = set()
        for pno, size, nchars, text in _iter_spans(doc):
            spans += 1
            sizes_seen.add(round(size, 2))
            if min_size is None or size < min_size:
                min_size = size
            if size < threshold:
                v = {"page": pno, "size_pt": round(size, 3), "chars": nchars}
                if want_text:
                    v["text"] = text
                violations.append(v)
        return {
            "pdf": str(path),
            "spans": spans,
            "min_size_pt": (round(min_size, 3) if min_size is not None else None),
            "sizes_seen": sorted(sizes_seen),
            "floor_pt": floor,
            "epsilon": epsilon,
            "threshold_pt": round(threshold, 3),
            "violation_count": len(violations),
            "violations": violations,
            "ok": len(violations) == 0,
        }
    finally:
        doc.close()


def evaluate(pdf_paths, floor=DEFAULT_FLOOR_PT, epsilon=DEFAULT_EPSILON):
    """Manifest entry symbol (ENGINE-MANIFEST autofails AF-AE-FONT-FLOOR, py_symbol
    "evaluate"). Importable harness API for the font-floor autofail.

    Accepts a single PDF path or an iterable of paths. Returns True when EVERY PDF is
    clean (no visible glyph below floor - epsilon); False when any PDF carries a glyph
    below the floor. Raises ImportError if PyMuPDF (fitz) is unavailable and
    FileNotFoundError if a path is missing (the CLI maps these to exit 3 and 2)."""
    import fitz  # noqa: F401  -- surface ImportError to the caller if unavailable
    if isinstance(pdf_paths, (str, Path)):
        pdf_paths = [pdf_paths]
    all_clean = True
    for p in pdf_paths:
        path = Path(p)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(str(p))
        if not check_pdf(path, floor, epsilon)["ok"]:
            all_clean = False
    return all_clean


def self_test(floor, epsilon):
    print("[guard-font-floor] self-test: building an in-memory PDF via fitz "
          "(a 14pt line and a 12pt line)")
    try:
        import fitz
    except ImportError:
        sys.stderr.write("[guard-font-floor] self-test: fitz (PyMuPDF) not importable\n")
        return EX_DEP
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        # PASS case: a single 14pt line.
        pass_pdf = os.path.join(td, "pass.pdf")
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Fourteen point line renders at the floor.", fontsize=14)
        doc.save(pass_pdf)
        doc.close()

        # DETECT case: a 14pt line plus a 12pt line.
        detect_pdf = os.path.join(td, "detect.pdf")
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Fourteen point line.", fontsize=14)
        page.insert_text((72, 120), "Twelve point footnote below the floor.", fontsize=12)
        doc.save(detect_pdf)
        doc.close()

        rp = check_pdf(pass_pdf, floor, epsilon)
        assert rp["ok"] and rp["min_size_pt"] is not None and rp["min_size_pt"] >= floor - epsilon, \
            "PASS case wrongly flagged: %r" % rp
        print("[guard-font-floor] pass case: PASS (min %.1fpt, %d violations)"
              % (rp["min_size_pt"], rp["violation_count"]))

        rd = check_pdf(detect_pdf, floor, epsilon)
        assert not rd["ok"] and rd["violation_count"] >= 1, "DETECT case not caught: %r" % rd
        assert any(abs(v["size_pt"] - 12.0) < 0.6 for v in rd["violations"]), \
            "12pt glyph not among violations: %r" % rd["violations"]
        print("[guard-font-floor] detect case: PASS (caught min %.1fpt, %d violation(s))"
              % (rd["min_size_pt"], rd["violation_count"]))
    print("[guard-font-floor] self-test: PASS")
    return EX_OK


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Font-floor gate over RENDERED PDFs for the Anthology Engine (W1.12).")
    ap.add_argument("pdfs", nargs="*", help="one or more rendered PDF paths")
    ap.add_argument("--floor", type=float, default=DEFAULT_FLOOR_PT,
                    help="font floor in points (default 14)")
    ap.add_argument("--epsilon", type=float, default=DEFAULT_EPSILON,
                    help="tolerance below the floor for float noise (default 0.5)")
    ap.add_argument("--json", action="store_true", help="emit a machine-readable report to stdout")
    ap.add_argument("--show-text", action="store_true",
                    help="include offending text in the report (LOCAL DEBUG ONLY; content is PII)")
    ap.add_argument("--self-test", action="store_true", help="run the built-in self-test and exit")
    args = ap.parse_args(argv)

    try:
        if args.self_test:
            return self_test(args.floor, args.epsilon)

        if not args.pdfs:
            ap.error("at least one PDF path is required (or use --self-test)")

        try:
            import fitz  # noqa: F401
        except ImportError:
            sys.stderr.write("[guard-font-floor] dependency unavailable: PyMuPDF (fitz) "
                             "is not importable\n")
            return EX_DEP

        reports = []
        for p in args.pdfs:
            path = Path(p)
            if not path.exists() or not path.is_file():
                sys.stderr.write("[guard-font-floor] bad invocation: not a file: %s\n" % p)
                return EX_BAD
            reports.append(check_pdf(path, args.floor, args.epsilon, want_text=args.show_text))

        any_viol = any(not r["ok"] for r in reports)

        if args.json:
            print(json.dumps({"floor_pt": args.floor, "epsilon": args.epsilon,
                              "ok": not any_viol, "reports": reports}, indent=2))
        else:
            for r in reports:
                if r["ok"]:
                    print("[guard-font-floor] CLEAN  %s  (%d spans, min %s pt, sizes %s)"
                          % (r["pdf"], r["spans"],
                             r["min_size_pt"], r["sizes_seen"]))
                else:
                    # Report size + page + counts only; never the prose (PII), unless --show-text.
                    by_page = {}
                    for v in r["violations"]:
                        by_page.setdefault(v["page"], []).append(v["size_pt"])
                    pages = ", ".join("p%d:%d span(s) @%s" % (pg, len(sz), sorted(set(sz)))
                                      for pg, sz in sorted(by_page.items()))
                    print("[guard-font-floor] VIOLATION  %s  %d glyph(s) below %.1f-%.1f=%.1f pt  [%s]"
                          % (r["pdf"], r["violation_count"], r["floor_pt"], r["epsilon"],
                             r["threshold_pt"], pages))
                    if args.show_text:
                        for v in r["violations"]:
                            print("    p%d @%spt: %r" % (v["page"], v["size_pt"], v.get("text", "")))

        return EX_VIOLATION if any_viol else EX_OK

    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[guard-font-floor] unexpected error: %s\n" % exc)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
