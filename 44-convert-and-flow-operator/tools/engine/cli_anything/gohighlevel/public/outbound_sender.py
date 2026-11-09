"""The one real GHL Conversations sender — built on the frozen public adapter.

WHY THIS EXISTS (review Wave 1, finding C2)
-------------------------------------------
Every Purple "sent" today is a line in a local journal: ``JournalTransport`` in
Skill 38 is ``local, append-only ... no network`` and it is the only transport
bound in production (``pb_contracts.py::_run_fulfillment``).  The original gift,
ordinary replies, reminders, the comment opener and the email ask therefore
never reach a person.

This module is the single GHL Conversations sender.  It is NOT a new HTTP
client: method, path, Version, auth class, tenant binding, approval seam,
capability gate, idempotency fingerprint and mandatory read-back all come from
``PublicGhlAdapter``.  What is added here is only what the gate contract needs:

* ``sender(ctx)`` — the ``outbound_gate.dispatch`` sender shape.  ``ctx`` must
  carry ``idempotency_key`` (the durable action key) plus, for the reply path,
  ``channel`` / ``text`` / ``contact_id``.  Returns the provider receipt, or
  ``None`` when read-back did not prove the send (the gate records unknown).
* ``find(idempotency_key)`` — the ``JournalTransport.find`` shape, so
  ``reconciliation.resolve_unknown`` can prove applied / not applied.
* A local SQLite sent-index written BEFORE the POST returns, so a crash leaves
  evidence that a send may exist.

READ-BACK
---------
``OperationResult`` carries a receipt, not the response body (the frozen
envelope).  The caller therefore injects the transport (the same pattern Skill
06's ``OpenerTransport`` uses) and the sender parses
``transport.last_response``.  Without a transport the sender still sends, but
it can never certify, so it returns ``None`` (unknown) by contract.

CHANNEL MAP
-----------
GHL's send ``type`` is the documented channel vocabulary; the agent mirrors the
inbound channel and the map below is the only translation.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .adapter import ApprovalRef, PublicGhlAdapter
from .auth import TenantBinding
from .errors import ContractViolation
from .readback import ReadbackSpec
from .transport import RequestsTransport

SEND = "conversations.messages.send"
SEARCH = "conversations.search"
LIST = "conversations.messages.list"

KEY_PREFIX = "gxo_conv-msgs-send-"

#: GHL Conversations ``type`` per inbound channel (mirror, never hardcode SMS).
CHANNEL_TYPE = {
    "sms": "SMS",
    "email": "Email",
    "fb": "FB",
    "facebook": "FB",
    "instagram": "IG",
    "ig": "IG",
    "whatsapp": "WhatsApp",
    "live_chat": "Live_Chat",
    "live chat": "Live_Chat",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sent (
    idempotency_key TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    contact_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    message_sha256 TEXT NOT NULL,
    conversation_id TEXT,
    provider_receipt_id TEXT,
    state TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
"""


def channel_type(channel: Any) -> str:
    text = str(channel or "").strip().lower()
    kind = CHANNEL_TYPE.get(text)
    if kind is None:
        raise ContractViolation("channel_unsupported", detail={"channel": text})
    return kind


def derive_idempotency_key(logical_key: Any) -> str:
    """A valid adapter key derived deterministically from the durable key.

    ``IdempotencyKey`` requires ``gxo_<op-short>-<32 hex>``; hashing keeps the
    provider key stable per durable action so a retry cannot mint a new one.
    """
    raw = str(logical_key or "").strip()
    if not raw:
        raise ContractViolation("idempotency_key_required")
    return KEY_PREFIX + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def message_sha256(text: Any) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


class SentIndex:
    """Local sent-index. ``path`` omitted -> in-memory (tests, one process)."""
    def __init__(self, path: Optional[str] = None) -> None:
        self.path = ":memory:" if path is None else str(path)
        self._db = sqlite3.connect(self.path, timeout=30.0)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def begin(self, *, idempotency_key: str, tenant_id: str, contact_id: str,
              channel: str, content_sha256: str, now: Optional[float] = None) -> None:
        """Write the intent BEFORE the POST: a crash still leaves evidence."""
        ts = time.time() if now is None else float(now)
        self._db.execute(
            "INSERT OR IGNORE INTO sent (idempotency_key, tenant_id, contact_id,"
            " channel, message_sha256, conversation_id, provider_receipt_id,"
            " state, created_at, updated_at) VALUES (?,?,?,?,?,NULL,NULL,?,?,?)",
            (idempotency_key, tenant_id, contact_id, channel, content_sha256,
             "pending", ts, ts),
        )
        self._db.commit()

    def confirm(self, idempotency_key: str, *, provider_receipt_id: str,
                conversation_id: Optional[str],
                now: Optional[float] = None) -> None:
        ts = time.time() if now is None else float(now)
        self._db.execute(
            "UPDATE sent SET provider_receipt_id=?, conversation_id=?,"
            " state='confirmed', updated_at=? WHERE idempotency_key=?",
            (provider_receipt_id, conversation_id, ts, idempotency_key),
        )
        self._db.commit()

    def get(self, idempotency_key: str) -> Optional[dict]:
        row = self._db.execute(
            "SELECT * FROM sent WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        return None if row is None else dict(row)


class CapturingTransport:
    """Wrap any frozen ``Transport`` and retain its last response body.

    The frozen envelope (``OperationResult``) carries a receipt, not the body,
    so read-back proof needs the bytes. This wrapper adds no contract: it
    delegates every request unchanged and keeps the last ``TransportResponse``.
    """

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.last_response: Any = None

    def request(self, **kwargs: Any) -> Any:
        response = self.inner.request(**kwargs)
        self.last_response = response
        return response

    @property
    def requests(self) -> Any:
        return getattr(self.inner, "requests", [])

    @property
    def call_count(self) -> int:
        return len(self.requests)


def _receipt(row: Mapping[str, Any]) -> dict:    return {
        "provider": "ghl",
        "provider_receipt_id": row["provider_receipt_id"],
        "idempotency_key": row["idempotency_key"],
        "conversation_id": row["conversation_id"],
    }


def _parse(transport: Any) -> Any:
    response = getattr(transport, "last_response", None)
    body = getattr(response, "body", None) if response is not None else None
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


def _messages(payload: Any) -> list:
    if not isinstance(payload, Mapping):
        return []
    for key in ("messages", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [m for m in value if isinstance(m, Mapping)]
        if isinstance(value, Mapping):
            inner = value.get("messages")
            if isinstance(inner, list):
                return [m for m in inner if isinstance(m, Mapping)]
    return []


def _conversation_id(payload: Any) -> Optional[str]:
    if not isinstance(payload, Mapping):
        return None
    for key in ("conversations", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping) and item.get("id"):
                    return str(item["id"])
    return None


@dataclass
class GhlSender:
    adapter: PublicGhlAdapter
    tenant: TenantBinding
    sent_index: SentIndex
    transport: Any = None
    approval: Any = None
    timeout_s: Optional[float] = None

    # -- outbound_gate.dispatch sender shape -------------------------------
    def __call__(self, ctx: dict) -> Optional[dict]:
        key = str(ctx.get("idempotency_key") or "").strip()
        if not key:
            raise ContractViolation("idempotency_key_required")
        existing = self.find(key)
        if existing is not None:
            return existing  # a confirmed send is never POSTed twice

        action = ctx.get("action") or {}
        contact_id = str(ctx.get("contact_id")
                         or action.get("canonical_contact_id") or "").strip()
        text = ctx.get("text")
        if not contact_id or text is None:
            raise ContractViolation("sender_context_incomplete")
        kind = channel_type(ctx.get("channel"))
        digest = message_sha256(text)

        self.sent_index.begin(
            idempotency_key=key, tenant_id=self.tenant.location_id,
            contact_id=contact_id, channel=kind, content_sha256=digest,
            now=ctx.get("now"),
        )

        conversation_id = ctx.get("conversation_id") or self._known_conversation(key)
        readback = self._readback(contact_id, conversation_id)
        body = {
            "type": kind,
            "contactId": contact_id,
            "locationId": self.tenant.location_id,
            "message": str(text),
        }
        kwargs = {
            "operation_id": SEND,
            "tenant": self.tenant,
            "body": body,
            "idempotency_key": derive_idempotency_key(key),
            "readback": readback,
            "approval": self._approval(ctx),
        }
        if self.timeout_s is not None:
            kwargs["timeout_s"] = float(self.timeout_s)
        result = self.adapter.call(**kwargs)

        status = getattr(result.status, "value", str(result.status))
        if status != "ok":
            # No verified read-back: the effect is unknown, never "not sent".
            return None

        receipt_id, conversation_id = self._read_back(contact_id, conversation_id)
        if receipt_id is None:
            return None
        self.sent_index.confirm(key, provider_receipt_id=receipt_id,
                                conversation_id=conversation_id,
                                now=ctx.get("now"))
        row = self.sent_index.get(key)
        return None if row is None else _receipt(row)

    # -- JournalTransport.find shape ---------------------------------------
    def find(self, idempotency_key: str) -> Optional[dict]:
        row = self.sent_index.get(str(idempotency_key))
        if row is None:
            return None
        if row["state"] == "confirmed":
            return _receipt(row)
        # A pending row may be a send whose confirmation was lost: re-prove.
        receipt_id, conversation_id = self._read_back(
            row["contact_id"], row["conversation_id"])
        if receipt_id is None:
            return None
        self.sent_index.confirm(row["idempotency_key"],
                                provider_receipt_id=receipt_id,
                                conversation_id=conversation_id)
        return _receipt(self.sent_index.get(row["idempotency_key"]))

    # -- internals ---------------------------------------------------------
    def _known_conversation(self, key: str) -> Optional[str]:
        row = self.sent_index.get(key)
        return None if row is None else row["conversation_id"]

    def _approval(self, ctx: dict) -> ApprovalRef:
        supplied = self.approval if self.approval is not None else ctx.get("approval_ref")
        if supplied is None:
            raise ContractViolation("approval_required", operation_id=SEND)
        if isinstance(supplied, ApprovalRef):
            return supplied
        return ApprovalRef(ref=str(supplied))

    def _readback(self, contact_id: str, conversation_id: Optional[str]) -> ReadbackSpec:
        if conversation_id:
            return ReadbackSpec(
                operation_id=LIST,
                target_params={"conversationId": str(conversation_id)},
                query={"limit": 20},
                expect={"contactId": contact_id},
                scan_nested=True,
            )
        return ReadbackSpec(
            operation_id=SEARCH,
            query={"contactId": contact_id},
            expect={"contactId": contact_id},
            scan_nested=True,
        )

    def _read_back(self, contact_id: str,
                   conversation_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """Prove the message exists; return (messageId, conversationId)."""
        if self.transport is None:
            return None, conversation_id
        first = _parse(self.transport)
        if conversation_id is None:
            conversation_id = _conversation_id(first)
        if conversation_id is None:
            return None, None
        if first is not None and _messages(first):
            payload = first
        else:
            result = self.adapter.call(
                operation_id=LIST, tenant=self.tenant,
                path_params={"conversationId": str(conversation_id)},
                query={"limit": 20},
            )
            if getattr(result.status, "value", str(result.status)) != "ok":
                return None, conversation_id
            payload = _parse(self.transport)
        for message in reversed(_messages(payload)):
            if str(message.get("contactId") or contact_id) != contact_id:
                continue
            if str(message.get("direction") or "outbound").lower() == "inbound":
                continue
            identifier = message.get("id") or message.get("messageId")
            if identifier:
                return str(identifier), conversation_id
        return None, conversation_id


def make_sender(adapter: PublicGhlAdapter, tenant: TenantBinding, *,
                sent_index: Optional[SentIndex] = None,
                sent_index_path: Optional[str] = None,
                transport: Any = None,
                approval: Any = None,
                timeout_s: Optional[float] = None) -> GhlSender:
    """Build the one GHL Conversations sender for a tenant."""
    if not isinstance(adapter, PublicGhlAdapter):
        raise ContractViolation("adapter_required")
    if not isinstance(tenant, TenantBinding):
        raise ContractViolation("tenant_required")
    index = sent_index if sent_index is not None else SentIndex(sent_index_path)
    if transport is None:
        transport = CapturingTransport(RequestsTransport())
    elif not hasattr(transport, "last_response"):
        transport = CapturingTransport(transport)
    return GhlSender(adapter=adapter, tenant=tenant, sent_index=index,
                     transport=transport, approval=approval, timeout_s=timeout_s)


__all__ = [
    "CHANNEL_TYPE",
    "CapturingTransport",
    "GhlSender",
    "SentIndex",
    "channel_type",
    "derive_idempotency_key",
    "make_sender",
    "message_sha256",
]
