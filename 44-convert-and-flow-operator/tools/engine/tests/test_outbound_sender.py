"""Offline proofs for the one GHL Conversations sender (review C2).

Run either way:
    python3 -I test_outbound_sender.py
    pytest -q test_outbound_sender.py

Proves, with no network:
  1. HTTP 200 + read-back returns the provider receipt and POSTs exactly once.
  2. A 5xx returns None (unknown outcome), never a "sent" receipt.
  3. The same idempotency key twice makes exactly one POST.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
for path in (ENGINE, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

from cli_anything.gohighlevel.public.adapter import ApprovalRef  # noqa: E402
from cli_anything.gohighlevel.public.auth import (  # noqa: E402
    AuthKind,
    AuthContext,
    TenantBinding,
)
from cli_anything.gohighlevel.public.capability import CapabilityGate  # noqa: E402
from cli_anything.gohighlevel.public.outbound_sender import (  # noqa: E402
    SEND,
    LIST,
    CapturingTransport,
    derive_idempotency_key,
    make_sender,
)
from cli_anything.gohighlevel.public.readback import ReadbackRegistry  # noqa: E402

import _public_contract_fakes as fakes  # noqa: E402

TENANT = "loc_synthetic_0001"
CONTACT = "contact_synthetic_0001"
CONVERSATION = "conv_synthetic_0001"
KEY = "reply:loc_synthetic_0001:contact_synthetic_0001:msg_in_1"


def _rows():
    return fakes.registry(
        fakes.row(SEND, method="POST", path_template="/conversations/messages",
                  write=True, approval_required=True),
        fakes.row(LIST, method="GET",
                  path_template="/conversations/{conversationId}/messages",
                  tenant_binding="path.conversationId"),
    )


def _build(responses):
    inner = fakes.FakeTransport(responses)
    transport = CapturingTransport(inner)
    gate = fakes.enabled_gate(list(_rows().values()))
    adapter = fakes.make_adapter(transport, _rows(), gate=gate,
                                 readbacks=ReadbackRegistry())
    sender = make_sender(adapter, fakes.fake_tenant(TENANT),
                         transport=transport,
                         approval=ApprovalRef(ref="owner-approval-1"))
    return sender, transport


def _ctx():
    return {
        "idempotency_key": KEY,
        "action": {"canonical_contact_id": CONTACT},
        "channel": "sms",
        "text": "Yes — the gift is yours. Tap this link.",
        "contact_id": CONTACT,
        "conversation_id": CONVERSATION,
    }


SEND_BODY = json.dumps({"messageId": "msg_out_1",
                        "conversationId": CONVERSATION}).encode()
LIST_BODY = json.dumps({"messages": [
    {"id": "msg_out_1", "conversationId": CONVERSATION,
     "contactId": CONTACT, "direction": "outbound"},
]}).encode()


def test_http_200_returns_receipt_and_posts_once():
    sender, transport = _build([fakes.resp(200, SEND_BODY),
                               fakes.resp(200, LIST_BODY)])
    receipt = sender(_ctx())
    assert receipt is not None, "a verified send must return a receipt"
    assert receipt["provider"] == "ghl"
    assert receipt["provider_receipt_id"] == "msg_out_1"
    assert receipt["idempotency_key"] == KEY
    assert transport.call_count == 2, transport.requests
    assert transport.requests[0]["method"] == "POST"
    assert transport.requests[0]["url"] == "/conversations/messages"
    assert transport.requests[0]["body"]["type"] == "SMS"
    assert transport.requests[0]["body"]["contactId"] == CONTACT
    assert transport.requests[0]["body"]["locationId"] == TENANT
    assert derive_idempotency_key(KEY).startswith("gxo_conv-msgs-send-")


def test_5xx_is_unknown_not_sent():
    sender, transport = _build([fakes.resp(500, b'{"message":"boom"}')])
    assert sender(_ctx()) is None
    assert transport.call_count == 1, "a 5xx must not be read back as success"


def test_duplicate_key_makes_no_second_post():
    sender, transport = _build([fakes.resp(200, SEND_BODY),
                               fakes.resp(200, LIST_BODY)])
    first = sender(_ctx())
    posts = sum(1 for r in transport.requests if r["method"] == "POST")
    second = sender(dict(_ctx()))
    posts_after = sum(1 for r in transport.requests if r["method"] == "POST")
    assert first is not None and second is not None
    assert second["provider_receipt_id"] == first["provider_receipt_id"]
    assert posts == 1 and posts_after == 1, transport.requests


def _main():
    checks = [test_http_200_returns_receipt_and_posts_once,
              test_5xx_is_unknown_not_sent,
              test_duplicate_key_makes_no_second_post]
    for check in checks:
        check()
        print("PASS", check.__name__)
    print("RESULT: PASS 3/3")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
