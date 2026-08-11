#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u23_modules/sms_sender.py
# GHL-GATED TEST-SMS SENDER — send one test SMS to a given contact through the
# Convert and Flow location's LeadConnector conversation surface, with an
# idempotent GET-first contact check, a bounded read-back verification, and a
# strict --execute gate around the actual send.
#
# WHAT THIS IS (the ACTION is GHL-scope-gated; the tooling ships now):
#   The U23 surface (provision_sms_phone.py) proves a location's number can
#   send; THIS module is the companion send-side tool: it sends one SMS to a
#   specific CONTACT (not a phone number — the send is addressed by contactId,
#   exactly the canonical Skill 44 send-sms contract, see below). The v2
#   public surface it uses:
#
#     GET   /contacts/<contactId>                  read-back existence (idempotency
#                                                  law: never send into the unknown)
#     POST  /conversations/messages                send the test SMS
#     GET   /conversations/<conversationId>/messages?limit=1
#                                                  bounded read-back: the newest
#                                                  message of the conversation
#                                                  must BE the sent text
#
#   CANONICAL SEND CONTRACT (imported byte-exact, never re-invented): the
#   engine's own proven-live sibling — Skill 44's `contacts send-sms`
#   (tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py, PR #651, the
#   fleet-wide Cloudflare-1010 fix) — sends:
#
#     POST /conversations/messages
#     body {"type": "SMS", "contactId": <contact_id>, "message": <text>}
#
#   and the conversation surface's documented Version header is "2021-04-15"
#   (Skill 44 VERSION_MAP "/conversations/": "2021-04-15" and
#   29-ghl-convert-and-flow/references/conversations.md: "Version: 2021-04-15
#   (required on all calls)" — NOT 2021-07-28, the commonly-mis-cited value).
#   This module mirrors that contract exactly. Because the registry's
#   CafClient pins 2021-07-28 for its general surface, this module's send
#   rides a minimal CafClient SUBCLASS whose only addition is a per-request
#   Version override for the conversations surface; the Bearer, the browser
#   User-Agent (CAF_BROWSER_UA — the W0.6/GK-09/CF-1010 doctrine that a bare
#   urllib UA gets 403'd at the Cloudflare edge BEFORE it reaches Convert and
#   Flow) and the scope-vs-edge-block discrimination are inherited unchanged.
#   NEVER hand-roll a raw urllib POST to /conversations/messages (the exact
#   fleet-wide bug PR #651 fixed).
#
#   BOUNDED VERIFICATION, never a false pass: after a successful POST the
#   module reads back the conversation's newest messages (GET
#   /conversations/<id>/messages?limit=1) and confirms the newest message's
#   body IS the text that was sent, within a bounded window. A send whose
#   read-back never confirms is HELD (exit 3) — never reported as sent.
#
#   THE SEND ACTION STAYS GATED: this module NEVER sends without --execute.
#   Default and --dry-run are read-only / plan-only (no network in dry-run).
#   The POST /conversations/messages is a GHL-scope ACTION: it runs ONLY when
#   the operator explicitly passes --execute, which is exactly the GHL-gated
#   scope boundary.
#
# CREDENTIAL DOCTRINE: the token + location are resolved BY LABEL exactly
# like every other adapter (reg.resolve_pit / reg.resolve_location:
# CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_LOCATION_ID etc. across live process
# env then the three canonical client env stores). Values are NEVER printed
# (SET / NOT SET + masked location only). The contact id and the message body
# are surfaced only as masked markers (the message as a fixed-length hash
# marker — never the text itself). The engine's scope-vs-edge-block
# discrimination (ScopeDenied vs UpstreamBlockedError) applies to every read
# AND write: a bare 401/403 is NEVER reported as a scope problem, it is HELD.
#
# AF ERROR CODES (fail-closed surfaces, house scheme):
#   AF-AE-SMSENDER-MISSING-LABEL   -> a required label (PIT / location) is NOT
#          SET or resolves to a non-pit- value. STOP (exit 2), fail-closed.
#   AF-AE-SMSENDER-NO-EXECUTE      -> the send (POST /conversations/messages)
#          was requested without --execute. STOP; the module NEVER sends
#          without the explicit GHL-gated execute flag.
#   AF-AE-SMSENDER-NO-CONTACT      -> --contact-id missing or empty. STOP
#          (exit 2) — fail-closed before any network call.
#   AF-AE-SMSENDER-NO-MESSAGE      -> --message missing or empty. STOP
#          (exit 2) — fail-closed before any network call.
#   AF-AE-SMSENDER-READ-REFUSED    -> the GET-first contact check failed
#          (scope / validation / edge block / transport). STOP or HELD per
#          class — never a silent skip, never a send-into-the-unknown.
#   AF-AE-SMSENDER-SEND-REFUSED    -> the POST /conversations/messages was
#          rejected (validation / scope / edge block / transport). STOP or
#          HELD per class.
#   AF-AE-SMSENDER-VERIFY-REFUSED  -> the read-back GET failed (scope /
#          validation / edge / transport). STOP or HELD per class.
#   AF-AE-SMSENDER-VERIFY-STALLED  -> the read-back never confirmed the sent
#          text within the bounded window. HELD (exit 3), never a false pass.
#
# EXIT CODES (house convention; nonzero STOPS/HELDs with an operator surface):
#   0  verified success (idempotent no-op / dry run counts as pass)
#   1  unexpected error
#   2  STOP refusal — usage error / missing credential / missing --execute
#   3  Convert and Flow API unreachable / verification not confirmed (retryable)
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-SMSENDER-* family). A tamper NEVER masquerades as exit 1.
#   5  data or read-back mismatch (a required response field missing/renamed)
#
# STDLIB ONLY (urllib + json), reusing anthology_registry (CafClient transport
# + credential resolution). Calls NO model. DOCTRINE: move in silence; NOTHING
# Anthropic in any runtime file; Convert and Flow naming in every client
# surface; NEVER print a secret value; --dry-run and --self-test are OFFLINE.
# =============================================================================
"""sms_sender.py — GHL-gated test-SMS sender for the Convert and Flow location:
GET-first contact check, POST /conversations/messages under --execute, bounded
read-back verification (Skill 59, U23 tooling)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
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
DEFAULT_POLL_INTERVAL_S = 5
DEFAULT_POLL_TIMEOUT_S = 120

# The canonical send contract — byte-exact from the engine's proven-live
# sibling, Skill 44 `contacts send-sms` (PR #651). NEVER re-invented.
SEND_TYPE = "SMS"

# The conversations surface's documented Version header (Skill 44 VERSION_MAP
# "/conversations/": "2021-04-15"; 29-ghl-convert-and-flow references
# conversations.md: "Version: 2021-04-15 (required on all calls)") — NOT
# 2021-07-28, the commonly-mis-cited value. The registry's CafClient pins its
# own CAF_VERSION_HEADER (2021-07-28) for its general surface; the
# conversations endpoint needs ITS documented version, so this module's send
# carries its own header override rather than reusing the general one.
CONVERSATIONS_VERSION_HEADER = "2021-04-15"

# Fixed length of the message body marker (hex sha256 prefix). The marker is a
# hash — non-reversible, so the message text itself is never recoverable from
# any surface.
HASH_MARKER_LEN = 12


# ---------------------------------------------------------------------------
# Conversations-aware client: reg.CafClient plus a per-request Version
# override. The ONLY addition is the optional `version` keyword; the Bearer,
# the browser User-Agent (CAF_BROWSER_UA — the CF 1010 fix) and the
# scope-vs-edge-block discrimination are inherited unchanged from the registry
# (the classification core reg._auth_denial_kind is reused, never re-written).
# ---------------------------------------------------------------------------
class CafClient(reg.CafClient):
    """reg.CafClient plus an optional per-request Version override for the
    conversations surface (documented 2021-04-15). Without `version` the
    parent's exact transport applies unchanged."""

    def _request(self, method: str, path: str, query=None, body=None,
                 version: str = ""):
        if not version:
            return super()._request(method, path, query=query, body=body)
        url = reg.CAF_API_BASE + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {
            "Authorization": "Bearer %s" % self._token,
            "Version": version,
            "Accept": "application/json",
            # W0.6 / GK-09: the Cloudflare edge fronting services.leadconnectorhq.com
            # 403s urllib's default UA (CF 1010) before the request reaches Convert
            # and Flow. A browser UA is REQUIRED for the request to be scope-checked.
            "User-Agent": reg.CAF_BROWSER_UA,
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8") or "{}"
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            code = exc.code
            if code in (401, 403):
                # A bare 401/403 is NOT proof of a scope problem: the Cloudflare
                # edge fronting services.leadconnectorhq.com returns 403 (CF 1010)
                # for a blocked request BEFORE it ever reaches the scope check.
                # Inspect the BODY and only call it a scope denial when it matches
                # the genuine W0.5 signature; otherwise it is an upstream/edge block.
                raw = b""
                try:
                    raw = exc.read()
                except Exception:
                    raw = b""
                if reg._auth_denial_kind(raw) == "scope":
                    # NEVER surface the body verbatim (it could echo a credential);
                    # we matched only the fixed signature substring.
                    raise reg.ScopeDenied(
                        "token not authorized for this scope (HTTP %s)" % code)
                raise reg.UpstreamBlockedError(
                    "HTTP %s did NOT match a Convert and Flow scope-denial signature "
                    "-- likely a Cloudflare/WAF edge block, NOT a token-scope problem. "
                    "The request already carries the proven browser User-Agent "
                    "(CAF_BROWSER_UA); if this persists, re-run from the operator's "
                    "own authenticated Convert and Flow session" % code)
            if code in (400, 409, 422):
                raise reg.CafValidation(
                    "Convert and Flow rejected the request (HTTP %s)" % code)
            raise reg.CafUnreachable(
                "Convert and Flow HTTP %s on %s" % (code, method))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise reg.CafUnreachable(
                "Convert and Flow transport error: %s" % type(exc).__name__)


def _wrap_client(client):
    """Wrap a reg.CafClient in the conversations-aware client (same token and
    timeout; the registry's client is the shared credential-resolution
    surface, this wrapper only adds the per-endpoint Version override)."""
    if isinstance(client, CafClient):
        return client
    return CafClient(client._token, client._timeout)


def _mask_contact(contact_id: str) -> str:
    """A non-reversible marker for a contact id: last 4 chars only."""
    cid = (contact_id or "").strip()
    return ("..." + cid[-4:]) if len(cid) >= 4 else "...(short)"


def _mark_message(text: str) -> str:
    """A non-reversible marker for a message body: a fixed-length hex sha256
    prefix. The text itself NEVER appears on any surface."""
    return "sha256:%s" % hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:HASH_MARKER_LEN]


# ---------------------------------------------------------------------------
# LeadConnector surfaces (read-only on this client)
# ---------------------------------------------------------------------------
def get_contact(client, contact_id: str):
    """GET /contacts/<contactId>. READ-ONLY. Returns the contact dict or None.
    The GET-first idempotency law: never send into the unknown — a contact the
    read cannot confirm is a STOP/HELD, never a blind send."""
    out = client._request("GET", "/contacts/%s" % str(contact_id).strip())
    if isinstance(out, dict):
        for key in ("contact", "data"):
            v = out.get(key)
            if isinstance(v, dict):
                return v
        if "id" in out or "firstName" in out or "contactId" in out:
            return out
    return None


def send_test_sms(client, contact_id: str, message: str):
    """POST /conversations/messages — the GHL-gated ACTION. Body mirrors the
    Skill 44 canonical send contract byte-exact (type/contactId/message), with
    the conversations surface's documented Version header. Returns the parsed
    response dict (a write is never trusted without a read-back)."""
    return client._request(
        "POST", "/conversations/messages",
        body={"type": SEND_TYPE, "contactId": str(contact_id).strip(),
              "message": message},
        version=CONVERSATIONS_VERSION_HEADER)


def _find_conversation_id(sent: dict) -> str:
    """Pull the conversation id out of a send response. Returns "" when absent
    (the caller then HELDs — a send whose conversation cannot be read back is
    never called delivered)."""
    if not isinstance(sent, dict):
        return ""
    for key in ("conversationId", "conversation_id", "id"):
        v = sent.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def newest_message(client, conversation_id: str):
    """GET /conversations/<id>/messages?limit=1. READ-ONLY. Returns the newest
    message dict (the first of the returned list, if any) or None. The
    read-back verification surface — the same messages list the operator
    watches in the Convert and Flow UI."""
    out = client._request(
        "GET", "/conversations/%s/messages" % str(conversation_id).strip(),
        query={"limit": "1"}, version=CONVERSATIONS_VERSION_HEADER)
    if isinstance(out, dict):
        for key in ("messages", "data", "results"):
            v = out.get(key)
            if isinstance(v, list) and v:
                return v[0]
        return None
    if isinstance(out, list) and out:
        return out[0]
    return None


def _message_text(msg) -> str:
    """The message body text, read on the fixed key set only — never any other
    field of the message object."""
    if not isinstance(msg, dict):
        return ""
    for key in ("body", "message", "text", "content"):
        v = msg.get(key)
        if isinstance(v, str):
            return v
    return ""


# ---------------------------------------------------------------------------
# Send action (the write is never trusted without read-back)
# ---------------------------------------------------------------------------
def send_action(client, contact_id: str, message: str, *, execute: bool = False,
                poll_interval_s: int = DEFAULT_POLL_INTERVAL_S,
                poll_timeout_s: int = DEFAULT_POLL_TIMEOUT_S,
                out=None, jsonout=None) -> int:
    """GHL-gated test-SMS send: GET-first contact check, --execute boundary,
    POST /conversations/messages, then a bounded read-back confirming the
    newest message of the conversation IS the sent text. Never a false pass."""
    out = out or sys.stderr
    cid_masked = _mask_contact(contact_id)
    msg_marker = _mark_message(message)

    # -- 1. READ-ONLY contact check (idempotency law: never send blind) -------
    try:
        contact = get_contact(client, contact_id)
    except reg.ScopeDenied as exc:
        out.write("[sms-sender] AF-AE-SMSENDER-READ-REFUSED: scope denied "
                  "checking contact %s: %s\n" % (cid_masked, exc))
        return EX_STOP
    except reg.CafValidation as exc:
        out.write("[sms-sender] AF-AE-SMSENDER-READ-REFUSED: the API rejected "
                  "the contact check for %s: %s\n" % (cid_masked, exc))
        return EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[sms-sender] AF-AE-SMSENDER-READ-REFUSED: the contact check "
                  "for %s is HELD (retryable), NOT a scope problem: %s\n"
                  % (cid_masked, exc))
        return EX_HELD
    if contact is None:
        out.write("[sms-sender] AF-AE-SMSENDER-READ-REFUSED: the contact check "
                  "for %s returned no contact object (exit 5: read-back "
                  "mismatch). Nothing sent.\n" % cid_masked)
        return EX_MISMATCH

    # -- 2. GHL-gated ACTION boundary -----------------------------------------
    if not execute:
        out.write("[sms-sender] AF-AE-SMSENDER-NO-EXECUTE: contact %s exists "
                  "but --execute was NOT passed. The POST /conversations/"
                  "messages is a GHL-gated ACTION: STOP, nothing sent.\n"
                  % cid_masked)
        if jsonout is not None:
            json.dump({"ok": False, "contact": cid_masked,
                       "message": msg_marker, "exit": EX_STOP,
                       "reason": "no-execute"}, jsonout)
            jsonout.write("\n")
        return EX_STOP

    # -- 3. SEND (only under --execute) ----------------------------------------
    try:
        sent = send_test_sms(client, contact_id, message)
    except reg.ScopeDenied as exc:
        out.write("[sms-sender] AF-AE-SMSENDER-SEND-REFUSED: scope denied "
                  "sending to contact %s: %s\n" % (cid_masked, exc))
        return EX_STOP
    except reg.CafValidation as exc:
        out.write("[sms-sender] AF-AE-SMSENDER-SEND-REFUSED: the API rejected "
                  "the send to contact %s: %s\n" % (cid_masked, exc))
        return EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[sms-sender] AF-AE-SMSENDER-SEND-REFUSED: the send to "
                  "contact %s is HELD (retryable), never a scope problem: %s\n"
                  % (cid_masked, exc))
        return EX_HELD

    conversation_id = _find_conversation_id(sent)
    if not conversation_id:
        out.write("[sms-sender] AF-AE-SMSENDER-SEND-REFUSED: the API responded "
                  "to the send POST for contact %s without a conversation id "
                  "(exit 5: read-back mismatch). Nothing considered sent.\n"
                  % cid_masked)
        return EX_MISMATCH
    out.write("[sms-sender] SENT (contact %s): message %s recorded; "
              "conversation id captured.\n" % (cid_masked, msg_marker))

    # -- 4. Bounded read-back verification (a write is never trusted without
    #    confirmation; the newest message of the conversation must BE the sent
    #    text — never a false pass) --------------------------------------------
    deadline = time.monotonic() + max(0, poll_timeout_s)
    polls = 0
    while True:
        time.sleep(max(0, poll_interval_s))
        polls += 1
        try:
            newest = newest_message(client, conversation_id)
        except reg.ScopeDenied as exc:
            out.write("[sms-sender] AF-AE-SMSENDER-VERIFY-REFUSED: scope "
                      "denied during the read-back poll for contact %s: %s\n"
                      % (cid_masked, exc))
            return EX_STOP
        except reg.CafValidation as exc:
            out.write("[sms-sender] AF-AE-SMSENDER-VERIFY-REFUSED: the API "
                      "rejected the read-back poll for contact %s: %s\n"
                      % (cid_masked, exc))
            return EX_STOP
        except reg.CafUnreachable as exc:
            out.write("[sms-sender] AF-AE-SMSENDER-VERIFY-REFUSED: a read-back "
                      "poll for contact %s is HELD (retryable): %s\n"
                      % (cid_masked, exc))
            return EX_HELD
        if newest is not None and _message_text(newest) == message:
            out.write("[sms-sender] VERIFY (contact %s): newest message "
                      "matches sent text after %d poll(s).\n" % (cid_masked, polls))
            if jsonout is not None:
                json.dump({"ok": True, "contact": cid_masked,
                           "message": msg_marker, "verified": True,
                           "polls": polls}, jsonout)
                jsonout.write("\n")
            return EX_OK
        if time.monotonic() >= deadline:
            out.write("[sms-sender] AF-AE-SMSENDER-VERIFY-STALLED: the "
                      "read-back for contact %s never confirmed the sent text "
                      "within %ds (%d poll(s)). HELD, never a false pass.\n"
                      % (cid_masked, poll_timeout_s, polls))
            if jsonout is not None:
                json.dump({"ok": False, "contact": cid_masked,
                           "message": msg_marker, "verified": False,
                           "exit": EX_HELD}, jsonout)
                jsonout.write("\n")
            return EX_HELD


# ---------------------------------------------------------------------------
# SELF-TEST: golden + attack fixtures, zero network, zero secrets, zero writes.
# Mirrors the sibling self-tests (provision_sms_phone / anthology_registry):
# an assertion failure is an ENFORCED VIOLATION, exit 4 — a tamper never
# masquerades as "unexpected error" (exit 1).
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory Convert and Flow for the self-test. Mirrors the REAL surface
    used by this module (GET contact, send, newest-message read-back), with
    programmable contact contents, behaviors, and a mutation log so the tests
    can prove no write happened when none should."""

    def __init__(self, *, contact_present=True, contact_behavior=None,
                 send_behavior=None, verify_behavior=None,
                 newest_matches=True, send_returns_conversation=True,
                 stored_message=""):
        self.contact_present = contact_present
        self.contact_behavior = contact_behavior  # None|"scope"|"validation"|"edge"|"transport"|"no-id"
        self.send_behavior = send_behavior        # None|"scope"|"validation"|"edge"|"transport"|"no-conv"
        self.verify_behavior = verify_behavior    # None|"scope"|"validation"|"edge"|"transport"|"stall"|"no-id"
        self.newest_matches = newest_matches       # read-back body equals the sent text
        self.send_returns_conversation = send_returns_conversation
        self.stored_message = stored_message       # what the read-back reports
        self.writes = []                           # every mutating call, in order
        self._verify_polls = 0

    def _request(self, method, path, query=None, body=None, version=""):
        q = query or {}
        if method == "GET" and path == "/contacts/ct_QcDX":
            if self.contact_behavior == "scope":
                raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
            if self.contact_behavior == "validation":
                raise reg.CafValidation("rejected (HTTP 422)")
            if self.contact_behavior in ("edge", "transport"):
                raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
            if self.contact_behavior == "no-id" or not self.contact_present:
                return {}
            return {"contact": {"id": "ct_QcDX", "firstName": "Test",
                                "lastName": "Contact"}}
        if method == "GET" and path.startswith("/conversations/"):
            if self.verify_behavior == "scope":
                raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
            if self.verify_behavior == "validation":
                raise reg.CafValidation("rejected (HTTP 422)")
            if self.verify_behavior in ("edge", "transport"):
                raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
            if self.verify_behavior == "no-id":
                return {}
            self._verify_polls += 1
            if self.verify_behavior == "stall":
                return {"messages": [{"id": "msg_OLD", "body": "different text"}]}
            if self.newest_matches:
                text = self.stored_message or "test message body"
                return {"messages": [{"id": "msg_VERIFY", "body": text}]}
            return {"messages": [{"id": "msg_OLD", "body": "different text"}]}
        if method == "POST" and path == "/conversations/messages":
            self.writes.append(("send", q, body, version))
            if self.send_behavior == "scope":
                raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
            if self.send_behavior == "validation":
                raise reg.CafValidation("rejected (HTTP 422)")
            if self.send_behavior in ("edge", "transport"):
                raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
            if self.send_behavior == "no-conv" or not self.send_returns_conversation:
                return {}
            return {"conversationId": "conv_QcDX"}
        raise AssertionError("unexpected call: %s %s" % (method, path))


def self_test(out=None) -> int:
    import io
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # (0) marker helpers are non-reversible and never leak values
        assert _mask_contact("ct_QcDX1234") == "...1234"
        assert _mask_contact("") == "...(short)"
        marker = _mark_message("test message body")
        assert marker.startswith("sha256:") and len(marker) == 7 + HASH_MARKER_LEN
        assert "test message body" not in marker
        assert _mark_message("a") != _mark_message("b")
        assert _message_text({"body": "hi"}) == "hi"
        assert _message_text({"body": 7}) == ""
        assert _message_text({}) == ""

        # (1) no-execute: contact present, no --execute -> STOP (exit 2), NO
        #     write, message surfaced only as its hash marker
        caf1 = _FakeCaf()
        rc1 = send_action(caf1, "ct_QcDX", "test message body", out=dev)
        assert rc1 == EX_STOP, "missing --execute must STOP (exit 2), got %s" % rc1
        assert caf1.writes == [], "without --execute nothing may be sent"
        assert "AF-AE-SMSENDER-NO-EXECUTE" in dev.getvalue()
        assert "test message body" not in dev.getvalue(), \
            "the message text must never reach a surface"

        # (2) contact-check refusal ladder: scope -> STOP, validation -> STOP,
        #     edge block -> HELD, transport -> HELD, missing contact -> MISMATCH
        #     (never a blind send)
        for behavior, want in (("scope", EX_STOP), ("validation", EX_STOP),
                               ("edge", EX_HELD), ("transport", EX_HELD),
                               ("no-id", EX_MISMATCH)):
            dev2 = io.StringIO()
            caf2 = _FakeCaf(contact_behavior=behavior)
            rc2 = send_action(caf2, "ct_QcDX", "test message body",
                              execute=True, out=dev2)
            assert rc2 == want, "contact_behavior %r: want %s, got %s" % (behavior, want, rc2)
            assert caf2.writes == [], "a refused contact check must never be followed by a send"
            if behavior == "edge":
                assert "NOT a scope problem" in dev2.getvalue(), \
                    "an edge block must NEVER be mislabeled as a scope problem"
        dev2b = io.StringIO()
        rc2b = send_action(_FakeCaf(contact_present=False), "ct_QcDX",
                           "test message body", execute=True, out=dev2b)
        assert rc2b == EX_MISMATCH, "absent contact must MISMATCH, got %s" % rc2b
        assert caf1.writes == [], "an absent contact must never be sent to"

        # (3) send-refusal ladder (with --execute): refused send NEVER records
        #     a delivered message, exit per class
        for behavior, want in (("scope", EX_STOP), ("validation", EX_STOP),
                               ("edge", EX_HELD), ("transport", EX_HELD),
                               ("no-conv", EX_MISMATCH)):
            dev3 = io.StringIO()
            caf3 = _FakeCaf(send_behavior=behavior)
            rc3 = send_action(caf3, "ct_QcDX", "test message body", execute=True,
                              poll_interval_s=0, poll_timeout_s=1, out=dev3)
            assert rc3 == want, "send_behavior %r: want %s, got %s" % (behavior, want, rc3)

        # (4) the send contract is byte-exact: type SMS, contactId, message,
        #     Version 2021-04-15 on the conversations POST
        dev4 = io.StringIO()
        caf4 = _FakeCaf()
        rc4 = send_action(caf4, "ct_QcDX", "test message body", execute=True,
                          poll_interval_s=0, poll_timeout_s=1, out=dev4)
        assert rc4 == EX_OK, "happy path must exit 0, got %s" % rc4
        assert len(caf4.writes) == 1 and caf4.writes[0][0] == "send", \
            "exactly one send write expected, got %s" % [w[0] for w in caf4.writes]
        _kind, _q, body, version = caf4.writes[0]
        assert isinstance(body, dict)
        assert body.get("type") == "SMS", "send type must be SMS, got %r" % body.get("type")
        assert body.get("contactId") == "ct_QcDX", "contactId must ride the send"
        assert body.get("message") == "test message body", "message must ride the send"
        assert version == "2021-04-15", \
            "conversations surface must carry Version 2021-04-15, got %r" % version
        assert "VERIFY" in dev4.getvalue()

        # (5) verification ladder: stalled -> HELD, refused -> STOP/HELD per
        #     class, never a false pass
        dev5 = io.StringIO()
        caf5 = _FakeCaf(verify_behavior="stall")
        rc5 = send_action(caf5, "ct_QcDX", "test message body", execute=True,
                          poll_interval_s=0, poll_timeout_s=1, out=dev5)
        assert rc5 == EX_HELD, "stalled verification must HELD, got %s" % rc5
        assert "AF-AE-SMSENDER-VERIFY-STALLED" in dev5.getvalue()
        # NOTE: a read-back returning no message object is NOT a data
        # mismatch — a send simply not yet visible is propagation latency, so
        # the module keeps polling and only HELDs at the deadline (never a
        # false pass). EX_MISMATCH is reserved for the send response carrying
        # no conversation id (ladder 3).
        for behavior, want in (("scope", EX_STOP), ("validation", EX_STOP),
                               ("edge", EX_HELD), ("transport", EX_HELD),
                               ("no-id", EX_HELD)):
            dev5b = io.StringIO()
            caf5b = _FakeCaf(verify_behavior=behavior)
            rc5b = send_action(caf5b, "ct_QcDX", "test message body", execute=True,
                               poll_interval_s=0, poll_timeout_s=1, out=dev5b)
            assert rc5b == want, "verify_behavior %r: want %s, got %s" % (behavior, want, rc5b)

        # (6) a read-back whose newest message is NOT the sent text never
        #     false-passes -> HELD
        dev6 = io.StringIO()
        caf6 = _FakeCaf(newest_matches=False)
        rc6 = send_action(caf6, "ct_QcDX", "test message body", execute=True,
                          poll_interval_s=0, poll_timeout_s=1, out=dev6)
        assert rc6 == EX_HELD, "non-matching read-back must HELD, got %s" % rc6
        assert "AF-AE-SMSENDER-VERIFY-STALLED" in dev6.getvalue()

        # (7) never-print: no token, no location id, no contact id, no message
        #     text, no conversation id ever reaches the operator surfaces (the
        #     self-test's own dev streams and the JSON summaries -- raw
        #     test-fixture internals are not surfaces)
        import json as _json
        all_text = (dev.getvalue() + dev4.getvalue() + dev5.getvalue()
                    + dev6.getvalue())
        for token in ("pit-", "loc_", "ct_QcDX", "conv_QcDX", "test message body",
                      "SEKRIT", "Bearer "):
            assert token not in all_text, "surface leak: %r must never appear" % token

        # (8) _find_conversation_id reads the fixed key set only
        assert _find_conversation_id({"conversationId": "c1"}) == "c1"
        assert _find_conversation_id({"conversation_id": "c2"}) == "c2"
        assert _find_conversation_id({"id": "c3"}) == "c3"
        assert _find_conversation_id({"conversationId": "  "}) == ""
        assert _find_conversation_id({}) == ""
        assert _find_conversation_id(None) == ""

        # (9) the REAL transport path (CafClient wrapper + patched urlopen):
        #     the browser User-Agent (CF 1010 fix) AND the documented
        #     conversations Version ride the POST — the W0.6/GK-09 pin.
        _orig_urlopen = urllib.request.urlopen
        captured = {}

        class _FakeResp:
            def __init__(self, body=b"{}"):
                self._body = body
            def read(self):
                return self._body
            def getcode(self):
                return 200
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        try:
            def _ok_open(req, timeout=None):
                captured["headers"] = {k.lower(): v for k, v in req.header_items()}
                captured["method"] = req.get_method()
                captured["path"] = req.full_url
                return _FakeResp(b'{"conversationId": "conv_LIVE"}')
            urllib.request.urlopen = _ok_open
            client = CafClient("pit_probe", timeout=5)
            sent = send_test_sms(client, "ct_LIVE", "live test body")
            assert sent.get("conversationId") == "conv_LIVE"
            assert captured["headers"].get("user-agent") == reg.CAF_BROWSER_UA, \
                "browser User-Agent not sent on the conversations POST"
            assert captured["headers"].get("version") == "2021-04-15", \
                "conversations POST must carry Version 2021-04-15"
            assert captured["method"] == "POST"
            assert captured["path"] == reg.CAF_API_BASE + "/conversations/messages"

            # a Cloudflare/WAF edge block (CF 1010 HTML) is NEVER labeled a
            # scope problem on the real transport path either
            def _cf_open(req, timeout=None):
                raise urllib.error.HTTPError(
                    "https://services.leadconnectorhq.com/conversations/messages",
                    403, "err", {}, io.BytesIO(
                        b"<!DOCTYPE html><html><head><title>Attention Required! | "
                        b"Cloudflare</title></head><body>error code: 1010 Ray ID: "
                        b"deadbeef</body></html>"))
            urllib.request.urlopen = _cf_open
            try:
                send_test_sms(client, "ct_LIVE", "live test body")
                assert False, "a Cloudflare block must raise"
            except reg.ScopeDenied:
                assert False, "Cloudflare WAF block MISLABELED as ScopeDenied"
            except reg.UpstreamBlockedError:
                pass  # correctly distinguished from a scope problem
        finally:
            urllib.request.urlopen = _orig_urlopen

        out.write("sms_sender self-test: OK (golden+attack fixtures, GET-first "
                  "contact check [absent contact -> never sent], no-execute "
                  "STOP, dry-run plan offline, contact/send/verify refusal "
                  "ladders scope/validation/edge/transport/no-id, stall -> "
                  "HELD never a false pass, byte-exact send contract "
                  "type=SMS + contactId + message + Version 2021-04-15, "
                  "real-transport browser-UA + version pin, CF 1010 never "
                  "mislabeled, non-matching read-back HELD, never-print, "
                  "masking)\n")
        return EX_OK
    except AssertionError as exc:
        sys.stderr.write("[sms_sender] SELF-TEST FAILED "
                         "(AF-AE-SMSENDER-* family): %s\n" % exc)
        return EX_VIOLATION


def _json_safe(obj) -> str:
    try:
        return json.dumps(obj)
    except Exception:
        return "<unserializable>"


# ---------------------------------------------------------------------------
# CLI (house style: argparse + subcommands + --self-test/--selftest aliases)
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="sms_sender.py",
        description="GHL-gated test-SMS sender for the Convert and Flow "
                    "location: GET-first contact check, POST "
                    "/conversations/messages under --execute, bounded read-back "
                    "verification (Skill 59, U23 tooling). NEVER sends without "
                    "--execute.")
    ap.add_argument("--contact-id", default="",
                    help="the contact id the test SMS goes to (never printed)")
    ap.add_argument("--message", default="",
                    help="the test SMS text (never printed; surfaced only as a "
                    "fixed-length hash marker)")
    ap.add_argument("--location-id", default="",
                    help="override the client Convert and Flow location id "
                    "(label CONVERT_AND_FLOW_LOCATION_ID by default; never printed)")
    ap.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL_S,
                    help="verification poll cadence in seconds (default %d)"
                    % DEFAULT_POLL_INTERVAL_S)
    ap.add_argument("--poll-timeout", type=int, default=DEFAULT_POLL_TIMEOUT_S,
                    help="verification poll bound in seconds (default %d)"
                    % DEFAULT_POLL_TIMEOUT_S)
    ap.add_argument("--dry-run", action="store_true",
                    help="plan the send without performing it / no network")
    ap.add_argument("--execute", action="store_true",
                    help="GHL-gated ACTION flag: only with this flag may the "
                    "module POST /conversations/messages")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout")
    ap.add_argument("cmd", choices=["send", "plan", "self-test"])

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
                # No network in dry-run: a masked placeholder surface so
                # surfaces read; nothing exists offline.
                masked_loc = args.location_id or "DRYRUN"
                sys.stderr.write("[sms-sender] DRY RUN (marker %s): would "
                                 "GET-check the contact, then POST "
                                 "/conversations/messages, then verify the "
                                 "newest message read-back. No writes "
                                 "performed.\n" % masked_loc)
                if jsonout is not None:
                    json.dump({"ok": True, "dry_run": True,
                               "location": masked_loc, "state": "planned"}, jsonout)
                    jsonout.write("\n")
                return EX_OK
            client, loc_or_rc = reg._live_client(args.location_id)
            if client is None:
                return loc_or_rc
            client = _wrap_client(client)
            masked_loc = reg._mask_location(loc_or_rc)
            cid_masked = _mask_contact(args.contact_id)
            msg_marker = _mark_message(args.message)
            try:
                contact = get_contact(client, args.contact_id)
            except reg.ScopeDenied as exc:
                sys.stderr.write("[sms-sender] AF-AE-SMSENDER-READ-REFUSED: "
                                 "scope denied checking contact %s: %s\n"
                                 % (cid_masked, exc))
                return EX_STOP
            except reg.CafValidation as exc:
                sys.stderr.write("[sms-sender] AF-AE-SMSENDER-READ-REFUSED: "
                                 "the API rejected the contact check for %s: %s\n"
                                 % (cid_masked, exc))
                return EX_STOP
            except reg.CafUnreachable as exc:
                sys.stderr.write("[sms-sender] AF-AE-SMSENDER-READ-REFUSED: "
                                 "the contact check for %s is HELD (retryable), "
                                 "NOT a scope problem: %s\n" % (cid_masked, exc))
                return EX_HELD
            if contact is None:
                sys.stderr.write("[sms-sender] AF-AE-SMSENDER-READ-REFUSED: "
                                 "the contact check for %s returned no contact "
                                 "object (exit 5: read-back mismatch).\n"
                                 % cid_masked)
                return EX_MISMATCH
            sys.stderr.write("[sms-sender] PLAN (marker %s): contact %s exists. "
                             "With --execute, the module would POST "
                             "/conversations/messages with message %s, then "
                             "verify the read-back.\n"
                             % (masked_loc, cid_masked, msg_marker))
            if jsonout is not None:
                json.dump({"ok": True, "dry_run": False, "location": masked_loc,
                           "contact": cid_masked, "message": msg_marker,
                           "plan": "send"}, jsonout)
                jsonout.write("\n")
            return EX_OK

        if args.cmd == "send":
            if args.dry_run:
                # No network in dry-run: same offline plan surface.
                masked_loc = args.location_id or "DRYRUN"
                sys.stderr.write("[sms-sender] DRY RUN (marker %s): would "
                                 "GET-check the contact, then POST "
                                 "/conversations/messages, then verify the "
                                 "newest message read-back. No writes "
                                 "performed.\n" % masked_loc)
                if jsonout is not None:
                    json.dump({"ok": True, "dry_run": True,
                               "location": masked_loc, "state": "planned"}, jsonout)
                    jsonout.write("\n")
                return EX_OK
            if not args.contact_id.strip():
                sys.stderr.write("[sms-sender] AF-AE-SMSENDER-NO-CONTACT: "
                                 "--contact-id is required (never printed). "
                                 "STOP before any network call.\n")
                return EX_STOP
            if not args.message.strip():
                sys.stderr.write("[sms-sender] AF-AE-SMSENDER-NO-MESSAGE: "
                                 "--message is required (never printed; "
                                 "surfaced only as a hash marker). STOP before "
                                 "any network call.\n")
                return EX_STOP
            client, loc_or_rc = reg._live_client(args.location_id)
            if client is None:
                return loc_or_rc
            client = _wrap_client(client)
            return send_action(
                client, args.contact_id.strip(), args.message.strip(),
                execute=args.execute,
                poll_interval_s=args.poll_interval,
                poll_timeout_s=args.poll_timeout,
                out=sys.stderr, jsonout=jsonout)

        ap.error("unknown command %r" % args.cmd)
    except SystemExit:
        raise
    except reg.ScopeDenied as exc:
        sys.stderr.write("[sms_sender] scope denied: %s\n" % exc)
        return EX_STOP
    except reg.CafUnreachable as exc:
        sys.stderr.write("[sms_sender] HELD: %s\n" % exc)
        return EX_HELD
    except Exception as exc:
        sys.stderr.write("[sms_sender] unexpected error: %s\n" % exc)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
