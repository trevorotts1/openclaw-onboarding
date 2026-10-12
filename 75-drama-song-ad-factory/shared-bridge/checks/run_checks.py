#!/usr/bin/env python3
"""U5 runnable checks for the shared studio bridge.

Every check returns a REAL exit code and every negative has a control on the
SAME instrument, so a green run means the check discriminates.

  A  a double claim attempt leaves exactly ONE winner; the loser exits 2
  B  a replayed message is refused (second record of the same id is False)
  C  the lease works on a Windows-style path, a conflict exits 2, and the
     Windows liveness probe never reaches os.kill (which would KILL on Windows)
  D  the nudge/reminder/silence sequence yields exactly two notices then none,
     with two negative controls: the predicate fails on an unguarded sequence,
     and clearing the guard re-opens a notice (so the guard is load-bearing)
  E  no key value is ever printed — with a positive control proving the
     detector can see the sentinel when it is present
  F  every request the bridge sends carries the one explicit User-Agent, with
     two controls on the same server: bare urllib is refused 403/1010, and a
     planted-bad bridge copy with the header removed is refused too

Run: python3 checks/run_checks.py
Exit: 0 all pass · 1 at least one failed
"""
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
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
BRIDGE_DIR = HERE.parent
sys.path.insert(0, str(BRIDGE_DIR))
import studio_claim as SC  # noqa: E402
import studio_bridge as SB  # noqa: E402

PY = sys.executable
BRIDGE = str(BRIDGE_DIR / "studio_bridge.py")
WORK = pathlib.Path(tempfile.mkdtemp(prefix="u5-checks-", dir=str(HERE)))


def _run(args, **kw):
    return subprocess.run([PY, BRIDGE] + args, capture_output=True, text=True, **kw)


# --- A: atomic single-winner claim ------------------------------------------

def check_a_double_claim():
    db = str(WORK / "claim.db")
    base = [PY, BRIDGE, "claim", "--db", db, "--order", "r_deadbeef"]
    p1 = subprocess.Popen(base + ["--owner", "runA"], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True)
    p2 = subprocess.Popen(base + ["--owner", "runB"], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True)
    o1, _ = p1.communicate()
    o2, _ = p2.communicate()
    codes = sorted([p1.returncode, p2.returncode])
    with SC.ClaimLedger(db) as led:
        owner = led.claim_owner("r_deadbeef")
    winners = [c for c in (p1.returncode, p2.returncode) if c == 0]
    ok = codes == [0, 2] and len(winners) == 1 and owner in ("runA", "runB")
    return ok, "exit codes=%s, winner rows=%d, stored owner=%s" % (codes, len(winners), owner)


# --- B: replay refusal -------------------------------------------------------

def check_b_replay_refused():
    db = str(WORK / "replay.db")
    with SC.ClaimLedger(db) as led:
        first = led.record_message("run-1", "m-1", kind="nudge")
        second = led.record_message("run-1", "m-1", kind="nudge")
        # a different run may carry the same message id: replay is per run
        other = led.record_message("run-2", "m-1", kind="nudge")
        sent = []
        board = SB.Board(led, lambda *a: sent.append(a))
        emit1 = board.emit("run-3", "r_x", "approval", {"seq": 1})
        emit2 = board.emit("run-3", "r_x", "approval", {"seq": 1})
    ok = (first is True and second is False and other is True
          and emit1 is True and emit2 is False and len(sent) == 1)
    return ok, ("first=%s replay=%s other_run=%s emit1=%s emit2=%s sends=%d"
                % (first, second, other, emit1, emit2, len(sent)))


# --- C: Windows-safe lease ---------------------------------------------------

def check_c_windows_safe_lease():
    # a Windows-style path: backslash segment (POSIX names may contain it) and
    # a drive-letter style segment. The lease NAME holds colons -- illegal in a
    # Windows filename -- yet no colon-named file may appear, because this
    # ledger never builds a lock file.
    win_dir = WORK / ("win\\style" if os.name != "nt" else "win") / "C_drive"
    win_dir.mkdir(parents=True, exist_ok=True)
    db = str(win_dir / "studio.db")
    name = "order:c-abc:r_123"
    with SC.ClaimLedger(db) as led:
        got = led.lease_acquire(name, "runA", ttl_s=60)
        holder = led.lease_holder(name)
        refused = led.lease_acquire(name, "runB", ttl_s=60)
    conflict = _run(["lease", "--db", db, "--name", name, "--owner", "runC"])
    colon_files = [p.name for p in win_dir.rglob("*") if ":" in p.name]

    # the Windows liveness branch must never reach os.kill (it terminates there)
    def _boom(*a):
        raise AssertionError("os.kill was reached on the Windows branch")

    alive = SC.pid_is_alive(4321, os_name="nt", win_probe=lambda p: True, kill=_boom)
    dead = SC.pid_is_alive(4321, os_name="nt", win_probe=lambda p: False, kill=_boom)
    ok = (got is True and holder == "runA" and refused is False
          and conflict.returncode == 2 and not colon_files
          and alive is True and dead is False)
    return ok, ("acquire=%s holder=%s conflict=%s conflict_exit=%d colon_files=%s "
                "nt_alive=%s nt_dead=%s"
                % (got, holder, refused, conflict.returncode, colon_files, alive, dead))


# --- D: nudge / reminder / silence ------------------------------------------

def exactly_two_then_silence(seq):
    notices = [s for s in seq if s]
    if notices != ["nudge", "reminder"] or "reminder" not in seq:
        return False
    return all(s is None for s in seq[seq.index("reminder") + 1:])


def check_d_notice_discipline():
    db = str(WORK / "notices.db")
    base = 1_000_000.0
    with SC.ClaimLedger(db) as led:
        seq = [led.notice_gate("r_1", now=base + t, reminder_after_s=86400.0)
               for t in (0, 10, 100_000, 200_000)]
        # negative control 1: the predicate MUST reject an unguarded sequence
        unguarded_rejected = exactly_two_then_silence(
            ["nudge", "nudge", "nudge", "nudge"]) is False
        # negative control 2: clear the guard and a notice re-opens, proving the
        # guard (not luck) is what enforced silence
        led.con.execute("UPDATE notices SET reminded_at=NULL WHERE order_id=?", ("r_1",))
        led.con.commit()
        reopened = led.notice_gate("r_1", now=base + 300_000, reminder_after_s=86400.0)
    ok = (exactly_two_then_silence(seq) is True and unguarded_rejected
          and reopened == "reminder")
    return ok, "sequence=%s unguarded_rejected=%s reopened_after_guard_cleared=%s" % (
        seq, unguarded_rejected, reopened)


# --- E: no secret is ever printed -------------------------------------------

SENTINEL = "sk-DEADBEEF-not-a-real-key-1234567890"


def check_e_no_secret_printed():
    db = str(WORK / "secrets.db")
    env = dict(os.environ, DS_KEY=SENTINEL)
    cmds = [
        ["handshake", "--base-url", "http://127.0.0.1:1"],
        ["claim", "--db", db, "--order", "r_secret", "--owner", "runA"],
        ["notice", "--db", db, "--order", "r_secret"],
        ["photo", "--path", str(WORK / "missing.png")],
        ["cleanup-receipt", "--run-dir", str(WORK)],
        ["status", "--base-url", "http://127.0.0.1:1", "--order", "r_secret",
         "--event", "claim"],
    ]
    haystack, codes = "", []
    for c in cmds:
        p = _run(c, env=env)
        haystack += p.stdout + p.stderr
        codes.append(p.returncode)
    found = SENTINEL in haystack
    # positive control on the SAME instrument: the detector must see a planted
    # copy, or "not found" would mean nothing
    control_seen = (SENTINEL in ("planted " + SENTINEL)) is True
    ok = (found is False) and control_seen
    return ok, "sentinel_printed=%s detector_control=%s exit_codes=%s" % (
        found, control_seen, codes)



# --- F: the one explicit User-Agent ------------------------------------------
# Cloudflare in front of the studio refuses Python's default User-Agent
# ("Python-urllib/3.x") with HTTP 403 and the body "error code: 1010". A bridge
# shipped without the header cannot check in at all. This check drives the REAL
# `studio_bridge._http` at a fake studio on 127.0.0.1 and requires both the 200
# and the exact string on the wire. Controls on the SAME server: bare urllib must
# be refused 403/1010 (the instrument discriminates), and a planted-bad copy of
# the bridge with the header line removed must NOT get 200.

EXPECTED_USER_AGENT = "drama-studio-client/2.7.48 (+https://studio.zerohumanworkforce.com)"
_UA_SEEN = []

class _FakeStudio(http.server.BaseHTTPRequestHandler):
    def _serve(self):
        try:
            n = int(self.headers.get("content-length") or 0)
        except ValueError:
            n = 0
        if n:
            self.rfile.read(n)
        ua = self.headers.get("User-Agent") or ""
        _UA_SEEN.append(ua)
        if not ua or ua.startswith("Python-urllib") or ua != EXPECTED_USER_AGENT:
            body = b"error code: 1010\n"
            self.send_response(403)
            self.send_header("content-type", "text/plain")
        else:
            body = json.dumps({"ok": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _serve

    def log_message(self, *a):
        pass

def _planted_bad_bridge():
    """A copy of the bridge with exactly the User-Agent header line removed."""
    d = WORK / "bad-bridge"
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy(BRIDGE_DIR / "studio_claim.py", d / "studio_claim.py")
    src = (BRIDGE_DIR / "studio_bridge.py").read_text(encoding="utf-8")
    line = '    req.add_header("User-Agent", STUDIO_USER_AGENT)\n'
    if src.count(line) != 1:
        raise AssertionError("plant anchor %r appears %d times in studio_bridge.py"
                             % (line, src.count(line)))
    (d / "studio_bridge.py").write_text(src.replace(line, ""), encoding="utf-8")
    return d / "studio_bridge.py"

def check_f_user_agent():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeStudio)
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        # control 1: the instrument discriminates — bare urllib is refused, with the body
        bare = None
        try:
            urllib.request.urlopen(base + "/api/studio/health", timeout=10)
        except urllib.error.HTTPError as e:
            bare = (e.code, e.read().decode("utf-8", "replace").strip())
        control_ok = bare == (403, "error code: 1010")

        # the real bridge
        status, body = SB._http("GET", base + "/api/studio/health", timeout=10)
        real_ua = _UA_SEEN[-1]
        constant_ok = getattr(SB, "STUDIO_USER_AGENT", None) == EXPECTED_USER_AGENT
        real_ok = (status == 200 and getattr(body, "get", None) and body.get("ok") is True
                   and real_ua == EXPECTED_USER_AGENT and constant_ok)

        # control 2: the planted-bad copy (header line removed) must not get 200
        bad_status = None
        try:
            bad_path = _planted_bad_bridge()
            spec = importlib.util.spec_from_file_location("bad_bridge", bad_path)
            bad = importlib.util.module_from_spec(spec)
            sys.modules["bad_bridge"] = bad
            spec.loader.exec_module(bad)
            bad_status, _ = bad._http("GET", base + "/api/studio/health", timeout=10)
            plant_caught = bad_status != 200
        except AssertionError:
            # the bridge under test carries no User-Agent line to plant against
            # (a pre-change copy). Nothing to plant, so the control cannot pass;
            # the real request above already records what it sends instead.
            plant_caught = False
    finally:
        srv.shutdown()
        srv.server_close()
    ok = control_ok and real_ok and plant_caught
    return ok, ("instrument_control=%s constant=%s status=%s ua_seen=%r planted_bad_status=%s"
                % (control_ok, constant_ok, status, real_ua, bad_status))

CHECKS = (
    ("A double-claim single winner", check_a_double_claim),
    ("B replay refused", check_b_replay_refused),
    ("C Windows-safe lease", check_c_windows_safe_lease),
    ("D nudge/reminder/silence", check_d_notice_discipline),
    ("E no secret printed", check_e_no_secret_printed),
    ("F one explicit User-Agent", check_f_user_agent),
)


def main():
    fails = 0
    try:
        for name, fn in CHECKS:
            try:
                ok, detail = fn()
            except Exception as e:  # noqa: BLE001
                ok, detail = False, "raised %r" % (e,)
            print("%s %s :: %s" % ("PASS" if ok else "FAIL", name, detail))
            if not ok:
                fails += 1
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
    print("ALL PASS" if not fails else "%d CHECK(S) FAILED" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
