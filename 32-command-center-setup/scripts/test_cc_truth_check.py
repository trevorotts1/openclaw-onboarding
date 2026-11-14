#!/usr/bin/env python3
"""Acceptance tests for cc_truth_check.py (build unit U-11).

Runs the real script as a subprocess against fake `pm2` / `openclaw` executables
on a temporary PATH and a throwaway HTTP server on 127.0.0.1. No live system,
no live database, no real process manager is contacted.

Acceptance rows covered:
  app online -> 0; app errored -> 1; pm2 missing -> 2; pm2 non-JSON -> 2;
  HTTP 200 {"status":"ok"} -> 0; HTTP 503 -> 1; connection refused -> 1;
  HTTP 401 -> 0 with reason "sign-in wall answered, app is up".
Cron rows: a registered enabled job -> 0; an absent job -> 1.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "cc_truth_check.py")

APP = "blackceo-command-center"


def run(args, tmp_path, tools):
    """Run cc_truth_check.py with only the given fake tools on PATH."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in tools.items():
        exe = bin_dir / name
        exe.write_text(body, encoding="utf-8")
        exe.chmod(0o755)
    env = {"PATH": str(bin_dir), "HOME": str(tmp_path), "TMPDIR": str(tmp_path)}
    proc = subprocess.run([sys.executable, SCRIPT, *args], capture_output=True,
                          text=True, env=env, timeout=120)
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    return proc.returncode, payload


def _shell_print(payload):
    """A fake executable that prints payload and exits 0 (single-quoted: JSON has no single quotes)."""
    return "#!/bin/sh\nprintf '%s' '" + json.dumps(payload) + "'\n"


def pm2_with(status):
    return _shell_print([{"name": APP, "pm2_env": {"status": status, "restart_time": 1}}])


def openclaw_listing(jobs):
    return (
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *--help*) echo 'Usage: openclaw cron list [--json] [--all]'; exit 0 ;;\n"
        "  *) printf '%s' '" + json.dumps({"jobs": jobs}) + "' ; exit 0 ;;\n"
        "esac\n"
    )


# ---- app ------------------------------------------------------------------

def test_app_online_is_good(tmp_path):
    code, payload = run(["app"], tmp_path, {"pm2": pm2_with("online")})
    assert code == 0, payload
    assert payload["verdict"] == "GOOD"


def test_app_errored_is_bad(tmp_path):
    code, payload = run(["app"], tmp_path, {"pm2": pm2_with("errored")})
    assert code == 1, payload
    assert payload["verdict"] == "BAD"


def test_pm2_missing_is_undetermined(tmp_path):
    code, payload = run(["app"], tmp_path, {})
    assert code == 2, payload
    assert payload["verdict"] == "UNDETERMINED"


def test_pm2_non_json_is_undetermined(tmp_path):
    code, payload = run(["app"], tmp_path, {"pm2": "#!/bin/sh\nprintf 'not json\\n'\n"})
    assert code == 2, payload
    assert payload["verdict"] == "UNDETERMINED"


# ---- http -----------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        code, body = self.server.reply
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


def _serve(reply):
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    server.reply = reply
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_http_200_ok_is_good(tmp_path):
    server = _serve((200, b'{"status": "ok"}'))
    try:
        code, payload = run(["http", "--port", str(server.server_address[1])], tmp_path, {})
    finally:
        server.shutdown()
        server.server_close()
    assert code == 0, payload
    assert payload["verdict"] == "GOOD"


def test_http_503_is_bad(tmp_path):
    server = _serve((503, b""))
    try:
        code, payload = run(["http", "--port", str(server.server_address[1])], tmp_path, {})
    finally:
        server.shutdown()
        server.server_close()
    assert code == 1, payload
    assert payload["verdict"] == "BAD"


def test_http_connection_refused_is_bad(tmp_path):
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    code, payload = run(["http", "--port", str(port)], tmp_path, {})
    assert code == 1, payload
    assert payload["verdict"] == "BAD"


def test_http_401_sign_in_wall_is_good(tmp_path):
    server = _serve((401, b""))
    try:
        code, payload = run(["http", "--port", str(server.server_address[1])], tmp_path, {})
    finally:
        server.shutdown()
        server.server_close()
    assert code == 0, payload
    assert payload["verdict"] == "GOOD"
    assert payload["reason"] == "sign-in wall answered, app is up"


# ---- cron -----------------------------------------------------------------

def test_cron_registered_and_enabled_is_good(tmp_path):
    tools = {"openclaw": openclaw_listing([{"name": "cc-watchdog", "id": "7", "enabled": True}])}
    code, payload = run(["cron", "--name", "cc-watchdog"], tmp_path, tools)
    assert code == 0, payload
    assert payload["verdict"] == "GOOD"


def test_cron_absent_is_bad(tmp_path):
    tools = {"openclaw": openclaw_listing([{"name": "some-other-job", "id": "1"}])}
    code, payload = run(["cron", "--name", "cc-watchdog"], tmp_path, tools)
    assert code == 1, payload
    assert payload["verdict"] == "BAD"


def test_cron_openclaw_missing_is_undetermined(tmp_path):
    code, payload = run(["cron", "--name", "cc-watchdog"], tmp_path, {})
    assert code == 2, payload
    assert payload["verdict"] == "UNDETERMINED"
