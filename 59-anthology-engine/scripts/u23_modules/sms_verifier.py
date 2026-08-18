#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u23_modules/sms_verifier.py
# FAIL-CLOSED SMS SEND VERIFIER (U23 tooling, extension module) — for the
# Convert and Flow client location, send an SMS via the GHL /v2 surface and
# verify the send came back HTTP 200 WITH a message identifier (SID) before
# anything is called delivered.
#
# WHERE THIS SITS: scripts/u23_modules/ — an importable module under the U23
# provisioning tooling (the SMS surface family of provision_sms_phone.py). It
# is NOT a manifest row: it ships as a sibling helper (the delivery_report.py /
# fields_check.py pattern), imported BY NAME as u23_modules.sms_verifier from
# the engine scripts, per the u23_modules package contract (pure namespace
# container — fail-closed empty __init__, no runtime code, side-effect free).
# Standalone invocation works too: the SAME sys.path.insert bootstrap the
# sibling imports use resolves anthology_registry from scripts/.
#
# THE SURFACE (same public GHL v2 rail provision_sms_phone.py uses):
#     POST /conversations/messages/outbound   send an outbound SMS message
#   with query locationId=<loc> and a JSON body carrying the destination
#   number, the message text, and the messaging channel (sms). The response
#   body's message identifier (id / messageId / sid / messageSid — read by
#   key ORDER on the same fixed key set, exact keys only, never any other
#   field) IS the SID that proves the send was accepted: an HTTP 200 whose
#   body carries NO id is NEVER a pass — it is a read-back mismatch (exit 5),
#   because a write is never trusted without its identifier (same law as the
#   number-id read-back in provision_sms_phone.py).
#
# THE ACTION STAYS GATED — --execute or nothing is sent:
#   The send POST is a GHL-scope ACTION (it charges an outbound SMS). Default
#   and --dry-run are OFFLINE: they validate the arguments, resolve NOTHING
#   live, print the plan surface, and exit 0 — the same offline-plan law as
#   provision_sms_phone.py's dry run. The POST itself runs ONLY under
#   --execute, which is exactly the GHL-gated scope boundary. verify-live
#   without --execute STOPS (exit 2, AF-AE-SMSVER-NO-EXECUTE), never sends.
#
# CREDENTIAL DOCTRINE: token + location resolve BY LABEL exactly like every
# other adapter (reg.resolve_pit / reg.resolve_location across the live
# process env then the three canonical client env stores). Values are NEVER
# printed (SET / NOT SET + masked location only). The destination number is
# reported as a masked marker (last 2 digits) only, and the message text is
# NEVER echoed back on any surface. The browser User-Agent rides every
# request via reg.CafClient (W0.6/GK-09: services.leadconnectorhq.com is
# Cloudflare-fronted and 403s urllib's default UA — CF 1010). The engine's
# scope-vs-edge-block discrimination (ScopeDenied vs UpstreamBlockedError)
# applies to the send: a bare 401/403 is NEVER reported as a scope problem,
# it is HELD (retryable) — an unconfirmed send is never called delivered.
#
# AF ERROR CODES (fail-closed surfaces, house scheme):
#   AF-AE-SMSVER-MISSING-LABEL   -> a required label (PIT / location) is NOT
#          SET or resolves to a non-pit- value. STOP (exit 2), fail-closed.
#   AF-AE-SMSVER-NO-EXECUTE      -> the send POST was requested without
#          --execute. STOP (exit 2); the module NEVER sends without the
#          explicit GHL-gated execute flag. Dry-run plans do not require it.
#   AF-AE-SMSVER-SEND-REFUSED    -> the outbound POST was rejected (scope /
#          validation / edge block / transport). STOP or HELD per class —
#          never a silent skip, never a false delivered.
#   AF-AE-SMSVER-NO-SID          -> the send returned HTTP 200 but the body
#          carried NO message identifier. EXIT 5 (read-back mismatch), never
#          a pass — an unconfirmed send is never called delivered.
#   AF-AE-SMSVER-ATTACK          -> an attack fixture tripped the OFFLINE
#          self-test. Exit 4 (enforced violation), never exit 1.
#
# EXIT CODES (house convention; nonzero STOPS/HELDs with an operator surface):
#   0  verified success (send confirmed: HTTP 200 + SID; dry run counts as pass)
#   1  unexpected error
#   2  STOP refusal — usage error / missing credential / missing --execute
#   3  Convert and Flow API unreachable / edge-blocked (retryable HELD)
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-SMSVER-* family). A tamper NEVER masquerades as exit 1.
#   5  data or read-back mismatch — HTTP 200 without a message identifier
#
# STDLIB ONLY (urllib + json), reusing anthology_registry.CafClient +
# credential resolution. Calls NO model. DOCTRINE: move in silence; NOTHING
# Anthropic in any runtime file; Convert and Flow naming in every client
# surface; NEVER print a secret value; --dry-run and --self-test are OFFLINE.
# =============================================================================
"""sms_verifier.py — fail-closed SMS send verifier for the Convert and Flow
location: POST the outbound message under --execute and require HTTP 200 PLUS
a message identifier (SID) before anything is called delivered (Skill 59, U23
tooling)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Sibling import bootstrap (the u02/u03 module pattern, parent.parent -> scripts/):
# the registry does the Cloudflare browser-UA wiring + LeadConnector client +
# label resolution we reuse. Never resolve credentials here by hand.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The exact outbound-message surface (same public v2 rail the SMS phone
# provisioner uses; documented in provision_sms_phone.py's surface block).
SEND_PATH = "/conversations/messages/outbound"

# The fixed message-identifier key set. Read in ORDER, exact keys only — the
# GHL v2 send response may carry any of these spellings; presence alone is the
# contract (an identifier is opaque — we never validate or echo its content).
# Truthiness only, and NOTHING else about the body is ever trusted or echoed.
SID_KEYS = ("id", "messageId", "message_id", "sid", "messageSid")


def _mask_destination(dest: str) -> str:
    """A non-reversible marker for a destination number: last 2 digits only."""
    dest = (dest or "").strip()
    digits = "".join(ch for ch in dest if ch.isdigit())
    return ("..." + digits[-2:]) if len(digits) >= 2 else "(short number)"


def _extract_sid(body) -> str:
    """The message identifier (SID) from a send response body. Fail-closed:
    returns "" unless the body is a mapping carrying a truthy value under one
    of the fixed SID_KEYS (read in order). The identifier itself is a write
    proof, never a secret — but it is only ever surfaced as SET (never
    echoed), so a token-shaped value can never leak through it."""
    if not isinstance(body, dict):
        return ""
    for key in SID_KEYS:
        val = body.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def verify_send(client, location_id: str, destination: str, message: str, *,
                execute: bool = False, out=None, jsonout=None) -> int:
    """Send the outbound SMS under --execute and require HTTP 200 PLUS a
    message identifier before reporting verified. Fail-closed: an empty
    destination or message STOPS before any network; a refused send STOPS or
    HELDs per class; HTTP 200 without a SID is a read-back mismatch (exit 5),
    NEVER a pass."""
    out = out or sys.stderr
    masked = reg._mask_location(location_id)
    dest_masked = _mask_destination(destination)

    # -- 1. Argument validation (fail-closed, before any network) ------------
    if not destination.strip():
        out.write("[sms-verifier] AF-AE-SMSVER-REFUSED: no destination number "
                  "given for marker %s. STOP, nothing sent.\n" % masked)
        return EX_STOP
    if not message.strip():
        out.write("[sms-verifier] AF-AE-SMSVER-REFUSED: no message text given "
                  "for marker %s. STOP, nothing sent.\n" % masked)
        return EX_STOP

    # -- 2. GHL-gated ACTION boundary -----------------------------------------
    if not execute:
        out.write("[sms-verifier] AF-AE-SMSVER-NO-EXECUTE: marker %s has a "
                  "message to send but --execute was NOT passed. The outbound "
                  "SMS POST is a GHL-gated ACTION: STOP, nothing sent.\n"
                  % masked)
        if jsonout is not None:
            json.dump({"ok": False, "location": masked, "exit": EX_STOP,
                       "reason": "no-execute"}, jsonout)
            jsonout.write("\n")
        return EX_STOP

    # -- 3. The send POST (only under --execute) ------------------------------
    out.write("[sms-verifier] Sending outbound SMS to %s (marker %s) and "
              "waiting for HTTP 200 + message identifier.\n"
              % (dest_masked, masked))
    try:
        body = client._request(
            "POST", SEND_PATH, query={"locationId": location_id},
            body={"to": destination, "message": message, "channel": "sms"})
    except reg.ScopeDenied as exc:
        out.write("[sms-verifier] AF-AE-SMSVER-SEND-REFUSED: scope denied "
                  "sending the SMS for marker %s: %s\n" % (masked, exc))
        return EX_STOP
    except reg.CafValidation as exc:
        out.write("[sms-verifier] AF-AE-SMSVER-SEND-REFUSED: the API rejected "
                  "the send for marker %s: %s\n" % (masked, exc))
        return EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[sms-verifier] AF-AE-SMSVER-SEND-REFUSED: the send for "
                  "marker %s is HELD (retryable), never a scope problem: %s\n"
                  % (masked, exc))
        return EX_HELD

    # -- 4. Read-back proof: HTTP 200 ALONE is never a pass -------------------
    sid = _extract_sid(body)
    if not sid:
        out.write("[sms-verifier] AF-AE-SMSVER-NO-SID: the send for marker %s "
                  "returned HTTP 200 without a message identifier. Exit 5 "
                  "(read-back mismatch) — an unconfirmed send is NEVER called "
                  "delivered.\n" % masked)
        if jsonout is not None:
            json.dump({"ok": False, "location": masked, "verified": False,
                       "exit": EX_MISMATCH, "reason": "no-sid"}, jsonout)
            jsonout.write("\n")
        return EX_MISMATCH

    out.write("[sms-verifier] VERIFIED (marker %s): outbound SMS accepted — "
              "HTTP 200 with message identifier SET.\n" % masked)
    if jsonout is not None:
        json.dump({"ok": True, "location": masked, "verified": True,
                   "sms": True, "sid": "SET"}, jsonout)
        jsonout.write("\n")
    return EX_OK


# ---------------------------------------------------------------------------
# SELF-TEST: golden + attack fixtures, zero network, zero secrets, zero writes.
# Mirrors the sibling self-tests (provision_sms_phone / anthology_registry): an
# assertion failure is an ENFORCED VIOLATION, exit 4 — a tamper never
# masquerades as "unexpected error" (exit 1).
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory Convert and Flow for the self-test. Mirrors the REAL surface
    this module uses (the outbound send POST), with programmable behaviors and
    a mutation log so the tests can prove no send happened when none should.
    Binds ONLY the one path the module uses — anything else is a fail."""

    def __init__(self, send_behavior=None, sid=None, http_ok=True):
        self.send_behavior = send_behavior  # None | "scope" | "validation" | "edge" | "transport" | "no-sid"
        self.sid = sid                      # the identifier the fake returns on success
        self.http_ok = http_ok              # False -> HTTP 200-with-no-id (no-sid) surface
        self.writes = []                    # every mutating call, in order

    def _request(self, method, path, query=None, body=None):
        q = query or {}
        if method == "POST" and path == SEND_PATH:
            self.writes.append(("send", q.get("locationId"), body))
            if self.send_behavior == "scope":
                raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
            if self.send_behavior == "validation":
                raise reg.CafValidation("rejected (HTTP 422)")
            if self.send_behavior in ("edge", "transport"):
                raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
            if self.send_behavior == "no-sid" or not self.http_ok:
                return {"ok": True}  # 200 but NO identifier — never a pass
            return {"id": self.sid or "SM_SELF_TEST_SID"}
        raise AssertionError("unexpected call: %s %s" % (method, path))


def self_test(out=None) -> int:
    import io
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # (0) the marker helper is non-reversible and never leaks a full number
        assert _mask_destination("+12025550123") == "...23"
        assert _mask_destination("") == "(short number)"

        # (1) fail-closed arguments: missing destination or message STOPS
        #     before any network, with NO write
        caf0 = _FakeCaf()
        rc = verify_send(caf0, "loc_QcDX", "  ", "hello", execute=True, out=dev)
        assert rc == EX_STOP, "empty destination must STOP, got %s" % rc
        rc = verify_send(caf0, "loc_QcDX", "+12025550123", "", execute=True, out=dev)
        assert rc == EX_STOP, "empty message must STOP, got %s" % rc
        assert caf0.writes == [], "a refused send must never reach the wire"

        # (2) no-execute: message ready, no --execute -> STOP (exit 2), NO send
        caf2 = _FakeCaf()
        rc2 = verify_send(caf2, "loc_QcDX", "+12025550123", "hello", out=dev)
        assert rc2 == EX_STOP, "missing --execute must STOP (exit 2), got %s" % rc2
        assert caf2.writes == [], "without --execute nothing may be sent"
        assert "AF-AE-SMSVER-NO-EXECUTE" in dev.getvalue()

        # (3) happy path under --execute: ONE send, HTTP 200 + SID, exit 0,
        #     and the identifier is only ever surfaced as SET
        dev3 = io.StringIO()
        caf3 = _FakeCaf(sid="SM_X1Y2Z3")
        rc3 = verify_send(caf3, "loc_QcDX", "+12025550123", "hello", execute=True, out=dev3)
        assert rc3 == EX_OK, "happy path must exit 0, got %s" % rc3
        assert caf3.writes == [("send", "loc_QcDX", {
            "to": "+12025550123", "message": "hello", "channel": "sms"})], \
            "exactly one outbound send with the documented body"
        assert "VERIFIED" in dev3.getvalue()
        assert "message identifier SET" in dev3.getvalue()
        assert "SM_X1Y2Z3" not in dev3.getvalue(), \
            "the identifier must never be echoed — SET only"
        dev3j = io.StringIO()
        rc3j = verify_send(caf3, "loc_QcDX", "+12025550123", "hello",
                           execute=True, out=dev3j, jsonout=dev3j)
        assert rc3j == EX_OK and '"sid": "SET"' in dev3j.getvalue(), \
            "the JSON surface must report sid as SET, never its value"
        assert "SM_X1Y2Z3" not in dev3j.getvalue()

        # (4) send-refusal ladder: scope -> STOP, validation -> STOP, edge
        #     block -> HELD, transport -> HELD (never mislabeled)
        for behavior, want in (("scope", EX_STOP), ("validation", EX_STOP),
                               ("edge", EX_HELD), ("transport", EX_HELD)):
            dev4 = io.StringIO()
            caf4 = _FakeCaf(send_behavior=behavior)
            rc4 = verify_send(caf4, "loc_QcDX", "+12025550123", "hello",
                              execute=True, out=dev4)
            assert rc4 == want, "send_behavior %r: want %s, got %s" % (behavior, want, rc4)
            if behavior == "edge":
                assert "never a scope problem" in dev4.getvalue(), \
                    "an edge block must NEVER be mislabeled as a scope problem"

        # (5) HTTP 200 WITHOUT an identifier -> EXIT 5 (read-back mismatch),
        #     NEVER a pass — an unconfirmed send is never called delivered
        dev5 = io.StringIO()
        caf5 = _FakeCaf(send_behavior="no-sid")
        rc5 = verify_send(caf5, "loc_QcDX", "+12025550123", "hello",
                          execute=True, out=dev5)
        assert rc5 == EX_MISMATCH, "200-no-SID must exit 5, got %s" % rc5
        assert "AF-AE-SMSVER-NO-SID" in dev5.getvalue()
        assert "VERIFIED" not in dev5.getvalue(), \
            "a SID-less response must never read as verified"

        # (6) the SID extractor is exact-key, presence-only, and refuses a
        #     non-mapping body (never trusts any other field)
        assert _extract_sid({"id": "SM_A", "messageId": "SM_B"}) == "SM_A"
        assert _extract_sid({"messageId": "SM_B"}) == "SM_B"
        assert _extract_sid({"message_id": "SM_C"}) == "SM_C"
        assert _extract_sid({"sid": "SM_D"}) == "SM_D"
        assert _extract_sid({"messageSid": "SM_E"}) == "SM_E"
        assert _extract_sid({"id": "", "messageId": "  "}) == ""
        assert _extract_sid({"ok": True}) == ""
        assert _extract_sid({"sms": "SM_X"}) == ""  # foreign keys are NEVER read
        assert _extract_sid([]) == ""
        assert _extract_sid(None) == ""
        assert _extract_sid("SM_RAW") == ""

        # (7) never-print: no token, no location id, no full destination, no
        #     message text ever reaches the operator surfaces (the self-test's
        #     own dev streams and the JSON summaries -- raw test-fixture
        #     internals are not surfaces)
        all_text = (dev.getvalue() + dev3.getvalue() + dev3j.getvalue()
                    + dev5.getvalue())
        for token in ("pit-", "loc_QcDX", "+12025550123", "hello", "SM_X1Y2Z3",
                      "Bearer ", "SEKRIT"):
            assert token not in all_text, "surface leak: %r must never appear" % token

        out.write("sms_verifier self-test: OK (fail-closed args, no-execute "
                  "STOP, happy path HTTP 200 + SID, send-refusal ladder "
                  "scope/validation/edge/transport, 200-without-SID -> exit 5 "
                  "never a pass, exact-key SID extractor, never-print, "
                  "identifier SET-only)\n")
        return EX_OK
    except AssertionError as exc:
        sys.stderr.write("[sms_verifier] SELF-TEST FAILED "
                         "(AF-AE-SMSVER-* family): %s\n" % exc)
        return EX_VIOLATION


# ---------------------------------------------------------------------------
# CLI (house style: argparse + subcommands + --self-test/--selftest aliases)
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="sms_verifier.py",
        description="Fail-closed SMS send verifier for the Convert and Flow "
                    "location: POST the outbound message under --execute and "
                    "require HTTP 200 PLUS a message identifier (SID) before "
                    "anything is called delivered (Skill 59, U23 tooling). "
                    "NEVER sends without --execute.")
    ap.add_argument("--location-id", default="",
                    help="override the client Convert and Flow location id "
                    "(label CONVERT_AND_FLOW_LOCATION_ID by default; never printed)")
    ap.add_argument("--destination", default="",
                    help="destination number for the SMS (never printed; "
                    "reported as a masked marker only)")
    ap.add_argument("--message", default="",
                    help="the SMS text to send (never printed, never echoed)")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan the send without performing it / no network, "
                    "no credential resolution")
    ap.add_argument("--execute", action="store_true",
                    help="GHL-gated ACTION flag: only with this flag may the "
                    "module POST the outbound message")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout")
    ap.add_argument("cmd", choices=["verify", "plan", "self-test"])

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
            # OFFLINE plan: validates the arguments, resolves NO credentials,
            # touches NO network, prints the plan surface. Never requires
            # --execute — a plan is not an action.
            if not args.destination.strip():
                sys.stderr.write("[sms-verifier] plan needs --destination "
                                 "(never printed)\n")
                return EX_STOP
            if not args.message.strip():
                sys.stderr.write("[sms-verifier] plan needs --message "
                                 "(never printed)\n")
                return EX_STOP
            masked_loc = args.location_id or "DRYRUN"
            sys.stderr.write("[sms-verifier] DRY RUN (marker %s): would POST "
                             "%s to send one outbound SMS to %s. No writes "
                             "performed; HTTP 200 + message identifier "
                             "required before delivered.\n"
                             % (masked_loc, SEND_PATH,
                                _mask_destination(args.destination)))
            if jsonout is not None:
                json.dump({"ok": True, "dry_run": True,
                           "location": masked_loc,
                           "destination": _mask_destination(args.destination),
                           "state": "planned"}, jsonout)
                jsonout.write("\n")
            return EX_OK

        if args.cmd == "verify":
            # Validate the action arguments OFFLINE before any credential
            # resolution or network (fail-closed, never an unplanned send).
            if not args.destination.strip():
                sys.stderr.write("[sms-verifier] verify needs --destination "
                                 "(never printed)\n")
                return EX_STOP
            if not args.message.strip():
                sys.stderr.write("[sms-verifier] verify needs --message "
                                 "(never printed)\n")
                return EX_STOP
            if args.dry_run:
                # No network in dry-run: same offline plan surface.
                masked_loc = args.location_id or "DRYRUN"
                sys.stderr.write("[sms-verifier] DRY RUN (marker %s): would "
                                 "POST %s to send one outbound SMS to %s, "
                                 "then require HTTP 200 + message "
                                 "identifier. No writes performed.\n"
                                 % (masked_loc, SEND_PATH,
                                    _mask_destination(args.destination)))
                if jsonout is not None:
                    json.dump({"ok": True, "dry_run": True,
                               "location": masked_loc,
                               "destination": _mask_destination(args.destination),
                               "state": "planned"}, jsonout)
                    jsonout.write("\n")
                return EX_OK
            pit_label, token = reg.resolve_pit()
            if not token:
                checked = ", ".join(reg.PIT_LABELS)
                reg._stop(sys.stderr,
                          "No Convert and Flow private-integration token is SET.",
                          ["Checked (in order): %s — all NOT SET." % checked,
                           "Set the client's OWN location-scoped pit- token and re-run."])
                return EX_STOP
            loc_label, loc = reg.resolve_location(args.location_id)
            if not loc:
                reg._stop(sys.stderr, "No Convert and Flow Location id is SET.",
                          ["Checked (in order): %s — all NOT SET."
                           % ", ".join(reg.LOCATION_LABELS),
                           "Set the client's OWN location id and re-run."])
                return EX_STOP
            sys.stderr.write("[sms-verifier] PIT resolved via %s (SET). "
                             "Location via %s (marker %s).\n"
                             % (pit_label, loc_label, reg._mask_location(loc)))
            client = reg.CafClient(token)
            return verify_send(client, loc, args.destination.strip(),
                               args.message.strip(), execute=args.execute,
                               out=sys.stderr, jsonout=jsonout)

        ap.error("unknown command %r" % args.cmd)
    except SystemExit:
        raise
    except reg.ScopeDenied as exc:
        sys.stderr.write("[sms_verifier] STOP: %s\n" % exc)
        return EX_STOP
    except reg.CafUnreachable as exc:
        sys.stderr.write("[sms_verifier] HELD: %s\n" % exc)
        return EX_HELD
    except Exception as exc:
        sys.stderr.write("[sms_verifier] unexpected error: %s\n" % exc)
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
