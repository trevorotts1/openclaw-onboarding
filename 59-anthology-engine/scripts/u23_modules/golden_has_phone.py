#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u23_modules/golden_has_phone.py  (U23)
# GOLDEN PHONE-PROVISIONED FIXTURE — the canonical in-memory SMS-PHONE
# PROVISIONED state of the U23 GHL-gated SMS phone provisioner: the client
# location's SMS-capable number ALREADY PRESENT — the golden control of the
# GET-first idempotency law (an already-provisioned location is VERIFIED,
# never re-provisioned: exit 0, idempotent no-op, never a second number,
# never a second charge). The anti-attack mirror of the attack fixture that
# certifies the state where an SMS marker is MISSING (an unmarked entry can
# never be trusted as SMS-capable).
#
# WHERE THIS SITS: scripts/u23_modules/ — an importable module under the
# u23_modules package (pure namespace container per the package __init__.py:
# imported BY NAME, side-effect-free at import). It is NOT a manifest row and
# NOT a checker: it ships the GOLDEN SMS-PHONE-PROVISIONED surface the
# OFFLINE self-test of the owning sibling (provision_sms_phone.py) and its
# attack fixtures assert against, so the happy path is judged against the
# SAME payload and a drift in the engine's phone-provisioning law breaks
# THIS module's self-test first (fail-closed: an inconsistent law is a
# refusal, never a blind pass).
#
# WHAT THIS OWNS (the U23 PHONE-PROVISIONING LAW, derived from the engine
# source that owns the surface — provision_sms_phone.py — never
# re-implemented here):
#   1. THE ALREADY-PROVISIONED LAW: the module LISTS the location's numbers
#      first (GET /phones/numbers?locationId=<loc>) and provisions ONLY when
#      no number already present matches the requested scope (SMS-capable).
#      A location that already carries an SMS-enabled number is VERIFIED,
#      never re-provisioned (exit 0, idempotent no-op — the IDEMPOTENCY LAW
#      the module's own happy-path self-test asserts as
#      "IDEMPOTENT NO-OP (marker ...)"). The golden listing therefore
#      carries EXACTLY ONE number whose SMS marker is PRESENT and TRUE —
#      a listing that carries NO SMS-capable number is the OTHER state
#      (needs-provision), never this fixture.
#   2. THE SMS-MARKER LAW: a number counts as SMS-capable ONLY by
#      presence/truthiness of the fixed marker keys ("smsEnabled",
#      "sms_enabled" — provision_sms_phone.SMS_ENABLED_KEYS, the ONE
#      authority, read through the owning module, never retyped here). An
#      entry whose marker is MISSING (not False) can NEVER be trusted as
#      SMS-capable — the attack shape the golden state must refuse, and the
#      marker law is pinned so a drift in the owning module breaks THIS
#      module's self-test first — never silently.
#   3. THE EXECUTE LAW: provisioning (the POST /phones/numbers create and
#      the send-test-message POST) is a GHL-gated ACTION that NEVER runs
#      without --execute (provision_sms_phone.py: "the module NEVER
#      provisions without --execute. Default and --dry-run are read-only /
#      plan-only"). A fixture cannot perform an action — it pins the LAW as
#      the truth its surfaces carry, exactly as golden_title pins the
#      --execute gate for the U08/U09 dispatcher.
#   4. THE BROWSER UA LAW: services.leadconnectorhq.com is Cloudflare-fronted
#      and 403s urllib's default User-Agent at the WAF edge (CF error 1010)
#      before it ever reaches the API; the house pattern is the browser UA
#      (CAF_BROWSER_UA in anthology_registry.py) on EVERY request via
#      reg.CafClient. THIS module makes NO network call and defines NO
#      User-Agent constant of its own; the sibling that DOES (the
#      provisioner rides the house rail client, which sends CAF_BROWSER_UA on
#      every request) — the proven edge fix. The self-test pins the browser
#      UA law so a registry regression is caught HERE first.
#   5. THE SCOPE-VS-EDGE LAW: a bare 401/403 is NEVER reported as a scope
#      problem — it is HELD (retryable). The fixture pins the discrimination
#      truth (ScopeDenied -> STOP family, UpstreamBlockedError/transport ->
#      HELD family) as the law its surfaces certify; the provisioner owns the
#      live discrimination.
#   6. GOLDEN_HAS_PHONE — the deep-frozen canonical record: the one
#      SMS-capable number entry (the fixed marker keys only, SMS marker
#      present and True), the masked id marker for every operator surface,
#      the masked number marker, the synthetic location marker, and the
#      already-provisioned truth. The record is a MappingProxyType (types
#      module) and every container inside it is a tuple, so NO caller can
#      mutate the canonical payload through the module's public surface —
#      the self-test proves every mutation route raises.
#   7. golden_has_phone() / golden_has_phone_listing() — the deep-copied
#      payload surfaces (the canonical provisioned-state record, and the
#      {"numbers": [<the golden entry>]} listing shape the provisioner's
#      list_phone_numbers consumes) — consumers mutate freely; the canon
#      never changes.
#   8. payload — a FAIL-CLOSED already-provisioned gate: the golden listing
#      carries the one SMS-capable number under the golden markers, each
#      matched BY EXACT VALUE, the marker law held, the already-provisioned
#      truth held, and the EXECUTE law certified -> PASS exit 0 with the
#      dispatcher-consumed dict surface {"ok": True, "provisioned": False,
#      "already": True, "verified": False, "af_code": "PHONE-PROVISIONED",
#      "note": ...}. ANY deviation (a blank or drifted number marker, a
#      marker NOT True, a listing with NO SMS-capable number, a listing with
#      MORE than one number, a malformed payload, a non-object candidate, a
#      credential-shaped value) is a REFUSED exit 5 — never a blind pass,
#      never a fabricated success. The one JSON report object lands on
#      stdout; human notes go to stderr; the dict the dispatcher's
#      verify_live consumes is the payload() RETURN VALUE.
#
# DOCTRINE (house, inherited from the registry / the u02..u09 golden
# siblings — the SAME doctrine every fixture carries):
#   - Never a token printed: credentials resolve BY LABEL only (SET / NOT
#     SET). This module holds NO credential surface and reads NO env var — a
#     fixture cannot leak what it never holds. The only id-shaped material
#     it carries is SYNTHETIC fixture markers (loc_golden_phone /
#     num_GOLDEN / +12025559876 — a fixture number is never a real client
#     number), and the never-print self-test proves no pit-/Bearer-shaped
#     string ever rides any surface.
#   - Fail-closed: a blank or drifted marker, a marker not True, a listing
#     with no SMS-capable number, a listing with more than one number, a
#     malformed payload, a credential-shaped value all STOP or FAIL — never
#     a blind pass, never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates. The
#     --execute gate (Trevor-gated) lives in the OWNING provisioner
#     (provision_sms_phone.py), never in a fixture; THIS module pins the gate
#     as the law its surfaces carry, exactly as golden_title pins it for the
#     U08/U09 dispatcher and golden_all_present pins it for the U07
#     provisioning action.
#   - BROWSER UA: any module that TALKS to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a
#     browser User-Agent on every request — urllib's default
#     "Python-urllib/x.y" is 403'd at the WAF edge (CF error 1010) before it
#     ever reaches the API (CAF_BROWSER_UA in anthology_registry.py is the
#     house pattern). THIS module makes NO network call and defines NO
#     User-Agent constant of its own; the sibling that DOES (the provisioner
#     rides the house rail client, which sends CAF_BROWSER_UA on every
#     request) — the proven edge fix. The self-test pins the browser UA law
#     so a registry regression is caught HERE first.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface.
#
# THE SUBJECT MATERIAL IS NEVER HARDCODED HERE AS A LIVE VALUE (SPEC M8): the
# fixture ships SYNTHETIC deterministic markers only (loc_golden_phone /
# num_GOLDEN / +12025559876 — the discipline of the u02..u09 golden
# siblings: a fixture id is never a real location, number, or client phone
# number), and the LAW (the one-marker presence/truthiness SMS contract, the
# already-provisioned idempotency, the --execute gate, the browser UA) is
# pinned from the engine source: provision_sms_phone.py (the U23 owner),
# with the canonical constants read through the registry the same way every
# other golden sibling reads them. The OFFLINE self-test pins the contract
# values so a drift in the LAW is caught first — never silently.
#
# EXIT CODE CONTRACT (house convention 0/1/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified success — the golden phone-provisioned payload is internally
#      consistent and the golden state PASSES the gate; also self-test /
#      plan OK
#   1  unexpected error (top-level guard; never a secret leak)
#   4  self-test FAILED (an enforced violation — a tamper NEVER masquerades
#      as exit 1)
#   5  mismatch / fail-closed default — a blank or drifted marker, a marker
#      not True, a listing with no SMS-capable number, a listing with more
#      than one number, a malformed payload, a non-object candidate, or a
#      credential-shaped value (all FAIL-CLOSED refusals)
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# u05/u06/u07/u08/u09 golden siblings: sys.path.insert to scripts/ then
# `import anthology_registry as reg` for its canonical constants, and the
# SMS-marker law shape is read through provision_sms_phone.SMS_ENABLED_KEYS
# — never duplicated here.
# =============================================================================
"""golden_has_phone.py — golden PHONE-PROVISIONED fixture for the U23
self-tests. The canonical SMS-capable-number-already-present state: the one
SMS-capable number entry under the fixed marker keys, already-provisioned
truth, EXECUTE law certified, scope-vs-edge truth, browser-UA law.
Pure data + the fail-closed already-provisioned gate; never prints a token."""

from __future__ import annotations

import argparse
import copy
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to the u05..u09
# golden siblings): the registry owns the canonical constants and the
# Cloudflare browser-UA wiring; the SMS-marker law shape is read through
# provision_sms_phone.SMS_ENABLED_KEYS (the ONE authority) — a fixture
# never re-implements what a sibling owns.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import provision_sms_phone as prov  # noqa: E402

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for a
# phone-provisioned fixture (the self-test asserts the golden report carries
# the exact string — the surface contract is load-bearing).
FIXTURE_CONTRACT = "anthology-engine-golden-has-phone"

# The U23 surface (provision_sms_phone.py — the ONE authority, read through
# the owning module, never retyped): the fixed SMS-marker key set. The
# fixture certifies presence/truthiness on these keys only — never any other
# field of a number entry.
SMS_ENABLED_KEYS = prov.SMS_ENABLED_KEYS  # ("smsEnabled", "sms_enabled")

# The one already-provisioned truth, pinned from the owning module's
# happy-path contract: a location that already carries an SMS-enabled number
# is VERIFIED, never re-provisioned — exit 0, idempotent no-op, never a
# second number, never a second charge (provision_sms_phone.py
# provision_action: "IDEMPOTENT NO-OP (marker ...)").
ALREADY_PROVISIONED = True

# The EXECUTE law, pinned from the owning module's contract: the
# provisioning POST and the send-test-message POST are GHL-gated ACTIONS that
# NEVER run without --execute (provision_sms_phone.py: "this module NEVER
# provisions without --execute. Default and --dry-run are read-only /
# plan-only"). The fixture certifies the law on every surface; the gate lives
# in the provisioner, never in a fixture.
EXECUTE_REQUIRED_FOR_PROVISION = True

# The scope-vs-edge discrimination truth, pinned from the owning module's
# contract: a bare 401/403 is NEVER reported as a scope problem — it is HELD
# (retryable) (provision_sms_phone.py READ-REFUSED ladder: scope ->
# STOP family, edge/transport -> HELD family).
SCOPE_STOP_EXIT = reg.EX_STOP      # scope refusal -> STOP
EDGE_HELD_EXIT = reg.EX_HELD       # edge block / transport -> HELD, never mislabeled

# The stable SYNTHETIC subject material (the synthetic-id discipline of the
# u02..u09 golden siblings — a fixture id is never a real id). The location
# marker and the masked number marker are the same non-reversible shapes the
# house uses for every operator-facing mention (reg._mask_location / the
# provisioner's _mask_number).
GOLDEN_LOCATION_ID = "loc_golden_phone"
GOLDEN_LOCATION_MASKED = reg._mask_location(GOLDEN_LOCATION_ID)
GOLDEN_NUMBER_ID = "num_GOLDEN"
GOLDEN_NUMBER_ID_MASKED = reg._mask_location(GOLDEN_NUMBER_ID)
GOLDEN_PHONE_NUMBER = "+12025559876"  # fabricated — never a real client number
GOLDEN_PHONE_MASKED = prov._mask_number(GOLDEN_PHONE_NUMBER)

# The one af_code the golden payload certifies — the named ok surface a
# machine consumer reads (the owning provisioner's ok surface carries the
# already/already-provisioned marker; the two can never drift apart).
GOLDEN_AF_CODE = "PHONE-PROVISIONED"
REFUSED_AF_CODE = "PHONE-PROVISIONED-REFUSED"


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the
    phone-provisioning law is inconsistent with the golden provisioned state,
    so NO fixture is shipped — a wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing law is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _is_blank(value) -> bool:
    return not isinstance(value, str) or not value.strip()


def _sms_enabled(number: dict) -> bool:
    """The SMS-marker law, read through the ONE authority
    (provision_sms_phone.SMS_ENABLED_KEYS): a number counts as SMS-capable
    ONLY by presence/truthiness of the fixed marker keys — never any other
    field of the number entry. An entry whose marker is MISSING (not False)
    can NEVER be trusted as SMS-capable — the attack shape the golden state
    refuses fail-closed."""
    for k in SMS_ENABLED_KEYS:
        v = number.get(k)
        if v is not None:
            return bool(v)
    return False


def _contract_entry(payload: dict) -> dict:
    """The golden number entry of a provisioned-state payload, fail-closed. A
    listing entry must be an OBJECT carrying the id marker, the phone-number
    marker, and the SMS marker present and TRUE — a marker-less entry is the
    attack shape, never the golden one."""
    if not isinstance(payload, dict):
        raise FixtureError(
            "the provisioned state carries no number-entry object — a "
            "malformed listing is never a pass; refusing to certify the "
            "golden phone-provisioned state.")
    entry = dict(payload)
    for field in ("id", "phoneNumber"):
        value = entry.get(field)
        if _is_blank(value):
            raise FixtureError(
                "the number entry carries no %r — a malformed entry is never "
                "a pass; refusing to certify the golden phone-provisioned "
                "state." % field)
    if not _sms_enabled(entry):
        raise FixtureError(
            "the number entry carries no SMS marker present and TRUE — an "
            "unmarked entry can NEVER be trusted as SMS-capable; refusing to "
            "certify a listing that does not already carry an SMS-capable "
            "number.")
    return entry


def _contract_exact(entry: dict) -> None:
    """The byte-exact law, fail-closed: the entry's markers must BYTE-EQUAL
    the golden ones. A blank or drifted marker is exactly the shape the
    golden state must REFUSE — the provisioned state is pinned once, so a
    drift is indistinguishable from a blank and BOTH refuse fail-closed."""
    if entry["id"] != GOLDEN_NUMBER_ID:
        raise FixtureError(
            "the entry's number id marker is not byte-exact — the golden "
            "phone-provisioned state requires %r exactly; a drifted id "
            "marker is indistinguishable from a blank one and BOTH refuse "
            "fail-closed." % GOLDEN_NUMBER_ID)
    if entry["phoneNumber"] != GOLDEN_PHONE_NUMBER:
        raise FixtureError(
            "the entry's phone-number marker is not byte-exact — the golden "
            "phone-provisioned state requires the fabricated marker %s "
            "exactly; a drifted marker is indistinguishable from a blank one "
            "and BOTH refuse fail-closed (the full number is never named on "
            "any surface — masked only)." % GOLDEN_PHONE_MASKED)


def _contract_listing(payload: dict) -> dict:
    """The listing law, fail-closed: the listing carries the numbers array,
    and the golden state requires EXACTLY ONE SMS-capable number — a listing
    with NO SMS-capable number is the other state (needs-provision), and a
    listing with MORE than one number is never the golden already-
    provisioned truth (never a second number, never a second charge)."""
    numbers = payload.get("numbers")
    if not isinstance(numbers, list):
        raise FixtureError(
            "the listing carries no numbers array — a malformed listing is "
            "never a pass; refusing to certify the golden phone-provisioned "
            "state.")
    sms_capable = [n for n in numbers if isinstance(n, dict) and _sms_enabled(n)]
    if len(sms_capable) != 1:
        raise FixtureError(
            "the listing carries %d SMS-capable number(s), but the golden "
            "already-provisioned state requires EXACTLY ONE — a listing "
            "without an SMS-capable number is the needs-provision state, and "
            "a listing with more than one is never the golden truth (never a "
            "second number, never a second charge); refusing to certify."
            % len(sms_capable))
    return sms_capable[0]


def _contract_exact_listing(payload: dict) -> None:
    """The one-number law, fail-closed: the listing must carry EXACTLY ONE
    number entry in total — the golden already-provisioned state is the one
    SMS-capable number and nothing else (a listing that carries extra,
    non-SMS entries is not the state the provisioner's idempotent no-op
    verified; refusing to certify a drifted listing)."""
    numbers = payload.get("numbers")
    if not isinstance(numbers, list) or len(numbers) != 1:
        raise FixtureError(
            "the listing must carry EXACTLY ONE number entry — the golden "
            "already-provisioned state is the one SMS-capable number and "
            "nothing else; a listing that carries extra entries is not the "
            "state the idempotent no-op verified; refusing to certify.")


def _contract_markers(payload: dict) -> None:
    """The marker law, fail-closed: the payload's masked markers must be the
    non-reversible last-4 shapes, never full values — the never-print law on
    the fixture's own surface."""
    if payload.get("id_masked") != GOLDEN_NUMBER_ID_MASKED:
        raise FixtureError(
            "the payload's masked id marker is not the golden marker — every "
            "operator-facing mention of an id rides the non-reversible "
            "last-4 shape; refusing to certify a payload that would print a "
            "full marker.")
    if payload.get("phone_masked") != GOLDEN_PHONE_MASKED:
        raise FixtureError(
            "the payload's masked phone marker is not the golden marker — "
            "every operator-facing mention of a number rides the "
            "non-reversible last-4 shape; refusing to certify a payload that "
            "would print a full number.")


def _contract_location(payload: dict) -> str:
    """The location law, fail-closed: the provisioned state must name the
    golden synthetic location marker BYTE-EXACT — a payload carrying a
    different marker certifies a DIFFERENT location, never the golden one,
    and a drifted marker is indistinguishable from a blank one (BOTH refuse
    fail-closed, exactly as the byte-exact marker law refuses)."""
    loc = payload.get("location")
    if not isinstance(loc, str) or not loc.strip():
        raise FixtureError(
            "the provisioned state carries no location — the golden "
            "phone-provisioned state names the synthetic location marker; a "
            "location-less payload is a refusal, never a pass.")
    if loc != GOLDEN_LOCATION_ID:
        raise FixtureError(
            "the provisioned state names location %r, but the golden "
            "phone-provisioned state requires %r exactly — a state that "
            "certifies a different location is never a golden pass; a "
            "drifted location marker is indistinguishable from a blank one "
            "and BOTH refuse fail-closed."
            % (loc, GOLDEN_LOCATION_ID))
    return loc


def _contract_truths(payload: dict) -> None:
    """The already-provisioned + EXECUTE truth law, fail-closed: the payload
    certifies already_provisioned TRUE (the idempotent no-op truth) and
    execute_required TRUE (the --execute law — provisioning NEVER runs
    without it). A payload certifying either otherwise is a refusal, never a
    pass."""
    if payload.get("already_provisioned") is not ALREADY_PROVISIONED:
        raise FixtureError(
            "the payload does not certify already_provisioned TRUE — the "
            "golden state is the idempotent no-op truth (an SMS-capable "
            "number already exists; never a second number, never a second "
            "charge); refusing to certify.")
    if payload.get("execute_required") is not EXECUTE_REQUIRED_FOR_PROVISION:
        raise FixtureError(
            "the payload does not certify the EXECUTE law — provisioning is "
            "a GHL-gated ACTION that NEVER runs without --execute; a "
            "payload that would certify otherwise is a refusal, never a "
            "pass.")


# ---------------------------------------------------------------------------
# The golden builder — fail-closed, deterministic, never a live id.
# ---------------------------------------------------------------------------
def golden_has_phone() -> dict:
    """The canonical phone-provisioned record: the one SMS-capable number
    entry under the golden markers (the fixed marker keys, SMS marker present
    and TRUE), the masked id marker and masked phone marker (the
    non-reversible last-4 shapes every operator-facing mention carries — the
    full synthetic markers ride inside the JSON payload a machine consumer
    reads), the synthetic location marker, and the already-provisioned +
    EXECUTE truths. Returns a deep copy; mutating it never touches the
    internal canonical payload (which itself is mappingproxy-frozen)."""
    return copy.deepcopy({
        "location": GOLDEN_LOCATION_ID,
        "id": GOLDEN_NUMBER_ID,
        "phoneNumber": GOLDEN_PHONE_NUMBER,
        SMS_ENABLED_KEYS[0]: True,  # the fixed marker, present and TRUE
        "id_masked": GOLDEN_NUMBER_ID_MASKED,
        "phone_masked": GOLDEN_PHONE_MASKED,
        "already_provisioned": ALREADY_PROVISIONED,
        "execute_required": EXECUTE_REQUIRED_FOR_PROVISION,
    })


def golden_has_phone_listing() -> dict:
    """The canonical listing surface: {"numbers": [<the golden entry>]} — the
    shape the provisioner's list_phone_numbers consumes (GET
    /phones/numbers?locationId=<loc>). A deep copy; callers may mutate it."""
    return copy.deepcopy({
        "numbers": [{
            "id": GOLDEN_NUMBER_ID,
            "phoneNumber": GOLDEN_PHONE_NUMBER,
            SMS_ENABLED_KEYS[0]: True,
        }],
    })


# ---------------------------------------------------------------------------
# The golden fixture itself — derived ONCE at import, deep-frozen. The record
# is a MappingProxyType and every container is a tuple, so NO caller can
# mutate the canonical payload through the module's public surface — the
# self-test proves it. Consumers that need a mutable payload call
# golden_has_phone() / golden_has_phone_listing() (deep copies).
# ---------------------------------------------------------------------------
def _build_golden() -> tuple:
    from types import MappingProxyType
    return (MappingProxyType(dict(golden_has_phone())),)


# The canonical phone-provisioned record: deep-frozen (a mappingproxy —
# immutable through every route).
GOLDEN_HAS_PHONE_RECORD = _build_golden()[0]


# ---------------------------------------------------------------------------
# Fail-closed already-provisioned gate — the offline gate the self-test and
# `payload` both ride on. A blank or drifted marker, a marker not True, a
# listing without exactly the one SMS-capable number, or a drifted surface is
# REFUSED with exit 5, never tolerated.
# ---------------------------------------------------------------------------
def _judge(payload: dict, *, out) -> int:
    """The fail-closed already-provisioned gate. Returns the exit code: 0
    PASS, 5 REFUSED (mismatch family). Emits the ONE JSON report object on
    stdout; human notes go to out (stderr)."""
    detail = ""
    ok = False
    found = {"id_masked": None, "phone_masked": None, "location": None}
    try:
        entry = _contract_entry(payload)
        _contract_exact(entry)
        _contract_markers(payload)
        loc = _contract_location(payload)
        _contract_truths(payload)
    except FixtureError as exc:
        detail = str(exc)
    else:
        found["id_masked"] = payload.get("id_masked")
        found["phone_masked"] = payload.get("phone_masked")
        found["location"] = loc
        ok = True
        detail = ("the location already carries an SMS-capable number "
                  "(%s, id marker %s) — the golden phone-provisioned "
                  "state holds (idempotent no-op: verified, never "
                  "re-provisioned, never a second number, never a second "
                  "charge; provisioning stays --execute-gated)"
                  % (found["phone_masked"], found["id_masked"]))
    print(json.dumps({
        "contract": FIXTURE_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "REFUSED",
        "expected": {
            "surface": "provision_sms_phone",
            "sms_enabled_keys": list(SMS_ENABLED_KEYS),
            "already_provisioned": ALREADY_PROVISIONED,
            "execute_required": EXECUTE_REQUIRED_FOR_PROVISION,
        },
        "found": found,
        "detail": detail,
    }, indent=2, sort_keys=True))
    if not ok:
        out.write("[golden-has-phone] REFUSED: %s\n" % detail)
        return EX_MISMATCH
    return EX_OK


def payload(candidate: dict = None, *, out=None) -> int:
    """Judge a provisioned-state payload against the golden
    phone-provisioned contract.

    READ-ONLY: asserts the U23 phone-provisioning law — the one SMS-capable
    number entry under the fixed marker keys (presence/truthiness only), the
    byte-exact golden markers, the non-reversible masked markers, the golden
    synthetic location marker, the already-provisioned truth, and the EXECUTE
    law. A blank or drifted marker, a marker not True, a non-golden location,
    a listing with no SMS-capable number or more than one number, a
    malformed payload (a missing numbers array / a non-string value), a
    non-object candidate, or a credential-shaped value is a FAIL-CLOSED exit
    5, never a blind pass. With no candidate the GOLDEN state itself is
    judged — the dispatcher's offline gate. Emits the ONE JSON report object
    on stdout; human notes go to out (stderr)."""
    out = out or sys.stderr
    if candidate is None:
        candidate = golden_has_phone()
    if not isinstance(candidate, dict):
        detail = "the candidate is not a JSON object — malformed provisioned " \
                 "state, never a pass (fail-closed)"
        print(json.dumps({
            "contract": FIXTURE_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "expected": {
                "surface": "provision_sms_phone",
                "sms_enabled_keys": list(SMS_ENABLED_KEYS),
                "already_provisioned": ALREADY_PROVISIONED,
                "execute_required": EXECUTE_REQUIRED_FOR_PROVISION,
            },
            "found": None,
            "detail": detail,
        }, indent=2, sort_keys=True))
        out.write("[golden-has-phone] REFUSED: %s\n" % detail)
        return EX_MISMATCH
    return _judge(candidate, out=out)


def listing(candidate: dict = None, *, out=None) -> int:
    """Judge a LISTING payload — the {"numbers": [...]} shape the owning
    provisioner's list_phone_numbers consumes — against the golden
    already-provisioned contract: EXACTLY ONE number entry, SMS marker
    present and TRUE. A listing with no SMS-capable number is the
    needs-provision state, and a listing with more than one number is never
    the golden truth — both REFUSE fail-closed (exit 5). The listing also
    certifies the EXECUTE law: the provisioned state is verified, never
    re-provisioned; any provisioning ACTION requires --execute (the gate
    lives in the provisioner). With no candidate the GOLDEN listing itself is
    judged. Emits the ONE JSON report object on stdout; human notes go to
    out (stderr)."""
    out = out or sys.stderr
    if candidate is None:
        candidate = golden_has_phone_listing()
    if not isinstance(candidate, dict):
        detail = "the listing candidate is not a JSON object — malformed " \
                 "listing, never a pass (fail-closed)"
        print(json.dumps({
            "contract": FIXTURE_CONTRACT + "-listing",
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "expected": {
                "surface": "provision_sms_phone",
                "numbers": 1,
                "sms_enabled_keys": list(SMS_ENABLED_KEYS),
                "already_provisioned": ALREADY_PROVISIONED,
                "execute_required": EXECUTE_REQUIRED_FOR_PROVISION,
            },
            "found": None,
            "detail": detail,
        }, indent=2, sort_keys=True))
        out.write("[golden-has-phone] REFUSED: %s\n" % detail)
        return EX_MISMATCH
    detail = ""
    ok = False
    found = {"numbers": None, "sms_capable": None}
    try:
        _contract_exact_listing(candidate)
        entry = _contract_listing(candidate)
        _contract_exact(entry)
    except FixtureError as exc:
        detail = str(exc)
    else:
        found["numbers"] = len(candidate.get("numbers") or [])
        found["sms_capable"] = prov._mask_number(
            str(entry.get("phoneNumber") or ""))
        ok = True
        detail = ("the listing carries EXACTLY ONE number and it reports "
                  "SMS-capable (%s) — the already-provisioned state holds "
                  "(idempotent no-op; provisioning stays --execute-gated)"
                  % found["sms_capable"])
    print(json.dumps({
        "contract": FIXTURE_CONTRACT + "-listing",
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "REFUSED",
        "expected": {
            "surface": "provision_sms_phone",
            "numbers": 1,
            "sms_enabled_keys": list(SMS_ENABLED_KEYS),
            "already_provisioned": ALREADY_PROVISIONED,
            "execute_required": EXECUTE_REQUIRED_FOR_PROVISION,
        },
        "found": found,
        "detail": detail,
    }, indent=2, sort_keys=True))
    if not ok:
        out.write("[golden-has-phone] REFUSED: %s\n" % detail)
        return EX_MISMATCH
    return EX_OK


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
        sys.stderr.write("[golden-has-phone] SELF-TEST FAILED "
                         "(AF-AE-GOLDENHASPHONE-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    from types import MappingProxyType
    import contextlib

    # ---- contract coherence: the marker law is the shape authority ----------
    assert SMS_ENABLED_KEYS == ("smsEnabled", "sms_enabled"), \
        "the SMS-marker law drifted (provision_sms_phone.SMS_ENABLED_KEYS)"
    assert ALREADY_PROVISIONED is True, \
        "the golden state certifies the already-provisioned truth"
    assert EXECUTE_REQUIRED_FOR_PROVISION is True, \
        "the EXECUTE law: provisioning NEVER runs without --execute"
    assert SCOPE_STOP_EXIT == reg.EX_STOP and EDGE_HELD_EXIT == reg.EX_HELD, \
        "the scope-vs-edge discrimination must map scope -> STOP, edge -> HELD"
    assert GOLDEN_LOCATION_MASKED == "...hone", \
        "the masked location marker must be the non-reversible last-4 shape"
    assert GOLDEN_NUMBER_ID_MASKED == "...LDEN", \
        "the masked number-id marker must be the non-reversible last-4 shape"
    assert GOLDEN_PHONE_MASKED == "...9876", \
        "the masked phone marker must be the non-reversible last-4 shape"
    assert _sms_enabled({"smsEnabled": True}) is True, \
        "the marker law must read presence/truthiness on the fixed keys"
    assert _sms_enabled({"smsEnabled": False}) is False
    assert _sms_enabled({"sms_enabled": "false"}) is True, \
        "a truthy string stays truthy (the provisioner's own law)"
    assert _sms_enabled({"other": True}) is False, \
        "an unmarked entry can NEVER be trusted as SMS-capable"

    # ---- the canonical fixture: phone-provisioned record deep-frozen -------
    assert isinstance(GOLDEN_HAS_PHONE_RECORD, MappingProxyType), \
        "GOLDEN_HAS_PHONE_RECORD must be mappingproxy-frozen"
    for field in ("location", "id", "phoneNumber", "id_masked", "phone_masked",
                  "already_provisioned", "execute_required"):
        assert field in GOLDEN_HAS_PHONE_RECORD, \
            "the canonical record lost its %r field" % field
    assert GOLDEN_HAS_PHONE_RECORD["location"] == GOLDEN_LOCATION_ID == \
        "loc_golden_phone", "the canonical location marker drifted"
    assert GOLDEN_HAS_PHONE_RECORD["id"] == GOLDEN_NUMBER_ID == "num_GOLDEN", \
        "the canonical number-id marker drifted"
    assert GOLDEN_HAS_PHONE_RECORD["phoneNumber"] == GOLDEN_PHONE_NUMBER == \
        "+12025559876", "the canonical phone marker drifted"
    assert GOLDEN_HAS_PHONE_RECORD["id_masked"].startswith("..."), \
        "the canonical record must mask the id marker to its last-4 shape"
    assert GOLDEN_HAS_PHONE_RECORD["phone_masked"].startswith("..."), \
        "the canonical record must mask the phone marker to its last-4 shape"
    assert GOLDEN_HAS_PHONE_RECORD["already_provisioned"] is True, \
        "the canonical record must certify the already-provisioned truth"
    assert GOLDEN_HAS_PHONE_RECORD["execute_required"] is True, \
        "the canonical record must certify the EXECUTE law"
    # the canonical LISTING: exactly the one SMS-capable entry, marker true
    listing_ = golden_has_phone_listing()
    assert isinstance(listing_, dict) and isinstance(listing_["numbers"], list) \
        and len(listing_["numbers"]) == 1, \
        "the canonical listing must carry exactly one number entry"
    assert _sms_enabled(listing_["numbers"][0]) is True, \
        "the canonical listing's entry must report SMS-capable"
    assert listing_["numbers"][0]["id"] == "num_GOLDEN", \
        "the canonical listing entry must carry the golden number-id marker"

    # ---- the payload surfaces cover the law on every shape ------------------
    rec = golden_has_phone()
    assert rec["location"] == GOLDEN_LOCATION_ID and \
        rec["id"] == GOLDEN_NUMBER_ID and \
        rec["phoneNumber"] == GOLDEN_PHONE_NUMBER, \
        "the canonical record drifted from the golden contract"
    assert rec["already_provisioned"] is True and \
        rec["execute_required"] is True, \
        "the canonical record must certify the truths"

    # ---- the canonical fixture can never be mutated through the surface -----
    before = GOLDEN_HAS_PHONE_RECORD["phoneNumber"]

    def _try_rebind():  # subscript assignment on a mappingproxy -> TypeError
        GOLDEN_HAS_PHONE_RECORD["phoneNumber"] = "Mutated"  # noqa: B034 -- deliberately attempted

    try:
        _try_rebind()
        raise AssertionError("the canonical fixture must be immutable")
    except TypeError:
        pass
    assert GOLDEN_HAS_PHONE_RECORD["phoneNumber"] == before, \
        "the canonical fixture changed during the self-test"
    # golden_has_phone() returns a deep copy: mutating it never touches the
    # canon.
    copy_ = golden_has_phone()
    copy_["phoneNumber"] = "Mutated"
    assert GOLDEN_HAS_PHONE_RECORD["phoneNumber"] == before, \
        "the returned copy must not alias the canonical payload"

    # ---- attack fixtures: every drift REFUSED, never shipped ----------------
    # 1. a BLANK phone-number marker -> the state cannot be certified
    blank_phone = dict(golden_has_phone())
    blank_phone["phoneNumber"] = ""
    try:
        _contract_entry(blank_phone)
        raise AssertionError("a blank phone marker was NOT refused")
    except FixtureError:
        pass
    # 2. a DRIFTED phone-number marker -> the state cannot be certified
    drifted_phone = dict(golden_has_phone())
    drifted_phone["phoneNumber"] = "+12025559999"
    try:
        _contract_exact(_contract_entry(drifted_phone))
        raise AssertionError("a drifted phone marker was NOT refused")
    except FixtureError:
        pass
    # 3. a DRIFTED number-id marker -> the state cannot be certified
    drifted_id = dict(golden_has_phone())
    drifted_id["id"] = "num_OTHER"
    try:
        _contract_exact(_contract_entry(drifted_id))
        raise AssertionError("a drifted number-id marker was NOT refused")
    except FixtureError:
        pass
    # 4. an SMS marker present but NOT True -> never SMS-capable
    marker_off = dict(golden_has_phone())
    marker_off["smsEnabled"] = False
    try:
        _contract_entry(marker_off)
        raise AssertionError("a marker not True was NOT refused")
    except FixtureError:
        pass
    # 5. an SMS marker MISSING (the attack shape) -> never trusted
    marker_missing = dict(golden_has_phone())
    marker_missing.pop("smsEnabled", None)
    try:
        _contract_entry(marker_missing)
        raise AssertionError("an unmarked entry was NOT refused")
    except FixtureError:
        pass
    # 6. a drifted masked id marker -> the never-print law broken
    bad_mask = dict(golden_has_phone())
    bad_mask["id_masked"] = "num_GOLDEN"
    try:
        _contract_markers(bad_mask)
        raise AssertionError("a full id marker on the surface was NOT refused")
    except FixtureError:
        pass
    # 7. a drifted location -> a DIFFERENT location, never the golden one
    bad_loc = dict(golden_has_phone())
    bad_loc["location"] = "loc_OTHER"
    try:
        _contract_location(bad_loc)
        raise AssertionError("a non-golden location was NOT refused")
    except FixtureError:
        pass
    # 8. the already-provisioned truth lost -> never certified
    not_already = dict(golden_has_phone())
    not_already["already_provisioned"] = False
    try:
        _contract_truths(not_already)
        raise AssertionError("a non-already-provisioned state was NOT refused")
    except FixtureError:
        pass
    # 9. the EXECUTE law lost -> never certified
    no_execute_law = dict(golden_has_phone())
    no_execute_law["execute_required"] = False
    try:
        _contract_truths(no_execute_law)
        raise AssertionError("a payload dropping the EXECUTE law was NOT "
                             "refused")
    except FixtureError:
        pass
    # 10. a listing with NO SMS-capable number -> the needs-provision state
    no_sms = {"numbers": [{"id": "num_OTHER", "phoneNumber": "+12025559999"}]}
    try:
        _contract_listing(no_sms)
        raise AssertionError("a listing without an SMS-capable number was NOT "
                             "refused")
    except FixtureError:
        pass
    # 11. a listing with MORE than one number -> never the golden truth
    two_numbers = {"numbers": [
        dict(golden_has_phone_listing()["numbers"][0]),
        {"id": "num_OTHER", "phoneNumber": "+12025559999", "smsEnabled": True},
    ]}
    try:
        _contract_listing(two_numbers)
        raise AssertionError("a two-number listing was NOT refused")
    except FixtureError:
        pass
    # 12. a listing carrying extra non-SMS entries -> never the verified state
    extra_entry = {"numbers": [
        dict(golden_has_phone_listing()["numbers"][0]),
        {"id": "num_OTHER", "phoneNumber": "+12025559999"},
    ]}
    try:
        _contract_exact_listing(extra_entry)
        raise AssertionError("a listing with an extra entry was NOT refused")
    except FixtureError:
        pass
    # 13. a listing whose entry marker is missing -> the attack shape
    listing_attack = {"numbers": [{"id": "num_SUSPECT",
                                   "phoneNumber": "+12025559999"}]}
    try:
        _contract_listing(listing_attack)
        raise AssertionError("an unmarked listing entry was NOT refused")
    except FixtureError:
        pass

    # ---- the payload gate: golden exits 0, every drift exits 5 --------------
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload()
    assert rc == EX_OK, "payload on the golden state must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["contract"] == FIXTURE_CONTRACT
    assert parsed["expected"]["surface"] == "provision_sms_phone"
    assert parsed["expected"]["sms_enabled_keys"] == ["smsEnabled",
                                                      "sms_enabled"]
    assert parsed["expected"]["already_provisioned"] is True
    assert parsed["expected"]["execute_required"] is True
    assert parsed["found"]["id_masked"] == "...LDEN"
    assert parsed["found"]["phone_masked"] == "...9876"
    assert parsed["found"]["location"] == "loc_golden_phone"
    # a drifted phone marker -> REFUSED exit 5
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = payload(dict(golden_has_phone(), phoneNumber="+12025559999"))
    assert rc2 == EX_MISMATCH, "a drifted phone marker must exit 5, got %s" % rc2
    assert json.loads(buf2.getvalue())["verdict"] == "REFUSED"
    # a blank phone marker -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(dict(golden_has_phone(), phoneNumber="")) == EX_MISMATCH, \
            "a blank phone marker must exit 5"
    # a marker not True -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(dict(golden_has_phone(), smsEnabled=False)) == \
            EX_MISMATCH, "a marker not True must exit 5"
    # an unmarked entry -> REFUSED exit 5 (never trusted as SMS-capable)
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(dict(golden_has_phone(), smsEnabled=None)) == \
            EX_MISMATCH, "an unmarked entry must exit 5"
    # a drifted number-id marker -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(dict(golden_has_phone(), id="num_OTHER")) == \
            EX_MISMATCH, "a drifted number-id marker must exit 5"
    # a drifted location -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(dict(golden_has_phone(), location="loc_OTHER")) == \
            EX_MISMATCH, "a non-golden location must exit 5"
    # the already-provisioned truth lost -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(dict(golden_has_phone(), already_provisioned=False)) \
            == EX_MISMATCH, "a non-already-provisioned state must exit 5"
    # the EXECUTE law lost -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(dict(golden_has_phone(), execute_required=False)) \
            == EX_MISMATCH, "a payload dropping the EXECUTE law must exit 5"
    # a malformed candidate -> REFUSED exit 5 (never a pass)
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"no_number_here": True}) == EX_MISMATCH, \
            "a malformed candidate must exit 5"
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload("not-an-object") == EX_MISMATCH, \
            "a non-object candidate must exit 5"

    # ---- the listing gate: golden exits 0, every drift exits 5 --------------
    lbuf = io.StringIO()
    with contextlib.redirect_stdout(lbuf):
        rc_l = listing()
    assert rc_l == EX_OK, "listing on the golden listing must exit 0, " \
                          "got %s" % rc_l
    lparsed = json.loads(lbuf.getvalue())
    assert lparsed["ok"] is True and lparsed["verdict"] == "PASS"
    assert lparsed["contract"] == FIXTURE_CONTRACT + "-listing"
    assert lparsed["found"]["numbers"] == 1
    # a listing with no SMS-capable number -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert listing({"numbers": []}) == EX_MISMATCH, \
            "a listing without an SMS-capable number must exit 5"
    # a listing with two numbers -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert listing(two_numbers) == EX_MISMATCH, \
            "a two-number listing must exit 5"
    # a listing with an unmarked entry -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert listing(listing_attack) == EX_MISMATCH, \
            "an unmarked listing entry must exit 5"
    # a malformed listing -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert listing({"numbers": "not-a-list"}) == EX_MISMATCH, \
            "a malformed listing must exit 5"
    with contextlib.redirect_stdout(io.StringIO()):
        assert listing("not-an-object") == EX_MISMATCH, \
            "a non-object listing candidate must exit 5"

    # ---- the BROWSER UA law is pinned (CF 1010) ------------------------------
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), \
        "CAF_BROWSER_UA must be a browser User-Agent (CF 1010)"

    # ---- never-print: no credential-shaped string on any surface ------------
    # The FULL synthetic location / number-id markers ride inside the machine
    # JSON payload a consumer reads by design (the same tolerance golden_title
    # applies to its composite key); every OPERATOR-facing mention carries
    # only the masked last-4 markers, and the full fabricated phone number
    # never rides ANY surface — the gate reports, the plan, and this self-
    # test's own stream (including its attack-refusal text) — masked only.
    all_text = (buf.getvalue() + buf2.getvalue() + lbuf.getvalue()
                + dev.getvalue())
    for token in ("pit-", "Bearer ", "+12025559876"):
        assert token not in all_text, \
            "surface leak: %r must never appear" % token

    dev.write("golden_has_phone self-test: OK (already-provisioned law "
              "pinned: the one SMS-capable number entry under the fixed "
              "markers %s, presence/truthiness only — an unmarked entry can "
              "NEVER be trusted as SMS-capable; EXECUTE law certified "
              "(provisioning NEVER runs without --execute); scope-vs-edge "
              "discrimination pinned (scope -> STOP, edge -> HELD); "
              "canonical mappingproxy-frozen immutability + deep-copy "
              "surface; 13 attack fixtures refused (blank / drifted phone "
              "marker, drifted id marker, marker not True, missing marker, "
              "full id on the surface, non-golden location, "
              "already-provisioned lost, EXECUTE law lost, no SMS-capable "
              "number, two numbers, extra entries, unmarked listing entry); "
              "payload + listing gates exit 0 on the golden state, 5 on "
              "every drift; BROWSER UA pinned; never-print)\n"
              % ", ".join(SMS_ENABLED_KEYS))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="golden_has_phone.py",
        description="Golden phone-provisioned fixture for the U23 self-tests "
                    "(Skill 59): the canonical SMS-capable-number-"
                    "already-present state — the one SMS-capable number "
                    "entry under the fixed marker keys, already-provisioned "
                    "truth, EXECUTE law certified — fail-closed, offline, "
                    "never prints a token.")
    ap.add_argument("cmd", nargs="?", choices=["payload", "listing", "plan",
                                               "self-test"],
                    default="payload")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the U07/U08/U09 siblings use).
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
            # phone-provisioned surface — the one SMS-capable number, the
            # masked markers, the already-provisioned truth, the EXECUTE law.
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "surface": "provision_sms_phone",
                "location": GOLDEN_LOCATION_MASKED,
                "id_masked": GOLDEN_NUMBER_ID_MASKED,
                "phone_masked": GOLDEN_PHONE_MASKED,
                "already_provisioned": ALREADY_PROVISIONED,
                "execute_required": EXECUTE_REQUIRED_FOR_PROVISION,
                "note": "offline plan only — synthetic fixture markers, no "
                        "network, no credential needed; a LIVE provisioning "
                        "write must ride the house clients (CAF_BROWSER_UA "
                        "on every request — CF 1010 law); the provisioning "
                        "ACTION is Trevor-gated (--execute) — the gate lives "
                        "in the provisioner, never in a fixture",
            }, indent=2, sort_keys=True))
            return EX_OK
        # payload: the candidate provisioned-state payload arrives on stdin,
        # read from NO network (the live listing surface is the sibling
        # provisioner, which rides the house rail clients and their
        # CAF_BROWSER_UA — this fixture never touches the wire). The
        # candidate is a {"location": ..., "id": ..., "phoneNumber": ...,
        # "id_masked": ..., "phone_masked": ..., "already_provisioned": ...,
        # "execute_required": ...} provisioned-state payload object; with
        # none, the golden state itself is judged.
        try:
            candidate = json.load(sys.stdin)
        except ValueError as exc:
            sys.stderr.write("[golden-has-phone] the provisioned-state "
                             "payload on stdin is not valid JSON: %s\n" % exc)
            return EX_MISMATCH
        if args.cmd == "listing":
            return listing(candidate)
        return payload(candidate)
    except FixtureError as exc:
        sys.stderr.write("[golden-has-phone] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[golden-has-phone] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
