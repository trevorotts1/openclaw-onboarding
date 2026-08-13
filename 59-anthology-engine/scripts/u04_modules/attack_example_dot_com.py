#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u04_modules/attack_example_dot_com.py
# ATTACK FIXTURE — EXAMPLE.COM LINK, MUST FAIL (U04 brand-surface law).
# The adversarial sibling of the brand-surface legal-link gate
# (brand_link_checker.py, u04 item 1): an HTTPS link whose host is
# example.com — the IETF RFC 2606 reserved test domain — is a PLACEHOLDER
# destination that must never ship in a client's brand surface. This module
# ships the attack shape that MUST FAIL every example.com-link gate, in BOTH
# of its directions: the example.com link read is a FAIL (never a pass), and
# THIS module's own gate payload() must REFUSE shipping anything that is not
# exactly the one-host-wrong attack — a link with zero hosts, two hosts, the
# right host, or a non-https scheme is drift, never an attack fixture.
#
# THE ATTACK IS DETERMINISTIC AND SINGLE-VARIABLE: the canonical link is
# built by the SINGLE AUTHORITY (brand_link_checker.check_html — never a
# second implementation), then the ONE host is swapped to the reserved
# test-domain host, preserving the path, the scheme, and the fragment
# byte-for-byte. A real-domain link carrying the exact placeholder path is
# precisely the shape that must never pass a gate; the path is NOT part of
# the attack, so the failure isolates the host law and nothing else.
#
# THE "DOMAIN IS THE LAW" NOT-HARDCODED RULE (inherited from the gate): the
# placeholder host set is the RFC 2606 reserved test-domain family
# (example.com / example.net / example.org / example.edu, and the
# "example.*" namespace) — an exact, stable, spec-pinned blocklist. A
# client's own brand domain is NEVER the fixture's business: any host
# outside the reserved family is treated as real, so the attack link always
# carries the ONE adversarial host and the control link always carries a
# SYNTHETIC real-looking host (realbrandco.test — RFC 2606 reserved TLD,
# never a live domain, never a client domain).
#
# WHERE THIS SITS: scripts/u04_modules/ — an importable module under the U04
# intake/brand tooling, exactly like its sibling attack_bad_query.py. It is
# NOT a manifest row and NOT a checker: it ships the ADVERSARIAL FIXTURE the
# self-tests of the U04 link gates and their sibling checkers assert
# against, so the FAIL path is judged against the SAME surface the happy
# path judges against — a drift in the brand-link law (brand_link_checker)
# breaks THIS module's self-test first (fail-closed: an inconsistent law is
# a refusal, never a blind pass). Imported BY NAME as
# u04_modules.attack_example_dot_com from the engine scripts, per the
# u04_modules package contract (__init__.py: pure namespace container —
# fail-closed empty init, no runtime code). Standalone invocation works
# too: the SAME sys.path.insert bootstrap the sibling imports use resolves
# brand_link_checker / anthology_registry from scripts/.
#
# WHAT THIS OWNS:
#   1. attack_link(real_host, path) — the builder, fail-closed: the
#      canonical link is judged by brand_link_checker.check_html (the single
#      authority) BEFORE the swap, and the builder REFUSES a canonical link
#      that is not a clean, real-host, https legal row (the exact shape a
#      regression would produce); the one host is then swapped to
#      ATTACK_HOST and the rest is preserved byte-for-byte. A malformed host
#      or path raises FixtureError instead of shipping a wrong fixture.
#   2. verify_live(link) — the JUDGE: reports the link against the
#      brand-link law and exits 5 (mismatch family) on the example.com
#      attack, naming the placeholder host and the safe surface (host +
#      path only — the raw href, which can carry a query-string token, is
#      never echoed); on the true real-host golden link it exits 0. The one
#      place this module makes the FAIL explicit: an attack fixture that
#      PASSES any example.com-link gate is a broken gate.
#   3. payload() / payload_true() — the FAIL-CLOSED gates. payload() ships
#      the attack link (the fixture is the module's product) and exits 0
#      only when the attack is EXACTLY one wrong host; any drift (zero
#      hosts, the right host, a conflated authority) is REFUSED with exit 5
#      (verdict REFUSED). payload_true() is the control: the TRUE real-host
#      golden link passes exit 0, so the self-test's pass/fail split
#      discriminates the one-host-wrong boundary and never a broken
#      instrument (the negative-result contract: a negative is a claim and
#      carries the same burden of proof as a positive one — a gate that
#      fails everything is a broken check, not a real fault).
#
# DOCTRINE (inherited from the registry / the gate / U02 tooling):
#   - Never a token printed: this module holds and resolves NO credential —
#     the fixture is pure in-memory link metadata over a SYNTHETIC domain
#     (realbrandco.test) and SYNTHETIC path (/privacy), never a live
#     destination, and the verify surface reports the link by host + path
#     only, never the raw href (a query string can carry a token; the
#     never-a-token doctrine is inherited from brand_link_checker.py, which
#     never prints an href value). Nothing in this module can ever echo a
#     secret because no secret is ever read.
#   - Fail-closed: a drifted authority, an unparseable link, a non-https
#     shape, a non-example.com host all STOP or FAIL — never a blind pass,
#     never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#   - The GHL / Convert and Flow hosted-form surface is Cloudflare-fronted:
#     urllib's default "Python-urllib/x.y" User-Agent is 403'd at the WAF
#     edge (CF error 1010) before it ever reaches the API (CAF_BROWSER_UA in
#     anthology_registry.py is the house pattern). This module itself makes
#     NO network call — it ships the offline adversarial fixture only; any
#     sibling that DOES fetch brand pages must ride the house browser
#     User-Agent on every request, and the self-test pins the constant so a
#     registry regression is caught HERE first.
#
# EXIT CODE CONTRACT (house convention; mirrors the U02 verifier and the
# attack_bad_query sibling):
#   0  verified success — the golden real-host control link is internally
#      consistent and byte-exact to the brand-link law; also self-test /
#      plan OK
#   1  unexpected error (malformed input / no link to judge)
#   4  self-test FAILED (AF-AE-ATTACKEXAMPLEDOTCOM-* family, enforced
#      violation)
#   5  mismatch — the example.com attack link is FAIL (verify_live) or
#      REFUSED (payload under drift), never a blind pass
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to
# attack_bad_query.py: sys.path.insert to scripts/ then
# `import brand_link_checker as brand` / `import anthology_registry as reg`.
# =============================================================================
"""attack_example_dot_com.py — the example.com-link attack fixture that must FAIL.

The adversarial sibling of brand_link_checker.py: a deterministic one-host-wrong
HTTPS legal link (example.com in place of the real host) which every
example.com-link gate must refuse and which this module's own gates refuse
fail-closed (exit 5). The placeholder host is the RFC 2606 reserved test-domain
family — the domain is the law, never a hardcoded guess.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

# Sibling import bootstrap (house convention): the gate owns the brand-link
# law + the placeholder host family, the registry owns the Cloudflare
# browser-UA wiring — the module reuses them, never re-implements.
# brand_link_checker.py sits in THIS directory (u04_modules/), while the
# registry sits in scripts/ — both are on sys.path (absolute, __file__-
# relative, so standalone and BY-NAME invocation resolve the same way).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import brand_link_checker as brand  # noqa: E402
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The one fixed report contract.
ATTACK_CONTRACT = "anthology-engine-attack-example-dot-com"

# The adversarial host — the RFC 2606 reserved test-domain family, taken
# from the SINGLE AUTHORITY (brand_link_checker.PLACEHOLDER_HOSTS, never a
# second hardcoded list) and PINNED against the authority in the self-test
# (brand.PLACEHOLDER_HOSTS must carry "example.com"; if the authority ever
# drifts, the fixture's self-test breaks first, fail-closed). NEVER used to
# build a golden link — only to attack one.
ATTACK_HOST = "example.com"

# The control host — SYNTHETIC, deliberately never a live domain and never a
# client domain: realbrandco.test rides the RFC 2606 reserved .test TLD, so
# the golden control can never be mistaken for a real brand destination, and
# the attack can never be mistaken for touching a real client.
GOLDEN_HOST = "realbrandco.test"

# The legal-row path the fixture attacks (the shape the gate's legal-named
# anchor check rides on). SYNTHETIC fixture data — never a live path.
ATTACK_PATH = "/privacy"

# The synthetic source link the attack derives from (host swapped later):
# the legal row must be https, carry a real host, and be judged CLEAN by the
# single authority BEFORE the swap — a drift in the gate breaks the fixture's
# own self-test first (fail-closed: an inconsistent law is a refusal, never a
# blind pass).
SOURCE_LINK = "https://%s%s" % (GOLDEN_HOST, ATTACK_PATH)


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the brand-link
    authority or the link drifted from the law, so NO fixture is shipped — a
    wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# Link parsing helpers — fail-closed: an unparseable / law-less link is a
# refusal, never a verdict.
# ---------------------------------------------------------------------------
def _parse_link(link: str) -> tuple:
    """Split a link into a urlsplit 5-tuple. Refuses an empty or non-https
    link — the legal surface this fixture attacks is HTTPS only; anything
    else is drift, never judgeable."""
    if not isinstance(link, str) or not link.strip():
        raise FixtureError(
            "no link to judge — refusing to judge an empty surface "
            "(never fabricated).")
    parts = urlsplit(link.strip())
    if parts.scheme.lower() != "https":
        raise FixtureError(
            "link scheme is %r, not https — the legal surface this fixture "
            "attacks is HTTPS only; refusing to judge." % parts.scheme)
    return parts


def _host(parts) -> str:
    """The lowercase host of a parsed link. Fail-closed: a link with NO host
    (a bare path, a scheme-less absolute path) is drift, never judgeable."""
    host = (parts.hostname or "").lower()
    if not host:
        raise FixtureError(
            "link carries no host — refusing to judge a hostless surface.")
    return host


def _swap_host(link: str, new_host: str) -> str:
    """Swap the ONE host of a canonical link to new_host, preserving the
    scheme, the path, the query, and the fragment byte-for-byte. Fail-closed:
    a canonical link without exactly one host is drift, and a canonical that
    ALREADY carries a reserved-family host (the exact conflation a regression
    would produce) is a double-swap — both are refused, never swapped."""
    parts = _parse_link(link)
    host = _host(parts)
    if brand._host_flagged(host):
        raise FixtureError(
            "canonical link already carries the reserved test-domain host %r "
            "— the brand-link authority conflated the hosts; refusing to "
            "ship a double-swap attack." % host)
    if new_host != new_host.lower():
        raise FixtureError(
            "adversarial host %r must be lowercase — refusing." % new_host)
    return urlunsplit((parts.scheme, new_host, parts.path, parts.query,
                       parts.fragment))


# ---------------------------------------------------------------------------
# The attack builder — fail-closed, deterministic, golden-shaped minus the host.
# ---------------------------------------------------------------------------
def attack_link(real_host: str, path: str) -> str:
    """Build the attack link: the canonical link is judged by the SINGLE
    AUTHORITY (brand.check_html — never a second implementation) and must be
    a CLEAN real-host https legal row BEFORE the swap; the one host is then
    swapped to ATTACK_HOST. Any drift (a gate that flags the canonical, a
    non-https shape, a malformed host or path) raises FixtureError — a wrong
    fixture is never shipped."""
    if not isinstance(real_host, str) or not real_host.strip():
        raise FixtureError(
            "real_host %r is empty — refusing to attack an unparseable link."
            % (real_host,))
    if real_host.lower() == ATTACK_HOST:
        raise FixtureError(
            "real_host %r is already the adversarial host — the authority "
            "conflated the hosts; refusing to ship a double-swap attack."
            % real_host)
    canonical = "https://%s%s" % (real_host, path or "/")
    rep = brand.check_html(
        ("<html><body><footer><a href=\"%s\">Privacy Policy</a>"
         "</footer></body></html>" % canonical).encode("utf-8"))
    if not rep["ok"]:
        raise FixtureError(
            "the canonical link %s is NOT judged clean by the brand-link "
            "authority (flags %r) — the authority drifted; refusing to ship "
            "an attack payload." % (canonical, [f["flag"] for f in rep["flags"]]))
    return _swap_host(canonical, ATTACK_HOST)


# The canonical attack link, derived ONCE at import from the brand-link
# authority — fail-fast: a drifted authority breaks the import of the fixture
# itself, so the verifier that imports this module by name catches the drift
# first. The shipped link is built from SYNTHETIC fixture data (realbrandco
# .test / /privacy — never a live destination), so shipping it is harmless.
ATTACK_LINK = attack_link(GOLDEN_HOST, ATTACK_PATH)

# The golden control link, derived from the SAME authority — the pass side of
# the pass/fail split (a gate that fails everything is a broken instrument).
GOLDEN_LINK = "https://%s%s" % (GOLDEN_HOST, ATTACK_PATH)


# ---------------------------------------------------------------------------
# The judge — verify_live: the ONE surface that makes the FAIL explicit.
# ---------------------------------------------------------------------------
def _safe_href(link: str) -> str:
    """The SAFE surface form of a link: host + path only, NEVER the raw href
    (a query string can carry a token — the never-a-token doctrine inherited
    from the gate, which never prints an href value)."""
    try:
        parts = _parse_link(link)
    except FixtureError:
        return ""
    return (parts.hostname or "") + (parts.path or "")


def verify_live(link: str, *, out=None) -> int:
    """Judge a link against the brand-link host law.

    READ-ONLY and OFFLINE: the judged surface is whatever link the caller
    hands in — the canonical ATTACK_LINK fixture, the GOLDEN_LINK control, or
    a link piped from the brand surface (this module never makes a network
    call — the brand-link gate is pure local shape analysis, and the only
    thing that ever talks to Convert and Flow, reg.CafClient, sends
    CAF_BROWSER_UA on every request, the proven CF-1010 edge fix). The judge
    is the explicit fail: on the example.com attack the verdict is FAIL, exit
    5 (mismatch family), naming the placeholder host and the safe surface
    (host + path only); on the true real-host golden link the verdict is
    PASS, exit 0.

    Report: ONE JSON object on stdout (the link is reported by HOST + PATH
    only, never the raw href — a query string can carry a token), human notes
    on stderr. NEVER prints a token (it holds none: the fixture is pure
    in-memory link metadata)."""
    out = out or sys.stderr
    parts = _parse_link(link)
    host = _host(parts)
    flagged = brand._host_flagged(host)
    ok = not flagged
    detail = ("all brand checks pass: host %r is a real destination outside "
              "the RFC 2606 reserved test-domain family — the golden control "
              "PASSES this judge"
              % host if ok else (
                  "host %r is in the RFC 2606 reserved test-domain family "
                  "(placeholder) — the example.com link must FAIL, never a "
                  "pass" % host))
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "host": host,
        "safe_href": _safe_href(link),
        "placeholder_host": ATTACK_HOST if flagged else None,
        "detail": detail,
        "fail_closed": {
            "example_dot_com_fails": True,
            "host_law_required": True,
            "note": "a link whose host is example.com (RFC 2606 reserved "
                    "test domain) is FAIL, exit 5 — never a pass. An attack "
                    "fixture that passes ANY example.com-link gate is a "
                    "broken gate."},
    }, indent=2, sort_keys=True))
    if ok:
        out.write("[attack-example-dot-com] verify OK: %s\n" % detail)
        return EX_OK
    out.write("[attack-example-dot-com] verify FAIL: %s\n" % detail)
    return EX_MISMATCH


# ---------------------------------------------------------------------------
# Fail-closed payload gates — the offline verdict the self-test rides on.
# ---------------------------------------------------------------------------
def payload(*, out=None) -> int:
    """The FAIL-CLOSED gate: ship the attack link, but ONLY the one-host-wrong
    attack. Any drift — the authority conflating the hosts, an unparseable
    shape, a link the authority does not judge clean — is REFUSED with exit 5
    (verdict REFUSED, ok False), never shipped. Returns the exit code; emits
    the ONE JSON report object on stdout, human notes on stderr. The shipped
    link is built from SYNTHETIC fixture data (never a live destination), so
    shipping it is harmless."""
    out = out or sys.stderr
    try:
        link = attack_link(GOLDEN_HOST, ATTACK_PATH)
    except FixtureError as exc:
        out.write("[attack-example-dot-com] payload REFUSED: %s\n" % exc)
        print(json.dumps({
            "contract": ATTACK_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "link": None,
            "detail": str(exc),
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    parts = _parse_link(link)
    host = _host(parts)
    if host != ATTACK_HOST:
        out.write("[attack-example-dot-com] payload REFUSED: the attack link "
                  "carries host %r, not exactly [%r] — the fixture drifted; "
                  "refusing.\n" % (host, ATTACK_HOST))
        print(json.dumps({
            "contract": ATTACK_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "link": link,
            "host": host,
            "detail": "attack fixture must carry EXACTLY the one adversarial "
                      "host %r, got %r — drift." % (ATTACK_HOST, host),
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    if not brand._host_flagged(host):
        out.write("[attack-example-dot-com] payload REFUSED: the attack link "
                  "host %r is NOT flagged by the brand-link authority — the "
                  "host law drifted; refusing.\n" % host)
        print(json.dumps({
            "contract": ATTACK_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "link": link,
            "host": host,
            "detail": "the authority no longer flags the attack host %r — "
                      "the brand-link law regressed." % host,
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "link": link,
        "host": host,
        "path": parts.path,
        "safe_href": _safe_href(link),
        "detail": "attack link derived byte-exact from the brand-link "
                  "authority (brand_link_checker.check_html judged the "
                  "canonical clean, one host swapped %r -> %r, scheme/path/"
                  "fragment preserved): the example.com link that MUST FAIL "
                  "every example.com-link gate."
                  % (GOLDEN_HOST, ATTACK_HOST),
    }, indent=2, sort_keys=True))
    return EX_OK


def payload_true(*, out=None) -> int:
    """The CONTROL gate (negative-result contract): the TRUE real-host golden
    link must PASS exit 0 — so a payload gate that fails EVERYTHING (a broken
    instrument) is never mistaken for a real one-host-wrong discrimination.
    Judges the golden link via the brand-link authority (never a second
    implementation) and pins the law on it: if the authority ever regresses
    (flags the golden host, or the golden host drifts into the reserved
    family), the control REFUSES with exit 5 — a regression is caught HERE
    first."""
    out = out or sys.stderr
    rep = brand.check_html(
        ("<html><body><footer><a href=\"%s\">Privacy Policy</a>"
         "</footer></body></html>" % GOLDEN_LINK).encode("utf-8"))
    parts = _parse_link(GOLDEN_LINK)
    host = _host(parts)
    if not rep["ok"] or brand._host_flagged(host):
        out.write("[attack-example-dot-com] payload-true REFUSED: the golden "
                  "link host %r is flagged by the brand-link authority (flags "
                  "%r) — the authority regressed; refusing.\n"
                  % (host, [f["flag"] for f in rep["flags"]]))
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "link": None,
            "detail": "the brand-link authority no longer judges the golden "
                      "host %r clean (flags %r) — the authority regressed."
                      % (host, [f["flag"] for f in rep["flags"]]),
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-true",
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "link": GOLDEN_LINK,
        "host": host,
        "safe_href": _safe_href(GOLDEN_LINK),
        "detail": "control: the true real-host golden link passes exit 0 — "
                  "the example.com attack fails by comparison, never by a "
                  "broken gate.",
    }, indent=2, sort_keys=True))
    return EX_OK


def plan(*, out=None) -> int:
    """Offline plan (no network, no credentials): what the attack swaps and
    why, straight from the brand-link authority (the single source of truth —
    never a hardcoded law). One JSON object on stdout."""
    out = out or sys.stderr
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-plan",
        "schema_version": 1,
        "golden_host": GOLDEN_HOST,
        "attack_host": ATTACK_HOST,
        "host_count": 1,
        "path_preserved": True,
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed. The "
                "attack swaps the ONE host of a clean real-host https legal "
                "link from %r to %r (the RFC 2606 reserved test-domain "
                "family), preserving the scheme, the path, and the fragment "
                "byte-for-byte: the example.com link that MUST FAIL every "
                "example.com-link gate." % (GOLDEN_HOST, ATTACK_HOST),
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: fixture coherence + the fail-closed gates + the golden
# control, no network, no secrets. A FAILED self-test is exit 4 (enforced
# violation), never 'unexpected error' — the same discipline attack_bad_query
# and its siblings apply.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[attack-example-dot-com] SELF-TEST FAILED "
                         "(AF-AE-ATTACKEXAMPLEDOTCOM-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    import contextlib
    from types import MappingProxyType  # noqa: F401 -- import-time import guard only

    # ---- the authority is the single source of truth ------------------------
    assert ATTACK_HOST in brand.PLACEHOLDER_HOSTS, \
        "the brand-link authority must pin the reserved test-domain family, " \
        "got %r without %r" % (brand.PLACEHOLDER_HOSTS, ATTACK_HOST)
    assert brand.PLACEHOLDER_HOSTS == frozenset({
        "example.com", "example.net", "example.org", "example.edu",
        "www.example.com", "www.example.net", "www.example.org",
        "www.example.edu"}), \
        "the placeholder family must be the exact RFC 2606 blocklist, got %r" \
        % brand.PLACEHOLDER_HOSTS
    assert GOLDEN_HOST != ATTACK_HOST, \
        "the control host must differ from the adversarial host"
    assert not brand._host_flagged(GOLDEN_HOST), \
        "the synthetic control host realbrandco.test must never be flagged"
    assert brand._host_flagged(ATTACK_HOST), \
        "the adversarial host must be flagged by the brand-link authority"

    # ---- the canonical attack link: one host, wrong host, path preserved ----
    parts = urlsplit(ATTACK_LINK)
    assert (parts.hostname or "").lower() == ATTACK_HOST, \
        "the attack link must carry EXACTLY the one adversarial host, got %r" \
        % parts.hostname
    assert parts.scheme.lower() == "https", \
        "the attack link must keep the https scheme, got %r" % parts.scheme
    assert parts.path == ATTACK_PATH, \
        "the attack must preserve the path byte-for-byte, got %r" % parts.path
    assert ATTACK_LINK.startswith("https://example.com"), \
        "the attack link must be https://example.com-shaped, got %r" % ATTACK_LINK

    # ---- the judge: example.com read MUST FAIL, golden control MUST PASS ----
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(ATTACK_LINK, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "the example.com attack link must FAIL (exit 5), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "FAIL" and parsed["ok"] is False, \
        "the example.com read must be FAIL, got %s" % parsed["verdict"]
    assert parsed["host"] == ATTACK_HOST, \
        "the judge must name the placeholder host, got %r" % parsed["host"]
    assert parsed["placeholder_host"] == ATTACK_HOST, \
        "the judge must pin the placeholder host"
    assert parsed["fail_closed"]["example_dot_com_fails"] is True
    blob = buf.getvalue()
    assert "Bearer" not in blob and "pit-" not in blob and "sk-" not in blob, \
        "the judge output must never carry a token shape"
    assert ATTACK_HOST in parsed["safe_href"] and ATTACK_PATH in parsed["safe_href"], \
        "the judge must report the link by host + path only (got %r)" \
        % parsed["safe_href"]

    # the golden control PASSES the same judge (the pass/fail split is a
    # discrimination, never a broken instrument)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(GOLDEN_LINK, out=io.StringIO())
    assert rc == EX_OK, "the golden real-host link must PASS (exit 0), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "PASS" and parsed["ok"] is True, \
        "the golden read must be PASS, got %s" % parsed["verdict"]
    assert parsed["host"] == GOLDEN_HOST

    # ---- the judge's other FAIL directions (all never a pass) ---------------
    # 1. subdomain.example.com -> FAIL (the `(^|\.)example\.` law fires)
    sub = ATTACK_LINK.replace("https://example.com",
                              "https://subdomain.example.com")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(sub, out=io.StringIO())
    assert rc == EX_MISMATCH, "a subdomain.example.com link must FAIL (exit 5)"
    # 2. a golden link carrying an added query string -> STILL PASS (the host
    #    law is the only law the fixture attacks; the query is never echoed)
    queried = GOLDEN_LINK + "?utm_source=attacker"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(queried, out=io.StringIO())
    assert rc == EX_OK, "a queried golden link must still PASS (exit 0)"
    # 3. a non-https link is a REFUSAL (unjudgeable surface), never a verdict
    try:
        verify_live("http://example.com/privacy", out=io.StringIO())
        raise AssertionError("a non-https link was NOT refused")
    except FixtureError:
        pass
    # 4. a hostless link is a REFUSAL
    try:
        verify_live("https:///privacy", out=io.StringIO())
        raise AssertionError("a hostless link was NOT refused")
    except FixtureError:
        pass
    # 5. an empty surface is a REFUSAL
    try:
        verify_live("", out=io.StringIO())
        raise AssertionError("an empty link was NOT refused")
    except FixtureError:
        pass

    # ---- the fail-closed gates: the attack ships, the control passes --------
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(out=io.StringIO())
    assert rc == EX_OK, "payload on the true authority must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["host"] == ATTACK_HOST
    assert parsed["path"] == ATTACK_PATH
    assert parsed["contract"] == ATTACK_CONTRACT
    assert parsed["link"].startswith("https://example.com"), \
        "the payload fixture must be https://example.com-shaped"
    # the payload fixture never touches a live platform or brand domain
    assert "msgsndr" not in buf.getvalue() and "services.leadconnectorhq" \
        not in buf.getvalue(), \
        "the fixture must never reference a live platform domain"

    # the golden payload can never be mistaken for an ATTACK payload: the
    # attack gate REFUSES the golden host (the wrong direction is drift) --
    # cross-surface fail-closed proof.
    saved = brand._host_flagged
    try:
        brand._host_flagged = lambda h: h == GOLDEN_HOST  # the law regressed
        try:
            attack_link(GOLDEN_HOST, ATTACK_PATH)
            raise AssertionError("a conflated authority must be REFUSED")
        except FixtureError:
            pass
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = payload(out=io.StringIO())
        assert rc == EX_MISMATCH, \
            "payload under a conflated authority must REFUSE (exit 5), got %s" % rc
        assert json.loads(buf.getvalue())["verdict"] == "REFUSED"
    finally:
        brand._host_flagged = saved
    # after restore the payload ships again (the refusal was the drift, not
    # the instrument)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(out=io.StringIO())
    assert rc == EX_OK, "payload must ship again after the authority restored"

    # payload-true (the control): the true real-host golden link passes exit 0
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload_true(out=io.StringIO())
    assert rc == EX_OK, "payload-true on the true authority must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["host"] == GOLDEN_HOST

    # ---- attack fixtures: every drift REFUSED, never shipped ---------------
    # 1. the golden host passed as the adversarial real_host -> refusal
    try:
        attack_link(ATTACK_HOST, ATTACK_PATH)
        raise AssertionError("an already-adversarial host was NOT refused")
    except FixtureError:
        pass
    # 2. an empty real_host -> refusal
    try:
        attack_link("", ATTACK_PATH)
        raise AssertionError("an empty host was NOT refused")
    except FixtureError:
        pass
    # 3. a canonical link the authority does not judge clean -> refusal
    try:
        _swap_host("https://example.net" + ATTACK_PATH, ATTACK_HOST)
        raise AssertionError("a placeholder canonical was NOT refused")
    except FixtureError:
        pass
    # 4. a hostless canonical -> refusal
    try:
        _swap_host("https:///privacy", ATTACK_HOST)
        raise AssertionError("a hostless canonical was NOT refused")
    except FixtureError:
        pass
    # 5. an empty canonical -> refusal
    try:
        _swap_host("", ATTACK_HOST)
        raise AssertionError("an empty canonical was NOT refused")
    except FixtureError:
        pass
    # 6. a non-https canonical -> refusal
    try:
        _swap_host("http://" + GOLDEN_HOST + ATTACK_PATH, ATTACK_HOST)
        raise AssertionError("a non-https canonical was NOT refused")
    except FixtureError:
        pass

    # ---- the browser-UA pin: the edge fix is a house constant, never optional --
    assert reg.CAF_BROWSER_UA and reg.CAF_BROWSER_UA.startswith("Mozilla/"), \
        "CAF_BROWSER_UA must carry a browser User-Agent (the CF-1010 edge fix)"

    # ---- plan: offline, no network, exact swap ----
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = plan(out=io.StringIO())
    assert rc == EX_OK, "plan must exit 0"
    p = json.loads(buf.getvalue())
    assert p["golden_host"] == GOLDEN_HOST and p["attack_host"] == ATTACK_HOST
    assert p["host_count"] == 1 and p["path_preserved"] is True

    dev.write("attack_example_dot_com self-test: OK (brand-link authority "
              "pinned (RFC 2606 reserved family via PLACEHOLDER_HOSTS, "
              "realbrandco.test never flagged); canonical one-host attack "
              "link swapping %r -> %r with the scheme/path/fragment preserved "
              "byte-for-byte over synthetic fixture data; judge FAILs the "
              "example.com read with exit 5 naming the placeholder host and "
              "reports host + path only while the golden control PASSES exit "
              "0; subdomain.example.com FAILs, a queried golden link still "
              "PASSes, non-https / hostless / empty surfaces refuse; payload "
              "gate ships the one-host-wrong attack and REFUSES under a "
              "conflated authority while payload-true control PASSes the "
              "golden link; 6 attack fixtures refused (already-adversarial "
              "host / empty host / placeholder canonical / hostless canonical "
              "/ empty canonical / non-https canonical); never a token shape; "
              "CAF_BROWSER_UA pinned; plan offline)\n"
              % (GOLDEN_HOST, ATTACK_HOST))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="attack_example_dot_com.py",
        description="Attack fixture — example.com link, must FAIL (Skill 59, "
                    "U04 tooling): the adversarial sibling of the brand-link "
                    "legal gate, shipping the deterministic one-host-wrong "
                    "read (real host swapped to example.com, the RFC 2606 "
                    "reserved test-domain family) that every example.com-link "
                    "gate must refuse, and the fail-closed offline gates that "
                    "prove it (the golden real-host control PASSES).")
    ap.add_argument("--link", default=None,
                    help="link to judge (verify); defaults to the first "
                         "stdin line")
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
                sys.stderr.write("[attack-example-dot-com] no link given "
                                 "(--link or stdin) — nothing to judge.\n")
                return EX_ERR
            return verify_live(link, out=sys.stderr)
        return payload()
    except FixtureError as exc:
        sys.stderr.write("[attack-example-dot-com] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[attack-example-dot-com] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
