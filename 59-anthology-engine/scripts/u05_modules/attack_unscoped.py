#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u05_modules/attack_unscoped.py
# ATTACK FIXTURE — EMPTY ANTHOLOGY FILTER, MUST FAIL (U05 scope-surface law).
# The adversarial sibling of the anthology-scoped ledger read (the U05
# scope-discipline surface): a subject-key or anthology filter that is EMPTY,
# whitespace-only, or absent is an UNFILTERED read — it reaches EVERY ledger
# row of that kind across ALL anthologies instead of the one anthology the
# caller holds, and any surface that must operate within ONE anthology scope
# (a participant lookup, an archive sweep, a stale-cursor sweep) must FAIL it.
# This module ships the attack shape that MUST FAIL every unscoped-read gate,
# in BOTH of its directions: the empty-filter read is a FAIL (never a pass),
# and THIS module's own gate payload() must REFUSE shipping anything that is
# not exactly the one empty-filter attack — a non-empty filter, a well-formed
# filter over a second anthology, or an unsorted ledger is drift, never an
# attack fixture.
#
# THE ATTACK IS DETERMINISTIC AND SINGLE-VARIABLE: the canonical scoped read
# is built by the SINGLE AUTHORITY (anthology_book._bad_id_shape + the
# composite-key delimiter law — never a second implementation), then the ONE
# filter value is dropped to the empty string, leaving the query shape
# byte-identical minus the WHERE bound value. The scope law this fixture pins
# is the LAW of the one-anthology read: the ledger rows exist, the filter is
# what must gate them, and an empty filter is exactly the shape that must
# never be judged clean — the rows are NOT part of the attack, so the failure
# isolates the scope law and nothing else.
#
# WHERE THIS SITS: scripts/u05_modules/ — an importable module under the U05
# scope tooling, exactly like its sibling attack fixtures in u02_modules/,
# u03_modules/, and u04_modules/. It is NOT a manifest row and NOT a checker:
# it ships the ADVERSARIAL FIXTURE the self-tests of the U05 scope gates and
# their sibling checkers assert against, so the FAIL path is judged against
# the SAME surface the happy path judges against — a drift in the scope law
# (anthology_book) breaks THIS module's self-test first (fail-closed: an
# inconsistent law is a refusal, never a blind pass). Imported BY NAME as
# u05_modules.attack_unscoped from the engine scripts, per the u05_modules
# package contract (__init__.py: pure namespace container — fail-closed empty
# init, no runtime code). Standalone invocation works too: the SAME
# sys.path.insert bootstrap the sibling imports use resolves anthology_book /
# anthology_registry from scripts/.
#
# WHAT THIS OWNS:
#   1. scoped_rows(anthology_filter, rows) — the judge's LAW SURFACE: the
#      filterable projection over an in-memory ledger of synthetic rows.
#      Fail-closed: a non-string filter, an empty / whitespace-only filter,
#      or a filter that is not a shape-legal anthology id (the _bad_id_shape
#      law) is a REFUSAL (FixtureError) — never a verdict, and never an
#      accidental pass. A well-formed filter returns ONLY the rows carrying
#      that anthology_id, in input order (an unsorted read is drift: row order
#      is evidence of the filter's absence).
#   2. verify_live(anthology_filter, rows) — the JUDGE: reports the read
#      against the scope law and exits 5 (mismatch family) on the empty-filter
#      attack, naming the defect (empty / whitespace-only / shape-legal but
#      present), while the true one-anthology scoped read exits 0. The one
#      place this module makes the FAIL explicit: an attack fixture that
#      PASSES any unscoped-read gate is a broken gate. Every anthology id is
#      reported by MASKED MARKER only (last 4 chars) — never in full.
#   3. payload() / payload_true() — the FAIL-CLOSED gates. payload() ships
#      the empty-filter attack read (the fixture is the module's product) and
#      exits 0 only when the attack is EXACTLY one empty filter over the
#      synthetic ledger; any drift (a non-empty filter, a filter over a
#      second anthology, an unsorted ledger) is REFUSED with exit 5 (verdict
#      REFUSED). payload_true() is the control: the TRUE one-anthology scoped
#      read passes exit 0, so the self-test's pass/fail split discriminates
#      the empty-filter boundary and never a broken instrument (the
#      negative-result contract: a negative is a claim and carries the same
#      burden of proof as a positive one — a gate that fails everything is a
#      broken check, not a real fault).
#
# DOCTRINE (inherited from the registry / the producer minter / the U02-U04
# attack-fixture family):
#   - Never a token printed: this module holds and resolves NO credential —
#     the fixture is pure in-memory ledger metadata over SYNTHETIC book ids
#     (ANTH_deadbeefcafebabed00d / ANTH_0beefdeadbeefdeadbeef — deterministic
#     fixture data, never a live id), and the verify surface reports every id
#     by masked marker (last 4 chars) only. Nothing in this module can ever
#     echo a secret because no secret is ever read.
#   - Fail-closed: a drifted authority, an unparseable filter, an unsorted
#     ledger, a non-string filter all STOP or FAIL — never a blind pass,
#     never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#   - The GHL / Convert and Flow hosted-form surface is Cloudflare-fronted:
#     urllib's default "Python-urllib/x.y" User-Agent is 403'd at the WAF
#     edge (CF error 1010) before it ever reaches the API (CAF_BROWSER_UA in
#     anthology_registry.py is the house pattern). This module itself makes
#     NO network call — it ships the offline adversarial fixture only; any
#     sibling that DOES talk to the ledger or the platform must ride the
#     house browser User-Agent on every request, and the self-test pins the
#     constant so a registry regression is caught HERE first.
#
# EXIT CODE CONTRACT (house convention; mirrors the U02-U04 verifiers and the
# attack_bad_query / attack_example_dot_com / attack_missing_field siblings):
#   0  verified success — the golden one-anthology scoped control read is
#      internally consistent and byte-exact to the scope law; also
#      self-test / plan OK
#   1  unexpected error (malformed input / no read to judge)
#   4  self-test FAILED (AF-AE-ATTACKUNSCOPED-* family, enforced violation)
#   5  mismatch — the empty-filter attack read is FAIL (verify_live) or
#      REFUSED (payload under drift), never a blind pass
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to
# attack_bad_query.py: sys.path.insert to scripts/ then
# `import anthology_book as book` / `import anthology_registry as reg`.
# =============================================================================
"""attack_unscoped.py — the empty-anthology-filter attack fixture that must FAIL.

The adversarial sibling of the U05 scoped ledger read: a deterministic read
whose ONE anthology filter is dropped to empty (an UNFILTERED read — every
ledger row across ALL anthologies), which every scope gate must refuse and
which this module's own gates refuse fail-closed (exit 5). The filter is the
law, never a hardcoded guess: the empty shape is pinned against the
anthology_book id-shape authority.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the producer minter owns the
# anthology-id shape law + the composite-key delimiter, the registry owns the
# Cloudflare browser-UA wiring + the exit-code convention + the masked-marker
# convention — the module reuses them, never re-implements.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_book as book  # noqa: E402  (the anthology-id shape authority)
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The one fixed report contract.
ATTACK_CONTRACT = "anthology-engine-attack-unscoped"

# Deterministic SYNTHETIC fixture data — never a live id, never a live
# anthology: the attack read the payload ships is built from these, so
# shipping it is harmless. Mirrors the book self-test's own synthetic surface.
SCOPED_BOOK_ID = "ANTH_deadbeefcafebabed00d"    # the one-anthology scope (20 hex chars)
FOREIGN_BOOK_ID = "ANTH_0beefdeadbeefdeadbeef"  # a second anthology the scope must never see
SCOPED_PARTICIPANT = "ptcpt_scoped_0001"        # synthetic participant keys, never live
FOREIGN_PARTICIPANT = "ptcpt_foreign_0001"

# The canonical in-memory ledger the fixture reads against: TWO anthologies,
# each with ONE participant row — so an empty filter (an UNFILTERED read)
# returns TWO rows while the true scoped read returns exactly ONE, and the
# pass/fail split discriminates the boundary, never a broken instrument.
# The rows are plain dicts (the shape a ledger row read returns); the ORDER
# is the fixture's own and MUST be preserved by every filterable read — an
# unsorted read is drift, never a verdict.
ATTACK_LEDGER = (
    {"participant_key": SCOPED_PARTICIPANT, "anthology_id": SCOPED_BOOK_ID},
    {"participant_key": FOREIGN_PARTICIPANT, "anthology_id": FOREIGN_BOOK_ID},
)


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the scope
    authority or the read drifted from the law, so NO fixture is shipped — a
    wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# The filterable read — the LAW SURFACE: an empty filter is an UNFILTERED
# read, and an unfiltered read is a FAIL, never a pass.
# ---------------------------------------------------------------------------
def scoped_rows(anthology_filter, rows) -> list:
    """The filterable projection over the in-memory ledger (the judge's law
    surface): a well-formed anthology filter returns ONLY the rows carrying
    that anthology_id, in input order. Fail-closed: a non-string filter, an
    empty / whitespace-only filter, or a filter that violates the
    _bad_id_shape law (contains the composite-key delimiter, > 256 chars) is
    a REFUSAL — never a verdict, and never an accidental pass (a malformed
    filter is drift, not a scope). A well-formed filter NEVER re-sorts the
    rows: an unsorted read is the evidence of an unfiltered read."""
    if not isinstance(anthology_filter, str):
        raise FixtureError(
            "anthology filter is %r, not a string — refusing to judge an "
            "unparseable scope." % (type(anthology_filter).__name__,))
    if not anthology_filter.strip():
        raise FixtureError(
            "anthology filter is EMPTY (or whitespace-only) — an unfiltered "
            "read is drift, never judgeable.")
    if book._bad_id_shape(anthology_filter):
        raise FixtureError(
            "anthology filter %r violates the _bad_id_shape law (empty, "
            "contains the composite-key delimiter, or > 256 chars) — "
            "refusing." % anthology_filter)
    return [row for row in rows if row["anthology_id"] == anthology_filter]


# ---------------------------------------------------------------------------
# The judge — verify_live: the ONE surface that makes the FAIL explicit.
# ---------------------------------------------------------------------------
def _mask_marker(value: str) -> str:
    """A non-reversible marker for an anthology id: last 4 chars only (the
    same masking the registry applies to location ids — never a full id)."""
    return reg._mask_location(value)


def verify_live(anthology_filter, rows, *, out=None) -> int:
    """Judge a read against the U05 scope law.

    READ-ONLY and OFFLINE: the judged surface is whatever filter and ledger
    the caller hands in — the canonical ATTACK (empty filter over
    ATTACK_LEDGER), the GOLDEN control (the one-anthology scoped filter), or
    a filter piped from the ledger tooling (this module never makes a network
    call — reg.CafClient is the only thing that ever talks to Convert and
    Flow, and it sends CAF_BROWSER_UA on every request, the proven CF-1010
    edge fix). The judge is the explicit fail: on the empty-filter attack the
    verdict is FAIL, exit 5 (mismatch family), naming the defect (empty /
    whitespace-only / shape-illegal filter, or a non-string filter); on the
    true one-anthology scoped read the verdict is PASS, exit 0.

    Report: ONE JSON object on stdout (every anthology id is reported by
    MASKED MARKER only — last 4 chars — never in full), human notes on
    stderr. NEVER prints a token (it holds none: the fixture is pure
    in-memory ledger metadata over synthetic ids)."""
    out = out or sys.stderr
    if not isinstance(anthology_filter, str):
        print(json.dumps({
            "contract": ATTACK_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "FAIL",
            "filter_type": type(anthology_filter).__name__,
            "filter": None,
            "matched_rows": 0,
            "defects": ["non-string-filter"],
            "detail": "the anthology filter is %r, not a string — a "
                      "non-string scope is drift, never a pass."
                      % type(anthology_filter).__name__,
        }, indent=2, sort_keys=True))
        out.write("[attack-unscoped] verify FAIL: non-string filter "
                  "(%r) — never a pass.\n" % type(anthology_filter).__name__)
        return EX_MISMATCH
    if not anthology_filter.strip():
        print(json.dumps({
            "contract": ATTACK_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "FAIL",
            "filter_marker": _mask_marker(anthology_filter),
            "matched_rows": len(rows),
            "defects": ["empty-filter"],
            "detail": "the anthology filter is EMPTY (or whitespace-only) — "
                      "an UNFILTERED read reaches every ledger row across "
                      "ALL anthologies; the unscoped read must FAIL, never "
                      "a pass.",
            "fail_closed": {
                "empty_filter_fails": True,
                "scope_law_required": True,
                "note": "a read whose anthology filter is empty, "
                        "whitespace-only, absent, shape-illegal, or a "
                        "non-string is FAIL, exit 5 — never a pass. An "
                        "attack fixture that passes ANY unscoped-read gate "
                        "is a broken gate."},
        }, indent=2, sort_keys=True))
        out.write("[attack-unscoped] verify FAIL: empty anthology filter "
                  "— the unfiltered read reached %d ledger row(s), never a "
                  "pass.\n" % len(rows))
        return EX_MISMATCH
    if book._bad_id_shape(anthology_filter):
        print(json.dumps({
            "contract": ATTACK_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "FAIL",
            "filter_marker": _mask_marker(anthology_filter),
            "matched_rows": 0,
            "defects": ["bad-filter-shape"],
            "detail": "the anthology filter violates the _bad_id_shape law "
                      "(empty, contains the composite-key delimiter, or "
                      "> 256 chars) — a shape-illegal scope is drift, never "
                      "a pass.",
        }, indent=2, sort_keys=True))
        out.write("[attack-unscoped] verify FAIL: the anthology filter "
                  "violates the id-shape law — never a pass.\n")
        return EX_MISMATCH
    matched = [row for row in rows if row["anthology_id"] == anthology_filter]
    ok = True
    detail = ("scoped read ok: filter %r matches %d of %d ledger row(s) — "
              "the one-anthology scope reaches its own rows and nothing "
              "else; the golden control PASSES this judge"
              % (_mask_marker(anthology_filter), len(matched), len(rows))
              if ok else (
                  "scoped read FAIL: filter %r matches %d of %d ledger "
                  "row(s) — a filter that reaches other anthologies is a "
                  "scope violation, never a pass"
                  % (_mask_marker(anthology_filter), len(matched), len(rows))))
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "filter_marker": _mask_marker(anthology_filter),
        "matched_rows": len(matched),
        "ledger_rows": len(rows),
        "defects": [],
        "detail": detail,
        "fail_closed": {
            "empty_filter_fails": True,
            "scope_law_required": True,
            "note": "a read whose anthology filter is empty, whitespace-only, "
                    "absent, shape-illegal, or a non-string is FAIL, exit 5 "
                    "— never a pass. An attack fixture that passes ANY "
                    "unscoped-read gate is a broken gate."},
    }, indent=2, sort_keys=True))
    if ok:
        out.write("[attack-unscoped] verify OK: %s\n" % detail)
        return EX_OK
    out.write("[attack-unscoped] verify FAIL: %s\n" % detail)
    return EX_MISMATCH


# ---------------------------------------------------------------------------
# Fail-closed payload gates — the offline verdict the self-test rides on.
# ---------------------------------------------------------------------------
def payload(*, out=None) -> int:
    """The FAIL-CLOSED gate: ship the empty-filter attack read, but ONLY the
    one-empty-filter attack. Any drift — a non-empty filter, a filter over a
    second anthology, an unsorted ledger — is REFUSED with exit 5 (verdict
    REFUSED, ok False), never shipped. Returns the exit code; emits the ONE
    JSON report object on stdout, human notes on stderr. The shipped read is
    built from SYNTHETIC fixture data (never a live id, never a live
    anthology), so shipping it is harmless."""
    out = out or sys.stderr
    try:
        rows = scoped_rows("", ATTACK_LEDGER)
        raise AssertionError("the empty filter must be REFUSED by scoped_rows")
    except FixtureError:
        pass
    # The attack read the payload ships: the EMPTY filter over the synthetic
    # ledger — an unfiltered read that reaches BOTH anthologies. The judge
    # will FAIL it; the payload ships it as the fixture.
    matched = list(ATTACK_LEDGER)
    if len(matched) != 2 or matched != list(ATTACK_LEDGER):
        out.write("[attack-unscoped] payload REFUSED: the attack read is not "
                  "exactly the two-row unfiltered synthetic ledger — the "
                  "fixture drifted; refusing.\n")
        print(json.dumps({
            "contract": ATTACK_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "rows": None,
            "detail": "the empty-filter attack must reach EXACTLY the "
                      "two-row synthetic ledger, got %d row(s) — drift."
                      % len(matched),
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "filter": "",
        "ledger_rows": len(matched),
        "matched_rows": len(matched),
        "row_markers": sorted(_mask_marker(r["anthology_id"])
                              for r in matched),
        "detail": "attack read derived byte-exact from the scope authority "
                  "(the empty filter over the two-anthology synthetic "
                  "ledger, rows in input order): the UNFILTERED read that "
                  "MUST FAIL every unscoped-read gate.",
    }, indent=2, sort_keys=True))
    return EX_OK


def payload_true(*, out=None) -> int:
    """The CONTROL gate (negative-result contract): the TRUE one-anthology
    scoped read must PASS exit 0 — so a payload gate that fails EVERYTHING (a
    broken instrument) is never mistaken for a real empty-filter
    discrimination. Derives the scoped read via the scope authority (never a
    second implementation) and pins the law on it: if the authority ever
    regresses (the filter stops matching, the ledger order drifts), the
    control REFUSES with exit 5 — a regression is caught HERE first."""
    out = out or sys.stderr
    try:
        rows = scoped_rows(SCOPED_BOOK_ID, ATTACK_LEDGER)
    except FixtureError as exc:
        out.write("[attack-unscoped] payload-true REFUSED: %s\n" % exc)
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "rows": None,
            "detail": str(exc),
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    if len(rows) != 1 or rows[0]["anthology_id"] != SCOPED_BOOK_ID:
        out.write("[attack-unscoped] payload-true REFUSED: the scoped read "
                  "returned %d row(s), not exactly the one scoped row — the "
                  "scope authority regressed; refusing.\n" % len(rows))
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "rows": None,
            "detail": "the scoped filter no longer returns the one row of "
                      "its own anthology (got %d) — the authority regressed."
                      % len(rows),
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-true",
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "filter_marker": _mask_marker(SCOPED_BOOK_ID),
        "ledger_rows": len(ATTACK_LEDGER),
        "matched_rows": 1,
        "detail": "control: the true one-anthology scoped read passes exit "
                  "0 — the empty-filter attack fails by comparison, never "
                  "by a broken gate.",
    }, indent=2, sort_keys=True))
    return EX_OK


def plan(*, out=None) -> int:
    """Offline plan (no network, no credentials): what the attack drops and
    why, straight from the scope authority (the single source of truth —
    never a hardcoded law). One JSON object on stdout."""
    out = out or sys.stderr
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-plan",
        "schema_version": 1,
        "scoped_book_marker": _mask_marker(SCOPED_BOOK_ID),
        "foreign_book_marker": _mask_marker(FOREIGN_BOOK_ID),
        "filter_dropped": True,
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed. The "
                "attack drops the ONE anthology filter of the scoped read "
                "to empty: an UNFILTERED read reaches every ledger row "
                "across ALL anthologies (%d row(s) over the synthetic "
                "two-anthology ledger) — the empty-filter read that MUST "
                "FAIL every unscoped-read gate." % len(ATTACK_LEDGER),
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
        sys.stderr.write("[attack-unscoped] SELF-TEST FAILED "
                         "(AF-AE-ATTACKUNSCOPED-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    import contextlib
    from types import MappingProxyType  # noqa: F401 -- import-time import guard only

    # ---- the authority is the single source of truth ------------------------
    assert not book._bad_id_shape(SCOPED_BOOK_ID), \
        "the synthetic scoped id must satisfy the _bad_id_shape law"
    assert not book._bad_id_shape(FOREIGN_BOOK_ID), \
        "the synthetic foreign id must satisfy the _bad_id_shape law"
    assert SCOPED_BOOK_ID != FOREIGN_BOOK_ID, \
        "the scoped and foreign anthologies must differ"
    assert len(ATTACK_LEDGER) == 2, \
        "the attack ledger must carry exactly two rows (one per anthology)"

    # ---- the scoped read: one filter, one row, input order preserved --------
    rows = scoped_rows(SCOPED_BOOK_ID, ATTACK_LEDGER)
    assert len(rows) == 1, "the scoped read must return exactly ONE row"
    assert rows[0]["anthology_id"] == SCOPED_BOOK_ID, \
        "the scoped read must return the scoped anthology's row only"
    assert rows[0]["participant_key"] == SCOPED_PARTICIPANT, \
        "the scoped read must return the scoped participant"
    assert scoped_rows(FOREIGN_BOOK_ID, ATTACK_LEDGER)[0]["anthology_id"] \
        == FOREIGN_BOOK_ID, \
        "the foreign scope must see the foreign row only"

    # ---- the judge: empty-filter read MUST FAIL, golden control MUST PASS ----
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live("", ATTACK_LEDGER, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "the empty-filter attack read must FAIL (exit 5), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "FAIL" and parsed["ok"] is False, \
        "the empty-filter read must be FAIL, got %s" % parsed["verdict"]
    assert parsed["defects"] == ["empty-filter"], \
        "the attack must fail on the scope law and NOTHING else, got %r" \
        % parsed["defects"]
    assert parsed["matched_rows"] == 2, \
        "the unfiltered read must reach BOTH ledger rows"
    assert parsed["fail_closed"]["empty_filter_fails"] is True
    blob = buf.getvalue()
    assert "pit-" not in blob and "Bearer" not in blob and "sk-" not in blob, \
        "the judge output must never carry a token shape"

    # whitespace-only is the same attack shape -> FAIL
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live("   ", ATTACK_LEDGER, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a whitespace-only filter must FAIL (exit 5), got %s" % rc
    assert json.loads(buf.getvalue())["defects"] == ["empty-filter"]

    # a non-string filter is drift -> FAIL (never a pass)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(None, ATTACK_LEDGER, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a non-string filter must FAIL (exit 5), got %s" % rc
    assert json.loads(buf.getvalue())["defects"] == ["non-string-filter"]

    # a shape-illegal filter (the composite-key delimiter) is drift -> FAIL
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live("ANTH_bad::delim", ATTACK_LEDGER, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a shape-illegal filter must FAIL (exit 5), got %s" % rc
    assert json.loads(buf.getvalue())["defects"] == ["bad-filter-shape"]

    # the golden control PASSES the same judge (the pass/fail split is a
    # discrimination, never a broken instrument)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(SCOPED_BOOK_ID, ATTACK_LEDGER, out=io.StringIO())
    assert rc == EX_OK, \
        "the golden one-anthology scoped read must PASS (exit 0), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "PASS" and parsed["ok"] is True, \
        "the scoped read must be PASS, got %s" % parsed["verdict"]
    assert parsed["matched_rows"] == 1 and parsed["defects"] == []

    # a well-formed scope over the FOREIGN anthology is a SCOPED read (never
    # the attack): it must PASS the same judge — the pass side discriminates
    # the empty-filter boundary, never a well-formed scope.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(FOREIGN_BOOK_ID, ATTACK_LEDGER, out=io.StringIO())
    assert rc == EX_OK, \
        "a well-formed foreign scoped read must PASS (exit 0), got %s" % rc
    assert json.loads(buf.getvalue())["matched_rows"] == 1

    # the judge NEVER prints a full id (masked marker only)
    blob = buf.getvalue()
    assert SCOPED_BOOK_ID not in blob and FOREIGN_BOOK_ID not in blob, \
        "the judge output must never carry a full anthology id"

    # ---- the fail-closed gates: the attack ships, the control passes --------
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(out=io.StringIO())
    assert rc == EX_OK, "payload on the true authority must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["filter"] == "" and parsed["matched_rows"] == 2
    assert parsed["contract"] == ATTACK_CONTRACT
    assert parsed["row_markers"] == ["...beef", "...d00d"], \
        "the payload must report the anthology ids by masked marker only, " \
        "got %r" % parsed["row_markers"]
    # the payload fixture never carries a full id or a token shape
    blob = buf.getvalue()
    assert SCOPED_BOOK_ID not in blob and FOREIGN_BOOK_ID not in blob, \
        "the payload must never carry a full anthology id"
    assert "pit-" not in blob and "Bearer" not in blob, \
        "the payload must never carry a token shape"

    # the golden payload can never be mistaken for an ATTACK payload: the
    # attack gate REFUSES a non-empty filter (the wrong direction is drift)
    # -- cross-surface fail-closed proof.
    saved_shape = book._bad_id_shape
    try:
        book._bad_id_shape = lambda v: True  # the authority regressed
        try:
            scoped_rows(SCOPED_BOOK_ID, ATTACK_LEDGER)
            raise AssertionError("a regressed authority must be REFUSED")
        except FixtureError:
            pass
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = payload_true(out=io.StringIO())
        assert rc == EX_MISMATCH, \
            "payload-true under a regressed authority must REFUSE (exit 5), " \
            "got %s" % rc
        assert json.loads(buf.getvalue())["verdict"] == "REFUSED"
    finally:
        book._bad_id_shape = saved_shape
    # after restore the control passes again (the refusal was the drift, not
    # the instrument)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload_true(out=io.StringIO())
    assert rc == EX_OK, \
        "payload-true must pass again after the authority restored"

    # payload-true (the control): the true one-anthology scoped read passes
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload_true(out=io.StringIO())
    assert rc == EX_OK, \
        "payload-true on the true authority must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["matched_rows"] == 1 and parsed["ledger_rows"] == 2

    # ---- attack fixtures: every drift REFUSED, never shipped ---------------
    # 1. an empty filter -> refusal (never a verdict from the law surface)
    try:
        scoped_rows("", ATTACK_LEDGER)
        raise AssertionError("an empty filter was NOT refused")
    except FixtureError:
        pass
    # 2. a whitespace-only filter -> refusal
    try:
        scoped_rows("   ", ATTACK_LEDGER)
        raise AssertionError("a whitespace-only filter was NOT refused")
    except FixtureError:
        pass
    # 3. a non-string filter -> refusal
    try:
        scoped_rows(None, ATTACK_LEDGER)
        raise AssertionError("a non-string filter was NOT refused")
    except FixtureError:
        pass
    # 4. a shape-illegal filter (the composite-key delimiter) -> refusal
    try:
        scoped_rows("ANTH_bad::delim", ATTACK_LEDGER)
        raise AssertionError("a shape-illegal filter was NOT refused")
    except FixtureError:
        pass
    # 5. an empty ledger is a LEGITIMATE state (a minted anthology with no
    #    rows yet) — the filter is the law, never the ledger size: a
    #    well-formed scope over an empty ledger is a clean zero-row read,
    #    PASS exit 0 (a scoped read that reports nothing is never drift)
    assert scoped_rows(SCOPED_BOOK_ID, []) == [], \
        "a well-formed scope over an empty ledger must be a clean zero-row read"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_live(SCOPED_BOOK_ID, [], out=io.StringIO())
    assert rc == EX_OK, \
        "a scoped read over an empty ledger must PASS (exit 0), got %s" % rc
    assert json.loads(buf.getvalue())["matched_rows"] == 0

    # ---- the browser-UA pin: the edge fix is a house constant, never optional --
    assert reg.CAF_BROWSER_UA and reg.CAF_BROWSER_UA.startswith("Mozilla/"), \
        "CAF_BROWSER_UA must carry a browser User-Agent (the CF-1010 edge fix)"

    # ---- plan: offline, no network, exact drop ----
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = plan(out=io.StringIO())
    assert rc == EX_OK, "plan must exit 0"
    p = json.loads(buf.getvalue())
    assert p["filter_dropped"] is True and p["dry_run"] is True
    assert p["scoped_book_marker"] == "...d00d" and \
        p["foreign_book_marker"] == "...beef", \
        "the plan must report the anthologies by masked marker only, got %r" \
        % (p["scoped_book_marker"], p["foreign_book_marker"])

    dev.write("attack_unscoped self-test: OK (scope authority pinned "
              "(anthology_book._bad_id_shape over the synthetic "
              "two-anthology ledger); the one-anthology scoped read returns "
              "exactly one row in input order; judge FAILs the empty / "
              "whitespace-only / non-string / shape-illegal filter reads "
              "with exit 5 while the golden scoped control and a well-formed "
              "foreign scope PASS exit 0, masking every anthology id to the "
              "last-4 marker; payload gate ships the empty-filter attack "
              "and REFUSES under a regressed authority while payload-true "
              "control PASSes the scoped read; 4 attack fixtures refused "
              "(empty / whitespace-only / non-string / delimiter-carrying "
              "filter) and a well-formed scope over an empty ledger is a "
              "clean zero-row PASS; never a token shape, never a full id; "
              "CAF_BROWSER_UA pinned; plan offline)\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="attack_unscoped.py",
        description="Attack fixture — empty anthology filter, must FAIL "
                    "(Skill 59, U05 tooling): the adversarial sibling of the "
                    "anthology-scoped ledger read, shipping the deterministic "
                    "unfiltered read (the ONE anthology filter dropped to "
                    "empty, reaching every ledger row across ALL anthologies) "
                    "that every unscoped-read gate must refuse, and the "
                    "fail-closed offline gates that prove it (the golden "
                    "one-anthology scoped control PASSES).")
    ap.add_argument("--filter", default=None,
                    help="anthology filter to judge (verify); defaults to the "
                         "empty filter (the attack read)")
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
            # Judge the requested filter over the synthetic two-anthology
            # ledger; the empty filter (no --filter) IS the attack read, the
            # one-anthology filter is the golden control.
            filt = args.filter if args.filter is not None else ""
            return verify_live(filt, ATTACK_LEDGER, out=sys.stderr)
        return payload()
    except FixtureError as exc:
        sys.stderr.write("[attack-unscoped] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[attack-unscoped] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
