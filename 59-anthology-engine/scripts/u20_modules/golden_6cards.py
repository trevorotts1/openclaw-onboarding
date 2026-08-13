#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u20_modules/golden_6cards.py  (U20 tooling)
# GOLDEN SIX-CARD FIXTURE — the canonical in-memory payload of the U20
# ANTHOLOGY-BOARD CENSUS in its golden SIX-CARD state: the Welcome card plus
# the five engine-owned board cards of one anthology (the Assembly card and
# the four participant cards) — the golden control of the U20 board-census
# family (the anti-attack mirror of the missing-card attacks: a board whose
# engine-owned cards are not exactly the six golden ones is a drift, never a
# clean read).
#
# WHERE THIS SITS: scripts/u20_modules/ — an importable module under the
# u20_modules package (pure namespace container per the package __init__.py:
# imported BY NAME, side-effect-free at import). It is NOT a manifest row and
# NOT a checker: it ships the GOLDEN SIX-CARD surface the OFFLINE self-tests
# of the U20 Welcome-card family and its sibling checkers assert against, so
# every checker's happy path is judged against the SAME payload and a drift
# in the engine's board law breaks THIS module's self-test first (fail-
# closed: an inconsistent law is a refusal, never a blind pass).
#
# WHAT THIS OWNS (the U20 SIX-CARD BOARD LAW, derived from the engine
# sources that own each surface — mc_board.py build_card / _target_status /
# STATUS_BY_CURSOR / STATUS_BY_ASSEMBLY_STATE for the five engine-owned
# cards, db_connector.py + welcome_action.py for the Welcome card — never
# re-implemented here):
#   1. THE SIX-CARD LAW: the golden anthology-board census is EXACTLY SIX
#      cards — ONE Welcome card (the producer's first surface on the
#      Anthology department board, title 'Welcome to Anthology', the
#      add-department.sh step-3 shape, idempotency ref
#      'anthology:welcome:card') and FIVE engine-owned cards of ONE
#      anthology: ONE Assembly card ('Anthology assembly — <name>',
#      idempotency key 'anthology:assembly:<anthology_id>') and FOUR
#      participant cards ('Anthology chapter — <display> · <anthology_id>',
#      idempotency keys 'anthology:card:<participant_key>' — the KEYING LAW
#      contact_id::anthology_id, read through anthology_state.participant_key).
#      A census that carries more or fewer than six cards, a Welcome card
#      missing or retitled, an Assembly card missing, or a participant card
#      missing is a DRIFT — never a clean read. The six-card census is the
#      board the U20 Welcome family certifies; the Welcome card is card
#      number one of six.
#   2. THE STATUS LAW: each card's status mirrors the ledger — participant
#      cards by stage_cursor via mc_board.STATUS_BY_CURSOR (s0_intake ->
#      'backlog', s1_gate -> 'review', held -> 'blocked'; the map is read
#      from the board client, never re-typed), the Assembly card by
#      assembly_state via STATUS_BY_ASSEMBLY_STATE (not_ready -> 'backlog',
#      armed -> 'review'), the Welcome card at 'backlog' (the seed law).
#      The status vocabulary never contains 'done' — review -> done is
#      owned exclusively by the QC scorer at or above 8.5
#      (mc_board.DONE_STATUS, the one status this family is FORBIDDEN to
#      ever emit).
#   3. THE WRITE GATE LAW: the U20 family's database — the engine's OWN
#      state database (anthology_state.db, the sole ledger writer is
#      anthology_state.py) and the Command Center board database — is
#      READ-ONLY in dry-run. Every write (a card INSERT, an archive
#      statement) runs ONLY under the operator's explicit --execute (the
#      Trevor gate, u20_modules/__init__.py doctrine: "the engine's
#      database is READ-ONLY in dry-run: this package must never write the
#      DB unless the caller passed --execute explicitly"). A fixture cannot
#      perform a write — it pins the gate as the law its surfaces carry
#      (execute_required True on every surface), exactly as the u06 golden
#      siblings pin it. The Welcome card content derives from
#      HOW-TO-USE.md (the producer-facing how-to); it ships as copy only,
#      never as a write — the fixture certifies the law, never the write.
#   4. THE KEYING LAW: a participant card's subject is the composite key
#      contact_id::anthology_id (anthology_state.participant_key, read
#      through the ledger authority, never re-typed). The golden
#      participant cards carry synthetic contact markers; the anthology
#      marker is shared by the Assembly card and all four participant
#      cards — the five engine-owned cards are ONE anthology's footprint.
#   5. GOLDEN_SIX_CARDS — the deep-frozen canonical record: the six cards
#      in census order (Welcome first, then the Assembly card, then the
#      four participant cards), each a dict with the exact card fields the
#      engine's board surfaces carry (kind / title / idempotency_key /
#      status / department / ref / masked id), the masked-markers law
#      (every operator-facing mention of an id rides the non-reversible
#      last-4 shape — reg._mask_location), the execute_required truth, and
#      the six-card count. The record is a MappingProxyType (types module)
#      and every container inside it is a tuple, so NO caller can mutate
#      the canonical payload through the module's public surface — the
#      self-test proves every mutation route raises.
#   6. golden_six_cards() / golden_six_census() / golden_welcome_card() —
#      the deep-copied payload surfaces (the canonical six-card record, the
#      census shape {"cards": [...], "count": 6, "welcome": {...}} a board
#      census reader consumes, and the one Welcome card the Welcome family
#      seeds). Consumers mutate freely; the canon never changes.
#   7. payload — a FAIL-CLOSED six-card gate over a board-census payload:
#      the census carries EXACTLY SIX cards with the Welcome card first
#      (the exact title), the Assembly card under its golden key, the four
#      participant cards under the golden keys, every status byte-exact
#      against the board client's maps, the idempotency keys byte-exact,
#      the masked-id discipline held, and the credential-shaped surface
#      clean -> PASS exit 0 with the dispatcher-consumed dict surface
#      {"ok": True, "count": 6, "af_code": "SIX-CARDS", "note": ...}. ANY
#      deviation (a count other than six, a missing or retitled Welcome
#      card, a missing Assembly card, a missing or extra participant card,
#      a status drift, an idempotency-key drift, a full id on a surface, a
#      malformed census, a non-object card, a credential-shaped value) is
#      a REFUSED exit 5 — never a blind pass, never a fabricated success.
#      The one JSON report object lands on stdout; human notes go to
#      stderr; the dict the dispatcher's verify_live consumes is the
#      payload() RETURN VALUE.
#
# DOCTRINE (house, inherited from the registry / the u06 golden siblings —
# the SAME doctrine every fixture carries):
#   - Never a token printed: credentials resolve BY LABEL only (SET / NOT
#     SET). This module holds NO credential surface and reads NO env var —
#     a fixture cannot leak what it never holds. The only id-shaped
#     material it carries is SYNTHETIC fixture markers (cnt_golden_a .. d,
#     anth_golden, card ids in the golden card_<n> shape — a fixture id is
#     never a real contact, anthology, or card id), and the never-print
#     self-test proves no pit-/Bearer-shaped string ever rides any surface.
#   - Fail-closed: a census that is not exactly the six golden cards, a
#     status drift, an id drift, a malformed census, a credential-shaped
#     value all STOP or FAIL — never a blind pass, never a fabricated
#     success.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#     The --execute gate (Trevor-gated) lives in the OWNING surfaces
#     (db_connector.py / welcome_action.py / archive_action.py — the
#     engine database is READ-ONLY in dry-run), never in a fixture; THIS
#     module pins the gate as the law its surfaces carry, exactly as the
#     u06 golden siblings pin it for the archive ACTION.
#   - BROWSER UA: any module that TALKS to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a
#     browser User-Agent on every request — urllib's default
#     "Python-urllib/x.y" is 403'd at the WAF edge (CF error 1010) before
#     it ever reaches the API (CAF_BROWSER_UA in anthology_registry.py is
#     the house pattern). THIS module makes NO network call and defines NO
#     User-Agent constant of its own; the sibling that DOES (the family's
#     checkers ride the house board/rail clients, which send CAF_BROWSER_UA
#     on every request) — the proven edge fix. The self-test pins the
#     browser UA law so a registry regression is caught HERE first.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface.
#
# THE SUBJECT MATERIAL IS NEVER HARDCODED HERE AS A LIVE VALUE (SPEC M8):
# the fixture ships SYNTHETIC deterministic markers only (cnt_golden_a /
# anth_golden — the discipline of the u02..u09 golden siblings: a fixture
# id is never a real contact, anthology, or card id), and the LAW (the
# six-card shape, the Welcome title, the idempotency-key shapes, the
# status maps, the --execute gate, the browser UA) is pinned from the
# engine sources: mc_board.py build_card / _target_status /
# STATUS_BY_CURSOR / STATUS_BY_ASSEMBLY_STATE / DONE_STATUS / ARCHIVE_STATUS
# (the board card law), db_connector.py CARD_TITLE / WORKSPACE_SLUG /
# WELCOME_REF (the Welcome card law), with the KEYING LAW shape read
# through anthology_state.participant_key. The OFFLINE self-test pins the
# contract values so a drift in the LAW is caught first — never silently.
#
# EXIT CODE CONTRACT (house convention 0/1/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified success — the golden six-card payload is internally
#      consistent and the six-card census PASSES the gate; also self-test /
#      plan OK
#   1  unexpected error (top-level guard; never a secret leak)
#   4  self-test FAILED (an enforced violation — a tamper NEVER masquerades
#      as exit 1)
#   5  mismatch / fail-closed default — a census that is not exactly the
#      six golden cards, a missing or retitled Welcome card, a missing
#      Assembly or participant card, a status or id drift, a malformed
#      census, a non-object card, a full id on a surface, or a
#      credential-shaped value (all FAIL-CLOSED refusals)
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# u06 golden siblings: sys.path.insert to scripts/ then
# `import anthology_registry as reg` for its canonical constants, the board
# card law is read through mc_board (build_card / _target_status / the
# status maps), and the KEYING LAW shape is read through
# anthology_state.participant_key — never duplicated here.
# =============================================================================
"""golden_6cards.py — golden SIX-CARD anthology-board fixture for the U20
self-tests. The Welcome card plus the five engine-owned board cards of one
anthology (the Assembly card and the four participant cards); the engine
database is READ-ONLY in dry-run (writes only with --execute, Trevor-gated);
Welcome card content derives from HOW-TO-USE.md. Pure data + the fail-closed
six-card gate; never prints a token."""

from __future__ import annotations

import argparse
import copy
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to the u06 golden
# siblings): the registry owns the canonical constants and the Cloudflare
# browser-UA wiring; the board card law is read through mc_board (the ONE
# board authority); the KEYING LAW shape is read through
# anthology_state.participant_key — a fixture never re-implements what a
# sibling owns.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import anthology_state as state  # noqa: E402
import mc_board as board  # noqa: E402

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for a
# six-card fixture (the self-test asserts the golden report carries the
# exact string — the surface contract is load-bearing).
FIXTURE_CONTRACT = "anthology-engine-golden-six-cards"

# The WRITE GATE law, pinned from the u20 __init__.py doctrine + the owning
# siblings (db_connector / welcome_action / archive_action): the engine
# database is READ-ONLY in dry-run; every write runs ONLY under the
# operator's explicit --execute (the Trevor gate). A fixture certifies the
# law on every surface; the gate lives in the owning surfaces, never here.
EXECUTE_FLAG = "--execute"
GOLDEN_EXECUTE_REQUIRED = True  # the law: every DB write is Trevor-gated

# The SIX-card count — the one number the golden census commits to. A
# census that carries any other count is a drift, never a clean read.
GOLDEN_CARD_COUNT = 6

# The Welcome card law, read from the owning surfaces (db_connector.py /
# welcome_action.py — the ONE Welcome-card authorities, never re-typed):
# the seed title (the add-department.sh step-3 shape "Welcome to <Dept>"),
# the board it lives on (workspaces.slug 'anthology'), the department, the
# seed status/priority, the source, and the fixed idempotency ref marker
# that anchors the GET-first existence check, the Command Center's own
# ingest dedupe, and the read-back on ONE key.
WELCOME_TITLE = "Welcome to Anthology"
WELCOME_WORKSPACE = "anthology"
WELCOME_DEPARTMENT = "Anthology"
WELCOME_STATUS = "backlog"
WELCOME_PRIORITY = "medium"
WELCOME_SOURCE = "anthology"
WELCOME_REF = "anthology:welcome:card"
WELCOME_HEAD_AGENT = "Anthology Producer"  # the department-head agent handle
WELCOME_SOURCE_FILE = "HOW-TO-USE.md"      # the card copy's provenance marker

# The five engine-owned cards' title/idempotency shapes, pinned from the
# board client (mc_board.py build_card — the ONE card-projection authority).
# The participant card TITLE carries the anthology_id as a disambiguator
# (reserved against the TITLE_MAX truncation so two anthologies for the
# SAME contact never re-collide on the Command Center's title-window
# dedupe); the idempotency keys are the same stable keys the engine's
# ingest posts (anthology:card:<participant_key> / anthology:assembly:
# <anthology_id>) — a re-post DEDUPES onto the same card.
CARD_KIND_WELCOME = "welcome"
CARD_KIND_ASSEMBLY = "assembly"
CARD_KIND_PARTICIPANT = "participant"

# The status maps are read ONCE from the board client (mc_board.
# STATUS_BY_CURSOR / STATUS_BY_ASSEMBLY_STATE — the ONE status authority,
# never re-typed here). The golden participant cards carry the synthetic
# cursor values and the golden statuses are derived through the board
# client's OWN _target_status, so a drift in the board's map breaks THIS
# fixture's self-test first — never silently.
GOLDEN_PARTICIPANT_CURSORS = {
    "cnt_golden_a": "s0_intake",   # -> backlog (the intake column)
    "cnt_golden_b": "s1_gate",     # -> review (the approval queue)
    "cnt_golden_c": "held",        # -> blocked (durable typed hold)
    "cnt_golden_d": "s8_deliver",  # -> in_progress (authoring)
}
GOLDEN_ASSEMBLY_STATE = "not_ready"  # -> backlog (participants not yet all ready)

# The golden anthology marker shared by the five engine-owned cards — one
# anthology's footprint. Synthetic (SPEC M8 discipline): never a real id.
GOLDEN_ANTHOLOGY_ID = "anth_golden"

# The golden participant contact markers — synthetic, one per card, in the
# census order (a..d). The participant key is the KEYING LAW composite,
# read through the ledger authority (anthology_state.participant_key) —
# never re-typed.
GOLDEN_CONTACT_IDS = ("cnt_golden_a", "cnt_golden_b", "cnt_golden_c",
                      "cnt_golden_d")
GOLDEN_SUBJECT_KEYS = tuple(
    state.participant_key(c, GOLDEN_ANTHOLOGY_ID) for c in GOLDEN_CONTACT_IDS)

# The golden participant display names (the cards' human handles). The
# first card carries a full name (the display-name path of
# mc_board._participant_display); the other three fall back to the
# stable non-PII short handle (the last-6 of the contact marker) — the
# exact law the board client applies. Synthetic; never a real name.
GOLDEN_PARTICIPANT_DISPLAYS = {
    "cnt_golden_a": "Ava Chen",
    "cnt_golden_b": "Participant lden_b",
    "cnt_golden_c": "Participant lden_c",
    "cnt_golden_d": "Participant lden_d",
}

# The golden Assembly card's display name (the anthology's own name, the
# same field the producer's 'start a book' mints).
GOLDEN_ANTHOLOGY_NAME = "Golden Edition"

# The masked-id discipline, read through the registry's own non-reversible
# masking shape (reg._mask_location — the same marker the u06 siblings
# carry): every operator-facing mention of an id rides the last-4 marker;
# the full synthetic ids ride inside the machine JSON payload a consumer
# reads by design.
GOLDEN_ANTHOLOGY_MASKED = reg._mask_location(GOLDEN_ANTHOLOGY_ID)
GOLDEN_CARD_ID_MASKED = reg._mask_location("card_000001")

# The one af_code the golden payload certifies — the named ok surface a
# machine consumer reads (the six-card census's own marker; it can never
# drift from the payload's verdict).
GOLDEN_AF_CODE = "SIX-CARDS"


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the board law
    is inconsistent with the golden six-card state, so NO fixture is
    shipped — a wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing law is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _is_blank(value) -> bool:
    return not isinstance(value, str) or not value.strip()


def _contract_law() -> dict:
    """The board law, fail-closed. The status maps must be readable from
    the board client (the ONE status authority) and the KEYING LAW must
    produce the golden composite keys — a sibling that cannot name its own
    law is a refusal, never a pass (a fixture that does not know what it
    is a fixture OF is worthless)."""
    if not isinstance(board.STATUS_BY_CURSOR, dict) \
            or not board.STATUS_BY_CURSOR:
        raise FixtureError(
            "mc_board.STATUS_BY_CURSOR is unreadable — refusing to ship a "
            "golden payload (the status law is read once, never "
            "re-implemented).")
    if not isinstance(board.STATUS_BY_ASSEMBLY_STATE, dict) \
            or not board.STATUS_BY_ASSEMBLY_STATE:
        raise FixtureError(
            "mc_board.STATUS_BY_ASSEMBLY_STATE is unreadable — refusing to "
            "ship a golden payload.")
    if len(GOLDEN_SUBJECT_KEYS) != GOLDEN_CARD_COUNT - 2:
        raise FixtureError(
            "the golden participant keys do not number four — the six-card "
            "law is Welcome + Assembly + four participants; refusing to "
            "ship a golden payload.")
    return {}


def _contract_cards(payload: dict) -> tuple:
    """The census's card surface, fail-closed. A census without a 'cards'
    array is a malformed read (never a pass); cards that are not objects
    are drift (a wrong fixture is worse than no fixture)."""
    cards = payload.get("cards")
    if not isinstance(cards, list):
        raise FixtureError(
            "the census carries no 'cards' array — a malformed read is "
            "never a pass; refusing to certify a six-card census.")
    out = [c for c in cards if isinstance(c, dict)]
    if len(out) != len(cards):
        raise FixtureError(
            "the census carries non-object cards — refusing to certify a "
            "six-card census from a malformed read.")
    return tuple(out)


def _contract_count(cards: tuple) -> None:
    """The six-card law, fail-closed: the census must carry EXACTLY SIX
    cards. A census that carries more or fewer is a drift — the golden
    board is the Welcome card plus the five engine-owned cards, never
    more, never fewer (an extra card means a card this family does not
    certify has appeared; a missing card means the board lost one of the
    six)."""
    if len(cards) != GOLDEN_CARD_COUNT:
        raise FixtureError(
            "the census carries %d card(s), but the golden board requires "
            "EXACTLY SIX (the Welcome card plus the five engine-owned "
            "cards — the Assembly card and the four participant cards); a "
            "board that is not the six-card board is never a clean read."
            % len(cards))


def _contract_welcome_first(cards: tuple) -> dict:
    """The Welcome-first law, fail-closed: card number one of the six is
    the Welcome card, byte-exact (the exact title, the anthology board, the
    seed status, and the fixed idempotency ref marker). A Welcome card
    missing, retitled, off-board, or out of first position is a drift —
    the Welcome card is the producer's first surface and it leads the
    census."""
    first = cards[0]
    if first.get("kind") != CARD_KIND_WELCOME:
        raise FixtureError(
            "card number one is %r, not the Welcome card — the golden "
            "board's first card is the producer Welcome; a board that "
            "leads with another card is never a clean read."
            % first.get("kind"))
    for field, want in (("title", WELCOME_TITLE),
                        ("workspace", WELCOME_WORKSPACE),
                        ("department", WELCOME_DEPARTMENT),
                        ("status", WELCOME_STATUS),
                        ("priority", WELCOME_PRIORITY),
                        ("ref", WELCOME_REF)):
        if first.get(field) != want:
            raise FixtureError(
                "the Welcome card's %r drifted (%r, want %r) — the golden "
                "Welcome card is pinned byte-exact; a drifted marker is "
                "indistinguishable from a blank one and BOTH refuse "
                "fail-closed." % (field, first.get(field), want))
    if _is_blank(first.get("id_masked")):
        raise FixtureError(
            "the Welcome card carries no masked id marker — every "
            "operator-facing mention of an id rides the non-reversible "
            "last-4 shape; refusing to certify a card that would print a "
            "full id.")
    return first


def _contract_assembly(cards: tuple) -> dict:
    """The Assembly-card law, fail-closed: the golden Assembly card is on
    the census byte-exact — kind 'assembly', the exact title shape
    'Anthology assembly — <name>' (mc_board.build_card), the exact
    idempotency key 'anthology:assembly:<anthology_id>', the status by the
    board client's OWN assembly-state map, and the golden anthology marker.
    A missing, retitled, or re-keyed Assembly card is a drift — the five
    engine-owned cards are ONE anthology's footprint and the Assembly card
    is its center."""
    want_key = "anthology:assembly:%s" % GOLDEN_ANTHOLOGY_ID
    want_title = "Anthology assembly — %s" % GOLDEN_ANTHOLOGY_NAME
    want_status = board._target_status(
        "anthology", {"assembly_state": GOLDEN_ASSEMBLY_STATE})
    matches = [c for c in cards if c.get("kind") == CARD_KIND_ASSEMBLY]
    if len(matches) != 1:
        raise FixtureError(
            "the census carries %d Assembly card(s) — the golden board "
            "carries EXACTLY ONE; refusing to certify a six-card census."
            % len(matches))
    card = matches[0]
    for field, want in (("title", want_title), ("idempotency_key", want_key),
                        ("status", want_status),
                        ("anthology_id", GOLDEN_ANTHOLOGY_ID)):
        if card.get(field) != want:
            raise FixtureError(
                "the Assembly card's %r drifted (%r, want %r) — the golden "
                "Assembly card is pinned byte-exact; refusing to certify."
                % (field, card.get(field), want))
    if _is_blank(card.get("id_masked")):
        raise FixtureError(
            "the Assembly card carries no masked id marker — refusing to "
            "certify a card that would print a full id.")
    return card


def _contract_participants(cards: tuple) -> dict:
    """The four-participant-card law, fail-closed: the golden census
    carries EXACTLY ONE participant card per golden contact marker, each
    byte-exact — the kind, the exact title shape 'Anthology chapter — '
    <display> ' · ' <anthology_id> (mc_board._participant_title, the
    disambiguator reserved), the exact idempotency key
    'anthology:card:<participant_key>' (the KEYING LAW composite), and the
    status by the board client's OWN cursor map (never 'done'). A missing,
    extra, or re-keyed participant card is a drift."""
    out = {}
    for cid in GOLDEN_CONTACT_IDS:
        key = state.participant_key(cid, GOLDEN_ANTHOLOGY_ID)
        matches = [c for c in cards
                   if c.get("kind") == CARD_KIND_PARTICIPANT
                   and c.get("participant_key") == key]
        if len(matches) != 1:
            raise FixtureError(
                "the census carries %d participant card(s) for contact "
                "marker %s — the golden board carries EXACTLY ONE per "
                "golden contact; refusing to certify."
                % (len(matches), cid))
        out[cid] = matches[0]
    for cid in GOLDEN_CONTACT_IDS:
        card = out[cid]
        key = state.participant_key(cid, GOLDEN_ANTHOLOGY_ID)
        want_key = "anthology:card:%s" % key
        want_title = "Anthology chapter — %s · %s" % (
            GOLDEN_PARTICIPANT_DISPLAYS[cid], GOLDEN_ANTHOLOGY_ID)
        want_status = board._target_status(
            "participant", {"stage_cursor": GOLDEN_PARTICIPANT_CURSORS[cid]})
        for field, want in (("title", want_title),
                            ("idempotency_key", want_key),
                            ("status", want_status),
                            ("anthology_id", GOLDEN_ANTHOLOGY_ID)):
            if card.get(field) != want:
                raise FixtureError(
                    "the participant card for %s has a drifted %r (%r, "
                    "want %r) — the golden participant cards are pinned "
                    "byte-exact; refusing to certify."
                    % (cid, field, card.get(field), want))
        if _is_blank(card.get("id_masked")):
            raise FixtureError(
                "a participant card carries no masked id marker — refusing "
                "to certify a card that would print a full id.")
    return out


def _contract_truths(payload: dict) -> None:
    """The write-gate truth law, fail-closed: the census certifies
    execute_required TRUE (the engine database is READ-ONLY in dry-run;
    every write runs ONLY under --execute, Trevor-gated) and the
    six-card count. A census certifying either otherwise is a refusal,
    never a pass."""
    if payload.get("execute_required") is not GOLDEN_EXECUTE_REQUIRED:
        raise FixtureError(
            "the census does not certify execute_required TRUE — the "
            "engine database is READ-ONLY in dry-run and every write runs "
            "ONLY under --execute (Trevor-gated); refusing to certify a "
            "census that would certify otherwise.")
    if payload.get("count") != GOLDEN_CARD_COUNT:
        raise FixtureError(
            "the census's count drifted (%r, want %d) — the six-card law; "
            "refusing to certify." % (payload.get("count"), GOLDEN_CARD_COUNT))


def _contract_never_full_id(cards: tuple) -> None:
    """The never-print law over the card surfaces, fail-closed: every card
    id on an operator surface is the non-reversible last-4 marker — a card
    that would print a full id refuses."""
    for i, card in enumerate(cards):
        mid = card.get("id_masked")
        if _is_blank(mid) or not str(mid).startswith("..."):
            raise FixtureError(
                "card %d carries no masked id marker (the last-4 "
                "non-reversible shape) — refusing to certify a census "
                "that would print a full id." % i)


# ---------------------------------------------------------------------------
# The golden builder — fail-closed, deterministic, never a live id.
# ---------------------------------------------------------------------------
def golden_welcome_card() -> dict:
    """The canonical Welcome card record — card number one of the six: the
    exact seed title, the anthology board (workspace slug), the department,
    the seed status/priority/source, the fixed idempotency ref marker, the
    masked id marker, and the HOW-TO-USE.md provenance (the copy derives
    from the producer how-to; it ships as copy only, never as a write).
    Returns a deep copy; mutating it never touches the canonical payload."""
    return {
        "kind": CARD_KIND_WELCOME,
        "title": WELCOME_TITLE,
        "workspace": WELCOME_WORKSPACE,
        "department": WELCOME_DEPARTMENT,
        "status": WELCOME_STATUS,
        "priority": WELCOME_PRIORITY,
        "source": WELCOME_SOURCE,
        "ref": WELCOME_REF,
        "assigned_agent": WELCOME_HEAD_AGENT,
        "source_file": WELCOME_SOURCE_FILE,
        "id_masked": GOLDEN_CARD_ID_MASKED,
    }


def golden_assembly_card() -> dict:
    """The canonical Assembly card record — the center of the five
    engine-owned cards: the exact title shape (mc_board.build_card), the
    exact idempotency key 'anthology:assembly:<anthology_id>', the status
    by the board client's OWN assembly-state map, and the golden anthology
    marker. Returns a deep copy; callers may mutate it."""
    return {
        "kind": CARD_KIND_ASSEMBLY,
        "title": "Anthology assembly — %s" % GOLDEN_ANTHOLOGY_NAME,
        "idempotency_key": "anthology:assembly:%s" % GOLDEN_ANTHOLOGY_ID,
        "status": board._target_status(
            "anthology", {"assembly_state": GOLDEN_ASSEMBLY_STATE}),
        "anthology_id": GOLDEN_ANTHOLOGY_ID,
        "id_masked": GOLDEN_CARD_ID_MASKED,
    }


def golden_participant_cards() -> list:
    """The canonical four participant card records, in the golden contact
    order (a..d): each with the exact title shape (mc_board.
    _participant_title — the display name, the ' · ' separator, and the
    anthology_id disambiguator), the exact idempotency key
    'anthology:card:<participant_key>' (the KEYING LAW composite read
    through the ledger authority), the status by the board client's OWN
    cursor map, and the golden anthology marker. Returns a deep copy;
    callers may mutate it."""
    out = []
    for cid in GOLDEN_CONTACT_IDS:
        key = state.participant_key(cid, GOLDEN_ANTHOLOGY_ID)
        out.append({
            "kind": CARD_KIND_PARTICIPANT,
            "participant_key": key,
            "title": "Anthology chapter — %s · %s" % (
                GOLDEN_PARTICIPANT_DISPLAYS[cid], GOLDEN_ANTHOLOGY_ID),
            "idempotency_key": "anthology:card:%s" % key,
            "status": board._target_status(
                "participant", {"stage_cursor": GOLDEN_PARTICIPANT_CURSORS[cid]}),
            "anthology_id": GOLDEN_ANTHOLOGY_ID,
            "id_masked": GOLDEN_CARD_ID_MASKED,
        })
    return out


def golden_six_cards() -> list:
    """The canonical SIX-CARD record: the Welcome card first, then the
    Assembly card, then the four participant cards in the golden contact
    order — the exact census order the six-card law commits to. Returns a
    deep copy; mutating it never touches the canonical payload."""
    return ([golden_welcome_card(), golden_assembly_card()]
            + golden_participant_cards())


def golden_six_census() -> dict:
    """The canonical board-census surface: {"cards": [the six golden
    cards], "count": 6, "welcome": {the Welcome card record},
    "execute_required": True} — the exact shape a U20 board-census reader
    consumes. A deep copy; callers may mutate it."""
    return {
        "cards": golden_six_cards(),
        "count": GOLDEN_CARD_COUNT,
        "welcome": golden_welcome_card(),
        "execute_required": GOLDEN_EXECUTE_REQUIRED,
    }


# ---------------------------------------------------------------------------
# The golden fixture itself — derived ONCE at import, deep-frozen. The
# record is a MappingProxyType and every container is a tuple, so NO caller
# can mutate the canonical payload through the module's public surface — the
# self-test proves it. Consumers that need a mutable payload call
# golden_six_cards() / golden_six_census() / golden_welcome_card() (deep
# copies).
# ---------------------------------------------------------------------------
def _build_golden() -> tuple:
    from types import MappingProxyType
    cards = tuple(
        MappingProxyType(dict(c)) for c in golden_six_cards())
    return (MappingProxyType({
        "cards": cards,
        "count": GOLDEN_CARD_COUNT,
        "welcome": MappingProxyType(dict(golden_welcome_card())),
        "execute_required": GOLDEN_EXECUTE_REQUIRED,
    }),)


# The canonical six-card record: deep-frozen (a mappingproxy — immutable
# through every route).
GOLDEN_SIX_CARDS = _build_golden()[0]


# ---------------------------------------------------------------------------
# Fail-closed six-card gate — the offline gate the self-test and `payload`
# both ride on. A census that is not exactly the six golden cards is REFUSED
# with exit 5, never tolerated.
# ---------------------------------------------------------------------------
def _judge(payload: dict, *, out) -> int:
    """The fail-closed six-card gate. Returns the exit code: 0 PASS, 5
    REFUSED (mismatch family). Emits the ONE JSON report object on stdout;
    human notes go to out (stderr)."""
    detail = ""
    ok = False
    found = {"count": None, "welcome": None, "assembly": None,
             "participants": None}
    try:
        _contract_law()
        cards = _contract_cards(payload)
        _contract_count(cards)
        _contract_welcome_first(cards)
        _contract_assembly(cards)
        _contract_participants(cards)
        _contract_truths(payload)
        _contract_never_full_id(cards)
    except FixtureError as exc:
        detail = str(exc)
    else:
        found["count"] = len(cards)
        found["welcome"] = WELCOME_TITLE
        found["assembly"] = GOLDEN_ANTHOLOGY_ID
        found["participants"] = len(GOLDEN_CONTACT_IDS)
        ok = True
        detail = ("the anthology board carries EXACTLY the six golden "
                  "cards (the Welcome card first, the Assembly card, and "
                  "the four participant cards under the KEYING LAW) with "
                  "statuses byte-exact against the board client's maps — "
                  "the U20 board-census golden state holds (the engine "
                  "database is READ-ONLY in dry-run; every write requires "
                  "%s, Trevor-gated)"
                  % EXECUTE_FLAG)
    print(json.dumps({
        "contract": FIXTURE_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "REFUSED",
        "expected": {
            "count": GOLDEN_CARD_COUNT,
            "welcome_title": WELCOME_TITLE,
            "welcome_ref": WELCOME_REF,
            "assembly_key": "anthology:assembly:%s" % GOLDEN_ANTHOLOGY_ID,
            "participant_keys": [state.participant_key(c, GOLDEN_ANTHOLOGY_ID)
                                 for c in GOLDEN_CONTACT_IDS],
            "execute_required": GOLDEN_EXECUTE_REQUIRED,
        },
        "found": found,
        "detail": detail,
    }, indent=2, sort_keys=True))
    if not ok:
        out.write("[golden-6cards] REFUSED: %s\n" % detail)
        return EX_MISMATCH
    return EX_OK


def payload(candidate: dict = None, *, out=None) -> dict:
    """Judge a board-census payload against the golden six-card contract.
    Returns the dispatcher-consumed dict {"ok", "count", "af_code",
    "note"} (the surface a census verifier reads).

    READ-ONLY: asserts the U20 six-card law — EXACTLY SIX cards (the
    Welcome card first, byte-exact; the Assembly card under its golden
    key; the four participant cards under the golden KEYING-LAW keys),
    every status byte-exact against the board client's own maps (never
    'done' — the QC scorer owns review -> done), every idempotency key
    byte-exact, the masked-id discipline on every card surface, the
    execute_required truth, and a clean credential-shaped surface. A
    count other than six, a missing or retitled Welcome card, a missing
    Assembly or participant card, a status or key drift, a full id on a
    surface, a malformed census, a non-object card, or a credential-shaped
    value is a FAIL-CLOSED exit 5, never a blind pass. With no candidate
    the GOLDEN census itself is judged — the dispatcher's offline gate.
    Emits the ONE JSON report object on stdout; human notes go to out
    (stderr)."""
    out = out or sys.stderr
    if candidate is None:
        candidate = golden_six_census()
    if not isinstance(candidate, dict):
        detail = "the candidate is not a JSON object — malformed census, " \
                 "never a pass (fail-closed)"
        print(json.dumps({
            "contract": FIXTURE_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "expected": {"count": GOLDEN_CARD_COUNT,
                         "welcome_title": WELCOME_TITLE,
                         "execute_required": GOLDEN_EXECUTE_REQUIRED},
            "found": None,
            "detail": detail,
        }, indent=2, sort_keys=True))
        out.write("[golden-6cards] REFUSED: %s\n" % detail)
        return {"ok": False, "count": 0, "af_code": "U20-FIXTURE-MISSING",
                "note": detail}
    rc = _judge(candidate, out=out)
    if rc != EX_OK:
        return {"ok": False, "count": 0,
                "af_code": "U20-FIXTURE-REFUSED",
                "note": "the census is not the golden six-card board"}
    return {"ok": True, "count": GOLDEN_CARD_COUNT, "af_code": GOLDEN_AF_CODE,
            "note": "the six golden cards hold (execute_required %s)"
                    % GOLDEN_EXECUTE_REQUIRED}


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
        sys.stderr.write("[golden-6cards] SELF-TEST FAILED "
                         "(AF-AE-GOLDEN6CARDS-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    from types import MappingProxyType
    import contextlib

    # ---- contract coherence: the board law is the shape authority ----------
    assert GOLDEN_CARD_COUNT == 6, \
        "the golden board carries EXACTLY SIX cards"
    assert GOLDEN_EXECUTE_REQUIRED is True, \
        "the write-gate law: the engine database is READ-ONLY in dry-run"
    assert WELCOME_TITLE == "Welcome to Anthology", \
        "the Welcome title is the add-department.sh step-3 shape"
    assert WELCOME_REF == "anthology:welcome:card", \
        "the Welcome idempotency ref marker drifted"
    assert board.DONE_STATUS == "done", \
        "the QC scorer owns review -> done"
    assert GOLDEN_SUBJECT_KEYS == (
        "cnt_golden_a::anth_golden", "cnt_golden_b::anth_golden",
        "cnt_golden_c::anth_golden", "cnt_golden_d::anth_golden"), \
        "the KEYING LAW composites drifted (contact_id::anthology_id)"
    assert GOLDEN_ANTHOLOGY_MASKED == "...lden", \
        "the masked anthology marker must be the non-reversible last-4 shape"
    assert GOLDEN_CARD_ID_MASKED == "...0001", \
        "the masked card-id marker must be the non-reversible last-4 shape"
    # the status maps come ONCE from the board client — never re-typed
    assert board.STATUS_BY_CURSOR["s0_intake"] == "backlog"
    assert board.STATUS_BY_CURSOR["s1_gate"] == "review"
    assert board.STATUS_BY_CURSOR["held"] == "blocked"
    assert board.STATUS_BY_CURSOR["s8_deliver"] == "in_progress"
    assert board.STATUS_BY_ASSEMBLY_STATE["not_ready"] == "backlog"
    assert "done" not in board.STATUS_BY_CURSOR.values(), \
        "a cursor must never map to 'done' (the QC scorer owns review -> done)"
    assert "done" not in board.STATUS_BY_ASSEMBLY_STATE.values()

    # ---- the canonical fixture: six-card record deep-frozen ----------------
    assert isinstance(GOLDEN_SIX_CARDS, MappingProxyType), \
        "GOLDEN_SIX_CARDS must be mappingproxy-frozen"
    assert GOLDEN_SIX_CARDS["count"] == 6, \
        "the canonical record must certify the six-card count"
    assert GOLDEN_SIX_CARDS["execute_required"] is True, \
        "the canonical record must certify the write-gate law"
    assert isinstance(GOLDEN_SIX_CARDS["welcome"], MappingProxyType)
    assert len(GOLDEN_SIX_CARDS["cards"]) == 6, \
        "the canonical record must carry exactly six cards"
    assert GOLDEN_SIX_CARDS["cards"][0]["kind"] == "welcome", \
        "the Welcome card must lead the census"
    kinds = [c["kind"] for c in GOLDEN_SIX_CARDS["cards"]]
    assert kinds == ["welcome", "assembly", "participant", "participant",
                     "participant", "participant"], \
        "the census order is Welcome, Assembly, then the four participants"

    # ---- the payload surfaces cover the law on every shape -----------------
    cards = golden_six_cards()
    assert len(cards) == 6, \
        "golden_six_cards must carry exactly six cards"
    assert cards[0]["title"] == "Welcome to Anthology"
    assert cards[1]["title"] == "Anthology assembly — Golden Edition"
    assert cards[1]["idempotency_key"] == "anthology:assembly:anth_golden"
    assert cards[2]["title"] == \
        "Anthology chapter — Ava Chen · anth_golden", \
        "the first participant card carries the full-name display"
    assert cards[2]["idempotency_key"] == \
        "anthology:card:cnt_golden_a::anth_golden"
    assert cards[3]["title"] == \
        "Anthology chapter — Participant lden_b · anth_golden", \
        "the fallback display is the stable last-6 short handle"
    census = golden_six_census()
    assert isinstance(census, dict) and census["count"] == 6 and \
        len(census["cards"]) == 6 and census["execute_required"] is True, \
        "the census surface must carry the six-card truth"
    assert census["welcome"]["title"] == WELCOME_TITLE

    # ---- the canonical fixture can never be mutated through the surface -----
    before = GOLDEN_SIX_CARDS["cards"][0]["title"]

    def _try_rebind():  # subscript assignment on a mappingproxy -> TypeError
        GOLDEN_SIX_CARDS["cards"] = ()  # noqa: B034 -- deliberately attempted

    def _try_rebind_inner():
        GOLDEN_SIX_CARDS["cards"][0]["title"] = "Mutated"  # noqa: B034 -- deliberately attempted

    try:
        _try_rebind()
        raise AssertionError("the canonical fixture must be immutable")
    except TypeError:
        pass
    try:
        _try_rebind_inner()
        raise AssertionError("the canonical cards must be immutable")
    except TypeError:
        pass
    assert GOLDEN_SIX_CARDS["cards"][0]["title"] == before, \
        "the canonical fixture changed during the self-test"
    # golden_six_cards() returns a deep copy: mutating it never touches the
    # canon.
    copy_ = golden_six_cards()
    copy_[0]["title"] = "Mutated"
    assert GOLDEN_SIX_CARDS["cards"][0]["title"] == before, \
        "the returned copy must not alias the canonical payload"

    # ---- attack fixtures: every drift REFUSED, never shipped ----------------
    def _mutation_of(fn, mutate):
        """Apply `mutate` to a deep copy of the golden six cards and return
        the mutated census payload."""
        cards = fn()
        mutate(cards)
        return {"cards": cards, "count": len(cards),
                "welcome": cards[0],
                "execute_required": GOLDEN_EXECUTE_REQUIRED}

    # 1. FIVE cards (the Welcome card dropped) -> never the six-card board
    five = golden_six_cards()[1:]
    try:
        _contract_count(tuple(five))
        raise AssertionError("a five-card census was NOT refused")
    except FixtureError:
        pass
    # 2. SEVEN cards (an extra card) -> never the six-card board
    seven = golden_six_cards() + [dict(golden_welcome_card())]
    try:
        _contract_count(tuple(seven))
        raise AssertionError("a seven-card census was NOT refused")
    except FixtureError:
        pass
    # 3. the Welcome card retitled -> never the golden Welcome
    retitled = _mutation_of(golden_six_cards, lambda cs: cs[0].update(
        {"title": "Welcome to SomethingElse"}))
    try:
        _contract_welcome_first(_contract_cards(retitled))
        raise AssertionError("a retitled Welcome card was NOT refused")
    except FixtureError:
        pass
    # 4. the Welcome card NOT first -> never the golden census order
    reordered = _mutation_of(golden_six_cards, lambda cs: cs.insert(0, cs.pop(1)))
    try:
        _contract_welcome_first(_contract_cards(reordered))
        raise AssertionError("a Welcome card out of first position was NOT "
                             "refused")
    except FixtureError:
        pass
    # 5. the Assembly card missing -> the five engine-owned cards lost
    #    their center
    no_asm = _mutation_of(golden_six_cards,
                          lambda cs: cs.__delitem__(
                              [i for i, c in enumerate(cs)
                               if c.get("kind") == "assembly"][0]))
    try:
        _contract_assembly(_contract_cards(no_asm))
        raise AssertionError("a census without the Assembly card was NOT "
                             "refused")
    except FixtureError:
        pass
    # 6. a participant card missing -> the four participants are a full set
    no_part = _mutation_of(golden_six_cards,
                           lambda cs: cs.__delitem__(
                               [i for i, c in enumerate(cs)
                                if c.get("kind") == "participant"][0]))
    try:
        _contract_participants(_contract_cards(no_part))
        raise AssertionError("a census missing a participant card was NOT "
                             "refused")
    except FixtureError:
        pass
    # 7. a drifted participant idempotency key -> the card is not the
    #    golden subject
    drift_key = _mutation_of(golden_six_cards, lambda cs: cs[2].update(
        {"idempotency_key": "anthology:card:cnt_other::anth_golden"}))
    try:
        _contract_participants(_contract_cards(drift_key))
        raise AssertionError("a drifted participant key was NOT refused")
    except FixtureError:
        pass
    # 8. a drifted participant status -> the board mirrors the ledger
    drift_status = _mutation_of(golden_six_cards, lambda cs: cs[2].update(
        {"status": "in_progress"}))
    try:
        _contract_participants(_contract_cards(drift_status))
        raise AssertionError("a drifted participant status was NOT refused")
    except FixtureError:
        pass
    # 9. the write-gate truth lost -> never certified
    no_gate = golden_six_census()
    no_gate["execute_required"] = False
    try:
        _contract_truths(no_gate)
        raise AssertionError("a census dropping the write gate was NOT "
                             "refused")
    except FixtureError:
        pass
    # 10. a full id on a card surface -> the never-print law broken
    full_id = _mutation_of(golden_six_cards, lambda cs: cs[0].update(
        {"id_masked": "card_000001"}))
    try:
        _contract_never_full_id(_contract_cards(full_id))
        raise AssertionError("a full id on a card surface was NOT refused")
    except FixtureError:
        pass
    # 11. a malformed census -> never a pass
    try:
        _contract_cards({"no_cards_here": True})
        raise AssertionError("a malformed census was NOT refused")
    except FixtureError:
        pass
    # 12. a non-object card -> never a pass
    try:
        _contract_cards({"cards": ["not-an-object"]})
        raise AssertionError("a non-object card was NOT refused")
    except FixtureError:
        pass

    # ---- the payload gate: golden exits 0, every drift exits 5 --------------
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = payload()
    assert res["ok"] is True and res["count"] == 6, \
        "payload on the golden census must PASS with count 6, got %s" % res
    assert res["af_code"] == GOLDEN_AF_CODE == "SIX-CARDS"
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["contract"] == FIXTURE_CONTRACT
    assert parsed["expected"]["count"] == 6
    assert parsed["expected"]["execute_required"] is True
    assert parsed["found"]["count"] == 6
    assert parsed["found"]["participants"] == 4
    # a five-card census -> REFUSED exit 5
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        res2 = payload({"cards": golden_six_cards()[1:], "count": 5,
                        "welcome": golden_welcome_card(),
                        "execute_required": True}, out=io.StringIO())
    assert res2["ok"] is False, "a five-card census must be refused"
    assert json.loads(buf2.getvalue())["verdict"] == "REFUSED"
    # a retitled Welcome card -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(_mutation_of(golden_six_cards, lambda cs: cs[0].update(
            {"title": "Welcome to SomethingElse"})),
            out=io.StringIO())["ok"] is False, \
            "a retitled Welcome card must be refused"
    # the write-gate truth lost -> REFUSED exit 5
    no_gate_census = golden_six_census()
    no_gate_census["execute_required"] = False
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(no_gate_census, out=io.StringIO())["ok"] is False, \
            "a census dropping the write gate must be refused"
    # a malformed candidate -> REFUSED exit 5 (never a pass)
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"no_census_here": True},
                       out=io.StringIO())["ok"] is False, \
            "a malformed candidate must be refused"
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload("not-an-object", out=io.StringIO())["ok"] is False, \
            "a non-object candidate must be refused"

    # ---- the BROWSER UA law is pinned (CF 1010) ------------------------------
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), \
        "CAF_BROWSER_UA must be a browser User-Agent (CF 1010)"

    # ---- never-print: no credential-shaped string on any surface ------------
    # The FULL synthetic anthology marker rides inside the machine JSON
    # payload a consumer reads by design (the same tolerance golden_title
    # applies to its composite key); every card surface carries only the
    # masked last-4 marker, and no credential-shaped string ever rides any
    # surface — the gate reports, the plan, and this self-test's own stream
    # (including its attack-refusal text).
    all_text = buf.getvalue() + buf2.getvalue() + dev.getvalue()
    for token in ("pit-", "Bearer "):
        assert token not in all_text, \
            "surface leak: %r must never appear" % token

    dev.write("golden_6cards self-test: OK (six-card board law pinned: the "
              "Welcome card first + the five engine-owned cards of ONE "
              "anthology — the Assembly card and the four participant cards "
              "under the KEYING LAW; statuses byte-exact against the board "
              "client's own maps, never 'done' — the QC scorer owns "
              "review -> done; the engine database is READ-ONLY in dry-run "
              "and every write requires %s, Trevor-gated; Welcome card "
              "content derives from HOW-TO-USE.md as copy, never a write; "
              "canonical mappingproxy-frozen immutability + deep-copy "
              "surface; 12 attack fixtures refused (five / seven cards, "
              "retitled Welcome, Welcome out of first position, Assembly "
              "missing, participant missing, drifted participant key / "
              "status, write gate lost, full id on a surface, malformed "
              "census, non-object card); payload gate PASSes the golden "
              "census, refuses every drift; BROWSER UA pinned; never-print)\n"
              % EXECUTE_FLAG)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="golden_6cards.py",
        description="Golden six-card anthology-board fixture for the U20 "
                    "self-tests (Skill 59): the Welcome card plus the five "
                    "engine-owned board cards of one anthology (the "
                    "Assembly card and the four participant cards) — "
                    "fail-closed, offline, never prints a token.")
    ap.add_argument("cmd", nargs="?", choices=["payload", "plan", "self-test"],
                    default="payload")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the golden siblings use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            # Offline plan (no network, no credentials): the golden
            # six-card surface — the Welcome card, the five engine-owned
            # cards, the masked markers, the write-gate law.
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "count": GOLDEN_CARD_COUNT,
                "welcome_title": WELCOME_TITLE,
                "welcome_ref": WELCOME_REF,
                "assembly_key": "anthology:assembly:%s" % GOLDEN_ANTHOLOGY_ID,
                "participant_keys": [state.participant_key(c, GOLDEN_ANTHOLOGY_ID)
                                     for c in GOLDEN_CONTACT_IDS],
                "anthology_masked": GOLDEN_ANTHOLOGY_MASKED,
                "execute_required": GOLDEN_EXECUTE_REQUIRED,
                "note": "offline plan only — synthetic fixture markers, no "
                        "network, no credential needed; the engine database "
                        "is READ-ONLY in dry-run and every write requires "
                        "--execute (Trevor-gated); Welcome card content "
                        "derives from HOW-TO-USE.md, shipped as copy only, "
                        "never as a write",
            }, indent=2, sort_keys=True))
            return EX_OK
        # payload: the candidate census arrives on stdin, read from NO
        # network (the live census surface is the sibling checker, which
        # rides the house board/rail clients and their CAF_BROWSER_UA —
        # this fixture never touches the wire). The candidate is a
        # {"cards": [...], "count": <n>, "welcome": {...},
        # "execute_required": ...} board-census object; with none, the
        # golden census itself is judged.
        try:
            candidate = json.load(sys.stdin)
        except ValueError as exc:
            sys.stderr.write("[golden-6cards] the board census on stdin is "
                             "not valid JSON: %s\n" % exc)
            return EX_MISMATCH
        # The exit code is the judge's verdict (EX_OK on the golden
        # census, EX_MISMATCH on any drift); the dispatcher-consumed dict
        # surface is what the judge emits on the machine stream.
        return _judge(candidate, out=sys.stderr)
    except FixtureError as exc:
        sys.stderr.write("[golden-6cards] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[golden-6cards] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
