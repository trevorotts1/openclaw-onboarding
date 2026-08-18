#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u23_modules/attack_no_phone.py
# NO-PHONE ATTACK FIXTURE (U23 tooling) — the fail-closed PHONE-LAW gate over
# the LeadConnector /phones/numbers listing surface: a location is VERIFIED
# only when an SMS-capable number is present on its listing; ANY listing that
# carries no SMS-capable number — above all a listing with NO number at all —
# means PROVISIONING IS NEEDED, and that state is REFUSED as a pass, never
# judged a clean read, never a silent fallback. It is the attack half of the
# U23 phone-law pair: the sibling golden_has_phone.py ships the GOLDEN state
# (an SMS-capable number present -> idempotent no-op, exit 0) that the SAME
# gate must PASS; THIS module ships the ATTACK state — the location with NO
# SMS-capable number, the exact state the operator must provision — that the
# SAME gate must REFUSE and report via the dry-run plan.
#
# WHY THE NO-PHONE LISTING IS THE U23 ATTACK: every SMS surface of the engine
# (stage gate nudges, snapshot-import notifications, per-stage SMS links)
# delivers through the location's SMS-capable number, and provisioning is
# GET-first idempotent (provision_sms_phone.py: list /phones/numbers, create
# only when no SMS-capable number exists). A listing that serves NO number —
# or only numbers without the SMS marker — is indistinguishable at the read
# step from a location that was never provisioned: the API call succeeds, the
# JSON parses, and the numbers array simply carries nothing SMS-capable — no
# error, no exception, just no SMS surface. A verifier that treated "no
# SMS-capable number" as a clean read would report the location as verified
# with NO SMS delivery path, and every subsequent SMS gate would fail against
# a phantom number. THIS module exists so that state is REFUSED at the gate:
# the dry-run plan reports provision_needed TRUE and what --execute would do,
# and the refusal names the two laws at once — the state law (AF-AE-PROVPHONE-
# NO-PHONE: provisioning is needed) and the action law (AF-AE-PROVPHONE-
# NO-EXECUTE: provisioning is a GHL-gated ACTION and REQUIRES --execute).
#
# WHAT THIS OWNS
#   1. verify(payload) — the fail-closed gate over a /phones/numbers LISTING
#      PAYLOAD ({"numbers": [...]} — EXACTLY the object a live
#      GET /phones/numbers?locationId=<loc> read serves, with the same
#      "data"/"results" fallback keys and bare-list form the provisioner's
#      list_phone_numbers accepts, so the live surface and the offline attack
#      surface share ONE implementation of the phone law):
#        - an SMS-capable number present (presence/truthiness on the FIXED
#          key set smsEnabled/sms_enabled, via provision_sms_phone._sms_enabled
#          — NEVER re-implemented) -> ("PASS", ...) with the masked marker
#          and the count read back
#        - NO number at all, only non-SMS-capable numbers, an unmarked entry
#          (SMS marker MISSING — never silently trusted), or a malformed
#          payload -> raises NoPhoneError (STOP/mismatch family, never a
#          pass, never a silent fallback) — the empty listing is refused UP
#          FRONT with its own loud message, so the no-phone attack never
#          shares the refusal path with a malformed read
#   2. dry_run(payload) — the OFFLINE dry-run plan body (the mirror of
#      provision_sms_phone.plan_action's report: ok / dry_run / location /
#      listed / state / provision_needed): the no-phone listing is reported
#      state "needs-provision" with provision_needed TRUE and exactly what
#      --execute would do — the dry-run REPORT is the law surface of the U23
#      action gate (package contract: "Without --execute the module must
#      report what it WOULD do and exit without mutating").
#   3. payload(*, execute, out) — the CLI gate: emits the ONE JSON report
#      object (contract / ok / verdict / provision_needed / listed / found /
#      location / execute / would_do / detail); on the no-phone state,
#      without --execute it STOPS (exit 2, AF-AE-PROVPHONE-NO-EXECUTE — the
#      provisioning POST is GHL-gated and NEVER runs without the explicit
#      execute flag; THIS fixture reports the plan and never mutates), and
#      WITH --execute it still never provisions (this fixture is DATA — the
#      mutation lives in provision_sms_phone.py) and exits 5 (AF-AE-PROVPHONE-
#      NO-PHONE, the data-state mismatch PROVEN in found via masked markers
#      and the explicit "(no numbers)" marker — a gap is never a fabricated
#      pass and never a silent failure).
#   4. self_test() — OFFLINE (no network, no credentials, no client, no
#      write): the golden listing PASSES (exit 0 through the CLI gate, the
#      idempotent no-op), the no-phone attack listings (empty / SMS-false /
#      SMS-marker-missing) are each REFUSED with the dry-run plan reporting
#      provision_needed TRUE, the malformed payloads are refused, and the
#      never-print law is asserted across every surface. A tamper NEVER
#      masquerades as exit 1 — it is exit 4 (AF-AE-PROVPHONE-ATTACK family,
#      the provisioner's own self-test convention), never 'unexpected error'.
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py /
# provision_sms_phone.py / the sibling attack fixtures):
#   - A fixture is DATA, not code: this module performs NO I/O and NO network
#     call and holds NO client — it can never leak a token and can never
#     mutate by construction. Nothing here reads an env var or touches the
#     wire.
#   - ONE implementation of the SMS-capable law: this module reuses
#     provision_sms_phone._sms_enabled and _mask_number (imported BY NAME)
#     instead of re-implementing them, so the attack fixture and the
#     provisioner can never drift on what "SMS-capable" means.
#   - BROWSER UA: any module that TALKS to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a browser
#     User-Agent on every request — urllib's default "Python-urllib/x.y" is
#     403'd at the WAF edge (CF error 1010) before it ever reaches the API.
#     This fixture makes no request of its own and therefore defines no UA
#     constant of its own; the client that DOES (reg.CafClient inside
#     provision_sms_phone.py) already sends reg.CAF_BROWSER_UA on every
#     request — the proven edge fix (W0.6 / GK-09 discipline). The --live
#     surface pipes a listing in and reads NOTHING from the network; the
#     live reader is provision_sms_phone.list_phone_numbers, which rides
#     reg.CafClient.
#   - FAIL-CLOSED: an EMPTY listing, a listing with no SMS-capable number, an
#     unmarked entry, a malformed payload — every deviation REFUSES
#     (NoPhoneError / exit 2 or 5), never a blind pass, never a fabricated
#     success.
#   - NEVER print a secret value or a full phone number: numbers surface as
#     masked markers only (last 4 digits, provision_sms_phone._mask_number);
#     the location id surfaces as the masked marker via reg._mask_location.
#     The masked marker is the PROVEN-presence marker — never a fabrication.
#   - PROVISIONING REQUIRES --execute (Trevor-gated, pinned as law here and
#     in provision_sms_phone.py): the no-phone state without --execute STOPS
#     (exit 2, AF-AE-PROVPHONE-NO-EXECUTE) after reporting the dry-run plan —
#     the module reports what it WOULD do and exits without mutating. This
#     fixture never provisions even with --execute: the GHL-gated ACTION
#     lives in provision_sms_phone.py provision --execute.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface.
#
# EXIT CODES (house convention 0/1/2/3/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified PASS — an SMS-capable number is present on the listing (the
#      idempotent no-op state; nothing to provision; also self-test PASS and
#      plan OK)
#   1  unexpected error
#   2  STOP refusal — the no-phone state WITHOUT --execute: provisioning is a
#      GHL-gated ACTION and REQUIRES the explicit execute flag
#      (AF-AE-PROVPHONE-NO-EXECUTE; the dry-run plan reports what --execute
#      would do, nothing is mutated); also usage (no gate mode selected) and
#      invalid listing JSON on stdin
#   4  self-test FAILED — an attack fixture was NOT refused
#      (AF-AE-PROVPHONE-ATTACK family; a tamper NEVER masquerades as exit 1)
#   5  data or read-back mismatch — the no-phone attack state WITH --execute
#      (AF-AE-PROVPHONE-NO-PHONE: provisioning needed and PROVEN in found;
#      this fixture still never provisions — run
#      provision_sms_phone.py provision --execute), or a malformed listing
#      payload
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# --plan and --self-test are OFFLINE and need no token and no network):
#   attack_no_phone.py --plan             # offline: the phone law with sources
#   attack_no_phone.py --live < listing.json
#                                        # pipes a /phones/numbers listing in
#   attack_no_phone.py --live --execute < listing.json
#                                        # same gate; the execute flag named
#                                        # (the fixture STILL never provisions)
#   attack_no_phone.py --self-test        # offline golden + attack fixtures
#
#   # the canonical live pairing (reader -> attack gate):
#   provision_sms_phone.py plan --location-id ... | attack_no_phone.py --live
#
# STDLIB ONLY (json + argparse). Calls NO model. Reuses anthology_registry
# (exit codes, _stop, _mask_location) and provision_sms_phone (_sms_enabled,
# _mask_number, SMS_ENABLED_KEYS) — the ONE implementation of the phone law.
# =============================================================================
"""attack_no_phone.py — no-phone attack fixture for the U23 phone law: REFUSES
any /phones/numbers listing with no SMS-capable number (the empty listing
included) and reports provisioning-needed via the dry-run plan, pinning the
--execute law — never a pass, never a mutation."""

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
# helper surfaces; provision_sms_phone owns the ONE implementation of the
# SMS-capable law (presence/truthiness on the fixed key set) and the masked
# number marker — reused here BY NAME, never re-implemented.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import provision_sms_phone as phone  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

FIXTURE_CONTRACT = "anthology-engine-attack-no-phone"

# The ONE fixed report contract on every surface (plan / live / self-test).
_REPORT = {
    "contract": FIXTURE_CONTRACT,
    "schema_version": 1,
}

# The marker that PROVES the empty listing in `found` — the empty state must
# never masquerade as a named number and never as a blank "(none)".
_EMPTY_MARKER = "(no numbers)"

# The refusal family codes (the provisioner's AF-AE-PROVPHONE-* scheme).
CODE_NO_PHONE = "AF-AE-PROVPHONE-NO-PHONE"
CODE_NO_EXECUTE = "AF-AE-PROVPHONE-NO-EXECUTE"

# Deterministic SYNTHETIC fixture data — never a live id, never a live
# number: the payloads the self-test ships are built from these, so shipping
# them is harmless. The numbers are canonical fake 202-555 test numbers (the
# same synthetic surface provision_sms_phone's own self-test uses); only
# masked markers ever reach an operator surface.
GOLDEN_NUMBER_ID = "num_GOLDEN"
GOLDEN_NUMBER_FULL = "+12025559876"   # fixture internals, never a surface
SUSPECT_NUMBER_ID = "num_SUSPECT"
SUSPECT_NUMBER_FULL = "+12025550123"  # fixture internals, never a surface
FIXTURE_LOCATION = "loc_QcDX"         # fixture internals, never a surface


class NoPhoneError(Exception):
    """A fail-closed verification refusal (STOP/mismatch family): the listing
    carries no SMS-capable number (the U23 attack state — an empty array, a
    non-SMS-capable set, an unmarked entry), or the payload cannot be judged
    at all. `code` names the refusal family the CLI maps to an exit code."""

    def __init__(self, message: str, code: str = CODE_NO_PHONE):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# The fail-closed gate over a /phones/numbers LISTING payload. The payload is
# {"numbers": [...]} — EXACTLY the object a live GET /phones/numbers read
# serves, with the same "data"/"results" fallback keys and bare-list form
# provision_sms_phone.list_phone_numbers accepts, so the live surface and the
# offline attack surface share ONE implementation of the phone law. The
# SMS-capable semantics are provision_sms_phone._sms_enabled — NEVER
# re-implemented here (one implementation, zero drift).
# ---------------------------------------------------------------------------
def _extract_numbers(payload) -> list:
    """The numbers list out of a listing payload — the one-to-one mirror of
    provision_sms_phone.list_phone_numbers' extraction (the same key set:
    "numbers", then "data"/"results", then a bare list). Raises NoPhoneError
    (MALFORMED) on a payload that cannot be judged — a malformed read is
    NEVER a pass (fail-closed)."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise NoPhoneError(
            "listing payload is %r, not an object or list — refusing to "
            "judge it." % type(payload).__name__, code="MALFORMED")
    for key in ("numbers", "data", "results"):
        v = payload.get(key)
        if v is not None:
            if not isinstance(v, list):
                raise NoPhoneError(
                    "listing %r is %r, not a list — refusing."
                    % (key, type(v).__name__), code="MALFORMED")
            return v
    raise NoPhoneError(
        "listing payload has no numbers array ('numbers' / 'data' / "
        "'results') — a malformed read is NEVER a pass (fail-closed).",
        code="MALFORMED")


def _found_markers(numbers) -> list:
    """The masked markers of a listing — or the EXPLICIT empty-listing marker,
    so the no-phone state is PROVEN in `found` and never collapses into a
    bare "(none)". Masked markers are the proven-presence surface (last 4
    digits only, phone._mask_number) — a full number is never surfaced."""
    if not numbers:
        return [_EMPTY_MARKER]
    markers = [phone._mask_number(n.get("phoneNumber") or n.get("number") or "")
               for n in numbers if isinstance(n, dict)]
    return markers or [_EMPTY_MARKER]


def verify(payload_obj: dict) -> tuple:
    """Verify a /phones/numbers listing against the SMS-capable phone law,
    fail-closed.

    Returns ("PASS", detail, markers, count) when an SMS-capable number is
    present on the listing (the golden state: the idempotent no-op — nothing
    to provision). Raises NoPhoneError on ANY other outcome — the EMPTY
    listing (refused UP FRONT, never judged "clean"), a listing whose numbers
    are all non-SMS-capable, an unmarked entry (SMS marker MISSING is never
    silently trusted as capable), a malformed payload — never a silent
    fallback. The masked markers are surfaced in the message (never
    fabricated; a masked marker cannot be a credential and a full number is
    never surfaced), so the gap is PROVEN present, not assumed.
    """
    numbers = _extract_numbers(payload_obj)
    if not numbers:
        # THE U23 ATTACK (empty): the API call succeeded, the JSON parsed,
        # and the array is empty — no error, no exception, just no SMS
        # surface. Refused UP FRONT with its own loud message — never judged
        # a clean read, never a blind pass.
        raise NoPhoneError(
            "AF-AE-PROVPHONE-NO-PHONE: the /phones/numbers listing is EMPTY "
            "(%s) — no number at all is bound at this location. Every SMS "
            "surface delivers through the location's SMS-capable number; a "
            "clean read of a fully provisioned location must serve one. "
            "Provisioning is needed." % _EMPTY_MARKER)
    for n in numbers:
        if isinstance(n, dict) and phone._sms_enabled(n):
            num = n.get("phoneNumber") or n.get("number") or ""
            return ("PASS", "SMS-capable number present",
                    [phone._mask_number(num)], 1)
    # The listing has numbers, but NONE is SMS-capable — including the
    # unmarked entry (SMS marker MISSING, not False): the entry cannot be
    # trusted as verified SMS. Provisioning is needed; never a pass.
    raise NoPhoneError(
        "AF-AE-PROVPHONE-NO-PHONE: the /phones/numbers listing carries "
        "%d number(s) but NONE is SMS-capable (found: %s) — an unmarked "
        "entry is never silently trusted. Every SMS surface delivers "
        "through the location's SMS-capable number; provisioning is needed."
        % (len(numbers), ", ".join(_found_markers(numbers))))


# ---------------------------------------------------------------------------
# The dry-run plan — the OFFLINE report body (no network, no credentials, no
# mutation): what --execute WOULD do. The mirror of provision_sms_phone
# plan_action's report (ok / dry_run / location / listed / state /
# provision_needed), so the plan surfaces of the provisioner and its attack
# fixture speak the same JSON.
# ---------------------------------------------------------------------------
def dry_run(payload_obj: dict) -> dict:
    """The dry-run plan over a listing payload: state "already-provisioned"
    (an SMS-capable number exists — nothing would be done) or
    "needs-provision" (the U23 attack state — with --execute the provisioner
    would provision one number and verify SMS sending). A payload that
    cannot be judged at all plans "unreadable" — never a fabricated
    provisioning verdict. Never prints a full number; the location is the
    masked marker; provision_needed is the boolean machine surface."""
    masked = reg._mask_location(FIXTURE_LOCATION)
    try:
        numbers = _extract_numbers(payload_obj)
    except NoPhoneError as exc:
        return {
            "ok": True, "dry_run": True, "location": masked,
            "listed": 0, "state": "unreadable",
            "provision_needed": None,
            "would_do": "cannot plan a listing that cannot be read "
                        "(malformed payload)",
            "refusal": exc.code,
        }
    try:
        verify(payload_obj)
    except NoPhoneError as exc:
        return {
            "ok": True, "dry_run": True, "location": masked,
            "listed": len(numbers), "state": "needs-provision",
            "provision_needed": True,
            "would_do": "provision one SMS-capable number and verify SMS "
                        "sending (provision_sms_phone.py provision --execute; "
                        "the POST is a GHL-gated ACTION)",
            "refusal": exc.code,
        }
    return {
        "ok": True, "dry_run": True, "location": masked,
        "listed": len(numbers), "state": "already-provisioned",
        "provision_needed": False,
        "would_do": "skip provisioning (an SMS-capable number already "
                    "exists)",
    }


# ---------------------------------------------------------------------------
# CLI gate — ONE JSON object on stdout, human notes on stderr, fail-closed.
# ---------------------------------------------------------------------------
def _report(ok: bool, verdict: str, plan: dict, found, execute: bool,
            detail: str, code: str = "PASS") -> None:
    sys.stdout.write(json.dumps(dict(
        _REPORT,
        ok=ok,
        verdict=verdict,
        code=code,
        provision_needed=plan["provision_needed"],
        listed=plan["listed"],
        found=found,
        location=plan["location"],
        execute=execute,
        would_do=plan["would_do"],
        detail=detail,
    ), indent=2, sort_keys=True) + "\n")


def payload(payload_obj: dict, *, execute: bool = False, out=None) -> int:
    """Run the fail-closed phone-law gate over a listing payload. Returns the
    exit code: 0 PASS (idempotent no-op), 2 STOP (needs provision WITHOUT
    --execute — the GHL-gated ACTION boundary, after reporting the dry-run
    plan), 5 refusal (needs provision WITH --execute — the attack state is
    PROVEN but THIS fixture never provisions; or a malformed payload). Human
    notes go to stderr; the ONE JSON report object lands on stdout."""
    out = out or sys.stderr
    plan = dry_run(payload_obj)
    try:
        status, detail, markers, _count = verify(payload_obj)
    except NoPhoneError as exc:
        if exc.code == "MALFORMED":
            found = [_EMPTY_MARKER]
            reg._stop(out, "The /phones/numbers listing cannot be judged.",
                      [str(exc),
                       "Pipe the exact JSON provision_sms_phone.py plan "
                       "emits (a listing with a numbers array)."])
            _report(False, "FAIL", plan, found, execute, str(exc),
                    code=exc.code)
            return EX_MISMATCH
        found = _found_markers(_extract_numbers(payload_obj))
        # ---- the U23 ATTACK state: provisioning needed -------------------
        # 1. the --execute law (Trevor-gated): provisioning is a GHL-gated
        #    ACTION and REQUIRES the explicit execute flag. Without it the
        #    fixture reports the dry-run plan (what --execute WOULD do) and
        #    STOPS without mutating — the package contract verbatim.
        if not execute:
            reg._stop(out, "This location needs SMS provisioning and "
                           "--execute was NOT passed.",
                      ["AF-AE-PROVPHONE-NO-EXECUTE: the provisioning POST is "
                       "a GHL-gated ACTION and REQUIRES --execute.",
                       "Dry-run report (what --execute WOULD do): state "
                       "needs-provision; %s" % plan["would_do"],
                       "Nothing was provisioned, nothing was sent — this "
                       "fixture never mutates."])
            _report(False, "PROVISION-NEEDED", plan, found, execute, str(exc),
                    code=CODE_NO_EXECUTE)
            return EX_STOP
        # 2. with --execute the attack state is still NEVER a pass — and this
        #    fixture is DATA: the mutation lives in provision_sms_phone.py.
        reg._stop(out, "This location needs SMS provisioning "
                       "(AF-AE-PROVPHONE-NO-PHONE).",
                  [str(exc),
                   "Proven on the listing: %s"
                   % (", ".join(found) or "(none)"),
                   "THIS fixture never provisions — run "
                   "provision_sms_phone.py provision --execute (the GHL-"
                   "gated ACTION), then re-run this gate."])
        _report(False, "PROVISION-NEEDED", plan, found, execute, str(exc),
                code=CODE_NO_PHONE)
        return EX_MISMATCH
    _report(True, "PASS", plan, markers, execute,
            "%s (%s) — the idempotent no-op state; nothing to provision."
            % (detail, markers[0]))
    out.write("[attack-no-phone] OK: SMS-capable number %s present; "
              "nothing to provision (idempotent no-op).\n" % markers[0])
    return EX_OK


# ---------------------------------------------------------------------------
# Offline self-test — golden + attack fixtures, zero network, zero secrets,
# zero writes. A FAILED self-test is exit 4 (enforced violation,
# AF-AE-PROVPHONE-ATTACK family), NEVER 'unexpected error' — the house
# convention.
# ---------------------------------------------------------------------------
def _golden_payload() -> dict:
    """The golden listing — an SMS-capable number present (smsEnabled True),
    exactly the row a live read of a fully provisioned location serves."""
    return {"numbers": [{"id": GOLDEN_NUMBER_ID,
                         "phoneNumber": GOLDEN_NUMBER_FULL,
                         "smsEnabled": True}]}


def _non_sms_payload() -> dict:
    """The U23 attack, non-empty: numbers present but NONE SMS-capable — the
    exact object a live read of a location whose numbers carry no SMS marker
    serves."""
    return {"numbers": [{"id": SUSPECT_NUMBER_ID,
                         "phoneNumber": SUSPECT_NUMBER_FULL,
                         "smsEnabled": False}]}


def _unmarked_payload() -> dict:
    """The U23 attack, unmarked: a number whose SMS marker is MISSING (not
    False) — the read is fine, but the entry cannot be trusted as
    SMS-capable. Never silently trusted."""
    return {"numbers": [{"id": SUSPECT_NUMBER_ID,
                         "phoneNumber": SUSPECT_NUMBER_FULL}]}


def self_test(out=None) -> int:
    """OFFLINE self-test: golden + attack fixtures, no network, no secrets,
    no writes. A tamper NEVER masquerades as exit 1 — it is exit 4
    (AF-AE-PROVPHONE-ATTACK family)."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[attack-no-phone] SELF-TEST FAILED "
                         "(AF-AE-PROVPHONE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    # ---- the law surfaces are pinned byte-exact ---------------------------
    assert phone.SMS_ENABLED_KEYS == ("smsEnabled", "sms_enabled"), \
        "the SMS-capable key set drifted from the U23 contract: %r" \
        % (phone.SMS_ENABLED_KEYS,)
    assert phone._mask_number(GOLDEN_NUMBER_FULL) == "...9876"
    assert phone._mask_number("") == "(short number)"
    assert phone._sms_enabled({"smsEnabled": True}) is True
    assert phone._sms_enabled({"smsEnabled": 0}) is False
    assert phone._sms_enabled({"sms_enabled": "false"}) is True  # truthy string stays truthy
    assert phone._sms_enabled({"other": True}) is False

    # ---- golden state: SMS-capable number present -> PASS, idempotent -----
    status, detail, markers, count = verify(_golden_payload())
    assert status == "PASS", "golden listing: %s" % detail
    assert markers == ["...9876"], "the masked marker must PROVE presence: %r" % markers
    plan_g = dry_run(_golden_payload())
    assert plan_g["state"] == "already-provisioned"
    assert plan_g["provision_needed"] is False
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(_golden_payload(), out=io.StringIO())
    assert rc == EX_OK, "golden payload must exit 0, got %s" % rc
    report = json.loads(buf.getvalue())
    assert report["ok"] is True and report["verdict"] == "PASS"
    assert report["provision_needed"] is False
    assert report["found"] == ["...9876"]
    assert report["contract"] == FIXTURE_CONTRACT
    # the golden no-op must pass EVEN without --execute (nothing to provision
    # never needs the execute flag) and must never be written
    assert rc == EX_OK

    # ---- THE U23 ATTACKS: every no-SMS-capable state REFUSED --------------
    # 1. THE U23 ATTACK (empty): {"numbers": []} — a location with NOTHING
    #    bound -> refusal, and the marker PROVEN in the message
    a1 = {"numbers": []}
    try:
        verify(a1)
        raise AssertionError("empty-listing attack was NOT refused")
    except NoPhoneError as exc:
        assert _EMPTY_MARKER in str(exc), \
            "the refusal must PROVE the empty listing: %s" % exc
    plan_a1 = dry_run(a1)
    assert plan_a1["state"] == "needs-provision"
    assert plan_a1["provision_needed"] is True
    # without --execute -> STOP (exit 2, NO-EXECUTE), the dry-run plan named
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = payload(a1, out=io.StringIO())
    assert rc2 == EX_STOP, (
        "empty listing without --execute must STOP "
        "(exit 2), got %s" % rc2)
    report2 = json.loads(buf2.getvalue())
    assert report2["ok"] is False and report2["verdict"] == "PROVISION-NEEDED"
    assert report2["code"] == CODE_NO_EXECUTE, \
        "the report must name the refusal code: %s" % report2["code"]
    assert report2["provision_needed"] is True
    assert report2["execute"] is False
    assert report2["found"] == [_EMPTY_MARKER], \
        "the empty listing must be PROVEN in found: %s" % report2["found"]
    # with --execute -> still REFUSED (exit 5, NO-PHONE); the fixture is DATA
    buf3 = io.StringIO()
    with contextlib.redirect_stdout(buf3):
        rc3 = payload(a1, execute=True, out=io.StringIO())
    assert rc3 == EX_MISMATCH, (
        "empty listing with --execute must exit 5, "
        "got %s" % rc3)
    report3 = json.loads(buf3.getvalue())
    assert report3["ok"] is False and report3["verdict"] == "PROVISION-NEEDED"
    assert report3["code"] == CODE_NO_PHONE, \
        "the report must name the refusal code: %s" % report3["code"]
    assert report3["provision_needed"] is True and report3["execute"] is True

    # 2. numbers present, NONE SMS-capable -> refused (provisioning needed)
    for attack, name in ((_non_sms_payload(), "non-SMS listing"),
                         (_unmarked_payload(), "unmarked-entry listing")):
        try:
            verify(attack)
            raise AssertionError("%s attack was NOT refused" % name)
        except NoPhoneError as exc:
            assert CODE_NO_PHONE in str(exc), \
                "%s: %s" % (name, exc)
        plan = dry_run(attack)
        assert plan["state"] == "needs-provision" and plan["provision_needed"] is True
        buf4 = io.StringIO()
        with contextlib.redirect_stdout(buf4):
            rc4 = payload(attack, out=io.StringIO())
        assert rc4 == EX_STOP, "%s without --execute must STOP, got %s" % (name, rc4)
        report4 = json.loads(buf4.getvalue())
        assert report4["provision_needed"] is True
        assert report4["found"] == [phone._mask_number(SUSPECT_NUMBER_FULL)], \
            "%s: masked marker must prove the gap: %s" % (name, report4["found"])

    # 3. malformed payloads -> refused, never a pass
    for bad in ({"no_numbers_here": True},
                {"numbers": "not-a-list"},
                "not-an-object"):
        try:
            verify(bad)
            raise AssertionError("malformed payload was NOT refused: %r" % (bad,))
        except NoPhoneError:
            pass
    buf5 = io.StringIO()
    with contextlib.redirect_stdout(buf5):
        rc5 = payload({"numbers": "not-a-list"}, execute=True, out=io.StringIO())
    assert rc5 == EX_MISMATCH, "malformed payload must exit 5, got %s" % rc5

    # ---- the --execute law pinned at the gate level -----------------------
    # a needs-provision state NEVER passes without the flag, and the fixture
    # NEVER mutates even with the flag (DATA, not an ACTION). The report
    # JSON is captured, never leaked to the self-test surface.
    buf6 = io.StringIO()
    with contextlib.redirect_stdout(buf6):
        rc6a = payload(a1, out=io.StringIO())
    assert rc6a == EX_STOP
    buf7 = io.StringIO()
    with contextlib.redirect_stdout(buf7):
        rc7a = payload(a1, execute=True, out=io.StringIO())
    assert rc7a == EX_MISMATCH

    # ---- never-print: no token, no location id, no full number ever
    #      reaches an operator surface (the self-test's own dev streams and
    #      the JSON summaries — raw test-fixture internals are not surfaces)
    all_text = (dev.getvalue() + buf.getvalue() + buf2.getvalue()
                + buf3.getvalue() + buf4.getvalue() + buf5.getvalue()
                + buf6.getvalue() + buf7.getvalue())
    for token in ("pit-", FIXTURE_LOCATION, GOLDEN_NUMBER_FULL,
                  SUSPECT_NUMBER_FULL, "SEKRIT", "Bearer "):
        assert token not in all_text, \
            "surface leak: %r must never appear" % token
    # the masked markers ARE the proven-presence surface and must appear
    assert "...9876" in buf.getvalue()
    assert phone._mask_number(SUSPECT_NUMBER_FULL) in buf4.getvalue()

    dev.write("attack_no_phone self-test: OK (phone law pinned to "
              "provision_sms_phone._sms_enabled key set; golden SMS listing "
              "-> idempotent no-op PASS exit 0; 3 no-phone attacks refused — "
              "empty listing / non-SMS numbers / unmarked entry — each "
              "reporting the dry-run plan provision_needed TRUE; without "
              "--execute STOP exit 2 AF-AE-PROVPHONE-NO-EXECUTE, with "
              "--execute exit 5 AF-AE-PROVPHONE-NO-PHONE and STILL never a "
              "mutation; malformed payloads refused; never-print; masked "
              "markers proven)\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="attack_no_phone.py",
        description="No-phone attack fixture for the U23 SMS phone law "
                    "(Skill 59): REFUSES any /phones/numbers listing with no "
                    "SMS-capable number — the EMPTY {'numbers': []} state (a "
                    "location with no number bound) included — and reports "
                    "provisioning-needed via the dry-run plan. Provisioning "
                    "is a GHL-gated ACTION and REQUIRES --execute; this "
                    "fixture reports what --execute WOULD do and NEVER "
                    "mutates. One JSON object on stdout; fail-closed; never "
                    "prints a secret value or a full phone number.")
    ap.add_argument("--live", action="store_true",
                    help="read a /phones/numbers listing JSON from stdin "
                         "(the exact shape provision_sms_phone.py plan "
                         "emits) and gate it against the SMS phone law")
    ap.add_argument("--execute", action="store_true",
                    help="operator gate: the GHL-gated ACTION flag. Naming "
                         "it confirms the operator may provision — the "
                         "fixture still only reports; the POST lives in "
                         "provision_sms_phone.py provision --execute")
    ap.add_argument("cmd", nargs="?", choices=["plan", "self-test"],
                    help="offline subcommands (no network, no credentials)")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the sibling adapters use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()

        if args.cmd == "plan":
            # offline plan: no network, no credentials — the phone law with
            # its sources, including the attack this fixture exists for and
            # the --execute gate it pins.
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "law": "a location is VERIFIED only when an SMS-capable "
                       "number is present on its /phones/numbers listing "
                       "(presence/truthiness on the fixed key set "
                       "smsEnabled/sms_enabled, provision_sms_phone "
                       "_sms_enabled)",
                "attack": "no SMS-capable number on the listing — the U23 "
                          "no-phone state (empty {'numbers': []}, non-SMS "
                          "numbers, or an unmarked entry): provisioning is "
                          "needed, and the state is REFUSED, never judged a "
                          "clean read",
                "dry_run": "the plan reports provision_needed TRUE and what "
                           "--execute WOULD do; nothing is ever mutated by "
                           "this fixture",
                "execute_law": "provisioning is a GHL-gated ACTION and "
                               "REQUIRES --execute (AF-AE-PROVPHONE-NO-"
                               "EXECUTE, exit 2 without it); the POST lives "
                               "in provision_sms_phone.py provision "
                               "--execute",
                "note": "offline plan only — no network, no credential needed",
            }, indent=2, sort_keys=True))
            return EX_OK

        # ---- live gate: the listing comes in on stdin, read from NO network
        #      (the live READER is provision_sms_phone.list_phone_numbers,
        #      which rides reg.CafClient and its CAF_BROWSER_UA — this
        #      fixture never touches the wire) ----
        if not args.live:
            reg._stop(sys.stderr, "No gate mode selected.",
                      ["Pass --live with a /phones/numbers listing JSON on "
                       "stdin (provision_sms_phone.py plan | "
                       "attack_no_phone.py --live), or --plan / --self-test "
                       "(offline)."])
            return EX_STOP
        try:
            listing = json.load(sys.stdin)
        except ValueError as exc:
            reg._stop(sys.stderr,
                      "The /phones/numbers listing on stdin is not valid JSON.",
                      ["%s" % exc,
                       "Pipe the exact JSON provision_sms_phone.py plan "
                       "emits."])
            return EX_STOP
        return payload(listing, execute=args.execute, out=sys.stderr)

    except NoPhoneError as exc:
        sys.stderr.write("[attack-no-phone] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except FileNotFoundError as exc:
        sys.stderr.write("[attack-no-phone] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[attack-no-phone] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
