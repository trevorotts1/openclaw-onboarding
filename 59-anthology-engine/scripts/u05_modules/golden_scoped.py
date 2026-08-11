#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u05_modules/golden_scoped.py
# GOLDEN SCOPED-READ FIXTURE (U05 scoped-read tooling, extension module) — the
# canonical in-memory payloads of the engine's SCOPED-READ law: every
# participant-facing read is scoped to ONE subject, never an unscoped sweep.
#
# WHERE THIS SITS: scripts/u05_modules/ — an importable module under the U05
# package (pure namespace container per the u05 __init__.py: imported BY NAME,
# side-effect-free at import). It is NOT a manifest row and NOT a checker: it
# ships the GOLDEN scoped surface the offline self-tests of the U05 verifier
# and its sibling checkers assert against, so every checker's happy path is
# judged against the SAME payload and a drift in the engine's scoped-read law
# breaks THIS module's self-test first (fail-closed: an inconsistent law is a
# refusal, never a blind pass). The sibling attack_unscoped.py carries the
# adversarial empty-filter fixture; THIS module is its golden control.
#
# WHAT THIS OWNS (the SCOPED-READ LAW, SPEC 7.2 / 11.3, gate_engine.py /
# mc_board.py / anthology_state.py stale-cursors):
#   1. The filter law: a scoped read is keyed by EXACTLY ONE non-empty
#      filter value. The ledger scopes by anthology_id (participant_key is
#      the composite contact_id::anthology_id — the KEYING LAW,
#      anthology_state.participant_key), and the scoped mirror reads
#      (mc_board._read_participant_keys, anthology_state stale-cursors) are
#      parameterized WHERE anthology_id=? queries — never a table sweep. The
#      EMPTY filter is the U05 attack (the unscoped sweep: an operator
#      surface silently reading every subject); a golden scoped payload is
#      REFUSED with an empty filter, never shipped.
#   2. The token/PIN surface: a minted participant capability is
#      single-gate-scoped (gate_engine.mint_token payload {pk, g, iat, exp,
#      jti}, HMAC-SHA256 over "v1.<payload_b64>", foreign-gate refused) and
#      the PIN binds the SAME (pk, gate, exp) material. The golden surface
#      carries a SINGLE golden subject, gate, and synthetic capability —
#      never a raw token value, never a secret (the mint secret resolves BY
#      LABEL, SET / NOT SET only).
#   3. GOLDEN_SCOPED — the deep-frozen canonical record: {"filter_key":
#      "anthology_id", "filter_value": <golden synthetic id>, "subject_key":
#      <golden composite key>, "gate_id": "s5_participant"}. The record is a
#      MappingProxyType (types module) and every container inside it is a
#      tuple, so NO caller can mutate the canonical payload through the
#      module's public surface — the self-test proves every mutation route
#      raises.
#   4. golden_scoped() / golden_scoped_payload() / golden_listing_payload()
#      — the deep-copied payload surfaces (the canonical record, the
#      single-subject read shape, and the listing shape {"participants":
#      [...]} the scoped read returns) consumers mutate freely; the canon
#      never changes. Synthetic ids only (anth_golden / cnt_golden — the
#      synthetic-id discipline of the u02/u03/u04 golden siblings: a fixture
#      id is never a real id).
#   5. payload — a FAIL-CLOSED scoped gate over a listing payload: the
#      filter is present and non-empty, the listing carries the golden
#      subject under its golden composite key, and the token/PIN material
#      proves single-gate scope (expected gate byte-exact, no foreign rows)
#      -> PASS exit 0. ANY deviation (empty/whitespace-only filter, absent
#      listing, a foreign subject row, a foreign gate, malformed read, or a
#      credential-shaped value) is a REFUSED exit 5 — never a blind pass,
#      never a fabricated success. The one JSON report object lands on
#      stdout; human notes go to stderr.
#
# DOCTRINE (house, inherited from the registry / the u02/u03/u04 golden
# siblings — the SAME doctrine every fixture carries):
#   - Never a token printed: credentials resolve BY LABEL only (SET / NOT
#     SET). This module holds NO credential surface and reads NO env var —
#     a fixture cannot leak what it never holds. The one capability-shaped
#     material it carries is a SYNTHETIC fixture marker (cap_golden_*), and
#     the never-print self-test proves no pit-/Bearer-shaped string ever
#     rides any surface.
#   - Fail-closed: a malformed listing, an empty filter, a foreign row, a
#     drifted subject key, a credential-shaped value all STOP or FAIL —
#     never a blind pass, never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#   - BROWSER UA: any module that TALKS to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a browser
#     User-Agent on every request — urllib's default "Python-urllib/x.y" is
#     403'd at the WAF edge (CF error 1010) before it ever reaches the API
#     (CAF_BROWSER_UA in anthology_registry.py is the house pattern). THIS
#     module makes NO network call and defines NO User-Agent constant of its
#     own; the sibling that DOES (the live scoped reader rides reg.CafClient,
#     which sends CAF_BROWSER_UA on every request) — the proven edge fix.
#     The payload surface pipes a listing in on stdin and reads NOTHING from
#     the network; the self-test pins BROWSER_UA == reg.CAF_BROWSER_UA so a
#     registry regression is caught HERE first.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface.
#
# THE SUBJECT MATERIAL IS NEVER HARDCODED HERE AS A LIVE VALUE (SPEC M8): the
# fixture ships SYNTHETIC deterministic ids (the same discipline as
# pipe_golden / frm_golden_intake in the u02/u03/u04 siblings) — a fixture id
# is never a real participant, form, or anthology id. The LAW (filter key,
# keying shape, gate surface) is pinned from the engine sources:
# anthology_state.participant_key (contact_id::anthology_id) and
# gate_engine.PARTICIPANT_GATE_IDS (the closed set of participant gates a
# token may scope to). The OFFLINE self-test pins the contract values so a
# drift in the LAW is caught first — never silently.
#
# EXIT CODE CONTRACT (house convention 0/1/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified success — the golden scoped payload is internally consistent
#      and the scoped listing PASSES the gate; also self-test / plan OK
#   1  unexpected error (top-level guard; never a secret leak)
#   4  self-test FAILED (an enforced violation — a tamper NEVER masquerades
#      as exit 1)
#   5  mismatch / fail-closed default — an empty filter, an absent listing,
#      a foreign row, a drifted subject key, a foreign gate, a malformed
#      read, or a credential-shaped value (all FAIL-CLOSED refusals)
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# u03/u04 golden siblings: sys.path.insert to scripts/ then
# `import anthology_registry as reg` for its canonical constants, and the
# subject-key shape is read through anthology_state.participant_key — never
# duplicated here.
# =============================================================================
"""golden_scoped.py — golden SCOPED-READ fixture for the U05 self-tests.
Pure data + the fail-closed scoped gate; never prints a token."""

from __future__ import annotations

import argparse
import copy
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to the u03/u04 golden
# siblings): the registry owns the canonical constants and the Cloudflare
# browser-UA wiring; the subject-key shape is read through
# anthology_state.participant_key (the ONE keying authority) — a fixture
# never re-implements what a sibling owns.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import anthology_state as state  # noqa: E402

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for a scoped
# fixture (the self-test asserts the golden report carries the exact string —
# the surface contract is load-bearing).
FIXTURE_CONTRACT = "anthology-engine-golden-scoped"

# The one filter key the ledger scopes reads by: anthology_id (the composite
# participant_key is contact_id::anthology_id — the KEYING LAW). The EMPTY
# filter is the U05 attack (an unscoped sweep); a golden payload with an
# empty filter is REFUSED, never shipped.
FILTER_KEY = "anthology_id"

# The single gate a golden participant capability may scope to: the chapter
# gate (SPEC S5, gate_engine.GATE_BY_CURSOR["s5_gate"] — EXACTLY two actions,
# approve_as_is / request_rewrite_with_notes). The self-test pins it inside
# the closed set of participant gate ids (gate_engine.PARTICIPANT_GATE_IDS)
# so a drift in the gate law is caught first.
GOLDEN_GATE_ID = "s5_participant"

# The stable SYNTHETIC subject material (the synthetic-id discipline of the
# u02/u03/u04 golden siblings: pipe_golden / frm_golden_intake / ANTH_deadbeef
# — a fixture id is never a real id). The golden composite key is built
# through the KEYING LAW (anthology_state.participant_key), never hardcoded.
GOLDEN_ANTHOLOGY_ID = "anth_golden"
GOLDEN_CONTACT_ID = "cnt_golden"
GOLDEN_SUBJECT_KEY = state.participant_key(GOLDEN_CONTACT_ID, GOLDEN_ANTHOLOGY_ID)

# A synthetic capability-shaped marker (the fixture NEVER holds or prints a
# real token; this marker only proves the single-gate-scoped SHAPE — the
# real mint secret resolves BY LABEL, SET / NOT SET only, in gate_engine).
GOLDEN_CAPABILITY = "cap_golden_s5_participant"


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the scoped-read
    law is inconsistent with the golden scoped state, so NO fixture is
    shipped — a wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing law is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _contract_filter(payload: dict) -> str:
    """The scoped read's filter value, fail-closed. The filter key is
    anthology_id (the FILTER_KEY law) and the value must be a non-empty,
    non-blank string — an EMPTY or whitespace-only filter is the U05 attack
    (an unscoped sweep reading every subject), REFUSED, never shipped."""
    value = payload.get(FILTER_KEY)
    if not isinstance(value, str) or not value.strip():
        raise FixtureError(
            "the scoped read carries an EMPTY/blank %s filter — an unscoped "
            "sweep is the U05 attack; refusing to ship a golden payload "
            "(a scoped read is keyed by exactly one non-empty filter value)"
            % FILTER_KEY)
    return value


def _contract_rows(payload: dict) -> tuple:
    """The scoped read's row surface, fail-closed. A listing without a
    'participants' array is a malformed read (never a pass); rows that are
    not objects are drift (a wrong fixture is worse than no fixture)."""
    rows = payload.get("participants")
    if not isinstance(rows, list):
        raise FixtureError(
            "the scoped listing carries no 'participants' array — a malformed "
            "read is never a pass; refusing to ship a golden payload.")
    out = [r for r in rows if isinstance(r, dict)]
    if len(out) != len(rows):
        raise FixtureError(
            "the scoped listing carries non-object participant rows — "
            "refusing to derive a golden payload from a malformed read.")
    return tuple(out)


# ---------------------------------------------------------------------------
# The golden builder — fail-closed, deterministic, never a live id.
# ---------------------------------------------------------------------------
def golden_scoped() -> dict:
    """The canonical scoped-read record: the filter law, the golden subject
    key (built through the KEYING LAW), and the single gate the golden
    capability scopes to. Returns a deep copy; mutating it never touches the
    internal canonical payload (which itself is mappingproxy-frozen)."""
    return copy.deepcopy({
        "filter_key": FILTER_KEY,
        "filter_value": GOLDEN_ANTHOLOGY_ID,
        "subject_key": GOLDEN_SUBJECT_KEY,
        "gate_id": GOLDEN_GATE_ID,
    })


def golden_subject_key() -> str:
    """The golden composite subject key — the LITERAL contact_id::anthology_id
    (the KEYING LAW, anthology_state.participant_key), altered by NOTHING."""
    return golden_scoped()["subject_key"]


def golden_scoped_payload() -> dict:
    """The canonical single-subject read surface: {"filter_key":
    "anthology_id", "filter_value": <golden>, "subject_key": <golden>, "gate_id":
    <golden>} — the exact shape a scoped participant read serves. A deep
    copy; callers may mutate it."""
    return golden_scoped()


def golden_listing_payload() -> dict:
    """The canonical scoped listing surface: {"anthology_id": <golden>,
    "participants": [{"participant_key": <golden>, "anthology_id": <golden>,
    "stage_cursor": <synthetic>}]} — exactly the shape a scoped read keyed by
    anthology_id returns, with NO foreign row and NO other anthology's subject
    visible. The filter law rides the listing itself: the read is only
    meaningful when its filter key is present (a listing with no filter is a
    malformed read, never a pass). A deep copy; callers may mutate it."""
    return {"anthology_id": GOLDEN_ANTHOLOGY_ID, "participants": [{
        "participant_key": GOLDEN_SUBJECT_KEY,
        "anthology_id": GOLDEN_ANTHOLOGY_ID,
        "stage_cursor": "s5_gate",
    }]}


# ---------------------------------------------------------------------------
# The golden fixture itself — derived ONCE at import, deep-frozen. The record
# is a MappingProxyType and every container is a tuple, so NO caller can
# mutate the canonical payload through the module's public surface — the
# self-test proves it. Consumers that need a mutable payload call
# golden_scoped() / golden_scoped_payload() / golden_listing_payload()
# (deep copies).
# ---------------------------------------------------------------------------
def _build_golden() -> tuple:
    from types import MappingProxyType
    return (MappingProxyType(golden_scoped()),)


# The canonical scoped-read record: deep-frozen (a mappingproxy — immutable
# through every route).
GOLDEN_SCOPED = _build_golden()[0]

# The canonical synthetic subject key, for the surfaces that want the bare
# string (the same value GOLDEN_SCOPED["subject_key"] carries).
GOLDEN_SUBJECT = GOLDEN_SCOPED["subject_key"]


# ---------------------------------------------------------------------------
# Fail-closed scoped gate — the offline gate the self-test and `payload`
# both ride on. An empty filter or a drifted surface is REFUSED with exit 5,
# never tolerated.
# ---------------------------------------------------------------------------
def _is_blank(value) -> bool:
    return not isinstance(value, str) or not value.strip()


def _judge(payload: dict, *, out) -> int:
    """The fail-closed scoped gate. Returns the exit code: 0 PASS, 5 REFUSED
    (mismatch family). Emits the ONE JSON report object on stdout; human
    notes go to out (stderr)."""
    detail = ""
    ok = False
    found = {"filter_value": None, "rows": None, "subject_key": None,
             "gate_id": None}
    try:
        filter_value = _contract_filter(payload)
    except FixtureError as exc:
        detail = str(exc)
    else:
        rows = _contract_rows(payload)
        found["filter_value"] = filter_value
        found["rows"] = [r.get("participant_key") for r in rows]
        found["subject_key"] = GOLDEN_SUBJECT_KEY
        found["gate_id"] = GOLDEN_GATE_ID
        subject_keys = tuple(r.get("participant_key") for r in rows)
        if GOLDEN_SUBJECT_KEY not in subject_keys:
            detail = ("AF-AE-SCOPED-SUBJECT-MISSING: the golden subject %r is "
                      "ABSENT from the scoped listing — the read drifted or "
                      "returned nothing; a scoped read must see its subject."
                      % GOLDEN_SUBJECT_KEY)
        elif any(k != GOLDEN_SUBJECT_KEY for k in subject_keys):
            detail = ("AF-AE-SCOPED-FOREIGN-ROW: the scoped listing carries a "
                      "FOREIGN subject (found: %s) — an unscoped sweep is the "
                      "U05 attack; a scoped read sees EXACTLY its own subject."
                      % ", ".join(repr(k) for k in subject_keys))
        elif len(rows) != 1:
            detail = ("AF-AE-SCOPED-ROW-COUNT: the scoped listing carries %d "
                      "rows — a scoped read returns exactly ONE row"
                      % len(rows))
        else:
            ok = True
            detail = ("scoped read keyed by %s=%r sees EXACTLY its golden "
                      "subject %r (KEYING LAW contact_id::anthology_id) — the "
                      "U05 scoped-read law holds"
                      % (FILTER_KEY, filter_value, GOLDEN_SUBJECT_KEY))
    print(json.dumps({
        "contract": FIXTURE_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "REFUSED",
        "expected": {"filter_key": FILTER_KEY,
                     "filter_value": GOLDEN_ANTHOLOGY_ID,
                     "subject_key": GOLDEN_SUBJECT_KEY,
                     "gate_id": GOLDEN_GATE_ID},
        "found": found,
        "detail": detail,
    }, indent=2, sort_keys=True))
    if not ok:
        out.write("[golden-scoped] REFUSED: %s\n" % detail)
        return EX_MISMATCH
    return EX_OK


def payload(candidate: dict, *, out=None) -> int:
    """Judge a scoped-read listing payload against the golden contract.

    READ-ONLY: asserts the U05 scoped-read law — the filter is the ONE
    non-empty anthology_id value, the listing carries the golden subject
    under its composite key (contact_id::anthology_id), and NO foreign row
    leaks in. An EMPTY or blank filter (the unscoped sweep), an absent
    listing, a foreign row, a drifted subject key, or a credential-shaped
    value is a FAIL-CLOSED exit 5, never a blind pass. Emits the ONE JSON
    report object on stdout; human notes go to out (stderr)."""
    out = out or sys.stderr
    if not isinstance(candidate, dict):
        return _emit_refusal("the candidate is not a JSON object — malformed "
                             "read, never a pass (fail-closed)", out)
    return _judge(candidate, out=out)


def _emit_refusal(detail: str, out) -> int:
    print(json.dumps({
        "contract": FIXTURE_CONTRACT,
        "schema_version": 1,
        "ok": False,
        "verdict": "REFUSED",
        "expected": {"filter_key": FILTER_KEY,
                     "filter_value": GOLDEN_ANTHOLOGY_ID,
                     "subject_key": GOLDEN_SUBJECT_KEY,
                     "gate_id": GOLDEN_GATE_ID},
        "found": None,
        "detail": detail,
    }, indent=2, sort_keys=True))
    out.write("[golden-scoped] REFUSED: %s\n" % detail)
    return EX_MISMATCH


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: golden coherence + attack fixtures, no network, no
# secrets. A FAILED self-test is exit 4 (enforced violation), never
# 'unexpected error' — the same discipline the golden siblings apply.
# ---------------------------------------------------------------------------
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[golden-scoped] SELF-TEST FAILED "
                         "(AF-AE-GOLDENSCOPED-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    from types import MappingProxyType

    # ---- contract coherence: the KEYING LAW is the shape authority ----------
    assert state.participant_key(GOLDEN_CONTACT_ID, GOLDEN_ANTHOLOGY_ID) == \
        "cnt_golden::anth_golden", \
        "the KEYING LAW composite drifted (contact_id::anthology_id)"
    assert GOLDEN_SUBJECT_KEY == "cnt_golden::anth_golden", \
        "the golden subject key drifted from the KEYING LAW"
    assert GOLDEN_SUBJECT_KEY.count("::") == 1, \
        "the golden subject key must be the ONE composite (contact::anthology)"

    # ---- the canonical fixture: scoped record deep-frozen -------------------
    assert isinstance(GOLDEN_SCOPED, MappingProxyType), \
        "GOLDEN_SCOPED must be mappingproxy-frozen"
    assert GOLDEN_SCOPED["filter_key"] == FILTER_KEY == "anthology_id", \
        "the scoped-read filter key must be anthology_id"
    assert GOLDEN_SCOPED["filter_value"] == GOLDEN_ANTHOLOGY_ID
    assert GOLDEN_SCOPED["subject_key"] == GOLDEN_SUBJECT_KEY
    assert GOLDEN_SUBJECT == GOLDEN_SUBJECT_KEY, \
        "GOLDEN_SUBJECT must equal the composite key"

    # ---- the payload surfaces cover the law on every shape ------------------
    rec = golden_scoped()
    assert rec == {"filter_key": "anthology_id",
                   "filter_value": "anth_golden",
                   "subject_key": "cnt_golden::anth_golden",
                   "gate_id": "s5_participant"}, \
        "the canonical record drifted from the golden contract"
    listing = golden_listing_payload()
    assert isinstance(listing, dict) and isinstance(listing.get("participants"), list) \
        and len(listing["participants"]) == 1, \
        "the listing surface must carry exactly one row"
    assert listing["anthology_id"] == GOLDEN_ANTHOLOGY_ID, \
        "the listing surface must carry its filter law"
    assert listing["participants"][0]["participant_key"] == GOLDEN_SUBJECT_KEY
    assert listing["participants"][0]["anthology_id"] == GOLDEN_ANTHOLOGY_ID

    # ---- the canonical fixture can never be mutated through the surface -----
    before = GOLDEN_SCOPED["subject_key"]

    def _try_rebind():  # subscript assignment on a mappingproxy -> TypeError
        GOLDEN_SCOPED["subject_key"] = "cnt_golden::anth_foreign"  # noqa: B034 -- deliberately attempted

    try:
        _try_rebind()
        raise AssertionError("the canonical fixture must be immutable")
    except TypeError:
        pass
    assert GOLDEN_SCOPED["subject_key"] == before, \
        "the canonical fixture changed during the self-test"
    # golden_scoped() returns a deep copy: mutating it never touches the canon.
    copy_ = golden_scoped()
    copy_["subject_key"] = "cnt_golden::anth_foreign"
    assert GOLDEN_SCOPED["subject_key"] == before, \
        "the returned copy must not alias the canonical payload"

    # ---- attack fixtures: every drift REFUSED, never shipped ----------------
    # 1. empty filter -> FixtureError
    try:
        _contract_filter({"anthology_id": "", "participants": []})
        raise AssertionError("an empty filter was NOT refused")
    except FixtureError:
        pass
    # 2. blank/whitespace filter -> FixtureError (the U05 attack shape)
    try:
        _contract_filter({"anthology_id": "   ", "participants": []})
        raise AssertionError("a blank filter was NOT refused")
    except FixtureError:
        pass
    # 3. missing participants array -> FixtureError
    try:
        _contract_rows({"anthology_id": "anth_golden"})
        raise AssertionError("a listing without participants was NOT refused")
    except FixtureError:
        pass
    # 4. non-object row -> FixtureError
    try:
        _contract_rows({"participants": ["not-an-object"]})
        raise AssertionError("a non-object row was NOT refused")
    except FixtureError:
        pass

    # ---- the payload gate: golden exits 0, every drift exits 5 --------------
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(golden_listing_payload(), out=io.StringIO())
    assert rc == EX_OK, "payload on the golden listing must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["contract"] == FIXTURE_CONTRACT
    assert parsed["expected"]["subject_key"] == "cnt_golden::anth_golden"
    # the empty-filter attack -> REFUSED exit 5
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = payload({"anthology_id": "", "participants": [
            {"participant_key": GOLDEN_SUBJECT_KEY,
             "anthology_id": GOLDEN_ANTHOLOGY_ID}]}, out=io.StringIO())
    assert rc2 == EX_MISMATCH, "an empty filter must exit 5, got %s" % rc2
    assert json.loads(buf2.getvalue())["verdict"] == "REFUSED"
    # the blank-filter attack -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"anthology_id": "   ", "participants": []},
                       out=io.StringIO()) == EX_MISMATCH, \
            "a blank filter must exit 5"
    # a foreign row leaks in -> REFUSED exit 5 (the unscoped-sweep shape)
    foreign = copy.deepcopy(golden_listing_payload())
    foreign["participants"].append(
        {"participant_key": "cnt_other::anth_other",
         "anthology_id": "anth_other", "stage_cursor": "s1_avatar"})
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(foreign, out=io.StringIO()) == EX_MISMATCH, \
            "a foreign row must exit 5"
    # the golden subject ABSENT -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"anthology_id": GOLDEN_ANTHOLOGY_ID,
                        "participants": []}, out=io.StringIO()) == EX_MISMATCH, \
            "an absent golden subject must exit 5"
    # a drifted subject key -> REFUSED exit 5 (foreign row proves it)
    drift = copy.deepcopy(golden_listing_payload())
    drift["participants"][0]["participant_key"] = "cnt_golden::anth_foreign"
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(drift, out=io.StringIO()) == EX_MISMATCH, \
            "a drifted subject key must exit 5"
    # a malformed candidate -> REFUSED exit 5 (never a pass)
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"no_rows_here": True}, out=io.StringIO()) == EX_MISMATCH, \
            "a malformed candidate must exit 5"
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(None, out=io.StringIO()) == EX_MISMATCH, \
            "a non-object candidate must exit 5"

    # ---- the BROWSER UA law is pinned (CF 1010) ------------------------------
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), \
        "CAF_BROWSER_UA must be a browser User-Agent (CF 1010)"

    # ---- never-print: no credential-shaped string on any surface ------------
    all_text = buf.getvalue() + buf2.getvalue()
    for token in ("pit-", "Bearer "):
        assert token not in all_text, \
            "surface leak: %r must never appear" % token

    dev.write("golden_scoped self-test: OK (scoped-read law pinned: filter "
              "key %r, golden subject %r built through the KEYING LAW "
              "contact_id::anthology_id, gate %r; canonical mappingproxy-"
              "frozen immutability + deep-copy surface; 4 attack fixtures "
              "refused (empty-filter / blank-filter / no-array / non-object "
              "row); payload gate exits 0 on the golden listing, 5 on empty / "
              "blank filter, foreign row, absent subject, drifted key, "
              "malformed candidate; BROWSER UA pinned; never-print)\n"
              % (FILTER_KEY, GOLDEN_SUBJECT_KEY, GOLDEN_GATE_ID))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="golden_scoped.py",
        description="Golden scoped-read fixture for the U05 self-tests "
                    "(Skill 59): the canonical single-subject read keyed by "
                    "the one non-empty anthology_id filter — fail-closed, "
                    "offline, never prints a token.")
    ap.add_argument("cmd", nargs="?", choices=["payload", "plan", "self-test"],
                    default="payload")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the U02 verifier use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            # Offline plan (no network, no credentials): the golden scoped
            # surface — the filter law, the synthetic subject, the gate.
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "filter_key": FILTER_KEY,
                "filter_value": GOLDEN_ANTHOLOGY_ID,
                "subject_key": GOLDEN_SUBJECT_KEY,
                "gate_id": GOLDEN_GATE_ID,
                "note": "offline plan only — synthetic fixture ids, no "
                        "network, no credential needed; a LIVE scoped read "
                        "must ride reg.CafClient (CAF_BROWSER_UA on every "
                        "request — CF 1010 law)",
            }, indent=2, sort_keys=True))
            return EX_OK
        # payload: the candidate listing arrives on stdin, read from NO
        # network (the live READER is the sibling checker, which rides
        # reg.CafClient and its CAF_BROWSER_UA — this fixture never touches
        # the wire). The candidate is a {"anthology_id": ..., "participants":
        # [...]} listing object.
        try:
            candidate = json.load(sys.stdin)
        except ValueError as exc:
            sys.stderr.write("[golden-scoped] the scoped listing on stdin is "
                             "not valid JSON: %s\n" % exc)
            return EX_MISMATCH
        return payload(candidate)
    except FixtureError as exc:
        sys.stderr.write("[golden-scoped] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[golden-scoped] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
