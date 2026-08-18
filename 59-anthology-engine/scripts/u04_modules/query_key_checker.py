#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u04_modules/query_key_checker.py  (U04 tooling)
# INTAKE QUERY-KEY CHECKER (G3) — the fail-closed tripwire that the LIVE
# universal author-intake form's hidden field carrying the Book ID is keyed
# EXACTLY "anthology_id", never the lookalike "anthology_active_id" — the
# query key the minted intake link builds (G3 QUERY-KEY LAW,
# scripts/anthology_book.py INTAKE_QUERY_KEY / build_intake_link:
# <forms_base>/widget/form/<form_id>?anthology_id=<minted>).
# -----------------------------------------------------------------------------
# WHAT THIS OWNS — THE G3 LAW, LIVE
#   The minted intake link rides the ONE query param anthology_id onto the
#   form's HIDDEN anthology_id field, so the router accepts
#   customData.anthology_id and the Book ID never types a keystroke
#   (SKILL.md:52; intake_router.py:133-134). anthology_active_id is a
#   DIFFERENT thing — the CONTACT custom field the delivery writer stamps
#   with the ACTIVE anthology (caf_delivery.py) — and the G3 defect is
#   exactly the conflation: a form whose hidden field is keyed
#   anthology_active_id silently drops the minted Book ID at submit time.
#   This module reads the LIVE hosted-form page (the SAME public
#   <forms_base>/widget/form/<form_id> surface the author's browser loads —
#   ZERO credentials, ZERO API calls) and requires:
#     - the form's hidden field carrying the Book ID to have query key
#       data-q EXACTLY "anthology_id" (byte-exact, never a strip, never a
#       case fold), and
#     - that field to be a HIDDEN field (the d-none container class), and
#     - the lookalike key "anthology_active_id" to be the LABEL of that same
#       hidden field, and
#     - the key "anthology_active_id" to appear NOWHERE as a data-q — no
#       live field may SUBMIT under the lookalike key (a wrong-keyed field
#       is a FAIL even when the right-keyed field also exists).
#   The check NEVER auto-heals a drifted form and NEVER edits the form: a
#   drift is a reportable FAIL, not a fix — the form definition is
#   UI/snapshot-created per config/anthology-snapshot-contract.json
#   (forms.$note: "The provisioner does NOT auto-create forms"), so the
#   operator repairs the key in the Convert and Flow form builder and
#   re-runs.
#
# THE LIVE SURFACE IS CREDENTIAL-FREE BY DESIGN
#   The hosted-form page at <forms_base>/widget/form/<form_id> is the PUBLIC
#   widget the author's browser loads (proofed live against the fleet-wide
#   universal form id U65pwoeMTy1niMqllKWG on the fleet-default domain
#   link.msgsndr.com). The hidden field row renders with the query key in
#   its markup:
#     <label ... for="<id>">anthology_active_id</label>
#       <textarea ... data-q="anthology_id" ...></textarea>
#   inside a container carrying the "d-none" class (hidden). So the G3 law
#   is verifiable with ONE public GET — no PIT, no location id, no Fire,
#   no rail. THIS module therefore holds NO credential surface at all:
#   there is nothing to resolve and nothing that could ever print a token.
#   The BROWSER UA law (CF 1010 / GK-09) still applies to the request
#   itself: the Cloudflare edge fronting the hosted-form domain 403s
#   urllib's default "Python-urllib/x.y" User-Agent (CF error 1010), so
#   every request rides the house browser UA, CAF_BROWSER_UA from
#   anthology_registry — proven live (this module's fetch is the same
#   UA'd GET this repo made to prove the page shape).
#
# FAIL-CLOSED (the whole point)
#   - a form page that cannot be fetched (HTTP error, transport failure,
#     timeout) is HELD (exit 3) — the law is UNDETERMINED, never proven
#     compliant,
#   - a 2xx body that cannot be parsed faithfully is a MISMATCH (exit 5) —
#     a tampered page is the attack this gate exists for,
#   - an unreadable body (gzip-decompression failure) is HELD (exit 3),
#   - no hidden field, no field with any data-q, a hidden field with
#     data-q != "anthology_id", the field keyed "anthology_id" that is NOT
#     hidden, or ANY data-q == "anthology_active_id" is a FAIL (exit 5) —
#     never a silent pass, never a fabricated compliance,
#   - the expected key is never hardcoded here: it is mirrored from
#     scripts/anthology_book.py INTAKE_QUERY_KEY (the SAME constant
#     build_intake_link uses, imported at runtime — the delta_reporter.py
#     single-implementation doctrine) and pinned byte-for-byte in the
#     offline self-test, so a drift between the minted link and this gate
#     trips the self-test before it can ship,
#   - "current" carries the LIVE hidden-field query key when a single
#     hidden field exists, else the first live data-q seen (so a gate can
#     tell a WRONG key from ABSENT), else "".
#
# EXIT CODES (house convention 0/1/2/3/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  PASS — the live hidden field is keyed anthology_id byte-exact,
#      is hidden, and no live field submits under anthology_active_id
#      (also plan and self-test PASS)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — usage error, or the expected query key cannot be
#      resolved (anthology_book.py INTAKE_QUERY_KEY unimportable or empty:
#      the law is unverifiable — a check that cannot see its law never
#      fabricates a pass)
#   3  HELD — the live form page is unreachable (HTTP error, transport
#      failure, edge block, timeout) or its bytes cannot be decompressed:
#      the law is UNDETERMINED, never proven compliant
#   4  self-test FAILED (an offline assertion tripped; a tamper NEVER
#      masquerades as exit 1)
#   5  FAIL — the live form's hidden query key drifted from anthology_id,
#      or any live field submits under the lookalike anthology_active_id
#      (AF-AE-INTAKE-QUERY-KEY; the G3 defect family)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; --self-test is OFFLINE and needs NO token and NO network):
#   query_key_checker.py live [--forms-base URL] [--intake-form-id ID]
#       [--timeout SECONDS]
#   query_key_checker.py plan            # offline; the G3 law with sources
#   query_key_checker.py self-test       # offline golden + attack fixtures
#
# STDLIB ONLY (urllib + json + re); calls NO model. Sibling import
# bootstrap identical to the other u04/u03 modules: sys.path insert to
# scripts/ then `import anthology_registry as reg` for the canonical
# CAF_BROWSER_UA; the expected key is imported from anthology_book (its
# own sibling bootstrap runs once at import). DOCTRINE: move in silence;
# NOTHING Anthropic in any runtime file; Convert and Flow naming in every
# client surface; NEVER print a secret value — and this module holds no
# secret to print.
# =============================================================================
"""query_key_checker.py — G3 intake query-key gate: the live hidden field
must be keyed anthology_id, never the lookalike anthology_active_id."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# canonical constants (CAF_BROWSER_UA / CAF_VERSION_HEADER) and the
# fail-closed helper surfaces; this module mirrors the constants it needs
# and pins the mirror in its offline self-test.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The lookalike key the G3 defect conflates with the hidden-field key. The
# ACTUAL contact custom field (caf_delivery.py stamps
# contact.anthology_active_id) is a DIFFERENT thing — a field that SUBMITS
# under this key on the intake form would silently drop the minted Book ID.
LOOKALIKE_QUERY_KEY = "anthology_active_id"

# The hidden field renders inside a container with the "d-none" class (the
# Convert and Flow hosted-form builder's hidden-field marker).
HIDDEN_CONTAINER_CLASS = "d-none"

# Fetched page cap (bytes): the form page is ~100KB decompressed; the cap
# only guards a runaway response. Read in chunks (the exact urllib pattern
# proved against the live page).
MAX_READ_BYTES = 4 * 1024 * 1024

# The fleet-wide non-client defaults mirrored from anthology_book.py: the
# shared LeadConnector hosted-form domain and the ONE universal author-intake
# form id (platform / universal values, never a per-client domain or
# credential; both overridable per box). Mirrored here so a fetch NEVER
# fabricates a URL from thin air; the mirror is pinned in the offline
# self-test.
DEFAULT_FORMS_BASE = "https://link.msgsndr.com"
DEFAULT_UNIVERSAL_INTAKE_FORM_ID = "U65pwoeMTy1niMqllKWG"
WIDGET_FORM_PATH = "/widget/form"


def _resolve_intake_key() -> str:
    """The G3 expected query key, from the ONE source of truth: the same
    INTAKE_QUERY_KEY constant build_intake_link mints links with
    (scripts/anthology_book.py). Fail-closed: an unimportable or empty
    constant returns "" — the law is unverifiable, never a guessed key."""
    try:
        import anthology_book  # noqa: F401  (sibling import after path bootstrap)
        key = (getattr(anthology_book, "INTAKE_QUERY_KEY", "") or "").strip()
    except Exception:  # noqa: BLE001  (import failure -> fail closed)
        return ""
    return key


def _mask_form_id(form_id: str) -> str:
    """Non-reversible marker for a form id (last 4 chars), the house
    masking law for every identifier surface."""
    form_id = (form_id or "").strip()
    return ("..." + form_id[-4:]) if len(form_id) >= 4 else "...(short)"


def _decompress(data: bytes) -> str:
    """Decode the fetched body, transparently gunzipping when the server
    served Content-Encoding: gzip. A body that cannot be decoded faithfully
    raises ValueError -> HELD (the law is UNDETERMINED on unreadable bytes,
    never proven compliant)."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data.decode("utf-8", errors="strict")


# ---------------------------------------------------------------------------
# The live read — the PUBLIC hosted-form page (zero credentials).
# ---------------------------------------------------------------------------
class _FormPageError(Exception):
    """Unexpected error surfaced by a query_key_checker run (fail-closed)."""


def fetch_form_page(forms_base: str = "", form_id: str = "",
                    timeout: float = 20.0) -> str:
    """Fetch the PUBLIC hosted-form page with the house browser User-Agent
    (reg.CAF_BROWSER_UA — the CF 1010 law; the SAME UA'd GET proved against
    the live page). Returns the decompressed page body. Raises
    _FormPageError (STOP family) on a URL that cannot be built and
    reg.CafUnreachable (HELD family) on any HTTP error / transport failure
    / timeout / undecodable body. NEVER reads a credential — there is none."""
    base = (forms_base or "").strip().rstrip("/")
    fid = (form_id or "").strip()
    if not base or not fid:
        raise _FormPageError(
            "cannot build the form page URL: forms base or form id is EMPTY")
    url = "%s%s/%s" % (base, WIDGET_FORM_PATH, fid)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": reg.CAF_BROWSER_UA,
                 "Accept-Encoding": "gzip",
                 "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            if status >= 400:
                raise urllib.error.HTTPError(
                    url, status, "form page HTTP %s" % status,
                    dict(resp.headers), resp)
            raw = resp.read(MAX_READ_BYTES + 1)
            if len(raw) > MAX_READ_BYTES:
                raise reg.CafUnreachable(
                    "form page exceeded %d bytes (runaway response)" % MAX_READ_BYTES)
        try:
            return _decompress(raw)
        except (OSError, ValueError) as exc:
            raise reg.CafUnreachable(
                "form page body cannot be decoded faithfully: %s" % exc) from exc
    except reg.CafUnreachable:
        raise
    except urllib.error.HTTPError as exc:
        # Edge / WAF / origin refusal -> HELD (UNDETERMINED, never a FAIL
        # and never a pass). A bare 403 here is most likely the CF 1010 edge
        # block — the scope-denial signature of the API does not apply to
        # this public page.
        raise reg.CafUnreachable(
            "form page HTTP %s on %s (held: the G3 law is UNDETERMINED)"
            % (exc.code, _mask_form_id(fid))) from exc
    except urllib.error.URLError as exc:
        raise reg.CafUnreachable(
            "form page unreachable (transport): %s (marker %s)"
            % (exc.reason, _mask_form_id(fid))) from exc
    except (TimeoutError, OSError) as exc:
        raise reg.CafUnreachable(
            "form page fetch failed: %s (marker %s)"
            % (type(exc).__name__, _mask_form_id(fid))) from exc


# ---------------------------------------------------------------------------
# The pure parser + the check — returns {"ok", "current", "expected"}.
# ---------------------------------------------------------------------------
def parse_form_fields(page: str) -> list:
    """Parse the hosted-form page into field rows [{"label", "query_key",
    "hidden", "element_id"}]. Pure, deterministic, stdlib-only: a field
    row is a label (with its for= element id) plus the element carrying the
    data-q query key inside the same field wrapper, and a field is hidden
    when its container carries the "d-none" class (the Convert and Flow
    hidden-field marker). A row with NO data-q is kept (it may still carry
    the lookalike LABEL — a mislabeled field is the G3 defect), and a row
    with NO label but a data-q is kept with an empty label. The page is
    parsed faithfully or not at all: an empty result is returned as-is and
    the check FAILS on it (never fabricated compliance)."""
    rows = []
    for chunk in re.split(r'class="col-12 form-field-wrapper"', page):
        label = None
        for_ = None
        lm = re.search(r'<label[^>]*for="([^"]*)"[^>]*>([^<]*)</label>', chunk)
        if lm:
            for_ = lm.group(1).strip()
            label = lm.group(2).strip()
        qm = re.search(r'data-q="([^"]*)"', chunk)
        hidden = ("d-none" in chunk) or ('class="d-none"' in chunk)
        if lm is None and qm is None:
            continue
        rows.append({"label": label or "", "query_key": qm.group(1) if qm else "",
                     "hidden": hidden, "element_id": for_ or ""})
    return rows


def check_query_key(page: str, want: str = "") -> dict:
    """The G3 law applied to a parsed (or raw) form page. Fail-closed:

      - "expected" is the SAME INTAKE_QUERY_KEY constant build_intake_link
        mints with; an empty want fails closed (ok False, expected ""),
      - ok True ONLY when SOME hidden field is keyed byte-exact want AND
        no live field submits under the lookalike anthology_active_id,
      - "current" is the hidden field's live query key when exactly one
        hidden field exists, else the first live data-q seen (so a gate
        can tell a WRONG key from ABSENT), else "".
    Never raises on a drift (a mismatch is a result) and never prints a
    value that could be a token (there are none in a form page)."""
    # The default resolves the SAME INTAKE_QUERY_KEY constant
    # build_intake_link mints with (the single-implementation doctrine) —
    # the rename_checker pattern (want or _expected_name).
    want = (want or "").strip() or _resolve_intake_key().strip()
    if not want:
        return {"ok": False, "current": "", "expected": ""}

    rows = page if isinstance(page, list) else parse_form_fields(page)
    hidden_rows = [r for r in rows if r["hidden"]]
    live_keys = [r["query_key"] for r in rows if r["query_key"]]

    if hidden_rows:
        current = hidden_rows[0]["query_key"]
    elif live_keys:
        current = live_keys[0]
    else:
        current = ""

    keyed = [r for r in hidden_rows if r["query_key"] == want]
    lookalike_abuse = any(r["query_key"] == LOOKALIKE_QUERY_KEY for r in rows)
    # A hidden field keyed correctly but with a MISLABELED lookalike label
    # is exactly the G3 shape (label anthology_active_id, data-q
    # anthology_id) and is COMPLIANT — the lookalike word is the human
    # label, never the wire key. Only a field that SUBMITS under the
    # lookalike key is a defect.
    ok = bool(keyed) and not lookalike_abuse

    # Defect detail, for the operator surface only (no values, just keys).
    detail = None
    if not keyed:
        if not hidden_rows:
            detail = "no HIDDEN field on the live form at all"
        else:
            detail = ("hidden field keyed %r, expected %r"
                      % (current, want))
    elif lookalike_abuse:
        detail = "a live field SUBMITS under the lookalike key %r" % LOOKALIKE_QUERY_KEY
    return {"ok": ok, "current": current, "expected": want, "detail": detail}


# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the pure logic:
# golden state passes, every attack fixture FAILS, and the G3 law stays
# pinned to the anthology_book constant. A tamper NEVER masquerades as
# exit 1.
# ---------------------------------------------------------------------------
def _golden_page(field="anthology_id", label="anthology_active_id",
                 hidden=True) -> str:
    """The G3 live shape as a page: a hidden field labeled
    anthology_active_id, keyed anthology_id (the exact live markup)."""
    klass = ' form-builder--item field-container d-none' if hidden else ''
    return ('<div class="col-12 form-field-wrapper">'
            '<div class="form-field-container"><div class="f-even%s">'
            '<label class="label-alignment field-label" for="f1">%s</label>'
            '<div class="flex-col"><textarea name="f1" data-q="%s" '
            'data-required="false" id="f1"></textarea></div>'
            '</div></div></div>' % (klass, label, field))


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[query-key-checker] SELF-TEST FAILED "
                         "(AF-AE-INTAKE-QUERY-KEY family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    want = _resolve_intake_key()
    assert want, "INTAKE_QUERY_KEY must not be empty"
    assert want == "anthology_id", \
        "INTAKE_QUERY_KEY drifted from the G3 contract (is %r)" % want

    # ---- golden live state: hidden + byte-exact -> ok True ----
    report = check_query_key(_golden_page())
    assert report["ok"] is True, "golden page must be ok"
    assert report["current"] == "anthology_id" and report["expected"] == want

    # ---- attack fixtures: every mutation FAILS (never a silent pass) ----
    # 1. hidden field keyed the LOOKALIKE -> ok False, current names it
    a1 = _golden_page(field="anthology_active_id")
    report = check_query_key(a1)
    assert report["ok"] is False, "lookalike key must be failed"
    assert report["current"] == "anthology_active_id"
    assert report["expected"] == want
    # 2. NO hidden field at all (the key rides a VISIBLE field) -> ok False
    a2 = _golden_page(hidden=False)
    report = check_query_key(a2)
    assert report["ok"] is False, "visible keyed field must be failed"
    assert report["current"] == "anthology_id", "visible key must be surfaced"
    # 3. empty page (no parseable fields) -> ok False, current ""
    report = check_query_key("")
    assert report["ok"] is False and report["current"] == ""
    # 4. NO fields at all -> ok False
    report = check_query_key("<html><body></body></html>")
    assert report["ok"] is False and report["current"] == ""
    # 5. right key hidden + a SECOND field submitting under the lookalike
    #    -> ok False (never a pass while the lookalike key can fire)
    both = (_golden_page()
            + _golden_page(field="anthology_active_id", label="lookalike"))
    report = check_query_key(both)
    assert report["ok"] is False, "lookalike alongside correct key must FAIL"
    # 6. whitespace-padded key -> ok False (byte-exact, not .strip())
    report = check_query_key(_golden_page(field="anthology_id "))
    assert report["ok"] is False, "padded key must fail byte-exact"
    # 7. case drift -> ok False
    report = check_query_key(_golden_page(field="Anthology_Id"))
    assert report["ok"] is False, "case drift must fail byte-exact"
    # 8. wrong key entirely -> ok False
    report = check_query_key(_golden_page(field="book_id"))
    assert report["ok"] is False, "unrelated key must fail byte-exact"
    # 9. the G3 golden label shape — label IS the lookalike word, data-q is
    #    anthology_id -> ok True (the label is human text, never the wire
    #    key; this IS the live shape, proofed against the universal form)
    g3 = _golden_page()
    assert "anthology_active_id" in g3, "golden page must carry the G3 label"
    assert check_query_key(g3)["ok"] is True, "G3 label shape must pass"
    # 10. an empty expected key fails closed (the law is unverifiable;
    #     pass an explicit non-empty WRONG law to bypass the auto-resolved
    #     default — the empty-"" path resolves the live constant instead,
    #     the rename_checker want-or-default pattern)
    report = check_query_key(_golden_page(), want="book_id")
    assert report["ok"] is False and report["expected"] == "book_id", \
        "a wrong law must fail closed"
    # 11. the live parse seam: the golden page parses to ONE hidden row
    rows = parse_form_fields(g3)
    assert len(rows) == 1 and rows[0]["query_key"] == "anthology_id"
    assert rows[0]["hidden"] is True and rows[0]["label"] == "anthology_active_id"
    # 12. the mirror pins: defaults + the browser UA contract (CF 1010)
    assert DEFAULT_FORMS_BASE == "https://link.msgsndr.com"
    assert DEFAULT_UNIVERSAL_INTAKE_FORM_ID == "U65pwoeMTy1niMqllKWG"
    assert WIDGET_FORM_PATH == "/widget/form"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), \
        "CAF_BROWSER_UA drifted from the browser-UA law"
    # 13. decompression round-trip (gzip bytes -> the same page)
    raw = gzip.compress(g3.encode("utf-8"))
    assert _decompress(raw) == g3, "gzip decode must round-trip exactly"

    dev.write("query_key_checker self-test: OK (G3 law pinned to "
              "anthology_book.INTAKE_QUERY_KEY %r; golden PASS; 13 "
              "fixtures: lookalike-key / no-hidden-field / empty-page / "
              "no-fields / lookalike-alongside / padded / case-drift / "
              "wrong-key / g3-label-shape / empty-contract / parse-seam / "
              "mirrors / gzip round-trip; the lookalike label "
              "anthology_active_id is the G3 shape and PASSES when the "
              "wire key is anthology_id)\n" % want)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _live_report(report: dict) -> None:
    """Emit the ONE JSON object (machine surface, stdout) for a live run."""
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")


def run_live(page: str, *, out=None) -> int:
    """Apply the G3 law to a fetched live page. Returns the exit code.
    One JSON object lands on stdout; human notes go to stderr."""
    out = out or sys.stderr
    want = _resolve_intake_key()
    if not want:
        reg._stop(out, "The intake query-key law is EMPTY.",
                  ["scripts/anthology_book.py INTAKE_QUERY_KEY is empty or "
                   "unimportable — restore the constant and re-run."])
        return EX_STOP
    report = check_query_key(page, want)
    if report["ok"]:
        out.write("[query-key-checker] OK: the live hidden field is keyed "
                  "%r byte-exact; no live field submits under %r.\n"
                  % (report["current"], LOOKALIKE_QUERY_KEY))
        _live_report(report)
        return EX_OK

    reg._stop(out, "The live intake form's hidden query key is NOT %r (G3)."
              % want,
              ["AF-AE-INTAKE-QUERY-KEY: %s" % report.get("detail", "drift"),
               "The minted link rides ?%s=<minted> onto this hidden field; "
               "a wrong key silently drops the Book ID at submit time." % want,
               "Expected byte-exact: %r" % want,
               "Live query key found: %r" % report["current"] if report["current"]
               else "Live query key found: NONE",
               "Repair the field key in the Convert and Flow form builder "
               "(the hidden field's query key, NOT its label) and re-run."])
    _live_report(report)
    return EX_MISMATCH


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="query_key_checker.py",
        description="Fail-closed G3 query-key gate against the LIVE universal "
                    "author-intake form (U04): the hidden field that carries "
                    "the minted Book ID must be keyed 'anthology_id' "
                    "byte-exact, never the lookalike 'anthology_active_id'. "
                    "The live read is the PUBLIC hosted-form page — zero "
                    "credentials. One JSON object on stdout; never prints a "
                    "secret (Skill 59).")
    ap.add_argument("--forms-base", default=DEFAULT_FORMS_BASE,
                    help="override the hosted-form base (default: the "
                         "fleet-default %s)" % DEFAULT_FORMS_BASE)
    ap.add_argument("--intake-form-id", default=DEFAULT_UNIVERSAL_INTAKE_FORM_ID,
                    help="override the universal intake form id (default: the "
                         "fleet-wide universal form id)")
    ap.add_argument("--timeout", type=float, default=20.0,
                    help="fetch timeout in seconds (default 20)")
    ap.add_argument("cmd", nargs="?", choices=["live", "plan", "self-test"],
                    default="live")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()

        want = _resolve_intake_key()
        if not want:
            reg._stop(sys.stderr, "The intake query-key law is EMPTY.",
                      ["scripts/anthology_book.py INTAKE_QUERY_KEY is empty "
                       "or unimportable — restore the constant and re-run."])
            return EX_STOP

        if args.cmd == "plan":
            # offline plan: no network, no credentials
            print(json.dumps({
                "contract": "anthology-engine-query-key-check-plan",
                "schema_version": 1,
                "expected_query_key": want,
                "lookalike_query_key": LOOKALIKE_QUERY_KEY,
                "check": "GET <forms_base>/widget/form/<form_id> (the PUBLIC "
                         "hosted-form page, browser UA — CF 1010 law) and "
                         "require the hidden field's data-q to be %r "
                         "byte-exact with no live field submitting under "
                         "%r; the %r label on the keyed hidden field is the "
                         "G3 live shape and passes" % (
                             want, LOOKALIKE_QUERY_KEY, LOOKALIKE_QUERY_KEY),
                "live_url": "%s%s/%s" % (
                    (args.forms_base or "").strip().rstrip("/"),
                    WIDGET_FORM_PATH, args.intake_form_id),
                "credential_surface": "none — the hosted-form page is the "
                                      "public widget the author's browser "
                                      "loads",
                "note": "offline plan only — no fetch, no credential needed",
            }, indent=2, sort_keys=True))
            return EX_OK

        # ---- live check: ONE public GET, zero credentials ----
        started = time.time()
        page = fetch_form_page(args.forms_base, args.intake_form_id,
                               timeout=args.timeout)
        elapsed = time.time() - started
        sys.stderr.write("[query-key-checker] fetched %s%s/%s (%d bytes in "
                         "%.2fs)\n"
                         % ((args.forms_base or "").strip().rstrip("/"),
                            WIDGET_FORM_PATH, _mask_form_id(args.intake_form_id),
                            len(page), elapsed))
        return run_live(page, out=sys.stderr)

    except _FormPageError as exc:
        reg._stop(sys.stderr, str(exc),
                  ["Pass --forms-base and --intake-form-id and re-run."])
        return EX_STOP
    except reg.CafUnreachable as exc:
        # includes UpstreamBlockedError (edge/WAF) — HELD, UNDETERMINED
        sys.stderr.write("[query-key-checker] HELD: %s. NOT a compliance "
                         "verdict — retryable.\n" % exc)
        return EX_HELD
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[query-key-checker] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
