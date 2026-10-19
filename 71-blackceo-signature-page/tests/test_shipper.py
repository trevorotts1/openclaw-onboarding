#!/usr/bin/env python3
"""Functional test for scripts/ship_run_events.py.

Stands up a local HTTP capture server as the ingest endpoint, then checks:
  - spool lines are POSTed as {events: [...]} with the bearer header,
  - host-index lines past the recorded offset are forwarded once,
  - a garbage spool line is quarantined, never sent,
  - a second run sends nothing (local dedupe + offset),
  - a dead endpoint leaves lines in place and exits 1.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# The shipper ships with the skill. It used to be read from a developer's
# private build tree, so this module failed everywhere that tree is absent --
# including continuous integration, where nothing exists under $HOME.
SHIPPER = Path(__file__).resolve().parents[1] / "scripts" / "ship_run_events.py"

received = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        received.append((self.headers.get("Authorization"), json.loads(body)))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


def ev(i):
    return {"event_id": f"00000000-0000-4000-8000-{i:012d}", "event_type": "stage_closed",
            "schema_version": "1.0", "emitted_at": "2026-10-13T10:00:00Z",
            "run_id": "00000000-0000-4000-8000-0000000000aa", "stage": "intake",
            "receipt_status": "pass", "closed_at": "2026-10-13T10:00:00Z"}


def run_shipper(env, *extra):
    return subprocess.run([sys.executable, str(SHIPPER), *extra],
                          env=env, capture_output=True, text=True)


def main():
    if not SHIPPER.is_file():
        print(f"SKIP test_shipper: shipper script absent: {SHIPPER}")
        return 0
    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/api/skill-runs/ingest"

    tmp = Path(tempfile.mkdtemp(prefix="ship-test-"))
    spool = tmp / "spool"; spool.mkdir()
    (spool / "a.jsonl").write_text(json.dumps(ev(1)) + "\n" + json.dumps(ev(2)) + "\n")
    (spool / "b.jsonl").write_text('{"not": "an event"}\n')
    index = tmp / "runs.jsonl"
    index.write_text(json.dumps(ev(3)) + "\n")
    token = tmp / "token.txt"; token.write_text("test-token-value\n")

    env = dict(os.environ, SKILL71_RUNS_SHIP_URL=url,
               SKILL71_RUNS_SHIP_TOKEN_FILE=str(token),
               SKILL71_RUNS_SPOOL=str(spool), SKILL71_RUNS_INDEX=str(index),
               SKILL71_RUNS_SHIP_STATE=str(spool / "state.json"))
    r1 = run_shipper(env)
    assert r1.returncode == 0, r1.stderr
    sent_ids = [e["event_id"] for _, batch in received for e in batch["events"]]
    assert sorted(sent_ids) == sorted([ev(1)["event_id"], ev(2)["event_id"], ev(3)["event_id"]]), sent_ids
    assert all(auth == "Bearer test-token-value" for auth, _ in received)
    assert not (spool / "a.jsonl").exists(), "drained spool file should be removed"
    assert (spool / "quarantine.jsonl").exists(), "garbage line must be quarantined"
    state = json.loads((spool / "state.json").read_text())
    assert len(state["shipped_event_ids"]) == 3, state

    received.clear()
    r2 = run_shipper(env)
    assert r2.returncode == 0, r2.stderr
    assert received == [], f"second run must send nothing, sent {received}"

    # Dead endpoint: line stays in the spool, exit 1.
    (spool / "c.jsonl").write_text(json.dumps(ev(4)) + "\n")
    env_dead = dict(env, SKILL71_RUNS_SHIP_URL="http://127.0.0.1:1/ingest")
    r3 = run_shipper(env_dead)
    assert r3.returncode == 1, (r3.returncode, r3.stderr)
    assert ev(4)["event_id"] in (spool / "c.jsonl").read_text()

    # Token value must never appear in output.
    assert "test-token-value" not in (r1.stdout + r1.stderr + r3.stdout + r3.stderr)
    server.shutdown()
    print("PASS: shipper posts spool+index once, dedupes, quarantines garbage, "
          "fails safe on a dead endpoint, never prints the token")
    return 0


if __name__ == "__main__":
    sys.exit(main())
