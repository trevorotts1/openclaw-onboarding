#!/usr/bin/env python3
"""tests/rescue/RRX-ESC/test_escalate_outbox.py   (unit RRX-011)

One command, a durable outbox, one request identifier. Runs the shipped
65-rescue-receiver/rr_escalate.py as a subprocess against a LOOPBACK stub
(127.0.0.1) and a temporary OpenClaw root (OC_CONFIG_ROOT). Offline: nothing
here can reach a real webhook.

  (a) server down            -> state queued_will_retry, exit 10, one outbox file
      then server up + flush -> the SAME request_id arrives, the file moves to
                                sent/, origins/<ticket>.json exists
  (b) server answers 403     -> state setup_problem, exit 20
  (c) server answers 200 HTML-> state queued_will_retry (a page is not an answer)
  (d) the secret is never in the child's process arguments, and it reaches the
      stub in the X-Rescue-Secret header only
  (e) 12 failed attempts move the entry to failed/
"""
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SCRIPT = os.path.join(REPO, "65-rescue-receiver", "rr_escalate.py")
SECRET = "rrx011-test-secret-value"
PASS = FAIL = 0

# Records every POST the stub received, and the answer it gives.
RECORDS = []
ANSWER = {"code": 200, "ctype": "application/json", "body": "{}"}

# Runs the script with a dump of the child's own argv, so (d) inspects the real
# process arguments instead of the ones this test happened to build.
SHIM = (
    "import json, runpy, sys\n"
    "dump, script = sys.argv[1], sys.argv[2]\n"
    "argv = sys.argv[3:]\n"
    "open(dump, 'w').write(json.dumps([script] + argv))\n"
    "sys.argv = [script] + argv\n"
    "runpy.run_path(script, run_name='__main__')\n"
)


def ok(name):
    global PASS
    PASS += 1
    print("  ok   " + name)


def bad(name, detail=""):
    global FAIL
    FAIL += 1
    print("  FAIL " + name + " " + str(detail)[:300])


def check(cond, name, detail=""):
    ok(name) if cond else bad(name, detail)


class Stub(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace")
        RECORDS.append({"path": self.path, "headers": dict(self.headers), "body": raw})
        payload = ANSWER["body"].encode("utf-8")
        self.send_response(ANSWER["code"])
        self.send_header("Content-Type", ANSWER["ctype"])
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


TMP = tempfile.mkdtemp(prefix="rrx011-outbox-")


def new_root(name):
    root = os.path.join(TMP, name)
    os.makedirs(os.path.join(root, "secrets"), exist_ok=True)
    return root


def run(args, root, url, secret=SECRET):
    """Run one sub-command. Returns (exit_code, last JSON object, child argv)."""
    dump = os.path.join(TMP, "argv-%d.json" % (len(RECORDS) + os.getpid()))
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
        "HOME": os.path.join(TMP, "home"),
        "OC_CONFIG_ROOT": root,
        "RESCUE_RANGERS_WEBHOOK_URL": url,
        "RESCUE_RANGERS_WEBHOOK_SECRET": secret,
        "FLEET_STANDING_BOX_SLUG": "test-box",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    cmd = [sys.executable, "-c", SHIM, dump, SCRIPT] + args
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    doc = {}
    if lines:
        try:
            doc = json.loads(lines[-1])
        except ValueError:
            doc = {}
    argv = []
    try:
        with open(dump, encoding="utf-8") as fh:
            argv = json.load(fh)
    except (OSError, ValueError):
        pass
    return proc.returncode, doc, argv, proc


def send_args():
    return ["send", "--person", "Owner", "--client", "test-client",
            "--problem", "The gateway will not start.", "--tried", "Restarted it twice."]


def outbox_files(root):
    d = os.path.join(root, "state", "rr-escalate", "outbox")
    return sorted(n for n in os.listdir(d)) if os.path.isdir(d) else []


def files_in(root, sub):
    d = os.path.join(root, "state", "rr-escalate", sub)
    return sorted(n for n in os.listdir(d)) if os.path.isdir(d) else []


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    live_url = "http://127.0.0.1:%d/webhook/rr-v2-intake" % srv.server_address[1]
    dead_url = "http://127.0.0.1:%d/webhook/rr-v2-intake" % free_port()
    try:
        # ---- (a) server down, then flush when it is up -------------------
        ANSWER.update({"code": 200, "ctype": "application/json",
                       "body": json.dumps({"accepted": True, "status": "accepted", "ticketId": "RR-000123"})})
        root = new_root("a")
        rc, doc, _, _ = run(send_args(), root, dead_url)
        check(rc == 10, "a1 server down: exit 10", rc)
        check(doc.get("state") == "queued_will_retry", "a2 server down: queued_will_retry", doc)
        left = outbox_files(root)
        check(len(left) == 1, "a3 server down: one file in outbox/", left)
        first_rid = ""
        if left:
            with open(os.path.join(root, "state", "rr-escalate", "outbox", left[0]), encoding="utf-8") as fh:
                first_rid = json.load(fh)["body"]["request_id"]
        RECORDS.clear()
        rc, doc, _, _ = run(["flush"], root, live_url)
        check(rc == 0, "a4 flush with the server up: exit 0", rc)
        check(doc.get("state") == "accepted", "a5 flush: accepted", doc)
        check(len(RECORDS) == 1, "a6 flush sent exactly one request", len(RECORDS))
        rid_seen = ""
        if RECORDS:
            try:
                rid_seen = json.loads(RECORDS[0]["body"])["request_id"]
            except (ValueError, KeyError):
                rid_seen = ""
        check(bool(first_rid) and rid_seen == first_rid, "a7 the SAME request_id is reused", (first_rid, rid_seen))
        if RECORDS:
            try:
                op_seen = json.loads(RECORDS[0]["body"]).get("operation_id")
            except ValueError:
                op_seen = None
            check(op_seen == first_rid, "a8 operation_id rides beside request_id", op_seen)
        check(outbox_files(root) == [], "a9 the outbox entry moved out", outbox_files(root))
        check(len(files_in(root, "sent")) == 1, "a10 the entry is in sent/", files_in(root, "sent"))
        check(os.path.isfile(os.path.join(root, "state", "rr-escalate", "origins", "RR-000123.json")),
              "a11 origins/<ticket>.json exists")

        # ---- (b) 403 is a setup problem ---------------------------------
        ANSWER.update({"code": 403, "ctype": "application/json", "body": '{"error":"refused"}'})
        root = new_root("b")
        rc, doc, _, _ = run(send_args(), root, live_url)
        check(doc.get("state") == "setup_problem", "b1 403: setup_problem", doc)
        check(rc == 20, "b2 403: exit 20", rc)

        # ---- (c) a 200 that is an HTML page is not an answer ------------
        ANSWER.update({"code": 200, "ctype": "text/html", "body": "<html><body>blocked</body></html>"})
        root = new_root("c")
        rc, doc, _, _ = run(send_args(), root, live_url)
        check(doc.get("state") == "queued_will_retry", "c1 200 HTML: queued_will_retry", doc)
        check(rc == 10, "c2 200 HTML: exit 10", rc)
        check(len(outbox_files(root)) == 1, "c3 200 HTML: the entry stays in outbox/", outbox_files(root))

        # ---- (d) the secret never rides the command line ----------------
        ANSWER.update({"code": 200, "ctype": "application/json",
                       "body": json.dumps({"accepted": True, "status": "accepted", "ticketId": "RR-000124"})})
        root = new_root("d")
        RECORDS.clear()
        rc, doc, argv, proc = run(send_args(), root, live_url)
        check(doc.get("state") == "accepted", "d1 accepted", doc)
        check(argv and SECRET not in json.dumps(argv), "d2 the secret is not in the child's argv", argv)
        check(SECRET not in proc.stdout and SECRET not in proc.stderr, "d3 the secret is not printed")
        got = RECORDS[0] if RECORDS else {"headers": {}, "path": ""}
        check(got["headers"].get("X-Rescue-Secret") == SECRET, "d4 the stub receives the secret in its header")
        check(SECRET not in got["path"], "d5 the secret is not in the request path", got["path"])
        leaks = [k for k, v in got["headers"].items() if v == SECRET and k.lower() != "x-rescue-secret"]
        check(not leaks, "d6 no other header carries the secret", leaks)

        # ---- (e) 12 failed attempts move the entry to failed/ -----------
        root = new_root("e")
        rc, doc, _, _ = run(send_args(), root, dead_url)
        check(doc.get("state") == "queued_will_retry", "e1 attempt 1 is queued", doc)
        for _ in range(11):
            run(["flush"], root, dead_url)
        check(outbox_files(root) == [], "e2 after 12 failed attempts the outbox is empty", outbox_files(root))
        check(len(files_in(root, "failed")) == 1, "e3 the entry is in failed/", files_in(root, "failed"))
    finally:
        srv.shutdown()
        srv.server_close()

    print("RESULT: %d passed, %d failed" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
