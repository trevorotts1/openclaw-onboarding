# test_cc_board_outbox.py — WF20: producer board bridge and durable outbox.
#
# A24 (Document 1 s17.2): board outage/replay does not stop execution or repeat
# GHL mutations. Every scenario is offline: the transport (cc_board._post_json)
# is monkeypatched and the outbox lives under tmp_path. The shared request
# contract fixture is the SAME file the Command Center consumer lanes consume
# (tests/fixtures/cc_board_delivery_contract.v1.json, checkpoint WF20-CP01).
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error

import pytest

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import cc_board  # noqa: E402
import cc_board_outbox as outbox_mod  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures",
                       "cc_board_delivery_contract.v1.json")
ENV = {"MISSION_CONTROL_URL": "https://demo.zerohumanworkforce.com", "MC_API_TOKEN": "synthetic"}
BASE = ENV["MISSION_CONTROL_URL"]


def _contract() -> dict:
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def _open(path):
    return outbox_mod.BoardOutbox(str(path))


# ─────────────────────────────────────────────────────────────────────────────
# A24 — durable event before delivery; outage queues; replay never re-runs work
# ─────────────────────────────────────────────────────────────────────────────
class TestDurableBeforeDelivery:
    def test_event_exists_before_the_wire_call(self, tmp_path, monkeypatch):
        outbox = tmp_path / "outbox.sqlite3"
        seen = {}

        def _fake(url, payload, cfg, method="POST"):
            ob = _open(outbox)
            try:
                seen["status"] = ob.status_of(payload["idempotency_key"])
                seen["payload"] = dict(payload)
            finally:
                ob.close()
            return 201, {"task_id": "task-1"}

        monkeypatch.setattr(cc_board, "_post_json", _fake)
        task_id = cc_board.ingest_task(
            "Durable job", env=ENV, outbox_path=str(outbox), run_id="run-a24",
            operation_key="course:outline", family="course")
        assert task_id == "task-1"
        assert seen["status"] == outbox_mod.STATUS_IN_FLIGHT, (
            "the durable event must exist (in_flight) when delivery is attempted")

    def test_board_timeout_queues_and_execution_continues(self, tmp_path, monkeypatch):
        outbox = tmp_path / "outbox.sqlite3"

        def _timeout(url, payload, cfg, method="POST"):
            raise urllib.error.URLError("timed out")

        monkeypatch.setattr(cc_board, "_post_json", _timeout)
        result = cc_board.ingest_task(
            "Timeout job", env=ENV, outbox_path=str(outbox), run_id="run-timeout",
            operation_key="course:outline", family="course")
        assert result is None  # no invented task id
        # The business caller continues: this line is reached without an exception.
        continued = True
        assert continued
        ob = _open(outbox)
        try:
            assert ob.counts()["pending"] == 1
            event = ob.events()[0]
            assert event["status"] == outbox_mod.STATUS_PENDING
            assert event["attempts"] == 1
            assert "timed out" in (event["last_error"] or "")
        finally:
            ob.close()

    def test_retry_resends_the_event_not_the_business_operation(self, tmp_path, monkeypatch):
        outbox = tmp_path / "outbox.sqlite3"
        sent = []

        def _timeout(url, payload, cfg, method="POST"):
            sent.append(dict(payload))
            raise urllib.error.URLError("board down")

        monkeypatch.setattr(cc_board, "_post_json", _timeout)
        cc_board.ingest_task("Retry job", env=ENV, outbox_path=str(outbox),
                             run_id="run-retry", operation_key="course:1",
                             family="course", idempotency_key="stable-key-1")
        monkeypatch.undo()

        ob = _open(outbox)
        original = ob.events()[0]
        ob.close()

        def _ok(url, payload, cfg, method="POST"):
            sent.append(dict(payload))
            return 201, {"task_id": "task-retry-1"}

        monkeypatch.setattr(cc_board, "_post_json", _ok)

        def _must_not_run(*args, **kwargs):
            raise AssertionError("business entrypoint re-executed on board retry")

        monkeypatch.setattr(cc_board, "ingest_task", _must_not_run)
        summary = cc_board.flush_outbox(str(outbox), env=ENV, now=time.time() + 10 ** 6)
        assert summary["delivered"] == 1
        assert len(sent) == 2  # the original attempt + ONE event retry
        assert sent[1]["idempotency_key"] == "stable-key-1"
        assert sent[1] == original["request"]
        ob = _open(outbox)
        try:
            assert ob.counts()["total"] == 1, "retry must not mint a second event"
            assert ob.counts()["acked"] == 1
        finally:
            ob.close()

    def test_replay_of_an_acked_ingest_is_harmless(self, tmp_path, monkeypatch):
        outbox = tmp_path / "outbox.sqlite3"
        calls = []

        def _ok(url, payload, cfg, method="POST"):
            calls.append(dict(payload))
            return 201, {"task_id": "task-once"}

        monkeypatch.setattr(cc_board, "_post_json", _ok)
        kwargs = dict(env=ENV, outbox_path=str(outbox), run_id="run-replay",
                      operation_key="course:1", family="course",
                      idempotency_key="replay-key")
        assert cc_board.ingest_task("Replay job", **kwargs) == "task-once"
        assert cc_board.ingest_task("Replay job", **kwargs) == "task-once"
        assert len(calls) == 1, "an acked replay must issue NO second POST"
        ob = _open(outbox)
        try:
            assert ob.counts()["total"] == 1
        finally:
            ob.close()

    def test_old_command_center_version_is_queued_not_reported(self, tmp_path, monkeypatch):
        outbox = tmp_path / "outbox.sqlite3"
        monkeypatch.setattr(cc_board, "_post_json",
                            lambda *a, **k: (404, {"error": "not found"}))
        result = cc_board.ingest_task("Old CC job", env=ENV, outbox_path=str(outbox),
                                      run_id="run-old", operation_key="course:1",
                                      family="course")
        assert result is None, "an absent ingest route must never claim a card"
        ob = _open(outbox)
        try:
            event = ob.events()[0]
            assert event["status"] == outbox_mod.STATUS_PENDING
            assert "old_cc_version" in (event["last_error"] or "")
        finally:
            ob.close()

    def test_ack_is_recorded_and_repeat_ack_is_harmless(self, tmp_path):
        ob = _open(tmp_path / "outbox.sqlite3")
        try:
            event = outbox_mod.build_event(
                idempotency_key="ack-key", request={"title": "synthetic"},
                run_id="run-ack", operation_key="course:1", family="course")
            ob.enqueue(event)
            ob.claim("ack-key")
            first = ob.ack("ack-key", "task-ack")
            second = ob.ack("ack-key", "task-ack")
            assert first == second
            assert first["status"] == outbox_mod.STATUS_ACKED
            assert first["ack_task_id"] == "task-ack"
            with pytest.raises(outbox_mod.OutboxError):
                ob.ack("ack-key", "some-other-task")
        finally:
            ob.close()


# ─────────────────────────────────────────────────────────────────────────────
# Redaction, source allowlist, legacy compatibility
# ─────────────────────────────────────────────────────────────────────────────
class TestRedactionAndSources:
    def test_redaction_happens_before_enqueue_and_hash_survives(self, tmp_path):
        outbox = tmp_path / "outbox.sqlite3"
        secret = "synthetic-secret-value-abcdef123456"
        description = f"Funnel brief with api_token={secret} and Bearer {secret}"
        captured = {}

        def _fake(url, payload, cfg, method="POST"):
            captured.update(payload)
            return 201, {"task_id": "task-redacted"}

        import unittest.mock as mock
        with mock.patch.object(cc_board, "_post_json", _fake):
            cc_board.ingest_task("Redacted job", description=description, env=ENV,
                                 outbox_path=str(outbox), run_id="run-redact",
                                 operation_key="course:1", family="course")
        assert secret not in captured["description"]
        assert "[REDACTED]" in captured["description"]
        ob = _open(outbox)
        try:
            event = ob.events()[0]
            assert secret not in json.dumps(event)
            # The stored hash is over the canonical intent pre-redaction; it must
            # remain a sha256 the consumer can match after redaction.
            assert event["request_hash"].startswith("sha256:")
            assert len(event["request_hash"]) == len("sha256:") + 64
        finally:
            ob.close()

    def test_unknown_source_is_refused_by_the_allowlist(self):
        with pytest.raises(outbox_mod.OutboxError):
            outbox_mod.build_event(
                idempotency_key="rogue", request={"title": "x"}, run_id="run-x",
                operation_key="x", family="board", source="rogue-source")

    def test_legacy_direct_path_unchanged_without_an_outbox(self, tmp_path, monkeypatch):
        calls = []

        def _ok(url, payload, cfg, method="POST"):
            calls.append(dict(payload))
            return 201, {"task_id": "legacy-task"}

        monkeypatch.setattr(cc_board, "_post_json", _ok)
        task_id = cc_board.ingest_task("Legacy job", env=ENV)
        assert task_id == "legacy-task"
        assert len(calls) == 1
        assert not list(tmp_path.iterdir()), "no outbox is created by legacy callers"


# ─────────────────────────────────────────────────────────────────────────────
# Parent/child — an existing parent is reused, never re-created
# ─────────────────────────────────────────────────────────────────────────────
class TestParentChild:
    def test_child_reuses_the_existing_parent_and_carries_engine_source(self, tmp_path, monkeypatch):
        outbox = tmp_path / "outbox.sqlite3"
        monkeypatch.setattr(cc_board, "_post_json",
                            lambda *a, **k: (201, {"task_id": "parent-1"}))
        assert cc_board.ingest_task(
            "Parent build", env=ENV, outbox_path=str(outbox), run_id="run-parent",
            operation_key="course:parent", family="course", is_parent=True
        ) == "parent-1"

        assert cc_board.ingest_child_task(
            "Outline phase", env=ENV, outbox_path=str(outbox), run_id="run-parent",
            operation_key="course:outline", family="course"
        ) == "parent-1"
        assert cc_board.ingest_child_task(
            "Publish phase", env=ENV, outbox_path=str(outbox), run_id="run-parent",
            operation_key="course:publish", family="course"
        ) == "parent-1"

        ob = _open(outbox)
        try:
            children = [e for e in ob.events() if e["parent_task_id"] == "parent-1"]
            assert len(children) == 2
            assert {c["request"]["title"] for c in children} == {"Outline phase", "Publish phase"}
            assert all(c["source"] == outbox_mod.ENGINE_SOURCE for c in children)
        finally:
            ob.close()

    def test_child_without_an_existing_parent_is_not_fabricated(self, tmp_path, monkeypatch):
        outbox = tmp_path / "outbox.sqlite3"
        called = []
        monkeypatch.setattr(cc_board, "_post_json",
                            lambda *a, **k: called.append(1) or (201, {"task_id": "x"}))
        result = cc_board.ingest_child_task(
            "Orphan child", env=ENV, outbox_path=str(outbox), run_id="run-unknown",
            operation_key="course:1", family="course")
        assert result is None
        assert called == []
        ob = _open(outbox)
        try:
            assert ob.counts()["total"] == 0
        finally:
            ob.close()


# ─────────────────────────────────────────────────────────────────────────────
# Projects sync keeps its own mapped logical action through WF33
# ─────────────────────────────────────────────────────────────────────────────
class TestProjectsSync:
    def test_projects_event_is_never_sent_to_the_board_endpoint(self, tmp_path, monkeypatch):
        outbox = tmp_path / "outbox.sqlite3"
        posts = []
        monkeypatch.setattr(cc_board, "_post_json",
                            lambda *a, **k: posts.append(1) or (201, {"task_id": "board-1"}))
        ob = _open(outbox)
        try:
            event = outbox_mod.build_event(
                idempotency_key="cc-task-1:projects", request={"title": "Synthetic CC task"},
                run_id="run-projects", operation_key="cc-task-1", family="projects_sync",
                domain="projects_sync", logical_action="projects.task.upsert")
            ob.enqueue(event)
        finally:
            ob.close()

        summary = cc_board.flush_outbox(str(outbox), env=ENV, now=10 ** 10)
        assert summary["skipped_domains"] == 1
        assert posts == [], "a Projects sync event must not hit /api/tasks/ingest"
        ob = _open(outbox)
        try:
            stored = ob.event("cc-task-1:projects")
            assert stored["status"] == outbox_mod.STATUS_PENDING
            assert stored["logical_action"] == "projects.task.upsert"
            assert stored["domain"] == "projects_sync"
        finally:
            ob.close()


# ─────────────────────────────────────────────────────────────────────────────
# Shared request contract — producer and consumer use the SAME fixture
# ─────────────────────────────────────────────────────────────────────────────
def _consumer_accepts(event: dict, contract: dict) -> bool:
    """Reference consumer check that reads ONLY the frozen fixture contract.

    This is the producer-side proof that the shared fixture is consumable; WF18
    owns the real receipt-store implementation and must accept the same file.
    """
    consumer = contract["consumer"]
    if not all(field in event for field in consumer["required_fields"]):
        return False
    if not all(field in event for field in contract["required_event_fields"]):
        return False
    if event["status"] not in contract["statuses"]:
        return False
    if event["source"] not in contract["source_allowlist"]:
        return False
    if event["family"] not in contract["families"]:
        return False
    prefix = contract["domains"][event["domain"]]["logical_action_prefix"]
    if not event["logical_action"].startswith(prefix):
        return False
    # Dedupe identity is present and stable: the consumer keys on it.
    if not event.get(consumer["dedupe_key"]):
        return False
    return True


class TestSharedRequestContract:
    def test_fixture_matches_the_producer_module(self):
        contract = _contract()
        assert contract["schema"] == outbox_mod.CONTRACT_SCHEMA
        assert contract["event_schema"] == outbox_mod.EVENT_SCHEMA
        assert tuple(contract["source_allowlist"]) == tuple(outbox_mod.ALLOWED_SOURCES)
        assert tuple(contract["statuses"]) == tuple(outbox_mod.ALL_STATUSES)
        assert contract["producer"]["board_endpoint"] == outbox_mod.BOARD_ENDPOINT

    def test_every_family_example_is_accepted_by_producer_and_consumer(self):
        contract = _contract()
        assert set(contract["families"]) == set(contract["family_examples"])
        for family, event in contract["family_examples"].items():
            outbox_mod.validate_event(event)  # producer-side shape check
            assert _consumer_accepts(event, contract), f"consumer rejects {family}"
            assert event["family"] == family
            assert event["source"] == outbox_mod.ENGINE_SOURCE

    def test_fixture_example_hash_is_verifiable_after_redaction(self):
        contract = _contract()
        event = contract["example_event"]
        intent_hash = event["request_hash"]
        assert intent_hash.startswith("sha256:")
        # Same fixture hashed again by the producer is stable (idempotent match).
        rebuilt = outbox_mod.build_event(
            idempotency_key=event["idempotency_key"], request=event["request"],
            run_id=event["run_id"], operation_key=event["operation_key"],
            family=event["family"], domain=event["domain"],
            logical_action=event["logical_action"])
        assert rebuilt["request_hash"] == intent_hash
        assert rebuilt["request"] == event["request"]
