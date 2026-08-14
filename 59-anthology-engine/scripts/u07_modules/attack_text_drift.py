#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u07_modules/attack_text_drift.py
# ATTACK FIXTURE — DATA-TYPE DRIFT (TEXT instead of LARGE_TEXT), MUST FAIL
# (U07 dataType law). The adversarial sibling of the engine's dataType
# contract: the canonical 38-key field inventory (the SINGLE AUTHORITY is
# config/field-map.json provisioning.fields — 36 LARGE_TEXT free-text keys +
# the two SINGLE_OPTIONS picklists (cover choice + review decision), never a
# second implementation) with
# the ONE data_type of one free-text key re-declared "TEXT" instead of the
# byte-exact "LARGE_TEXT". The "TEXT" token is exactly the drift the spec
# called out — field-map.json's data_type_choice states it in the engine's
# own words: "the earlier TEXT declaration was a repo-vs-live drift the spec
# called out (the field-map lied). TEXT was byte-for-byte verified at Wave 0
# (80 chars incl. unicode, spaces, pipe, ampersand, percent-encoding; sha256
# sent == sha256 read-back) and remains a safe subset, but LARGE_TEXT is the
# live-matching, multi-line-correct type and is now the [declared type]."
# Every dataType gate — provision-fields exact-match verify, the CI drift
# gates (qc-snapshot-contract.sh, qc-snapshot-fixture.sh), the U02 template
# live re-verify's dataType item, the snapshot fixture's own 36+2 invariant —
# MUST FAIL this attack, never a pass, and THIS module's own gates MUST
# refuse anything that is not exactly the one-TEXT-drift shape.
#
# THE ATTACK IS DETERMINISTIC AND SINGLE-VARIABLE: the canonical field
# inventory is read ONCE from the SINGLE AUTHORITY (config/field-map.json via
# reg.FIELD_MAP_PATH — the dataType LAW surface: 38 keys total, 36 LARGE_TEXT
# + 2 SINGLE_OPTIONS, the SINGLE_OPTIONS keys are exactly the cover choice
# contact.anthology_cover_choice with its four named options and the review
# decision contact.anthology_review_decision with its two gate actions),
# checked against the dataType law, then the ONE data_type of the first
# LARGE_TEXT key (deterministic order: sorted by intended_key) is
# re-declared "TEXT" with every other field byte-for-byte preserved. The two
# SINGLE_OPTIONS rows are NOT part of the attack — they are the golden
# picklist rows, so the failure isolates the TEXT-vs-LARGE_TEXT boundary and
# nothing else.
#
# WHERE THIS SITS: scripts/u07_modules/ — an importable module under the U07
# package (pure namespace container per the u07 __init__.py: imported BY
# NAME, side-effect-free at import). It is NOT a manifest row and NOT a
# checker: it ships the ADVERSARIAL FIXTURE the self-tests of the U07
# dataType gates and their sibling checkers assert against, so the FAIL path
# is judged against the SAME surface the happy path judges against — a drift
# in the dataType law (field-map.json) breaks THIS module's self-test first
# (fail-closed: an inconsistent law is a refusal, never a blind pass).
#
# WHAT THIS OWNS:
#   1. attack_inventory(record=None) — the builder, fail-closed: the
#      canonical inventory comes from the SINGLE AUTHORITY (the committed
#      config/field-map.json, read via reg.FIELD_MAP_PATH — the dataType LAW,
#      never a second implementation) and is checked against the dataType
#      law (38 keys, 36 LARGE_TEXT + 2 SINGLE_OPTIONS, the SINGLE_OPTIONS
#      keys are the byte-exact cover choice and review decision, NO row
#      already carries TEXT), then
#      the ONE data_type of the first free-text key is re-declared TEXT; a
#      malformed inventory, an inventory that already carries TEXT (the
#      double-swap a regression would produce), or an inventory that breaks
#      any dataType invariant raises FixtureError instead of shipping a
#      wrong fixture.
#   2. verify_inventory(record, gates=None) — the JUDGE: runs a field
#      inventory through the U07 dataType law's authorities (the total-key
#      census, the 36-LARGE_TEXT + 2-SINGLE_OPTIONS dataType census, and the
#      per-key picklist laws) and exits 5 (mismatch family) on the TEXT-drift
#      attack, naming the drifted key by MASKED MARKER and the type tokens —
#      never a pass; on the golden 36+2 control it exits 0. The one place
#      this module makes the FAIL explicit: an attack fixture that PASSES any
#      dataType gate is a broken gate.
#   3. payload() / payload_true() — the FAIL-CLOSED gates. payload() ships
#      the TEXT-drift attack report (the fixture is the module's product —
#      counts and masked markers, never the raw inventory) and exits 0 only
#      when the attack is EXACTLY the one-TEXT-drift shape; any drift (a
#      second TEXT row, a drifted picklist row, a missing data_type, an
#      unparseable inventory, a conflated authority) is REFUSED with exit 5
#      (verdict REFUSED). payload_true() is the control: the TRUE canonical
#      inventory (36 LARGE_TEXT + 2 SINGLE_OPTIONS) passes exit 0 and its
#      own law checks catch a regression in the dataType authority, so the
#      self-test's pass/fail split discriminates the TEXT boundary and never
#      a broken instrument (the negative-result contract: a gate that fails
#      everything is a broken check, not a real fault).
#
# DOCTRINE (inherited from the registry / the U07 package init / the U02-U06
# attack-fixture family):
#   - Never a token printed: this module holds and resolves NO credential —
#     the fixture is pure in-memory field-inventory metadata read from the
#     committed field-map.json (never a live id, never a live workflow,
#     never a live anthology, never a credential), and every emitted surface
#     reports drifted keys by MASKED MARKER (last-4 chars, reg._mask_location
#     — the house masking helper) only, with data_type tokens (LARGE_TEXT /
#     TEXT / SINGLE_OPTIONS — type tokens, never secrets) surfaced verbatim
#     exactly as the gates' own contracts do. Nothing in this module can ever
#     echo a secret because no secret is ever read.
#   - Fail-closed: a drifted authority, an unparseable inventory, a
#     wrong-shaped payload all STOP or FAIL — never a blind pass, never a
#     fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates. It
#     ships the TEXT-drift read that MUST FAIL the dataType gate; the field
#     provisioning itself is owned by the mutation surface
#     (reg.provision_fields, create-or-verify + exact-match) and this module
#     pins the law it enforces.
#   - The GHL / Convert and Flow surface is Cloudflare-fronted: urllib's
#     default "Python-urllib/x.y" User-Agent is 403'd at the WAF edge (CF
#     error 1010) before it ever reaches the API (CAF_BROWSER_UA in
#     anthology_registry.py is the house pattern). This module itself makes
#     NO network call — it ships the offline adversarial fixture only; any
#     sibling that DOES talk to the platform must ride the house browser
#     User-Agent on every request, and the self-test pins the constant so a
#     registry regression is caught HERE first.
#
# EXIT CODE CONTRACT (house convention; mirrors the U06 attack_no_execute
# sibling and the U05 attack_wrong_form / attack_unscoped family):
#   0  verified success — the golden 36+2 control inventory is internally
#      consistent and byte-exact to the dataType law; also self-test / plan
#      OK
#   1  unexpected error (malformed input / no inventory to judge)
#   4  self-test FAILED (AF-AE-ATTACKTEXTDRIFT-* family, enforced violation)
#   5  mismatch — the TEXT-drift attack inventory is FAIL (verify_inventory)
#      or REFUSED (payload under drift), never a blind pass
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# u06/u05 attack siblings: sys.path.insert to scripts/ then `import
# anthology_registry as reg` — the registry owns the exit-code contract, the
# browser-UA wiring, the masking helper, and the path to the SINGLE
# AUTHORITY (config/field-map.json). The dataType LAW is never hardcoded: it
# is read from field-map.json at import (fail-fast — a drifted authority
# breaks the import of the fixture itself).
# =============================================================================
"""attack_text_drift.py — the TEXT-instead-of-LARGE_TEXT dataType attack
fixture that must FAIL.

The adversarial sibling of the engine's dataType law: the canonical 38-key
field inventory read from config/field-map.json (the single authority) with
the ONE data_type of one free-text key re-declared "TEXT" — the exact
repo-vs-live drift the spec called out — every dataType gate must refuse it
while this module's own gates refuse anything that is not exactly that shape
(exit 5).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to the U05/U06
# attack siblings): the registry owns the exit-code contract, the browser-UA
# wiring, the masking helper, and the path to the SINGLE AUTHORITY
# (config/field-map.json) — the module reuses them, never re-implements.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The one fixed report contract.
ATTACK_CONTRACT = "anthology-engine-attack-text-drift"

# The dataType law tokens — the drift direction and the live-matching
# direction, pinned against the authority in the self-test (if the authority
# ever stops declaring LARGE_TEXT the fixture's self-test breaks first,
# fail-closed). "TEXT" is exactly the earlier repo-vs-live declaration the
# spec called out (the field-map lied); "LARGE_TEXT" is the live-matching,
# multi-line-correct type the law now requires.
ATTACK_DATATYPE = "TEXT"              # the drifted type the attack declares
GOLDEN_DATATYPE = "LARGE_TEXT"        # the byte-exact live-matching type
OPTIONS_DATATYPE = "SINGLE_OPTIONS"   # the cover choice's data_type

# The dataType law's census — the exact counts every dataType gate must see:
# 38 total keys, 36 LARGE_TEXT free-text keys + the two SINGLE_OPTIONS
# choices (the cover choice and the review decision — the U15-absorbed
# 36+2 invariant, formerly the 27+1 invariant before the 2026-08-13
# absorb). Read from the authority at import and pinned here for the law
# checks (never a second implementation of the inventory itself).
TOTAL_KEYS = 38
COUNT_LARGE_TEXT = 36
COUNT_SINGLE_OPTIONS = 2

# The SINGLE_OPTIONS law: the TWO SINGLE_OPTIONS keys are byte-exact the
# cover choice (with its four named options Signature / Bold Editorial /
# Fine Art / Pure Type — the PRD locked choice set) and the review
# decision (with its two gate_engine s5_gate actions). Neither is part of
# the attack — both are golden rows.
COVER_CHOICE_KEY = "contact.anthology_cover_choice"
COVER_CHOICE_OPTIONS = ("Signature", "Bold Editorial", "Fine Art", "Pure Type")
DECISION_KEY = "contact.anthology_review_decision"
DECISION_OPTIONS = ("approve_as_is", "request_rewrite_with_notes")


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the dataType
    authority or the inventory record drifted from the law, so NO fixture is
    shipped — a wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# The SINGLE AUTHORITY — the committed config/field-map.json, read ONCE.
# ---------------------------------------------------------------------------
def _load_field_inventory() -> list:
    """The dataType LAW surface: the canonical field inventory read from the
    SINGLE AUTHORITY (config/field-map.json provisioning.fields via
    reg.FIELD_MAP_PATH — never a second implementation, never a hardcoded
    copy). Fail-closed: a missing file, an unreadable file, a missing
    provisioning.fields array, or a non-list inventory is a refusal — the
    fixture cannot ship without the law."""
    path = reg.FIELD_MAP_PATH
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        raise FixtureError(
            "the dataType authority %s cannot be read: %s — refusing to "
            "build an attack without the law (never fabricated)."
            % (path, exc)) from exc
    inventory = (doc or {}).get("provisioning", {}).get("fields")
    if not isinstance(inventory, list) or not inventory:
        raise FixtureError(
            "%s carries no provisioning.fields inventory — the dataType "
            "authority drifted; refusing to build an attack without the "
            "law." % path)
    return inventory


def _check_data_type_law(inventory: list) -> str:
    """The dataType LAW over a field inventory, as a human reason string (""
    when the inventory satisfies the law): 38 keys total, 36 LARGE_TEXT + the
    two SINGLE_OPTIONS picklists (cover choice + review decision), NO TEXT
    anywhere, every row a mapping with a non-empty intended_key /
    create_name / data_type. Fail-closed: a malformed row is drift, never a
    pass. The counts come from the law constants pinned against the
    authority at import (never a second implementation of the inventory
    itself)."""
    if not isinstance(inventory, list):
        return "the inventory is %r, not a list — unparseable" \
            % type(inventory).__name__
    if len(inventory) != TOTAL_KEYS:
        return "the inventory carries %d keys, not the law's %d" \
            % (len(inventory), TOTAL_KEYS)
    counts = {}
    for row in inventory:
        if not isinstance(row, dict):
            return "a census row is %r, not a mapping — unparseable" \
                % type(row).__name__
        for key in ("intended_key", "create_name", "data_type"):
            value = row.get(key)
            if not isinstance(value, str) or not value.strip():
                return "a census row carries no non-empty %r — drift" % key
        counts[row["data_type"]] = counts.get(row["data_type"], 0) + 1
    if counts.get(GOLDEN_DATATYPE) != COUNT_LARGE_TEXT:
        return "the inventory carries %d LARGE_TEXT keys, not the law's %d" \
            % (counts.get(GOLDEN_DATATYPE, 0), COUNT_LARGE_TEXT)
    if counts.get(OPTIONS_DATATYPE) != COUNT_SINGLE_OPTIONS:
        return ("the inventory carries %d SINGLE_OPTIONS keys, not the law's "
                "%d" % (counts.get(OPTIONS_DATATYPE, 0),
                        COUNT_SINGLE_OPTIONS))
    if counts.get(ATTACK_DATATYPE):
        return ("the inventory already carries %d TEXT key(s) — the drift "
                "the law bans; never a pass"
                % counts[ATTACK_DATATYPE])
    extra = sorted(set(counts) - {GOLDEN_DATATYPE, OPTIONS_DATATYPE})
    if extra:
        return "the inventory carries foreign data_type(s) %r — drift" % extra
    return ""


def _check_single_options_law(inventory: list) -> str:
    """The SINGLE_OPTIONS law: the TWO SINGLE_OPTIONS rows are byte-exact the
    cover choice (contact.anthology_cover_choice, the four named PRD
    choices) and the review decision (contact.anthology_review_decision, the
    two gate_engine s5_gate actions — U15-absorbed 2026-08-13). Fail-closed:
    any other SINGLE_OPTIONS key, a duplicated key, or drifted options is a
    refusal, never a pass. Both rows are golden — never part of the attack."""
    found = {}
    for row in inventory:
        if row.get("data_type") == OPTIONS_DATATYPE:
            key = row.get("intended_key")
            if key not in (COVER_CHOICE_KEY, DECISION_KEY):
                return ("a SINGLE_OPTIONS row is %r, not one of the two "
                        "byte-exact choices %r — the authority drifted"
                        % (key, (COVER_CHOICE_KEY, DECISION_KEY)))
            if key in found:
                return ("the SINGLE_OPTIONS key %r appears twice — the "
                        "authority drifted" % key)
            found[key] = tuple(row.get("options") or ())
    if COVER_CHOICE_KEY not in found:
        return "the cover-choice SINGLE_OPTIONS row is missing"
    if found[COVER_CHOICE_KEY] != COVER_CHOICE_OPTIONS:
        return ("the cover choice options %r are not the byte-exact four "
                "PRD choices %r — the authority drifted"
                % (found[COVER_CHOICE_KEY], COVER_CHOICE_OPTIONS))
    if DECISION_KEY not in found:
        return "the review-decision SINGLE_OPTIONS row is missing"
    if found[DECISION_KEY] != DECISION_OPTIONS:
        return ("the decision options %r are not the byte-exact two "
                "gate_engine s5_gate actions %r — the authority drifted"
                % (found[DECISION_KEY], DECISION_OPTIONS))
    return ""


def _drifted_key_markers(inventory: list) -> list:
    """The MASKED-MARKER projection of every TEXT-declared row of an
    inventory: the create_name reduced to its last-4 marker (the house
    masked-marker discipline — never a full key on any surface; intended_key
    never rides a surface). Fail-closed: a non-mapping row, or a TEXT row
    with no non-empty create_name, refuses."""
    markers = []
    for row in inventory:
        if isinstance(row, dict) and row.get("data_type") == ATTACK_DATATYPE:
            name = row.get("create_name")
            if not isinstance(name, str) or not name.strip():
                raise FixtureError(
                    "a TEXT row carries no non-empty create_name — refusing "
                    "to mask an unparseable census.")
            markers.append(reg._mask_location(name))
    return sorted(markers)


# ---------------------------------------------------------------------------
# The attack builder — fail-closed, deterministic, canonical minus the type.
# ---------------------------------------------------------------------------
def _first_free_text_key(inventory: list) -> str:
    """The deterministic drift target: the first LARGE_TEXT row's create_name
    in sorted-by-intended_key order — deterministic across runs and across
    inventory reorderings, so the attack is the same attack every time.
    Fail-closed: an inventory with no LARGE_TEXT row refuses (the law would
    be broken)."""
    names = sorted(row["intended_key"] for row in inventory
                   if row.get("data_type") == GOLDEN_DATATYPE)
    if not names:
        raise FixtureError(
            "the canonical inventory carries no LARGE_TEXT key — the dataType "
            "authority drifted; refusing to ship an attack payload.")
    for row in inventory:
        if row.get("intended_key") == names[0]:
            return row["create_name"]
    raise FixtureError(
        "the first LARGE_TEXT key %r has no create_name row — the dataType "
        "authority drifted; refusing." % names[0])


def attack_inventory(record: dict = None) -> dict:
    """Build the attack record: the canonical field inventory comes from the
    SINGLE AUTHORITY (config/field-map.json — the dataType LAW, never a
    second implementation), is checked against the dataType law (38 keys, 36
    LARGE_TEXT + 2 SINGLE_OPTIONS, the SINGLE_OPTIONS rows are the byte-exact
    cover choice and review decision, NO row already carries TEXT), then the
    ONE data_type of the
    first LARGE_TEXT key is re-declared TEXT — every other field preserved
    byte-for-byte. Any drift raises FixtureError — a wrong fixture is never
    shipped."""
    if record is not None and not isinstance(record, dict):
        raise FixtureError(
            "record is %r, not a mapping with a 'fields' list — refusing to "
            "build an attack from an unparseable surface (never fabricated)."
            % type(record).__name__)
    base = dict(record) if record is not None else None
    inventory = base.get("fields") if base is not None else None
    if inventory is None:
        inventory = _load_field_inventory()
    if not isinstance(inventory, list):
        raise FixtureError(
            "record is %r, not a mapping with a 'fields' list — refusing to "
            "build an attack from an unparseable surface (never fabricated)."
            % type(inventory).__name__)
    law = _check_data_type_law(inventory)
    if law:
        raise FixtureError(
            "the canonical inventory breaks the dataType law (%s) — the "
            "authority drifted; refusing to ship an attack payload." % law)
    cover = _check_single_options_law(inventory)
    if cover:
        raise FixtureError(
            "the canonical inventory breaks the SINGLE_OPTIONS law (%s) — the "
            "authority drifted; refusing to ship an attack payload." % cover)
    drift = _first_free_text_key(inventory)
    out = []
    for row in inventory:
        item = dict(row)
        if item.get("create_name") == drift:
            if item.get("data_type") == ATTACK_DATATYPE:
                raise FixtureError(
                    "the drift target already carries TEXT (the double-swap "
                    "a regression would produce) — refusing to ship a "
                    "double-swap attack.")
            item["data_type"] = ATTACK_DATATYPE
        out.append(item)
    return {
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "source": "config/field-map.json",
        "drift_key_marker": reg._mask_location(drift),
        "drift_key_create_name": drift,
        "drifted": ATTACK_DATATYPE,
        "golden": GOLDEN_DATATYPE,
        "fields": out,
    }


# The canonical attack record, derived ONCE at import from the dataType
# authority — fail-fast: a drifted authority breaks the import of the fixture
# itself, so a checker that imports this module by name catches the drift
# first.
ATTACK_RECORD = attack_inventory()

# The golden control record — the canonical inventory under the dataType
# law's own counts, derived from the SAME authority: the pass side of the
# pass/fail split (a gate that fails everything is a broken instrument).
GOLDEN_RECORD = {
    "contract": ATTACK_CONTRACT + "-golden",
    "schema_version": 1,
    "source": "config/field-map.json",
    "fields": _load_field_inventory(),
}


# ---------------------------------------------------------------------------
# The judge — verify_inventory: the ONE surface that makes the FAIL explicit.
# ---------------------------------------------------------------------------
def _verify_one_authority(authority_check, record: dict) -> tuple:
    """Run ONE dataType authority over ITS canonical surface and return
    (ok, reason). The authority is the law owner's own check — never a
    re-implementation — and it is side-effect-free by contract."""
    try:
        ok, reason = authority_check(record)
    except FixtureError as exc:
        return False, str(exc)
    return bool(ok), str(reason or "unknown")


def _authority_total_keys(record: dict) -> tuple:
    """The total-key census: the inventory carries EXACTLY the law's 38 keys.
    A record with any other count is drift — the census a drifted snapshot
    would produce. The count alone cannot pass the TEXT read — the drift
    already failed the law."""
    fields = (record or {}).get("fields")
    if not isinstance(fields, list):
        return False, "the record carries no 'fields' list — unparseable"
    if len(fields) != TOTAL_KEYS:
        return False, ("the inventory carries %d keys, not the law's %d"
                       % (len(fields), TOTAL_KEYS))
    return False, ("the total-key census is present but the dataType law "
                   "must be judged by the type census, never the count alone")


def _authority_data_type_law(record: dict) -> tuple:
    """The dataType census: 36 LARGE_TEXT free-text keys + the two
    SINGLE_OPTIONS picklists (cover choice + review decision), NO TEXT
    anywhere — the exact census every dataType gate must see. A TEXT row is
    the drift the law bans: the attack read is a FAIL, never a pass."""
    fields = (record or {}).get("fields")
    law = _check_data_type_law(fields) if isinstance(fields, list) else \
        "the record carries no 'fields' list — unparseable"
    if law:
        return False, law
    return False, ("the 36+2 census is present but a free-text key declared "
                   "TEXT instead of the byte-exact LARGE_TEXT is the drift "
                   "this gate must refuse")


def _authority_single_options(record: dict) -> tuple:
    """The SINGLE_OPTIONS law: the TWO SINGLE_OPTIONS rows are byte-exact the
    cover choice with the four named PRD options and the review decision
    with the two gate_engine s5_gate actions — both golden, never part of
    the attack. A drifted row (or a row re-declared TEXT) is drift, never a
    pass."""
    fields = (record or {}).get("fields")
    if not isinstance(fields, list):
        return False, "the record carries no 'fields' list — unparseable"
    singles = _check_single_options_law(fields)
    if singles:
        return False, singles
    return False, ("the SINGLE_OPTIONS rows are intact but the dataType "
                   "census already failed — never a pass")


def verify_inventory(record: dict, authorities=None, *, out=None) -> int:
    """Judge a field inventory against the U07 dataType law.

    READ-ONLY and OFFLINE: the judged surface is whatever record the caller
    hands in — the canonical ATTACK_RECORD fixture, the GOLDEN_RECORD
    control, or a record piped from a dataType gate (this module never makes
    a network call — reg.CafClient / reg.InternalRailClient are the only
    things that ever talk to Convert and Flow, and they send CAF_BROWSER_UA
    on every request, the proven CF-1010 edge fix). The judge is the
    explicit fail: on the TEXT-drift attack the verdict is FAIL, exit 5
    (mismatch family), naming the drifted key by masked marker and the type
    tokens; on the true golden 36+2 inventory the verdict is PASS, exit 0.

    `authorities` defaults to (_authority_total_keys,
    _authority_data_type_law, _authority_cover_choice) — the three checks of
    the dataType law, each judged against the SINGLE AUTHORITY surface
    (field-map.json), because the law must be coherent in every direction:
    an attack that passes ANY dataType gate is a broken gate. Report: ONE
    JSON object on stdout (every drifted key is reported by MASKED MARKER
    only — never a token, never a full key, never a credential), human notes
    on stderr. NEVER prints a token (it holds none: the fixture is pure
    in-memory field-inventory metadata read from the committed
    field-map.json)."""
    out = out or sys.stderr
    if authorities is None:
        authorities = (_authority_total_keys,
                       _authority_data_type_law,
                       _authority_single_options)
    results = []
    if not isinstance(record, dict):
        results.append({"authority": "n/a", "ok": False,
                        "reason": "not_a_dict"})
    elif record.get("contract") == ATTACK_CONTRACT + "-golden":
        # The golden control record: the canonical inventory under the
        # dataType law's own counts — the pass side of the pass/fail split,
        # judged against the single authority. It carries the exact fields
        # the law ships, and it is the ONE shape that is NOT the attack.
        ok_law = not _check_data_type_law(record.get("fields"))
        ok_cover = not _check_single_options_law(record.get("fields"))
        if ok_law and ok_cover:
            results.append({"authority": "golden_control",
                            "ok": True,
                            "reason": "the 36-LARGE_TEXT + 2-SINGLE_OPTIONS "
                                      "canonical inventory (field-map.json) "
                                      "— a clean census, never the TEXT "
                                      "drift"})
        else:
            results.append({"authority": "golden_control",
                            "ok": False,
                            "reason": ("the canonical inventory broke the "
                                       "dataType/cover-choice law — the "
                                       "authority regressed")})
    else:
        for auth in authorities:
            ok, reason = _verify_one_authority(auth, record)
            results.append({"authority": getattr(auth, "__name__", "?"),
                            "ok": ok, "reason": reason})
    # The law's ONE verdict: the TEXT-drift attack MUST FAIL every dataType
    # authority, and the golden 36+2 control MUST PASS — the pass/fail split
    # discriminates the TEXT boundary, never a broken instrument.
    ok = bool(results) and all(r["ok"] for r in results)
    markers = []
    fields = record.get("fields") if isinstance(record, dict) else None
    try:
        markers = _drifted_key_markers(fields) if isinstance(fields, list) else []
    except FixtureError:
        markers = []
    counts = {}
    if isinstance(fields, list):
        for row in fields:
            if isinstance(row, dict) and isinstance(row.get("data_type"), str):
                counts[row["data_type"]] = counts.get(row["data_type"], 0) + 1
    detail = ("all dataType authorities pass: the inventory carries the "
              "byte-exact 36 LARGE_TEXT + 2 SINGLE_OPTIONS census and the "
              "golden control PASSES this judge"
              if ok else (
                  "%d dataType authority(ies) refuse the inventory — TEXT "
                  "declared instead of the byte-exact LARGE_TEXT, drifted "
                  "keys by marker %r, census %r: %s"
                  % (sum(0 if r["ok"] else 1 for r in results),
                     markers, counts,
                     "; ".join("%s (%s)" % (r["reason"], r["authority"])
                               for r in results))))
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "data_type_counts": counts,
        "text_drifted_markers": markers,
        "authorities": results,
        "detail": detail,
        "fail_closed": {
            "text_drift_fails": True,
            "byte_exact_required": True,
            "note": "a free-text key declared TEXT instead of the byte-exact "
                    "LARGE_TEXT is FAIL, exit 5 — never a pass. An attack "
                    "fixture that passes ANY dataType gate is a broken "
                    "gate."},
    }, indent=2, sort_keys=True))
    if ok:
        out.write("[attack-text-drift] verify OK: %s\n" % detail)
        return EX_OK
    out.write("[attack-text-drift] verify FAIL: %s\n" % detail)
    return EX_MISMATCH


# ---------------------------------------------------------------------------
# Fail-closed payload gates — the offline verdict the self-test rides on.
# ---------------------------------------------------------------------------
def _emit_refusal(detail: str, out) -> int:
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": False,
        "verdict": "REFUSED",
        "record": None,
        "detail": detail,
    }, indent=2, sort_keys=True))
    out.write("[attack-text-drift] payload REFUSED: %s\n" % detail)
    return EX_MISMATCH


def payload(*, out=None) -> int:
    """The FAIL-CLOSED gate: ship the TEXT-drift attack report, but ONLY the
    one-TEXT-drift attack. Any drift — a second TEXT row, a drifted cover
    choice, a missing data_type, an unparseable inventory, a conflated
    authority — is REFUSED with exit 5 (verdict REFUSED, ok False), never
    shipped. Returns the exit code; emits the ONE JSON report object on
    stdout, human notes on stderr. The shipped report carries counts and
    masked markers only — never the raw inventory, never a full key, never a
    token (the inventory is read from the committed config/field-map.json,
    never a live id, never a live domain), so shipping it is harmless."""
    out = out or sys.stderr
    try:
        record = attack_inventory()
    except FixtureError as exc:
        return _emit_refusal(str(exc), out)
    drifted = [row for row in record["fields"]
               if row.get("data_type") == ATTACK_DATATYPE]
    if len(drifted) != 1:
        return _emit_refusal(
            "the attack inventory carries %d TEXT row(s), not exactly 1 — "
            "the fixture drifted; refusing." % len(drifted), out)
    if record.get("drifted") != ATTACK_DATATYPE or \
            record.get("golden") != GOLDEN_DATATYPE:
        return _emit_refusal(
            "the attack report carries drifted type tokens (drifted=%r, "
            "golden=%r) — the fixture drifted; refusing."
            % (record.get("drifted"), record.get("golden")), out)
    law = _check_data_type_law([row for row in record["fields"]
                                if row.get("data_type") != ATTACK_DATATYPE]
                               + [dict(drifted[0],
                                       data_type=GOLDEN_DATATYPE)])
    if law:
        return _emit_refusal(
            "the attack inventory differs from the canonical inventory in "
            "more than the ONE type (%s) — the fixture drifted; refusing."
            % law, out)
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "source": record["source"],
        "drifted": ATTACK_DATATYPE,
        "golden": GOLDEN_DATATYPE,
        "drift_key_marker": record["drift_key_marker"],
        "data_type_counts": {"LARGE_TEXT": COUNT_LARGE_TEXT - 1,
                             "TEXT": 1,
                             "SINGLE_OPTIONS": COUNT_SINGLE_OPTIONS},
        "detail": "attack inventory derived byte-exact from the dataType "
                  "authority (config/field-map.json, the LAW) with the ONE "
                  "data_type of the first free-text key re-declared TEXT "
                  "(marker %s) — the exact repo-vs-live drift the spec "
                  "called out — every other field preserved byte-for-byte: "
                  "the TEXT-drift read that MUST FAIL every byte-exact "
                  "dataType gate."
                  % record["drift_key_marker"],
    }, indent=2, sort_keys=True))
    return EX_OK


def payload_true(*, out=None) -> int:
    """The CONTROL gate (negative-result contract): the TRUE canonical
    36+2 inventory must PASS exit 0 — so a payload gate that fails
    EVERYTHING (a broken instrument) is never mistaken for a real TEXT-drift
    discrimination. Derives the golden inventory via the dataType authority
    (never a second implementation) and pins the law on it: if the authority
    ever regresses (a TEXT appears, the 36+2 census breaks, a picklist row
    drifts), the control REFUSES with exit 5 — a regression is caught HERE
    first."""
    out = out or sys.stderr
    inventory = _load_field_inventory()
    law = _check_data_type_law(inventory)
    if law:
        out.write("[attack-text-drift] payload-true REFUSED: the dataType "
                  "authority no longer satisfies the law (%s) — the law "
                  "regressed; refusing.\n" % law)
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "record": None,
            "detail": "config/field-map.json no longer satisfies the "
                      "dataType law: %s" % law,
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    cover = _check_single_options_law(inventory)
    if cover:
        out.write("[attack-text-drift] payload-true REFUSED: the dataType "
                  "authority no longer satisfies the SINGLE_OPTIONS law (%s) "
                  "— the law regressed; refusing.\n" % cover)
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "record": None,
            "detail": "config/field-map.json no longer satisfies the "
                      "SINGLE_OPTIONS law: %s" % cover,
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-true",
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "record": None,
        "source": "config/field-map.json",
        "data_type_counts": {"LARGE_TEXT": COUNT_LARGE_TEXT,
                             "SINGLE_OPTIONS": COUNT_SINGLE_OPTIONS},
        "detail": "control: the true canonical inventory carries the "
                  "byte-exact 36 LARGE_TEXT + 2 SINGLE_OPTIONS census and "
                  "passes exit 0 — the TEXT-drift attack fails by "
                  "comparison, never by a broken gate.",
    }, indent=2, sort_keys=True))
    return EX_OK


def plan(*, out=None) -> int:
    """Offline plan (no network, no credentials): what the attack drifts and
    why, straight from the dataType authority (the single source of truth —
    never a hardcoded law). One JSON object on stdout."""
    out = out or sys.stderr
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-plan",
        "schema_version": 1,
        "source": "config/field-map.json",
        "total_keys": TOTAL_KEYS,
        "golden_counts": {"LARGE_TEXT": COUNT_LARGE_TEXT,
                          "SINGLE_OPTIONS": COUNT_SINGLE_OPTIONS},
        "drifted": ATTACK_DATATYPE,
        "golden": GOLDEN_DATATYPE,
        "drift_key_marker": ATTACK_RECORD["drift_key_marker"],
        "cover_choice_key": COVER_CHOICE_KEY,
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed. The "
                "attack re-declares the ONE data_type of the first free-text "
                "key of the canonical 38-key inventory (config/field-map."
                "json, the single authority) as TEXT instead of the "
                "byte-exact LARGE_TEXT — the exact repo-vs-live drift the "
                "spec called out — with every other field preserved "
                "byte-for-byte and the two SINGLE_OPTIONS picklists left "
                "golden: the TEXT-drift read that MUST FAIL every byte-exact "
                "dataType gate (provision-fields exact-match, the CI drift "
                "gates, the U02 live template re-verify, the snapshot "
                "fixture's 36+2 invariant).",
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: fixture coherence + the fail-closed gates + the golden
# control, no network, no secrets. A FAILED self-test is exit 4 (enforced
# violation), never 'unexpected error' — the same discipline the U05/U06
# attack siblings apply.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[attack-text-drift] SELF-TEST FAILED "
                         "(AF-AE-ATTACKTEXTDRIFT-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    # ---- the dataType authority is the single source of truth ---------------
    inventory = _load_field_inventory()
    assert _check_data_type_law(inventory) == "", \
        "the authority must satisfy the dataType law, got %r" \
        % _check_data_type_law(inventory)
    assert _check_single_options_law(inventory) == "", \
        "the authority must satisfy the SINGLE_OPTIONS law, got %r" \
        % _check_single_options_law(inventory)
    assert len(inventory) == TOTAL_KEYS == 38, \
        "the authority must carry EXACTLY the law's 38 keys, got %d" \
        % len(inventory)
    assert ATTACK_DATATYPE == "TEXT" and GOLDEN_DATATYPE == "LARGE_TEXT", \
        "the drift direction must be TEXT-vs-LARGE_TEXT, got %r/%r" \
        % (ATTACK_DATATYPE, GOLDEN_DATATYPE)
    assert ATTACK_DATATYPE != GOLDEN_DATATYPE, \
        "the drift token must differ from the golden token"

    # ---- the canonical attack record: the one type drifted, everything else
    #      preserved ------------------------------------------------
    record = ATTACK_RECORD
    assert record["drifted"] == "TEXT" and record["golden"] == "LARGE_TEXT", \
        "the attack must re-declare TEXT instead of LARGE_TEXT, got %r/%r" \
        % (record["drifted"], record["golden"])
    drifted = [row for row in record["fields"]
               if row.get("data_type") == "TEXT"]
    assert len(drifted) == 1, \
        "the attack must drift EXACTLY one key, got %d TEXT rows" \
        % len(drifted)
    # the attack differs from the canonical inventory in the ONE variable only
    canonical_types = [row["data_type"] for row in inventory]
    attack_types = [row["data_type"] for row in record["fields"]]
    diffs = [(row["create_name"], before, after)
             for row, before, after in
             zip(record["fields"], canonical_types, attack_types)
             if before != after]
    assert len(diffs) == 1 and diffs[0][1] == "LARGE_TEXT" and \
        diffs[0][2] == "TEXT", \
        "the attack must differ in the ONE data_type only, got %r" % diffs
    # the two SINGLE_OPTIONS rows are NOT part of the attack — they stay golden
    assert _check_single_options_law(record["fields"]) == "", \
        "both SINGLE_OPTIONS rows must stay golden in the attack"
    # the full canonical inventory never rides a surface: the record's drift
    # key is carried by marker only in the report shape, and the payload
    # ships counts + marker, never the raw record
    assert record["drift_key_marker"].startswith("..."), \
        "the drift key must be reported by masked marker"

    # ---- the judge: TEXT-drift read MUST FAIL, golden control MUST PASS ----
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_inventory(record, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "the TEXT-drift attack inventory must FAIL (exit 5), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "FAIL" and parsed["ok"] is False, \
        "the TEXT-drift read must be FAIL, got %s" % parsed["verdict"]
    assert parsed["data_type_counts"].get("TEXT") == 1, \
        "the judge must report the one drifted TEXT row, got %r" \
        % parsed["data_type_counts"]
    assert parsed["text_drifted_markers"] == [record["drift_key_marker"]], \
        "the judge must report the drifted key by masked marker only"
    assert len(parsed["authorities"]) == 3 and all(
        a["ok"] is False for a in parsed["authorities"]), \
        "EVERY dataType authority must refuse the TEXT-drift attack, got %r" \
        % parsed["authorities"]

    # the judge NEVER prints a token, never a full key (masked markers only;
    # the surface carries type tokens and counts only)
    blob = buf.getvalue()
    assert "pit-" not in blob and "Bearer" not in blob, \
        "the judge output must never carry a token shape"
    assert "https://" not in blob and "msgsndr" not in blob, \
        "the judge output must never reference a live platform domain"
    full = record["drift_key_create_name"]
    assert full not in blob, \
        "the judge output must never carry a full drifted key"

    # the golden control PASSES the same judge (the pass/fail split is a
    # discrimination, never a broken instrument)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_inventory(GOLDEN_RECORD, out=io.StringIO())
    assert rc == EX_OK, \
        "the golden 36+2 control must PASS (exit 0), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "PASS" and parsed["ok"] is True, \
        "the golden read must be PASS, got %s" % parsed["verdict"]
    assert len(parsed["authorities"]) == 1 and \
        parsed["authorities"][0]["ok"] is True and \
        parsed["authorities"][0]["authority"] == "golden_control", \
        "the golden control must PASS the golden-control authority, got %r" \
        % parsed["authorities"]

    # ---- the judge's other FAIL directions (all never a pass) ---------------
    # NOTE (fixture discipline): every drift fixture DEEP-copies the rows
    # ([dict(r) for r in record["fields"]]) — the module-level ATTACK_RECORD
    # is a shared authority and the battery is re-run by the U07 dispatcher
    # (provision_fields.py) and by the main_skeleton self-test, so an
    # in-place mutation of the shared record would corrupt the second run
    # (the fixture must be idempotent: a battery that poisons its own module
    # is a broken instrument).
    # 1. a DOUBLE drift (two TEXT rows) -> FAIL, never a pass
    two = {"fields": [dict(r) for r in record["fields"]]}
    for row in two["fields"]:
        if row.get("data_type") == "LARGE_TEXT":
            row["data_type"] = "TEXT"
            break
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_inventory(two, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a double-drift inventory must FAIL (exit 5), got %s" % rc
    # 2. a drift on either SINGLE_OPTIONS picklist row (SINGLE_OPTIONS ->
    #    TEXT) -> FAIL (cover choice or review decision drifted to TEXT is
    #    the same dataType law break)
    cover_drift = {"fields": [dict(r) for r in record["fields"]]}
    for row in cover_drift["fields"]:
        if row.get("data_type") == "SINGLE_OPTIONS":
            row["data_type"] = "TEXT"
            break
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_inventory(cover_drift, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a SINGLE_OPTIONS drift must FAIL (exit 5), got %s" % rc
    # 3. a LARGE_TEXT -> SINGLE_OPTIONS swap (the wrong-direction drift) -> FAIL
    swap = {"fields": [dict(r) for r in record["fields"]]}
    for row in swap["fields"]:
        if row.get("data_type") == "LARGE_TEXT":
            row["data_type"] = "SINGLE_OPTIONS"
            break
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_inventory(swap, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a wrong-direction dataType swap must FAIL (exit 5), got %s" % rc
    # 4. a MISSING data_type -> FAIL (a malformed row is drift)
    missing = {"fields": [dict(r) for r in record["fields"]]}
    for row in missing["fields"]:
        if row.get("data_type") == "TEXT":
            del row["data_type"]
            break
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_inventory(missing, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a data_type-less row must FAIL (exit 5), got %s" % rc
    # 5. a truncated census (27 rows) -> FAIL
    truncated = {"fields": list(record["fields"][:-1])}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_inventory(truncated, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a truncated census must FAIL (exit 5), got %s" % rc
    # 6. a non-mapping surface -> FAIL (the judge is never a pass)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_inventory("not-a-mapping", out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a non-mapping surface must FAIL (exit 5), got %s" % rc
    assert json.loads(buf.getvalue())["verdict"] == "FAIL", \
        "a non-mapping surface must never be a pass"

    # ---- the fail-closed gates: the attack ships, the control passes --------
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(out=io.StringIO())
    assert rc == EX_OK, "payload on the true authority must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["contract"] == ATTACK_CONTRACT
    assert parsed["drifted"] == "TEXT" and parsed["golden"] == "LARGE_TEXT"
    assert parsed["data_type_counts"] == {"LARGE_TEXT": 35,
                                          "TEXT": 1,
                                          "SINGLE_OPTIONS": 2}, \
        "the payload must ship the exact one-TEXT-drift census, got %r" \
        % parsed["data_type_counts"]
    assert parsed["drift_key_marker"] == record["drift_key_marker"]
    # the payload ships the attack as the report, never the raw record: the
    # record's full census carries full keys and stays OFF the surface — the
    # attack's shape is carried by counts and the masked marker only.
    assert "record" not in parsed, \
        "the payload must not ship the raw attack record (full keys)"
    # the shipped payload carries only synthetic fixture material — never a
    # live platform domain, never a token shape, never a full key
    dumped = buf.getvalue()
    assert "https://" not in dumped and "msgsndr" not in dumped, \
        "the fixture must never reference a live platform domain"
    assert "pit-" not in dumped and "Bearer" not in dumped, \
        "the payload output must never carry a token shape"
    assert record["drift_key_create_name"] not in dumped, \
        "the payload must never carry the full drifted key"

    # the golden payload can never be mistaken for an ATTACK payload: the
    # attack gate REFUSES an inventory that already carries TEXT (the wrong
    # direction is drift) -- cross-surface fail-closed proof.
    pre_drifted = {"fields": list(record["fields"])}
    try:
        attack_inventory(pre_drifted)
        raise AssertionError("a pre-drifted inventory must be REFUSED")
    except FixtureError:
        pass
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(out=io.StringIO())
    assert rc == EX_OK, "payload must still ship the attack after the refusal"

    # payload-true (the control): the true canonical 36+2 inventory passes
    # exit 0
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload_true(out=io.StringIO())
    assert rc == EX_OK, \
        "payload-true on the true authority must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["data_type_counts"] == {"LARGE_TEXT": 36,
                                          "SINGLE_OPTIONS": 2}

    # ---- attack fixtures: every drift REFUSED, never shipped ---------------
    # 1. an inventory that already carries TEXT -> refusal (the double-swap a
    #    regression would produce)
    try:
        attack_inventory(pre_drifted)
        raise AssertionError("a pre-drifted inventory was NOT refused")
    except FixtureError:
        pass
    # 2. an inventory under a drifted total (27 rows) -> refusal
    try:
        attack_inventory({"fields": list(inventory[:-1])})
        raise AssertionError("a truncated inventory was NOT refused")
    except FixtureError:
        pass
    # 3. an inventory with a SINGLE_OPTIONS key re-declared -> refusal
    cover_broken = {"fields": list(inventory)}
    for row in cover_broken["fields"]:
        if row.get("data_type") == "SINGLE_OPTIONS":
            row["intended_key"] = "contact.anthology_wrong_key"
            break
    try:
        attack_inventory(cover_broken)
        raise AssertionError("a drifted SINGLE_OPTIONS key was NOT refused")
    except FixtureError:
        pass
    # 4. a non-mapping record -> refusal
    try:
        attack_inventory("not-a-mapping")
        raise AssertionError("a non-mapping record was NOT refused")
    except FixtureError:
        pass

    # ---- the BROWSER UA law is pinned (CF 1010) ------------------------------
    assert reg.CAF_BROWSER_UA and reg.CAF_BROWSER_UA.startswith("Mozilla/"), \
        "CAF_BROWSER_UA must carry a browser User-Agent (the CF-1010 edge fix)"

    # ---- plan: offline, no network, exact drift ----
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = plan(out=io.StringIO())
    assert rc == EX_OK, "plan must exit 0"
    p = json.loads(buf.getvalue())
    assert p["drifted"] == "TEXT" and p["golden"] == "LARGE_TEXT"
    assert p["total_keys"] == 38
    assert p["golden_counts"] == {"LARGE_TEXT": 36, "SINGLE_OPTIONS": 2}
    assert "pit-" not in buf.getvalue()

    dev.write("attack_text_drift self-test: OK (dataType authority pinned "
              "(config/field-map.json: %d keys, 36 LARGE_TEXT + 2 "
              "SINGLE_OPTIONS (cover choice + review decision), no TEXT "
              "anywhere); canonical one-TEXT-drift inventory re-declaring "
              "the ONE data_type of the first free-text key as TEXT instead "
              "of the byte-exact LARGE_TEXT — the repo-vs-live drift the "
              "spec called out — with every other field preserved "
              "byte-for-byte and both SINGLE_OPTIONS rows left golden; "
              "judge FAILs the TEXT-drift read with exit 5 through EVERY "
              "dataType authority naming the drifted key by masked marker "
              "while the golden 36+2 control PASSES exit 0; double-drift / "
              "choice-drift / wrong-direction-swap / missing-data_type / "
              "truncated / non-mapping records FAIL; payload gate ships the "
              "one-TEXT-drift attack and REFUSES under a pre-drifted or "
              "drifted authority while payload-true control PASSes the "
              "canonical census; 4 attack fixtures refused (pre-drifted / "
              "truncated / drifted SINGLE_OPTIONS key / non-mapping); "
              "CAF_BROWSER_UA pinned; never a token shape, never a full "
              "key; plan offline)\n" % TOTAL_KEYS)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="attack_text_drift.py",
        description="Attack fixture — dataType drift (TEXT instead of "
                    "LARGE_TEXT), must FAIL (Skill 59, U07 tooling): the "
                    "adversarial sibling of the engine's dataType law, "
                    "shipping the deterministic one-TEXT-drift inventory "
                    "(the canonical 38-key field inventory read from "
                    "config/field-map.json with the ONE data_type of one "
                    "free-text key re-declared TEXT, every other field "
                    "preserved) that every byte-exact dataType gate must "
                    "refuse, and the fail-closed offline gates that prove "
                    "it (the golden 36+2 control PASSES).")
    ap.add_argument("--record", default=None,
                    help="field-inventory record to judge (verify); "
                         "defaults to the first stdin line (e.g. a gate-"
                         "piped inventory JSON | attack_text_drift.py "
                         "--live)")
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
            raw = (args.record or sys.stdin.read().strip())
            if not raw:
                sys.stderr.write("[attack-text-drift] no record given "
                                 "(--record or stdin) — nothing to judge.\n")
                return EX_ERR
            try:
                record = json.loads(raw)
            except ValueError as exc:
                sys.stderr.write("[attack-text-drift] the record on stdin is "
                                 "not valid JSON: %s\n" % exc)
                return EX_ERR
            return verify_inventory(record, out=sys.stderr)
        return payload()
    except FixtureError as exc:
        sys.stderr.write("[attack-text-drift] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[attack-text-drift] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
