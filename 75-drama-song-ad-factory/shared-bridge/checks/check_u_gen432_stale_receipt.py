#!/usr/bin/env python3
"""U-GEN432 — a refused resume must not leave a stale poll line.

The claim commit (`studio_claim.ClaimLedger.claim_order`) and the poll line's
receipt (`cmd_poll` -> `write_receipt("poll_line")`) are TWO SQLite commits. A
process killed between them leaves the stored line frozen on the old fence and
the old claim token. The next poll presents that token, the claim guard refuses
(rightly), and the refusal path returned success WITHOUT refreshing the receipt
— so the line stayed wedged until the lease expired and a takeover rewrote it,
with a success exit code that says nothing is wrong.

The instrument (same script, `--bridge-dir` picks the code under test):

  1  a real poll materializes the order and stores `poll_line` at fence 1
  2  the lease is expired and a TAKEOVER claim commits fence 2 with no receipt
     write — the process is "killed" between the two commits
  3  the next poll presents the stale fence-1 token and is refused:
     exit 0, no output (the exit-code contract is unchanged)
  4  after that refusal the stored line must match the LIVE claim (fence 2)
  5  so the poll after it resumes and re-emits the line, instead of sitting
     wedged for the rest of the lease

OLD bytes: 4 fails (line stays at fence 1) and 5 is silent.
NEW bytes: 4 refreshes, 5 prints the fence-2 line.

Run: python3 checks/check_u_gen432_stale_receipt.py [--bridge-dir DIR]
Exit: 0 the refusal refreshes the line · 1 it does not
"""
import argparse
import http.server
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
PY = sys.executable
ORDER = "r_gen432"
CLIENT = "c-" + "4" * 32
KEY = "machine-" + "9" * 40


def _load(bridge_dir, stem, alias):
    spec = importlib.util.spec_from_file_location(
        alias, str(bridge_dir / (stem + ".py")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeStudio(http.server.BaseHTTPRequestHandler):
    """The two routes the poll path speaks, on 127.0.0.1 only."""

    studio = {"line": None, "order": {}}

    def _send(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._route()

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        if n:
            self.rfile.read(n)
        self._route()

    def _route(self):
        path = urllib.parse.urlparse(self.path).path
        if self.headers.get("x-ds-key") != KEY:
            return self._send(401, {"ok": False, "code": "AF-DS-AUTH"})
        if path == "/api/studio/checkin":
            return self._send(200, {"ok": True, "line": self.studio["line"]})
        if path.endswith("/state") and "/orders/" in path:
            return self._send(200, {"ok": True, "order": {"state": "claimed"}})
        if "/orders/" in path:
            return self._send(200, {"ok": True, "order": self.studio["order"]})
        return self._send(404, {"ok": False, "code": "AF-DS-NOT-FOUND"})

    def log_message(self, *args):
        pass


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge-dir", default=str(HERE.parent))
    args = ap.parse_args(argv)
    bridge_dir = pathlib.Path(args.bridge_dir).resolve()
    bridge = bridge_dir / "studio_bridge.py"
    if not bridge.is_file():
        print("FAIL no studio_bridge.py under %s" % bridge_dir)
        return 1
    SB = _load(bridge_dir, "studio_bridge", "studio_bridge_under_test")
    SC = _load(bridge_dir, "studio_claim", "studio_claim_under_test")

    tmp = pathlib.Path(tempfile.mkdtemp(
        prefix="u-gen432-", dir=os.environ.get("TMPDIR") or str(HERE)))
    try:
        home, state, runs = tmp / "home", tmp / "state", tmp / "runs"
        for d in (home, state, runs):
            d.mkdir(parents=True, exist_ok=True)
        db = str(tmp / "studio.db")
        factory_log = tmp / "factory-argv.jsonl"
        core = tmp / "stub-skill" / "scripts" / "core" / "intake_preflight"
        core.mkdir(parents=True, exist_ok=True)
        (core / "factory.py").write_text(
            "import json, os, sys\n"
            "with open(os.environ['STUB_FACTORY_LOG'], 'a', encoding='utf-8') as fh:\n"
            "    fh.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "sys.stdout.write('next question\\n')\n", encoding="utf-8")
        skill_root = tmp / "stub-skill"

        _FakeStudio.studio = {
            "line": 'DRAMA_ORDER %s "Crashed Claim"' % ORDER,
            "order": {"order_id": ORDER, "client_id": CLIENT,
                      "title": "Crashed Claim", "replies": ["yes"]},
        }
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeStudio)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d" % srv.server_address[1]

        env = {"PATH": os.environ.get("PATH", ""),
               "HOME": str(home), "DRAMA_STUDIO_STATE": str(state),
               "PYTHONDONTWRITEBYTECODE": "1", "DS_KEY": KEY,
               "STUB_FACTORY_LOG": str(factory_log)}
        if os.environ.get("TMPDIR"):
            env["TMPDIR"] = os.environ["TMPDIR"]

        def poll():
            return subprocess.run(
                [PY, str(bridge), "poll", "--skill-root", str(skill_root),
                 "--runs", str(runs), "--base-url", base, "--db", db],
                capture_output=True, text=True, env=env)

        def line_of(proc):
            lines = [l for l in proc.stdout.splitlines() if l.strip()]
            return json.loads(lines[0]) if len(lines) == 1 else None

        def stored_line():
            with SC.ClaimLedger(db) as led:
                payload = next((r["payload"] for r in reversed(led.receipts(ORDER))
                                if r["kind"] == "poll_line"), None)
                return payload, led.order_state(ORDER) or {}

        results = []

        def check(label, ok, detail):
            results.append(ok)
            print("%s %-58s %s" % ("PASS" if ok else "FAIL", label, detail))

        # 1 — a real poll claims fence 1 and stores the line
        p1 = poll()
        out1 = line_of(p1)
        check("1 first poll claims and prints one line",
              p1.returncode == 0 and out1 is not None
              and out1.get("fence") == 1 and p1.stdout.count("\n") == 1,
              "exit=%d fence=%s" % (p1.returncode,
                                    None if out1 is None else out1.get("fence")))
        first, live = stored_line()
        check("1 stored poll_line matches the live claim",
              bool(first) and first.get("fence") == live.get("fence") == 1,
              "stored=%s live=%s" % (None if not first else first.get("fence"),
                                     live.get("fence")))

        # 2 — lease expires; a takeover claim commits fence 2; the receipt write
        #     never happens (the process is killed between the two commits)
        with SC.ClaimLedger(db) as led:
            led.con.execute("UPDATE orders SET lease_expires_at=? WHERE order_id=?",
                            (time.time() - 60.0, ORDER))
            led.con.commit()
            took = led.claim_order(ORDER, SB.BRIDGE_OWNER)
        after, live2 = stored_line()
        check("2 takeover committed fence 2 with NO receipt write",
              took is True and live2.get("fence") == 2
              and after.get("fence") == 1,
              "took=%s stored=%s live=%s" % (took, after.get("fence"),
                                             live2.get("fence")))

        # 3 — the refused resume: exit 0, silent, exit-code contract unchanged
        p3 = poll()
        check("3 stale-fence resume refused: exit 0, no output",
              p3.returncode == 0 and p3.stdout == "" and p3.stderr == "",
              "exit=%d stdout=%r" % (p3.returncode, p3.stdout[:60]))

        # 4 — THE FIX: the refusal must not leave the line stale
        refreshed, live3 = stored_line()
        check("4 refusal refreshed the receipt to the live claim",
              refreshed.get("fence") == live3.get("fence") == 2
              and refreshed.get("claim_token") == live3.get("claim_token"),
              "stored=%s live=%s same_token=%s"
              % (refreshed.get("fence"), live3.get("fence"),
                 refreshed.get("claim_token") == live3.get("claim_token")))

        # 5 — and so the next poll resumes instead of sitting wedged
        p5 = poll()
        out5 = line_of(p5)
        check("5 next poll resumes and re-emits the fence-2 line",
              p5.returncode == 0 and out5 is not None
              and out5.get("fence") == 2 and out5.get("order_id") == ORDER,
              "exit=%d fence=%s" % (p5.returncode,
                                    None if out5 is None else out5.get("fence")))
        srv.shutdown()
        srv.server_close()

        # control: the same instrument sees a healthy line when there is one
        check("control the stored line now matches the live claim",
              stored_line()[0].get("fence") == 2,
              "stored=%s" % stored_line()[0].get("fence"))

        ok = all(results)
        print("%s %d/%d checks passed (%s)"
              % ("PASS" if ok else "FAIL", sum(results), len(results), bridge_dir))
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
