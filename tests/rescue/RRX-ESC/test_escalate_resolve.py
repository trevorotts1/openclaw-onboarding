#!/usr/bin/env python3
"""tests/rescue/RRX-ESC/test_escalate_resolve.py   (unit RRX-007)

The box can close its own case, and the agent can read an outcome.

Runs the shipped 65-rescue-receiver/rr_escalate.py as a subprocess against a
LOOPBACK stub (127.0.0.1) and a temporary OpenClaw root (OC_CONFIG_ROOT).
Offline: nothing here can reach a real webhook.

  (a) no done record    -> the resolution body has no attempt_id key, and the
      client and agent fall back to the box slug and "main"
  (b) done records      -> the NEWEST done record's attempt_id rides the body,
      and client/agent are read from the sent/ record for this ticket
  (c) resolve twice     -> both requests carry the SAME operation_id
  (d) status            -> outcome_recorded (the poll's file), waiting (a sent
      record, no outcome yet) and unknown_ticket (nothing at all, exit 21)
  (e) 409               -> unknown_incident
"""
import hashlib
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
SECRET = "rrx007-test-secret-value"
TICKET = "RR-000900"
FIXED = "restarted the gateway and cleared its lock"
PASS = FAIL = 0

# Records every POST the stub received, and the answer it gives.
RECORDS = []
ANSWER = {"code": 200, "ctype": "application/json", "body": '{"status":"resolution_recorded"}'}


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


TMP = tempfile.mkdtemp(prefix="rrx007-resolve-")


def new_root(name):
    root = os.path.join(TMP, name)
    os.makedirs(os.path.join(root, "secrets"), exist_ok=True)
    return root


def write_json(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
        fh.write("\n")


def done_record(root, name, doc):
    write_json(os.path.join(root, "state", "rr-receiver", "done", name + ".json"), doc)


def sent_record(root, name, ticket, client, agent):
    write_json(os.path.join(root, "state", "rr-escalate", "sent", name + ".json"),
               {"body": {"clientName": client, "agentName": agent},
                "attempts": 1,
                "final": {"state": "accepted", "ticket_id": ticket}})


def outcome_record(root, ticket, doc):
    write_json(os.path.join(root, "state", "rr-receiver", "case-outcomes", ticket + ".json"), doc)


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


def resolve_args():
    return ["resolve", "--ticket", TICKET, "--fixed", FIXED]


def last_body():
    if not RECORDS:
        return {}
    try:
        return json.loads(RECORDS[-1]["body"])
    except (ValueError, KeyError):
        return {}


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/webhook/rr-v2-intake" % srv.server_address[1]
    try:
        # ---- (a) no done record: no attempt_id, slug/main fallback --------
        root = new_root("a")
        RECORDS.clear()
        rc, doc, _ = run(resolve_args(), root, url)
        body = last_body()
        check(doc.get("state") == "resolved", "a1 resolution_recorded is resolved", doc)
        check(rc == 0, "a2 exit 0", rc)
        check("attempt_id" not in body, "a3 no done record: no attempt_id key", sorted(body))
        check(body.get("clientName") == "test-box", "a4 clientName falls back to the box slug", body)
        check(body.get("agentName") == "main", "a5 agentName falls back to main", body)
        check(body.get("incident_id") == TICKET, "a6 the ticket rides as incident_id", body)
        check(body.get("problem") == "RESOLVED: " + FIXED, "a7 problem carries the fixed text", body)
        digest = "sha256-" + hashlib.sha256(("RESOLVED: " + FIXED).encode("utf-8")).hexdigest()
        check(body.get("result_digest") == digest, "a8 result_digest is the sha256 of that text",
              body.get("result_digest"))
        check(body.get("operation_id") == body.get("request_id") == doc.get("request_id"),
              "a9 operation_id and request_id are the one identifier", (body, doc))

        # ---- (b) the newest done record's attempt_id, and the sent/ names --
        root = new_root("b")
        done_record(root, "d1", {"ticket_id": TICKET, "attempt_id": "att-old", "written_at": 100})
        done_record(root, "d2", {"ticket_id": TICKET, "attempt_id": "att-new", "written_at": 200})
        done_record(root, "other", {"ticket_id": "RR-000901", "attempt_id": "att-other", "written_at": 300})
        sent_record(root, "req-1", TICKET, "acme", "diagnostician")
        RECORDS.clear()
        rc, doc, _ = run(resolve_args(), root, url)
        body = last_body()
        check(doc.get("state") == "resolved", "b1 resolved", doc)
        check(body.get("attempt_id") == "att-new", "b2 the newest done record's attempt_id rides", body)
        check(body.get("clientName") == "acme", "b3 clientName is read from the sent/ record", body)
        check(body.get("agentName") == "diagnostician", "b4 agentName is read from the sent/ record", body)

        # ---- (c) resolving twice sends the same operation_id --------------
        root = new_root("c")
        RECORDS.clear()
        rc, doc, _ = run(resolve_args(), root, url)
        first = last_body().get("operation_id")
        rc, doc, _ = run(resolve_args(), root, url)
        second = last_body().get("operation_id")
        check(bool(first) and first.startswith("res-" + TICKET + "-"),
              "c1 the operation_id keeps the res-<ticket>- shape", first)
        check(first == second, "c2 a re-run sends the SAME operation_id", (first, second))
        check(len(RECORDS) == 2, "c3 both resolutions reached the intake", len(RECORDS))

        # ---- (d) status: the three states ---------------------------------
        root = new_root("d")
        outcome_record(root, TICKET, {"ticket_id": TICKET, "outcome": "solved",
                                      "summary": "the gateway comes up again"})
        rc, doc, _ = run(["status", "--ticket", TICKET], root, url)
        check(doc.get("state") == "outcome_recorded", "d1 an outcome file: outcome_recorded", doc)
        check(rc == 0, "d2 outcome_recorded exits 0", rc)
        check(doc.get("outcome") == "solved", "d3 the poll's own fields are kept", doc)

        root = new_root("d-waiting")
        sent_record(root, "req-2", TICKET, "acme", "main")
        rc, doc, _ = run(["status", "--ticket", TICKET], root, url)
        check(doc.get("state") == "waiting", "d4 a sent record and no outcome: waiting", doc)
        check(rc == 0, "d5 waiting exits 0", rc)
        check("still working" in str(doc.get("say_to_owner") or ""),
              "d6 waiting tells the owner support is still working", doc.get("say_to_owner"))

        root = new_root("d-unknown")
        rc, doc, _ = run(["status", "--ticket", TICKET], root, url)
        check(doc.get("state") == "unknown_ticket", "d7 nothing at all: unknown_ticket", doc)
        check(rc == 21, "d8 unknown_ticket exits 21", rc)

        # ---- (e) the intake has no such incident --------------------------
        ANSWER.update({"code": 409, "ctype": "application/json", "body": '{"status":"no_such_incident"}'})
        root = new_root("e")
        rc, doc, _ = run(resolve_args(), root, url)
        check(doc.get("state") == "unknown_incident", "e1 409: unknown_incident", doc)
        check(rc == 0, "e2 unknown_incident exits 0", rc)
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
