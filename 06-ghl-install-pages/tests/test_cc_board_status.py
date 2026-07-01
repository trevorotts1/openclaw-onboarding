# test_cc_board_status.py — Area-6 Kanban status-transition producer (cc_board.update_status).
# No network: the transport (_post_json) is monkeypatched so URL/method/body
# construction is asserted directly, and every guard is checked for fail-soft.
from __future__ import annotations

import os
import sys

import pytest

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import cc_board  # noqa: E402

BASE = "https://demo.zerohumanworkforce.com"
ENV = {"MISSION_CONTROL_URL": BASE}


class TestStatusGuards:
    def test_no_url_returns_false(self):
        assert cc_board.update_status("t1", "in_progress", env={}) is False

    def test_empty_task_id_returns_false(self):
        assert cc_board.update_status("", "review", env=ENV) is False

    def test_invalid_status_returns_false(self):
        assert cc_board.update_status("t1", "not-a-status", env=ENV) is False

    def test_template_without_id_placeholder_returns_false(self):
        env = dict(ENV, CC_STATUS_PATH_TEMPLATE="/api/tasks/status")
        assert cc_board.update_status("t1", "blocked", env=env) is False

    def test_never_raises_on_bad_input(self):
        # None task id / None status must not raise (fail-soft contract).
        assert cc_board.update_status(None, None, env=ENV) is False  # type: ignore[arg-type]

    def test_update_status_done_is_blocked(self):
        # DoD5 parity (v16.2.15): update_status must mirror move_task's 'done'
        # hard-block — no caller can bypass the QC gate via this legacy path.
        assert cc_board.update_status("t1", "done", env=ENV) is False


class TestStateMapping:
    def test_dispatch_state_table_matches_area6_spec(self):
        assert cc_board.DISPATCH_STATE_TO_CC == {
            "dispatched": "in_progress",
            "building": "in_progress",
            "verified": "review",
            "FAILED": "blocked",
        }

    def test_every_mapped_status_is_a_valid_enum_value(self):
        for st in cc_board.DISPATCH_STATE_TO_CC.values():
            assert st in cc_board._CC_STATUS_VALUES

    def test_update_status_for_state_unknown_is_noop(self):
        # 'backlog' (the ingest-created column) and unknown states are no-ops.
        assert cc_board.update_status_for_state("t1", "backlog", env=ENV) is False
        assert cc_board.update_status_for_state("t1", "nope", env=ENV) is False


class TestTransport:
    """Assert the request the producer would send, without any network."""

    def _capture(self, monkeypatch):
        captured = {}

        def fake_post(url, payload, cfg, method="POST"):
            captured["url"] = url
            captured["payload"] = payload
            captured["method"] = method
            return 200, {"ok": True}

        monkeypatch.setattr(cc_board, "_post_json", fake_post)
        return captured

    def test_default_route_and_body(self, monkeypatch):
        captured = self._capture(monkeypatch)
        ok = cc_board.update_status("task-123", "in_progress", note="building", env=ENV)
        assert ok is True
        assert captured["url"] == f"{BASE}/api/tasks/task-123/status"
        assert captured["method"] == "POST"
        assert captured["payload"] == {"status": "in_progress", "note": "building"}

    def test_method_and_path_overridable(self, monkeypatch):
        captured = self._capture(monkeypatch)
        env = dict(ENV, CC_STATUS_METHOD="patch", CC_STATUS_PATH_TEMPLATE="/api/tasks/{id}")
        ok = cc_board.update_status("abc", "review", env=env)
        assert ok is True
        assert captured["url"] == f"{BASE}/api/tasks/abc"
        assert captured["method"] == "PATCH"  # upper-cased
        assert captured["payload"] == {"status": "review"}

    def test_non_2xx_returns_false(self, monkeypatch):
        monkeypatch.setattr(cc_board, "_post_json", lambda *a, **k: (404, {"error": "no route"}))
        assert cc_board.update_status("abc", "blocked", env=ENV) is False

    def test_network_error_fail_soft(self, monkeypatch):
        import urllib.error

        def boom(*a, **k):
            raise urllib.error.URLError("down")

        monkeypatch.setattr(cc_board, "_post_json", boom)
        # Must swallow and return False, never raise.
        # Use 'blocked' (not 'done' — done is hard-blocked before the network call).
        assert cc_board.update_status("abc", "blocked", env=ENV) is False

    def test_full_lifecycle_backlog_to_review(self, monkeypatch):
        """backlog -> in_progress -> review, the way v2_dispatcher drives it."""
        sent = []

        def fake_post(url, payload, cfg, method="POST"):
            sent.append(payload["status"])
            return 200, {"ok": True}

        monkeypatch.setattr(cc_board, "_post_json", fake_post)
        assert cc_board.update_status_for_state("tid", "dispatched", env=ENV) is True
        assert cc_board.update_status_for_state("tid", "building", env=ENV) is True
        assert cc_board.update_status_for_state("tid", "verified", env=ENV) is True
        assert sent == ["in_progress", "in_progress", "review"]


def test_status_selftest_exits_zero():
    assert cc_board._status_selftest() == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
