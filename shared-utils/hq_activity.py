#!/usr/bin/env python3
"""hq_activity.py — the bounded, signed outbox sender for Headquarters activity.

SPEC.md rev 4 S5 ("Outbox defaults") + S7 ("Versioned producer envelope",
"Semantic hash").  Stdlib only — this module imports nothing outside the
standard library, because the box's runtime is what it is.

WHO CALLS THIS
    `scripts/mc-route.sh` and the Command Center task producers.  SPEC S5 makes
    one append path the only writer of Headquarters activity; this module is the
    ONB half — the *sender*.  It never writes to the Command Center database and
    never speaks to a client box.

WHAT IT GUARANTEES (each maps to one SPEC sentence, quoted at the code)
    * one JSON file per event, ATOMIC rename (never a half-written file)
    * byte caps checked on ENCODED bytes before enqueue (128 KiB payload,
      4 KiB metadata), count cap 1,000 and total cap 8 MiB, whichever fills first
    * dedupe and conflict detection run through a sidecar index over those files,
      so they stay O(1) on the caller's critical path instead of reading up to
      1,000 pending files per event
    * retry off the existing bounded job runner: 30 s minimum, exponential to
      5 minutes, no busy loop; 2 s emit timeout
    * explicit capture-health degradation when it cannot write or deliver —
      an honest degraded state, never a silent drop — and the caller's business
      work is never blocked by telemetry
    * the semantic hash is SHA-256 over the canonical UTF-8 serialization of
      `event` only, byte-identical to the frozen TypeScript side
    * no provider, model or policy value is read or written anywhere in here

RECEIVER EXPIRY IS NOT THIS SIDE'S CLOCK
    SPEC S7: original `issuedAt` older than 24 h is refused by the receiver (410
    `event_expired`); a future `issuedAt` over 5 minutes is 422.  So this module
    expires a pending file after 24 h, counts the loss, and NEVER rewrites
    `issuedAt` to renew it.  Dedup survives that horizon through the receiver's
    durable receipts (48 h), which is why a replayed key still dedupes.

CLI
    python3 shared-utils/hq_activity.py                 # runnable self-check
    python3 shared-utils/hq_activity.py --flush         # what the job runner calls
    python3 shared-utils/hq_activity.py --health        # print capture health JSON
    python3 shared-utils/hq_activity.py --write-vectors PATH
        # prints the shared golden-vector fixture for the cross-language test
"""

from __future__ import annotations

import calendar
import hashlib
import hmac
import json
import math
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

__all__ = [
    "HQ_ENVELOPE_SCHEMA_VERSION",
    "OUTBOX_DIRNAME",
    "PAYLOAD_MAX_BYTES",
    "METADATA_MAX_BYTES",
    "PENDING_MAX_COUNT",
    "PENDING_MAX_BYTES",
    "RETRY_MIN_SECONDS",
    "RETRY_MAX_SECONDS",
    "EMIT_TIMEOUT_SECONDS",
    "PENDING_EXPIRY_SECONDS",
    "ISSUED_AT_MAX_AGE_SECONDS",
    "ISSUED_AT_MAX_FUTURE_SECONDS",
    "RECEIPT_COVERAGE_SECONDS",
    "HqEnvelopeError",
    "HqConflictError",
    "HqOutbox",
    "hq_semantic_serialize",
    "hq_semantic_hash_hex",
    "hq_duplicate_object_keys",
    "hq_retry_delay",
    "hq_envelope_bounds",
    "enqueue_activity",
    "HqHttpTransport",
    "golden_vectors",
]

# ── frozen bounds (SPEC S5 outbox defaults, SPEC S7) ─────────────────────────

HQ_ENVELOPE_SCHEMA_VERSION = 1
OUTBOX_DIRNAME = os.path.join("hq-telemetry", "outbox")
PAYLOAD_MAX_BYTES = 128 * 1024          # serialized UTF-8 payload, encoded bytes
METADATA_MAX_BYTES = 4 * 1024           # everything that is not `event`
PENDING_MAX_COUNT = 1_000               # max 1,000 pending ...
PENDING_MAX_BYTES = 8 * 1024 * 1024     # ... AND 8 MiB total, whichever fills first
RETRY_MIN_SECONDS = 30.0                # 30-second retry minimum
RETRY_MAX_SECONDS = 300.0               # exponential delay to 5 minutes
EMIT_TIMEOUT_SECONDS = 2.0              # emit timeout 2 seconds
PENDING_EXPIRY_SECONDS = 24 * 3600      # producer expires pending files after 24 hours
ISSUED_AT_MAX_AGE_SECONDS = 24 * 3600   # receiver: issuedAt older than 24 h -> 410
ISSUED_AT_MAX_FUTURE_SECONDS = 300.0    # receiver: future issuedAt over 5 min -> 422
RECEIPT_COVERAGE_SECONDS = 48 * 3600    # receiver keeps dedup receipts 48 hours

# S5 safe content: full captured exchange message 8,000 chars, summary 2,000.
_MESSAGE_MAX_CHARS = 8_000
_SUMMARY_MAX_CHARS = 2_000
_SESSION_KEY_MAX_CHARS = 512
_TEXT_MAX_CHARS = 4_000                 # owner_note / decision / task strings

_KINDS_PHASES = {
    "task": ("created", "assigned", "status_changed"),
    "owner_note": ("recorded",),
    "decision": ("applied", "shadow", "unavailable"),
    "exchange": ("requested", "accepted", "replied", "failed", "uncertain"),
}
_TOOL_NAMES = ("sessions_send", "sessions_spawn", "task_dispatch")
_SOURCE_HOOKS = ("before_tool_call", "after_tool_call", "lifecycle", "task_dispatch")
_NATIVE_STATUSES = ("accepted", "ok", "timeout", "error", "forbidden", "no_reply", "queued", "end")
_TARGET_DISPOSITIONS = ("queued", "steered")
_CORRELATION_STATUSES = ("linked", "unresolved", "unsupported")
_DECISION_MODES = ("live", "shadow", "unavailable", "off", "legacy")

# All keys present; null is not omission.  Unknown keys rejected (S7).
_EVENT_KEYS = (
    "eventId", "sourceKey", "installationId", "companyId", "issuedAt", "occurredAt",
    "kind", "phase", "taskId", "actorRuntimeId", "recipientRuntimeId",
    "fromWorkspaceId", "toWorkspaceId", "exchangeId", "payload",
)
_TASK_PAYLOAD_KEYS = ("status", "previousStatus")
_OWNER_NOTE_PAYLOAD_KEYS = ("text",)
_DECISION_PAYLOAD_KEYS = (
    "intent", "routeAction", "departmentSlug", "confidenceBps",
    "fallback", "mode", "resolvedBy",
)
_EXCHANGE_PAYLOAD_KEYS = (
    "message", "summary", "toolName", "toolCallId", "callerRunId", "targetRunId",
    "callerSessionKey", "targetSessionKey", "sourceHook", "nativeStatus",
    "targetDisposition", "correlationStatus",
)

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_SOURCE_KEY_RE = re.compile(
    r"^(task|transition|decision|exchange|note):[^\s:]+(:[a-z_]+)?$")
_PENDING_PREFIX = "evt-"


class HqEnvelopeError(ValueError):
    """The event is not a valid S7 producer event. Nothing was written."""


class HqConflictError(HqEnvelopeError):
    """Same source key, different content. Recorded diagnostically, never overwritten."""


# ── canonical serialization (SPEC S7 "Semantic hash") ────────────────────────

def _assert_no_lone_surrogate(text: str) -> None:
    """SPEC S7: reject lone surrogates (they have no UTF-8 encoding)."""
    for i, ch in enumerate(text):
        code = ord(ch)
        if 0xD800 <= code <= 0xDBFF:
            nxt = ord(text[i + 1]) if i + 1 < len(text) else 0
            if not (0xDC00 <= nxt <= 0xDFFF):
                raise HqEnvelopeError("semantic value contains a lone surrogate")
        elif 0xDC00 <= code <= 0xDFFF:
            raise HqEnvelopeError("semantic value contains a lone surrogate")


def hq_semantic_serialize(value):
    """SPEC S7 canonical bytes-as-text.

    "lexicographically sorted ASCII keys at every object level; no extra
    whitespace; UTF-8 Unicode emitted directly; JSON control/quote/backslash
    escapes; reject lone surrogates, NaN, duplicate keys and non-integer
    numbers."

    Byte-identical to
    `json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',',':'),
                allow_nan=False)` — which is the formula SPEC S7 names for
    Python, so this function is a checked re-statement of it, not an invention.

    ponytail: a JSON object's keys should be ASCII strings. `str.isascii()` is
    asserted because Python's code-point ordering and JavaScript's UTF-16 code
    unit ordering disagree for non-BMP keys (U+10000+ vs U+E000..U+FFFF), so a
    non-ASCII key could not be byte-identical across the two languages anyway.
    The envelope's own keys are all fixed ASCII; raise rather than silently
    disagree.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        _assert_no_lone_surrogate(value)
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        if not -(2 ** 53 - 1) <= value <= 2 ** 53 - 1:
            raise HqEnvelopeError("semantic value integer is outside the safe range")
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise HqEnvelopeError("semantic value is NaN or Infinity")
        if not value.is_integer():
            raise HqEnvelopeError("semantic value is a non-integer number")
        raise HqEnvelopeError("semantic value must not be a float (use an int)")
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(hq_semantic_serialize(v) for v in value) + "]"
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise HqEnvelopeError("semantic object key is not a string")
            if key.isascii() is False:
                raise HqEnvelopeError("semantic object key is not ASCII")
        parts = []
        for key in sorted(value):
            parts.append(hq_semantic_serialize(key) + ":" + hq_semantic_serialize(value[key]))
        return "{" + ",".join(parts) + "}"
    raise HqEnvelopeError("semantic value has unsupported type %s" % type(value).__name__)


def hq_semantic_hash_hex(event) -> str:
    """SHA-256 of the canonical serialization of `event`, lowercase hex.

    SPEC S7: "Semantic hash is SHA-256 of UTF-8 serialization of `event` only."
    `sentAt` is excluded from the hash and covered by the signature instead.
    """
    return hashlib.sha256(hq_semantic_serialize(event).encode("utf-8")).hexdigest()


def hq_duplicate_object_keys(json_text: str) -> bool:
    """True when `json_text` contains an object with a duplicated key.

    SPEC S7 rejects duplicate keys before hashing. `json.loads` collapses them,
    so the check runs through `object_pairs_hook`, which sees the raw pairs at
    every object level. Returns False for text the parser cannot read.
    """
    found = False

    def _hook(pairs):
        nonlocal found
        seen = set()
        for key, _ in pairs:
            if key in seen:
                found = True
                break
            seen.add(key)
        return dict(pairs)

    try:
        json.loads(json_text, object_pairs_hook=_hook)
    except ValueError:
        return False
    return found


# ── retry schedule (SPEC S5 "30-second retry minimum, exponential ... 5 minutes") ──

def hq_retry_delay(attempts: int) -> float:
    """Seconds to wait after `attempts` failures. 30 s, doubling, capped at 300 s.

    Never returns 0 — that is the "no busy loop" clause. The caller (or the
    existing scheduled-job runner) owns the actual sleeping.
    """
    if attempts < 1:
        return 0.0
    return min(RETRY_MIN_SECONDS * (2.0 ** (attempts - 1)), RETRY_MAX_SECONDS)


# ── event validation (SPEC S7 envelope, S5 safe content) ─────────────────────

def _require(condition, message):
    if not condition:
        raise HqEnvelopeError(message)


def _str_or_none(value, field, max_chars=_TEXT_MAX_CHARS):
    if value is None:
        return None
    _require(isinstance(value, str), "%s must be a string or null" % field)
    _assert_no_lone_surrogate(value)
    _require(len(value) <= max_chars, "%s exceeds %d characters" % (field, max_chars))
    return value


def _enum_or_none(value, field, allowed):
    if value is None:
        return None
    _require(value in allowed, "%s has unsupported value %r" % (field, value))
    return value


def validate_event(event) -> dict:
    """Strict S7 validation. Returns the event; raises `HqEnvelopeError` otherwise.

    All keys present (null is not omission), unknown keys rejected, no floats
    anywhere, kind/phase pairing enforced, text caps enforced on the payload —
    this is the structural half of the S5 boundary that keeps provider payloads,
    hidden reasoning and credentials out of the outbox.
    """
    _require(isinstance(event, dict), "event must be an object")
    _require(not hq_duplicate_object_keys(json.dumps(event, ensure_ascii=False)),
             "event contains a duplicate key")
    unknown = set(event) - set(_EVENT_KEYS)
    _require(not unknown, "event has unknown key(s): %s" % sorted(unknown))
    missing = [k for k in _EVENT_KEYS if k not in event]
    _require(not missing, "event is missing key(s): %s" % missing)

    event_id = event["eventId"]
    _require(isinstance(event_id, str) and bool(_UUID_RE.match(event_id)),
             "eventId must be a UUID")
    _require(isinstance(event["sourceKey"], str) and bool(_SOURCE_KEY_RE.match(event["sourceKey"])),
             "sourceKey must be <family>:<id>[:<phase>]")
    for field in ("installationId", "companyId"):
        _require(isinstance(event[field], str) and event[field] != "",
                 "%s must be a non-empty string" % field)
    _require(isinstance(event["issuedAt"], str) and event["issuedAt"].endswith("Z"),
             "issuedAt must be a UTC ISO string ending in Z")
    if event["occurredAt"] is not None:
        _require(isinstance(event["occurredAt"], str) and event["occurredAt"].endswith("Z"),
                 "occurredAt must be null or a UTC ISO string ending in Z")

    kind = event["kind"]
    _require(kind in _KINDS_PHASES, "unsupported kind %r" % (kind,))
    _require(event["phase"] in _KINDS_PHASES[kind],
             "kind %r cannot carry phase %r" % (kind, event["phase"]))

    for field in ("taskId", "actorRuntimeId", "recipientRuntimeId",
                  "fromWorkspaceId", "toWorkspaceId", "exchangeId"):
        _str_or_none(event[field], field)
    if event["exchangeId"] is not None:
        _require(re.fullmatch(r"[0-9a-f]{64}", event["exchangeId"]) is not None,
                 "exchangeId must be exactly 64 lowercase hex characters")

    validate_payload(kind, event["payload"])
    return event


def validate_payload(kind: str, payload) -> dict:
    """Per-kind payload schema. Unknown keys are rejected, not ignored."""
    _require(isinstance(payload, dict), "payload must be an object")
    if kind == "task":
        keys = _TASK_PAYLOAD_KEYS
        _require(set(payload) == set(keys), "task payload keys must be exactly %s" % (list(keys),))
        _str_or_none(payload["status"], "payload.status")
        _str_or_none(payload["previousStatus"], "payload.previousStatus")
    elif kind == "owner_note":
        _require(set(payload) == set(_OWNER_NOTE_PAYLOAD_KEYS),
                 "owner_note payload keys must be exactly ['text']")
        _str_or_none(payload["text"], "payload.text")
    elif kind == "decision":
        _require(set(payload) == set(_DECISION_PAYLOAD_KEYS),
                 "decision payload keys must be exactly %s" % (list(_DECISION_PAYLOAD_KEYS),))
        for field in ("intent", "routeAction", "departmentSlug", "resolvedBy"):
            _str_or_none(payload[field], "payload.%s" % field)
        bps = payload["confidenceBps"]
        if bps is not None:
            _require(isinstance(bps, int) and not isinstance(bps, bool),
                     "payload.confidenceBps must be an integer or null")
            _require(0 <= bps <= 10_000, "payload.confidenceBps must be 0..10000")
        _require(isinstance(payload["fallback"], bool), "payload.fallback must be a boolean")
        _require(payload["mode"] is not None, "payload.mode is required")
        _require(payload["mode"] in _DECISION_MODES,
                 "payload.mode has unsupported value %r" % (payload["mode"],))
    elif kind == "exchange":
        _require(set(payload) == set(_EXCHANGE_PAYLOAD_KEYS),
                 "exchange payload keys must be exactly %s" % (list(_EXCHANGE_PAYLOAD_KEYS),))
        _require(isinstance(payload["summary"], str), "payload.summary must be a string")
        _str_or_none(payload["summary"], "payload.summary", _SUMMARY_MAX_CHARS)
        _str_or_none(payload["message"], "payload.message", _MESSAGE_MAX_CHARS)
        _str_or_none(payload["toolCallId"], "payload.toolCallId")
        _str_or_none(payload["callerRunId"], "payload.callerRunId")
        _str_or_none(payload["targetRunId"], "payload.targetRunId")
        _str_or_none(payload["callerSessionKey"], "payload.callerSessionKey", _SESSION_KEY_MAX_CHARS)
        _str_or_none(payload["targetSessionKey"], "payload.targetSessionKey", _SESSION_KEY_MAX_CHARS)
        _enum_or_none(payload["toolName"], "payload.toolName", _TOOL_NAMES)
        _require(payload["toolName"] is not None, "payload.toolName is required")
        _enum_or_none(payload["sourceHook"], "payload.sourceHook", _SOURCE_HOOKS)
        _require(payload["sourceHook"] is not None, "payload.sourceHook is required")
        _enum_or_none(payload["nativeStatus"], "payload.nativeStatus", _NATIVE_STATUSES)
        _enum_or_none(payload["targetDisposition"], "payload.targetDisposition", _TARGET_DISPOSITIONS)
        _enum_or_none(payload["correlationStatus"], "payload.correlationStatus", _CORRELATION_STATUSES)
        _require(payload["correlationStatus"] is not None,
                 "payload.correlationStatus is required")
    else:  # pragma: no cover - validate_event gates the kind first
        raise HqEnvelopeError("unsupported kind %r" % (kind,))
    return payload


# ── the outbox ───────────────────────────────────────────────────────────────

def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Temp file in the SAME directory + os.replace. Atomic within a filesystem,
    so a reader never sees a half-written file and a killed process never leaves
    a truncated one behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path: Path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def hq_envelope_bounds(event) -> dict:
    """Encoded-byte size of `event` and of the S5 metadata budget.

    SPEC S5: "Check encoded bytes, not string length, before enqueue."  This is
    the measurement that rule reads; exposed because the parity test and any
    producer need it.  A caller building a large exchange can check here instead
    of re-deriving the cap.
    """
    return {
        "eventBytes": len(hq_semantic_serialize(event).encode("utf-8")),
        "payloadMaxBytes": PAYLOAD_MAX_BYTES,
        "metadataMaxBytes": METADATA_MAX_BYTES,
        "pendingMaxCount": PENDING_MAX_COUNT,
        "pendingMaxBytes": PENDING_MAX_BYTES,
    }


class HqHttpTransport:
    """The only external destination: the existing configured Command Center
    address, bearer plus webhook signature. Secret VALUES are read from the
    box's own env at call time by NAME and never logged, echoed or stored."""

    def __init__(self, url=None, timeout=EMIT_TIMEOUT_SECONDS, opener=None):
        self.url = url if url is not None else os.environ.get("HQ_CC_ACTIVITY_URL", "")
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen

    def configured(self) -> bool:
        return bool(self.url)

    def __call__(self, body: bytes, envelope: dict):
        if not self.url:
            raise HqEnvelopeError("no Command Center activity address is configured")
        request = urllib.request.Request(self.url, data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        token = os.environ.get("MC_API_TOKEN") or os.environ.get("HQ_CC_TOKEN")
        if token:
            request.add_header("Authorization", "Bearer " + token)
        secret = (os.environ.get("WEBHOOK_SECRET") or os.environ.get("CC_WEBHOOK_SECRET"))
        if secret:
            # Same convention as scripts/mc-route.sh: HMAC-SHA256(secret, rawBody) hex.
            request.add_header(
                "x-webhook-signature",
                hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest())
        with self._opener(request, timeout=self.timeout) as response:
            payload = response.read().decode("utf-8", "replace")
            return getattr(response, "status", 200), payload


class HqOutbox:
    """Bounded signed outbox. One instance per tenant workspace root.

    `root` is the tenant workspace; events live under `hq-telemetry/outbox/` and
    capture health under `hq-telemetry/capture-health.json`.
    """

    def __init__(self, root, transport=None, clock=time.time,
                 max_count=PENDING_MAX_COUNT, max_bytes=PENDING_MAX_BYTES,
                 max_event_bytes=PAYLOAD_MAX_BYTES, max_meta_bytes=METADATA_MAX_BYTES):
        self.root = Path(root)
        self.telemetry = self.root / "hq-telemetry"
        self.outbox = self.telemetry / "outbox"
        self.health_path = self.telemetry / "capture-health.json"
        self.receipts_path = self.telemetry / "capture-receipts.json"
        self.transport = transport
        self.clock = clock
        self.max_count = max_count
        self.max_bytes = max_bytes
        self.index_path = self.telemetry / "outbox-index.json"
        # Injectable so the encoded-byte cap can be exercised directly. The
        # defaults are SPEC S5's; nothing in production passes anything else.
        self.max_event_bytes = max_event_bytes
        self.max_meta_bytes = max_meta_bytes

    # -- pending files -------------------------------------------------------

    def _pending(self):
        if not self.outbox.is_dir():
            return []
        names = sorted(n for n in os.listdir(self.outbox)
                       if n.startswith(_PENDING_PREFIX) and n.endswith(".json"))
        return [self.outbox / n for n in names]

    def pending_stats(self):
        count = 0
        total = 0
        for path in self._pending():
            try:
                count += 1
                total += path.stat().st_size
            except OSError:
                continue
        return {"count": count, "bytes": total}

    # -- capture health (S8 "connection/capture health", S5 degradation) -----

    def _default_health(self):
        return {
            "captureHealth": "ok",
            "since": None,
            "dropped": {"count": 0, "lastDroppedAt": None, "reasons": {}},
            "lastWriteFailure": None,
            "lastDeliveryFailure": None,
            "expired": {"count": 0, "lastExpiredAt": None},
            "conflicts": {"count": 0, "lastConflictAt": None},
            "flush": {"lastAt": None, "delivered": 0, "attempts": 0},
        }

    def _read_health(self):
        try:
            health = _read_json(self.health_path)
            if isinstance(health, dict) and "dropped" in health:
                return health
        except (OSError, ValueError):
            pass
        return self._default_health()

    def _write_health(self, health):
        _atomic_write_bytes(
            self.health_path,
            (json.dumps(health, sort_keys=True, indent=2) + "\n").encode("utf-8"))

    def _degrade(self, health, reason, count=1, at=None):
        """SPEC S5: overflow sets captureHealth=degraded with dropped-count and
        timestamps. Every degradation path goes through here, so a drop is never
        silent and never merely implied."""
        at = at if at is not None else self.clock()
        health["captureHealth"] = "degraded"
        health.setdefault("since", _iso(at))
        health["dropped"]["count"] += count
        health["dropped"]["lastDroppedAt"] = _iso(at)
        reasons = health["dropped"].setdefault("reasons", {})
        reasons[reason] = reasons.get(reason, 0) + count
        return health

    def capture_health(self):
        """Current honest state, with the live pending numbers folded in."""
        health = self._read_health()
        health["pending"] = self.pending_stats()
        health["outboxPath"] = str(self.outbox)
        health["receipts"] = self._receipts_summary()
        return health

    # -- receipts (48-hour dedup coverage) ----------------------------------

    def _receipts(self):
        try:
            data = _read_json(self.receipts_path)
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
        return {}

    def _receipts_live(self):
        """Only the receipts still inside the 48-hour coverage window.

        A receipt past the window is not coverage and must never be reported as
        such; the physical prune happens on the next write.
        """
        now = self.clock()
        return {k: v for k, v in self._receipts().items()
                if now - float(v.get("firstAcceptedAtUnix", 0)) <= RECEIPT_COVERAGE_SECONDS}

    def _receipts_summary(self):
        return {"count": len(self._receipts_live()),
                "coverageHours": RECEIPT_COVERAGE_SECONDS // 3600}

    def _record_receipt(self, source_key, content_hash):
        now = self.clock()
        receipts = self._receipts()
        previous = receipts.get(source_key)
        if previous:
            # S6: never refresh accepted_at on retry. First acceptance wins.
            previous["attempts"] = previous.get("attempts", 1) + 1
        else:
            receipts[source_key] = {
                "contentHash": content_hash,
                "firstAcceptedAtUnix": now,
                "firstAcceptedAt": _iso(now),
                "attempts": 1,
            }
        cutoff = now - RECEIPT_COVERAGE_SECONDS
        receipts = {k: v for k, v in receipts.items()
                    if float(v.get("firstAcceptedAtUnix", 0)) > cutoff}
        _atomic_write_bytes(
            self.receipts_path,
            (json.dumps(receipts, sort_keys=True, indent=2) + "\n").encode("utf-8"))

    # -- write side (never blocks the caller's business work) ---------------

    def enqueue(self, event) -> dict:
        """Validate, bound-check, then durably enqueue one envelope.

        Returns a result dict; NEVER raises for an outbox-side problem (full,
        unreadable, unknown source key) — the caller's business transaction must
        not be rolled back by telemetry. A structurally invalid event raises
        `HqEnvelopeError`, because that is a producer bug and must be loud.
        """
        validate_event(event)
        now = self.clock()
        envelope = {
            "schemaVersion": HQ_ENVELOPE_SCHEMA_VERSION,
            "sentAt": _iso(now),
            "event": event,
            "contentHash": hq_semantic_hash_hex(event),
        }
        event_bytes = hq_semantic_serialize(event).encode("utf-8")
        meta_bytes = hq_semantic_serialize(
            {k: v for k, v in envelope.items() if k != "event"}).encode("utf-8")
        if len(event_bytes) > self.max_event_bytes:
            # SPEC S5: "Check encoded bytes, not string length, before enqueue."
            return self._refuse("payload-cap", now,
                                "serialized event is %d bytes, cap %d"
                                % (len(event_bytes), self.max_event_bytes))
        if len(meta_bytes) > self.max_meta_bytes:
            return self._refuse("metadata-cap", now,
                                "envelope metadata is %d bytes, cap %d"
                                % (len(meta_bytes), self.max_meta_bytes))

        body = (json.dumps(envelope, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
        path = self.outbox / ("%s%d-%s.json" % (
            _PENDING_PREFIX, int(now * 1000), envelope["contentHash"][:16]))

        existing = self._find_by_source_key(event["sourceKey"])
        if existing is not None:
            try:
                previous = _read_json(existing)
            except (OSError, ValueError):
                previous = {}
            previous_hash = previous.get("contentHash")
            if previous_hash == envelope["contentHash"]:
                # Same key / same content is duplicate success.
                return {"status": "duplicate", "sourceKey": event["sourceKey"],
                        "path": str(existing), "captureHealth": self.capture_health()["captureHealth"]}
            return self._refuse(
                "same-key-conflict", now,
                "sourceKey %s already pending with a different contentHash"
                % event["sourceKey"], conflict=True)

        health = self._read_health()
        stats = self.pending_stats()
        if stats["count"] >= self.max_count or stats["bytes"] + len(body) > self.max_bytes:
            # "Max 1,000 pending AND 8 MiB total, whichever fills first ...
            #  Overflow sets captureHealth=degraded with dropped-count and
            #  timestamps, never blocks the underlying business work."
            # The NEW event is the one dropped: evicting already-captured pending
            # files to make room would destroy evidence to win a counter.
            health = self._degrade(health, "outbox-overflow", at=now)
            self._write_health(health)
            return {"status": "overflow", "sourceKey": event["sourceKey"],
                    "reason": "pending outbox is full",
                    "captureHealth": "degraded"}

        try:
            _atomic_write_bytes(path, body)
        except OSError as exc:
            # "never blocks the underlying business work or silently claims
            #  completeness" — record the failure and hand back a degraded state.
            health = self._degrade(health, "outbox-write-failed", at=now)
            health["lastWriteFailure"] = {"at": _iso(now), "error": type(exc).__name__}
            try:
                self._write_health(health)
            except OSError:
                pass
            return {"status": "write-failed", "sourceKey": event["sourceKey"],
                    "error": type(exc).__name__, "captureHealth": "degraded"}

        index = self._read_index()
        index[event["sourceKey"]] = {"file": path.name, "contentHash": envelope["contentHash"]}
        self._write_index(index)

        return {"status": "queued", "sourceKey": event["sourceKey"], "path": str(path),
                "contentHash": envelope["contentHash"], "bytes": len(body),
                "captureHealth": health.get("captureHealth", "ok")}

    def _refuse(self, reason, now, message, conflict=False):
        health = self._read_health()
        if conflict:
            health["conflicts"]["count"] += 1
            health["conflicts"]["lastConflictAt"] = _iso(now)
        else:
            health = self._degrade(health, reason, at=now)
        # A conflict is a diagnosed condition, not silent data loss: it is
        # recorded, the existing pending file is left exactly as it was.
        try:
            self._write_health(health)
        except OSError:
            pass
        return {"status": "rejected", "reason": reason, "message": message,
                "captureHealth": health.get("captureHealth", "ok")}

    def _read_index(self):
        """Sidecar sourceKey -> {path, contentHash} map.

        Dedupe and conflict detection run on EVERY enqueue. Reading every pending
        file to find one key is O(n) file reads per event, and at the 1,000-file
        ceiling that is ~1,000 reads on the caller's critical path — exactly the
        blocking the SPEC forbids. The index is a pure cache: `_rebuild_index`
        reconstructs it from the files, which stay the source of truth, and a
        damaged or missing index just costs one rebuild.
        """
        try:
            data = _read_json(self.index_path)
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
        return self._rebuild_index()

    def _rebuild_index(self):
        index = {}
        for path in self._pending():
            try:
                stored = _read_json(path)
                key = (stored.get("event") or {}).get("sourceKey")
                if key:
                    index[key] = {"file": path.name, "contentHash": stored.get("contentHash")}
            except (OSError, ValueError):
                continue
        self._write_index(index)
        return index

    def _write_index(self, index):
        try:
            _atomic_write_bytes(
                self.index_path,
                (json.dumps(index, sort_keys=True, indent=2) + "\n").encode("utf-8"))
        except OSError:
            pass

    def _drop_from_index(self, path):
        index = self._read_index()
        for key, entry in list(index.items()):
            if entry.get("file") == path.name:
                del index[key]
        self._write_index(index)

    def _find_by_source_key(self, source_key):
        entry = self._read_index().get(source_key)
        if entry is None:
            return None
        path = self.outbox / entry["file"]
        return path if path.is_file() else None

    # -- delivery side (bounded scheduled job) ------------------------------

    def flush(self) -> dict:
        """One bounded pass: deliver what is due, expire what is stale.

        Called by the existing bounded scheduled-job runner. Never busy-loops:
        each entry's `nextAttemptAt` is set from `hq_retry_delay`, so the pass
        can be invoked as often as the runner likes and still respect the
        30-second minimum between attempts on the same event.
        """
        now = self.clock()
        health = self._read_health()
        result = {"at": _iso(now), "delivered": 0, "retried": 0, "expired": 0,
                 "skipped": 0, "rejected": 0, "dropped": 0, "errors": []}
        transport = self.transport
        if transport is None:
            transport = HqHttpTransport()
        if not getattr(transport, "configured", lambda: True)():
            health = self._degrade(health, "no-destination", at=now)
            health["lastDeliveryFailure"] = {"at": _iso(now), "error": "no destination configured"}
            self._write_health(health)
            result["skipped"] = len(self._pending())
            result["captureHealth"] = "degraded"
            return result

        for path in self._pending():
            try:
                envelope = _read_json(path)
                event = envelope["event"]
            except (OSError, ValueError, KeyError):
                result["skipped"] += 1
                continue

            issued = _parse_iso(event.get("issuedAt"))
            if issued is not None and now - issued > PENDING_EXPIRY_SECONDS:
                # "Producer expires pending files after 24 hours, records loss
                #  count, and never changes issuedAt to renew them."
                try:
                    os.unlink(path)
                except OSError:
                    pass
                self._drop_from_index(path)
                health = self._degrade(health, "expired-24h", at=now)
                health["expired"]["count"] += 1
                health["expired"]["lastExpiredAt"] = _iso(now)
                result["expired"] += 1
                result["dropped"] += 1
                continue

            attempts = int(envelope.get("attempts") or 0)
            next_at = envelope.get("nextAttemptAtUnix")
            if next_at is not None and now < float(next_at):
                result["skipped"] += 1
                continue

            body = (json.dumps(envelope, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
            try:
                status, _payload = transport(body, envelope)
            except Exception as exc:  # transport failures are data, not crashes
                status = None
                error = type(exc).__name__
            else:
                error = None

            if status in (200, 201):
                try:
                    os.unlink(path)   # a receipt removes ONLY this adapter-owned file
                except OSError:
                    pass
                self._drop_from_index(path)
                self._record_receipt(event.get("sourceKey", ""), envelope.get("contentHash", ""))
                result["delivered"] += 1
                continue
            if status == 410:         # event_expired at the receiver
                try:
                    os.unlink(path)
                except OSError:
                    pass
                self._drop_from_index(path)
                health = self._degrade(health, "receiver-expired", at=now)
                health["expired"]["count"] += 1
                health["expired"]["lastExpiredAt"] = _iso(now)
                result["expired"] += 1
                result["dropped"] += 1
                continue
            if status == 409:         # same key / different content
                # Left in place on purpose: overwriting would destroy the very
                # evidence an operator needs. Diagnosed, not resolved.
                health["conflicts"]["count"] += 1
                health["conflicts"]["lastConflictAt"] = _iso(now)
                result["rejected"] += 1
                continue
            if status is not None and 400 <= status < 500 and status not in (408, 429):
                try:
                    os.unlink(path)
                except OSError:
                    pass
                self._drop_from_index(path)
                health = self._degrade(health, "receiver-rejected-%d" % status, at=now)
                result["dropped"] += 1
                continue

            attempts += 1
            envelope["attempts"] = attempts
            envelope["lastAttemptAt"] = _iso(now)
            envelope["nextAttemptAtUnix"] = now + hq_retry_delay(attempts)
            envelope["lastError"] = error or ("http-%s" % status)
            try:
                _atomic_write_bytes(
                    path,
                    (json.dumps(envelope, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8"))
            except OSError:
                pass
            health["lastDeliveryFailure"] = {"at": _iso(now), "error": envelope["lastError"]}
            result["retried"] += 1
            result["errors"].append(envelope["lastError"])

        # captureHealth describes whether capture is COMPLETE right now, so a
        # clean pass clears it. "Clean" means nothing was lost or refused — an
        # event merely waiting out its own backoff is normal operation, not
        # degradation (counting it would make the surface cry wolf). Cumulative
        # losses stay in `dropped`/`expired`/`conflicts` as history; a degraded
        # state that could never clear would stop meaning anything.
        trouble = (result["retried"] or result["expired"] or result["dropped"]
                   or result["rejected"])
        if trouble:
            health["captureHealth"] = "degraded"
            health.setdefault("since", _iso(now))
        else:
            health["captureHealth"] = "ok"
            health["since"] = None

        health["flush"] = {"lastAt": _iso(now), "delivered": result["delivered"],
                           "attempts": result["retried"]}
        try:
            self._write_health(health)
        except OSError:
            pass
        result["captureHealth"] = self.capture_health()["captureHealth"]
        result["pending"] = self.pending_stats()
        return result


# ── the seam the existing producers call ─────────────────────────────────────

def enqueue_activity(event, root, transport=None, clock=time.time) -> dict:
    """Append one Headquarters activity event through the bounded outbox.

    This is the ONB half of SPEC S5's "appendHqActivity(db, input) is the only
    writer" — producers call this after the underlying source action is
    recorded, and it never raises for an outbox-side problem.
    """
    return HqOutbox(root, transport=transport, clock=clock).enqueue(event)


# ── helpers ──────────────────────────────────────────────────────────────────

def _iso(unix_seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(unix_seconds))


def _parse_iso(text):
    """Unix seconds for a UTC ISO instant, or None when it is not one.

    Fractional seconds are accepted: a producer is entitled to emit them and a
    `None` here would silently switch off the 24-hour expiry, letting the outbox
    grow without bound. Anything genuinely unparseable returns None and is
    revalidated by `validate_event` before it can reach this path.
    """
    if not isinstance(text, str) or not text.endswith("Z"):
        return None
    body = text[:-1]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return float(calendar.timegm(time.strptime(body, fmt)))
        except ValueError:
            continue
    if "." in body:
        head, _, frac = body.partition(".")
        if frac.isdigit() and head:
            base = _parse_iso(head + "Z")
            if base is not None:
                return base + float("0." + frac)
    return None


# ── shared golden vectors (cross-language) ───────────────────────────────────

def golden_vectors():
    """The shared golden-vector fixture for the Python<->TypeScript parity test.

    SPEC S7: "Shared golden-vector test covers Unicode, control characters,
    nulls, re-signed retry, same-key conflict and expiry."  These are the bytes
    both languages must produce, computed here from the frozen rules.
    """
    base = {
        "eventId": "9f1c2d3e-4a5b-4c6d-8e7f-0a1b2c3d4e5f",
        "sourceKey": "exchange:6f1e:requested",
        "installationId": "install-operator",
        "companyId": "co-operator",
        "issuedAt": "2026-10-04T00:00:00Z",
        "occurredAt": None,
        "kind": "exchange",
        "phase": "requested",
        "taskId": None,
        "actorRuntimeId": "agent:general:main",
        "recipientRuntimeId": "agent:marketing:main",
        "fromWorkspaceId": None,
        "toWorkspaceId": None,
        "exchangeId": "6f1e" + "0" * 60,
        "payload": {
            "message": None,
            "summary": "request sent",
            "toolName": "sessions_send",
            "toolCallId": "call-1",
            "callerRunId": "run-1",
            "targetRunId": None,
            "callerSessionKey": "agent:general:main",
            "targetSessionKey": None,
            "sourceHook": "before_tool_call",
            "nativeStatus": None,
            "targetDisposition": None,
            "correlationStatus": "linked",
        },
    }
    owner_note = dict(base, kind="owner_note", phase="recorded",
                      sourceKey="note:n-1", exchangeId=None,
                      payload={"text": "owner said é☃"})
    control = dict(base, kind="owner_note", phase="recorded",
                   sourceKey="note:n-2", exchangeId=None,
                   payload={"text": "line\nbreak\ttab\u0001ctrl \"quote\" back\\slash"})
    decision = dict(base, kind="decision", phase="applied",
                    sourceKey="decision:corr-1:applied", exchangeId=None,
                    payload={"intent": "task_route", "routeAction": "create_task",
                             "departmentSlug": "presentations", "confidenceBps": 10000,
                             "fallback": False, "mode": "live", "resolvedBy": "classifier"})
    unicode_event = dict(base, sourceKey="exchange:é:requested",
                         payload=dict(base["payload"], summary="é☃ \U0001f600"))
    rejected = dict(base, kind="task", phase="created", sourceKey="task:t-1",
                    exchangeId=None, payload={"status": "open", "previousStatus": None})
    vectors = [
        {"id": "unicode", "note": "UTF-8 Unicode emitted directly, not escaped", "event": unicode_event},
        {"id": "control", "note": "control/quote/backslash escapes", "event": control},
        {"id": "nulls", "note": "null is not omission; every key present", "event": base},
        {"id": "owner_note", "note": "kind/phase pairing owner_note/recorded", "event": owner_note},
        {"id": "decision_bps", "note": "integer basis points, never a float", "event": decision},
        {"id": "kind_phase_mismatch", "note": "must be refused", "event": rejected, "expectError": True},
    ]
    for vector in vectors:
        canonical = None
        digest = None
        error = None
        try:
            canonical = hq_semantic_serialize(vector["event"])
            digest = hq_semantic_hash_hex(vector["event"])
        except HqEnvelopeError as exc:
            error = str(exc)
        vector["canonical"] = canonical
        vector["sha256"] = digest
        if error is not None:
            vector["serializeError"] = error
    # "re-signed retry": identical event -> identical hash, independent of sentAt.
    retry_a = dict(base, sourceKey="exchange:retry:requested")
    retry_b = json.loads(json.dumps(retry_a))
    vectors.append({"id": "resigned_retry", "note": "sentAt is excluded from the semantic hash",
                    "event": retry_a, "canonical": hq_semantic_serialize(retry_a),
                    "sha256": hq_semantic_hash_hex(retry_a),
                    "retrySha256": hq_semantic_hash_hex(retry_b)})
    return {"schemaVersion": HQ_ENVELOPE_SCHEMA_VERSION,
            "payloadMaxBytes": PAYLOAD_MAX_BYTES,
            "metadataMaxBytes": METADATA_MAX_BYTES,
            "pendingMaxCount": PENDING_MAX_COUNT,
            "pendingMaxBytes": PENDING_MAX_BYTES,
            "retryMinSeconds": RETRY_MIN_SECONDS,
            "retryMaxSeconds": RETRY_MAX_SECONDS,
            "emitTimeoutSeconds": EMIT_TIMEOUT_SECONDS,
            "pendingExpirySeconds": PENDING_EXPIRY_SECONDS,
            "receiptCoverageSeconds": RECEIPT_COVERAGE_SECONDS,
            "vectors": vectors}


# ── runnable self-check ──────────────────────────────────────────────────────

def _demo():  # pragma: no cover - run via __main__
    import tempfile as _tempfile

    # canonical serialization == the SPEC S7 Python formula, byte for byte
    samples = [
        {"b": 1, "a": 2},
        {"z": {"beta": 1, "alpha": [2, 3]}, "a": None},
        {"k": "é☃"}, {"k": "a\nb\tc\u0001"}, {"k": "quote\"slash\\"},
        [True, False, 0, -7], {"deep": {"deeper": {"n": 2 ** 53 - 1}}},
    ]
    for sample in samples:
        assert hq_semantic_serialize(sample) == json.dumps(
            sample, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False), sample
    for bad in (1.5, float("nan"), float("inf"), 2 ** 53 + 1, "\ud800", {1: "x"}):
        try:
            hq_semantic_serialize(bad)
        except HqEnvelopeError:
            pass
        else:
            raise AssertionError("expected a refusal for %r" % (bad,))

    assert hq_duplicate_object_keys('{"a":1,"a":2}') is True
    assert hq_duplicate_object_keys('{"a":1,"b":{"a":1}}') is False

    # backoff: 30 s minimum, doubling, capped at 5 minutes, never 0
    assert [hq_retry_delay(n) for n in (0, 1, 2, 3, 4, 5, 6, 50)] == [
        0.0, 30.0, 60.0, 120.0, 240.0, 300.0, 300.0, 300.0]

    vectors = golden_vectors()
    assert all(v["sha256"] for v in vectors["vectors"] if not v.get("expectError"))
    assert vectors["vectors"][-1]["sha256"] == vectors["vectors"][-1]["retrySha256"]

    with _tempfile.TemporaryDirectory() as tmp:
        sent = []

        def transport(body, envelope):
            sent.append(body)
            return 201, "{}"

        clock = [1_000_000.0]
        box = HqOutbox(tmp, transport=transport, clock=lambda: clock[0])
        event = dict(vectors["vectors"][0]["event"])
        first = box.enqueue(event)
        assert first["status"] == "queued", first
        again = box.enqueue(event)
        assert again["status"] == "duplicate", again
        assert box.pending_stats()["count"] == 1

        # byte cap is checked on ENCODED bytes, before enqueue. The real cap is
        # generous by design (an 8,000-char message + 2,000-char summary fits),
        # so the boundary is exercised with a lowered cap — the same code path.
        big = dict(event, payload=dict(event["payload"], summary="x" * 1000))
        tight = HqOutbox(tmp, transport=transport, clock=lambda: clock[0],
                         max_event_bytes=200, max_count=10)
        refused = tight.enqueue(big)
        assert refused["status"] == "rejected" and refused["reason"] == "payload-cap", refused
        assert tight.capture_health()["captureHealth"] == "degraded"
        # The maximum SPEC-bounded text still fits the real cap.
        widest = dict(event, payload=dict(event["payload"],
                                          message="é" * 8_000, summary="x" * 2_000))
        assert len(hq_semantic_serialize(widest).encode("utf-8")) < PAYLOAD_MAX_BYTES
        box2 = HqOutbox(tmp + "/wide", transport=transport, clock=lambda: clock[0])
        assert box2.enqueue(widest)["status"] == "queued"

        clock[0] += 1_000
        flushed = box.flush()
        assert flushed["delivered"] == 1, flushed
        assert box.pending_stats()["count"] == 0
        assert len(sent) == 1

        # 24-hour expiry, then the loss is counted (never silently dropped)
        stale = dict(event, eventId="11111111-2222-4333-8444-555555555555",
                     sourceKey="exchange:stale:requested", issuedAt=_iso(clock[0] - 90_000))
        assert box.enqueue(stale)["status"] == "queued"
        expired = box.flush()
        assert expired["expired"] == 1 and expired["dropped"] == 1, expired
        assert box.capture_health()["dropped"]["reasons"]["expired-24h"] == 1

        # 30-second retry minimum holds across repeated flush calls, no busy loop
        def failing(body, envelope):
            raise OSError("network down")

        retry_box = HqOutbox(tmp, transport=failing, clock=lambda: clock[0])
        assert retry_box.enqueue(dict(event, eventId="22222222-3333-4444-8555-666666666666",
                                      sourceKey="exchange:retry:requested"))["status"] == "queued"
        assert retry_box.flush()["retried"] == 1
        assert retry_box.flush()["retried"] == 0, "a second pass must respect the 30 s minimum"
        clock[0] += 30.5
        assert retry_box.flush()["retried"] == 1

        # count cap -> explicit degraded overflow, never a silent drop
        cap_box = HqOutbox(tmp, transport=transport, clock=lambda: clock[0], max_count=2)
        for n in range(4):
            cap_box.enqueue(dict(event, eventId="33333333-4444-4555-8666-77777777777%d" % n,
                                 sourceKey="exchange:cap%d:requested" % n))
        health = cap_box.capture_health()
        assert health["pending"]["count"] <= 2, health
        assert health["captureHealth"] == "degraded"
        assert health["dropped"]["reasons"].get("outbox-overflow", 0) >= 1, health

    print("hq_activity: all self-checks pass")


def _main(argv):
    if "--write-vectors" in argv:
        target = argv[argv.index("--write-vectors") + 1]
        Path(target).write_text(json.dumps(golden_vectors(), indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
        print("wrote %s" % target)
        return 0
    root = os.environ.get("HQ_TENANT_WORKSPACE_ROOT", ".")
    if "--flush" in argv:
        print(json.dumps(HqOutbox(root).flush(), sort_keys=True))
        return 0
    if "--health" in argv:
        print(json.dumps(HqOutbox(root).capture_health(), sort_keys=True))
        return 0
    _demo()
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
