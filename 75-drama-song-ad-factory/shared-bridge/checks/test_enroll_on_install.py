#!/usr/bin/env python3
"""DSR-101 runnable checks for shared-bridge/enroll-on-install.sh.

Everything here runs against a FAKE studio on 127.0.0.1 and a throwaway HOME /
state folder. No link is minted, no order is placed, nothing reaches the real
studio, and the live ~/.drama-studio is never opened.

  A  with a secret and a server that accepts, the helper posts /api/studio/enroll
     and writes machine.key into the state folder  (the one thing that unblocks
     studio_bridge.py `link` and `poll`)
  B  with a server that REFUSES, the helper writes nothing and still exits 0,
     with a refusal-code warning  (a studio outage must never fail an install)
     -- with a positive control proving the same server WOULD have written the
     key, so the clean refusal is the server's doing and not a dead instrument
  C  with no secret anywhere, the helper exits 0, prints the skip line to
     stderr, and leaves the box untouched
  D  the secret resolves from ~/.openclaw/secrets/.env, the store the operator
     already uses, when it is not in the live process environment
  E  a box that already holds a machine key is left alone -- no HTTP request is
     made at all (enroll is once per box)
  F  the secret value never reaches the helper's own output, and never appears
     on the python child's command line (argv is what `ps` shows)

Run: python3 checks/test_enroll_on_install.py
Exit: 0 all pass - 1 at least one failed
"""
import http.server
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
BRIDGE_DIR = HERE.parent
HELPER = str(BRIDGE_DIR / "enroll-on-install.sh")

SENTINEL = "DSR101-SECRET-9f3c2b7a4e1d8c6502ab"

_failures = []


def _ok(name):
    print("  ok    %s" % name)


def _bad(name, detail):
    print("  FAIL  %s: %s" % (name, detail))
    _failures.append(name)


def _assert(name, cond, detail):
    if cond:
        _ok(name)
    else:
        _bad(name, detail)


class FakeStudio:
    """A stdlib HTTP server that answers enroll one way, controlled per test."""

    def __init__(self, accept=True, delay=0.0):
        self.accept = accept
        self.delay = delay
        self.requests = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):  # keep the run quiet
                pass

            def do_POST(self):
                if outer.delay:
                    time.sleep(outer.delay)
                outer.requests.append({
                    "path": self.path,
                    "body": self.rfile.read(int(self.headers.get("Content-Length", 0))),
                    "argv_leak": False,
                })
                if outer.accept:
                    self._send(200, {"ok": True, "key": "fake-machine-key-" + "a" * 24,
                                     "client_id": "c_fake"})
                else:
                    self._send(403, {"ok": False, "code": "AF_ENROLL_REFUSED",
                                     "message": "refused by the fake studio"})

            def _send(self, status, payload):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        return False


def _sandbox(with_env_file=False):
    """A throwaway HOME + state folder; nothing here can reach the real box."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="dsr101-"))
    home = root / "home"
    state = root / "state"
    home.mkdir()
    state.mkdir()
    if with_env_file:
        secrets = home / ".openclaw" / "secrets"
        secrets.mkdir(parents=True)
        (secrets / ".env").write_text("KIE_API_KEY=sk-not-this-one\n"
                                      "export DS_ENROLLMENT_SECRET=%s\n" % SENTINEL)
    return root, home, state


def _run(home, state, secret=SENTINEL):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "DRAMA_STUDIO_STATE": str(state),
    }
    if secret is not None:
        env["DS_ENROLLMENT_SECRET"] = secret
    return subprocess.run(["bash", HELPER], env=env, capture_output=True, text=True)


# --- A: the happy path --------------------------------------------------------

def check_a_enrolls_against_accepting_server():
    root, home, state = _sandbox()
    try:
        with FakeStudio(accept=True) as studio:
            # the bridge reads the address from machine.url; seed it the way a
            # paired box would, so nothing about the REAL studio is implied
            (state / "machine.url").write_text(studio.url + "\n")
            p = _run(home, state)
            _assert("A rc is 0", p.returncode == 0, "rc=%d out=%r err=%r"
                    % (p.returncode, p.stdout, p.stderr))
            _assert("A machine.key written", (state / "machine.key").is_file(),
                    "no machine.key in %s; out=%r" % (state, p.stdout))
            _assert("A key value is not the fake server's key leaking into stdout",
                    "fake-machine-key" not in p.stdout + p.stderr,
                    "key value printed: %r" % p.stdout)
            _assert("A the bridge received the enroll POST",
                    any(r["path"] == "/api/studio/enroll" for r in studio.requests),
                    "requests=%r" % [r["path"] for r in studio.requests])
            body = b"".join(r["body"] for r in studio.requests)
            _assert("A the secret travelled in the POST body",
                    SENTINEL.encode() in body, "body=%r" % body)
    finally:
        _cleanup(root)


# --- B: refusal writes nothing, with a positive control -----------------------

def test_b_refusal_leaves_box_untouched():
    root, home, state = _sandbox()
    try:
        with FakeStudio(accept=False) as studio:
            (state / "machine.url").write_text(studio.url + "\n")
            p = _run(home, state)
            _assert("B rc is 0 (fail-soft)", p.returncode == 0,
                    "rc=%d err=%r" % (p.returncode, p.stderr))
            _assert("B nothing written", not (state / "machine.key").exists(),
                    "machine.key written despite the refusal")
            _assert("B the refusal code is surfaced", "AF_ENROLL_REFUSED" in p.stderr,
                    "stderr=%r" % p.stderr)
            _assert("B the secret is not in the output",
                    SENTINEL not in p.stdout + p.stderr,
                    "secret leaked: %r %r" % (p.stdout, p.stderr))
    finally:
        _cleanup(root)


def test_b_control_same_server_would_write():
    """Positive control on the SAME instrument: without the refusal the box
    enrols, so the clean refusal above is the server's doing."""
    root, home, state = _sandbox()
    try:
        with FakeStudio(accept=True) as studio:
            (state / "machine.url").write_text(studio.url + "\n")
            p = _run(home, state)
            _assert("B-control the same server enrols when it accepts",
                    p.returncode == 0 and (state / "machine.key").is_file(),
                    "control failed: rc=%d out=%r" % (p.returncode, p.stdout))
    finally:
        _cleanup(root)


# --- C: no secret -> skip ------------------------------------------------------

def test_c_no_secret_skips_cleanly():
    root, home, state = _sandbox()
    try:
        with FakeStudio(accept=True) as studio:
            (state / "machine.url").write_text(studio.url + "\n")
            p = _run(home, state, secret=None)
            _assert("C rc is 0", p.returncode == 0, "rc=%d" % p.returncode)
            _assert("C the skip line is on stderr",
                    "skipped: DS_ENROLLMENT_SECRET not set" in p.stderr,
                    "stderr=%r" % p.stderr)
            _assert("C nothing written",
                    not (state / "machine.key").exists(), "machine.key written")
            _assert("C the box was not contacted",
                    studio.requests == [], "requests=%r" % studio.requests)
    finally:
        _cleanup(root)


# --- D: the installer's own secret store ---------------------------------------

def test_d_secret_resolves_from_secrets_env():
    root, home, state = _sandbox(with_env_file=True)
    try:
        with FakeStudio(accept=True) as studio:
            (state / "machine.url").write_text(studio.url + "\n")
            p = _run(home, state, secret=None)  # not in the live process env
            _assert("D the secret was found in ~/.openclaw/secrets/.env",
                    p.returncode == 0 and (state / "machine.key").is_file(),
                    "rc=%d out=%r err=%r" % (p.returncode, p.stdout, p.stderr))
            _assert("D the other key in that file was not mistaken for it",
                    "skipped" not in p.stderr, "stderr=%r" % p.stderr)
    finally:
        _cleanup(root)


# --- E: once per box ------------------------------------------------------------

def test_e_second_run_is_a_no_op():
    root, home, state = _sandbox()
    try:
        with FakeStudio(accept=True) as studio:
            (state / "machine.url").write_text(studio.url + "\n")
            _run(home, state)
            before = len(studio.requests)
            p = _run(home, state)
            _assert("E rc is 0", p.returncode == 0, "rc=%d" % p.returncode)
            _assert("E it says it is already enrolled",
                    "already enrolled" in p.stdout, "stdout=%r" % p.stdout)
            _assert("E no second HTTP request was made",
                    len(studio.requests) == before,
                    "requests went %d -> %d" % (before, len(studio.requests)))
    finally:
        _cleanup(root)


# --- F: the secret never surfaces ------------------------------------------------

def test_f_secret_never_surfaces():
    root, home, state = _sandbox()
    try:
        with FakeStudio(accept=True, delay=0.6) as studio:
            (state / "machine.url").write_text(studio.url + "\n")

            # Instrument control FIRST: prove `ps` can see a secret that IS on a
            # command line, on this box, at this moment. Without this a clean
            # result below would prove nothing about the helper.
            ctrl = subprocess.Popen(
                ["python3", "-c", "import time; time.sleep(1.2)", "argv-control-" + SENTINEL],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            seen_ctrl = _ps_contains(SENTINEL, until=1.2)
            ctrl.wait()
            _assert("F-control ps sees an argv-borne secret",
                    seen_ctrl, "ps never showed the argv control; instrument is blind here")

            # Now the real run: the helper is alive while the fake studio holds
            # the request open, and `ps` is polled across that window.
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                   "HOME": str(home), "DRAMA_STUDIO_STATE": str(state),
                   "DS_ENROLLMENT_SECRET": SENTINEL}
            proc = subprocess.Popen(["bash", HELPER], env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
            seen_live = _ps_contains(SENTINEL, until=1.2)
            out, err = proc.communicate()
            _assert("F the secret is never on a process command line",
                    not seen_live, "ps showed the secret while the helper ran")

            _assert("F the secret is not in stdout or stderr",
                    SENTINEL not in out + err, "leaked: %r %r" % (out, err))
            _assert("F a placeholder secret is not echoed either",
                    "not-set-placeholder" not in
                    _run(home, state, secret="not-set-placeholder").stdout,
                    "placeholder echoed")
            _assert("F the helper never names python's argv with the secret",
                    not re.search(r"enroll[^\n]*" + re.escape(SENTINEL), out + err),
                    "secret appears next to the enroll call")
    finally:
        _cleanup(root)


def _ps_contains(needle, until=1.0):
    """True if `ps` shows `needle` in ANY command line at any poll before deadline."""
    deadline = time.time() + until
    found = False
    while time.time() < deadline:
        listing = subprocess.run(["ps", "-A", "-o", "args="], capture_output=True,
                                 text=True)
        if needle in listing.stdout:
            found = True
            break
        time.sleep(0.02)
    return found


def _cleanup(root):
    import shutil
    shutil.rmtree(root, ignore_errors=True)


def main():
    print("DSR-101 checks for enroll-on-install.sh")
    check_a_enrolls_against_accepting_server()
    test_b_refusal_leaves_box_untouched()
    test_b_control_same_server_would_write()
    test_c_no_secret_skips_cleanly()
    test_d_secret_resolves_from_secrets_env()
    test_e_second_run_is_a_no_op()
    test_f_secret_never_surfaces()
    if _failures:
        print("\n%d FAILED: %s" % (len(_failures), ", ".join(_failures)))
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
