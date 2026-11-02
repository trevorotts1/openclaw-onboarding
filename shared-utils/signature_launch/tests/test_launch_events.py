#!/usr/bin/env python3
"""CON-21: the launch event emitter posts to a (fake) CC and never fails a launch.

Free: stdlib only, local loopback fake CC, synthetic values, no real token.
Run: python3 -m pytest shared-utils/signature_launch/tests/test_launch_events.py -q
"""
import importlib.util
import json
import socket
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("launch_events", PKG / "launch_events.py")
le = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(le)

TOKEN = "synthetic-tenant-token"
LAUNCH = "bf-2026-11"


class _FakeCC:
    """Records every ingest POST; answers with a scripted status."""

    def __init__(self, status=200):
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                outer.requests.append({
                    "path": self.path,
                    "auth": self.headers.get("Authorization"),
                    "body": json.loads(self.rfile.read(n)),
                })
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *a):
                pass

        self.status = status
        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d" % self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def events(self):
        return [e for r in self.requests for e in r["body"]["events"]]


def _dead_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # nothing listens here: connection refused
    return "http://127.0.0.1:%d" % port


class LaunchEventsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tok = Path(self.tmp.name, "token")
        tok.write_text(TOKEN + "\n", encoding="utf-8")
        self.spool = Path(self.tmp.name, "spool")
        self.env = {"LAUNCH_EVENTS_SPOOL": str(self.spool), "LAUNCH_EVENTS_TOKEN_FILE": str(tok),
                    "LAUNCH_EVENTS_TIMEOUT": "2"}

    def _spooled(self):
        p = self.spool / le.SPOOL_FILE
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def test_posts_contract_shaped_event_with_token(self):
        cc = _FakeCC()
        self.addCleanup(cc.close)
        env = dict(self.env, COMMAND_CENTER_URL=cc.url)
        out = le.emit(83, LAUNCH, "dispatch", env=env)
        self.assertTrue(out["sent"] and not out["spooled"])
        req = cc.requests[0]
        self.assertEqual(req["path"], "/api/launch-runs/ingest")
        self.assertEqual(req["auth"], "Bearer " + TOKEN)
        ev = req["body"]["events"][0]
        self.assertEqual((ev["skill"], ev["launch_id"]), (83, LAUNCH))
        self.assertEqual((ev["event_type"], ev["stage"], ev["receipt_status"]),
                         ("stage_closed", "dispatch", "pass"))
        self.assertIn("closed_at", ev)
        self.assertEqual(ev["schema_version"], "1.0")
        self.assertEqual(len(ev["event_id"]), 36)
        self.assertEqual(self._spooled(), [])

    def test_one_run_per_launch_one_event_per_step(self):
        cc = _FakeCC()
        self.addCleanup(cc.close)
        env = dict(self.env, COMMAND_CENTER_URL=cc.url)
        for step in ("dispatch", "assemble", "checks"):
            le.emit(83, LAUNCH, step, env=env)
        le.emit(49, LAUNCH, {"event_type": "stage_blocked", "stage": "page_dispatch",
                             "failures": ["boom"]}, env=env)
        evs = cc.events()
        self.assertEqual([e["stage"] for e in evs], ["dispatch", "assemble", "checks", "page_dispatch"])
        self.assertEqual(len({e["event_id"] for e in evs}), 4)
        self.assertEqual(len({e["run_id"] for e in evs[:3]}), 1)
        self.assertNotEqual(evs[0]["run_id"], evs[3]["run_id"])  # skill 49 is its own run
        self.assertEqual(evs[3]["event_type"], "stage_blocked")
        self.assertIn("blocked_at", evs[3])

    def test_run_initialized_carries_host_shape(self):
        ev = le.build_event(83, LAUNCH, {"event_type": "run_initialized"}, env={})
        self.assertEqual(ev["host_shape"], "fleet-mac")

    def test_network_error_spools_and_never_raises(self):
        env = dict(self.env, COMMAND_CENTER_URL=_dead_url())
        out = le.emit(83, LAUNCH, "dispatch", env=env)
        self.assertEqual((out["sent"], out["spooled"]), (False, True))
        self.assertEqual([e["stage"] for e in self._spooled()], ["dispatch"])

    def test_raising_transport_spools(self):
        def boom(*a):
            raise OSError("down")
        out = le.emit(83, LAUNCH, "assemble", env=dict(self.env, COMMAND_CENTER_URL="http://x"), post=boom)
        self.assertTrue(out["spooled"])

    def test_http_500_spools(self):
        cc = _FakeCC(status=500)
        self.addCleanup(cc.close)
        out = le.emit(83, LAUNCH, "dispatch", env=dict(self.env, COMMAND_CENTER_URL=cc.url))
        self.assertTrue(out["spooled"] and not out["sent"])

    def test_unconfigured_cc_spools(self):
        out = le.emit(83, LAUNCH, "dispatch", env=self.env)
        self.assertTrue(out["spooled"])

    def test_bad_input_never_raises(self):
        for bad in (None, 7, {"stage": object()}):
            le.emit("not-a-skill", LAUNCH, bad, env=self.env)
        le.emit(83, LAUNCH, "dispatch", env={"LAUNCH_EVENTS_SPOOL": "/dev/null/x"})  # unwritable spool

    def test_backlog_replays_in_order_when_cc_returns(self):
        le.emit(83, LAUNCH, "dispatch", env=dict(self.env, COMMAND_CENTER_URL=_dead_url()))
        le.emit(83, LAUNCH, "pieces", env=dict(self.env, COMMAND_CENTER_URL=_dead_url()))
        self.assertEqual(len(self._spooled()), 2)
        cc = _FakeCC()
        self.addCleanup(cc.close)
        le.emit(83, LAUNCH, "assemble", env=dict(self.env, COMMAND_CENTER_URL=cc.url))
        self.assertEqual([e["stage"] for e in cc.events()], ["dispatch", "pieces", "assemble"])
        self.assertEqual(self._spooled(), [])

    def test_backlog_is_sent_before_a_new_event(self):
        env = dict(self.env, COMMAND_CENTER_URL="http://cc.test")

        def down(*a):
            raise OSError("down")
        le.emit(83, LAUNCH, {"event_type": "run_initialized"}, env=env, post=down)
        out = le.emit(83, LAUNCH, "dispatch", env=env, post=down)  # still down
        self.assertEqual((out["sent"], out["spooled"]), (False, True))
        self.assertEqual([e["event_type"] for e in self._spooled()], ["run_initialized", "stage_closed"])
        seen = []

        def up(url, token, events, timeout):
            seen.extend(e["event_type"] for e in events)
            return 200
        out = le.emit(83, LAUNCH, "assemble", env=env, post=up)
        self.assertEqual(seen, ["run_initialized", "stage_closed", "stage_closed"])
        self.assertTrue(out["sent"] and not out["spooled"])
        self.assertEqual(self._spooled(), [])
        self.assertFalse((self.spool / le.SPOOL_FILE).exists())

    def test_422_is_not_retried_forever(self):
        cc = _FakeCC(status=422)
        self.addCleanup(cc.close)
        out = le.emit(83, LAUNCH, "dispatch", env=dict(self.env, COMMAND_CENTER_URL=cc.url))
        self.assertFalse(out["sent"] or out["spooled"])
        self.assertEqual(self._spooled(), [])
        self.assertTrue((self.spool / le.REJECTED_FILE).exists())

    def test_token_never_written_to_spool(self):
        le.emit(83, LAUNCH, "dispatch", env=dict(self.env, COMMAND_CENTER_URL=_dead_url()))
        self.assertNotIn(TOKEN, (self.spool / le.SPOOL_FILE).read_text())


class LaunchCardTest(unittest.TestCase):
    """Skill 49 launch mode lands one board card per launch, fail-soft."""

    def _mc_board(self):
        spec = importlib.util.spec_from_file_location(
            "mc_board_under_test", PKG.parents[1] / "49-signature-funnel/scripts/mc_board.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod  # dataclasses resolve their module by name
        spec.loader.exec_module(mod)
        return mod

    def test_card_opened_in_progress_and_idempotent(self):
        mb = self._mc_board()
        calls = []

        def fake(method, url, payload, cfg):
            calls.append((method, url, payload))
            if url.endswith("/api/tasks/ingest"):
                return 201, {"task_id": "T1"}
            return 200, {"status": "backlog"}

        mb._request = fake
        env = {"COMMAND_CENTER_URL": "https://cc.example.test"}
        with tempfile.TemporaryDirectory() as run:
            self.assertEqual(mb.launch_card(run, LAUNCH, offer_name="Elevation", env=env), "T1")
            ingest = [c for c in calls if c[1].endswith("/api/tasks/ingest")]
            self.assertEqual(len(ingest), 1)
            self.assertIn("Elevation", ingest[0][2]["title"])
            self.assertIn("in_progress", [c[2].get("status") for c in calls if c[2]])
            self.assertEqual(mb.launch_card(run, LAUNCH, env=env), "T1")  # reuse, no 2nd card
            self.assertEqual(len([c for c in calls if c[1].endswith("/api/tasks/ingest")]), 1)

    def test_card_never_raises_when_disabled_or_down(self):
        mb = self._mc_board()
        with tempfile.TemporaryDirectory() as run:
            self.assertIsNone(mb.launch_card(run, LAUNCH, env={}))
            self.assertIsNone(mb.launch_card(run, "", env={"COMMAND_CENTER_URL": "http://x"}))
            self.assertIsNone(mb.launch_card(run, LAUNCH, env={"COMMAND_CENTER_URL": _dead_url()}))


if __name__ == "__main__":
    unittest.main()
