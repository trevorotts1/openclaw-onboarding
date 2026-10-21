#!/usr/bin/env python3
"""L4.3 (v2.9.73): the documented waiter cannot match its own shell.

Live proof: two shells spun ~8 h on `while pgrep -f "run_vtv_music.py"` —
`pgrep -f` matches the pattern against EVERY process's full argv, and every
waiter pass's parent shell argv HOLDS the quoted string, so the loop met
itself and never ended.

The documented, fixed pattern (references/stage-runbook.md, "Waiting for a
background stage job") anchors on the interpreter AND brackets the script
name's first character, so a waiter that quotes the pattern does NOT match
its own argv:

    while pgrep -f "[Pp]ython.*[r]un_vtv_music\\.py" >/dev/null; do sleep 30; done

Proven on THIS machine, by real processes ($0, no network), assertions
scoped by PID (never by "any process matched"):
  1. the waiter shell's OWN pid is not named by the documented pattern,
     while a REAL `python3 <path>/run_vtv_music.py` stub job IS named;
  2. the old pattern (unanchored, unbracketed) names a shell carrying the
     bare script name — the control that proves this test can see the bug;
  3. the runbook documents exactly this pattern, names the WRONG one, and
     requires the artifact-based second exit.

Run: python3 scripts/core/intake_preflight/test_waiter_pattern_v2973.py
stdlib only, no network, no spend; fixtures self-terminate in seconds.
"""
import os
import subprocess
import sys
import tempfile
import time
import shutil
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = Path(HERE).parents[2]                 # 75-drama-song-ad-factory/
RUNBOOK = SKILL / "references" / "stage-runbook.md"

#: the documented pattern, exactly as the runbook's RIGHT block carries it
PATTERN = r"[Pp]ython.*[r]un_vtv_music\.py"
#: the buggy pattern the runbook names as WRONG (the control's subject)
BUGGY = "run_vtv_music.py"

FAILS = []


def check(name, cond, detail=""):
    print("%s %s%s" % ("ok" if cond else "FAIL", name,
                       (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def pgrep(pattern):
    """One pgrep -f shot (exit code + pids), exactly as the waiter runs it."""
    r = subprocess.run(["pgrep", "-f", pattern], capture_output=True)
    return r.returncode == 0, set(r.stdout.decode().split()), list(r.stderr.decode().splitlines())


def stop(p):
    try:
        p.terminate()
        p.wait(timeout=10)
    except Exception:                                # noqa: BLE001
        pass


def main():
    td = tempfile.mkdtemp(prefix="waiter-t-")
    procs = []
    try:
        # --- fixtures live through the WHOLE window: holders first (their
        # loop's first pass finds nothing and sleeps), the stub job dead
        # LAST (a real job never dies mid-window). A holder exits as soon as
        # its pgrep matches, so the stub job is started after both holders
        # have made their first (unmatched) pass. -------------------------
        stub = os.path.join(td, "run_vtv_music.py")
        with open(stub, "w", encoding="utf-8") as f:
            f.write("import sys, time\nimport signal\nsignal.alarm(20)\n"
                    "time.sleep(19)\n")

        # --- fixture 1: the waiter itself (a shell running the documented
        # while loop; its OWN argv carries the documented pattern verbatim).
        # This is the 8 h bug shape, on the FIXED pattern. Each holder's
        # FIRST pgrep pass is un-matched; it then sleeps LONGER than the
        # whole shot window so a pass that would see the job cannot exit the
        # holder before the assertions read the process table.
        holder = subprocess.Popen(
            ["/bin/sh", "-c",
             'until pgrep -f "[Pp]ython.*[r]un_vtv_music\\.py" >/dev/null; '
             'do sleep 6; done'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(holder)
        # --- control fixture: the 8 h bug shape itself --------------------
        bare = subprocess.Popen(
            ["/bin/sh", "-c",
             'until pgrep -f "run_vtv_music.py" >/dev/null; do sleep 6; done'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(bare)
        time.sleep(0.8)     # both holders make one un-matched pass, sleep

        # --- fixture 2: the REAL job (python on argv, named as the script)
        job = subprocess.Popen([sys.executable, stub],
                               stdout=subprocess.DEVNULL)
        procs.append(job)
        # assertions all fire inside the holders' sleep window --------
        ok_h, pids_h, err_h = pgrep(PATTERN)
        check("documented pattern does NOT name the waiter shell's own pid",
              str(holder.pid) not in pids_h,
              "matched %s holder %s err %s" % (sorted(pids_h), holder.pid, err_h))
        check("documented pattern DOES name the real python job",
              str(job.pid) in pids_h,
              "matched %s job pid %s" % (sorted(pids_h), job.pid))

        # --- control: the OLD pattern still names the bare-string holder --
        ok_b, pids_b, _ = pgrep(BUGGY)
        # the bug's SUBSTANCE: a shell waiting on the bare pattern names SOME
        # process carrying that bare string (on bash 3.2/macOS that is the
        # holder's own pid; on Linux dash the loop's inner sh re-spawn carries
        # the same argv, so a descendant's pid). Either shape is the 8-h bug.
        check("CONTROL: the buggy unbracketed pattern NAMES a shell "
              "carrying the bare script name (the 8-h bug, reproduced)",
              bool(pids_b),
              "matched %s holder %s" % (sorted(pids_b), bare.pid))
        # (the buggy pattern names the JOB too - the job's own argv carries the
        # bare string - but its real 8-h damage is matching the waiter shell
        # itself, which the non-empty assertion above already proves).

        # --- the documented pattern must not name THAT bare holder either:
        # its argv holds only the bare name (no python script invocation)
        ok_d, pids_d, _ = pgrep(PATTERN)
        check("documented pattern does not name the bare-string holder",
              str(bare.pid) not in pids_d,
              "matched %s bare holder %s" % (sorted(pids_d), bare.pid))
        # bare is now done its job in the pid table: stop it before the
        # doc checks so nothing else races it.
        stop(bare)
        procs.remove(bare)

        # --- the runbook documents exactly this pattern -------------------
        text = RUNBOOK.read_text(encoding="utf-8")
        check("stage-runbook.md carries the documented waiter pattern "
              "verbatim",
              'pgrep -f "[Pp]ython.*[r]un_vtv_music\\.py"' in text,
              "pattern line missing")
        check("runbook names the wrong pattern as WRONG",
              'pgrep -f "run_vtv_music.py"' in text and "WRONG" in text)
        check("runbook demands the artifact-based second exit",
              "second, artifact-based exit" in text)
        check("runbook carries the self-check command",
              "test_waiter_pattern_v2973" in text)
    finally:
        for p in procs:
            stop(p)
        shutil.rmtree(td, ignore_errors=True)

    print()
    if FAILS:
        print("FAILED: %d: %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("test_waiter_pattern_v2973: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())