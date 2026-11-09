#!/usr/bin/env python3
"""rc6-box-lock.test.py — mac.MAC-1 / mac.MAC-13 for _BoxLock.

WHAT THIS PROVES (each case RUNS the real class, no source-string assertions):

  T1  acquire() takes the SHARED installation lease as well as the per-box
      marker, so a Python writer and a shell writer see each other.
  T2  release() gives BOTH back.
  T3  a marker whose recorded owner is the same live process (pid + start
      identity) is BUSY — the box is never double-driven.
  T4  a marker whose pid is alive but whose START IDENTITY does not match (a
      recycled pid) is RECLAIMED. Its mtime is set OLD for the same case.
  T5  a marker whose owner is DEAD is RECLAIMED even though its mtime is FRESH.
      T4 and T5 together are the mutation pair: any age-based rule fails one of
      them, and the old 4-hour cutoff and 60-second startup grace both did.
  T6  a LIVE FOREIGN shared lease is honoured: the runner refuses and does not
      displace the record.

Run: python3 -I tests/unit/rc6-box-lock.test.py
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "shared-utils" / "fleet_refresh_runner.py"

PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print("  PASS: " + msg)


def bad(msg):
    global FAIL
    FAIL += 1
    print("  FAIL: " + msg)


def load_runner():
    spec = importlib.util.spec_from_file_location("fleet_refresh_runner", str(RUNNER))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fleet_refresh_runner"] = mod
    spec.loader.exec_module(mod)
    return mod


def start_identity(pid):
    out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                         capture_output=True, text=True).stdout
    return " ".join(out.split())


def write_marker(root, pid, start):
    marker = Path(root) / ".fleet-refresh.lock"
    marker.mkdir(exist_ok=True)
    (marker / "pid").write_text(str(pid))
    if start is not None:
        (marker / "start").write_text(start)
    return marker


def main():
    print("=== rc6-box-lock.test.py ===")
    print("runner: " + str(RUNNER))
    mod = load_runner()

    # ── T1/T2: the shared lease is taken and given back ─────────────────────
    print("")
    print("=== T1/T2 — _BoxLock takes and releases the SHARED lease ===")
    with tempfile.TemporaryDirectory() as tmp:
        lease = Path(tmp) / "shared.lease"
        os.environ["OPENCLAW_UPDATE_LEASE"] = str(lease)
        root = Path(tmp) / "root"
        root.mkdir()
        lock = mod._BoxLock(root)
        err = lock.acquire()
        if err is None:
            ok("T1a: acquire() succeeded on a free box")
        else:
            bad("T1a: acquire() failed: %s" % err)
        if lease.is_file():
            ok("T1b: the SHARED installation lease exists while the box lock is held")
        else:
            bad("T1b: no shared lease was taken — a shell writer could not see this run")
        rec = mod._lease_read(lease) if lease.is_file() else {}
        if rec.get("pid") == str(os.getpid()) and rec.get("role") == "fleet-refresh":
            ok("T1c: the shared record names this process and this role")
        else:
            bad("T1c: shared record is %r" % (rec,))
        marker = root / ".fleet-refresh.lock"
        if (marker / "pid").read_text().strip() == str(os.getpid()) and (marker / "start").is_file():
            ok("T1d: the legacy marker still carries a bare pid (its shell readers do `kill -0`) plus a start identity")
        else:
            bad("T1d: the legacy marker is not readable the way the shell readers expect")
        lock.release()
        if not marker.exists() and not lease.exists():
            ok("T2: release() removed both the marker and the shared lease")
        else:
            bad("T2: release() left %s" % ("the marker" if marker.exists() else "the lease"))

    # ── T3: same live owner → BUSY ──────────────────────────────────────────
    print("")
    print("=== T3 — the same live owner keeps the box locked ===")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["OPENCLAW_UPDATE_LEASE"] = str(Path(tmp) / "shared.lease")
        root = Path(tmp) / "root"
        root.mkdir()
        helper = subprocess.Popen([sys.executable, "-c",
                                   "import time; time.sleep(30)"])
        try:
            time.sleep(0.2)
            write_marker(root, helper.pid, start_identity(helper.pid))
            err = mod._BoxLock(root).acquire()
            if err:
                ok("T3: a marker for a live owner with a matching start identity is BUSY")
            else:
                bad("T3: a live fleet-refresh was NOT detected — two runs would interleave")
        finally:
            helper.kill()
            helper.wait()

    # ── T4/T5: the mutation pair — pid+start, never age ─────────────────────
    print("")
    print("=== T4/T5 — reclaim is proven by the OWNER's death, never by age ===")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["OPENCLAW_UPDATE_LEASE"] = str(Path(tmp) / "shared.lease")
        root = Path(tmp) / "root"
        root.mkdir()
        helper = subprocess.Popen([sys.executable, "-c",
                                   "import time; time.sleep(30)"])
        try:
            time.sleep(0.2)
            m = write_marker(root, helper.pid, "not-this-process")
            os.utime(m, (time.time() - 86400, time.time() - 86400))   # 1 day old
            err = mod._BoxLock(root).acquire()
            if err is None:
                ok("T4: a recycled pid (live, start identity mismatch) is reclaimed even with an OLD mtime")
            else:
                bad("T4: recycled pid NOT reclaimed: %s" % err)
            mod._BoxLock(root).release()
        finally:
            helper.kill()
            helper.wait()
        # T5: dead pid, FRESH mtime
        m = write_marker(root, 999999, "whatever")
        os.utime(m, None)                                             # now
        err = mod._BoxLock(root).acquire()
        if err is None:
            ok("T5: a dead owner's marker is reclaimed even though its mtime is FRESH")
        else:
            bad("T5: dead owner NOT reclaimed: %s" % err)
        mod._BoxLock(root).release()

    # ── T6: a live foreign SHARED lease is honoured ─────────────────────────
    print("")
    print("=== T6 — the runner honours a live foreign shared lease ===")
    with tempfile.TemporaryDirectory() as tmp:
        lease = Path(tmp) / "shared.lease"
        os.environ["OPENCLAW_UPDATE_LEASE"] = str(lease)
        foreign = subprocess.Popen([sys.executable, "-c",
                                    "import time; time.sleep(30)"])
        try:
            time.sleep(0.2)
            lease.write_text(
                "pid=%d\nstart=%s\nrun_id=foreign\nrole=self-update\n"
                "install_path=/x\nutc=x\n" % (foreign.pid, start_identity(foreign.pid)))
            before = lease.read_text()
            root = Path(tmp) / "root"
            root.mkdir()
            err = mod._BoxLock(root).acquire()
            if err and "lease" in err:
                ok("T6a: refused while a foreign updater holds the shared lease")
            else:
                bad("T6a: not refused: %r" % (err,))
            if lease.read_text() == before:
                ok("T6b: the foreign shared record was not displaced")
            else:
                bad("T6b: the foreign shared record was overwritten")
        finally:
            foreign.kill()
            foreign.wait()

    print("")
    print("==========================================")
    print("  PASS: %d  FAIL: %d" % (PASS, FAIL))
    print("==========================================")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
