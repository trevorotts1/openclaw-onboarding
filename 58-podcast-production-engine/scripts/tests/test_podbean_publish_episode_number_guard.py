#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - U034: episode-number server-side idempotency guard tests
#
# Mock e2e tests that drive the REAL shipped podbean_publish.sh script
# against a loopback-only HTTP mock. The mock serves as a fake Podbean API
# (broker + episodes endpoint). The test observes subprocess exit codes and
# stderr text to verify the guard logic.
#
# What this proves:
#   T1) Server count matches roster -> proceed (exit 0, "agrees with local roster" logged)
#   T2) Server count exceeds roster beyond delta -> refuse (exit 2, "EPISODE-NUMBER CONFLICT" logged)
#   T3) Server count exceeds roster within delta -> proceed (exit 0, "within tolerance" logged)
#   T4) Server count behind roster beyond delta -> refuse (exit 2, CONFLICT logged)
#   T5) Guard not supplied (no --roster-episode-count flag) -> no effect (exit 0, NO conflict)
#   T6) Non-integer --roster-episode-count -> rejected (non-zero exit, validation message)
#   T7) Non-integer --roster-episode-delta -> rejected (non-zero exit, validation message)
#   T8) Delta defaults to 0 when not supplied (match works, one-off mismatch blocks)
#
# Run:  python3 -m pytest /tmp/test_podbean_publish_episode_number_guard.py -v
# =============================================================================
"""Mock e2e tests for the U034 episode-number idempotency guard."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_SCRIPT = Path("/tmp/podbean_publish_test.sh")

FIXTURE_BROKER_TOKEN = "test-fixt-broker-not-real"
FIXTURE_ACCESS_TOKEN = "test-fixt-access-not-real"


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Handler(BaseHTTPRequestHandler):
    """HTTP handler that serves pre-configured routes from the mock server."""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length:
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return None
        return {}

    def _serve(self, method):
        body = self._read_body()
        self.server.requests.append({
            "path": self.path,
            "method": method,
            "body": body,
            "token": self.headers.get("X-Podbean-Broker-Token", ""),
        })
        queue = self.server.routes.get((self.path, method))
        if not queue and method == "GET":
            for (rp, rm), q in self.server.routes.items():
                if rm == "GET" and self.path.startswith(rp):
                    queue = q
                    break
        if not queue:
            self.send_response(404)
            p = b'{"ok":false}'
            self.send_header("Content-Length", str(len(p)))
            self.end_headers()
            self.wfile.write(p)
            return
        status, body_obj = queue[0] if len(queue) == 1 else queue.pop(0)
        if body_obj is None:
            self.close_connection = True
            return
        payload = json.dumps(body_obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        self._serve("POST")

    def do_GET(self):
        self._serve("GET")


class MockServer:
    """A loopback-only HTTP mock with programmable routes."""

    def __init__(self):
        self.port = _free_port()
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), _Handler)
        self.server.requests = []
        self.server.routes = {}
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.port}"

    def route(self, path, method, responses):
        self.server.routes[(path, method)] = list(responses)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class EpisodeNumberGuardTest(unittest.TestCase):
    BROKER_PATH = "/webhook/podbean-broker"
    EPISODES_PREFIX = "/api/episodes"

    def setUp(self):
        self.mock = MockServer()
        self.addCleanup(self.mock.close)
        self.tmp = tempfile.mkdtemp(prefix="podbean-u034-")
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.audio = os.path.join(self.tmp, "episode.mp3")
        with open(self.audio, "wb") as f:
            f.write(b"not-real-audio-bytes")

    def _run(self, args, env_extra=None, timeout=30):
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", self.tmp),
            "PODBEAN_RETRY_BASE_DELAY": "0",
        }
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            ["bash", str(_SCRIPT), "--audio", self.audio,
             "--title", "Test Episode"] + args,
            env=env, capture_output=True, text=True, timeout=timeout,
        )

    def _broker_env(self, **extra):
        env = {
            "PODBEAN_PODCAST_ID": "chan-123",
            "PODBEAN_BROKER_WEBHOOK_URL": f"{self.mock.base_url}{self.BROKER_PATH}",
            "PODBEAN_BROKER_TOKEN": FIXTURE_BROKER_TOKEN,
            "PODBEAN_API_BASE": f"{self.mock.base_url}/api",
        }
        env.update(extra)
        return env

    def _route_broker_ok(self):
        self.mock.route(self.BROKER_PATH, "POST", [
            (200, {"ok": True, "access_token": FIXTURE_ACCESS_TOKEN}),
        ])

    def _route_episodes(self, count):
        self.mock.route(self.EPISODES_PREFIX, "GET", [
            (200, {"count": count, "episodes": []}),
        ])

    # ---- T1: Match -> proceed ----

    def test_match_allows_proceed(self):
        """Server count matches roster count exactly: exit 0, agreement logged."""
        self._route_broker_ok()
        self._route_episodes(5)
        proc = self._run(
            ["--dry-run", "--roster-episode-count", "5"],
            env_extra=self._broker_env(),
        )
        self.assertEqual(proc.returncode, 0,
            f"match must proceed; got exit {proc.returncode}\nstderr: {proc.stderr}")
        self.assertIn("agrees with local roster", proc.stderr)

    def test_match_delta_zero(self):
        """Exact match with explicit delta=0: exit 0."""
        self._route_broker_ok()
        self._route_episodes(10)
        proc = self._run(
            ["--dry-run", "--roster-episode-count", "10",
             "--roster-episode-delta", "0"],
            env_extra=self._broker_env(),
        )
        self.assertEqual(proc.returncode, 0,
            f"match delta=0 must proceed; got exit {proc.returncode}")

    # ---- T2: Mismatch beyond delta -> refuse ----

    def test_mismatch_beyond_delta_exit_2(self):
        """|7-5|=2 > delta 0: must refuse with exit 2."""
        self._route_broker_ok()
        self._route_episodes(7)
        proc = self._run(
            ["--dry-run", "--roster-episode-count", "5",
             "--roster-episode-delta", "0"],
            env_extra=self._broker_env(),
        )
        self.assertEqual(proc.returncode, 2,
            f"mismatch beyond delta must exit 2; got {proc.returncode}\nstderr: {proc.stderr}")
        self.assertIn("EPISODE-NUMBER CONFLICT", proc.stderr)

    def test_mismatch_beyond_nonzero_delta_exit_2(self):
        """|12-5|=7 > delta 3: must refuse with exit 2."""
        self._route_broker_ok()
        self._route_episodes(12)
        proc = self._run(
            ["--dry-run", "--roster-episode-count", "5",
             "--roster-episode-delta", "3"],
            env_extra=self._broker_env(),
        )
        self.assertEqual(proc.returncode, 2,
            f"|12-5|=7 > delta 3 must block; got exit {proc.returncode}")

    # ---- T3: Mismatch within delta -> proceed ----

    def test_mismatch_within_delta_allows(self):
        """|8-5|=3 <= delta 3: must proceed with tolerance log."""
        self._route_broker_ok()
        self._route_episodes(8)
        proc = self._run(
            ["--dry-run", "--roster-episode-count", "5",
             "--roster-episode-delta", "3"],
            env_extra=self._broker_env(),
        )
        self.assertEqual(proc.returncode, 0,
            f"|8-5|=3 within delta 3 must allow; got exit {proc.returncode}\nstderr: {proc.stderr}")
        self.assertIn("within tolerance", proc.stderr)

    # ---- T4: Server behind roster -> refuse ----

    def test_server_behind_roster_exit_2(self):
        """Server (3) < roster (10): |3-10|=7 > delta 0 -> exit 2."""
        self._route_broker_ok()
        self._route_episodes(3)
        proc = self._run(
            ["--dry-run", "--roster-episode-count", "10",
             "--roster-episode-delta", "0"],
            env_extra=self._broker_env(),
        )
        self.assertEqual(proc.returncode, 2,
            f"server behind roster must block; got exit {proc.returncode}")
        self.assertIn("EPISODE-NUMBER CONFLICT", proc.stderr)

    # ---- T5: Guard not supplied -> no effect ----

    def test_flag_not_supplied_no_effect(self):
        """Without --roster-episode-count, the guard is inactive."""
        self._route_broker_ok()
        self._route_episodes(99)
        proc = self._run(
            ["--dry-run"],
            env_extra=self._broker_env(),
        )
        self.assertEqual(proc.returncode, 0,
            f"no flag must not block; got exit {proc.returncode}")
        self.assertNotIn("EPISODE-NUMBER CONFLICT", proc.stderr)

    # ---- T6: Validation ----

    def test_non_integer_count_rejected(self):
        """'abc' is not a valid roster count: must fail."""
        self._route_broker_ok()
        self._route_episodes(5)
        proc = self._run(
            ["--dry-run", "--roster-episode-count", "abc"],
            env_extra=self._broker_env(),
        )
        self.assertNotEqual(proc.returncode, 0,
            f"non-integer count must fail; got exit {proc.returncode}")
        self.assertIn("non-negative integer", proc.stderr)

    def test_non_integer_delta_rejected(self):
        """'NaN' is not a valid delta: must fail."""
        self._route_broker_ok()
        self._route_episodes(5)
        proc = self._run(
            ["--dry-run", "--roster-episode-count", "5",
             "--roster-episode-delta", "NaN"],
            env_extra=self._broker_env(),
        )
        self.assertNotEqual(proc.returncode, 0,
            f"non-integer delta must fail; got exit {proc.returncode}")
        self.assertIn("non-negative integer", proc.stderr)

    def test_negative_count_rejected(self):
        """'-1' is not a valid roster count: must fail."""
        self._route_broker_ok()
        self._route_episodes(5)
        proc = self._run(
            ["--dry-run", "--roster-episode-count", "-1"],
            env_extra=self._broker_env(),
        )
        self.assertNotEqual(proc.returncode, 0,
            f"negative count must fail; got exit {proc.returncode}")
        self.assertIn("non-negative integer", proc.stderr)

    # ---- T8: Default delta is 0 ----

    def test_default_delta_is_zero_blocks_mismatch(self):
        """Delta defaults to 0: any mismatch is rejected."""
        self._route_broker_ok()
        self._route_episodes(6)
        proc = self._run(
            ["--dry-run", "--roster-episode-count", "5"],
            env_extra=self._broker_env(),
        )
        self.assertEqual(proc.returncode, 2,
            f"default delta=0 must block one-off; got exit {proc.returncode}")
        self.assertIn("EPISODE-NUMBER CONFLICT", proc.stderr)

    # ---- T9: Large value works ----

    def test_large_count_match_works(self):
        self._route_broker_ok()
        self._route_episodes(9999)
        proc = self._run(
            ["--dry-run", "--roster-episode-count", "9999"],
            env_extra=self._broker_env(),
        )
        self.assertEqual(proc.returncode, 0,
            f"large match must proceed; got exit {proc.returncode}")

    def test_large_count_mismatch_blocks(self):
        self._route_broker_ok()
        self._route_episodes(9999)
        proc = self._run(
            ["--dry-run", "--roster-episode-count", "9997"],
            env_extra=self._broker_env(),
        )
        self.assertEqual(proc.returncode, 2,
            f"large mismatch must block; got exit {proc.returncode}")
        self.assertIn("EPISODE-NUMBER CONFLICT", proc.stderr)


if __name__ == "__main__":
    unittest.main()
