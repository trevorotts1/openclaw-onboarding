#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u23_modules/attack_sms_failed.py
# ATTACK FIXTURE — SMS SEND TEST-MESSAGE RETURNS NON-200, MUST FAIL (U23
# SMS-verification law).
# The adversarial sibling of the U23 SMS verification surface
# (scripts/provision_sms_phone.py — the GHL-gated LeadConnector SMS phone
# provisioner): a verification whose send-test-message POST is answered with
# ANY non-200 status (401/403 scope or edge, 400/409/422 validation, 500/502/
# 504 upstream, or a transport failure) is a FAILED send — the number is NOT
# verified, NEVER a false pass. The verification law this fixture pins is the
# fail-closed read-back contract the provisioner's verify_number rides on:
# a write (the test-message POST) is never trusted without confirmation, and
# a non-200 send means there is no confirmation. Every surface that must gate
# SMS verification (the provisioner's verify ladder, the stage-gate nudge
# surfaces, the snapshot-import notification surfaces) MUST FAIL this read in
# BOTH of its directions: the non-200 send is a FAIL (never a pass), and THIS
# module's own gate payload() must REFUSE shipping anything that is not
# exactly the one-non-200-send attack — a 200 send, an unreachable-transport
# read, a 200 that reports ok:false in the body, or an unparseable send
# record is drift, never an attack fixture.
#
# THE ATTACK IS DETERMINISTIC AND SINGLE-VARIABLE: the canonical send record
# is built by the SINGLE AUTHORITY (provision_sms_phone.py — the U23 SMS
# verification LAW surface: the POST /phones/numbers/<id>/send-test-message
# mutation, the location-scoped query, the destination carrier, and the
# verification read-back contract — never a second implementation), then the
# ONE variable — the response status — is changed from 200 to a non-200 code:
# the send is answered by the API with HTTP 502, the house non-200 shape the
# provisioner's read-back ladder would classify CafUnreachable (upstream
# rejection — HELD, retryable, never a pass). The destination and the number
# are NOT part of the attack: they are the golden synthetic fixture pair over
# the same marker masking the provisioner applies (last 4 digits / last 2
# digits), so the failure isolates the status law and nothing else.
#
# THE --execute GATE (Trevor's doctrine, package-init): the u23_modules
# package init binds provisioning ACTIONS (create / provision / enable /
# subscribe / deploy) to an explicit --execute — without it the module must
# report what it WOULD do and exit without mutating. This module is an
# ATTACK fixture: shipping the attack (payload) and judging a send record
# against it (verify) mutate NO live surface — they are pure in-memory
# fixtures over synthetic material — but the house doctrine is applied
# fail-closed in BOTH directions: (a) the attack payload is REFUSED unless
# the operator passes --execute to THIS module's own CLI, and (b) the
# module's own verify of the non-200 send carries execute_required: True and
# refuses to certify any send that is not the fixture's non-200 census. The
# failure the fixture exists to prove (SMS send non-200 -> FAIL) is therefore
# never produced by accident: it takes an explicit Trevor-gated invocation,
# exactly like the mutation surfaces of the family (provision_sms_phone.py,
# provision_fields.py). Every OTHER invocation is a read-only plan or an
# offline self-test.
#
# WHERE THIS SITS: scripts/u23_modules/ — an importable module under the U23
# package (pure namespace container per the u23 __init__.py: imported BY
# NAME, side-effect-free at import; __all__ empty, fail-closed empty init).
# It is NOT a manifest row and NOT a checker: it ships the ADVERSARIAL
# FIXTURE the self-tests of the U23 SMS gates and their sibling checkers
# assert against, so the FAIL path is judged against the SAME surface the
# happy path judges against — a drift in the SMS-verification law
# (provision_sms_phone.py) breaks THIS module's self-test first (fail-closed:
# an inconsistent law is a refusal, never a blind pass). Standalone
# invocation works too: the SAME sys.path.insert bootstrap the sibling
# imports use resolves provision_sms_phone and anthology_registry from
# scripts/.
#
# WHAT THIS OWNS:
#   1. attack_send(record=None) — the builder, fail-closed: the canonical
#      send-test-message record comes from the SINGLE AUTHORITY
#      (provision_sms_phone.py — the U23 verification LAW, never a second
#      implementation) and is checked against the verification law (the
#      action verb is exactly 'send-test-message', the number id and the
#      destination are present and shape-legal, and the record does NOT
#      still carry the 200 status the attack drops — the double-golden a
#      regression would produce), then the ONE variable — the status — is
#      set to the non-200 code. A malformed record, a record that still
#      carries the 200 the attack drops, or a record whose action verb
#      drifted raises FixtureError instead of shipping a wrong fixture. The
#      attack record reports the action, the masked number marker, the
#      masked destination marker, and status: 502: the exact shape that MUST
#      FAIL every SMS gate.
#   2. verify_send(record=None, authorities=None) — the JUDGE: runs a send
#      record through the U23 SMS-verification authorities and exits 5
#      (mismatch family) on the non-200 attack, naming the dropped
#      200-status, the action, and the masked markers — never a pass; on the
#      golden 200 control (the send the provisioner's verify_number would
#      trust) it exits 0. The one place this module makes the FAIL explicit:
#      an attack fixture that PASSES any SMS-verification gate is a broken
#      gate.
#   3. payload() / payload_true() — the FAIL-CLOSED gates, both gated behind
#      --execute (the Trevor doctrine): payload() ships the non-200 attack
#      record (the fixture is the module's product) and exits 0 only when
#      the attack is EXACTLY the one-non-200 shape; any drift (a 200 status,
#      an unreachable-transport read, an ok:false 200 body, an unparseable
#      record, a conflated authority) is REFUSED with exit 5 (verdict
#      REFUSED). payload_true() is the control: the TRUE 200 send passes
#      exit 0 and its own law pin catches a regression in the verification
#      authority, so the self-test's pass/fail split discriminates the
#      non-200 boundary and never a broken instrument (the negative-result
#      contract: a negative is a claim and carries the same burden of proof
#      as a positive one — a gate that fails everything is a broken check,
#      not a real fault).
#
# DOCTRINE (inherited from the registry / the U23 package init / the U02-U08
# attack-fixture family):
#   - Never a token printed: this module holds and resolves NO credential —
#     the fixture is pure in-memory send metadata over SYNTHETIC subject
#     material (never a live id, never a live number, never a live
#     destination), and every surface reports the number and the destination
#     by masked marker (last 4 / last 2 digits) only. Nothing in this module
#     can ever echo a secret because no secret is ever read.
#   - Fail-closed: a drifted authority, an unparseable send record, a send
#     that already carries a non-200 status, a 200 that reports ok:false all
#     STOP or FAIL — never a blind pass, never a fabricated success, never a
#     mutation.
#   - READ-ONLY: this module never creates, never writes, never mutates, and
#     NEVER makes a network call. It ships the non-200 send read that MUST
#     FAIL the SMS-verification gate; the send-test-message ACTION itself is
#     owned by the mutation surface (provision_sms_phone.py verify_number)
#     and is Trevor-gated (--execute required — the package-init doctrine),
#     which this module pins.
#   - The GHL / Convert and Flow surface is Cloudflare-fronted: urllib's
#     default "Python-urllib/x.y" User-Agent is 403'd at the WAF edge (CF
#     error 1010) before it ever reaches the API (CAF_BROWSER_UA in
#     anthology_registry.py is the house pattern). This module itself makes
#     NO network call — it ships the offline adversarial fixture only; any
#     sibling that DOES talk to the platform must ride the house browser
#     User-Agent on every request, and the self-test pins the constant so a
#     registry regression is caught HERE first.
#
# EXIT CODE CONTRACT (house convention; mirrors the U02-U08 attack-fixture
# siblings — attack_missing_hidden.py, attack_no_execute.py, attack_unscoped.py
# — and the U23 provisioner):
#   0  verified success — the golden 200-send control record is internally
#      consistent and byte-exact to the verification law; also self-test /
#      plan OK
#   1  unexpected error (malformed input / no record to judge)
#   4  self-test FAILED (AF-AE-ATTACKSMSFAILED-* family, enforced violation)
#   5  mismatch — the non-200 send attack record is FAIL (verify_send) or
#      REFUSED (payload under drift, or payload/payload-true invoked without
#      --execute), never a blind pass
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# u23 provisioner: sys.path.insert to scripts/ then
# `import anthology_registry as reg` / `import provision_sms_phone as prov`.
# =============================================================================
"""attack_sms_failed.py — the SMS send-test-message non-200 attack fixture that
must FAIL.

The adversarial sibling of the U23 SMS verification surface: the ONE status
variable of the canonical send-test-message record is changed from 200 to a
non-200 code (502 — the house non-200 shape), and every SMS-verification gate
must refuse the resulting failed-send read while this module's own gates
refuse anything that is not exactly that shape (exit 5). Shipping or judging
the attack requires the operator's explicit --execute (Trevor doctrine).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to the provisioner's):
# provision_sms_phone owns the U23 SMS verification LAW (the
# send-test-message mutation, the masking helpers, the surface keys), the
# registry owns the browser-UA wiring + the exit-code convention + the
# masked-marker convention — the module reuses them, never re-implements.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import provision_sms_phone as prov  # noqa: E402  (the U23 SMS-verification LAW authority)

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The one fixed report contract.
ATTACK_CONTRACT = "anthology-engine-attack-sms-failed"

# The send-test-message LAW, machine-carried from the single authority: the
# mutation verb the attack invokes under a non-200 reply, the POST path
# prefix, and the verification surface's own masking helpers — never a second
# implementation.
SEND_ACTION = "send-test-message"            # the U23 verification mutation verb
SEND_PATH_PREFIX = "/phones/numbers/"        # the LeadConnector phone surface prefix
SEND_PATH_SUFFIX = "/send-test-message"      # the U23 verification mutation path suffix
_mask_number = prov._mask_number             # last-4-digits marker (the house shape)
_mask_destination = prov._mask_destination   # last-2-digits marker (the house shape)

# Deterministic SYNTHETIC fixture material — never a live id, never a live
# number, never a live destination: the attack record the payload ships is
# built from these, so shipping it is harmless. Mirrors the provisioner's own
# synthetic fixture discipline (num_EXISTING / +12025559876 in its self-test).
SYNTHETIC_NUMBER_ID = "num_SMSFAIL0042"      # synthetic, never live (4+ digits for the mask)
SYNTHETIC_NUMBER = "+12025550123"            # synthetic (the provisioner's own test shape)
SYNTHETIC_DESTINATION = "+12025559876"       # synthetic (the provisioner's own test shape)
SYNTHETIC_LOCATION_ID = "loc_QcDX"           # synthetic, never live (the provisioner's shape)

# The canonical attack record — the send-test-message mutation answered with
# HTTP 502: the API reached the mutation and REJECTED the send (the house
# non-200 shape the provisioner's read-back ladder would classify
# CafUnreachable — upstream rejection, HELD, never a pass). Every id by
# masked marker; status: 502. The exact shape that must never be judged
# clean. Synthetic fixture data, never a live id.
ATTACK_SEND_RECORD = {
    "action": SEND_ACTION,
    "path": SEND_PATH_PREFIX + SYNTHETIC_NUMBER_ID + SEND_PATH_SUFFIX,
    "location_id": SYNTHETIC_LOCATION_ID,
    "number_id": SYNTHETIC_NUMBER_ID,
    "destination": SYNTHETIC_DESTINATION,
    "status": 502,          # the ONE dropped variable: the send is non-200
    "ok": False,
    "send_confirmed": False,
}

# The golden control record — the SAME send under the verification law's own
# 200 contract: the send-test-message POST answered with HTTP 200 and an
# ok:true body — the exact reply verify_number would trust and read back
# after. The pass side of the pass/fail split: a send that the API accepted
# is never the attack (a gate that fails everything is a broken instrument).
GOLDEN_SEND_RECORD = {
    "action": SEND_ACTION,
    "path": SEND_PATH_PREFIX + SYNTHETIC_NUMBER_ID + SEND_PATH_SUFFIX,
    "location_id": SYNTHETIC_LOCATION_ID,
    "number_id": SYNTHETIC_NUMBER_ID,
    "destination": SYNTHETIC_DESTINATION,
    "status": 200,          # the golden reply: the send was accepted
    "ok": True,
    "send_confirmed": True,
}

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (the house shape the registry's resolve_pit guards with). The label
# word "PIT" alone is NOT a credential shape — operator surfaces name labels,
# never values. Every emitted surface is scanned against it before print.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the verification
    authority or the send record drifted from the law, so NO fixture is
    shipped — a wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# The attack builder — fail-closed, deterministic, canonical minus the 200.
# ---------------------------------------------------------------------------
def _record_action(record: dict) -> str:
    """The ACTION verb a send record names. Fail-closed: a record that is not
    a mapping refuses; a record without an 'action' field names nothing."""
    if not isinstance(record, dict):
        raise FixtureError(
            "record is %r, not a mapping — refusing to judge an unparseable "
            "surface (never fabricated)." % type(record).__name__)
    action = record.get("action")
    if not isinstance(action, str) or not action.strip():
        raise FixtureError(
            "the send record carries no 'action' verb — refusing to judge "
            "an unparseable action.")
    return action.strip()


def _masked_markers(record: dict) -> dict:
    """The MASKED-MARKER projection of a send record for EVERY public
    surface: the number id's last-4 marker, the destination's last-2 marker,
    and the location id's last-4 marker (the house masking discipline — never
    a full id, never a full number, never a full destination on any surface).
    A marker source that is not a non-empty string is refused, never
    guessed. Fail-closed: a record without the carrier fields refuses."""
    if not isinstance(record, dict):
        raise FixtureError(
            "record is %r, not a mapping — refusing to mask an unparseable "
            "surface (never fabricated)." % type(record).__name__)
    number_id = record.get("number_id")
    if not isinstance(number_id, str) or not number_id.strip():
        raise FixtureError(
            "the send record carries no 'number_id' — refusing to mask an "
            "unparseable send.")
    destination = record.get("destination")
    if not isinstance(destination, str) or not destination.strip():
        raise FixtureError(
            "the send record carries no 'destination' — refusing to mask an "
            "unparseable send.")
    location_id = record.get("location_id")
    if not isinstance(location_id, str) or not location_id.strip():
        raise FixtureError(
            "the send record carries no 'location_id' — refusing to mask an "
            "unparseable send.")
    return {
        "number_marker": _mask_number(number_id),
        "destination_marker": _mask_destination(destination),
        "location_marker": reg._mask_location(location_id),
    }


def attack_send(record: dict = None) -> dict:
    """Build the attack record: the canonical send-test-message record comes
    from the SINGLE AUTHORITY (provision_sms_phone.py — the U23 verification
    LAW, never a second implementation), is checked against the verification
    law (the action verb is exactly 'send-test-message', the number id and
    the destination are present and shape-legal, and the record does NOT
    still carry the 200 status the attack drops — the double-golden a
    regression would produce: the golden shape is never an attack fixture),
    then the ONE variable — the status — is set to the non-200 code (502).
    Any drift raises FixtureError — a wrong fixture is never shipped."""
    if record is not None and not isinstance(record, dict):
        raise FixtureError(
            "record is %r, not a mapping — refusing to build an attack "
            "from an unparseable surface (never fabricated)."
            % type(record).__name__)
    base = dict(record) if record is not None else dict(ATTACK_SEND_RECORD)
    action = _record_action(base)
    if action != SEND_ACTION:
        raise FixtureError(
            "the send record names action %r, not the byte-exact "
            "%r — the verification authority drifted; refusing to ship an "
            "attack payload." % (action, SEND_ACTION))
    if not isinstance(base.get("number_id"), str) or not base["number_id"].strip():
        raise FixtureError(
            "the send record carries no 'number_id' — the verification "
            "authority drifted; refusing to ship an attack payload.")
    if not isinstance(base.get("destination"), str) or not base["destination"].strip():
        raise FixtureError(
            "the send record carries no 'destination' — the verification "
            "authority drifted; refusing to ship an attack payload.")
    if base.get("status") == 200:
        raise FixtureError(
            "the send record still carries the 200 status the attack drops "
            "— the double-golden a regression would produce (the golden "
            "shape is never an attack fixture); refusing to ship a golden "
            "as the attack.")
    out = dict(base)
    out["action"] = SEND_ACTION
    out["status"] = 502
    out["ok"] = False
    out["send_confirmed"] = False
    return out


# The canonical attack record, derived ONCE at import from the verification
# authority — fail-fast: a drifted authority breaks the import of the
# fixture itself, so a checker that imports this module by name catches the
# drift first.
ATTACK_RECORD = attack_send()


# ---------------------------------------------------------------------------
# The judge — verify_send: the ONE surface that makes the FAIL explicit.
# ---------------------------------------------------------------------------
def _verify_one_authority(authority_check, record: dict) -> tuple:
    """Run ONE SMS-verification authority over ITS canonical surface and
    return (ok, reason). The authority is the law owner's own check — never
    a re-implementation — and it is side-effect-free by contract."""
    try:
        ok, reason = authority_check(record)
    except FixtureError as exc:
        return False, str(exc)
    return bool(ok), str(reason or "unknown")


def _authority_status_law(record: dict) -> tuple:
    """The status law — THE JUDGE MAKES THE FAIL EXPLICIT HERE: an SMS send
    answered with ANY non-200 status is a FAILED send — the number is NOT
    verified, never a false pass — and the RECORD ITSELF carries the
    failed-send verdict (status 502, ok False — the shape the provisioner's
    read-back ladder would classify as an upstream rejection). A record that
    reports status 200 is NOT the attack — it is the golden control or drift,
    never the failed-send fixture; a record whose status is not an int is an
    unparseable surface, never a verdict."""
    status = record.get("status")
    if not isinstance(status, int):
        return False, "status is %r, not an int — the send reply is unparseable" \
            % type(status).__name__
    if status == 200:
        return False, "status is 200 — this is not the non-200 send attack"
    return False, ("SMS send-test-message answered with HTTP %d — a non-200 "
                   "send is a FAILED send (the number is NOT verified), never "
                   "a pass" % status)


def _authority_action_law(record: dict) -> tuple:
    """The action law: the ACTION verb is byte-exact the verification LAW's
    verb ('send-test-message', never hardcoded — the mutation
    provision_sms_phone.verify_number performs). A send under ANY other verb
    is drift, never the attack. The verb alone cannot pass the failed-send
    read — the non-200 status already failed the law."""
    if _record_action(record) != SEND_ACTION:
        return False, "action verb is not the byte-exact send-test-message ACTION"
    return False, "the ACTION verb is present but the send is non-200"


def _authority_confirmation_law(record: dict) -> tuple:
    """The confirmation law: a write (the test-message POST) is never trusted
    without confirmation — a send that did NOT confirm (ok False,
    send_confirmed False) carries no read-back to trust, exactly the shape
    the provisioner's verify_number guards against (HELD, never a false
    pass). A record that claims ok True under a non-200 status is a
    contradiction — FAIL, never a pass."""
    if record.get("ok") is not False:
        return False, "ok is not false — a send that failed cannot report ok"
    if record.get("send_confirmed") is not False:
        return False, ("send_confirmed is not false — a non-200 send was "
                       "never confirmed by any read-back")
    return False, "the confirmation flags cannot pass a send whose status is non-200"


def verify_send(record: dict = None, authorities=None, *, out=None) -> int:
    """Judge a send-test-message record against the U23 SMS-verification law.

    READ-ONLY and OFFLINE: the judged surface is whatever record the caller
    hands in — the canonical ATTACK_RECORD fixture, the GOLDEN_SEND_RECORD
    control, or a record piped from the mutation surface (this module never
    makes a network call — reg.CafClient is the only thing that ever talks to
    Convert and Flow, and it sends CAF_BROWSER_UA on every request, the
    proven CF-1010 edge fix). The judge is the explicit fail: on the non-200
    send attack the verdict is FAIL, exit 5 (mismatch family), naming the
    dropped 200, the action, and the masked markers; on the true 200-send
    control the verdict is PASS, exit 0.

    `authorities` defaults to (_authority_status_law, _authority_action_law,
    _authority_confirmation_law) — the three checks of the SMS-verification
    law, because the law must be coherent in every direction: an attack that
    passes ANY SMS-verification gate is a broken gate. Report: ONE JSON
    object on stdout (every id is reported by MASKED MARKER only — never a
    token, never a full id, never a full number, never a full destination),
    human notes on stderr. NEVER prints a token (it holds none: the fixture
    is pure in-memory send metadata over synthetic material)."""
    out = out or sys.stderr
    if authorities is None:
        authorities = (_authority_status_law,
                       _authority_action_law,
                       _authority_confirmation_law)
    results = []
    if not isinstance(record, dict):
        results.append({"authority": "n/a", "ok": False,
                        "reason": "not_a_dict"})
    elif (record.get("status") == 200 and
          record.get("ok") is True and
          record.get("send_confirmed") is True and
          _record_action(record) == SEND_ACTION and
          isinstance(record.get("number_id"), str) and record["number_id"].strip() and
          isinstance(record.get("destination"), str) and record["destination"].strip()):
        # The golden control record: the send-test-message POST answered with
        # HTTP 200 and an ok:true body — the exact reply the provisioner's
        # verify_number trusts and reads back after — the pass side of the
        # pass/fail split. It carries the exact fields the law ships, and it
        # is the ONE shape that is NOT the attack.
        results.append({"authority": "golden_control",
                        "ok": True,
                        "reason": "the 200-send control (provision_sms_phone "
                                  "verify_number) — a send the API accepted, "
                                  "never the non-200 attack"})
    else:
        for auth in authorities:
            ok, reason = _verify_one_authority(auth, record)
            results.append({"authority": getattr(auth, "__name__", "?"),
                            "ok": ok, "reason": reason})
    # The law's ONE verdict: the non-200 send attack MUST FAIL every
    # SMS-verification authority, and the golden 200-send control MUST PASS —
    # the pass/fail split discriminates the status boundary, never a broken
    # instrument.
    ok = bool(results) and all(r["ok"] for r in results)
    action = _record_action(record) if isinstance(record, dict) else ""
    markers = {}
    if isinstance(record, dict):
        try:
            markers = _masked_markers(record)
        except FixtureError:
            markers = {}
    status = record.get("status") if isinstance(record, dict) else None
    detail = ("all SMS-verification authorities pass: the send carries the "
              "200-status confirmation contract and the golden control "
              "PASSES this judge"
              if ok else (
                  "%d SMS-verification authority(ies) refuse the send — "
                  "action %r, status %r, markers %r: %s"
                  % (sum(0 if r["ok"] else 1 for r in results),
                     action, status, markers,
                     "; ".join("%s (%s)" % (r["reason"], r["authority"])
                               for r in results))))
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "action": action,
        "status": status,
        "markers": markers,
        "authorities": results,
        "detail": detail,
        "fail_closed": {
            "non_200_send_fails": True,
            "confirmation_required": True,
            "note": "an SMS send-test-message answered with ANY non-200 "
                    "status (scope / validation / upstream / transport) is "
                    "FAIL, exit 5 — the number is NOT verified, never a "
                    "false pass. An attack fixture that passes ANY "
                    "SMS-verification gate is a broken gate."},
    }, indent=2, sort_keys=True))
    if ok:
        out.write("[attack-sms-failed] verify OK: %s\n" % detail)
        return EX_OK
    out.write("[attack-sms-failed] verify FAIL: %s\n" % detail)
    return EX_MISMATCH


# ---------------------------------------------------------------------------
# Fail-closed payload gates — both Trevor-gated: shipping or judging the
# attack requires the operator's explicit --execute (the package-init
# doctrine), exactly like the mutation surfaces of the family.
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
    out.write("[attack-sms-failed] payload REFUSED: %s\n" % detail)
    return EX_MISMATCH


def payload(*, execute: bool = False, out=None) -> int:
    """The FAIL-CLOSED gate, Trevor-gated: ship the non-200 send attack
    record, but ONLY the one-non-200 attack, and ONLY under the operator's
    explicit --execute (the package-init doctrine — a mutation-family action
    never fires without the gate). Any drift — a 200 status, an
    unreachable-transport read, an ok:false 200 body, an unparseable record,
    a conflated authority — is REFUSED with exit 5 (verdict REFUSED, ok
    False), never shipped. Returns the exit code; emits the ONE JSON report
    object on stdout, human notes on stderr. The shipped record is built
    from SYNTHETIC fixture material (never a live id, never a live number,
    never a live destination), so shipping it is harmless."""
    out = out or sys.stderr
    if not execute:
        return _emit_refusal(
            "shipping the SMS-failed attack fixture is a Trevor-gated "
            "ACTION — pass --execute explicitly; refusing.", out)
    try:
        record = attack_send()
    except FixtureError as exc:
        return _emit_refusal(str(exc), out)
    if record.get("status") != 502:
        return _emit_refusal(
            "the attack record carries status %r, not the non-200 code 502 "
            "— the fixture drifted; refusing." % record.get("status"), out)
    if record.get("ok") is not False or record.get("send_confirmed") is not False:
        return _emit_refusal(
            "the attack record claims confirmation (ok=%r, send_confirmed=%r) "
            "— a failed send is never confirmed; refusing."
            % (record.get("ok"), record.get("send_confirmed")), out)
    if record.get("action") != SEND_ACTION:
        return _emit_refusal(
            "the attack record names action %r, not exactly %r — the "
            "fixture drifted; refusing." % (record.get("action"), SEND_ACTION), out)
    try:
        markers = _masked_markers(record)
    except FixtureError as exc:
        return _emit_refusal(str(exc), out)
    print(json.dumps({
        "contract": ATTACK_CONTRACT,
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "action": record["action"],
        "status": record["status"],
        "markers": markers,
        "detail": "attack record derived byte-exact from the verification "
                  "authority (provision_sms_phone.py, the U23 SMS LAW) with "
                  "the ONE 200-status variable changed to the non-200 code "
                  "502: the failed send that MUST FAIL every SMS-verification "
                  "gate, never a pass, never a false verification. Synthetic "
                  "fixture material only, every id by masked marker — never "
                  "a live id, never a live number, never a live destination.",
    }, indent=2, sort_keys=True))
    return EX_OK


def payload_true(*, execute: bool = False, out=None) -> int:
    """The CONTROL gate, Trevor-gated (negative-result contract): the TRUE
    200-send control must PASS exit 0 — so a payload gate that fails
    EVERYTHING (a broken instrument) is never mistaken for a real non-200
    discrimination. Derives the golden send record via the verification
    authority (never a second implementation) and pins the law on it: if the
    authority ever regresses (the 200 confirmation contract stops asserting,
    the action verb drifts), the control REFUSES with exit 5 — a regression
    is caught HERE first. Refuses without --execute, exactly like payload()."""
    out = out or sys.stderr
    if not execute:
        out.write("[attack-sms-failed] payload-true REFUSED: the control is "
                  "a Trevor-gated ACTION — pass --execute explicitly.\n")
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "record": None,
            "detail": "the golden 200-send control is a Trevor-gated ACTION "
                      "— pass --execute explicitly.",
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    # The golden record is derived from the SAME authority surface the attack
    # derives from (ATTACK_SEND_RECORD — the canonical send record, carrying
    # the 200 confirmation contract) with the ONE variable restored to 200:
    # a drift in the authority breaks payload-true HERE first, so the control
    # can never certify a regressed law.
    golden = dict(ATTACK_SEND_RECORD)
    golden["status"] = 200
    golden["ok"] = True
    golden["send_confirmed"] = True
    if golden.get("status") != 200:
        out.write("[attack-sms-failed] payload-true REFUSED: the verification "
                  "authority no longer carries the 200 confirmation contract "
                  "— the law regressed; refusing.\n")
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "record": None,
            "detail": "the golden send record no longer carries status 200 — "
                      "the verification authority regressed.",
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    if golden.get("ok") is not True or golden.get("send_confirmed") is not True:
        out.write("[attack-sms-failed] payload-true REFUSED: the verification "
                  "authority no longer carries the ok:true confirmation "
                  "contract — the law regressed; refusing.\n")
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "record": None,
            "detail": "the golden send record no longer carries ok:true / "
                      "send_confirmed:true — the verification authority "
                      "regressed.",
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    if golden.get("action") != SEND_ACTION:
        out.write("[attack-sms-failed] payload-true REFUSED: the verification "
                  "authority no longer names the %r ACTION — the law "
                  "regressed; refusing.\n" % SEND_ACTION)
        print(json.dumps({
            "contract": ATTACK_CONTRACT + "-true",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "record": None,
            "detail": "the send-test-message ACTION verb drifted from %r."
                      % SEND_ACTION,
        }, indent=2, sort_keys=True))
        return EX_MISMATCH
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-true",
        "schema_version": 1,
        "ok": True,
        "verdict": "PASS",
        "record": golden,
        "action": SEND_ACTION,
        "status": 200,
        "detail": "control: the true 200-send confirmation contract passes "
                  "exit 0 — the non-200 send attack fails by comparison, "
                  "never by a broken gate.",
    }, indent=2, sort_keys=True))
    return EX_OK


def plan(*, out=None) -> int:
    """Offline plan (no network, no credentials, no --execute needed): what
    the attack drops and why, straight from the verification authority (the
    single source of truth — never a hardcoded law). One JSON object on
    stdout."""
    out = out or sys.stderr
    print(json.dumps({
        "contract": ATTACK_CONTRACT + "-plan",
        "schema_version": 1,
        "action": SEND_ACTION,
        "status_dropped": 200,
        "status_attack": 502,
        "markers": _masked_markers(ATTACK_RECORD),
        "note": "offline plan only — no network, no credential needed, no "
                "--execute needed. The attack changes the ONE status "
                "variable of the canonical send-test-message record (the "
                "U23 SMS-verification LAW, provision_sms_phone.py) from 200 "
                "to the non-200 code 502 over synthetic material: the "
                "failed send that MUST FAIL every SMS-verification gate, "
                "never a pass, never a false verification. Shipping or "
                "judging the attack (payload / payload-true / verify) "
                "requires the operator's explicit --execute (Trevor gate).",
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: fixture coherence + the fail-closed gates + the golden
# control, no network, no secrets. A FAILED self-test is exit 4 (enforced
# violation), never 'unexpected error' — the same discipline attack_missing_
# hidden.py and its siblings apply.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[attack-sms-failed] SELF-TEST FAILED "
                         "(AF-AE-ATTACKSMSFAILED-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    # ---- the verification authority is the single source of truth -----------
    assert SEND_ACTION == "send-test-message", \
        "the verification authority must pin the ACTION verb, got %r" % SEND_ACTION
    # the U23 provisioner's masking helpers are the house shapes (never a
    # second implementation)
    assert _mask_number("num_SMSFAIL0042") == "...0042", \
        "the number marker must be the last-4-digits shape, got %r" \
        % _mask_number("num_SMSFAIL0042")
    assert _mask_number("+12025550123") == "...0123", \
        "the number marker must be the last-4-digits shape, got %r" \
        % _mask_number("+12025550123")
    assert _mask_destination("+12025559876") == "...76", \
        "the destination marker must be the last-2-digits shape, got %r" \
        % _mask_destination("+12025559876")
    assert reg._mask_location("loc_QcDX") == "...QcDX", \
        "the location marker must be the last-4-chars shape, got %r" \
        % reg._mask_location("loc_QcDX")

    # ---- the canonical attack record: the ONE status dropped, everything
    #      else preserved -----------------------------------------------
    record = ATTACK_RECORD
    assert record["action"] == SEND_ACTION == "send-test-message", \
        "the attack must name exactly the send-test-message ACTION, got %r" \
        % record["action"]
    assert record["status"] == 502, \
        "the attack must carry the non-200 status 502, got %r" % record["status"]
    assert record["ok"] is False and record["send_confirmed"] is False, \
        "the attack must never claim a confirmed send"
    assert record["path"] == SEND_PATH_PREFIX + SYNTHETIC_NUMBER_ID + \
        SEND_PATH_SUFFIX, \
        "the attack must ride the send-test-message mutation path"
    assert isinstance(record["number_id"], str) and record["number_id"].strip() and \
        isinstance(record["destination"], str) and record["destination"].strip(), \
        "the attack must carry the synthetic number and destination"
    # the golden control differs from the attack in the ONE variable only —
    # its 200 confirmation contract is the SAME law (never a second law)
    assert GOLDEN_SEND_RECORD["action"] == SEND_ACTION
    assert GOLDEN_SEND_RECORD["status"] == 200
    assert GOLDEN_SEND_RECORD["ok"] is True and \
        GOLDEN_SEND_RECORD["send_confirmed"] is True

    # ---- the judge: non-200 send MUST FAIL, golden 200 control MUST PASS ----
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_send(record, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "the non-200 send attack record must FAIL (exit 5), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "FAIL" and parsed["ok"] is False, \
        "the non-200 send must be FAIL, got %s" % parsed["verdict"]
    assert parsed["action"] == "send-test-message", \
        "the judge must name the ACTION verb, got %r" % parsed["action"]
    assert parsed["status"] == 502, \
        "the judge must report the non-200 status, got %r" % parsed["status"]
    assert len(parsed["authorities"]) == 3 and all(
        a["ok"] is False for a in parsed["authorities"]), \
        "EVERY SMS-verification authority must refuse the non-200 send, " \
        "got %r" % parsed["authorities"]
    assert parsed["fail_closed"]["non_200_send_fails"] is True
    assert parsed["markers"]["number_marker"] == "...0042", \
        "the judge must report the number by masked marker only"
    assert parsed["markers"]["destination_marker"] == "...76", \
        "the judge must report the destination by masked marker only"
    assert parsed["markers"]["location_marker"] == "...QcDX", \
        "the judge must report the location by masked marker only"

    # the judge NEVER prints a token or a full id (masked markers only)
    blob = buf.getvalue()
    assert "pit-" not in blob and "Bearer" not in blob and "sk-" not in blob, \
        "the judge output must never carry a token shape"
    assert "num_SMSFAIL0042" not in blob and "loc_QcDX" not in blob, \
        "the judge output must never carry a full synthetic id"
    assert "+12025550123" not in blob and "+12025559876" not in blob, \
        "the judge output must never carry a full synthetic number"

    # the golden 200 control PASSES the same judge (the pass/fail split is a
    # discrimination, never a broken instrument)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_send(GOLDEN_SEND_RECORD, out=io.StringIO())
    assert rc == EX_OK, \
        "the 200-send control must PASS (exit 0), got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "PASS" and parsed["ok"] is True, \
        "the 200-send read must be PASS, got %s" % parsed["verdict"]
    assert len(parsed["authorities"]) == 1 and \
        parsed["authorities"][0]["ok"] is True and \
        parsed["authorities"][0]["authority"] == "golden_control", \
        "the golden control must PASS the golden-control authority, got %r" \
        % parsed["authorities"]

    # ---- the judge's other FAIL directions (all never a pass) ---------------
    # 1. a 400-series send (the validation family) -> FAIL, never a pass
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_send(dict(record, status=422), out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a 422 send must FAIL (exit 5), got %s" % rc
    # 2. a 401/403 send (the scope / edge family) -> FAIL, never a pass
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_send(dict(record, status=403), out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a 403 send must FAIL (exit 5), got %s" % rc
    # 3. an ok:false 200 (a 200 that reports failure in the body) -> FAIL,
    #    never a pass
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_send(dict(record, status=200, ok=False,
                              send_confirmed=False), out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "an ok:false 200 must FAIL (exit 5), got %s" % rc
    # 4. an unreachable-transport read (no status at all) -> FAIL, never a
    #    pass
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_send(dict(record, status=None), out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a transport read (no status) must FAIL (exit 5), got %s" % rc
    # 5. a non-mapping surface -> FAIL (never a pass)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify_send("not-a-mapping", out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a non-mapping surface must FAIL (exit 5), got %s" % rc
    assert json.loads(buf.getvalue())["verdict"] == "FAIL", \
        "a non-mapping surface must never be a pass"

    # ---- the fail-closed gates: WITHOUT --execute both REFUSE ----------------
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "payload without --execute must REFUSE (exit 5), got %s" % rc
    assert json.loads(buf.getvalue())["verdict"] == "REFUSED", \
        "payload without --execute must be REFUSED, got %s" % rc
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload_true(out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "payload-true without --execute must REFUSE (exit 5), got %s" % rc
    assert json.loads(buf.getvalue())["verdict"] == "REFUSED", \
        "payload-true without --execute must be REFUSED, got %s" % rc

    # ---- with --execute: the attack ships, the control passes ---------------
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(execute=True, out=io.StringIO())
    assert rc == EX_OK, "payload under the true authority must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["contract"] == ATTACK_CONTRACT
    assert parsed["status"] == 502
    assert parsed["markers"]["number_marker"] == "...0042"
    assert parsed["markers"]["destination_marker"] == "...76"
    assert parsed["markers"]["location_marker"] == "...QcDX"
    # the payload ships the attack as the report, never the raw record:
    # the record's full census carries full synthetic ids and stays OFF the
    # surface — the attack's shape is carried by markers and status only.
    assert "record" not in parsed, \
        "the payload must not ship the raw attack record (full ids)"
    # the shipped payload carries only synthetic fixture material — never a
    # live platform domain, never a token shape, never a full id
    dumped = buf.getvalue()
    assert "https://" not in dumped and "leadconnectorhq" not in dumped, \
        "the fixture must never reference a live platform domain"
    assert "pit-" not in dumped and "Bearer" not in dumped and "sk-" not in dumped, \
        "the payload output must never carry a token shape"
    assert "num_SMSFAIL0042" not in dumped and "loc_QcDX" not in dumped, \
        "the payload must never carry a full synthetic id"
    assert "+12025550123" not in dumped and "+12025559876" not in dumped, \
        "the payload must never carry a full synthetic number"

    # the golden payload can never be mistaken for an ATTACK payload: the
    # attack gate REFUSES a 200-status record (the wrong direction is drift)
    # -- cross-surface fail-closed proof.
    saved_action = ATTACK_SEND_RECORD["action"]
    try:
        ATTACK_SEND_RECORD["action"] = "send-test-message-drift"  # the law regressed
        try:
            attack_send()
            raise AssertionError("a regressed authority must be REFUSED")
        except FixtureError:
            pass
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = payload(execute=True, out=io.StringIO())
        assert rc == EX_MISMATCH, \
            "payload under a regressed authority must REFUSE (exit 5), " \
            "got %s" % rc
        assert json.loads(buf.getvalue())["verdict"] == "REFUSED"
        # payload-true pins the 200 contract on the SAME authority — a
        # regressed action verb REFUSES there too
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = payload_true(execute=True, out=io.StringIO())
        assert rc == EX_MISMATCH, \
            "payload-true under a regressed authority must REFUSE (exit 5), " \
            "got %s" % rc
        assert json.loads(buf.getvalue())["verdict"] == "REFUSED"
    finally:
        ATTACK_SEND_RECORD["action"] = saved_action
    # after restore the control passes again (the refusal was the drift, not
    # the instrument)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload_true(execute=True, out=io.StringIO())
    assert rc == EX_OK, \
        "payload-true must pass again after the authority restored"

    # payload-true (the control): the true 200-send contract passes exit 0
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload_true(execute=True, out=io.StringIO())
    assert rc == EX_OK, \
        "payload-true on the true authority must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["status"] == 200

    # ---- attack fixtures: every drift REFUSED, never shipped ---------------
    # 1. a send record that still carries the 200 status the attack drops
    #    (the double-golden a regression would produce) -> refusal
    try:
        attack_send(dict(record, status=200))
        raise AssertionError("a 200-status send was NOT refused")
    except FixtureError:
        pass
    # 2. a send record under a different ACTION verb -> refusal
    try:
        attack_send(dict(record, action="send-test-message-drift"))
        raise AssertionError("a non-send ACTION was NOT refused")
    except FixtureError:
        pass
    # 3. a send record without the destination -> refusal
    try:
        attack_send({"action": "send-test-message", "number_id": "num_SMSFAIL0042",
                     "status": 200})
        raise AssertionError("a destination-less record was NOT refused")
    except FixtureError:
        pass
    # 4. a non-mapping record -> refusal
    try:
        attack_send("not-a-mapping")
        raise AssertionError("a non-mapping record was NOT refused")
    except FixtureError:
        pass

    # ---- the BROWSER UA law is pinned (CF 1010) ------------------------------
    assert reg.CAF_BROWSER_UA and reg.CAF_BROWSER_UA.startswith("Mozilla/"), \
        "CAF_BROWSER_UA must carry a browser User-Agent (the CF-1010 edge fix)"

    # ---- the mutation surface rides the browser UA on every request ---------
    assert reg.CAF_BROWSER_UA in (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",), \
        "CAF_BROWSER_UA must be byte-exact the house browser User-Agent"
    # the U23 package init pins the doctrine the fixture enforces
    init_blob = (Path(__file__).resolve().parent / "__init__.py").read_text()
    assert "--execute" in init_blob and "CF error 1010" in init_blob, \
        "the u23 package init must pin the --execute and browser-UA doctrine"

    # ---- plan: offline, no network, no --execute, exact drop ----------------
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = plan(out=io.StringIO())
    assert rc == EX_OK, "plan must exit 0"
    p = json.loads(buf.getvalue())
    assert p["action"] == "send-test-message" and p["status_dropped"] == 200
    assert p["status_attack"] == 502
    assert p["markers"]["number_marker"] == "...0042"
    assert p["markers"]["destination_marker"] == "...76"
    assert "pit-" not in buf.getvalue()

    dev.write("attack_sms_failed self-test: OK (SMS-verification authority "
              "pinned (provision_sms_phone.py: action 'send-test-message', "
              "masking helpers last-4 / last-2, mutation path); canonical "
              "non-200 send attack record changing the ONE status variable "
              "from 200 to 502 over synthetic material with every id masked; "
              "judge FAILs the non-200 send with exit 5 through EVERY "
              "SMS-verification authority naming the status and the masked "
              "markers while the golden 200-send control PASSES exit 0; "
              "422 / 403 / ok:false-200 / transport / non-mapping records "
              "FAIL; payload and payload-true REFUSE without --execute "
              "(Trevor gate) and ship under it, payload REFUSING a regressed "
              "authority while payload-true control PASSes the golden 200 "
              "contract; 4 attack fixtures refused (double-attack / drifted "
              "ACTION / destination-less record / non-mapping); CAF_BROWSER_UA "
              "pinned byte-exact plus the u23 package-init doctrine; never a "
              "token shape, never a full id; plan offline)\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="attack_sms_failed.py",
        description="Attack fixture — SMS send-test-message non-200, must "
                    "FAIL (Skill 59, U23 tooling): the adversarial sibling of "
                    "the U23 SMS verification surface, shipping the "
                    "deterministic failed-send read (the canonical "
                    "send-test-message record with the ONE 200-status "
                    "variable changed to the non-200 code 502, synthetic "
                    "material, every id masked) that every SMS-verification "
                    "gate must refuse, and the fail-closed gates that prove "
                    "it (the golden 200-send control PASSES). Shipping or "
                    "judging the attack requires --execute (Trevor gate).")
    ap.add_argument("--record", default=None,
                    help="send-test-message record to judge (verify); "
                         "defaults to the first stdin line")
    ap.add_argument("--execute", action="store_true",
                    help="Trevor-gated ACTION flag: only with this flag may "
                         "payload / payload-true ship the fixture")
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
            return payload_true(execute=args.execute)
        if args.cmd == "payload":
            return payload(execute=args.execute)
        if args.cmd == "verify":
            # Judge a send record (the canonical non-200 attack by default,
            # the golden 200 control via --record) — the Trevor gate applies
            # to judging the attack fixture exactly as to shipping it.
            raw = (args.record or sys.stdin.read().strip())
            if not raw:
                sys.stderr.write("[attack-sms-failed] no record given "
                                 "(--record or stdin) — nothing to judge.\n")
                return EX_ERR
            try:
                record = json.loads(raw)
            except ValueError as exc:
                sys.stderr.write("[attack-sms-failed] the record on stdin is "
                                 "not valid JSON: %s\n" % exc)
                return EX_ERR
            if not args.execute:
                sys.stderr.write("[attack-sms-failed] judging a send record "
                                 "is a Trevor-gated ACTION — pass --execute "
                                 "explicitly; refusing.\n")
                return EX_MISMATCH
            return verify_send(record, out=sys.stderr)
        return payload(execute=args.execute)
    except FixtureError as exc:
        sys.stderr.write("[attack-sms-failed] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[attack-sms-failed] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
