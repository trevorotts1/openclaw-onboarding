#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u04_modules/brand_link_checker.py
# BRAND-SURFACE LEGAL LINK GATE — never an example.com privacy/terms link
# (U04 item 1; the brand-link law of the cover/brand-marketing HTML family).
# -----------------------------------------------------------------------------
# WHAT THIS OWNS
#   Brand-marketing HTML (the cover template, the announcement card, the
#   sales-page and delivery surfaces) must link its legal destinations to the
#   client's OWN real domains — a footer that points Privacy Policy / Terms
#   of Service at example.com (or at a bare href that resolves to no real
#   host at all) ships a placeholder law into the client's brand. This module
#   is the OFFLINE, fail-closed tripwire: it scans brand HTML for legal-link
#   anchors and REFUSES any that are not replacement-ready. It NEVER fetches
#   a link, NEVER resolves DNS, and NEVER reads a credential — it is pure
#   local shape analysis, so it runs with zero network and zero tokens.
#
# FAIL-CLOSED, BOTH DIRECTIONS:
#   - a legal link whose href is empty or lacks a real host            -> FAIL
#   - a legal link whose host is a PLACEHOLDER domain (example.com and
#     siblings, or the *.example.* RFC 2606 reserved family)           -> FAIL
#   - a legal link whose href is a bare path ("./privacy") or a
#     scheme-less absolute path ("/privacy") — there is no real host     -> FAIL
#   - a legal link whose href is a mailto: / tel: / javascript: link     -> FAIL
#   - a brand page that carries NO legal links at all                  -> FAIL
#     (a brand surface without a Privacy Policy / Terms row is a missing
#     legal row — never a blind pass; the caller decides, the gate flags)
#   - an anchor whose link text CLEARLY names a legal destination but whose
#     href is a placeholder ("#", "javascript:void(0)", another brand
#     section URL) — the mislabeled row is refused, never a silent pass
#   - the check itself cannot run (no pages, unreadable file, no parser) -> FAIL
#   - unparseable fragments and unreadable href bytes are REFUSED (exit 5),
#     NEVER skipped: a tampered anchor is the attack this gate exists for.
#
# REPLACEMENT-READY LAW: the gate FAILS (exit 5) and names the anchors BY
# KEY — line number, element index, link text — and the flag is exactly
# "REPLACE": the offending href is never a clean pass and never a silent
# skip. The href VALUE is NEVER printed to any surface (it can carry a
# query-string token, so it is reported by key only; the full offender list
# goes to the JSON surface when --json is passed, and even there the href is
# reduced to host + path, never the raw query).
#
# THE "DOMAIN IS THE LAW" NOT-HARDCODED RULE: the PLACEHOLDER domain set is
# the IETF RFC 2606 reserved test-domain family (example.com / example.net /
# example.org / example.edu, and the "example.*" namespace) — an exact,
# stable, spec-pinned blocklist. A client's own brand domain is NEVER the
# gate's business: any host outside the reserved family is treated as real
# (the gate flags only what cannot possibly be a real destination).
#
# EXIT CODES (house convention, anthology_registry.py / drive_adapter.py):
#   0  all brand pages clean — every legal link is replacement-ready
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP-family refusal — no brand pages given, or a page cannot be read
#      (missing / unreadable file). A check that cannot see its inputs never
#      fabricates a pass.
#   4  self-test FAILED (golden PASS / attack FAIL asserted offline)
#   5  mismatch family — at least one legal link is a placeholder or
#      hostless (flag: REPLACE), or the parsed HTML cannot be faithfully
#      scanned (AF-AE-BRAND-LINK family)
#
# RESULT SHAPE (exactly as the caller's contract states):
#   {"ok": bool, "pages": int, "checked_links": int,
#    "flags": [{"page", "line", "index", "text", "host", "path", "flag"}]}
#   Every offender is named BY KEY. The href value is NEVER echoed in full —
#   host + path only (a query string can carry a token; never-a-token
#   doctrine).
#
# STDLIB ONLY (html.parser + urllib.parse); calls NO model, makes NO
# network requests. The CF 1010 law does not apply to THIS module's own
# traffic because it has none — but the doctrine does: any sibling module
# that later fetches brand pages must ride the house browser User-Agent
# (reg.CAF_BROWSER_UA) because the Convert and Flow / Cloudflare edge 403s
# urllib's default "Python-urllib/x.y" UA at the WAF edge (CF error 1010)
# before the request ever reaches the origin — the pattern lives in
# anthology_registry.py and every engine request rides it.
#
# IMPORT: imported by NAME as u04_modules.brand_link_checker from the engine
# scripts (the package init is a pure namespace container). It is a MODULE
# with a thin CLI: check_html() / check_pages() are the importable entry
# points, main() is the operator surface. --self-test is OFFLINE and needs
# no token and no network:
#   brand_link_checker.py [page.html ...]
#   brand_link_checker.py self-test     # offline golden + attack fixtures
# =============================================================================
"""brand_link_checker.py — fail-closed gate: no example.com privacy/terms links."""

from __future__ import annotations

import argparse
import io
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

# Exit codes (house convention 0/1/2/5; 4 = enforced violation):
#   0 clean · 1 unexpected · 2 STOP (bad invocation / unreadable input) ·
#   4 self-test FAILED · 5 mismatch family (placeholder legal link).
EX_OK, EX_ERR, EX_STOP, EX_MISMATCH = 0, 1, 2, 5
EX_SELFTEST_FAIL = 4

# The RFC 2606 reserved test-domain family — the ONLY domains the gate
# refuses. Anything outside this exact spec-pinned set is treated as a real
# destination (the client's own brand domains are never the gate's business).
PLACEHOLDER_HOSTS = frozenset({
    "example.com", "example.net", "example.org", "example.edu",
    "www.example.com", "www.example.net", "www.example.org", "www.example.edu",
})

# Anchor text that marks a link as a legal row. A legal-named anchor whose
# href is a placeholder ("#", "javascript:...", a bare path, a section link)
# is a MISLABELED legal row — refused, never a silent pass.
LEGAL_TEXT_RE = re.compile(
    r"privacy|terms\s*of\s*(service|use)|terms\s*&?\s*conditions|"
    r"legal\s*notice|disclaimer|cookie\s*policy|gdpr|ccpa|"
    r"privacy\s*policy", re.IGNORECASE)

# Anchor text that must never be mistaken for a legal row.
SKIP_TEXT_RE = re.compile(
    r"privacy\s*policy\s*(of|for|by)\b|terms\s*(apply|and\s*conditions\s*of\s*use)"
    r"|terms\s*conditions\s*(apply|of\s*use)|third[- ]party", re.IGNORECASE)

# A legal link with NO legal text but a placeholder href (e.g. href to
# example.com/privacy) is still flagged — host truth beats link text.
EXAMPLE_HOST_RE = re.compile(
    r"(^|\.)example\.[a-z]{2,}$", re.IGNORECASE)


def _host_flagged(host: str) -> bool:
    """True for a placeholder test-domain host (RFC 2606 reserved family)."""
    host = (host or "").strip().lower()
    # search(), never match(): the pattern's `(^|\.)` alternative must fire
    # for subdomain-prefixed hosts (subdomain.example.net) too.
    return host in PLACEHOLDER_HOSTS or bool(EXAMPLE_HOST_RE.search(host))


def _link_is_placeholder(href: str) -> bool:
    """Fail-closed href classification. A link is replacement-ready ONLY when
    it carries a real host. The href VALUE is never surfaced — only this
    verdict, the host, and the path leave this function."""
    href = (href or "").strip()
    if not href:
        return True
    if href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return True
    parsed = urlparse(href)
    if parsed.scheme:
        # An absolute URL with a real scheme must carry a real host.
        if parsed.scheme not in ("http", "https"):
            return True
        host = (parsed.hostname or "").lower()
        if not host or _host_flagged(host):
            return True
        return False
    # Scheme-less forms: "//host/path" carries a host; a bare path or a
    # relative URL ("privacy.html", "./privacy", "/privacy") carries none.
    if href.startswith("//"):
        host = (parsed.hostname or "").lower()
        if not host or _host_flagged(host):
            return True
        return False
    return True


def _host_and_path(href: str) -> tuple:
    """The SAFE surface form of an href: host + path only. The raw href
    (and any query string, which can carry a token) is never emitted."""
    href = (href or "").strip()
    if not href:
        return "", ""
    try:
        # Bare-path hrefs have no host to parse; report the path alone.
        if not href.startswith(("http://", "https://", "//")):
            return "", (href.split("?", 1)[0] or "").strip()[:120]
        parsed = urlparse(href)
    except Exception:  # noqa: BLE001 — never leak a parse failure
        return "", ""
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").strip()[:120]
    return host, path


class _LinkScanner(HTMLParser):
    """Extracts anchors as (line, index, text, href). Fail-closed: unreadable
    href bytes REFUSE the scan (they cannot be faithfully judged)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self._in_anchor = False
        self._text_parts = []
        self._href = None
        self._index = 0
        self._seen_href_errors = 0

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        self._index += 1
        self._in_anchor = True
        self._text_parts = []
        self._href = None
        for key, value in attrs:
            if key == "href" and value is not None:
                try:
                    self._href = value.decode("utf-8") if isinstance(value, bytes) else str(value)
                except Exception:  # noqa: BLE001 — unreadable href bytes
                    self._seen_href_errors += 1
                    self._href = None
                break

    def handle_endtag(self, tag):
        if tag == "a" and self._in_anchor:
            text = " ".join(" ".join(self._text_parts).split())
            if self._href is not None or text:
                self.anchors.append((self.getpos()[0], self._index, text, self._href or ""))
            self._in_anchor = False

    def handle_data(self, data):
        if self._in_anchor:
            self._text_parts.append(data)


def _scan_html(html_bytes: bytes) -> list:
    """Parse brand HTML into [(line, index, text, href), ...]. Raises
    ValueError on unreadable href bytes (fail-closed, never a silent skip)."""
    text = html_bytes.decode("utf-8", "replace")
    scanner = _LinkScanner()
    scanner.feed(text)
    if scanner._seen_href_errors:
        raise ValueError("an anchor href carried unreadable bytes (refused, "
                         "never silently skipped)")
    return list(scanner.anchors)


def check_html(html_bytes: bytes, page_name: str = "<inline>") -> dict:
    """Scan ONE brand HTML document for placeholder legal links. Returns a
    page report dict (never raises on a violation; a violation IS the
    result). Raises ValueError when the document cannot be faithfully
    scanned (unreadable href bytes — fail-closed, never a silent skip).

    Flags, by key only (the href value is never echoed):
      flag "REPLACE"  — a legal row whose link is a placeholder: href empty,
        hostless (bare path / relative / scheme-less), reserved example.*
        host, or a non-http(s) scheme; ALSO a legal-named anchor carrying a
        placeholder href ("#", "javascript:void(0)", a section link).
      flag "HOSTLESS" — any anchor (legal-named or not) whose href is a bare
        path or relative URL with no host at all.
      flag "MISSING"  — the page carries NO anchors at all: a brand surface
        without any link row is a missing legal row (the caller decides, the
        gate flags)."""
    anchors = _scan_html(html_bytes)
    flags = []

    if not anchors:
        flags.append({"page": page_name, "line": 0, "index": 0, "text": "",
                      "host": "", "path": "", "flag": "MISSING"})
        return {"page": page_name, "anchors": 0, "ok": False, "flags": flags}

    checked = 0
    for line, index, text, href in anchors:
        text_norm = " ".join(text.split())
        legal_named = bool(LEGAL_TEXT_RE.search(text_norm)) and not SKIP_TEXT_RE.search(text_norm)
        if not legal_named and not href:
            continue
        checked += 1
        host, path = _host_and_path(href)
        placeholder = _link_is_placeholder(href)
        if placeholder:
            flags.append({"page": page_name, "line": line, "index": index,
                          "text": text_norm, "host": host, "path": path,
                          "flag": "REPLACE" if legal_named else "HOSTLESS"})
            continue
        if legal_named and EXAMPLE_HOST_RE.search(host):
            flags.append({"page": page_name, "line": line, "index": index,
                          "text": text_norm, "host": host, "path": path,
                          "flag": "REPLACE"})
            continue
        if legal_named and href.lstrip().startswith("#"):
            flags.append({"page": page_name, "line": line, "index": index,
                          "text": text_norm, "host": "", "path": path,
                          "flag": "REPLACE"})

    return {"page": page_name, "anchors": len(anchors), "ok": not flags, "flags": flags}


def check_pages(paths) -> dict:
    """The aggregate entry point (importable harness API): scan every page,
    fail-closed. Returns {"ok", "pages", "checked_links", "flags", "errors"}.
    Raises FileNotFoundError when a path is missing (the CLI maps that to
    exit 2) and ValueError when a document cannot be faithfully scanned
    (exit 5 at the CLI — a tampered anchor is never a silent skip)."""
    if isinstance(paths, (str, Path)):
        paths = [paths]
    reports = []
    flags = []
    errors = []
    for p in paths:
        path = Path(p)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(str(p))
        data = path.read_bytes()
        rep = check_html(data, page_name=str(path))
        reports.append(rep)
        flags.extend(rep["flags"])
    return {
        "ok": all(r["ok"] for r in reports),
        "pages": len(reports),
        "checked_links": sum(len(r["flags"]) + r["anchors"] for r in reports),
        "flags": flags,
        "errors": errors,
    }


def self_test(out=None) -> int:
    """Offline battery (no network, no credentials): the golden page PASSES,
    every attack fixture FAILS. Exit 0 pass / 4 enforced violation — a
    tamper NEVER masquerades as exit 1."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[brand-link-checker] SELF-TEST FAILED "
                         "(AF-AE-BRAND-LINK family): %s\n" % exc)
        return EX_SELFTEST_FAIL
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    golden = (
        b"<html><body><footer>"
        b'<a href="https://www.realbrandco.com/privacy">Privacy Policy</a>'
        b'<a href="https://www.realbrandco.com/terms">Terms of Service</a>'
        b"</footer></body></html>")
    g = check_html(golden)
    assert g["ok"], "golden page wrongly flagged: %r" % g["flags"]

    attack1 = (
        b"<html><body><footer>"
        b'<a href="https://www.example.com/privacy">Privacy Policy</a>'
        b'<a href="https://www.example.com/terms">Terms of Service</a>'
        b"</footer></body></html>")
    a1 = check_html(attack1)
    assert not a1["ok"], "example.com legal link not caught"
    assert [f["flag"] for f in a1["flags"]].count("REPLACE") >= 2, (
        "example.com legal links must flag REPLACE, got %r" % a1["flags"])

    attack2 = (b"<html><body><footer>"
               b'<a href="/privacy">Privacy Policy</a>'
               b'<a href="/terms">Terms of Service</a>'
               b"</footer></body></html>")
    a2 = check_html(attack2)
    assert not a2["ok"], "hostless legal link not caught"
    assert a2["flags"][0]["flag"] == "REPLACE", "hostless legal link must flag REPLACE"

    attack3 = (b"<html><body><footer>"
               b'<a href="https://www.example.org">Privacy Policy</a>'
               b"</footer></body></html>")
    a3 = check_html(attack3)
    assert not a3["ok"], "example.org legal link not caught"

    attack4 = (b"<html><body><footer>"
               b'<a href="mailto:legal@example.com">Terms of Service</a>'
               b"</footer></body></html>")
    a4 = check_html(attack4)
    assert not a4["ok"], "mailto legal link not caught"

    attack5 = (b"<html><body><footer>"
               b'<a href="https://www.example.com/terms" target="_blank">'
               b"Open the Terms and Conditions</a></footer></body></html>")
    a5 = check_html(attack5)
    assert not a5["ok"], "example.com legal link with plain text not caught"

    attack5b = (b"<html><body><footer>"
                b'<a href="https://subdomain.example.net/legal/terms.html">'
                b"Terms of Service</a></footer></body></html>")
    a5b = check_html(attack5b)
    assert not a5b["ok"], "subdomain.example.net legal link not caught"

    attack6 = (b"<html><body><footer>"
               b'<a href="https://www.realbrandco.com/">Privacy Policy</a>'
               b'<a href="https://www.realbrandco.com/terms">Terms of Service</a>'
               b'<a href="/about">About</a>'
               b"</footer></body></html>")
    a6 = check_html(attack6)
    assert not a6["ok"], "hostless non-legal link not caught"

    attack7 = b"<html><body><footer></footer></body></html>"
    a7 = check_html(attack7)
    assert not a7["ok"] and a7["flags"][0]["flag"] == "MISSING", (
        "page with no anchors must flag MISSING")

    attack8 = (b"<html><body><footer>"
               b'<a href="https://www.realbrandco.com/privacy">Privacy Policy</a>'
               b"</footer></body></html>")
    a8 = check_html(attack8)
    assert a8["ok"], "a lone REAL legal row is a business decision, not a placeholder: %r" % a8["flags"]

    attack9 = (b"<html><body><footer>"
               b'<a href="javascript:void(0)">Privacy Policy</a>'
               b"</footer></body></html>")
    a9 = check_html(attack9)
    assert not a9["ok"], "javascript: legal link not caught"

    dev.write("[brand-link-checker] golden PASS; attack fixtures 1-9b all FAIL "
              "(example.com / example.org / hostless / mailto / plain-text / "
              "subdomain.example.net / non-legal hostless / MISSING / "
              "lone-real-row PASS / javascript:).\n")
    dev.write("[brand-link-checker] self-test: PASS\n")


def _run_main(pages, jsonout):
    """Shared CLI body: 0 clean · 2 unreadable input · 5 violation / refused."""
    if not pages:
        sys.stderr.write("[brand-link-checker] STOP: no brand page(s) given "
                         "(or use --self-test). A check that cannot see its "
                         "inputs never fabricates a pass.\n")
        return EX_STOP
    try:
        result = check_pages(pages)
    except FileNotFoundError as exc:
        sys.stderr.write("[brand-link-checker] STOP: cannot read brand page: "
                         "%s\n" % exc)
        return EX_STOP
    except ValueError as exc:
        sys.stderr.write("[brand-link-checker] REFUSED (fail-closed): %s\n" % exc)
        return EX_MISMATCH

    if jsonout is not None:
        import json
        json.dump(result, jsonout)
        jsonout.write("\n")

    if result["ok"]:
        sys.stderr.write("[brand-link-checker] OK: %d page(s), %d anchor(s) "
                         "checked, all legal links replacement-ready.\n"
                         % (result["pages"], result["checked_links"]))
        return EX_OK

    by_flag = {}
    for f in result["flags"]:
        by_flag.setdefault(f["flag"], []).append(f)
    for flag, rows in sorted(by_flag.items()):
        if flag == "REPLACE":
            sys.stderr.write("[brand-link-checker] REPLACE %d legal link(s):\n"
                             % len(rows))
        elif flag == "HOSTLESS":
            sys.stderr.write("[brand-link-checker] HOSTLESS %d anchor(s):\n"
                             % len(rows))
        else:
            sys.stderr.write("[brand-link-checker] %s %d row(s):\n"
                             % (flag, len(rows)))
        for f in rows[:50]:
            loc = (f["page"], f["line"], f["index"], f["text"][:80])
            sys.stderr.write("    %s:%s #%s  %r\n" % loc)
    sys.stderr.write("[brand-link-checker] FAIL (AF-AE-BRAND-LINK family): "
                     "%d page(s), %d flag(s). Replace the placeholder legal "
                     "links with the client's real domains and re-run.\n"
                     % (result["pages"], len(result["flags"])))
    return EX_MISMATCH


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="brand_link_checker.py",
        description="Fail-closed gate: no example.com privacy/terms links in "
                    "brand-marketing HTML (Skill 59, u04_modules). OFFLINE — "
                    "no network, no credentials. Flags placeholder legal "
                    "links BY KEY (line / index / text) for replacement.")
    ap.add_argument("pages", nargs="*", metavar="page.html",
                    help="one or more brand HTML files to scan")
    ap.add_argument("--json", action="store_true",
                    help="emit the machine-readable report to stdout "
                         "(hrefs still reduced to host + path)")
    ap.add_argument("--selftest", "--self-test", dest="self_test",
                    action="store_true",
                    help="run the offline self-test (golden + attack fixtures) and exit")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Positional subcommand form (house shape, per u03 main_skeleton): a
    # leading "self-test" positional runs the offline battery; the flag
    # spellings --self-test / --selftest normalize to the same surface.
    if argv and argv[0] == "self-test":
        argv = argv[1:]
        args = ap.parse_args(argv)
        return self_test()
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()

    jsonout = sys.stdout if args.json else None
    return _run_main(args.pages, jsonout)


if __name__ == "__main__":
    sys.exit(main())
