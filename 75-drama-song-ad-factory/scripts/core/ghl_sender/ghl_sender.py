#!/usr/bin/env python3
"""ghl_sender: the version-1 GoHighLevel text/e-mail sender (U17).

WHAT THIS IS
------------
ONE sender the drama-song studio uses to hand a finished video's LINK to a
client and to send the follow-up NUDGES, over the client's OWN GoHighLevel
(white label: Convert and Flow) conversation rail. Two channels, ONE endpoint:

  * text   -> POST /conversations/messages   type "SMS"
  * e-mail -> POST /conversations/messages   type "Email"

That is the canonical shape (38-conversational-ai-system/references/
ghl-api-quick-reference.md): the All-in-One Chat endpoint carries every channel,
threaded by contactId. There is no second endpoint, no second sender, no new
proxy or adapter, and no dashboard.

TOKEN-PRESENCE GATING -- no token means REFUSE, never send
----------------------------------------------------------
The sender runs ONLY where the box has a working GHL token. `token_present()`
checks the location-token ENV NAMES and yields a boolean; a send with no token
REFUSES with a stable code before anything is built or transmitted. The token
VALUE is never read into a variable this module returns, stores or prints:
`Authorization: Bearer <token>` is attached by the INJECTED transport from the
runtime's own secret store, so the secret never enters this module's request
bytes, its receipts or its output. Only the presence check exists.

NO LIVE SEND, NO TEST SEND
--------------------------
This module opens no socket. The wire call is a TRANSPORT the runtime injects
(`transport(request) -> result`), and there is NO default live transport: a send
with no transport injected REFUSES. Every test runs a recording stub, so the
unit proves the REQUEST BYTES are exactly the canonical shape without
transmitting anything.

Stdlib only.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys

TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.ghl-sender/receipt/v1"

GHL_API_URL = "https://services.leadconnectorhq.com/conversations/messages"
GHL_API_VERSION = "2021-04-15"

#: channel name -> GHL `type`. The short codes are the only valid send types.
CHANNELS = {"text": "SMS", "email": "Email"}

#: Location Private Integration Token env NAMES (presence is checked, the value
#: is never read out). Any one set-and-non-empty is a working token.
TOKEN_ENV_ALIASES = (
    "GHL_PRIVATE_INTEGRATION_TOKEN",
    "GHL_LOCATION_PIT",
    "GOHIGHLEVEL_API_KEY",
    "GHL_API_KEY",
    "CONVERT_AND_FLOW_PIT",
)
#: The sub-account (location) id env NAMES -- also presence-checked.
LOCATION_ENV_ALIASES = (
    "GHL_LOCATION_ID",
    "GOHIGHLEVEL_LOCATION_ID",
    "CONVERT_AND_FLOW_LOCATION_ID",
)

#: Named refusals -- a refusal always names itself, never a silent blank.
AF_TOKEN_MISSING = "AF-U17-TOKEN-MISSING"
AF_TRANSPORT_MISSING = "AF-U17-TRANSPORT-MISSING"

class SenderError(ValueError):
    """The request is malformed (bad channel or missing required field)."""

class SendRefused(RuntimeError):
    """A fail-closed refusal: nothing was built, nothing was transmitted."""

    def __init__(self, reason_code, message):
        super().__init__("%s: %s" % (reason_code, message))
        self.reason_code = reason_code
        self.message = message

def _env(env):
    return os.environ if env is None else env

def _present(names, env):
    """True when ANY of the named env vars is set to a non-empty value. The
    VALUE is consumed by the boolean and never returned, stored or printed."""
    e = _env(env)
    return any(bool((e.get(name) or "").strip()) for name in names)

def token_present(env=None):
    """PRESENCE only: True when a GHL location token name is set-and-non-empty.
    Never returns, logs or stores the value -- this is the whole credential
    check, there is no read of a secret."""
    return _present(TOKEN_ENV_ALIASES, env)

def location_present(env=None):
    """PRESENCE only: True when a location-id name is set-and-non-empty."""
    return _present(LOCATION_ENV_ALIASES, env)

def _require(value, name):
    if value is None or (isinstance(value, str) and not value.strip()):
        raise SenderError("missing required field: %s" % name)
    return value

def build_body(channel, contact_id, location_id, *, text=None, subject=None,
               html=None, email_from=None, email_to=None):
    """The canonical JSON body for one message. text -> SMS {type,contactId,
    locationId,message}; e-mail -> Email {type,contactId,locationId,subject,html,
    emailFrom,emailTo}. Unknown channel is refused."""
    if channel not in CHANNELS:
        raise SenderError("unknown channel %r; channels are %s"
                          % (channel, ", ".join(sorted(CHANNELS))))
    body = {"type": CHANNELS[channel], "contactId": _require(contact_id, "contact_id"),
            "locationId": _require(location_id, "location_id")}
    if channel == "text":
        body["message"] = _require(text, "text")
    else:
        body["subject"] = _require(subject, "subject")
        body["html"] = _require(html, "html")
        body["emailFrom"] = _require(email_from, "email_from")
        body["emailTo"] = _require(email_to, "email_to")
    return body

def encode_body(body):
    """Canonical request bytes: compact JSON, UTF-8. Deterministic (insertion
    order), so the exact bytes are assertable without transmitting anything."""
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def build_request(channel, contact_id, location_id, *, text=None, subject=None,
                  html=None, email_from=None, email_to=None, purpose=None):
    """The non-secret request the transport must send. Carries NO Authorization
    header and NO secret -- the token value never enters these bytes. Returns
    {channel, type, purpose, method, url, headers, body(bytes)}."""
    body = build_body(channel, contact_id, location_id, text=text, subject=subject,
                      html=html, email_from=email_from, email_to=email_to)
    return {
        "channel": channel,
        "type": CHANNELS[channel],
        "purpose": purpose,
        "method": "POST",
        "url": GHL_API_URL,
        "headers": {"Version": GHL_API_VERSION, "Content-Type": "application/json"},
        "body": encode_body(body),
    }

def build_receipt(request, result, now=None):
    """ONE receipt per message: the non-secret request identity plus the ids the
    rail returned (messageId / conversationId). Never a secret, never the body
    verbatim -- only its sha256."""
    result = result or {}
    when = now or _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    return {
        "schema": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "channel": request["channel"],
        "type": request["type"],
        "purpose": request.get("purpose"),
        "contact_id": json.loads(request["body"].decode("utf-8")).get("contactId"),
        "location_id": json.loads(request["body"].decode("utf-8")).get("locationId"),
        "url": request["url"],
        "body_sha256": hashlib.sha256(request["body"]).hexdigest(),
        "message_id": result.get("messageId") or result.get("message_id"),
        "conversation_id": result.get("conversationId") or result.get("conversation_id"),
        "delivered": bool(result),
        "sent_at": when.isoformat().replace("+00:00", "Z"),
    }

def send(channel, contact_id, location_id, *, text=None, subject=None, html=None,
         email_from=None, email_to=None, purpose=None, transport=None, env=None,
         now=None):
    """Send ONE message on the client's own GHL rail and return its receipt.

    Fail-closed, in this order: no token -> :class:`SendRefused`
    AF-U17-TOKEN-MISSING; no transport -> AF-U17-TRANSPORT-MISSING. The
    transport is the ONLY wire call and is injected (tests inject a recording
    stub). The receipt is built from the request and the transport's result."""
    if not token_present(env):
        raise SendRefused(AF_TOKEN_MISSING,
                          "no GHL location token on this box; nothing was sent")
    if transport is None:
        raise SendRefused(AF_TRANSPORT_MISSING,
                          "no transport injected; this module never sends live")
    request = build_request(channel, contact_id, location_id, text=text,
                            subject=subject, html=html, email_from=email_from,
                            email_to=email_to, purpose=purpose)
    return build_receipt(request, transport(request), now=now)

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build (and, with an injected transport, send) one GHL text "
                    "or e-mail. There is no live transport here: `send` refuses.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for verb in ("build", "send"):
        p = sub.add_parser(verb)
        p.add_argument("--channel", choices=sorted(CHANNELS), required=True)
        p.add_argument("--contact-id", required=True)
        p.add_argument("--location-id", required=True)
        p.add_argument("--text", default=None)
        p.add_argument("--subject", default=None)
        p.add_argument("--html", default=None)
        p.add_argument("--email-from", default=None)
        p.add_argument("--email-to", default=None)
        p.add_argument("--purpose", default=None)
    a = ap.parse_args(argv)
    kw = dict(text=a.text, subject=a.subject, html=a.html,
              email_from=a.email_from, email_to=a.email_to, purpose=a.purpose)
    if a.cmd == "build":
        r = build_request(a.channel, a.contact_id, a.location_id, **kw)
        print(json.dumps({**r, "body": r["body"].decode("utf-8")}, sort_keys=True))
        return 0
    try:
        send(a.channel, a.contact_id, a.location_id, **kw)
    except SendRefused as e:
        sys.stderr.write("REFUSED: %s\n" % e)
        return 5
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
