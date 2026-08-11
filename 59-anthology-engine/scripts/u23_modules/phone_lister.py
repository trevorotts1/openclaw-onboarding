#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u23_modules/phone_lister.py  (U23 tooling)
# LIVE PHONE LISTER — READ-ONLY GET of the Convert and Flow location's existing
# phone numbers, fail-closed. This is the GET-first side of the engine's phone
# surface: every provisioning decision starts from THIS listing, never from
# memory and never from a blind POST.
#
# WHAT THIS IS (the ACTION is GHL-scope-gated; the tooling ships now):
#   The client's Convert and Flow location carries phone numbers, some
#   SMS-capable (the surface the U23 SMS provisioner — provision_sms_phone.py —
#   and every SMS delivery path depend on). This module lists what is ALREADY
#   there and never assumes: a live GET /phones/numbers, per-number capability
#   read, masked markers on every human surface, and a machine JSON summary.
#   The v2 public surface this module uses:
#
#     GET    /phones/numbers?locationId=<loc>            list existing numbers
#     GET    /phones/numbers/<id>?locationId=<loc>       one number by id
#     POST   /phones/numbers                             provision (GHL-gated)
#
#   IDEMPOTENCY LAW (GET-first, provision only if absent): the module LISTS the
#   location's numbers first and provisions ONLY when no SMS-capable number is
#   already present. A location that already carries an SMS-enabled number is
#   VERIFIED, never re-provisioned (exit 0, idempotent no-op — never a second
#   number, never a second charge). A write is never trusted without read-back:
#   after a create, the module GETs the number back before reporting it.
#
#   THE PROVISIONING ACTION STAYS GATED: this module NEVER provisions without
#   --execute. Default and --dry-run are read-only / plan-only (no network in
#   dry-run). The actual POST that creates a number is a GHL-scope action: it
#   runs ONLY when the operator explicitly passes --execute, which is exactly
#   the GHL-gated scope boundary.
#
# CREDENTIAL DOCTRINE: the token + location are resolved BY LABEL exactly like
# every other adapter (reg.resolve_pit / reg.resolve_location:
# CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_LOCATION_ID etc. across live process
# env then the three canonical client env stores). Values are NEVER printed
# (SET / NOT SET + masked location only); a phone number is never printed in
# full — the non-reversible last-4-digits marker only. The browser User-Agent
# rides every request via reg.CafClient (W0.6/GK-09:
# services.leadconnectorhq.com is Cloudflare-fronted and 403s urllib's default
# UA — CF 1010). The engine's scope-vs-edge-block discrimination (ScopeDenied
# vs UpstreamBlockedError) applies to every read AND write: a bare 401/403 is
# NEVER reported as a scope problem, it is HELD.
#
# AF ERROR CODES (fail-closed surfaces, house scheme):
#   AF-AE-PHONELIST-MISSING-LABEL   -> a required label (PIT / location) is NOT
#          SET or resolves to a non-pit- value. STOP (exit 2), fail-closed.
#   AF-AE-PHONELIST-READ-REFUSED    -> listing numbers for the location failed
#          (scope / validation / edge block / transport). STOP or HELD per
#          class — never a silent skip, never a provision-into-the-unknown.
#   AF-AE-PHONELIST-NO-EXECUTE      -> provisioning (POST /phones/numbers) was
#          requested without --execute. STOP; the module NEVER provisions
#          without the explicit GHL-gated execute flag.
#   AF-AE-PHONELIST-CREATE-REFUSED  -> the location exists, no matching number,
#          and the POST /phones/numbers was rejected (validation / scope /
#          edge block / transport / no id on the response). STOP, HELD or
#          MISMATCH per class — a refused create is NEVER recorded as
#          provisioned.
#   AF-AE-PHONELIST-ATTACK          -> an attack fixture tripped the OFFLINE
#          self-test. Exit 4 (enforced violation), never exit 1.
#
# EXIT CODES (house convention; nonzero STOPS/HELDs with an operator surface):
#   0  verified success (list ok / plan ok / idempotent no-op / self-test ok)
#   1  unexpected error
#   2  STOP refusal — usage error / missing credential / missing --execute
#   3  Convert and Flow API unreachable / edge block (retryable) — HELD, never
#      mislabeled as a scope problem
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-PHONELIST-* family). A tamper NEVER masquerades as exit 1.
#   5  data or read-back mismatch (a required response field missing/renamed)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr):
#   phone_lister.py list [--location-id X]     # LIVE READ-ONLY listing
#   phone_lister.py plan                       # offline: what the listing would
#                                              # report and what provision would do
#   phone_lister.py provision [--location-id X]  # live GET-first; a missing
#                                              # SMS-capable number is a STOP
#                                              # without --execute
#   phone_lister.py provision --execute        # GHL-gated: create only when
#                                              # absent, then read back
#   phone_lister.py self-test                  # offline golden + attack battery
#
# STDLIB ONLY (urllib + json), reusing anthology_registry.CafClient + credential
# resolution. Calls NO model. DOCTRINE: move in silence; NOTHING Anthropic in
# any runtime file; Convert and Flow naming in every client surface; NEVER
# print a secret value; --dry-run and --self-test are OFFLINE.
# =============================================================================
"""phone_lister.py — READ-ONLY live listing of the Convert and Flow location's
existing phone numbers (GET /phones/numbers), fail-closed, masked markers
only, with a GHL-gated (--execute) GET-first provisioning path and bounded
read-back (Skill 59, U23 tooling)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Sibling import bootstrap (mirrors the sibling adapters' convention). The
# registry does the Cloudflare browser-UA wiring + LeadConnector client +
# label resolution we reuse.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The field that marks a number as SMS-capable in the listing surface. The
# module reads presence/truthiness only, never any other field of a number.
SMS_ENABLED_KEYS = ("smsEnabled", "sms_enabled")

def _mask_number(num: str) -> str:
    """A non-reversible marker for a phone number: last 4 digits only."""
    num = (num or "").strip()
    digits = "".join(ch for ch in num if ch.isdigit())
    if len(digits) >= 4:
        return "...%s" % digits[-4:]
    return "(short number)"

def _sms_enabled(number: dict) -> bool:
    """Does this number carry SMS capability? Presence/truthiness only, on the
    fixed key set — never any other field of the number object."""
    for k in SMS_ENABLED_KEYS:
        v = number.get(k)
        if v is not None:
            return bool(v)
    return False

# ---------------------------------------------------------------------------
# LeadConnector phone surface (READ-ONLY on this client)
# ---------------------------------------------------------------------------
def list_phone_numbers(client, location_id: str):
    """GET /phones/numbers?locationId=<loc>. READ-ONLY. Returns a list of
    number dicts (each entry is only ever used for the SMS-capable marker and
    the masked number; no other field is read)."""
    out = client._request("GET", "/phones/numbers", query={"locationId": location_id})
    if isinstance(out, dict):
        for key in ("numbers", "data", "results"):
            v = out.get(key)
            if isinstance(v, list):
                return v
        return []
    if isinstance(out, list):
        return out
    return []

def get_phone_number(client, number_id: str, location_id: str):
    """GET /phones/numbers/<id>?locationId=<loc>. READ-ONLY. Returns the number
    dict or None. Used for the post-create read-back (the same verification a
    write is never trusted without)."""
    out = client._request(
        "GET", "/phones/numbers/%s" % str(number_id).strip(),
        query={"locationId": location_id})
    if isinstance(out, dict):
        for key in ("number", "phone", "data"):
            v = out.get(key)
            if isinstance(v, dict):
                return v
        if "id" in out or "phoneNumber" in out or "number" in out:
            return out
    return None

def _list_refused(out, masked, exc, held=False):
    """One refusal surface for the listing path — STOP or HELD per class, never
    a silent skip and never a scope mislabel."""
    if held:
        out.write("[phone-lister] AF-AE-PHONELIST-READ-REFUSED: the listing "
                  "for marker %s is HELD (retryable), NOT a scope problem: %s\n"
                  % (masked, exc))
        return EX_HELD
    out.write("[phone-lister] AF-AE-PHONELIST-READ-REFUSED: %s for marker %s: "
              "%s\n" % ("scope denied listing numbers" if isinstance(exc, reg.ScopeDenied)
                        else "the API rejected the listing", masked, exc))
    return EX_STOP

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
def list_action(client, location_id: str, *, out=None, jsonout=None) -> int:
    """LIVE READ-ONLY listing: GET the location's numbers and report each one
    with a masked marker + capability. Never prints a full number, never
    prints the location id, never prints a token. Fail-closed: a refused
    listing STOPs or HELDs per class."""
    out = out or sys.stderr
    masked = reg._mask_location(location_id)
    try:
        numbers = list_phone_numbers(client, location_id)
    except reg.ScopeDenied as exc:
        return _list_refused(out, masked, exc)
    except reg.CafValidation as exc:
        return _list_refused(out, masked, exc)
    except reg.CafUnreachable as exc:
        return _list_refused(out, masked, exc, held=True)

    sms_count = 0
    for n in numbers:
        if not isinstance(n, dict):
            continue
        num = n.get("phoneNumber") or n.get("number") or ""
        sms = _sms_enabled(n)
        if sms:
            sms_count += 1
        out.write("[phone-lister] (marker %s) number %s, SMS-capable: %s\n"
                  % (masked, _mask_number(num), "yes" if sms else "no"))
    out.write("[phone-lister] LISTED (marker %s): %d number(s), %d SMS-capable.\n"
              % (masked, len(numbers), sms_count))
    if jsonout is not None:
        json.dump({
            "ok": True, "action": "list", "location": masked,
            "listed": len(numbers), "sms_capable": sms_count,
            "numbers": [{
                "id": str(n.get("id") or ""),
                "number": _mask_number(n.get("phoneNumber") or n.get("number") or ""),
                "sms": _sms_enabled(n),
            } for n in numbers if isinstance(n, dict)],
        }, jsonout)
        jsonout.write("\n")
    return EX_OK

def provision_action(client, location_id: str, *, execute: bool = False,
                     out=None, jsonout=None) -> int:
    """GET-first provisioning: list, then create ONLY when no SMS-capable
    number exists, then read back. The CREATE (POST /phones/numbers) happens
    ONLY under --execute (the GHL-gated ACTION boundary). Never provisions
    into the unknown: a refused listing refuses before any create."""
    out = out or sys.stderr
    masked = reg._mask_location(location_id)

    # -- 1. READ-ONLY listing (idempotency law: GET-check before create) -------
    try:
        numbers = list_phone_numbers(client, location_id)
    except reg.ScopeDenied as exc:
        return _list_refused(out, masked, exc)
    except reg.CafValidation as exc:
        return _list_refused(out, masked, exc)
    except reg.CafUnreachable as exc:
        return _list_refused(out, masked, exc, held=True)

    found = None
    for n in numbers:
        if isinstance(n, dict) and _sms_enabled(n):
            found = n
            break
    if found is not None:
        num = found.get("phoneNumber") or found.get("number") or ""
        out.write("[phone-lister] IDEMPOTENT NO-OP (marker %s): an SMS-capable "
                  "number (%s) already exists; nothing provisioned, nothing "
                  "sent.\n" % (masked, _mask_number(num)))
        if jsonout is not None:
            json.dump({"ok": True, "action": "provision", "location": masked,
                       "provisioned": False, "already": True}, jsonout)
            jsonout.write("\n")
        return EX_OK

    # -- 2. GHL-gated ACTION boundary -----------------------------------------
    if not execute:
        out.write("[phone-lister] AF-AE-PHONELIST-NO-EXECUTE: marker %s has no "
                  "SMS-capable number and --execute was NOT passed. The "
                  "provisioning POST is a GHL-gated ACTION: STOP, nothing "
                  "created.\n" % masked)
        if jsonout is not None:
            json.dump({"ok": False, "action": "provision", "location": masked,
                       "exit": EX_STOP, "reason": "no-execute"}, jsonout)
            jsonout.write("\n")
        return EX_STOP

    # -- 3. CREATE (only under --execute) --------------------------------------
    try:
        created = client._request(
            "POST", "/phones/numbers", query={"locationId": location_id},
            body={})
    except reg.ScopeDenied as exc:
        out.write("[phone-lister] AF-AE-PHONELIST-CREATE-REFUSED: scope denied "
                  "provisioning for marker %s: %s\n" % (masked, exc))
        return EX_STOP
    except reg.CafValidation as exc:
        out.write("[phone-lister] AF-AE-PHONELIST-CREATE-REFUSED: the API "
                  "rejected the provisioning for marker %s: %s\n" % (masked, exc))
        return EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[phone-lister] AF-AE-PHONELIST-CREATE-REFUSED: the "
                  "provisioning for marker %s is HELD (retryable), never a "
                  "scope problem: %s\n" % (masked, exc))
        return EX_HELD

    created_id = ""
    if isinstance(created, dict):
        created_id = str(created.get("id") or created.get("numberId") or "").strip()
    if not created_id:
        out.write("[phone-lister] AF-AE-PHONELIST-CREATE-REFUSED: the API "
                  "responded to the provisioning POST for marker %s without a "
                  "number id (exit 5: read-back mismatch). Nothing considered "
                  "provisioned.\n" % masked)
        return EX_MISMATCH

    # -- 4. READ-BACK (a write is never trusted without read-back) -------------
    try:
        current = get_phone_number(client, created_id, location_id)
    except reg.ScopeDenied as exc:
        out.write("[phone-lister] AF-AE-PHONELIST-CREATE-REFUSED: scope denied "
                  "reading back the provisioned number for marker %s: %s\n"
                  % (masked, exc))
        return EX_STOP
    except reg.CafValidation as exc:
        out.write("[phone-lister] AF-AE-PHONELIST-CREATE-REFUSED: the API "
                  "rejected the read-back for marker %s: %s\n" % (masked, exc))
        return EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[phone-lister] AF-AE-PHONELIST-CREATE-REFUSED: the read-back "
                  "for marker %s is HELD (retryable), never a scope problem: "
                  "%s\n" % (masked, exc))
        return EX_HELD

    if current is None:
        out.write("[phone-lister] AF-AE-PHONELIST-CREATE-REFUSED: the read-back "
                  "of the provisioned number for marker %s returned no number "
                  "object (exit 5: read-back mismatch). Nothing considered "
                  "provisioned.\n" % masked)
        return EX_MISMATCH
    num = current.get("phoneNumber") or current.get("number") or ""
    out.write("[phone-lister] CREATED + READ BACK (marker %s): number %s "
              "provisioned and confirmed on read-back.\n"
              % (masked, _mask_number(num)))
    if jsonout is not None:
        json.dump({"ok": True, "action": "provision", "location": masked,
                   "provisioned": True, "already": False,
                   "number": _mask_number(num)}, jsonout)
        jsonout.write("\n")
    return EX_OK

def plan_action(out=None, jsonout=None) -> int:
    """OFFLINE plan (no network, no credential): report what the live listing
    would do and what provision would do under --execute."""
    out = out or sys.stderr
    out.write("[phone-lister] PLAN (offline): would GET /phones/numbers for "
              "the location and report each existing number (masked marker + "
              "SMS capability). If no SMS-capable number exists, provision "
              "would create ONE number — but ONLY with --execute (GHL-gated "
              "ACTION). Nothing written, nothing provisioned.\n")
    if jsonout is not None:
        json.dump({"ok": True, "action": "plan", "dry_run": True,
                   "state": "planned"}, jsonout)
        jsonout.write("\n")
    return EX_OK

# ---------------------------------------------------------------------------
# SELF-TEST: golden + attack fixtures, zero network, zero secrets, zero writes.
# Mirrors the sibling self-tests (provision_sms_phone / anthology_registry):
# an assertion failure is an ENFORCED VIOLATION, exit 4 — a tamper never
# masquerades as "unexpected error" (exit 1).
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory Convert and Flow for the self-test. Mirrors the REAL surface
    used by this module (list/get phones, create), with programmable listing
    contents and behaviors, and a mutation log so the tests can prove no write
    happened when none should."""

    def __init__(self, numbers=None, list_behavior=None, create_behavior=None,
                 readback_behavior=None, sms_after_create=False):
        self._numbers = list(numbers or [])
        self.list_behavior = list_behavior       # None | "scope" | "validation" | "edge" | "transport"
        self.create_behavior = create_behavior   # None | "scope" | "validation" | "edge" | "transport" | "no-id"
        self.readback_behavior = readback_behavior  # None | "scope" | "edge" | "no-id"
        self.sms_after_create = sms_after_create  # number reports SMS-capable immediately at create
        self.writes = []                         # every mutating call, in order

    def _request(self, method, path, query=None, body=None):
        q = query or {}
        if method == "GET" and path == "/phones/numbers":
            if self.list_behavior == "scope":
                raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
            if self.list_behavior == "validation":
                raise reg.CafValidation("rejected (HTTP 422)")
            if self.list_behavior in ("edge", "transport"):
                raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
            return {"numbers": list(self._numbers)}
        if method == "GET" and path.startswith("/phones/numbers/"):
            if self.readback_behavior == "scope":
                raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
            if self.readback_behavior in ("edge", "transport"):
                raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
            if self.readback_behavior == "no-id":
                return None
            nid = path.rsplit("/", 1)[-1]
            for n in self._numbers:
                if str(n.get("id")) == nid:
                    if self.sms_after_create:
                        return dict(n, smsEnabled=True)
                    return {k: v for k, v in n.items() if k not in SMS_ENABLED_KEYS}
            return None
        if method == "POST" and path == "/phones/numbers":
            self.writes.append(("create", q.get("locationId"), body))
            if self.create_behavior == "scope":
                raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
            if self.create_behavior == "validation":
                raise reg.CafValidation("rejected (HTTP 422)")
            if self.create_behavior in ("edge", "transport"):
                raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
            if self.create_behavior == "no-id":
                return {}
            self._numbers.append({
                "id": "num_NEWQcDX", "phoneNumber": "+12025550123",
                "smsEnabled": self.sms_after_create})
            return {"id": "num_NEWQcDX"}
        raise AssertionError("unexpected call: %s %s" % (method, path))

def _golden_numbers():
    return [{
        "id": "num_EXISTING", "phoneNumber": "+12025559876",
        "smsEnabled": True,
    }]

def _mixed_numbers():
    return [
        {"id": "num_EXISTING", "phoneNumber": "+12025559876",
         "smsEnabled": True},
        {"id": "num_VOICE", "phoneNumber": "+12025554321",
         "smsEnabled": False},
    ]

def _attack_numbers():
    # A listing carrying a number whose SMS marker is MISSING (not False): the
    # read is fine, but the entry cannot be trusted as SMS-capable. The module
    # must never treat an unmarked entry as verified SMS.
    return [{
        "id": "num_SUSPECT", "phoneNumber": "+12025559876",
        # deliberately NO smsEnabled key
    }]

def self_test(out=None) -> int:
    import io
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # (0) marker helpers are non-reversible and never leak full values;
        #     the browser UA is pinned to the registry's (a registry regression
        #     would be caught HERE first — CF 1010 doctrine)
        assert _mask_number("+12025559876") == "...9876"
        assert _mask_number("") == "(short number)"
        assert _sms_enabled(_golden_numbers()[0]) is True
        assert _sms_enabled(_attack_numbers()[0]) is False
        assert _sms_enabled({}) is False
        assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), \
            "browser UA must ride every request (CF 1010 edge fix)"

        # (1) live listing: every number reported with a masked marker, never
        #     a full number; exit 0; zero writes
        dev1 = io.StringIO()
        caf1 = _FakeCaf(numbers=_mixed_numbers())
        rc1 = list_action(caf1, "loc_QcDX", out=dev1)
        assert rc1 == EX_OK, "live listing must exit 0, got %s" % rc1
        assert caf1.writes == [], "a listing must never write"
        assert "...9876" in dev1.getvalue() and "...4321" in dev1.getvalue()
        assert "+12025559876" not in dev1.getvalue(), \
            "a full number must never reach the surface"
        assert "loc_QcDX" not in dev1.getvalue(), \
            "the location id must never reach the surface"
        assert "2 number(s), 1 SMS-capable" in dev1.getvalue()

        # (2) listing-refusal ladder: scope -> STOP, validation -> STOP,
        #     edge block -> HELD, transport -> HELD (never mislabeled)
        for behavior, want in (("scope", EX_STOP), ("validation", EX_STOP),
                               ("edge", EX_HELD), ("transport", EX_HELD)):
            dev2 = io.StringIO()
            caf2 = _FakeCaf(list_behavior=behavior)
            rc2 = list_action(caf2, "loc_QcDX", out=dev2)
            assert rc2 == want, "list_behavior %r: want %s, got %s" % (behavior, want, rc2)
            assert "AF-AE-PHONELIST-READ-REFUSED" in dev2.getvalue()
            if behavior == "edge":
                assert "NOT a scope problem" in dev2.getvalue(), \
                    "an edge block must NEVER be mislabeled as a scope problem"

        # (3) idempotency: an SMS-capable number already exists -> NO-OP, no
        #     writes at all, exit 0
        dev3 = io.StringIO()
        caf3 = _FakeCaf(numbers=_golden_numbers())
        rc3 = provision_action(caf3, "loc_QcDX", execute=True, out=dev3)
        assert rc3 == EX_OK, "already-provisioned must exit 0, got %s" % rc3
        assert caf3.writes == [], "already-provisioned location must NEVER be written"
        assert "IDEMPOTENT NO-OP" in dev3.getvalue()

        # (4) no-execute: no number, no --execute -> STOP (exit 2), NO write
        dev4 = io.StringIO()
        caf4 = _FakeCaf()
        rc4 = provision_action(caf4, "loc_QcDX", out=dev4)
        assert rc4 == EX_STOP, "missing --execute must STOP (exit 2), got %s" % rc4
        assert caf4.writes == [], "without --execute nothing may be created"
        assert "AF-AE-PHONELIST-NO-EXECUTE" in dev4.getvalue()

        # (5) provision refusal ladder for the listing step: a refused listing
        #     must never be followed by a create, even with --execute
        for behavior, want in (("scope", EX_STOP), ("validation", EX_STOP),
                               ("edge", EX_HELD), ("transport", EX_HELD)):
            dev5 = io.StringIO()
            caf5 = _FakeCaf(list_behavior=behavior)
            rc5 = provision_action(caf5, "loc_QcDX", execute=True, out=dev5)
            assert rc5 == want, "provision list_behavior %r: want %s, got %s" % (behavior, want, rc5)
            assert caf5.writes == [], "a refused listing must never be followed by a create"

        # (6) create-refusal ladder (with --execute): refused create NEVER
        #     records a number, exit per class
        for behavior, want in (("scope", EX_STOP), ("validation", EX_STOP),
                               ("edge", EX_HELD), ("transport", EX_HELD),
                               ("no-id", EX_MISMATCH)):
            dev6 = io.StringIO()
            caf6 = _FakeCaf(create_behavior=behavior)
            rc6 = provision_action(caf6, "loc_QcDX", execute=True, out=dev6)
            assert rc6 == want, "create_behavior %r: want %s, got %s" % (behavior, want, rc6)
            assert "AF-AE-PHONELIST-CREATE-REFUSED" in dev6.getvalue()

        # (7) full happy path with --execute: create once, read back, exit 0
        dev7 = io.StringIO()
        caf7 = _FakeCaf(sms_after_create=True)
        rc7 = provision_action(caf7, "loc_QcDX", execute=True, out=dev7)
        assert rc7 == EX_OK, "happy path must exit 0, got %s" % rc7
        assert caf7.writes == [("create", "loc_QcDX", {})], \
            "happy path must create exactly once"
        assert "READ BACK" in dev7.getvalue()

        # (8) read-back refusal ladder: refused / empty read-back NEVER
        #     records the number as provisioned
        for behavior, want in (("scope", EX_STOP), ("edge", EX_HELD),
                               ("no-id", EX_MISMATCH)):
            dev8 = io.StringIO()
            caf8 = _FakeCaf(create_behavior=None, readback_behavior=behavior,
                            sms_after_create=False)
            rc8 = provision_action(caf8, "loc_QcDX", execute=True, out=dev8)
            assert rc8 == want, "readback_behavior %r: want %s, got %s" % (behavior, want, rc8)

        # (9) attack listing: an SMS-marker-less entry is NEVER treated as
        #     verified SMS-capable (provision path stays open, no silent trust)
        dev9 = io.StringIO()
        caf9 = _FakeCaf(numbers=_attack_numbers())
        rc9 = provision_action(caf9, "loc_QcDX", out=dev9)
        assert rc9 == EX_STOP, "unmarked entry must not short-circuit to verified"
        assert "AF-AE-PHONELIST-NO-EXECUTE" in dev9.getvalue()
        rc9b = provision_action(caf9, "loc_QcDX", execute=True, out=dev9)
        assert rc9b == EX_OK, "attack listing must still provision under --execute"
        assert caf9.writes == [("create", "loc_QcDX", {})], \
            "attack listing must create exactly once"

        # (10) plan is offline: no client, no credential, exit 0
        dev10 = io.StringIO()
        rc10 = plan_action(out=dev10)
        assert rc10 == EX_OK, "offline plan must exit 0, got %s" % rc10

        # (11) never-print: no token, no location id, no full number ever
        #     reaches the human surfaces (the self-test's own dev streams --
        #     raw test-fixture internals are not surfaces)
        all_text = (dev1.getvalue() + dev3.getvalue() + dev4.getvalue()
                    + dev7.getvalue() + dev9.getvalue())
        for token in ("pit-", "loc_QcDX", "+12025559876", "+12025550123",
                      "+12025554321", "SEKRIT", "Bearer "):
            assert token not in all_text, "surface leak: %r must never appear" % token

        # (12) _sms_enabled is presence/truthiness-only on the fixed key set
        assert _sms_enabled({"smsEnabled": 0}) is False
        assert _sms_enabled({"sms_enabled": "false"}) is True  # truthy string stays truthy
        assert _sms_enabled({"smsEnabled": True}) is True
        assert _sms_enabled({"other": True}) is False

        out.write("phone_lister self-test: OK (live listing masked markers "
                  "+ capability, listing/provision/read-back refusal ladders "
                  "scope/validation/edge/transport/no-id, edge block never "
                  "mislabeled as scope, GET-first idempotency [existing SMS "
                  "number -> no-op], no-execute STOP, create-then-read-back "
                  "write order, attack listing never silently trusted, offline "
                  "plan, never-print, marker masking, browser UA pinned)\n")
        return EX_OK
    except AssertionError as exc:
        sys.stderr.write("[phone_lister] SELF-TEST FAILED "
                         "(AF-AE-PHONELIST-* family): %s\n" % exc)
        return EX_VIOLATION

# ---------------------------------------------------------------------------
# CLI (house style: argparse + subcommands + --self-test/--selftest aliases)
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="phone_lister.py",
        description="READ-ONLY live listing of the Convert and Flow location's "
                    "existing phone numbers (GET /phones/numbers), fail-closed, "
                    "masked markers only, with a GHL-gated (--execute) "
                    "GET-first provisioning path and bounded read-back (Skill "
                    "59, U23 tooling).")
    ap.add_argument("--location-id", default="",
                    help="override the client Convert and Flow location id "
                    "(label CONVERT_AND_FLOW_LOCATION_ID by default; never printed)")
    ap.add_argument("--execute", action="store_true",
                    help="GHL-gated ACTION flag: only with this flag may the "
                    "module POST a number (provision)")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan the provisioning without performing it / no network")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout")
    ap.add_argument("cmd", choices=["list", "provision", "plan", "self-test"])

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # so argparse's required positional cmd never rejects the flag form.
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)
    jsonout = sys.stdout if args.json else None

    try:
        if args.cmd == "self-test":
            return self_test()

        if args.cmd == "plan":
            return plan_action(out=sys.stderr, jsonout=jsonout)

        if args.cmd == "list":
            # Live READ-ONLY listing — never requires --execute.
            client, loc_or_rc = reg._live_client(args.location_id)
            if client is None:
                return loc_or_rc
            return list_action(client, loc_or_rc, out=sys.stderr, jsonout=jsonout)

        if args.cmd == "provision":
            if args.dry_run:
                # No network in dry-run: the offline plan surface.
                return plan_action(out=sys.stderr, jsonout=jsonout)
            client, loc_or_rc = reg._live_client(args.location_id)
            if client is None:
                return loc_or_rc
            return provision_action(client, loc_or_rc, execute=args.execute,
                                    out=sys.stderr, jsonout=jsonout)

        ap.error("unknown command %r" % args.cmd)
    except SystemExit:
        raise
    except reg.ScopeDenied as exc:
        sys.stderr.write("[phone_lister] scope denied: %s\n" % exc)
        return EX_STOP
    except reg.CafUnreachable as exc:
        sys.stderr.write("[phone_lister] HELD: %s\n" % exc)
        return EX_HELD
    except Exception as exc:
        sys.stderr.write("[phone_lister] unexpected error: %s\n" % exc)
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
