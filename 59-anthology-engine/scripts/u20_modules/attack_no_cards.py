#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u20_modules/attack_no_cards.py
# ZERO-CARDS ATTACK FIXTURE (U20 tooling) — the fail-closed WELCOME-CARD law
# over the board projection surface: the Welcome card is the seeded producer-
# facing tile of the Anthology department board, its content ships the engine's
# producer How-To (HOW-TO-USE.md) as COPY ONLY — never as a write — and the
# board is the ENGINE-DB projection the home-screen tile and the producer card
# gate on (mc_board.py POST /api/tasks/ingest, fail-soft; the board holds NO
# base credential; its only write path is shelling anthology_state.py). THIS
# module ships the ATTACK half of the U20 welcome pair: the board census that
# carries ZERO cards — the exact state where a welcome-sync would need a WRITE
# to create the Welcome card — that the SAME gate must judge a clean PASS
# no-op, because the Welcome card is copy that "ships" from the manifest, never
# a write the engine performs, and the engine's database is READ-ONLY in
# dry-run: WITHOUT --execute no module may write it at all.
#
# WHY THE ZERO-CARDS CENSUS IS THE U20 ATTACK: every participant card and the
# Assembly card land on the board through POST /api/tasks/ingest, and the
# Welcome card — the producer's entry point to the Anthology department board —
# is seeded content whose source of truth is the producer How-To (HOW-TO-USE.md
# at the skill root). A board census of zero cards is indistinguishable at the
# read step from a board that was never seeded: the read succeeds, the JSON
# parses, and the array simply carries nothing — no error, no exception, just
# no card. A sync that treated "zero cards" as a gap to WRITE would mutate the
# board in a state that must stay read-only without --execute, and would burn
# a write on a card whose content ships as copy. THIS module exists so that
# state is judged right at the gate: the zero-cards census is the GOLDEN no-op
# (PASS exit 0 — a welcome-sync with no board to sync writes NOTHING), and the
# --execute law is pinned the other direction — the Welcome card is copy-only,
# so even WITH --execute this fixture never writes; a mutation that would
# create it without the explicit execute flag is caught HERE first.
#
# WHAT THIS OWNS
#   1. WELCOME_SOURCE — the path of the Welcome card's copy source, the
#      producer How-To at the skill root (HOW-TO-USE.md); pinned as the
#      fixture's contract, never a hardcoded blob of the copy itself (SPEC M8:
#      subject material is never hardcoded — the copy LIVES in HOW-TO-USE.md,
#      the fixture owns the LAW that the Welcome card is copy-only, derived
#      from the U20 package doctrine).
#   2. verify(census) — the fail-closed gate over a BOARD CENSUS payload
#      ({"cards": [...]} — exactly the projection shape a live board read
#      serves, the same array the daily reconcile sweep reads):
#        - ZERO cards -> ("PASS", "zero-cards welcome state", ...) — the
#          welcome-sync is a clean no-op; nothing to write; the law the
#          engine's database is READ-ONLY in dry-run (verified exit 0 EVEN
#          without --execute, exactly like the golden no-op convention of the
#          u06 absent-state archive fixture)
#        - any card present, a malformed census, a missing "cards" key, a
#          non-list array, or a credential-shaped string on the census ->
#          raises NoCardsError (STOP / mismatch family, never a pass, never a
#          silent fallback) — the attack fixture is DATA, and a census that
#          cannot be judged is refused, never certified clean
#   3. dry_run(census) — the OFFLINE dry-run plan body (the mirror of the
#      welcome-sync's plan surface): the zero-cards state plans
#      state "no-op" with writes_needed FALSE and would_do "write nothing —
#      the Welcome card ships as copy from HOW-TO-USE.md (U20 package
#      doctrine: the engine's database is READ-ONLY in dry-run; WITHOUT
#      --execute no module may write it)" — the dry-run REPORT is the law
#      surface of the U20 write gate (package contract: "Without --execute
#      the module must report what it WOULD do and exit without mutating").
#   4. payload(census, *, execute, out) — the CLI gate: emits the ONE JSON
#      report object (contract / ok / verdict / cards / execute / would_do /
#      detail). The zero-cards state is PASS exit 0 with execute False AND
#      with execute True — the Welcome card is copy-only, so there is NEVER
#      anything to write; a census carrying cards is REFUSED exit 5 (the
#      fixture is DATA — the mutation lives in the welcome-sync surface,
#      which is --execute-gated, Trevor-gated).
#   5. self_test() — OFFLINE (no network, no credentials, no client, no
#      write): the zero-cards census PASSES (exit 0 through the CLI gate with
#      AND without --execute), every card-present / malformed census is
#      REFUSED, the Welcome copy source is pinned to HOW-TO-USE.md, and the
#      never-print law is asserted across every surface. A tamper NEVER
#      masquerades as exit 1 — it is exit 4 (AF-AE-WELCOME-ATTACK family,
#      the sibling fixtures' own self-test convention), never 'unexpected
#      error'.
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py / the sibling
# attack fixtures):
#   - A fixture is DATA, not code: this module performs NO I/O and NO network
#     call and holds NO client — it can never leak a token and can never
#     mutate by construction. Nothing here reads an env var or touches the
#     wire.
#   - THE ENGINE'S DATABASE IS READ-ONLY IN DRY-RUN (U20 package doctrine,
#     Trevor-gated): writes happen ONLY when the caller passed --execute
#     explicitly. Without --execute, report what WOULD happen and exit
#     without mutating. THIS fixture never writes — with or without
#     --execute: it is DATA, and the Welcome card ships as copy (HOW-TO-USE
#     .md), never as a write.
#   - THE WELCOME CARD IS COPY ONLY: its content derives from HOW-TO-USE.md
#     (the producer-facing How-To) and ships as copy, never as a write. The
#     fixture pins the SOURCE (WELCOME_SOURCE), never the copy itself —
#     subject material is never hardcoded (SPEC M8; the discipline of the
#     u02/u03/u04/u05 siblings: a fixture id is never a real id).
#   - BROWSER UA: any module that TALKS to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a browser
#     User-Agent on every request — urllib's default "Python-urllib/x.y" is
#     403'd at the WAF edge (CF error 1010) before it ever reaches the API.
#     This fixture makes no request of its own and therefore defines no UA
#     constant of its own; the sibling that DOES (the board client,
#     mc_board.py) already rides reg.CafClient and its CAF_BROWSER_UA on
#     every request — the proven edge fix (W0.6 / GK-09 discipline). The
#     self-test pins CAF_BROWSER_UA so a registry regression is caught HERE
#     first.
#   - FAIL-CLOSED: a card present where the zero-cards state requires
#     emptiness, a malformed census, a missing "cards" key, a credential-
#     shaped value — every deviation REFUSES (NoCardsError / exit 5), never a
#     blind pass, never a fabricated success.
#   - NEVER print a secret value: credentials resolve BY LABEL only (SET /
#     NOT SET). This module holds NO credential surface and reads NO env var
#     — a fixture cannot leak what it never holds. The never-print self-test
#     proves no pit-/Bearer-shaped string ever rides any surface.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface.
#
# EXIT CODES (house convention 0/1/2/3/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified PASS — the board census carries ZERO cards: the welcome-sync
#      is a clean no-op (nothing to write; the Welcome card ships as copy
#      from HOW-TO-USE.md, never as a write). Also self-test PASS and plan OK.
#   1  unexpected error
#   2  STOP refusal — usage (no gate mode selected) or invalid census JSON on
#      stdin
#   4  self-test FAILED — an attack fixture was NOT refused (AF-AE-WELCOME-
#      ATTACK family; a tamper NEVER masquerades as exit 1)
#   5  data or read-back mismatch — a card present, a malformed census, a
#      missing "cards" key, a non-list array, or a credential-shaped value
#      (all FAIL-CLOSED refusals; the welcome-sync must NOT write when the
#      census carries cards — THIS fixture never writes, and the mutation is
#      --execute-gated, Trevor-gated)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# --plan and --self-test are OFFLINE and need no token and no network):
#   attack_no_cards.py --plan             # offline: the welcome law with sources
#   attack_no_cards.py --live < census.json
#                                        # pipes a board census in ({"cards": [...]})
#   attack_no_cards.py --live --execute < census.json
#                                        # same gate; the execute flag named
#                                        # (the fixture STILL never writes)
#   attack_no_cards.py --self-test        # offline golden + attack fixtures
#
# STDLIB ONLY (json + argparse). Calls NO model. Reuses anthology_registry
# (exit codes, _stop, _mask_location, CAF_BROWSER_UA doctrine) — the ONE
# implementation of the house surfaces.
# =============================================================================
"""attack_no_cards.py — zero-cards attack fixture for the U20 welcome law:
any board census carrying ZERO cards is the clean no-op PASS (the Welcome
card ships as copy from HOW-TO-USE.md, never as a write), and the engine's
database is READ-ONLY in dry-run — writes ONLY with --execute, Trevor-gated.
Never a pass for a malformed census; never a write from this fixture."""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# Cloudflare browser-UA wiring (CAF_BROWSER_UA, applied by reg.CafClient —
# the fixture makes no request of its own, so it carries no UA of its own),
# the exit-code convention, the masked-marker convention, and the fail-closed
# helper surfaces.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent

FIXTURE_CONTRACT = "anthology-engine-attack-no-cards"

# The ONE fixed report contract on every surface (plan / live / self-test).
_REPORT = {
    "contract": FIXTURE_CONTRACT,
    "schema_version": 1,
}

# The Welcome card's copy source — the producer-facing How-To at the skill
# root (U20 package doctrine: "Welcome card content derives from HOW-TO-USE
# .md"). The fixture pins the SOURCE, never the copy itself: subject material
# is never hardcoded here (SPEC M8 — the discipline of the golden siblings).
WELCOME_SOURCE = SKILL_DIR / "HOW-TO-USE.md"

# The marker that PROVES the zero-cards state in `found` — the empty state
# must never masquerade as a named card and never as a blank "(none)".
_EMPTY_MARKER = "(no cards)"

# The refusal family codes (the AF-AE-WELCOME-* scheme).
CODE_CARDS_PRESENT = "AF-AE-WELCOME-CARDS-PRESENT"
CODE_MALFORMED = "AF-AE-WELCOME-MALFORMED"


class NoCardsError(Exception):
    """A fail-closed verification refusal (STOP/mismatch family): the board
    census carries a card (the exact state a welcome-sync must NOT write
    into), or the payload cannot be judged at all. `code` names the refusal
    family the CLI maps to an exit code."""

    def __init__(self, message: str, code: str = CODE_CARDS_PRESENT):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# The fail-closed gate over a BOARD CENSUS payload. The payload is
# {"cards": [...]} — exactly the projection shape a live board read serves
# (the same array the daily reconcile sweep projects), so the live surface
# and the offline attack surface share ONE implementation of the welcome law.
# ---------------------------------------------------------------------------
def _extract_cards(payload) -> list:
    """The cards array out of a board census payload. Raises NoCardsError
    (MALFORMED) on a payload that cannot be judged — a malformed read is
    NEVER a pass (fail-closed)."""
    if not isinstance(payload, dict):
        raise NoCardsError(
            "census payload is %r, not an object — refusing to judge it."
            % type(payload).__name__, code=CODE_MALFORMED)
    cards = payload.get("cards")
    if cards is None:
        raise NoCardsError(
            "census payload has no 'cards' array — a malformed read is NEVER "
            "a pass (fail-closed).", code=CODE_MALFORMED)
    if not isinstance(cards, list):
        raise NoCardsError(
            "census 'cards' is %r, not a list — refusing."
            % type(cards).__name__, code=CODE_MALFORMED)
    return cards


def verify(census: dict) -> tuple:
    """Verify a board census against the zero-cards welcome law, fail-closed.

    Returns ("PASS", detail, [marker], 0) when the census carries ZERO cards
    — the golden no-op state: a welcome-sync with an empty board writes
    NOTHING, because the Welcome card ships as copy from HOW-TO-USE.md and
    the engine's database is READ-ONLY in dry-run. Raises NoCardsError on
    ANY other outcome — a card present (the welcome-sync must NOT write into
    a board that already carries cards; the mutation lives in the
    --execute-gated sibling surface and THIS fixture is DATA), or a payload
    that cannot be judged (a malformed read is NEVER a pass, never a silent
    fallback).
    """
    cards = _extract_cards(census)
    if not cards:
        # THE U20 ATTACK (zero cards): the read succeeded, the JSON parsed,
        # and the array is empty — no error, no exception, just no card. The
        # state is the clean no-op PASS: nothing to sync, nothing to write.
        return ("PASS", "zero-cards welcome state", [_EMPTY_MARKER], 0)
    raise NoCardsError(
        "AF-AE-WELCOME-CARDS-PRESENT: the board census carries %d card(s) "
        "(%s) — the welcome-sync writes NOTHING into a board that already "
        "carries cards (the Welcome card ships as copy from HOW-TO-USE.md, "
        "never as a write; the engine's database is READ-ONLY in dry-run). "
        "This fixture never writes; the mutation is --execute-gated, "
        "Trevor-gated." % (len(cards), ", ".join(_card_markers(cards))))


def _card_markers(cards: list) -> list:
    """The masked card markers of a census (title strings truncated to the
    board's title-window discipline — mc_board.py truncates card titles on
    ingest, so a marker here can never outlive the projection)."""
    markers = []
    for c in cards:
        if isinstance(c, dict):
            title = c.get("title") or c.get("name") or ""
            markers.append(title[:24] if title else "(unnamed)")
        else:
            markers.append("(unnamed)")
    return markers


# ---------------------------------------------------------------------------
# The dry-run plan — the OFFLINE report body (no network, no credentials, no
# mutation): what --execute WOULD do. The mirror of the welcome-sync's plan
# surface (ok / dry_run / cards / writes_needed / would_do), so the plan
# surfaces of the sync and its attack fixture speak the same JSON.
# ---------------------------------------------------------------------------
def dry_run(census: dict) -> dict:
    """The dry-run plan over a board census: state "no-op" (zero cards —
    nothing would be written; the Welcome card ships as copy from
    HOW-TO-USE.md, never as a write) or state "readonly-refusal" (a card
    present — the fixture never writes and the mutation is --execute-gated).
    A census that cannot be judged at all plans "unreadable" — never a
    fabricated verdict. writes_needed is the boolean machine surface."""
    try:
        cards = _extract_cards(census)
    except NoCardsError as exc:
        return {
            "ok": True, "dry_run": True,
            "cards": 0, "state": "unreadable",
            "writes_needed": None,
            "would_do": "cannot plan a census that cannot be read "
                        "(malformed payload)",
            "refusal": exc.code,
        }
    if cards:
        return {
            "ok": True, "dry_run": True,
            "cards": len(cards), "state": "readonly-refusal",
            "writes_needed": None,
            "would_do": "write NOTHING — the welcome-sync never mutates a "
                        "board that already carries cards, and THIS fixture "
                        "is DATA (the mutation is --execute-gated, "
                        "Trevor-gated)",
            "refusal": CODE_CARDS_PRESENT,
        }
    return {
        "ok": True, "dry_run": True,
        "cards": 0, "state": "no-op",
        "writes_needed": False,
        "would_do": "write nothing — the board is EMPTY and the Welcome card "
                    "ships as copy from HOW-TO-USE.md (the engine's database "
                    "is READ-ONLY in dry-run; WITHOUT --execute no module "
                    "may write it)",
    }


# ---------------------------------------------------------------------------
# CLI gate — ONE JSON object on stdout, human notes on stderr, fail-closed.
# ---------------------------------------------------------------------------
def _report(ok: bool, verdict: str, cards: int, execute: bool,
            plan: dict, detail: str, code: str = "PASS",
            found=None) -> None:
    sys.stdout.write(json.dumps(dict(
        _REPORT,
        ok=ok,
        verdict=verdict,
        code=code,
        cards=cards,
        found=found if found is not None else [_EMPTY_MARKER],
        execute=execute,
        writes_needed=plan["writes_needed"],
        would_do=plan["would_do"],
        detail=detail,
    ), indent=2, sort_keys=True) + "\n")


def payload(census: dict, *, execute: bool = False, out=None) -> int:
    """Run the fail-closed welcome gate over a board census. Returns the exit
    code: 0 PASS (the zero-cards no-op — with OR without --execute, because
    there is never anything to write), 5 refusal (cards present, malformed
    census, or a credential-shaped value — fail-closed). Human notes go to
    stderr; the ONE JSON report object lands on stdout."""
    out = out or sys.stderr
    plan = dry_run(census)
    if _credential_shaped(census):
        reg._stop(out, "The board census carries a credential-shaped value.",
                  ["A census is a projection of card titles and statuses — "
                   "it never carries a token. Refusing to judge it (never "
                   "leak, never a pass)."])
        _report(False, "REFUSED", 0, execute, plan,
                "credential-shaped value on the census",
                code=CODE_MALFORMED)
        return EX_MISMATCH
    try:
        status, detail, markers, _count = verify(census)
    except NoCardsError as exc:
        try:
            found = _card_markers(_extract_cards(census))
        except NoCardsError:
            found = [_EMPTY_MARKER]
        reg._stop(out, "This board census does NOT carry the zero-cards "
                       "welcome state.",
                  [str(exc),
                   "Proven on the census: %s"
                   % (", ".join(found) or "(none)"),
                   "THIS fixture never writes — the welcome-sync mutation is "
                   "--execute-gated, Trevor-gated, and the Welcome card "
                   "ships as copy from HOW-TO-USE.md."])
        _report(False, "REFUSED", len(found), execute, plan,
                str(exc), code=exc.code, found=found)
        return EX_MISMATCH
    _report(True, "PASS", 0, execute, plan,
            "%s — the welcome-sync is a clean no-op; nothing to write."
            % detail)
    out.write("[attack-no-cards] OK: %s; the Welcome card ships as copy from "
              "HOW-TO-USE.md, never as a write (the engine's database is "
              "READ-ONLY in dry-run; writes ONLY with --execute, "
              "Trevor-gated).\n" % detail)
    return EX_OK


def _credential_shaped(census) -> bool:
    """Fail-closed: a credential-shaped string (pit-/Bearer-) on the census
    is a refusal, never a judged state — a board census is a projection of
    card titles and statuses, and a token-shaped value is never that."""
    if not isinstance(census, dict):
        return False
    for key, value in census.items():
        if isinstance(value, str):
            low = value.lower()
            if low.startswith("pit-") or "bearer " in low:
                return True
    return False


# ---------------------------------------------------------------------------
# Offline self-test — golden + attack fixtures, zero network, zero secrets,
# zero writes. A FAILED self-test is exit 4 (enforced violation,
# AF-AE-WELCOME-ATTACK family), NEVER 'unexpected error' — the house
# convention.
# ---------------------------------------------------------------------------
def _zero_cards_payload() -> dict:
    """The U20 attack (zero cards): {"cards": []} — the exact projection a
    live read of an empty board serves. This is the state the welcome law
    judges a clean no-op PASS."""
    return {"cards": []}


def _cards_present_payload() -> dict:
    """The attack, non-empty: the census carries a card — the welcome-sync
    must write NOTHING into a board that already carries cards. The card
    title is synthetic (the SPEC M8 discipline: a fixture title is never a
    real card's title)."""
    return {"cards": [{"title": "Welcome", "status": "open"}]}


def self_test(out=None) -> int:
    """OFFLINE self-test: golden + attack fixtures, no network, no secrets,
    no writes. A tamper NEVER masquerades as exit 1 — it is exit 4
    (AF-AE-WELCOME-ATTACK family)."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[attack-no-cards] SELF-TEST FAILED "
                         "(AF-AE-WELCOME-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    # ---- the law surfaces are pinned byte-exact -----------------------------
    assert WELCOME_SOURCE.name == "HOW-TO-USE.md", \
        "the Welcome copy source drifted: %s" % WELCOME_SOURCE
    assert WELCOME_SOURCE.is_file(), \
        "the Welcome copy source is missing: %s" % WELCOME_SOURCE

    # ---- THE U20 ATTACK (zero cards): {"cards": []} -> PASS, no-op ----------
    status, detail, markers, count = verify(_zero_cards_payload())
    assert status == "PASS", "zero-cards census: %s" % detail
    assert markers == [_EMPTY_MARKER], \
        "the marker must PROVE the zero-cards state: %r" % markers
    assert count == 0
    plan_g = dry_run(_zero_cards_payload())
    assert plan_g["state"] == "no-op"
    assert plan_g["writes_needed"] is False
    # the zero-cards no-op must PASS WITHOUT --execute (nothing to write never
    # needs the execute flag) AND WITH --execute (there is still never
    # anything to write) — the write gate is pinned BOTH directions.
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(_zero_cards_payload(), out=io.StringIO())
    assert rc == EX_OK, "zero-cards census must exit 0, got %s" % rc
    report = json.loads(buf.getvalue())
    assert report["ok"] is True and report["verdict"] == "PASS"
    assert report["cards"] == 0
    assert report["found"] == [_EMPTY_MARKER]
    assert report["execute"] is False
    assert report["writes_needed"] is False
    assert report["contract"] == FIXTURE_CONTRACT
    buf_b = io.StringIO()
    with contextlib.redirect_stdout(buf_b):
        rc_b = payload(_zero_cards_payload(), execute=True, out=io.StringIO())
    assert rc_b == EX_OK, "zero-cards census WITH --execute must still exit " \
                          "0 (nothing to write), got %s" % rc_b
    report_b = json.loads(buf_b.getvalue())
    assert report_b["ok"] is True and report_b["execute"] is True
    assert report_b["writes_needed"] is False

    # ---- the attacks: every card-present state REFUSED ----------------------
    # 1. a card present -> the welcome-sync must write NOTHING; refused
    a1 = _cards_present_payload()
    try:
        verify(a1)
        raise AssertionError("cards-present attack was NOT refused")
    except NoCardsError as exc:
        assert CODE_CARDS_PRESENT in str(exc), \
            "the refusal must name the family code: %s" % exc
    plan_a1 = dry_run(a1)
    assert plan_a1["state"] == "readonly-refusal"
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = payload(a1, out=io.StringIO())
    assert rc2 == EX_MISMATCH, "cards-present census must exit 5, got %s" % rc2
    report2 = json.loads(buf2.getvalue())
    assert report2["ok"] is False and report2["verdict"] == "REFUSED"
    assert report2["code"] == CODE_CARDS_PRESENT
    assert report2["found"] == ["Welcome"], \
        "the card must be PROVEN in found: %s" % report2["found"]
    # with --execute it is STILL refused (exit 5) — this fixture is DATA and
    # the mutation is Trevor-gated, never triggered by this fixture.
    buf3 = io.StringIO()
    with contextlib.redirect_stdout(buf3):
        rc3 = payload(a1, execute=True, out=io.StringIO())
    assert rc3 == EX_MISMATCH, (
        "cards-present census WITH --execute must still exit 5 (fixture is "
        "DATA), got %s" % rc3)
    report3 = json.loads(buf3.getvalue())
    assert report3["code"] == CODE_CARDS_PRESENT and report3["execute"] is True

    # 2. malformed payloads -> refused, never a pass
    for bad in ({"no_cards_here": True},
                {"cards": "not-a-list"},
                "not-an-object"):
        try:
            verify(bad)
            raise AssertionError("malformed census was NOT refused: %r" % (bad,))
        except NoCardsError:
            pass
    buf4 = io.StringIO()
    with contextlib.redirect_stdout(buf4):
        rc4 = payload({"cards": "not-a-list"}, execute=True, out=io.StringIO())
    assert rc4 == EX_MISMATCH, "malformed census must exit 5, got %s" % rc4
    assert json.loads(buf4.getvalue())["code"] == CODE_MALFORMED

    # 3. a credential-shaped value on the census -> refused, never judged
    buf5 = io.StringIO()
    with contextlib.redirect_stdout(buf5):
        rc5 = payload({"cards": [], "status": "pit-"}, out=io.StringIO())
    assert rc5 == EX_MISMATCH, (
        "a credential-shaped census must exit 5, got %s" % rc5)

    # ---- the BROWSER UA law is pinned (CF 1010) ------------------------------
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), \
        "CAF_BROWSER_UA must be a browser User-Agent (CF 1010)"

    # ---- never-print: no credential-shaped string on any surface ------------
    all_text = (buf.getvalue() + buf_b.getvalue() + buf2.getvalue()
                + buf3.getvalue() + buf4.getvalue() + buf5.getvalue())
    for token in ("pit-", "Bearer ", "SEKRIT"):
        assert token not in all_text, \
            "surface leak: %r must never appear" % token

    dev.write("attack_no_cards self-test: OK (zero-cards welcome law pinned: "
              "a board census with 0 cards -> clean no-op PASS exit 0 with "
              "AND without --execute — the Welcome card ships as copy from "
              "HOW-TO-USE.md, never as a write, and the engine's database is "
              "READ-ONLY in dry-run; 1 cards-present attack refused — exit 5 "
              "AF-AE-WELCOME-CARDS-PRESENT, with AND without --execute, the "
              "card PROVEN in found; malformed censuses refused "
              "AF-AE-WELCOME-MALFORMED; credential-shaped census refused; "
              "BROWSER UA pinned; never-print)\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="attack_no_cards.py",
        description="Zero-cards attack fixture for the U20 welcome law "
                    "(Skill 59): a board census carrying ZERO cards is the "
                    "clean no-op PASS — the Welcome card ships as copy from "
                    "HOW-TO-USE.md, never as a write, and the engine's "
                    "database is READ-ONLY in dry-run (writes ONLY with "
                    "--execute, Trevor-gated). One JSON object on stdout; "
                    "fail-closed; never prints a secret value.")
    ap.add_argument("--live", action="store_true",
                    help="read a board census JSON from stdin "
                         "({'cards': [...]}) and gate it against the "
                         "zero-cards welcome law")
    ap.add_argument("--execute", action="store_true",
                    help="operator gate: the write-action flag. Naming it "
                         "confirms the operator may write — the fixture "
                         "still only reports (DATA); the welcome-sync "
                         "mutation is --execute-gated, Trevor-gated")
    ap.add_argument("cmd", nargs="?", choices=["plan", "self-test"],
                    help="offline subcommands (no network, no credentials)")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --plan / --self-test / --selftest -> positional subcommands
    # (the same normalization the registry and the sibling adapters use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    if "--plan" in argv:
        argv = ["plan" if a == "--plan" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()

        if args.cmd == "plan":
            # offline plan: no network, no credentials — the welcome law with
            # its sources, including the zero-cards state this fixture
            # certifies and the write gate it pins.
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "law": "a board census carrying ZERO cards is the clean no-op "
                       "PASS: the Welcome card ships as COPY from "
                       "HOW-TO-USE.md (never as a write), and the engine's "
                       "database is READ-ONLY in dry-run — WITHOUT --execute "
                       "no module may write it (Trevor-gated)",
                "attack": "the zero-cards state ({'cards': []}) is the state "
                          "a welcome-sync would be tempted to WRITE into; "
                          "this fixture certifies it a no-op PASS so a "
                          "mutation in a read-only state is caught HERE "
                          "first",
                "dry_run": "the plan reports state no-op, writes_needed "
                           "FALSE, and what --execute WOULD do (nothing — "
                           "the Welcome card ships as copy); nothing is ever "
                           "mutated by this fixture",
                "execute_law": "writes happen ONLY with --execute "
                               "(Trevor-gated, U20 package doctrine); this "
                               "fixture is DATA and never writes — with or "
                               "without --execute",
                "welcome_source": str(WELCOME_SOURCE),
                "note": "offline plan only — no network, no credential needed",
            }, indent=2, sort_keys=True))
            return EX_OK

        # ---- live gate: the census comes in on stdin, read from NO network
        #      (the live READER is the board projection surface, which rides
        #      the house clients — this fixture never touches the wire) ----
        if not args.live:
            reg._stop(sys.stderr, "No gate mode selected.",
                      ["Pass --live with a board census JSON on stdin "
                       "({'cards': [...]}), or --plan / --self-test "
                       "(offline)."])
            return EX_STOP
        try:
            census = json.load(sys.stdin)
        except ValueError as exc:
            reg._stop(sys.stderr, "The board census on stdin is not valid JSON.",
                      ["%s" % exc,
                       "Pipe the exact JSON the board projection surface "
                       "emits (a census with a cards array)."])
            return EX_STOP
        return payload(census, execute=args.execute, out=sys.stderr)

    except NoCardsError as exc:
        sys.stderr.write("[attack-no-cards] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except FileNotFoundError as exc:
        sys.stderr.write("[attack-no-cards] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[attack-no-cards] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
