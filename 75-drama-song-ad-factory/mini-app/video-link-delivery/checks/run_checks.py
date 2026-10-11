#!/usr/bin/env python3
"""U10 required — runnable checks for the video-link delivery rule.

Every check runs the CLI as a REAL subprocess and asserts a TRUE exit code, and
every check has a PLANTED-BAD control: a copy of the module with one load-bearing
line mutated, run through the SAME check, which must then FAIL. A check therefore
only passes when it discriminates — silences and false greens are both failures.

Every URL is served (or not served) by a LOCAL mock server on 127.0.0.1. No live
network call, no credential, no client message, no client-box write.

  A  GHL-first: with a client-owned GHL link available it is the deliverable, even
     when a stored/previous link is also present
     plant: prefer the stored link  -> must be caught
  B  R2 fallback: used only because the client-owned GHL path was unavailable, and
     only when the R2 copy verifies; an R2 copy serving the wrong media is refused
     plant: deliver nothing when GHL is down  -> must be caught
  C  unverified is refused: a link that does not resolve is refused non-zero, and a
     200 serving the wrong media is refused too (so "verified" means the right media,
     not merely "resolved")
     plant: skip the verification gate  -> must be caught
  D  operator-owned link is refused non-zero (control: the same request is accepted
     once the operator marker is removed, so the guard is what discriminates)
     plant: drop the operator guard  -> must be caught
  E  cross-client delivery is refused non-zero (control: the same request is accepted
     once the record belongs to the delivering client)
     plant: drop the cross-client guard  -> must be caught
  F  no token value appears in stdout, stderr or the delivered record (reported with
     the TRUE exit code of the grep), with a positive control proving the detector
     can see the sentinel, and a credential-bearing URL refused
     plant: allow a credential-bearing URL through  -> must be caught

Run:  python3 checks/run_checks.py
Exit: 0 all checks pass and every plant is caught · 1 otherwise
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
MODULE_DIR = HERE.parent
MODULE = MODULE_DIR / "video_link_delivery.py"
# All scratch lives under the operator box's lane prefix, never the repo tree.
WORK = pathlib.Path(tempfile.mkdtemp(prefix="op-U10-U1-", dir="/tmp"))
PY = sys.executable

GOOD = b"DRAMA-SONG-FINISHED-VIDEO-BYTES-v1" * 64
OTHER = b"SOME-OTHER-MEDIA-ENTIRELY-BYTES-v2" * 64
GOOD_SHA = hashlib.sha256(GOOD).hexdigest()
OTHER_SHA = hashlib.sha256(OTHER).hexdigest()
TOKEN = "sk-planted-TOKEN-9f2c1a7b"

LOC = "LOC_CLIENT_ACME_0001"
OP_LOC = "LOC_OPERATOR_0000"

# ── local mock server (the only "network" any check touches) ──────────────────

_ROUTES = {
    "/msgsndr/video.mp4": GOOD,
    "/msgsndr/other.mp4": OTHER,
    "/r2/video.mp4": GOOD,
    "/r2/other.mp4": OTHER,
}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        # A query string (a stale-revision marker, a planted signature) must not
        # change which media the mock serves.
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


def start_mock() -> tuple[str, http.server.ThreadingHTTPServer, int]:
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    return f"http://127.0.0.1:{port}", srv, port


# ── CLI runner + plant machinery ──────────────────────────────────────────────

def _run_cli(module_path, request, out=None):
    req_path = WORK / f"req-{uuid.uuid4().hex[:8]}.json"
    req_path.write_text(json.dumps(request), encoding="utf-8")
    argv = [PY, str(module_path), "deliver", "--request", str(req_path), "--timeout", "10"]
    if out:
        argv += ["--out", str(out)]
    p = subprocess.run(argv, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr, req_path


def _runner(module_path):
    def run(request, out=None):
        return _run_cli(module_path, request, out)
    return run


def _envelope(stdout):
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {}


def _plant(plant):
    src = MODULE.read_text(encoding="utf-8")
    old, new = plant
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"FATAL: plant anchor is not unique ({n} matches): {old!r}")
    dst = WORK / f"planted-{uuid.uuid4().hex[:8]}.py"
    dst.write_text(src.replace(old, new), encoding="utf-8")
    return dst


def _grep_rc(needle, path):
    """TRUE exit code of a fixed-string grep for `needle` in `path` (1 = absent)."""
    p = subprocess.run(["grep", "-F", "-q", "--", needle, str(path)], capture_output=True, text=True)
    return p.returncode


# ── shared request builders ───────────────────────────────────────────────────

def _base(base, **over):
    req = {
        "client_id": "acme",
        "record_client_id": "acme",
        "client_location_id": LOC,
        "expected_sha256": GOOD_SHA,
        "ghl_allowed_hosts": ["127.0.0.1", "localhost"],
        "r2_allowed_hosts": ["127.0.0.1"],
        "operator_location_ids": [OP_LOC],
        "operator_hosts": [],
        "ghl_candidate": {"url": base + "/msgsndr/video.mp4", "owner_location_id": LOC},
    }
    req.update(over)
    return req


# ── A: GHL-first preference ───────────────────────────────────────────────────

def check_a(run, base, closed):
    req = _base(base, stored_link={"url": base + "/msgsndr/video.mp4?rev=1",
                                   "owner_location_id": LOC, "source": "ghl"})
    rc, out, err, _ = run(req)
    env = _envelope(out)
    d = (env.get("data") or {}).get("delivery") or {}
    ok = (rc == 0
          and d.get("url") == base + "/msgsndr/video.mp4"
          and d.get("source") == "ghl"
          and d.get("ownership") == "client-ghl"
          and d.get("fallback") is False)
    return ok, (f"rc={rc} url={d.get('url')} source={d.get('source')} "
                f"ownership={d.get('ownership')} (stored link present, must NOT be preferred)")


# ── B: R2 fallback, and an unverified fallback refused ───────────────────────

def check_b(run, base, closed):
    ghl_down = _base(base, ghl_candidate={"url": f"http://127.0.0.1:{closed}/msgsndr/video.mp4",
                                          "owner_location_id": LOC},
                     r2_candidate={"url": base + "/r2/video.mp4"})
    rc, out, err, _ = run(ghl_down)
    env = _envelope(out)
    d = (env.get("data") or {}).get("delivery") or {}
    pos = (rc == 0 and d.get("source") == "r2" and d.get("fallback") is True
           and d.get("ownership") == "studio-r2-fallback"
           and bool(d.get("r2_delete_after"))
           and str(d.get("fallback_reason", "")).startswith("ghl-unverified"))

    ghl_down_bad_r2 = _base(base, ghl_candidate={"url": f"http://127.0.0.1:{closed}/msgsndr/video.mp4",
                                                 "owner_location_id": LOC},
                            r2_candidate={"url": base + "/r2/other.mp4"})
    rc2, out2, _e2, _p2 = run(ghl_down_bad_r2)
    env2 = _envelope(out2)
    neg = rc2 == 4 and env2.get("reason_code") == "fallback-unverified"

    ok = pos and neg
    return ok, (f"fallback rc={rc} source={d.get('source')} ownership={d.get('ownership')} "
                f"delete_after={'set' if d.get('r2_delete_after') else 'MISSING'}; "
                f"wrong-media R2 rc={rc2} reason={env2.get('reason_code')} (want 4/fallback-unverified)")


# ── C: unverified is refused ─────────────────────────────────────────────────

def check_c(run, base, closed):
    unresolvable = _base(base, ghl_candidate={"url": f"http://127.0.0.1:{closed}/msgsndr/video.mp4",
                                              "owner_location_id": LOC})
    rc, out, err, _ = run(unresolvable)
    env = _envelope(out)
    refused = rc == 4 and env.get("reason_code") == "no-verified-deliverable-link"

    wrong_media = _base(base, ghl_candidate={"url": base + "/msgsndr/other.mp4",
                                             "owner_location_id": LOC})
    rc2, out2, _e2, _p2 = run(wrong_media)
    env2 = _envelope(out2)
    refused_wrong = rc2 == 4 and env2.get("reason_code") == "no-verified-deliverable-link"

    rc3, out3, _e3, _p3 = run(_base(base))  # instrument control: the good link passes
    instrument_ok = rc3 == 0

    ok = refused and refused_wrong and instrument_ok
    return ok, (f"unresolvable rc={rc} reason={env.get('reason_code')} "
                f"next_action_mentions_unreachable={'unreachable' in str(env.get('next_action', ''))}; "
                f"wrong-media-200 rc={rc2} reason={env2.get('reason_code')}; "
                f"good-link instrument control rc={rc3}")


# ── D: operator-owned link refused ───────────────────────────────────────────

def check_d(run, base, closed):
    port = int(base.rsplit(":", 1)[1])
    operator = _base(base, ghl_candidate={"url": f"http://localhost:{port}/msgsndr/video.mp4",
                                          "owner_location_id": LOC},
                     operator_hosts=["localhost"])
    rc, out, err, _ = run(operator)
    env = _envelope(out)
    refused = rc == 4 and env.get("reason_code") == "operator-owned-link" \
        and "OPERATOR" in str(env.get("next_action", ""))

    control = dict(operator)
    control["operator_hosts"] = []
    rc2, out2, _e2, _p2 = run(control)
    control_ok = rc2 == 0  # same link, marker removed -> accepted: the guard discriminates

    ok = refused and control_ok
    return ok, (f"operator rc={rc} reason={env.get('reason_code')} "
                f"names_operator={'OPERATOR' in str(env.get('next_action', ''))}; "
                f"control(no operator marker) rc={rc2}")


# ── E: cross-client refused ──────────────────────────────────────────────────

def check_e(run, base, closed):
    cross = _base(base, record_client_id="otherco")
    rc, out, err, _ = run(cross)
    env = _envelope(out)
    refused = rc == 4 and env.get("reason_code") == "cross-client-delivery"

    control = _base(base)
    rc2, out2, _e2, _p2 = run(control)
    control_ok = rc2 == 0

    ok = refused and control_ok
    return ok, (f"cross-client rc={rc} reason={env.get('reason_code')}; "
                f"control(record=client) rc={rc2}")


# ── F: no token in any output ────────────────────────────────────────────────

def check_f(run, base, closed):
    out_file = WORK / f"record-{uuid.uuid4().hex[:8]}.json"
    req = _base(base, token=TOKEN)
    rc, out, err, req_path = run(req, out=out_file)

    blob = WORK / f"blob-{uuid.uuid4().hex[:8]}.txt"
    blob.write_text(out + "\n" + err + "\n" + (out_file.read_text(encoding="utf-8") if out_file.exists() else ""),
                    encoding="utf-8")
    leak_rc = _grep_rc(TOKEN, blob)                    # want 1 (absent)
    detector_rc = _grep_rc(TOKEN, req_path)            # want 0 (the detector CAN see it)

    signed = _base(base, token=TOKEN,
                   ghl_candidate={"url": base + "/msgsndr/video.mp4?X-Amz-Signature=" + TOKEN,
                                  "owner_location_id": LOC})
    rc2, out2, err2, _p2 = run(signed)
    env2 = _envelope(out2)
    signed_refused = rc2 == 4 and env2.get("reason_code") == "token-in-url"
    blob2 = WORK / f"blob2-{uuid.uuid4().hex[:8]}.txt"
    blob2.write_text(out2 + "\n" + err2, encoding="utf-8")
    signed_leak_rc = _grep_rc(TOKEN, blob2)            # want 1 (absent)

    ok = (rc == 0 and leak_rc == 1 and detector_rc == 0
          and signed_refused and signed_leak_rc == 1)
    return ok, (f"deliver rc={rc}; token grep in stdout+stderr+record rc={leak_rc} (want 1); "
                f"detector positive control grep rc={detector_rc} (want 0); "
                f"credential-URL rc={rc2} reason={env2.get('reason_code')}; "
                f"credential-URL output grep rc={signed_leak_rc} (want 1)")


# ── check table: (name, fn, plant) ───────────────────────────────────────────

CHECKS = [
    ("A", "client-owned GHL-first link is chosen", check_a, (
        '    return request.get("ghl_candidate") or None',
        '    return request.get("stored_link") or request.get("ghl_candidate")',
    )),
    ("B", "R2 fallback used only when GHL is unavailable, and only when it verifies", check_b, (
        '        return _delivered(r2, verified, "r2", ghl_unavailable, request)',
        '        raise DeliveryRefused("no-verified-deliverable-link", "planted: delivers nothing")',
    )),
    ("C", "an unverified link is refused non-zero", check_c, (
        '    if not v["ok"]:',
        '    if False:',
    )),
    ("D", "an operator-owned link is refused non-zero", check_d, (
        '        if _is_operator_owned(cand, request):',
        '        if False:',
    )),
    ("E", "a cross-client delivery is refused non-zero", check_e, (
        '    if str(request.get("record_client_id", "")) != str(request.get("client_id", "")):',
        '    if False:',
    )),
    ("F", "no token value appears in stdout, stderr or the delivered record", check_f, (
        '        if _embeds_secret(str(cand.get("url", "")), secrets):',
        '        if False:',
    )),
]


def main() -> int:
    base, srv, _port = start_mock()
    closed = _free_port()
    failures = 0
    try:
        for name, desc, fn, plant in CHECKS:
            ok, detail = fn(_runner(MODULE), base, closed)
            print(f"{'PASS' if ok else 'FAIL'}  {name}  {desc}")
            print(f"        {detail}")
            if not ok:
                failures += 1

            if plant is None:
                continue
            planted = _plant(plant)
            pok, pdetail = fn(_runner(planted), base, closed)
            caught = not pok
            print(f"{'PASS' if caught else 'FAIL'}  {name}-plant  planted-bad copy is caught")
            print(f"        plant={plant[0].strip()!r}")
            print(f"        on the planted copy: {pdetail}")
            if not caught:
                failures += 1
    finally:
        srv.shutdown()

    print()
    if failures:
        print(f"RESULT: {failures} failure(s) — the delivery rule is NOT proven")
        return 1
    print(f"RESULT: all {len(CHECKS)} checks pass and all {len(CHECKS)} planted-bad copies are caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())
