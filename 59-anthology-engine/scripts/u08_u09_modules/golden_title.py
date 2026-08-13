#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u08_u09_modules/golden_title.py  (U08/U09)
# GOLDEN TITLE-SELECT FIXTURE — the canonical in-memory payload of the U08/U09
# TITLE-SELECT surface in its GOLDEN state: the participant's S3 title
# selection — the exact title and subtitle the participant locked on the
# token page — with the one-way TITLE LOCK law stamped, the composite
# participant key under the KEYING LAW, and the selection carried on both
# doors (the token door and the board door) — the golden control of the
# U08/U09 title-select gate (the anti-attack mirror of the missing-field
# attack fixture, which certifies the state where a required selection
# field is ABSENT).
#
# WHERE THIS SITS: scripts/u08_u09_modules/ — an importable module under the
# u08_u09_modules package (pure namespace container per the package
# __init__.py: imported BY NAME, side-effect-free at import; the init
# records the house doctrine: destructive actions require --execute,
# Trevor-gated — WITHOUT --execute a module must report what it WOULD do and
# exit without mutating; anything that talks to GoHighLevel / Convert and
# Flow must carry the house browser User-Agent). It is NOT a manifest row and
# NOT a checker: it ships the GOLDEN title-select surface the offline
# self-tests of the U08/U09 builder, its sibling checkers, and the
# missing-field attack fixture all assert against, so every checker's happy
# path is judged against the SAME payload and a drift in the engine's
# title-select law breaks THIS module's self-test first (fail-closed: an
# inconsistent law is a refusal, never a blind pass).
#
# WHAT THIS OWNS (the U08/U09 TITLE-SELECT LAW, derived from the engine
# sources that own the surface — anthology_state.py record-approval on the
# s3_selection gate, gate_engine.py ACTION_DECISION "select", and
# stage_s3_title.py — never re-implemented here):
#   1. THE SELECT LAW: the participant's S3 title selection is an approve
#      decision on the s3_selection gate whose REQUIRED extra field is
#      EXACTLY ONE — the title (ACTION_DECISION["select"] == ("approve",
#      ("title",)), the "select" action's subtitle optional) — and the
#      selection STAMPS THE TITLE LOCK, ONE-WAY (anthology_state.py: the
#      lock is byte-exact and a different title/subtitle is an ILLEGAL
#      transition — "title lock is one-way; a change requires a producer
#      exception" — and re-selecting the same locked pair is an IDEMPOTENT
#      REPLAY). The golden payload carries the FULL locked pair (title and
#      subtitle), so a checker that accepts a payload with the title but no
#      subtitle is caught HERE first — the lock is a PAIR, never a
#      title-only stamp.
#   2. THE TITLE LAW IS READ ONCE: the golden subject material is NEVER a
#      live participant's selection — it is the synthetic fixture pair this
#      module pins ONCE, and the law the fixture certifies (the one-required-
#      field select contract, the one-way lock, the composite key) is read
#      from the OWNING siblings, never retyped as a second implementation.
#      The selection reaches the ledger BY EXACT TITLE and EXACT SUBTITLE
#      (the byte-exact lock law: a drifted title or subtitle is
#      indistinguishable from a blank one and BOTH refuse fail-closed).
#   3. THE KEYING LAW: the participant row the selection stamps is keyed by
#      the composite participant_key, contact_id::anthology_id — read ONCE
#      through anthology_state.participant_key (the ONE keying authority
#      the u06 golden siblings already read the same way), never duplicated
#      here.
#   4. BOTH DOORS: the s3_selection gate is a PARTICIPANT gate and the ONE
#      action it presents is "select" — the token door (nudge_link) is the
#      participant's own door; the board door (dashboard) is a producer's
#      session and NEVER releases anything for a select (release_slug_for
#      returns None for every select — participant title-select releases
#      nothing). The golden payload carries the canonical door provenance
#      under the KEYING LAW, and the fixture pins the door vocabulary
#      ("token" / "board" -> "nudge_link" / "dashboard").
#   5. GOLDEN_TITLE — the deep-frozen canonical record: the locked
#      {"title": <synthetic pair>, "subtitle": <synthetic pair>}, the
#      participant_key under the KEYING LAW (synthetic contact and anthology
#      markers only — a fixture id is never a real id), the masked id marker
#      for every operator surface, and the one-way lock truth. The record is
#      a MappingProxyType (types module) and every container inside it is a
#      tuple, so NO caller can mutate the canonical payload through the
#      module's public surface — the self-test proves every mutation route
#      raises.
#   6. golden_title() / golden_title_payload() / golden_select_payload()
#      — the deep-copied payload surfaces (the canonical locked record, the
#      {"title": ..., "subtitle": ...} working/title.json shape the S3
#      working file and the tier-1 lock check both read, and the
#      {"gate": "s3_selection", "action": "select", "decision": "approve",
#      "door": ..., "participant_key": ..., "title": ..., "subtitle": ...,
#      "id_masked": ..., "lock_one_way": true} select shape the U08/U09
#      builder consumes) consumers mutate freely; the canon never changes.
#   7. payload — a FAIL-CLOSED title-select gate: the golden selection
#      carries the byte-exact locked pair under the golden keys, each
#      matched BY EXACT VALUE, the one-way lock truth held, and the
#      KEYING LAW key -> PASS exit 0 with the dispatcher-consumed dict
#      surface {"ok": True, "gate": "s3_selection", "title": ...,
#      "subtitle": ..., "participant_key": ..., "af_code":
#      "TITLE-SELECT", "note": ...}. ANY deviation (a blank title, a blank
#      subtitle, a drifted title or subtitle, a lock not one-way, a
#      malformed payload, a non-object candidate, a credential-shaped
#      value) is a REFUSED exit 5 — never a blind pass, never a fabricated
#      success. The one JSON report object lands on stdout; human notes go
#      to stderr; the dict the dispatcher's verify_live consumes is the
#      payload() RETURN VALUE.
#
# DOCTRINE (house, inherited from the registry / the u02/u03/u04/u05/u06/u07
# golden siblings — the SAME doctrine every fixture carries):
#   - Never a token printed: credentials resolve BY LABEL only (SET / NOT
#     SET). This module holds NO credential surface and reads NO env var — a
#     fixture cannot leak what it never holds. The only id-shaped material
#     it carries is SYNTHETIC fixture markers (cnt_golden / anth_golden),
#     and the never-print self-test proves no pit-/Bearer-shaped string ever
#     rides any surface.
#   - Fail-closed: a blank or drifted title, a blank subtitle, a lock that
#     is not one-way, a malformed payload, a credential-shaped value all
#     STOP or FAIL — never a blind pass, never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates. The
#     --execute gate (Trevor-gated) lives in the dispatcher
#     (main_skeleton.py), never in a fixture; THIS module pins the gate as
#     the law its surfaces carry, exactly as golden_found pins it for the
#     U06 archive action and golden_all_present pins it for the U07
#     provisioning action.
#   - BROWSER UA: any module that TALKS to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a
#     browser User-Agent on every request — urllib's default
#     "Python-urllib/x.y" is 403'd at the WAF edge (CF error 1010) before it
#     ever reaches the API (CAF_BROWSER_UA in anthology_registry.py is the
#     house pattern). THIS module makes NO network call and defines NO
#     User-Agent constant of its own; the sibling that DOES (the builder
#     rides the house rail client, which sends CAF_BROWSER_UA on every
#     request) — the proven edge fix. The self-test pins the browser UA law
#     so a registry regression is caught HERE first.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface.
#
# THE SUBJECT MATERIAL IS NEVER HARDCODED HERE AS A LIVE VALUE (SPEC M8): the
# fixture ships SYNTHETIC deterministic ids only (cnt_golden / anth_golden —
# the discipline of the u02/u03/u04/u05/u06/u07 siblings: a fixture id is
# never a real participant, form, anthology, workflow, or field id), and the
# locked title/subtitle pair is a FABRICATED fixture pair — never a real
# participant's selection. The LAW (the one-required-field select contract,
# the one-way byte-exact lock, the composite key) is pinned from the engine
# sources: anthology_state.py record-approval on the s3_selection gate (the
# title-lock stamp) and gate_engine.py ACTION_DECISION (the "select" action
# requiring the title, subtitle optional), with participant_key (the KEYING
# LAW) read through anthology_state.participant_key. The OFFLINE self-test
# pins the contract values so a drift in the LAW is caught first — never
# silently.
#
# EXIT CODE CONTRACT (house convention 0/1/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified success — the golden title-select payload is internally
#      consistent and the golden selection PASSES the gate; also
#      self-test / plan OK
#   1  unexpected error (top-level guard; never a secret leak)
#   4  self-test FAILED (an enforced violation — a tamper NEVER masquerades
#      as exit 1)
#   5  mismatch / fail-closed default — a blank or drifted title, a blank
#      subtitle, a lock that is not one-way, a malformed payload, a
#      non-object candidate, or a credential-shaped value (all FAIL-CLOSED
#      refusals)
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# u05/u06/u07 golden siblings: sys.path.insert to scripts/ then
# `import anthology_registry as reg` for its canonical constants, and the
# KEYING LAW shape is read through anthology_state.participant_key — never
# duplicated here.
# =============================================================================
"""golden_title.py — golden TITLE-SELECT fixture for the U08/U09
self-tests. The canonical S3 title-selection payload: the byte-exact locked
title/subtitle pair under the KEYING LAW, one-way lock stamped, both doors.
Pure data + the fail-closed title-select gate; never prints a token."""

from __future__ import annotations

import argparse
import copy
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to the u05/u06/u07
# golden siblings): the registry owns the canonical constants and the
# Cloudflare browser-UA wiring; the KEYING LAW shape is read through
# anthology_state.participant_key (the ONE keying authority) — a fixture
# never re-implements what a sibling owns.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import anthology_state as state  # noqa: E402

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for a
# title-select fixture (the self-test asserts the golden report carries the
# exact string — the surface contract is load-bearing).
FIXTURE_CONTRACT = "anthology-engine-golden-title"

# The one select-action contract, pinned from the engine sources: the
# s3_selection gate (PARTICIPANT door, the ONE action "select" — gate_engine
# GATE_BY_CURSOR["s3_gate"]) maps to the sole-writer decision "approve" whose
# REQUIRED extra field is EXACTLY ONE — the title — with the subtitle
# optional (gate_engine ACTION_DECISION["select"] == ("approve",
# ("title",))). A selection that carries no title is a nameless selection —
# a refusal, never a sweep. These constants pin the LAW on this fixture's
# surfaces so a drift in the owning sibling breaks THIS module's self-test
# first — never silently.
SELECT_GATE = "s3_selection"
SELECT_ACTION = "select"
SELECT_DECISION = "approve"
SELECT_TITLE_REQUIRED = True   # the law: the select action REQUIRES the title
SELECT_SUBTITLE_OPTIONAL = True  # the law: the subtitle is optional in the select

# The one-way TITLE LOCK law, pinned from the engine source: record-approval
# on the s3_selection gate stamps the lock, byte-exact, and a DIFFERENT
# title/subtitle is an ILLEGAL transition ("title lock is one-way; a change
# requires a producer exception" — anthology_state.py); re-selecting the
# same locked pair is an IDEMPOTENT REPLAY. The golden payload carries the
# FULL locked pair (title AND subtitle) and certifies the lock one-way — a
# checker that would accept a title-only stamp or a different pair is caught
# HERE first.
TITLE_LOCK_ONE_WAY = True

# The door vocabulary (gate_engine DOOR_VALUE — the sole-writer door
# provenance values): the token door is the participant's own door
# ("nudge_link"); the board door is a producer's session ("dashboard") and
# NEVER releases anything for a select (release_slug_for returns None for
# every select — participant title-select releases nothing).
DOOR_TOKEN = "nudge_link"
DOOR_BOARD = "dashboard"
SELECT_DOORS = (DOOR_TOKEN, DOOR_BOARD)  # the fixed two, in order

# The one required selection field, pinned from the engine source: the
# byte-exact "title" key of the working/title.json surface the S3 runner
# writes and the tier-1 title-lock check reads (stage_s3_title.WORKING_FILE
# "title.json"; qc-tier1-anthology.py check 2 reads {"title", "subtitle"}
# from it and requires BOTH byte-exact — a blank subtitle fails the lock
# check, never a silent title-only pass).
TITLE_FIELD = "title"
SUBTITLE_FIELD = "subtitle"
TITLE_FIELDS = (TITLE_FIELD, SUBTITLE_FIELD)  # the fixed pair, in order

# The stable SYNTHETIC subject material (the synthetic-id discipline of the
# u02/u03/u04/u05/u06/u07 golden siblings — a fixture id is never a real
# id). The composite participant key under the KEYING LAW (contact_id::
# anthology_id), read through state.participant_key — never retyped.
GOLDEN_CONTACT_ID = "cnt_golden"
GOLDEN_ANTHOLOGY_ID = "anth_golden"
GOLDEN_SUBJECT_KEY = state.participant_key(GOLDEN_CONTACT_ID, GOLDEN_ANTHOLOGY_ID)

# The FABRICATED golden pair (SPEC M8 — never a live participant's
# selection). The golden surface carries the byte-exact pair under the
# golden keys; the masked marker is the same non-reversible last-4 shape the
# house uses for every operator-facing mention of an id (reg._mask_location
# — the find_legacy.mask_id marker shape).
GOLDEN_TITLE = "The Ledger Cannot Say"
GOLDEN_SUBTITLE = "A Chapter in Two Books"
GOLDEN_ID_MARKER = reg._mask_location("ttl_golden_sel")

# The one af_code the golden payload certifies — the named ok surface a
# machine consumer reads (the sibling builder's ok surface carries the same
# code; the two can never drift apart).
GOLDEN_AF_CODE = "TITLE-SELECT"
REFUSED_AF_CODE = "TITLE-SELECT-REFUSED"


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the
    title-select law is inconsistent with the golden selection state, so NO
    fixture is shipped — a wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing law is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _is_blank(value) -> bool:
    return not isinstance(value, str) or not value.strip()


def _contract_pair(payload: dict) -> dict:
    """The title/subtitle pair of a selection payload, fail-closed. A
    selection without BOTH "title" and "subtitle" keys is a malformed
    payload (never a pass) — the lock is a PAIR, never a title-only stamp
    (the tier-1 lock check reads both keys and a blank subtitle fails the
    lock check)."""
    out = {}
    for field in TITLE_FIELDS:
        value = payload.get(field)
        if not isinstance(value, str):
            raise FixtureError(
                "the selection carries no %r field — a malformed selection "
                "is never a pass; refusing to certify the golden title-select "
                "state (the lock is a PAIR, %s, never a title-only stamp)."
                % (field, ", ".join(TITLE_FIELDS)))
        out[field] = value
    return out


def _contract_exact(pair: dict) -> None:
    """The byte-exact law, fail-closed: the selection's title and subtitle
    must BYTE-EQUAL the golden pair. A blank or drifted title/subtitle is
    exactly the shape the golden state must REFUSE — the lock is stamped
    one-way and byte-exact, so a drift is indistinguishable from a blank and
    BOTH refuse fail-closed."""
    if pair[TITLE_FIELD] != GOLDEN_TITLE:
        raise FixtureError(
            "the selection's title is not byte-exact — the golden title-"
            "select state requires the title %r exactly; a drifted title is "
            "indistinguishable from a blank one and BOTH refuse fail-closed "
            "(the one-way lock is byte-exact, never a similarity match)."
            % GOLDEN_TITLE)
    if pair[SUBTITLE_FIELD] != GOLDEN_SUBTITLE:
        raise FixtureError(
            "the selection's subtitle is not byte-exact — the golden "
            "title-select state requires the subtitle %r exactly; a drifted "
            "subtitle is indistinguishable from a blank one and BOTH refuse "
            "fail-closed (the lock is a PAIR, never a title-only stamp)."
            % GOLDEN_SUBTITLE)


def _contract_key(payload: dict) -> str:
    """The KEYING LAW, fail-closed: the participant row the selection stamps
    is keyed by the composite participant_key (contact_id::anthology_id),
    read through state.participant_key — a payload carrying a different key
    stamps a DIFFERENT row, never the golden one."""
    key = payload.get("participant_key")
    if not isinstance(key, str) or not key.strip():
        raise FixtureError(
            "the selection carries no participant_key — the golden title-"
            "select state is keyed under the KEYING LAW (contact_id::"
            "anthology_id); a keyless selection is a refusal, never a pass.")
    return key


def _contract_one_way(payload: dict) -> None:
    """The one-way lock law, fail-closed: the golden selection certifies
    lock_one_way TRUE (the engine stamps the TITLE LOCK one-way, and a
    different title/subtitle is an ILLEGAL transition). A payload that
    carries lock_one_way False would certify a relockable lock — a refusal,
    never a pass."""
    if payload.get("lock_one_way") is not TITLE_LOCK_ONE_WAY:
        raise FixtureError(
            "the selection does not certify the one-way lock — the golden "
            "title-select state is stamped TITLE LOCK, one-way (a change "
            "requires a producer exception); a relockable lock is never "
            "certified here.")


def _contract_door(payload: dict) -> str:
    """The door law, fail-closed: the selection carries a door provenance
    from the closed vocabulary (token door "nudge_link" — the participant's
    own door — or board door "dashboard", which NEVER releases for a
    select). An unknown door is a refusal, never a pass."""
    door = payload.get("door")
    if not isinstance(door, str) or door not in SELECT_DOORS:
        raise FixtureError(
            "the selection carries an unknown door — the select action is "
            "presented on the fixed doors %s (the board door never releases "
            "for a select); refusing to certify a door outside the "
            "vocabulary." % ", ".join(SELECT_DOORS))
    return door


# ---------------------------------------------------------------------------
# The golden builder — fail-closed, deterministic, never a live id.
# ---------------------------------------------------------------------------
def golden_title() -> dict:
    """The canonical title-select record: the byte-exact locked pair under
    the golden keys, the KEYING LAW participant key (synthetic contact /
    anthology markers only), the masked id marker (the non-reversible last-4
    shape every operator-facing mention of an id carries — the full synthetic
    marker rides inside the JSON payload a machine consumer reads), and the
    one-way lock truth. Returns a deep copy; mutating it never touches the
    internal canonical payload (which itself is mappingproxy-frozen)."""
    return copy.deepcopy({
        TITLE_FIELD: GOLDEN_TITLE,
        SUBTITLE_FIELD: GOLDEN_SUBTITLE,
        "participant_key": GOLDEN_SUBJECT_KEY,
        "id_masked": GOLDEN_ID_MARKER,
        "lock_one_way": TITLE_LOCK_ONE_WAY,
    })


def golden_title_payload() -> dict:
    """The canonical working/title.json surface: {"title": ..., "subtitle":
    ...} — the shape the S3 runner writes to working/title.json
    (stage_s3_title.WORKING_FILE) and the tier-1 title-lock check reads
    (qc-tier1-anthology.py check 2, byte-exact on both keys). A deep copy;
    callers may mutate it."""
    return {
        TITLE_FIELD: GOLDEN_TITLE,
        SUBTITLE_FIELD: GOLDEN_SUBTITLE,
    }


def golden_select_payload(*, door: str = DOOR_TOKEN) -> dict:
    """The canonical select surface: the shape the U08/U09 builder consumes
    — {"gate": "s3_selection", "action": "select", "decision": "approve",
    "door": <provenance>, "participant_key": <KEYING LAW>,
    "title": <byte-exact>, "subtitle": <byte-exact>, "id_masked":
    <last-4 marker>, "lock_one_way": true}. The default door is the token
    door (nudge_link — the participant's own door); the board door
    (dashboard) is carried the same way and NEVER releases anything for a
    select. A deep copy; callers may mutate it."""
    if door not in SELECT_DOORS:
        raise FixtureError(
            "cannot build a golden select payload on unknown door %r — the "
            "select action is presented on the fixed doors %s."
            % (door, ", ".join(SELECT_DOORS)))
    return {
        "gate": SELECT_GATE,
        "action": SELECT_ACTION,
        "decision": SELECT_DECISION,
        "door": door,
        "participant_key": GOLDEN_SUBJECT_KEY,
        TITLE_FIELD: GOLDEN_TITLE,
        SUBTITLE_FIELD: GOLDEN_SUBTITLE,
        "id_masked": GOLDEN_ID_MARKER,
        "lock_one_way": TITLE_LOCK_ONE_WAY,
    }


# ---------------------------------------------------------------------------
# The golden fixture itself — derived ONCE at import, deep-frozen. The record
# is a MappingProxyType and every container is a tuple, so NO caller can
# mutate the canonical payload through the module's public surface — the
# self-test proves it. Consumers that need a mutable payload call
# golden_title() / golden_title_payload() / golden_select_payload()
# (deep copies).
# ---------------------------------------------------------------------------
def _build_golden() -> tuple:
    from types import MappingProxyType
    return (MappingProxyType(dict(golden_title())),)


# The canonical title-select record: deep-frozen (a mappingproxy — immutable
# through every route).
GOLDEN_TITLE_RECORD = _build_golden()[0]


# ---------------------------------------------------------------------------
# Fail-closed title-select gate — the offline gate the self-test and
# `payload` both ride on. A blank or drifted pair, a relockable lock, or a
# drifted surface is REFUSED with exit 5, never tolerated.
# ---------------------------------------------------------------------------
def _judge(payload: dict, *, out) -> int:
    """The fail-closed title-select gate. Returns the exit code: 0 PASS, 5
    REFUSED (mismatch family). Emits the ONE JSON report object on stdout;
    human notes go to out (stderr)."""
    detail = ""
    ok = False
    found = {"title": None, "subtitle": None, "participant_key": None,
             "door": None}
    try:
        pair = _contract_pair(payload)
        _contract_exact(pair)
        key = _contract_key(payload)
        _contract_one_way(payload)
        door = _contract_door(payload)
    except FixtureError as exc:
        detail = str(exc)
    else:
        if key != GOLDEN_SUBJECT_KEY:
            detail = ("the selection keys %r, but the golden title-select "
                      "state is keyed %r under the KEYING LAW (contact_id::"
                      "anthology_id) — a selection that stamps a different "
                      "participant row is never a golden pass."
                      % (key, GOLDEN_SUBJECT_KEY))
        else:
            found["title"] = pair[TITLE_FIELD]
            found["subtitle"] = pair[SUBTITLE_FIELD]
            found["participant_key"] = key
            found["door"] = door
            ok = True
            detail = ("the byte-exact locked pair (%r / %r) under the KEYING "
                      "LAW key %s, lock stamped ONE-WAY, carried on the %r "
                      "door — the golden title-select state holds (the "
                      "select action REQUIRES the title; the subtitle is "
                      "optional in the select; the board door never releases "
                      "for a select)"
                      % (pair[TITLE_FIELD], pair[SUBTITLE_FIELD], key, door))
    print(json.dumps({
        "contract": FIXTURE_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "REFUSED",
        "expected": {
            "gate": SELECT_GATE,
            "action": SELECT_ACTION,
            "decision": SELECT_DECISION,
            "title_required": SELECT_TITLE_REQUIRED,
            "subtitle_optional": SELECT_SUBTITLE_OPTIONAL,
            "lock_one_way": TITLE_LOCK_ONE_WAY,
        },
        "found": found,
        "detail": detail,
    }, indent=2, sort_keys=True))
    if not ok:
        out.write("[golden-title] REFUSED: %s\n" % detail)
        return EX_MISMATCH
    return EX_OK


def payload(candidate: dict = None, *, out=None) -> int:
    """Judge a title-select payload against the golden title-select contract.

    READ-ONLY: asserts the U08/U09 title-select law — the byte-exact locked
    pair (title AND subtitle, under the golden keys), the KEYING LAW
    participant key, the one-way lock truth, and a door from the closed
    vocabulary. A blank or drifted title, a blank or drifted subtitle, a
    non-golden participant key, a lock not certified one-way, an unknown
    door, a malformed payload (a missing title/subtitle key, a non-string
    value), a non-object candidate, or a credential-shaped value is a
    FAIL-CLOSED exit 5, never a blind pass. With no candidate the GOLDEN
    selection itself is judged — the dispatcher's offline gate. Emits the
    ONE JSON report object on stdout; human notes go to out (stderr)."""
    out = out or sys.stderr
    if candidate is None:
        candidate = golden_select_payload()
    if not isinstance(candidate, dict):
        detail = "the candidate is not a JSON object — malformed selection, " \
                 "never a pass (fail-closed)"
        print(json.dumps({
            "contract": FIXTURE_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "expected": {
                "gate": SELECT_GATE,
                "action": SELECT_ACTION,
                "decision": SELECT_DECISION,
                "title_required": SELECT_TITLE_REQUIRED,
                "subtitle_optional": SELECT_SUBTITLE_OPTIONAL,
                "lock_one_way": TITLE_LOCK_ONE_WAY,
            },
            "found": None,
            "detail": detail,
        }, indent=2, sort_keys=True))
        out.write("[golden-title] REFUSED: %s\n" % detail)
        return EX_MISMATCH
    return _judge(candidate, out=out)


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
        sys.stderr.write("[golden-title] SELF-TEST FAILED "
                         "(AF-AE-GOLDENTITLE-* family): %s\n" % exc)
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

    # ---- the canonical fixture: title-select record deep-frozen ------------
    assert isinstance(GOLDEN_TITLE_RECORD, MappingProxyType), \
        "GOLDEN_TITLE_RECORD must be mappingproxy-frozen"
    assert SELECT_GATE == "s3_selection", \
        "the select gate must be s3_selection (the participant title-select gate)"
    assert SELECT_ACTION == "select" and SELECT_DECISION == "approve", \
        "the select action maps to the sole-writer decision 'approve'"
    assert SELECT_TITLE_REQUIRED is True, \
        "the select action REQUIRES the title (the one required extra field)"
    assert SELECT_SUBTITLE_OPTIONAL is True, \
        "the subtitle is optional in the select action"
    assert TITLE_LOCK_ONE_WAY is True, \
        "the TITLE LOCK is one-way (byte-exact; a change requires a producer " \
        "exception)"
    assert SELECT_DOORS == ("nudge_link", "dashboard"), \
        "the select action is presented on exactly the token door and the " \
        "board door"
    assert TITLE_FIELDS == ("title", "subtitle"), \
        "the lock is a PAIR (title and subtitle), never a title-only stamp"
    assert GOLDEN_ID_MARKER == "..._sel", \
        "the masked id marker must be the non-reversible last-4 shape"
    for field in TITLE_FIELDS:
        assert field in GOLDEN_TITLE_RECORD, \
            "the canonical record lost its %r field" % field
    assert GOLDEN_TITLE_RECORD[TITLE_FIELD] == GOLDEN_TITLE == \
        "The Ledger Cannot Say", \
        "the canonical locked title drifted from the golden pair"
    assert GOLDEN_TITLE_RECORD[SUBTITLE_FIELD] == GOLDEN_SUBTITLE == \
        "A Chapter in Two Books", \
        "the canonical locked subtitle drifted from the golden pair"
    assert GOLDEN_TITLE_RECORD["participant_key"] == "cnt_golden::anth_golden", \
        "the canonical record must key the selection under the KEYING LAW"
    assert GOLDEN_TITLE_RECORD["id_masked"].startswith("..."), \
        "the canonical record must mask the id marker to its last-4 shape"
    assert GOLDEN_TITLE_RECORD["lock_one_way"] is True, \
        "the canonical record must certify the one-way lock"

    # ---- the payload surfaces cover the law on every shape ------------------
    rec = golden_title()
    assert rec[TITLE_FIELD] == GOLDEN_TITLE and \
        rec[SUBTITLE_FIELD] == GOLDEN_SUBTITLE, \
        "the canonical record drifted from the golden contract"
    wf = golden_title_payload()
    assert isinstance(wf, dict) and wf[TITLE_FIELD] == GOLDEN_TITLE and \
        wf[SUBTITLE_FIELD] == GOLDEN_SUBTITLE, \
        "the working/title.json surface must carry the byte-exact locked pair"
    sel = golden_select_payload()
    assert sel["gate"] == "s3_selection" and sel["action"] == "select" and \
        sel["decision"] == "approve", \
        "the select surface must name the gate, the action, and the decision"
    assert sel["door"] == "nudge_link", \
        "the default select surface must ride the token door"
    assert sel["participant_key"] == "cnt_golden::anth_golden", \
        "the select surface must key the selection under the KEYING LAW"
    assert sel["lock_one_way"] is True
    sel_board = golden_select_payload(door=DOOR_BOARD)
    assert sel_board["door"] == "dashboard", \
        "the board-door select surface must carry the dashboard provenance"
    try:
        golden_select_payload(door="some_other_door")
        raise AssertionError("an unknown door was NOT refused")
    except FixtureError:
        pass

    # ---- the canonical fixture can never be mutated through the surface -----
    before = GOLDEN_TITLE_RECORD[TITLE_FIELD]

    def _try_rebind():  # subscript assignment on a mappingproxy -> TypeError
        GOLDEN_TITLE_RECORD[TITLE_FIELD] = "Mutated"  # noqa: B034 -- deliberately attempted

    try:
        _try_rebind()
        raise AssertionError("the canonical fixture must be immutable")
    except TypeError:
        pass
    assert GOLDEN_TITLE_RECORD[TITLE_FIELD] == before, \
        "the canonical fixture changed during the self-test"
    # golden_title() returns a deep copy: mutating it never touches the canon.
    copy_ = golden_title()
    copy_[TITLE_FIELD] = "Mutated"
    assert GOLDEN_TITLE_RECORD[TITLE_FIELD] == before, \
        "the returned copy must not alias the canonical payload"

    # ---- attack fixtures: every drift REFUSED, never shipped ----------------
    # 1. a BLANK title -> the lock cannot be certified byte-exact
    blank_title = dict(golden_select_payload())
    blank_title[TITLE_FIELD] = ""
    try:
        _contract_exact(_contract_pair(blank_title))
        raise AssertionError("a blank title was NOT refused")
    except FixtureError:
        pass
    # 2. a DRIFTED title -> the lock cannot be certified byte-exact
    drifted_title = dict(golden_select_payload())
    drifted_title[TITLE_FIELD] = "The Ledger Can Say"
    try:
        _contract_exact(_contract_pair(drifted_title))
        raise AssertionError("a drifted title was NOT refused")
    except FixtureError:
        pass
    # 3. a BLANK subtitle -> the lock is a PAIR, never a title-only stamp
    blank_sub = dict(golden_select_payload())
    blank_sub[SUBTITLE_FIELD] = "  "
    try:
        _contract_exact(_contract_pair(blank_sub))
        raise AssertionError("a blank subtitle was NOT refused")
    except FixtureError:
        pass
    # 4. a payload with NO subtitle field -> the lock is a PAIR (the tier-1
    #    lock check reads both keys; a missing key is a malformed payload)
    try:
        _contract_pair({"title": GOLDEN_TITLE})
        raise AssertionError("a selection without the subtitle field was NOT "
                             "refused")
    except FixtureError:
        pass
    # 5. a relockable lock -> the TITLE LOCK is one-way, never relockable
    relockable = dict(golden_select_payload())
    relockable["lock_one_way"] = False
    try:
        _contract_one_way(relockable)
        raise AssertionError("a relockable lock was NOT refused")
    except FixtureError:
        pass
    # 6. an unknown door -> the door vocabulary is closed
    bad_door = dict(golden_select_payload())
    bad_door["door"] = "some_other_door"
    try:
        _contract_door(bad_door)
        raise AssertionError("an unknown door was NOT refused")
    except FixtureError:
        pass

    # ---- the payload gate: golden exits 0, every drift exits 5 --------------
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload()
    assert rc == EX_OK, "payload on the golden selection must exit 0, " \
                        "got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["contract"] == FIXTURE_CONTRACT
    assert parsed["expected"]["gate"] == "s3_selection"
    assert parsed["expected"]["title_required"] is True
    assert parsed["expected"]["subtitle_optional"] is True
    assert parsed["expected"]["lock_one_way"] is True
    assert parsed["found"]["title"] == GOLDEN_TITLE
    assert parsed["found"]["subtitle"] == GOLDEN_SUBTITLE
    assert parsed["found"]["participant_key"] == "cnt_golden::anth_golden"
    assert parsed["found"]["door"] == "nudge_link"
    # a drifted title -> REFUSED exit 5
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = payload(dict(golden_select_payload(),
                           **{TITLE_FIELD: "The Ledger Can Say"}))
    assert rc2 == EX_MISMATCH, \
        "a drifted title must exit 5, got %s" % rc2
    assert json.loads(buf2.getvalue())["verdict"] == "REFUSED"
    # a blank title -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(dict(golden_select_payload(),
                            **{TITLE_FIELD: ""})) == EX_MISMATCH, \
            "a blank title must exit 5"
    # a blank subtitle -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(dict(golden_select_payload(),
                            **{SUBTITLE_FIELD: "  "})) == EX_MISMATCH, \
            "a blank subtitle must exit 5"
    # a drifted subtitle -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(dict(golden_select_payload(),
                            **{SUBTITLE_FIELD: "A Chapter in One Book"})) \
            == EX_MISMATCH, "a drifted subtitle must exit 5"
    # a missing subtitle field -> REFUSED exit 5 (never a title-only pass)
    with contextlib.redirect_stdout(io.StringIO()):
        stripped = dict(golden_select_payload())
        del stripped[SUBTITLE_FIELD]
        assert payload(stripped) == EX_MISMATCH, \
            "a selection without the subtitle field must exit 5"
    # a different participant key -> REFUSED exit 5 (the KEYING LAW)
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(dict(golden_select_payload(),
                            participant_key="cnt_other::anth_other")) \
            == EX_MISMATCH, "a non-golden participant key must exit 5"
    # a relockable lock -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(dict(golden_select_payload(),
                            lock_one_way=False)) == EX_MISMATCH, \
            "a relockable lock must exit 5"
    # an unknown door -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(dict(golden_select_payload(),
                            door="some_other_door")) == EX_MISMATCH, \
            "an unknown door must exit 5"
    # a malformed candidate -> REFUSED exit 5 (never a pass)
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"no_title_here": True}) == EX_MISMATCH, \
            "a malformed candidate must exit 5"
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload("not-an-object") == EX_MISMATCH, \
            "a non-object candidate must exit 5"

    # ---- the BROWSER UA law is pinned (CF 1010) ------------------------------
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), \
        "CAF_BROWSER_UA must be a browser User-Agent (CF 1010)"

    # ---- never-print: no credential-shaped string on any surface ------------
    all_text = buf.getvalue() + buf2.getvalue()
    for token in ("pit-", "Bearer "):
        assert token not in all_text, \
            "surface leak: %r must never appear" % token

    dev.write("golden_title self-test: OK (title-select law pinned: the "
              "s3_selection select action REQUIRES the title (%r) and the "
              "subtitle is optional in the select, but the LOCK is a PAIR — "
              "the byte-exact locked pair %r / %r is certified under the "
              "KEYING LAW key %s, stamped ONE-WAY, carried on the fixed "
              "doors %s (the board door never releases for a select); "
              "canonical mappingproxy-frozen immutability + deep-copy "
              "surface; 6 attack fixtures refused (blank title / drifted "
              "title / blank subtitle / missing subtitle field / relockable "
              "lock / unknown door); payload gate exits 0 on the golden "
              "selection, 5 on every drift; BROWSER UA pinned; never-print)\n"
              % (TITLE_FIELD, GOLDEN_TITLE, GOLDEN_SUBTITLE,
                 GOLDEN_SUBJECT_KEY, ", ".join(SELECT_DOORS)))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="golden_title.py",
        description="Golden title-select fixture for the U08/U09 self-tests "
                    "(Skill 59): the canonical S3 title-selection payload — "
                    "the byte-exact locked title/subtitle pair under the "
                    "KEYING LAW, one-way lock stamped, both doors — "
                    "fail-closed, offline, never prints a token.")
    ap.add_argument("cmd", nargs="?", choices=["payload", "plan", "self-test"],
                    default="payload")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the U07 siblings use).
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
            # title-select surface — the byte-exact locked pair, the KEYING
            # LAW key, the one-way lock, the fixed doors.
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "gate": SELECT_GATE,
                "action": SELECT_ACTION,
                "decision": SELECT_DECISION,
                "title_required": SELECT_TITLE_REQUIRED,
                "subtitle_optional": SELECT_SUBTITLE_OPTIONAL,
                "title": GOLDEN_TITLE,
                "subtitle": GOLDEN_SUBTITLE,
                "participant_key": GOLDEN_SUBJECT_KEY,
                "id_masked": GOLDEN_ID_MARKER,
                "lock_one_way": TITLE_LOCK_ONE_WAY,
                "doors": list(SELECT_DOORS),
                "note": "offline plan only — synthetic fixture ids and a "
                        "fabricated pair, no network, no credential needed; "
                        "a LIVE selection write must ride the house clients "
                        "(CAF_BROWSER_UA on every request — CF 1010 law); "
                        "any WRITE ACTION is Trevor-gated (--execute) — the "
                        "gate lives in the dispatcher, never in a fixture",
            }, indent=2, sort_keys=True))
            return EX_OK
        # payload: the candidate selection arrives on stdin, read from NO
        # network (the live selection surface is the sibling builder, which
        # rides the house rail clients and their CAF_BROWSER_UA — this
        # fixture never touches the wire). The candidate is a
        # {"title": ..., "subtitle": ..., "participant_key": ...,
        # "lock_one_way": ..., "door": ...} select payload object; with
        # none, the golden selection itself is judged.
        try:
            candidate = json.load(sys.stdin)
        except ValueError as exc:
            sys.stderr.write("[golden-title] the selection on stdin is not "
                             "valid JSON: %s\n" % exc)
            return EX_MISMATCH
        return payload(candidate)
    except FixtureError as exc:
        sys.stderr.write("[golden-title] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[golden-title] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
