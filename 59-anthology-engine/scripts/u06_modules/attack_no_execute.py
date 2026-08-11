#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u06_modules/attack_no_execute.py
# ATTACK FIXTURE — ARCHIVE WITHOUT --execute, MUST FAIL (U06 archive-gate
# law). The adversarial sibling of the Trevor-gated archive ACTION: an
# archive ACTION (delete / archive / remove / deactivate / revoke /
# unpublish — ANY mutation of an archive target) invoked WITHOUT the
# operator's explicit --execute flag is a REFUSAL, never a silent no-op and
# never a mutation. This module ships the attack shape that MUST FAIL every
# archive gate, in BOTH of its directions: the no-execute read is a FAIL
# (never a pass), and THIS module's own gate payload() must REFUSE shipping
# anything that is not exactly the one-no-execute attack — an archive with
# --execute, an archive without a target, a dry-run report that carries
# applied:true, or an unparseable action record is drift, never an attack
# fixture.
#
# THE ATTACK IS DETERMINISTIC AND SINGLE-VARIABLE: the canonical archive
# ACTION is built by the SINGLE AUTHORITY (u06_modules.golden_absent — the
# U06 archive LAW surface: the TWO archive targets, board and ledger, the
# dry-run report contract the mutation surface MUST emit without --execute,
# and the execute-required law), then the ONE variable — the execute gate —
# is dropped: the archive is invoked WITHOUT the explicit --execute the
# package-init doctrine requires ("Destructive actions fail closed: any
# archive ACTION ... requires the caller to pass --execute explicitly
# (Trevor-gated). Without --execute the module must report what it WOULD do
# and exit without mutating."). The targets are NOT part of the attack: they
# are the golden two-target census over synthetic fixture material (the
# board footprint keyed by participant_key — the KEYING LAW,
# anthology_state.participant_key, contact_id::anthology_id — and the
# ledger rows, deactivate-never-delete, ninety-day retention, the revoke
# flow's R2 / R6 pair), so the failure isolates the execute gate and nothing
# else.
#
# WHERE THIS SITS: scripts/u06_modules/ — an importable module under the U06
# package (pure namespace container per the u06 __init__.py: imported BY
# NAME, side-effect-free at import). It is NOT a manifest row and NOT a
# checker: it ships the ADVERSARIAL FIXTURE the self-tests of the U06
# archive gates and their sibling checkers assert against, so the FAIL path
# is judged against the SAME surface the happy path judges against — a drift
# in the archive law (golden_absent) breaks THIS module's self-test first
# (fail-closed: an inconsistent law is a refusal, never a blind pass). The
# sibling golden_absent.py covers the ABSENT direction (both archive targets
# absent — nothing to archive, clean no-op PASS, and the dry-run report
# contract); THIS module owns the NO-EXECUTE direction and refuses to ship
# any other shape (a fixture that drifts is REFUSED, never shipped).
#
# WHAT THIS OWNS:
#   1. attack_action(record=None) — the builder, fail-closed: the canonical
#      archive ACTION record comes from the SINGLE AUTHORITY
#      (u06_modules.golden_absent — the archive LAW, never a second
#      implementation) and is checked against the two-target archive law,
#      then the ONE execute-gate flag is dropped; a malformed record, a
#      record that already carries execute (the double-gate a regression
#      would produce), or a record without the two-target census raises
#      FixtureError instead of shipping a wrong fixture. The attack record
#      reports the action, the targets (ids by MASKED MARKER — last 4 chars
#      — and counts), what it WOULD do, and execute: false: the exact shape
#      that MUST FAIL the gate.
#   2. verify_archive(record, gates=None) — the JUDGE: runs an archive
#      ACTION record through the U06 archive gate AND its sibling
#      authorities (golden_absent.golden_dry_run_report — the dry-run
#      contract — and find_legacy.LEGACY_NAMES — the find law) and exits 5
#      (mismatch family) on the no-execute attack, naming the missing gate,
#      the action, and the masked target markers — never a pass; on the
#      golden execute-required dry-run contract it exits 0. The one place
#      this module makes the FAIL explicit: an attack fixture that PASSES
#      any archive gate is a broken gate.
#   3. payload() / payload_true() — the FAIL-CLOSED gates. payload() ships
#      the no-execute attack record (the fixture is the module's product)
#      and exits 0 only when the attack is EXACTLY the one-no-execute
#      shape; any drift (an execute flag present, a missing target, an
#      applied:true report, an unparseable record, a conflated authority)
#      is REFUSED with exit 5 (verdict REFUSED). payload_true() is the
#      control: the TRUE execute-required dry-run contract passes exit 0 and
#      its own law pin catches a regression in the archive authority, so
#      the self-test's pass/fail split discriminates the no-execute
#      boundary and never a broken instrument (the negative-result
#      contract: a negative is a claim and carries the same burden of proof
#      as a positive one — a gate that fails everything is a broken check,
#      not a real fault).
#
# DOCTRINE (inherited from the registry / the U06 package init / the
# U02-U05 attack-fixture family):
#   - Never a token printed: this module holds and resolves NO credential —
#     the fixture is pure in-memory archive-ACTION metadata over SYNTHETIC
#     subject material (never a live id, never a live workflow, never a
#     live anthology), and the verify surface reports every id by masked
#     marker (last 4 chars) only. Nothing in this module can ever echo a
#     secret because no secret is ever read.
#   - Fail-closed: a drifted authority, an unparseable action record, an
#     archive with --execute where the attack requires its absence all STOP
#     or FAIL — never a blind pass, never a fabricated success, never a
#     mutation.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#     It ships the no-execute read that MUST FAIL the archive gate; the
#     archive ACTION itself is owned by the mutation surface and is
#     Trevor-gated (--execute required — the package-init doctrine), which
#     this module pins.
#   - The GHL / Convert and Flow surface is Cloudflare-fronted: urllib's
#     default "Python-urllib/x.y" User-Agent is 403'd at the WAF edge (CF
#     error 1010) before it ever reaches the API (CAF_BROWSER_UA in
#     anthology_registry.py is the house pattern). This module itself makes
#     NO network call — it ships the offline adversarial fixture only; any
#     sibling that DOES talk to the platform must ride the house browser
#     User-Agent on every request, and the self-test pins the constant so a
#     registry regression is caught HERE first.
#
# EXIT CODE CONTRACT (house convention; mirrors the U05 attack_wrong_form /
# attack_unscoped siblings and the U04 attack_bad_query family):
#   0  verified success — the golden execute-required control record is
#      internally consistent and byte-exact to the archive law; also
#      self-test / plan OK
#   1  unexpected error (malformed input / no record to judge)
#   4  self-test FAILED (AF-AE-ATTACKNOEXECUTE-* family, enforced violation)
#   5  mismatch — the no-execute attack record is FAIL (verify_archive) or
#      REFUSED (payload under drift), never a blind pass
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# u06 golden siblings: sys.path.insert to scripts/ then
# `import anthology_registry as reg` / `import u06_modules.golden_absent as
# golden` / `import u06_modules.find_legacy as legacy_finder`.
# =============================================================================
"""attack_no_execute.py — the archive-without---execute attack fixture that
must FAIL.

The adversarial sibling of the U06 Trevor-gated archive ACTION: the ONE
execute-gate flag of the canonical archive ACTION record is dropped, and
every archive gate must refuse the resulting no-execute read while this
module's own gates refuse anything that is not exactly that shape (exit 5).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to golden_absent.py):
# golden_absent owns the archive LAW (the two archive targets + the
# execute-required dry-run report contract), find_legacy owns the legacy
# find law (the byte-exact legacy workflow names the U06 archive targets),
# the registry owns the browser-UA wiring + the masking helper — the module
# reuses them, never re-implements.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import u06_modules.find_legacy as legacy_finder  # noqa: E402  (the find law)
import u06_modules.golden_absent as golden  # noqa: E402  (the archive LAW authority)

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The one fixed report contract.
ATTACK_CONTRACT = "anthology-engine-attack-no-execute"

# The archive ACTION law, machine-carried from the single authority: the
# mutation verb the attack invokes WITHOUT its gate, the execute flag whose
# explicit presence is Trevor's gate, and the archive LAW's own assertion
# that the gate is REQUIRED (golden_absent.GOLDEN_EXECUTE_REQUIRED). The
# self-test pins all three against golden_absent so a drift in the archive
# law breaks THIS fixture first, fail-closed.
ATTACK_ACTION = golden.ARCHIVE_ACTION            # "archive"
EXECUTE_FLAG = golden.EXECUTE_FLAG               # "--execute"
GOLDEN_EXECUTE_REQUIRED = golden.GOLDEN_EXECUTE_REQUIRED

# The archive targets the ACTION touches — the TWO targets of the engine's
# archive sweep (the revoke flow's R2 / R6 pair), read once from the single
# authority: the board footprint (mc_board.py cmd_archive — the Assembly
# card + every participant card, keyed by participant_key, the KEYING LAW)
# and the ledger rows (anthology_state.py upsert-anthology --status
# archived — deactivate-never-delete, ninety-day retention).
ARCHIVE_TARGETS = golden.ARCHIVE_TARGETS  # ("board", "ledger"), in order

# Deterministic SYNTHETIC fixture material — never a live id, never a live
# workflow, never a live anthology: the attack record the payload ships is
# built from these, so shipping it is harmless. Mirrors the golden siblings'
# synthetic discipline (anth_golden / cnt_golden / wfLegacyStart01).
GOLDEN_ANTHOLOGY_ID = "anth_golden"                       # synthetic, never live
GOLDEN_CONTACT_ID = "cnt_golden"                          # synthetic, never live
SYNTHETIC_WRITER_ID = "wfLegacyStart01"                   # synthetic, never live
SYNTHETIC_MANAGER_ID = "wfLegacyPipe02"                   # synthetic, never live

# The board footprint is keyed by participant_key — the KEYING LAW read
# through the single keying authority (never a second implementation).
SYNTHETIC_SUBJECT_KEY = golden.GOLDEN_SUBJECT_KEY  # "cnt_golden::anth_golden"

# The canonical attack record — the archive ACTION with its execute gate
# DROPPED: the two-target census over the synthetic material (one board
# card, one ledger row — BOTH present, so the action is NOT the golden
# absent no-op and the no-execute read MUST FAIL the archive gate), every
# id by masked marker, and execute: false. The exact shape that must never
# be judged clean. Synthetic fixture data, never a live id.
ATTACK_ACTION_RECORD = {
    "action": ATTACK_ACTION,
    "targets": {
        "board": [
            {"participant_key": SYNTHETIC_SUBJECT_KEY,
             "card_id_marker": reg._mask_location("card_golden_bd01")},
        ],
        "ledger": [
            {"anthology_id": GOLDEN_ANTHOLOGY_ID,
             "status": "active"},
        ],
    },
    "execute": False,
    "execute_required": GOLDEN_EXECUTE_REQUIRED,
    "applied": False,
    "dry_run": True,
    "would_do": "archive the board footprint and the ledger rows of the "
                "synthetic anthology WITHOUT the operator's explicit "
                "--execute — the gate is missing, the ACTION is a refusal",
}

# The golden control record — the SAME ACTION under the archive LAW's own
# execute-required dry-run contract (golden.golden_dry_run_report), with the
# law's targets at their golden counts. The pass side of the pass/fail
# split: an archive ACTION that reports what it WOULD do and exits without
# mutating, with execute_required: true, is a clean dry-run — never the
# attack (a gate that fails everything is a broken instrument).
GOLDEN_RECORD = {
    "action": golden.ARCHIVE_ACTION,
    "targets": {"board": 0, "ledger": 0},
    "applied": False,
    "dry_run": True,
    "execute_required": True,
}

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (the house shape find_legacy guards with). The label word "PIT"
# alone is NOT a credential shape — operator surfaces name labels, never
# values. Every emitted surface is scanned against it before print.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the archive
    authority or the action record drifted from the law, so NO fixture is
    shipped — a wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# The attack builder — fail-closed, deterministic, canonical minus the gate.
# ---------------------------------------------------------------------------
def _record_action(record: dict) -> str:
    """The ACTION verb an archive record names. Fail-closed: a record that
    is not a mapping refuses; a record without an 'action' field names
    nothing."""
    if not isinstance(record, dict):
        raise FixtureError(
            "record is %r, not a mapping — refusing to judge an unparseable "
            "surface (never fabricated)." % type(record).__name__)
    action = record.get("action")
    if not isinstance(action, str) or not action.strip():
        raise FixtureError(
            "the archive record carries no 'action' verb — refusing to "
            "judge an unparseable action.")
    return action.strip()


def _mask_target_markers(record: dict) -> dict:
    """The MASKED-MARKER projection of the target census of an archive
    record: every id on the target rows is reduced to its last-4 marker (the
    house masked-marker discipline — never a full id on any surface). The
    marker of an id that is not a non-empty string is refused, never
    guessed. Fail-closed: a census that is not a mapping, or a target that
    is not a list of rows, refuses."""
    targets = record.get("targets")
    if not isinstance(targets, dict):
        raise FixtureError(
            "the archive record carries no 'targets' mapping — refusing to "
            "judge an unparseable census.")
    out = {}
    for target in ARCHIVE_TARGETS:
        rows = targets.get(target)
        if not isinstance(rows, list):
            raise FixtureError(
                "the archive census carries no %r array — refusing to judge "
                "an unparseable census." % target)
        markers = []
        for row in rows:
            if not isinstance(row, dict):
                raise FixtureError(
                    "the %r census carries a non-object row — refusing." % target)
            # the id-bearing key per target: participant_key (board, the
            # KEYING LAW) or anthology_id (ledger). A row without one is
            # drift — the census cannot be masked, so it cannot be judged.
            idkey = "participant_key" if target == "board" else "anthology_id"
            value = row.get(idkey)
            if not isinstance(value, str) or not value.strip():
                raise FixtureError(
                    "the %r census row carries no %r — refusing." % (target, idkey))
            markers.append(reg._mask_location(value))
        out[target] = sorted(markers)
    return out


def _mask_target_markers_public(record: dict) -> dict:
    """The MASKED-MARKER projection of the target census for EVERY public
    surface (the payload and the judge): the marker of every id-bearing key
    that rides a surface — participant_key (board, the KEYING LAW),
    anthology_id (ledger), and the card id under its marker-named key
    (card_id_marker / card_id_masked) — reduced to its last-4 marker, NEVER
    a full id on any surface. Every key's full value is dropped from the
    projection; a non-string marker value is refused, never guessed. The
    board marker is the composite KEYING-LAW key masked (the same marker
    _mask_target_markers yields); the card marker rides under its own
    key."""
    targets = record.get("targets")
    if not isinstance(targets, dict):
        raise FixtureError(
            "the archive record carries no 'targets' mapping — refusing to "
            "judge an unparseable census.")
    out = {}
    for target in ARCHIVE_TARGETS:
        rows = targets.get(target)
        if not isinstance(rows, list):
            raise FixtureError(
                "the archive census carries no %r array — refusing to judge "
                "an unparseable census." % target)
        markers = []
        card_markers = []
        for row in rows:
            if not isinstance(row, dict):
                raise FixtureError(
                    "the %r census carries a non-object row — refusing." % target)
            idkey = "participant_key" if target == "board" else "anthology_id"
            value = row.get(idkey)
            if not isinstance(value, str) or not value.strip():
                raise FixtureError(
                    "the %r census row carries no %r — refusing." % (target, idkey))
            markers.append(reg._mask_location(value))
            for card_key in ("card_id_marker", "card_id_masked"):
                cval = row.get(card_key)
                if cval is not None:
                    if not isinstance(cval, str) or not cval.strip():
                        raise FixtureError(
                            "the %r census row carries a non-string %r — "
                            "refusing." % (target, card_key))
                    card_markers.append(reg._mask_location(cval))
        out[target] = sorted(markers)
        if card_markers:
            out[target + "_cards"] = sorted(card_markers)
    return out


def attack_action(record: dict = None) -> dict:
    """Build the attack record: the canonical archive ACTION record comes
    from the SINGLE AUTHORITY (u06_modules.golden_absent — the archive LAW,
    never a second implementation), is checked against the archive law (the
    action verb is exactly 'archive', the two-target census over the
    synthetic material is present, and the record does NOT already carry the
    execute gate — the double-gate a regression would produce), then the ONE
    execute-gate flag is dropped (execute: false). Any drift raises
    FixtureError — a wrong fixture is never shipped."""
    if record is not None and not isinstance(record, dict):
        raise FixtureError(
            "record is %r, not a mapping — refusing to build an attack "
            "from an unparseable surface (never fabricated)."
            % type(record).__name__)
    base = dict(record) if record is not None else dict(ATTACK_ACTION_RECORD)
    action = _record_action(base)
    if golden.GOLDEN_EXECUTE_REQUIRED is not True:
        raise FixtureError(
            "the archive authority no longer asserts the execute-required "
            "law — the Trevor gate regressed; refusing to ship an attack "
            "payload.")
    if action != golden.ARCHIVE_ACTION:
        raise FixtureError(
            "the archive record names action %r, not the byte-exact "
            "'archive' — the archive authority drifted; refusing to ship an "
            "attack payload." % action)
    if not isinstance(base.get("targets"), dict):
        raise FixtureError(
            "the archive record carries no two-target census — the archive "
            "authority drifted; refusing to ship an attack payload.")
    for target in ARCHIVE_TARGETS:
        if not isinstance(base["targets"].get(target), list):
            raise FixtureError(
                "the archive record carries no %r target array — the "
                "archive authority drifted; refusing to ship an attack "
                "payload." % target)
    if base.get("execute") is not False:
        raise FixtureError(
            "the archive record already carries the execute gate (the "
            "double-gate a regression would produce) — refusing to ship a "
            "double-gate attack.")
    out = dict(base)
    out["action"] = golden.ARCHIVE_ACTION
    out["execute"] = False
    out["execute_required"] = golden.GOLDEN_EXECUTE_REQUIRED
    out["applied"] = False
    out["dry_run"] = True
    return out


# The canonical attack record, derived ONCE at import from the archive
# authority — fail-fast: a drifted authority breaks the import of the
# fixture itself, so a checker that imports this module by name catches the
# drift first.
ATTACK_RECORD = attack_action()


# ---------------------------------------------------------------------------
# The judge — verify_archive: the ONE surface that makes the FAIL explicit.
# ---------------------------------------------------------------------------
def _verify_one_authority(authority_check, record: dict) -> tuple:
    """Run ONE archive authority over ITS canonical surface and return
    (ok, reason). The authority is the law owner's own check — never a
    re-implementation — and it is side-effect-free by contract."""
    try:
        ok, reason = authority_check(record)
    except FixtureError as exc:
        return False, str(exc)
    return bool(ok), str(reason or "unknown")


def _authority_execute_required(record: dict) -> tuple:
    """The execute-required law — the JUDGE MAKES THE FAIL EXPLICIT HERE:
    an archive ACTION invoked WITHOUT the operator's explicit --execute is a
    REFUSAL, and the RECORD ITSELF carries the missing-gate verdict
    (execute: false, the boolean the attack ships) plus the archive LAW's
    own gate pin (record['execute_required'] must assert
    golden_absent.GOLDEN_EXECUTE_REQUIRED — the single authority, never
    re-implemented). A record that reports the gate PRESENT (execute not
    False — the shape a mutation surface would produce after a real write)
    is drift, never the no-execute attack; a record whose gate pin drifted
    from the authority is drift, never a pass."""
    if record.get("execute") is not False:
        return False, "execute gate present — this is not the no-execute attack"
    if record.get("execute_required") is not golden.GOLDEN_EXECUTE_REQUIRED:
        return False, ("execute_required drifted from the archive authority "
                       "(got %r, want %r)" % (record.get("execute_required"),
                                              golden.GOLDEN_EXECUTE_REQUIRED))
    return False, ("archive ACTION invoked without the operator's explicit "
                   "--execute — the no-execute read is a REFUSAL (Trevor "
                   "gate), never a pass")


def _authority_dry_run_contract(record: dict) -> tuple:
    """The dry-run contract: an archive ACTION invoked WITHOUT --execute
    must report what it WOULD do and exit WITHOUT mutating — applied: false,
    dry_run: true (the exact contract golden_absent.golden_dry_run_report
    ships, never re-implemented). The no-execute read carries the dry-run
    flags, but carrying them is NOT a pass — the missing gate already failed
    the law; a record that additionally reports applied: true, or that is
    not a dry-run, is a mutation claim — FAIL, never a pass."""
    if record.get("applied") is not False:
        return False, "applied is not false — a mutation was claimed without --execute"
    if record.get("dry_run") is not True:
        return False, "dry_run is not true — the no-execute read must be a dry-run"
    return False, "the dry-run flags cannot pass an ACTION whose execute gate is absent"


def _authority_action_law(record: dict) -> tuple:
    """The action law: the ACTION verb is byte-exact the archive LAW's verb
    ('archive', read once from golden_absent — never hardcoded). An archive
    ACTION under ANY other verb is drift, never the attack. The verb alone
    cannot pass the no-execute read — the missing gate already failed the
    law."""
    if _record_action(record) != golden.ARCHIVE_ACTION:
        return False, "action verb is not the byte-exact archive ACTION"
    return False, "the ACTION verb is present but the execute gate is absent"


def verify_archive(record: dict, authorities=None, *, out=None) -> int:
    """Judge an archive ACTION record against the U06 archive-gate law.

    READ-ONLY and OFFLINE: the judged surface is whatever record the caller
    hands in — the canonical ATTACK_RECORD fixture, the GOLDEN_RECORD
    control, or a record piped from the mutation surface (this module never
    makes a network call — reg.CafClient / reg.InternalRailClient are the
    only things that ever talk to Convert and Flow, and they send
    CAF_BROWSER_UA on every request, the proven CF-1010 edge fix). The judge
    is the explicit fail: on the no-execute attack the verdict is FAIL,
    exit 5 (mismatch family), naming the missing gate, the action, and the
    masked target markers; on the true execute-required dry-run contract the
    verdict is PASS, exit 0.

    `authorities` defaults to (_authority_execute_required,
    _authority_dry_run_contract, _authority_action_law) — the three checks
    of the archive law, each judged against the SINGLE authority surface
    (golden_absent / the KEYING LAW), because the law must be coherent in
    every direction: an attack that passes ANY archive gate is a broken
    gate. Report: ONE JSON object on stdout (every id is reported by MASKED
    MARKER only — never a token, never a full id), human notes on stderr.
    NEVER prints a token (it holds none: the fixture is pure in-memory
    archive-ACTION metadata over synthetic material)."""
    out = out or sys.stderr
    if authorities is None:
        authorities = (_authority_execute_required,
                       _authority_dry_run_contract,
                       _authority_action_law)
    results = []
    if not isinstance(record, dict):
        results.append({"authority": "n/a", "ok": False,
                        "reason": "not_a_dict"})
    elif record.get("execute_required") is True and \
            (record.get("execute") is None or record.get("execute") is False) and \
            record.get("applied") is False and \
            record.get("dry_run") is True and \
            _record_action(record) == golden.ARCHIVE_ACTION and \
            isinstance(record.get("targets"), dict) and \
            not record["targets"].get("board") and \
            not record["targets"].get("ledger"):
        # The golden control record: the archive LAW's own execute-required
        # dry-run contract (golden_absent.golden_dry_run_report) with the
        # law's targets at their golden counts — the pass side of the
        # pass/fail split, judged against the single authority. It carries
        # the exact fields the law ships, and it is the ONE shape that is
        # NOT the attack.
        results.append({"authority": "golden_control",
                        "ok": True,
                        "reason": "the execute-required dry-run contract "
                                  "(golden_absent) — a clean dry-run, never "
                                  "the no-execute attack"})
    else:
        for auth in authorities:
            ok, reason = _verify_one_authority(auth, record)
            results.append({"authority": getattr(auth, "__name__", "?"),
                            "ok": ok, "reason": reason})
    # The law's ONE verdict: the no-execute attack MUST FAIL every archive
    # authority, and the golden execute-required control MUST PASS — the
    # pass/fail split discriminates the missing-gate boundary, never a
    # broken instrument. `record['execute']` is the caller's own verdict
    # (false on the attack and on the golden dry-run contract); whether the
    # record is the attack or the control is decided by the authorities.
    ok = bool(results) and all(r["ok"] for r in results) and \
        isinstance(record, dict) and \
        record.get("execute_required") is True and \
        isinstance(record.get("targets"), dict) and \
        not record["targets"].get("board") and \
        not record["targets"].get("ledger")
    action = _record_action(record) if isinstance(record, dict) else ""
    markers = {}
    if isinstance(record, dict):
        try:
            markers = _mask_target_markers_public(record)
        except FixtureError:
            markers = {}
    detail = ("all archive authorities pass: the ACTION carries the "
              "execute-required dry-run contract and the golden control "
              "PASSES this judge"
              if ok else (
                  "%d archive authority(ies) refuse the record — action %r, "
                  "execute absent, targets by marker %r: %s"
                  % (sum(0 if r["ok"] else 1 for r in results),
                     action, markers,
                     "; ".join("%s (%s)" % (r["reason"], r["authority"])
                               for r in results))))
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "action": action,
        "execute": False,
        "execute_required": (record.get("execute_required")
                             if isinstance(record, dict) else None),
        "target_markers": markers,
        "authorities": results,
        "detail": detail,
        "fail_closed": {
            "no_execute_fails": True,
            "execute_required": True,
            "note": "an archive ACTION invoked without the operator's "
                    "explicit --execute (the Trevor gate) is FAIL, exit 5 — "
                    "never a pass, never a mutation. An attack fixture that "
                    "passes ANY archive gate is a broken gate."},
    }, indent=2, sort_keys=True))
    if ok:
        out.write("[attack-no-execute] verify OK: %s\n" % detail)
        return EX_OK
    out.write("[attack-no-execute] verify FAIL: %s\n" % detail)
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
    out.write("[attack-no-execute] payload REFUSED: %s\n" % detail)
    return EX_MISMATCH


def payload(*, out=None) -> int:
    """The FAIL-CLOSED gate: ship the no-execute attack record, but ONLY the
    one-no-execute attack. Any drift — an execute flag present, a missing
    target, an applied:true report, an unparseable record, a conflated
    authority — is REFUSED with exit 5 (verdict REFUSED, ok False), never
    shipped. Returns the exit code; emits the ONE JSON report object on
    stdout, human notes on stderr. The shipped record is built from
    SYNTHETIC fixture material (never a live id, never a live workflow,
    never a live anthology), so shipping it is harmless."""
    out = out or sys.stderr
    try:
        record = attack_action()
    except FixtureError as exc:
        return _emit_refusal(str(exc), out)
    if record.get("execute") is not False:
        return _emit_refusal(
            "the attack record carries the execute gate — the fixture "
            "drifted (execute=%r); refusing." % record.get("execute"), out)
    if record.get("action") != golden.ARCHIVE_ACTION:
        return _emit_refusal(
            "the attack record names action %r, not exactly %r — the "
            "fixture drifted; refusing." % (record.get("action"),
                                            golden.ARCHIVE_ACTION), out)
    if record.get("applied") is not False or record.get("dry_run") is not True:
        return _emit_refusal(
            "the attack record is not the no-mutation dry-run (applied=%r, "
            "dry_run=%r) — a mutation claim is drift, never the attack; "
            "refusing." % (record.get("applied"), record.get("dry_run")), out)
    try:
        markers = _mask_target_markers_public(record)
    except FixtureError as exc:
        return _emit_refusal(str(exc), out)
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "action": record["action"],
        "execute": False,
        "execute_required": golden.GOLDEN_EXECUTE_REQUIRED,
        "applied": False,
        "dry_run": True,
        "target_markers": markers,
        "target_counts": {"board": len(record["targets"]["board"]),
                          "ledger": len(record["targets"]["ledger"])},
        "detail": "attack record derived byte-exact from the archive "
                  "authority (golden_absent, the archive LAW) with the ONE "
                  "execute-gate flag dropped: the no-execute archive read "
                  "that MUST FAIL every Trevor-gated archive surface. "
                  "Synthetic fixture material only, every id by masked "
                  "marker — never a live id, never a live workflow, never "
                  "a live anthology.",
    }, indent=2, sort_keys=True))
    return EX_OK


def payload_true(*, out=None) -> int:
    """The CONTROL gate (negative-result contract): the TRUE execute-required
    dry-run contract must PASS exit 0 — so a payload gate that fails
    EVERYTHING (a broken instrument) is never mistaken for a real no-execute
    discrimination. Derives the golden record via the archive authority
    (never a second implementation) and pins the law on it: if the authority
    ever regresses (the execute-required law stops asserting, the action
    verb drifts), the control REFUSES with exit 5 — a regression is caught
    HERE first."""
    out = out or sys.stderr
    golden_report = golden.golden_dry_run_report()
    if golden_report.get("execute_required") is not True:
        out.write("[attack-no-execute] payload-true REFUSED: the archive "
                  "authority no longer asserts execute_required — the law "
                  "regressed; refusing.\n")
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "record": None,
            "detail": "golden_absent.golden_dry_run_report no longer carries "
                      "execute_required: true — the archive authority "
                      "regressed.",
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    if golden_report.get("action") != ATTACK_ACTION:
        out.write("[attack-no-execute] payload-true REFUSED: the archive "
                  "authority no longer names the %r ACTION — the law "
                  "regressed; refusing.\n" % ATTACK_ACTION)
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "record": None,
            "detail": "the archive ACTION verb drifted from %r."
                      % ATTACK_ACTION,
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-true",
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "record": GOLDEN_RECORD,
        "action": golden.ARCHIVE_ACTION,
        "execute": False,
        "execute_required": True,
        "detail": "control: the true execute-required dry-run contract "
                  "passes exit 0 — the no-execute attack fails by "
                  "comparison, never by a broken gate.",
    }, indent=2, sort_keys=True))
    return EX_OK


def plan(*, out=None) -> int:
    """Offline plan (no network, no credentials): what the attack drops and
    why, straight from the archive authority (the single source of truth —
    never a hardcoded law). One JSON object on stdout."""
    out = out or sys.stderr
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-plan",
        "schema_version": 1,
        "action": ATTACK_ACTION,
        "execute_dropped": True,
        "execute_required": GOLDEN_EXECUTE_REQUIRED,
        "targets": {target: list(markers) for target, markers in
                    _mask_target_markers(ATTACK_RECORD).items()},
        "legacy_targets": list(legacy_finder.LEGACY_NAMES.keys()),
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed. The "
                "attack drops the ONE execute gate of the canonical archive "
                "ACTION (the Trevor-gated --execute of the U06 package "
                "init): the two-target archive census (board + ledger, "
                "synthetic material, every id masked to its last-4 marker) "
                "is invoked WITHOUT the gate — the no-execute read that "
                "MUST FAIL every archive gate, never a pass, never a "
                "mutation.",
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: fixture coherence + the fail-closed gates + the golden
# control, no network, no secrets. A FAILED self-test is exit 4 (enforced
# violation), never 'unexpected error' — the same discipline golden_absent
# and its siblings apply.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[attack-no-execute] SELF-TEST FAILED "
                         "(AF-AE-ATTACKNOEXECUTE-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    # ---- the archive authority is the single source of truth ----------------
    assert golden.ARCHIVE_ACTION == "archive", \
        "the archive authority must pin the ACTION verb, got %r" \
        % golden.ARCHIVE_ACTION
    assert golden.EXECUTE_FLAG == "--execute", \
        "the archive authority must pin the Trevor gate flag, got %r" \
        % golden.EXECUTE_FLAG
    assert golden.GOLDEN_EXECUTE_REQUIRED is True, \
        "the archive authority must assert that the ACTION is --execute-gated"
    assert golden.ARCHIVE_TARGETS == ("board", "ledger"), \
        "the archive sweep reads EXACTLY the two targets board / ledger"
    # the two authority families agree on the ACTION surface (never a split)
    assert legacy_finder.LEGACY_NAMES["start_anthology_writer"].strip() and \
        legacy_finder.LEGACY_NAMES["pipeline_manager"].strip(), \
        "the find law must carry both legacy names non-empty"

    # ---- the canonical attack record: the one gate dropped, everything else
    #      preserved ------------------------------------------------
    record = ATTACK_RECORD
    assert record["action"] == ATTACK_ACTION == "archive", \
        "the attack must name exactly the archive ACTION, got %r" \
        % record["action"]
    assert record["execute"] is False, \
        "the attack must drop the execute gate (execute=False), got %r" \
        % record["execute"]
    assert record["execute_required"] is True, \
        "the attack must still carry the archive LAW's execute-required pin"
    assert record["applied"] is False and record["dry_run"] is True, \
        "the attack must be the no-mutation dry-run read"
    assert isinstance(record["targets"], dict), \
        "the attack must carry the two-target census"
    assert len(record["targets"]["board"]) == 1 and \
        len(record["targets"]["ledger"]) == 1, \
        "the attack census must carry BOTH targets present (one row each)"
    markers = _mask_target_markers(record)
    assert markers["board"] == ["...lden"], \
        "the board marker must be the synthetic subject key's last-4, got %r" \
        % markers["board"]
    assert markers["ledger"] == ["...lden"], \
        "the ledger marker must be the synthetic anthology's last-4, got %r" \
        % markers["ledger"]
    # the golden control differs from the attack in the ONE variable only —
    # its execute-required contract is the SAME law (never a second law)
    assert GOLDEN_RECORD["action"] == ATTACK_ACTION
    assert GOLDEN_RECORD["execute_required"] is True

    # ---- the judge: no-execute read MUST FAIL, golden control MUST PASS ----
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_archive(record, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "the no-execute attack record must FAIL (exit 5), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "FAIL" and parsed["ok"] is False, \
        "the no-execute read must be FAIL, got %s" % parsed["verdict"]
    assert parsed["action"] == "archive", \
        "the judge must name the ACTION verb, got %r" % parsed["action"]
    assert parsed["execute"] is False and parsed["execute_required"] is True, \
        "the judge must report the dropped gate and the law's pin"
    assert len(parsed["authorities"]) == 3 and all(
        a["ok"] is False for a in parsed["authorities"]), \
        "EVERY archive authority must refuse the no-execute attack, got %r" \
        % parsed["authorities"]
    assert parsed["target_markers"]["board"] == ["...lden"], \
        "the judge must report the board by masked marker only"
    assert parsed["target_markers"]["ledger"] == ["...lden"], \
        "the judge must report the ledger by masked marker only"

    # the judge NEVER prints a token or a full id (masked markers only)
    blob = buf.getvalue()
    assert "pit-" not in blob and "Bearer" not in blob, \
        "the judge output must never carry a token shape"
    assert "cnt_golden" not in blob and "anth_golden" not in blob, \
        "the judge output must never carry a full synthetic subject id"
    assert "wfLegacyStart01" not in blob and \
        "wfLegacyPipe02" not in blob, \
        "the judge output must never carry a full synthetic workflow id"

    # the golden control PASSES the same judge (the pass/fail split is a
    # discrimination, never a broken instrument)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_archive(GOLDEN_RECORD, out=io.StringIO())
    assert rc == EX_OK, \
        "the execute-required dry-run control must PASS (exit 0), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "PASS" and parsed["ok"] is True, \
        "the golden read must be PASS, got %s" % parsed["verdict"]
    assert len(parsed["authorities"]) == 1 and \
        parsed["authorities"][0]["ok"] is True and \
        parsed["authorities"][0]["authority"] == "golden_control", \
        "the golden control must PASS the golden-control authority, got %r" \
        % parsed["authorities"]

    # ---- the judge's other FAIL directions (all never a pass) ---------------
    # 1. an execute-present record (the double-gate a regression would
    #    produce) -> FAIL, never a pass
    double = dict(record, execute=True)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_archive(double, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "an execute-present record must FAIL (exit 5), got %s" % rc
    # 2. a record that claims a mutation (applied true) -> FAIL
    mutation = dict(record, applied=True)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_archive(mutation, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a mutation-claiming record must FAIL (exit 5), got %s" % rc
    # 3. a record under a drifted execute-required pin -> FAIL (the law is
    #    the single authority, never re-implemented)
    drift = dict(record, execute_required=False)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_archive(drift, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a drifted execute-required pin must FAIL (exit 5), got %s" % rc
    # 4. a non-mapping surface -> FAIL (never a pass)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_archive("not-a-mapping", out=io.StringIO())
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
    assert parsed["execute"] is False and parsed["applied"] is False
    assert parsed["dry_run"] is True
    assert parsed["execute_required"] is True
    assert parsed["target_counts"] == {"board": 1, "ledger": 1}
    assert parsed["target_markers"]["board"] == ["...lden"]
    assert parsed["target_markers"]["board_cards"] == ["...bd01"]
    assert parsed["target_markers"]["ledger"] == ["...lden"]
    # the payload ships the attack as the report, never the raw record:
    # the record's full census carries full synthetic ids and stays OFF the
    # surface — the attack's shape is carried by markers and counts only.
    assert "record" not in parsed, \
        "the payload must not ship the raw attack record (full ids)"
    # the shipped payload carries only synthetic fixture material — never a
    # live platform domain, never a token shape, never a full id
    dumped = buf.getvalue()
    assert "https://" not in dumped and "msgsndr" not in dumped, \
        "the fixture must never reference a live platform domain"
    assert "pit-" not in dumped and "Bearer" not in dumped, \
        "the payload output must never carry a token shape"
    assert "cnt_golden" not in dumped and "anth_golden" not in dumped, \
        "the payload must never carry a full synthetic subject id"
    assert "wfLegacyStart01" not in dumped and \
        "wfLegacyPipe02" not in dumped, \
        "the payload must never carry a full synthetic workflow id"
    assert "card_golden" not in dumped, \
        "the payload must never carry a full synthetic card id"

    # the golden payload can never be mistaken for an ATTACK payload: the
    # attack gate REFUSES an execute-present record (the wrong direction is
    # drift) -- cross-surface fail-closed proof.
    saved_gate = golden.GOLDEN_EXECUTE_REQUIRED
    try:
        golden.GOLDEN_EXECUTE_REQUIRED = False  # the archive law regressed
        try:
            attack_action()
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
        golden.GOLDEN_EXECUTE_REQUIRED = saved_gate
    # after restore the control passes again (the refusal was the drift, not
    # the instrument)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload_true(out=io.StringIO())
    assert rc == EX_OK, \
        "payload-true must pass again after the authority restored"

    # payload-true (the control): the true execute-required dry-run contract
    # passes exit 0
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload_true(out=io.StringIO())
    assert rc == EX_OK, \
        "payload-true on the true authority must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["execute_required"] is True

    # ---- attack fixtures: every drift REFUSED, never shipped ---------------
    # 1. an archive record that already carries the execute gate -> refusal
    try:
        attack_action(dict(record, execute=True))
        raise AssertionError("a double-gate attack was NOT refused")
    except FixtureError:
        pass
    # 2. an archive record under a different ACTION verb -> refusal
    try:
        attack_action(dict(record, action="deactivate"))
        raise AssertionError("a non-archive ACTION was NOT refused")
    except FixtureError:
        pass
    # 3. an archive record without the two-target census -> refusal
    try:
        attack_action({"action": "archive", "execute": False})
        raise AssertionError("a census-less record was NOT refused")
    except FixtureError:
        pass
    # 4. a non-mapping record -> refusal
    try:
        attack_action("not-a-mapping")
        raise AssertionError("a non-mapping record was NOT refused")
    except FixtureError:
        pass

    # ---- the BROWSER UA law is pinned (CF 1010) ------------------------------
    assert reg.CAF_BROWSER_UA and reg.CAF_BROWSER_UA.startswith("Mozilla/"), \
        "CAF_BROWSER_UA must carry a browser User-Agent (the CF-1010 edge fix)"

    # ---- plan: offline, no network, exact drop ----
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = plan(out=io.StringIO())
    assert rc == EX_OK, "plan must exit 0"
    p = json.loads(buf.getvalue())
    assert p["action"] == "archive" and p["execute_dropped"] is True
    assert p["execute_required"] is True and p["dry_run"] is True
    assert p["targets"]["board"] == ["...lden"]
    assert p["targets"]["ledger"] == ["...lden"]
    assert "pit-" not in buf.getvalue()

    dev.write("attack_no_execute self-test: OK (archive authority pinned "
              "(golden_absent: action 'archive', targets board/ledger, "
              "execute-required law); canonical no-execute attack record "
              "dropping the ONE execute gate over synthetic material with "
              "every id masked to the last-4 marker; judge FAILs the "
              "no-execute read with exit 5 through EVERY archive authority "
              "naming the dropped gate while the golden execute-required "
              "dry-run control PASSES exit 0; execute-present / "
              "mutation-claiming / drifted-pin / non-mapping records FAIL; "
              "payload gate ships the one-no-execute attack and REFUSES "
              "under a regressed authority while payload-true control "
              "PASSes the golden contract; 4 attack fixtures refused "
              "(double-gate / non-archive ACTION / census-less record / "
              "non-mapping); CAF_BROWSER_UA pinned; never a token shape, "
              "never a full id; plan offline)\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="attack_no_execute.py",
        description="Attack fixture — archive without --execute, must FAIL "
                    "(Skill 59, U06 tooling): the adversarial sibling of the "
                    "Trevor-gated archive ACTION, shipping the deterministic "
                    "no-execute read (the canonical archive ACTION record "
                    "with the ONE execute-gate flag dropped, both archive "
                    "targets present over synthetic material, every id "
                    "masked) that every archive gate must refuse, and the "
                    "fail-closed offline gates that prove it (the golden "
                    "execute-required dry-run control PASSES).")
    ap.add_argument("--record", default=None,
                    help="archive ACTION record to judge (verify); defaults "
                         "to the first stdin line (e.g. a mutation-surface "
                         "record JSON | attack_no_execute.py --live)")
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
                sys.stderr.write("[attack-no-execute] no record given "
                                 "(--record or stdin) — nothing to judge.\n")
                return EX_ERR
            try:
                record = json.loads(raw)
            except ValueError as exc:
                sys.stderr.write("[attack-no-execute] the record on stdin is "
                                 "not valid JSON: %s\n" % exc)
                return EX_ERR
            return verify_archive(record, out=sys.stderr)
        return payload()
    except FixtureError as exc:
        sys.stderr.write("[attack-no-execute] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[attack-no-execute] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
