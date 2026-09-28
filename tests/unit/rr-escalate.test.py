#!/usr/bin/env python3
# tests/unit/rr-escalate.test.py
#
# Proves scripts/rr-escalate.sh (the one Rescue Rangers sender) against a
# loopback stub of the RR-01 intake contract:
#   * auth header X-Rescue-Secret required (403 otherwise)
#   * message AND box required (400 accepted:false invalid_payload otherwise)
#   * a body containing __AUTHTEST__ is answered 200 test_suppressed
# Cases: selftest parses test_suppressed; a real escalation carries the box
# slug + identity and prints the ticket; a missing box is refused BEFORE any
# POST (non-zero); intake refusal / accepted-without-ticket / wrong secret are
# all non-zero; the secret never appears in output.
#
# Hermetic: 127.0.0.1 only, throwaway HOME, stub openclaw. Run:
#   python3 tests/unit/rr-escalate.test.py
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(REPO, "scripts", "rr-escalate.sh")
SECRET = "fixture-secret-value-0000"
REQUESTS = []

PASS = FAIL = 0


def check(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + (("\n       " + str(detail)) if detail else ""))


class Intake(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        REQUESTS.append({"headers": dict(self.headers), "body": body})
        doc = json.loads(body or "{}")
        if self.headers.get("X-Rescue-Secret") != SECRET:
            code, out = 403, {"status": "unauthorized"}
        elif "__AUTHTEST__" in body:
            code, out = 200, {"accepted": True, "ticketId": None, "status": "test_suppressed"}
        elif not (doc.get("message") or doc.get("problem")) or not doc.get("boxName"):
            code, out = 400, {"accepted": False, "status": "invalid_payload",
                              "reason": "unresolvable box"}
        elif doc.get("problem") == "no-ticket":
            code, out = 200, {"accepted": True, "status": "queued"}
        elif doc.get("problem") == "refuse-me":
            code, out = 200, {"accepted": False, "status": "rejected", "reason": "cap_exceeded"}
        else:
            code, out = 200, {"accepted": True, "ticketId": "RR-TICKET-1", "status": "admitted"}
        raw = json.dumps(out).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), Intake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d/webhook/rr-v2-intake" % srv.server_port


def make_box(slug="box-fixture", secret=SECRET):
    home = tempfile.mkdtemp(prefix="rr-esc-test.")
    root = os.path.join(home, ".openclaw")
    os.makedirs(os.path.join(root, "secrets"))
    os.makedirs(os.path.join(home, "bin"))
    env_vars = {"RESCUE_RANGERS_WEBHOOK_URL": URL, "OPENCLAW_COMPANY_NAME": "Fixture Co"}
    if slug:
        env_vars["FLEET_STANDING_BOX_SLUG"] = slug
    with open(os.path.join(root, "openclaw.json"), "w") as fh:
        json.dump({"env": {"vars": env_vars},
                   "agents": {"list": [{"id": "helper"}, {"id": "main", "name": "Aria", "default": True}]}}, fh)
    with open(os.path.join(root, "secrets", ".env"), "w") as fh:
        fh.write('RESCUE_RANGERS_WEBHOOK_SECRET="%s"\n' % secret)
    stub = os.path.join(home, "bin", "openclaw")
    with open(stub, "w") as fh:
        fh.write("#!/bin/sh\necho 'OpenClaw 2026.9.0'\n")
    os.chmod(stub, 0o755)
    return home, root


def run(home, root, *args):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("RESCUE_RANGERS_", "FLEET_STANDING_", "OPENCLAW_"))}
    env.update(HOME=home, OC_ROOT=root, PATH=os.path.join(home, "bin") + os.pathsep + env["PATH"])
    p = subprocess.run(["bash", SCRIPT] + list(args), env=env, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout, p.stderr


print("== rr-escalate.sh ==")
check(os.access(SCRIPT, os.X_OK), "scripts/rr-escalate.sh exists and is executable")

home, root = make_box()
REQUESTS.clear()
rc, out, err = run(home, root, "--selftest")
check(rc == 0 and "status=test_suppressed" in out, "selftest exits 0 only on test_suppressed", (rc, out, err))
check(len(REQUESTS) == 1 and REQUESTS[0]["headers"].get("X-Rescue-Secret") == SECRET,
      "selftest sends the X-Rescue-Secret header read from the secrets file")
check(SECRET not in out + err, "the secret is never printed")

REQUESTS.clear()
rc, out, err = run(home, root, "--problem", "gateway keeps restarting", "--tried", "1. restarted",
                   "--agent", "ops-agent")
body = json.loads(REQUESTS[0]["body"]) if REQUESTS else {}
check(rc == 0 and "ticket=RR-TICKET-1" in out and "incident_id=RR-TICKET-1" in out,
      "a real escalation prints the ticket id and exits 0", (rc, out, err))
check(body.get("boxName") == "box-fixture", "payload carries boxName from FLEET_STANDING_BOX_SLUG", body)
check(body.get("clientName") == "Fixture Co" and body.get("agentName") == "ops-agent",
      "clientName from openclaw.json, --agent override honored", body)
check(body.get("openclawVersion") == "OpenClaw 2026.9.0" and body.get("alreadyTried") == "1. restarted"
      and body.get("message") == "gateway keeps restarting", "version, tried and message filled", body)

REQUESTS.clear()
rc, out, err = run(home, root, "--problem", "x")
body = json.loads(REQUESTS[0]["body"]) if REQUESTS else {}
check(body.get("agentName") == "Aria", "default agent resolved from agents.list (default entry)", body)

for problem, name in (("no-ticket", "accepted without a ticket id"),
                      ("refuse-me", "accepted:false refusal")):
    rc, out, err = run(home, root, "--problem", problem)
    check(rc == 4 and "REJECTED" in err and "ticket=" not in out, name + " exits 4, prints no ticket", (rc, out, err))

nobox_home, nobox_root = make_box(slug="")
REQUESTS.clear()
rc, out, err = run(nobox_home, nobox_root, "--problem", "something broke")
check(rc == 3 and "FLEET_STANDING_BOX_SLUG" in err and not REQUESTS,
      "missing box slug is refused locally (exit 3) and nothing is POSTed", (rc, err, len(REQUESTS)))

wrong_home, wrong_root = make_box(secret="wrong-secret")
rc, out, err = run(wrong_home, wrong_root, "--selftest")
check(rc == 4 and "http=403" in err and "wrong-secret" not in out + err,
      "wrong secret: 403 -> exit 4, secret not echoed", (rc, err))

rc, out, err = run(home, root)
check(rc == 2, "--problem is required (usage exit 2)", rc)

REQUESTS.clear()
rc, out, err = run(home, root, "--resolve", "RR-TICKET-1", "--problem", "RESOLVED: restarted gateway",
                   "--attempt", "a1")
body = json.loads(REQUESTS[0]["body"]) if REQUESTS else {}
check(rc == 0 and all(body.get(k) for k in ("incident_id", "operation_id", "attempt_id",
                                             "result_digest", "runtime_id")),
      "--resolve carries the RR-002 correlation fields", body)

srv.shutdown()
print("\nRESULT: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
