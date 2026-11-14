#!/usr/bin/env python3
"""cc_truth_check.py - for 32-command-center-setup/scripts/ (build unit U-11). Not installed anywhere.

Replaces the grep/echo status checks in Skill 32 (finding CC-005). Every answer
is read from structured output; an empty or unreadable result is never an answer.

Exit codes (same for every sub-command):
  0  PROVEN GOOD
  1  PROVEN BAD
  2  UNDETERMINED - the check itself could not run or could not be read.
     Callers must treat 2 as "I do not know", never as good and never as bad.

Sub-commands:
  app  [--name blackceo-command-center]        is the process manager running the app?
  http [--port 4000] [--host 127.0.0.1]        does the app answer its health address?
  cron --name <job-name>                       is that scheduled job registered and enabled?
  selftest                                     prove the parsers and the three verdicts on fixed
                                               samples and on a throwaway local server (no live system)

Always prints ONE JSON object: {"check","verdict","exit","reason","evidence"}.
Never prints secrets: only names, states, codes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request

GOOD, BAD, UNDETERMINED = 0, 1, 2
VERDICT = {0: "GOOD", 1: "BAD", 2: "UNDETERMINED"}


def emit(check: str, code: int, reason: str, evidence: dict | None = None) -> int:
    print(json.dumps({"check": check, "verdict": VERDICT[code], "exit": code,
                      "reason": reason, "evidence": evidence or {}}))
    return code


def run_json(cmd: list[str], timeout: float = 20.0):
    """Return (parsed_json, None) or (None, reason). Never returns an empty success."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return None, f"{cmd[0]} is not on PATH (this proves nothing about the app)"
    except subprocess.TimeoutExpired:
        return None, f"{cmd[0]} timed out after {timeout}s"
    if p.returncode != 0:
        return None, f"{cmd[0]} exited {p.returncode}: {p.stderr.strip()[:160]}"
    text = p.stdout.strip()
    if not text:
        return None, f"{cmd[0]} printed nothing"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"{cmd[0]} output is not JSON ({exc.msg})"


def check_app(name: str) -> int:
    data, why = run_json(["pm2", "jlist"])
    if data is None:
        return emit("app", UNDETERMINED, why)
    if not isinstance(data, list):
        return emit("app", UNDETERMINED, "pm2 jlist did not return a list")
    rows = [r for r in data if isinstance(r, dict) and r.get("name") == name]
    if not rows:
        return emit("app", BAD, f"no process named {name} is registered",
                    {"registered_names": sorted(str(r.get('name')) for r in data if isinstance(r, dict))})
    states = [str((r.get("pm2_env") or {}).get("status")) for r in rows]
    restarts = [(r.get("pm2_env") or {}).get("restart_time") for r in rows]
    evidence = {"states": states, "restarts": restarts, "instances": len(rows)}
    if len(rows) > 1:
        return emit("app", BAD, f"{len(rows)} processes share the name {name}", evidence)
    if states[0] == "online":
        return emit("app", GOOD, f"{name} is online", evidence)
    return emit("app", BAD, f"{name} is registered but its state is {states[0]}", evidence)


def check_http(host: str, port: int) -> int:
    url = f"http://{host}:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            code, body = resp.status, resp.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        code, body = exc.code, ""
        if code in (401, 403):
            return emit("http", GOOD, "sign-in wall answered, app is up", {"http": code})
        return emit("http", BAD, f"health address answered HTTP {code}", {"http": code})
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        return emit("http", BAD, f"no answer on port {port}: {exc}", {"url": url})
    try:
        status = json.loads(body).get("status")
    except (json.JSONDecodeError, AttributeError):
        return emit("http", UNDETERMINED, "port answered but not with health JSON "
                    "(something else may be listening on this port)", {"http": code})
    if code == 200 and status in ("ok", "degraded"):
        return emit("http", GOOD, f"app answered, status field is {status}", {"http": code, "status": status})
    return emit("http", BAD, f"app answered HTTP {code} with status {status}", {"http": code, "status": status})


def find_cron(data, name: str):
    """Locate a job by exact name. Returns (job_dict, None) / (None, None) when
    provably absent / (None, reason) when the shape is not recognised.
    Shape follows the installer's own reader (run-full-install.sh, the
    cc_watchdog_cron_lookup function): a list of jobs, or an object with "jobs"."""
    jobs = data if isinstance(data, list) else (data.get("jobs") if isinstance(data, dict) else None)
    if not isinstance(jobs, list) or any(not isinstance(j, dict) for j in jobs):
        return None, "cron list shape not recognised"
    if jobs and not any("name" in j for j in jobs):
        return None, "cron list rows carry no name field"
    for j in jobs:
        if j.get("name") == name:
            return j, None
    return None, None


def cron_list_command() -> list[str]:
    """Disabled jobs are left out of the default listing on builds that have --all."""
    cmd = ["openclaw", "cron", "list", "--json"]
    try:
        helptext = subprocess.run(["openclaw", "cron", "list", "--help"], capture_output=True,
                                  text=True, timeout=20)
        words = (helptext.stdout + " " + helptext.stderr).replace("=", " ").replace("<", " ").split()
        if "--all" in words:
            cmd.append("--all")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # run_json below reports the missing tool as UNDETERMINED
    return cmd


def check_cron(name: str) -> int:
    data, why = run_json(cron_list_command(), timeout=30)
    if data is None:
        return emit("cron", UNDETERMINED, why)
    job, shape_problem = find_cron(data, name)
    if shape_problem:
        return emit("cron", UNDETERMINED, shape_problem)
    if job is None:
        return emit("cron", BAD, f"no scheduled job named {name}")
    # The installer treats a job with no "enabled" key as enabled.
    if job.get("enabled", True) is True:
        return emit("cron", GOOD, f"{name} is registered and enabled", {"id": job.get("id")})
    return emit("cron", BAD, f"{name} is registered but disabled", {"id": job.get("id")})


def selftest() -> int:
    """No live system is contacted: fixed samples, one throwaway server on 127.0.0.1, one closed port."""
    import contextlib
    import http.server
    import io
    import socket
    import threading

    n = 0

    def check(cond: bool, what: str) -> None:
        nonlocal n
        assert cond, what
        n += 1

    # Cron listing shapes (the installer's own reader accepts a list, or an object with "jobs").
    check(find_cron([{"name": "cc-watchdog", "id": "1"}], "cc-watchdog")[0]["id"] == "1", "list shape")
    check(find_cron({"jobs": [{"name": "a"}, {"name": "cc-watchdog", "enabled": False}]}, "cc-watchdog")[0]["enabled"] is False,
          "object shape, disabled job is still found")
    check(find_cron([{"name": "other"}], "cc-watchdog") == (None, None), "provably absent")
    check(find_cron([], "cc-watchdog") == (None, None), "empty list is absent, not an error")
    check(find_cron("text", "cc-watchdog")[1] is not None, "unrecognised shape is a reason, never 'absent'")
    check(find_cron([{"id": "1"}], "cc-watchdog")[1] is not None, "rows with no name field are a reason")
    check(find_cron([{"name": "cc-watchdog-old"}], "cc-watchdog") == (None, None), "exact name only, no substring match")

    # A tool that is missing or prints nothing is UNDETERMINED, never an answer.
    check(run_json(["cc-truth-check-no-such-tool"])[0] is None, "missing tool gives no data")
    check(run_json(["/usr/bin/true"])[0] is None, "empty output gives no data")
    check(run_json(["/bin/echo", "not json"])[0] is None, "non-JSON gives no data")
    check(run_json(["/bin/echo", '{"a": 1}'])[0] == {"a": 1}, "known-good control: JSON is read")

    answers = {"/api/health": (200, b'{"status": "ok"}')}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            code, body = answers["/api/health"]
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep the selftest quiet
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink):
            check(check_http("127.0.0.1", port) == GOOD, "200 ok is GOOD")
            answers["/api/health"] = (200, b'{"status": "degraded"}')
            check(check_http("127.0.0.1", port) == GOOD, "200 degraded is GOOD (the app is up)")
            answers["/api/health"] = (401, b"")
            check(check_http("127.0.0.1", port) == GOOD, "401 sign-in wall is GOOD")
            answers["/api/health"] = (403, b"")
            check(check_http("127.0.0.1", port) == GOOD, "403 sign-in wall is GOOD")
            answers["/api/health"] = (503, b"")
            check(check_http("127.0.0.1", port) == BAD, "503 is BAD")
            answers["/api/health"] = (404, b"")
            check(check_http("127.0.0.1", port) == BAD, "404 is BAD (the old check passed it)")
            answers["/api/health"] = (200, b"<html>something else</html>")
            check(check_http("127.0.0.1", port) == UNDETERMINED, "a non-health answer is UNDETERMINED")
    finally:
        server.shutdown()
        server.server_close()
    with socket.socket() as probe:  # a port that is provably closed
        probe.bind(("127.0.0.1", 0))
        closed = probe.getsockname()[1]
    with contextlib.redirect_stdout(sink):
        check(check_http("127.0.0.1", closed) == BAD, "nothing listening is BAD")
    printed = [json.loads(line) for line in sink.getvalue().strip().splitlines()]
    check(all(set(row) == {"check", "verdict", "exit", "reason", "evidence"} for row in printed), "one JSON object per check")
    print(f"selftest: {n} assertions passed")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    a = sub.add_parser("app"); a.add_argument("--name", default="blackceo-command-center")
    h = sub.add_parser("http"); h.add_argument("--port", type=int, default=4000); h.add_argument("--host", default="127.0.0.1")
    c = sub.add_parser("cron"); c.add_argument("--name", required=True)
    args = ap.parse_args()
    if args.cmd == "selftest":
        return selftest()
    if args.cmd == "app":
        return check_app(args.name)
    if args.cmd == "http":
        return check_http(args.host, args.port)
    return check_cron(args.name)


if __name__ == "__main__":
    sys.exit(main())
