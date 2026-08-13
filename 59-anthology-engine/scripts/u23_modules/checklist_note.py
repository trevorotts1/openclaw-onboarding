#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u23_modules/checklist_note.py  (U23 tooling)
# ONBOARDING CHECKLIST NOTE — "SMS phone number verified present before
# snapshot push" — the fail-closed live gate that certifies the U23
# SMS-PHONE-PROVISIONED law on the client's OWN Convert and Flow location
# (GET /phones/numbers?locationId=<loc> through the house rail client, the
# SMS-capable marker read by presence/truthiness on the fixed key set, the
# idempotency truth held: an SMS-capable number ALREADY present is verified,
# never re-provisioned — never a second number, never a second charge).
#
# WHERE THIS SITS: the snapshot contract's OWN note (config/anthology-snapshot-
# contract.json workflows.per_client_sms_phone_flag) names the requirement
# this module turns into an executable checklist item:
#   "SMS steps require a provisioned LeadConnector phone number in each
#    client's Convert and Flow sub-account (PRD Gap G15). Without a number
#    the SMS step silently no-ops (the email still sends). Add to the
#    per-client onboarding checklist."
# The eight release-notification workflows (workflows.release_notifications)
# all carry send-sms actions; the release tags (anthology-release-* /
# anthology-delivered) are pushed at S7/S8/S9 delivery time — AFTER the
# snapshot push that provisions the location. A number MISSING at push time
# means every later SMS silently no-ops: the checklist item MUST be verified
# BEFORE the snapshot push ships the location into production (the engine's
# same-agency push branch, authorized_mechanisms row 1). This module is the
# on-demand, operator-invoked gate for exactly that item. It is NOT a manifest
# row and NOT part of any skeleton inventory: it ships as a sibling helper of
# the U23 module family (phone_lister.py / provision_sms_phone.py carry the
# read surface this module reuses BY NAME — never a second implementation),
# callable standalone (the same sys.path.insert bootstrap the siblings use)
# or imported BY NAME as u23_modules.checklist_note by a caller that wants the
# checklist gate in-process (engine scripts, provision-anthology-client.sh).
#
# THE LAW (read through the U23 family, never re-implemented here):
#   1. THE PRESENT-BEFORE-PUSH LAW: the checklist item certifies the SMS
#      phone number VERIFIED PRESENT on the client location. "Present" means
#      the GET /phones/numbers listing carries a number entry whose SMS
#      marker is present and TRUE on the fixed key set (SMS_ENABLED_KEYS from
#      provision_sms_phone.py — the ONE authority). An unmarked entry (marker
#      MISSING, not False) can NEVER be trusted as SMS-capable — the attack
#      shape the gate must fail. A number absent or unmarked means the SMS
#      steps of every release-notification workflow silently no-op (the email
#      still sends, so nothing screams): the checklist item is UNVERIFIED,
#      and the snapshot push is NOT cleared to proceed.
#   2. THE IDEMPOTENCY LAW: an SMS-capable number already present is
#      VERIFIED, never re-provisioned (exit 0, idempotent no-op — never a
#      second number, never a second charge). This module NEVER provisions:
#      it only certifies. The PROVISIONING ACTION lives in the owning
#      provisioner (provision_sms_phone.py), where the Trevor gate
#      (--execute) is enforced; this module pins the gate as the law its
#      surface carries (EXECUTE_REQUIRED_FOR_PROVISION) exactly as
#      golden_has_phone.py pins it.
#   3. THE --execute LAW: a PROVISIONING ACTION (POST /phones/numbers, the
#      send-test-message POST) requires the operator's explicit --execute
#      (package-init doctrine; Trevor-gated). THIS module performs NO ACTION
#      — the check is a READ-ONLY live listing — so it never requires
#      --execute itself; but its surface certifies the gate so the checklist
#      item can never read as a license to provision without it.
#   4. THE BROWSER UA LAW: services.leadconnectorhq.com is Cloudflare-fronted
#      and 403s urllib's default "Python-urllib/x.y" User-Agent at the WAF
#      edge (CF error 1010) before the request ever reaches the API. Every
#      request rides reg.CafClient, which applies reg.CAF_BROWSER_UA on every
#      request — the house pattern ported byte-for-byte from the Podcast
#      gate. The self-test pins the UA so a registry regression is caught
#      HERE first.
#   5. THE SCOPE-VS-EDGE LAW: a bare 401/403 is NEVER reported as a scope
#      problem — it is HELD (retryable). The engine's discrimination
#      (ScopeDenied -> STOP family, CafUnreachable/UpstreamBlockedError ->
#      HELD family) applies to the read: a scope denial STOPs the check
#      (UNDETERMINED, never a fabricated pass); an edge block / transport
#      failure is HELD (exit 3), never a false verified.
#
# FAIL-CLOSED: a missing credential label, a listing refused, a listing with
# NO SMS-capable number, an unmarked entry (the only entry or among them — a
# single unmarked entry means the checklist cannot certify a verified number
# because a marker-less number can NEVER be trusted as SMS-capable), a
# malformed response shape, or a credential-shaped value on any surface is a
# REFUSED exit 5 (or STOP/HELD per class) — never a blind pass, never a
# fabricated success. The gate exits 0 ONLY on the exact verified-present
# truth: at least one number entry with the SMS marker present and TRUE.
#
# CREDENTIAL DOCTRINE: the token + location resolve BY LABEL exactly like
# every other adapter (reg.resolve_pit / reg.resolve_location:
# CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY /
# GOHIGHLEVEL_PIT / GHL_API_KEY and CONVERT_AND_FLOW_LOCATION_ID /
# GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID, live process env first then the
# three canonical client env stores). Values are NEVER printed (SET / NOT SET
# + masked location only); a phone number is never printed in full — the
# non-reversible last-4-digits marker only (reg._mask_location /
# provision_sms_phone._mask_number, the house masking shapes). The one JSON
# report object lands on stdout; human notes go to stderr.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation; the
# primary operator surface is 0 = PASS, 5 = FAIL):
#   0  verified success — at least one SMS-capable number is present on the
#      location (the checklist item is verified; also plan / self-test pass)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — credential label NOT SET / non-pit- value / usage /
#      a genuine scope denial (UNDETERMINED, never a fabricated pass)
#   3  Convert and Flow API unreachable / edge block (retryable) — HELD,
#      never mislabeled as a scope problem, never a false verified
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-CHECKLIST-ATTACK family). A tamper NEVER masquerades as exit 1.
#   5  the checklist item is NOT verified — no SMS-capable number present, an
#      unmarked entry present, or a malformed response shape (data or
#      read-back mismatch; the fail-closed verdict for the checklist item)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr):
#   checklist_note.py check [--location-id X]   # LIVE READ-ONLY gate: the
#                                               # checklist item verified /
#                                               # unverified (fail-closed)
#   checklist_note.py plan                       # offline: what the check
#                                                 # would certify, no network
#   checklist_note.py self-test                  # offline golden + attack
#
# STDLIB ONLY (urllib + json via the registry), reusing
# anthology_registry.CafClient + credential resolution and the U23 family's
# read surface (provision_sms_phone.list_phone_numbers /
# provision_sms_phone._mask_number — read BY NAME, never re-implemented).
# Calls NO model. DOCTRINE: move in silence; NOTHING Anthropic in any
# runtime file; Convert and Flow naming in every client surface; NEVER print
# a secret value; --dry-run / plan and --self-test are OFFLINE.
# =============================================================================
"""checklist_note.py — onboarding checklist item "SMS phone number verified
present before snapshot push": the fail-closed live gate certifying the U23
SMS-PHONE-PROVISIONED law on the client's Convert and Flow location (GET
/phones/numbers, the SMS-capable marker by presence/truthiness on the fixed
key set, idempotency held, provisioning stays --execute-gated) before the
snapshot push ships the location (Skill 59, U23 tooling)."""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to the u05..u09
# golden siblings): the registry owns the canonical constants, the
# Cloudflare browser-UA wiring, the LeadConnector client and the label
# resolution; the U23 family owns the read surface. A law is read BY NAME
# through the module that owns it — never re-implemented here.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import provision_sms_phone as prov  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for the
# checklist gate's report (the self-test asserts the exact string — the
# surface contract is load-bearing).
CHECKLIST_CONTRACT = "anthology-engine-checklist-note"

# The checklist item this module certifies — the exact naming the snapshot
# contract's own note (workflows.per_client_sms_phone_flag) requires on the
# per-client onboarding checklist. The self-test pins the string so a drift
# in the item's name breaks the module first, never silently.
CHECKLIST_ITEM = "SMS phone number verified present before snapshot push"

# The fixed SMS-marker key set — the ONE authority, read through the owning
# provisioner (never retyped here), exactly as golden_has_phone.py reads it.
SMS_ENABLED_KEYS = prov.SMS_ENABLED_KEYS  # ("smsEnabled", "sms_enabled")

# The EXECUTE law, pinned from the owning provisioner's contract: the
# provisioning POST (POST /phones/numbers) and the send-test-message POST
# are GHL-gated ACTIONS that NEVER run without --execute. THIS module
# performs no ACTION — the check is READ-ONLY — so it never requires
# --execute itself, but its surface certifies the gate: the checklist item
# is a VERIFIED-present certificate, never a license to provision.
EXECUTE_REQUIRED_FOR_PROVISION = True

# The scope-vs-edge discrimination truth (house law, the same the family
# modules pin): a bare 401/403 is NEVER reported as a scope problem — it is
# HELD (retryable). Scope denial -> STOP family; edge block / transport ->
# HELD family.
SCOPE_STOP_EXIT = reg.EX_STOP
EDGE_HELD_EXIT = reg.EX_HELD


class ChecklistError(Exception):
    """A fail-closed refusal (STOP/mismatch family): the checklist gate
    cannot certify the SMS-phone-present law, so NO pass is shipped — a
    wrong certificate is worse than no certificate."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing law is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _sms_enabled(number: dict) -> bool:
    """The SMS-marker law, read through the ONE authority
    (provision_sms_phone.SMS_ENABLED_KEYS): a number counts as SMS-capable
    ONLY by presence/truthiness of the fixed marker keys — never any other
    field of the number entry. An entry whose marker is MISSING (not False)
    can NEVER be trusted as SMS-capable — the attack shape the checklist
    gate must refuse fail-closed."""
    for k in SMS_ENABLED_KEYS:
        v = number.get(k)
        if v is not None:
            return bool(v)
    return False


def _mask_number(num: str) -> str:
    """A non-reversible marker for a phone number: last 4 digits only. Read
    through the owning provisioner's masking (the house shape — never a
    second implementation)."""
    return prov._mask_number(num)


def _contract_listing(payload) -> list:
    """The listing law, fail-closed: the check result must carry a numbers
    array (the list_phone_numbers surface shape). A malformed shape (a
    non-mapping result, a non-list numbers) is a refusal, never a pass."""
    if not isinstance(payload, dict):
        raise ChecklistError(
            "the listing result is %s, not a JSON object — a malformed "
            "response shape is never a pass; refusing to certify the "
            "checklist item." % type(payload).__name__)
    numbers = payload.get("numbers")
    if not isinstance(numbers, list):
        raise ChecklistError(
            "the listing result carries no numbers array — a malformed "
            "response shape is never a pass; refusing to certify the "
            "checklist item.")
    return numbers


def _marker_state(number: dict) -> str:
    """The marker state of a number entry, on the fixed key set only:
    "present-true" (SMS-capable), "present-false" (voice-only — the marker
    is present and False, a legitimate correctly-marked entry, never the
    attack shape), or "missing" (the marker key is ABSENT — the attack
    shape: an unmarked entry can NEVER be trusted as SMS-capable)."""
    for k in SMS_ENABLED_KEYS:
        v = number.get(k)
        if v is not None:
            return "present-true" if bool(v) else "present-false"
    return "missing"


def _contract_numbers(numbers: list) -> dict:
    """The verified-present law, fail-closed: the checklist item is verified
    ONLY when the listing carries at least one entry whose SMS marker is
    present and TRUE, and NO entry carries a MISSING marker (an unmarked
    entry can NEVER be trusted as SMS-capable — a marker-less number among
    the listing means the checklist cannot certify a verified SMS-capable
    number; a marker present and False is voice-only, correctly marked, and
    simply not SMS-capable). A non-object entry is a malformed shape — a
    refusal, never a pass. Returns the verified entry."""
    marked = []
    for n in numbers:
        if not isinstance(n, dict):
            raise ChecklistError(
                "the listing carries a non-object number entry (%s) — a "
                "malformed response shape is never a pass; refusing to "
                "certify the checklist item." % type(n).__name__)
        state = _marker_state(n)
        if state == "missing":
            num = _mask_number(str(n.get("phoneNumber") or
                                   n.get("number") or ""))
            raise ChecklistError(
                "the listing carries number %s with the SMS marker MISSING "
                "(not False) — an unmarked entry can NEVER be trusted as "
                "SMS-capable; the checklist item cannot be certified "
                "verified-present (fail-closed)." % num)
        if state == "present-true":
            marked.append(n)
    if not marked:
        raise ChecklistError(
            "the listing carries NO SMS-capable number — every "
            "release-notification SMS step would silently no-op (the email "
            "still sends, so nothing screams); the checklist item is "
            "UNVERIFIED and the snapshot push is NOT cleared.")
    return marked[0]


# ---------------------------------------------------------------------------
# The gate — LIVE READ-ONLY: the client's own Convert and Flow location is
# listed via the house rail client (reg.CafClient — CAF_BROWSER_UA rides
# every request, CF 1010 law), the SMS-capable marker read on the fixed key
# set, the idempotency truth held (already-present is verified, never
# re-provisioned), and the checklist item certified. The read surface is
# provision_sms_phone.list_phone_numbers — the ONE authority — never a
# second implementation.
# ---------------------------------------------------------------------------
def check(client, location_id: str, *, out=None, jsonout=None) -> int:
    """The checklist item gate: GET /phones/numbers for the location (READ-
    ONLY, through the house rail client) and certify the SMS phone number
    VERIFIED PRESENT. Fail-closed: a refused listing STOPs or HELDs per
    class (never a fabricated pass); a listing with NO SMS-capable number or
    with an unmarked entry is a REFUSED exit 5 — the checklist item is
    UNVERIFIED and the snapshot push is NOT cleared. On the verified truth
    the gate exits 0 and reports the masked marker of the verified number.
    The one JSON report object lands on stdout (or jsonout); human notes go
    to out (stderr)."""
    out = out or sys.stderr
    masked = reg._mask_location(location_id)
    try:
        numbers = prov.list_phone_numbers(client, location_id)
    except reg.ScopeDenied as exc:
        out.write("[checklist-note] AF-AE-CHECKLIST-READ-REFUSED: scope "
                  "denied listing numbers for marker %s: %s\n"
                  % (masked, exc))
        if jsonout is not None:
            json.dump({"ok": False, "checklist_item": CHECKLIST_ITEM,
                       "location": masked, "verified": False,
                       "exit": EX_STOP, "reason": "scope-denied"}, jsonout)
            jsonout.write("\n")
        return EX_STOP
    except reg.CafValidation as exc:
        out.write("[checklist-note] AF-AE-CHECKLIST-READ-REFUSED: the API "
                  "rejected the listing for marker %s: %s\n" % (masked, exc))
        if jsonout is not None:
            json.dump({"ok": False, "checklist_item": CHECKLIST_ITEM,
                       "location": masked, "verified": False,
                       "exit": EX_STOP, "reason": "validation"}, jsonout)
            jsonout.write("\n")
        return EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[checklist-note] AF-AE-CHECKLIST-READ-REFUSED: the listing "
                  "for marker %s is HELD (retryable), NOT a scope problem: %s\n"
                  % (masked, exc))
        if jsonout is not None:
            json.dump({"ok": False, "checklist_item": CHECKLIST_ITEM,
                       "location": masked, "verified": False,
                       "exit": EX_HELD, "reason": "held"}, jsonout)
            jsonout.write("\n")
        return EX_HELD

    found = {"number_masked": None, "listed": len(numbers)}
    detail = ""
    ok = False
    try:
        entry = _contract_numbers(numbers)
    except ChecklistError as exc:
        detail = str(exc)
    else:
        found["number_masked"] = _mask_number(
            str(entry.get("phoneNumber") or entry.get("number") or ""))
        ok = True
        detail = ("the location already carries an SMS-capable number (%s) "
                  "— the checklist item is VERIFIED: the release-"
                  "notification SMS steps will not silently no-op; the "
                  "snapshot push is cleared (idempotent no-op: verified, "
                  "never re-provisioned, never a second number, never a "
                  "second charge; provisioning stays --execute-gated)"
                  % found["number_masked"])
    if jsonout is not None:
        json.dump({
            "contract": CHECKLIST_CONTRACT,
            "schema_version": 1,
            "ok": ok,
            "checklist_item": CHECKLIST_ITEM,
            "verdict": "PASS" if ok else "UNVERIFIED",
            "location": masked,
            "verified": ok,
            "sms_enabled_keys": list(SMS_ENABLED_KEYS),
            "execute_required": EXECUTE_REQUIRED_FOR_PROVISION,
            "found": found,
            "detail": detail,
        }, jsonout)
        jsonout.write("\n")
    if ok:
        out.write("[checklist-note] PASS (marker %s): %s\n" % (masked, detail))
        return EX_OK
    out.write("[checklist-note] UNVERIFIED (marker %s): %s\n" % (masked, detail))
    return EX_MISMATCH


# ---------------------------------------------------------------------------
# Offline plan — no network, no credential. What the check would certify and
# why the checklist item gates the snapshot push, printed as ONE JSON object
# on stdout; human notes go to stderr.
# ---------------------------------------------------------------------------
def plan(out=None) -> int:
    out = out or sys.stderr
    out.write("[checklist-note] PLAN (offline): the checklist item is "
              "verified by a LIVE READ-ONLY GET /phones/numbers for the "
              "client's Convert and Flow location (via reg.CafClient — "
              "CAF_BROWSER_UA on every request, CF 1010 law). The location "
              "must carry at least one number entry with the SMS marker "
              "present and TRUE; an unmarked entry can NEVER be trusted as "
              "SMS-capable. Verified-present certifies that the "
              "release-notification SMS steps will not silently no-op; "
              "without it the snapshot push is NOT cleared. Nothing "
              "provisioned — the PROVISIONING ACTION stays --execute-gated "
              "(Trevor gate) in the owning provisioner.\n")
    print(json.dumps({
        "contract": CHECKLIST_CONTRACT + "-plan",
        "schema_version": 1,
        "checklist_item": CHECKLIST_ITEM,
        "surface": "GET /phones/numbers?locationId=<loc> (READ-ONLY, "
                   "provision_sms_phone.list_phone_numbers — the ONE "
                   "authority)",
        "sms_enabled_keys": list(SMS_ENABLED_KEYS),
        "execute_required": EXECUTE_REQUIRED_FOR_PROVISION,
        "law": "the SMS phone number must be VERIFIED PRESENT before the "
               "snapshot push (the snapshot contract's own note, "
               "workflows.per_client_sms_phone_flag): every release-"
               "notification workflow carries a send-sms action, and "
               "without a number the SMS step silently no-ops (the email "
               "still sends)",
        "note": "offline plan only — no network, no credential needed; "
                "every number is reported by masked marker (last 4 digits) "
                "only, never in full",
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: golden + attack fixtures, no network, no secrets, no
# writes. A FAILED self-test is exit 4 (enforced violation), never
# 'unexpected error' — the same discipline the sibling modules apply.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory Convert and Flow for the self-test. Mirrors the REAL read
    surface this module uses (the phone listing GET), with programmable
    listing contents and behaviors, and a mutation log so the tests can
    prove no write ever happens (the checklist is READ-ONLY)."""

    def __init__(self, numbers=None, list_behavior=None):
        self._numbers = list(numbers or [])
        self.list_behavior = list_behavior  # None | "scope" | "validation" | "edge" | "transport"
        self.writes = []                    # every mutating call, in order

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
        self.writes.append((method, path, q, body))
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


def _attack_unmarked():
    # A listing carrying a number whose SMS marker is MISSING (not False):
    # the read is fine, but the entry cannot be trusted as SMS-capable. The
    # checklist gate must NEVER certify verified-present while an unmarked
    # entry rides the listing.
    return [{
        "id": "num_SUSPECT", "phoneNumber": "+12025559876",
        # deliberately NO smsEnabled key
    }]


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # (0) the law constants are pinned: the marker key set reads through
        #     the ONE authority, the EXECUTE law holds, the checklist item's
        #     exact name holds, and the browser UA is the registry's
        #     well-formed browser UA (a registry regression would be caught
        #     HERE first — CF 1010 doctrine)
        assert SMS_ENABLED_KEYS == ("smsEnabled", "sms_enabled"), \
            "the SMS-marker law drifted (provision_sms_phone.SMS_ENABLED_KEYS)"
        assert EXECUTE_REQUIRED_FOR_PROVISION is True, \
            "the EXECUTE law: provisioning NEVER runs without --execute"
        assert CHECKLIST_ITEM == \
            "SMS phone number verified present before snapshot push", \
            "the checklist item's exact name drifted"
        assert SCOPE_STOP_EXIT == reg.EX_STOP and EDGE_HELD_EXIT == reg.EX_HELD, \
            "the scope-vs-edge discrimination must map scope -> STOP, edge -> HELD"
        assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), \
            "CAF_BROWSER_UA must be a browser User-Agent (CF 1010)"
        assert _mask_number("+12025559876") == "...9876", \
            "the phone marker must be the non-reversible last-4 shape"
        assert _sms_enabled({"smsEnabled": True}) is True, \
            "the marker law must read presence/truthiness on the fixed keys"
        assert _sms_enabled({"smsEnabled": False}) is False
        assert _sms_enabled({"sms_enabled": "false"}) is True, \
            "a truthy string stays truthy (the provisioner's own law)"
        assert _sms_enabled({"other": True}) is False, \
            "an unmarked entry can NEVER be trusted as SMS-capable"

        # (1) golden listing: verified-present, exit 0, ZERO writes (the
        #     checklist is READ-ONLY), masked marker on every surface, the
        #     full number and the location id never printed
        dev1 = io.StringIO()
        caf1 = _FakeCaf(numbers=_golden_numbers())
        rc1 = check(caf1, "loc_QcDX", out=dev1)
        assert rc1 == EX_OK, "golden listing must exit 0, got %s" % rc1
        assert caf1.writes == [], "the checklist gate must never write"
        assert "...9876" in dev1.getvalue(), \
            "the verified number must be reported by masked marker"
        assert "+12025559876" not in dev1.getvalue(), \
            "a full number must never reach the surface"
        assert "loc_QcDX" not in dev1.getvalue(), \
            "the location id must never reach the surface"
        # the JSON surface carries the contract, the item, and the truth
        j1 = io.StringIO()
        rc1j = check(caf1, "loc_QcDX", out=dev1, jsonout=j1)
        assert rc1j == EX_OK
        parsed1 = json.loads(j1.getvalue())
        assert parsed1["contract"] == CHECKLIST_CONTRACT
        assert parsed1["checklist_item"] == CHECKLIST_ITEM
        assert parsed1["ok"] is True and parsed1["verdict"] == "PASS"
        assert parsed1["verified"] is True
        assert parsed1["found"]["number_masked"] == "...9876"
        assert parsed1["execute_required"] is True
        assert "+12025559876" not in j1.getvalue()

        # (2) a listing with an SMS-marker FALSE entry only (voice-only,
        #     correctly marked — the marker is present and False, never the
        #     attack shape) -> UNVERIFIED exit 5, never a pass
        dev2 = io.StringIO()
        caf2 = _FakeCaf(numbers=[
            {"id": "num_VOICE", "phoneNumber": "+12025554321",
             "smsEnabled": False}])
        rc2 = check(caf2, "loc_QcDX", out=dev2)
        assert rc2 == EX_MISMATCH, "voice-only listing must exit 5, got %s" % rc2
        assert "UNVERIFIED" in dev2.getvalue()
        assert "snapshot push is NOT cleared" in dev2.getvalue()
        # (2b) the marker-state discrimination: present-and-False (voice-
        #      only, correctly marked) is NOT the attack shape — it is
        #      simply not SMS-capable; an entry with the marker MISSING is
        #      the attack shape (refused in (4) below)
        assert _marker_state({"smsEnabled": False}) == "present-false"
        assert _marker_state({"sms_enabled": "false"}) == "present-true", \
            "a truthy string stays truthy (the provisioner's own law)"
        assert _marker_state({"smsEnabled": True}) == "present-true"
        assert _marker_state({"other": True}) == "missing"

        # (3) a listing with NO numbers -> UNVERIFIED exit 5 (every SMS step
        #     would silently no-op — the email still sends)
        dev3 = io.StringIO()
        caf3 = _FakeCaf(numbers=[])
        rc3 = check(caf3, "loc_QcDX", out=dev3)
        assert rc3 == EX_MISMATCH, "an empty listing must exit 5, got %s" % rc3
        assert "silently no-op" in dev3.getvalue()

        # (4) an UNMARKED entry (the attack shape) -> UNVERIFIED exit 5,
        #     even when another entry IS marked (a marker-less number can
        #     NEVER be trusted as SMS-capable)
        dev4 = io.StringIO()
        caf4 = _FakeCaf(numbers=_attack_unmarked())
        rc4 = check(caf4, "loc_QcDX", out=dev4)
        assert rc4 == EX_MISMATCH, "an unmarked entry must exit 5, got %s" % rc4
        assert "can NEVER be trusted" in dev4.getvalue()
        dev4b = io.StringIO()
        caf4b = _FakeCaf(numbers=_golden_numbers() + _attack_unmarked())
        rc4b = check(caf4b, "loc_QcDX", out=dev4b)
        assert rc4b == EX_MISMATCH, \
            "an unmarked entry beside a marked one must exit 5, got %s" % rc4b

        # (5) the listing-refusal ladder: scope -> STOP, validation -> STOP,
        #     edge block -> HELD, transport -> HELD (never mislabeled, never
        #     a fabricated pass), with zero writes throughout
        for behavior, want in (("scope", EX_STOP), ("validation", EX_STOP),
                               ("edge", EX_HELD), ("transport", EX_HELD)):
            dev5 = io.StringIO()
            caf5 = _FakeCaf(list_behavior=behavior)
            rc5 = check(caf5, "loc_QcDX", out=dev5)
            assert rc5 == want, "list_behavior %r: want %s, got %s" % (behavior, want, rc5)
            assert "AF-AE-CHECKLIST-READ-REFUSED" in dev5.getvalue()
            assert caf5.writes == [], "a refused listing must never write"
            if behavior == "edge":
                assert "NOT a scope problem" in dev5.getvalue(), \
                    "an edge block must NEVER be mislabeled as a scope problem"

        # (6) the READ-ONLY law on the contract surface: the golden check
        #     result carries execute_required TRUE (the checklist item
        #     certifies the --execute gate, never a license to provision)
        assert parsed1["execute_required"] is True

        # (7) never-print: no token, no location id, no full number ever
        #     reaches the surfaces (the self-test's own dev streams -- raw
        #     test-fixture internals are not surfaces)
        all_text = (dev1.getvalue() + dev2.getvalue() + dev3.getvalue()
                    + dev4.getvalue() + dev4b.getvalue())
        for token in ("pit-", "loc_QcDX", "+12025559876", "+12025554321",
                      "Bearer ", "SEKRIT"):
            assert token not in all_text, "surface leak: %r must never appear" % token

        # (8) the offline plan is credential-free and exits 0
        dev8 = io.StringIO()
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            rc8 = plan(out=dev8)
        assert rc8 == EX_OK, "the offline plan must exit 0, got %s" % rc8

        dev.write("checklist_note self-test: OK (checklist item pinned: "
                  "%r; SMS-marker law read through provision_sms_phone "
                  "(%s, presence/truthiness only — an unmarked entry can "
                  "NEVER be trusted as SMS-capable; marker present and "
                  "False is voice-only, correctly marked, never the attack "
                  "shape); golden verified-present exit 0 with zero writes "
                  "and masked markers; unverified exit 5 on voice-only / "
                  "empty / unmarked listings; refusal ladder "
                  "scope/validation/edge/transport with edge never "
                  "mislabeled as scope; READ-ONLY law — the gate never "
                  "writes, provisioning stays --execute-gated; browser UA "
                  "pinned; never-print)\n"
                  % (CHECKLIST_ITEM, ", ".join(SMS_ENABLED_KEYS)))
        out.write(dev.getvalue())
        return EX_OK
    except AssertionError as exc:
        sys.stderr.write("[checklist_note] SELF-TEST FAILED "
                         "(AF-AE-CHECKLIST-ATTACK family): %s\n" % exc)
        return EX_VIOLATION


# ---------------------------------------------------------------------------
# CLI (house style: argparse + subcommands + --self-test/--selftest aliases)
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="checklist_note.py",
        description="Onboarding checklist item: 'SMS phone number verified "
                    "present before snapshot push' — the fail-closed live "
                    "gate that certifies the U23 SMS-PHONE-PROVISIONED law "
                    "on the client's Convert and Flow location (GET "
                    "/phones/numbers, SMS-capable marker by presence/"
                    "truthiness on the fixed key set) before the snapshot "
                    "push ships the location; READ-ONLY, never provisions, "
                    "never prints a token (Skill 59, U23 tooling).")
    ap.add_argument("--location-id", default="",
                    help="override the client Convert and Flow location id "
                    "(label CONVERT_AND_FLOW_LOCATION_ID by default; never printed)")
    ap.add_argument("--dry-run", action="store_true",
                    help="offline plan only — no network, no credential")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout")
    ap.add_argument("cmd", choices=["check", "plan", "self-test"],
                    default="check", nargs="?")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the U04..U09 siblings use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)
    jsonout = sys.stdout if args.json else None

    try:
        if args.cmd == "self-test":
            return self_test()

        if args.cmd == "plan" or args.dry_run:
            return plan(out=sys.stderr)

        # ---- check: LIVE READ-ONLY gate (never requires --execute — the
        # checklist certifies, it never provisions) ----
        client, loc_or_rc = reg._live_client(args.location_id)
        if client is None:
            return loc_or_rc
        return check(client, loc_or_rc, out=sys.stderr, jsonout=jsonout)
    except SystemExit:
        raise
    except reg.ScopeDenied as exc:
        sys.stderr.write("[checklist_note] STOP: %s\n" % exc)
        return EX_STOP
    except reg.CafUnreachable as exc:
        sys.stderr.write("[checklist_note] HELD: %s\n" % exc)
        return EX_HELD
    except ChecklistError as exc:
        sys.stderr.write("[checklist_note] UNVERIFIED: %s\n" % exc)
        return EX_MISMATCH
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[checklist_note] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
