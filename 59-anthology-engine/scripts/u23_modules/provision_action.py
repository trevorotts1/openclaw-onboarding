#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u23_modules/provision_action.py
# LEADCONNECTOR PHONE NUMBER PROVISIONER (U23 tooling) — GET-first idempotent
# provisioning of an SMS-capable phone number for the client's Convert and
# Flow location. The ACTION (the POST that creates the number) is Trevor-gated:
# it runs ONLY under --execute. Without --execute the module reports what it
# WOULD do and exits without mutating (STOP, exit 2).
#
# WHAT THIS IS:
#   The client's location needs an SMS-capable phone number BEFORE any SMS
#   surface (stage gate nudges, snapshot-import notifications, per-stage SMS
#   links) can deliver. The v2 public surface this module uses:
#
#     GET    /phones/numbers?locationId=<loc>      list existing numbers
#     GET    /phones/numbers/<id>?locationId=<loc> read-back one number
#     POST   /phones/numbers?locationId=<loc>      provision a number
#
#   IDEMPOTENCY LAW (GET-first, provision only if absent): the module LISTS the
#   location's existing numbers first and provisions ONLY when no number is
#   already present that matches the requested scope (SMS-capable, judged by
#   presence/truthiness on the fixed key set -- never any other field of a
#   number). A location that already carries an SMS-enabled number is VERIFIED
#   and skipped (exit 0, idempotent no-op -- never a second number, never a
#   second charge). A failed listing REFUSES before any create: the module
#   never provisions into the unknown.
#
#   READ-BACK LAW: a write is never trusted without read-back. After the POST,
#   the module GETs the created number by id and confirms it exists before any
#   report claims provisioned. A missing read-back is a MISMATCH (exit 5),
#   never a false success.
#
#   THE ACTION STAYS GATED: the module NEVER provisions without --execute.
#   Default and --dry-run are read-only / plan-only (no network in dry-run).
#   The actual POST that creates the number is the GHL-scoped ACTION boundary:
#   it runs ONLY when the operator explicitly passes --execute.
#
# CREDENTIAL DOCTRINE: the token + location are resolved BY LABEL exactly like
# every other adapter (anthology_registry.resolve_pit / resolve_location --
# CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_LOCATION_ID etc. across live process
# env then the three canonical client env stores). Values are NEVER printed
# (SET / NOT SET + masked location only). The browser User-Agent rides every
# request via reg.CafClient (W0.6/GK-09: services.leadconnectorhq.com is
# Cloudflare-fronted and 403s urllib's default UA -- CF 1010). The engine's
# scope-vs-edge-block discrimination (ScopeDenied vs UpstreamBlockedError)
# applies to every read AND write: a bare 401/403 is NEVER reported as a scope
# problem, it is HELD.
#
# AF ERROR CODES (fail-closed surfaces, house scheme):
#   AF-AE-PROVACTION-MISSING-LABEL    -> a required label (PIT / location) is
#          NOT SET or resolves to a non-pit- value (surfaced by the registry's
#          own _live_client; STOP, exit 2). The module itself adds no label
#          surface of its own.
#   AF-AE-PROVACTION-NO-EXECUTE       -> provisioning (the create POST) was
#          requested without --execute. STOP (exit 2); the module NEVER
#          provisions without the explicit Trevor-gated execute flag.
#   AF-AE-PROVACTION-READ-REFUSED     -> listing numbers for the location
#          failed (scope / validation / edge block / transport). STOP or HELD
#          per class -- never a silent skip, never a provision-into-the-unknown.
#   AF-AE-PROVACTION-CREATE-REFUSED   -> the location exists, no matching
#          number, and the POST /phones/numbers was rejected (validation /
#          scope / edge block / transport). STOP or HELD per class.
#   AF-AE-PROVACTION-READBACK-MISMATCH-> the post-create read-back returned no
#          number object for the created id (exit 5: read-back mismatch).
#          Nothing is ever reported provisioned without read-back.
#   AF-AE-PROVACTION-ATTACK           -> an attack fixture tripped the OFFLINE
#          self-test. Exit 4 (enforced violation), never exit 1.
#
# EXIT CODES (house convention; nonzero STOPS/HELDs with an operator surface):
#   0  verified success (idempotent no-op / dry run counts as pass)
#   1  unexpected error
#   2  STOP refusal -- usage error / missing credential / missing --execute
#   3  Convert and Flow API unreachable (retryable)
#   4  self-test FAILED -- an assertion in the OFFLINE self-test tripped
#      (AF-AE-PROVACTION-* family). A tamper NEVER masquerades as exit 1.
#   5  data or read-back mismatch (the post-create read-back was missing)
#
# STDLIB ONLY (urllib + json via anthology_registry.CafClient), reusing the
# registry's credential resolution + browser-UA wiring. Calls NO model.
# DOCTRINE: move in silence; nothing Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value;
# --dry-run and --self-test are OFFLINE.
# =============================================================================
"""provision_action.py -- Trevor-gated LeadConnector phone number provisioner
with GET-first idempotency and post-create read-back (Skill 59, U23 tooling).
The create POST runs ONLY under --execute."""

from __future__ import annotations

import argparse
import io
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

# ---------------------------------------------------------------------------
# Surface + defaults
# ---------------------------------------------------------------------------

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
    fixed key set -- never any other field of the number object."""
    for k in SMS_ENABLED_KEYS:
        v = number.get(k)
        if v is not None:
            return bool(v)
    return False


# ---------------------------------------------------------------------------
# LeadConnector phone surface (reads always; the create under --execute only)
# ---------------------------------------------------------------------------
def list_numbers(client, location_id: str):
    """GET /phones/numbers?locationId=<loc>. READ-ONLY. Returns a list of
    number dicts (each entry is only ever used for the SMS-capable marker and
    the masked number; no other field is read)."""
    out = client._request("GET", "/phones/numbers",
                          query={"locationId": location_id})
    if isinstance(out, dict):
        for key in ("numbers", "data", "results"):
            v = out.get(key)
            if isinstance(v, list):
                return v
        return []
    if isinstance(out, list):
        return out
    return []


def get_number(client, number_id: str, location_id: str):
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


def _find_sms_number(numbers, location_masked: str, out=None):
    """First SMS-capable number in a listing, or None. Never prints any number
    value -- the masked marker only."""
    out = out or sys.stderr
    for n in numbers:
        if isinstance(n, dict) and _sms_enabled(n):
            num = n.get("phoneNumber") or n.get("number") or ""
            out.write("    found SMS-capable number: %s\n" % _mask_number(num))
            return n
    return None


def plan_action(client, location_id: str, *, out=None, jsonout=None) -> int:
    """READ-ONLY plan: list the location's numbers, report what provisioning
    WOULD do. No network in dry-run (plan is the dry-run body)."""
    out = out or sys.stderr
    masked = reg._mask_location(location_id)
    try:
        numbers = list_numbers(client, location_id)
    except reg.ScopeDenied as exc:
        out.write("[provision-action] AF-AE-PROVACTION-READ-REFUSED: scope "
                  "denied listing numbers for marker %s: %s\n" % (masked, exc))
        return EX_STOP
    except reg.CafValidation as exc:
        out.write("[provision-action] AF-AE-PROVACTION-READ-REFUSED: the API "
                  "rejected the listing for marker %s: %s\n" % (masked, exc))
        return EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[provision-action] AF-AE-PROVACTION-READ-REFUSED: the "
                  "listing for marker %s is HELD (retryable), NOT a scope "
                  "problem: %s\n" % (masked, exc))
        return EX_HELD
    found = _find_sms_number(numbers, masked, out=out)
    state = "already-provisioned" if found is not None else "needs-provision"
    out.write("[provision-action] PLAN (marker %s): %d number(s) listed, %s. "
              "With --execute, the module would %s.\n"
              % (masked, len(numbers), state,
                 "skip provisioning (an SMS-capable number already exists)"
                 if found is not None
                 else "provision one SMS-capable number"))
    if jsonout is not None:
        json.dump({
            "ok": True, "dry_run": True, "location": masked,
            "listed": len(numbers), "state": state,
            "provision_needed": found is None,
        }, jsonout)
        jsonout.write("\n")
    return EX_OK


def provision_action(client, location_id: str, *, execute: bool = False,
                     out=None, jsonout=None) -> int:
    """Idempotent provisioning: GET first, provision only when absent, then
    read back the created number. The CREATE POST happens ONLY under --execute
    (the Trevor-gated ACTION boundary). Never provisions into the unknown: a
    failed listing refuses before any create; a missing read-back refuses the
    success claim (exit 5), never a false pass."""
    out = out or sys.stderr
    masked = reg._mask_location(location_id)

    # -- 1. READ-ONLY listing (idempotency law: GET-check before create) -------
    try:
        numbers = list_numbers(client, location_id)
    except reg.ScopeDenied as exc:
        out.write("[provision-action] AF-AE-PROVACTION-READ-REFUSED: scope "
                  "denied listing numbers for marker %s: %s\n" % (masked, exc))
        return EX_STOP
    except reg.CafValidation as exc:
        out.write("[provision-action] AF-AE-PROVACTION-READ-REFUSED: the API "
                  "rejected the listing for marker %s: %s\n" % (masked, exc))
        return EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[provision-action] AF-AE-PROVACTION-READ-REFUSED: the "
                  "listing for marker %s is HELD (retryable), NOT a scope "
                  "problem: %s\n" % (masked, exc))
        return EX_HELD

    found = _find_sms_number(numbers, masked, out=out)
    if found is not None:
        out.write("[provision-action] IDEMPOTENT NO-OP (marker %s): an "
                  "SMS-capable number already exists; nothing provisioned.\n"
                  % masked)
        if jsonout is not None:
            json.dump({"ok": True, "location": masked, "provisioned": False,
                       "already": True}, jsonout)
            jsonout.write("\n")
        return EX_OK

    # -- 2. Trevor-gated ACTION boundary --------------------------------------
    if not execute:
        out.write("[provision-action] AF-AE-PROVACTION-NO-EXECUTE: marker %s "
                  "has no SMS-capable number and --execute was NOT passed. "
                  "The provisioning POST is a Trevor-gated ACTION: STOP, "
                  "nothing created.\n" % masked)
        if jsonout is not None:
            json.dump({"ok": False, "location": masked,
                       "exit": EX_STOP, "reason": "no-execute"}, jsonout)
            jsonout.write("\n")
        return EX_STOP

    # -- 3. CREATE (only under --execute) -------------------------------------
    try:
        created = client._request(
            "POST", "/phones/numbers", query={"locationId": location_id},
            body={})
    except reg.ScopeDenied as exc:
        out.write("[provision-action] AF-AE-PROVACTION-CREATE-REFUSED: scope "
                  "denied provisioning for marker %s: %s\n" % (masked, exc))
        return EX_STOP
    except reg.CafValidation as exc:
        out.write("[provision-action] AF-AE-PROVACTION-CREATE-REFUSED: the API "
                  "rejected the provisioning for marker %s: %s\n" % (masked, exc))
        return EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[provision-action] AF-AE-PROVACTION-CREATE-REFUSED: the "
                  "provisioning for marker %s is HELD (retryable), never a "
                  "scope problem: %s\n" % (masked, exc))
        return EX_HELD

    created_id = ""
    if isinstance(created, dict):
        created_id = str(created.get("id") or created.get("numberId")
                         or created.get("data", {}).get("id")
                         or "").strip()
    if not created_id:
        out.write("[provision-action] AF-AE-PROVACTION-CREATE-REFUSED: the API "
                  "responded to the provisioning POST for marker %s without a "
                  "number id (exit 5: read-back mismatch). Nothing considered "
                  "provisioned.\n" % masked)
        return EX_MISMATCH

    # -- 4. READ-BACK (a write is never trusted without read-back) ------------
    try:
        read_back = get_number(client, created_id, location_id)
    except reg.ScopeDenied as exc:
        out.write("[provision-action] AF-AE-PROVACTION-READBACK-MISMATCH: "
                  "scope denied reading back the created number for marker %s: "
                  "%s\n" % (masked, exc))
        return EX_STOP
    except reg.CafValidation as exc:
        out.write("[provision-action] AF-AE-PROVACTION-READBACK-MISMATCH: the "
                  "API rejected the read-back for marker %s: %s\n"
                  % (masked, exc))
        return EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[provision-action] AF-AE-PROVACTION-READBACK-MISMATCH: the "
                  "read-back for marker %s is HELD (retryable): %s\n"
                  % (masked, exc))
        return EX_HELD

    if read_back is None:
        out.write("[provision-action] AF-AE-PROVACTION-READBACK-MISMATCH: the "
                  "post-create read-back for marker %s returned no number "
                  "object (exit 5). The create is NOT reported as "
                  "provisioned.\n" % masked)
        if jsonout is not None:
            json.dump({"ok": False, "location": masked,
                       "exit": EX_MISMATCH, "reason": "readback-missing"},
                      jsonout)
            jsonout.write("\n")
        return EX_MISMATCH

    num = read_back.get("phoneNumber") or read_back.get("number") or ""
    out.write("[provision-action] PROVISIONED (marker %s): number %s created "
              "and confirmed by read-back.\n"
              % (masked, _mask_number(num)))
    if jsonout is not None:
        json.dump({"ok": True, "location": masked, "provisioned": True,
                   "already": False, "readback": True}, jsonout)
        jsonout.write("\n")
    return EX_OK


# ---------------------------------------------------------------------------
# SELF-TEST: golden + attack fixtures, zero network, zero secrets, zero writes.
# Mirrors the sibling self-tests (provision_sms_phone / provision_fields /
# anthology_registry): an assertion failure is an ENFORCED VIOLATION, exit 4
# -- a tamper never masquerades as "unexpected error" (exit 1).
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory Convert and Flow for the self-test. Mirrors the REAL surface
    used by this module (list numbers, get one, create), with programmable
    listing contents, behaviors, and a mutation log so the tests can prove no
    write happened when none should."""

    def __init__(self, numbers=None, list_behavior=None, create_behavior=None,
                 readback_behavior=None, created_id="num_QcDX"):
        self._numbers = list(numbers or [])
        self.list_behavior = list_behavior       # None | "scope" | "validation" | "edge" | "transport"
        self.create_behavior = create_behavior   # None | "scope" | "validation" | "edge" | "transport" | "no-id"
        self.readback_behavior = readback_behavior  # None | "scope" | "validation" | "edge" | "transport" | "missing"
        self.created_id = created_id
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
            if self.readback_behavior == "validation":
                raise reg.CafValidation("rejected (HTTP 422)")
            if self.readback_behavior in ("edge", "transport"):
                raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
            if self.readback_behavior == "missing":
                return None
            nid = path.rsplit("/", 1)[-1]
            for n in self._numbers:
                if str(n.get("id")) == nid:
                    return n
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
                "id": self.created_id, "phoneNumber": "+12025550123",
                "smsEnabled": True,
            })
            return {"id": self.created_id}
        raise AssertionError("unexpected call: %s %s" % (method, path))


def _golden_numbers():
    return [{
        "id": "num_EXISTING", "phoneNumber": "+12025559876",
        "smsEnabled": True,
    }]


def _attack_numbers():
    # A listing carrying a number whose SMS marker is MISSING (not False): the
    # read is fine, but the entry cannot be trusted as SMS-capable. The module
    # must never treat an unmarked entry as verified SMS.
    return [{
        "id": "num_SUSPECT", "phoneNumber": "+12025559876",
        # deliberately NO smsEnabled key
    }]


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # (0) marker helper is non-reversible and never leaks full values
        assert _mask_number("+12025559876") == "...9876"
        assert _mask_number("") == "(short number)"
        assert _sms_enabled(_golden_numbers()[0]) is True
        assert _sms_enabled(_attack_numbers()[0]) is False
        assert _sms_enabled({}) is False

        # (1) idempotency: an SMS-capable number already exists -> NO-OP, no
        #     writes at all, exit 0, marker says already
        caf = _FakeCaf(numbers=_golden_numbers())
        rc = provision_action(caf, "loc_QcDX", out=dev)
        assert rc == EX_OK, "already-provisioned must exit 0, got %s" % rc
        assert caf.writes == [], "already-provisioned location must NEVER be written"
        assert "IDEMPOTENT NO-OP" in dev.getvalue()

        # (2) no-execute: no number, no --execute -> STOP (exit 2), NO write
        caf2 = _FakeCaf()
        rc2 = provision_action(caf2, "loc_QcDX", out=dev)
        assert rc2 == EX_STOP, "missing --execute must STOP (exit 2), got %s" % rc2
        assert caf2.writes == [], "without --execute nothing may be created"
        assert "AF-AE-PROVACTION-NO-EXECUTE" in dev.getvalue()

        # (3) dry-run plan: READ-ONLY, no writes, reports what WOULD happen
        dev3 = io.StringIO()
        rc3 = plan_action(_FakeCaf(), "loc_QcDX", out=dev3)
        assert rc3 == EX_OK, "dry-run plan must exit 0, got %s" % rc3
        assert "needs-provision" in dev3.getvalue()
        rc3b = plan_action(_FakeCaf(numbers=_golden_numbers()), "loc_QcDX",
                           out=dev3)
        assert rc3b == EX_OK and "already-provisioned" in dev3.getvalue()
        caf3 = _FakeCaf()
        plan_action(caf3, "loc_QcDX", out=dev3)
        assert caf3.writes == [], "dry-run must never write"

        # (4) listing-refusal ladder: scope -> STOP, validation -> STOP,
        #     edge block -> HELD, transport -> HELD (never mislabeled)
        for behavior, want in (("scope", EX_STOP), ("validation", EX_STOP),
                               ("edge", EX_HELD), ("transport", EX_HELD)):
            dev4 = io.StringIO()
            caf4 = _FakeCaf(list_behavior=behavior)
            rc4 = provision_action(caf4, "loc_QcDX", execute=True, out=dev4)
            assert rc4 == want, "list_behavior %r: want %s, got %s" % (behavior, want, rc4)
            assert caf4.writes == [], "a refused listing must never be followed by a create"
            if behavior == "edge":
                assert "NOT a scope problem" in dev4.getvalue(), \
                    "an edge block must NEVER be mislabeled as a scope problem"

        # (5) create-refusal ladder (with --execute): refused create NEVER
        #     records a number, exit per class
        for behavior, want in (("scope", EX_STOP), ("validation", EX_STOP),
                               ("edge", EX_HELD), ("transport", EX_HELD),
                               ("no-id", EX_MISMATCH)):
            dev5 = io.StringIO()
            caf5 = _FakeCaf(create_behavior=behavior)
            rc5 = provision_action(caf5, "loc_QcDX", execute=True, out=dev5)
            assert rc5 == want, "create_behavior %r: want %s, got %s" % (behavior, want, rc5)
            assert all(w[0] == "create" for w in caf5.writes), \
                "a refused create must not be recorded as provisioned"

        # (6) read-back ladder: a missing / refused read-back NEVER reports
        #     provisioned (exit 5 on missing, STOP/HELD per class otherwise)
        for behavior, want in (("missing", EX_MISMATCH), ("scope", EX_STOP),
                               ("validation", EX_STOP), ("edge", EX_HELD),
                               ("transport", EX_HELD)):
            dev6 = io.StringIO()
            caf6 = _FakeCaf(readback_behavior=behavior)
            rc6 = provision_action(caf6, "loc_QcDX", execute=True, out=dev6)
            assert rc6 == want, "readback_behavior %r: want %s, got %s" % (behavior, want, rc6)
            if behavior == "missing":
                assert "AF-AE-PROVACTION-READBACK-MISMATCH" in dev6.getvalue()

        # (7) full happy path with --execute: create exactly once, read-back
        #     confirms, exit 0, marker says provisioned
        dev7 = io.StringIO()
        caf7 = _FakeCaf()
        rc7 = provision_action(caf7, "loc_QcDX", execute=True, out=dev7)
        assert rc7 == EX_OK, "happy path must exit 0, got %s" % rc7
        assert caf7.writes == [("create", "loc_QcDX", {})], \
            "happy path must create exactly once, got %s" % caf7.writes
        assert "PROVISIONED" in dev7.getvalue()
        assert "read-back" in dev7.getvalue()

        # (8) attack listing: an SMS-marker-less entry is NEVER treated as
        #     verified SMS-capable (provision path stays open, no silent trust)
        dev8 = io.StringIO()
        caf8 = _FakeCaf(numbers=_attack_numbers())
        rc8 = provision_action(caf8, "loc_QcDX", out=dev8)
        assert rc8 == EX_STOP, "unmarked entry must not short-circuit to verified"
        assert "AF-AE-PROVACTION-NO-EXECUTE" in dev8.getvalue()
        rc8b = provision_action(caf8, "loc_QcDX", execute=True, out=dev8)
        assert rc8b == EX_OK, "attack listing must still provision under --execute"
        assert caf8.writes == [("create", "loc_QcDX", {})], \
            "attack listing must create exactly once"

        # (9) never-print: no token, no location id, no full number, no
        #     authorization header value ever reaches the operator surfaces
        #     (the self-test's own dev streams and the JSON summaries -- raw
        #     test-fixture internals are not surfaces)
        import json as _json
        all_text = (dev.getvalue() + dev3.getvalue() + dev6.getvalue()
                    + dev7.getvalue() + dev8.getvalue())
        for token in ("pit-", "loc_QcDX", "+12025559876", "+12025550123",
                      "SEKRIT", "Bearer ", "num_QcDX"):
            assert token not in all_text, "surface leak: %r must never appear" % token

        # (10) _sms_enabled is presence/truthiness-only on the fixed key set
        assert _sms_enabled({"smsEnabled": 0}) is False
        assert _sms_enabled({"sms_enabled": "false"}) is True  # truthy string stays truthy
        assert _sms_enabled({"smsEnabled": True}) is True
        assert _sms_enabled({"other": True}) is False

        out.write("provision_action self-test: OK (golden+attack listings, "
                  "GET-first idempotency [existing SMS number -> no-op], "
                  "no-execute STOP, dry-run plan offline, listing/create/readback "
                  "refusal ladders scope/validation/edge/transport/no-id/missing, "
                  "read-back enforced never a false pass, attack listing never "
                  "silently trusted, create-once write order, never-print, "
                  "marker masking)\n")
        return EX_OK
    except AssertionError as exc:
        sys.stderr.write("[provision_action] SELF-TEST FAILED "
                         "(AF-AE-PROVACTION-* family): %s\n" % exc)
        return EX_VIOLATION


# ---------------------------------------------------------------------------
# CLI (house style: argparse + subcommands + --self-test/--selftest aliases)
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="provision_action.py",
        description="Trevor-gated LeadConnector phone number provisioning for "
                    "the Convert and Flow location: GET-first idempotent "
                    "provisioning with post-create read-back (Skill 59, U23 "
                    "tooling). NEVER provisions without --execute.")
    ap.add_argument("--location-id", default="",
                    help="override the client Convert and Flow location id "
                    "(label CONVERT_AND_FLOW_LOCATION_ID by default; never printed)")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan the provisioning without performing it / no network")
    ap.add_argument("--execute", action="store_true",
                    help="Trevor-gated ACTION flag: only with this flag may the "
                    "module POST the number")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout")
    ap.add_argument("cmd", choices=["provision", "plan", "self-test"])

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
            if args.dry_run:
                # No network in dry-run: a masked placeholder location so
                # surfaces read; the listing is skipped (nothing exists offline).
                masked_loc = args.location_id or "DRYRUN"
                sys.stderr.write("[provision-action] DRY RUN (marker %s): would "
                                 "list /phones/numbers for the location, then "
                                 "provision only if no SMS-capable number "
                                 "exists. No writes performed.\n" % masked_loc)
                if jsonout is not None:
                    json.dump({"ok": True, "dry_run": True,
                               "location": masked_loc, "state": "planned"},
                              jsonout)
                    jsonout.write("\n")
                return EX_OK
            client, loc_or_rc = reg._live_client(args.location_id)
            if client is None:
                return loc_or_rc
            return plan_action(client, loc_or_rc, out=sys.stderr,
                               jsonout=jsonout)

        if args.cmd == "provision":
            if args.dry_run:
                # No network in dry-run: same offline plan surface.
                masked_loc = args.location_id or "DRYRUN"
                sys.stderr.write("[provision-action] DRY RUN (marker %s): would "
                                 "GET-check the location's numbers, then "
                                 "provision only if no SMS-capable number "
                                 "exists, then read back the created number. "
                                 "No writes performed.\n" % masked_loc)
                if jsonout is not None:
                    json.dump({"ok": True, "dry_run": True,
                               "location": masked_loc,
                               "provision_needed": True}, jsonout)
                    jsonout.write("\n")
                return EX_OK
            client, loc_or_rc = reg._live_client(args.location_id)
            if client is None:
                return loc_or_rc
            return provision_action(client, loc_or_rc, execute=args.execute,
                                    out=sys.stderr, jsonout=jsonout)

        ap.error("unknown command %r" % args.cmd)
    except SystemExit:
        raise
    except reg.ScopeDenied as exc:
        sys.stderr.write("[provision_action] scope denied: %s\n" % exc)
        return EX_STOP
    except reg.CafUnreachable as exc:
        sys.stderr.write("[provision_action] HELD: %s\n" % exc)
        return EX_HELD
    except Exception as exc:
        sys.stderr.write("[provision_action] unexpected error: %s\n" % exc)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
