#!/usr/bin/env python3
"""S75-083 / U-GEN305 — the R2 deletion deadline must reach the operator surface.

THE DEFECT THIS PINS
--------------------
`_delivered` wrote `r2_delete_after` onto the delivered record, and NOTHING in
production ever read it. The only readers were two lines of the check script. So
the 7-day retention promise existed as a field nobody could see, and the module's
own comment pointed at a deletion receipt that does not exist in the tree.

WHAT THIS CHECK ASSERTS
-----------------------
1. An R2 fallback delivery prints the deadline in the delivery step's
   operator-visible output (`evidence`), worded as a deadline that is RECORDED
   and explicitly not enforced, and the printed value is the record's value.
2. The envelope's `next_action` says the deadline is recorded, not enforced.
3. Control: a GHL delivery carries no deletion deadline anywhere in its output —
   the deadline belongs to the R2 fallback only, so the marker is not just noise.

WHY IT FAILS WITHOUT THE FIX
----------------------------
The final section runs the SAME assertion against a planted-bad copy of the
module with the deadline-surfacing block switched off — which is exactly the
pre-fix state, where no production code reads the field. That copy MUST fail the
check, or this check proves nothing.

Every URL is served by a local mock server on 127.0.0.1. No live network call, no
credential, no client message, no client-box write, and nothing is deleted.

Run:  python3 checks/test_r2_delete_after_surface.py
Exit: 0 all three assertions hold and the planted-bad copy is caught · 1 otherwise
"""
import hashlib
import http.server
import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import uuid

HERE = pathlib.Path(__file__).resolve().parent
MODULE = HERE.parent / "video_link_delivery.py"
WORK = pathlib.Path(tempfile.mkdtemp(prefix="op-GEN305-", dir=tempfile.gettempdir()))
PY = sys.executable

GOOD = b"DRAMA-SONG-FINISHED-VIDEO-BYTES-v1" * 64
GOOD_SHA = hashlib.sha256(GOOD).hexdigest()
LOC = "LOC_CLIENT_ACME_0001"

# The exact wording the fix must emit. Anchored on phrases the pre-fix module has
# nowhere: it never named the deadline in any operator string at all.
MARKER = "r2_delete_after="
RECORDED_WORD = "RECORDED"
NOT_ENFORCED_WORD = "no deletion is performed"
NEXT_ACTION_WORD = "recorded, not enforced"

_ROUTES = {
    "/msgsndr/video.mp4": GOOD,
    "/r2/video.mp4": GOOD,
}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = _ROUTES.get(urllib.parse.urlsplit(self.path).path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # silence the mock server
        pass


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_mock():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv


def _deliver(module_path, request):
    req_path = WORK / f"req-{uuid.uuid4().hex[:8]}.json"
    req_path.write_text(json.dumps(request), encoding="utf-8")
    argv = [PY, str(module_path), "deliver", "--request", str(req_path), "--timeout", "10"]
    p = subprocess.run(argv, capture_output=True, text=True)
    try:
        env = json.loads(p.stdout)
    except json.JSONDecodeError:
        env = {}
    return p.returncode, env


def _request(**over):
    req = {
        "client_id": "acme",
        "record_client_id": "acme",
        "client_location_id": LOC,
        "expected_sha256": GOOD_SHA,
        "ghl_allowed_hosts": ["127.0.0.1", "localhost"],
        "r2_allowed_hosts": ["127.0.0.1"],
        "operator_location_ids": [],
        "operator_hosts": [],
    }
    req.update(over)
    return req


def _deadline_lines(env):
    return [e for e in (env.get("evidence") or []) if str(e).startswith(MARKER)]


def _surface_violations(env):
    """Every way the R2 deadline fails to reach the operator surface, or reads as
    an enforced deletion rather than a recorded one."""
    bad = []
    record = (env.get("data") or {}).get("delivery") or {}
    deadline = str(record.get("r2_delete_after") or "")
    lines = _deadline_lines(env)
    if not deadline:
        bad.append("the delivered record carries no r2_delete_after")
    if len(lines) != 1:
        bad.append(f"expected exactly 1 '{MARKER}' evidence line, found {len(lines)}")
        return bad
    line = str(lines[0])
    if deadline and deadline not in line:
        bad.append(f"the printed deadline ({line!r}) is not the record's ({deadline!r})")
    if RECORDED_WORD not in line:
        bad.append(f"the deadline line does not say {RECORDED_WORD}: {line!r}")
    if NOT_ENFORCED_WORD not in line:
        bad.append(f"the deadline line does not say {NOT_ENFORCED_WORD!r}: {line!r}")
    if NEXT_ACTION_WORD not in str(env.get("next_action", "")):
        bad.append(f"next_action does not say {NEXT_ACTION_WORD!r}: {env.get('next_action')!r}")
    return bad


def _ghl_violations(env):
    """The deadline belongs to the R2 fallback only; a GHL delivery must not
    carry it, so the marker above is a real discriminator and not constant noise."""
    bad = []
    if _deadline_lines(env):
        bad.append("a GHL delivery printed an R2 deletion deadline")
    if "deletion deadline" in str(env.get("next_action", "")):
        bad.append("a GHL delivery's next_action mentions a deletion deadline")
    return bad


def _plant_no_surface():
    """The pre-fix state: the deadline-surfacing block switched off. If this copy
    passes, the check above cannot tell the fix from the defect."""
    src = MODULE.read_text(encoding="utf-8")
    anchor = '    if record.get("r2_delete_after"):'
    n = src.count(anchor)
    if n != 1:
        raise SystemExit(f"FATAL: plant anchor is not unique ({n} matches): {anchor!r}")
    dst = WORK / f"planted-{uuid.uuid4().hex[:8]}.py"
    dst.write_text(src.replace(anchor, "    if False:  # planted-bad: no surface"), encoding="utf-8")
    return dst


def main() -> int:
    base, srv = _start_mock()
    closed = _free_port()
    failures = 0
    try:
        r2_req = _request(ghl_candidate={"url": f"http://127.0.0.1:{closed}/msgsndr/video.mp4",
                                         "owner_location_id": LOC},
                          r2_candidate={"url": base + "/r2/video.mp4"})
        rc, env = _deliver(MODULE, r2_req)
        bad = _surface_violations(env) if rc == 0 else [f"delivery failed: rc={rc}"]
        ok = not bad
        print(f"{'PASS' if ok else 'FAIL'}  G  the R2 deletion deadline reaches the operator surface, recorded-not-enforced")
        print(f"        rc={rc} evidence={json.dumps(env.get('evidence'))}")
        print(f"        next_action={env.get('next_action')!r}")
        for b in bad:
            print(f"        -> {b}")
        failures += 0 if ok else 1

        ghl_req = _request(ghl_candidate={"url": base + "/msgsndr/video.mp4",
                                          "owner_location_id": LOC})
        rc2, env2 = _deliver(MODULE, ghl_req)
        bad2 = _ghl_violations(env2) if rc2 == 0 else [f"delivery failed: rc={rc2}"]
        ok2 = not bad2
        print(f"{'PASS' if ok2 else 'FAIL'}  G-control  a GHL delivery carries no R2 deletion deadline")
        print(f"        rc={rc2} evidence={json.dumps(env2.get('evidence'))}")
        for b in bad2:
            print(f"        -> {b}")
        failures += 0 if ok2 else 1

        planted = _plant_no_surface()
        prc, penv = _deliver(planted, r2_req)
        pbad = _surface_violations(penv) if prc == 0 else [f"delivery failed: rc={prc}"]
        caught = bool(pbad)
        print(f"{'PASS' if caught else 'FAIL'}  G-plant  the plant (no deadline surface = the pre-fix state) is caught")
        print(f"        on the planted copy: rc={prc} evidence={json.dumps(penv.get('evidence'))}")
        for b in pbad:
            print(f"        -> {b}")
        failures += 0 if caught else 1
    finally:
        srv.shutdown()

    print()
    if failures:
        print(f"RESULT: {failures} failure(s) - the deadline does not reach the operator surface")
        return 1
    print("RESULT: the deadline reaches the operator surface as recorded-not-enforced, and the pre-fix state is caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())
