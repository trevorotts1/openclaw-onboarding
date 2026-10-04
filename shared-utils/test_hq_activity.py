"""Focused behaviour tests for the bounded signed outbox (`hq_activity.py`).

Covers the parts SPEC S5/S7 state as acceptance for this unit that the module's
own `_demo()` self-check does not: atomicity under a killed writer, the real
byte/count ceilings at their boundary, silent-drop impossibility, the 24-hour
producer expiry, 48-hour receipt coverage, and the fact that this adapter reads
or writes NO provider setting.

Test style follows this repo's existing shared-utils tests: load the module by
path (shared-utils is not an installed package) and exercise it directly.
Offline only — a fake transport; no network, no client box, no live message.
"""
import importlib.util
import json
import os

import pytest

_MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hq_activity.py")
_spec = importlib.util.spec_from_file_location("hq_activity_under_test", _MOD)
hq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hq)


def _event(**overrides):
    """A minimal valid exchange event, matching the frozen S7 shape."""
    event = {
        "eventId": "2b0f5e2a-3d2e-4f4a-8f9b-3a2d4c5b6a70",
        "sourceKey": "exchange:" + "a" * 64 + ":requested",
        "installationId": "install-1",
        "companyId": "co-1",
        "issuedAt": "2026-10-04T00:00:00Z",
        "occurredAt": None,
        "kind": "exchange",
        "phase": "requested",
        "taskId": None,
        "actorRuntimeId": "agent:general:main",
        "recipientRuntimeId": None,
        "fromWorkspaceId": None,
        "toWorkspaceId": None,
        "exchangeId": "a" * 64,
        "payload": {
            "message": None, "summary": "request sent",
            "toolName": "sessions_send", "toolCallId": "call-1",
            "callerRunId": "run-1", "targetRunId": None,
            "callerSessionKey": None, "targetSessionKey": None,
            "sourceHook": "before_tool_call", "nativeStatus": None,
            "targetDisposition": None, "correlationStatus": "linked",
        },
    }
    event.update(overrides)
    return event


@pytest.fixture
def clock():
    """Deterministic clock; time never advances unless a test says so."""
    return [1_700_000_000.0]


@pytest.fixture
def box(tmp_path, clock):
    delivered = []

    def transport(body, envelope):
        delivered.append(json.loads(body.decode("utf-8")))
        return 201, "{}"

    instance = hq.HqOutbox(tmp_path, transport=transport, clock=lambda: clock[0])
    instance.delivered = delivered
    return instance


def test_module_self_check_passes(capsys):
    hq._demo()
    assert "all self-checks pass" in capsys.readouterr().out


# ── atomicity ────────────────────────────────────────────────────────────────

def test_a_killed_writer_leaves_no_half_written_file(box, tmp_path, monkeypatch):
    """S5: "one JSON file per event, atomic rename". A crash between the temp
    write and the rename must leave the outbox readable — never a truncated
    event that later parses as broken and gets silently re-sent or dropped."""
    real_replace = os.replace

    def dying_replace(src, dst):
        raise KeyboardInterrupt("killed mid-write")

    monkeypatch.setattr(os, "replace", dying_replace)
    with pytest.raises(KeyboardInterrupt):
        box.enqueue(_event())
    monkeypatch.setattr(os, "replace", real_replace)

    assert list(tmp_path.glob("hq-telemetry/outbox/*.json")) == []
    # The temp file was cleaned up too — no litter that a later listing sees.
    assert list(tmp_path.glob("hq-telemetry/outbox/.*")) == []
    assert box.pending_stats() == {"count": 0, "bytes": 0}


def test_pending_file_is_valid_json_at_every_observable_moment(box):
    assert box.enqueue(_event())["status"] == "queued"
    paths = list((box.root / "hq-telemetry" / "outbox").glob("*.json"))
    assert len(paths) == 1
    envelope = json.loads(paths[0].read_text(encoding="utf-8"))
    assert envelope["schemaVersion"] == 1
    assert envelope["event"]["sourceKey"] == _event()["sourceKey"]
    assert envelope["contentHash"] == hq.hq_semantic_hash_hex(_event())


# ── byte and count caps, at the boundary ─────────────────────────────────────

def test_byte_cap_is_measured_on_encoded_bytes_not_string_length(tmp_path, clock):
    """S5: "Check encoded bytes, not string length, before enqueue." A 2-byte
    character costs 2 bytes; measuring characters would under-count by half."""
    box = hq.HqOutbox(tmp_path, transport=lambda b, e: (201, "{}"), clock=lambda: clock[0])
    event = _event(payload=dict(_event()["payload"], summary="é" * 500))
    encoded = len(hq.hq_semantic_serialize(event).encode("utf-8"))
    chars = len(hq.hq_semantic_serialize(event))
    assert encoded > chars, "the fixture must actually contain multi-byte characters"
    strict = hq.HqOutbox(tmp_path / "strict", transport=lambda b, e: (201, "{}"),
                         clock=lambda: clock[0], max_event_bytes=chars, )
    assert encoded > chars
    assert strict.enqueue(event)["status"] == "rejected"      # encoded bytes, not chars


def test_the_declared_maximum_text_still_fits_the_real_cap(box):
    """S5's discriminator: an 8,000-character message plus a 2,000-character
    summary must fit inside 128 KiB even with JSON escapes."""
    widest = _event(payload=dict(
        _event()["payload"],
        message="é" * 8_000,         # worst case: 2 bytes per char
        summary="x" * 2_000))
    measured = len(hq.hq_semantic_serialize(widest).encode("utf-8"))
    assert measured <= hq.PAYLOAD_MAX_BYTES
    assert box.enqueue(widest)["status"] == "queued"


def test_count_cap_degrades_explicitly_and_never_returns_silent_success(tmp_path, clock):
    """S5: "Max 1,000 pending AND 8 MiB total, whichever fills first ... Overflow
    sets captureHealth=degraded with dropped-count and timestamps, never blocks
    the underlying business work or silently claims completeness." """
    box = hq.HqOutbox(tmp_path, transport=lambda b, e: (201, "{}"),
                      clock=lambda: clock[0], max_count=3)
    statuses = [box.enqueue(_event(eventId="%08d-0000-4000-8000-000000000000" % n,
                                   sourceKey="exchange:%s:requested" % ("%064d" % n)))
                for n in range(5)]
    assert [s["status"] for s in statuses[:3]] == ["queued"] * 3
    assert statuses[3]["status"] == "overflow"
    assert statuses[3]["reason"] == "pending outbox is full"

    health = box.capture_health()
    assert health["captureHealth"] == "degraded"
    assert health["dropped"]["count"] >= 2
    assert health["dropped"]["reasons"]["outbox-overflow"] >= 2
    assert health["dropped"]["lastDroppedAt"] is not None
    # A dropped event is NEVER reported as queued — the caller can always tell.
    assert all(s["status"] != "queued" for s in statuses[3:])
    # And nothing already captured was sacrificed to make room.
    assert box.pending_stats()["count"] == 3


def test_overflow_does_not_raise_so_business_work_is_never_blocked(tmp_path, clock):
    box = hq.HqOutbox(tmp_path, transport=lambda b, e: (201, "{}"),
                      clock=lambda: clock[0], max_count=1)
    box.enqueue(_event())
    result = box.enqueue(_event(eventId="33333333-4444-4555-8666-777777777777",
                                sourceKey="exchange:b:requested"))
    assert result["status"] == "overflow"      # returned, not raised


# ── semantics: duplicate, conflict, expiry ───────────────────────────────────

def test_same_key_same_content_is_duplicate_success_not_a_second_file(box):
    assert box.enqueue(_event())["status"] == "queued"
    again = box.enqueue(_event())
    assert again["status"] == "duplicate"
    assert box.pending_stats()["count"] == 1


def test_same_key_different_content_is_a_recorded_conflict_never_an_overwrite(box):
    """S5: "Same key/same content is duplicate success; same key/different
    content is conflict recorded diagnostically, not overwrite." """
    assert box.enqueue(_event())["status"] == "queued"
    before = sorted(p.read_bytes() for p in (box.root / "hq-telemetry" / "outbox").glob("*.json"))
    result = box.enqueue(_event(payload=dict(_event()["payload"], summary="different")))
    after = sorted(p.read_bytes() for p in (box.root / "hq-telemetry" / "outbox").glob("*.json"))
    assert result["status"] == "rejected" and result["reason"] == "same-key-conflict"
    assert before == after, "the pending file was overwritten"
    assert box.capture_health()["conflicts"]["count"] == 1


def test_pending_expires_after_24_hours_and_the_loss_is_counted(tmp_path, clock):
    """S7: "Producer expires pending files after 24 hours, records loss count,
    and never changes issuedAt to renew them." """
    box = hq.HqOutbox(tmp_path, transport=lambda b, e: (201, "{}"), clock=lambda: clock[0])
    stale = _event(issuedAt=hq._iso(clock[0] - 90_000))     # 25 hours old
    assert box.enqueue(stale)["status"] == "queued"
    result = box.flush()

    assert result["expired"] == 1 and result["dropped"] == 1
    assert box.pending_stats() == {"count": 0, "bytes": 0}
    health = box.capture_health()
    assert health["expired"]["count"] == 1
    assert health["dropped"]["reasons"]["expired-24h"] == 1
    assert health["captureHealth"] == "degraded"


def test_an_event_just_inside_the_24_hour_horizon_is_still_sent(tmp_path, clock):
    """The known-good control for the expiry test: the same code path, one
    second inside the horizon, must deliver rather than expire."""
    sent = []
    box = hq.HqOutbox(tmp_path, transport=lambda b, e: (sent.append(b) or (201, "{}")),
                      clock=lambda: clock[0])
    box.enqueue(_event(issuedAt=hq._iso(clock[0] - (24 * 3600 - 1))))
    result = box.flush()
    assert result["expired"] == 0 and result["delivered"] == 1
    assert len(sent) == 1


def test_a_retry_never_rewrites_issued_at(box, clock):
    """S7: "never changes issuedAt to renew them." """
    box.transport = lambda b, e: (_ for _ in ()).throw(OSError("down"))
    original = _event(issuedAt=hq._iso(clock[0]))
    box.enqueue(original)
    clock[0] += 60
    box.flush()
    stored = json.loads(next((box.root / "hq-telemetry" / "outbox").glob("*.json"))
                        .read_text(encoding="utf-8"))
    assert stored["event"]["issuedAt"] == original["issuedAt"]


# ── retry schedule ───────────────────────────────────────────────────────────

def test_retry_is_a_30_second_minimum_doubling_to_a_5_minute_ceiling():
    assert [hq.hq_retry_delay(n) for n in (0, 1, 2, 3, 4, 5, 6, 99)] == [
        0.0, 30.0, 60.0, 120.0, 240.0, 300.0, 300.0, 300.0]


def test_repeated_flushes_do_not_busy_loop(tmp_path, clock):
    """S5: "30-second retry minimum, exponential delay to 5 minutes, no busy
    loop." A runner may call flush as often as it likes; the same event must not
    be re-attempted until its own delay has elapsed."""
    attempts = []

    def failing(body, envelope):
        attempts.append(clock[0])
        raise OSError("network down")

    box = hq.HqOutbox(tmp_path, transport=failing, clock=lambda: clock[0])
    box.enqueue(_event())
    assert box.flush()["retried"] == 1
    for _ in range(5):                       # five immediate repeat calls
        assert box.flush()["retried"] == 0
    assert len(attempts) == 1
    clock[0] += 29.0
    assert box.flush()["retried"] == 0
    clock[0] += 1.5                          # now past 30 s
    assert box.flush()["retried"] == 1
    assert len(attempts) == 2


def test_emit_timeout_is_two_seconds():
    assert hq.HqHttpTransport().timeout == 2.0
    assert hq.EMIT_TIMEOUT_SECONDS == 2.0


# ── receipts: 48-hour coverage ───────────────────────────────────────────────

def test_an_accepted_receipt_removes_only_its_own_pending_file(box):
    first = _event()
    second = _event(eventId="44444444-5555-4666-8777-888888888888",
                    sourceKey="exchange:" + "b" * 64 + ":requested", exchangeId="b" * 64)
    box.enqueue(first)
    box.enqueue(second)
    assert box.pending_stats()["count"] == 2
    box.flush()                                    # both deliver
    assert box.pending_stats()["count"] == 0
    assert len(box.delivered) == 2


def test_receipts_cover_48_hours_and_survive_the_24_hour_retry_horizon(box, clock):
    """S6: retain receipts 48 hours after first acceptance, never refresh
    accepted_at on retry. S7 accepts only events issued within 24 hours, so any
    valid retry is still covered after the visible activity was pruned."""
    box.enqueue(_event())
    box.flush()
    receipts = box._receipts()
    key = _event()["sourceKey"]
    assert key in receipts
    first_accepted = receipts[key]["firstAcceptedAtUnix"]

    clock[0] += 25 * 3600                    # past the 24 h retry horizon
    box.enqueue(_event())
    box.flush()
    assert box._receipts()[key]["firstAcceptedAtUnix"] == first_accepted, \
        "accepted_at was refreshed on retry"

    clock[0] += 22 * 3600                    # 47 h after first acceptance
    assert key in box._receipts_live(), "a receipt inside 48 h must still cover"
    assert box._receipts()[key]["firstAcceptedAtUnix"] == first_accepted
    clock[0] += 2 * 3600                     # now past 48 h
    assert key not in box._receipts_live()
    assert box.capture_health()["receipts"]["count"] == 0
    # The next write physically prunes it — cleanup removes expired receipts
    # before evaluating capacity (S6).
    box.enqueue(_event(eventId="55555555-6666-4777-8888-999999999999",
                       sourceKey="exchange:" + "c" * 64 + ":requested", exchangeId="c" * 64))
    box.flush()
    assert key not in box._receipts()


def test_receipts_are_reported_against_the_frozen_48_hour_window(box):
    assert hq.RECEIPT_COVERAGE_SECONDS == 48 * 3600
    assert box.capture_health()["receipts"]["coverageHours"] == 48


# ── degradation is honest ────────────────────────────────────────────────────

def test_an_unwritable_outbox_reports_degraded_instead_of_dropping_silently(tmp_path, clock):
    """S5: "Overflow sets captureHealth=degraded ... never blocks the underlying
    business work or silently claims completeness." An unwritable outbox is the
    same class of failure and must surface the same way."""
    box = hq.HqOutbox(tmp_path, transport=lambda b, e: (201, "{}"), clock=lambda: clock[0])
    box.outbox.mkdir(parents=True)
    box.outbox.chmod(0o500)                  # read+execute, no write
    try:
        result = box.enqueue(_event())
    finally:
        box.outbox.chmod(0o700)
    if result["status"] == "queued":         # e.g. running as a user who ignores mode bits
        pytest.skip("filesystem permissions are not enforced for this user")
    assert result["status"] == "write-failed"
    assert result["captureHealth"] == "degraded"
    assert box.capture_health()["dropped"]["reasons"]["outbox-write-failed"] == 1


def test_a_missing_destination_degrades_and_keeps_the_event_queued(tmp_path, clock):
    """No destination configured must not delete pending work: the event is
    still there, and the health says degraded."""
    box = hq.HqOutbox(tmp_path, transport=hq.HqHttpTransport(url=""), clock=lambda: clock[0])
    box.enqueue(_event())
    result = box.flush()
    assert result["captureHealth"] == "degraded"
    assert box.pending_stats()["count"] == 1
    assert box.capture_health()["dropped"]["reasons"]["no-destination"] == 1


def test_a_clean_flush_reports_ok_again(box):
    box.enqueue(_event())
    assert box.flush()["captureHealth"] == "ok"
    assert box.capture_health()["captureHealth"] == "ok"


def test_enqueue_does_not_read_every_pending_file(tmp_path, clock):
    """Dedupe must not be O(n) file reads on the caller's critical path. At the
    1,000-file ceiling the naive scan is ~1,000 reads per event — the blocking
    SPEC S5 forbids. The sidecar index is a cache over the files, so a damaged
    index costs one rebuild, never a wrong answer."""
    reads = []
    real_read_json = hq._read_json

    def counting_read(path):
        reads.append(os.path.basename(str(path)))
        return real_read_json(path)

    box = hq.HqOutbox(tmp_path, transport=lambda b, e: (201, "{}"), clock=lambda: clock[0])
    for n in range(40):
        box.enqueue(_event(eventId="%08d-0000-4000-8000-000000000000" % n,
                           sourceKey="exchange:%064d:requested" % n,
                           exchangeId="%064d" % n))
    hq._read_json = counting_read
    try:
        box.enqueue(_event(eventId="%08d-0000-4000-8000-000000000000" % 99,
                           sourceKey="exchange:%064d:requested" % 99,
                           exchangeId="%064d" % 99))
    finally:
        hq._read_json = real_read_json
    assert len(reads) <= 3, "enqueue read %d files (pending files: %d)" % (len(reads), 41)


def test_a_corrupt_index_rebuilds_from_the_pending_files(tmp_path, clock):
    """The index is a cache; the pending files are the source of truth."""
    box = hq.HqOutbox(tmp_path, transport=lambda b, e: (201, "{}"), clock=lambda: clock[0])
    box.enqueue(_event())
    box.index_path.write_text("{ not json", encoding="utf-8")
    assert box.enqueue(_event())["status"] == "duplicate"
    assert box.pending_stats()["count"] == 1


def test_an_expired_entry_leaves_no_orphan_in_the_index(tmp_path, clock):
    """A key that is no longer pending must not read as pending — otherwise a
    later legitimate event under that key would be called a duplicate of a file
    that no longer exists and would never be sent."""
    box = hq.HqOutbox(tmp_path, transport=lambda b, e: (201, "{}"), clock=lambda: clock[0])
    key = _event()["sourceKey"]
    box.enqueue(_event(issuedAt=hq._iso(clock[0] - 90_000)))
    assert key in box._read_index()
    box.flush()                                   # expires it
    assert key not in box._read_index()
    fresh = dict(_event(), issuedAt=hq._iso(clock[0]))
    assert box.enqueue(fresh)["status"] == "queued", "a fresh event under an expired key must send"


def test_fractional_second_issued_at_still_expires(tmp_path, clock):
    """A producer emitting milliseconds must not silently disable the 24-hour
    bound by making the timestamp unparseable."""
    box = hq.HqOutbox(tmp_path, transport=lambda b, e: (201, "{}"), clock=lambda: clock[0])
    stamp = hq._iso(clock[0] - 90_000).replace("Z", ".250Z")
    assert hq._parse_iso(stamp) is not None, "a fractional-second instant must parse"
    box.enqueue(_event(issuedAt=stamp))
    assert box.flush()["expired"] == 1
    # And a fractional second inside the window is still delivered.
    box.enqueue(_event(eventId="66666666-7777-4888-8999-000000000000",
                       sourceKey="exchange:" + "d" * 64 + ":requested", exchangeId="d" * 64,
                       issuedAt=hq._iso(clock[0]).replace("Z", ".500Z")))
    assert box.flush()["delivered"] == 1


def test_health_is_json_serializable_for_the_snapshot_route(box):
    json.dumps(box.capture_health())


def test_waiting_out_backoff_is_not_called_degraded(tmp_path, clock):
    """A pass that only skipped events still inside their own backoff is normal
    operation. If it reported degraded, the surface would cry wolf on every
    quiet flush and an operator could not tell it from real loss."""
    box = hq.HqOutbox(tmp_path, transport=lambda b, e: (_ for _ in ()).throw(OSError("down")),
                      clock=lambda: clock[0])
    box.enqueue(_event())
    assert box.flush()["captureHealth"] == "degraded"     # the attempt really failed
    clock[0] += 1                                          # not yet due
    result = box.flush()
    assert result["skipped"] == 1 and result["retried"] == 0
    assert box.capture_health()["captureHealth"] == "ok", "backoff wait must not read as degradation"
    # The event itself is untouched and still pending — nothing was lost.
    assert box.pending_stats()["count"] == 1
    # And a real delivery afterwards clears it too.
    box.transport = lambda b, e: (201, "{}")
    clock[0] += 60
    assert box.flush()["delivered"] == 1
    assert box.capture_health()["captureHealth"] == "ok"


# ── the boundary this adapter must NOT cross ─────────────────────────────────

def test_no_provider_model_or_policy_value_is_read_or_written(tmp_path, monkeypatch):
    """This adapter alters no provider setting. Every env var it touches is
    named for the Command Center ingest; nothing model/provider/policy-shaped
    is read, and no config file is written outside the tenant workspace.

    The spy records reads made through `os.environ.get` by THIS module only;
    the interpreter and the `ssl` module read their own variables, which is not
    this adapter's doing and is filtered out by name.
    """
    touched = []
    real_getenv = os.environ.get
    module_file = hq.__file__

    def spying_getenv(key, *args):
        import sys as _sys
        frame = _sys._getframe(1)
        if frame.f_globals.get("__file__") == module_file:
            touched.append(key)
        return real_getenv(key, *args)

    monkeypatch.setattr(os.environ, "get", spying_getenv)
    box = hq.HqOutbox(tmp_path, transport=hq.HqHttpTransport(url="http://127.0.0.1:4000/api/hq/activity"),
                      clock=lambda: 1_700_000_000.0)
    box.enqueue(_event())
    box.flush()

    allowed = {"HQ_CC_ACTIVITY_URL", "MC_API_TOKEN", "HQ_CC_TOKEN",
               "WEBHOOK_SECRET", "CC_WEBHOOK_SECRET"}
    assert set(touched) <= allowed, "unexpected env read: %s" % sorted(set(touched) - allowed)
    for key in touched:
        assert not any(word in key.upper() for word in
                       ("PROVIDER", "MODEL", "OLLAMA", "OPENAI", "ANTHROPIC", "POLICY", "ROUTE"))
    # Everything written stayed inside the tenant workspace it was given.
    written = {p.relative_to(tmp_path).parts[0] for p in tmp_path.rglob("*") if p.is_file()}
    assert written == {"hq-telemetry"}


def test_no_network_is_reachable_without_a_configured_transport(box):
    """The default target is the existing configured Command Center address; an
    unset address must never silently fall through to a hardcoded host."""
    assert hq.HqOutbox(box.root).transport is None
    assert hq.HqHttpTransport(url="").configured() is False


def test_secrets_are_referenced_by_name_and_never_written_into_the_outbox(box, monkeypatch):
    monkeypatch.setenv("MC_API_TOKEN", "token-value-must-not-appear")
    monkeypatch.setenv("WEBHOOK_SECRET", "secret-value-must-not-appear")
    box.transport = hq.HqHttpTransport(url="http://127.0.0.1:9/x",
                                       opener=lambda req, timeout=None: _FakeResponse())
    box.enqueue(_event())
    box.flush()
    blob = b"".join(p.read_bytes() for p in (box.root / "hq-telemetry").rglob("*") if p.is_file())
    assert b"token-value-must-not-appear" not in blob
    assert b"secret-value-must-not-appear" not in blob


class _FakeResponse:
    status = 201

    def read(self):
        return b"{}"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_signature_header_uses_the_existing_webhook_convention(monkeypatch):
    """S5: "existing configured Command Center address, bearer plus webhook
    signature". Same HMAC convention as scripts/mc-route.sh —
    HMAC-SHA256(secret, rawBody) hex."""
    import hashlib
    import hmac as hmac_mod

    monkeypatch.setenv("MC_API_TOKEN", "tok")
    monkeypatch.setenv("WEBHOOK_SECRET", "sec")
    seen = {}

    def opener(request, timeout=None):
        seen["auth"] = request.get_header("Authorization")
        seen["sig"] = request.get_header("X-webhook-signature")
        seen["body"] = request.data
        return _FakeResponse()

    transport = hq.HqHttpTransport(url="http://127.0.0.1:9/x", opener=opener)
    transport(b'{"a":1}', {"event": {}})
    assert seen["auth"] == "Bearer tok"
    assert seen["sig"] == hmac_mod.new(b"sec", b'{"a":1}', hashlib.sha256).hexdigest()


# ── validation: the structural half of the S5 safety boundary ───────────────

@pytest.mark.parametrize("bad", [
    lambda: _event(zz=1),                                            # unknown key
    lambda: {k: v for k, v in _event().items() if k != "taskId"},    # missing key
    lambda: _event(kind="task", phase="replied"),                    # kind/phase mismatch
    lambda: _event(eventId="not-a-uuid"),
    lambda: _event(exchangeId="short"),
    lambda: _event(payload=dict(_event()["payload"], nativeStatus="invented")),
    lambda: _event(payload=dict(_event()["payload"], message="x" * 8_001)),
    lambda: _event(payload={k: v for k, v in _event()["payload"].items() if k != "summary"}),
])
def test_invalid_events_are_refused_loudly(bad):
    """A structurally invalid event is a producer bug: it raises, unlike an
    outbox-side failure which returns a degraded result."""
    with pytest.raises(hq.HqEnvelopeError):
        hq.validate_event(bad())


def test_a_float_confidence_is_refused_never_truncated():
    with pytest.raises(hq.HqEnvelopeError):
        hq.validate_event(_event(kind="decision", phase="applied", payload={
            "intent": None, "routeAction": None, "departmentSlug": None,
            "confidenceBps": 80.5, "fallback": False, "mode": "live", "resolvedBy": None,
        }))


def test_no_credentials_or_hidden_reasoning_can_ride_along():
    """S5: "provider payloads, hidden reasoning and credentials are excluded
    structurally." There is no field to put them in, so an unknown key is the
    only route — and that route is rejected."""
    for key in ("apiKey", "authorization", "llm_output", "reasoning", "prompt"):
        with pytest.raises(hq.HqEnvelopeError):
            hq.validate_event(_event(**{key: "leak"}))


# ── the vectors ──────────────────────────────────────────────────────────────

def test_golden_vectors_are_stable_and_self_consistent():
    vectors = hq.golden_vectors()
    by_id = {v["id"]: v for v in vectors["vectors"]}
    assert set(by_id) >= {"unicode", "control", "nulls", "resigned_retry"}
    # sentAt is excluded from the semantic hash: the retry hash equals the original.
    assert by_id["resigned_retry"]["sha256"] == by_id["resigned_retry"]["retrySha256"]
    # Hash the canonical bytes back and confirm they agree.
    import hashlib as _hashlib
    for vector in vectors["vectors"]:
        if vector.get("expectError"):
            continue
        assert _hashlib.sha256(vector["canonical"].encode("utf-8")).hexdigest() == vector["sha256"]


def test_the_canonical_serializer_matches_the_spec_python_formula():
    """SPEC S7 names the exact Python formula; the serializer must equal it."""
    samples = [
        {"b": 1, "a": 2}, {"z": {"beta": 1, "alpha": [2, 3]}, "a": None},
        {"k": "é☃"}, {"k": "a\nb\tc\u0001"}, {"k": 'quote"slash\\'},
        [True, False, 0, -7], {"n": 2 ** 53 - 1}, {}, [],
    ]
    for sample in samples:
        assert hq.hq_semantic_serialize(sample) == json.dumps(
            sample, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False)


@pytest.mark.parametrize("bad", [1.5, float("nan"), float("inf"), 2 ** 53 + 1, "\ud800"])
def test_the_canonical_serializer_refuses_what_spec_s7_refuses(bad):
    with pytest.raises(hq.HqEnvelopeError):
        hq.hq_semantic_serialize(bad)


def test_duplicate_keys_are_detected_before_hashing():
    assert hq.hq_duplicate_object_keys('{"a":1,"a":2}') is True
    assert hq.hq_duplicate_object_keys('{"a":1,"b":{"a":1}}') is False
    assert hq.hq_duplicate_object_keys('not json') is False


def test_envelope_bounds_reports_the_frozen_ceilings():
    bounds = hq.hq_envelope_bounds(_event())
    assert bounds["payloadMaxBytes"] == 128 * 1024
    assert bounds["metadataMaxBytes"] == 4 * 1024
    assert bounds["pendingMaxCount"] == 1_000
    assert bounds["pendingMaxBytes"] == 8 * 1024 * 1024
    assert bounds["eventBytes"] > 0
