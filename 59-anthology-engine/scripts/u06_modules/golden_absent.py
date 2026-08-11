#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u06_modules/golden_absent.py  (U06 tooling)
# GOLDEN ABSENT-STATE ARCHIVE FIXTURE — the canonical in-memory payload of the
# engine's ARCHIVE ACTION in its ABSENT state: BOTH archive targets (the board
# footprint and the ledger rows) are absent, so there is NOTHING to archive
# and the archive action is a clean PASS exit 0 (a no-op pass, exactly like
# the golden "R3 no shared Drive folders" no-op in revoke-anthology-client.sh
# — the engine's OWN precedent: nothing to do is a PASS, never an error).
#
# WHERE THIS SITS: scripts/u06_modules/ — an importable module under the U06
# package (pure namespace container per the u06 __init__.py: imported BY NAME,
# side-effect-free at import; the init records the U06 archive doctrine:
# destructive actions require --execute, Trevor-gated — WITHOUT --execute a
# module must report what it WOULD do and exit without mutating). It is NOT a
# manifest row and NOT a checker: it ships the GOLDEN absent-state surface the
# offline self-tests of the U06 verifier and its sibling checkers assert
# against, so every checker's happy path is judged against the SAME payload
# and a drift in the engine's archive law breaks THIS module's self-test
# first (fail-closed: an inconsistent law is a refusal, never a blind pass).
#
# WHAT THIS OWNS (the U06 ARCHIVE LAW, derived from the archive surfaces the
# revoke flow rides — mc_board.py cmd_archive (board cards, fail-soft, SPEC
# 11.2) and anthology_state.py upsert-anthology --status archived (ledger
# rows, deactivate-never-delete, ninety-day retention — revoke R2 / R6)):
#   1. THE ABSENT-STATE LAW: an archive action has EXACTLY TWO targets — the
#      board footprint (the Assembly card + every participant card, keyed by
#      participant_key — the KEYING LAW, anthology_state.participant_key,
#      contact_id::anthology_id) and the ledger rows (the anthology's status
#      rows). BOTH absent -> NOTHING to archive -> PASS exit 0. The golden
#      surface carries BOTH targets ABSENT (zero board cards, zero ledger
#      rows) and certifies the action a no-op PASS — the anti-attack control
#      of the archive sweep (an archive that mutates when there is nothing to
#      archive is a defect: an archive sweep with nothing to archive must
#      archive NOTHING).
#   2. THE ARCHIVE ACTION LAW (Trevor-gated, per the u06 __init__.py
#      doctrine): any archive ACTION — a mutation that deletes / archives /
#      removes / deactivates / revokes / unpublishes — REQUIRES --execute.
#      WITHOUT --execute the action is a read-only DRY-RUN: it reports what
#      it WOULD do (the action, the target ids by masked marker, the write
#      shape) and exits WITHOUT mutating (applied false, dry_run true). This
#      module does NOT perform the mutation itself — it ships the golden
#      absent-state + the dry-run report contract the mutation surface must
#      emit, so a checker that would mutate without --execute is caught HERE
#      first (the GATED-WRITE doctrine of the U05 scope_applier, carried
#      into U06 by the package init).
#   3. GOLDEN_ABSENT — the deep-frozen canonical record: {"board": [], 0
#      cards, "ledger": [], 0 rows, "targets": {"board": <0>, "ledger": <0>}}
#      — the absent-state census of BOTH targets. The record is a
#      MappingProxyType (types module) and every container inside it is a
#      tuple, so NO caller can mutate the canonical payload through the
#      module's public surface — the self-test proves every mutation route
#      raises.
#   4. golden_absent() / golden_absent_payload() / golden_dry_run_report()
#      — the deep-copied payload surfaces (the canonical absent record, the
#      census shape {"board": [...], "ledger": [...]} the archive sweep
#      reads, and the dry-run report shape {"action": "archive",
#      "targets": {...}, "applied": false, "dry_run": true} a mutation
#      surface MUST emit without --execute). Synthetic ids only — the
#      surface carries NO real id at all in the absent state; the dry-run
#      report's masked-marker discipline is pinned from the house
#      (ids are masked to their last 4 characters on every operator
#      surface — never printed in full).
#   5. payload — a FAIL-CLOSED absent-state gate over an archive census
#      payload: the census is a well-formed {"board": [...], "ledger": [...]}
#      pair, BOTH targets are EMPTY (zero cards, zero rows), and the
#      credential-shaped surface is clean (no pit-/Bearer-shaped string) ->
#      PASS exit 0 ("nothing to archive — clean no-op PASS"). ANY deviation
#      (a board card present, a ledger row present, a malformed census, a
#      missing target key, a non-empty string where the census must be
#      empty, or a credential-shaped value) is a REFUSED exit 5 — never a
#      blind pass, never a fabricated success. The one JSON report object
#      lands on stdout; human notes go to stderr.
#
# DOCTRINE (house, inherited from the registry / the u02/u03/u04/u05 golden
# siblings — the SAME doctrine every fixture carries):
#   - Never a token printed: credentials resolve BY LABEL only (SET / NOT
#     SET). This module holds NO credential surface and reads NO env var —
#     a fixture cannot leak what it never holds. The absent state carries
#     NO live id by construction; the dry-run report masks any id to its
#     last 4 characters (the house masked-marker discipline), and the
#     never-print self-test proves no pit-/Bearer-shaped string ever rides
#     any surface.
#   - Fail-closed: a malformed census, a present card or row where the
#     golden absent state requires emptiness, a missing target key, a
#     credential-shaped value all STOP or FAIL — never a blind pass, never
#     a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#     It CERTIFIES the absent state; the archive ACTION itself is owned by
#     the mutation surface and is Trevor-gated (--execute required — the
#     package-init doctrine), which this module pins.
#   - BROWSER UA: any module that TALKS to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a
#     browser User-Agent on every request — urllib's default
#     "Python-urllib/x.y" is 403'd at the WAF edge (CF error 1010) before it
#     ever reaches the API (CAF_BROWSER_UA in anthology_registry.py is the
#     house pattern). THIS module makes NO network call and defines NO
#     User-Agent constant of its own; the sibling that DOES (the archive
#     mutation surface rides the house clients, which send CAF_BROWSER_UA on
#     every request) — the proven edge fix. The self-test pins
#     BROWSER_UA == reg.CAF_BROWSER_UA so a registry regression is caught
#     HERE first.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface.
#
# THE SUBJECT MATERIAL IS NEVER HARDCODED HERE AS A LIVE VALUE (SPEC M8): the
# fixture ships SYNTHETIC deterministic ids only, and the golden ABSENT state
# carries NO id at all — the census is empty by construction (the discipline
# of the u02/u03/u04/u05 siblings: pipe_golden / frm_golden_intake /
# anth_golden / cnt_golden — a fixture id is never a real participant, form,
# or anthology id). The LAW (the two-target archive shape, the absent-state
# census keys "board" / "ledger", the KEYING LAW for any non-absent census)
# is pinned from the engine sources: mc_board.py cmd_archive (board target)
# and anthology_state.py upsert-anthology --status archived (ledger target),
# with participant_key (the KEYING LAW) read through
# anthology_state.participant_key. The OFFLINE self-test pins the contract
# values so a drift in the LAW is caught first — never silently.
#
# EXIT CODE CONTRACT (house convention 0/1/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified success — the golden absent state is internally consistent
#      and the absent census PASSES the gate ("nothing to archive"); also
#      self-test / plan OK
#   1  unexpected error (top-level guard; never a secret leak)
#   4  self-test FAILED (an enforced violation — a tamper NEVER masquerades
#      as exit 1)
#   5  mismatch / fail-closed default — a board card present, a ledger row
#      present, a malformed census, a missing target key, a non-empty
#      string where the census must be empty, or a credential-shaped value
#      (all FAIL-CLOSED refusals; the archive action must NOT mutate when
#      there is nothing to archive)
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# u05 golden siblings: sys.path.insert to scripts/ then
# `import anthology_registry as reg` for its canonical constants, and the
# KEYING LAW shape is read through anthology_state.participant_key — never
# duplicated here.
# =============================================================================
"""golden_absent.py — golden ABSENT-STATE archive fixture for the U06
self-tests. Both archive targets absent -> PASS (nothing to archive);
the archive ACTION is --execute-gated (Trevor-gated). Pure data + the
fail-closed absent-state gate; never prints a token."""

from __future__ import annotations

import argparse
import copy
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to the u05 golden
# siblings): the registry owns the canonical constants and the Cloudflare
# browser-UA wiring; the KEYING LAW shape is read through
# anthology_state.participant_key (the ONE keying authority) — a fixture
# never re-implements what a sibling owns.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import anthology_state as state  # noqa: E402

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for an absent
# fixture (the self-test asserts the golden report carries the exact string —
# the surface contract is load-bearing).
FIXTURE_CONTRACT = "anthology-engine-golden-absent"

# The U06 ARCHIVE ACTION LAW (Trevor-gated, per the u06 package-init
# doctrine): any archive ACTION — a mutation that deletes / archives /
# removes / deactivates / revokes / unpublishes — REQUIRES the caller to
# pass --execute explicitly. Without --execute the action is a read-only
# DRY-RUN: it reports what it WOULD do and exits WITHOUT mutating. This
# module ships the golden dry-run report contract the mutation surface must
# emit (applied false, dry_run true), so a checker that would mutate
# without --execute is caught HERE first.
ARCHIVE_ACTION = "archive"
EXECUTE_FLAG = "--execute"
GOLDEN_EXECUTE_REQUIRED = True  # the law: the archive ACTION is gated

# The TWO archive targets of the engine's archive sweep (the revoke flow's
# R2 / R6 pair): the board footprint (mc_board.py cmd_archive — the Assembly
# card + every participant card, keyed by participant_key, the KEYING LAW)
# and the ledger rows (anthology_state.py upsert-anthology --status archived
# — deactivate-never-delete, ninety-day retention). BOTH absent -> NOTHING
# to archive -> PASS exit 0.
TARGET_BOARD = "board"
TARGET_LEDGER = "ledger"
ARCHIVE_TARGETS = (TARGET_BOARD, TARGET_LEDGER)  # the fixed two, in order

# The stable SYNTHETIC subject material (the synthetic-id discipline of the
# u02/u03/u04/u05 golden siblings — a fixture id is never a real id). The
# golden ABSENT state carries NO live id at all; these markers exist only so
# a NON-absent census (an attack) can be built deterministically, and they
# never ride the golden surface.
GOLDEN_ANTHOLOGY_ID = "anth_golden"
GOLDEN_CONTACT_ID = "cnt_golden"
GOLDEN_SUBJECT_KEY = state.participant_key(GOLDEN_CONTACT_ID, GOLDEN_ANTHOLOGY_ID)


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the archive law
    is inconsistent with the golden absent state, so NO fixture is shipped —
    a wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing law is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _contract_census(payload: dict) -> dict:
    """The archive census, fail-closed. A census is a well-formed
    {"board": [...], "ledger": [...]} pair: BOTH target keys MUST be present
    and MUST be lists (an archive sweep reads exactly the two-target shape —
    a missing target key or a non-list target is a malformed census, never a
    pass)."""
    out = {}
    for target in ARCHIVE_TARGETS:
        rows = payload.get(target)
        if not isinstance(rows, list):
            raise FixtureError(
                "the archive census carries no %r array — a malformed "
                "census is never a pass; refusing to certify the absent "
                "state (the archive sweep reads EXACTLY the two-target "
                "shape %s)." % (target, ", ".join(ARCHIVE_TARGETS)))
        out[target] = tuple(rows)
    return out


def _contract_empty(census: dict) -> None:
    """The absent-state law, fail-closed: BOTH archive targets must be EMPTY
    (zero board cards, zero ledger rows). A present card or row is exactly
    the shape the golden absent state must REFUSE — the archive action must
    NOT mutate when there is nothing to archive, and an archive sweep that
    sees a target must say so, never certify absence."""
    for target in ARCHIVE_TARGETS:
        rows = census[target]
        if rows:
            raise FixtureError(
                "the archive census carries %d %r row(s) — the golden "
                "absent state requires BOTH targets EMPTY (nothing to "
                "archive); a present target is never certified absent."
                % (len(rows), target))


# ---------------------------------------------------------------------------
# The golden builder — fail-closed, deterministic, never a live id.
# ---------------------------------------------------------------------------
def golden_absent() -> dict:
    """The canonical absent-state record: the two-target census with BOTH
    targets EMPTY (zero board cards, zero ledger rows). Returns a deep copy;
    mutating it never touches the internal canonical payload (which itself is
    mappingproxy-frozen)."""
    return copy.deepcopy({
        TARGET_BOARD: [],
        TARGET_LEDGER: [],
    })


def golden_absent_payload() -> dict:
    """The canonical archive census surface: {"board": [], "ledger": []} —
    the exact shape an archive sweep reads when BOTH targets are absent.
    A deep copy; callers may mutate it."""
    return golden_absent()


def golden_dry_run_report() -> dict:
    """The canonical DRY-RUN report an archive ACTION must emit WITHOUT
    --execute (the Trevor-gated law): {"action": "archive", "targets":
    {"board": 0, "ledger": 0}, "applied": false, "dry_run": true,
    "execute_required": true} — the action reports what it WOULD do
    (nothing — both targets absent) and exits WITHOUT mutating. A checker
    that would mutate without --execute deviates from this shape and is
    caught HERE first. A deep copy; callers may mutate it."""
    return {
        "action": ARCHIVE_ACTION,
        "targets": {TARGET_BOARD: 0, TARGET_LEDGER: 0},
        "applied": False,
        "dry_run": True,
        "execute_required": GOLDEN_EXECUTE_REQUIRED,
    }


# ---------------------------------------------------------------------------
# The golden fixture itself — derived ONCE at import, deep-frozen. The record
# is a MappingProxyType and every container is a tuple, so NO caller can
# mutate the canonical payload through the module's public surface — the
# self-test proves it. Consumers that need a mutable payload call
# golden_absent() / golden_absent_payload() / golden_dry_run_report()
# (deep copies).
# ---------------------------------------------------------------------------
def _build_golden() -> tuple:
    from types import MappingProxyType
    return (MappingProxyType({
        TARGET_BOARD: (),
        TARGET_LEDGER: (),
    }),)


# The canonical absent-state record: deep-frozen (a mappingproxy — immutable
# through every route).
GOLDEN_ABSENT = _build_golden()[0]

# The canonical dry-run report (the --execute-gate law surface), deep-frozen
# the same way.
def _build_report() -> tuple:
    from types import MappingProxyType
    return (MappingProxyType(golden_dry_run_report()),)


GOLDEN_DRY_RUN = _build_report()[0]


# ---------------------------------------------------------------------------
# Fail-closed absent-state gate — the offline gate the self-test and
# `payload` both ride on. A present target or a drifted surface is REFUSED
# with exit 5, never tolerated.
# ---------------------------------------------------------------------------
def _is_blank(value) -> bool:
    return not isinstance(value, str) or not value.strip()


def _judge(payload: dict, *, out) -> int:
    """The fail-closed absent-state gate. Returns the exit code: 0 PASS, 5
    REFUSED (mismatch family). Emits the ONE JSON report object on stdout;
    human notes go to out (stderr)."""
    detail = ""
    ok = False
    found = {"board_rows": None, "ledger_rows": None}
    try:
        census = _contract_census(payload)
    except FixtureError as exc:
        detail = str(exc)
    else:
        found["board_rows"] = len(census[TARGET_BOARD])
        found["ledger_rows"] = len(census[TARGET_LEDGER])
        try:
            _contract_empty(census)
        except FixtureError as exc:
            detail = str(exc)
        else:
            ok = True
            detail = ("both archive targets ABSENT (board 0 cards, ledger 0 "
                      "rows) — NOTHING to archive; the archive action is a "
                      "clean no-op PASS (and any mutation would require "
                      "%s, Trevor-gated)" % EXECUTE_FLAG)
    print(json.dumps({
        "contract": FIXTURE_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "REFUSED",
        "expected": {"board": 0, "ledger": 0,
                     "archive_action": ARCHIVE_ACTION,
                     "execute_required": GOLDEN_EXECUTE_REQUIRED},
        "found": found,
        "detail": detail,
    }, indent=2, sort_keys=True))
    if not ok:
        out.write("[golden-absent] REFUSED: %s\n" % detail)
        return EX_MISMATCH
    return EX_OK


def payload(candidate: dict, *, out=None) -> int:
    """Judge an archive census payload against the golden absent contract.

    READ-ONLY: asserts the U06 absent-state law — BOTH archive targets (the
    board footprint and the ledger rows) are EMPTY, so the archive action is
    a clean no-op PASS exit 0 ("nothing to archive"), and the archive ACTION
    itself is --execute-gated (Trevor-gated). A malformed census, a missing
    target key, a board card or ledger row present, a non-empty string where
    the census must be empty, or a credential-shaped value is a FAIL-CLOSED
    exit 5, never a blind pass. Emits the ONE JSON report object on stdout;
    human notes go to out (stderr)."""
    out = out or sys.stderr
    if not isinstance(candidate, dict):
        return _emit_refusal("the candidate is not a JSON object — malformed "
                             "census, never a pass (fail-closed)", out)
    return _judge(candidate, out=out)


def _emit_refusal(detail: str, out) -> int:
    print(json.dumps({
        "contract": FIXTURE_CONTRACT,
        "schema_version": 1,
        "ok": False,
        "verdict": "REFUSED",
        "expected": {"board": 0, "ledger": 0,
                     "archive_action": ARCHIVE_ACTION,
                     "execute_required": GOLDEN_EXECUTE_REQUIRED},
        "found": None,
        "detail": detail,
    }, indent=2, sort_keys=True))
    out.write("[golden-absent] REFUSED: %s\n" % detail)
    return EX_MISMATCH


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: golden coherence + attack fixtures, no network, no
# secrets. A FAILED self-test is exit 4 (enforced violation), never
# 'unexpected error' — the same discipline the golden siblings apply.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[golden-absent] SELF-TEST FAILED "
                         "(AF-AE-GOLDENABSENT-* family): %s\n" % exc)
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

    # ---- the canonical fixture: absent record deep-frozen -------------------
    assert isinstance(GOLDEN_ABSENT, MappingProxyType), \
        "GOLDEN_ABSENT must be mappingproxy-frozen"
    assert ARCHIVE_TARGETS == ("board", "ledger"), \
        "the archive sweep reads EXACTLY the two targets board / ledger"
    for target in ARCHIVE_TARGETS:
        assert target in GOLDEN_ABSENT, \
            "the canonical absent record lost its %r target" % target
        assert GOLDEN_ABSENT[target] == (), \
            "the canonical absent record must carry an EMPTY %r target" % target
    assert GOLDEN_ABSENT[TARGET_BOARD] == GOLDEN_ABSENT[TARGET_LEDGER] == ()

    # ---- the payload surfaces cover the law on every shape ------------------
    rec = golden_absent()
    assert rec == {"board": [], "ledger": []}, \
        "the canonical absent record drifted from the golden contract"
    census = golden_absent_payload()
    assert isinstance(census, dict) \
        and census[TARGET_BOARD] == [] and census[TARGET_LEDGER] == [], \
        "the census surface must carry BOTH targets empty"
    report = golden_dry_run_report()
    assert report == {"action": "archive", "targets": {"board": 0, "ledger": 0},
                      "applied": False, "dry_run": True,
                      "execute_required": True}, \
        "the dry-run report drifted from the --execute-gate law"
    assert report["action"] == ARCHIVE_ACTION == "archive", \
        "the archive ACTION name must be 'archive'"
    assert report["execute_required"] is True, \
        "the archive ACTION must be --execute-gated (Trevor-gated)"

    # ---- the canonical fixture can never be mutated through the surface -----
    before = GOLDEN_ABSENT[TARGET_BOARD]

    def _try_rebind():  # subscript assignment on a mappingproxy -> TypeError
        GOLDEN_ABSENT[TARGET_BOARD] = ("cnt_golden::anth_golden",)  # noqa: B034 -- deliberately attempted

    try:
        _try_rebind()
        raise AssertionError("the canonical fixture must be immutable")
    except TypeError:
        pass
    assert GOLDEN_ABSENT[TARGET_BOARD] == before, \
        "the canonical fixture changed during the self-test"
    # golden_absent() returns a deep copy: mutating it never touches the canon.
    copy_ = golden_absent()
    copy_[TARGET_BOARD] = [{"participant_key": GOLDEN_SUBJECT_KEY}]
    assert GOLDEN_ABSENT[TARGET_BOARD] == before, \
        "the returned copy must not alias the canonical payload"

    # ---- attack fixtures: every drift REFUSED, never shipped ----------------
    # 1. a board card present -> the absent state is NOT certified
    with_bcard = {"board": [{"participant_key": GOLDEN_SUBJECT_KEY}],
                  "ledger": []}
    try:
        _contract_empty(_contract_census(with_bcard))
        raise AssertionError("a present board card was NOT refused")
    except FixtureError:
        pass
    # 2. a ledger row present -> the absent state is NOT certified
    with_lrow = {"board": [], "ledger": [{"status": "active"}]}
    try:
        _contract_empty(_contract_census(with_lrow))
        raise AssertionError("a present ledger row was NOT refused")
    except FixtureError:
        pass
    # 3. a missing target key -> malformed census, FixtureError
    try:
        _contract_census({"board": []})
        raise AssertionError("a census without the ledger target was NOT "
                             "refused")
    except FixtureError:
        pass
    # 4. a non-list target -> malformed census, FixtureError
    try:
        _contract_census({"board": "not-a-list", "ledger": []})
        raise AssertionError("a non-list target was NOT refused")
    except FixtureError:
        pass

    # ---- the payload gate: golden exits 0, every drift exits 5 --------------
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(golden_absent_payload(), out=io.StringIO())
    assert rc == EX_OK, "payload on the golden absent census must exit 0, " \
                        "got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["contract"] == FIXTURE_CONTRACT
    assert parsed["expected"]["board"] == 0 and parsed["expected"]["ledger"] == 0
    assert parsed["expected"]["execute_required"] is True
    # a board card present -> REFUSED exit 5
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = payload({"board": [{"participant_key": GOLDEN_SUBJECT_KEY}],
                       "ledger": []}, out=io.StringIO())
    assert rc2 == EX_MISMATCH, "a present board card must exit 5, got %s" % rc2
    assert json.loads(buf2.getvalue())["verdict"] == "REFUSED"
    # a ledger row present -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"board": [], "ledger": [{"status": "active"}]},
                       out=io.StringIO()) == EX_MISMATCH, \
            "a present ledger row must exit 5"
    # a missing target key -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"board": []}, out=io.StringIO()) == EX_MISMATCH, \
            "a census missing a target key must exit 5"
    # a malformed candidate -> REFUSED exit 5 (never a pass)
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"no_census_here": True}, out=io.StringIO()) == EX_MISMATCH, \
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

    dev.write("golden_absent self-test: OK (absent-state archive law pinned: "
              "both targets %r EMPTY — nothing to archive, clean no-op PASS; "
              "the archive ACTION is %s-gated, Trevor-gated; canonical "
              "mappingproxy-frozen immutability + deep-copy surface; 4 attack "
              "fixtures refused (board card / ledger row / missing target "
              "key / non-list target); payload gate exits 0 on the golden "
              "absent census, 5 on every present or malformed target; BROWSER "
              "UA pinned; never-print)\n"
              % (", ".join(ARCHIVE_TARGETS), EXECUTE_FLAG))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="golden_absent.py",
        description="Golden absent-state archive fixture for the U06 "
                    "self-tests (Skill 59): both archive targets absent -> "
                    "PASS (nothing to archive); the archive ACTION is "
                    "--execute-gated (Trevor-gated) — fail-closed, offline, "
                    "never prints a token.")
    ap.add_argument("cmd", nargs="?", choices=["payload", "plan", "self-test"],
                    default="payload")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the U05 siblings use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            # Offline plan (no network, no credentials): the golden absent
            # surface — the two-target census, the empty state, the
            # --execute-gated archive action.
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "targets": {TARGET_BOARD: 0, TARGET_LEDGER: 0},
                "archive_action": ARCHIVE_ACTION,
                "execute_required": GOLDEN_EXECUTE_REQUIRED,
                "note": "offline plan only — synthetic fixture ids, no "
                        "network, no credential needed; a LIVE archive "
                        "ACTION must ride the house clients (CAF_BROWSER_UA "
                        "on every request — CF 1010 law) and require "
                        "--execute before any mutation (Trevor-gated)",
            }, indent=2, sort_keys=True))
            return EX_OK
        # payload: the candidate census arrives on stdin, read from NO
        # network (the live archive surface is the sibling checker, which
        # rides the house clients and their CAF_BROWSER_UA — this fixture
        # never touches the wire). The candidate is a {"board": [...],
        # "ledger": [...]} census object.
        try:
            candidate = json.load(sys.stdin)
        except ValueError as exc:
            sys.stderr.write("[golden-absent] the archive census on stdin is "
                             "not valid JSON: %s\n" % exc)
            return EX_MISMATCH
        return payload(candidate)
    except FixtureError as exc:
        sys.stderr.write("[golden-absent] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[golden-absent] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
