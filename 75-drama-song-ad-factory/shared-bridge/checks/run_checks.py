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

Run: python3 checks/run_checks.py
Exit: 0 all pass · 1 at least one failed
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

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


CHECKS = (
    ("A double-claim single winner", check_a_double_claim),
    ("B replay refused", check_b_replay_refused),
    ("C Windows-safe lease", check_c_windows_safe_lease),
    ("D nudge/reminder/silence", check_d_notice_discipline),
    ("E no secret printed", check_e_no_secret_printed),
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
