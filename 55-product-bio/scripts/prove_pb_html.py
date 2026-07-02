#!/usr/bin/env python3
# =============================================================================
# SKILL 55 — PRODUCT BIO :: HTML ENVELOPE BATTERY (fail-closed, stdlib-only)
# -----------------------------------------------------------------------------
# Enforces the Google-Doc HTML Writer's strict contract (source prompt P2):
#
#   AF-PB-HTML-ENVELOPE — output does not start EXACTLY '<!DOCTYPE html>' or end
#                         EXACTLY '</html>' (P2 lines 18/24/323-324). With
#                         --allow-trim the ONE permitted repair is applied first
#                         (strip pre/post commentary, logged) and then re-checked.
#   AF-PB-HTML-H1       — the document does not contain exactly one <h1> (P2 line 269).
#   AF-PB-HTML-CSS      — any CSS beyond page-break-after: a <style> block, or an
#                         inline style="" with any other property (P2 line 289).
#   AF-PB-HTML-LOSS     — content loss vs the source bio beyond tolerance
#                         (deterministic normalized-token coverage < 90%).
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_pb_html.py <product-bio.html> [--source-bio F] [--allow-trim] [--json]
#        prove_pb_html.py --self-test
# =============================================================================
"""Fail-closed HTML envelope battery for the Product Bio engine (Skill 55)."""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _pb_common as c  # noqa: E402

AF_HTML_ENVELOPE = "AF-PB-HTML-ENVELOPE"
AF_HTML_H1 = "AF-PB-HTML-H1"
AF_HTML_CSS = "AF-PB-HTML-CSS"
AF_HTML_LOSS = "AF-PB-HTML-LOSS"
_FIX = Path(__file__).resolve().parent.parent / "test-fixtures"

DOCTYPE = "<!DOCTYPE html>"
END = "</html>"
LOSS_TOLERANCE = 0.90     # HTML must retain >= 90% of the bio's significant tokens
_STYLE_BLOCK_RE = re.compile(r"<style\b", re.I)
_INLINE_STYLE_RE = re.compile(r'style\s*=\s*"([^"]*)"', re.I)
_H1_RE = re.compile(r"<h1\b", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def auto_trim(html: str):
    """The ONE permitted repair: strip commentary before <!DOCTYPE html> and
    after </html>. Returns (trimmed, was_trimmed)."""
    start = html.find(DOCTYPE)
    end = html.rfind(END)
    if start == -1 or end == -1:
        return html, False
    trimmed = html[start:end + len(END)]
    return trimmed, (trimmed != html)


def _check_envelope(html, r):
    if not html.startswith(DOCTYPE):
        r.fail(AF_HTML_ENVELOPE, "output does not start EXACTLY with %r" % DOCTYPE)
    if not html.rstrip("\n").endswith(END):
        r.fail(AF_HTML_ENVELOPE, "output does not end EXACTLY with %r" % END)
    if r.passed:
        r.note("strict envelope OK (starts <!DOCTYPE html>, ends </html>)")


def _check_h1(html, r):
    n = len(_H1_RE.findall(html))
    if n != 1:
        r.fail(AF_HTML_H1, "found %d <h1> elements, require exactly 1" % n)
    else:
        r.note("exactly one <h1>")


def _check_css(html, r):
    if _STYLE_BLOCK_RE.search(html):
        r.fail(AF_HTML_CSS, "a <style> block is present (only page-break-after is permitted)")
    for decl_block in _INLINE_STYLE_RE.findall(html):
        for decl in decl_block.split(";"):
            decl = decl.strip()
            if not decl:
                continue
            prop = decl.split(":", 1)[0].strip().lower()
            if prop != "page-break-after":
                r.fail(AF_HTML_CSS, "disallowed inline CSS property %r (only "
                       "page-break-after is permitted)" % prop)
    if not any(code == AF_HTML_CSS for code, _ in r.violations):
        r.note("no CSS beyond page-break-after")


def _visible_text(html: str) -> str:
    return _TAG_RE.sub(" ", html)


def _check_loss(html, source_bio, r):
    if source_bio is None:
        r.note("content-loss check skipped (no --source-bio supplied)")
        return
    bio_tokens = set(c.normalized_tokens(source_bio, min_len=4))
    html_tokens = set(c.normalized_tokens(_visible_text(html), min_len=4))
    if not bio_tokens:
        r.note("content-loss check skipped (empty source bio)")
        return
    covered = len(bio_tokens & html_tokens) / len(bio_tokens)
    if covered < LOSS_TOLERANCE:
        r.fail(AF_HTML_LOSS, "content coverage %.1f%% < %.0f%% tolerance vs source bio "
               "(content lost in conversion)" % (covered * 100, LOSS_TOLERANCE * 100))
    else:
        r.note("content coverage %.1f%% >= %.0f%% tolerance"
               % (covered * 100, LOSS_TOLERANCE * 100))


def evaluate(html: str, source_bio=None, allow_trim=False) -> c.Result:
    r = c.Result("prove_pb_html")
    if allow_trim:
        html, trimmed = auto_trim(html)
        if trimmed:
            r.note("auto-trim applied (stripped commentary around the envelope) — logged")
    _check_envelope(html, r)
    _check_h1(html, r)
    _check_css(html, r)
    _check_loss(html, source_bio, r)
    return r


def prove(path, source_bio_path=None, allow_trim=False, as_json=False) -> int:
    html = c.read_text(path)
    src = c.read_text(source_bio_path) if source_bio_path else None
    return evaluate(html, source_bio=src, allow_trim=allow_trim).emit(as_json)


def self_test() -> int:
    checks = []
    golden_html = c.read_text(_FIX / "golden" / "product-bio.html")
    golden_bio = c.read_text(_FIX / "golden" / "product-bio.md")
    checks.append(("golden HTML PASS (envelope/h1/css/loss)",
                   evaluate(golden_html, source_bio=golden_bio).passed))

    env = evaluate(c.read_text(_FIX / "attack" / "html_envelope.html"))
    checks.append(("commentary-before-doctype AUTOFAILs AF-PB-HTML-ENVELOPE",
                   any(code == AF_HTML_ENVELOPE for code, _ in env.violations)))
    # ...and the ONE permitted auto-trim repairs exactly that commentary case.
    env_fixed = evaluate(c.read_text(_FIX / "attack" / "html_envelope.html"),
                         source_bio=golden_bio, allow_trim=True)
    checks.append(("...auto-trim repairs the commentary envelope to PASS", env_fixed.passed))

    h1 = evaluate(c.read_text(_FIX / "attack" / "html_two_h1.html"))
    checks.append(("two-<h1> AUTOFAILs AF-PB-HTML-H1",
                   any(code == AF_HTML_H1 for code, _ in h1.violations)))

    css = evaluate(c.read_text(_FIX / "attack" / "html_css.html"))
    checks.append(("custom-CSS AUTOFAILs AF-PB-HTML-CSS",
                   any(code == AF_HTML_CSS for code, _ in css.violations)))

    loss = evaluate(c.read_text(_FIX / "attack" / "html_loss.html"), source_bio=golden_bio)
    checks.append(("halved-content AUTOFAILs AF-PB-HTML-LOSS",
                   any(code == AF_HTML_LOSS for code, _ in loss.violations)))
    return c.selftest_report("prove_pb_html", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Product Bio HTML envelope battery (Skill 55).")
    ap.add_argument("path", nargs="?", help="product-bio.html to prove")
    ap.add_argument("--source-bio", help="the source bio .md for the content-loss check")
    ap.add_argument("--allow-trim", action="store_true",
                    help="apply the ONE permitted envelope auto-trim before checking")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("a path is required (or use --self-test)")
    return prove(args.path, source_bio_path=args.source_bio,
                 allow_trim=args.allow_trim, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
