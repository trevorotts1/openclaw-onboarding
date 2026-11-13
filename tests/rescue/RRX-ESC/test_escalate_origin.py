#!/usr/bin/env python3
"""tests/rescue/RRX-ESC/test_escalate_origin.py   (unit RRX-001a)

The conversation the case came from is recorded ON THE BOX, never sent.

Runs the shipped 65-rescue-receiver/rr_escalate.py as a subprocess against a
LOOPBACK stub (127.0.0.1) and a temporary OpenClaw root (OC_CONFIG_ROOT) that
carries a FAKE owner-chat helper. Offline: nothing here reaches a real webhook.

  (a) the helper prints 123456789 -> origins/<ticket>.json has
      origin.target == "123456789", and neither the request body's key set nor
      its text carries "origin" or "123456789"
  (b) the helper prints nothing   -> origin is null, and say_to_owner says a
      person on the support team will follow up directly
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
SECRET = "rrx001a-test-secret-value"
CHAT_ID = "123456789"
PASS = FAIL = 0

RECORDS = []
ANSWER = {"code": 200, "ctype": "application/json",
          "body": json.dumps({"accepted": True, "status": "accepted", "ticketId": "RR-000900"})}

# A stand-in for shared-utils/resolve-owner-chat.sh: same sourcing contract
# (a function named resolve_owner_chat_id that prints one line).
HELPER = "resolve_owner_chat_id() { printf '%%s\\n' '%s'; }\n"


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


TMP = tempfile.mkdtemp(prefix="rrx001a-origin-")


def new_root(name, helper_output):
    """An OpenClaw root whose fake helper prints `helper_output`."""
    root = os.path.join(TMP, name)
    os.makedirs(os.path.join(root, "secrets"), exist_ok=True)
    helper_dir = os.path.join(root, "skills", "shared-utils")
    os.makedirs(helper_dir, exist_ok=True)
    with open(os.path.join(helper_dir, "resolve-owner-chat.sh"), "w", encoding="utf-8") as fh:
        fh.write(HELPER % helper_output)
    return root


def run(args, root, url):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
        "HOME": os.path.join(TMP, "home"),
        "OC_CONFIG_ROOT": root,
        "RESCUE_RANGERS_WEBHOOK_URL": url,
        "RESCUE_RANGERS_WEBHOOK_SECRET": SECRET,
        "FLEET_STANDING_BOX_SLUG": "test-box",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    proc = subprocess.run([sys.executable, SCRIPT] + args, capture_output=True, text=True,
                          timeout=120, env=env)
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    doc = {}
    if lines:
        try:
            doc = json.loads(lines[-1])
        except ValueError:
            doc = {}
    return proc.returncode, doc, proc


def send_args():
    return ["send", "--person", "Owner", "--client", "test-client",
            "--problem", "The gateway will not start.", "--tried", "Restarted it twice."]


def origin_file(root, ticket):
    return os.path.join(root, "state", "rr-escalate", "origins", ticket + ".json")


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/webhook/rr-v2-intake" % srv.server_address[1]
    try:
        # ---- (a) the helper names the conversation ----------------------
        root = new_root("a", CHAT_ID)
        RECORDS.clear()
        rc, doc, _ = run(send_args(), root, url)
        check(doc.get("state") == "accepted", "a1 accepted", doc)
        check(rc == 0, "a2 exit 0", rc)
        path = origin_file(root, "RR-000900")
        check(os.path.isfile(path), "a3 origins/RR-000900.json exists", os.listdir(
            os.path.join(root, "state", "rr-escalate", "origins"))
            if os.path.isdir(os.path.join(root, "state", "rr-escalate", "origins")) else [])
        origin = {}
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                origin = (json.load(fh) or {}).get("origin") or {}
        check(origin.get("target") == CHAT_ID, "a4 origin.target is the helper's chat id", origin)
        check(origin.get("channel") == "telegram" and origin.get("account") == "default",
              "a5 origin is the telegram/default shape", origin)
        body_raw = RECORDS[0]["body"] if RECORDS else ""
        try:
            body = json.loads(body_raw) if body_raw else {}
        except ValueError:
            body = {}
        check("origin" not in body, "a6 the request body has no origin key", sorted(body))
        check(CHAT_ID not in body_raw, "a7 the chat id is nowhere in the request body", body_raw[:300])
        check(CHAT_ID not in json.dumps(doc), "a8 the chat id is not printed to the agent", doc)

        # ---- (b) the helper finds nothing -------------------------------
        root = new_root("b", "")
        RECORDS.clear()
        rc, doc, _ = run(send_args(), root, url)
        check(doc.get("state") == "accepted", "b1 accepted", doc)
        check(rc == 0, "b2 exit 0", rc)
        path = origin_file(root, "RR-000900")
        recorded = {"absent": True}
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                recorded = json.load(fh)
        check(recorded.get("origin") is None, "b3 origin is null on the box", recorded)
        check("follow up with you directly" in str(doc.get("say_to_owner") or ""),
              "b4 the owner is told a person will follow up directly", doc.get("say_to_owner"))
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
