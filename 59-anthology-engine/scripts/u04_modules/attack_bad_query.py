#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u04_modules/attack_bad_query.py
# ATTACK FIXTURE — WRONG QUERY KEY, MUST FAIL (U04 intake-link surface).
# The adversarial sibling of the minted author-intake link: the ONE query key
# the GHL / Convert and Flow hosted form carries is anthology_id (G3 QUERY-KEY
# LAW, anthology_book.py:87-99 — the form's hidden-field key, NEVER
# anthology_active_id, which is the CONTACT custom field the delivery writer
# stamps with the ACTIVE anthology; conflating the two is the G3 defect this
# fixture pins shut). This module ships the attack shape that MUST FAIL every
# byte-exact query-key gate, in BOTH of its directions: the wrong-key read is
# a FAIL (never a pass), and THIS module's own gate payload() must REFUSE
# shipping anything that is not exactly the one-key-wrong attack — a link with
# zero, two, or the right key is drift, never an attack fixture.
#
# THE ATTACK IS DETERMINISTIC AND SINGLE-VARIABLE: the canonical link is built
# by the SINGLE AUTHORITY (anthology_book.build_intake_link — never a second
# implementation), then the ONE query key is swapped to the adversarial key,
# preserving the value byte-for-byte. A wrong key carrying the right minted id
# is exactly the G3 conflation shape that must never pass a gate; the value is
# NOT part of the attack, so the failure isolates the key law and nothing else.
#
# WHERE THIS SITS: scripts/u04_modules/ — an importable module under the U04
# intake-link tooling, exactly like its sibling attack_missing_field.py in
# u02_modules/. It is NOT a manifest row and NOT a checker: it ships the
# ADVERSARIAL FIXTURE the self-tests of the U04 link gate and its sibling
# checkers assert against, so the FAIL path is judged against the SAME surface
# the happy path judges against — a drift in the G3 authority (anthology_book)
# breaks THIS module's self-test first (fail-closed: an inconsistent law is a
# refusal, never a blind pass). Imported BY NAME as u04_modules.attack_bad_query
# from the engine scripts, per the u04_modules package contract (__init__.py:
# pure namespace container — fail-closed empty init, no runtime code).
# Standalone invocation works too: the SAME sys.path.insert bootstrap the
# sibling imports use resolves anthology_book / anthology_registry from scripts/.
#
# WHAT THIS OWNS:
#   1. attack_link(forms_base, form_id, anthology_id) — the builder, fail-
#      closed: the canonical link is built by anthology_book.build_intake_link
#      (the single authority), and the builder REFUSES a canonical link that
#      drifted from the G3 law (not exactly one key, or the key already is the
#      adversarial one — the exact conflation a regression would produce); a
#      malformed book id (the _bad_id_shape law) raises FixtureError instead of
#      shipping a wrong fixture. The one query key is then swapped to
#      ATTACK_QUERY_KEY and the value is preserved byte-for-byte.
#   2. verify_live(link) — the JUDGE: reports the link against the G3 query-key
#      law and exits 5 (mismatch family) on the wrong-key attack, naming the
#      wrong key and the expected one — never a pass; on the true one-key
#      golden link it exits 0. The one place this module makes the FAIL
#      explicit: an attack fixture that PASSES any query-key gate is a broken
#      gate. The value is reported by MASKED MARKER only (last 4 chars).
#   3. payload() / payload_true() — the FAIL-CLOSED gates. payload() ships the
#      attack link (the fixture is the module's product) and exits 0 only when
#      the attack is EXACTLY one wrong key; any drift (zero keys, two keys,
#      the right key, a conflated authority) is REFUSED with exit 5 (verdict
#      REFUSED). payload_true() is the control: the TRUE golden link passes
#      exit 0 and its own law pin catches a regression in the canonical
#      builder, so the self-test's pass/fail split discriminates the one-key-
#      wrong boundary and never a broken instrument (the negative-result
#      contract: a negative is a claim and carries the same burden of proof as
#      a positive one — a gate that fails everything is a broken check, not a
#      real fault).
#
# DOCTRINE (inherited from the registry / the producer minter / U02 tooling):
#   - Never a token printed: this module holds and resolves NO credential —
#     the fixture is pure in-memory link metadata over a SYNTHETIC book id
#     (ANTH_deadbeefcafebabed00d, deterministic fixture data, never a live
#     id), and the verify surface reports the id value by masked marker (last
#     4 chars) only. Nothing in this module can ever echo a secret because no
#     secret is ever read.
#   - Fail-closed: a drifted authority, an unparseable link, a non-G3 shape
#     all STOP or FAIL — never a blind pass, never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#   - The GHL hosted-form surface is Cloudflare-fronted: urllib's default
#     "Python-urllib/x.y" User-Agent is 403'd at the WAF edge (CF error 1010)
#     before it ever reaches the API (CAF_BROWSER_UA in anthology_registry.py
#     is the house pattern). This module itself makes NO network call — it
#     ships the offline adversarial fixture only; the client that DOES
#     (reg.CafClient) already sends CAF_BROWSER_UA on every request, and the
#     self-test pins the constant so a registry regression is caught HERE
#     first.
#
# EXIT CODE CONTRACT (house convention; mirrors the U02 verifier and the
# attack_missing_field sibling):
#   0  verified success — the golden one-key control link is internally
#      consistent and byte-exact to the G3 law; also self-test / plan OK
#   1  unexpected error (malformed input / no link to judge)
#   4  self-test FAILED (AF-AE-ATTACKBADQUERY-* family, enforced violation)
#   5  mismatch — the wrong-key attack link is FAIL (verify_live) or REFUSED
#      (payload under drift), never a blind pass
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to
# attack_missing_field.py: sys.path.insert to scripts/ then
# `import anthology_book as book` / `import anthology_registry as reg`.
# =============================================================================
"""attack_bad_query.py — the wrong-query-key attack fixture that must FAIL.

The adversarial sibling of the minted author-intake link: the ONE query key is
anthology_id (G3), the attack swaps it to anthology_active_id — the documented
G3 conflation — and every byte-exact query-key gate must refuse it while this
module's own gates refuse anything that is not exactly that shape (exit 5).
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

# Sibling import bootstrap (house convention): the producer minter owns the G3
# query-key law + the link builder, the registry owns the Cloudflare browser-UA
# wiring + the credential label resolution — the module reuses them, never
# re-implements.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_book as book  # noqa: E402  (the G3 authority: single source of truth)
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The one fixed report contract.
ATTACK_CONTRACT = "anthology-engine-attack-bad-query"

# The adversarial query key — the DOCUMENTED G3 conflation, hardcoded here and
# PINNED against the authority in the self-test (book.INTAKE_QUERY_KEY must be
# "anthology_id"; if the authority ever drifts, the fixture's self-test breaks
# first, fail-closed). NEVER used to build a golden link — only to attack one.
ATTACK_QUERY_KEY = "anthology_active_id"  # the CONTACT custom field, NOT the form key

# Deterministic SYNTHETIC fixture data — never a live id, never a live domain:
# the attack link the payload ships is built from these, so shipping it is
# harmless. Mirrors the book self-test's own synthetic surface
# ("https://forms.example.test/widget/form/form_self").
FORMS_BASE = "https://forms.example.test"          # synthetic fixture base, never live
FORM_ID = "form_self"                              # synthetic fixture form id, never live
SYNTHETIC_BOOK_ID = "ANTH_deadbeefcafebabed00d"     # 20 hex chars, the ANTH_ shape law


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the G3 authority
    or the link drifted from the law, so NO fixture is shipped — a wrong
    fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# Link parsing helpers — fail-closed: an unparseable / law-less link is a
# refusal, never a verdict.
# ---------------------------------------------------------------------------
def _parse_link(link: str) -> tuple:
    """Split a link into (parts, query_dict) with the query parsed by KEY with
    blank values kept (an empty value is a defect the judge must see, never
    silently dropped). Refuses an empty link."""
    if not isinstance(link, str) or not link.strip():
        raise FixtureError(
            "no link to judge — refusing to judge an empty surface "
            "(never fabricated).")
    parts = urlsplit(link.strip())
    q = parse_qs(parts.query, keep_blank_values=True)
    return parts, q


def _swap_query_key(link: str, new_key: str) -> str:
    """Swap the ONE query key of a canonical link to new_key, preserving the
    value byte-for-byte. Fail-closed: a canonical link with zero or multiple
    query pairs, or one that already carries new_key, is drift — refusing."""
    parts, q = _parse_link(link)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    if len(pairs) != 1:
        raise FixtureError(
            "canonical link carries %d query pair(s), not exactly 1 — refusing "
            "to attack an unparseable link." % len(pairs))
    old_key, value = pairs[0]
    if old_key == new_key:
        raise FixtureError(
            "canonical link already carries the adversarial key %r — the G3 "
            "authority conflated the keys; refusing to ship a double-swap "
            "attack." % new_key)
    query = urlencode([(new_key, value)], doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


# ---------------------------------------------------------------------------
# The attack builder — fail-closed, deterministic, golden-shaped minus the key.
# ---------------------------------------------------------------------------
def attack_link(forms_base: str, form_id: str, anthology_id: str) -> str:
    """Build the attack link: the canonical link comes from the SINGLE
    AUTHORITY (book.build_intake_link — never a second implementation), is
    checked against the G3 law (exactly one query key, and it is the golden
    key, never already the adversarial one), then the one key is swapped to
    ATTACK_QUERY_KEY. A malformed book id (the _bad_id_shape law) or any drift
    raises FixtureError — a wrong fixture is never shipped."""
    if book._bad_id_shape(anthology_id):
        raise FixtureError(
            "book id %r violates the _bad_id_shape law (empty, contains the "
            "composite-key delimiter, or > 256 chars) — refusing." % anthology_id)
    canonical = book.build_intake_link(forms_base, form_id, anthology_id)
    parts, q = _parse_link(canonical)
    keys = list(q.keys())
    if len(keys) != 1:
        raise FixtureError(
            "canonical link carries %d query key(s), not exactly 1 — the "
            "authority drifted from the G3 one-key law; refusing to ship an "
            "attack payload." % len(keys))
    if keys[0] != book.INTAKE_QUERY_KEY:
        raise FixtureError(
            "canonical link query key is %r, not the G3 key %r — the authority "
            "drifted; refusing to ship an attack payload."
            % (keys[0], book.INTAKE_QUERY_KEY))
    return _swap_query_key(canonical, ATTACK_QUERY_KEY)


# The canonical attack link, derived ONCE at import from the G3 authority —
# fail-fast: a drifted authority breaks the import of the fixture itself, so
# the verifier that imports this module by name catches the drift first.
ATTACK_LINK = attack_link(FORMS_BASE, FORM_ID, SYNTHETIC_BOOK_ID)

# The golden control link, derived from the SAME authority — the pass side of
# the pass/fail split (a gate that fails everything is a broken instrument).
GOLDEN_LINK = book.build_intake_link(FORMS_BASE, FORM_ID, SYNTHETIC_BOOK_ID)


# ---------------------------------------------------------------------------
# The judge — verify_live: the ONE surface that makes the FAIL explicit.
# ---------------------------------------------------------------------------
def _mask_marker(value: str) -> str:
    """A non-reversible marker for the link's id value: last 4 chars only
    (the same masking the registry applies to location ids)."""
    return reg._mask_location(value)


def _defects(link: str) -> tuple:
    """The G3 law checks, byte-exact: the link path must be the widget-form
    path, the query must carry EXACTLY one key, that key must be
    book.INTAKE_QUERY_KEY, it must not repeat, and the value must pass the
    _bad_id_shape law. Returns the list of defect names (empty == PASS)."""
    parts, q = _parse_link(link)
    bad = []
    path = parts.path or ""
    if not path.startswith(book.WIDGET_FORM_PATH):
        bad.append("path-not-widget-form")
    keys = list(q.keys())
    if len(keys) != 1:
        bad.append("key-count-%d" % len(keys))
    elif keys[0] != book.INTAKE_QUERY_KEY:
        bad.append("wrong-key")
        if len(q[keys[0]]) != 1:
            bad.append("duplicated-key")
    else:
        if len(q[keys[0]]) != 1:
            bad.append("duplicated-key")
        value = q[keys[0]][0]
        if book._bad_id_shape(value):
            bad.append("bad-value")
    return tuple(bad)


def verify_live(link: str, *, out=None) -> int:
    """Judge a link against the G3 query-key law.

    READ-ONLY and OFFLINE: the judged surface is whatever link the caller
    hands in — the canonical ATTACK_LINK fixture, the GOLDEN_LINK control, or
    a live link piped from `anthology_book.py intake-link` (this module never
    makes a network call — reg.CafClient is the only thing that ever talks to
    Convert and Flow, and it sends CAF_BROWSER_UA on every request, the
    proven CF-1010 edge fix). The judge is the explicit fail: on the wrong-key
    attack the verdict is FAIL, exit 5 (mismatch family), naming the wrong key
    and the expected one; on the true one-key golden link the verdict is PASS,
    exit 0.

    Report: ONE JSON object on stdout (the id value is reported by MASKED
    MARKER only — last 4 chars — never in full), human notes on stderr. NEVER
    prints a token (it holds none: the fixture is pure in-memory link
    metadata)."""
    out = out or sys.stderr
    bad = _defects(link)
    ok = not bad
    parts, q = _parse_link(link)
    keys = list(q.keys())
    value = ""
    if keys and len(q[keys[0]]) == 1:
        value = q[keys[0]][0]
    detail = ("all G3 checks pass: path %s, exactly one query key and it is %r "
              "— the golden control PASSES this judge"
              % (parts.path, book.INTAKE_QUERY_KEY) if ok else (
                  "%d defect(s) against the G3 law: %s — key(s) found %r, "
                  "expected exactly [%r]"
                  % (len(bad), ", ".join(bad), keys, book.INTAKE_QUERY_KEY)))
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "query_keys": keys,
        "expected_key": book.INTAKE_QUERY_KEY,
        "key_count": len(keys),
        "value_marker": _mask_marker(value),
        "path": parts.path,
        "defects": list(bad),
        "detail": detail,
        "fail_closed": {
            "wrong_key_fails": True,
            "byte_exact_required": True,
            "note": "a link whose ONE query key is not anthology_id (G3) is "
                    "FAIL, exit 5 — never a pass. An attack fixture that "
                    "passes ANY query-key gate is a broken gate."},
    }, indent=2, sort_keys=True))
    if ok:
        out.write("[attack-bad-query] verify OK: %s\n" % detail)
        return EX_OK
    out.write("[attack-bad-query] verify FAIL: %s\n" % detail)
    return EX_MISMATCH


# ---------------------------------------------------------------------------
# Fail-closed payload gates — the offline verdict the self-test rides on.
# ---------------------------------------------------------------------------
def payload(*, out=None) -> int:
    """The FAIL-CLOSED gate: ship the attack link, but ONLY the one-key-wrong
    attack. Any drift — the authority conflating the keys, a canonical link
    with zero or multiple keys, an unparseable shape — is REFUSED with exit 5
    (verdict REFUSED, ok False), never shipped. Returns the exit code; emits
    the ONE JSON report object on stdout, human notes on stderr. The shipped
    link is built from SYNTHETIC fixture data (never a live id, never a live
    domain), so shipping it is harmless."""
    out = out or sys.stderr
    try:
        link = attack_link(FORMS_BASE, FORM_ID, SYNTHETIC_BOOK_ID)
    except FixtureError as exc:
        out.write("[attack-bad-query] payload REFUSED: %s\n" % exc)
        print(json.dumps({
            "contract": ATTACK_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "link": None,
            "detail": str(exc),
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    parts, q = _parse_link(link)
    keys = list(q.keys())
    if keys != [ATTACK_QUERY_KEY]:
        out.write("[attack-bad-query] payload REFUSED: the attack link carries "
                  "query keys %r, not exactly [%r] — the fixture drifted; "
                  "refusing.\n" % (keys, ATTACK_QUERY_KEY))
        print(json.dumps({
            "contract": ATTACK_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "link": link,
            "query_keys": keys,
            "detail": "attack fixture must carry EXACTLY the one adversarial "
                      "key %r, got %r — drift." % (ATTACK_QUERY_KEY, keys),
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    value = q[keys[0]][0]
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "link": link,
        "query_keys": keys,
        "expected_key": book.INTAKE_QUERY_KEY,
        "value": value,
        "detail": "attack link derived byte-exact from the G3 authority "
                  "(anthology_book.build_intake_link, one query key swapped "
                  "%r -> %r, value preserved): the wrong-key read that MUST "
                  "FAIL every byte-exact query-key gate."
                  % (book.INTAKE_QUERY_KEY, ATTACK_QUERY_KEY),
    }, indent=2, sort_keys=True))
    return EX_OK


def payload_true(*, out=None) -> int:
    """The CONTROL gate (negative-result contract): the TRUE golden one-key
    link must PASS exit 0 — so a payload gate that fails EVERYTHING (a broken
    instrument) is never mistaken for a real one-key-wrong discrimination.
    Derives the golden link via the G3 authority (never a second
    implementation) and pins the law on it: if the canonical builder ever
    regresses (zero keys, two keys, the wrong key), the control REFUSES with
    exit 5 — a regression is caught HERE first."""
    out = out or sys.stderr
    link = book.build_intake_link(FORMS_BASE, FORM_ID, SYNTHETIC_BOOK_ID)
    parts, q = _parse_link(link)
    keys = list(q.keys())
    if keys != [book.INTAKE_QUERY_KEY] or len(q[keys[0]]) != 1:
        out.write("[attack-bad-query] payload-true REFUSED: the golden link "
                  "carries query keys %r, not exactly [%r] — the G3 authority "
                  "regressed; refusing.\n" % (keys, book.INTAKE_QUERY_KEY))
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "link": None,
            "detail": "the canonical builder no longer produces the one-key "
                      "golden link (keys %r) — the authority regressed."
                      % keys,
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    value = q[keys[0]][0]
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-true",
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "link": link,
        "query_keys": keys,
        "expected_key": book.INTAKE_QUERY_KEY,
        "value_marker": _mask_marker(value),
        "detail": "control: the true one-key golden link passes exit 0 — the "
                  "wrong-key attack fails by comparison, never by a broken "
                  "gate.",
    }, indent=2, sort_keys=True))
    return EX_OK


def plan(*, out=None) -> int:
    """Offline plan (no network, no credentials): what the attack swaps and
    why, straight from the G3 authority (the single source of truth — never a
    hardcoded law). One JSON object on stdout."""
    out = out or sys.stderr
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-plan",
        "schema_version": 1,
        "golden_key": book.INTAKE_QUERY_KEY,
        "attack_key": ATTACK_QUERY_KEY,
        "key_count": 1,
        "value_preserved": True,
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed. The "
                "attack swaps the ONE query key of the minted intake link "
                "from %r to %r (the G3 conflation), preserving the value "
                "byte-for-byte: the wrong-key read that MUST FAIL every "
                "byte-exact query-key gate." % (book.INTAKE_QUERY_KEY,
                                                ATTACK_QUERY_KEY),
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: fixture coherence + the fail-closed gates + the golden
# control, no network, no secrets. A FAILED self-test is exit 4 (enforced
# violation), never 'unexpected error' — the same discipline attack_missing_
# field.py and its siblings apply.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[attack-bad-query] SELF-TEST FAILED "
                         "(AF-AE-ATTACKBADQUERY-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    import contextlib
    from types import MappingProxyType  # noqa: F401 -- import-time import guard only

    # ---- the authority is the single source of truth ------------------------
    assert book.INTAKE_QUERY_KEY == "anthology_id", \
        "G3 authority must pin the query key to anthology_id, got %r" % book.INTAKE_QUERY_KEY
    assert book.WIDGET_FORM_PATH == "/widget/form", \
        "G3 authority must pin the widget-form path, got %r" % book.WIDGET_FORM_PATH
    assert ATTACK_QUERY_KEY != book.INTAKE_QUERY_KEY, \
        "the adversarial key must differ from the golden key (G3 conflation)"
    assert ATTACK_QUERY_KEY == "anthology_active_id", \
        "the adversarial key must be the documented G3 conflation"
    assert not book._bad_id_shape(SYNTHETIC_BOOK_ID), \
        "the synthetic fixture id must satisfy the _bad_id_shape law"

    # ---- the canonical attack link: one key, wrong key, value preserved -----
    parts, q = _parse_link(ATTACK_LINK)
    keys = list(q.keys())
    assert keys == [ATTACK_QUERY_KEY], \
        "the attack link must carry EXACTLY the one adversarial key, got %r" % keys
    assert q[keys[0]] == [SYNTHETIC_BOOK_ID], \
        "the attack must preserve the value byte-for-byte (wrong key, right value)"
    assert parts.path == "/widget/form/" + FORM_ID, \
        "the attack link must keep the golden path, got %r" % parts.path
    assert parts.netloc == "forms.example.test", \
        "the attack link must never carry a live domain, got %r" % parts.netloc

    # ---- the judge: wrong-key read MUST FAIL, golden control MUST PASS ------
    import io as _io
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(ATTACK_LINK, out=_io.StringIO())
    assert rc == EX_MISMATCH, "the wrong-key attack link must FAIL (exit 5), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "FAIL" and parsed["ok"] is False, \
        "the wrong-key read must be FAIL, got %s" % parsed["verdict"]
    assert parsed["query_keys"] == [ATTACK_QUERY_KEY], \
        "the judge must name the wrong key, got %r" % parsed["query_keys"]
    assert parsed["expected_key"] == "anthology_id", \
        "the judge must name the expected G3 key"
    assert parsed["defects"] == ["wrong-key"], \
        "the attack must fail on the key law and NOTHING else, got %r" % parsed["defects"]
    assert parsed["key_count"] == 1

    # the judge NEVER prints a token or a full id (masked marker only)
    assert parsed["value_marker"] == "...d00d", \
        "the id value must be masked to the last-4 marker, got %r" % parsed["value_marker"]
    blob = buf.getvalue()
    assert SYNTHETIC_BOOK_ID not in blob, \
        "the judge output must never carry the full id value"
    assert "pit-" not in blob and "Bearer" not in blob, \
        "the judge output must never carry a token shape"

    # the golden control PASSES the same judge (the pass/fail split is a
    # discrimination, never a broken instrument)
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(GOLDEN_LINK, out=_io.StringIO())
    assert rc == EX_OK, "the golden one-key link must PASS (exit 0), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "PASS" and parsed["ok"] is True, \
        "the golden read must be PASS, got %s" % parsed["verdict"]
    assert parsed["query_keys"] == ["anthology_id"] and parsed["defects"] == []

    # ---- the judge's other FAIL directions (all never a pass) ---------------
    # 1. two query keys (the right one plus a stowaway) -> FAIL
    dup = GOLDEN_LINK + "&utm_source=attacker"
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(dup, out=_io.StringIO())
    assert rc == EX_MISMATCH, "a two-key link must FAIL (exit 5), got %s" % rc
    assert json.loads(buf.getvalue())["defects"] == ["key-count-2"], \
        "the two-key read must fail on the key-count law"
    # 2. the right key with an EMPTY value -> FAIL (never a silent drop)
    empty = GOLDEN_LINK.rsplit("=", 1)[0] + "="
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(empty, out=_io.StringIO())
    assert rc == EX_MISMATCH, "an empty-value link must FAIL (exit 5), got %s" % rc
    assert "bad-value" in json.loads(buf.getvalue())["defects"]
    # 3. a query-less link is still judgeable -> FAIL on the key-count law
    #    (zero keys is a defect, never a pass)
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(GOLDEN_LINK.split("?", 1)[0], out=_io.StringIO())
    assert rc == EX_MISMATCH, "a key-count-0 link must FAIL (exit 5), got %s" % rc
    assert json.loads(buf.getvalue())["defects"] == ["key-count-0"], \
        "the query-less read must fail on the key-count law"
    # 4. a non-link surface is a REFUSAL
    try:
        verify_live("", out=_io.StringIO())
        raise AssertionError("an empty link was NOT refused")
    except FixtureError:
        pass

    # ---- the fail-closed gates: the attack ships, the control passes --------
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(out=_io.StringIO())
    assert rc == EX_OK, "payload on the true authority must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["query_keys"] == [ATTACK_QUERY_KEY]
    assert parsed["expected_key"] == "anthology_id"
    assert parsed["value"] == SYNTHETIC_BOOK_ID
    assert parsed["contract"] == ATTACK_CONTRACT
    # the payload fixture never touches a live platform domain
    assert "msgsndr" not in buf.getvalue(), \
        "the fixture must never reference the live hosted-form domain"

    # the golden payload can never be mistaken for an ATTACK payload: the
    # attack gate REFUSES the golden key (the wrong direction is drift) --
    # cross-surface fail-closed proof.
    saved_key = book.INTAKE_QUERY_KEY
    try:
        book.INTAKE_QUERY_KEY = ATTACK_QUERY_KEY  # the G3 conflation regressed
        try:
            attack_link(FORMS_BASE, FORM_ID, SYNTHETIC_BOOK_ID)
            raise AssertionError("a conflated authority must be REFUSED")
        except FixtureError:
            pass
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = payload(out=_io.StringIO())
        assert rc == EX_MISMATCH, \
            "payload under a conflated authority must REFUSE (exit 5), got %s" % rc
        assert json.loads(buf.getvalue())["verdict"] == "REFUSED"
    finally:
        book.INTAKE_QUERY_KEY = saved_key
    # after restore the payload ships again (the refusal was the drift, not
    # the instrument)
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(out=_io.StringIO())
    assert rc == EX_OK, "payload must ship again after the authority restored"

    # payload-true (the control): the true one-key golden link passes exit 0
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload_true(out=_io.StringIO())
    assert rc == EX_OK, "payload-true on the true authority must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["query_keys"] == ["anthology_id"]

    # ---- attack fixtures: every drift REFUSED, never shipped ---------------
    # 1. a malformed book id (the composite-key delimiter) -> refusal
    try:
        attack_link(FORMS_BASE, FORM_ID, "ANTH_bad::delim")
        raise AssertionError("a delimiter-carrying id was NOT refused")
    except FixtureError:
        pass
    # 2. an empty book id -> refusal
    try:
        attack_link(FORMS_BASE, FORM_ID, "")
        raise AssertionError("an empty id was NOT refused")
    except FixtureError:
        pass
    # 3. a canonical link that already carries the adversarial key -> refusal
    try:
        _swap_query_key(GOLDEN_LINK.replace("anthology_id", ATTACK_QUERY_KEY),
                        ATTACK_QUERY_KEY)
        raise AssertionError("a double-swap was NOT refused")
    except FixtureError:
        pass
    # 4. a canonical link with two query pairs -> refusal
    try:
        _swap_query_key(GOLDEN_LINK + "&utm_source=attacker", ATTACK_QUERY_KEY)
        raise AssertionError("a two-pair canonical link was NOT refused")
    except FixtureError:
        pass
    # 5. an empty link -> refusal
    try:
        _swap_query_key("", ATTACK_QUERY_KEY)
        raise AssertionError("an empty link was NOT refused")
    except FixtureError:
        pass

    # ---- the browser-UA pin: the edge fix is a house constant, never optional --
    assert reg.CAF_BROWSER_UA and reg.CAF_BROWSER_UA.startswith("Mozilla/"), \
        "CAF_BROWSER_UA must carry a browser User-Agent (the CF-1010 edge fix)"

    # ---- plan: offline, no network, exact swap ----
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = plan(out=_io.StringIO())
    assert rc == EX_OK, "plan must exit 0"
    p = json.loads(buf.getvalue())
    assert p["golden_key"] == "anthology_id" and p["attack_key"] == ATTACK_QUERY_KEY
    assert p["key_count"] == 1 and p["value_preserved"] is True

    dev.write("attack_bad_query self-test: OK (G3 authority pinned "
              "(anthology_id / /widget/form); canonical one-key attack link "
              "swapping %r -> %r with the value preserved byte-for-byte over "
              "synthetic fixture data; judge FAILs the wrong-key read with "
              "exit 5 naming the wrong key and masks the id to the last-4 "
              "marker while the golden control PASSES exit 0; two-key / "
              "empty-value reads FAIL, query-less and empty links refuse; "
              "payload gate ships the one-key-wrong attack and REFUSES under "
              "a conflated authority while payload-true control PASSes the "
              "golden link; 5 attack fixtures refused (delimiter id / empty "
              "id / double-swap / two-pair canonical / empty link); "
              "CAF_BROWSER_UA pinned; plan offline)\n"
              % (book.INTAKE_QUERY_KEY, ATTACK_QUERY_KEY))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="attack_bad_query.py",
        description="Attack fixture — wrong query key on the minted intake "
                    "link, must FAIL (Skill 59, U04 tooling): the adversarial "
                    "sibling of anthology_book.build_intake_link, shipping the "
                    "deterministic G3-conflation read (anthology_id swapped to "
                    "anthology_active_id, value preserved) that every "
                    "byte-exact query-key gate must refuse, and the fail-closed "
                    "offline gates that prove it (the golden one-key control "
                    "PASSES).")
    ap.add_argument("--link", default=None,
                    help="link to judge (verify); defaults to the first "
                         "stdin line (e.g. `anthology_book.py intake-link ... "
                         "| attack_bad_query.py --live`)")
    ap.add_argument("cmd", nargs="?", choices=["payload", "payload-true",
                                               "verify", "plan", "self-test"],
                    default="payload")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest / --live -> positional subcommands
    # (the same normalization the registry and the U02 verifier use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    if "--live" in argv:
        argv = ["verify" if a == "--live" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            return plan()
        if args.cmd == "payload-true":
            return payload_true()
        if args.cmd == "verify":
            link = args.link or sys.stdin.read().strip()
            if not link:
                sys.stderr.write("[attack-bad-query] no link given (--link or "
                                 "stdin) — nothing to judge.\n")
                return EX_ERR
            return verify_live(link, out=sys.stderr)
        return payload()
    except FixtureError as exc:
        sys.stderr.write("[attack-bad-query] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[attack-bad-query] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
